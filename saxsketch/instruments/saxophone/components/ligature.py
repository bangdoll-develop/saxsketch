"""サクソフォン リガチャー コンポーネント。

参照マウスピース（`Component.REQUIRES_REF`）の外形に内周が自動追従する。
ジオメトリは「外周ロフト − 内周ロフト → スリット切除 → ネジ座加算 → ネジ穴減算」
の順で、実績のあるロフト＋差集合のみで構成する（フィレットは破綻しやすいので
使わない）。**リードへの接触は内周断面の凸**として持つので、要素を足しても
ブーリアンは増えない（`ligature_profiles.contact_bottom_pts`）。唯一の例外が
逆締めの橋で、スリットが接触面を割るため片持ちの構造部材として別に足す。
"""
from __future__ import annotations

from saxsketch.core.dimension import dim
from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec
from saxsketch.geometry.builders import loft_sections

from saxsketch import i18n

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
#: **テーパ圧入には掛からない** —— そちらは伸びではなく楔で掴むので剛体でよい。
STRETCHY_MATERIALS = {"tpu"}
#: 材料のヤング率 [MPa]。**文献値・代表値**（pla / petg は
#: `reed_model.MATERIALS` と同じ 3500 / 2000）。テーパ圧入の挟み力の見積りにだけ
#: 使う。TPU は楔が効かないので見積りの対象外（カードが warn を出す）。
MATERIAL_E_MPA = {"petg": 2000.0, "pla": 3500.0, "nylon_sls": 1700.0,
                  "resin": 2400.0}

