"""SaxSketch FastAPI サーバ。

起動:  python -m saxsketch.server.app  →  http://127.0.0.1:8712
       （8712 占有時は WF_PORT で上書き、または空きポートへ自動退避）
"""
from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import os
import re
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from saxsketch.acoustics import goalseek as gs
from saxsketch.export.bom import bom_csv
from saxsketch.export.models import check_mesh, export_model
from saxsketch.export.package import build_package, readme_text
from saxsketch.export.spec import spec_html
from . import filedialog
from .hostenv import IS_WSL, host_kind
from .hostenv import to_win_path as _to_win_path
from .hostenv import to_wsl_path as _to_wsl_path
from .state import STATE

@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI):
    """CAD ビルド用の子プロセスを先に上げておく。

    build123d の import に 2〜3 秒かかるので、最初の 3D 表示にそれを払わせない。
    上がらない環境（`SAXSKETCH_NO_BUILD_WORKER=1` やテスト）でも黙って親側の
    経路に落ちるだけなので、ここでは失敗を握りつぶしてよい。
    """
    from .buildworker import WORKER
    await asyncio.to_thread(WORKER.start)
    try:
        yield
    finally:
        WORKER.stop()


app = FastAPI(title="SaxSketch", version="0.1.0", lifespan=_lifespan)

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# ------------------------------------------------------------------ WSL interop
# SAC 回避のためバックエンドを WSL2(Linux) で動かす。外部ツール連携（Windows 側の
# FreeCAD/エクスプローラ/既定アプリ）は WSL⇄Windows のパス変換と exe 起動が要る。
# Windows ネイティブ実行時は従来どおり動くよう両対応で分岐する。
#
# 実体は `hostenv.py`。`filedialog.py` と `state.py` も要るので切り出した
# （この app が filedialog を import するので、逆向きは循環になる）。
# 旧来の `app.IS_WSL` を見ている呼び出し（`scripts/wsl_sync.sh`）のため名前は残す。


def _open_default_app(path: Path) -> None:
    """既定アプリでファイルを開く（spec.html 等）。OS/WSL 差異を吸収。"""
    if IS_WSL:
        subprocess.Popen(["cmd.exe", "/c", "start", "", _to_win_path(str(path))])
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]  # Windows 専用
    else:
        subprocess.Popen(["xdg-open", str(path)])


# 外部ツールの既定インストール先（設定未登録時の自動検出用）。glob で版・大小文字を吸収。
_TOOL_DEFAULTS = {
    "freecad": [
        "/mnt/c/Program Files/FreeCAD*/bin/[Ff]reeCAD.exe",
        "/mnt/c/Program Files/FreeCAD*/bin/freecad.exe",
    ] if IS_WSL else [
        "C:/Program Files/FreeCAD*/bin/FreeCAD.exe",
    ],
}


def _detect_tool_path(tool: str) -> str:
    """設定にパス未登録のとき既定インストール先を走査。見つからなければ空。"""
    from glob import glob
    for pattern in _TOOL_DEFAULTS.get(tool, []):
        hits = sorted(glob(pattern))
        if hits:
            return hits[-1]  # 版が複数なら新しい方（辞書順末尾）
    return ""


def _reveal_in_explorer(path: Path) -> None:
    """ファイルマネージャでファイルを選択表示。"""
    if IS_WSL:
        subprocess.Popen(["explorer.exe", "/select,", _to_win_path(str(path))])
    elif os.name == "nt":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:  # Linux ネイティブ: 親フォルダを開く（/select 相当は環境依存）
        subprocess.Popen(["xdg-open", str(path.parent)])


def _require_project():
    if STATE.project is None:
        raise HTTPException(status_code=409, detail="プロジェクトが開かれていません")


# ------------------------------------------------------------------ 楽器・プロジェクト

@app.get("/api/instruments")
def instruments():
    return STATE.registry.summaries()


