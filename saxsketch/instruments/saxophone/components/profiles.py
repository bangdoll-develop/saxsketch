"""マウスピースの断面プロファイル（純数学・OCCT非依存）。

座標系:
  Z: 軸方向。z=0 がティップ（先端）、z=L がシャンク端。
  Y: +Y がビーク（上面）、-Y がテーブル（リード側）。
  X: 幅方向。

ジオメトリ生成・体積計算・断面SVG・音響シミュレーションが本モジュールを共用する。
断面はすべてスーパー楕円 |2x/w|^n + |2(y-yc)/h|^n = 1 で表現する
（n=2 かつ w=h で真円、n が大きいほど角形）。ロフトが安定し自己交差しない。
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------- 基本量

def table_y(p: dict) -> float:
    """テーブル平面（リード接地面）の Y 座標。"""
    return -0.40 * p["body_dia"]


def bore_radius(p: dict) -> float:
    return p["bore_dia"] / 2.0


def bore_start_z(p: dict) -> float:
    return p["overall_length"] - p["bore_length"]


def window_width(p: dict) -> float:
    return p["reed_width"] - 2.0 * p["side_rail_width"]


def throat_radius(p: dict) -> float:
    """スロート（チェンバー最狭部）の等価半径。断面積 = throat_ratio × ボア断面積。"""
    return bore_radius(p) * math.sqrt(p["throat_ratio"])


# ---------------------------------------------------------------- フェイシング

def facing_rise(p: dict, z: float) -> float:
    """テーブル平面からのフェイシングカーブ持ち上がり量（z<=facing_length で >0）。"""
    fl = p["facing_length"]
    tip = p["tip_opening"]
    if z >= fl:
        return 0.0
    if p.get("facing_curve", "elliptic") == "radial":
        # テーブルに接する円弧。R は y(0)=tip となるよう決定。
        r = (fl * fl + tip * tip) / (2.0 * tip)
        return r - math.sqrt(max(r * r - (fl - z) ** 2, 0.0))
    # 楕円（z=fl で接線水平）
    t = (fl - z) / fl
    return tip * (1.0 - math.sqrt(max(1.0 - t * t, 0.0)))


def cut_top_y(p: dict, z: float) -> float:
    """テーブル/フェイシングカット面の上端 Y。

    テーブルはリガチャー座の下まで平面、その先はランプで胴の丸みに消える。
    """
    ty = table_y(p)
    length = p["overall_length"]
    ramp_start = 0.55 * length
    ramp_end = 0.63 * length
    if z <= ramp_start:
        return ty + facing_rise(p, z)
    if z >= ramp_end:
        return ty - 4.0
    t = (z - ramp_start) / (ramp_end - ramp_start)
    return ty - 4.0 * t


def table_cut_end_z(p: dict) -> float:
    return 0.63 * p["overall_length"]


# ---------------------------------------------------------------- 外形・ビーク

_OUTER_PROFILE = [  # (z/L, r/rb) 制御点
    (0.00, 0.70),
    (0.15, 0.82),
    (0.32, 0.96),
    (0.42, 1.00),
    (0.70, 1.00),
    (0.86, 0.93),
    (1.00, 0.84),
]


def outer_radius(p: dict, z: float) -> float:
    rb = p["body_dia"] / 2.0
    t = min(max(z / p["overall_length"], 0.0), 1.0)
    pts = _OUTER_PROFILE
    for (t0, r0), (t1, r1) in zip(pts, pts[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            u = u * u * (3 - 2 * u)  # smoothstep で滑らかに
            return rb * (r0 + (r1 - r0) * u)
    return rb * pts[-1][1]


def beak_y(p: dict, z: float) -> float:
    """ビークカット平面の Y 座標（この上側を切除）。"""
    ty = table_y(p)
    y0 = ty + p["tip_opening"] + 2.6          # ティップ先端のくさび厚
    z_bite = 0.25 * p["overall_length"]       # バイトポイント目安
    y_bite = ty + p["beak_height"]
    m = (y_bite - y0) / z_bite
    return y0 + m * z


# ---------------------------------------------------------------- 内部空洞

def _smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _baffle_progress(p: dict, t: float) -> float:
    """窓区間内 t∈[0,1] に対する天井上昇率 u∈[0,1]。バッフル種別で形が変わる。"""
    kind = p.get("baffle_type", "rollover")
    if kind == "straight":
        return t
    if kind == "rollover":
        expo = 1.6 + p.get("rollover_radius", 8.0) / 10.0
        return t ** expo
    if kind == "step":
        return 0.06 + 0.94 * _smoothstep((t - 0.40) / 0.15)
    if kind == "high":
        return 0.04 + 0.96 * _smoothstep((t - 0.75) / 0.22)
    return t


def cavity_stations(p: dict) -> list[dict]:
    """内部空洞ロフトの断面ステーション列。

    各要素: {z, yc, h, w, n}（スーパー楕円）。ティップ側→ボア側の順。
    """
    ty = table_y(p)
    z_start = p["tip_rail_width"] + 0.2
    z_we = z_start + p["window_length"]
    zb = bore_start_z(p)
    z_we = min(z_we, zb - 8.0)  # チェンバー遷移の余地を確保
    rb_bore = bore_radius(p)
    r_t = throat_radius(p)
    w_win = window_width(p)
    h_b = p["baffle_height"]
    min_wall = p["min_wall"]

    # チェンバー円（窓の直後）
    z_c1 = z_we + 3.0
    c1_bot = ty + 1.5
    c1_top = c1_bot + 1.7 * r_t
    # ボア円
    b_bot, b_top = -rb_bore, rb_bore

    # ティップ天井基準
    floor0 = ty + facing_rise(p, z_start) - 0.8
    c_tip = floor0 + 1.6
    ch_top_target = c1_top

    n_window = 3.5
    n_chamber = 2.2 if p.get("chamber_shape", "round") == "round" else 3.8

    stations: list[dict] = []
    window_ts = [0.0, 0.12, 0.25, 0.40, 0.55, 0.70, 0.82, 0.92, 1.0]
    for t in window_ts:
        z = z_start + t * (z_we - z_start)
        if t <= 0.90:
            floor = ty + facing_rise(p, z) - 0.8   # カット面より下 → 窓が開く
        else:
            floor = ty + 1.2                        # 窓を閉じる
        u = _baffle_progress(p, t)
        ceil_ = c_tip + (ch_top_target - c_tip) * u
        ceil_ -= h_b * 0.55 * (1.0 - t)             # 高バッフル = 天井をリードに近づける
        ceil_ = min(ceil_, beak_y(p, z) - min_wall)
        ceil_ = max(ceil_, floor + 1.0)
        w = w_win * (0.82 + 0.18 * t)
        stations.append({"z": z, "yc": (floor + ceil_) / 2, "h": ceil_ - floor,
                         "w": w, "n": n_window})

    # チェンバー遷移（窓終端 → ボア開始）
    z_c2 = (z_c1 + zb) / 2.0
    chamber = [
        (z_c1, c1_bot, c1_top, 2.0 * r_t * 1.05, n_chamber),
        (z_c2, (c1_bot + b_bot) / 2, (c1_top + b_top) / 2,
         (2.0 * r_t * 1.05 + 2.0 * rb_bore) / 2, (n_chamber + 2.0) / 2),
        (zb, b_bot, b_top, 2.0 * rb_bore, 2.0),
    ]
    for z, bot, top, w, n in chamber:
        # 外壁肉厚の確保
        lim = -(outer_radius(p, z) - min_wall)
        bot = max(bot, lim)
        stations.append({"z": z, "yc": (bot + top) / 2, "h": top - bot, "w": w, "n": n})
    return stations


def superellipse_area(w: float, h: float, n: float) -> float:
    """スーパー楕円の面積。A = w·h·Γ(1+1/n)² / Γ(1+2/n)"""
    g1 = math.gamma(1.0 + 1.0 / n)
    g2 = math.gamma(1.0 + 2.0 / n)
    return w * h * (g1 * g1) / g2


def cavity_volume_cc(p: dict) -> dict:
    """内部空洞体積の解析近似（断面積の台形積分 + ボア円筒）。

    Returns: total_cc(空洞全体), effective_cc(コーク位置まで＝ネック挿入分を除く)
    """
    st = cavity_stations(p)
    vol = 0.0
    for a, b in zip(st, st[1:]):
        area_a = superellipse_area(a["w"], a["h"], a["n"])
        area_b = superellipse_area(b["w"], b["h"], b["n"])
        vol += (area_a + area_b) / 2.0 * (b["z"] - a["z"])
    r = bore_radius(p)
    vol += math.pi * r * r * p["bore_length"]
    total_cc = vol / 1000.0
    neck_occupied = math.pi * r * r * p["cork_depth"] / 1000.0
    return {"total_cc": total_cc, "effective_cc": total_cc - neck_occupied}


# ---------------------------------------------------------------- 影響領域（UIハイライト用）

def param_regions(p: dict) -> dict:
    """各パラメータが影響するモデル領域 {key: {z0, z1, side, label}}。

    side: "top"=ビーク側(y>0) / "bottom"=テーブル側(y<0) / "all"=全周。
    3Dビューアが頂点カラーで該当部を着色するために使う。
    """
    length = p["overall_length"]
    fl = p["facing_length"]
    z_start = p["tip_rail_width"] + 0.2
    zb = bore_start_z(p)
    z_we = min(z_start + p["window_length"], zb - 8.0)
    z_baffle_end = z_start + 0.60 * (z_we - z_start)

    def r(z0, z1, side, label):
        return {"z0": round(max(z0, 0.0), 2), "z1": round(min(z1, length), 2),
                "side": side, "label": label}

    return {
        # フェイシング
        "tip_opening":     r(0.0, fl, "bottom", "フェイシング（ティップ〜カーブ終端）"),
        "facing_length":   r(0.0, fl, "bottom", "フェイシング（ティップ〜カーブ終端）"),
        "facing_curve":    r(0.0, fl, "bottom", "フェイシングカーブ"),
        "tip_rail_width":  r(0.0, max(z_start + 1.0, 2.5), "bottom", "ティップレール"),
        "side_rail_width": r(z_start, z_we, "bottom", "サイドレール（窓の両脇）"),
        # バッフル（窓の天井前半）
        "baffle_type":     r(z_start, z_baffle_end, "all", "バッフル（窓の天井）"),
        "baffle_height":   r(z_start, z_baffle_end, "all", "バッフル（窓の天井）"),
        "rollover_radius": r(z_start, z_start + 0.5 * (z_we - z_start), "all",
                             "バッフル肩の丸み"),
        # チェンバー
        "throat_ratio":    r(z_we, zb, "all", "チェンバー〜スロート"),
        "chamber_shape":   r(z_we, zb, "all", "チェンバー断面"),
        # ボア
        "bore_dia":        r(zb, length, "all", "ボア（円筒部）"),
        "bore_length":     r(zb, length, "all", "ボア（円筒部）"),
        "cork_depth":      r(length - p["cork_depth"], length, "all",
                             "シャンク（ネック挿入部）"),
        # ウィンドウ
        "window_length":   r(z_start, z_we, "bottom", "ウィンドウ（リード開口）"),
        "reed_width":      r(z_start, z_we, "bottom", "テーブル・窓幅"),
        # 外形
        "beak_height":     r(0.0, 0.30 * length, "top", "ビーク（上面）"),
        "body_dia":        r(0.42 * length, 0.70 * length, "all", "ボディ（リガチャー座）"),
        "overall_length":  r(0.0, length, "all", "全体"),
        # 製造
        "min_wall":        r(0.0, length, "all", "全体（肉厚）"),
        # material は形状に影響しない → 領域なし
    }


# ---------------------------------------------------------------- 断面SVG用

def side_profile_polylines(p: dict, samples: int = 120) -> dict:
    """側面断面図のポリライン群（SVG描画用、単位mm）。"""
    length = p["overall_length"]
    zs = [length * i / (samples - 1) for i in range(samples)]
    outer_top = [(z, min(beak_y(p, z), outer_radius(p, z))) for z in zs]
    outer_bot = [(z, max(-outer_radius(p, z), cut_top_y(p, z))
                  if z < table_cut_end_z(p) else -outer_radius(p, z)) for z in zs]
    stations = cavity_stations(p)
    cavity_top = [(s["z"], s["yc"] + s["h"] / 2) for s in stations]
    cavity_bot = [(s["z"], s["yc"] - s["h"] / 2) for s in stations]
    r = bore_radius(p)
    zb = bore_start_z(p)
    cavity_top += [(length, r)]
    cavity_bot += [(length, -r)]
    return {
        "outer_top": outer_top,
        "outer_bot": outer_bot,
        "cavity_top": cavity_top,
        "cavity_bot": cavity_bot,
        "table_y": table_y(p),
        "bore_start": zb,
    }
