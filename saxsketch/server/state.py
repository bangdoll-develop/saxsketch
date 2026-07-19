"""アプリケーション状態（シングルユーザー・ローカルアプリ）。"""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
from pathlib import Path

from saxsketch.core.project import Project
from saxsketch.core.registry import get_registry
from saxsketch.core.schema import ParamSet

SETTINGS_DIR = Path.home() / ".saxsketch"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
DEFAULT_EXPORT_ROOT = Path.home() / "Documents" / "SaxSketch"

DEFAULT_SETTINGS = {
    "external_tools": {
        "freecad": "",
        "slicer": "",
        "openwind_note": "Phase 2 で統合予定",
    },
    "recent_projects": [],
    "export_root": str(DEFAULT_EXPORT_ROOT),
}


class AppState:
    def __init__(self):
        self.registry = get_registry()
        self.project: Project | None = None
        self.component = None
        self.paramset: ParamSet | None = None
        self.build_lock = threading.Lock()
        self._stl_cache: dict[str, bytes] = {}
        self._imp_cache: dict[str, dict] = {}
        self._wav_cache: dict[str, tuple] = {}
        self.settings = self._load_settings()

    # ---------------------------------------------------------- 設定

    def _load_settings(self) -> dict:
        if SETTINGS_FILE.exists():
            try:
                loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                merged = dict(DEFAULT_SETTINGS)
                merged.update(loaded)
                return merged
            except Exception:
                pass
        return dict(DEFAULT_SETTINGS)

    def save_settings(self) -> None:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def push_recent(self, path: str) -> None:
        recent = [p for p in self.settings.get("recent_projects", []) if p != path]
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
        self._stl_cache.clear()
        self._imp_cache.clear()
        self._wav_cache.clear()
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
        self._stl_cache.clear()
        self._imp_cache.clear()
        self._wav_cache.clear()
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
            inst = self.registry.get(src.instrument_id)
            ref_comp = inst.make_component(ref_id, src.template_id)
            ps = ParamSet(ref_comp.param_specs(),
                          ref_comp.template.get(ref_id, {}))
            ps.apply(src.params)
            self.project.refs[ref_id] = {
                "source": path, "label": src.name, "params": dict(ps.values)}
        self.component.set_refs(self.project.refs)
        self._stl_cache.clear()
        self._imp_cache.clear()
        self._wav_cache.clear()

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
        assert self.paramset is not None and self.project is not None
        applied = self.paramset.apply(values)
        self.project.params = dict(applied)
        return applied

    # ---------------------------------------------------------- 形状

    def _params_key(self) -> str:
        payload = json.dumps(
            {"i": self.project.instrument_id, "t": self.project.template_id,
             "c": self.project.component_id, "p": self.paramset.values,
             "r": self.project.refs},
            sort_keys=True, default=str)
        return hashlib.md5(payload.encode()).hexdigest()

    def build_part(self):
        with self.build_lock:
            return self.component.build(dict(self.paramset.values))

    def get_stl_bytes(self, tolerance: float = 0.03) -> bytes:
        key = self._params_key() + f":{tolerance}"
        cached = self._stl_cache.get(key)
        if cached is not None:
            return cached
        from saxsketch.export.models import export_model
        part = self.build_part()
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "model.stl"
            export_model(part, f, "stl", tolerance=tolerance)
            data = f.read_bytes()
        # キャッシュは直近3件のみ保持
        if len(self._stl_cache) > 3:
            self._stl_cache.clear()
        self._stl_cache[key] = data
        return data

    def simulate(self) -> dict:
        return self.component.simulate(dict(self.paramset.values))

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
        """凍結後にパラメータが変更されたか。"""
        if self.project is None or self.project.frozen is None:
            return False
        frozen_params = self.project.frozen["params"]
        cur = self.paramset.values
        for k, v in frozen_params.items():
            if cur.get(k) != v:
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
                       "quality": p.derived["quality"]}
        return {"frozen": frozen, "derived": derived, "stale": self.is_stale()}

    def freeze(self, export_dir: str, solid_volume_cc: float | None) -> dict:
        """現パラメータで凍結スナップショットを記録。既存の派生モデルは破棄。"""
        from datetime import datetime, timezone
        assert self.project is not None
        self.project.frozen = {
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "params": dict(self.paramset.values),
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

    def analyze_derived(self, path: str) -> dict:
        """編集済みモデルを読み込み解析（まだ登録しない）。"""
        from saxsketch.analysis import meshdiff
        assert self.project is not None and self.project.frozen is not None
        frozen_params = dict(self.project.frozen["params"])

        edited = meshdiff.load_mesh(path)
        quality = meshdiff.mesh_quality(edited)

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

    def commit_derived(self) -> dict:
        """解析済みモデルをプロジェクトに登録。"""
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


STATE = AppState()
