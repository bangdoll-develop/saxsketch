"""取込メッシュと凍結形状の差分解析（楽器非依存の汎用部）。

- load_mesh: STL/3MF/OBJ/STEP を trimesh.Trimesh に読み込む
- mesh_quality: 水密・法線・体積
- region_deviations: パラメータ影響領域ごとの表面偏差
  （両メッシュを高密度サンプリングし、点対「面」距離を測る。
   0.12mm 以上の偏差は 1e-3mm 精度、それ未満は 0.12mm で頭打ちにする）
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

SAMPLE_COUNT = 200_000
# 判定しきい値 [mm]
DEV_UNCHANGED = 0.15
DEV_MINOR = 0.50


def load_mesh(path: str | Path) -> trimesh.Trimesh:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".stl", ".3mf", ".obj", ".ply"):
        m = trimesh.load(str(p), force="mesh")
    elif suffix in (".step", ".stp"):
        # STEP はソリッド → 一旦メッシュ化
        from build123d import import_step
        from saxsketch.export.models import export_model
        part = import_step(str(p))
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "m.stl"
            export_model(part, f, "stl", tolerance=0.02)
            m = trimesh.load(str(f), force="mesh")
    else:
        raise ValueError(f"未対応の形式です: {suffix}（STL / 3MF / STEP に対応）")
    if isinstance(m, trimesh.Scene):
        m = m.to_mesh()
    return m


def mesh_quality(m: trimesh.Trimesh) -> dict:
    watertight = bool(m.is_watertight)
    return {
        "watertight": watertight,
        "winding_consistent": bool(m.is_winding_consistent),
        "faces": int(len(m.faces)),
        "volume_cc": float(m.volume / 1000.0) if watertight else None,
    }


def part_to_mesh(part, tolerance: float = 0.03) -> trimesh.Trimesh:
    """build123d ソリッド → trimesh。"""
    from saxsketch.export.models import export_model
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "ref.stl"
        export_model(part, f, "stl", tolerance=tolerance)
        return trimesh.load(str(f), force="mesh")


# 距離計算の定数。実測記録は cad/meshdiff/README.md。
_CAND_K = 6          # 候補にする最近傍サンプル点の数
_FAR_CAP = 5.0       # ここまでしか近傍を探さない [mm]。DEV_MINOR の 10 倍
_REFINE_MIN = 0.12   # これ未満は厳密化しない（DEV_UNCHANGED 未満なので判定に効かない）
_REFINE_MAX = 3.0    # これ超えも厳密化しない（DEV_MINOR の 6 倍＝判定は「変化あり」で確定）
_EST_TOL = 0.30      # 見積りの過大評価の想定上限 [mm]（実測 0.152 の約2倍）
_MAX_EXACT = 20_000  # 1 方向あたりの厳密計算の上限点数
_CHUNK = 40_000      # 点対面計算の分割幅（(_CHUNK * _CAND_K, 3, 3) を一度に持つ）


def _sample(m: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    """表面の一様サンプル。点だけでなく**乗っている面番号**も返す。"""
    pts, face = trimesh.sample.sample_surface(m, SAMPLE_COUNT)
    return (np.ascontiguousarray(np.asarray(pts, dtype=np.float64)),
            np.asarray(face, dtype=np.int64))


def _estimate_dist(pts: np.ndarray, other: trimesh.Trimesh,
                   other_pts: np.ndarray, other_face: np.ndarray) -> np.ndarray:
    """pts から other 表面への距離の**上界**。全点ぶんベクトル化する。

    点対点の最近傍だけだとサンプル間隔（tenor で 0.25mm）ぶん必ず過大評価し、
    同一メッシュでも最大 0.51mm が出てしまう。最近傍サンプル点が**乗っている
    三角形**を候補にして厳密な点対面距離を取ると、同一メッシュで平均 0.002mm
    まで落ちる。候補は面の部分集合なので結果は常に真の表面距離以上＝
    「変化なし」を誤検出しない、という安全側の性質は保たれる。

    `distance_upper_bound` は速度の要。KDTree の最近傍は点群どうしが離れていると
    枝刈りが効かず 100 倍以上遅くなる（別座標系のメッシュで 0.05s → 5.6s）。
    上界を渡せば 0.01s で済み、超えた点は頂点 KDTree の粗い距離で埋める
    （そこまで離れていれば判定は「変化あり」で確定なので精度は要らない）。
    """
    k = min(_CAND_K, len(other_pts))
    dd, ii = cKDTree(other_pts).query(pts, k=k, workers=-1,
                                      distance_upper_bound=_FAR_CAP)
    if k == 1:
        dd, ii = dd[:, None], ii[:, None]
    d = np.ascontiguousarray(dd[:, 0])
    finite = np.isfinite(d)

    tri = np.asarray(other.triangles)
    near = np.flatnonzero(finite)
    for s in range(0, near.size, _CHUNK):
        sl = near[s:s + _CHUNK]
        # 近傍が k 個に満たない点には番兵（=len(other_pts)）が入る。面 0 で埋める:
        # どの面への距離も真の表面距離以上なので、min に混ざっても過小評価しない。
        faces = other_face[np.where(ii[sl] < len(other_pts), ii[sl], 0)]
        q = np.repeat(pts[sl], k, axis=0)
        dt = np.linalg.norm(trimesh.triangles.closest_point(tri[faces.ravel()], q)
                            - q, axis=1)
        # 取込メッシュは退化三角形を含みうる。nan は min から外す。
        dt = np.nan_to_num(dt, nan=np.inf, posinf=np.inf)
        d[sl] = np.minimum(d[sl], dt.reshape(-1, k).min(axis=1))

    if not finite.all():
        verts = np.asarray(other.vertices, dtype=np.float64)
        d[~finite] = cKDTree(verts).query(pts[~finite], workers=-1)[0]
    return d


def _exact_dist(pts: np.ndarray, other: trimesh.Trimesh,
                sel: np.ndarray) -> np.ndarray:
    """sel の点だけ trimesh の厳密な点対面距離を出す。

    近い点なら約 0.12ms/点だが、**遠い点だと 5.4ms/点**になる（trimesh の
    `nearby_faces` が「最近傍頂点までの距離」を半径に rtree を引くので、
    離れた点ではメッシュの全面が候補になる）。呼ぶ前に `_REFINE_MAX` で
    遠い点を落としておくこと。
    """
    from trimesh.proximity import ProximityQuery
    return ProximityQuery(other).on_surface(pts[sel])[1]


def _verdict(dev: float | None) -> str:
    if dev is None:
        return "判定不可"
    if dev < DEV_UNCHANGED:
        return "変化なし"
    if dev < DEV_MINOR:
        return "軽微"
    return "変化あり"


def region_deviations(ref: trimesh.Trimesh, edited: trimesh.Trimesh,
                      regions: dict) -> list[dict]:
    """領域別の表面偏差。regions = {param_key: {z0, z1, side, label}}。

    同一 (z0, z1, side) の領域は1ゾーンに統合する。
    偏差 = max(編集→凍結, 凍結→編集) の点対面距離（追加・削除の両方を検出）。
    """
    ref_pts, ref_face = _sample(ref)
    ed_pts, ed_face = _sample(edited)
    d_ed = _estimate_dist(ed_pts, ref, ref_pts, ref_face)      # 編集面 → 凍結面
    d_ref = _estimate_dist(ref_pts, edited, ed_pts, ed_face)   # 凍結面 → 編集面

    # ゾーン統合
    zones: dict[tuple, dict] = {}
    for key, r in regions.items():
        zk = (r["z0"], r["z1"], r["side"])
        z = zones.setdefault(zk, {"z0": r["z0"], "z1": r["z1"], "side": r["side"],
                                  "labels": [], "params": []})
        if r["label"] not in z["labels"]:
            z["labels"].append(r["label"])
        z["params"].append(key)

    def mask(pts, z0, z1, side):
        # 領域境界の縁効果を避けるため 0.3mm 内側で評価
        m = (pts[:, 2] >= z0 + 0.3) & (pts[:, 2] <= z1 - 0.3)
        if side == "top":
            m &= pts[:, 1] > 0
        elif side == "bottom":
            m &= pts[:, 1] < 0
        return m

    # 出すのはゾーンごとの最大値なので、最大値になり得ない点を厳密化しても無駄。
    # 見積りは上界（d_true ≤ d_est）だから、d_est が「そのゾーンの見積り最大値
    # − _EST_TOL」以下の点は最大値になれない。その帯だけ集めて 1 方向 1 回で流す。
    masks: list[tuple[dict, np.ndarray | None, np.ndarray | None]] = []
    cand_ed: list[np.ndarray] = []
    cand_ref: list[np.ndarray] = []
    for z in zones.values():
        m_ed = mask(ed_pts, z["z0"], z["z1"], z["side"])
        m_ref = mask(ref_pts, z["z0"], z["z1"], z["side"])
        if m_ed.sum() < 50 or m_ref.sum() < 50:
            masks.append((z, None, None))
            continue
        thr = max(_REFINE_MIN,
                  max(d_ed[m_ed].max(), d_ref[m_ref].max()) - _EST_TOL)
        cand_ed.append(np.flatnonzero(m_ed & (d_ed > thr) & (d_ed < _REFINE_MAX)))
        cand_ref.append(np.flatnonzero(m_ref & (d_ref > thr) & (d_ref < _REFINE_MAX)))
        masks.append((z, m_ed, m_ref))

    for cands, d, pts, other in ((cand_ed, d_ed, ed_pts, ref),
                                 (cand_ref, d_ref, ref_pts, edited)):
        if not cands:
            continue
        sel = np.unique(np.concatenate(cands))
        # 上限に当たった分は見積り値のまま＝過大評価側なので安全。最大値に効く
        # （＝距離の大きい）点から採る。
        if sel.size > _MAX_EXACT:
            sel = sel[np.argsort(-d[sel])[:_MAX_EXACT]]
        if sel.size:
            d[sel] = np.minimum(d[sel], _exact_dist(pts, other, sel))

    out = []
    for z, m_ed, m_ref in masks:
        if m_ed is None:
            dev = None
        else:
            dev = float(max(d_ed[m_ed].max(), d_ref[m_ref].max()))
        out.append({
            "label": " / ".join(z["labels"]),
            "params": z["params"],
            "z0": z["z0"], "z1": z["z1"], "side": z["side"],
            "max_dev_mm": round(dev, 3) if dev is not None else None,
            "verdict": _verdict(dev),
        })
    # 偏差の大きい順
    out.sort(key=lambda r: -(r["max_dev_mm"] or 0.0))
    return out
