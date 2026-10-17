# -*- coding: utf-8 -*-
"""WindyCity Tenor 3mf → SaxSketch パラメータ実測フィット＋候補3案生成。

実在マウスピース（WindyCity Tenor .100" Long Shank の 3mf メッシュ）を
SaxSketch 座標系（z=0 ティップ / z=L シャンク / +Y ビーク / −Y テーブル）へ整列し、
レイキャスト・表面サンプルで各部寸法を実測して、SaxSketch のパラメータ一式へ
フィットさせる。フィット方針の異なる3案のテンプレート JSON と、実測根拠の
レポート（fit_report.md）、FreeCAD 重ね合わせ用の整列済み STL を出力する。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/fit_windycity.py

外部メッシュは設計プロファイルの事前知識なしに測るため、
measure.py（自アプリ往復用・座標系凍結前提）とは別実装。手法は同系統
（テーブル平面基準・レイ走査・p95回帰）で、整列だけ align.axis_align に
テーブル検出による roll 解決を足している。
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import trimesh

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

from saxsketch.analysis import align, meshdiff  # noqa: E402
from saxsketch.instruments.saxophone.components import profiles  # noqa: E402

#: 基準 3mf（リポジトリには入っていない。出所は `../ATTRIBUTION.md`）。
SRC_DEFAULT = os.environ.get("WINDYCITY_3MF", "")
TENOR_JSON = _REPO / "saxsketch/instruments/saxophone/templates/tenor.json"

#: スキーマの (min, max, step)。mouthpiece.py::_specs と同値（クランプ判定用）。
SCHEMA = {
    "tip_opening": (1.0, 3.2, 0.05),
    "facing_length": (16.0, 30.0, 0.5),
    "tip_rail_width": (0.5, 2.0, 0.1),
    "side_rail_width": (0.6, 2.0, 0.1),
    "baffle_height": (0.0, 5.0, 0.1),
    "rollover_radius": (3.0, 20.0, 0.5),
    "throat_ratio": (0.60, 1.35, 0.01),
    "chamber_ratio": (1.00, 3.00, 0.05),
    "bore_length": (18.0, 60.0, 1.0),
    "window_length": (24.0, 44.0, 0.5),
    "reed_width": (10.0, 18.0, 0.1),
    "body_dia": (20.0, 34.0, 0.1),
    "overall_length": (70.0, 130.0, 0.5),
    "bore_dia": (None, None, 0.05),   # テンプレ値±1mm なので候補では自由
    "beak_height": (None, None, 0.5),  # 範囲は 0.35〜0.75×body_dia（動的にクランプ）
}


def clamp_round(key: str, val: float, clamps: list[str]) -> float:
    lo, hi, step = SCHEMA[key]
    v = round(val / step) * step
    if lo is not None and v < lo:
        clamps.append(f"{key}: 実測 {val:.3f} → 下限 {lo} にクランプ")
        v = lo
    if hi is not None and v > hi:
        clamps.append(f"{key}: 実測 {val:.3f} → 上限 {hi} にクランプ")
        v = hi
    return round(v, 4)


def batch_first_hits(mesh, origins, dirs):
    """レイごとの最初のヒット位置（なければ None）。1回の呼び出しでバッチ処理。"""
    o = np.asarray(origins, float)
    d = np.asarray(dirs, float)
    locs, idx_ray, _ = mesh.ray.intersects_location(o, d)
    best: dict[int, tuple[float, np.ndarray]] = {}
    for loc, ir in zip(locs, idx_ray):
        dist = float(np.linalg.norm(loc - o[ir]))
        if ir not in best or dist < best[ir][0]:
            best[ir] = (dist, loc)
    return [best.get(i, (None, None))[1] for i in range(len(origins))]


# ------------------------------------------------------------------ 整列

def refine_axis(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """シャンク側リング断面の中心列に主軸を合わせ、ボア軸を x=y=0 に載せる。

    axis_align の PCA 軸は非対称形状（テーブルカット）の影響でボア軸から僅かに
    ずれる。シャンク側 30mm はほぼ回転体なのでリング中心列が真のボア軸を与える。
    頂点は疎で偏るため表面サンプル点で中心を取り、補正は微小角のみ許す。
    """
    for _ in range(2):
        pts, _ = trimesh.sample.sample_surface(mesh, 80_000)
        pts = np.asarray(pts)
        zmax = float(pts[:, 2].max())
        centers = []
        for zc in np.linspace(zmax - 30.0, zmax - 4.0, 9):
            m = np.abs(pts[:, 2] - zc) < 1.5
            if m.sum() < 200:
                continue
            centers.append((zc, float(pts[m, 0].mean()), float(pts[m, 1].mean())))
        if len(centers) < 5:
            return mesh
        zs = np.array([c[0] for c in centers])
        xs = np.array([c[1] for c in centers])
        ys = np.array([c[2] for c in centers])
        sx = float(np.polyfit(zs, xs, 1)[0])
        sy = float(np.polyfit(zs, ys, 1)[0])
        # 軸方向 (sx, sy, 1) を +Z へ回す。大きな補正はフィット不良なのでかけない
        tilt = math.hypot(sx, sy)
        if tilt > math.tan(math.radians(3.0)):
            return mesh
        v = np.array([sx, sy, 1.0])
        v /= np.linalg.norm(v)
        axis = np.cross(v, [0.0, 0.0, 1.0])
        s = np.linalg.norm(axis)
        if s > 1e-9:
            ang = math.asin(min(s, 1.0))
            T = trimesh.transformations.rotation_matrix(ang, axis / s)
            mesh.apply_transform(T)
        # 軸線（シャンク中央）を x=y=0 へ
        pts, _ = trimesh.sample.sample_surface(mesh, 40_000)
        pts = np.asarray(pts)
        zmax = float(pts[:, 2].max())
        m = np.abs(pts[:, 2] - (zmax - 15.0)) < 3.0
        cx, cy = float(pts[m, 0].mean()), float(pts[m, 1].mean())
        mesh.apply_translation([-cx, -cy, 0.0])
    return mesh


def solve_roll(mesh: trimesh.Trimesh, report: dict) -> trimesh.Trimesh:
    """テーブル面の向きを −Y へ回す（Z 軸まわりの roll 解決）。

    「最大の平坦領域＝テーブル」は成り立たない（WindyCity 実物は側面ファセットや
    背面下部の平面を持ち、そちらの方が広い）。代わりに**ティップの楔**を使う:
    楔（z<2mm の薄い断面）の薄い方向がテーブル法線の方向で、2つある向きのうち
    「サイドレール／テーブルがその平面上に乗る」側が本物。判定は候補面レベルの
    近傍ヒット率（レール面は平面上、ビーク側は平面から離れて曲がる）で行う。
    """
    pts, _ = trimesh.sample.sample_surface(mesh, 120_000)
    pts = np.asarray(pts)

    tip = pts[pts[:, 2] < 2.0]
    if len(tip) < 200:
        raise RuntimeError("ティップ近傍のサンプル点が不足しています")
    xy = tip[:, :2] - tip[:, :2].mean(axis=0)
    w, v = np.linalg.eigh(xy.T @ xy / len(xy))
    thin = v[:, 0]                            # 最小分散 = 楔の薄い方向

    zmax = float(pts[:, 2].max())

    def window_frac(nh):
        """楔面（レール面）レベルより 1.5mm 以上深くまで届く中心線レイの割合。

        テーブル側: 窓を素通りして空洞天井（面より内側）に届く → 高い。
        ビーク側: ビーク斜面が楔面より外側に張り出しており、面レベルの手前で
        当たる → ほぼ 0。
        """
        level = float(np.percentile(tip[:, :2] @ nh, 98.0))
        origins, dirs = [], []
        for z in np.arange(0.12 * zmax, 0.35 * zmax, 2.0):
            o2 = nh * (level + 8.0)
            origins.append([o2[0], o2[1], float(z)])
            dirs.append([-nh[0], -nh[1], 0.0])
        hits = batch_first_hits(mesh, origins, dirs)
        levels = [float(np.asarray(h)[:2] @ nh) for h in hits if h is not None]
        if not levels:
            return 0.0
        return sum(1 for lv in levels if lv < level - 1.5) / len(levels)

    f_pos = window_frac(thin)
    f_neg = window_frac(-thin)
    report["roll_sign"] = {"window_frac_pos": round(f_pos, 3),
                           "window_frac_neg": round(f_neg, 3)}
    if max(f_pos, f_neg) < 0.3:
        raise RuntimeError("テーブル側（ウィンドウ開口）を判定できませんでした")
    nh = thin if f_pos >= f_neg else -thin

    # 粗回転: nh → (0,-1,0)
    ang = -math.pi / 2.0 - math.atan2(nh[1], nh[0])
    mesh.apply_transform(trimesh.transformations.rotation_matrix(ang, [0, 0, 1]))

    # 精密化: テーブル/レール平坦点（下向き法線・レール面レベル近傍）の法線平均で微修正
    pts, fidx = trimesh.sample.sample_surface(mesh, 120_000)
    pts = np.asarray(pts)
    nrm = mesh.face_normals[np.asarray(fidx)]
    level = float(np.percentile(pts[pts[:, 2] < 2.0][:, 1], 2.0))  # レール下面 y
    sel = ((nrm[:, 1] < -0.9) & (np.abs(nrm[:, 2]) < 0.3)
           & (pts[:, 2] > 4.0) & (pts[:, 2] < 40.0)
           & (np.abs(pts[:, 1] - level) < 2.5))
    if sel.sum() >= 100:
        n_ref = nrm[sel].mean(axis=0)
        n_ref[2] = 0.0
        n_ref /= np.linalg.norm(n_ref)
        ang2 = -math.pi / 2.0 - math.atan2(n_ref[1], n_ref[0])
        if abs(ang2) < math.radians(15.0):
            mesh.apply_transform(
                trimesh.transformations.rotation_matrix(ang2, [0, 0, 1]))
        # テーブル平面 y（レール/テーブル平坦点の中央値）
        pts2 = pts.copy()
        c, s = math.cos(ang2), math.sin(ang2)
        pts2[:, 0], pts2[:, 1] = (c * pts[:, 0] - s * pts[:, 1],
                                  s * pts[:, 0] + c * pts[:, 1])
        table_y = float(np.median(pts2[sel, 1]))
        n_plane = int(sel.sum())
    else:
        table_y = level
        n_plane = 0
        report.setdefault("warnings", []).append(
            "テーブル平坦点が少なく、roll の微修正を省略しました。")
    report["roll"] = {"plane_points": n_plane,
                      "table_y_mm": round(table_y, 3)}
    return mesh


def _ensure_shank_at_high_z(mesh: trimesh.Trimesh, report: dict) -> trimesh.Trimesh:
    """シャンク（太い端）を +Z へ。axis_align の端面判定は頂点密度が疎な端で
    点数不足（<30）になり半径 0 と誤判定するため、サンプル点で自前判定する。"""
    pts, _ = trimesh.sample.sample_surface(mesh, 60_000)
    pts = np.asarray(pts)
    zmin, zmax = float(pts[:, 2].min()), float(pts[:, 2].max())

    def band_r90(lo, hi):
        m = (pts[:, 2] >= lo) & (pts[:, 2] <= hi)
        xy = pts[m, :2] - pts[m, :2].mean(axis=0)
        return float(np.percentile(np.hypot(xy[:, 0], xy[:, 1]), 90))

    r_lo = band_r90(zmin + 2.0, zmin + 7.0)
    r_hi = band_r90(zmax - 7.0, zmax - 2.0)
    if r_hi < r_lo:   # 細い端（ティップ）が +Z に居る → 反転
        mesh.apply_transform(np.diag([1.0, -1.0, -1.0, 1.0]))
        report.setdefault("warnings", []).append(
            f"軸向きを自前判定で反転（端面半径 tip={r_hi:.1f} / shank={r_lo:.1f}mm）")
    report["end_radii_mm"] = {"low_z": round(r_lo, 2), "high_z": round(r_hi, 2)}
    return mesh


def align_to_saxsketch(mesh: trimesh.Trimesh, report: dict) -> trimesh.Trimesh:
    aligned, _, info = align.axis_align(mesh)
    report["axis_align"] = info
    aligned = _ensure_shank_at_high_z(aligned, report)
    aligned = refine_axis(aligned)
    # シャンクは +Z のまま。z=0 をティップ端へ（solve_roll はティップ帯 z<2 を使う）
    zmin = float(aligned.bounds[0][2])
    aligned.apply_translation([0.0, 0.0, -zmin])
    aligned = solve_roll(aligned, report)
    # 妥当性: ティップ近傍はテーブル側（y が小さい）にあるはず
    av = np.asarray(aligned.vertices)
    tipband = av[av[:, 2] < 2.0]
    if len(tipband) and float(tipband[:, 1].mean()) > 0.0:
        report.setdefault("warnings", []).append(
            "ティップ近傍が +Y 側にあります。roll 解決を確認してください。")
    return aligned


# ------------------------------------------------------------------ 実測

def measure(mesh: trimesh.Trimesh, report: dict) -> dict:
    """整列済みメッシュから実測値 {key: value} と根拠を返す。"""
    av = np.asarray(mesh.vertices)
    L = float(av[:, 2].max())
    pts, fidx = trimesh.sample.sample_surface(mesh, 150_000)
    pts = np.asarray(pts)
    nrm = mesh.face_normals[np.asarray(fidx)]

    m: dict[str, float] = {}
    how: dict[str, str] = {}
    warn: list[str] = report.setdefault("warnings", [])

    m["overall_length"] = L
    how["overall_length"] = "バウンディングボックス Z 長"

    # ---- ボディ径（リガチャー座帯の最大半径）
    seat0, seat1 = profiles.ligature_seat_range({"overall_length": L})
    band = (pts[:, 2] > seat0 + 1.0) & (pts[:, 2] < seat1 - 1.0)
    r = np.hypot(pts[band, 0], pts[band, 1])
    m["body_dia"] = 2.0 * float(np.percentile(r, 99.5))
    how["body_dia"] = f"座帯 z∈[{seat0:.0f},{seat1:.0f}] の半径 p99.5"

    # ---- テーブル平面（傾斜平面 y = a + b·z）
    # WindyCity 実物のテーブルはボア軸に対して傾いている（ティップ側が高く
    # ヒール側が低い）。SaxSketch のテーブルは軸平行なので、リード面基準の
    # 寸法（ティップ開き・フェイシング・ビーク高さ・バッフル天井）はすべて
    # この実測平面からの距離で取り、SaxSketch パラメータへ写像する。
    a_t, b_t = _fit_table_plane(pts, nrm, L)
    ty_at = lambda z: a_t + b_t * np.asarray(z, dtype=float)
    m["_table_plane"] = (a_t, b_t)
    how["_table_plane"] = "リード側下向き平坦点の下側包絡の頑健直線フィット"
    m["_table_tilt_deg"] = math.degrees(math.atan(b_t))
    how["_table_tilt_deg"] = "テーブル平面のボア軸に対する傾き（SaxSketch は 0°）"

    # ---- ボア径・ボア長（軸上内径プロファイルのプラトーから）
    prof = []
    for zc in np.arange(L - 3.0, L - 70.0, -1.5):
        dia = align.radial_inner_diameter(mesh, float(zc), (0.0, 0.0),
                                          max_r=m["body_dia"] / 2.0)
        prof.append((float(zc), dia))
    head = [d for _, d in prof[:8] if d is not None]
    if len(head) < 4:
        raise RuntimeError("シャンクボア径を測定できませんでした")
    m["bore_dia"] = float(np.median(head))
    how["bore_dia"] = "シャンク側 12mm の軸上内径プラトー中央値"
    z_end_bore = L - 60.0
    for zc, dia in prof:
        if dia is None or abs(dia - m["bore_dia"]) > 0.5:
            z_end_bore = zc + 1.5
            break
    m["bore_length"] = L - z_end_bore
    how["bore_length"] = "内径がプラトーから 0.5mm 以上外れる位置まで"
    m["_bore_profile"] = [(z, d) for z, d in prof]

    # ---- ウィンドウ（下方 +Y レイの開口走査。開判定はテーブル平面基準）
    zb = L - m["bore_length"]
    z_scan = np.arange(0.2, zb - 2.0, 0.2)
    origins = [[0.0, float(ty_at(z)) - 8.0, float(z)] for z in z_scan]
    hits = batch_first_hits(mesh, origins, [[0, 1, 0]] * len(origins))
    hit_y = np.array([np.nan if h is None else float(h[1]) for h in hits])
    open_mask = hit_y > (ty_at(z_scan) + 0.35)

    # 窓の後端: 開口の最後（後端側は table 平面上に閉じるので閾値で確実）
    open_idx = np.where(open_mask)[0]
    if len(open_idx) < 10:
        raise RuntimeError("ウィンドウ開口を検出できませんでした")
    z_open1 = float(z_scan[open_idx[-1]])

    # 窓の前端＝ティップレール後端: フェイシングの持ち上がりが閾値を超えるため
    # 下方レイでは判別できない。空洞の内側から −Z レイで前壁（レール裏）を打つ。
    z_probe = 4.0
    yc_probe = (float(hit_y[np.argmin(np.abs(z_scan - z_probe))])
                + float(ty_at(z_probe))) / 2.0
    hw = batch_first_hits(mesh, [[0.0, yc_probe, z_probe]], [[0, 0, -1]])[0]
    if hw is not None and 0.3 < float(hw[2]) < 3.5:
        z_start = float(hw[2])
        m["tip_rail_width"] = z_start - 0.2
        how["tip_rail_width"] = f"空洞内から前壁レイ z={z_start:.2f} − 0.2"
    else:
        z_start = 1.3
        m["tip_rail_width"] = 1.1
        how["tip_rail_width"] = "前壁を検出できず → 現行値継承"
        warn.append("ティップレール幅: 空洞前壁の検出に失敗、現行値を継承")

    m["window_length"] = (z_open1 - z_start) / 0.86
    how["window_length"] = (f"開口実測 {z_open1 - z_start:.1f}mm ÷ 0.86"
                            "（設計窓はステーション補間で t≈0.86 に閉じるため）")
    ceil_prof = [(float(z), float(y)) for z, y in zip(z_scan, hit_y)
                 if z_start + 0.3 <= z <= z_open1 and np.isfinite(y)
                 and y > ty_at(z) + 0.35]

    # ---- 窓幅（x 走査。開判定は「その z の下側基準からの持ち上がり」で行う。
    #      テーブル平面基準だとフェイシング区間のレール持ち上がりを開口と誤判定する）
    z_q = np.linspace(z_start + 1.5, z_open1 - 2.0, 14)
    xs = np.arange(-11.0, 11.01, 0.2)
    origins, meta = [], []
    for zq in z_q:
        for x in xs:
            origins.append([float(x), float(ty_at(zq)) - 8.0, float(zq)])
            meta.append((float(zq), float(x)))
    hits = batch_first_hits(mesh, origins, [[0, 1, 0]] * len(origins))
    prof_by_z: dict[float, list[tuple[float, float]]] = {}
    for (zq, x), h in zip(meta, hits):
        if h is not None:
            prof_by_z.setdefault(zq, []).append((x, float(h[1])))
    wprof = {}
    for zq, xy in prof_by_z.items():
        xy.sort()
        ys = np.array([y for _, y in xy])
        base = float(np.percentile(ys, 10.0))     # レール/テーブル面レベル
        # 開口 = x=0 を含む連続区間のみ（外側の丸い側面も base より上に出るため）
        xs_a = np.array([x for x, _ in xy])
        order = np.argsort(xs_a)
        open_flag = ys[order] > base + 0.7
        xs_s = xs_a[order]
        i0 = int(np.argmin(np.abs(xs_s)))
        if not open_flag[i0]:
            continue
        il = i0
        while il - 1 >= 0 and open_flag[il - 1]:
            il -= 1
        ih = i0
        while ih + 1 < len(xs_s) and open_flag[ih + 1]:
            ih += 1
        if ih - il > 2:
            wprof[zq] = float(xs_s[ih] - xs_s[il])
    if not wprof:
        raise RuntimeError("窓幅を測定できませんでした")
    half_w_at = lambda z: 0.5 * float(np.interp(z, sorted(wprof),
                                                [wprof[k] for k in sorted(wprof)]))
    # 設計窓幅: 窓前半 60% の中央値（後半はチェンバーへ開くため広く出る）
    front = [w for zq, w in wprof.items()
             if zq <= z_start + 0.6 * (z_open1 - z_start)]
    w_win = float(np.median(front if front else list(wprof.values())))
    m["_window_width"] = w_win
    how["_window_width"] = "下方レイ x 走査の開口幅（z毎基準+0.7mm超）、窓前半の中央値"

    # サイドレール幅: 実物はテーブルの平坦がレール外まで連続しており、レール
    # 外縁を幾何だけで一意に切り出せない → 現行値を継承し、リード幅を逆算する。
    m["side_rail_width"] = 1.1
    how["side_rail_width"] = "実測不能（テーブル平坦がレール外縁まで連続）→ 現行値継承"
    m["reed_width"] = w_win + 2.0 * m["side_rail_width"]
    how["reed_width"] = "窓幅 + 2×サイドレール幅（window_width 定義の逆算）"

    # ---- フェイシング（レール持ち上がりプロファイル → カーブモデルフィット）
    # レール rise は「x ビンごとの下面 y の局所最小」で取る。中央は窓越しの
    # バッフル、外側はエッジの丸みで高く出るため、レールの谷が最小になる。
    # プロファイルを楕円・円弧（radial）の両モデルにフィットし、残差の小さい方を
    # facing_curve として採用、facing_length と tip_opening を同時に解く。
    fpts, ffidx = trimesh.sample.sample_surface(mesh, 300_000)
    fpts = np.asarray(fpts)
    fnrm = mesh.face_normals[np.asarray(ffidx)]
    down = fnrm[:, 1] < -0.3
    rise_z, rise_v = [], []
    for z0 in np.arange(0.4, min(0.40 * L, z_open1 - 1.0), 0.5):
        band = down & (fpts[:, 2] >= z0) & (fpts[:, 2] < z0 + 0.5)
        bp = fpts[band]
        if len(bp) < 12:
            continue
        zc = z0 + 0.25
        x_lim = half_w_at(zc) + 1.6
        vals = []
        for xc in np.arange(-x_lim, x_lim + 0.01, 0.75):
            mm = np.abs(bp[:, 0] - xc) < 0.6
            if mm.sum() >= 3:
                vals.append(float(np.percentile(bp[mm, 1], 15.0)))
        if not vals:
            continue
        r = min(vals) - float(ty_at(zc))
        if -0.5 < r < 5.0:
            rise_z.append(float(zc))
            rise_v.append(r)
    if len(rise_z) < 20:
        raise RuntimeError("フェイシング面（レール持ち上がり）を検出できませんでした")
    zs_r = np.asarray(rise_z)
    rs_r = np.asarray(rise_v)

    def _curve_coef(kind, fl_c, tip_c, z):
        t = np.clip((fl_c - z) / fl_c, 0.0, 1.0)
        if kind == "elliptic":
            return 1.0 - np.sqrt(np.clip(1.0 - t * t, 0.0, 1.0))
        rr = (fl_c * fl_c + tip_c * tip_c) / (2.0 * tip_c)   # radial（円弧）
        return (rr - np.sqrt(np.maximum(rr * rr - (t * fl_c) ** 2, 0.0))) / tip_c

    best = None
    for kind in ("elliptic", "radial"):
        for fl_c in np.arange(14.0, 38.01, 0.25):
            for tip_c in np.arange(1.2, 3.4001, 0.05):
                coef = _curve_coef(kind, fl_c, float(tip_c), zs_r)
                c0 = float(np.mean(rs_r - tip_c * coef))
                err = float(np.mean((rs_r - tip_c * coef - c0) ** 2))
                if best is None or err < best[0]:
                    best = (err, kind, float(fl_c), float(tip_c), c0)
    fit_rmse, kind, fl, tip, c0 = best
    fit_rmse = math.sqrt(fit_rmse)
    m["facing_length"] = fl
    how["facing_length"] = (f"レール rise {len(zs_r)} 点のカーブフィット"
                            f"（{kind}, RMSE {fit_rmse:.3f}mm, 平面補正 {c0:+.2f}mm）")
    m["tip_opening"] = tip
    how["tip_opening"] = "同上（カーブフィットの tip）"
    m["facing_curve"] = kind
    how["facing_curve"] = "楕円/円弧の両モデル残差比較"
    m["_facing_rise"] = list(zip(rise_z, rise_v))
    if abs(c0) > 0.6:
        warn.append(f"テーブル平面とフェイシングの整合が悪い（補正 {c0:+.2f}mm）。")
    if fit_rmse > 0.25:
        warn.append(f"フェイシングカーブのフィット残差が大きい（RMSE {fit_rmse:.2f}mm）。"
                    "実物のカーブは楕円/円弧のどちらにも厳密には一致しません。")

    # ---- ビーク高さ（上面 p95 のビン回帰 @ 0.25L、テーブル平面基準）
    top = (nrm[:, 1] > 0.5) & (pts[:, 2] > 0.20 * L) & (pts[:, 2] < 0.28 * L)
    bz, by = [], []
    for b0 in np.arange(0.20 * L, 0.28 * L, 1.0):
        mm = (pts[top, 2] >= b0) & (pts[top, 2] < b0 + 1.0)
        if mm.sum() >= 15:
            bz.append(b0 + 0.95)
            by.append(float(np.percentile(pts[top][mm, 1], 95.0)))
    a, b = np.polyfit(bz, by, 1)
    m["beak_height"] = float(a * 0.25 * L + b) - float(ty_at(0.25 * L))
    how["beak_height"] = "ビーク斜面 p95 回帰 @ z=0.25L − テーブル平面"

    # ---- 内部断面プロファイル（窓終端〜シャンク。レイ多角形の面積）
    sec = _internal_sections(mesh, z_open1 + 1.0, L - 2.0, float(ty_at(z_open1)))
    m["_sections"] = sec
    a_bore = math.pi * (m["bore_dia"] / 2.0) ** 2
    closed = [s for s in sec if s["area"] is not None]
    pre_bore = [s for s in closed if s["z"] < zb - 1.0]
    if not pre_bore:
        raise RuntimeError("チェンバー区間の閉断面を測定できませんでした")
    s_throat = min(pre_bore, key=lambda s: s["area"])
    s_chamber = max(pre_bore, key=lambda s: s["area"])
    m["throat_ratio"] = s_throat["area"] / a_bore
    how["throat_ratio"] = (f"最狭断面積 {s_throat['area']:.1f}mm² @z={s_throat['z']:.1f}"
                           f" ÷ ボア断面積 {a_bore:.1f}mm²")
    m["chamber_ratio"] = s_chamber["area"] / s_throat["area"]
    how["chamber_ratio"] = (f"最大断面積 {s_chamber['area']:.1f}mm² @z={s_chamber['z']:.1f}"
                            " ÷ 最狭断面積")
    m["_chamber_station"] = s_chamber
    m["_throat_station"] = s_throat

    # 閉領域の実測内容積（台形積分）— 案3の突き合わせ用
    zs = [s["z"] for s in closed]
    ars = [s["area"] for s in closed]
    m["_closed_volume_cc"] = float(np.trapezoid(ars, zs)) / 1000.0
    how["_closed_volume_cc"] = f"閉領域 z∈[{zs[0]:.1f},{zs[-1]:.1f}] の断面積積分"

    # ---- チェンバー形状分類
    m["chamber_shape"], shape_scores = _classify_chamber(s_chamber)
    how["chamber_shape"] = "断面レイ16方向 vs 4形状テンプレの残差最小: " + \
        ", ".join(f"{k}={v:.3f}" for k, v in sorted(shape_scores.items(),
                                                    key=lambda kv: kv[1]))

    # ---- バッフル（種別×高さのグリッド探索。天井プロファイル一致）
    # 天井はテーブル平面（リード面）からの高さで持つ。モデル側もモデルの
    # テーブルからの高さで比較する（リード基準＝音響的に効く量で合わせる）。
    m["_ceil_profile"] = [(z, y - float(ty_at(z))) for z, y in ceil_prof]
    return m, how


def _fit_table_plane(pts, nrm, L) -> tuple[float, float]:
    """テーブル平面 y = a + b·z の頑健フィット。

    リード側の下向き平坦点の**下側包絡**（z ビンごとの低位パーセンタイル）を
    直線フィットする。窓越しに見えるバッフル天井（下向き法線だが平面より上）や
    フェイシングの持ち上がりは、包絡＋残差フィルタで自然に外れる。
    """
    sel = (nrm[:, 1] < -0.85) & (np.abs(pts[:, 0]) < 11.0)
    zb_, yb_ = [], []
    # 0.72L 以降はシャンクの丸い底がテーブル平面より上に入り込み回帰を汚す
    for z0 in np.arange(20.0, 0.72 * L, 2.0):
        mask = sel & (pts[:, 2] >= z0) & (pts[:, 2] < z0 + 2.0)
        if mask.sum() < 25:
            continue
        zb_.append(z0 + 1.0)
        yb_.append(float(np.percentile(pts[mask, 1], 4.0)))
    if len(zb_) < 6:
        raise RuntimeError("テーブル平面のフィットに必要な平坦点が不足しています")
    zb_, yb_ = np.asarray(zb_), np.asarray(yb_)
    b, a = np.polyfit(zb_, yb_, 1)
    for _ in range(2):
        res = np.abs(yb_ - (a + b * zb_))
        keep = res < max(0.35, 2.0 * float(np.median(res)))
        if keep.sum() < 6:
            break
        b, a = np.polyfit(zb_[keep], yb_[keep], 1)
    return float(a), float(b)


def _internal_sections(mesh, z0, z1, ty, n_z=60, n_ray=16):
    """z ∈ [z0, z1] の内部空洞断面（16方向レイ多角形）。開口/測定不能は area=None。"""
    seeds = [0.0, -3.0, 3.0, -6.0, 6.0, ty + 3.0]
    zs = np.linspace(z0, z1, n_z)
    # 1) 各 z の縦プローブ（seed から ±Y）で内側の点を決める
    origins, dirs, meta = [], [], []
    for zi, z in enumerate(zs):
        for si, ys in enumerate(seeds):
            for di, dy in enumerate((1.0, -1.0)):
                origins.append([0.0, ys, float(z)])
                dirs.append([0.0, dy, 0.0])
                meta.append((zi, si, di))
    hits = batch_first_hits(mesh, origins, dirs)
    yc_of = {}
    for (zi, si, di), h in zip(meta, hits):
        yc_of.setdefault(zi, {}).setdefault(si, [None, None])[di] = \
            None if h is None else float(h[1])
    centers = {}
    for zi in range(len(zs)):
        best = None
        for si, pair in yc_of.get(zi, {}).items():
            up, dn = pair
            if up is None or dn is None:
                continue
            h = up - dn
            if 1.0 < h < 30.0 and (best is None or h > best[1]):
                best = ((up + dn) / 2.0, h)
        if best is not None:
            centers[zi] = best[0]
    # 2) 16方向レイで断面ポリゴン
    origins, dirs, meta = [], [], []
    for zi, yc in centers.items():
        for k in range(n_ray):
            th = 2.0 * math.pi * k / n_ray
            origins.append([0.0, yc, float(zs[zi])])
            dirs.append([math.cos(th), math.sin(th), 0.0])
            meta.append((zi, k))
    hits = batch_first_hits(mesh, origins, dirs)
    rays = {}
    for (zi, k), h in zip(meta, hits):
        if h is not None:
            d = math.hypot(h[0], h[1] - centers[zi])
            rays.setdefault(zi, {})[k] = d
    out = []
    for zi, z in enumerate(zs):
        entry = {"z": float(z), "area": None, "yc": centers.get(zi),
                 "radii": None}
        rr = rays.get(zi, {})
        if len(rr) == n_ray and max(rr.values()) < 25.0:
            poly = [(rr[k] * math.cos(2 * math.pi * k / n_ray),
                     rr[k] * math.sin(2 * math.pi * k / n_ray))
                    for k in range(n_ray)]
            a = 0.0
            for i in range(n_ray):
                x0, y0 = poly[i]
                x1, y1 = poly[(i + 1) % n_ray]
                a += x0 * y1 - x1 * y0
            entry["area"] = abs(a) / 2.0
            entry["radii"] = [rr[k] for k in range(n_ray)]
        out.append(entry)
    return out


def _classify_chamber(s_chamber) -> tuple[str, dict]:
    """実測16方向半径 vs profiles の4形状断面テンプレの正規化残差で分類。"""
    rr = np.asarray(s_chamber["radii"], float)
    n_ray = len(rr)
    th_meas = np.arange(n_ray) * 2.0 * math.pi / n_ray
    w = 2.0 * max(rr[0], rr[n_ray // 2])
    h = 2.0 * max(rr[n_ray // 4], rr[3 * n_ray // 4])
    scores = {}
    for shape in ("round", "square", "horseshoe", "flat_sidewall"):
        pts = profiles.section_pts({"yc": 0.0, "h": h, "w": w,
                                    "n": profiles._CHAMBER_N[shape],
                                    "shape": shape})
        pth = np.array([math.atan2(y, x) % (2 * math.pi) for x, y in pts])
        prr = np.array([math.hypot(x, y) for x, y in pts])
        order = np.argsort(pth)
        cand = np.interp(th_meas, pth[order], prr[order],
                         period=2.0 * math.pi)
        scale = max(np.mean(rr), 1e-9)
        scores[shape] = float(np.sqrt(np.mean(((rr - cand) / scale) ** 2)))
    best = min(scores, key=scores.get)
    return best, scores


def fit_baffle(p_base: dict, ceil_prof: list, report: dict,
               front_weight: bool = False) -> dict:
    """バッフル種別×高さ（×肩半径）のグリッド探索。

    候補パラメータで profiles.cavity_stations を回し、窓ステーションの解析天井
    (yc + h/2) と実測天井（下方レイの空洞天井プロファイル）の残差二乗和が最小の
    組み合わせを返す。数式を再実装せず本番のステーション生成をそのまま使う。
    """
    zs_meas = np.array([z for z, _ in ceil_prof])
    ys_meas = np.array([y for _, y in ceil_prof])
    results = []
    for btype in ("straight", "rollover", "step", "curve"):
        rolls = [4.0, 8.0, 12.0, 16.0] if btype in ("rollover", "curve") else [10.0]
        for roll in rolls:
            for hb in np.arange(0.0, 5.01, 0.1):
                p = dict(p_base, baffle_type=btype, baffle_height=round(float(hb), 2),
                         rollover_radius=roll)
                st = profiles.stations_by_role(profiles.cavity_stations(p), "window")
                ts = profiles._window_ts(p)
                z_lo, z_hi = zs_meas.min(), zs_meas.max()
                err, wsum, nn = 0.0, 0.0, 0
                ty_model = profiles.table_y(p)
                for s, t in zip(st, ts):
                    if not (z_lo + 0.3 <= s["z"] <= z_hi - 0.3):
                        continue
                    y_a = (s["yc"] + s["h"] / 2.0) - ty_model  # リード面基準
                    y_m = float(np.interp(s["z"], zs_meas, ys_meas))
                    w = ((1.0 - t) ** 1.5 + 0.1) if front_weight else 1.0
                    err += w * (y_a - y_m) ** 2
                    wsum += w
                    nn += 1
                if nn >= 4:
                    results.append((math.sqrt(err / wsum), btype, float(hb), roll))
    results.sort()
    key = "baffle_fit_top_front" if front_weight else "baffle_fit_top"
    report[key] = [
        {"rmse_mm": round(r, 3), "type": t, "height": round(h, 1),
         "rollover_radius": ro}
        for r, t, h, ro in results[:6]]
    rmse, btype, hb, roll = results[0]
    return {"baffle_type": btype, "baffle_height": round(hb, 1),
            "rollover_radius": roll, "rmse": rmse}


# ------------------------------------------------------------------ 候補生成

#: 実測をそのまま使う「演奏面・外形」系パラメータ
PLAYING_KEYS = ["tip_opening", "facing_length", "tip_rail_width", "side_rail_width",
                "window_length", "reed_width", "beak_height", "body_dia",
                "overall_length", "bore_dia", "bore_length"]
#: 内部空洞系パラメータ
CAVITY_KEYS = ["baffle_type", "baffle_height", "rollover_radius",
               "throat_ratio", "chamber_ratio", "chamber_shape"]


def build_candidates(meas: dict, baffle: dict, baffle_front: dict,
                     tenor_mp: dict, report: dict):
    """3案の mouthpiece パラメータ辞書と、クランプ記録を返す。"""
    clamps: dict[str, list[str]] = {}

    def adopt(name, keys_playing=True, cavity_from="measured"):
        cl: list[str] = []
        p = dict(tenor_mp)
        for k in PLAYING_KEYS:
            p[k] = clamp_round(k, meas[k], cl)
        p["facing_curve"] = meas.get("facing_curve", p.get("facing_curve", "elliptic"))
        # beak_height のスキーマ範囲は body_dia 依存（0.35〜0.75×body_dia）
        lo_b = round(0.35 * p["body_dia"], 1)
        hi_b = round(0.75 * p["body_dia"], 1)
        if not (lo_b <= p["beak_height"] <= hi_b):
            cl.append(f"beak_height: 実測 {p['beak_height']} → "
                      f"範囲 [{lo_b},{hi_b}] にクランプ")
            p["beak_height"] = min(max(p["beak_height"], lo_b), hi_b)
        if cavity_from == "measured":
            p["baffle_type"] = baffle["baffle_type"]
            p["baffle_height"] = clamp_round("baffle_height",
                                             baffle["baffle_height"], cl)
            p["rollover_radius"] = clamp_round("rollover_radius",
                                               baffle["rollover_radius"], cl)
            p["throat_ratio"] = clamp_round("throat_ratio", meas["throat_ratio"], cl)
            p["chamber_ratio"] = clamp_round("chamber_ratio",
                                             meas["chamber_ratio"], cl)
            p["chamber_shape"] = meas["chamber_shape"]
        clamps[name] = cl
        return p

    # 案1: 忠実 — 実測値をそのまま
    c1 = adopt("faithful")

    # 案2: 演奏面優先 — 内部空洞は現行テンプレ値のまま
    c2 = adopt("playing", cavity_from="template")

    # 案3: 音響優先 — 案1をベースに、(a) バッフルはティップ近傍（音色支配域）
    # 重み付きフィットの結果を使い、(b) 閉領域内容積が実測と一致するよう
    # chamber_ratio を1次元探索で微調整する。
    c3 = dict(c1)
    cl3 = list(clamps["faithful"])
    c3["baffle_type"] = baffle_front["baffle_type"]
    c3["baffle_height"] = clamp_round("baffle_height",
                                      baffle_front["baffle_height"], cl3)
    c3["rollover_radius"] = clamp_round("rollover_radius",
                                        baffle_front["rollover_radius"], cl3)
    target = meas["_closed_volume_cc"]
    sec = [s for s in meas["_sections"] if s["area"] is not None]
    z_lo, z_hi = sec[0]["z"], sec[-1]["z"]

    def closed_vol(p):
        """測定と同じ z 範囲 [z_lo, z_hi] のモデル空洞体積。

        モデルのステーション位置は実測の閉領域境界と揃わないため、ステーション
        断面積を z の区分線形（ルールドロフトと同じ補間）として範囲内を積分する。
        """
        st = sorted(profiles.cavity_stations(p), key=lambda s: s["z"])
        sz = [s["z"] for s in st]
        sa = [profiles.section_area(s) for s in st]
        zb = profiles.bore_start_z(p)
        r = profiles.bore_radius(p)
        a_bore = math.pi * r * r

        def area_at(z):
            if z >= sz[-1]:
                return a_bore
            if z <= sz[0]:
                return sa[0]
            return float(np.interp(z, sz, sa))

        grid = np.arange(z_lo, z_hi + 0.25, 0.5)
        return float(np.trapezoid([area_at(z) for z in grid], grid)) / 1000.0

    lo, hi = SCHEMA["chamber_ratio"][0], SCHEMA["chamber_ratio"][1]
    best = (abs(closed_vol(c3) - target), c3["chamber_ratio"])
    for cr in np.arange(lo, hi + 1e-9, 0.05):
        p = dict(c3, chamber_ratio=round(float(cr), 2))
        d = abs(closed_vol(p) - target)
        if d < best[0]:
            best = (d, round(float(cr), 2))
    c3["chamber_ratio"] = best[1]
    report["acoustic_fit"] = {
        "measured_closed_cc": round(target, 3),
        "candidate3_closed_cc": round(closed_vol(c3), 3),
        "chamber_ratio_area_fit": c1["chamber_ratio"],
        "chamber_ratio_volume_fit": c3["chamber_ratio"],
    }
    clamps["acoustic"] = list(clamps["faithful"])
    return {"faithful": c1, "playing": c2, "acoustic": c3}, clamps


# ------------------------------------------------------------------ 検証・出力

def verify_candidate(name: str, mp: dict, tenor: dict, report: dict):
    """SaxSketch 本体でビルド＋シミュレーションが通ることを確認。"""
    from saxsketch.instruments.saxophone.components.mouthpiece import (
        MouthpieceComponent)
    desc = json.loads((_REPO / "saxsketch/instruments/saxophone/descriptor.json")
                      .read_text(encoding="utf-8"))
    template = dict(tenor, mouthpiece=mp)
    comp = MouthpieceComponent(desc, template)
    part = comp.build(mp)
    vol = float(part.volume)
    sim = comp.simulate(mp)
    cav = profiles.cavity_volume_cc(mp)
    report.setdefault("verify", {})[name] = {
        "solid_volume_mm3": round(vol, 1),
        "cavity_total_cc": round(cav["total_cc"], 3),
        "simulate_ok": bool(sim.get("tier1")),
    }
    assert vol > 1000.0, f"{name}: ソリッド体積が異常 ({vol})"


def write_report(path: Path, meas, how, cands, clamps, baffle, report, quality):
    rows = []
    keys = PLAYING_KEYS + ["facing_curve"] + CAVITY_KEYS
    baffle_how = {"baffle_type": "天井プロファイル グリッド探索",
                  "baffle_height": "同上", "rollover_radius": "同上"}
    for k in keys:
        raw = meas.get(k, baffle.get(k))
        f = lambda v: (f"{v:.3f}" if isinstance(v, float) else str(v))
        rows.append("| {} | {} | {} | {} | {} | {} |".format(
            k,
            f(raw) if raw is not None else "—",
            f(cands["faithful"][k]), f(cands["playing"][k]), f(cands["acoustic"][k]),
            how.get(k, baffle_how.get(k, ""))))
    aux_rows = []
    for k in ("_table_tilt_deg", "_window_width", "_closed_volume_cc"):
        aux_rows.append(f"| {k[1:]} | {meas[k]:.3f} | {how[k]} |")

    clamp_txt = "\n".join(
        f"- **{n}**: " + ("; ".join(c) if c else "クランプなし")
        for n, c in clamps.items())
    baffle_tbl = "\n".join(
        "| {type} | {height} | {rollover_radius} | {rmse_mm} |".format(**r)
        for r in report["baffle_fit_top"])
    baffle_tbl_front = "\n".join(
        "| {type} | {height} | {rollover_radius} | {rmse_mm} |".format(**r)
        for r in report.get("baffle_fit_top_front", []))
    verify_tbl = "\n".join(
        "| {} | {solid_volume_mm3} | {cavity_total_cc} | {simulate_ok} |".format(
            n, **v) for n, v in report.get("verify", {}).items())

    path.write_text(f"""# WindyCity Tenor 3mf フィットレポート（自動生成）

