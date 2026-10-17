"""サクソフォン リード コンポーネント。

参照マウスピース（`Component.REQUIRES_REF`）のテーブル幅・ウィンドウ長に従属する。
ジオメトリは `reed_profiles.sections()` を `loft_sections` でロフトするだけの
単一ソリッド（ブーリアン無し＝破綻しにくい）。
"""
from __future__ import annotations

from saxsketch.acoustics import reed_model
from saxsketch.core.dimension import dim
from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec
from saxsketch.geometry.builders import loft_sections

from saxsketch import i18n

from . import profiles
from . import reed_profiles as rp
from . import reed_seat
from . import reference_check

# 踵がリガチャー座の後端に届いているかの許容差 [mm]。**規格照合カードと同じ 1 個の値**
# を使う（同じ幾何を判定しているので、しきい値が 2 つあると片方だけ厳しくなる）。
SEAT_REACH_TOL = reference_check.SEAT_REACH_TOL

#: 前縁とマウスピースのティップ輪郭のずれをどこから警告するか [mm]。
#: **MP の輪郭を実測したサイズだけ**（`reference_check.mp_tip_contour_is_measured`、
#: いまは無い）。
#: **円弧では輪郭に 0.1mm より近づけない**（実物の輪郭は真円ではなく、既定同士でも
#: 0.094〜0.118 残る）ので、その残差を警告にしない値にする。他のカードと同じ 0.3。
TIP_CONTOUR_TOL = 0.3


def _reach_text(value: float | None, limit: tuple[float, float] | None,
                current: float) -> str:
    """推奨値の表示。**届かないときに端の値を解のように書かない。**

    4-C.2d 以前は 3 サイズ × 5 材料の 15 通りのうち 6 通りで、二分法の端
    （1.20mm）をそのまま「これで 3番相当になります」と書いていた。1.20mm でも
    2.72 にしかならない。届かないことは届かないと言う。
    """
    if value is not None:
        return i18n.t(
            "{value} mm（現在 {current}）",
            value=f"{value:.2f}", current=f"{current:.2f}")
    edge, got = limit
    return i18n.t(
        "届かない（可動域の端 {edge} mm でも {got}）",
        edge=f"{edge:.2f}", got=f"{got:.1f}")


def _specs(t: dict) -> list[ParamSpec]:
    """テンプレート値 t を初期値としてスキーマを構築。"""
    def f(key, label, cat, unit, lo, hi, step, effect, advanced=False, **kw):
        return ParamSpec(key=key, label=label, category=cat, type="float", unit=unit,
                         default=t[key], min=lo, max=hi, step=step, effect=effect,
                         advanced=advanced, **kw)

    return [
        # --- 寸法 ---
        f("reed_length", "リード全長", "寸法", "mm", 55.0, 90.0, 0.5,
          "規格長。踵位置がリガチャー座に一致する必要がある"),
        f("tip_width", "先端幅", "寸法", "mm", 9.0, 18.0, 0.1,
          "マウスピースのテーブル幅に合わせる。ずれるとサイドレールから漏れる"),
        f("heel_width", "踵幅", "寸法", "mm", 9.0, 18.0, 0.1,
          "踵側の幅。先端幅とのテーパー量を決める", advanced=True),
        # --- プロファイル ---
        # 可動域は `reed_model` の定数から引く。**推奨値のソルバと同じ域**でないと、
        # カードが UI で設定できない厚みを勧めることになる（4-C.2d で実際に起きた）。
        f("tip_thickness", "先端厚（中央）", "プロファイル", "mm",
          reed_model.TIP_THICKNESS_RANGE[0], reed_model.TIP_THICKNESS_RANGE[1], 0.01,
          "先端の閉じ方と立ち上がりを決める。**硬さへのレバーとしては最弱**"
          "（たわみ寄与は先端 1/4 で 6% 前後）。印刷の下限もここに当たる"),
        # 帯の上限は実物 15 本の最大（テナー #5 の 3.75、2026-09-23）。
        f("heel_thickness", "踵厚", "プロファイル", "mm", 1.8, 3.75, 0.05,
          "バーク（未削部）の厚み。規格寸法。テーブル密着に効く", advanced=True),
        # **壁は数字ではなく関係**（`param_bounds`）: 中央厚 − 側端厚 ≥
        # `rp.MIN_CROWN_MM`。以前は上限 1.6 を `heel_thickness` の下限 1.8 より
        # 小さく置いて**2 本の直値で**これを代理していたが、実物のアルト #1 の
        # 1.65（2026-09-21）を締め出した。帯の上限は実測 15 本の最大 2.45 ——
        # **上端はテナーの樹脂（Forestone HINOKI）で、ケーンは 3 サイズとも 1.8 以下**。
        # 樹脂リードは元のケーン管の円弧に縛られないので、ここだけ別の分布になる。
        f("heel_edge_thickness", "踵の側端厚", "プロファイル", "mm", 0.3, 2.45, 0.05,
          "元のケーン管の円弧を決める（断面がカマボコになる）。中央厚との差が"
          "大きいほど深い円弧。実物はアルト 5 本で 1.5〜1.65、ソプラノ 5 本で "
          "1.0〜1.45、テナー 5 本で 1.35〜2.45（2.45 は樹脂）",
          advanced=True,
          source="帯の上限は実物 15 本の最大（アルト 2026-09-21 / ソプラノ 09-22 / "
                 "テナー 09-23）。壁は踵厚 − 0.2",
          hard_max=3.75 - rp.MIN_CROWN_MM),
        f("vamp_length", "ヴァンプ長", "プロファイル", "mm",
          reed_model.VAMP_LENGTH_RANGE[0], reed_model.VAMP_LENGTH_RANGE[1], 0.5,
          "削り始めの位置。長いほど柔軟で低音寄り、短いと抵抗が増す。"
          "**硬さへのレバーとしては最強の部類**（±6mm で ±45〜75%）"),
        ParamSpec(key="profile_curve", label="プロファイル曲線", category="プロファイル",
                  type="choice", default=t["profile_curve"],
                  choices=[Choice("linear", "直線"),
                           Choice("parabolic", "放物（フレンチ系）"),
                           Choice("concave", "凹（アメリカン系）")],
                  effect="抵抗感とレスポンスの性格。凹=先端が薄く保たれ立ち上がりが速い"),
        f("spine_ratio", "背骨の広さ", "プロファイル", "指数", 1.0, 1.4, 0.05,
          "幅方向の薄化指数。大きいほど中央の平坦部（背骨）が広く芯が強い",
          advanced=True),
        # --- レール ---
        f("side_rail_thin", "サイドレール比", "レール", "比", 0.20, 1.00, 0.05,
          "側端厚 ÷ 中央厚。小さいほど柔軟で鳴りやすいが耐久が落ちる"),
        f("tip_corner_r", "先端角の丸み", "レール", "mm", 0.3, 2.0, 0.1,
          "平面視の先端角。マウスピースのティップレール形状に合わせる", advanced=True),
        # **帯は実測、壁は関係**（`param_bounds`）。帯の上限 3.0 は実物 15 本の
        # 逆算 1.91〜2.932 が入るぶん（出所の無い 2.5 が 6 本を、2.8 がテナーの
        # 3 本を締め出していた。2026-09-22 / 23）。壁は前縁アークが側面へ届く深さ
        # `rp.nose_depth_limit`（踵が広がらなければ半円）。**帯を 3.0 にしたことで、
        # 帯の上端が壁を越える組が初めて出た** —— 壁の最小は 2.976（先端 9.0 ×
        # 踵 18.0 × 全長 55 × 丸み 2.0 という隅）で、そこでは関係のほうが先に効いて
        # 2.976 で止まる。2.8 の頃は「帯はどの組でも壁の内側」だったが、それは
        # 偶然であって規則ではない（壁は関係、帯は実測。4-E の区別のまま）。
        # 実物のリードは 15 本とも踵が狭まる側なので、壁は先端幅の半分 ＝ 6.95 以上。
        # 2.8 以下で輪郭が折れて見えた 5 通り（先端 9.0 × 踵 ≥ 15.4）は、形では
        # なく `_nose_geometry` の反復の打ち切りだった（2026-09-23）。以前に見送った
        # 関係「半幅 − 丸み」は、踵が大きく広がる組では本当の壁より外にあった
        # （先端 9.0 × 踵 18.0 × 丸み 1.2 で 3.3 に対し 2.98）。掛け金は先端幅の
        # 上限の半分（半円）。
        f("tip_curve_depth", "先端カーブ", "レール", "mm", 0.0, 3.0, 0.1,
          "前縁の落ち込み。角が中央よりどれだけ後ろに来るか。0 にすると前縁が"
          "直線になり、角がティップレールより前へ出る。実物（逆算）はアルト 5 本で"
          " 1.91〜2.61、ソプラノ 5 本で 2.48〜2.72、テナー 5 本で 2.76〜2.93",
          source="帯の上限は実物 15 本の逆算の最大 2.932 を入れるぶん"
                 "（2026-09-21 / 22 / 23）。壁は前縁の円弧が側面に届く深さ"
                 "（踵が広がらなければ先端幅の半分）",
          hard_max=18.0 / 2.0),
        # --- カット ---
        ParamSpec(key="file_cut", label="カット種別", category="カット",
                  type="choice", default=t["file_cut"],
                  choices=[Choice("unfiled", "アンファイルド"),
                           Choice("filed", "ファイルド（表皮を一直線まで剥がす）")],
                  effect="ケーンの表皮をどこまで落とすか。ファイルド=削り終わりの"
                         "曲線より後ろも一直線の位置まで剥がすので、その間に"
                         "「表皮を削った部分」の帯が出る。明るく反応が速い傾向"),
        # --- 製造 ---
        ParamSpec(key="material", label="材料プリセット", category="製造",
                  type="choice", default=t["material"],
                  choices=[Choice(k, v[0])
                           for k, v in reed_model.MATERIALS.items()],
                  effect="ヤング率・密度から硬さ相当値と共振周波数を算出する。"
                         "工程（FDM / 光造形 / 切削）ごとの実用強度の下限もここから引く"),
        f("min_layer", "積層ピッチ", "製造", "mm",
          reed_model.MIN_LAYER_RANGE[0], reed_model.MIN_LAYER_RANGE[1], 0.01,
          "解像度の下限を決める（先端厚がこの3倍を下回ると造形できない）。"
          "光造形なら 0.02〜0.05、FDM なら 0.08〜0.20 が目安"),
    ]


