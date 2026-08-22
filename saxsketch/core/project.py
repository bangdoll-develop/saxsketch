"""プロジェクトファイル (.wproj) の管理。

.wproj = ZIP:
  project.json                … スキーマバージョン、楽器/テンプレート、メンバー
                                （部品ごとのパラメータ・メモ・凍結・派生・採寸）
  derived/<部品ID>/model.stl  … （任意）外部編集済みモデル（部品ごと）
後方互換は SCHEMA_VERSION と _migrate() で担保する。

**1 ファイル = 1 セット。単体プロジェクトはメンバー 1 個のセット**として同じ経路を
通る。開く/保存/最近使った/凍結/採寸/エクスポートを 2 本に割らないための形で、
v1（1 プロジェクト = 1 部品の平置き）は `_migrate()` がメンバー 1 個へ持ち上げる。

**楽器 ID とテンプレート ID はセットが 1 か所だけ持つ。** メンバーへ複製すると、
食い違ったときにどちらが正かがデータの有無で決まる規則になる（このリポジトリで
実際に起きた型）。セットの中では全メンバーが同じ楽器・同じサイズであることが
構造的に保証される。
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2


@dataclass
class Member:
    """セットの構成部品 1 つぶんの状態（v1 の Project の中身がそのまま入る）。"""

    component_id: str
    name: str = ""
    params: dict = field(default_factory=dict)
    # 参照コンポーネント（リード/リガチャーが従属するマウスピース等のスナップショット）
    #   {"mouthpiece": {"source": path|None, "label": str, "params": {...}}}
    # **セット内では使わない** —— 兄弟メンバーの現在値を `AppState._bind_refs()` が
    # そのつど束ねる（生きた参照）。ここに残るのは、セット外の .wproj から取り込んだ
    # 凍結スナップショットだけ。取込時点の値で固定し、参照元を後から編集しても
    # 自動追従しない（frozen と同じ思想）。
    refs: dict = field(default_factory=dict)
    notes: str = ""
    # 外部編集ワークフロー（省略可能な追加フィールド）
    frozen: dict | None = None        # {frozen_at, params, refs, solid_volume_cc, export_dir}
    derived: dict | None = None       # {imported_at, source_file, quality, analysis}
    derived_stl: bytes | None = None  # 編集済みモデル本体（ZIP内 derived/<部品ID>/model.stl）
    # 採寸ワークフロー（Phase 4-A。実物をノギスで測った値をプロジェクト局所で反映）
    #   {surveyed_at, note, measured, measured_size, checkpoint, card}
    #   measured=設計パラの実測 / measured_size=音響基準定数(size_info)の実測 /
    #   checkpoint=適用直後の復元点 {params, refs, size_overrides} / card=照合結果
    survey: dict | None = None

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "params": self.params,
            "refs": self.refs,
            "notes": self.notes,
            "frozen": self.frozen,
            "derived": self.derived,
            "survey": self.survey,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Member":
        return cls(
            component_id=data["component_id"],
            name=data.get("name", ""),
            params=data.get("params", {}) or {},
            refs=data.get("refs", {}) or {},   # refs 欠落の旧 .wproj は空 dict
            notes=data.get("notes", ""),
            frozen=data.get("frozen"),
            derived=data.get("derived"),
            survey=data.get("survey"),         # survey 欠落の旧 .wproj は None
        )


def _delegated(name: str) -> property:
    """active メンバーの属性へ委譲するプロパティ。

    単体しか無かった頃の `project.params` / `project.frozen` … がそのまま動く
    （読み書きとも active に効く）。呼び出し側を一斉に書き換えると、セットに
    関係の無い経路まで巻き添えで壊れる。
    """
    def getter(self: "Project"):
        return getattr(self.active_member, name)

    def setter(self: "Project", value):
        setattr(self.active_member, name, value)

    return property(getter, setter)


class Project:
    """セット（＝ .wproj 1 ファイル）。単体プロジェクトはメンバー 1 個。"""

    def __init__(self, instrument_id: str, template_id: str,
                 component_id: str | None = None,
                 name: str = "無題プロジェクト",
                 params: dict | None = None,
                 notes: str = "",
                 refs: dict | None = None,
                 schema_version: int = SCHEMA_VERSION,
                 path: str | None = None,
                 frozen: dict | None = None,
                 derived: dict | None = None,
                 derived_stl: bytes | None = None,
                 survey: dict | None = None,
                 members: dict[str, Member] | None = None,
                 active: str | None = None,
                 set_id: str | None = None):
        self.instrument_id = instrument_id
        self.template_id = template_id
        self.name = name
        self.schema_version = schema_version
        self.path = path            # 最後に保存したファイルパス
        self.set_id = set_id        # descriptor の sets[].id（単体は None）
        if members is None:
            if component_id is None:
                raise ValueError("component_id か members のどちらかが必要です")
            members = {component_id: Member(
                component_id=component_id, name=name, params=params or {},
                refs=refs or {}, notes=notes, frozen=frozen, derived=derived,
                derived_stl=derived_stl, survey=survey)}
        self.members: dict[str, Member] = members
        self.active: str = active or next(iter(self.members))

    # ------------------------------------------------------------ メンバー

    @property
    def active_member(self) -> Member:
        return self.members[self.active]

    def member(self, component_id: str) -> Member:
        return self.members[component_id]

    def has(self, component_id: str) -> bool:
        return component_id in self.members

    @property
    def is_set(self) -> bool:
        """実際に組になっているか（部品が 2 つ以上）。

        **`set_id` は見ない。** 見ると、部品を外して 1 個になったプロジェクトが
        「セット」を名乗り続け、出力の既定範囲もセット 3D も 1 部品のまま出る。
        `set_id` のほうは「どのセットへ育てられるか」を指すので消さない
        （`AppState.set_summary` が ＋ボタンを出すのに使う）。
        """
        return len(self.members) > 1

    def add_member(self, member: Member) -> None:
        self.members[member.component_id] = member

    def remove_member(self, component_id: str) -> None:
        if len(self.members) <= 1:
            raise ValueError("最後の 1 部品は取り外せません")
        del self.members[component_id]
        if self.active == component_id:
            self.active = next(iter(self.members))

    # ------------------------------------------------------------ 委譲プロパティ

    @property
    def component_id(self) -> str:
        return self.active_member.component_id

    params = _delegated("params")
    refs = _delegated("refs")
    notes = _delegated("notes")
    frozen = _delegated("frozen")
    derived = _delegated("derived")
    derived_stl = _delegated("derived_stl")
    survey = _delegated("survey")

    # ------------------------------------------------------------ 入出力

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "app": "SaxSketch",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "name": self.name,
            "instrument_id": self.instrument_id,
            "template_id": self.template_id,
            "set_id": self.set_id,
            "active": self.active,
            "members": {cid: m.to_dict() for cid, m in self.members.items()},
        }

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.json",
                        json.dumps(self.to_dict(), ensure_ascii=False, indent=2))
            for cid, m in self.members.items():
                if m.derived is not None and m.derived_stl is not None:
                    zf.writestr(f"derived/{cid}/model.stl", m.derived_stl)
        self.path = str(path)

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        path = Path(path)
        with zipfile.ZipFile(path) as zf:
            data = _migrate(json.loads(zf.read("project.json").decode("utf-8")))
            names = zf.namelist()
            members: dict[str, Member] = {}
            for cid, md in data["members"].items():
                m = Member.from_dict(md)
                if m.derived is not None:
                    # v2 は部品ごと。v1 から持ち上げたぶんは平置きの 1 本を拾う。
                    for arc in (f"derived/{cid}/model.stl", "derived/model.stl"):
                        if arc in names:
                            m.derived_stl = zf.read(arc)
                            break
                members[cid] = m
        p = cls(
            instrument_id=data["instrument_id"],
            template_id=data["template_id"],
            name=data.get("name", path.stem),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            members=members,
            active=data.get("active") or next(iter(members)),
            set_id=data.get("set_id"),
        )
        p.path = str(path)
        return p


def _migrate(data: dict) -> dict:
    """旧バージョンの project.json を現行スキーマへ変換する。"""
    version = int(data.get("schema_version", 1))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"このプロジェクトは新しいバージョン(v{version})で作成されています。"
            f"アプリを更新してください。"
        )
    if version < 2:
        # v1 = 1 プロジェクト 1 部品の平置き。メンバー 1 個のセットへ持ち上げる。
        cid = data["component_id"]
        data = {
            **data,
            "set_id": None,
            "active": cid,
            "members": {cid: {
                "component_id": cid,
                "name": data.get("name", ""),
                "params": data.get("params", {}),
                "refs": data.get("refs", {}) or {},
                "notes": data.get("notes", ""),
                "frozen": data.get("frozen"),
                "derived": data.get("derived"),
                "survey": data.get("survey"),
            }},
        }
    data["schema_version"] = SCHEMA_VERSION
    return data
