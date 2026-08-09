# -*- coding: utf-8 -*-
"""新しいベース形状（SaxSketch の profiles.py）を実物メッシュと突き合わせて検証する。

`align_reference.py` が作った `reference_aligned.stl`（ボア軸基準）と、テンプレート
値で生成したソリッドの表面偏差・ランドマーク・気柱体積を比較し、Markdown レポートと
重ね合わせ PNG を出す。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/verify_base.py
"""
from __future__ import annotations

import collections
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

from saxsketch.analysis import meshdiff  # noqa: E402
from saxsketch.export.models import export_model  # noqa: E402
from saxsketch.instruments.saxophone.components import profiles as P  # noqa: E402
from saxsketch.instruments.saxophone.components.mouthpiece import (  # noqa: E402
    MouthpieceComponent)
from cad.windycity.align_reference import (  # noqa: E402
    SAMPLE_SEED, facing_fit, facing_rise_profile, table_plane, window_outline,
    window_span)

REF_STL = _HERE / "reference_aligned.stl"
OUT_STL = _HERE / "base_tenor.stl"
OUT_STEP = _HERE / "base_tenor_cad.step"
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
    """a の表面サンプルから b 表面への距離（片側・KDTree 近似）。

    **両側で別のシードを使う**。ref とモデルは近い形なので、同じ乱数列で叩くと
    pa の各点のすぐ隣に pb の点が来て最近傍距離が過小に出る恐れがある。
    """
    pa, _ = trimesh.sample.sample_surface(a, n, seed=SAMPLE_SEED)
    pb, _ = trimesh.sample.sample_surface(b, n, seed=SAMPLE_SEED + 1)
    d = cKDTree(np.asarray(pb)).query(np.asarray(pa), workers=-1)[0]
    return np.asarray(pa), d


def _generatrix_err(p: dict) -> dict[str, tuple[float, float]]:
    """胴の母線が法則 `outer_radius` からどれだけ外れるか (rms, 符号つき最大ずれ)。

    ソリッドもメッシュも経由せず母線そのもので測る。2つの表現の本質的な差はここで、
    多角形（`body_stations` の折れ線）は弦が内側を通るので**常に痩せる側**、
    スプライン（`body_segments`）は内挿誤差なので両側に出る。

    メッシュ越しに測ろうとすると分解能に負ける: STL 化の許容 0.02mm が誤差と同程度で、
    しかもプリミティブ版は 1 面が広いぶん頂点が疎になる（帯に数点しか入らず nan になった）。
    """
    from build123d import Edge, Vector

    zq = np.linspace(0.0, p["overall_length"], 4000)
    rq = np.array([P.outer_radius(p, z) for z in zq])
    zs = P.body_stations(p)
    e_poly = np.interp(zq, zs, [P.outer_radius(p, z) for z in zs]) - rq

    e_spl: list[float] = []
    for seg in P.body_segments(p):
        if len(seg) < 3:
            continue                       # 直線区間は法則そのもの
        edge = Edge.make_spline([Vector(r, 0.0, z) for (z, r) in seg])
        for i in range(401):
            v = edge.position_at(i / 400.0)
            e_spl.append(v.X - P.outer_radius(p, v.Z))

    def stat(e):
        e = np.asarray(e)
        return float(np.sqrt((e ** 2).mean())), float(e[np.argmax(np.abs(e))])

    return {"poly": stat(e_poly), "spline": stat(e_spl)}


def _pair_dev(a: trimesh.Trimesh, b: trimesh.Trimesh) -> np.ndarray:
    """a の頂点から b 表面への厳密距離。同じ設計の2表現を突き合わせる用。

    `_surface_dev` の KDTree 近似はサンプル間隔（≈0.15mm）が分解能なので、
    0.05mm 台の差を見るここでは使えない。
    """
    return trimesh.proximity.closest_point(b, a.vertices)[1]


def _continuity(p: dict) -> list[tuple]:
    """空洞3法則の傾きと、隣接区間での傾きジャンプ。

    内部に見える棚・縦壁・段差は例外なく「区間ごとに別の式を継いだ所で傾きが飛ぶ」
    ことの現れなので、形状を目視する前にここで数値化しておく。合否は課さない
    （実物との一致が合格ラインで、こちらはその内訳を説明するための指標）。
    """
    st = P.cavity_stations(p)
    rows = []
    slopes = []
    for a, b in zip(st, st[1:]):
        dz = b["z"] - a["z"]
        slopes.append((
            0.5 * (a["z"] + b["z"]),
            (b["w"] - a["w"]) / 2.0 / dz,
            ((b["yc"] - b["h"] / 2) - (a["yc"] - a["h"] / 2)) / dz,
            ((b["yc"] + b["h"] / 2) - (a["yc"] + a["h"] / 2)) / dz,
        ))
    for (z0, w0, f0, c0), (z1, w1, f1, c1) in zip(slopes, slopes[1:]):
        rows.append((0.5 * (z0 + z1), abs(w1 - w0), abs(f1 - f0), abs(c1 - c0)))
    return rows