生成: fit_windycity.py / 元データ: WindyCity-Tenor-72-100-LS.3mf

## メッシュ品質・整列

- watertight: {quality['watertight']} / faces: {quality['faces']} / 体積: {quality['volume_cc']} cc
- 主軸整列: elongation={report['axis_align']['elongation']}, axis={report['axis_align']['axis_conf']}, shank={report['axis_align']['shank_conf']}
- roll（テーブル検出）: 平面点数 {report['roll']['plane_points']}, テーブル面 y {report['roll']['table_y_mm']} mm, サイン判定 {report.get('roll_sign')}
- 警告: {'; '.join(report.get('warnings', [])) or 'なし'}

## 実測値と3案の採用値

| パラメータ | 実測 | 案1 忠実 | 案2 演奏面 | 案3 音響 | 測定方法 |
|---|---|---|---|---|---|
{chr(10).join(rows)}

補助測定値（パラメータではない基準量）:

| 量 | 値 | 方法 |
|---|---|---|
{chr(10).join(aux_rows)}

## クランプ（スキーマ範囲へ丸めた項目）

{clamp_txt}

## バッフル グリッド探索（上位）

全域均等重み（案1が採用）:

| 種別 | 高さ | 肩半径 | RMSE mm |
|---|---|---|---|
{baffle_tbl}

