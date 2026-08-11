"""アプリケーション状態（シングルユーザー・ローカルアプリ）。"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from saxsketch.core.project import Project
from saxsketch.core.registry import get_registry
from saxsketch.core.schema import ParamSet

from .hostenv import IS_WSL, windows_documents

#: 設定ファイルの版。**上げるのは移行が要るときだけ。**
#: 2 = 出力先を「環境から導く」に変えた版（下の `_migrate_export_root`）。
SETTINGS_VERSION = 2

#: 旧バージョンが既定として書き込んでいた出力先。移行判定にだけ使う。
_LEGACY_EXPORT_ROOT = Path.home() / "Documents" / "SaxSketch"

DEFAULT_SETTINGS = {
    "settings_version": SETTINGS_VERSION,
    "external_tools": {
        "freecad": "",
        "slicer": "",
        "openwind_note": "Phase 2 で統合予定",
    },
    "recent_projects": [],
    # 空 = 未設定。既定は `default_export_root()` がその都度導く。ここに値を
    # 焼き付けると、環境（WSL / ネイティブ）が変わっても古い場所を指し続ける。
    "export_root": "",
}


def settings_dir() -> Path:
    """設定の置き場所。`SAXSKETCH_HOME` で差し替えられる。

    差し替え口が要るのは**テストのため**。以前は実ユーザーの
    `~/.saxsketch/settings.json` を直接書き換えていて、「最近使ったプロジェクト」が
    pytest の一時ディレクトリ 10 件で埋まっていた（実際に起きた）。
    """
    override = os.environ.get("SAXSKETCH_HOME")
    return Path(override) if override else Path.home() / ".saxsketch"


def settings_file() -> Path:
    return settings_dir() / "settings.json"


def default_export_root() -> Path:
    """エクスポートの既定の出力先。

    WSL では **Windows 側の**ドキュメントを使う。サーバは Linux で動いているが、
    出来上がった STL や入稿 ZIP を掴むのは Windows のエクスプローラだから、
    `~/Documents` に置くと利用者からはほぼ辿れない場所に消える。
    """
    docs = windows_documents() if IS_WSL else None
    return (docs or Path.home() / "Documents") / "SaxSketch"


def _migrate_export_root(value: str) -> str:
    """旧版が既定として書き込んだ出力先を「未設定」に戻す（版 1 → 2 で一度だけ）。

    旧既定は Linux 側の `~/Documents/SaxSketch`。WSL で動かすと Windows の
    エクスプローラからほぼ辿れない場所で、しかも**利用者が選んだのではなく
    `DEFAULT_SETTINGS` が勝手に書いた値**なので捨てて構わない。

    判定を「実在しないこと」にしてはいけない —— そのフォルダは書き出した結果
    実在するのが普通で、条件がほぼ成立しない。かといって値の一致だけで毎回
    消すと、**同じ場所を自分で選び直した人の設定が二度と保存できない**。
    だから一致で判定し、**版で一度きり**にする。保存時に版が刻まれる。
    """
    if IS_WSL and value and Path(value) == _LEGACY_EXPORT_ROOT:
        return ""
    return value


def _existing(paths) -> list[str]:
    """実在するパスだけ残す。"""
    return [p for p in paths if p and Path(p).exists()]


class AppState:
    def __init__(self):
        self.registry = get_registry()
        self.project: Project | None = None
        self.component = None
        self.paramset: ParamSet | None = None
        self.build_lock = threading.Lock()
        self._stl_cache: dict[str, bytes] = {}
        self._sim_cache: dict[str, dict] = {}
        self._imp_cache: dict[str, dict] = {}
        self._wav_cache: dict[str, tuple] = {}
        # 採寸ワークフロー（Phase 4-A）。音響基準定数(size_info)へのプロジェクト局所上書き。
        self.size_overrides: dict = {}
        self._base_size: dict = {}   # コンポーネント既定の size_info（descriptor 由来のコピー）
        self.settings = self._load_settings()

    # ---------------------------------------------------------- 設定

    def _load_settings(self) -> dict:
        loaded: dict = {}
        path = settings_file()
        if path.exists():
            with contextlib.suppress(Exception):
                loaded = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_SETTINGS)
        merged.update(loaded)
        # 消えたプロジェクトは読み込みの時点で落とす。`/api/recent` も同じ条件で
        # 濾しているが、保存側が素通しだと一度混ざったゴミが永久に残る。
        merged["recent_projects"] = _existing(merged.get("recent_projects", []))
        # 版は **loaded** で見る。merged は既定で埋まっているので判定できない。
        if int(loaded.get("settings_version", 1)) < SETTINGS_VERSION:
            merged["export_root"] = _migrate_export_root(merged.get("export_root", ""))
        merged["settings_version"] = SETTINGS_VERSION
        return merged

    def save_settings(self) -> None:
        settings_dir().mkdir(parents=True, exist_ok=True)
        settings_file().write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_root(self) -> Path:
        """エクスポートの出力先。設定が空なら環境から導く。"""
        value = str(self.settings.get("export_root") or "").strip()
        return Path(value) if value else default_export_root()

    def push_recent(self, path: str) -> None:
        recent = [p for p in _existing(self.settings.get("recent_projects", []))
                  if p != path]
        recent.insert(0, path)
        self.settings["recent_projects"] = recent[:10]
        self.save_settings()

    # ---------------------------------------------------------- プロジェクト

    def new_project(self, instrument_id: str, template_id: str, component_id: str,
                    name: str | None = None) -> None:
        inst = self.registry.get(instrument_id)
        component = inst.make_component(component_id, template_id)
        specs = component.param_specs()
        template_values = component.template.get(component_id, {})
        paramset = ParamSet(specs, template_values)
        tmpl_label = inst.templates[template_id].get("label", template_id)
        self.project = Project(
            instrument_id=instrument_id, template_id=template_id,
            component_id=component_id,
            name=name or f"{tmpl_label} {component.label}",
            params=dict(paramset.values))
        self.component = component
        self.paramset = paramset
        self._bind_refs()
        self.size_overrides = {}
        self._bind_size()
        self._clear_caches()
        self._pending_derived = None

    def open_project(self, path: str) -> None:
        proj = Project.load(path)
        inst = self.registry.get(proj.instrument_id)
        component = inst.make_component(proj.component_id, proj.template_id)
        specs = component.param_specs()
        paramset = ParamSet(specs, component.template.get(proj.component_id, {}))
        paramset.apply(proj.params)
        proj.params = dict(paramset.values)
        self.project = proj
        self.component = component
        self.paramset = paramset
        self._bind_refs()
        # 採寸チェックポイントに保存された音響基準の上書きを復元する。
        self.size_overrides = dict(
            (proj.survey or {}).get("checkpoint", {}).get("size_overrides", {}))
        self._bind_size()
        self._clear_caches()
        self._pending_derived = None
        self.push_recent(path)

    def save_project(self, path: str) -> None:
        assert self.project is not None
        self.project.params = dict(self.paramset.values)
        self.project.save(path)
        self.push_recent(path)

    # ---------------------------------------------------------- 参照コンポーネント

    def _default_ref(self, ref_id: str) -> dict:
        """参照未設定時の既定値。自テンプレートの当該ブロックを ParamSet で正規化する。

        テンプレートに欠けたキーはコンポーネントの既定値で埋まるため、参照は常に
        「完全なパラメータ一式」になる（ジオメトリ生成も音響合成もそのまま使える）。
        """
        inst = self.registry.get(self.project.instrument_id)
        ref_comp = inst.make_component(ref_id, self.project.template_id)
        ps = ParamSet(ref_comp.param_specs(),
                      ref_comp.template.get(ref_id, {}))
        tmpl_label = inst.templates[self.project.template_id].get(
            "label", self.project.template_id)
        return {
            "source": None,
            "label": f"{tmpl_label} テンプレート既定値",
            "params": dict(ps.values),
        }

    def _template_label(self, proj: Project) -> str:
        """プロジェクトのテンプレート表示名（エラーメッセージ用）。"""
        try:
            inst = self.registry.get(proj.instrument_id)
            return inst.templates[proj.template_id].get("label", proj.template_id)
        except KeyError:
            return proj.template_id

    def _bind_refs(self) -> None:
        """コンポーネントに参照を結び付ける。未設定なら既定値を入れる。"""
        ref_id = getattr(self.component, "REQUIRES_REF", None)
        if ref_id and not self.project.refs.get(ref_id):
            self.project.refs[ref_id] = self._default_ref(ref_id)
        self.component.set_refs(self.project.refs)

    def set_reference(self, ref_id: str, path: str | None) -> None:
        """参照コンポーネントを .wproj から取込む。path=None で既定値へ戻す。"""
        required = getattr(self.component, "REQUIRES_REF", None)
        if required != ref_id:
            raise ValueError(
                f"{self.component.label} は「{ref_id}」を参照しません")
        if path is None:
            self.project.refs[ref_id] = self._default_ref(ref_id)
        else:
            src = Project.load(path)
            if src.component_id != ref_id:
                raise ValueError(
                    f"このプロジェクトは「{src.component_id}」です。"
                    f"「{ref_id}」の .wproj を選んでください。")
            # 楽器・サイズが違う参照は通さない。自コンポーネントの size_info（規格寸法）や
            # BOM のサイズ表記は自テンプレート由来のままなので、形だけ別サイズになる。
            if (src.instrument_id != self.project.instrument_id
                    or src.template_id != self.project.template_id):
                raise ValueError(
                    f"このマウスピースは「{self._template_label(src)}」用です。"
                    f"「{self._template_label(self.project)}」のものを選んでください。")
            inst = self.registry.get(src.instrument_id)
            ref_comp = inst.make_component(ref_id, src.template_id)
            ps = ParamSet(ref_comp.param_specs(),
                          ref_comp.template.get(ref_id, {}))
            ps.apply(src.params)
            self.project.refs[ref_id] = {
                "source": path, "label": src.name, "params": dict(ps.values)}
        self.component.set_refs(self.project.refs)
        self._clear_caches()

    def reference_summary(self) -> dict | None:
        """フロント表示用の参照情報。参照不要なコンポーネントでは None。"""
        ref_id = getattr(self.component, "REQUIRES_REF", None)
        if not ref_id:
            return None
        entry = self.project.refs.get(ref_id, {})
        return {
            "component_id": ref_id,
            "label": entry.get("label", "-"),
            "source": entry.get("source"),
            "dims": [list(d) for d in self.component.ref_dimensions()],
        }

    def apply_params(self, values: dict) -> dict:
        """スライダーの値を適用する。成立しない組は**保存せずに弾く**。

        `ParamSpec.validate` はパラメータを 1 本ずつしか見ないので、各自のレンジ内
        なのに組み合わせると形状が潰れる値の組が作れる（`Component.params_error`）。
        保存してしまうと以後の `simulate` も `build` も同じ理由で落ち、スライダーを
        戻すための画面ごと出せなくなる。試した値を捨てて `ValueError` を上げる。
        """
        assert self.paramset is not None and self.project is not None
        keep = dict(self.paramset.values)
        applied = self.paramset.apply(values)
        bad = self.component.params_error(applied) if self.component else None
        if bad:
            self.paramset.apply(keep)
            raise ValueError(bad)
        self.project.params = dict(applied)
        return applied

    # ---------------------------------------------------------- 形状

    def _params_key(self) -> str:
        payload = json.dumps(
            {"i": self.project.instrument_id, "t": self.project.template_id,
             "c": self.project.component_id, "p": self.paramset.values,
             "r": self.project.refs, "so": self.size_overrides},
            sort_keys=True, default=str)
        return hashlib.md5(payload.encode()).hexdigest()

    def _clear_caches(self) -> None:
        self._stl_cache.clear()
        self._sim_cache.clear()
        self._imp_cache.clear()
        self._wav_cache.clear()

    def build_part(self):
        with self.build_lock:
            return self.component.build(dict(self.paramset.values))

    def build_part_cad(self):
        """STEP 出力用のソリッド。面を1枚ずつに畳んだ版（`Component.build_cad`）。

        プレビュー・STL・シミュレーションは `build_part()` のまま。STEP だけ
        分けるのは、プリミティブ表現はブーリアンが数倍遅い代わりに FreeCAD で
        面選択とフィレットができるという、出力先でしか意味の無い差だから。
        """
        with self.build_lock:
            return self.component.build_cad(dict(self.paramset.values))

    def build_spec(self, tolerance: float, cad: bool = False) -> dict:
        """ビルドに必要な入力だけを取り出した、プロセス間で運べる辞書。"""
        return {
            "instrument_id": self.project.instrument_id,
            "template_id": self.project.template_id,
            "component_id": self.project.component_id,
            "refs": copy.deepcopy(self.project.refs),
            "params": dict(self.paramset.values),
            "tolerance": tolerance,
            "cad": cad,
        }

    def get_stl_bytes(self, tolerance: float = 0.03) -> bytes:
        """プレビュー/エクスポート用の STL。

        ビルド自体は**別プロセス**へ出す。OCCT が GIL を離さないので、親で回すと
        再生成中に断面もパラメータ更新も止まる（`buildworker` の注記を参照）。
        ワーカが使えない環境では親で作る — 遅いだけで結果は同じ。
        """
        key = self._params_key() + f":{tolerance}"
        cached = self._stl_cache.get(key)
        if cached is not None:
            return cached

        from saxsketch.server.buildworker import WORKER
        data = None
        if WORKER.alive:
            with contextlib.suppress(RuntimeError):
                data = WORKER.build_stl(self.build_spec(tolerance))
        if data is None:
            data = self._stl_bytes_inproc(tolerance)

        # キャッシュは直近3件のみ保持
        if len(self._stl_cache) > 3:
            self._stl_cache.clear()
        self._stl_cache[key] = data
        return data

    def _stl_bytes_inproc(self, tolerance: float) -> bytes:
        from saxsketch.export.models import export_model
        part = self.build_part()
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "model.stl"
            export_model(part, f, "stl", tolerance=tolerance)
            return f.read_bytes()

    def simulate(self) -> dict:
        """シミュレーション結果。同じパラメータなら作り直さない。

        `GET /api/project` と `PUT /api/project/params` の両方から呼ばれるので、
        スライダーを1目盛り動かすたびに走る。中身は決定的（乱数なし）なので
        `_params_key()` でそのままキャッシュしてよい。パラメータ・参照・
        size_overrides のどれかが変われば鍵が変わり、明示的な `_clear_caches()`
        でも消える。
        """
        key = self._params_key()
        cached = self._sim_cache.get(key)
        if cached is not None:
            return cached
        res = self.component.simulate(dict(self.paramset.values))
        if len(self._sim_cache) > 4:
            self._sim_cache.clear()
        self._sim_cache[key] = res
        return res

    # ---------------------------------------------------------- Tier3（インピーダンス・音合成）

    def impedance(self) -> dict:
        """入力インピーダンス（重い→パラメータハッシュでキャッシュ）。"""
        key = self._params_key() + ":imp"
        cached = self._imp_cache.get(key)
        if cached is not None:
            return cached
        res = self.component.impedance(dict(self.paramset.values))
        if len(self._imp_cache) > 4:
            self._imp_cache.clear()
        self._imp_cache[key] = res
        return res

    def synthesize_wav(self, embouchure: str) -> tuple[bytes, dict]:
        """単音の物理モデル音（数秒〜かかる→キャッシュ＋ビルドと直列化）。"""
        key = self._params_key() + f":wav:{embouchure}"
        cached = self._wav_cache.get(key)
        if cached is not None:
            return cached
        with self.build_lock:
            res = self.component.synthesize(dict(self.paramset.values), embouchure)
        self._cache_wav(key, res)
        return res

    def scale_wav(self) -> tuple[bytes, dict]:
        key = self._params_key() + ":scale"
        cached = self._wav_cache.get(key)
        if cached is not None:
            return cached
        with self.build_lock:
            res = self.component.scale(dict(self.paramset.values))
        self._cache_wav(key, res)
        return res

    def _cache_wav(self, key: str, res: tuple) -> None:
        if len(self._wav_cache) > 4:
            self._wav_cache.clear()
        self._wav_cache[key] = res

    # ---------------------------------------------------------- 外部編集（凍結・再取込）

    def is_stale(self) -> bool:
        """凍結後にパラメータ**または参照コンポーネント**が変更されたか。

        リード/リガチャーは参照マウスピースの寸法で形が決まるため、自パラメータが
        同じでも参照を差し替えれば凍結時とは別の形状になる。参照を見ないと、
        古い外部編集モデルがそのまま入稿パッケージに入ってしまう。
        """
        if self.project is None:
            return False
        # 外部取込モデルは凍結パラメータから派生していないので陳腐化しない
        # （自分の設計を後からいじっても、取込んだ市販モデルは無関係のまま）。
        if (self.project.derived or {}).get("kind") == "external":
            return False
        if self.project.frozen is None:
            return False
        frozen_params = self.project.frozen["params"]
        cur = self.paramset.values
        for k, v in frozen_params.items():
            if cur.get(k) != v:
                return True
        return self._refs_changed()

    def _refs_changed(self) -> bool:
        """凍結時の参照パラメータと現在の差分。

        比較するのは `params` だけ（`source`/`label` は形状に影響しない）。
        `refs` を持たない Phase 3 以前の凍結スナップショットは比較をスキップする。
        """
        frozen_refs = self.project.frozen.get("refs")
        if frozen_refs is None:
            return False
        for ref_id, entry in frozen_refs.items():
            cur = self.project.refs.get(ref_id, {})
            if entry.get("params") != cur.get("params"):
                return True
        return False

    def manual_edit_summary(self) -> dict:
        """フロント表示用の外部編集状態。"""
        p = self.project
        if p is None:
            return {"frozen": None, "derived": None, "stale": False}
        frozen = None
        if p.frozen is not None:
            frozen = {"frozen_at": p.frozen["frozen_at"],
                      "export_dir": p.frozen.get("export_dir"),
                      "solid_volume_cc": p.frozen.get("solid_volume_cc")}
        derived = None
        if p.derived is not None:
            derived = {"imported_at": p.derived["imported_at"],
                       "source_file": p.derived["source_file"],
                       "quality": p.derived["quality"],
                       "kind": p.derived.get("kind", "edited")}
        return {"frozen": frozen, "derived": derived, "stale": self.is_stale()}

    def freeze(self, export_dir: str, solid_volume_cc: float | None) -> dict:
        """現パラメータで凍結スナップショットを記録。既存の派生モデルは破棄。"""
        from datetime import datetime, timezone
        assert self.project is not None
        self.project.frozen = {
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "params": dict(self.paramset.values),
            # 参照も凍結する。リード/リガチャーは参照マウスピースで形が決まるため
            "refs": copy.deepcopy(self.project.refs),
            "solid_volume_cc": solid_volume_cc,
            "export_dir": export_dir,
        }
        self.project.derived = None
        self.project.derived_stl = None
        self._pending_derived = None
        return self.manual_edit_summary()

    def unfreeze(self) -> dict:
        assert self.project is not None
        self.project.frozen = None
        self.project.derived = None
        self.project.derived_stl = None
        self._pending_derived = None
        return self.manual_edit_summary()

    _pending_derived: dict | None = None  # {stl_bytes, source_file, quality, analysis}

    @contextlib.contextmanager
    def _frozen_refs(self):
        """凍結時の参照でコンポーネントを一時的に動かす。

        比較の基準形状は凍結時のものでなければならない。現在の参照で作ると、
        参照を差し替えた後の解析が「編集による差分」と「参照差替えによる差分」を
        混ぜてしまう。
        """
        frozen_refs = (self.project.frozen or {}).get("refs")
        if frozen_refs is None:
            yield
            return
        current = self.component.refs
        self.component.set_refs(copy.deepcopy(frozen_refs))
        try:
            yield
        finally:
            self.component.set_refs(current)

    def analyze_derived(self, path: str) -> dict:
        """編集済みモデルを読み込み解析（まだ登録しない）。"""
        from saxsketch.analysis import meshdiff
        assert self.project is not None and self.project.frozen is not None
        frozen_params = dict(self.project.frozen["params"])

        edited = meshdiff.load_mesh(path)
        quality = meshdiff.mesh_quality(edited)

        with self._frozen_refs():
            with self.build_lock:
                ref_part = self.component.build(frozen_params)
            ref_mesh = meshdiff.part_to_mesh(ref_part, tolerance=0.03)
            ref_vol_cc = float(ref_mesh.volume / 1000.0)
            analysis = self.component.analyze_import(frozen_params, ref_mesh, edited)

        vol_row = None
        if quality["volume_cc"] is not None:
            delta_pct = (quality["volume_cc"] - ref_vol_cc) / ref_vol_cc * 100.0
            vol_row = {"frozen_cc": round(ref_vol_cc, 2),
                       "edited_cc": round(quality["volume_cc"], 2),
                       "delta_pct": round(delta_pct, 2)}
            if abs(delta_pct) > 5.0:
                analysis["warnings"].append(
                    f"⚠ 体積が {delta_pct:+.1f}% 変化しています。削りすぎ／穴あきの疑い。")
        else:
            analysis["warnings"].append(
                "⚠ メッシュが水密ではありません。修復しないと印刷できません。")

        # STL バイト列を保持（STEP等は解析メッシュから STL 化）
        import trimesh  # noqa: F401
        stl_bytes = edited.export(file_type="stl")
        if isinstance(stl_bytes, str):
            stl_bytes = stl_bytes.encode()
        self._pending_derived = {
            "stl_bytes": stl_bytes,
            "source_file": path,
            "quality": quality,
            "analysis": {**analysis, "volume": vol_row},
        }
        return {"quality": quality, "volume": vol_row, **analysis}

    def load_external(self, path: str) -> dict:
        """外部（本アプリ非由来）の完成モデルを読み込み、整列・採寸して
        表示・入稿用の派生モデル候補にする。

        差分や逆算はしない——市販完成品は座標系も内部形状も本アプリの設計と別物で、
        領域別偏差もパラメータ逆算も意味を持たない（かつ非重なりメッシュ同士の差分は
        極端に重い）。ここでは座標非依存の整列で表示・エクスポートできる姿勢に載せ、
        確実に測れる外形寸法だけを採寸する。凍結は不要。
        """
        from saxsketch.analysis import align, meshdiff
        assert self.project is not None and self.component is not None

        mesh = meshdiff.load_mesh(path)
        quality = meshdiff.mesh_quality(mesh)
        measured = self.component.survey_measure_mesh(mesh)
        # 表示・外部編集用に正準姿勢（主軸=+Z, シャンク=+Z側）へ整列した STL を保持
        aligned, _, info = align.axis_align(mesh)
        stl_bytes = aligned.export(file_type="stl")
        if isinstance(stl_bytes, str):
            stl_bytes = stl_bytes.encode()

        self._pending_derived = {
            "stl_bytes": stl_bytes,
            "source_file": path,
            "quality": quality,
            "kind": "external",
            "measured": measured.get("measured", {}),
            "analysis": {
                "regions": [], "params": [],
                "warnings": measured.get("notes", []),
                "volume": None,
                "align": info,
            },
        }
        return {
            "kind": "external",
            "quality": quality,
            "measured": measured.get("measured", {}),
            "measured_size": measured.get("measured_size", {}),
            "confidence": measured.get("confidence", {}),
            "notes": measured.get("notes", []),
            "align": info,
        }

    def commit_derived(self) -> dict:
        """解析済み／取込済みモデルをプロジェクトに登録。"""
        from datetime import datetime, timezone
        assert self.project is not None
        pd = self._pending_derived
        if pd is None:
            raise ValueError("先に編集済みモデルを取込・解析してください")
        self.project.derived = {
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source_file": pd["source_file"],
            "quality": pd["quality"],
            "analysis": pd["analysis"],
            "kind": pd.get("kind", "edited"),
            "measured": pd.get("measured", {}),
        }
        self.project.derived_stl = pd["stl_bytes"]
        self._pending_derived = None
        return self.manual_edit_summary()

    def discard_derived(self) -> dict:
        assert self.project is not None
        self.project.derived = None
        self.project.derived_stl = None
        self._pending_derived = None
        return self.manual_edit_summary()

    # ---------------------------------------------------------- 採寸ワークフロー（Phase 4-A）

    def _bind_size(self) -> None:
        """コンポーネント既定の size_info を控え、局所上書きを重ねて再束縛する。

        `component.size_info` は descriptor の dict 参照そのものなので、控えは必ず
        コピーする。上書きは新しい dict を割り当てて行い、descriptor は汚さない。
        """
        base = getattr(self.component, "size_info", None)
        self._base_size = dict(base) if base else {}
        self._apply_size_overrides()

    def _apply_size_overrides(self) -> None:
        if not hasattr(self.component, "size_info"):
            return
        self.component.size_info = {**self._base_size, **self.size_overrides}

    def survey_state(self) -> dict:
        """フロント採寸パネル用の状態。現在の設計値/基準値でフィールドを埋める。"""
        empty = {"targets": {"params": [], "size": []}, "measured": {},
                 "measured_size": {}, "has_checkpoint": False, "card": None,
                 "surveyed_at": None, "note": ""}
        if self.project is None or self.component is None:
            return empty
        targets = self.component.survey_targets()
        for f in targets["params"]:
            f["current"] = self.paramset.values.get(f["key"])
        for f in targets["size"]:
            f["current"] = self.component.size_info.get(f["key"])
        s = self.project.survey or {}
        return {
            "targets": targets,
            "measured": s.get("measured", {}),
            "measured_size": s.get("measured_size", {}),
            "has_checkpoint": bool(s.get("checkpoint")),
            "card": s.get("card"),
            "surveyed_at": s.get("surveyed_at"),
            "note": s.get("note", ""),
        }

    @staticmethod
    def _clean_measures(raw: dict | None, allowed: set) -> dict:
        """許可キーのみ・数値化できる値だけを拾う（空欄/未知キーは捨てる）。"""
        out: dict = {}
        for k, v in (raw or {}).items():
            if k not in allowed or v is None or v == "":
                continue
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    def survey_commit(self, measured: dict | None, measured_size: dict | None,
                      note: str = "") -> dict:
        """採寸値を反映し、復元点（チェックポイント）を記録する。"""
        from datetime import datetime, timezone
        assert self.project is not None and self.component is not None
        targets = self.component.survey_targets()
        param_keys = {f["key"] for f in targets["params"]}
        size_keys = {f["key"] for f in targets["size"]}

        # 採寸前の値（照合カードの比較基準）
        before_params = dict(self.paramset.values)
        before_size = dict(self.component.size_info)

        # 系統A: 設計パラ（ParamSet でクランプ・型変換される）
        m_params = self._clean_measures(measured, param_keys)
        if m_params:
            self.apply_params(m_params)
        applied_params = {k: self.paramset.values[k] for k in m_params}

        # 系統B: 音響基準定数（size_info への局所上書き）
        m_size = self._clean_measures(measured_size, size_keys)
        self.size_overrides = {**self.size_overrides, **m_size}
        self._apply_size_overrides()

        card = self.component.survey_card(
            before_params, before_size, applied_params, m_size)

        prev = self.project.survey or {}
        self.project.survey = {
            "surveyed_at": datetime.now(timezone.utc).isoformat(),
            "note": note or "",
            "measured": {**prev.get("measured", {}), **applied_params},
            "measured_size": {**prev.get("measured_size", {}), **m_size},
            "checkpoint": {
                "params": dict(self.paramset.values),
                "refs": copy.deepcopy(self.project.refs),
                "size_overrides": dict(self.size_overrides),
            },
            "card": card,
        }
        self.project.params = dict(self.paramset.values)
        self._clear_caches()
        return self.survey_state()

    def survey_revert(self) -> dict:
        """採寸チェックポイントへ復元する（設計をいじって破綻した時の回復）。"""
        assert self.project is not None
        cp = (self.project.survey or {}).get("checkpoint")
        if not cp:
            raise ValueError("復元点がありません。先に採寸を確定してください。")
        self.apply_params(dict(cp["params"]))
        if cp.get("refs") is not None:
            self.project.refs = copy.deepcopy(cp["refs"])
            self.component.set_refs(self.project.refs)
        self.size_overrides = dict(cp.get("size_overrides", {}))
        self._apply_size_overrides()
        self._clear_caches()
        return self.survey_state()

    def survey_clear(self) -> dict:
        """採寸ブロックと音響基準の上書きを破棄する（params は現状維持）。"""
        assert self.project is not None
        self.project.survey = None
        self.size_overrides = {}
        self._apply_size_overrides()
        self._clear_caches()
        return self.survey_state()


STATE = AppState()