def _rail_curves(mesh, z_lo=0.10, z_hi=6.0, dz=0.05, dx=0.02, flat=0.06):
    """リード面を真下から見た2本の輪郭を測る → (zs, 窓の縁 x, 先端輪郭 x)。

    各 z で下から +Y レイを打ち、最初に当たる面の高さ y(x) を見る。リード面は
    x 方向に真っ平ら（母線が X に平行な円筒）なので、y(x) は

        窓（天井＝高い） → **レール（リード面＝最低の平坦部）** → 弦の外（胴の丸み＝上がる）

    という形になる。**最小値の平坦部がレールそのもの**なので、その内端が窓の縁、
    外端が先端輪郭（リード面が胴を切る弦）。しきい値としてリード面の高さを
    別途フィットする必要が無く、実物とモデルで同じ判定になる（`facing_fit` は
    裾だけの2母数フィットが条件不良で、ティップへ外挿すると 0.15mm ずれる）。
    """
    xs = np.arange(0.03, 10.0, dx)
    zs, we, ce = [], [], []
    for z in np.arange(z_lo, z_hi, dz):
        o = np.stack([xs, np.full(len(xs), -40.0), np.full(len(xs), z)], 1)
        d = np.tile([0.0, 1.0, 0.0], (len(xs), 1))
        locs, idx, _ = mesh.ray.intersects_location(o, d)
        first: dict[int, float] = {}
        for loc, i in zip(locs, idx):
            if i not in first or loc[1] < first[i]:
                first[i] = float(loc[1])
        y = np.array([first.get(i, np.nan) for i in range(len(xs))])
        ok_ = np.isfinite(y)
        if ok_.sum() < 10:
            continue
        i0 = int(np.nanargmin(np.where(ok_, y, np.inf)))
        lo = hi = i0
        while lo - 1 >= 0 and ok_[lo - 1] and y[lo - 1] <= y[i0] + flat:
            lo -= 1
        while hi + 1 < len(xs) and ok_[hi + 1] and y[hi + 1] <= y[i0] + flat:
            hi += 1
        zs.append(float(z))
        # lo == 0 はまだ窓が開いていない（レールが x=0 まで続く）
        we.append(float(xs[lo]) if lo > 0 else float("nan"))
        ce.append(float(xs[hi]))
    return np.asarray(zs), np.asarray(we), np.asarray(ce)


def _rail_widths(zs, we, ce):
    """窓の縁から先端輪郭への**垂直距離**（z 一定で測ると弧の傾きぶん過大に出る）。

    先端輪郭は窓が開く前の z まで含めて全部使う。ここを切り詰めると、輪郭が
    急に立ち上がるティップ側で最短点を取り逃して距離が数 mm 過大に出る。
    """
    return np.asarray([np.min(np.hypot(ce - x, zs - z)) if np.isfinite(x)
                       else np.nan for z, x in zip(zs, we)])


def _tip_arc_z(p: dict) -> tuple[float, float]:
    """ティップ弧の z 範囲。弦が最大幅の 94% に達するまでが「先端が回り込む」区間。

    そこから先はサイドレールで、`side_rail_width` が支配する別の量になる。実物と
    モデルで同じ区間を見るため、範囲はメッシュではなく解析式から決める。
    """
    zb = P.bore_start_z(p)
    zs = np.arange(0.05, min(12.0, zb), 0.01)
    ch = np.array([P.reed_chord(p, z) / 2.0 for z in zs])
    lim = 0.94 * float(ch.max())
    return float(P.window_open_z(p)), float(zs[np.argmax(ch >= lim)])


def _tip_face_height(mesh, x_half=1.0, z_hi=0.02) -> float:
    """先端前面（z≈0 の面）の高さ [mm]。クラウン付近だけを見る。

    実物はリード面側から面取りされていて、ここが 0.25mm しかない。面取りが無いと
    `tip_rail_thickness` ぶん（テナーで 1.25mm）の角ばった壁が先端に立ち、
    その両端が 90°近い稜線として見える。
    """
    v = mesh.vertices
    s = (np.abs(v[:, 0]) <= x_half) & (v[:, 2] <= mesh.bounds[0][2] + z_hi)
    if int(s.sum()) < 3:
        return float("nan")
    return float(v[s, 1].max() - v[s, 1].min())


