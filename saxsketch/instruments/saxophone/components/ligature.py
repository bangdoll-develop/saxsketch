"""サクソフォン リガチャー コンポーネント。

参照マウスピース（`Component.REQUIRES_REF`）の外形に内周が自動追従する。
ジオメトリは「外周ロフト − 内周ロフト → スリット切除 → ネジ座加算 → ネジ穴減算」
の順で、実績のあるロフト＋差集合のみで構成する（フィレットは破綻しやすいので
使わない）。**リードへの接触は内周断面の凸**として持つので、要素を足しても
ブーリアンは増えない（`ligature_profiles.contact_bottom_pts`）。唯一の例外が
逆締めの橋で、スリットが接触面を割るため片持ちの構造部材として別に足す。
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
    "tpu": "TPU95A(FDM・弾性)",
}
#: 材料ごとの推奨最小バンド厚 [mm]（締結荷重に耐える目安）。
#: **TPU の 1.2 は出典未記録の仮定** —— 弾性バンドは締結荷重ではなく伸びで掴むので
#: 他の材料と同じ根拠では決められない。決着させるのは実際に印刷して伸ばすこと。
MIN_BAND_THICKNESS = {"petg": 2.0, "pla": 2.4, "nylon_sls": 1.8, "resin": 2.6,
                      "tpu": 1.2}
#: 弾性バンド（ネジなし）に使える材料。他はリングが伸びないので掴めない。
STRETCHY_MATERIALS = {"tpu"}

CLOSURE_LABELS = {
    "screw_beak": "ネジ（ビーク側）",
    "screw_reed": "ネジ（リード側・逆締め）",
    "elastic": "弾性バンド（ネジなし）",
}
CONTACT_LABELS = {
    "none": "なし（バンド直接）",
    "face": "面（背面に密着）",
    "line": "線（軸方向のレール）",
    "point": "点（前後2列）",
}

#: スリットの切り込みを橋の底面より上へ抜く量 [mm]。橋を残したまま帯を切り割る。
#: 橋の下（バンド側）は全部切りたいが、面がぴったり重なるブーリアンは避けたい。
_SLIT_OVERCUT = 0.5


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
        # 下限が負なのは弾性バンド（ネジなし）のため。締め代は「負の隙間」で表す。
        # 既定 0.25 は可動域の内側なので、剛体バンドの黙ったクランプは起きない。
        f("clearance", "はめあい隙間", "バンド", "mm", -0.60, 0.60, 0.05,
          "マウスピース外形との隙間。3Dプリントの寸法公差を見込む。"
          "弾性バンドでは負にして締め代にする", advanced=True),
        f("reed_clearance", "リード逃げ", "バンド", "mm", 0.0, 0.5, 0.05,
          "リード背面に対する追加の逃げ。小さいほど締め代が残る", advanced=True),
        # --- 締結 ---
        ParamSpec(key="closure", label="締結方式", category="締結",
                  type="choice", default=t["closure"],
                  choices=[Choice(k, v) for k, v in CLOSURE_LABELS.items()],
                  effect="逆締め=ネジがリード側。スリットを橋渡しするプレートが"
                         "リードを押さえる。弾性=ネジなしで伸ばして嵌める"),
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
        # --- 接触 ---
        ParamSpec(key="contact_type", label="リードへの当たり方", category="接触",
                  type="choice", default=t["contact_type"],
                  choices=[Choice(k, v) for k, v in CONTACT_LABELS.items()],
                  effect="線/点=支点が少なく中央が自由に振動して明るい。"
                         "面=背面に密着して芯が出る"),
        ParamSpec(key="contact_count", label="接触の数（x方向）", category="接触",
                  type="int", default=t["contact_count"], min=1, max=6, step=1,
                  effect="多いほど拘束が均等になる。点接触では前後2列なので総数は2倍"),
        # --- 製造 ---
        ParamSpec(key="material", label="材料プリセット", category="製造",
                  type="choice", default=t["material"],
                  choices=[Choice(k, v) for k, v in MATERIAL_LABELS.items()],
                  effect="締結荷重に対する強度。仕様書の印刷推奨条件にも反映"),
        f("min_wall", "最小肉厚", "製造", "mm", 1.0, 3.0, 0.1,
          "印刷可否判定の下限。逆締めでは橋の厚みそのもの", advanced=True),
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

    def reed_params(self) -> dict:
        """挟むリードの形（踵の幅・中央厚・側端厚）。

        リード プロジェクトと同じ .wproj には入らないため、寸法の根拠は
        テンプレート（同じサイズのリード規格）とする。背面がカマボコなので
        厚み 1 つでは足りない —— 接触の頂点は `rp.cane_top` から起こす。
        """
        r = self.template.get("reed", {})
        return {
            "heel_thickness": float(r.get("heel_thickness", 2.8)),
            "heel_width": float(r.get("heel_width", 14.0)),
            "heel_edge_thickness": float(r.get("heel_edge_thickness", 0.9)),
        }

    def reed_thickness(self) -> float:
        """挟むリードの踵の**中央**厚（表示用）。"""
        return self.reed_params()["heel_thickness"]

    def ref_dimensions(self) -> list[tuple[str, str]]:
        m = self.ref_params()
        if not m:
            return []
        import math

        from . import profiles
        from . import reed_profiles as rp
        r = self.reed_params()
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
            ("想定リード踵厚（中央 / 側端）",
             f"{r['heel_thickness']:.2f} / {r['heel_edge_thickness']:.2f} mm"),
            ("リード背面の円弧（導出）", f"R{rp.cane_radius(r):.1f} mm"),
        ]

    # ------------------------------------------------------------ 成立しない組

    def params_error(self, params: dict) -> str | None:
        p = params
        closure = str(p.get("closure", "screw_beak"))
        if closure == "screw_reed":
            if lp.contact_kind(p) == "none":
                return ("逆締めはスリットがリード接触面を必ず割るので、橋渡しする"
                        "接触形状が要ります。当たり方を「面 / 線 / 点」から"
                        "選んでください。")
            bad = lp.bridge_floor_error(p)
            if bad:
                return bad
        # 接触の逃げ（頂点から床まで）がはめあい隙間より深いと、そのぶん床が
        # 下がってタブの肉が薄くなる。弾性バンド（負の隙間）で効いてくる。
        wall = (p["band_thickness"] + p["clearance"]
                - max(p["clearance"], lp.contact_relief(p)))
        if wall < p["min_wall"] - 1e-9:
            return (f"リード側の肉が {wall:.2f}mm しか残りません（最小肉厚 "
                    f"{p['min_wall']:.1f}mm）。接触の逃げがはめあい隙間より深いので、"
                    f"バンド厚を上げるか隙間を広げてください。")
        return None

    # ------------------------------------------------------------ 旧プロジェクトの変換

    def migrate_params(self, values: dict) -> tuple[dict, list[str]]:
        """旧 `plate_type`（圧力プレート）を締結方式＋当たり方へ移す。

        `ParamSet` は未知キーを黙って捨てるので、何もしないと「全面プレート」に
        してあったプロジェクトが黙って線接触に変わる。**黙って値が変わる経路を
        作らない**ので、変換したことを 1 行返す。
        """
        if "plate_type" not in values:
            return values, []
        v = dict(values)
        old = str(v.pop("plate_type"))
        table = {"none": ("none", 1), "plain": ("face", 1), "rail": ("line", 2)}
        kind, count = table.get(old, ("line", 2))
        v.setdefault("closure", "screw_beak")
        v.setdefault("contact_type", kind)
        v.setdefault("contact_count", count)
        was = {"none": "なし", "plain": "全面", "rail": "2点レール"}.get(old, old)
        return v, [f"旧の圧力プレート設定（{was}）を接触形状"
                   f"「{CONTACT_LABELS[kind]}」×{count} へ移しました。"
                   f"接触の頂点はリード背面（カマボコ）に沿うので、"
                   f"体積と部品表が変わります。"]

    # ------------------------------------------------------------ 形状生成

    def build(self, params: dict):
        from build123d import Pos, Rot, Solid

        m = self.ref_params()
        if not m:
            raise RuntimeError("参照マウスピースが未設定のためリガチャーを生成できません")
        p = params
        r = self.reed_params()
        z0, z1 = lp.seat_range(m, p)
        closure = str(p.get("closure", "screw_beak"))

        part = loft_sections(lp.outer_sections(m, p, r)) \
            - loft_sections(lp.inner_sections(m, p, r))
        if closure == "elastic":
            return part                      # スリットもネジ座も無い一連リング

        slit = p["slit_width"]
        ear = lp.ear_thickness(p)
        band = p["band_thickness"]
        base, tip = lp.ear_span(m, p, r)     # 耳の付け根 → 頂点（逆締めは下向き）

        if closure == "screw_reed":
            # スリット: リード側から、橋の底面のすぐ上まで切り割る（橋は残す）。
            # テーブルが傾いているので箱ではなく前後端の矩形をロフトした角柱。
            t = lp.bridge_thickness(p)
            part = part - loft_sections([
                {"z": z, "pts": _rect_pts(
                    -slit / 2.0, slit, tip - 1.0,
                    lp.tab_floor_y(m, p, r, z) - t + _SLIT_OVERCUT - (tip - 1.0))}
                for z in (z0, z1)])
            # ネジ座（耳）: スリットの両脇へ、バンドの外面から下向きに立てる
            for sx in (-1.0, 1.0):
                x0 = slit / 2.0 if sx > 0 else -slit / 2.0 - ear
                part = part + loft_sections([
                    {"z": z, "pts": _rect_pts(
                        x0, ear, tip,
                        lp.tab_outer_y(m, p, r, z) + band * 0.5 - tip)}
                    for z in (z0, z1)])
        else:
            r_in = lp.inner_radius(m, p)
            # スリット（締め代）: ビーク側を Z 方向に切り割る
            part = part - (Pos(-slit / 2.0, r_in - 1.0, z0 - 1.0)
                           * Solid.make_box(slit, tip - r_in + 2.0, z1 - z0 + 2.0))
            # ネジ座（耳）: スリットの両脇に立てる
            for sx in (-1.0, 1.0):
                x0 = slit / 2.0 if sx > 0 else -slit / 2.0 - ear
                part = part + (Pos(x0, base - band * 0.5, z0)
                               * Solid.make_box(ear, tip - base + band * 0.5,
                                                z1 - z0))

        # ネジ穴（バカ穴）: X 軸方向に貫通
        _, hole_d, _ = lp.screw_spec(p)
        x_span = slit + 2.0 * ear + 4.0
        for zs in lp.screw_zs(m, p):
            hole = Rot(0, 90, 0) * Solid.make_cylinder(hole_d / 2.0, x_span)
            part = part - Pos(-x_span / 2.0, lp.screw_axis_y(m, p, r), zs) * hole

        if closure == "screw_reed":
            # 橋（圧力プレート）: -x 側の床へ食い込ませて融合し、+x 側とは
            # `_BRIDGE_GAP` 空ける片持ち。スリットを切った**後**に足す。
            part = part + loft_sections(lp.bridge_sections(m, p, r))
        return part

    # ------------------------------------------------------------ シミュレーション

    def simulate(self, params: dict) -> dict:
        return {"kind": "ligature", "cards": [
            self._fit_card(params), self._screw_card(params),
            self._strength_card(params)]}

    def _contact_rows(self, m: dict, p: dict) -> list[list[str]]:
        """接触の実測値（適合カードの後半）。

        「締め代」は接触の頂点とリード背面の距離。**平らな面だとここが x で
        大きくばらつく**（旧「2点レール」の位置で 0.83〜1.04mm、全面プレートの端で
        1.55〜1.88mm ＝ 剛体バンドが埋められる量ではない）。頂点をカマボコから
        起こしたので、いまは全接触で `reed_clearance` に揃う。
        """
        from . import profiles
        from . import reed_profiles as rp
        r = self.reed_params()
        z0, z1 = lp.seat_range(m, p)
        rows_z = lp.contact_rows(m, p)
        zc = rows_z[0] if rows_z else (z0 + z1) / 2.0
        hw = lp.flat_half_width(m, p)
        kind = lp.contact_kind(p)
        n = lp.contact_n(p)
        out = [["リードへの当たり方",
                CONTACT_LABELS.get(kind, kind)
                + ("" if n == 0 else
                   f" × {n}" + (f"（総数 {2 * n}）" if kind == "point" else ""))]]
        if kind == "none":
            out.append(["締め代", "接触なし（バンドの床が直接当たる）"])
            return out
        span = lp.contact_span(hw)
        xs = [-span, 0.0, span] if kind == "face" else lp.contact_xs(hw, n)
        back = [profiles.table_plane_y(m, zc) - rp.cane_top(r, abs(x)) for x in xs]
        gaps = [b - lp.contact_top_y(m, p, r, x, zc) for b, x in zip(back, xs)]
        flat = [b - lp.reed_face_y(m, p, r, zc) for b in back]   # 平らな面だったら
        out += [
            ["接触の x 位置", " / ".join(f"{x:+.2f}" for x in xs) + " mm"],
            ["締め代（全接触）", f"{min(gaps):.2f}〜{max(gaps):.2f} mm"],
            ["（平らな面なら）", f"{min(flat):.2f}〜{max(flat):.2f} mm"],
            ["リード踵幅 / タブ幅",
             f"{r['heel_width']:.1f} / "
             f"{lp.requested_tab_half_width(m, p) * 2.0:.1f} mm"],
        ]
        return out

    def _fit_card(self, params: dict) -> dict:
        m = self.ref_params()
        p = params
        if not m:
            return {"title": "マウスピース適合", "big": None, "status": "warn",
                    "rows": [], "advice": "参照マウスピースが未設定です。"}
        from . import profiles
        z0, z1 = lp.seat_range(m, p)
        seat0, seat1 = profiles.ligature_seat_range(m)
        elastic = str(p.get("closure")) == "elastic"
        rows = [
            ["内周径", f"φ{lp.inner_radius(m, p) * 2.0:.2f} mm"],
            ["マウスピース ボディ径", f"φ{m['body_dia']:.1f} mm"],
            ["装着位置 z", f"{z0:.1f}〜{z1:.1f} mm"],
            ["リガチャー座", f"{seat0:.1f}〜{seat1:.1f} mm"],
            ["リード収納幅（要求/実際)",
             f"{lp.requested_tab_half_width(m, p) * 2.0:.1f} / "
             f"{lp.flat_half_width(m, p) * 2.0:.1f} mm"],
        ] + self._contact_rows(m, p)

        def card(status, advice):
            return {"title": "マウスピース適合", "big": None, "status": status,
                    "rows": rows, "advice": advice}

        if lp.flat_half_width(m, p) < lp.requested_tab_half_width(m, p) - 0.01:
            return card("warn",
                        f"マウスピースの外形径に対してリードが幅広く、収納幅が "
                        f"{lp.flat_half_width(m, p) * 2.0:.1f}mm に切り詰め"
                        f"られています。リードが入りません。タブは外形の外へ"
                        f"張り出せますが、外形径そのものは超えられません。"
                        f"ボディ径の大きいマウスピースを参照するか、はめあい"
                        f"隙間を減らしてください。")
        if z1 - z0 < p["band_width"] - 0.05:
            return card("warn",
                        f"バンド幅がリガチャー座に収まりません（座は "
                        f"{seat1 - seat0:.1f}mm）。幅を狭めるか座位置"
                        f"オフセットを小さくしてください。")
        if elastic and p["clearance"] > 0.0:
            return card("warn",
                        "弾性バンドなのにはめあい隙間が正です。伸ばして嵌める"
                        "方式では隙間が締め代になるので、負の値（-0.2〜-0.4mm）に"
                        "してください。")
        if not elastic and p["clearance"] < 0.0:
            return card("warn",
                        "剛体バンド（ネジ締め）で隙間が負です。リングは伸びないので"
                        "マウスピースに入りません。隙間を 0 以上にするか、締結方式を"
                        "弾性バンドにしてください。")
        if not elastic and p["clearance"] < 0.15:
            return card("warn",
                        "はめあい隙間が小さく、印刷公差では入らない可能性が"
                        "あります。0.20〜0.30mm を推奨します。")
        return card("ok",
                    "マウスピース外形に追従した内周です。参照マウスピースの"
                    "ボディ径を変えると内周も自動で追従します。接触の頂点は"
                    "リード背面（カマボコ）に沿うので、締め代は全接触で揃います。")

    def _screw_card(self, params: dict) -> dict:
        p = params
        closure = str(p.get("closure", "screw_beak"))
        if closure == "elastic":
            rows = [
                ["締結方式", CLOSURE_LABELS[closure]],
                ["締め代（負のはめあい隙間）", f"{-p['clearance']:.2f} mm"],
                ["材料", MATERIAL_LABELS.get(p["material"], p["material"])],
                ["バンド厚", f"{p['band_thickness']:.1f} mm"],
            ]
            return {"title": "締結", "big": "ネジなし", "status": "ok", "rows": rows,
                    "advice": "スリットもネジも無い一連のリングです。伸ばして嵌める"
                              "ので、締め代（負の隙間）と材料の伸びが締結の実体に"
                              "なります。市販ねじは部品表に載りません。"}

        nominal, hole_d, head_d = lp.screw_spec(p)
        need = lp.required_screw_length(p)
        stock = lp.stock_screw_length(p)
        need_boss = lp.min_boss_height(p)
        rows = [
            ["締結方式", CLOSURE_LABELS[closure]],
            ["ネジ", f"M{nominal:g} × {int(p['screw_count'])} 本"],
            ["必要な首下長さ", f"{need:.1f} mm 以上"],
            ["推奨する市販長さ", f"{stock} mm"],
            ["バカ穴径", f"φ{hole_d:.1f} mm"],
            ["耳の厚み", f"{lp.ear_thickness(p):.1f} mm"],
            ["ネジ座の高さ / 下限",
             f"{p['boss_height']:.1f} / {need_boss:.1f} mm"],
        ]
        if closure == "screw_reed":
            rows += [
                ["橋（圧力プレート）の厚み", f"{lp.bridge_thickness(p):.1f} mm"],
                ["橋の下に残る床", f"{lp.bridge_residual_floor(p):.2f} mm"],
            ]
        big = f"M{nominal:g}×{stock}"
        if p["boss_height"] < need_boss:
            return {"title": "締結", "big": big, "status": "bad", "rows": rows,
                    "advice": f"ネジ座が低くバカ穴（φ{hole_d:.1f}）が耳から出ます。"
                              f"閉じた穴にならずネジが抜けます。ネジ座の高さを "
                              f"{need_boss:.1f}mm 以上にするか、ネジを細くしてください。"}
        if stock < need:
            return {"title": "締結", "big": big, "status": "bad", "rows": rows,
                    "advice": "市販レンジで必要長さを満たせません。スリット幅か"
                              "バンド厚を減らしてください。"}
        advice = ("ネジは市販品です。ナットは使わず、片側の耳をタップ"
                  "（下穴を開けてねじ立て）しても組めます。")
        if closure == "screw_reed":
            advice += ("逆締めではスリットがリード接触面を割るので、片側から"
                       "張り出した橋が反対側に重なって押さえます（橋は構造部材"
                       "なので、当たり方を「なし」にはできません）。")
        return {"title": "締結", "big": big, "status": "ok", "rows": rows,
                "advice": advice}

    def _strength_card(self, params: dict) -> dict:
        p = params
        mat = p.get("material", "petg")
        elastic = str(p.get("closure")) == "elastic"
        need = max(MIN_BAND_THICKNESS.get(mat, 2.0), p["min_wall"])
        _, _, head_d = lp.screw_spec(p)
        rows = [
            ["バンド厚", f"{p['band_thickness']:.1f} mm"],
            ["材料別の推奨下限", f"{need:.1f} mm"],
            ["耳の厚み / ネジ頭径", f"{lp.ear_thickness(p):.1f} / {head_d:.1f} mm"],
        ]
        if elastic:
            rows.append(["伸びる材料か",
                         "はい" if mat in STRETCHY_MATERIALS else "いいえ"])
            if mat not in STRETCHY_MATERIALS:
                return {"title": "印刷強度", "big": "不可", "status": "bad",
                        "rows": rows,
                        "advice": f"{MATERIAL_LABELS.get(mat, mat)} のリングは"
                                  f"伸びません。ネジなしで嵌めるには "
                                  f"{MATERIAL_LABELS['tpu']} のような弾性材料が"
                                  f"要ります（薄いバンドなら成立する余地はあるので、"
                                  f"形状としては作れます）。"}
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
        m = self.ref_params()
        rows = [
            {"type": "3Dプリント", "name": f"リガチャー本体（{size_label}）", "qty": 1,
             "material": MATERIAL_LABELS.get(p["material"], p["material"]),
             "note": f"内周 φ{lp.inner_radius(m, p) * 2.0:.1f}mm" if m else "-"},
        ]
        if lp.has_screws(p):
            nominal, _, _ = lp.screw_spec(p)
            rows.append({"type": "市販品",
                         "name": f"なべ小ねじ M{nominal:g}×{lp.stock_screw_length(p)}",
                         "qty": int(p["screw_count"]), "material": "ステンレス",
                         "note": "締結用。頭部は+または六角穴"})
        kind = lp.contact_kind(p)
        if kind != "none":
            n = lp.contact_n(p)
            rows.append({"type": "備考", "name": "リード接触", "qty": 1,
                         "material": "本体と一体",
                         "note": CONTACT_LABELS[kind]
                                 + ("" if n == 0 else f" × {n}")})
        if str(p.get("closure")) == "screw_reed":
            rows.append({"type": "備考", "name": "橋（圧力プレート）", "qty": 1,
                         "material": "本体と一体",
                         "note": f"厚み {lp.bridge_thickness(p):.1f}mm・片持ち"})
        return rows

    def _section_svg(self, m: dict, params: dict) -> str:
        """帯の断面図（XY 断面）。"""
        from saxsketch.export.svg import polyline_svg
        sec = lp.section_polylines(m, params, self.reed_params())
        xs = [x for x, _ in sec["outer"]]
        ty, ry = sec["table_y"], sec["reed_face_y"]
        layers = [
            {"pts": sec["outer"], "stroke": "#222", "width": 1.5},
            {"pts": sec["inner"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": [(min(xs), ty), (max(xs), ty)], "stroke": "#cc3300",
             "width": 0.8, "dash": "2 2"},
            {"pts": [(min(xs), ry), (max(xs), ry)], "stroke": "#3aa06a",
             "width": 0.8, "dash": "2 2"},
        ]
        caption = ("帯の断面（実線=外周 / 青破線=内周（接触の凸を含む） / "
                   "赤破線=テーブル面 / 緑破線=リード裏面の中央） 単位:mm")
        if sec["bridge"]:
            layers.append({"pts": sec["bridge"], "stroke": "#9944cc", "width": 1.2})
            caption = ("帯の断面（実線=外周 / 青破線=内周 / 紫=橋（圧力プレート） / "
                       "赤破線=テーブル面 / 緑破線=リード裏面の中央） 単位:mm")
        return polyline_svg(layers, caption)

    def spec_extras(self, params: dict) -> dict:
        m = self.ref_params()
        p = params
        kind = lp.contact_kind(p)
        n = lp.contact_n(p)
        dims = [
            ("バンド幅 × 厚み",
             f"{p['band_width']:.1f} × {p['band_thickness']:.1f} mm"),
            ("締結方式", CLOSURE_LABELS.get(str(p.get("closure")), "-")),
            ("リードへの当たり方",
             CONTACT_LABELS.get(kind, "-") + ("" if n == 0 else f" × {n}")),
        ]
        if lp.has_screws(p):
            dims += [
                ("スリット幅", f"{p['slit_width']:.1f} mm"),
                ("ネジ", f"M{lp.screw_spec(p)[0]:g} × {int(p['screw_count'])} 本 "
                         f"（首下 {lp.stock_screw_length(p)}mm）"),
            ]
        if str(p.get("closure")) == "screw_reed":
            dims.append(("橋の厚み / 残る床",
                         f"{lp.bridge_thickness(p):.1f} / "
                         f"{lp.bridge_residual_floor(p):.2f} mm"))
        extras: dict = {"dimensions": dims}
        if m:
            z0, z1 = lp.seat_range(m, p)
            dims.insert(0, ("内周径", f"φ{lp.inner_radius(m, p) * 2.0:.2f} mm"))
            dims.append(("装着位置 z", f"{z0:.1f}〜{z1:.1f} mm"))
            extras["sections"] = [{"title": "帯の断面",
                                   "svg": self._section_svg(m, p)}]
        return extras
