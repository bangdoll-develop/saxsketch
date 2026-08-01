# -*- coding: utf-8 -*-
"""実物マウスピース 3mf を SaxSketch 座標系（ボア軸基準）へ整列して STL 出力する。

SaxSketch の座標系は **ボア軸が Z、z=0 がティップ、+Y がビーク**。外来メッシュは
原点も向きも不定なので、次の順で正準姿勢へ載せる:

  1. `analysis.align.axis_align` で主軸を +Z（PCA）
  2. 太い端がシャンクになるよう必要なら反転（端面近傍の半径で判定。axis_align の
     端面判定は頂点が疎な端で点数不足になり半径 0 と誤るので自前で判定する）
  3. **シャンク内側のボア円筒の中心列を直線フィットし、その軸を厳密に +Z に載せる**。
     PCA 軸はテーブルカットの非対称性で約1°ずれる。この1°を残したまま測ると
     ティップ開きが 3.1mm（刻印 .100"=2.54mm）と過大に出るため、ここが要。
  4. ティップの楔（z<2mm の薄い断面）の薄い方向がテーブル法線。2つある向きのうち
     「ウィンドウを貫通するレイが通る」側が本物のテーブル側 → −Y へ回す
  5. z=0 をティップ端へ

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/align_reference.py
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

from saxsketch.analysis import align, meshdiff  # noqa: E402

SRC_DEFAULT = "/mnt/c/Users/<user>/Downloads/WindyCity-Tenor-72-100-LS.3mf"
OUT_DEFAULT = _HERE / "reference_aligned.stl"


def _first_hits(mesh, origins, dirs):
    o = np.asarray(origins, float)
    d = np.asarray(dirs, float)
    locs, idx, _ = mesh.ray.intersects_location(o, d)
    best: dict[int, tuple[float, np.ndarray]] = {}
    for loc, i in zip(locs, idx):
        dist = float(np.linalg.norm(loc - o[i]))
        if i not in best or dist < best[i][0]:
            best[i] = (dist, loc)
    return [best.get(i, (None, None))[1] for i in range(len(origins))]


def _shank_to_positive_z(mesh, report):
    """太い端（シャンク）を +Z 側へ。端面近傍の半径で判定する。"""
    pts, _ = trimesh.sample.sample_surface(mesh, 60_000)
    pts = np.asarray(pts)
    zmin, zmax = float(pts[:, 2].min()), float(pts[:, 2].max())

    def r90(lo, hi):
        m = (pts[:, 2] >= lo) & (pts[:, 2] <= hi)
        xy = pts[m, :2] - pts[m, :2].mean(axis=0)
        return float(np.percentile(np.hypot(xy[:, 0], xy[:, 1]), 90))

    r_lo, r_hi = r90(zmin + 2.0, zmin + 7.0), r90(zmax - 7.0, zmax - 2.0)
    if r_hi < r_lo:
        mesh.apply_transform(np.diag([1.0, -1.0, -1.0, 1.0]))
    report["end_radii_mm"] = {"low_z": round(r_lo, 2), "high_z": round(r_hi, 2)}
    return mesh


def _bore_ring_center(mesh, zc, n=32, max_r=16.0):
    th = np.arange(n) * 2.0 * math.pi / n
    o = np.stack([np.zeros(n), np.zeros(n), np.full(n, zc)], 1)
    d = np.stack([np.cos(th), np.sin(th), np.zeros(n)], 1)
    locs, idx, _ = mesh.ray.intersects_location(o, d)
    best: dict[int, tuple[float, np.ndarray]] = {}
    for loc, i in zip(locs, idx):
        r = math.hypot(loc[0], loc[1])
        if i not in best or r < best[i][0]:
            best[i] = (r, loc)
    pts = np.array([b[1] for b in best.values() if b[0] < max_r])
    if len(pts) < n - 4:
        return None
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def _align_bore_axis(mesh, report, iters=14):
    """シャンク内ボア円筒の中心列を +Z へ載せ、軸を x=y=0 に通す。"""
    tilt = None
    for _ in range(iters):
        L = float(mesh.vertices[:, 2].max())
        cs = []
        for z in np.arange(L - 4.0, L - 46.0, -3.0):
            c = _bore_ring_center(mesh, float(z))
            if c:
                cs.append((z, c[0], c[1]))
        if len(cs) < 6:
            raise RuntimeError("シャンク内ボアの断面中心を検出できませんでした")
        Z = np.array([c[0] for c in cs])
        sx = float(np.polyfit(Z, np.array([c[1] for c in cs]), 1)[0])
        sy = float(np.polyfit(Z, np.array([c[2] for c in cs]), 1)[0])
        tilt = math.degrees(math.atan(math.hypot(sx, sy)))
        if tilt < 0.01:
            break
        v = np.array([sx, sy, 1.0])
        v /= np.linalg.norm(v)
        axis = np.cross(v, [0.0, 0.0, 1.0])
        s = np.linalg.norm(axis)
        if s > 1e-12:
            mesh.apply_transform(trimesh.transformations.rotation_matrix(
                math.asin(min(s, 1.0)), axis / s))
        L = float(mesh.vertices[:, 2].max())
        c = _bore_ring_center(mesh, L - 20.0)
        if c:
            mesh.apply_translation([-c[0], -c[1], 0.0])
    report["bore_axis_tilt_deg"] = round(tilt, 4)
    return mesh


def _solve_roll(mesh, report):
    """テーブル側（ウィンドウの開く側）を −Y へ回す。"""
    pts, _ = trimesh.sample.sample_surface(mesh, 120_000)
    pts = np.asarray(pts)
    zmax = float(pts[:, 2].max())
    tip = pts[pts[:, 2] < 2.0]
    if len(tip) < 200:
        raise RuntimeError("ティップ近傍のサンプル点が不足しています")
    xy = tip[:, :2] - tip[:, :2].mean(axis=0)
    _, vec = np.linalg.eigh(xy.T @ xy / len(xy))
    thin = vec[:, 0]                      # 楔の薄い方向 = テーブル法線の候補

    def window_frac(nh):
        """楔面レベルより 1.5mm 以上奥へ届く中心線レイの割合。テーブル側で高い。"""
        level = float(np.percentile(tip[:, :2] @ nh, 98.0))
        origins, dirs = [], []
        for z in np.arange(0.12 * zmax, 0.35 * zmax, 2.0):
            o = nh * (level + 8.0)
            origins.append([o[0], o[1], float(z)])
            dirs.append([-nh[0], -nh[1], 0.0])
        hits = _first_hits(mesh, origins, dirs)
        lv = [float(np.asarray(h)[:2] @ nh) for h in hits if h is not None]
        return sum(1 for v in lv if v < level - 1.5) / len(lv) if lv else 0.0

    f_pos, f_neg = window_frac(thin), window_frac(-thin)
    report["roll_window_frac"] = {"pos": round(f_pos, 3), "neg": round(f_neg, 3)}
    if max(f_pos, f_neg) < 0.3:
        raise RuntimeError("テーブル側（ウィンドウ開口）を判定できませんでした")
    nh = thin if f_pos >= f_neg else -thin
    ang = -math.pi / 2.0 - math.atan2(nh[1], nh[0])
    mesh.apply_transform(trimesh.transformations.rotation_matrix(ang, [0, 0, 1]))
    return mesh


def table_plane(mesh, z_lo=15.0, z_hi_ratio=0.72):
    """テーブル平面 y = a + b·z の頑健フィット。Returns (a, b, rms)。

    リード側の下向き平坦点の下側包絡を直線フィットする。0.72L 以降はシャンクの
    丸い底がテーブル平面より上に入り込むので除く。
    """
    pts, fidx = trimesh.sample.sample_surface(mesh, 300_000)
    pts = np.asarray(pts)
    nrm = mesh.face_normals[np.asarray(fidx)]
    L = float(pts[:, 2].max())
    sel = (nrm[:, 1] < -0.85) & (np.abs(pts[:, 0]) < 0.36 * L)
    zb, yb = [], []
    for z0 in np.arange(z_lo, z_hi_ratio * L, 2.0):
        m = sel & (pts[:, 2] >= z0) & (pts[:, 2] < z0 + 2.0)
        if m.sum() < 25:
            continue
        zb.append(z0 + 1.0)
        yb.append(float(np.percentile(pts[m, 1], 4.0)))
    zb, yb = np.asarray(zb), np.asarray(yb)
    b, a = np.polyfit(zb, yb, 1)
    keep = np.ones(len(zb), bool)
    for _ in range(3):
        res = np.abs(yb - (a + b * zb))
        keep = res < max(0.2, 2.0 * float(np.median(res)))
        b, a = np.polyfit(zb[keep], yb[keep], 1)
    rms = float(np.sqrt(np.mean((yb[keep] - (a + b * zb[keep])) ** 2)))
    return float(a), float(b), rms


def window_outline(mesh, a_t: float, b_t: float, z_hi: float = 46.0,
                   dz: float = 0.5, dx: float = 0.2, step: float = 0.35):
    """ウィンドウ（リード開口）の輪郭を z ごとに測る。Returns (zs, widths, lo, hi)。

    各 z で幅方向に下からレイを打ち、最初に当たる面の高さ y(x) を取る。サイドレール
    （リード面）に当たる x では低く、窓を通る x では天井（バッフル）に当たって高く出る。
    その **段差** を検出して開口の左右端とする。絶対高さのしきい値は使えない:
    ティップ側ではリード面と天井がほぼ同じ高さまで近づくので、しきい値だと窓が
    無いと誤判定する（段差自体は残るので相対判定なら効く）。

    閉じている z は width=0 で返す。
    """
    ty = lambda z: a_t + b_t * z                                   # noqa: E731
    # 胴より広く取り、端は必ず「当たらない」ようにする。x=0 ちょうどは避ける:
    # 空洞の天井は x=0 で稜線になり、そこへ真上に打つレイは接線ヒットになって
    # テッセレーション由来の縮退面をすり抜ける（測定が跳ねる）。
    xs = np.arange(-17.0 + dx / 2.0, 17.0, dx)
    zs, ws, los, his = [], [], [], []
    for zc in np.arange(0.5, z_hi, dz):
        o = np.stack([xs, np.full(len(xs), ty(zc) - 30.0),
                      np.full(len(xs), zc)], 1)
        d = np.tile([0.0, 1.0, 0.0], (len(xs), 1))
        locs, idx, _ = mesh.ray.intersects_location(o, d)
        first: dict[int, float] = {}
        for loc, i in zip(locs, idx):
            if i not in first or loc[1] < first[i]:
                first[i] = float(loc[1])
        ys = np.array([first.get(i, np.nan) for i in range(len(xs))])
        ok = np.isfinite(ys)
        if ok.sum() < 12:
            continue
        i0 = int(np.argmin(np.abs(xs)))
        if not ok[i0]:
            continue
        # 中央から左右へ、y が step 以上落ちる（レール面に乗る）ところで止める
        def edge(direction):
            i = i0
            while True:
                j = i + direction
                if j < 0 or j >= len(xs) or not ok[j]:
                    return i, "end"          # 段差を見つけずに材料が尽きた
                if ys[i] - ys[j] > step:
                    return i, "step"         # ここがレールの内側 = 窓の縁
                i = j
        (il, rl), (ih, rh) = edge(-1), edge(+1)
        # 左右とも段差なしで端まで到達 = サイドレールが無い = 窓として測れない
        closed = rl == "end" and rh == "end"
        zs.append(float(zc))
        if closed:
            ws.append(0.0)
            los.append(np.nan)
            his.append(np.nan)
        else:
            ws.append(float(xs[ih] - xs[il]))
            los.append(float(xs[il]))
            his.append(float(xs[ih]))
    return (np.asarray(zs), np.asarray(ws), np.asarray(los), np.asarray(his))


def window_span(zs, ws, min_w: float = 1.0):
    """窓が開いている z 範囲（width>min_w の最長連続区間）。"""
    op = ws > min_w
    best, cur = None, None
    for i, o in enumerate(op):
        if o and cur is None:
            cur = i
        if not o and cur is not None:
            if best is None or i - cur > best[1] - best[0]:
                best = (cur, i - 1)
            cur = None
    if cur is not None and (best is None or len(op) - cur > best[1] - best[0]):
        best = (cur, len(op) - 1)
    if best is None:
        return float("nan"), float("nan")
    return float(zs[best[0]]), float(zs[best[1]])


def facing_rise_profile(mesh, a_t: float, b_t: float,
                        z_lo: float = 14.0, z_hi: float = 32.0,
                        rise_max: float = 1.6):
    """サイドレール上面の、テーブル平面からの持ち上がりプロファイル。

    各 z で幅方向にレイを走査し、**最初のヒットの持ち上がりが最小になる x** を採る。
    ウィンドウを通るレイは天井（ずっと高い）を拾い、レールを踏むレイだけが低い値を
    返すので、最小値が自動的にレールを選ぶ。ティップ寄りは窓がテーブルの弦いっぱいに
    開いていてレールが実質無いため、`z_lo` 以降・`rise_max` 未満だけを使う。
    """
    ty = lambda z: a_t + b_t * z                                   # noqa: E731
    zs, rs = [], []
    for zc in np.arange(z_lo, z_hi, 0.5):
        xm = 0.0
        for x in np.arange(4.0, 13.01, 0.25):     # 弦の外側までは当たらない
            o = np.array([[float(x), ty(zc) - 14.0, float(zc)]])
            locs, _, _ = mesh.ray.intersects_location(o, np.array([[0.0, 1.0, 0.0]]))
            if len(locs):
                xm = max(xm, float(x))
        best = None
        for sgn in (1.0, -1.0):
            for x in np.arange(0.45 * xm, 0.99 * xm, 0.25):
                o = np.array([[sgn * float(x), ty(zc) - 14.0, float(zc)]])
                locs, _, _ = mesh.ray.intersects_location(o, np.array([[0.0, 1.0, 0.0]]))
                if not len(locs):
                    continue
                r = min(float(pt[1]) for pt in locs) - ty(zc)
                if -0.3 < r and (best is None or r < best):
                    best = r
        if best is not None and best < rise_max:
            zs.append(float(zc))
            rs.append(best)
    return np.asarray(zs), np.asarray(rs)


def facing_fit(mesh, a_t: float, b_t: float, z_hi: float = 32.0) -> dict:
    """レールの持ち上がりプロファイルからフェイシングカーブを同定する。

    Returns {curve, facing_length, tip_opening, rmse, n}。
    """
    zs, rs = facing_rise_profile(mesh, a_t, b_t, z_hi=z_hi)
    if len(zs) < 8:
        return {"curve": None, "facing_length": float("nan"),
                "tip_opening": float("nan"), "rmse": float("nan"), "n": len(zs)}
    best = None
    for kind in ("radial", "elliptic"):
        for fl in np.arange(16.0, 36.01, 0.25):
            for tip in np.arange(1.6, 3.8001, 0.02):
                t = np.clip((fl - zs) / fl, 0.0, 1.0)
                if kind == "elliptic":
                    coef = 1.0 - np.sqrt(np.clip(1.0 - t * t, 0.0, 1.0))
                else:
                    rr = (fl * fl + tip * tip) / (2.0 * tip)
                    coef = (rr - np.sqrt(np.maximum(rr * rr - (t * fl) ** 2, 0.0))) / tip
                err = float(np.mean((rs - tip * coef) ** 2))
                if best is None or err < best[0]:
                    best = (err, kind, float(fl), float(tip))
    err, kind, fl, tip = best
    return {"curve": kind, "facing_length": fl, "tip_opening": tip,
            "rmse": math.sqrt(err), "n": len(zs)}


def align_reference(src: str) -> tuple[trimesh.Trimesh, dict]:
    report: dict = {}
    mesh = meshdiff.load_mesh(src)
    report["quality"] = meshdiff.mesh_quality(mesh)
    aligned, _, info = align.axis_align(mesh)
    report["axis_align"] = info
    aligned = _shank_to_positive_z(aligned, report)
    aligned = _align_bore_axis(aligned, report)
    aligned.apply_translation([0.0, 0.0, -float(aligned.bounds[0][2])])
    aligned = _solve_roll(aligned, report)
    aligned.apply_translation([0.0, 0.0, -float(aligned.bounds[0][2])])
    a, b, rms = table_plane(aligned)
    report["table_plane"] = {"y0": round(a, 4), "slope": round(b, 6),
                            "angle_deg": round(math.degrees(math.atan(b)), 3),
                            "flatness_rms_mm": round(rms, 4)}
    report["length_mm"] = round(float(aligned.bounds[1][2]), 3)
    return aligned, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    aligned, report = align_reference(args.src)
    aligned.export(args.out)
    for k, v in report.items():
        print("%-20s %s" % (k, v))
    print("saved:", args.out)


if __name__ == "__main__":
    main()
