"""サクソフォン リード コンポーネント。

参照マウスピース（`Component.REQUIRES_REF`）のテーブル幅・ウィンドウ長に従属する。
ジオメトリは `reed_profiles.sections()` を `loft_sections` でロフトするだけの
単一ソリッド（ブーリアン無し＝破綻しにくい）。
"""
from __future__ import annotations

from saxsketch.acoustics import reed_model
from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec
from saxsketch.geometry.builders import loft_sections, yz_profile_cut_solid

from . import profiles
from . import reed_profiles as rp
from . import reference_check

# 踵がリガチャー座の後端に届いているかの許容差 [mm]。**規格照合カードと同じ 1 個の値**
# を使う（同じ幾何を判定しているので、しきい値が 2 つあると片方だけ厳しくなる）。
SEAT_REACH_TOL = reference_check.SEAT_REACH_TOL


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
        f("tip_thickness", "先端厚（中央）", "プロファイル", "mm", 0.15, 0.90, 0.01,
          "硬さへの影響が最大の要素。薄いほど軽く鳴るが潰れやすく、印刷下限もある"),
        f("heel_thickness", "踵厚", "プロファイル", "mm", 1.8, 3.6, 0.05,
          "バーク（未削部）の厚み。規格寸法。テーブル密着に効く", advanced=True),
        f("vamp_length", "ヴァンプ長", "プロファイル", "mm", 18.0, 48.0, 0.5,
          "削り始めの位置。長いほど柔軟で低音寄り、短いと抵抗が増す"),
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
        # --- カット ---
        ParamSpec(key="file_cut", label="カット種別", category="カット",
                  type="choice", default=t["file_cut"],
                  choices=[Choice("unfiled", "アンファイルド"),
                           Choice("filed", "ファイルド（横一文字）")],
                  effect="ファイルド=削り終わりが直線。明るく反応が速い傾向"),
        # --- 製造 ---
        ParamSpec(key="material", label="材料プリセット", category="製造",
                  type="choice", default=t["material"],
                  choices=[Choice(k, v[0])
                           for k, v in reed_model.MATERIALS.items()],
                  effect="ヤング率・密度から硬さ相当値と共振周波数を算出する"),
        f("min_layer", "積層ピッチ", "製造", "mm", 0.04, 0.20, 0.01,
          "印刷可否の判定に使う。先端厚がこの3倍を下回ると造形できない"),
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

    # ------------------------------------------------------------ 参照

    def ref_dimensions(self) -> list[tuple[str, str]]:
        m = self.ref_params()
        if not m:
            return []
        return [
            ("テーブル幅（リード幅）", f"{m['reed_width']:.1f} mm"),
            ("ウィンドウ長", f"{m['window_length']:.1f} mm"),
            ("フェイシング長", f"{m['facing_length']:.1f} mm"),
            ("ティップ開き", f"{m['tip_opening']:.2f} mm"),
        ]

    # ------------------------------------------------------------ 形状生成

    def build(self, params: dict):
        p = params
        part = loft_sections(rp.sections(p))
        if p.get("file_cut") == "filed":
            # ファイルドカット: バーク端に横一文字の段差を入れる（上面のみ薄く削る）
            zv = rp.vamp_start_z(p)
            depth = min(0.25, p["heel_thickness"] * 0.12)
            top = p["heel_thickness"] + 1.0
            cut = [(zv - 1.2, top), (zv + 1.2, top),
                   (zv + 1.2, p["heel_thickness"] - depth),
                   (zv - 1.2, p["heel_thickness"] - depth)]
            part = part - yz_profile_cut_solid(cut, half_width=p["heel_width"])
        return part

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
        return [self._stiffness_card(params), self._fit_card(params),
                reference_check.reed_card(params, self.size_info),
                self._print_card(params)]

    def _stiffness_card(self, params: dict) -> dict:
        props = reed_model.reed_properties(params, self.ref_params())
        rows = [
            ["リード共振 f_reed", f"{props['f_reed_hz']:.0f} Hz"],
            ["自由振動長", f"{props['l_eff_mm']:.1f} mm"],
            ["曲げ剛性 EI", f"{props['ei_n_mm2']:.0f} N·mm²"],
            ["先端たわみ", f"{props['tip_compliance_mm_per_kpa']:.2f} mm / kPa"],
            [f"3番相当にする先端厚（{reed_model.material_label(params['material'])}）",
             f"{props['recommended_tip_mm']:.2f} mm（現在 {params['tip_thickness']:.2f}）"],
        ]
        s = props["strength_equiv"]
        if s < 1.5:
            status, advice = "warn", (
                "柔らかすぎます。先端が閉じきって音が詰まりやすく、耐久も落ちます。"
                "先端厚を上げるか、ヴァンプを短くしてください。")
        elif s > 5.0:
            rec = props["recommended_tip_mm"]
            status, advice = "warn", (
                "硬すぎます。鳴らすのに強い吹圧が要り、低音が出にくくなります。"
                f"この材料なら先端厚 {rec:.2f}mm で 3番相当になります"
                f"（現在 {params['tip_thickness']:.2f}mm）。")
        else:
            status, advice = "ok", (
                "一般的な硬さのレンジです。数値は片持ち梁近似による推定なので、"
                "絶対値ではなくパラメータを動かしたときの変化方向を見てください。")
        return {"title": "硬さ・剛性", "big": props["strength_label"],
                "status": status, "rows": rows, "advice": advice}

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
        rows.append(["ヴァンプ長 / ウィンドウ長",
                     f"{zv:.1f} / {m['window_length']:.1f} mm"])
        seat0, seat1 = profiles.ligature_seat_range(m)
        rows.append(["踵位置 / リガチャー座",
                     f"{p['reed_length']:.1f} / {seat0:.1f}〜{seat1:.1f} mm"])

        if abs(dw) > 0.3:
            status = "warn"
            advice = (f"幅が {abs(dw):.2f}mm {'広い' if dw > 0 else '狭い'}です。"
                      f"{'サイドレールからはみ出します。' if dw > 0 else '脇から息が漏れます。'}"
                      f"先端幅を {m['reed_width']:.1f}mm に合わせてください。")
        elif zv < m["window_length"] * 0.75:
            status = "warn"
            advice = ("ヴァンプがウィンドウ長に対して短く、削り面が窓に届いていません。"
                      "振動部が硬くなり鳴りにくくなります。")
        elif p["reed_length"] < seat1 - SEAT_REACH_TOL:
            status = "warn"
            advice = (f"踵がリガチャー座の後端（{seat1:.1f}mm）まで届いていません。"
                      f"リガチャーがリードの無い位置を締めることになり、固定できません。"
                      f"全長を伸ばしてください。")
        return {"title": "マウスピース適合", "big": None, "status": status,
                "rows": rows, "advice": advice}

    def _print_card(self, params: dict) -> dict:
        p = params
        need = p["min_layer"] * 3.0
        vol_cc = rp.blade_volume_mm3(p) / 1000.0
        rows = [
            ["先端厚（中央）", f"{p['tip_thickness']:.2f} mm"],
            ["先端厚の下限（積層×3）", f"{need:.2f} mm"],
            ["側端厚", f"{rp.edge_thickness(p, 0.0):.2f} mm"],
            ["材料体積", f"{vol_cc:.2f} cc"],
        ]
        if p["tip_thickness"] < need:
            return {"title": "印刷可否", "big": "造形不可", "status": "bad", "rows": rows,
                    "advice": f"先端厚が積層ピッチの3倍（{need:.2f}mm）を下回ります。"
                              f"積層を細かくするか先端厚を上げてください。"}
        if p["tip_thickness"] < 0.35:
            return {"title": "印刷可否", "big": "要注意", "status": "warn", "rows": rows,
                    "advice": "先端 0.35mm 未満は造形できても実用強度が出にくい領域です。"
                              "実績報告のある 0.35〜0.50mm を推奨します。"}
        return {"title": "印刷可否", "big": "造形可", "status": "ok", "rows": rows,
                "advice": "実績のある先端厚レンジです。積層方向はリード長手方向に"
                          "平行（面内）にしてください。"}

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

    def regions(self, params: dict) -> dict:
        return rp.param_regions(params)

    def bom(self, params: dict) -> list[dict]:
        size_label = {"soprano": "ソプラノ", "alto": "アルト", "tenor": "テナー"}[self.size]
        std_len = self.size_info.get("reed_std_length_mm")
        note = f"口に触れる部品。食品接触適合材料を使用のこと（規格長 {std_len}mm）"
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

    def spec_extras(self, params: dict) -> dict:
        p = params
        dims = [
            ("全長", f"{p['reed_length']:.1f} mm"),
            ("先端幅 × 踵幅", f"{p['tip_width']:.1f} × {p['heel_width']:.1f} mm"),
            ("先端厚（中央/側端）",
             f"{p['tip_thickness']:.2f} / {rp.edge_thickness(p, 0.0):.2f} mm"),
            ("踵厚", f"{p['heel_thickness']:.2f} mm"),
            ("ヴァンプ長", f"{rp.vamp_start_z(p):.1f} mm"),
            ("材料体積", f"{rp.blade_volume_mm3(p) / 1000.0:.2f} cc"),
        ]
        m = self.ref_params()
        props = reed_model.reed_properties(p, m)
        dims.append(("硬さ相当（推定）", props["strength_label"]))
        dims.append(("リード共振 f_reed（推定）", f"{props['f_reed_hz']:.0f} Hz"))
        if m:
            dims.append(("参照マウスピース テーブル幅", f"{m['reed_width']:.1f} mm"))
        return {"dimensions": dims,
                "sections": [{"title": "厚みプロファイル",
                              "svg": self._section_svg(p)}]}
