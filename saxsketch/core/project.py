"""プロジェクトファイル (.wproj) の管理。

.wproj = ZIP:
  project.json      … スキーマバージョン、楽器/テンプレート/コンポーネントID、
                       全パラメータ、メモ、凍結スナップショット、派生モデルのメタ
  derived/model.stl … （任意）外部編集済みモデル
後方互換は SCHEMA_VERSION と _migrate() で担保する。
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


@dataclass
class Project:
    instrument_id: str
    template_id: str
    component_id: str
    name: str = "無題プロジェクト"
    params: dict = field(default_factory=dict)
    notes: str = ""
    schema_version: int = SCHEMA_VERSION
    path: str | None = None  # 最後に保存したファイルパス
    # 参照コンポーネント（リード/リガチャーが従属するマウスピース等のスナップショット）
    #   {"mouthpiece": {"source": path|None, "label": str, "params": {...}}}
    # 取込時点の値で固定する。参照元を後から編集しても自動追従しない（frozen と同じ思想）。
    refs: dict = field(default_factory=dict)
    # 外部編集ワークフロー（省略可能な追加フィールド。v1 のまま後方互換）
    frozen: dict | None = None        # {frozen_at, params, solid_volume_cc, export_dir}
    derived: dict | None = None       # {imported_at, source_file, quality, analysis}
    derived_stl: bytes | None = None  # 編集済みモデル本体（ZIP内 derived/model.stl）
    # 採寸ワークフロー（Phase 4-A。実物をノギスで測った値をプロジェクト局所で反映）
    #   {surveyed_at, note, measured, measured_size, checkpoint, card}
    #   measured=設計パラの実測 / measured_size=音響基準定数(size_info)の実測 /
    #   checkpoint=適用直後の復元点 {params, refs, size_overrides} / card=照合結果
    # frozen と同じく後方互換の任意フィールド。旧 .wproj は None で読める。
    survey: dict | None = None

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "app": "SaxSketch",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "name": self.name,
            "instrument_id": self.instrument_id,
            "template_id": self.template_id,
            "component_id": self.component_id,
            "params": self.params,
            "refs": self.refs,
            "notes": self.notes,
            "frozen": self.frozen,
            "derived": self.derived,
            "survey": self.survey,
        }

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.json", json.dumps(self.to_dict(), ensure_ascii=False, indent=2))
            if self.derived is not None and self.derived_stl is not None:
                zf.writestr("derived/model.stl", self.derived_stl)
        self.path = str(path)

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        path = Path(path)
        with zipfile.ZipFile(path) as zf:
            data = json.loads(zf.read("project.json").decode("utf-8"))
            data = _migrate(data)
            derived_stl = None
            if data.get("derived") is not None and "derived/model.stl" in zf.namelist():
                derived_stl = zf.read("derived/model.stl")
        p = cls(
            instrument_id=data["instrument_id"],
            template_id=data["template_id"],
            component_id=data["component_id"],
            name=data.get("name", path.stem),
            params=data.get("params", {}),
            refs=data.get("refs", {}) or {},  # refs 欠落の旧 .wproj は空 dict
            notes=data.get("notes", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            frozen=data.get("frozen"),
            derived=data.get("derived"),
            derived_stl=derived_stl,
            survey=data.get("survey"),  # survey 欠落の旧 .wproj は None
        )
        p.path = str(path)
        return p


def _migrate(data: dict) -> dict:
    """旧バージョンの project.json を現行スキーマへ変換する。"""
    version = data.get("schema_version", 1)
    # 現状 v1 のみ。将来: if version == 1: ... data["schema_version"] = 2
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"このプロジェクトは新しいバージョン(v{version})で作成されています。"
            f"アプリを更新してください。"
        )
    return data
