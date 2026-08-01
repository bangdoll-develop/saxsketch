# -*- coding: utf-8 -*-
"""A案: プリミティブ＋Boolean＋Spreadsheet 方式 マウスピース（数値編集が最易）。

FreeCAD の Part プリミティブ（テーパ円柱＝Cone、円柱＝Cylinder、箱＝Box）を
Boolean で組む素直な構成。寸法は Spreadsheet「params」に集約し、主要寸法
（全長・ボディ径・ボア径・ボア長・テーブル位置など）はプリミティブへ式束縛して
あるので、**FreeCAD で params のセルを書き換えると 3D 形状がその場で再計算**される。

意匠を掴むための近似モデル: スーパー楕円チェンバー・馬蹄・実段差バッフル・
フェイシングカーブは表現しない（チェンバー＝箱、窓＝スロット、テーブル＝平面）。
実物断面を厳密に要るなら C 案、滑らかな曲面が要るなら B 案を使う。

編集方法:
  - サイズ変更は下の SIZE を "alto"/"soprano" に（またはこのマクロを再実行）。
  - FreeCAD 上では Spreadsheet「params」のセルを直接編集 → 再計算。
  - ビーク傾斜・チェンバー箱など一部は生成時の値で作った補助ソリッド。大きく
    変えたときはマクロを再実行して作り直す。

実行: "C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" variant_a_primitives.py
"""
import os
import sys
import math

import FreeCAD
import Part

App = FreeCAD
V = FreeCAD.Vector

# ----------------------------------------------------------------- パラメータ
SIZE = "tenor"          # "soprano" / "alto" / "tenor"

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from mp_presets import preset  # noqa: E402

p = preset(SIZE)

# 外形制御点（アプリ _OUTER_PROFILE 準拠）を 3 プリミティブに単純化した比率
_R_TIP = 0.70          # ティップ端 r/rb
_R_MID = 1.00          # バレル最大 r/rb
_R_SHANK = 0.86        # シャンク端 r/rb
_Z_TIPCONE = 0.45      # ティップ円錐の終わり z/L
_Z_BARREL = 0.88       # バレル（最大径）の終わり z/L


# ----------------------------------------------------------------- Spreadsheet

def _sheet(doc):
    sh = doc.addObject("Spreadsheet::Sheet", "params")
    rows = [
        ("overall_length", p["overall_length"], "全長"),
        ("body_dia",       p["body_dia"],       "ボディ径"),
        ("body_r",         p["body_dia"] / 2.0, "ボディ半径"),
        ("bore_dia",       p["bore_dia"],       "ボア径"),
        ("bore_r",         p["bore_dia"] / 2.0, "ボア半径"),
        ("bore_length",    p["bore_length"],    "ボア長"),
        ("tip_opening",    p["tip_opening"],    "ティップ開き"),
        ("facing_length",  p["facing_length"],  "フェイシング長"),
        ("beak_height",    p["beak_height"],    "ビーク高さ"),
        ("window_length",  p["window_length"],  "ウィンドウ長"),
        ("reed_width",     p["reed_width"],     "リード幅"),
        ("side_rail_width", p["side_rail_width"], "サイドレール幅"),
        ("tip_rail_width", p["tip_rail_width"], "ティップレール幅"),
        ("min_wall",       p["min_wall"],       "最小肉厚"),
        ("table_y",        -0.40 * p["body_dia"], "テーブル面Y(=-0.4*body_dia)"),
    ]
    for i, (alias, val, label) in enumerate(rows, start=1):
        sh.set("A%d" % i, label)
        sh.set("B%d" % i, repr(float(val)))
        sh.setAlias("B%d" % i, alias)
    doc.recompute()
    return sh


# ----------------------------------------------------------------- 外形（テーパ円柱）

def _body(doc):
    L = p["overall_length"]
    tip = doc.addObject("Part::Cone", "ConeTip")
    tip.setExpression("Radius1", "params.body_r * %g" % _R_TIP)
    tip.setExpression("Radius2", "params.body_r * %g" % _R_MID)
    tip.setExpression("Height", "params.overall_length * %g" % _Z_TIPCONE)
    tip.Placement = App.Placement(V(0, 0, 0), App.Rotation())

    barrel = doc.addObject("Part::Cylinder", "Barrel")
    barrel.setExpression("Radius", "params.body_r * %g" % _R_MID)
    barrel.setExpression("Height", "params.overall_length * %g" % (_Z_BARREL - _Z_TIPCONE))
    barrel.setExpression(".Placement.Base.z", "params.overall_length * %g" % _Z_TIPCONE)

    shank = doc.addObject("Part::Cone", "ConeShank")
    shank.setExpression("Radius1", "params.body_r * %g" % _R_MID)
    shank.setExpression("Radius2", "params.body_r * %g" % _R_SHANK)
    shank.setExpression("Height", "params.overall_length * %g" % (1.0 - _Z_BARREL))
    shank.setExpression(".Placement.Base.z", "params.overall_length * %g" % _Z_BARREL)

    fuse = doc.addObject("Part::MultiFuse", "Body")
    fuse.Shapes = [tip, barrel, shank]
    return fuse


# ----------------------------------------------------------------- 補助ソリッド（Part shape → Feature）

def _feature(doc, name, shape):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    return obj


