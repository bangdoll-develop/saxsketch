# -*- coding: utf-8 -*-
"""新ベース形状と実物リファレンスの重ね合わせ図を書き出す（提示用）。

出力: overlay_base.png
  1) 側面 ZY  2) 上面 ZX  3) 横断面 6枚  4) 表面偏差の z 分布

実行:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/render_overlay.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

OUT = _HERE / "overlay_base.png"
REF_C, MOD_C = "#9aa4ad", "#d1495b"


def _section(mesh, z, tol=0.35):
    pts, _ = trimesh.sample.sample_surface(mesh, 400_000)
    pts = np.asarray(pts)
    m = np.abs(pts[:, 2] - z) < tol
    return pts[m]


def main():
    ref = trimesh.load(str(_HERE / "reference_aligned.stl"))
    mod = trimesh.load(str(_HERE / "base_tenor.stl"))
    pr, _ = trimesh.sample.sample_surface(ref, 200_000)
    pm, _ = trimesh.sample.sample_surface(mod, 200_000)
    pr, pm = np.asarray(pr), np.asarray(pm)
    dev = cKDTree(pr).query(pm, workers=-1)[0]
    L = float(pr[:, 2].max())

    fig = plt.figure(figsize=(19, 10))
    gs = fig.add_gridspec(3, 6, height_ratios=[1.15, 1.15, 1.5], hspace=0.32,
                          wspace=0.30)

    for row, (ia, ib, title) in enumerate([
            (2, 1, "side  ZY  (+Y = beak / -Y = table)"),
            (2, 0, "top  ZX")]):
        ax = fig.add_subplot(gs[row, :])
        ax.scatter(pr[:, ia], pr[:, ib], s=0.25, c=REF_C, label="reference (WindyCity)")
        ax.scatter(pm[:, ia], pm[:, ib], s=0.25, c=MOD_C, alpha=0.45,
                   label="new SaxSketch base")
        ax.set_aspect("equal")
        ax.grid(alpha=0.3)
        ax.set_title(title, fontsize=10)
        ax.legend(loc="lower left", fontsize=8, markerscale=14)

    for i, z in enumerate([3, 10, 20, 35, 55, 85]):
        ax = fig.add_subplot(gs[2, i])
        for pts, c, lb in ((_section(ref, z), REF_C, "ref"),
                           (_section(mod, z), MOD_C, "model")):
            if len(pts):
                ax.scatter(pts[:, 0], pts[:, 1], s=1.2, c=c, label=lb)
        ax.set_aspect("equal")
        ax.grid(alpha=0.3)
        ax.set_title("z = %d mm" % z, fontsize=9)
        if i == 0:
            ax.legend(fontsize=7, markerscale=4)

    fig.suptitle("SaxSketch new base mouthpiece vs real reference   "
                 "(surface deviation: mean %.3f mm, p95 %.3f mm, max %.2f mm)"
                 % (dev.mean(), np.percentile(dev, 95), dev.max()), fontsize=12)
    fig.savefig(OUT, dpi=95, bbox_inches="tight")
    print("saved:", OUT)
    print("deviation mean=%.3f p95=%.3f max=%.3f (L=%.2f)"
          % (dev.mean(), np.percentile(dev, 95), dev.max(), L))


if __name__ == "__main__":
    main()