CLOSURE_LABELS = {
    "screw_beak": "ネジ（ビーク側）",
    "screw_reed": "ネジ（リード側・逆締め）",
    "elastic": "弾性バンド（ネジなし）",
    "taper": "テーパ圧入（ネジなし）",
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
        # 起点は**胴の最大径**（帯の後端が当たる物理の壁）。座の前端を起点に
        # していた頃は、増やすとその壁へ押し付けるだけで可動域の 99% が死んでいた。
        f("seat_setback", "座位置（最大径から前へ）", "バンド", "mm", 0.0, 15.0, 0.5,
          "帯を最大径からどれだけ前へ引くか。前寄りほど明るく反応が速い"),
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
        f("press_depth", "押し込み量", "締結", "mm", 0.0, 10.0, 0.1,
          "テーパ圧入で、無圧入で載る位置からどれだけ押し込むか。"
          "円錐とテーブルの両方の締め代がこれで決まる"),
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
    #: 同じセットにリードが居れば、その**実寸**で当たり面を作る（居なければ
    #: 同サイズのテンプレート値）。必須にしないのは、リードを設計せずに市販品を
    #: 使う作り方が普通にあるから。
    OPTIONAL_REFS = ("reed",)
    #: 断面はマウスピースの z でそのまま張られている（`lp.outer_sections` /
    #: `inner_sections` が z ごとに `profiles.outer_radius` と `table_plane_y` を
    #: 引く。`build()` に平行移動も回転も無い）ので、参照の形をそのまま重ねられる。
    REF_SHARES_FRAME = True

    def __init__(self, descriptor: dict, template: dict):
        super().__init__(descriptor, template)
        self.size = template["size"]
        self.size_info = descriptor["sizes"][self.size]

    def param_specs(self) -> list[ParamSpec]:
        return _specs(self.template["ligature"])

    # ------------------------------------------------------------ 参照

    def reed_params(self) -> dict:
        """挟むリードの形（踵の幅・中央厚・側端厚）。

        **出所は 2 通りで、どちらかは常にはっきりしている**:
          - 同じセットにリードが居る → その実寸（`OPTIONAL_REFS` の参照）
          - 居ない → 同じサイズのテンプレート（＝リード規格の代表値）

        背面がカマボコなので厚み 1 つでは足りない —— 接触の頂点は
        `rp.cane_top` から起こす。

        セットのリードを触れば当たり面の形が変わる。**黙って変えない**ために、
        リードを足した/外した時点で `AppState` が通知を出し、セットの適合カードに
        どちらを使っているかを書く。
        """
        r = self.refs.get("reed", {}).get("params") or self.template.get("reed", {})
        return {
            "heel_thickness": float(r.get("heel_thickness", 2.8)),
            "heel_width": float(r.get("heel_width", 14.0)),
            "heel_edge_thickness": float(r.get("heel_edge_thickness", 0.9)),
        }

    def reed_is_from_set(self) -> bool:
        """当たり面の寸法がセットのリード由来か（テンプレート既定なら False）。"""
        return bool(self.refs.get("reed", {}).get("params"))

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
            (i18n.t("ボディ径（リガチャー座）"), f"φ{m['body_dia']:.1f} mm"),
            (i18n.t("座での外形径"), f"φ{profiles.outer_radius(m, (seat0 + seat1) / 2.0) * 2.0:.2f} mm"),
            (i18n.t("リガチャー座の範囲"), f"{seat0:.1f}〜{seat1:.1f} mm"),
            # テーブルは傾斜平面なので 1 点では表せない。座の前端〜後端で示す。
            (i18n.t("テーブル面 Y（座の前端→後端）"),
             f"{profiles.table_plane_y(m, seat0):.1f} → "
             f"{profiles.table_plane_y(m, seat1):.1f} mm"),
            (i18n.t("テーブル傾斜"), f"{math.degrees(profiles.table_angle(m)):.2f}°"),
            (i18n.t("想定リード踵厚（中央 / 側端）"),
             f"{r['heel_thickness']:.2f} / {r['heel_edge_thickness']:.2f} mm"),
            (i18n.t("リード背面の円弧（導出）"), f"R{rp.cane_radius(r):.1f} mm"),
        ]

    # ------------------------------------------------------------ 成立しない組

    def params_error(self, params: dict) -> str | None:
        p = params
        closure = str(p.get("closure", "screw_beak"))
        if closure == "screw_reed":
            if lp.contact_kind(p) == "none":
                return (i18n.t(
                    "逆締めはスリットがリード接触面を必ず割るので、"
                    "橋渡しする接触形状が要ります。当たり方を「面 / 線 / "
                    "点」から選んでください。"))
            bad = lp.bridge_floor_error(p)
            if bad:
                return bad
        if closure == "taper" and p["clearance"] < 0.0:
            return (i18n.t(
                "テーパ圧入は正のはめあい隙間から始めて押し込みます。隙間を "
                "0 以上にするか、負の隙間で嵌めたいなら締結方式を弾性バンドに"
                "してください。"))
        # 接触の逃げ（頂点から床まで）がはめあい隙間より深いと、そのぶん床が
        # 下がってタブの肉が薄くなる。弾性バンド（負の隙間）で効いてくる。
        wall = (p["band_thickness"] + p["clearance"]
                - max(p["clearance"], lp.contact_relief(p)))
        if wall < p["min_wall"] - 1e-9:
            return (i18n.t(
                "リード側の肉が {wall}mm しか残りません（最小肉厚 "
                "{min_wall}mm）。接触の逃げがはめあい隙間より深いので、"
                "バンド厚を上げるか隙間を広げてください。",
                wall=f"{wall:.2f}", min_wall=f"{p['min_wall']:.1f}"))
        return None

    # ------------------------------------------------------------ 旧プロジェクトの変換

    def migrate_params(self, values: dict) -> tuple[dict, list[str]]:
        """保存済みプロジェクトのパラメータを現行のキーへ移す。

        `ParamSet` は未知キーを黙って捨てるので、何もしないと古い .wproj が
        黙って既定値へ落ちる。**黙って値が変わる経路を作らない**ので、
        変換したことを 1 件 1 行返す。
        """
        v = dict(values)
        notes: list[str] = []
        notes += self._migrate_plate_type(v)
        notes += self._migrate_seat_offset(v)
        return v, notes

    @staticmethod
    def _migrate_plate_type(v: dict) -> list[str]:
        """旧 `plate_type`（圧力プレート）を締結方式＋当たり方へ移す。"""
        if "plate_type" not in v:
            return []
        old = str(v.pop("plate_type"))
        table = {"none": ("none", 1), "plain": ("face", 1), "rail": ("line", 2)}
        kind, count = table.get(old, ("line", 2))
        v.setdefault("closure", "screw_beak")
        v.setdefault("contact_type", kind)
        v.setdefault("contact_count", count)
        was = {"none": i18n.t("なし"), "plain": i18n.t("全面"),
               "rail": i18n.t("2点レール")}.get(old, old)
        return [i18n.t(
            "旧の圧力プレート設定（{was}）を接触形状「{contact_labels}」"
            "×{count} へ移しました。接触の頂点はリード背面（カマボコ）"
            "に沿うので、体積と部品表が変わります。",
            was=f"{was}",
            contact_labels=i18n.choice_label(kind, CONTACT_LABELS[kind]),
            count=f"{count}")]

    @staticmethod
    def _migrate_seat_offset(v: dict) -> list[str]:
        """旧 `seat_offset`（座の前端から後ろ向き）を `seat_setback` へ移す。

        **形は変えない。** 旧定義では帯の後端が胴の最大径の壁に必ず当たっており、
        実効値は 3 サイズとも 0.17mm 以下だった（既定 3.0/4.0/4.5 は壁の外＝
        どの値でも同じ形）。新定義の 0.0 がその「最大径に密着」なので、旧値が
        何であれ 0.0 へ移すと**保存されていた形とビット一致**する。

        **キーごと変えている**のは、値の意味だけ変えると旧値と新値を区別できず、
        利用者が意図して入れた 8.0mm を黙って 0 に戻す経路ができるから。
        """
        if "seat_offset" not in v:
            return []
        old = float(v.pop("seat_offset"))
        v.setdefault("seat_setback", 0.0)
        return [i18n.t(
            "座位置の測り方を変えました（旧「座の前端から {old}mm 後ろ」"
            "→新「最大径から前へ 0.0mm」）。旧の値は帯の後端が最大径の壁で止ま"
            "っていて実効 0.17mm 以下だったので、**形は変わりません**。"
            "いまはスライダの 0〜15mm が全部効きます。",
            old=f"{old:.1f}")]

    # ------------------------------------------------------------ 形状生成

    def build(self, params: dict):
        from build123d import Pos, Rot, Solid

        m = self.ref_params()
        if not m:
            raise RuntimeError(i18n.t("参照マウスピースが未設定のためリガチャーを生成できません"))
        p = params
        r = self.reed_params()
        z0, z1 = lp.seat_range(m, p)
        closure = str(p.get("closure", "screw_beak"))

        part = loft_sections(lp.outer_sections(m, p, r)) \
            - loft_sections(lp.inner_sections(m, p, r))
        if closure in ("elastic", "taper"):
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
        cards = [self._fit_card(params), self._screw_card(params),
                 self._strength_card(params)]
        if str(params.get("closure")) == "taper":
            cards.insert(1, self._taper_card(params))
        return {"kind": "ligature", "cards": cards}

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
        hw = lp.flat_half_width(m, p, r)
        kind = lp.contact_kind(p)
        n = lp.contact_n(p)
        out = [[i18n.t("リードへの当たり方"),
                i18n.choice_label(kind, CONTACT_LABELS.get(kind, kind))
                + ("" if n == 0 else
                   f" × {n}" + (i18n.t("（総数 {n}）", n=f"{2 * n}") if kind == "point" else ""))]]
        if kind == "none":
            out.append([i18n.t("締め代"), i18n.t("接触なし（バンドの床が直接当たる）")])
            return out
        span = lp.contact_span(hw)
        xs = [-span, 0.0, span] if kind == "face" else lp.contact_xs(hw, n)
        back = [profiles.table_plane_y(m, zc) - rp.cane_top(r, abs(x)) for x in xs]
        gaps = [b - lp.contact_top_y(m, p, r, x, zc) for b, x in zip(back, xs)]
        flat = [b - lp.reed_face_y(m, p, r, zc) for b in back]   # 平らな面だったら
        out += [
            [i18n.t("接触の x 位置"), " / ".join(f"{x:+.2f}" for x in xs) + " mm"],
            [i18n.t("締め代（全接触）"), f"{min(gaps):.2f}〜{max(gaps):.2f} mm"],
            [i18n.t("（平らな面なら）"), f"{min(flat):.2f}〜{max(flat):.2f} mm"],
            [i18n.t("リード踵幅 / タブ幅"),
             f"{r['heel_width']:.1f} / "
             f"{lp.requested_tab_half_width(p, r) * 2.0:.1f} mm"],
        ]
        return out

    def _fit_card(self, params: dict) -> dict:
        m = self.ref_params()
        p = params
        if not m:
            return {"title": i18n.t("マウスピース適合"), "big": None, "status": "warn",
                    "rows": [], "advice": i18n.t("参照マウスピースが未設定です。")}
        from . import profiles
        r = self.reed_params()
        z0, z1 = lp.seat_range(m, p)
        seat0, seat1 = profiles.ligature_seat_range(m)
        elastic = str(p.get("closure")) == "elastic"
        rows = [
            [i18n.t("内周径"), f"φ{lp.inner_radius(m, p) * 2.0:.2f} mm"],
            [i18n.t("マウスピース ボディ径"), f"φ{m['body_dia']:.1f} mm"],
            [i18n.t("装着位置 z"), f"{z0:.1f}〜{z1:.1f} mm"],
            [i18n.t("リガチャー座（公称）"), f"{seat0:.1f}〜{seat1:.1f} mm"],
            [i18n.t("座位置・最大径から前へ（要求/実効）"),
             f"{p['seat_setback']:.1f} / {lp.effective_seat_setback(m, p):.2f} mm"],
            [i18n.t("リード収納幅（要求/実際)"),
             f"{lp.requested_tab_half_width(p, r) * 2.0:.1f} / "
             f"{lp.flat_half_width(m, p, r) * 2.0:.1f} mm"],
        ] + self._contact_rows(m, p)

        def card(status, advice):
            return {"title": i18n.t("マウスピース適合"), "big": None, "status": status,
                    "rows": rows, "advice": advice}

        if lp.flat_half_width(m, p, r) < lp.requested_tab_half_width(p, r) - 0.01:
            return card("warn",
                        i18n.t(
                            "マウスピースの外形径に対してリードが幅広く、"
                            "収納幅が {lp}mm に切り詰められています。リー"
                            "ドが入りません。タブは外形の外へ張り出せますが、"
                            "外形径そのものは超えられません。"
                            "ボディ径の大きいマウスピースを参照するか、"
                            "はめあい隙間を減らしてください。",
                            lp=f"{lp.flat_half_width(m, p, r) * 2.0:.1f}"))
        win = profiles.window_end_z(m)
        if z0 < win:
            return card("warn",
                        i18n.t(
                            "帯の前端 {z0}mm が窓の後端 {win}mm "
                            "より前に出ます。リガチャーが窓（リー"
                            "ドが振動する開口）に掛かるので、",
                            z0=f"{z0:.1f}", win=f"{win:.1f}")
                        + (i18n.t(
                            "バンド幅を {z1}mm 以下にするか、",
                            z1=f"{z1 - win:.1f}")
                           if z1 - win > 0 else "")
                        + i18n.t("座位置を小さく（最大径寄りに）してください。"))
        if elastic and p["clearance"] > 0.0:
            return card("warn",
                        i18n.t(
                            "弾性バンドなのにはめあい隙間が正です。"
                            "伸ばして嵌める方式では隙間が締め代になるので、"
                            "負の値（-0.2〜-0.4mm）にしてください。"))
        if not elastic and str(p.get("closure")) != "taper"                 and p["clearance"] < 0.0:
            return card("warn",
                        i18n.t(
                            "剛体バンド（ネジ締め）で隙間が負です。"
                            "リングは伸びないのでマウスピースに入りません。"
                            "隙間を 0 以上にするか、締結方式を弾性バンドにして"
                            "ください。"))
        if str(p.get("closure")) not in ("elastic", "taper")                 and p["clearance"] < 0.15:
            return card("warn",
                        i18n.t(
                            "はめあい隙間が小さく、印刷公差では入らない可能性"
                            "があります。0.20〜0.30mm を推奨します。"))
        advice = (i18n.t(
            "マウスピース外形に追従した内周です。参照マウスピー"
            "スのボディ径を変えると内周も自動で追従します。接触の頂点はリー"
            "ド背面（カマボコ）に沿うので、締め代は全接触で揃います。"))
        if z0 < seat0 - 1e-9:
            # 座は「実測のリガチャー帯 ≈18mm / heel 79mm」から作った公称値であって
            # 壁ではない。はみ出しは事実として出すだけで、警告にはしない。
            advice += (i18n.t(
                "帯は公称の座より {seat0}mm 前へ出ていますが、"
                "座の長さ（最大径の 23%）は典型的なリガチャー"
                "幅から作った公称値なので、これ自体は不都合ではありません。",
                seat0=f"{seat0 - z0:.1f}"))
        if lp.effective_seat_setback(m, p) < p["seat_setback"] - 0.005:
            advice += (i18n.t(
                "座位置は最大径から {seat_setback}mm 前を要求していますが、"
                "これ以上前へ出すと帯が胴から落ちるため実効 {lp}mm です。",
                seat_setback=f"{p['seat_setback']:.1f}",
                lp=f"{lp.effective_seat_setback(m, p):.2f}"))
        return card("ok", advice)

    def _screw_card(self, params: dict) -> dict:
        p = params
        closure = str(p.get("closure", "screw_beak"))
        if closure in ("elastic", "taper"):
            taper = closure == "taper"
            rows = [
                [i18n.t("締結方式"),
                 i18n.choice_label(closure, CLOSURE_LABELS[closure])],
                [i18n.t("締め代"),
                 i18n.t(
                     "押し込み {press_depth} mm ぶん",
                     press_depth=f"{p['press_depth']:.1f}") if taper
                 else i18n.t(
                     "負のはめあい隙間 {clearance} mm",
                     clearance=f"{-p['clearance']:.2f}")],
                [i18n.t("材料"),
                 i18n.choice_label(p["material"],
                                   MATERIAL_LABELS.get(p["material"],
                                                       p["material"]))],
                [i18n.t("バンド厚"), f"{p['band_thickness']:.1f} mm"],
            ]
            advice = (i18n.t(
                "スリットもネジも無い一連のリングです。"
                "市販ねじは部品表に載りません。"))
            advice += (i18n.t(
                "胴の円錐に押し込んで楔で止めます。"
                "掴んでいるのは伸びではなくリングの楕円化（直径方向のたわみ）"
                "なので、伸びない樹脂でも成立します。詳細はテーパ圧入のカー"
                "ドへ。") if taper
                       else i18n.t(
                           "伸ばして嵌めるので、締め代（負の隙間）"
                           "と材料の伸びが締結の実体になります。"))
            return {"title": i18n.t("締結"), "big": i18n.t("ネジなし"), "status": "ok", "rows": rows,
                    "advice": advice}

        nominal, hole_d, head_d = lp.screw_spec(p)
        need = lp.required_screw_length(p)
        stock = lp.stock_screw_length(p)
        need_boss = lp.min_boss_height(p)
        rows = [
            [i18n.t("締結方式"),
             i18n.choice_label(closure, CLOSURE_LABELS[closure])],
            [i18n.t("ネジ"), i18n.t(
                "M{nominal} × {screw_count} 本",
                nominal=f"{nominal:g}", screw_count=f"{int(p['screw_count'])}")],
            [i18n.t("必要な首下長さ"), i18n.t("{need} mm 以上", need=f"{need:.1f}")],
            [i18n.t("推奨する市販長さ"), f"{stock} mm"],
            [i18n.t("バカ穴径"), f"φ{hole_d:.1f} mm"],
            [i18n.t("耳の厚み"), f"{lp.ear_thickness(p):.1f} mm"],
            [i18n.t("ネジ座の高さ / 下限"),
             f"{p['boss_height']:.1f} / {need_boss:.1f} mm"],
        ]
        if closure == "screw_reed":
            rows += [
                [i18n.t("橋（圧力プレート）の厚み"), f"{lp.bridge_thickness(p):.1f} mm"],
                [i18n.t("橋の下に残る床"), f"{lp.bridge_residual_floor(p):.2f} mm"],
            ]
        big = f"M{nominal:g}×{stock}"
        if p["boss_height"] < need_boss:
            return {"title": i18n.t("締結"), "big": big, "status": "bad", "rows": rows,
                    "advice": i18n.t(
                        "ネジ座が低くバカ穴（φ{hole_d}）が耳から出ます。"
                        "閉じた穴にならずネジが抜けます。"
                        "ネジ座の高さを {need_boss}mm 以上にするか、"
                        "ネジを細くしてください。",
                        hole_d=f"{hole_d:.1f}", need_boss=f"{need_boss:.1f}")}
        if stock < need:
            return {"title": i18n.t("締結"), "big": big, "status": "bad", "rows": rows,
                    "advice": i18n.t(
                        "市販レンジで必要長さを満たせません。"
                        "スリット幅かバンド厚を減らしてください。")}
        advice = (i18n.t(
            "ネジは市販品です。ナットは使わず、"
            "片側の耳をタップ（下穴を開けてねじ立て）しても組めます。"))
        if closure == "screw_reed":
            advice += (i18n.t(
                "逆締めではスリットがリード接触面を割るので、"
                "片側から張り出した橋が反対側に重なって押さえます（橋は構造部"
                "材なので、当たり方を「なし」にはできません）。"))
        return {"title": i18n.t("締結"), "big": big, "status": "ok", "rows": rows,
                "advice": advice}

    #: 樹脂どうしの摩擦係数の**仮定**。楔の比（保持力÷挿入力）はこれと楔角だけで
    #: 決まり、寸法にも材料にも依らない。決着させるのは実測。
    ASSUMED_MU = 0.30
    #: 半径の印刷公差の**仮定** [mm]。`clearance` の推奨 0.20〜0.30mm が
    #: 「印刷公差を見込む」ぶんなので、その半分を片側公差として置いた。
    PRINT_TOL_MM = 0.10
    #: 手で押し込める軸力の目安 [N]（**仮定**）。超えると治具か万力が要る。
    HAND_PRESS_N = 150.0

    def _taper_card(self, params: dict) -> dict:
        """テーパ圧入の楔と挟み力（`closure == "taper"` のときだけ出す）。

        **荷重の型はフープではない。** リードが下から・胴が上から押す直径方向の
        2 点なので、効くのはリングの楕円化。一様内圧のフープ剛性で見積もると
        68〜76 倍硬く出て「閉じた剛体リングは成立しない」という誤った結論になる
        （計画中に実際に踏んだ）。
        """
        import math

        m = self.ref_params()
        p = params
        if not m:
            return {"title": i18n.t("テーパ圧入"), "big": None, "status": "warn",
                    "rows": [], "advice": i18n.t("参照マウスピースが未設定です。")}
        cs, ts = lp.cone_slope(m, p), lp.table_slope(m)
        cone_at, reed_at = lp.press_engagement(m, p)
        ir_cone, ir_reed = lp.press_interference(m, p)
        mat = p.get("material", "petg")
        e = MATERIAL_E_MPA.get(mat)
        rows = [
            [i18n.t("楔半角（円錐 / テーブル）"),
             f"{math.degrees(math.atan(cs)):.2f}° / {math.degrees(math.atan(ts)):.2f}°"],
            [i18n.t("押し込み量"), f"{p['press_depth']:.1f} mm"],
            [i18n.t("円錐側の締め代"), i18n.t(
                "{ir_cone} mm（当たり始め {cone_at} mm）",
                ir_cone=f"{ir_cone:+.3f}", cone_at=f"{cone_at:.2f}")],
            [i18n.t("リード側の締め代"), i18n.t(
                "{ir_reed} mm（当たり始め {reed_at} mm）",
                ir_reed=f"{ir_reed:+.3f}", reed_at=f"{reed_at:.2f}")],
        ]
        force = stress = axial = None
        if e is not None:
            k = lp.ring_stiffness(m, p, e)
            force = k * max(ir_reed, 0.0)
            z0, z1 = lp.seat_range(m, p)
            t = p["band_thickness"]
            second = (z1 - z0) * t ** 3 / 12.0
            r = lp.inner_radius(m, p) + t / 2.0
            stress = (force * r / 2.0) * (t / 2.0) / second
            # 直径方向の荷重 `force` は上（円錐）と下（リード）に同じ大きさで
            # 立つので、軸方向の摩擦は 2 か所ぶん。楔は両方の傾きが足し算になる。
            grip = 2.0 * self.ASSUMED_MU
            wedge = cs + ts
            axial = force * (grip + wedge)
            rows += [
                [i18n.t("リングの楕円化剛性"),
                 i18n.t(
                     "{k} N/mm（{material_labels}・E {e} MPa）",
                     k=f"{k:.0f}",
                     material_labels=i18n.choice_label(
                        mat, MATERIAL_LABELS.get(mat, mat)),
                     e=f"{e:.0f}")],
                [i18n.t("挟み力（リードを押す力）"), f"{force:.0f} N"],
                [i18n.t("帯の曲げ応力"), f"{stress:.1f} MPa"],
                [i18n.t("リードが滑り出す軸力"),
                 i18n.t(
                     "{force} N（μ={self} の仮定）",
                     force=f"{force * self.ASSUMED_MU:.0f}",
                     self=f"{self.ASSUMED_MU}")],
                [i18n.t("押し込む / 抜く軸力（概算）"),
                 i18n.t(
                     "{axial} / {force} N（保持 ÷ 挿入 = {grip}。比は μ "
                     "と楔角だけで決まり寸法にも材料にも依らない）",
                     axial=f"{axial:.0f}",
                     force=f"{force * (grip - wedge):.0f}",
                     grip=f"{grip / (grip + wedge):.2f}")],
                [i18n.t("印刷公差 ±%.2fmm の影響") % self.PRINT_TOL_MM,
                 i18n.t(
                     "停止位置 ±{self} mm ＝ 挟み力 ±{k} N",
                     self=f"{self.PRINT_TOL_MM / cs:.2f}",
                     k=f"{k * self.PRINT_TOL_MM:.0f}")],
            ]

        def card(status, advice):
            return {"title": i18n.t("テーパ圧入"),
                    "big": None if force is None else f"{force:.0f}N",
                    "status": status, "rows": rows, "advice": advice}

        if ir_reed <= 0.0 and ir_cone <= 0.0:
            return card("bad",
                        i18n.t(
                            "押し込み {press_depth}mm "
                            "ではどこにも当たりません（リードは "
                            "{reed_at}mm、円錐は {cone_at}mm から）。"
                            "リングはすべり嵌めのまま抜け落ちます。",
                            press_depth=f"{p['press_depth']:.1f}",
                            reed_at=f"{reed_at:.2f}", cone_at=f"{cone_at:.2f}"))
        if ir_cone <= 0.0:
            return card("warn",
                        i18n.t(
                            "リードには当たっていますが円錐が {ir_cone}mm "
                            "浮いています。リングの上が支えられないので首を振"
                            "ります。押し込みを {cone_at}mm 以上にするか、"
                            "はめあい隙間を {reed_clearance}mm "
                            "以下にして（テーブル 4.18° は円錐 {math}° "
                            "より急なので、隙間 ≤ {cs}×リード逃げ "
                            "で同時に当たります）ください。",
                            ir_cone=f"{-ir_cone:.3f}",
                            cone_at=f"{cone_at:.2f}",
                            reed_clearance=f"{cs / ts * p['reed_clearance']:.2f}",
                            math=f"{math.degrees(math.atan(cs)):.2f}",
                            cs=f"{cs / ts:.2f}"))
        if axial is not None and axial > self.HAND_PRESS_N:
            return card("warn",
                        i18n.t(
                            "押し込みに {axial}N 要ります（手で押せる目安 "
                            "{self}N）。押し込み量を減らすか、"
                            "バンド厚を薄くしてリングを柔らかくしてください。",
                            axial=f"{axial:.0f}",
                            self=f"{self.HAND_PRESS_N:.0f}"))
        if e is None:
            return card("warn",
                        i18n.t(
                            "{material_labels} は楔で掴む方式に向きません（柔"
                            "らかすぎて締め代が力にならない）。"
                            "伸ばして嵌めたいなら締結方式を弾性バンドにしてく"
                            "ださい。",
                            material_labels=i18n.choice_label(
                        mat, MATERIAL_LABELS.get(mat, mat))))
        return card("ok",
                    i18n.t(
                        "円錐とリードの両方に当たっています。"
                        "掴んでいるのはフープの伸びではなく**リングの楕円化**"
                        "（直径方向のたわみ）なので、"
                        "伸びない樹脂でも成立します。挟み力・"
                        "応力はリングだけの見積りで、実物はリー"
                        "ド背面が潰れるぶん柔らかい ＝ "
                        "**硬め側に外れます**。決着させるのは印刷して押し込む"
                        "こと。"))

    def _strength_card(self, params: dict) -> dict:
        p = params
        mat = p.get("material", "petg")
        elastic = str(p.get("closure")) == "elastic"
        need = max(MIN_BAND_THICKNESS.get(mat, 2.0), p["min_wall"])
        _, _, head_d = lp.screw_spec(p)
        rows = [
            [i18n.t("バンド厚"), f"{p['band_thickness']:.1f} mm"],
            [i18n.t("材料別の推奨下限"), f"{need:.1f} mm"],
            [i18n.t("耳の厚み / ネジ頭径"), f"{lp.ear_thickness(p):.1f} / {head_d:.1f} mm"],
        ]
        if elastic:
            rows.append([i18n.t("伸びる材料か"),
                         i18n.t("はい") if mat in STRETCHY_MATERIALS else i18n.t("いいえ")])
            if mat not in STRETCHY_MATERIALS:
                return {"title": i18n.t("印刷強度"), "big": i18n.t("不可"), "status": "bad",
                        "rows": rows,
                        "advice": i18n.t(
                            "{material_labels} のリングは伸びません。"
                            "ネジなしで嵌めるには {tpu} "
                            "のような弾性材料が要ります（薄いバンドなら成立す"
                            "る余地はあるので、形状としては作れます）。",
                            material_labels=i18n.choice_label(
                        mat, MATERIAL_LABELS.get(mat, mat)),
                            tpu=i18n.choice_label("tpu", MATERIAL_LABELS["tpu"]))}
        if p["band_thickness"] < need:
            return {"title": i18n.t("印刷強度"), "big": i18n.t("要注意"), "status": "warn", "rows": rows,
                    "advice": i18n.t(
                        "{material_labels} では {need}mm 以上を推奨します。"
                        "締結荷重で層間剥離（FDM）や割れ（レジン）"
                        "が起きやすい厚みです。",
                        material_labels=i18n.choice_label(
                        mat, MATERIAL_LABELS.get(mat, mat)),
                        need=f"{need:.1f}")}
        return {"title": i18n.t("印刷強度"), "big": i18n.t("良好"), "status": "ok", "rows": rows,
                "advice": i18n.t(
                    "積層方向はバンドの周方向に対して垂直（軸方向を積層方向に"
                    "しない）にすると層間剥離を避けられます。")}

    # ------------------------------------------------------------ 領域・BOM・仕様書

    def assembly_placement(self, params: dict) -> dict | None:
        """恒等。断面が参照マウスピースの z でそのまま張られている
        （`REF_SHARES_FRAME` と同じ根拠。`build()` に平行移動も回転も無い）。"""
        return {"origin": [0.0, 0.0, 0.0], "rotate_x_deg": 0.0}

    def regions(self, params: dict) -> dict:
        m = self.ref_params()
        return lp.param_regions(m, params) if m else {}

    def dimensions(self, params: dict) -> list[dict]:
        """主要寸法の寸法線。座標は**マウスピースの系**（4-C.4 と同じ理由で共有）。

        座位置は**実効値**を測る（最大径から帯の後端まで）。前へ出しすぎて胴から
        落ちる手前で飲まれることがあるので、`dim()` が「指定 ○○」を併記して
        **報告されたクランプ**をそのまま図に出す。既定（最大径に密着）では
        長さ 0 になるので線ごと出さない。

        スリットとネジ座はネジ式のときだけ。弾性バンド／テーパ圧入には存在しない。
        """
        m = self.ref_params()
        if not m:
            return []
        from . import profiles

        p = params
        sp = {s.key: s for s in self.localized_specs()}
        reed = self.reed_params()
        z0, z1 = lp.seat_range(m, p)
        zm = 0.5 * (z0 + z1)
        _, seat1 = profiles.ligature_seat_range(m)
        r_in = lp.inner_radius(m, p)
        r_out = r_in + p["band_thickness"]
        UP, AFT = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)

        out = [
            dim([0.0, r_out, z0], [0.0, r_out, z1], UP,
                spec=sp["band_width"], params=p, level=0),
            dim([0.0, r_in, zm], [0.0, r_out, zm], AFT,
                spec=sp["band_thickness"], params=p, level=0),
            dim([0.0, -r_in, zm], [0.0, r_in, zm], AFT,
                key="inner_dia", label=i18n.t("内周径"), unit="mm", level=1),
        ]
        # 最大径に密着（既定）なら長さ 0 の線になるので**出さない**。
        # 潰れた寸法は図の情報を増やさず、ラベルだけが重なる。
        if seat1 - z1 > 1e-9:
            out.append(dim([0.0, r_out, z1], [0.0, r_out, seat1], UP,
                           spec=sp["seat_setback"], params=p, level=1))
        if lp.has_screws(p):
            base, tip = lp.ear_span(m, p, reed)
            ear = lp.ear_thickness(p)
            x_ear = p["slit_width"] / 2.0 + ear / 2.0
            # スリットは耳の頂点で測る（そこが外から見える幅）。逆締めでは
            # 耳が下（リード側）へ伸びるので、逃がす向きも一緒に反転する。
            away = (0.0, 1.0 if tip >= base else -1.0, 0.0)
            out.append(dim([-p["slit_width"] / 2.0, tip, zm],
                           [p["slit_width"] / 2.0, tip, zm], away,
                           spec=sp["slit_width"], params=p, level=2))
            out.append(dim([x_ear, base, zm], [x_ear, tip, zm], AFT,
                           spec=sp["boss_height"], params=p, level=2))
        return out

    def bom(self, params: dict) -> list[dict]:
        p = params
        size_label = {"soprano": i18n.t("ソプラノ"), "alto": i18n.t("アルト"), "tenor": i18n.t("テナー")}[self.size]
        m = self.ref_params()
        rows = [
            {"type": i18n.t("3Dプリント"), "name": i18n.t(
                "リガチャー本体（{size_label}）",
                size_label=f"{size_label}"), "qty": 1,
             "material": i18n.choice_label(
                 p["material"], MATERIAL_LABELS.get(p["material"],
                                                    p["material"])),
             "note": i18n.t("内周 φ{lp}mm", lp=f"{lp.inner_radius(m, p) * 2.0:.1f}") if m else "-"},
        ]
        if lp.has_screws(p):
            nominal, _, _ = lp.screw_spec(p)
            rows.append({"type": i18n.t("市販品"),
                         "name": i18n.t(
                             "なべ小ねじ M{nominal}×{lp}",
                             nominal=f"{nominal:g}",
                             lp=f"{lp.stock_screw_length(p)}"),
                         "qty": int(p["screw_count"]), "material": i18n.t("ステンレス"),
                         "note": i18n.t("締結用。頭部は+または六角穴")})
        kind = lp.contact_kind(p)
        if kind != "none":
            n = lp.contact_n(p)
            rows.append({"type": i18n.t("備考"), "name": i18n.t("リード接触"), "qty": 1,
                         "material": i18n.t("本体と一体"),
                         "note": i18n.choice_label(
                             kind, CONTACT_LABELS[kind])
                                 + ("" if n == 0 else f" × {n}")})
        if str(p.get("closure")) == "screw_reed":
            rows.append({"type": i18n.t("備考"), "name": i18n.t("橋（圧力プレート）"), "qty": 1,
                         "material": i18n.t("本体と一体"),
                         "note": i18n.t(
                             "厚み {lp}mm・片持ち",
                             lp=f"{lp.bridge_thickness(p):.1f}")})
        if str(p.get("closure")) == "taper" and m:
            ic, ir = lp.press_interference(m, p)
            rows.append({"type": i18n.t("備考"), "name": i18n.t("テーパ圧入"), "qty": 1,
                         "material": "-",
                         "note": i18n.t(
                             "押し込み {press_depth}mm（締め代 円錐 {ic} / "
                             "リード {ir} mm）",
                             press_depth=f"{p['press_depth']:.1f}",
                             ic=f"{ic:+.3f}", ir=f"{ir:+.3f}")})
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
        caption = (i18n.t(
            "帯の断面（実線=外周 / 青破線=内周（接触の凸を含む） / "
            "赤破線=テーブル面 / 緑破線=リード裏面の中央） 単位:mm"))
        if sec["bridge"]:
            layers.append({"pts": sec["bridge"], "stroke": "#9944cc", "width": 1.2})
            caption = (i18n.t(
                "帯の断面（実線=外周 / 青破線=内周 / 紫=橋（圧力プレート） /"
                " 赤破線=テーブル面 / 緑破線=リード裏面の中央） 単位:mm"))
        return polyline_svg(layers, caption)

    def spec_extras(self, params: dict) -> dict:
        m = self.ref_params()
        p = params
        kind = lp.contact_kind(p)
        n = lp.contact_n(p)
        dims = [
            (i18n.t("バンド幅 × 厚み"),
             f"{p['band_width']:.1f} × {p['band_thickness']:.1f} mm"),
            (i18n.t("締結方式"),
             i18n.choice_label(str(p.get("closure")),
                               CLOSURE_LABELS.get(str(p.get("closure")),
                                                  "-"))),
            (i18n.t("リードへの当たり方"),
             i18n.choice_label(kind, CONTACT_LABELS.get(kind, "-"))
             + ("" if n == 0 else f" × {n}")),
        ]
        if lp.has_screws(p):
            dims += [
                (i18n.t("スリット幅"), f"{p['slit_width']:.1f} mm"),
                (i18n.t("ネジ"), i18n.t(
                    "M{lp} × {screw_count} 本 （首下 {lp2}mm）",
                    lp=f"{lp.screw_spec(p)[0]:g}",
                    screw_count=f"{int(p['screw_count'])}",
                    lp2=f"{lp.stock_screw_length(p)}")),
            ]
        if str(p.get("closure")) == "screw_reed":
            dims.append((i18n.t("橋の厚み / 残る床"),
                         f"{lp.bridge_thickness(p):.1f} / "
                         f"{lp.bridge_residual_floor(p):.2f} mm"))
        if str(p.get("closure")) == "taper" and m:
            ic, ir = lp.press_interference(m, p)
            ca, ra = lp.press_engagement(m, p)
            dims += [
                (i18n.t("押し込み量"), f"{p['press_depth']:.1f} mm"),
                (i18n.t("締め代（円錐 / リード）"), f"{ic:+.3f} / {ir:+.3f} mm"),
                (i18n.t("当たり始め（円錐 / リード）"), f"{ca:.2f} / {ra:.2f} mm"),
            ]
        extras: dict = {"dimensions": dims}
        if m:
            z0, z1 = lp.seat_range(m, p)
            dims.insert(0, (i18n.t("内周径"), f"φ{lp.inner_radius(m, p) * 2.0:.2f} mm"))
            dims.append((i18n.t("装着位置 z"), f"{z0:.1f}〜{z1:.1f} mm"))
            extras["sections"] = [{"title": i18n.t("帯の断面"),
                                   "svg": self._section_svg(m, p)}]
        return extras
