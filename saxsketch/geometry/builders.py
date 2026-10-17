"""build123d 共通ビルダー（全楽器・全コンポーネントで再利用）。

多角形＋ルールド（`superellipse_wire` / `loft_sections` / `revolve_profile`）と、
1面ずつのプリミティブ（`revolve_spline_profile` / `loft_spline_sections` /
`yz_profile_cut_solid_curved` / `extrude_arc_prism`）の**2系統**がある。

前者が既定。プレビュー・シミュレーション・STL はこちらで作る。後者は STEP 出力
専用で、FreeCAD で面を選んでフィレットを掛けられるようにするためだけに使う。

以前ここには「スプラインワイヤはブーリアン破綻を招く」と書いてあったが、実測すると
壊れるのは**多エッジのスプラインワイヤ**と `ruled=False` であって、スプライン自体
ではなかった。テナー実測（OCCT）:

  - 1断面 = 1本の周期スプライン + `ruled=True` → 面数 2547→90、単一ソリッド、
    形状は多角形版と同一（ルールドなので断面間の補間が変わらない）。
  - `ruled=False` にすると断面間でオーバーシュートして**気柱が 2〜3% 増え**、
    さらにボア円筒と接線接触して 1回のカットに 92 秒＋0.5mm² 未満のスリバー面が 29 枚。
  - 回転体の母線を1本のスプラインで通すと、C1 の折れ目（ティップ面取りの端）で
    0.58mm オーバーシュートする。区間ごとに分けて張れば消える。

プリミティブ系はブーリアンが 3〜6 倍遅い（4.6s → 15〜28s）。これが STEP 出力
専用にとどめている理由。
"""
from __future__ import annotations

import math

from build123d import Edge, Face, Solid, Vector, Wire, extrude