def _tip_face_profile(mesh, x=0.0, z_hi=0.5, dz=0.02):
    """x 一定での先端の縦断面（z, 上面 y, 下面 y）。面取りの形を図に出すため。"""
    zs = np.arange(mesh.bounds[0][2] + 1e-3, z_hi, dz)
    o = np.stack([np.full(len(zs), x), np.full(len(zs), -40.0), zs], 1)
    d = np.tile([0.0, 1.0, 0.0], (len(zs), 1))
    locs, idx, _ = mesh.ray.intersects_location(o, d)
    lo: dict[int, float] = {}
    hi: dict[int, float] = {}
    for loc, i in zip(locs, idx):
        y = float(loc[1])
        if i not in lo or y < lo[i]:
            lo[i] = y
        if i not in hi or y > hi[i]:
            hi[i] = y
    return (zs,
            np.array([hi.get(i, np.nan) for i in range(len(zs))]),
            np.array([lo.get(i, np.nan) for i in range(len(zs))]))


def _tip_arc_stats(mesh, p):
    """ティップ弧に沿ったレール幅の (平均, ばらつき, 本数)。"""
    z0, z1 = _tip_arc_z(p)
    zs, we, ce = _rail_curves(mesh)
    if len(zs) < 6:
        return float("nan"), float("nan"), 0
    d = _rail_widths(zs, we, ce)
    m = np.isfinite(d) & (zs >= z0) & (zs <= z1)
    if m.sum() < 4:
        return float("nan"), float("nan"), 0
    return float(d[m].mean()), float(d[m].max() - d[m].min()), int(m.sum())


