"""SaxSketch FastAPI サーバ。

起動:  python -m saxsketch.server.app  →  http://127.0.0.1:8712
       （8712 占有時は SAX_PORT で上書き、または空きポートへ自動退避）
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
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from saxsketch.acoustics import goalseek as gs
from saxsketch.export.bom import bom_csv, bom_csv_set
from saxsketch.export.models import check_mesh, export_model
from saxsketch.export.package import build_package, readme_text, readme_text_set
from saxsketch.export.spec import spec_html, spec_html_set
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


# ------------------------------------------------------------------ 外から触られない
#
# このサーバは「自分の机の上のデスクトップアプリ」で、API は任意の絶対パスを
# 読み書きし、外部ツールを起動する。**それは設計であって欠陥ではない** ——
# 入口は OS のファイルダイアログで、利用者が自分で選んだ絶対パスが返ってくる。
# パスをルート配下へ閉じ込めると製品が壊れるので、守るのはパスではなく
# **誰がこの API を叩けるか** のほう。
#
# ブラウザから外へ開いてしまう経路は 2 つしかない:
#
#   1. **DNS リバインディング** —— 悪意あるページが自分のドメインを 127.0.0.1 へ
#      張り替えると、ブラウザはこのサーバを同一オリジンとみなすので CORS が
#      効かなくなる。このとき `Host:` は攻撃者のドメインのままなので、
#      **サーバが自分の名前を知っていれば弾ける**。
#   2. **クロスサイトの単純リクエスト** —— preflight の要らない形。
#      `Sec-Fetch-Site` を見れば弾ける。
#
# ローカルに閉じている限りこの 2 つで足りるので、認証トークンは置かない ——
# トークンをフロントへ渡す経路のほうが新しい弱点になる。

#: `Host:` に来てよい名前（ポートは落として比較する）。
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})

#: ループバック以外へ出すことを明示的に許すスイッチ。
#: LAN へ出す＝**認証の無いファイルシステム API を公開する**ことなので、
#: 既定では `main()` が起動そのものを断る。立てるとこの検査も丸ごと外れる。
ALLOW_REMOTE = bool(os.environ.get("SAX_ALLOW_REMOTE"))


def _host_name(header: str) -> str:
    """`Host:` からポートを落とす。IPv6 の `[::1]:8712` も剥く。"""
    h = (header or "").strip().lower()
    if h.startswith("["):
        return h[:h.index("]") + 1] if "]" in h else h
    if h.count(":") > 1:
        return h          # 角括弧の無い素の IPv6（curl -g など）。ポートは付かない
    return h.rsplit(":", 1)[0] if ":" in h else h


def _refuse(status: int, why: str) -> Response:
    return Response(status_code=status, content=why,
                    media_type="text/plain; charset=utf-8")


@app.middleware("http")
async def _local_only(request: Request, call_next):
    """他所のページから叩かれたリクエストを落とす（上のコメントの実装）。

    ヘッダが**無い**ときは通す。curl・テスト・古いブラウザが該当するが、
    守る相手は「利用者のブラウザで動く他人のページ」であって、ヘッダを
    送ってこない相手はもうローカルの権限を持っている。
    """
    if not ALLOW_REMOTE:
        host = _host_name(request.headers.get("host", ""))
        if host and host not in _LOCAL_HOSTS:
            return _refuse(400, "Host %r は許可されていません。"
                                "SaxSketch はローカル専用です。" % host)
    if request.headers.get("sec-fetch-site", "") in ("cross-site", "same-site"):
        return _refuse(403, "他のサイトからは操作できません。")
    return await call_next(request)


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

#: 殻が読み込んでいるモジュールスクリプトの名前。Vite が内容ハッシュを付けるので、
#: これが**そのビルドの世代**そのものになる。
_ASSET_RE = re.compile(r'<script[^>]+src="/assets/([^"]+\.js)"')


def frontend_asset() -> str | None:
    """いま配っているアプリの世代（`index-XXXX.js`）。dist が無ければ None。

    **ビルド時に何も仕込まない** —— `index.html` の実物から読む。別に埋め込むと
    「実際に配っている物」と「世代を名乗る値」が別々に古くなれるので、
    食い違いを検出するための値が自分で食い違える。
    """
    try:
        html = (FRONTEND_DIST / "index.html").read_text(encoding="utf-8")
    except OSError:
        return None
    m = _ASSET_RE.search(html)
    return m.group(1) if m else None


# ------------------------------------------------------------------ WSL interop
# SAC 回避のためバックエンドを WSL2(Linux) で動かす。外部ツール連携（Windows 側の
# FreeCAD/エクスプローラ/既定アプリ）は WSL⇄Windows のパス変換と exe 起動が要る。
# Windows ネイティブ実行時は従来どおり動くよう両対応で分岐する。
#
# 実体は `hostenv.py`。`filedialog.py` と `state.py` も要るので切り出した
# （この app が filedialog を import するので、逆向きは循環になる）。
# 旧来の `app.IS_WSL` を見ている呼び出し（`scripts/wsl_sync.sh`）のため名前は残す。


#: `tool="browser"` で既定アプリに渡してよい拡張子。
#:
#: `os.startfile` と `cmd /c start` は**拡張子の関連付けで実行する**ので、
#: `.bat` `.ps1` `.hta` `.lnk` を渡せばそれが走る。渡すのはアプリ自身が
#: 書き出した物だけのはずなので、その形式に限る（禁止リストではなく許可リスト
#: にするのは、関連付けで実行される拡張子を数え上げきれないから）。
_OPENABLE_SUFFIXES = frozenset({
    ".html", ".htm", ".csv", ".zip", ".svg", ".txt", ".md", ".json",
    ".stl", ".step", ".stp", ".3mf", ".wav", ".png", ".pdf",
})


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
    component_id: str | None = None   # 単体プロジェクト
    set_id: str | None = None         # セット（descriptor の sets[].id）
    name: str | None = None


@app.post("/api/project/new")
def project_new(req: NewProject):
    try:
        inst = STATE.registry.get(req.instrument_id)
    except KeyError:
        raise HTTPException(status_code=400,
                            detail="知らない楽器です: %s" % req.instrument_id)
    if req.set_id:
        try:
            sdef = inst.set_def(req.set_id)
        except KeyError:
            raise HTTPException(status_code=400, detail="未知のセットです")
        missing = [m["component"] for m in sdef["members"]
                   if m.get("required", True)
                   and not (inst.component_classes.get(m["component"])
                            and inst.component_classes[m["component"]].available())]
        if missing:
            raise HTTPException(status_code=400,
                                detail="このセットの部品に未実装のものがあります")
    else:
        cls = inst.component_classes.get(req.component_id or "")
        if cls is None or not cls.available():
            raise HTTPException(status_code=400,
                                detail="このコンポーネントは未実装です（後フェーズで追加予定）")
    STATE.new_project(req.instrument_id, req.template_id, req.component_id,
                      req.name, set_id=req.set_id)
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
        # いまの組での**実効の壁**（Phase 4-E B-5）。スキーマの `hard_*` は
        # テンプレート値で作った掛け金なので、関係で決まる 9 本はここが上書きする。
        "bounds": STATE.param_bounds(),
        "simulation": STATE.simulate(),
        "manual_edit": STATE.manual_edit_summary(),
        "reference": STATE.reference_summary(),
        # セット情報。単体プロジェクトでは None（UI は部品タブを出さない）。
        "set": STATE.set_summary(),
        # 部品どうしでしか出せない量の判定（`set_check`）。単体では None。
        "set_card": STATE.set_card(),
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


class MemberReq(BaseModel):
    component_id: str


@app.post("/api/set/active")
def set_active(req: MemberReq):
    """編集対象の部品を切り替える。"""
    _require_project()
    try:
        STATE.set_active(req.component_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return project_get()


@app.post("/api/set/member/add")
def set_member_add(req: MemberReq):
    """セットに部品を足す（テンプレート既定値から）。"""
    _require_project()
    try:
        STATE.add_member(req.component_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return project_get()


@app.post("/api/set/member/remove")
def set_member_remove(req: MemberReq):
    _require_project()
    try:
        STATE.remove_member(req.component_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return project_get()


class MemberImportReq(BaseModel):
    path: str


@app.post("/api/set/member/import")
def set_member_import(req: MemberImportReq):
    """既存の単体 .wproj をセットのメンバーとして取り込む。"""
    _require_project()
    if not Path(req.path).exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    try:
        STATE.import_member(req.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"読み込み失敗: {e}")
    return project_get()


class MemberExportReq(BaseModel):
    component_id: str
    path: str


@app.post("/api/set/member/export")
def set_member_export(req: MemberExportReq):
    """セットの部品 1 つを単体 .wproj として書き出す。"""
    _require_project()
    path = req.path if req.path.lower().endswith(".wproj") else req.path + ".wproj"
    try:
        STATE.export_member(req.component_id, path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "path": path}


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
    # 帯／壁で丸めた項目。**空でも必ず入れる** —— フロントは前回の報告を
    # 消す判断をこのキーだけで行う。
    # 壁は**毎回返す**。相手を動かすと別のパラメータの端が動くので、フロントが
    # 前回の値を使い回すとスライダが古い壁で止まる（`adjustments` と同じ理由で
    # 空でも必ず入れる）。
    return {"params": applied, "simulation": STATE.simulate(),
            "stale": STATE.is_stale(), "adjustments": STATE.adjustments,
            "bounds": STATE.param_bounds()}


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

    `asset` は**いま配っているアプリの世代**（`frontend_asset`）。開きっぱなしの
    タブは殻の `no-store` では入れ替わらないので、フロントが自分の読み込んだ
    スクリプト名と突き合わせて、食い違ったら再読み込みを促す。
    """
    return {
        "native_dialogs": _is_local_client(request) and filedialog.available(),
        "host": host_kind(),
        "export_root": str(STATE.export_root()),
        "asset": frontend_asset(),
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


@app.get("/api/set/placement")
def set_placement():
    """セット合わせ表示の配置。**編集中の部品を基準にした相対変換**。

    置き場所を宣言しない部品は出さない（`unplaced` に名前だけ返す）。
    単体プロジェクトでは `parts` が空。
    """
    _require_project()
    return STATE.assembly_placements()


@app.get("/api/set/model.stl")
async def set_model_stl(member: str):
    """セットの部品 1 つの STL（合わせ表示用）。**常にプレビュー品質**。

    位置関係を見るためのもので、寸法を測る用途には出さない（参照の重ねと同じ扱い）。
    """
    _require_project()
    if not STATE.project.has(member):
        raise HTTPException(status_code=404, detail="この部品はセットにありません")
    try:
        data = await asyncio.to_thread(STATE.get_stl_bytes, 0.05, member)
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
    # **まず型だけ合わせて組を作り、その組から壁を引く。** ドラッグ中の丸めが
    # 確定（`PUT`）の丸めと食い違わないようにするため ——相手で動く壁は
    # 「頼まれた組」から引くので、静的な `hard_*` で丸めると指を離した瞬間に
    # 値が飛ぶ（Phase 4-E B-5）。
    for k, v in request.query_params.items():
        spec = STATE.paramset.specs.get(k)
        if spec is None:
            continue
        # 数値に読めないクエリは無視して現在値のままにする（500 にしない）。
        with contextlib.suppress(ValueError, TypeError):
            values[k] = spec.coerce(v)
    bounds = STATE.param_bounds(values)
    for k in list(request.query_params):
        spec = STATE.paramset.specs.get(k)
        if spec is not None and k in values:
            with contextlib.suppress(ValueError, TypeError):
                values[k] = spec.validate(values[k], bounds.get(k))
    data = STATE.component.section(values)
    if data is None:
        raise HTTPException(status_code=404, detail="このコンポーネントに断面編集はありません")
    # 寸法はここで**ルート側が**足す。断面を持つ部品が増えたときに
    # `section()` の中へ書き足し忘れる経路を作らないため（定義は `dimensions()`
    # の 1 か所のまま）。ドラッグ中のクエリ上書きがそのまま効くので、寸法は
    # 形と同じフレームで動く。
    data["dimensions"] = STATE.component.dimensions(values)
    # 警告も同じ理由でルート側が足す。**ここに置くとドラッグ中も追従する** ——
    # 上のクエリ上書きがそのまま `values` に効くので、断面側の警告は指を離す前に
    # 動く（右パネルの警告カードは確定＝`PUT` を待つ）。定義は `warnings()` の
    # 1 か所のまま。
    data["warnings"] = STATE.component.warnings(values)
    # 実効の壁も同じフレームで返す。**ドラッグで相手を動かすと別のハンドルの
    # 端が動く**ので、指を離すまで古い壁のままにしない。
    data["bounds"] = bounds
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
    #: "member" = 編集中の部品だけ（従来）。"set" = セットの全部品を 1 フォルダへ。
    scope: str = "member"


def _safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "project"


MATERIAL_LABELS = {"resin": "レジン(光造形)", "pla": "PLA", "petg": "PETG",
                   "nylon_sls": "ナイロンPA12(SLS)", "tpu": "TPU95A(FDM・弾性)",
                   "resin_flex": "フレキシブルレジン(光造形)", "pp": "ポリプロピレン",
                   "cane": "ケーン(切削・参考)"}


async def _write_member_models(cid: str, out_dir: str | Path, formats: list[str],
                               use_derived: bool) -> dict:
    """部品 1 つのモデルを書き出す。**単体出力もセット出力もここを通る。**

    Returns:
        {"files": {ファイル名: Path}, "part": Part, "used_derived": bool,
         "quality": dict|None}
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    member = STATE.project.member(cid)
    comp = STATE.members[cid].component

    part = await asyncio.to_thread(STATE.build_part, cid)

    # 派生モデル（外部編集済み）があれば STL はそれを採用（陳腐化していなければ）
    used_derived = False
    derived_stl = member.derived_stl
    if use_derived and derived_stl is not None:
        if STATE.is_stale(cid):
            raise HTTPException(
                status_code=409,
                detail=f"「{comp.label}」は凍結後にパラメータ（または参照する部品）が"
                       f"変更されています。編集済みモデルは古い形状です。"
                       f"外部編集をやり直すか、派生モデルを破棄してください。")
        used_derived = True

    files: dict[str, Path] = {}
    part_cad = None
    for fmt in formats:
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
                part_cad = await asyncio.to_thread(STATE.build_part_cad, cid)
            await asyncio.to_thread(export_model, part_cad, f, fmt)
        else:
            await asyncio.to_thread(export_model, part, f, fmt)
        files[f"model.{fmt}"] = f

    quality = None
    stl_key = "model_edited.stl" if used_derived else "model.stl"
    if stl_key in files:
        quality = check_mesh(files[stl_key])
    return {"files": files, "part": part, "used_derived": used_derived,
            "quality": quality}


@app.post("/api/export")
async def export(req: ExportReq):
    _require_project()
    proj = STATE.project
    inst = STATE.registry.get(proj.instrument_id)
    template_label = inst.templates[proj.template_id].get("label", proj.template_id)
    instrument_label = inst.descriptor.get("label", proj.instrument_id)

    as_set = req.scope == "set" and proj.is_set
    member_ids = list(proj.members) if as_set else [proj.active]

    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = Path(req.out_dir) if req.out_dir else STATE.export_root()
    out_dir = base / f"{_safe_name(proj.name)}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}      # アーカイブ内の名前 → 実ファイル
    built: dict[str, dict] = {}
    spec_members: list[dict] = []
    bom_by_member: list[tuple[str, list[dict]]] = []
    readme_members: list[dict] = []

    for cid in member_ids:
        sub = out_dir / cid if as_set else out_dir
        res = await _write_member_models(cid, sub, req.formats, req.use_derived)
        built[cid] = res
        prefix = f"{cid}/" if as_set else ""
        for name, path in res["files"].items():
            files[prefix + name] = path

        comp = STATE.members[cid].component
        params = dict(STATE.members[cid].paramset.values)
        extras = comp.spec_extras(params)
        bom_rows = comp.bom(params)
        bom_by_member.append((comp.label, bom_rows))
        spec_members.append({
            "label": comp.label, "name": proj.member(cid).name, "dir": cid,
            "params": params, "specs": comp.param_specs(),
            "dimensions": extras.get("dimensions", []), "bom_rows": bom_rows,
            "sim": STATE.simulate(cid), "sections": extras.get("sections", []),
            "material": params.get("material", "resin"),
        })
        readme_members.append({
            "label": comp.label, "dir": cid,
            "material_label": MATERIAL_LABELS.get(params.get("material"), "-"),
            "dims": extras.get("dimensions", []),
        })

    # 仕様書と部品表は**セットで 1 枚**（部品ごとに割らない）
    if as_set:
        html = spec_html_set(proj.name, instrument_label, template_label,
                             spec_members, STATE.set_card())
        csv_text = bom_csv_set(bom_by_member, proj.name)
    else:
        m = spec_members[0]
        html = spec_html(
            project_name=proj.name, instrument_label=instrument_label,
            component_label=m["label"], template_label=template_label,
            params=m["params"], specs=m["specs"], dimensions=m["dimensions"],
            bom_rows=m["bom_rows"], sim=m["sim"], sections=m["sections"],
            material=m["material"])
        csv_text = bom_csv(m["bom_rows"], proj.name)

    (out_dir / "spec.html").write_text(html, encoding="utf-8")
    files["spec.html"] = out_dir / "spec.html"
    (out_dir / "bom.csv").write_bytes(csv_text.encode("utf-8-sig"))
    files["bom.csv"] = out_dir / "bom.csv"

    package_path = None
    if req.make_package:
        if as_set:
            readme = readme_text_set(proj.name, readme_members)
        else:
            readme = readme_text(proj.name, readme_members[0]["dims"],
                                 readme_members[0]["material_label"])
        edited = [STATE.members[cid].component.label
                  for cid in member_ids if built[cid]["used_derived"]]
        if edited:
            readme += ("\n\n[外部編集済みモデル]\n"
                       "model_edited.stl は外部ツールで手動編集したモデルです。\n"
                       "印刷にはこのファイルを使用してください。\n"
                       f"対象: {'、'.join(edited)}\n")
        package_path = out_dir / f"{_safe_name(proj.name)}_入稿パッケージ.zip"
        build_package(package_path, {k: v for k, v in files.items()}, readme)

    # 凍結: STEP出力とセットでスナップショット記録（外部編集ワークフローの起点）。
    # **凍結は部品単位のまま** —— 外部編集は部品ごとに往復するので、まとめて
    # 凍結すると触っていない部品まで「編集待ち」の状態になる。
    manual_edit = None
    if req.freeze:
        vol_cc = float(built[proj.active]["part"].volume / 1000.0)
        target = out_dir / proj.active if as_set else out_dir
        manual_edit = STATE.freeze(str(target), round(vol_cc, 2))

    active = built[proj.active]
    return {
        "out_dir": str(out_dir),
        "files": {k: str(v) for k, v in files.items()},
        "package": str(package_path) if package_path else None,
        "mesh_quality": active["quality"],
        "used_derived": active["used_derived"],
        "manual_edit": manual_edit,
        "scope": "set" if as_set else "member",
        "members": member_ids,
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
    #: **文字列にしない。** かつてここは `str` で、コメントだけが 4 種と
    #: 言っていた。`settings["external_tools"]` は任意のキーを受けていたので、
    #: 「設定に任意の exe を登録 → それを `tool` 名で起動」が 2 リクエストで
    #: 通った。型で閉じておけば FastAPI が 422 で落とす。
    tool: Literal["freecad", "slicer", "reveal", "browser"]
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
        if f.suffix.lower() not in _OPENABLE_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail="この形式は既定アプリで開きません: %s" % f.suffix)
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


#: 書き換えてよい設定キー。`external_tools` だけは中身も絞る（下）。
_SETTABLE = frozenset({"external_tools", "export_root", "recent_projects"})

#: 外部ツールとして登録してよい名前。`ToolReq` の Literal と**同じ集合**で、
#: 片方だけ増えると「登録できるのに起動できない」か、その逆になる。
_TOOL_KEYS = frozenset({"freecad", "slicer"})


@app.put("/api/settings")
def settings_put(req: SettingsReq):
    """設定を更新する。**知っているキーだけ**通す。

    かつては受け取った dict を丸ごと `update` してディスクへ書いていた。
    `external_tools` に任意の名前で任意の exe を登録でき、それを
    `/api/tools/open` が起動したので、2 リクエストで任意コード実行になっていた。
    """
    unknown = sorted(set(req.settings) - _SETTABLE)
    if unknown:
        raise HTTPException(status_code=400,
                            detail="知らない設定キー: %s" % ", ".join(unknown))
    tools = req.settings.get("external_tools")
    if tools is not None:
        if not isinstance(tools, dict):
            raise HTTPException(status_code=400, detail="external_tools は辞書")
        bad = sorted(set(tools) - _TOOL_KEYS)
        if bad:
            raise HTTPException(status_code=400,
                                detail="知らない外部ツール: %s" % ", ".join(bad))
        # 既存のキー（旧版の openwind_note など）を消さずに重ねる
        merged = dict(STATE.settings.get("external_tools", {}))
        merged.update({k: str(v) for k, v in tools.items()})
        req.settings = {**req.settings, "external_tools": merged}
    STATE.settings.update(req.settings)
    STATE.save_settings()
    return STATE.settings


# ------------------------------------------------------------------ フロントエンド静的配信

if FRONTEND_DIST.exists():

    class _ImmutableAssets(StaticFiles):
        """資産は内容ハッシュ付きの名前なので、中身が変われば URL も変わる。

        だから資産そのものは永久にキャッシュしてよい。**世代を切り替えるのは
        殻（`index.html`）の役目**で、そちらは下で `no-store` にしている。
        """

        def file_response(self, *args, **kwargs):
            resp = super().file_response(*args, **kwargs)
            resp.headers["cache-control"] = "public, max-age=31536000, immutable"
            return resp

    app.mount("/assets", _ImmutableAssets(directory=FRONTEND_DIST / "assets"),
              name="assets")

    @app.get("/")
    def index():
        """アプリの殻。**キャッシュさせない。**

        ここを配り直せないと、ブラウザは古い `index-XXXX.js` を読み続ける。
        サーバだけ新しい状態は**エラーにならず、それらしく組み上がった絵が出る**
        ので気付けない —— 実際に 2026-09-03 に起きた（セット表示でフロントが
        `flip_z` を落とし、リードがマウスピースの反対側に付いて見えた）。
        資産は immutable なので、殻を取り直す代償は数百バイトで済む。
        """
        return FileResponse(FRONTEND_DIST / "index.html",
                            headers={"cache-control": "no-store"})


def _is_loopback_host(host: str) -> bool:
    """bind 先がループバックか。名前は `localhost` だけ認める。"""
    if host.lower() in ("localhost", "::1", "[::1]"):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


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

    host = os.environ.get("SAX_HOST", "127.0.0.1")
    want = int(os.environ.get("SAX_PORT", "8712"))

    # 認証が無いので、ループバック以外へ bind するのは
    # **ファイルシステム API を無防備に公開する**のと同じ。黙って従わない。
    if not _is_loopback_host(host) and not ALLOW_REMOTE:
        print("✗ SAX_HOST=%s はループバックではありません。" % host,
              file=sys.stderr)
        print("  SaxSketch は認証を持たず、API は任意の絶対パスを読み書きし、",
              file=sys.stderr)
        print("  外部ツールを起動します。LAN へ出すと誰でもそれを使えます。",
              file=sys.stderr)
        print("  それでも出すなら SAX_ALLOW_REMOTE=1 を立ててください（自分の責任で）。",
              file=sys.stderr)
        sys.exit(1)
    if ALLOW_REMOTE:
        print(f"⚠ SAX_ALLOW_REMOTE が立っています。{host} からは認証なしで"
              f"ファイルを読み書きできます。")

    if _in_use(host, want):
        if _is_saxsketch(host, want):
            print(f"✔ SaxSketch は既に起動中 → http://{host}:{want} を開いてください")
            return
        port = _free_port(host, want + 1)
        if port is None:
            print(f"✗ {want} が使用中で、近傍にも空きポートがありません。"
                  f"占有元を止めるか SAX_PORT で別ポートを指定してください。", file=sys.stderr)
            sys.exit(1)
        print(f"⚠ ポート {want} は使用中。空いている {port} で起動します。")
    else:
        port = want

    print(f"▶ SaxSketch → http://{host}:{port} （停止: Ctrl+C）")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
