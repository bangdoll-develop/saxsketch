"""パラメータスキーマエンジン。

各コンポーネントは ParamSpec のリストでパラメータを宣言する。
UI はこのスキーマを取得して編集パネルを自動生成する（楽器非依存）。

**壁は 2 種類ある。** `min`/`max` は「勧める帯」、`hard_min`/`hard_max` は
「越えられない壁」。以前は 1 種類しか無く、しかも `validate` が範囲外を
**黙ってクランプ**していたので、利用者にはスライダが勝手に戻ったようにしか
見えなかった。壁の性格（`limit_kind`）と出所（`source`）を持たせ、
クランプしたら口に出す（`ParamSet.adjustments`）。

**そして壁の 3 つ目 —— 相手で動く壁**（Phase 4-E B-5）。Phase B で 29 本の壁を
掃引で測ったら、**9 本は「数字」ではなく「関係」**だった（`bore_dia` <
`shank_dia`、全長 ≥ ボア長 + 窓の取り分、踵の床は `shank_length` と
`shoulder_ratio` の組、など）。`ParamSpec` は静的な数字しか持てないので、
`hard_*` に入っているのはテンプレート値で作った**掛け金**でしかなく、副作用が
3 つ出ていた ——帯の端が壁の外へはみ出す（12 端のうち 6 端）、関係する 2 本を
両方とも壁へ置くと 400 で断られる、型で実効範囲が変わる `baffle_plateau` の
スライダが 86% 死ぬ。

そこで `ParamSet` は**組から壁を引き直せる**ようにした（`bounds_provider`
＝ `Component.param_bounds`）。掛け金は**外さない** ——`params` を持たない
経路（プロジェクト読み込み、直に組んだ dict、掃引器）が帯まで縮むのを
避けるため。動的な壁があるときは**それが掛け金を上書きする**（相手を太く
すれば壁は掛け金より外へも動く）。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from saxsketch import i18n

#: 壁の出所の分類。**説明のためのラベルで、硬さは決めない**（硬さを決めるのは
#: `hard_min`/`hard_max` があるかどうかだけ。`ParamSpec.bounds`）。既定は
#: `unclassified` ＝「まだ誰も分類していない」で、`hard_*` も無いのが普通なので
#: **分類していないパラメータの挙動は現行と 1 ビットも変わらない**。
#: いま分類済みなのはマウスピースの 33 個だけで、リード・リガチャー・ネック・
#: 管体はまだ `unclassified` のまま。**Phase B はマウスピースの 29 本を測って
#: 終わった**ので、残り 4 部品はまだどのスライスにも入っていない
#: （`Component.param_bounds` も空 dict のままで、挙動は現行どおり）。
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

    def coerce(self, value: Any) -> Any:
        """**型だけ**合わせる（範囲は見ない）。不正な choice は default へ。

        `ParamSet.apply` が「利用者が意図した組」を作るために使う ——
        相手で動く壁は**その組から**引くので、丸める前の値が要る
        （`baffle_type` を切り替えると `baffle_plateau` の壁が動く、など）。
        """
        if self.type == "bool":
            return bool(value)
        if self.type == "choice":
            return value if value in {c.value for c in self.choices} else self.default
        return int(round(float(value))) if self.type == "int" else float(value)

    def validate(self, value: Any, bound: dict | None = None) -> Any:
        """値を型変換し範囲にクランプして返す。不正な choice は default に戻す。"""
        return self.validate_report(value, bound)[0]

    def validate_report(self, value: Any,
                        bound: dict | None = None) -> tuple[Any, dict | None]:
        """`validate` の実体。**丸めたときは何をしたか一緒に返す。**

        黙ってクランプすると、利用者にはスライダが勝手に戻ったようにしか
        見えない（既知 8 例目）。呼び出し側（`ParamSet.apply`）がこれを溜めて
        UI へ渡す。

        `bound` は**相手で動く壁**（`Component.param_bounds` が返す
        `{"lo", "hi", "lo_by", "hi_by"}`）。入っている側は `hard_*` の掛け金を
        **上書きする** ——掛け金はテンプレート値で作った静的な数字なので、
        相手を動かせば内側にも外側にもずれる。丸めたときは相手の名前を文面に
        出す（**この方式そのものが黙ったクランプの 9 例目にならないように**）。
        """
        if self.type in ("bool", "choice"):
            v = self.coerce(value)
            if self.type == "bool" or v == value:
                return v, None
            return self.default, {
                "key": self.key, "label": self.label, "unit": self.unit,
                "requested": value, "applied": self.default, "edge": "choice",
                "partner": None,
                "limit_kind": self.limit_kind, "source": self.source,
                "message": (i18n.t(
                    "{self}に不明な値 {value} が来たので既定 {self2} "
                    "に戻しました",
                    self=f"{self.label}", value=f"{value!r}",
                    self2=f"{self.default!r}")),
            }
        v = self.coerce(value)
        req = v
        lo, hi = self.bounds()
        by_lo = by_hi = ""
        if bound:
            if bound.get("lo") is not None:
                lo, by_lo = bound["lo"], bound.get("lo_by", "")
            if bound.get("hi") is not None:
                hi, by_hi = bound["hi"], bound.get("hi_by", "")
        edge = None
        if lo is not None and v < lo:
            v, edge = lo, "min"
        if hi is not None and v > hi:
            v, edge = hi, "max"
        if edge is None:
            return v, None
        side = i18n.t("下限") if edge == "min" else i18n.t("上限")
        src = self.source or i18n.t("記載なし")
        # 単位の前に空白を置くのは「比」「度」でも読めるようにするため。
        unit = f" {self.unit}" if self.unit else ""
        # **どちらの境界に当たったかを言い分ける。** 帯を広げてあるパラメータで
        # 「推奨帯の上限」と言うと、帯（越えられる）と壁（越えられない）を
        # 取り違えさせる —— 実際に止めたのは壁のほう。
        by = by_lo if edge == "min" else by_hi
        hard = self.hard_min if edge == "min" else self.hard_max
        partner = None
        if by:
            # **相手で動く壁。** ここだけは掛け金や帯より先に名乗る ——
            # 「なぜここで止まるのか」の答えが相手の名前そのものなので、
            # 「越えられない壁」とだけ言うと相手を動かせば届くことが伝わらない。
            at, partner = "relation", by
            why = i18n.t(
                "{by}で決まる壁の{side}（{by2}を動かすとここも動きます）",
                by=f"{by}", side=f"{side}", by2=f"{by}")
        elif hard is not None:
            at = "wall"
            # 帯が片側しか無い spec でも落ちないようにしておく（いまは無いが、
            # `hard_*` だけ入れた spec を後から足せてしまう）。
            band = ("" if self.min is None or self.max is None else
                    i18n.t(
                        "（勧める帯は {self}〜{self2}{unit}）",
                        self=f"{self.min:g}", self2=f"{self.max:g}",
                        unit=f"{unit.strip()}"))
            why = i18n.t(
                "越えられない壁の{side}{band}",
                side=f"{side}", band=f"{band}")
        else:
            at = "band"
            kind = i18n.limit_kind_label(
                self.limit_kind,
                LIMIT_KIND_LABELS.get(self.limit_kind, self.limit_kind))
            why = i18n.t("{kind}の{side}", kind=f"{kind}", side=f"{side}")
        return v, {
            "key": self.key, "label": self.label, "unit": self.unit,
            "requested": req, "applied": v, "edge": edge, "at": at,
            "partner": partner,
            "limit_kind": self.limit_kind, "source": self.source,
            "message": (i18n.t(
                "{self} {req} → {v}{unit} に丸めました（{why}、出所: {src}）",
                self=f"{self.label}", req=f"{req:g}", v=f"{v:g}",
                unit=f"{unit}", why=f"{why}", src=f"{src}")),
        }


class ParamSet:
    """スキーマ + 現在値。テンプレート値 → プロジェクト差分 の順で重ねる。"""

    def __init__(self, specs: list[ParamSpec], template_values: dict | None = None,
                 bounds_provider: Any = None):
        self.specs = {s.key: s for s in specs}
        self.values: dict[str, Any] = {k: s.default for k, s in self.specs.items()}
        #: 直近の `apply` で丸めた項目。**署名を変えずに報告を足すため**に
        #: 属性で持つ（`apply` の呼び出しは 5 か所ある）。
        self.adjustments: list[dict] = []
        #: 相手で動く壁を引く関数（`Component.param_bounds`）。`None` なら
        #: 掛け金と帯だけ ＝ **入れない部品の挙動は 1 ビットも変わらない**。
        self.bounds_provider = bounds_provider
        if template_values:
            self.apply(template_values)

    def bounds_for(self, values: dict | None = None) -> dict:
        """その組での動的な壁 `{key: {"lo","hi","lo_by","hi_by"}}`。

        provider を持たなければ空 dict。**例外は握り潰さない** ——
        provider は「型さえ合っていればどんな組でも答えられる」ことになって
        いて（`profiles` 側のヘルパは 0 除算も負の分母も自分で処理する）、
        黙って壁が消える経路を作ると、その先で起きる丸めが原因不明になる。
        """
        if self.bounds_provider is None:
            return {}
        return self.bounds_provider(dict(self.values if values is None else values))

    def apply(self, values: dict) -> dict:
        """複数値を検証つきで適用。適用後の全値を返す。未知キーは無視。

        丸めた項目は `self.adjustments` に残す。**毎回入れ替える**ので、
        直前の適用の結果だけが入っている。

        **壁は「頼まれた組」から引く。** 型変換だけした値をいまの値へ重ねて
        から `bounds_for` を呼ぶので、`baffle_type` を切り替えた同じ apply で
        `baffle_plateau` の壁が新しい型のものになる。関係する 2 本を同時に
        動かした組（踵の床の `shank_length` と `shoulder_ratio` が実例）でも、
        互いの壁が**頼まれたほうの値**から引かれるので両方が内側へ寄る。

        **引き直すのは 1 巡だけ。** 2 巡目は丸めた後の値から壁を引くことに
        なり、1 巡目で内側へ寄せた組では壁が**緩む** ——せっかく成立させた
        丸めを解いて元の組へ戻してしまう。1 巡で成立しない組は
        `params_error` が断る（`AppState.apply_params`）。

        **丸めるのは頼まれたキーだけ。** 全キーを丸め直すと、相手を細くした
        だけで利用者が触っていない値が動く ——それは「黙って設計が変わる」
        側の壊れ方で、断られるより悪い。
        """
        self.adjustments = []
        wanted = {k: v for k, v in values.items() if k in self.specs}
        if not wanted:
            return dict(self.values)
        trial = dict(self.values)
        trial.update({k: self.specs[k].coerce(v) for k, v in wanted.items()})
        bnds = self.bounds_for(trial)
        for k in wanted:
            # 報告は**頼まれた生の値**から作る（`trial` は既に型変換済みなので、
            # 不正な choice がここでは「既定に戻した」と言えなくなる）。
            self.values[k], adj = self.specs[k].validate_report(wanted[k], bnds.get(k))
            if adj is not None:
                self.adjustments.append(adj)
        return dict(self.values)

    def get(self, key: str) -> Any:
        return self.values[key]

    def schema_dicts(self) -> list[dict]:
        return [s.to_dict() for s in self.specs.values()]