def main():
    ref = meshdiff.load_mesh(str(REF_STL))
    comp, p = _load("tenor")
    t_poly = time.time()
    part = comp.build(p)
    t_poly = time.time() - t_poly
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

    # ---- ティップレール（先端曲線に沿う一定幅の帯になっているか）
    #      旧実装はロフト前端が z 一定の平面だったため窓の前縁が直線になり、
    #      コーナーでレール幅が 0.02mm まで痩せていた。
    rail_r = _tip_arc_stats(ref, p)
    rail_m = _tip_arc_stats(model, p)
    ok &= chk("ティップレール幅 平均", rail_m[0], rail_r[0], 0.15)
    ok &= chk("ティップレール幅 ばらつき", rail_m[1], rail_r[1], 0.20)
    face_r, face_m = _tip_face_height(ref), _tip_face_height(model)
    ok &= chk("先端前面の高さ", face_m, face_r, 0.15)

    # ---- ウィンドウ輪郭（FreeCAD で先端が点に潰れていた箇所。形状の主目的なので必ず見る）
    #      dx は既定の 0.2mm だと縁がグリッドをまたぐたび ±0.2mm 量子化されて
    #      系統差に見える（実体は 0.06mm）。両者とも 0.05mm で測る。
    zwr, wwr, _, _ = window_outline(ref, a_r, b_r, dx=0.05)
    zwm, wwm, _, _ = window_outline(model, a_m, b_m, dx=0.05)
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

    # ---- 断面法則の傾き不連続（診断のみ・合否は課さない）
    #      内部の棚・縦壁・段差はすべて「隣接ステーション間で傾きが飛ぶ」ことの
    #      現れなので、形を見る前にここで数値として出しておく。
    cont = _continuity(p)

    # ---- STEP 用プリミティブ表現（Stage C-2）
    #      面の張り方だけ替えた版。同じ合格ラインを通ること＋面が畳めていることを見る。
    #      ここで書き出す STEP を `check_step_cad.py` が FreeCAD で読んでフィレットを試す。
    t_cad = time.time()
    part_cad = comp.build_cad(p)
    t_cad = time.time() - t_cad
    # 生成時間は**レポートに入れない**。実行のたびに数秒動くので、形状を一切変えずに
    # 2 回走らせるだけで verify_report.md に差分が出てしまい、「本当に形が変わったのか」
    # がレビューで判別できなくなる。見たい人には標準出力で出す。
    print("build: 多角形 %.1fs / プリミティブ %.1fs" % (t_poly, t_cad), flush=True)
    model_cad = meshdiff.part_to_mesh(part_cad, tolerance=0.02)
    export_model(part_cad, OUT_STEP, "step")
    faces_cad = part_cad.faces()
    kinds_cad = collections.Counter(
        str(f.geom_type).split(".")[-1] for f in faces_cad)
    slivers_cad = sum(1 for f in faces_cad if f.area < 0.5)

    a_c, b_c, _ = table_plane(model_cad)
    rail_c = _tip_arc_stats(model_cad, p)
    ok &= chk("[CAD] ティップレール幅 平均", rail_c[0], rail_r[0], 0.15)
    ok &= chk("[CAD] ティップレール幅 ばらつき", rail_c[1], rail_r[1], 0.20)
    ok &= chk("[CAD] 先端前面の高さ", _tip_face_height(model_cad), face_r, 0.15)
    zwc, wwc, _, _ = window_outline(model_cad, a_c, b_c, dx=0.05)
    sc = window_span(zwc, wwc)
    ok &= chk("[CAD] 窓 開始 z", sc[0], sr[0], TOL["window_z"])
    ok &= chk("[CAD] 窓 終端 z", sc[1], sr[1], TOL["window_z"])
    ok &= chk("[CAD] 材料体積", float(model_cad.volume) / 1000.0, v_ref,
              0.05 * v_ref, "cc")
    # 多角形版との差。残るのは多角形版の近似（母線の弦誤差・ルールドの断面間補間）で、
    # 向きは常に「プリミティブ版の方が法則に近い」。
    d_cad = _pair_dev(model_cad, model)
    ok &= chk("[CAD] 多角形版との表面差 p95", float(np.percentile(d_cad, 95)), 0.0, 0.08)
    ok &= chk("[CAD] 面数", float(len(faces_cad)), 0.0, 100.0, "面")
    ok &= chk("[CAD] 微小面(<0.5mm²)", float(slivers_cad), 0.0, 5.0, "枚")
    gen = _generatrix_err(p)
    rad_poly, rad_cad = gen["poly"], gen["spline"]
    ok &= chk("[CAD] 胴母線の法則からの誤差 rms", rad_cad[0], 0.0, 0.002)
    ok &= chk("[CAD] 胴母線の法則からの最大ずれ", abs(rad_cad[1]), 0.0, 0.01)

    # ---- 他サイズがビルド＆シミュレートできること
    sizes = []
    for size in ("tenor", "alto", "soprano"):
        c, pp = _load(size)
        s = c.build(pp)
        sim = c.simulate(pp)
        sizes.append((size, float(s.volume), len(s.solids()),
                      bool(sim.get("tier1")), bool(s.is_valid)))
        ok &= s.volume > 1000.0
        ok &= bool(s.is_valid)          # OCCT が健全と認めるソリッドであること

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
    lines += ["", "## STEP 用プリミティブ表現（Stage C-2）", "",
              "`build_cad()` は同じ `profiles.py` から、面の張り方だけを替えて組む。",
              "FreeCAD で外周面を選んでフィレットを掛けられるようにするための表現で、",
              "STEP 出力のときだけ使う（`build()` は対話用に多角形のまま）。", "",
              "| | 多角形版 `build()` | プリミティブ版 `build_cad()` |",
              "|---|---|---|",
              "| 面数 | %d | **%d** |" % (len(part.faces()), len(faces_cad)),
              "| 微小面 (<0.5mm²) | – | %d |" % slivers_cad,
              "| ソリッド体積 | %.1f mm³ | %.1f mm³ (%+.3f%%) |" % (
                  part.volume, part_cad.volume,
                  100.0 * (part_cad.volume - part.volume) / part.volume), "",
              "面の内訳: " + " / ".join("%s %d" % kv for kv in sorted(kinds_cad.items())),
              "", "多角形版との表面距離: 平均 %.3f / p95 %.3f / 最大 %.3f mm。"
              % (float(d_cad.mean()), float(np.percentile(d_cad, 95)),
                 float(d_cad.max())),
              "残差はすべて**多角形版の近似**（母線の弦誤差・ルールドロフトの断面間補間）で、",
              "向きは常に「プリミティブ版の方が法則に近い」。胴の母線を法則と直接比べると、",
              "多角形は rms %.4f mm・最大 %+.3f mm（弦が内側を通るので常に痩せる側）、"
              % rad_poly,
              "スプラインは rms %.4f mm・最大 %+.3f mm。" % rad_cad, "",
              "## 3サイズのビルド", "",
              "| サイズ | ソリッド体積 mm³ | ソリッド数 | simulate | is_valid |",
              "|---|---|---|---|---|"]
    for size, vol, ns, sim, valid in sizes:
        lines.append("| %s | %.0f | %d | %s | %s |" % (size, vol, ns, sim, valid))
    worst = max(cont, key=lambda r: max(r[1], r[2], r[3])) if cont else None
    lines += ["", "## 断面法則の連続性（診断・合否なし）", "",
              "隣接区間での**傾きのジャンプ**。棚・縦壁・段差はこれが飛ぶ所に出る。", "",
              "| 指標 | 最大ジャンプ | 位置 z |", "|---|---|---|"]
    for i, name in ((1, "d(半幅)/dz"), (2, "d(床)/dz"), (3, "d(天井)/dz")):
        top = max(cont, key=lambda r: r[i])
        lines.append("| %s | %.3f | %.1f |" % (name, top[i], top[0]))
    if worst:
        lines.append("")
        lines.append("最悪地点 z=%.1f（旧実装は d(半幅)/dz が z=41 で 3.03 飛んでいた）"
                     % worst[0])
    lines += ["", "## ウィンドウ輪郭（リード開口の幅）", "",
              "| z | 実物 | モデル | 差 |", "|---|---|---|---|"]
    for z in zw[::2]:
        a_ = float(np.interp(z, zwr, wwr))
        b_ = float(np.interp(z, zwm, wwm))
        lines.append("| %.0f | %.2f | %.2f | %+.2f |" % (z, a_, b_, b_ - a_))
    lines += ["", "開口 z 範囲: 実物 %.1f–%.1f / モデル %.1f–%.1f"
              % (sr[0], sr[1], sm[0], sm[1]),
              "", "## ティップレール（先端曲線に沿う帯の幅）", "",
              "窓の縁から先端輪郭への**垂直距離**。弧の範囲は z = %.2f–%.2f"
              % _tip_arc_z(p),
              "（弦が最大幅の 94%% に達するまで。そこから先はサイドレール）。"
              "設計値 `tip_rail_width` = %.2f mm。" % p["tip_rail_width"], "",
              "| | 平均 | ばらつき(最大−最小) | 測定点数 |", "|---|---|---|---|",
              "| 実物 | %.3f mm | %.3f mm | %d |" % rail_r,
              "| モデル | %.3f mm | %.3f mm | %d |" % rail_m, ""]
    zs_m, we_m, ce_m = _rail_curves(model)
    zs_r, we_r, ce_r = _rail_curves(ref)
    dm_, dr_ = _rail_widths(zs_m, we_m, ce_m), _rail_widths(zs_r, we_r, ce_r)
    lines += ["| z | 実物 窓縁 | モデル 窓縁 | 実物 レール | モデル レール |",
              "|---|---|---|---|---|"]
    for z in np.arange(1.0, 5.01, 0.25):
        if len(zs_r) == 0 or len(zs_m) == 0:
            break
        lines.append("| %.2f | %.2f | %.2f | %.3f | %.3f |" % (
            z, float(np.interp(z, zs_r, we_r)), float(np.interp(z, zs_m, we_m)),
            float(np.interp(z, zs_r, dr_)), float(np.interp(z, zs_m, dm_))))
    lines += ["", "## 先端前面（ティップ前縁の面取り）", "",
              "実物はリード面側から面取りされていて、z=0 の前面は %.2f mm しかない。"
              % face_r,
              "面取りが無いと `tip_rail_thickness` ぶんの角ばった壁が立ち、その両端が"
              "90°近い稜線として見える。", "",
              "| | 前面の高さ (x≈0) |", "|---|---|",
              "| 実物 | %.3f mm |" % face_r, "| モデル | %.3f mm |" % face_m, "",
              "x=0 の縦断面（上面 / 下面の y）:", "",
              "| z | 実物 上 | モデル 上 | 実物 下 | モデル 下 |",
              "|---|---|---|---|---|"]
    zt_r, up_r, dn_r = _tip_face_profile(ref)
    zt_m, up_m, dn_m = _tip_face_profile(model)
    for z in np.arange(0.02, 0.41, 0.04):
        lines.append("| %.2f | %.2f | %.2f | %.2f | %.2f |" % (
            z, float(np.interp(z, zt_r, up_r)), float(np.interp(z, zt_m, up_m)),
            float(np.interp(z, zt_r, dn_r)), float(np.interp(z, zt_m, dn_m))))
    lines += [
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
