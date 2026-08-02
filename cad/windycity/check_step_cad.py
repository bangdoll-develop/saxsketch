# -*- coding: utf-8 -*-
"""SaxSketch が出した STEP を FreeCAD で読み、面選択とフィレットが通るか確かめる。

Stage C-2 の目的は「FreeCAD で外周面を選んでフィレット/面取り/ポケットを掛けられる
ようにする」ことなので、確認は**実際にユーザーへ渡る成果物（STEP）**で行う。
`build_base.py` の Part API を書き換えて同じ形を二重実装すると、出荷される経路とは
別のコードを検証することになるのでそれはしない。

前提: `verify_base.py` が `base_tenor_cad.step` を書き出していること。

実行:
  "C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" cad/windycity/check_step_cad.py
"""
import collections
import os

import FreeCAD
import Part

_HERE = os.path.dirname(os.path.abspath(__file__))
STEP = os.path.join(_HERE, "base_tenor_cad.step")

#: 掛けてみるフィレット半径 [mm]。0.5 ではなく 0.2 なのは、C-1c 以降ティップの
#: 前面が 0.25mm しかないため（0.5 では確実に落ちる）。
FILLET_R = 0.2


def _kind(face) -> str:
    """面の種類の短い名前（GeomSurfaceOfRevolution → Revolution）。"""
    return face.Surface.TypeId.split("::")[-1].replace("Geom", "") \
        .replace("SurfaceOf", "").replace("Surface", "")


def _adjacent(shape, edge) -> list:
    """そのエッジに接している面。頂点距離で拾う（TopoShape の逆引きが無いため）。"""
    out = []
    mid = edge.valueAt(0.5 * (edge.FirstParameter + edge.LastParameter))
    for f in shape.Faces:
        if f.distToShape(Part.Vertex(mid))[0] < 1e-6:
            out.append(f)
    return out[:2] if len(out) >= 2 else out


def main():
    if not os.path.exists(STEP):
        print("missing:", STEP)
        print("先に verify_base.py を実行してください")
        print("SOME_FAIL")
        return

    shape = Part.Shape()
    shape.read(STEP)
    faces, edges = shape.Faces, shape.Edges
    kinds = collections.Counter(_kind(f) for f in faces)
    tiny = [e for e in edges if e.Length < 0.05]
    ok = shape.isValid() and len(shape.Solids) == 1

    print("== STEP round trip ==")
    print("valid=%s solids=%d faces=%d edges=%d" % (
        shape.isValid(), len(shape.Solids), len(faces), len(edges)))
    print("volume=%.1f mm^3" % shape.Volume)
    bb = shape.BoundBox
    print("bbox X=%.2f Y=%.2f Z=%.2f" % (bb.XLength, bb.YLength, bb.ZLength))
    print("face kinds:", dict(kinds))
    print("edges shorter than 0.05mm: %d" % len(tiny))
    ok = ok and len(faces) < 100 and len(tiny) < 20

    # フィレットは1本ずつ試す。全エッジへ一括で掛けるのは実運用と違う（ユーザーは
    # 掛けたい所を選ぶ）し、1本でも失敗すると全体が落ちて「どれが不可か」が分からない。
    # 結果は**接している面の種類の組**でまとめる。どの稜線にフィレットを掛けてよいかを
    # 手動編集ワークフローの文書へ書き写すのが目的。
    cands = [e for e in edges if e.Length > 2.0]
    by_pair = {}
    good = 0
    for e in cands:
        pair = " + ".join(sorted(_kind(f) for f in _adjacent(shape, e)))
        try:
            f = shape.makeFillet(FILLET_R, [e])
            hit = f.isValid() and len(f.Solids) == 1
        except Exception:                              # noqa: BLE001
            hit = False
        good += 1 if hit else 0
        o, n = by_pair.setdefault(pair, [0, 0])
        by_pair[pair] = [o + (1 if hit else 0), n + (0 if hit else 1)]

    print("== fillet R%.2f (one edge at a time) ==" % FILLET_R)
    print("%d of %d edges longer than 2mm succeeded" % (good, len(cands)))
    print("%-46s %4s %4s" % ("adjacent surfaces", "ok", "ng"))
    for pair in sorted(by_pair):
        o, n = by_pair[pair]
        print("%-46s %4d %4d" % (pair, o, n))
    ok = ok and good > 0

    print("ALL_PASS" if ok else "SOME_FAIL")


# freecadcmd はスクリプト直実行時に __name__ を "__main__" にしないため無条件実行
main()
