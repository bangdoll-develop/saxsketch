# -*- coding: utf-8 -*-
"""新しいベース形状（SaxSketch の profiles.py）を実物メッシュと突き合わせて検証する。

`align_reference.py` が作った `reference_aligned.stl`（ボア軸基準）と、テンプレート
値で生成したソリッドの表面偏差・ランドマーク・気柱体積を比較し、Markdown レポートと
重ね合わせ PNG を出す。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/verify_base.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

from saxsketch.analysis import meshdiff  # noqa: E402
from saxsketch.instruments.saxophone.components import profiles as P  # noqa: E402
from saxsketch.instruments.saxophone.components.mouthpiece import (  # noqa: E402
    MouthpieceComponent)
from cad.windycity.align_reference import (  # noqa: E402
    facing_fit, facing_rise_profile, table_plane, window_outline, window_span)

REF_STL = _HERE / "reference_aligned.stl"
OUT_STL = _HERE / "base_tenor.stl"
REPORT = _HERE / "verify_report.md"

#: 合格ライン（plan の完了条件）
TOL = {"mean_dev": 0.30, "p95_dev": 0.80, "table_angle": 0.10,
       "tip_opening": 0.10, "length": 0.20, "cavity_pct": 5.0,
       "window_w_max": 1.0, "window_w_mean": 0.5, "window_z": 1.5}
#: 窓幅を突き合わせる z 帯。この外側はサイドレールが分解能以下で
#: 「窓の縁」を一意に取れない（実物・モデルとも）。
WINDOW_Z = (6.0, 38.0)


def _load(size):
    desc = json.loads((_REPO / "saxsketch/instruments/saxophone/descriptor.json")
                      .read_text(encoding="utf-8"))
    tpl = json.loads((_REPO / f"saxsketch/instruments/saxophone/templates/{size}.json")
                     .read_text(encoding="utf-8"))
    return MouthpieceComponent(desc, tpl), tpl["mouthpiece"]


def _surface_dev(a: trimesh.Trimesh, b: trimesh.Trimesh, n=120_000):
    """a の表面サンプルから b 表面への距離（片側・KDTree 近似）。"""
    pa, _ = trimesh.sample.sample_surface(a, n)
    pb, _ = trimesh.sample.sample_surface(b, n)
    d = cKDTree(np.asarray(pb)).query(np.asarray(pa), workers=-1)[0]
    return np.asarray(pa), d


def main():
    ref = meshdiff.load_mesh(str(REF_STL))
    comp, p = _load("tenor")
    part = comp.build(p)
    model = meshdiff.part_to_mesh(part, tolerance=0.02)
    model.export(str(OUT_STL))

    rows: list[tuple[str, float, float, float, str]] = []

    def chk(name, got, want, tol, unit="mm"):
        ok = abs(got - want) <= tol
        rows.append((name, got, want, tol, "OK" if ok else "*** NG"))
        return ok

    ok = True
    bb_m, bb_r = model.bounds, ref.bounds
    ok &= chk("全長", float(bb_m[1][2] - bb_m[0][2]),
              float(bb_r[1][2] - bb_r[0][2]), TOL["length"])
    ok &= chk("幅 X", float(bb_m[1][0] - bb_m[0][0]),
              float(bb_r[1][0] - bb_r[0][0]), 0.4)
    ok &= chk("高さ Y", float(bb_m[1][1] - bb_m[0][1]),
              float(bb_r[1][1] - bb_r[0][1]), 0.4)

    a_r, b_r, rms_r = table_plane(ref)
    a_m, b_m, rms_m = table_plane(model)
    ok &= chk("テーブル傾斜", math.degrees(math.atan(b_m)),
              math.degrees(math.atan(b_r)), TOL["table_angle"], "度")
    ok &= chk("テーブル面 y(0)", a_m, a_r, 0.25)

    # フェイシングは「カーブ種別＋長さ＋開き」の3値フィットが裾では条件不良になる
    # （fl と tip が交換可能で R がほぼ一意にしか決まらない）。リード密着面そのもの、
    # つまり持ち上がりプロファイルを z ごとに直接突き合わせる。
    zr, rr = facing_rise_profile(ref, a_r, b_r, z_lo=8.0, z_hi=32.0, rise_max=3.2)
    zm, rm = facing_rise_profile(model, a_m, b_m, z_lo=8.0, z_hi=32.0, rise_max=3.2)
    zq = np.arange(8.0, 30.01, 1.0)
    d_face = np.abs(np.interp(zq, zm, rm) - np.interp(zq, zr, rr))
    ok &= chk("フェイシング面 最大差", float(d_face.max()), 0.0, 0.15)
    ok &= chk("フェイシング面 平均差", float(d_face.mean()), 0.0, 0.08)
    fac_r = facing_fit(ref, a_r, b_r)
    fac_m = facing_fit(model, a_m, b_m)

    # ---- ウィンドウ輪郭（FreeCAD で先端が点に潰れていた箇所。形状の主目的なので必ず見る）
    zwr, wwr, _, _ = window_outline(ref, a_r, b_r)
    zwm, wwm, _, _ = window_outline(model, a_m, b_m)
    zw = np.arange(WINDOW_Z[0], WINDOW_Z[1] + 0.01, 1.0)
    d_win = np.abs(np.interp(zw, zwm, wwm) - np.interp(zw, zwr, wwr))
    ok &= chk("窓幅 最大差", float(d_win.max()), 0.0, TOL["window_w_max"])
    ok &= chk("窓幅 平均差", float(d_win.mean()), 0.0, TOL["window_w_mean"])
    sr, sm = window_span(zwr, wwr), window_span(zwm, wwm)
    ok &= chk("窓 開始 z", sm[0], sr[0], TOL["window_z"])
    ok &= chk("窓 終端 z", sm[1], sr[1], TOL["window_z"])

    v_ref = float(ref.volume) / 1000.0
    v_mod = float(model.volume) / 1000.0
    ok &= chk("材料体積", v_mod, v_ref, 0.05 * v_ref, "cc")
    cav = P.cavity_volume_cc(p)["total_cc"]
    cav_ref = 18.59            # align_reference 済みメッシュからのレイ積分（実測）
    ok &= chk("気柱体積", cav, cav_ref, TOL["cavity_pct"] / 100.0 * cav_ref, "cc")

    # ---- 表面偏差（モデル→実物）。シャンク遷移部（0.72L 以降）は仕様差が出るので分離
    pa, dev = _surface_dev(model, ref)
    L = float(bb_r[1][2])
    body = pa[:, 2] < 0.72 * L
    stats = {}
    for label, mask in (("本体 (z<0.72L)", body), ("全体", np.ones(len(dev), bool))):
        d = dev[mask]
        stats[label] = (float(d.mean()), float(np.percentile(d, 95)), float(d.max()))
    ok &= chk("表面偏差 平均(本体)", stats["本体 (z<0.72L)"][0], 0.0, TOL["mean_dev"])
    ok &= chk("表面偏差 p95(本体)", stats["本体 (z<0.72L)"][1], 0.0, TOL["p95_dev"])

    # ---- z 帯ごとの偏差
    bands = []
    for z0 in np.arange(0, L, 10.0):
        m = (pa[:, 2] >= z0) & (pa[:, 2] < z0 + 10.0)
        if m.sum() < 100:
            continue
        bands.append((z0, z0 + 10.0, float(dev[m].mean()),
                      float(np.percentile(dev[m], 95))))

    # ---- 他サイズがビルド＆シミュレートできること
    sizes = []
    for size in ("tenor", "alto", "soprano"):
        c, pp = _load(size)
        s = c.build(pp)
        sim = c.simulate(pp)
        sizes.append((size, float(s.volume), len(s.solids()),
                      bool(sim.get("tier1"))))
        ok &= s.volume > 1000.0

    lines = ["# 新ベース形状 vs 実物リファレンス 検証レポート", "",
             "生成: `cad/windycity/verify_base.py` / 実物: WindyCity-Tenor-72-100-LS.3mf",
             "", "## ランドマーク照合", "",
             "| 項目 | モデル | 実物 | 許容 | 判定 |", "|---|---|---|---|---|"]
    for name, got, want, tol, verdict in rows:
        lines.append("| %s | %.3f | %.3f | ±%.2f | %s |" % (name, got, want, tol, verdict))
    lines += ["", "## 表面偏差（モデル表面 → 実物表面の距離）", "",
              "| 範囲 | 平均 | p95 | 最大 |", "|---|---|---|---|"]
    for label, (mu, p95, mx) in stats.items():
        lines.append("| %s | %.3f mm | %.3f mm | %.3f mm |" % (label, mu, p95, mx))
    lines += ["", "### z 帯別", "", "| z 範囲 | 平均 | p95 |", "|---|---|---|"]
    for z0, z1, mu, p95 in bands:
        lines.append("| %.0f–%.0f | %.3f mm | %.3f mm |" % (z0, z1, mu, p95))
    lines += ["", "## 3サイズのビルド", "",
              "| サイズ | ソリッド体積 mm³ | ソリッド数 | simulate |", "|---|---|---|---|"]
    for size, vol, ns, sim in sizes:
        lines.append("| %s | %.0f | %d | %s |" % (size, vol, ns, sim))
    lines += ["", "## ウィンドウ輪郭（リード開口の幅）", "",
              "| z | 実物 | モデル | 差 |", "|---|---|---|---|"]
    for z in zw[::2]:
        a_ = float(np.interp(z, zwr, wwr))
        b_ = float(np.interp(z, zwm, wwm))
        lines.append("| %.0f | %.2f | %.2f | %+.2f |" % (z, a_, b_, b_ - a_))
    lines += ["", "開口 z 範囲: 実物 %.1f–%.1f / モデル %.1f–%.1f"
              % (sr[0], sr[1], sm[0], sm[1]),
              "", "## テーブル平面の平面度", "",
              "- 実物 rms %.4f mm / モデル rms %.4f mm" % (rms_r, rms_m),
              "", "## フェイシング面（リード密着面）の持ち上がり", "",
              "| z | 実物 | モデル | 差 |", "|---|---|---|---|"]
    for z in zq:
        a = float(np.interp(z, zr, rr))
        b = float(np.interp(z, zm, rm))
        lines.append("| %.0f | %.3f | %.3f | %+.3f |" % (z, a, b, b - a))
    lines += ["",
              "参考（裾だけの2母数フィットは条件不良なので情報として）: "
              "実物 %s fl=%.2f tip=%.3f / モデル %s fl=%.2f tip=%.3f"
              % (fac_r["curve"], fac_r["facing_length"], fac_r["tip_opening"],
                 fac_m["curve"], fac_m["facing_length"], fac_m["tip_opening"]), "",
              "## 総合: " + ("**合格**" if ok else "**不合格**"), ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    for name, got, want, tol, verdict in rows:
        print("%-18s model=%9.3f ref=%9.3f tol=%.2f %s" % (name, got, want, tol, verdict))
    for label, (mu, p95, mx) in stats.items():
        print("dev %-14s mean=%.3f p95=%.3f max=%.3f" % (label, mu, p95, mx))
    print("report ->", REPORT)
    print("ALL_PASS" if ok else "SOME_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