class NewProject(BaseModel):
    instrument_id: str
    template_id: str
    component_id: str
    name: str | None = None


@app.post("/api/project/new")
def project_new(req: NewProject):
    inst = STATE.registry.get(req.instrument_id)
    cls = inst.component_classes.get(req.component_id)
    if cls is None or not cls.available():
        raise HTTPException(status_code=400,
                            detail="このコンポーネントは未実装です（後フェーズで追加予定）")
    STATE.new_project(req.instrument_id, req.template_id, req.component_id, req.name)
    return project_get()


@app.get("/api/project")
def project_get():
    _require_project()
    p = STATE.project
    return {
        "name": p.name,
        "notes": p.notes,
        "path": p.path,
        "instrument_id": p.instrument_id,
        "template_id": p.template_id,
        "component_id": p.component_id,
        "component_label": STATE.component.label,
        "params": STATE.paramset.values,
        "schema": STATE.paramset.schema_dicts(),
        "simulation": STATE.simulate(),
        "manual_edit": STATE.manual_edit_summary(),
        "reference": STATE.reference_summary(),
        "survey": STATE.survey_state(),
        # 旧プロジェクトを開いたときの変換報告（`Component.migrate_params`）。
        # 黙って値が変わらないための経路なので、パラメータを触るまで残る。
        "notices": STATE.notices,
    }


class ReferenceReq(BaseModel):
    component: str = "mouthpiece"
    path: str | None = None   # None = テンプレート既定値へ戻す


@app.post("/api/project/reference")
def project_reference(req: ReferenceReq):
    """参照コンポーネント（リード/リガチャーが従属するマウスピース）を差し替える。"""
    _require_project()
    if req.path is not None and not Path(req.path).exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    try:
        STATE.set_reference(req.component, req.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"読み込み失敗: {e}")
    return project_get()


class ParamUpdate(BaseModel):
    params: dict


@app.put("/api/project/params")
def project_params(req: ParamUpdate):
    _require_project()
    try:
        applied = STATE.apply_params(req.params)
    except ValueError as e:
        # 値の組が形状として成立しない。前の値のまま据え置かれているので、
        # フロントは理由を出してスライダーを戻すだけでよい。
        raise HTTPException(status_code=400, detail=str(e))
    return {"params": applied, "simulation": STATE.simulate(),
            "stale": STATE.is_stale()}


class MetaUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None


@app.put("/api/project/meta")
def project_meta(req: MetaUpdate):
    _require_project()
    if req.name is not None:
        STATE.project.name = req.name
    if req.notes is not None:
        STATE.project.notes = req.notes
    return {"ok": True}


class PathReq(BaseModel):
    path: str


@app.post("/api/project/save")
def project_save(req: PathReq):
    _require_project()
    path = req.path
    if not path.lower().endswith(".wproj"):
        path += ".wproj"
    STATE.save_project(path)
    return {"ok": True, "path": path}


@app.post("/api/project/open")
def project_open(req: PathReq):
    if not Path(req.path).exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    try:
        STATE.open_project(req.path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"読み込み失敗: {e}")
    return project_get()


@app.get("/api/recent")
def recent():
    return [p for p in STATE.settings.get("recent_projects", []) if Path(p).exists()]


# ------------------------------------------------------------------ ファイルダイアログ（ローカル同居時のみ）
# ダイアログは **サーバのデスクトップ** に出る。サーバと利用者が同じ机に居るときだけ
# 意味があるので、出せるかどうかを `/api/capabilities` で宣言し、UI が分岐する。
# 実装は `filedialog.py`（必ず別プロセス。理由はそちらの docstring）。

_dialog_lock = asyncio.Lock()

#: ダイアログの順番待ちの上限 [秒]。`filedialog.pick` 自体にも時間切れがあるので
#: 本来ここで詰まることは無いが、待ち行列が伸びたまま返らない状態を作らない。
_DIALOG_QUEUE_TIMEOUT = 200.0


