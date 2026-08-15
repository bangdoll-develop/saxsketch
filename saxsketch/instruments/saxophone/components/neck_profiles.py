"""サクソフォン ネックの幾何（純数学・OCCT非依存）。

`profiles.py` / `reed_profiles.py` と同じ方針で、build123d に依存しない座標計算だけを
持つ。ソリッド生成（revolve / loft / ブーリアン）は `neck.py` 側が本モジュールの返す
点列・配置を使って行う。

座標系:
  - センターライン弧長 s：s=0 がマウスピース側（テノン端・小ボア）、s 増加でボディ側。
  - 曲げ（ベンド）は XZ 平面内。曲げ角 0 なら +Z 一直線（`neck.py` は revolve 経路へ）。
  - 断面リングは局所接線に直交する2軸 a(面内)・b=+Y(面外) で張る。
"""
from __future__ import annotations

import math

_RING_N = 48       # 断面リングの点数（全リング一定＝ロフト堅牢性）
_STATIONS = 40     # ベンド時のロフト断面数


# --------------------------------------------------------------------------- 寸法

def bore_large_id(p: dict, si: dict) -> float:
    """ボディ側（大端）ボア内径 [mm]。"""
    if p["taper_from_cone"] == "on":
        half = math.radians(si["cone_half_angle_deg"])
        return p["bore_small_id"] + 2.0 * p["neck_length"] * math.tan(half)
    return p["bore_large_id"]


def bore_radius_at(s: float, p: dict, si: dict) -> float:
    """弧長 s におけるボア半径 [mm]（小端→大端の線形テーパ）。"""
    L = p["neck_length"]
    r0 = p["bore_small_id"] / 2.0
    r1 = bore_large_id(p, si) / 2.0
    return r0 + (r1 - r0) * (s / L)


def outer_radius_at(s: float, p: dict, si: dict) -> float:
    """弧長 s における外形半径 [mm]。

    テノン区間は外径一定（コルク座）、本管は ボア半径＋肉厚、ボディ側は挿入用に一段細く。
    """
    L = p["neck_length"]
    tube = bore_radius_at(s, p, si) + p["wall_thickness"]
    if s <= p["tenon_length"]:
        return p["tenon_od"] / 2.0
    body0 = L - p["body_tenon_length"]
    if s >= body0:
        # ボディ受けへ差し込む段付きスピゴット（肉厚は残す）
        return max(tube - 1.0, bore_radius_at(s, p, si) + 0.8)
    return tube


def arc_length(p: dict) -> float:
    return p["neck_length"]


# --------------------------------------------------------------------------- センターライン

def _bend(p: dict):
    """(straight_len, arc_len, Rb, ang_rad)。Rb=None ならストレート。"""
    ang = math.radians(p["bend_angle"])
    L = p["neck_length"]
    straight = min(p["bend_start"], L)
    arc_len = L - straight
    if p["bend_angle"] <= 0.0 or arc_len <= 1e-6:
        return straight, arc_len, None, 0.0
    return straight, arc_len, arc_len / ang, ang


def centerline_point(s: float, p: dict):
    """弧長 s の (point(x,y,z), tangent(unit), in_plane_axis a(unit))。

    a は接線に直交する面内(XZ)軸。曲げ平面外軸は常に b=(0,1,0)。
    """
    straight, _arc, Rb, _ang = _bend(p)
    if Rb is None or s <= straight:
        return (0.0, 0.0, s), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)
    phi = (s - straight) / Rb
    x = Rb - Rb * math.cos(phi)          # 中心 C=(Rb,0,straight) 周りの円弧
    z = straight + Rb * math.sin(phi)
    tangent = (math.sin(phi), 0.0, math.cos(phi))
    a = (math.cos(phi), 0.0, -math.sin(phi))   # φ=0 で +X（曲率中心=凹側）
    return (x, 0.0, z), tangent, a


def _cab(s: float, p: dict):
    """(center, a, b) —— リング生成用フレーム。"""
    pt, _t, a = centerline_point(s, p)
    return pt, a, (0.0, 1.0, 0.0)


def _ring(center, a, b, r: float, n: int = _RING_N):
    out = []
    for i in range(n):
        th = 2.0 * math.pi * i / n
        c, s = math.cos(th), math.sin(th)
        out.append((center[0] + r * (c * a[0] + s * b[0]),
                    center[1] + r * (c * a[1] + s * b[1]),
                    center[2] + r * (c * a[2] + s * b[2])))
    return out


def stations(p: dict) -> list[float]:
    """リングを置く弧長の列。

    公開しているのは `body_profiles` が一体型（ネック直結）でこの列をそのまま
    使うため。同じ列を使うので、一体型のネック区間は別体のネックと**同じリング**
    になる。別に刻むと、同じはずの形が 2 通りできる。
    """
    L = p["neck_length"]
    return [L * i / (_STATIONS - 1) for i in range(_STATIONS)]


# --------------------------------------------------------------------------- ベンド用リング列

def outer_rings(p: dict, si: dict) -> list[list[tuple[float, float, float]]]:
    return [_ring(*_cab(s, p), outer_radius_at(s, p, si)) for s in stations(p)]


def bore_rings(p: dict, si: dict) -> list[list[tuple[float, float, float]]]:
    return [_ring(*_cab(s, p), bore_radius_at(s, p, si)) for s in stations(p)]


# --------------------------------------------------------------------------- ストレート用 (z,r)

