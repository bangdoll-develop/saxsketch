"""SaxSketch FastAPI サーバ。

起動:  python -m saxsketch.server.app  →  http://127.0.0.1:8712
"""
from __future__ import annotations

import asyncio
import os
import platform
import re
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from saxsketch.acoustics import goalseek as gs
from saxsketch.export.bom import bom_csv
from saxsketch.export.models import check_mesh, export_model
from saxsketch.export.package import build_package, readme_text
from saxsketch.export.spec import spec_html
from .state import STATE

app = FastAPI(title="SaxSketch", version="0.1.0")

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# ------------------------------------------------------------------ WSL interop
# SAC 回避のためバックエンドを WSL2(Linux) で動かす。外部ツール連携（Windows 側の
# FreeCAD/エクスプローラ/既定アプリ）は WSL⇄Windows のパス変換と exe 起動が要る。
# Windows ネイティブ実行時は従来どおり動くよう両対応で分岐する。
IS_WSL = "microsoft" in platform.uname().release.lower()


def _to_win_path(p: str) -> str:
    """WSL パス → Windows パス（wslpath -w）。Windows 実行時/失敗時は原文を返す。"""
    if not IS_WSL:
        return str(p)
    try:
        return subprocess.check_output(["wslpath", "-w", str(p)], text=True).strip()
    except Exception:
        return str(p)


def _to_wsl_path(p: str) -> str:
    """Windows パス(C:\\..) → WSL パス(/mnt/c/..)。既に WSL パスなら原文を返す。"""
    if not IS_WSL:
        return str(p)
    try:
        return subprocess.check_output(["wslpath", "-u", str(p)], text=True).strip()
    except Exception:
        return str(p)


def _open_default_app(path: Path) -> None:
    """既定アプリでファイルを開く（spec.html 等）。OS/WSL 差異を吸収。"""
    if IS_WSL:
        subprocess.Popen(["cmd.exe", "/c", "start", "", _to_win_path(str(path))])
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]  # Windows 専用
    else:
        subprocess.Popen(["xdg-open", str(path)])


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
    applied = STATE.apply_params(req.params)
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


# ------------------------------------------------------------------ ファイルダイアログ（ローカルアプリ向け）

_dialog_lock = asyncio.Lock()


def _native_dialog(mode: str, suggested: str) -> str | None:
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if mode == "save":
            path = filedialog.asksaveasfilename(
                title="プロジェクトを保存", defaultextension=".wproj",
                initialfile=suggested,
                filetypes=[("SaxSketch プロジェクト", "*.wproj")])
        elif mode == "open":
            path = filedialog.askopenfilename(
                title="プロジェクトを開く",
                filetypes=[("SaxSketch プロジェクト", "*.wproj")])
        elif mode == "open_model":
            kwargs = {"initialdir": suggested} if suggested and Path(suggested).is_dir() else {}
            path = filedialog.askopenfilename(
                title="編集済みモデルを取込",
                filetypes=[("3Dモデル", "*.stl *.step *.stp *.3mf *.obj *.ply"),
                           ("すべて", "*.*")],
                **kwargs)
        else:  # dir
            path = filedialog.askdirectory(title="出力先フォルダを選択")
        return path or None
    finally:
        root.destroy()


class DialogReq(BaseModel):
    mode: str  # save | open | dir
    suggested: str = ""


@app.post("/api/dialog")
async def dialog(req: DialogReq):
    async with _dialog_lock:
        try:
            path = await asyncio.to_thread(_native_dialog, req.mode, req.suggested)
        except Exception:
            path = None  # tkinter 不可の環境ではフロント側でパス手入力にフォールバック
    return {"path": path}


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


@app.get("/api/model/regions")
def model_regions():
    """各パラメータの影響領域（3Dハイライト用）。現在のパラメータ値で計算。"""
    _require_project()
    return STATE.component.regions(dict(STATE.paramset.values))


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
    base = Path(req.out_dir) if req.out_dir else \
        Path(STATE.settings.get("export_root", str(Path.home() / "Documents" / "SaxSketch")))
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
    for fmt in req.formats:
        f = out_dir / f"model.{fmt}"
        if fmt == "stl" and used_derived:
            f = out_dir / "model_edited.stl"
            f.write_bytes(derived_stl)
            files["model_edited.stl"] = f
            continue
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
        raise HTTPException(
            status_code=400,
            detail=f"{req.tool} の実行パスが未設定です。設定画面で登録してください。")
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


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8712)


if __name__ == "__main__":
    main()