def _is_local_client(request: Request) -> bool:
    """リクエスト元が同じ機械か。

    WSL 構成でも Windows のブラウザからは localhost 転送で 127.0.0.1 に見える。
    LAN やトンネル越しに公開したときは非ループバックになるので、その場合は
    「サーバの机の前に誰も居ない」とみなしてダイアログを出さない。
    """
    if os.environ.get("SAXSKETCH_FORCE_REMOTE"):
        return False
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@app.get("/api/capabilities")
def capabilities(request: Request):
    """この稼働環境で UI が使ってよい機能。

    `native_dialogs` が false のときフロントはパス入力へ落ちる。ダイアログを
    「出したのに誰も見えない」状態が、利用者からはフリーズと区別できないため。
    """
    return {
        "native_dialogs": _is_local_client(request) and filedialog.available(),
        "host": host_kind(),
        "export_root": str(STATE.export_root()),
    }


class DialogReq(BaseModel):
    mode: str  # save | open | open_model | dir
    suggested: str = ""


@app.post("/api/dialog")
async def dialog(req: DialogReq, request: Request):
    """OS のファイルダイアログ。`{"path": …, "reason": …}` を返す。

    `reason` は UI の分岐用（`filedialog.pick` を参照）。**例外にはしない**。
    出せないことは異常ではなく、手入力に落ちるだけの通常経路。
    """
    if not _is_local_client(request):
        return {"path": None, "reason": "unavailable"}
    try:
        await asyncio.wait_for(_dialog_lock.acquire(), _DIALOG_QUEUE_TIMEOUT)
    except asyncio.TimeoutError:
        return {"path": None, "reason": "timeout"}
    try:
        path, reason = await filedialog.pick(req.mode, req.suggested)
    finally:
        _dialog_lock.release()
    return {"path": path, "reason": reason}


# ------------------------------------------------------------------ モデル・シミュレーション

@app.get("/api/model.stl")
async def model_stl(quality: str = "preview"):
    _require_project()
    tol = 0.05 if quality == "preview" else 0.02
    try:
        data = await asyncio.to_thread(STATE.get_stl_bytes, tol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"形状生成に失敗: {e}")
    return Response(content=data, media_type="application/octet-stream")


@app.get("/api/ref/model.stl")
async def ref_model_stl():
    """重ね表示用の参照コンポーネント（リガチャー → マウスピース）の STL。

    **参照が無い／座標系が違うコンポーネントでは 404。** フロントは
    `reference.overlay` を見てトグルを出すので、ここへ来るのは本来その 1 通りだけ。

    品質はプレビュー固定。位置関係を見るための表示で、寸法を測る用途には出さない。
    URL の `?v=` は**サーバは見ない**（ブラウザのキャッシュ鍵としてだけ付く。
    実体の鍵は `AppState.ref_hash()`）。
    """
    _require_project()
    if not getattr(STATE.component, "REF_SHARES_FRAME", False):
        raise HTTPException(status_code=404,
                            detail="このコンポーネントは参照を重ねて表示できません")
    try:
        data = await asyncio.to_thread(STATE.ref_stl_bytes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"形状生成に失敗: {e}")
    return Response(content=data, media_type="application/octet-stream")


@app.get("/api/model/regions")
def model_regions():
    """各パラメータの影響領域（3Dハイライト用）。現在のパラメータ値で計算。"""
    _require_project()
    return STATE.component.regions(dict(STATE.paramset.values))


@app.get("/api/dimensions")
def model_dimensions():
    """パラメータの寸法（3D の図示用）。**CAD ビルドを伴わない**。

    `/api/model/regions` と同じ形（引数なし・現在値）。断面のドラッグ中に
    追従させる側は `/api/section` の `dimensions` が運ぶ（定義は同じ 1 か所）。
    寸法を持たないコンポーネントは `[]`。UI はそれを見てトグルを出さない。
    """
    _require_project()
    return STATE.component.dimensions(dict(STATE.paramset.values))


