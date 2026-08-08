# -*- coding: utf-8 -*-
"""WindyCity フィット候補3案の FreeCAD 確認モデル生成。

candidate_{1_faithful,2_playing,3_acoustic}.json（SaxSketch テンプレート形式）を
読み、アプリの profiles.py を直読した app-exact ソリッド（cad/freecad/
variant_c_sections.py と同方式: 実断面ロフト）を作り、整列済みの実物メッシュ
reference_aligned.stl を同一座標系に重ねた FCStd を 1 案 = 1 ファイルで保存する。

FreeCAD で開くと「候補ソリッド + 実物メッシュ」が重なって表示され、乖離を
直接目視できる（メッシュはツリーで非表示にもできる。半透明化は表示プロパティ
の Transparency を上げる）。

実行（ヘッドレス生成）:
  "C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" cad/windycity/build_candidates.py
"""
import importlib.util
import json
import os
import sys

import FreeCAD
import Mesh
import Part

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))

CANDIDATES = [
    ("candidate_1_faithful", "Mouthpiece_WC1_faithful"),
    ("candidate_2_playing", "Mouthpiece_WC2_playing"),
    ("candidate_3_acoustic", "Mouthpiece_WC3_acoustic"),
]
REF_STL = os.path.join(_HERE, "reference_aligned.stl")


def _load_profiles():
    """アプリの profiles.py を package __init__（build123d 依存）を通さず直接ロード。"""
    path = os.path.join(_REPO_ROOT, "saxsketch", "instruments", "saxophone",
                        "components", "profiles.py")
    spec = importlib.util.spec_from_file_location("mp_profiles_wc", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load_profiles()


# ------------------------------------------------- 形状要素（variant_c_sections と同方式）

def _revolved_body(p):
    length = p["overall_length"]
    n = 48
    zs = [length * i / (n - 1) for i in range(n)]
    verts = [FreeCAD.Vector(P.outer_radius(p, z), 0.0, z) for z in zs]
    verts += [FreeCAD.Vector(0.0, 0.0, zs[-1]), FreeCAD.Vector(0.0, 0.0, zs[0])]
    verts.append(verts[0])
    face = Part.Face(Part.makePolygon(verts))
    return face.revolve(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360.0)


def _zy_prism(p, zy_pts, half_width):
    verts = [FreeCAD.Vector(-half_width, y, z) for (z, y) in zy_pts]
    verts.append(verts[0])
    face = Part.Face(Part.makePolygon(verts))
    return face.extrude(FreeCAD.Vector(2.0 * half_width, 0.0, 0.0))


def _beak_cut(p):
    length = p["overall_length"]
    n = 40
    pts = [(-3.0 + (length + 6.0) * i / (n - 1)) for i in range(n)]
    pts = [(z, P.beak_y(p, z)) for z in pts]
    pts += [(length + 3.0, 80.0), (-3.0, 80.0)]
    return _zy_prism(p, pts, half_width=p["body_dia"])


def _facing_cut(p):
    z_end = P.table_cut_end_z(p)
    n = 48
    pts = [(-3.0 + (z_end + 3.0) * i / (n - 1)) for i in range(n)]
    pts = [(z, P.cut_top_y(p, z)) for z in pts]
    pts += [(z_end, -80.0), (-3.0, -80.0)]
    return _zy_prism(p, pts, half_width=p["body_dia"])


def _cavity(p):
    wires = []
    for s in P.cavity_sections(p):
        z = s["z"]
        verts = [FreeCAD.Vector(x, y, z) for (x, y) in s["pts"]]
        verts.append(verts[0])
        wires.append(Part.makePolygon(verts))
    return Part.makeLoft(wires, True, True)  # solid=True, ruled=True


def _bore(p):
    zb = P.bore_start_z(p)
    r = P.bore_radius(p)
    h = p["overall_length"] - zb + 1.5
    return Part.makeCylinder(r, h, FreeCAD.Vector(0, 0, zb), FreeCAD.Vector(0, 0, 1))


def build_shape(p):
    body = _revolved_body(p)
    shape = body.cut(_beak_cut(p))
    shape = shape.cut(_facing_cut(p))
    shape = shape.cut(_cavity(p))
    shape = shape.cut(_bore(p))
    return shape.removeSplitter()


def main():
    for stem, obj_name in CANDIDATES:
        path = os.path.join(_HERE, stem + ".json")
        with open(path, encoding="utf-8") as f:
            tpl = json.load(f)
        p = tpl["mouthpiece"]

        doc = FreeCAD.newDocument("wc_" + stem)
        shape = build_shape(p)
        obj = doc.addObject("Part::Feature", obj_name)
        obj.Shape = shape

        # 実物メッシュを同一座標系で重ねる（フィットスクリプトが整列済み）
        if os.path.exists(REF_STL):
            Mesh.insert(REF_STL, doc.Name)
            for o in doc.Objects:
                if o.TypeId.startswith("Mesh::"):
                    o.Label = "WindyCity_Reference"
        else:
            print("!! reference_aligned.stl が見つかりません（重ね合わせなし）")

        doc.recompute()
        out = os.path.join(_HERE, stem + ".FCStd")
        doc.saveAs(out)

        bb = shape.BoundBox
        print("== %s (%s) ==" % (stem, tpl.get("label", "")))
        print("valid=%s solids=%d volume=%.1f mm^3" %
              (shape.isValid(), len(shape.Solids), shape.Volume))
        print("bbox Z=%.2f (overall=%.2f) X=%.2f Y=%.2f" %
              (bb.ZLength, p["overall_length"], bb.XLength, bb.YLength))
        print("cavity_volume_cc(app)=%.3f" % P.cavity_volume_cc(p)["total_cc"])
        print("saved:", out)
        FreeCAD.closeDocument(doc.Name)


# freecadcmd はスクリプト直実行時に __name__ を "__main__" にしないため無条件実行
main()