def superellipse_wire(z: float, yc: float, h: float, w: float, n: float,
                      samples: int = 96) -> Wire:
    """z=const 平面上のスーパー楕円ワイヤ（多角形近似）。

    96点で弦誤差 ≒ 0.01mm 未満（3Dプリント精度未満）。
    多角形＋ルールドロフトを既定にするのは堅牢性と速度のため（下の注記を参照）。
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


def loft_3d_rings(rings: list[list[tuple[float, float, float]]]) -> Solid:
    """任意の3D位置・向きに置かれたリング列をロフトした水密ソリッド。

    各リングは同数の3D点からなる多角形。`revolve_profile` では作れない
    「曲がった管（グースネック等）」用。点数を全リングで一定に保ち、多角形ワイヤ＋
    ルールドロフトで面を張る（`loft_sections`/`superellipse_wire` と同じ堅牢性方針）。
    """
    wires = [Wire.make_polygon([Vector(x, y, z) for (x, y, z) in ring], close=True)
             for ring in rings]
    solid = Solid.make_loft(wires, ruled=True)
    if solid.volume < 0:  # ThruSections が裏返しシェルを返すことがある
        solid = Solid(solid.wrapped.Reversed())
    return solid


# ------------------------------------------------------------ プリミティブ系（STEP 出力用）
#
# ここから下は「1つの面を1枚として張る」ための版。上の多角形系と**同じ形**を作るが、
# FreeCAD で面を選択してフィレット/面取り/ポケットを掛けられるようにする。
# 使うのは STEP エクスポート経路だけ（理由はモジュール冒頭の注記）。


def _curve_edge(pts: list[Vector]) -> Edge:
    """2点なら直線、3点以上ならスプラインの 1 エッジ。"""
    if len(pts) == 2:
        return Edge.make_line(pts[0], pts[1])
    return Edge.make_spline(pts)


def revolve_spline_profile(segments: list[list[tuple[float, float]]]) -> Solid:
    """(z, r) の**区間列**を Z 軸回りに回した回転体。区間ごとに母線1本＝面1枚。

    `revolve_profile` は母線が多角形なので区間の数だけ円錐面ができる
    （テナーで 248 枚）。ここでは区間ごとに 1 本のスプライン母線を張る。

    **区間に分ける理由**: 母線の C1 の折れ目で切るため。全体を 1 本のスプラインで
    内挿すると折れ目でうねり、実測でティップ面取りの端に 0.58mm のオーバーシュートが
    出て胴の体積が 1.3% 痩せた。母線は pchip（単調保存）で作ってあるのに、それを
    C2 のスプラインで通し直すのが原因なので、刻みを細かくしても直らない
    （0.05mm 刻みでも 0.60mm のまま）。折れ目はマウスピースでは3箇所 ——
    ティップ面取りの端・胴プロファイルから肩プロファイルへ移る踵・肩からシャンク平行部。

    各区間は (z, r) の点列で、隣の区間と端点を共有していること。
    """
    edges = [_curve_edge([Vector(r, 0.0, z) for (z, r) in seg]) for seg in segments]
    z_lo, r_lo = segments[0][0]
    z_hi, r_hi = segments[-1][-1]
    edges += [
        Edge.make_line(Vector(r_hi, 0.0, z_hi), Vector(0.0, 0.0, z_hi)),
        Edge.make_line(Vector(0.0, 0.0, z_hi), Vector(0.0, 0.0, z_lo)),
        Edge.make_line(Vector(0.0, 0.0, z_lo), Vector(r_lo, 0.0, z_lo)),
    ]
    from build123d import Axis, revolve
    return revolve(Face(Wire(edges)), axis=Axis.Z, revolution_arc=360.0)


def loft_spline_sections(sections: list[dict], ruled: bool = True) -> Solid:
    """任意断面のロフト。各断面を 1 本の**周期スプライン**にする。

    `loft_sections` と同じ入力（[{"z", "pts"}]）を取り、同じ形を作る。断面の
    ワイヤが 72 エッジ → 1 エッジになるので、ロフト面が断面間 72 枚 → 1 枚になる。
    断面間の補間は `ruled=True` のままなので、`cavity_volume_cc` の台形積分
    （＝ルールド表現）とも引き続き一致する。

    `ruled=False` を既定にしない理由は形が変わるから。実測では断面間で
    オーバーシュートして**気柱が 2〜3% 増え**、さらにロフト末端がボア円筒と
    接線接触して 1 回のカットに 92 秒かかり、0.5mm² 未満のスリバー面を 29 枚吐いた。
    """
    wires = [Wire([Edge.make_spline([Vector(x, y, s["z"]) for (x, y) in s["pts"]],
                                    periodic=True)])
             for s in sections]
    solid = Solid.make_loft(wires, ruled=ruled)
    if solid.volume < 0:  # ThruSections が裏返しシェルを返すことがある
        solid = Solid(solid.wrapped.Reversed())
    return solid


def yz_profile_cut_solid_curved(segments_yz: list[list[tuple[float, float]]],
                                half_width: float) -> Solid:
    """YZ平面の閉ループ（直線とスプラインの混在）を X 方向 ±half_width に押し出す。

    `yz_profile_cut_solid` の曲線対応版。テーブル＝PLANE 1面、フェイシング＝
    BSPLINE 1面になる。

    フェイシングを**円筒面にはしない**: `facing_rise` 単体は真円だが、テーブルが
    軸に対して傾いているぶん `cut_top_y` は Y 方向にせん断されていて、厳密には
    楕円弧になる（円弧で最小二乗フィットすると 0.0024mm 残る）。リードが密着する
    面なので近似しない。スプラインなら 1 面のまま厳密に通せる。

    各区間は (z, y) の点列。2点なら直線、3点以上ならスプライン。最後の区間の終点は
    最初の区間の始点と一致していること（閉ループ）。
    """
    edges = [_curve_edge([Vector(0.0, y, z) for (z, y) in seg]) for seg in segments_yz]
    return extrude(Face(Wire(edges)), amount=half_width, both=True)


def extrude_arc_prism(arc3: list[tuple[float, float, float]], cap_y: float,
                      direction: tuple[float, float, float],
                      length: float) -> Solid:
    """円弧断面（3点）を y=cap_y の天井で閉じ、`direction` へ斜めに押し出す。

    ビークの直線ランプ用。稜線が z の一次式で横断面の曲率半径が一定な区間では、
    ビーク面は「円弧を直線に沿って平行移動した面」そのものなので、この押出で
    **厳密に一致する**（断面ロフトのような近似ではない）。

    arc3: (始点, 中点, 終点) の (x, y, z)。3点とも同じ z 平面にあること。
    cap_y: 断面を閉じる天井の Y（切除ソリッドが胴の上を確実に覆う高さ）。
    direction: 押出方向（正規化不要）。length: その方向への距離。
    """
    d = Vector(*direction)
    n = d.length
    return extrude(Face(_arc_cap_wire(arc3, cap_y)), amount=length,
                   dir=(d.X / n, d.Y / n, d.Z / n))


def _arc_cap_wire(arc3: list[tuple[float, float, float]], cap_y: float) -> Wire:
    p0, p1, p2 = (Vector(*p) for p in arc3)
    top_a, top_b = Vector(p2.X, cap_y, p2.Z), Vector(p0.X, cap_y, p0.Z)
    return Wire([
        Edge.make_three_point_arc(p0, p1, p2),
        Edge.make_line(p2, top_a),
        Edge.make_line(top_a, top_b),
        Edge.make_line(top_b, p0),
    ])


def loft_arc_sections(arcs: list[list[tuple[float, float, float]]], cap_y: float,
                      ruled: bool = True) -> Solid:
    """円弧断面（3点）を y=cap_y で閉じた断面列のロフト。

    `extrude_arc_prism` では作れない区間（断面の曲率半径が z で変わる所）用。
    下辺が円弧のままなので、多角形ロフトのように断面あたり 33 枚の面にならず
    断面間で 1 枚になる。

    `ruled=True` を既定にするのは、多角形版（`loft_sections` +
    `profiles.beak_cut_section`）と**同じ面**を張るため。断面 z を揃えておけば
    形が 1mm も動かない。
    """
    solid = Solid.make_loft([_arc_cap_wire(a, cap_y) for a in arcs], ruled=ruled)
    if solid.volume < 0:  # ThruSections が裏返しシェルを返すことがある
        solid = Solid(solid.wrapped.Reversed())
    return solid
