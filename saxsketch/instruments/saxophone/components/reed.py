"""サクソフォン リード コンポーネント。

参照マウスピース（`Component.REQUIRES_REF`）のテーブル幅・ウィンドウ長に従属する。
ジオメトリは `reed_profiles.sections()` を `loft_sections` でロフトするだけの
単一ソリッド（ブーリアン無し＝破綻しにくい）。
"""
from __future__ import annotations

from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec
from saxsketch.geometry.builders import loft_sections, yz_profile_cut_solid

from . import profiles
from . import reed_profiles as rp

MATERIAL_LABELS = {
    "pla": "PLA(FDM)",
    "petg": "PETG(FDM)",
    "resin_flex": "フレキシブルレジン(光造形)",
    "pp": "ポリプロピレン",
    "cane": "ケーン（参考値・切削前提）",
}


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
                  choices=[Choice(k, v) for k, v in MATERIAL_LABELS.items()],
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
        return {"kind": "reed", "cards": self._cards(params)}

    def _cards(self, params: dict) -> list[dict]:
        return [self._fit_card(params), self._print_card(params)]

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
        elif p["reed_length"] < seat0:
            status = "warn"
            advice = ("踵がリガチャー座に届いていません。リガチャーで固定できず、"
                      "リードがずれます。全長を伸ばしてください。")
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

    # ------------------------------------------------------------ 領域・BOM・仕様書

    def regions(self, params: dict) -> dict:
        return rp.param_regions(params)

    def bom(self, params: dict) -> list[dict]:
        size_label = {"soprano": "ソプラノ", "alto": "アルト", "tenor": "テナー"}[self.size]
        std_len = self.size_info.get("reed_std_length_mm")
        note = f"口に触れる部品。食品接触適合材料を使用のこと（規格長 {std_len}mm）"
        return [
            {"type": "3Dプリント", "name": f"リード（{size_label}）", "qty": 1,
             "material": MATERIAL_LABELS.get(params["material"], params["material"]),
             "note": note},
            {"type": "市販品", "name": "リードケース", "qty": 1, "material": "-",
             "note": "反り防止（任意）"},
        ]

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
        if m:
            dims.append(("参照マウスピース テーブル幅", f"{m['reed_width']:.1f} mm"))
        return {"dimensions": dims, "reed_profile": rp.side_profile_polylines(p)}