ティップ近傍（音色支配域）重み付き（案3が採用）:

| 種別 | 高さ | 肩半径 | RMSE mm |
|---|---|---|---|
{baffle_tbl_front}

## 音響フィット（案3）

- 実測 閉領域内容積: {report['acoustic_fit']['measured_closed_cc']} cc
- 案3 同範囲解析値: {report['acoustic_fit']['candidate3_closed_cc']} cc
- chamber_ratio: 断面積比フィット {report['acoustic_fit']['chamber_ratio_area_fit']} → 体積フィット {report['acoustic_fit']['chamber_ratio_volume_fit']}

## SaxSketch ビルド検証（build123d 実行）

| 案 | ソリッド体積 mm³ | 空洞 cc | simulate |
|---|---|---|---|
{verify_tbl}

## 実測不能・継承項目

- tip_rail_width / side_rail_width: 分解能・形状連続性の限界 → 現行値を継承（表参照）
- cork_depth: 組立条件で形状に現れない → 現行値を継承
- min_wall / material: 現行値を継承

## 既知のスキーマ限界（SaxSketch で表現できない実物の特徴）

- **テーブルの傾き**: 実物のテーブル面はボア軸に対し約 {meas['_table_tilt_deg']:.1f}° 傾いて
  いるが、SaxSketch のテーブルは軸平行（table_y = −0.40·body_dia 固定）。リード面基準の
  寸法（ティップ開き・フェイシング・ビーク高さ・バッフル天井）で写像しているため演奏
  ジオメトリは保たれるが、FreeCAD の重ね合わせではテーブル側が扇形にずれて見える。
