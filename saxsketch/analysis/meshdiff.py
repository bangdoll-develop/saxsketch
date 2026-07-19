"""取込メッシュと凍結形状の差分解析（楽器非依存の汎用部）。

- load_mesh: STL/3MF/OBJ/STEP を trimesh.Trimesh に読み込む
- mesh_quality: 水密・法線・体積
- region_deviations: パラメータ影響領域ごとの表面偏差
  （両メッシュを高密度サンプリングし KDTree 最近傍距離。分解能 約±0.15mm）
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

SAMPLE_COUNT = 200_000
# サンプリング分解能に応じた判定しきい値 [mm]
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


def _surface_dist(pts: np.ndarray, other_pts: np.ndarray,
                  other: trimesh.Trimesh) -> np.ndarray:
    """pts から other 表面への距離。KDTree 粗選別 → 疑い点のみ厳密計算。"""
    d = cKDTree(other_pts).query(pts, workers=-1)[0]
    suspect = d > 0.12
    if suspect.any():
        from trimesh.proximity import ProximityQuery
        _, d_exact, _ = ProximityQuery(other).on_surface(pts[suspect])
        d[suspect] = d_exact
    return d


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
    偏差 = max(編集→凍結, 凍結→編集) の最近傍距離（追加・削除の両方を検出）。
    """
    ref_pts, _ = trimesh.sample.sample_surface(ref, SAMPLE_COUNT)
    ed_pts, _ = trimesh.sample.sample_surface(edited, SAMPLE_COUNT)
    ref_pts = np.asarray(ref_pts)
    ed_pts = np.asarray(ed_pts)
    # 点対点の最近傍は疎な箇所で過大評価する（偽陽性）ため、
    # 疑わしい点だけ正確な「点対面」距離に置き換える2段構え。
    d_ed = _surface_dist(ed_pts, ref_pts, ref)    # 編集面 → 凍結面
    d_ref = _surface_dist(ref_pts, ed_pts, edited)  # 凍結面 → 編集面

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

    out = []
    for z in zones.values():
        m_ed = mask(ed_pts, z["z0"], z["z1"], z["side"])
        m_ref = mask(ref_pts, z["z0"], z["z1"], z["side"])
        if m_ed.sum() < 50 or m_ref.sum() < 50:
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
