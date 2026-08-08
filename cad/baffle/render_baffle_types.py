# -*- coding: utf-8 -*-
"""バッフル3型（＋ロールオーバー）を**実際にソリッドを生成して**断面で検証する。

「型を作り分けられること」「ハンドルで調整できること」を、法則の数値ではなく
**造形される形**で確かめるのが目的。各ケースについて

  1. `MouthpieceComponent.build()` でソリッドを作り STL 化
  2. x=0 の中央面でメッシュ断面（シルエット）を取る
  3. 中央面上を **下から上へレイキャスト**して空洞の天井 y を実測し、
     解析値 `profiles.cavity_roof_y` と突き合わせる

を行い、PNG と PASS 表を出す。

出力:
  baffle_types.png    4型の中央断面（メッシュ実断面 × 解析天井）
  baffle_handles.png  ハンドルを振ったときの天井の動き

実行:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/baffle/render_baffle_types.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

# CJK フォント設定と平面断面の輪郭抽出は windycity 側と同じものを使う
# （図の見た目を揃えるためと、同じ処理を2回書かないため）。
from cad.windycity.render_sections import _use_cjk_font, contours  # noqa: E402
from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.export.models import check_mesh, export_model  # noqa: E402
from saxsketch.instruments.saxophone.components import profiles as pf  # noqa: E402

_CJK = _use_cjk_font()

OUT_TYPES = _HERE / "baffle_types.png"
OUT_HANDLES = _HERE / "baffle_handles.png"

TYPE_LABEL = {"straight": "ストレート型", "step": "ステップ型",
              "curve": "カーブ型", "rollover": "ロールオーバー型"}
TYPE_CAPTION = {"straight": "暗くソフトな音", "step": "バランスのとれた音色",
                "curve": "メタリックでアグレッシブな音", "rollover": "肩を丸めた中間"}


def _lbl(ja: str, en: str) -> str:
    return ja if _CJK else en


#: レイを中央面からわずかにずらす量 [mm]。
#:
#: 形状は x=0 に対して左右対称で、断面点列も対称に作られるので、**x=0 ちょうどには
#: 三角形の稜線が並ぶ**。そこを真上へ飛ばすとレイが稜線に乗って当たり判定を
#: 取りこぼし、天井を素通りして外形に当たる（実測で 90 点中 4〜9 点が 6mm 誤差
#: として出た）。天井の横アーチは x=0.15mm では 0.001mm も動かないので、
#: ここだけずらして測る。
_RAY_X = 0.15


def roof_from_mesh(mesh, p: dict, zs) -> np.ndarray:
    """中央面のすぐ脇で下から上へレイを飛ばし、空洞の天井 y を実測する。

    x=0 では窓が開いているので、断面の輪郭は外形と空洞がひと続きの1本になる
    （＝輪郭から天井だけを取り出せない）。レイなら「その z で最初に当たる上面」
    が天井そのものなので、素直に測れる。始点は解析値の空洞の中ほど。
    """
    out = np.full(len(zs), np.nan)
    origins, dirs, idx = [], [], []
    for i, z in enumerate(zs):
        roof = pf.cavity_roof_y(p, z)
        floor = pf.cavity_floor_y(p, z)
        if roof - floor < 0.2:
            continue
        origins.append([_RAY_X, 0.5 * (roof + floor), z])
        dirs.append([0.0, 1.0, 0.0])
        idx.append(i)
    if not origins:
        return out
    org = np.array(origins)
    loc, ray_idx, _ = mesh.ray.intersects_location(
        org, np.array(dirs), multiple_hits=True)
    for i in range(len(idx)):
        hits = loc[ray_idx == i]
        # 始点より上の当たりだけを採る（trimesh は始点の後ろ側も返しうる）。
        hits = hits[hits[:, 1] > org[i][1] + 1e-6]
        if len(hits):
            out[idx[i]] = float(np.min(hits[:, 1]))   # 最初に当たる面＝天井
    return out


def build_case(comp, p: dict, tmp: Path, name: str) -> dict:
    """1ケース分をビルドして測る。"""
    part = comp.build(p)
    f = tmp / f"{name}.stl"
    export_model(part, f, "stl")
    q = check_mesh(f)
    mesh = trimesh.load(str(f))
    zs = np.linspace(pf.window_start_z(p) + 0.6, pf.bore_start_z(p) - 0.6, 90)
    meas = roof_from_mesh(mesh, p, zs)
    law = np.array([pf.cavity_roof_y(p, z) for z in zs])
    ok = ~np.isnan(meas)
    err = np.abs(meas[ok] - law[ok]) if ok.any() else np.array([np.nan])
    slope = np.max(np.diff(law) / np.diff(zs))
    return {
        "name": name, "p": p, "mesh": mesh, "quality": q,
        "solids": len(part.solids()), "valid": bool(part.is_valid),
        "volume_cc": part.volume / 1000.0,
        "air_cc": pf.cavity_volume_cc(p)["total_cc"],
        "zs": zs, "meas": meas, "law": law,
        "err_max": float(np.nanmax(err)), "err_p95": float(np.nanpercentile(err, 95)),
        "chord_sag": chord_sag(p),
        "covered": int(ok.sum()), "n": len(zs),
        "roof_slope": float(slope),
        "window_open_z": pf.window_open_z(p),
        "tip_rail_width": p["tip_rail_width"],
    }


def chord_sag(p: dict) -> float:
    """ルールドロフトの弦が天井の法則から落ちる最大量 [mm]。

    ロフトは断面間を直線で結ぶので、**この量は表現の下限**であって形状の誤差では
    ない。実ソリッドの測定値をこの値と比べれば「法則どおりに造形できているか」を
    表現の粗さと切り分けて判定できる。
    """
    zs = pf._station_zs(p)
    worst = 0.0
    for a, b in zip(zs, zs[1:]):
        ya, yb = pf.cavity_roof_y(p, a), pf.cavity_roof_y(p, b)
        for t in range(1, 20):
            z = a + (b - a) * t / 20.0
            worst = max(worst, abs(pf.cavity_roof_y(p, z) - (ya + (yb - ya) * t / 20.0)))
    return worst


def draw_case(ax, r: dict, title: str, sub: str) -> None:
    p = r["p"]
    for c in contours(r["mesh"], (0, 0, 0), (1, 0, 0), (2, 1)):
        ax.plot(c[:, 0], c[:, 1], color="#adb5bd", lw=0.9, solid_capstyle="round")
    cur = pf.section_curves(p)
    ax.plot(*zip(*cur["reed"]), color="#d1495b", lw=1.0, ls="--",
            label=_lbl("リード面", "reed face"))
    ax.plot(*zip(*cur["shell_top"]), color="#8d99ae", lw=0.8, ls=":",
            label=_lbl("天井の上限", "ceiling limit"))
    ax.plot(r["zs"], r["law"], color="#1d3557", lw=1.8,
            label=_lbl("天井（法則）", "roof (law)"))
    ax.plot(r["zs"], r["meas"], color="#f4a261", lw=0.0, marker=".", ms=2.4,
            label=_lbl("天井（実ソリッド）", "roof (built solid)"))
    ax.axvline(pf.baffle_plateau_end_z(p), color="#2a9d8f", lw=0.8, ls="-.")
    ax.set_xlim(-2, pf.bore_start_z(p) + 4)
    ax.set_title(f"{title}\n{sub}", fontsize=9)
    ax.set_xlabel("z [mm]", fontsize=8)
    ax.set_ylabel("y [mm]", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.25)
    ax.set_aspect("equal")


def main() -> int:
    reg = get_registry()
    comp = reg.get("saxophone").make_component("mouthpiece", "tenor")
    base = {s.key: s.default for s in comp.param_specs()}

    types = ["straight", "step", "curve", "rollover"]
    sweeps = [
        ("step  棚 0.15", dict(base, baffle_type="step", baffle_plateau=0.15)),
        ("step  棚 0.60", dict(base, baffle_type="step", baffle_plateau=0.60)),
        ("step  段 0.80", dict(base, baffle_type="step", baffle_step_rise=0.80)),
        ("curve  c=-1.0", dict(base, baffle_type="curve", baffle_curvature=-1.0)),
        ("curve  c=+1.0", dict(base, baffle_type="curve", baffle_curvature=1.0)),
        ("rollover R=3", dict(base, baffle_type="rollover", rollover_radius=3.0)),
    ]

    results: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fig, axes = plt.subplots(2, 2, figsize=(13, 7.5))
        for ax, bt in zip(axes.ravel(), types):
            r = build_case(comp, dict(base, baffle_type=bt), tmp, bt)
            results.append(r)
            draw_case(ax, r, _lbl(TYPE_LABEL[bt], bt),
                      _lbl(TYPE_CAPTION[bt], "") +
                      f"  ({_lbl('気柱', 'air')} {r['air_cc']:.2f}cc)")
        axes[0][0].legend(fontsize=7, loc="upper left")
        fig.suptitle(_lbl("バッフル型ごとの中央断面（灰=実ソリッドの断面 / 橙点=実測天井）",
                          "Baffle types, median section"), fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=2.6)
        fig.savefig(OUT_TYPES, dpi=130)
        plt.close(fig)

        fig, axes = plt.subplots(2, 3, figsize=(17, 7.5))
        for ax, (label, q) in zip(axes.ravel(), sweeps):
            r = build_case(comp, q, tmp, label.replace(" ", "_").replace("=", ""))
            results.append(r)
            draw_case(ax, r, label, f"{_lbl('気柱', 'air')} {r['air_cc']:.2f}cc")
        fig.suptitle(_lbl("ハンドルを振ったときの断面（調整可能範囲の両端）",
                          "Handle sweeps"), fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=2.6)
        fig.savefig(OUT_HANDLES, dpi=130)
        plt.close(fig)

    print(f"\n図: {OUT_TYPES.name} / {OUT_HANDLES.name}\n")
    hdr = (f"{'ケース':<16}{'水密':>5}{'単一':>5}{'有効':>5}{'材料cc':>9}{'気柱cc':>8}"
           f"{'天井差max':>10}{'p95':>8}{'弦の下限':>10}{'測定率':>8}"
           f"{'最大勾配':>10}{'窓開始-レール':>14}")
    print(hdr)
    print("-" * len(hdr))
    fails = []
    for r in results:
        wt = r["quality"]["watertight"] and r["quality"]["winding_consistent"]
        single = r["solids"] == 1
        d_win = r["window_open_z"] - r["tip_rail_width"]
        # 判定は「**表現の下限（弦）を超える誤差が出ていないか**」で行う。
        # ルールドロフトは断面間を直線で結ぶので、勾配が急な所では弦のぶんだけ
        # 必ず内側へ落ちる。それ以上の誤差が無ければ法則どおりに造形できている。
        # 0.08 は STL 化（tol）とレイの当たり判定ぶんの余裕。
        ok = (wt and single and r["valid"]
              and r["err_max"] <= r["chord_sag"] + 0.08
              and r["err_p95"] < 0.10
              and abs(d_win) < 0.15 and r["covered"] > 0.9 * r["n"])
        if not ok:
            fails.append(r["name"])
        print(f"{r['name']:<16}{'○' if wt else '×':>5}{'○' if single else '×':>5}"
              f"{'○' if r['valid'] else '×':>5}{r['volume_cc']:>9.3f}{r['air_cc']:>8.3f}"
              f"{r['err_max']:>10.3f}{r['err_p95']:>8.3f}{r['chord_sag']:>10.3f}"
              f"{r['covered'] / r['n']:>8.0%}{r['roof_slope']:>10.3f}{d_win:>14.3f}")
    print()
    print("「弦の下限」= ルールドロフトが断面間を直線で結ぶぶん。天井差 max がこれを")
    print("超えなければ、法則どおりに造形できている（表現の粗さと形状誤差の切り分け）。")
    print()
    if fails:
        print("FAIL:", ", ".join(fails))
        return 1
    print("ALL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