@app.get("/api/section")
def model_section(request: Request):
    """中央面の断面とドラッグハンドル。**CAD ビルドを伴わない**。

    ドラッグ中に毎フレーム叩かれるので、形状法則の数値計算だけで返す
    （3D の再生成は従来どおりデバウンスされた `/api/model.stl` のまま）。
    断面を持たないコンポーネントでは 404 を返し、UI は断面タブを出さない。

    クエリでパラメータを渡すと「**もしこの値にしたら**」の断面を返す（ドラッグ中の
    プレビュー用）。プロジェクトの状態は変えないので、確定は従来どおり
    `PUT /api/project/params` で行う。検証は通常の適用と同じ `ParamSpec.validate`。
    """
    _require_project()
    values = dict(STATE.paramset.values)
    for k, v in request.query_params.items():
        spec = STATE.paramset.specs.get(k)
        if spec is None:
            continue
        # 数値に読めないクエリは無視して現在値のままにする（500 にしない）。
        with contextlib.suppress(ValueError, TypeError):
            values[k] = spec.validate(v)
    data = STATE.component.section(values)
    if data is None:
        raise HTTPException(status_code=404, detail="このコンポーネントに断面編集はありません")
    # 寸法はここで**ルート側が**足す。断面を持つ部品が増えたときに
    # `section()` の中へ書き足し忘れる経路を作らないため（定義は `dimensions()`
    # の 1 か所のまま）。ドラッグ中のクエリ上書きがそのまま効くので、寸法は
    # 形と同じフレームで動く。
    data["dimensions"] = STATE.component.dimensions(values)
    return data


class GoalSeekReq(BaseModel):
    targets: dict


@app.post("/api/project/goalseek")
async def goal_seek(req: GoalSeekReq):
    _require_project()
    comp = STATE.component
    result = await asyncio.to_thread(
        gs.goal_seek, dict(STATE.paramset.values), comp.param_specs(),
        req.targets, comp.goal_seek_size_info(), comp.cavity_volume)
    return result


# ------------------------------------------------------------------ 外部編集（凍結・再取込）

@app.post("/api/manual/unfreeze")
def manual_unfreeze():
    _require_project()
    return STATE.unfreeze()


@app.post("/api/manual/import")
async def manual_import(req: PathReq):
    """編集済みモデルの解析（プレビュー。まだ登録しない）。"""
    _require_project()
    if STATE.project.frozen is None:
        raise HTTPException(status_code=409,
                            detail="先に「凍結して編集用エクスポート」を実行してください")
    if not Path(req.path).exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    try:
        return await asyncio.to_thread(STATE.analyze_derived, req.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析に失敗しました: {e}")


@app.post("/api/external/load")
async def external_load(req: PathReq):
    """外部（市販完成品など本アプリ非由来）の3Dモデルを読み込み、整列・採寸する。

    凍結不要。差分/逆算はしない（座標系が別物で無意味）。表示・入稿用の派生候補として
    保持し、/api/manual/commit で登録すると「取込モデル」タブで表示・エクスポートできる。
    """
    _require_project()
    if not Path(req.path).exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    try:
        return await asyncio.to_thread(STATE.load_external, req.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"読み込みに失敗しました: {e}")


@app.post("/api/manual/commit")
def manual_commit():
    """解析済みモデルをプロジェクトに登録。"""
    _require_project()
    try:
        return STATE.commit_derived()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/manual/discard")
def manual_discard():
    _require_project()
    return STATE.discard_derived()


@app.get("/api/manual/model.stl")
def manual_model():
    _require_project()
    stl = STATE.project.derived_stl
    if stl is None:
        raise HTTPException(status_code=404, detail="編集済みモデルは未登録です")
    return Response(content=stl, media_type="application/octet-stream")


# ------------------------------------------------------------------ 採寸ワークフロー（Phase 4-A）

@app.get("/api/survey")
def survey_get():
    _require_project()
    return STATE.survey_state()


@app.post("/api/survey/measure")
async def survey_measure(req: PathReq):
    """外部3Dモデル（3mf/STL/STEP）から採寸ターゲットを実測しプレフィル値を返す。

    commit はしない（ユーザーが確認・修正のうえ /api/survey/commit で反映）。
    """
    _require_project()
    f = Path(req.path)
    if not f.exists():
        raise HTTPException(status_code=404, detail="ファイルが存在しません")

    def _run():
        from saxsketch.analysis import meshdiff
        mesh = meshdiff.load_mesh(str(f))
        result = STATE.component.survey_measure_mesh(mesh)
        result["quality"] = meshdiff.mesh_quality(mesh)
        return result
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"測定に失敗: {e}")


