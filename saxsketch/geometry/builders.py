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


def loft_sections(sections: list[dict]) -> Solid:
    """任意断面のロフト。各要素 {"z": float, "pts": [(x, y), …]}（z 昇順）。

    `loft_stations` のスーパー楕円では作れない形状（底面が厳密に平坦なリード等）
    のための汎用版。堅牢性の理由は `superellipse_wire` と同じで、多角形ワイヤ＋
    ルールドロフトに統一している。
    """
    wires = []
    for s in sections:
        pts = [Vector(x, y, s["z"]) for (x, y) in s["pts"]]
        wires.append(Wire.make_polygon(pts, close=True))
    solid = Solid.make_loft(wires, ruled=True)
    if solid.volume < 0:  # ThruSections が裏返しシェルを返すことがある
        solid = Solid(solid.wrapped.Reversed())
    return solid


def flat_bottom_rect_pts(w: float, h: float, y0: float = 0.0,
                         corner_r: float = 0.0,
                         samples: int = 8) -> list[tuple[float, float]]:
    """底面が y=y0 で厳密に平坦な角丸長方形の点列（反時計回り）。

    リードのテーブル面はマウスピースへ密着させる必要があり、スーパー楕円では
    わずかに膨らんで密着しない。角丸は上側の2隅にのみ入れる（下側は平坦を保つ）。

    点数は `corner_r` によらず常に `2*samples + 4` 個で一定にする。`loft_sections`
    のルールドロフトは頂点対応ではなくパラメータ対応で面を張るため、断面ごとに
    点数が変わると角の位置が辺の途中に写像されて面がねじれる。角丸が実質ゼロの
    断面でも微小半径を残して点を並べる（形状差は 0.01mm 未満＝造形精度以下）。
    """
    hw = w / 2.0
    r = min(corner_r, hw - 1e-6, h - 1e-6)
    r = max(r, min(h, w) * 1e-3)   # 点が重ならない下限。角は実質直角のまま
    top = y0 + h
    pts: list[tuple[float, float]] = [(-hw, y0), (hw, y0)]  # 底辺（平坦）
    pts.append((hw, top - r))
    for i in range(1, samples + 1):  # 右上の角丸（終点 (hw-r, top) まで含む）
        th = (math.pi / 2.0) * i / samples
        pts.append((hw - r + r * math.cos(th), top - r + r * math.sin(th)))
    pts.append((-hw + r, top))
    for i in range(1, samples):  # 左上の角丸
        th = (math.pi / 2.0) * i / samples
        pts.append((-hw + r - r * math.sin(th), top - r + r * math.cos(th)))
    pts.append((-hw, top - r))
    return pts


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