def _straight_zs(p: dict) -> list[float]:
    L = p["neck_length"]
    tl = p["tenon_length"]
    body0 = L - p["body_tenon_length"]
    zs = {L * i / 24.0 for i in range(25)}
    for zb in (tl, tl + 1e-3, body0 - 1e-3, body0):   # 段差を明示（肩を立てる）
        if 0.0 <= zb <= L:
            zs.add(zb)
    return sorted(zs)


def outer_stations(p: dict, si: dict) -> list[tuple[float, float]]:
    return [(z, outer_radius_at(z, p, si)) for z in _straight_zs(p)]


def bore_stations(p: dict, si: dict) -> list[tuple[float, float]]:
    L = p["neck_length"]
    return [(L * i / 24.0, bore_radius_at(L * i / 24.0, p, si)) for i in range(25)]


# --------------------------------------------------------------------------- オクターブベント

def octave_vent_placement(p: dict, si: dict) -> dict | None:
    """ベント貫通切削・チムニー・キー座の配置（build123d 非依存の座標のみ）。"""
    if p["octave_vent"] != "on":
        return None
    L = p["neck_length"]
    s = max(0.05, min(0.95, p["vent_position"])) * L
    pt, _t, a = centerline_point(s, p)
    straight, _arc, Rb, _ang = _bend(p)
    if Rb is None or s <= straight:
        axis = (1.0, 0.0, 0.0)                    # 直管は +X 側
    else:
        axis = (-a[0], -a[1], -a[2])              # 曲げの凸(外)側
    outer_r = outer_radius_at(s, p, si)
    bosses = []
    if p["key_mount_bosses"] == "on":
        for off in (-8.0, 8.0):
            cs = max(0.05 * L, min(0.95 * L, s + off))
            cpt, _tt, _aa = centerline_point(cs, p)
            bosses.append({"center": cpt, "axis": axis})
    return {"center": pt, "axis": axis, "dia": p["vent_dia"],
            "chimney_height": p["chimney_height"], "seat_flat": p["seat_flat"] == "on",
            "outer_r": outer_r, "bosses": bosses}


# --------------------------------------------------------------------------- 体積・領域・断面図

def neck_volume_mm3(p: dict, si: dict) -> float:
    """管壁の材料体積 [mm^3]（弧長積分の近似。ベント孔の差分は無視）。"""
    L = p["neck_length"]
    n = 80
    vol = 0.0
    ds = L / n
    for i in range(n):
        s = L * (i + 0.5) / n
        ro = outer_radius_at(s, p, si)
        ri = bore_radius_at(s, p, si)
        vol += math.pi * (ro * ro - ri * ri) * ds
    return vol


def param_regions(p: dict) -> dict:
    """パラメータ → 3Dハイライト用 z ゾーン（曲げ後の実 z で近似）。"""
    L = p["neck_length"]
    tl = p["tenon_length"]
    zt = centerline_point(tl, p)[0][2]
    zL = centerline_point(L, p)[0][2]
    zbody = centerline_point(L - p["body_tenon_length"], p)[0][2]
    reg = {
        "tenon_length": {"z0": 0.0, "z1": zt, "side": "all", "label": "テノン（コルク座）"},
        "tenon_od": {"z0": 0.0, "z1": zt, "side": "all", "label": "テノン外径"},
        "cork_thickness": {"z0": 0.0, "z1": zt, "side": "all", "label": "コルク厚"},
        "bore_small_id": {"z0": 0.0, "z1": zt, "side": "all", "label": "小端ボア"},
        "neck_length": {"z0": 0.0, "z1": zL, "side": "all", "label": "ネック全長"},
        "bend_angle": {"z0": zt, "z1": zL, "side": "all", "label": "曲げ区間"},
        "bore_large_id": {"z0": zt, "z1": zL, "side": "all", "label": "大端ボア"},
        "wall_thickness": {"z0": zt, "z1": zL, "side": "all", "label": "肉厚"},
        "body_tenon_length": {"z0": zbody, "z1": zL, "side": "all", "label": "本体挿入部"},
    }
    if p["octave_vent"] == "on":
        sv = max(0.05, min(0.95, p["vent_position"])) * L
        zv = centerline_point(sv, p)[0][2]
        vent = {"z0": max(0.0, zv - 6.0), "z1": zv + 6.0, "side": "all",
                "label": "オクターブベント"}
        reg["vent_position"] = vent
        reg["vent_dia"] = dict(vent)
        reg["chimney_height"] = dict(vent)
    return reg


def side_profile_polylines(p: dict, si: dict) -> dict:
    """曲げ平面(XZ)での外形・ボア母線。座標は (z, x)（横長に読める向き）。"""
    stations = [p["neck_length"] * i / 60.0 for i in range(61)]
    ot, ob, it, ib = [], [], [], []
    for s in stations:
        (cx, _cy, cz), _t, a = centerline_point(s, p)
        ro = outer_radius_at(s, p, si)
        ri = bore_radius_at(s, p, si)
        ot.append((cz + ro * a[2], cx + ro * a[0]))
        ob.append((cz - ro * a[2], cx - ro * a[0]))
        it.append((cz + ri * a[2], cx + ri * a[0]))
        ib.append((cz - ri * a[2], cx - ri * a[0]))
    return {"outer_top": ot, "outer_bot": ob, "bore_top": it, "bore_bot": ib}