class SurveyCommitReq(BaseModel):
    measured: dict = {}       # 設計パラの実測 {key: value}
    measured_size: dict = {}  # 音響基準定数の実測 {key: value}
    note: str = ""


@app.post("/api/survey/commit")
def survey_commit(req: SurveyCommitReq):
    """採寸値を反映し、復元点を記録する。反映後のプロジェクト全体を返す。"""
    _require_project()
    try:
        STATE.survey_commit(req.measured, req.measured_size, req.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return project_get()


@app.post("/api/survey/revert")
def survey_revert():
    """採寸チェックポイントへ復元する。"""
    _require_project()
    try:
        STATE.survey_revert()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return project_get()


@app.post("/api/survey/clear")
def survey_clear():
    """採寸ブロックと音響基準の上書きを破棄する。"""
    _require_project()
    STATE.survey_clear()
    return project_get()


# ------------------------------------------------------------------ エクスポート

class ExportReq(BaseModel):
    formats: list[str] = ["stl", "step", "3mf"]
    out_dir: str | None = None
    make_package: bool = True
    freeze: bool = False        # 出力と同時に凍結スナップショット記録（外部編集用）
    use_derived: bool = True    # 派生モデル登録済みなら STL をそれに差し替え


def _safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "project"


@app.post("/api/export")
async def export(req: ExportReq):
    _require_project()
    proj = STATE.project
    comp = STATE.component
    params = dict(STATE.paramset.values)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = Path(req.out_dir) if req.out_dir else STATE.export_root()
    out_dir = base / f"{_safe_name(proj.name)}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    part = await asyncio.to_thread(STATE.build_part)

    # 派生モデル（外部編集済み）があれば STL はそれを採用（陳腐化していなければ）
    used_derived = False
    derived_stl = STATE.project.derived_stl
    if req.use_derived and derived_stl is not None:
        if STATE.is_stale():
            raise HTTPException(
                status_code=409,
                detail="凍結後にパラメータが変更されています。編集済みモデルは古い形状です。"
                       "外部編集をやり直すか、派生モデルを破棄してください。")
        used_derived = True

    files: dict[str, Path] = {}
    part_cad = None
    for fmt in req.formats:
        f = out_dir / f"model.{fmt}"
        if fmt == "stl" and used_derived:
            f = out_dir / "model_edited.stl"
            f.write_bytes(derived_stl)
            files["model_edited.stl"] = f
            continue
        # STEP だけは面を1枚ずつに畳んだ表現で出す（FreeCAD での面選択・フィレット用）。
        # 生成に十数秒かかるので、STEP を要求されたときだけ組む。
        if fmt == "step":
            if part_cad is None:
                part_cad = await asyncio.to_thread(STATE.build_part_cad)
            await asyncio.to_thread(export_model, part_cad, f, fmt)
        else:
            await asyncio.to_thread(export_model, part, f, fmt)
        files[f"model.{fmt}"] = f

    quality = None
    stl_key = "model_edited.stl" if used_derived else "model.stl"
    if stl_key in files:
        quality = check_mesh(files[stl_key])

    inst = STATE.registry.get(proj.instrument_id)
    extras = comp.spec_extras(params)
    sim = STATE.simulate()
    bom_rows = comp.bom(params)

    html = spec_html(
        project_name=proj.name,
        instrument_label=inst.descriptor.get("label", proj.instrument_id),
        component_label=comp.label,
        template_label=inst.templates[proj.template_id].get("label", proj.template_id),
        params=params, specs=comp.param_specs(),
        dimensions=extras.get("dimensions", []),
        bom_rows=bom_rows, sim=sim,
        sections=extras.get("sections", []),
        material=params.get("material", "resin"))
    (out_dir / "spec.html").write_text(html, encoding="utf-8")
    files["spec.html"] = out_dir / "spec.html"

    csv_text = bom_csv(bom_rows, proj.name)
    (out_dir / "bom.csv").write_bytes(csv_text.encode("utf-8-sig"))
    files["bom.csv"] = out_dir / "bom.csv"

    package_path = None
    if req.make_package:
        mat_label = {"resin": "レジン(光造形)", "pla": "PLA", "petg": "PETG",
                     "nylon_sls": "ナイロンPA12(SLS)"}.get(params.get("material"), "-")
        readme = readme_text(proj.name, extras.get("dimensions", []), mat_label)
        if used_derived:
            readme += ("\n\n[外部編集済みモデル]\n"
                       "model_edited.stl は外部ツールで手動編集したモデルです。\n"
                       "印刷にはこのファイルを使用してください。\n"
                       f"編集元: {STATE.project.derived.get('source_file', '-')}\n")
        package_path = out_dir / f"{_safe_name(proj.name)}_入稿パッケージ.zip"
        build_package(package_path, {k: v for k, v in files.items()}, readme)

    # 凍結: STEP出力とセットでスナップショット記録（外部編集ワークフローの起点）
    manual_edit = None
    if req.freeze:
        vol_cc = float(part.volume / 1000.0)
        manual_edit = STATE.freeze(str(out_dir), round(vol_cc, 2))

    return {
        "out_dir": str(out_dir),
        "files": {k: str(v) for k, v in files.items()},
        "package": str(package_path) if package_path else None,
        "mesh_quality": quality,
        "used_derived": used_derived,
        "manual_edit": manual_edit,
    }


# ------------------------------------------------------------------ 音響（Tier3, Phase2）

@app.get("/api/acoustics/impedance")
def acoustics_impedance():
    _require_project()
    try:
        return STATE.impedance()
    except Exception as e:  # 音響を持たないコンポーネント / OpenWind 不在
        raise HTTPException(status_code=422, detail=str(e))


def _wav_response(wav: bytes, meta: dict) -> Response:
    """WAV 本体＋実測結果ヘッダ。音高は指定できないので鳴った音を返す。"""
    def ascii_(v) -> str:  # HTTP ヘッダは latin-1 しか通らない
        return str(v).encode("ascii", "replace").decode("ascii")

    return Response(content=wav, media_type="audio/wav", headers={
        "X-Played-F0": ascii_(meta.get("f0", "")),
        "X-Played-Note": ascii_(meta.get("note", "")),
        "X-Mouth-Pa": ascii_(meta.get("mouth_pa", "")),
        "X-Embouchure": ascii_(meta.get("embouchure", "")),
    })


@app.get("/api/acoustics/sound.wav")
def acoustics_sound(embouchure: str = "normal"):
    _require_project()
    try:
        wav, meta = STATE.synthesize_wav(embouchure)
    except Exception as e:  # OpenWind 未導入/失敗 → フロントは印象合成へ退避
        raise HTTPException(status_code=422, detail=str(e))
    return _wav_response(wav, meta)


@app.get("/api/acoustics/scale.wav")
def acoustics_scale():
    _require_project()
    try:
        wav, meta = STATE.scale_wav()
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _wav_response(wav, meta)




# ------------------------------------------------------------------ 外部ツール連携

class ToolReq(BaseModel):
    tool: str          # freecad | slicer | reveal | browser
    file: str


@app.post("/api/tools/open")
def tools_open(req: ToolReq):
    f = Path(req.file)
    if not f.exists():
        raise HTTPException(status_code=404, detail="ファイルが存在しません")
    if req.tool == "reveal":
        _reveal_in_explorer(f)
        return {"ok": True}
    if req.tool == "browser":
        _open_default_app(f)  # 既定アプリ（spec.html など）
        return {"ok": True}
    tool_path = STATE.settings.get("external_tools", {}).get(req.tool, "")
    if not tool_path:
        tool_path = _detect_tool_path(req.tool)  # 既定インストール先を自動検出
    if not tool_path:
        raise HTTPException(
            status_code=400,
            detail=f"{req.tool} が見つかりません。設定画面で実行パスを登録してください。")
    # WSL: 設定値が Windows パス(C:\..\FreeCAD.exe)でも WSL パスへ変換して exec。
    # 渡すファイル引数は Windows 側ツールが読めるよう Windows パスへ変換。
    exe = _to_wsl_path(tool_path) if IS_WSL else tool_path
    file_arg = _to_win_path(str(f)) if IS_WSL else str(f)
    if not Path(exe).exists():
        raise HTTPException(
            status_code=400,
            detail=f"{req.tool} の実行ファイルが見つかりません: {tool_path}")
    subprocess.Popen([exe, file_arg])
    return {"ok": True}


@app.get("/api/settings")
def settings_get():
    return STATE.settings


class SettingsReq(BaseModel):
    settings: dict


@app.put("/api/settings")
def settings_put(req: SettingsReq):
    STATE.settings.update(req.settings)
    STATE.save_settings()
    return STATE.settings


# ------------------------------------------------------------------ フロントエンド静的配信

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIST / "index.html")


