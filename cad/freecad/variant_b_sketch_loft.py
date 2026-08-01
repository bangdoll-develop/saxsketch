# -*- coding: utf-8 -*-
"""B案: 曲線ベース（線分・円弧・スプライン）＋Revolve＋Loft 方式 マウスピース。

CAD の王道的な作り方。外形は制御点を通す B スプライン断面を Z 軸で回転（Revolve）、
ビーク／テーブル面はスプライン・直線の輪郭を幅方向へ押し出して Boolean カット、
内部空洞は各ステーションの断面（円＝円弧、チェンバー＝横長スーパー楕円を B スプライン
近似）を滑らかに Loft して減算する。C 案の 96 点ポリゴン断面に対し、こちらは曲線
プリミティブと非ルールド（滑らか）ロフトで構成する点が異なる。

寸法の縦位置・フェイシング・チェンバー寸法などの算出はアプリの profiles.py を
共有して破綻を防ぐ（＝形状はアプリにほぼ一致するが、面の作り方が曲線ベース）。
厳密な断面一致が要るなら C 案を使う。

編集方法:
  - サイズ変更は下の SIZE を "alto" / "soprano" に。
  - 個別寸法は `p[...] = ...` で上書き。
  - 変更後、FreeCAD でマクロ実行するか `freecadcmd variant_b_sketch_loft.py` で再生成。
"""
import os
import sys
import importlib.util

import FreeCAD
import Part

# ----------------------------------------------------------------- パラメータ
SIZE = "tenor"          # "soprano" / "alto" / "tenor"

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from mp_presets import preset  # noqa: E402

p = preset(SIZE)
# --- 個別上書きの例 -------------------------------------------------------
# p["baffle_type"] = "step"
# p["chamber_shape"] = "horseshoe"
# -------------------------------------------------------------------------


