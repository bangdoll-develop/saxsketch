# -*- coding: utf-8 -*-
"""新ベース形状と実物リファレンスを **各軸の断面** で比較する図を書き出す。

出力:
  sections_xy.png   Z 一定の横断面（10枚）
  sections_yz_xz.png  X 一定の縦断面 / Y 一定の水平断面 / リード面から見た窓輪郭

点群散布だと重なって潰れるので、`mesh.section` の輪郭線（ポリライン）で描く。

実行:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/render_sections.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402


def _use_cjk_font():
    """日本語ラベルが豆腐にならないよう、あれば CJK フォントを使う。

    WSL2 には CJK フォントが無いことが多いので Windows 側の実体を直接拾う。
    見つからなければ英語だけのラベルになるよう呼び出し側でフォールバックする。
    """
    for path in ("/mnt/c/Windows/Fonts/meiryo.ttc",
                 "/mnt/c/Windows/Fonts/YuGothR.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(path).exists():
            try:
                fm.fontManager.addfont(path)
                name = fm.FontProperties(fname=path).get_name()
                matplotlib.rcParams["font.family"] = name
                matplotlib.rcParams["axes.unicode_minus"] = False
                return True
            except Exception:
                continue
    return False


_CJK = _use_cjk_font()

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

from cad.windycity.align_reference import (  # noqa: E402
    table_plane, window_outline)

REF_C, MOD_C = "#6c757d", "#d1495b"
OUT_XY = _HERE / "sections_xy.png"
OUT_LONG = _HERE / "sections_yz_xz.png"


def contours(mesh, origin, normal, cols):
    """平面断面の輪郭線を、指定した2軸 `cols`（例 (2,1)=横z縦y）の座標で返す。

    `to_planar()` は稀に失敗するので、線分エンティティから直接ポリラインを組む。
    """
    sec = mesh.section(plane_origin=list(origin), plane_normal=list(normal))
    if sec is None:
        return []
    verts = np.asarray(sec.vertices)
    return [verts[ent.points][:, list(cols)] for ent in sec.entities]


def draw(ax, mesh, origin, normal, cols, color, label, lw=1.4):
    first = True
    for c in contours(mesh, origin, normal, cols):
        ax.plot(c[:, 0], c[:, 1], color=color, lw=lw,
                label=label if first else None, solid_capstyle="round")
        first = False


def main():
    ref = trimesh.load(str(_HERE / "reference_aligned.stl"))
    mod = trimesh.load(str(_HERE / "base_tenor.stl"))
    a_r, b_r, _ = table_plane(ref)
    a_m, b_m, _ = table_plane(mod)
    L = float(ref.bounds[1][2])

    # ---------------------------------------------------------------- XY 断面
    zs = [2, 4, 8, 14, 22, 30, 38, 44, 60, 90]
    fig, axes = plt.subplots(2, 5, figsize=(20, 8.6))
    for ax, z in zip(axes.ravel(), zs):
        draw(ax, ref, (0, 0, z), (0, 0, 1), (0, 1), REF_C, "reference")
        draw(ax, mod, (0, 0, z), (0, 0, 1), (0, 1), MOD_C, "new base")
        ax.axhline(a_r + b_r * z, color="#2a9d8f", lw=0.8, ls="--",
                   label="reed plane")
        ax.set_aspect("equal")
        ax.grid(alpha=0.25)
        ax.set_title("XY  z = %d mm" % z, fontsize=10)
        ax.set_xlabel("x", fontsize=8)
        ax.set_ylabel("y", fontsize=8)
    axes[0][0].legend(fontsize=8, loc="lower left")
    fig.suptitle("横断面比較（Z 一定）  灰=実物 WindyCity / 赤=新ベース", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT_XY, dpi=95)
    print("saved:", OUT_XY)

    # ------------------------------------------------------- YZ / XZ 縦横断面
    fig, axes = plt.subplots(3, 2, figsize=(19, 9.5))
    panels = [("YZ", 0.0), ("YZ", 4.0), ("YZ", 7.0),
              ("XZ_reed", None), ("XZ", 0.0), ("XZ", 6.0)]
    for ax, (kind, val) in zip(axes.ravel(), panels):
        if kind == "YZ":
            # 縦断面（x 一定）: 横=z, 縦=y
            draw(ax, ref, (val, 0, 0), (1, 0, 0), (2, 1), REF_C, "reference")
            draw(ax, mod, (val, 0, 0), (1, 0, 0), (2, 1), MOD_C, "new base")
            ax.plot([0, L], [a_r, a_r + b_r * L], color="#2a9d8f", lw=0.9,
                    ls="--", label="reed plane")
            ax.set_title("YZ 縦断面  x = %.0f mm  （横=z, 縦=y）" % val, fontsize=10)
        elif kind == "XZ":
            # 水平断面（y 一定）: 横=z, 縦=x
            draw(ax, ref, (0, val, 0), (0, 1, 0), (2, 0), REF_C, "reference")
            draw(ax, mod, (0, val, 0), (0, 1, 0), (2, 0), MOD_C, "new base")
            ax.set_title("XZ 水平断面  y = %+.0f mm  （横=z, 縦=x）" % val, fontsize=10)
        else:
            # リード面は傾いているので、各メッシュ自身の平面に沿って切る
            for m, (a, b), c, lb in ((ref, (a_r, b_r), REF_C, "reference"),
                                     (mod, (a_m, b_m), MOD_C, "new base")):
                n = np.array([0.0, 1.0, -b])
                n /= np.linalg.norm(n)
                draw(ax, m, (0.0, a + 0.3, 0.0), n, (2, 0), c, lb)
            ax.set_title("XZ 水平断面  リード面 +0.3mm（＝窓の開口）  （横=z, 縦=x）",
                         fontsize=10)
        ax.set_aspect("equal")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="lower left")
    fig.suptitle("縦断面・水平断面比較  灰=実物 WindyCity / 赤=新ベース", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT_LONG, dpi=95)
    print("saved:", OUT_LONG)

    # ---------------------------------------------------- 窓輪郭の平面図（主題）
    zr, wr, lor, hir = window_outline(ref, a_r, b_r)
    zm, wm, lom, him = window_outline(mod, a_m, b_m)
    fig, ax = plt.subplots(figsize=(14, 4.2))
    for zz, lo, hi, c, lb in ((zr, lor, hir, REF_C, "reference"),
                              (zm, lom, him, MOD_C, "new base")):
        ok = np.isfinite(lo)
        ax.plot(zz[ok], lo[ok], color=c, lw=2.0, label=lb)
        ax.plot(zz[ok], hi[ok], color=c, lw=2.0)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_xlabel("z  (mm)  ← ティップ")
    ax.set_ylabel("x  (mm)")
    ax.set_title("ウィンドウ輪郭（リード面から見た開口）  灰=実物 / 赤=新ベース",
                 fontsize=12)
    ax.legend(fontsize=9)
    fig.savefig(_HERE / "window_outline.png", dpi=110, bbox_inches="tight")
    print("saved:", _HERE / "window_outline.png")


if __name__ == "__main__":
    main()