def _in_use(host: str, port: int) -> bool:
    """port で誰かが listen していれば True。bind 可否ではなく接続可否で見る。

    bind の成否は Windows と Linux で SO_REUSEADDR/SO_EXCLUSIVEADDRUSE の意味が
    違って当てにならない。connect_ex==0 で「誰かが listen 中」はどちらでも確実。
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _is_saxsketch(host: str, port: int) -> bool:
    """占有主が SaxSketch 自身か。/api/instruments が 200 を返すかで判定。"""
    from urllib.error import URLError
    from urllib.request import urlopen
    try:
        with urlopen(f"http://{host}:{port}/api/instruments", timeout=0.7) as r:
            return r.status == 200
    except (URLError, OSError):
        return False


def _free_port(host: str, start: int, tries: int = 20) -> int | None:
    """start から連番で最初の空きを返す。無ければ None。"""
    for p in range(start, start + tries):
        if not _in_use(host, p):
            return p
    return None


def main():
    import sys

    import uvicorn

    # 起動メッセージに ▶ ✔ ⚠ を使っている。Windows の既定コンソール（cp932）だと
    # ここで UnicodeEncodeError を出して**サーバが起動する前に落ちる**ので、
    # 出力の符号化だけ先に UTF-8 へ寄せる（端末が出せない字は置換に任せる）。
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")

    host = os.environ.get("WF_HOST", "127.0.0.1")
    want = int(os.environ.get("WF_PORT", "8712"))

    if _in_use(host, want):
        if _is_saxsketch(host, want):
            print(f"✔ SaxSketch は既に起動中 → http://{host}:{want} を開いてください")
            return
        port = _free_port(host, want + 1)
        if port is None:
            print(f"✗ {want} が使用中で、近傍にも空きポートがありません。"
                  f"占有元を止めるか WF_PORT で別ポートを指定してください。", file=sys.stderr)
            sys.exit(1)
        print(f"⚠ ポート {want} は使用中。空いている {port} で起動します。")
    else:
        port = want

    print(f"▶ SaxSketch → http://{host}:{port} （停止: Ctrl+C）")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
