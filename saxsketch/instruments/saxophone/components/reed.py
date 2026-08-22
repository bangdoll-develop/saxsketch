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

from . import profiles
from . import reed_profiles as rp
from . import reference_check

# 踵がリガチャー座の後端に届いているかの許容差 [mm]。**規格照合カードと同じ 1 個の値**
# を使う（同じ幾何を判定しているので、しきい値が 2 つあると片方だけ厳しくなる）。
SEAT_REACH_TOL = reference_check.SEAT_REACH_TOL

#: 前縁とマウスピースのティップ輪郭のずれをどこから警告するか [mm]。
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
        return f"{value:.2f} mm（現在 {current:.2f}）"
    edge, got = limit
    return f"届かない（可動域の端 {edge:.2f} mm でも {got:.1f}）"


def _specs(t: dict) -> list[ParamSpec]:
    """テンプレート値 t を初期値としてスキーマを構築。"""
    def f(key, label, cat, unit, lo, hi, step, effect, advanced=False):
        return ParamSpec(key=key, label=label, category=cat, type="float", unit=unit,
                         default=t[key], min=lo, max=hi, step=step, effect=effect,
                         advanced=advanced)

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
        f("heel_thickness", "踵厚", "プロファイル", "mm", 1.8, 3.6, 0.05,
          "バーク（未削部）の厚み。規格寸法。テーブル密着に効く", advanced=True),
        # 上限 1.6 は `heel_thickness` の下限 1.8 より小さい。これで
        # 中央厚 − 側端厚 ≥ 0.2 が構造的に保証され、`cane_radius` が発散する
        # 組み合わせをそもそも作れない（`params_error` を足さずに済む）。
        f("heel_edge_thickness", "踵の側端厚", "プロファイル", "mm", 0.3, 1.6, 0.05,
          "元のケーン管の円弧を決める（断面がカマボコになる）。中央厚との差が"
          "大きいほど深い円弧。未実測（実物の踵端面を 1 点測れば決まる）",
          advanced=True),
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
        f("tip_curve_depth", "先端カーブ", "レール", "mm", 0.0, 2.5, 0.1,
          "前縁の落ち込み。角が中央よりどれだけ後ろに来るか。0 にすると前縁が"
          "直線になり、マウスピースのティップレールから角が 1.3〜1.6mm 前へ出る"),
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
        return rp.cane_layout_error(params)

    # ------------------------------------------------------------ 参照

    def ref_dimensions(self) -> list[tuple[str, str]]:
        m = self.ref_params()
        if not m:
            return []
        return [
            ("テーブル幅（リード幅）", f"{m['reed_width']:.1f} mm"),
            # 指定値ではなく**実際に開く長さ**。`window_length` はボアの始まりで
            # 頭打ちになることがある（`profiles.window_length_effective`）。
            # リードが合わせる相手は形であって、スライダの値ではない。
            ("ウィンドウ長", f"{profiles.window_length_effective(m):.1f} mm"),
            ("フェイシング長", f"{m['facing_length']:.1f} mm"),
            ("ティップ開き", f"{m['tip_opening']:.2f} mm"),
            # 前縁を合わせたい人がそのまま読める値。合わせるかどうかは設計者の判断
            # なので、ここでリードのパラメータを書き換えたりはしない。
            ("ティップ輪郭の落ち込み", f"{self._ref_contour_depth(m):.2f} mm"),
        ]

    @staticmethod
    def _ref_contour_depth(m: dict) -> float:
        """参照マウスピースのティップ輪郭が中央から角までに落ち込む量 [mm]。"""
        return (profiles.tip_contour_z(m, m["reed_width"] / 2.0)
                - profiles.tip_contour_z(m, 0.0))

    def _tip_contour_gap(self, p: dict, m: dict, samples: int = 40) -> float:
        """リード前縁と参照マウスピースのティップ輪郭の最大ずれ [mm]（符号付き）。

        正ならリードが後退（ティップレールが露出）、負なら前へ張り出す。
        比べるのは共通の x 範囲だけ（幅そのものの差は「幅の差」の行が見ている）。

        **角の丸みが効く区間は除く**（x > `_nose` の接点）。そこはリードが
        意図的に逃げている所で、0.46〜0.59mm の後退は形状の仕様であって
        「輪郭が合っていない」ではない。逃げの量は別の行が出す。
        """
        hw = min(p["tip_width"], m["reed_width"]) / 2.0
        x_max = min(rp.arc_end_x(p), hw)
        z0 = profiles.tip_contour_z(m, 0.0)
        worst = 0.0
        for i in range(samples + 1):
            x = x_max * i / samples
            gap = rp.front_edge_z(p, x) - (profiles.tip_contour_z(m, x) - z0)
            if abs(gap) > abs(worst):
                worst = gap
        return worst

    def _corner_relief(self, p: dict, m: dict) -> tuple[float, float]:
        """(リードが全幅へ達する z, 参照MP のティップ輪郭が角で落ち込む量) [mm]。"""
        hw = min(p["tip_width"], m["reed_width"]) / 2.0
        return (rp.front_edge_z(p, hw),
                profiles.tip_contour_z(m, hw) - profiles.tip_contour_z(m, 0.0))

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
            ["リード共振 f_reed", f"{props['f_reed_hz']:.0f} Hz"],
            ["自由振動長", f"{props['l_eff_mm']:.1f} mm"],
            ["曲げ剛性 EI", f"{props['ei_n_mm2']:.0f} N·mm²"],
            ["先端たわみ", f"{props['tip_compliance_mm_per_kpa']:.2f} mm / kPa"],
            # 「硬さは材質と厚さで決まるのか」への答え。たわみは z³ の重みなので
            # 固定端側が支配し、先端 1/4 の寄与は 6% 前後しかない。
            ["たわみの寄与（先端→根元）",
             " / ".join(f"{v:.0f}%" for v in props["deflection_bands"])],
            [f"3番相当にする先端厚（{reed_model.material_label(p['material'])}）",
             _reach_text(props["recommended_tip_mm"],
                         props["recommended_tip_limit"], p["tip_thickness"])],
            ["3番相当にするヴァンプ長",
             _reach_text(props["recommended_vamp_mm"],
                         props["recommended_vamp_limit"], rp.vamp_start_z(p))],
        ]
        s = props["strength_equiv"]
        if s < 1.5:
            status = "warn"
            advice = ("柔らかすぎます。先端が閉じきって音が詰まりやすく、耐久も"
                      "落ちます。" + self._lever_hint(p, props))
        elif s > 5.0:
            status = "warn"
            advice = ("硬すぎます。鳴らすのに強い吹圧が要り、低音が出にくく"
                      "なります。" + self._lever_hint(p, props))
        else:
            status, advice = "ok", (
                "一般的な硬さのレンジです。数値は片持ち梁近似による推定なので、"
                "絶対値ではなくパラメータを動かしたときの変化方向を見てください。")
        return {"title": "硬さ・剛性", "big": props["strength_label"],
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
            moves.append(f"ヴァンプ長を {v:.1f}mm へ（現在 {rp.vamp_start_z(p):.1f}）")
        t = props["recommended_tip_mm"]
        if t is not None:
            moves.append(f"先端厚を {t:.2f}mm へ（現在 {p['tip_thickness']:.2f}）")
        head = (f"効くのはヴァンプ長とプロファイル曲線です —— たわみは先端からの"
                f"距離の 3 乗で効くので固定端側が支配し、**先端厚の寄与は"
                f" {tip_pct:.0f}% しかありません**。")
        if not moves:
            return (head + "この材料と形では 3番相当に届きません。"
                    "プロファイル曲線を「直線」寄りにするか、材料を硬いものへ"
                    "変えてください。")
        return head + "3番相当にするなら " + " か ".join(moves) + "。"

    def _fit_card(self, params: dict) -> dict:
        """参照マウスピースとの適合。ここが Phase 3 の「自動整合」の可視化。"""
        m = self.ref_params()
        p = params
        rows = [["リード先端幅", f"{p['tip_width']:.1f} mm"]]
        status, advice = "ok", "マウスピースのテーブル・レールに整合しています。"
        if not m:
            return {"title": "マウスピース適合", "big": None, "status": "warn",
                    "rows": rows, "advice": "参照マウスピースが未設定です。"}

        dw = p["tip_width"] - m["reed_width"]
        rows.append(["マウスピース テーブル幅", f"{m['reed_width']:.1f} mm"])
        rows.append(["幅の差", f"{dw:+.2f} mm"])
        zv = rp.vamp_start_z(p)
        win = profiles.window_length_effective(m)
        rows.append(["ヴァンプ長 / ウィンドウ長", f"{zv:.1f} / {win:.1f} mm"])
        seat0, seat1 = profiles.ligature_seat_range(m)
        rows.append(["踵位置 / リガチャー座",
                     f"{p['reed_length']:.1f} / {seat0:.1f}〜{seat1:.1f} mm"])
        gap = self._tip_contour_gap(p, m)
        rows.append(["先端カーブ / MPのティップ輪郭",
                     f"{p['tip_curve_depth']:.2f} / "
                     f"{self._ref_contour_depth(m):.2f} mm（最大ずれ {gap:+.2f}）"])
        # 角は丸みの半径ぶん後ろへ逃げる。意図した造形なので判定には入れないが、
        # ティップレールがどれだけ露出するかは設計者が読める所に出しておく。
        reed_corner, mp_corner = self._corner_relief(p, m)
        rows.append(["角の位置（リード / MP）",
                     f"{reed_corner:.2f} / {mp_corner:.2f} mm"
                     f"（丸み {p['tip_corner_r']:.1f} ぶん {reed_corner - mp_corner:+.2f}）"])

        if abs(dw) > 0.3:
            status = "warn"
            advice = (f"幅が {abs(dw):.2f}mm {'広い' if dw > 0 else '狭い'}です。"
                      f"{'サイドレールからはみ出します。' if dw > 0 else '脇から息が漏れます。'}"
                      f"先端幅を {m['reed_width']:.1f}mm に合わせてください。")
        elif zv < win * 0.75:
            status = "warn"
            advice = ("ヴァンプがウィンドウ長に対して短く、削り面が窓に届いていません。"
                      "振動部が硬くなり鳴りにくくなります。")
        elif p["reed_length"] < seat1 - SEAT_REACH_TOL:
            status = "warn"
            advice = (f"踵がリガチャー座の後端（{seat1:.1f}mm）まで届いていません。"
                      f"リガチャーがリードの無い位置を締めることになり、固定できません。"
                      f"全長を伸ばしてください。")
        elif abs(gap) > TIP_CONTOUR_TOL:
            status = "warn"
            advice = (
                f"前縁がマウスピースのティップ輪郭から最大 {abs(gap):.2f}mm "
                f"{'後退しています（レールが露出）' if gap > 0 else '前へ張り出します'}。"
                f"先端カーブを {self._ref_contour_depth(m):.1f}mm 前後にすると揃います。"
                f"ただし市販のリードは規格品でマウスピース個体に合わせて作られていない"
                f"ので、揃えるかどうかは設計の判断です。")
        return {"title": "マウスピース適合", "big": None, "status": status,
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
        binds = "解像度" if res_floor >= str_floor else "実用強度"
        rows = [
            ["先端厚（中央）", f"{p['tip_thickness']:.2f} mm"],
            [f"解像度の下限（積層 {p['min_layer']:.2f} × 3）",
             f"{res_floor:.2f} mm" + ("  ← 効いている" if binds == "解像度" else "")],
            [f"実用強度の下限（{mat}）",
             f"{str_floor:.2f} mm" + ("  ← 効いている" if binds == "実用強度" else "")],
            ["側端厚", f"{rp.edge_thickness(p, 0.0):.2f} mm"],
            ["材料体積", f"{rp.blade_volume_mm3(p) / 1000.0:.2f} cc"],
        ]
        if p["tip_thickness"] < res_floor:
            return {"title": "印刷可否", "big": "造形不可", "status": "bad", "rows": rows,
                    "advice": f"先端厚が解像度の下限（積層 {p['min_layer']:.2f} × 3 "
                              f"= {res_floor:.2f}mm）を下回ります。積層を細かくするか"
                              f"先端厚を上げてください。"}
        if not props["printable"]:
            return {"title": "印刷可否", "big": "要注意", "status": "warn", "rows": rows,
                    "advice": f"造形はできますが、{mat} の実用強度の下限 "
                              f"{str_floor:.2f}mm を下回ります。**この下限は出典の"
                              f"無い仮定**で、この薄さが屈曲に耐えるかは未確認です"
                              f"（実物のリードは先端 0.1mm 前後ですが、それはケーンの"
                              f"繊維方向の強さがあってのものです）。"}
        return {"title": "印刷可否", "big": "造形可", "status": "ok", "rows": rows,
                "advice": "解像度・実用強度の下限をどちらも上回っています。"
                          "積層方向はリード長手方向に平行（面内）にしてください。"}

    # ------------------------------------------------------------ Tier3（物理モデル音）

    def _require_ref(self) -> dict:
        m = self.ref_params()
        if not m:
            raise RuntimeError("参照マウスピースが未設定のため音合成できません")
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
        sp = {s.key: s for s in self.param_specs()}
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
        size_label = {"soprano": "ソプラノ", "alto": "アルト", "tenor": "テナー"}[self.size]
        # 規格長は 1 点ではない（同じソプラノ用でケーン 59.1 / 樹脂 62.0 の実測差）。
        span = reference_check.reed_length_span(self.size_info)
        note = f"口に触れる部品。食品接触適合材料を使用のこと（規格長 {span}mm）"
        return [
            {"type": "3Dプリント", "name": f"リード（{size_label}）", "qty": 1,
             "material": reed_model.material_label(params["material"]),
             "note": note},
            {"type": "市販品", "name": "リードケース", "qty": 1, "material": "-",
             "note": "反り防止（任意）"},
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
        ], "厚みプロファイル（実線=中央 / 青破線=側端 / 赤破線=テーブル面 / "
           "灰=ヴァンプ端） 単位:mm")

    def _heel_section_svg(self, params: dict) -> str:
        """踵の断面図（カマボコ）。上面に残る元のケーン管の円弧を示す。"""
        from saxsketch.export.svg import polyline_svg
        p = params
        pts = rp.sections(p)[-1]["pts"]           # 最後のステーション＝踵の端面
        return polyline_svg([
            {"pts": list(pts) + [pts[0]], "stroke": "#222", "width": 1.5},
            {"pts": [(-p["heel_width"] / 2.0, 0.0), (p["heel_width"] / 2.0, 0.0)],
             "stroke": "#cc3300", "width": 0.8, "dash": "2 2"},
        ], f"踵の断面（上面＝ケーン外径 φ{2.0 * rp.cane_radius(p):.1f} の円弧 / "
           f"赤破線＝テーブル面） 単位:mm")

    def spec_extras(self, params: dict) -> dict:
        p = params
        dims = [
            ("全長", f"{p['reed_length']:.1f} mm"),
            ("先端幅 × 踵幅", f"{p['tip_width']:.1f} × {p['heel_width']:.1f} mm"),
            ("先端厚（中央/側端）",
             f"{p['tip_thickness']:.2f} / {rp.edge_thickness(p, 0.0):.2f} mm"),
            ("踵厚（中央/側端）",
             f"{p['heel_thickness']:.2f} / {rp.heel_edge_thickness(p):.2f} mm"),
            # 側端厚は未実測なので、そこから導いたケーン外径も未実測。実物の踵端面を
            # 1 点測れば決まる（中央厚と踵幅は規格値なので、残りの自由度はこれだけ）。
            ("ケーン外径（側端厚からの導出）",
             f"φ{2.0 * rp.cane_radius(p):.1f} mm（側端厚は未実測）"),
            ("ヴァンプ長", f"{rp.vamp_start_z(p):.1f} mm"),
            # 2 つ出すのは値が違うから。`tip_curve_depth` は前縁アークの理論的な角で、
            # 実際に全幅へ達するのは角の丸みぶん後ろ（既定で +0.46〜0.59mm）。
            ("先端カーブ / 全幅に達する位置",
             f"{p['tip_curve_depth']:.2f} / {rp.tip_full_width_z(p):.2f} mm"),
            ("材料体積", f"{rp.blade_volume_mm3(p) / 1000.0:.2f} cc"),
        ]
        m = self.ref_params()
        props = reed_model.reed_properties(p, m)
        dims.append(("硬さ相当（推定）", props["strength_label"]))
        dims.append(("リード共振 f_reed（推定）", f"{props['f_reed_hz']:.0f} Hz"))
        if m:
            dims.append(("参照マウスピース テーブル幅", f"{m['reed_width']:.1f} mm"))
            dims.append(("参照マウスピース ティップ輪郭の落ち込み",
                         f"{self._ref_contour_depth(m):.2f} mm"))
        return {"dimensions": dims,
                "sections": [{"title": "厚みプロファイル",
                              "svg": self._section_svg(p)},
                             {"title": "踵の断面（カマボコ）",
                              "svg": self._heel_section_svg(p)}]}