def _beak_tool(doc):
    """ティップのくさびからバイトポイントへ立ち上がる 1 平面でビーク上面を切る楔。"""
    L = p["overall_length"]
    rb = p["body_dia"] / 2.0
    ty = -0.40 * p["body_dia"]
    y_tip = ty + p["tip_opening"] + 2.6           # ティップ端のくさび上面
    y_bite = ty + p["beak_height"]                # バイトポイント(0.25L)
    z_bite = 0.25 * L
    m = (y_bite - y_tip) / z_bite                 # 傾き
    z_sh = 0.55 * L                               # ショルダー（ここまで切る）
    hw = rb + 1.0
    # (z,y) 平面の楔ポリゴン: 下辺 = ビーク直線、上を y=+80 で閉じる
    pts = [(-3.0, y_tip + m * (-3.0)), (z_sh, y_tip + m * z_sh),
           (z_sh, 80.0), (-3.0, 80.0)]
    verts = [V(-hw, y, z) for (z, y) in pts]
    verts.append(verts[0])
    face = Part.Face(Part.makePolygon(verts))
    solid = face.extrude(V(2.0 * hw, 0, 0))
    return _feature(doc, "BeakTool", solid)


def _table_tool(doc):
    """テーブル面（平面）でリード側を平坦に削ぐ箱。"""
    L = p["overall_length"]
    rb = p["body_dia"] / 2.0
    ty = -0.40 * p["body_dia"]
    z_end = 0.90 * L                              # リード踵付近まで
    box = doc.addObject("Part::Box", "TableTool")
    box.setExpression("Length", "2 * (params.body_r + 1)")   # X
    box.Width = 40.0                                          # Y（下方向）
    box.setExpression("Height", "%g * params.overall_length + 3" % 0.90)  # Z
    # 箱の上面が table_y に来るよう配置（y は table_y-40 から table_y）
    box.setExpression(".Placement.Base.x", "-(params.body_r + 1)")
    box.setExpression(".Placement.Base.y", "params.table_y - 40")
    box.Placement.Base.z = -1.5
    return box


def _cavity_tool(doc):
    """窓スロット＋チェンバー箱＋スロート/ボア円柱を融合した内部空洞ソリッド。"""
    L = p["overall_length"]
    rb = p["body_dia"] / 2.0
    ty = -0.40 * p["body_dia"]
    r_bore = p["bore_dia"] / 2.0
    mw = p["min_wall"]
    zb = L - p["bore_length"]
    z_start = p["tip_rail_width"] + 0.2
    z_we = min(z_start + p["window_length"], zb - 8.0)
    w_win = p["reed_width"] - 2.0 * p["side_rail_width"]
    w_ch = min(2.0 * (rb - mw), 0.78 * p["body_dia"])   # チェンバー幅（壁内に収める）
    h_ch = min(2.0 * (rb - mw) - 1.0, 0.60 * p["body_dia"])

    parts = []
    # 窓スロット: テーブル開口〜チェンバー天井。床を table_y より下げて窓を開ける
    win = Part.makeBox(w_win, (ty + 0.35 * h_ch) - (ty - 1.0), z_we - z_start,
                       V(-w_win / 2.0, ty - 1.0, z_start))
    parts.append(win)
    # チェンバー箱（中央）
    cy0 = ty + 1.0
    cham = Part.makeBox(w_ch, h_ch, zb - z_we, V(-w_ch / 2.0, cy0, z_we))
    parts.append(cham)
    # スロート→ボア円柱（軸上）
    bore = Part.makeCylinder(r_bore, L - zb + 2.0, V(0, 0, zb), V(0, 0, 1))
    parts.append(bore)
    # 面取り無しの融合
    solid = parts[0].fuse(parts[1]).fuse(parts[2]).removeSplitter()
    return _feature(doc, "CavityTool", solid)


def _bore_tool(doc):
    box = doc.addObject("Part::Cylinder", "BoreTool")
    box.setExpression("Radius", "params.bore_r")
    box.setExpression("Height", "params.bore_length + 2")
    box.setExpression(".Placement.Base.z", "params.overall_length - params.bore_length")
    return box


# ----------------------------------------------------------------- 組み立て（Boolean 木）

def _cut(doc, name, base, tool):
    c = doc.addObject("Part::Cut", name)
    c.Base = base
    c.Tool = tool
    return c


def main():
    doc = App.newDocument("mp_variant_a_primitives")
    _sheet(doc)
    body = _body(doc)
    c1 = _cut(doc, "CutBeak", body, _beak_tool(doc))
    c2 = _cut(doc, "CutTable", c1, _table_tool(doc))
    c3 = _cut(doc, "CutCavity", c2, _cavity_tool(doc))
    result = _cut(doc, "Mouthpiece_A_%s" % SIZE, c3, _bore_tool(doc))
    doc.recompute()

    shape = result.Shape
    bb = shape.BoundBox
    out = os.path.join(_HERE, "variant_a_primitives.FCStd")
    doc.saveAs(out)
    print("== A案 プリミティブ+Boolean+Spreadsheet (%s) ==" % SIZE)
    print("valid=%s  solids=%d  volume=%.1f mm^3"
          % (shape.isValid(), len(shape.Solids), shape.Volume))
    print("bbox Z=%.2f (overall_length=%.2f)  X=%.2f  Y=%.2f"
          % (bb.ZLength, p["overall_length"], bb.XLength, bb.YLength))
    print("saved: %s" % out)
    return doc


main()