- 外形プロファイル・窓の閉じ方・ランプ形状は SaxSketch の構成式に従う（完全複製ではない）。
- 実測の窓長・ボア長はスキーマ上限（44 / 60mm）でクランプされている。

FreeCAD の重ね合わせで乖離を目視確認のうえ、採用案を選ぶこと。
""", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--out", default=str(_HERE))
    ap.add_argument("--no-verify", action="store_true",
                    help="build123d でのビルド検証を省く（高速化）")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report: dict = {}
    mesh = meshdiff.load_mesh(args.src)
    quality = meshdiff.mesh_quality(mesh)
    print(f"mesh: faces={quality['faces']} watertight={quality['watertight']}")

    mesh = align_to_saxsketch(mesh, report)
    mesh.export(str(out / "reference_aligned.stl"))
    print("aligned →", out / "reference_aligned.stl")

    meas, how = measure(mesh, report)
    print("measured:", {k: round(v, 3) for k, v in meas.items()
                        if isinstance(v, float)})

    tenor = json.loads(TENOR_JSON.read_text(encoding="utf-8"))
    tenor_mp = tenor["mouthpiece"]

    # バッフル探索は実測外形パラメータの上で行う（stations が外形に依存するため）
    p_probe = dict(tenor_mp)
    cl_probe: list[str] = []
    for k in PLAYING_KEYS:
        p_probe[k] = clamp_round(k, meas[k], cl_probe)
    p_probe["throat_ratio"] = clamp_round("throat_ratio", meas["throat_ratio"], cl_probe)
    p_probe["chamber_ratio"] = clamp_round("chamber_ratio", meas["chamber_ratio"],
                                           cl_probe)
    p_probe["chamber_shape"] = meas["chamber_shape"]
    baffle = fit_baffle(p_probe, meas["_ceil_profile"], report)
    baffle_front = fit_baffle(p_probe, meas["_ceil_profile"], report,
                              front_weight=True)
    print("baffle fit:", baffle)

    print("baffle fit (front-weighted):", baffle_front)
    cands, clamps = build_candidates(meas, baffle, baffle_front, tenor_mp, report)

    labels = {
        "faithful": ("candidate_1_faithful",
                     "テナー WindyCity 案1 忠実フィット",
                     "WindyCity Tenor .100\" LS の 3mf 実測値を全パラメータに採用。"),
        "playing": ("candidate_2_playing",
                    "テナー WindyCity 案2 演奏面優先",
                    "ティップ開き・フェイシング・窓・ビーク等は実測、内部空洞は"
                    "現行テナー校正値を維持。"),
        "acoustic": ("candidate_3_acoustic",
                     "テナー WindyCity 案3 音響優先",
                     "案1ベースで、閉領域内容積が実測と一致するよう chamber_ratio "
                     "を体積フィット。"),
    }
    for name, mp in cands.items():
        stem, label, note = labels[name]
        tpl = copy.deepcopy(tenor)
        tpl["label"] = label
        tpl["note"] = note + " 由来: WindyCity-Tenor-72-100-LS.3mf 実測（fit_report.md 参照）。"
        tpl["mouthpiece"] = mp
        (out / f"{stem}.json").write_text(
            json.dumps(tpl, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", out / f"{stem}.json")
        if not args.no_verify:
            verify_candidate(name, mp, tenor, report)
            print("verified", name, report["verify"][name])

    write_report(out / "fit_report.md", meas, how, cands, clamps, baffle,
                 report, quality)
    print("report →", out / "fit_report.md")


main()
