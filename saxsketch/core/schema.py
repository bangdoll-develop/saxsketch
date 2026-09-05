"""パラメータスキーマエンジン。

各コンポーネントは ParamSpec のリストでパラメータを宣言する。
UI はこのスキーマを取得して編集パネルを自動生成する（楽器非依存）。

**壁は 2 種類ある。** `min`/`max` は「勧める帯」、`hard_min`/`hard_max` は
「越えられない壁」。以前は 1 種類しか無く、しかも `validate` が範囲外を
**黙ってクランプ**していたので、利用者にはスライダが勝手に戻ったようにしか
見えなかった。壁の性格（`limit_kind`）と出所（`source`）を持たせ、
クランプしたら口に出す（`ParamSet.adjustments`）。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

#: 壁の出所の分類。**説明のためのラベルで、硬さは決めない**（硬さを決めるのは
#: `hard_min`/`hard_max` があるかどうかだけ。`ParamSpec.bounds`）。既定は
#: `unclassified` ＝「まだ誰も分類していない」で、`hard_*` も無いのが普通なので
#: **分類していないパラメータの挙動は現行と 1 ビットも変わらない**。
#: いま分類済みなのはマウスピースの 33 個だけで、リード・リガチャー・ネック・
#: 管体はまだ `unclassified` のまま（Phase B で順に埋める）。
LIMIT_KINDS = ("geometry", "manufacturing", "convention", "unclassified")

#: 表示用。クランプ報告の文面に入る。
LIMIT_KIND_LABELS = {
    "geometry": "幾何の成立条件",
    "manufacturing": "製造の制約",
    "convention": "慣習の推奨帯",
    "unclassified": "未分類の壁",
}


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
    #: 壁の性格（`LIMIT_KINDS`）。既定 `unclassified` は**現行と同じ挙動**。
    limit_kind: str = "unclassified"
    #: `min`/`max` の出所。実測・文献・暫定など。**空なら「記載なし」と表示する**
    #: ——空欄を埋めるために出所を発明しない。
    source: str = ""
    #: 越えられない壁。`None` なら `min`/`max` がそのまま壁になる。
    hard_min: float | None = None
    hard_max: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def bounds(self) -> tuple[float | None, float | None]:
        """実際にクランプする境界。

        **`hard_*` が入っていればそれが壁、無ければ `min`/`max` が壁。**
        `min`/`max` は常に「勧める帯」で、`hard_*` を入れたぶんだけ帯の外へ
        出られるようになる。`limit_kind` は**説明のためのラベル**で、
        硬さそのものは決めない —— 1 本のパラメータでも下限が幾何・上限が慣習
        ということがあり（`shank_length` の 0 と 30.0 がそれ）、片側ずつ
        `hard_min` / `hard_max` で緩められる必要があるため。

        `hard_*` を 1 つも入れなければ**現行と完全に同じ**挙動になる。
        """
        lo = self.hard_min if self.hard_min is not None else self.min
        hi = self.hard_max if self.hard_max is not None else self.max
        return lo, hi

    def validate(self, value: Any) -> Any:
        """値を型変換し範囲にクランプして返す。不正な choice は default に戻す。"""
        return self.validate_report(value)[0]

    def validate_report(self, value: Any) -> tuple[Any, dict | None]:
        """`validate` の実体。**丸めたときは何をしたか一緒に返す。**

        黙ってクランプすると、利用者にはスライダが勝手に戻ったようにしか
        見えない（既知 8 例目）。呼び出し側（`ParamSet.apply`）がこれを溜めて
        UI へ渡す。
        """
        if self.type == "bool":
            return bool(value), None
        if self.type == "choice":
            valid = {c.value for c in self.choices}
            if value in valid:
                return value, None
            return self.default, {
                "key": self.key, "label": self.label, "unit": self.unit,
                "requested": value, "applied": self.default, "edge": "choice",
                "limit_kind": self.limit_kind, "source": self.source,
                "message": (f"{self.label}に不明な値 {value!r} が来たので既定 "
                            f"{self.default!r} に戻しました"),
            }
        v = int(round(float(value))) if self.type == "int" else float(value)
        req = v
        lo, hi = self.bounds()
        edge = None
        if lo is not None and v < lo:
            v, edge = lo, "min"
        if hi is not None and v > hi:
            v, edge = hi, "max"
        if edge is None:
            return v, None
        side = "下限" if edge == "min" else "上限"
        src = self.source or "記載なし"
        # 単位の前に空白を置くのは「比」「度」でも読めるようにするため。
        unit = f" {self.unit}" if self.unit else ""
        # **どちらの境界に当たったかを言い分ける。** 帯を広げてあるパラメータで
        # 「推奨帯の上限」と言うと、帯（越えられる）と壁（越えられない）を
        # 取り違えさせる —— 実際に止めたのは壁のほう。
        hard = self.hard_min if edge == "min" else self.hard_max
        if hard is not None:
            at = "wall"
            # 帯が片側しか無い spec でも落ちないようにしておく（いまは無いが、
            # `hard_*` だけ入れた spec を後から足せてしまう）。
            band = ("" if self.min is None or self.max is None else
                    f"（勧める帯は {self.min:g}〜{self.max:g}{unit.strip()}）")
            why = f"越えられない壁の{side}{band}"
        else:
            at = "band"
            kind = LIMIT_KIND_LABELS.get(self.limit_kind, self.limit_kind)
            why = f"{kind}の{side}"
        return v, {
            "key": self.key, "label": self.label, "unit": self.unit,
            "requested": req, "applied": v, "edge": edge, "at": at,
            "limit_kind": self.limit_kind, "source": self.source,
            "message": (f"{self.label} {req:g} → {v:g}{unit} に丸めました"
                        f"（{why}、出所: {src}）"),
        }


class ParamSet:
    """スキーマ + 現在値。テンプレート値 → プロジェクト差分 の順で重ねる。"""

    def __init__(self, specs: list[ParamSpec], template_values: dict | None = None):
        self.specs = {s.key: s for s in specs}
        self.values: dict[str, Any] = {k: s.default for k, s in self.specs.items()}
        #: 直近の `apply` で丸めた項目。**署名を変えずに報告を足すため**に
        #: 属性で持つ（`apply` の呼び出しは 5 か所ある）。
        self.adjustments: list[dict] = []
        if template_values:
            self.apply(template_values)

    def apply(self, values: dict) -> dict:
        """複数値を検証つきで適用。適用後の全値を返す。未知キーは無視。

        丸めた項目は `self.adjustments` に残す。**毎回入れ替える**ので、
        直前の適用の結果だけが入っている。
        """
        self.adjustments = []
        for k, v in values.items():
            spec = self.specs.get(k)
            if spec is not None:
                self.values[k], adj = spec.validate_report(v)
                if adj is not None:
                    self.adjustments.append(adj)
        return dict(self.values)

    def get(self, key: str) -> Any:
        return self.values[key]

    def schema_dicts(self) -> list[dict]:
        return [s.to_dict() for s in self.specs.values()]
