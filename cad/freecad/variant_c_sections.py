# -*- coding: utf-8 -*-
"""C案: 実断面ロフト方式 マウスピース（アプリ幾何と一致・最も実物忠実）。

SaxSketch アプリ本体の純数学モジュール profiles.py をそのまま読み込み、
アプリと同一の外形プロファイル・ビーク/テーブルのカット曲線・96 点断面の
内部空洞を FreeCAD ソリッドとして再構築する。生成される形状はアプリの
build123d 版と幾何一致し、内容積もカタログ値（tenor で約 19.637cc）に一致する。

構成要素:
  1. 外形    : outer_radius(z) の閉プロファイルを Z 軸まわりに 360° 回転（Revolve）
  2. ビーク  : beak_y(z) 上側を YZ プリズムで Boolean カット
  3. テーブル: cut_top_y(z) 下側を YZ プリズムで Boolean カット（フェイシング＋窓開口）
  4. 空洞    : cavity_sections(p) の 96 点ポリゴン 13 枚を Loft して Boolean 減算
  5. ボア    : シャンク端からの円柱を Boolean 減算

編集方法:
  - サイズ変更は下の SIZE を "alto" / "soprano" に。
  - 個別寸法は `p[...] = ...` 行のコメントを外して上書き（例: バッフルを step に、
    チェンバーを horseshoe に、など。実形状がそのまま反映される）。
  - 変更後、FreeCAD で本ファイルをマクロ実行するか、
    `freecadcmd variant_c_sections.py` で FCStd を再生成する。

実行（ヘッドレス再生成）:
  "C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" variant_c_sections.py
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
# --- 個別上書きの例（必要ならコメントを外す）-----------------------------
# p["baffle_type"] = "step"          # straight / rollover / step / curve
# p["chamber_shape"] = "horseshoe"   # round / square / horseshoe / flat_sidewall
# p["tip_opening"] = 2.6
# -------------------------------------------------------------------------


def _load_profiles():
    """アプリの profiles.py を package __init__（build123d 依存）を通さず直接ロード。"""
    path = os.path.join(_REPO_ROOT, "saxsketch", "instruments", "saxophone",
                        "components", "profiles.py")
    spec = importlib.util.spec_from_file_location("mp_profiles_freecad", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load_profiles()


# ----------------------------------------------------------------- 形状要素

def _revolved_body():
    """outer_radius(z) の閉プロファイルを Z 軸まわりに回転した外形ソリッド。"""
    length = p["overall_length"]
    n = 48
    zs = [length * i / (n - 1) for i in range(n)]
    verts = [FreeCAD.Vector(P.outer_radius(p, z), 0.0, z) for z in zs]
    # 軸（x=0）側を閉じて回転用の閉プロファイルにする
    verts += [FreeCAD.Vector(0.0, 0.0, zs[-1]), FreeCAD.Vector(0.0, 0.0, zs[0])]
    verts.append(verts[0])
    face = Part.Face(Part.makePolygon(verts))
    return face.revolve(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360.0)


def _zy_prism(zy_pts, half_width):
    """(z, y) の閉ポリゴンを X 方向へ ±half_width 押し出したプリズム。

    アプリの builders.yz_profile_cut_solid と同じ「YZ 断面を幅方向に押し出して
    切り取る」方式。"""
    verts = [FreeCAD.Vector(-half_width, y, z) for (z, y) in zy_pts]
    verts.append(verts[0])
    face = Part.Face(Part.makePolygon(verts))
    return face.extrude(FreeCAD.Vector(2.0 * half_width, 0.0, 0.0))


def _beak_cut():
    length = p["overall_length"]
    n = 40
    pts = [(-3.0 + (length + 6.0) * i / (n - 1), 0.0) for i in range(n)]
    pts = [(z, P.beak_y(p, z)) for z, _ in pts]
    pts += [(length + 3.0, 80.0), (-3.0, 80.0)]
    return _zy_prism(pts, half_width=p["body_dia"])


def _facing_cut():
    z_end = P.table_cut_end_z(p)
    n = 48
    pts = [(-3.0 + (z_end + 3.0) * i / (n - 1), 0.0) for i in range(n)]
    pts = [(z, P.cut_top_y(p, z)) for z, _ in pts]
    pts += [(z_end, -80.0), (-3.0, -80.0)]
    return _zy_prism(pts, half_width=p["body_dia"])


def _cavity():
    """cavity_sections の 96 点ポリゴン断面を Loft した空洞ソリッド。"""
    wires = []
    for s in P.cavity_sections(p):
        z = s["z"]
        verts = [FreeCAD.Vector(x, y, z) for (x, y) in s["pts"]]
        verts.append(verts[0])
        wires.append(Part.makePolygon(verts))
    return Part.makeLoft(wires, True, True)  # solid=True, ruled=True


def _bore():
    zb = P.bore_start_z(p)
    r = P.bore_radius(p)
    h = p["overall_length"] - zb + 1.5
    return Part.makeCylinder(r, h, FreeCAD.Vector(0, 0, zb), FreeCAD.Vector(0, 0, 1))


# ----------------------------------------------------------------- 組み立て

def build_shape():
    body = _revolved_body()
    shape = body.cut(_beak_cut())
    shape = shape.cut(_facing_cut())
    shape = shape.cut(_cavity())
    shape = shape.cut(_bore())
    return shape.removeSplitter()  # 冗長な面を統合


def main():
    doc_name = "mp_variant_c_sections"
    doc = FreeCAD.newDocument(doc_name)
    shape = build_shape()
    obj = doc.addObject("Part::Feature", "Mouthpiece_C_%s" % SIZE)
    obj.Shape = shape
    doc.recompute()

    out = os.path.join(_HERE, "variant_c_sections.FCStd")
    doc.saveAs(out)

    bb = shape.BoundBox
    expect_cc = P.cavity_volume_cc(p)["total_cc"]
    print("== C案 実断面ロフト (%s) ==" % SIZE)
    print("valid=%s  solids=%d  volume=%.1f mm^3"
          % (shape.isValid(), len(shape.Solids), shape.Volume))
    print("bbox Z=%.2f (overall_length=%.2f)  X=%.2f  Y=%.2f"
          % (bb.ZLength, p["overall_length"], bb.XLength, bb.YLength))
    print("cavity_volume_cc(app)=%.3f cc" % expect_cc)
    print("saved: %s" % out)
    return doc


# FreeCAD マクロ実行・freecadcmd 実行のどちらでも動くよう無条件で実行する
# （freecadcmd はスクリプト直実行時に __name__ を "__main__" にしない）。
main()
