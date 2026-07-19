"""build123d 共通ビルダー（全楽器・全コンポーネントで再利用）。"""
from __future__ import annotations

import math

from build123d import Edge, Face, Plane, Solid, Vector, Wire, extrude


def superellipse_wire(z: float, yc: float, h: float, w: float, n: float,
                      samples: int = 96) -> Wire:
    """z=const 平面上のスーパー楕円ワイヤ（多角形近似）。

    96点で弦誤差 ≒ 0.01mm 未満（3Dプリント精度未満）。
    スプラインワイヤはロフト面の三角形分割不良・ブーリアン破綻を招いたため
    多角形＋ルールドロフトで堅牢性を優先する。
    """
    pts = []
    for i in range(samples):
        th = 2.0 * math.pi * i / samples
        c, s = math.cos(th), math.sin(th)
        x = (w / 2.0) * math.copysign(abs(c) ** (2.0 / n), c)
        y = yc + (h / 2.0) * math.copysign(abs(s) ** (2.0 / n), s)
        pts.append(Vector(x, y, z))
    return Wire.make_polygon(pts, close=True)


def loft_stations(stations: list[dict]) -> Solid:
    """cavity_stations 形式 [{z,yc,h,w,n}] をロフトして水密ソリッドにする。"""
    wires = [superellipse_wire(s["z"], s["yc"], s["h"], s["w"], s["n"])
             for s in stations]
    solid = Solid.make_loft(wires, ruled=True)
    if solid.volume < 0:  # ThruSections が裏返しシェルを返すことがある
        solid = Solid(solid.wrapped.Reversed())
    return solid


def yz_profile_cut_solid(points_yz: list[tuple[float, float]], half_width: float) -> Solid:
    """YZ平面の閉ポリゴン (z,y) を X 方向 ±half_width に押し出したソリッド。

    フェイシング/テーブルカット・ビークカットなど「側面プロファイルで切る」用途。
    """
    pts = [Vector(0.0, y, z) for (z, y) in points_yz]
    wire = Wire.make_polygon(pts, close=True)
    face = Face(wire)
    solid = extrude(face, amount=half_width, both=True)
    return solid


def revolve_profile(radii: list[tuple[float, float]]) -> Solid:
    """(z, r) プロファイルを Z 軸回りに回転させた回転体。"""
    pts = [Vector(r, 0.0, z) for (z, r) in radii]
    pts.append(Vector(0.0, 0.0, radii[-1][0]))
    pts.append(Vector(0.0, 0.0, radii[0][0]))
    wire = Wire.make_polygon(pts, close=True)
    face = Face(wire)
    from build123d import Axis, revolve
    return revolve(face, axis=Axis.Z, revolution_arc=360.0)