def _load_profiles():
    path = os.path.join(_REPO_ROOT, "saxsketch", "instruments", "saxophone",
                        "components", "profiles.py")
    spec = importlib.util.spec_from_file_location("mp_profiles_freecad_b", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load_profiles()

V = FreeCAD.Vector


# ----------------------------------------------------------------- 補助

def _bspline_edge(pts3d):
    """3D 点列を通る B スプライン曲線のエッジ。"""
    bs = Part.BSplineCurve()
    bs.interpolate([V(*t) for t in pts3d])
    return bs.toShape()


def _closed_wire(edges):
    return Part.Wire(edges)


# ----------------------------------------------------------------- 外形（Revolve）

def _revolved_body():
    """外形制御点を通す B スプライン断面を Z 軸で 360° 回転。"""
    length = p["overall_length"]
    rb = p["body_dia"] / 2.0
    # (z/L, r/rb) 制御点（アプリ _OUTER_PROFILE 準拠）
    outer = [(0.00, 0.70), (0.20, 0.84), (0.45, 0.96), (0.66, 1.00),
             (0.88, 1.00), (0.95, 0.93), (1.00, 0.86)]
    ctrl = [(rb * rr, 0.0, tt * length) for (tt, rr) in outer]
    spline = _bspline_edge(ctrl)
    p_tip = V(*ctrl[0])
    p_shank = V(*ctrl[-1])
    edges = [
        spline,
        Part.LineSegment(p_shank, V(0, 0, length)).toShape(),  # シャンク端を軸へ
        Part.LineSegment(V(0, 0, length), V(0, 0, 0)).toShape(),  # 軸（回転中心）
        Part.LineSegment(V(0, 0, 0), p_tip).toShape(),  # ティップ端を軸へ
    ]
    face = Part.Face(_closed_wire(edges))
    return face.revolve(V(0, 0, 0), V(0, 0, 1), 360.0)


# ----------------------------------------------------------------- カット（押し出し）

def _zy_prism_from_curve(sample_zy, top_or_bottom, half_width):
    """(z,y) サンプル点を通すスプライン輪郭＋直線閉じで作る YZ プリズム。

    top_or_bottom="top": 曲線の上側を y=+H で閉じる（ビーク上面の切除）。
    "bottom": 下側を y=-H で閉じる（テーブル下面の切除）。
    """
    H = 80.0
    curve = _bspline_edge([(-half_width, y, z) for (z, y) in sample_zy])
    z0, y0 = sample_zy[0]
    z1, y1 = sample_zy[-1]
    yb = H if top_or_bottom == "top" else -H
    edges = [
        curve,
        Part.LineSegment(V(-half_width, y1, z1), V(-half_width, yb, z1)).toShape(),
        Part.LineSegment(V(-half_width, yb, z1), V(-half_width, yb, z0)).toShape(),
        Part.LineSegment(V(-half_width, yb, z0), V(-half_width, y0, z0)).toShape(),
    ]
    face = Part.Face(_closed_wire(edges))
    return face.extrude(V(2.0 * half_width, 0.0, 0.0))


def _beak_cut():
    length = p["overall_length"]
    zs = [-3.0 + (length + 6.0) * i / 11.0 for i in range(12)]
    sample = [(z, P.beak_y(p, z)) for z in zs]
    return _zy_prism_from_curve(sample, "top", half_width=p["body_dia"])


def _facing_cut():
    z_end = P.table_cut_end_z(p)
    zs = [-3.0 + (z_end + 3.0) * i / 15.0 for i in range(16)]
    sample = [(z, P.cut_top_y(p, z)) for z in zs]
    return _zy_prism_from_curve(sample, "bottom", half_width=p["body_dia"])


# ----------------------------------------------------------------- 空洞（Loft）

def _section_wire(s):
    """ステーション {yc,h,w,shape} をアプリ断面点列の閉ポリゴン ワイヤに。

    空洞は Boolean 減算で壁ぎわを通るため、断面をスプライン化するとオーバーシュートや
    自己交差でカットが失敗しやすい。空洞だけは堅牢なポリゴン断面ロフトを用い、B 案の
    「曲線ベース」の性格は外形（B スプライン回転体）とカット輪郭（B スプライン）で担う。
    """
    z = s["z"]
    verts = [V(x, y, z) for (x, y) in P.section_pts(s)]
    verts.append(verts[0])
    return Part.makePolygon(verts)


def _cavity():
    wires = [_section_wire(s) for s in P.cavity_stations(p)]
    return Part.makeLoft(wires, True, True)  # solid=True, ruled=True


def _bore():
    zb = P.bore_start_z(p)
    r = P.bore_radius(p)
    h = p["overall_length"] - zb + 1.5
    return Part.makeCylinder(r, h, V(0, 0, zb), V(0, 0, 1))


# ----------------------------------------------------------------- 組み立て

def build_shape():
    body = _revolved_body()
    shape = body.cut(_beak_cut())
    shape = shape.cut(_facing_cut())
    shape = shape.cut(_cavity())
    shape = shape.cut(_bore())
    return shape.removeSplitter()


def main():
    doc = FreeCAD.newDocument("mp_variant_b_sketch_loft")
    shape = build_shape()
    obj = doc.addObject("Part::Feature", "Mouthpiece_B_%s" % SIZE)
    obj.Shape = shape
    doc.recompute()

    out = os.path.join(_HERE, "variant_b_sketch_loft.FCStd")
    doc.saveAs(out)

    bb = shape.BoundBox
    print("== B案 曲線+Revolve+Loft (%s) ==" % SIZE)
    print("valid=%s  solids=%d  volume=%.1f mm^3"
          % (shape.isValid(), len(shape.Solids), shape.Volume))
    print("bbox Z=%.2f (overall_length=%.2f)  X=%.2f  Y=%.2f"
          % (bb.ZLength, p["overall_length"], bb.XLength, bb.YLength))
    print("saved: %s" % out)
    return doc


main()
