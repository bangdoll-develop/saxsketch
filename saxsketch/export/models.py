"""3Dモデルのエクスポート（STL / STEP / 3MF）。"""
from __future__ import annotations

from pathlib import Path


def export_model(part, out_path: str | Path, fmt: str,
                 tolerance: float = 0.02, angular_tolerance: float = 0.1) -> Path:
    """part(build123d Solid/Part) を指定形式で書き出す。

    **STL と 3MF は同じ Part を同じ許容でメッシュ化する。** 3MF を直接パースして
    三角形数・頂点数・周方向の刻みが STL と一致することを確認済み。食い違う理由は
    無い。STEP はメッシュではないのでここは効かない。

    既定の根拠（アルト、リガチャー座の中で胴の円周を実測。三角形分割を毎回
    捨ててから測った値）:

      | linear | angular | 面数   | STL    | 周方向の刻み | 弦誤差    |
      |--------|---------|--------|--------|--------------|-----------|
      | 0.05   | 0.3     |  8,444 | 0.42MB | 4.49°        | 0.0109 mm |
      | 0.02   | 0.3     |  8,540 | 0.43MB | 4.49°        | 0.0109 mm |
      | 0.01   | 0.3     |  8,976 | 0.45MB | 4.49°        | 0.0109 mm |
      | 0.02   | **0.1** | 15,072 | 0.75MB | **0.86°**    | 0.0004 mm |
      | 0.005  | 0.1     | 16,694 | 0.83MB | 0.86°        | 0.0004 mm |
      | 0.02   | 0.05    | 31,122 | 1.56MB | 0.10°        | 0.0000 mm |

    **周方向を割っているのは angular のほうで、linear はほとんど効かない**
    （0.05 → 0.01 で面数 8,444 → 8,976、刻みは 4.49° のまま）。0.3 のままだと
    胴が 80 角柱で、画面でも印刷物でもはっきり紋様が見える。0.1 にすると 419 角柱。
    0.05 まで行くと面数が倍になるのに刻みは既に見えない域なので、そこは取らない。

    **測り直すときの注意**: OCCT は三角形分割を形状に持ち回り、`BRepMesh` は
    linear が細かくなったときしか作り直さない。だから 1 プロセスで許容を振ると
    **前の呼び出しの結果が残って angular の効きが消えて見える**（実際にこれで
    1 度誤った結論を出した）。`BRepTools.Clean_s(part.wrapped)` を挟むこと。

    寸法としては 4.49° の弦誤差 0.0109mm でも設計クリアランス 0.25mm・刻み
    0.05mm に対して 1〜2 桁小さく、**篏合には効かない**。0.1 へ細かくするのは
    見え方のためで、「見えている凹凸が寸法誤差かもしれない」と疑わせないため。

    **メッシュ許容では消えない誤差が別にある** —— `revolve_profile` は多角形の
    母線を回すので、母線方向の弦誤差はソリッド自体に焼き込まれている
    （`profiles.body_stations`。3 サイズで 0.026〜0.034mm ＝ 周方向より 1 桁大きい）。
    STEP だけ紋様が出ないのは、そちらがスプライン母線（`profiles.body_segments`）
    だから。**形が違うのはこの母線のぶんで、周方向ではない。**
    """
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
