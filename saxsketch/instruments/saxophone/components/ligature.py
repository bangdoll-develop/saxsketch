"""サクソフォン リガチャー コンポーネント。

参照マウスピース（`Component.REQUIRES_REF`）の外形に内周が自動追従する。
ジオメトリは「外周ロフト − 内周ロフト → スリット切除 → ネジ座加算 → ネジ穴減算
→ 圧力プレート加算」の順で、実績のあるロフト＋差集合のみで構成する
（フィレットは破綻しやすいので使わない）。
"""
from __future__ import annotations

from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec
from saxsketch.geometry.builders import loft_sections

from . import ligature_profiles as lp

MATERIAL_LABELS = {
    "petg": "PETG(FDM)",
    "pla": "PLA(FDM)",
    "nylon_sls": "ナイロンPA12(SLS)",
    "resin": "レジン(光造形)",
}
#: 材料ごとの推奨最小バンド厚 [mm]（締結荷重に耐える目安）
MIN_BAND_THICKNESS = {"petg": 2.0, "pla": 2.4, "nylon_sls": 1.8, "resin": 2.6}


def _rect_pts(x0: float, w: float, y0: float, h: float) -> list[tuple[float, float]]:
    """XY 平面の矩形（反時計回り）。ロフト断面用。"""
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]


def _specs(t: dict) -> list[ParamSpec]:
    def f(key, label, cat, unit, lo, hi, step, effect, advanced=False):
        return ParamSpec(key=key, label=label, category=cat, type="float", unit=unit,
                         default=t[key], min=lo, max=hi, step=step, effect=effect,
                         advanced=advanced)

    return [
        # --- バンド ---
        f("band_width", "バンド幅", "バンド", "mm", 8.0, 28.0, 0.5,
          "広いほどリードの拘束が強く芯のある音、狭いほど自由に鳴る"),
        f("band_thickness", "バンド厚", "バンド", "mm", 1.2, 4.0, 0.1,
          "剛性。薄いほどしなって響くが、締結荷重で割れやすくなる"),
        f("seat_offset", "座位置オフセット", "バンド", "mm", 0.0, 15.0, 0.5,
          "リガチャー座の前端からの距離。前寄りほど明るく反応が速い"),
        f("clearance", "はめあい隙間", "バンド", "mm", 0.05, 0.60, 0.05,
          "マウスピース外形との隙間。3Dプリントの寸法公差を見込む", advanced=True),
        f("reed_clearance", "リード逃げ", "バンド", "mm", 0.0, 0.5, 0.05,
          "リード厚に対する追加の逃げ。小さいほど締め代が残る", advanced=True),
        # --- 締結 ---
        ParamSpec(key="screw_count", label="ネジ本数", category="締結",
                  type="int", default=t["screw_count"], min=1, max=2, step=1,
                  effect="2本=均等に締まる、1本=部品が単純で軽い"),
        ParamSpec(key="screw_size", label="ネジ呼び径", category="締結",
                  type="choice", default=t["screw_size"],
                  choices=[Choice("m2.5", "M2.5"), Choice("m3", "M3")],
                  effect="市販の小ねじ。部品表に必要長さを自動計算して載せる"),
        f("boss_height", "ネジ座の高さ", "締結", "mm", 5.0, 12.0, 0.5,
          "耳の高さ。高いほど締めやすいが出っ張る。低すぎるとネジ穴が耳から出る"),
        f("slit_width", "スリット幅", "締結", "mm", 1.5, 6.0, 0.5,
          "締め代。広いほど大きく締められるが、締めきると変形が大きい"),
        # --- プレート ---
        ParamSpec(key="plate_type", label="圧力プレート", category="プレート",
                  type="choice", default=t["plate_type"],
                  choices=[Choice("none", "なし（バンド直接）"),
                           Choice("plain", "全面プレート"),
                           Choice("rail", "2点レール")],
                  effect="リードへの当たり方。レール=2点支持で中央が自由に振動し明るい"),
        # --- 製造 ---
        ParamSpec(key="material", label="材料プリセット", category="製造",
                  type="choice", default=t["material"],
                  choices=[Choice(k, v) for k, v in MATERIAL_LABELS.items()],
                  effect="締結荷重に対する強度。仕様書の印刷推奨条件にも反映"),
        f("min_wall", "最小肉厚", "製造", "mm", 1.0, 3.0, 0.1,
          "印刷可否判定の下限", advanced=True),
    ]


