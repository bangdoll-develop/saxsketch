"""パラメータスキーマエンジン。

各コンポーネントは ParamSpec のリストでパラメータを宣言する。
UI はこのスキーマを取得して編集パネルを自動生成する（楽器非依存）。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Choice:
    value: str
    label: str  # 日本語表示名


@dataclass
class ParamSpec:
    key: str
    label: str               # 日本語表示名
    category: str            # UIグルーピング（例: フェイシング）
    type: str = "float"      # float | int | choice | bool
    unit: str = ""           # mm, °, 比 など
    default: Any = 0.0
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[Choice] = field(default_factory=list)
    effect: str = ""         # 音・演奏性への効果の説明
    advanced: bool = False   # 詳細設定に折りたたむか

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def validate(self, value: Any) -> Any:
        """値を型変換し範囲にクランプして返す。不正な choice は default に戻す。"""
        if self.type == "bool":
            return bool(value)
        if self.type == "choice":
            valid = {c.value for c in self.choices}
            return value if value in valid else self.default
        if self.type == "int":
            v = int(round(float(value)))
        else:
            v = float(value)
        if self.min is not None:
            v = max(v, self.min)
        if self.max is not None:
            v = min(v, self.max)
        return v


class ParamSet:
    """スキーマ + 現在値。テンプレート値 → プロジェクト差分 の順で重ねる。"""

    def __init__(self, specs: list[ParamSpec], template_values: dict | None = None):
        self.specs = {s.key: s for s in specs}
        self.values: dict[str, Any] = {k: s.default for k, s in self.specs.items()}
        if template_values:
            self.apply(template_values)

    def apply(self, values: dict) -> dict:
        """複数値を検証つきで適用。適用後の全値を返す。未知キーは無視。"""
        for k, v in values.items():
            spec = self.specs.get(k)
            if spec is not None:
                self.values[k] = spec.validate(v)
        return dict(self.values)

    def get(self, key: str) -> Any:
        return self.values[key]

    def schema_dicts(self) -> list[dict]:
        return [s.to_dict() for s in self.specs.values()]
