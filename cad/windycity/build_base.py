# -*- coding: utf-8 -*-
"""新ベース形状を FreeCAD ソリッド化し、実物メッシュを重ねた FCStd を出力する。

SaxSketch 本体の `profiles.py`（純数学モジュール）を importlib で直読し、
アプリと同一の構成式で FreeCAD ソリッドを組む（package __init__ は build123d を
引くので通さない）。`reference_aligned.stl` を同じ座標系で重ねるので、FreeCAD で
開けば新ベースと実物のズレをそのまま目視できる。

実行:
  "C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" cad/windycity/build_base.py
"""
import importlib.util
import json
import os
import sys

import FreeCAD
import Mesh
import Part

SIZES = ["tenor", "alto", "soprano"]      # tenor 以外は形が破綻しないことの確認用

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(_HERE, "..", ".."))
REF_STL = os.path.join(_HERE, "reference_aligned.stl")


def _load_profiles():
    path = os.path.join(_REPO, "saxsketch", "instruments", "saxophone",
                        "components", "profiles.py")
    spec = importlib.util.spec_from_file_location("mp_profiles_base", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load_profiles()
V = FreeCAD.Vector


def _revolved_body(p):
    """胴（ボア軸まわりの真円回転体）。ノーズと肩でステーションを詰める。"""
    length = p["overall_length"]
    heel = P.heel_z(p)
    zs = sorted({*(heel * (i / 40.0) ** 1.6 for i in range(41)),
                 *(heel + (length - heel) * i / 24.0 for i in range(25))})
    verts = [V(P.outer_radius(p, z), 0.0, z) for z in zs]
    verts += [V(0.0, 0.0, zs[-1]), V(0.0, 0.0, zs[0])]
    verts.append(verts[0])
    face = Part.Face(Part.makePolygon(verts))
    return face.revolve(V(0, 0, 0), V(0, 0, 1), 360.0)


def _beak_cut(p):
    """ビーク切除。稜線は直線だが横断面が円弧なので断面ロフトで作る。"""
    heel = P.heel_z(p)
    n = 44
    wires = []
    for i in range(n):
        z = -2.0 + (heel + 4.0) * i / (n - 1)
        pts = P.beak_cut_section(p, z, half_width=p["body_dia"])
        verts = [V(x, y, z) for (x, y) in pts]
        verts.append(verts[0])
        wires.append(Part.makePolygon(verts))
    return Part.makeLoft(wires, True, True)


def _facing_cut(p):
    """テーブル/フェイシングカット。傾斜平面なので全長ぶん伸ばしても余計に切らない。"""
    length = p["overall_length"]
    n = 56
    pts = [(-3.0 + (length + 6.0) * i / (n - 1)) for i in range(n)]
    pts = [(z, P.cut_top_y(p, z)) for z in pts]
    pts += [(length + 3.0, -80.0), (-3.0, -80.0)]
    hw = p["body_dia"]
    verts = [V(-hw, y, z) for (z, y) in pts]
    verts.append(verts[0])
    face = Part.Face(Part.makePolygon(verts))
    return face.extrude(V(2.0 * hw, 0.0, 0.0))


def _cavity(p):
    wires = []
    for s in P.cavity_sections(p):
        verts = [V(x, y, s["z"]) for (x, y) in s["pts"]]
        verts.append(verts[0])
        wires.append(Part.makePolygon(verts))
    return Part.makeLoft(wires, True, True)


def _bore(p):
    zb = P.bore_start_z(p)
    r = P.bore_radius(p)
    return Part.makeCylinder(r, p["overall_length"] - zb + 1.5,
                             V(0, 0, zb), V(0, 0, 1))


def build_shape(p):
    shape = _revolved_body(p)
    shape = shape.cut(_beak_cut(p))
    shape = shape.cut(_facing_cut(p))
    shape = shape.cut(_cavity(p))
    shape = shape.cut(_bore(p))
    return shape.removeSplitter()


def main():
    ok = True
    for size in SIZES:
        path = os.path.join(_REPO, "saxsketch", "instruments", "saxophone",
                            "templates", size + ".json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)["mouthpiece"]

        doc = FreeCAD.newDocument("mp_base_" + size)
        shape = build_shape(p)
        obj = doc.addObject("Part::Feature", "Mouthpiece_base_%s" % size)
        obj.Shape = shape
        if size == "tenor" and os.path.exists(REF_STL):
            Mesh.insert(REF_STL, doc.Name)
            for o in doc.Objects:
                if o.TypeId.startswith("Mesh::"):
                    o.Label = "WindyCity_Reference"
        doc.recompute()
        out = os.path.join(_HERE, "base_%s.FCStd" % size)
        doc.saveAs(out)

        # Shape.BoundBox は曲面の制御点から取る緩い外接箱で実形状より大きく出るため、
        # 実寸はテッセレーション後の頂点から測る。
        vs, _ = shape.tessellate(0.02)
        xs = [v.x for v in vs]
        ys = [v.y for v in vs]
        zs_t = [v.z for v in vs]
        good = shape.isValid() and len(shape.Solids) == 1
        ok = ok and good
        print("== %s ==" % size)
        print("valid=%s solids=%d volume=%.1f mm^3 %s"
              % (shape.isValid(), len(shape.Solids), shape.Volume,
                 "" if good else "*** NG"))
        print("bbox X=%.2f Y=%.2f Z=%.2f (overall_length=%.2f)"
              % (max(xs) - min(xs), max(ys) - min(ys),
                 max(zs_t) - min(zs_t), p["overall_length"]))
        print("cavity_volume_cc=%.3f" % P.cavity_volume_cc(p)["total_cc"])
        print("saved:", out)
        FreeCAD.closeDocument(doc.Name)
    print("ALL_PASS" if ok else "SOME_FAIL")


# freecadcmd はスクリプト直実行時に __name__ を "__main__" にしないため無条件実行
main()
