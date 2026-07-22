"""外部メッシュを座標非依存で正準姿勢へ整列する（楽器非依存の汎用部）。

外部（他所で作られた/スキャンした）モデルは原点・向きが不定。ここでは
主軸（PCA 最大分散方向）を +Z に載せ、内部空洞（ボア開口）の深い端を
シャンク＝+Z 側へ向ける。ビーク方向（軸まわりの回転）は解かない
——外形バルク寸法（全長・外径・シャンク内径）はいずれも軸対称的で
ビーク向きに依らないため不要。信頼度が低い判定は info で明示し、
呼び出し側が「測定不能」に落とせるようにする。
"""
from __future__ import annotations

import numpy as np
import trimesh

_SAMPLE = 60_000


def _principal_rotation(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """点群の主軸回転。Returns (R, center, eigvals_ascending)。

    R は列基底ではなく行基底: 新座標 = R @ (p - center)。最大分散軸を z' に置く。
    """
    c = pts.mean(axis=0)
    x = pts - c
    cov = x.T @ x / len(x)
    w, v = np.linalg.eigh(cov)          # w 昇順, v[:, i] が固有ベクトル
    long = v[:, 2]                       # 最大分散 = 長軸 → z'
    e1, e2 = v[:, 0], v[:, 1]
    R = np.vstack([e1, e2, long])        # 行 = 新基底
    if np.linalg.det(R) < 0:             # 右手系に
        R[0] *= -1.0
    return R, c, w


def _transform(R: np.ndarray, c: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = -R @ c
    return T


def _near_face_radius(av: np.ndarray, z_face: float, inward: float) -> tuple[float, int]:
    """端面 z_face から inward(±1) 方向へ 2〜7mm 内側の断面の代表半径(p90)と点数。

    シャンク（丸い管端）は端面近くでも太い断面を持ち、ビーク先端は細く尖る。
    この near-face 半径の大小が両端の識別子になる（軸レイの侵入深さは細い先端に
    騙されるため使わない）。
    """
    lo, hi = sorted((z_face + inward * 2.0, z_face + inward * 7.0))
    m = (av[:, 2] >= lo) & (av[:, 2] <= hi)
    if int(m.sum()) < 30:
        return 0.0, int(m.sum())
    xy = av[m, :2]
    c = xy.mean(axis=0)
    r = np.hypot(xy[:, 0] - c[0], xy[:, 1] - c[1])
    return float(np.percentile(r, 90)), int(m.sum())


def axis_align(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, np.ndarray, dict]:
    """主軸を +Z、シャンク（開口ボア）端を +Z 側へ向けた整列メッシュを返す。

    Returns (aligned_mesh, transform_4x4, info)。
    info = {elongation, axis_conf, shank_conf, length_mm,
            shank_at_positive_z, warnings}。
    """
    pts, _ = trimesh.sample.sample_surface(mesh, min(_SAMPLE, max(2000, len(mesh.faces))))
    pts = np.asarray(pts)
    R, c, w = _principal_rotation(pts)
    T = _transform(R, c)
    aligned = mesh.copy()
    aligned.apply_transform(T)

    zmin, zmax = float(aligned.bounds[0, 2]), float(aligned.bounds[1, 2])
    length = zmax - zmin
    # 長軸の卓越度（第1/第2主分散比）。細長い部品ほど軸が確か。
    elong = float(np.sqrt(w[2] / max(w[1], 1e-9)))
    axis_conf = "high" if elong > 3.0 else "med" if elong > 1.8 else "low"

    av = np.asarray(aligned.vertices)
    r_outer = float(np.percentile(np.hypot(av[:, 0], av[:, 1]), 98))

    # シャンク（太い丸管端）vs ビーク（細い尖端）を端面近傍断面の太さで識別
    r_top, n_top = _near_face_radius(av, zmax, -1.0)
    r_bot, n_bot = _near_face_radius(av, zmin, +1.0)
    warnings: list[str] = []
    shank_at_pos = r_top >= r_bot          # 太い方がシャンク
    hi, lo = max(r_top, r_bot), min(r_top, r_bot)
    if hi > 4.0 and hi > 1.5 * max(lo, 1e-6):
        shank_conf = "high"
    elif hi > 3.0 and hi > 1.2 * max(lo, 1e-6):
        shank_conf = "med"
    else:
        shank_conf = "low"
        warnings.append("両端の太さが近く、シャンク方向を特定できません。")

    if not shank_at_pos:
        # x 軸まわり 180° 回転で z を反転（右手系維持: y,z を反転）
        flip = np.diag([1.0, -1.0, -1.0, 1.0])
        aligned.apply_transform(flip)
        T = flip @ T

    if axis_conf == "low":
        warnings.append("形状が十分に細長くないため、主軸の向きが不確実です。")

    info = {
        "elongation": round(elong, 2),
        "axis_conf": axis_conf,
        "shank_conf": shank_conf,
        "length_mm": round(length, 2),
        "outer_radius_mm": round(r_outer, 2),
        "shank_at_positive_z": True,  # 反転後は常に +Z
        "warnings": warnings,
    }
    return aligned, T, info


def radial_inner_diameter(mesh: trimesh.Trimesh, z: float,
                          center_xy: tuple[float, float],
                          max_r: float) -> float | None:
    """軸上 (center_xy, z) から放射状に飛ばしたレイの最初のヒット＝内壁までの径。

    ヒットが3方向以上・すべて max_r 未満のとき 2·中央値を返す。空洞外なら None。
    """
    dirs = []
    for k in range(8):
        a = 2.0 * np.pi * k / 8
        dirs.append([np.cos(a), np.sin(a), 0.0])
    o = np.tile([center_xy[0], center_xy[1], z], (8, 1))
    d = np.asarray(dirs)
    locs, idx_ray, _ = mesh.ray.intersects_location(o, d)
    best: dict[int, float] = {}
    for loc, ir in zip(locs, idx_ray):
        dist = float(np.hypot(loc[0] - center_xy[0], loc[1] - center_xy[1]))
        if ir not in best or dist < best[ir]:
            best[ir] = dist
    good = [v for v in best.values() if v < max_r]
    if len(good) < 3:
        return None
    return 2.0 * float(np.median(good))


def shank_bore_diameter(mesh: trimesh.Trimesh, av: np.ndarray, zmax: float,
                        length: float, outer_r: float) -> tuple[float, str] | None:
    """シャンク（+Z 端）の円筒ボア内径を推定。Returns (diameter_mm, confidence) か None。

    端面近くはソケットのテーパ/面取りで内径が細く出るため、深さ 5mm〜0.28L を走査し、
    最大付近の「プラトー」（円筒部）を代表値に採る。テーパやリムは内径を小さくする側、
    単発の外れ値は各深さ 8方向の中央値で吸収される。過度に深いとチェンバーへ抜けるため
    深さ上限を設ける。
    """
    z = av[:, 2]
    d1 = min(0.28 * length, 35.0)
    reads: list[float] = []
    for depth in np.arange(5.0, d1, 2.5):
        zc = zmax - depth
        slab = (z > zc - 1.5) & (z < zc + 1.5)
        if int(slab.sum()) < 20:
            continue
        cx = float(av[slab, 0].mean())
        cy = float(av[slab, 1].mean())
        dia = radial_inner_diameter(mesh, zc, (cx, cy), max_r=outer_r)
        if dia is not None and 2.0 < dia < 2.0 * outer_r:
            reads.append(dia)
    if len(reads) < 3:
        return None
    arr = np.asarray(reads)
    plateau = arr[arr >= 0.82 * arr.max()]   # 円筒部（最大付近）
    dia = float(np.median(plateau))
    conf = "med" if float(np.std(plateau)) < 1.0 else "low"
    return dia, conf