class LigatureComponent(Component):
    id = "ligature"
    label = "リガチャー"
    REQUIRES_REF = "mouthpiece"

    def __init__(self, descriptor: dict, template: dict):
        super().__init__(descriptor, template)
        self.size = template["size"]
        self.size_info = descriptor["sizes"][self.size]

    def param_specs(self) -> list[ParamSpec]:
        return _specs(self.template["ligature"])

    # ------------------------------------------------------------ 参照

    def reed_thickness(self) -> float:
        """挟むリードの踵厚。自テンプレートのリード既定値を採る。

        リード プロジェクトと同じ .wproj には入らないため、寸法の根拠は
        テンプレート（同じサイズのリード規格）とする。
        """
        return float(self.template.get("reed", {}).get("heel_thickness", 2.8))

    def ref_dimensions(self) -> list[tuple[str, str]]:
        m = self.ref_params()
        if not m:
            return []
        import math

        from . import profiles
        seat0, seat1 = profiles.ligature_seat_range(m)
        return [
            ("ボディ径（リガチャー座）", f"φ{m['body_dia']:.1f} mm"),
            ("座での外形径", f"φ{profiles.outer_radius(m, (seat0 + seat1) / 2.0) * 2.0:.2f} mm"),
            ("リガチャー座の範囲", f"{seat0:.1f}〜{seat1:.1f} mm"),
            # テーブルは傾斜平面なので 1 点では表せない。座の前端〜後端で示す。
            ("テーブル面 Y（座の前端→後端）",
             f"{profiles.table_plane_y(m, seat0):.1f} → "
             f"{profiles.table_plane_y(m, seat1):.1f} mm"),
            ("テーブル傾斜", f"{math.degrees(profiles.table_angle(m)):.2f}°"),
            ("想定リード踵厚", f"{self.reed_thickness():.2f} mm"),
        ]

    # ------------------------------------------------------------ 形状生成

    def build(self, params: dict):
        from build123d import Pos, Rot, Solid

        m = self.ref_params()
        if not m:
            raise RuntimeError("参照マウスピースが未設定のためリガチャーを生成できません")
        p = params
        rt = self.reed_thickness()
        z0, z1 = lp.seat_range(m, p)
        r_in = lp.inner_radius(m, p)
        band = p["band_thickness"]
        ear = lp.ear_thickness(p)
        slit = p["slit_width"]
        y_top = r_in + band                      # 外周の頂点（ビーク側）
        y_ear = y_top + p["boss_height"]

        part = loft_sections(lp.outer_sections(m, p, rt)) \
            - loft_sections(lp.inner_sections(m, p, rt))

        # スリット（締め代）: ビーク側を Z 方向に切り割る
        part = part - (Pos(-slit / 2.0, r_in - 1.0, z0 - 1.0)
                       * Solid.make_box(slit, y_ear - r_in + 2.0, z1 - z0 + 2.0))

        # ネジ座（耳）: スリットの両脇に立てる
        for sx in (-1.0, 1.0):
            x0 = slit / 2.0 if sx > 0 else -slit / 2.0 - ear
            part = part + (Pos(x0, y_top - band * 0.5, z0)
                           * Solid.make_box(ear, y_ear - y_top + band * 0.5,
                                            z1 - z0))

        # ネジ穴（バカ穴）: X 軸方向に貫通
        _, hole_d, _ = lp.screw_spec(p)
        x_span = slit + 2.0 * ear + 4.0
        for zs in lp.screw_zs(m, p):
            hole = Rot(0, 90, 0) * Solid.make_cylinder(hole_d / 2.0, x_span)
            part = part - Pos(-x_span / 2.0, lp.screw_axis_y(m, p), zs) * hole

        # 圧力プレート: 内周の平坦部とリード面の隙間を埋める
        part = self._add_plate(part, m, p, rt, z0, z1)
        return part

    def _add_plate(self, part, m: dict, p: dict, rt: float,
                   z0: float, z1: float):
        kind = p.get("plate_type", "rail")
        if kind == "none":
            return part
        gap = p["clearance"]                     # 平坦部とリード面の隙間
        if gap <= 1e-6:
            return part
        hw = lp.flat_half_width(m, p, rt)
        if kind == "plain":
            spans = [(-hw * 0.92, hw * 1.84)]
        else:                                    # rail: 両脇2本のリブ
            rib = min(2.0, hw * 0.4)
            spans = [(-hw * 0.80, rib), (hw * 0.80 - rib, rib)]
        # プレートはタブ底面とリード面の間を埋める。どちらもテーブルと同じ 4.18° で
        # 傾いているので、角柱ではなく前後端の矩形をロフトした**平行四辺形の柱**になる。
        # 角柱のままだと後端で 1.3mm ぶんリード面へ食い込む。
        for x0, w in spans:
            part = part + loft_sections([
                {"z": z, "pts": _rect_pts(
                    x0, w, lp.reed_face_y(m, p, rt, z) - gap, gap)}
                for z in (z0, z1)])
        return part

    # ------------------------------------------------------------ シミュレーション

    def simulate(self, params: dict) -> dict:
        return {"kind": "ligature", "cards": [
            self._fit_card(params), self._screw_card(params),
            self._strength_card(params)]}

    def _fit_card(self, params: dict) -> dict:
        m = self.ref_params()
        p = params
        if not m:
            return {"title": "マウスピース適合", "big": None, "status": "warn",
                    "rows": [], "advice": "参照マウスピースが未設定です。"}
        from . import profiles
        rt = self.reed_thickness()
        z0, z1 = lp.seat_range(m, p)
        seat0, seat1 = profiles.ligature_seat_range(m)
        rows = [
            ["内周径", f"φ{lp.inner_radius(m, p) * 2.0:.2f} mm"],
            ["マウスピース ボディ径", f"φ{m['body_dia']:.1f} mm"],
            ["装着位置 z", f"{z0:.1f}〜{z1:.1f} mm"],
            ["リガチャー座", f"{seat0:.1f}〜{seat1:.1f} mm"],
            ["リード収納幅（要求/実際)",
             f"{lp.requested_tab_half_width(m, p) * 2.0:.1f} / "
             f"{lp.flat_half_width(m, p, rt) * 2.0:.1f} mm"],
        ]
        if lp.flat_half_width(m, p, rt) < lp.requested_tab_half_width(m, p) - 0.01:
            return {"title": "マウスピース適合", "big": None, "status": "warn",
                    "rows": rows,
                    "advice": f"マウスピースの外形径に対してリードが幅広く、収納幅が "
                              f"{lp.flat_half_width(m, p, rt) * 2.0:.1f}mm に切り詰め"
                              f"られています。リードが入りません。タブは外形の外へ"
                              f"張り出せますが、外形径そのものは超えられません。"
                              f"ボディ径の大きいマウスピースを参照するか、はめあい"
                              f"隙間を減らしてください。"}
        if z1 - z0 < p["band_width"] - 0.05:
            return {"title": "マウスピース適合", "big": None, "status": "warn",
                    "rows": rows,
                    "advice": f"バンド幅がリガチャー座に収まりません（座は "
                              f"{seat1 - seat0:.1f}mm）。幅を狭めるか座位置"
                              f"オフセットを小さくしてください。"}
        if p["clearance"] < 0.15:
            return {"title": "マウスピース適合", "big": None, "status": "warn",
                    "rows": rows,
                    "advice": "はめあい隙間が小さく、印刷公差では入らない可能性が"
                              "あります。0.20〜0.30mm を推奨します。"}
        return {"title": "マウスピース適合", "big": None, "status": "ok", "rows": rows,
                "advice": "マウスピース外形に追従した内周です。参照マウスピースの"
                          "ボディ径を変えると内周も自動で追従します。"}

    def _screw_card(self, params: dict) -> dict:
        p = params
        nominal, hole_d, head_d = lp.screw_spec(p)
        need = lp.required_screw_length(p)
        stock = lp.stock_screw_length(p)
        need_boss = lp.min_boss_height(p)
        rows = [
            ["ネジ", f"M{nominal:g} × {int(p['screw_count'])} 本"],
            ["必要な首下長さ", f"{need:.1f} mm 以上"],
            ["推奨する市販長さ", f"{stock} mm"],
            ["バカ穴径", f"φ{hole_d:.1f} mm"],
            ["耳の厚み", f"{lp.ear_thickness(p):.1f} mm"],
            ["ネジ座の高さ / 下限",
             f"{p['boss_height']:.1f} / {need_boss:.1f} mm"],
        ]
        if p["boss_height"] < need_boss:
            return {"title": "締結", "big": f"M{nominal:g}×{stock}", "status": "bad",
                    "rows": rows,
                    "advice": f"ネジ座が低くバカ穴（φ{hole_d:.1f}）が耳から出ます。"
                              f"閉じた穴にならずネジが抜けます。ネジ座の高さを "
                              f"{need_boss:.1f}mm 以上にするか、ネジを細くしてください。"}
        if stock < need:
            return {"title": "締結", "big": f"M{nominal:g}×{stock}", "status": "bad",
                    "rows": rows,
                    "advice": "市販レンジで必要長さを満たせません。スリット幅か"
                              "バンド厚を減らしてください。"}
        return {"title": "締結", "big": f"M{nominal:g}×{stock}", "status": "ok",
                "rows": rows,
                "advice": "ネジは市販品です。ナットは使わず、片側の耳をタップ"
                          "（下穴を開けてねじ立て）しても組めます。"}

    def _strength_card(self, params: dict) -> dict:
        p = params
        mat = p.get("material", "petg")
        need = max(MIN_BAND_THICKNESS.get(mat, 2.0), p["min_wall"])
        _, _, head_d = lp.screw_spec(p)
        rows = [
            ["バンド厚", f"{p['band_thickness']:.1f} mm"],
            ["材料別の推奨下限", f"{need:.1f} mm"],
            ["耳の厚み / ネジ頭径", f"{lp.ear_thickness(p):.1f} / {head_d:.1f} mm"],
        ]
        if p["band_thickness"] < need:
            return {"title": "印刷強度", "big": "要注意", "status": "warn", "rows": rows,
                    "advice": f"{MATERIAL_LABELS.get(mat, mat)} では "
                              f"{need:.1f}mm 以上を推奨します。締結荷重で層間剥離"
                              f"（FDM）や割れ（レジン）が起きやすい厚みです。"}
        return {"title": "印刷強度", "big": "良好", "status": "ok", "rows": rows,
                "advice": "積層方向はバンドの周方向に対して垂直（軸方向を積層方向に"
                          "しない）にすると層間剥離を避けられます。"}

    # ------------------------------------------------------------ 領域・BOM・仕様書

    def regions(self, params: dict) -> dict:
        m = self.ref_params()
        return lp.param_regions(m, params) if m else {}

    def bom(self, params: dict) -> list[dict]:
        p = params
        size_label = {"soprano": "ソプラノ", "alto": "アルト", "tenor": "テナー"}[self.size]
        nominal, _, _ = lp.screw_spec(p)
        stock = lp.stock_screw_length(p)
        rows = [
            {"type": "3Dプリント", "name": f"リガチャー本体（{size_label}）", "qty": 1,
             "material": MATERIAL_LABELS.get(p["material"], p["material"]),
             "note": f"内周 φ{lp.inner_radius(self.ref_params(), p) * 2.0:.1f}mm"
                     if self.ref_params() else "-"},
            {"type": "市販品", "name": f"なべ小ねじ M{nominal:g}×{stock}",
             "qty": int(p["screw_count"]), "material": "ステンレス",
             "note": "締結用。頭部は+または六角穴"},
        ]
        if p.get("plate_type") != "none":
            rows.append({"type": "備考", "name": "圧力プレート", "qty": 1,
                         "material": "本体と一体",
                         "note": {"plain": "全面", "rail": "2点レール"}
                                 .get(p["plate_type"], "-")})
        return rows

    def _section_svg(self, m: dict, params: dict, reed_thickness: float) -> str:
        """帯の断面図（XY 断面）。"""
        from saxsketch.export.svg import polyline_svg
        sec = lp.section_polylines(m, params, reed_thickness)
        xs = [x for x, _ in sec["outer"]]
        ty, ry = sec["table_y"], sec["reed_face_y"]
        return polyline_svg([
            {"pts": sec["outer"], "stroke": "#222", "width": 1.5},
            {"pts": sec["inner"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": [(min(xs), ty), (max(xs), ty)], "stroke": "#cc3300",
             "width": 0.8, "dash": "2 2"},
            {"pts": [(min(xs), ry), (max(xs), ry)], "stroke": "#3aa06a",
             "width": 0.8, "dash": "2 2"},
        ], "帯の断面（実線=外周 / 青破線=内周 / 赤破線=テーブル面 / "
           "緑破線=リード裏面） 単位:mm")

    def spec_extras(self, params: dict) -> dict:
        m = self.ref_params()
        p = params
        rt = self.reed_thickness()
        dims = [
            ("バンド幅 × 厚み",
             f"{p['band_width']:.1f} × {p['band_thickness']:.1f} mm"),
            ("スリット幅", f"{p['slit_width']:.1f} mm"),
            ("ネジ", f"M{lp.screw_spec(p)[0]:g} × {int(p['screw_count'])} 本 "
                     f"（首下 {lp.stock_screw_length(p)}mm）"),
            ("圧力プレート", {"none": "なし", "plain": "全面", "rail": "2点レール"}
                             .get(p["plate_type"], "-")),
        ]
        extras: dict = {"dimensions": dims}
        if m:
            z0, z1 = lp.seat_range(m, p)
            dims.insert(0, ("内周径", f"φ{lp.inner_radius(m, p) * 2.0:.2f} mm"))
            dims.append(("装着位置 z", f"{z0:.1f}〜{z1:.1f} mm"))
            extras["sections"] = [{"title": "帯の断面",
                                   "svg": self._section_svg(m, p, rt)}]
        return extras
