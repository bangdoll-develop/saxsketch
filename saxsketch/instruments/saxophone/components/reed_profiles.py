"""リードの断面プロファイル（純数学・OCCT非依存）。

`profiles.py`（マウスピース）と同じ方針: ジオメトリ生成・剛性計算・断面SVG・
音響モデルがすべて本モジュールを共用する。

座標系:
  Z: 軸方向。z=0 が先端（ティップ）、z=L が踵（ヒール）。
  Y: テーブル面（マウスピース接地面）が **y=0**。ブレードは y>0 側のみ。
  X: 幅方向（中心 0）。

テーブル面を y=0 に置くのは、(a) マウスピースへの密着面を厳密な平面にするため、
(b) 3Dビューアの領域ハイライトが y の符号で上下面を判定するため（リードは全体が
y>=0 なので side は "top" / "all" のみ使う）。
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------- 基本量

def vamp_start_z(p: dict) -> float:
    """削り始め（バーク端）の z。ここから踵側は未削の一定厚。"""
    return min(p["vamp_length"], p["reed_length"] - 2.0)


def width(p: dict, z: float) -> float:
    """z 位置の幅。先端幅 → 踵幅の線形テーパー＋先端角の丸み。"""
    t = min(max(z / p["reed_length"], 0.0), 1.0)
    w = p["tip_width"] + (p["heel_width"] - p["tip_width"]) * t
    r = p.get("tip_corner_r", 0.8)
    if 0.0 < z < r:  # 平面視での先端角の丸み（両側から削る）
        w -= 2.0 * (r - math.sqrt(max(r * r - (r - z) ** 2, 0.0)))
    elif z <= 0.0:
        w -= 2.0 * r
    return max(w, 0.5)


def _profile_shape(kind: str, t: float) -> float:
    """バンプ形状。t∈[0,1]（0=先端, 1=バーク端）→ 厚み上昇率 u∈[0,1]。"""
    t = min(max(t, 0.0), 1.0)
    if kind == "linear":
        return t
    if kind == "concave":
        # アメリカンカット風: 先端側が薄いまま伸び、後半で急に厚くなる
        return t ** 1.8
    return t ** 1.35  # parabolic（既定・フレンチカット寄り）


def thickness(p: dict, z: float, x: float = 0.0) -> float:
    """z（と幅方向 x）における厚み。x=0 が中央（背骨）、|x|=w/2 が側端。

    `tip_thickness` / `heel_thickness` は**中央の厚み**を指す（ゲージで測る位置）。
    幅方向は中央を頂点に側端へ向かって薄くなり、その比が `side_rail_thin`。
    `spine_ratio` は薄化の指数で、大きいほど中央の平坦部（背骨）が広くなる。
    薄化はバーク端でゼロに収束させる（削っていない部分は全幅一定厚）。
    """
    zv = vamp_start_z(p)
    if z >= zv:
        return p["heel_thickness"]  # バークは全幅一定（テーブル密着部）
    u = _profile_shape(p.get("profile_curve", "parabolic"), z / zv)
    t_center = p["tip_thickness"] + (p["heel_thickness"] - p["tip_thickness"]) * u
    hw = width(p, z) / 2.0
    q = min(abs(x) / hw, 1.0) if hw > 0 else 0.0
    rail = p.get("side_rail_thin", 0.55)
    spine = p.get("spine_ratio", 1.15)
    blend = 1.0 - u  # 先端で最大、バーク端で 0
    return t_center * (1.0 - (1.0 - rail) * blend * q ** (2.0 * spine))


def edge_thickness(p: dict, z: float) -> float:
    """側端の厚み（角丸半径の上限に使う）。"""
    return thickness(p, z, width(p, z) / 2.0)


# ---------------------------------------------------------------- ロフト断面

_STATION_TS = [0.0, 0.02, 0.05, 0.10, 0.18, 0.28, 0.40, 0.55, 0.72, 0.88, 1.0]


def station_zs(p: dict) -> list[float]:
    """断面を置く z 列。先端側を密にし、バーク端と踵を必ず含める。"""
    zv = vamp_start_z(p)
    zs = [t * zv for t in _STATION_TS]
    zs.append(zv + 0.01)          # バーク段差（削り終わりを明示）
    zs.append(p["reed_length"])
    return sorted(set(round(z, 4) for z in zs))


def sections(p: dict) -> list[dict]:
    """`loft_sections` 用の断面列。底面は y=0 で厳密に平坦。"""
    from saxsketch.geometry.builders import flat_bottom_rect_pts

    out: list[dict] = []
    for z in station_zs(p):
        w = width(p, z)
        h = thickness(p, z, 0.0)          # 中央（背骨）の厚み＝断面の最大高さ
        # 側端の薄化は上側2隅の角丸で表現する。半径 r の角丸は側端の高さを
        # ちょうど h-r にするので、r = 中央厚 - 側端厚 とすれば厚み分布と整合する。
        drop = max(h - edge_thickness(p, z), 0.0)
        r = min(drop, h * 0.9, w * 0.45)
        out.append({"z": z, "pts": flat_bottom_rect_pts(w, h, 0.0, r)})
    return out


def blade_volume_mm3(p: dict) -> float:
    """ブレード体積（断面積の台形積分）。BOM の材料量・質量推定に使う。"""
    zs = station_zs(p)
    vol = 0.0
    for a, b in zip(zs, zs[1:]):
        vol += (_area(p, a) + _area(p, b)) / 2.0 * (b - a)
    return vol


def _area(p: dict, z: float, samples: int = 12) -> float:
    """幅方向に厚みを積分した断面積。"""
    w = width(p, z)
    acc = 0.0
    for i in range(samples):
        x = -w / 2.0 + w * (i + 0.5) / samples
        acc += thickness(p, z, x)
    return acc * (w / samples)


# ---------------------------------------------------------------- 剛性（音響モデル用）

def second_moment(p: dict, z: float, samples: int = 12) -> float:
    """断面二次モーメント I [mm^4]（曲げ中立軸まわり）。

    厚みが幅方向に変わるため、幅を短冊に分けて平行軸の定理で合成する
    （各短冊は底面 y=0 の矩形だが図心の高さ h/2 が異なるため単純加算できない）。
    """
    w = width(p, z)
    dx = w / samples
    strips = []
    for i in range(samples):
        x = -w / 2.0 + w * (i + 0.5) / samples
        h = thickness(p, z, x)
        strips.append((h, dx))
    area = sum(h * b for h, b in strips)
    if area <= 0:
        return 0.0
    yc = sum(h * b * (h / 2.0) for h, b in strips) / area   # 図心の y
    inertia = 0.0
    for h, b in strips:
        inertia += b * h ** 3 / 12.0 + (h * b) * (h / 2.0 - yc) ** 2
    return inertia


def cross_area(p: dict, z: float) -> float:
    return _area(p, z)


# ---------------------------------------------------------------- 影響領域（UIハイライト用）

def param_regions(p: dict) -> dict:
    """各パラメータが影響するモデル領域 {key: {z0, z1, side, label}}。

    リードは全体が y>=0 にあるため side は "top" / "all" のみ使う
    （Viewer3D は y の符号で上下を判定する）。
    """
    length = p["reed_length"]
    zv = vamp_start_z(p)

    def r(z0, z1, side, label):
        return {"z0": round(max(z0, 0.0), 2), "z1": round(min(z1, length), 2),
                "side": side, "label": label}

    return {
        "reed_length":    r(0.0, length, "all", "リード全体"),
        "tip_width":      r(0.0, 0.15 * length, "all", "先端（ティップ）"),
        "heel_width":     r(zv, length, "all", "踵（ヒール）"),
        "tip_thickness":  r(0.0, 0.12 * zv, "top", "先端の削り"),
        "heel_thickness": r(zv, length, "all", "バーク（未削部）"),
        "vamp_length":    r(0.0, zv, "top", "ヴァンプ（削り面）"),
        "profile_curve":  r(0.0, zv, "top", "ヴァンプ（削り面）"),
        "spine_ratio":    r(0.0, zv, "top", "中央の背骨"),
        "side_rail_thin": r(0.0, zv, "top", "サイドレール（両脇）"),
        "tip_corner_r":   r(0.0, 0.10 * zv, "top", "先端角の丸み"),
        "file_cut":       r(zv - 2.0, zv + 1.0, "top", "ファイルドカット（削り終わり）"),
        # material / min_layer は形状に影響しない → 領域なし
    }


# ---------------------------------------------------------------- 断面SVG用

def side_profile_polylines(p: dict, samples: int = 100) -> dict:
    """厚みプロファイル図のポリライン群（SVG描画用、単位mm）。

    テーブル面（y=0）を基準に、中央（背骨）と側端の厚み曲線を重ねて示す。
    """
    length = p["reed_length"]
    zs = [length * i / (samples - 1) for i in range(samples)]
    return {
        "table": [(0.0, 0.0), (length, 0.0)],
        "center": [(z, thickness(p, z, 0.0)) for z in zs],
        "edge": [(z, edge_thickness(p, z)) for z in zs],
        "plan": [(z, width(p, z) / 2.0) for z in zs],
        "vamp_start": vamp_start_z(p),
    }
