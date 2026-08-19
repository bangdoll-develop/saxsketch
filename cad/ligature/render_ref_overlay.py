# -*- coding: utf-8 -*-
"""参照マウスピースの重ね表示を、`Viewer3D` と**同じ変換**で描き出す（4-C.4）。

出力: ref_overlay.png（3 サイズ × 側面 ZY / 正面 XY）

ブラウザのペインが非表示だとスクリーンショットが撮れないので、目視の代わりに
ここで再現する。フロントの置き方はこう:

    本体（リガチャー）  geo.center() 済み → 頂点_world = R · (v − C_main)
    重ね（マウスピース）center しない・position = R · (−C_main)
                                        → 頂点_world = R · (v − C_main)

**同じ写像**なので、共通の回転 R（x 軸まわり −90°）を外した「C_main を引いた
モデル座標」で描けば、画面に出る位置関係がそのまま出る。

実行:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/ligature/render_ref_overlay.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402


def _use_cjk_font() -> bool:
    """日本語ラベルが豆腐にならないよう CJK フォントを拾う（`render_sections` と同じ）."""
    for path in ("/mnt/c/Windows/Fonts/meiryo.ttc",
                 "/mnt/c/Windows/Fonts/YuGothR.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(path).exists():
            try:
                fm.fontManager.addfont(path)
                matplotlib.rcParams["font.family"] = fm.FontProperties(
                    fname=path).get_name()
                matplotlib.rcParams["axes.unicode_minus"] = False
                return True
            except Exception:
                continue
    return False


_use_cjk_font()

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.core.schema import ParamSet  # noqa: E402
from saxsketch.export.models import export_model  # noqa: E402

OUT = _HERE / "ref_overlay.png"
SIZES = ("soprano", "alto", "tenor")
LIG_C, REF_C = "#7fa8d8", "#a8c0d8"


def _mesh(comp, params, out: Path) -> trimesh.Trimesh:
    export_model(comp.build(params), out, "stl", tolerance=0.05)
    return trimesh.load(str(out), force="mesh")


def _draw(ax, mesh, axes, color, alpha, lw):
    """三角形をそのまま投影する（輪郭を推定しないので嘘が混ざらない）."""
    tris = mesh.triangles[:, :, axes]
    ax.add_collection(PolyCollection(
        tris, facecolors=color, edgecolors=color, alpha=alpha, linewidths=lw))


def main():
    inst = get_registry().get("saxophone")
    fig, axes = plt.subplots(3, 2, figsize=(13, 10))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for row, size in enumerate(SIZES):
            mp = inst.make_component("mouthpiece", size)
            mp_p = dict(ParamSet(mp.param_specs(),
                                 mp.template.get("mouthpiece", {})).values)
            lig = inst.make_component("ligature", size)
            lig_p = dict(ParamSet(lig.param_specs(),
                                  lig.template.get("ligature", {})).values)
            lig.set_refs({"mouthpiece": {"params": mp_p}})

            m_lig = _mesh(lig, lig_p, td / f"lig_{size}.stl")
            m_ref = _mesh(mp, mp_p, td / f"mp_{size}.stl")

            # ここが `Viewer3D` と同じ 1 行 —— **本体の重心**で両方を動かす。
            lo, hi = m_lig.bounds
            centre = (lo + hi) / 2.0
            m_lig.apply_translation(-centre)
            m_ref.apply_translation(-centre)

            for col, (aa, title) in enumerate((((2, 1), "側面 ZY"),
                                               ((0, 1), "正面 XY"))):
                ax = axes[row][col]
                _draw(ax, m_ref, aa, REF_C, 0.25, 0.0)   # 参照＝半透明
                _draw(ax, m_lig, aa, LIG_C, 0.9, 0.0)
                ax.set_aspect("equal")
                ax.autoscale_view()
                ax.set_title(f"{size} — {title}", fontsize=10)
                ax.axhline(0, color="#444", lw=0.4)
                ax.axvline(0, color="#444", lw=0.4)

            print(f"{size:8s} lig z {lo[2]:7.2f}–{hi[2]:7.2f}  "
                  f"重心 ({centre[0]:.2f}, {centre[1]:.2f}, {centre[2]:.2f})  "
                  f"参照 z {m_ref.bounds[0][2]:7.2f}–{m_ref.bounds[1][2]:7.2f}"
                  f"（重心を引いた後）")

    fig.suptitle("参照マウスピースの重ね表示（本体の重心で両方を動かす）", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=110)
    print("→", OUT)


if __name__ == "__main__":
    main()