class ReedComponent(Component):
    id = "reed"
    label = "リード"
    REQUIRES_REF = "mouthpiece"

    def __init__(self, descriptor: dict, template: dict):
        super().__init__(descriptor, template)
        self.size = template["size"]
        self.size_info = descriptor["sizes"][self.size]

    def param_specs(self) -> list[ParamSpec]:
        return _specs(self.template["reed"])

    def params_error(self, params: dict) -> str | None:
        return rp.cane_layout_error(params) or rp.nose_error(params)

    def param_bounds(self, params: dict) -> dict:
        """**相手で動く壁**: 踵の中央厚と側端厚、先端カーブ（Phase 4-F 実測）。

        - 踵: どちらを動かしても `cane_radius` の分母 `中央厚 − 側端厚` が
          `rp.MIN_CROWN_MM` を割らないようにする。以前はこの関係を 2 本の直値
          （側端厚 ≤ 1.6・中央厚 ≥ 1.8）に分けて持っていたので、実物の 1.65 が
          入らなかった。中央厚の側は**静的な下限 1.8 より緩めない**（あちらの
          出所は別で、ここで広げる理由が無い）。
        - 先端カーブ: 前縁アークが側面へ届く深さ（`rp.nose_bounds`）。相手は
          先端幅・踵幅・全長・丸みで、静的な端で届かないときだけ返る。

        判定は `rp.nose_bounds` / `params_error` の持ち主（`rp`）に書き、ここは
        繋ぐだけ（2 か所に書くと片方だけ直る）。
        """
        # `lo_by` / `hi_by` に相手の **label** を出すので訳した複製で引く。
        spec = {s.key: s for s in self.localized_specs()}
        crown = rp.MIN_CROWN_MM
        out = {"heel_edge_thickness": {"hi": params["heel_thickness"] - crown,
                                       "hi_by": spec["heel_thickness"].label}}
        lo_h = spec["heel_thickness"].bounds()[0]
        need = params["heel_edge_thickness"] + crown
        if need > lo_h:
            out["heel_thickness"] = {"lo": need,
                                     "lo_by": spec["heel_edge_thickness"].label}
        out.update(rp.nose_bounds(params, {k: spec[k].bounds() for k in
                                           ("tip_width", "heel_width",
                                            "reed_length", "tip_corner_r")}))
        return out

    # ------------------------------------------------------------ 参照

    def ref_dimensions(self) -> list[tuple[str, str]]:
        m = self.ref_params()
        if not m:
            return []
        seat0, seat1 = profiles.ligature_seat_range(m)
        return [
            # **`reed_width` を「テーブル幅」と呼ばない**（Phase 4-F）。あれは窓幅の
            # 公称値で、マウスピースの面を 1 つも決めていない。テーブルは平面カット
            # なので実幅は半径とカット深さから決まり、z で変わる。
            (i18n.t("テーブル実幅（帯の中央）"),
             f"{profiles.table_flat_width(m, (seat0 + seat1) / 2.0):.2f} mm"),
            (i18n.t("リード幅（規格の呼び）"), f"{m['reed_width']:.1f} mm"),
            # 指定値ではなく**実際に開く長さ**。`window_length` はボアの始まりで
            # 頭打ちになることがある（`profiles.window_length_effective`）。
            # リードが合わせる相手は形であって、スライダの値ではない。
            (i18n.t("ウィンドウ長"), f"{profiles.window_length_effective(m):.1f} mm"),
            (i18n.t("フェイシング長"), f"{m['facing_length']:.1f} mm"),
            (i18n.t("ティップ開き"), f"{m['tip_opening']:.2f} mm"),
            # **先端カーブにそのまま写す値ではない**（Phase 4-F 実測）。輪郭は
            # 角の近くで急に落ちる（alto で x=7.4→8.2 の 0.8mm で 1.9mm）ので、
            # 実物の幅 16.4 の角で読むと前縁の円弧とは別物になる。合わせたいときは
            # リードの適合カードの「輪郭に最も合う値」を読む。
            (i18n.t(
                "ティップ輪郭の落ち込み（x=±{reed_width}）",
                reed_width=f"{m['reed_width'] / 2.0:.1f}"),
             f"{self._ref_contour_depth(m):.2f} mm"),
        ]

    @staticmethod
    def _ref_contour_depth(m: dict, hw: float | None = None) -> float:
        """参照マウスピースのティップ輪郭が中央から x=±hw までに落ち込む量 [mm]。

        既定の hw は規格リードの角（`reed_width / 2`）。
        """
        hw = m["reed_width"] / 2.0 if hw is None else hw
        return profiles.tip_contour_z(m, hw) - profiles.tip_contour_z(m, 0.0)

    @staticmethod
    def _corner_half_width(p: dict, m: dict) -> float:
        """前縁を比べる幅の端 ＝ **リードが実際に達する半幅**と規格の角の小さいほう。

        以前は `min(tip_width, reed_width)/2`。`tip_width` は z=0 へ延ばした
        テーパーの値で、**先端が広いリードでは輪郭がそこまで届かない**
        （実物アルト #1: 先端幅 16.4 に対し全幅の点で 16.30）。届かない幅で
        `front_edge_z` を引くと「角の位置 = リード全長」が返っていた。
        """
        return min(rp.nose_half_width(p), p["tip_width"] / 2.0, m["reed_width"] / 2.0)

    def _best_curve_depth(self, p: dict, m: dict) -> tuple[float, float]:
        """(`_tip_contour_gap` をいちばん小さくする先端カーブ, そのときのずれ)。

        **スライダの刻みで探す** —— 勧める値は UI で置ける値でなければならない
        （`reed_model` の推奨値と同じ理由）。以前はマウスピースの輪郭が規格の角で
        落ち込む量をそのまま勧めていたが、輪郭は円弧ではない（中央が平らで角の
        近くで急に落ちる）ので、実物の幅 16.4 ではその値が 3.57 と出て、ずれを
        かえって広げる向きを勧めていた。
        """
        sp = {s.key: s for s in self.param_specs()}["tip_curve_depth"]
        # 探すのは**帯**（B-5 の「ゴールシークは帯のまま」）。壁は関係になって
        # 半円（掛け金 9.0）まで開いたので、`bounds()` を刻むと 3 倍の手間で
        # 勧めもしない深さを探し、先端が狭いと壁の外まで評価してしまう。
        lo, hi = sp.min, min(sp.max, rp.nose_depth_limit(p))
        n = int((hi - lo) / sp.step + 1e-9)       # 壁が刻みの間に来ても越えない
        # **輪郭は表にして補間する。** `tip_contour_z` は 1 点 0.4ms の二分法で、
        # 刻みごとに 41 点ずつ引くと `simulate` が 110 → 590ms になった（実測）。
        # 比べる幅の端は深さで動くが、`tip_width/2` と規格の角を越えない。
        # 61 点（0.14mm 刻み）の線形補間で、ずれの読みは 0.01mm 以内。
        x_end = min(p["tip_width"], m["reed_width"]) / 2.0
        xs = [x_end * i / 60.0 for i in range(61)]
        z0 = profiles.tip_contour_z(m, 0.0)
        zs = [profiles.tip_contour_z(m, x) - z0 for x in xs]

        def depth(x: float) -> float:
            j = min(int(x / x_end * 60.0), 59) if x_end > 0.0 else 0
            t = (x - xs[j]) / (xs[j + 1] - xs[j])
            return zs[j] + t * (zs[j + 1] - zs[j])

        best = None
        for i in range(n + 1):
            d = round(lo + i * sp.step, 6)
            g = self._tip_contour_gap({**p, "tip_curve_depth": d}, m, depth=depth)
            if best is None or abs(g) < abs(best[1]):
                best = (d, g)
        return best

    def _tip_contour_gap(self, p: dict, m: dict, samples: int = 40,
                         depth=None) -> float:
        """リード前縁と参照マウスピースのティップ輪郭の最大ずれ [mm]（符号付き）。

        正ならリードが後退（ティップレールが露出）、負なら前へ張り出す。
        比べるのは共通の x 範囲だけ（幅そのものの差は「幅の差」の行が見ている）。

        **角の丸みが効く区間は除く**（x > `_nose` の接点）。そこはリードが
        意図的に逃げている所で、0.46〜0.59mm の後退は形状の仕様であって
        「輪郭が合っていない」ではない。逃げの量は別の行が出す。

        `depth` は輪郭の落ち込み x → mm を差し替える口（`_best_curve_depth` が
        表の補間を渡す）。無ければ `tip_contour_z` をそのまま引く。
        """
        hw = self._corner_half_width(p, m)
        x_max = min(rp.arc_end_x(p), hw)
        if depth is None:
            z0 = profiles.tip_contour_z(m, 0.0)

            def depth(x: float) -> float:
                return profiles.tip_contour_z(m, x) - z0
        worst = 0.0
        for i in range(samples + 1):
            x = x_max * i / samples
            gap = rp.front_edge_z(p, x) - depth(x)
            if abs(gap) > abs(worst):
                worst = gap
        return worst

    def _corner_relief(self, p: dict, m: dict) -> tuple[float, float]:
        """(リードが全幅へ達する z, 参照MP のティップ輪郭が角で落ち込む量) [mm]。"""
        hw = self._corner_half_width(p, m)
        return (rp.front_edge_z(p, hw), self._ref_contour_depth(m, hw))

    # ------------------------------------------------------------ 採寸ワークフロー（Phase 4-F）

    #: ノギスで測れる設計パラだけ。比率（`spine_ratio` / `side_rail_thin`）と
    #: choice は測れないので入れない。`tip_corner_r` は半径ゲージが要るので外した。
    #: **`tip_curve_depth` は入れない** —— 直定規で測れるのは「側面がまっすぐに
    #: なる所」（`rp.tip_full_width_z`）で、パラメータそのもの（丸みを無視した
    #: 見かけの角）ではない。欄は `SURVEY_TIP_KEY` で受けて逆算する。
    _SURVEY_PARAM_KEYS = [
        "reed_length", "tip_width", "heel_width", "tip_thickness",
        "heel_thickness", "heel_edge_thickness", "vamp_length",
    ]
    #: 先端カーブの欄（パラメータではない仮想キー）。2026-09-21 のアルト採寸で
    #: 実測者が「側面がまっすぐになる所」まで測ったと確認した。以前はこの値を
    #: `tip_curve_depth` へそのまま入れる欄だったので、#1 の 2.7 がモデル値では
    #: 約 2.26 になるところを 0.4mm 深く取り込むところだった。
    SURVEY_TIP_KEY = "tip_full_width_z"
    #: 採寸できる基準定数。`reed_width_at20_mm` は幅のテーパーが直線かを反証する
    #: 欄（Phase 4-F）。**3 サイズで測った**（2026-09-21 / 22 / 23）: 直線は
    #: ほぼ成立して残差 −0.01〜+0.13（外へわずかに膨らむ側）、**外れていたのは
    #: 向き**で、旧既定は 3 サイズとも踵が 0.6 広く、実物は先端がアルトで 1.8〜2.2・
    #: ソプラノで 1.0〜1.4・テナーで 1.9〜2.2 広い。
    _SURVEY_SIZE_FIELDS = [
        {"key": "reed_std_length_mm", "label": "規格の全長", "unit": "mm"},
        {"key": "reed_std_tip_width_mm", "label": "規格の先端幅", "unit": "mm"},
        {"key": "reed_width_at20_mm", "label": "先端から 20mm の幅", "unit": "mm"},
    ]

    def survey_targets(self, values: dict | None = None) -> dict:
        """採寸フォームの入力欄。**範囲は帯ではなく壁**（`ParamSpec.bounds`）。

        ここに入るのは実物のリードをノギスで測った値なので、慣習の帯の外に
        あることがふつうにある（ソプラノの実測 2 本は 59.1 と 62.0）。

        リードはこれまで `survey_targets` を実装していなかったので、採寸パネルに
        入力欄が 1 つも出なかった（`registry.Component` の既定は空）。サーバも
        フロントも部品を選ばないので、ここを埋めるだけでワークフローが通る。
        """
        specs = {s.key: s for s in self.localized_specs()}
        params = []
        for k in self._SURVEY_PARAM_KEYS:
            if k not in specs:
                continue
            lo, hi = specs[k].bounds()
            params.append({"key": k, "label": specs[k].label,
                           "unit": specs[k].unit, "min": lo, "max": hi,
                           "step": specs[k].step})
        if "tip_curve_depth" in specs:
            # 範囲は `tip_curve_depth` の壁を全幅の位置へ写したもの（他の欄に
            # 合わせてテンプレート値の組で引く）。**壁は関係**なので組から引く ——
            # 掛け金（半円 9.0）のまま写すと、先端が狭い組では前縁が側面に届かない
            # 深さで `tip_full_width_z` を読むことになる。
            base = dict(self.template["reed"], **(values or {}))
            lo, _ = specs["tip_curve_depth"].bounds()
            hi = self.param_bounds(base)["tip_curve_depth"]["hi"]
            params.append({
                "key": self.SURVEY_TIP_KEY,
                "label": i18n.t("先端カーブ（側面がまっすぐになる所まで）"), "unit": "mm",
                "min": round(rp.tip_full_width_z({**base, "tip_curve_depth": lo}), 2),
                "max": round(rp.tip_full_width_z({**base, "tip_curve_depth": hi}), 2),
                "step": specs["tip_curve_depth"].step,
                "current": round(rp.tip_full_width_z(base), 2)})
        return {"params": params,
                "size": [dict(f, label=i18n.t(f["label"]))
                         for f in self._SURVEY_SIZE_FIELDS]}

    def survey_params(self, measured: dict, values: dict) -> dict:
        """先端カーブの欄を `tip_curve_depth` へ逆算する（ほかは素通し）。

        逆算は**同じ採寸で入った幅・長さを先に載せた組**で行う —— 全幅の位置は
        先端幅と角の丸みでも動くので、古い幅で解くと別のリードの深さになる。
        """
        out = dict(measured)
        z_full = out.pop(self.SURVEY_TIP_KEY, None)
        if z_full is not None:
            out["tip_curve_depth"] = rp.curve_depth_for_full_width_z(
                {**values, **out}, float(z_full))
        return out

    def survey_card(self, before_params: dict, before_size: dict,
                    measured_params: dict, measured_size: dict) -> dict | None:
        """採寸値 vs 採寸前。判定は `reference_check.survey_card`（1 か所）。"""
        return reference_check.survey_card(
            i18n.t("採寸 vs 設計（リード）"),
            {s.key: s for s in self.localized_specs()},
            {f["key"]: (i18n.t(f["label"]), f["unit"])
             for f in self._SURVEY_SIZE_FIELDS},
            before_params, before_size, measured_params, measured_size,
            i18n.t(
                "実測をプロジェクトへ反映しました。**1 本だけ入れないこと** —"
                "—銘柄・カットで寸法は動くので（全長はソプラノ 58.3〜62.0 / "
                "アルト 70.2〜72.8 / テナー 81.05〜82.7 と 2.6〜3.7mm "
                "振れる）、同じサイズを複数本まとめて測ってから入れてください"
                "。先端カーブは「側面がまっすぐになる所」"
                "まで測った値を入れれば、見かけの角（パラメータ）"
                "へ逆算して取り込みます。設計をいじって破綻したら「採寸時点へ"
                "戻す」で復元できます。"))

    # ------------------------------------------------------------ 形状生成

    def build(self, params: dict):
        """ロフト 1 回だけ。**ブーリアンを使わない。**

        ファイルド（表皮を一直線まで剥がす加工）は `reed_profiles.thickness` の
        天井として入っている。切除ソリッドで削っていた頃は、印刷される形だけが
        変わって `blade_volume_mm3` も `second_moment` も気づいていなかった。
        """
        return loft_sections(rp.sections(params))

    # ------------------------------------------------------------ シミュレーション

    def simulate(self, params: dict) -> dict:
        sim = {"kind": "reed", "cards": self._cards(params)}
        m = self.ref_params()
        if m:
            # 音プレビュー（印象合成）は参照マウスピースの音色指標から導く。
            # リード単体では音色を語れないので、組み合わせた状態の音を示す。
            from saxsketch.acoustics import brightness as ac_brightness
            from saxsketch.acoustics import harmonics as ac_harmonics
            sim["harmonics"] = ac_harmonics.harmonic_series(
                ac_brightness.tone_metrics(m))
        return sim

    def _cards(self, params: dict) -> list[dict]:
        # **1 回だけ解く。** 硬さカードと印刷カードが同じ `reed_properties` を読む
        # （推奨値のソルバが入っているので、2 回呼ぶとカードの応答が倍になる）。
        props = reed_model.reed_properties(params, self.ref_params())
        return [self._stiffness_card(params, props), self._fit_card(params),
                reference_check.reed_card(params, self.size_info),
                self._print_card(params, props)]

    def _stiffness_card(self, params: dict, props: dict) -> dict:
        p = params
        rows = [
            [i18n.t("リード共振 f_reed"), f"{props['f_reed_hz']:.0f} Hz"],
            [i18n.t("自由振動長"), f"{props['l_eff_mm']:.1f} mm"],
            [i18n.t("曲げ剛性 EI"), f"{props['ei_n_mm2']:.0f} N·mm²"],
            [i18n.t("先端たわみ"), f"{props['tip_compliance_mm_per_kpa']:.2f} mm / kPa"],
            # 「硬さは材質と厚さで決まるのか」への答え。たわみは z³ の重みなので
            # 固定端側が支配し、先端 1/4 の寄与は 6% 前後しかない。
            [i18n.t("たわみの寄与（先端→根元）"),
             " / ".join(f"{v:.0f}%" for v in props["deflection_bands"])],
            [i18n.t(
                "3番相当にする先端厚（{material}）",
                material=f"{reed_model.material_label(p['material'])}"),
             _reach_text(props["recommended_tip_mm"],
                         props["recommended_tip_limit"], p["tip_thickness"])],
            [i18n.t("3番相当にするヴァンプ長"),
             _reach_text(props["recommended_vamp_mm"],
                         props["recommended_vamp_limit"], rp.vamp_start_z(p))],
        ]
        s = props["strength_equiv"]
        if s < 1.5:
            status = "warn"
            advice = (i18n.t(
                "柔らかすぎます。先端が閉じきって音が詰まりやすく、"
                "耐久も落ちます。") + self._lever_hint(p, props))
        elif s > 5.0:
            status = "warn"
            advice = (i18n.t(
                "硬すぎます。鳴らすのに強い吹圧が要り、"
                "低音が出にくくなります。") + self._lever_hint(p, props))
        else:
            status, advice = "ok", (
                i18n.t(
                    "一般的な硬さのレンジです。数値は片持ち梁近似による推定な"
                    "ので、絶対値ではなくパラメータを動かしたときの変化方向を"
                    "見てください。"))
        return {"title": i18n.t("硬さ・剛性"), "big": props["strength_label"],
                "status": status, "rows": rows, "advice": advice}

    @staticmethod
    def _lever_hint(p: dict, props: dict) -> str:
        """どのパラメータを動かせば硬さが目標へ行くかの助言。

        **「先端厚を上げてください」だけを言っていたのをやめた。** たわみは
        `∫ w·z³/(2EI) dz` で固定端側が支配するため、先端厚はいちばん弱いレバー
        （寄与 6% 前後）。柔らかい材料だと可動域いっぱいでも届かないのに、
        以前は端の値を「これで 3番相当」と書いていた。
        """
        tip_pct = props["deflection_bands"][0]
        moves = []
        v = props["recommended_vamp_mm"]
        if v is not None:
            moves.append(i18n.t(
                "ヴァンプ長を {v}mm へ（現在 {rp}）",
                v=f"{v:.1f}", rp=f"{rp.vamp_start_z(p):.1f}"))
        t = props["recommended_tip_mm"]
        if t is not None:
            moves.append(i18n.t(
                "先端厚を {t}mm へ（現在 {tip_thickness}）",
                t=f"{t:.2f}", tip_thickness=f"{p['tip_thickness']:.2f}"))
        head = (i18n.t(
            "効くのはヴァンプ長とプロファイル曲線です —— "
            "たわみは先端からの距離の 3 乗で効くので固定端側が支配し、"
            "**先端厚の寄与は {tip_pct}% しかありません**。",
            tip_pct=f"{tip_pct:.0f}"))
        if not moves:
            return (head + i18n.t(
                "この材料と形では 3番相当に届きません。"
                "プロファイル曲線を「直線」寄りにするか、"
                "材料を硬いものへ変えてください。"))
        return head + i18n.t("3番相当にするなら ") + i18n.t(" か ").join(moves) + "。"

    def _fit_card(self, params: dict) -> dict:
        """参照マウスピースとの適合。ここが Phase 3 の「自動整合」の可視化。"""
        m = self.ref_params()
        p = params
        rows = [[i18n.t("リード先端幅 / 踵幅"),
                 f"{p['tip_width']:.1f} / {p['heel_width']:.1f} mm"]]
        status, advice = "ok", i18n.t("マウスピースのテーブル・レールに整合しています。")
        if not m:
            return {"title": i18n.t("マウスピース適合"), "big": None, "status": "warn",
                    "rows": rows, "advice": i18n.t("参照マウスピースが未設定です。")}

        # **裏面が密着するかは全長で見る**（Phase 4-F）。ここは長らく
        # `tip_width − reed_width` の 1 本だけで、相手はマウスピースの面を
        # 1 つも決めていない公称値だった。区間の切り方と判定は `reed_seat`。
        seat = reed_seat.seat_summary(m, p)
        sw, st = seat["window"], seat["table"]
        cover = reed_seat.cover_row(sw, self.size_info)
        rows.append(cover["row"])
        rows.append([i18n.t("帯までのはみ出し 最大"),
                     i18n.t("区間がありません") if st is None else
                     i18n.t("{mm} mm（z={z}）",
                            mm=f"{st['mm']:+.2f}", z=f"{st['z']:.1f}")])
        over = 0.0 if st is None else max(st["mm"], 0.0)
        zv = rp.vamp_start_z(p)
        win = profiles.window_length_effective(m)
        rows.append([i18n.t("ヴァンプ長 / ウィンドウ長"), f"{zv:.1f} / {win:.1f} mm"])
        seat0, seat1 = profiles.ligature_seat_range(m)
        rows.append([i18n.t("踵位置 / リガチャー座"),
                     f"{p['reed_length']:.1f} / "
                     + i18n.t("{lo}〜{hi}", lo=f"{seat0:.1f}",
                              hi=f"{seat1:.1f}") + " mm"])
        gap = self._tip_contour_gap(p, m)
        best_d, best_gap = self._best_curve_depth(p, m)
        # **MP 側の輪郭が未実測のサイズでは判定しない**（数字は出す）。ソプラノで
        # 実物と食い違った（`reference_check.mp_tip_contour_is_measured`）。
        contour_judged = reference_check.mp_tip_contour_is_measured(self.size_info)
        rows.append([i18n.t("先端カーブ / MPの輪郭に最も合う値"),
                     i18n.t(
                         "{tip_curve_depth} / {best_d} mm（最大ずれ {gap}、"
                         "合わせると {best_gap}）",
                         tip_curve_depth=f"{p['tip_curve_depth']:.2f}",
                         best_d=f"{best_d:.2f}", gap=f"{gap:+.2f}",
                         best_gap=f"{best_gap:+.2f}")
                     + ("" if contour_judged else
                        i18n.t("　参考: MP の輪郭が未実測のため判定しない"))])
        # 角は丸みの半径ぶん後ろへ逃げる。意図した造形なので判定には入れないが、
        # ティップレールがどれだけ露出するかは設計者が読める所に出しておく。
        reed_corner, mp_corner = self._corner_relief(p, m)
        rows.append([i18n.t("角の位置（リード / MP）"),
                     i18n.t(
                         "{reed_corner} / {mp_corner} mm（丸み "
                         "{tip_corner_r} ぶん {reed_corner2}）",
                         reed_corner=f"{reed_corner:.2f}",
                         mp_corner=f"{mp_corner:.2f}",
                         tip_corner_r=f"{p['tip_corner_r']:.1f}",
                         reed_corner2=f"{reed_corner - mp_corner:+.2f}")])

        if cover["verdict"] in ("軽微", "乖離"):
            status = "warn"
            advice = (i18n.t(
                "窓の区間（z={z}）でリードの縁がサイドレールに載らず、"
                "窓の上に {mm}mm 浮いています。脇から漏れます。"
                "先端幅を広げるか、マウスピースの窓を狭めてください。",
                z=f"{sw['z']:.1f}", mm=f"{-sw['mm']:.2f}"))
        elif over > reed_seat.OVER_TOL:
            status = "warn"
            advice = (i18n.t(
                "リガチャーが締める区間（z={z}）で縁がテーブルの外へ "
                "{over}mm 出ています。押しても密着しないので、"
                "そこは漏れます。踵幅を詰めるか、マウスピー"
                "スのボディ径を大きくしてください。"
                "**後ろへはみ出すぶんは害がありません** ——"
                "締めない区間なので参考値です。",
                z=f"{st['z']:.1f}", over=f"{over:.2f}"))
        elif zv < win * 0.75:
            status = "warn"
            advice = (i18n.t(
                "ヴァンプがウィンドウ長に対して短く、"
                "削り面が窓に届いていません。振動部が硬くなり鳴りにくくなりま"
                "す。"))
        elif p["reed_length"] < seat1 - SEAT_REACH_TOL:
            status = "warn"
            advice = (i18n.t(
                "踵がリガチャー座の後端（{seat1}mm）まで届いていません。"
                "リガチャーがリードの無い位置を締めることになり、"
                "固定できません。全長を伸ばしてください。",
                seat1=f"{seat1:.1f}"))
        elif contour_judged and abs(gap) > TIP_CONTOUR_TOL:
            status = "warn"
            fix = (i18n.t(
                "先端カーブを {best_d}mm にすると最大ずれが {best_gap}mm "
                "まで縮みます。",
                best_d=f"{best_d:.1f}", best_gap=f"{abs(best_gap):.2f}") if abs(best_gap) <= TIP_CONTOUR_TOL else
                   i18n.t(
                       "円弧の前縁ではこの輪郭に {tip_contour_tol}mm "
                       "以内まで寄せられません（いちばん近いのは {best_d}mm "
                       "で {best_gap}mm）。",
                       tip_contour_tol=f"{TIP_CONTOUR_TOL}",
                       best_d=f"{best_d:.1f}", best_gap=f"{abs(best_gap):.2f}"))
            advice = (
                i18n.t(
                    "前縁がマウスピースのティップ輪郭から最大 {gap}mm {vif}。",
                    gap=f"{abs(gap):.2f}",
                    vif=(i18n.t("後退しています（レールが露出）")
                         if gap > 0 else i18n.t("前へ張り出します")))
                + fix +
                i18n.t(
                    "ただし市販のリードは規格品でマウスピー"
                    "ス個体に合わせて作られていないので、"
                    "揃えるかどうかは設計の判断です。"))
        return {"title": i18n.t("マウスピース適合"), "big": None, "status": status,
                "rows": rows, "advice": advice}

    def _print_card(self, params: dict, props: dict) -> dict:
        """印刷可否。**下限を 2 つとも出し、どちらが効いているかを名指しする。**

        4-C.2d まで、この 2 つは別々の所に散らばって食い違っていた ——
        カードは `min_layer × 3` とハードコードの 0.35 を見て、`reed_properties`
        の `printable` は材料表の値を見ていて、しかも `printable` は**どこにも
        表示されていなかった**（tip=0.30 でカードは「要注意」・フラグは False）。
        意味の違う量なので両方残し、突き合わせて出す:

        - **解像度の下限** = 積層 × 3。工程を変えれば下がる（光造形なら 0.06mm）。
        - **実用強度の下限** = 材料表の値。**出典の無い仮定**で、下回っても
          「不可」ではなく「未確認」。
        """
        p = params
        res_floor = p["min_layer"] * 3.0
        str_floor = props["min_thickness_mm"]
        mat = f"{reed_model.material_label(p['material'])} / " \
              f"{reed_model.material_process(p['material'])}"
        binds = i18n.t("解像度") if res_floor >= str_floor else i18n.t("実用強度")
        rows = [
            [i18n.t("先端厚（中央）"), f"{p['tip_thickness']:.2f} mm"],
            [i18n.t(
                "解像度の下限（積層 {min_layer} × 3）",
                min_layer=f"{p['min_layer']:.2f}"),
             f"{res_floor:.2f} mm" + (i18n.t("  ← 効いている") if binds == "解像度" else "")],
            [i18n.t("実用強度の下限（{mat}）", mat=f"{mat}"),
             f"{str_floor:.2f} mm" + (i18n.t("  ← 効いている") if binds == "実用強度" else "")],
            [i18n.t("側端厚"), f"{rp.edge_thickness(p, 0.0):.2f} mm"],
            [i18n.t("材料体積"), f"{rp.blade_volume_mm3(p) / 1000.0:.2f} cc"],
        ]
        if p["tip_thickness"] < res_floor:
            return {"title": i18n.t("印刷可否"), "big": i18n.t("造形不可"), "status": "bad", "rows": rows,
                    "advice": i18n.t(
                        "先端厚が解像度の下限（積層 {min_layer} × 3 "
                        "= {res_floor}mm）を下回ります。"
                        "積層を細かくするか先端厚を上げてください。",
                        min_layer=f"{p['min_layer']:.2f}",
                        res_floor=f"{res_floor:.2f}")}
        if not props["printable"]:
            return {"title": i18n.t("印刷可否"), "big": i18n.t("要注意"), "status": "warn", "rows": rows,
                    "advice": i18n.t(
                        "造形はできますが、{mat} の実用強度の下限 "
                        "{str_floor}mm を下回ります。"
                        "**この下限は出典の無い仮定**で、"
                        "この薄さが屈曲に耐えるかは未確認です（実物のリー"
                        "ドは先端 0.1mm 前後ですが、それはケー"
                        "ンの繊維方向の強さがあってのものです）。",
                        mat=f"{mat}", str_floor=f"{str_floor:.2f}")}
        return {"title": i18n.t("印刷可否"), "big": i18n.t("造形可"), "status": "ok", "rows": rows,
                "advice": i18n.t(
                    "解像度・実用強度の下限をどちらも上回っています。"
                    "積層方向はリード長手方向に平行（面内）にしてください。")}

    # ------------------------------------------------------------ Tier3（物理モデル音）

    def _require_ref(self) -> dict:
        m = self.ref_params()
        if not m:
            raise RuntimeError(i18n.t("参照マウスピースが未設定のため音合成できません"))
        return m

    def _override(self, params: dict) -> dict:
        return reed_model.reed_override(
            reed_model.reed_properties(params, self.ref_params()), params)

    def impedance(self, params: dict) -> dict:
        """参照マウスピースの共鳴管インピーダンス（リードには依存しない）。"""
        from saxsketch.acoustics import openwind_bridge as ob
        return ob.impedance(self._require_ref(), self.size_info)

    def synthesize(self, params: dict, embouchure: str) -> tuple[bytes, dict]:
        """参照マウスピースの共鳴管に、このリードの実形状を結合して合成する。"""
        from saxsketch.acoustics import openwind_bridge as ob
        return ob.synthesize(self._require_ref(), self.size_info, embouchure,
                             override=self._override(params))

    def scale(self, params: dict) -> tuple[bytes, dict]:
        from saxsketch.acoustics import openwind_bridge as ob
        return ob.scale(self._require_ref(), self.size_info,
                        override=self._override(params))

    # ------------------------------------------------------------ 領域・BOM・仕様書

    def assembly_placement(self, params: dict) -> dict | None:
        """テーブル平面へ寝かせた姿（参照マウスピースのモデル座標）。

        リードのモデルは z=0 が先端・y=0 が平らな底面（`reed_profiles`）。組んだ姿は
        **底面がテーブル平面に載り、先端がティップレールの前縁に合う**位置。

        **傾きは平面そのものから測る**（`table_angle` の定数を読まない）。同じ
        `table_plane_y` から向きも位置も出すので、平面の定義が変われば置き場所も
        一緒に動く —— 符号を別に決め打つと、片方だけ直る状態が作れてしまう。

        参照マウスピースが無ければ `None`（置き場所が決まらない）。
        """
        import math

        m = self.ref_params()
        if not m:
            return None
        z_a = profiles.heel_z(m) * 0.5
        z_b = profiles.heel_z(m)
        slope = ((profiles.table_plane_y(m, z_b) - profiles.table_plane_y(m, z_a))
                 / (z_b - z_a))
        z0 = profiles.tip_contour_z(m, 0.0)      # 前縁が来る z（中央）
        return {"origin": [0.0, profiles.table_plane_y(m, z0), z0],
                "rotate_x_deg": math.degrees(math.atan(-slope)),
                # **裏返して載る。** リードの肉は底面 y=0 から +y へ付くが
                # （`reed_profiles.sections`）、テーブル平面は胴の下 ——
                # `table_plane_y` は負で、マウスピースの材料はその上（+y）に在る。
                # 載る側の外向き法線は −y なので、裏返さないと肉が丸ごと胴へ潜る
                # （アルト既定で +2.807mm ＝ リード厚 2.800 とほぼ一致した）。
                "flip_z": True}

    def regions(self, params: dict) -> dict:
        return rp.param_regions(params)

    def dimensions(self, params: dict) -> list[dict]:
        """主要寸法の寸法線。座標はリード自身の系（テーブル面 y=0・先端 z=0）。

        **先端の 2 本は z=0 に置けない。** 前縁カーブ（4-C.2b）のせいで z=0 の
        平面視幅は 0.5mm の刃で、`tip_width` の幅になるのは
        `tip_full_width_z`（既定 1.86 / 1.85 / 2.19）まで下がってから。幅の寸法は
        そこへ置き、前縁カーブの寸法は「実際に全幅へ達する z」を測る ——
        `tip_curve_depth` はフィレット前のアークが全幅に達する理論角なので、
        `dim()` が公称値として併記する（意図した造形なので警告にはしない）。
        """
        p = params
        sp = {s.key: s for s in self.localized_specs()}
        L = p["reed_length"]
        zv = rp.vamp_start_z(p)
        zf = rp.tip_full_width_z(p)
        w_tip = rp.width(p, zf)
        w_heel = rp.width(p, L)
        hw = p["heel_width"] / 2.0
        DOWN, FWD, AFT = (0.0, -1.0, 0.0), (0.0, 0.0, -1.0), (0.0, 0.0, 1.0)

        return [
            # --- 軸方向。テーブル面の下（材料の無い側）へ逃がす
            dim([0.0, 0.0, 0.0], [0.0, 0.0, zf], DOWN,
                spec=sp["tip_curve_depth"], params=p, level=0),
            dim([0.0, 0.0, 0.0], [0.0, 0.0, zv], DOWN,
                spec=sp["vamp_length"], params=p, level=1),
            dim([0.0, 0.0, 0.0], [0.0, 0.0, L], DOWN,
                spec=sp["reed_length"], params=p, level=2),
            # --- 幅（x 方向。断面には写らない）
            dim([-w_tip / 2.0, 0.0, zf], [w_tip / 2.0, 0.0, zf], DOWN,
                spec=sp["tip_width"], params=p, level=3),
            dim([-w_heel / 2.0, 0.0, L], [w_heel / 2.0, 0.0, L], DOWN,
                spec=sp["heel_width"], params=p, level=4),
            # --- 厚み
            dim([0.0, 0.0, 0.0], [0.0, rp.thickness(p, 0.0, 0.0), 0.0], FWD,
                spec=sp["tip_thickness"], params=p, level=0),
            dim([0.0, 0.0, L], [0.0, rp.thickness(p, L, 0.0), L], AFT,
                spec=sp["heel_thickness"], params=p, level=0),
            dim([hw, 0.0, L], [hw, rp.cane_top(p, hw), L], AFT,
                spec=sp["heel_edge_thickness"], params=p, level=1),
        ]

    def bom(self, params: dict) -> list[dict]:
        size_label = {"soprano": i18n.t("ソプラノ"), "alto": i18n.t("アルト"), "tenor": i18n.t("テナー")}[self.size]
        # 規格長は 1 点ではない（同じソプラノ用でケーン 59.1 / 樹脂 62.0 の実測差）。
        span = reference_check.reed_length_span(self.size_info)
        note = i18n.t(
            "口に触れる部品。食品接触適合材料を使用のこと（規格長 {span}mm）",
            span=f"{span}")
        return [
            {"type": i18n.t("3Dプリント"), "name": i18n.t("リード（{size_label}）", size_label=f"{size_label}"), "qty": 1,
             "material": reed_model.material_label(params["material"]),
             "note": note},
            {"type": i18n.t("市販品"), "name": i18n.t("リードケース"), "qty": 1, "material": "-",
             "note": i18n.t("反り防止（任意）")},
        ]

    def _section_svg(self, params: dict) -> str:
        """厚みプロファイル図（テーブル面 y=0 基準）。"""
        from saxsketch.export.svg import polyline_svg
        pr = rp.side_profile_polylines(params)
        zv = pr["vamp_start"]
        top = max(y for _, y in pr["center"])
        return polyline_svg([
            {"pts": pr["center"], "stroke": "#222", "width": 1.5},
            {"pts": pr["edge"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": pr["table"], "stroke": "#cc3300", "width": 0.8, "dash": "2 2"},
            {"pts": [(zv, 0.0), (zv, top)], "stroke": "#888", "width": 0.8, "dash": "3 3"},
        ], i18n.t(
            "厚みプロファイル（実線=中央 / 青破線=側端 / 赤破線=テーブル面 /"
            " 灰=ヴァンプ端） 単位:mm"))

    def _heel_section_svg(self, params: dict) -> str:
        """踵の断面図（カマボコ）。上面に残る元のケーン管の円弧を示す。"""
        from saxsketch.export.svg import polyline_svg
        p = params
        pts = rp.sections(p)[-1]["pts"]           # 最後のステーション＝踵の端面
        return polyline_svg([
            {"pts": list(pts) + [pts[0]], "stroke": "#222", "width": 1.5},
            {"pts": [(-p["heel_width"] / 2.0, 0.0), (p["heel_width"] / 2.0, 0.0)],
             "stroke": "#cc3300", "width": 0.8, "dash": "2 2"},
        ], i18n.t(
            "踵の断面（上面＝ケーン外径 φ{rp} の円弧 / 赤破線＝テーブル面） "
            "単位:mm",
            rp=f"{2.0 * rp.cane_radius(p):.1f}"))

    def spec_extras(self, params: dict) -> dict:
        p = params
        dims = [
            (i18n.t("全長"), f"{p['reed_length']:.1f} mm"),
            (i18n.t("先端幅 × 踵幅"), f"{p['tip_width']:.1f} × {p['heel_width']:.1f} mm"),
            (i18n.t("先端厚（中央/側端）"),
             f"{p['tip_thickness']:.2f} / {rp.edge_thickness(p, 0.0):.2f} mm"),
            (i18n.t("踵厚（中央/側端）"),
             f"{p['heel_thickness']:.2f} / {rp.heel_edge_thickness(p):.2f} mm"),
            # 側端厚は未実測なので、そこから導いたケーン外径も未実測。実物の踵端面を
            # 1 点測れば決まる（中央厚と踵幅は規格値なので、残りの自由度はこれだけ）。
            (i18n.t("ケーン外径（側端厚からの導出）"),
             i18n.t(
                 "φ{rp} mm（側端厚は未実測）",
                 rp=f"{2.0 * rp.cane_radius(p):.1f}")),
            (i18n.t("ヴァンプ長"), f"{rp.vamp_start_z(p):.1f} mm"),
            # 2 つ出すのは値が違うから。`tip_curve_depth` は前縁アークの理論的な角で、
            # 実際に全幅へ達するのは角の丸みぶん後ろ（既定で +0.46〜0.59mm）。
            (i18n.t("先端カーブ / 全幅に達する位置"),
             f"{p['tip_curve_depth']:.2f} / {rp.tip_full_width_z(p):.2f} mm"),
            (i18n.t("材料体積"), f"{rp.blade_volume_mm3(p) / 1000.0:.2f} cc"),
        ]
        m = self.ref_params()
        props = reed_model.reed_properties(p, m)
        dims.append((i18n.t("硬さ相当（推定）"), props["strength_label"]))
        dims.append((i18n.t("リード共振 f_reed（推定）"), f"{props['f_reed_hz']:.0f} Hz"))
        if m:
            # `reed_width` を「テーブル幅」と呼ばない（`ref_dimensions` の注記）。
            dims.append((i18n.t("参照マウスピース リード幅（規格の呼び）"),
                         f"{m['reed_width']:.1f} mm"))
            dims.append((i18n.t("先端カーブ / 参照マウスピースの輪郭に最も合う値"),
                         f"{p['tip_curve_depth']:.2f} / "
                         f"{self._best_curve_depth(p, m)[0]:.2f} mm"))
        return {"dimensions": dims,
                "sections": [{"title": i18n.t("厚みプロファイル"),
                              "svg": self._section_svg(p)},
                             {"title": i18n.t("踵の断面（カマボコ）"),
                              "svg": self._heel_section_svg(p)}]}
