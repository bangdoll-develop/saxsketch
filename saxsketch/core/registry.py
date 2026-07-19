"""楽器・コンポーネントのプラグインレジストリ。

楽器の追加 = saxsketch/instruments/<id>/ ディレクトリを追加するだけ。
必要物:
  - descriptor.json  … 楽器の物理定数・メタ情報
  - templates/*.json … サイズテンプレート（パラメータ初期値）
  - components/      … Component 派生クラス（COMPONENTS で公開）
コアは楽器の中身を知らない。
"""
from __future__ import annotations

import importlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .schema import ParamSpec

INSTRUMENTS_DIR = Path(__file__).resolve().parent.parent / "instruments"


class Component(ABC):
    """設計対象コンポーネント（マウスピース、リード等）の基底クラス。"""

    id: str = ""
    label: str = ""  # 日本語名
    #: 従属先コンポーネントのID。設定するとプロジェクトが参照スナップショットを持つ
    #: （例: リード/リガチャー → "mouthpiece"）。None なら参照不要。
    REQUIRES_REF: str | None = None

    def __init__(self, descriptor: dict, template: dict):
        self.descriptor = descriptor
        self.template = template
        self.refs: dict = {}

    # ------------------------------------------------------------ 参照

    def set_refs(self, refs: dict) -> None:
        self.refs = refs or {}

    def ref_params(self) -> dict:
        """参照コンポーネントのパラメータ。未設定なら空 dict。"""
        entry = self.refs.get(self.REQUIRES_REF or "", {})
        return dict(entry.get("params", {}))

    def ref_dimensions(self) -> list[tuple[str, str]]:
        """参照の要約表示用の主要寸法（UI カード）。"""
        return []

    @abstractmethod
    def param_specs(self) -> list[ParamSpec]:
        ...

    @abstractmethod
    def build(self, params: dict) -> Any:
        """build123d の Part（水密ソリッド）を返す。"""

    @abstractmethod
    def simulate(self, params: dict) -> dict:
        """設計時シミュレーション結果（Tier1/2、感度、倍音列）を返す。"""

    @abstractmethod
    def bom(self, params: dict) -> list[dict]:
        """部品表の行リスト。"""

    def spec_extras(self, params: dict) -> dict:
        """仕様書用の追加情報。

        Returns:
            {"dimensions": [(名前, 値), …],
             "sections":   [{"title": str, "svg": str}, …]}

        断面図は各コンポーネントが `saxsketch.export.svg.polyline_svg()` を使って
        自分で組み立てる。共通側は図の中身を知らない（コアは楽器を知らない）。
        """
        return {}

    def regions(self, params: dict) -> dict:
        """各パラメータの影響領域 {key: {z0, z1, side, label}}（3Dハイライト用）。"""
        return {}

    def analyze_import(self, frozen_params: dict, ref_mesh, edited_mesh) -> dict:
        """外部編集モデルの解析。領域別偏差＋（可能なら）パラメータ逆算。

        Returns {"regions": [...], "params": [...], "warnings": [...]}
        既定実装は領域別偏差のみ。逆算は各コンポーネントでオーバーライド。
        """
        from saxsketch.analysis import meshdiff
        return {
            "regions": meshdiff.region_deviations(
                ref_mesh, edited_mesh, self.regions(frozen_params)),
            "params": [],
            "warnings": [],
        }

    # --- Tier3（音響）。対応するコンポーネントだけがオーバーライドする ---

    def impedance(self, params: dict) -> dict:
        """入力インピーダンス曲線。"""
        raise NotImplementedError(f"{self.label}にはインピーダンス計算がありません")

    def synthesize(self, params: dict, embouchure: str) -> tuple[bytes, dict]:
        """物理モデルによる単音の WAV。"""
        raise NotImplementedError(f"{self.label}には音合成がありません")

    def scale(self, params: dict) -> tuple[bytes, dict]:
        """物理モデルによる簡易スケールの WAV。"""
        raise NotImplementedError(f"{self.label}には音合成がありません")

    def cavity_volume(self, params: dict) -> dict:
        """内部空洞体積の高速近似 {"total_cc","effective_cc"}（ゴールシーク用）。"""
        raise NotImplementedError

    def goal_seek_size_info(self) -> dict:
        """Tier1 目標値などのサイズ情報（ゴールシーク用）。"""
        raise NotImplementedError

    @classmethod
    def available(cls) -> bool:
        """実装済みで選択可能か（未実装の将来コンポーネントは False）。"""
        return getattr(cls, "AVAILABLE", True)


class Instrument:
    def __init__(self, path: Path):
        self.path = path
        self.id = path.name
        self.descriptor = json.loads((path / "descriptor.json").read_text(encoding="utf-8"))
        self.templates: dict[str, dict] = {}
        for tf in sorted((path / "templates").glob("*.json")):
            self.templates[tf.stem] = json.loads(tf.read_text(encoding="utf-8"))
        mod = importlib.import_module(f"saxsketch.instruments.{self.id}.components")
        self.component_classes: dict[str, type[Component]] = mod.COMPONENTS

    def make_component(self, component_id: str, template_id: str) -> Component:
        cls = self.component_classes[component_id]
        template = self.templates[template_id]
        return cls(self.descriptor, template)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "label": self.descriptor.get("label", self.id),
            "templates": [
                {"id": tid, "label": t.get("label", tid)}
                for tid, t in self.templates.items()
            ],
            "components": [
                {"id": cid, "label": cls.label, "available": cls.available()}
                for cid, cls in self.component_classes.items()
            ],
        }


class Registry:
    def __init__(self):
        self.instruments: dict[str, Instrument] = {}
        for d in sorted(INSTRUMENTS_DIR.iterdir()):
            if d.is_dir() and (d / "descriptor.json").exists():
                self.instruments[d.name] = Instrument(d)

    def get(self, instrument_id: str) -> Instrument:
        return self.instruments[instrument_id]

    def summaries(self) -> list[dict]:
        return [i.summary() for i in self.instruments.values()]


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry
