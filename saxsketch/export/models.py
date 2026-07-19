"""3Dモデルのエクスポート（STL / STEP / 3MF）。"""
from __future__ import annotations

from pathlib import Path


def export_model(part, out_path: str | Path, fmt: str,
                 tolerance: float = 0.02, angular_tolerance: float = 0.3) -> Path:
    """part(build123d Solid/Part) を指定形式で書き出す。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "stl":
        from build123d import export_stl
        export_stl(part, str(out_path), tolerance=tolerance,
                   angular_tolerance=angular_tolerance)
    elif fmt == "step":
        from build123d import export_step
        export_step(part, str(out_path))
    elif fmt == "3mf":
        from build123d import Mesher, Unit
        mesher = Mesher(unit=Unit.MM)
        mesher.add_shape(part, linear_deflection=tolerance,
                         angular_deflection=angular_tolerance)
        mesher.write(str(out_path))
    else:
        raise ValueError(f"未対応の形式: {fmt}")
    return out_path


def check_mesh(stl_path: str | Path) -> dict:
    """出力 STL の品質検査（水密性・自己交差など）。"""
    import trimesh
    m = trimesh.load(str(stl_path))
    return {
        "watertight": bool(m.is_watertight),
        "winding_consistent": bool(m.is_winding_consistent),
        "faces": int(len(m.faces)),
        "volume_cc": round(float(m.volume) / 1000.0, 2) if m.is_watertight else None,
    }
