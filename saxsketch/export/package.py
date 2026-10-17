"""入稿パッケージ（ZIP）生成。オンライン3Dプリントサービスへそのまま渡せる構成。"""
from __future__ import annotations

import zipfile
from pathlib import Path


def build_package(zip_path: str | Path, files: dict[str, Path | str | bytes],
                  readme_text: str) -> Path:
    """files: {アーカイブ内名: 実ファイルパス or bytes/str}"""
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme_text)
        for arcname, src in files.items():
            if isinstance(src, (bytes, str)) and not isinstance(src, Path):
                data = src.encode("utf-8-sig") if isinstance(src, str) else src
                zf.writestr(arcname, data)
            else:
                zf.write(str(src), arcname)
    return zip_path


def readme_text_set(set_name: str, members: list[dict]) -> str:
    """セット 1 式の README。**部品ごとのフォルダ構成をそのまま書く。**

    Args:
        members: [{"label", "dir", "material_label", "dims": [(名, 値), …]}, …]
    """
    blocks = ""
    for m in members:
        dim_lines = "\n".join(f"    - {k}: {v}" for k, v in m["dims"])
        blocks += (f"\n[{m['label']}]  → {m['dir']}/\n"
                   f"  推奨材料: {m['material_label']}\n"
                   f"  主要寸法:\n{dim_lines}\n")
    return f"""SaxSketch 入稿パッケージ（セット）
========================================
プロジェクト: {set_name}
用途: 管楽器のマウスピース一式（口に触れる部品）

構成:
{blocks}
共通ファイル:
  - spec.html  … 製作仕様書（全部品＋部品どうしの適合）
  - bom.csv    … 部品表（先頭列がどの部品かを示す）

各部品フォルダの中身:
  - model.stl  … 3Dプリント用メッシュ（単位: mm）
  - model.step … 精密CAD形状（寸法検証用）
  - model.3mf  … 単位情報付きメッシュ

注意: 食品接触適合材料を指定してください（口に入れる部品です）。
      レジンは二次硬化と洗浄を十分に。PLA は約 55℃ で変形します。
      寸法・音響指標は推定であり、できあがる物の安全性・耐久性・
      適合性を保証するものではありません。
部品ごとに推奨材料が違うことがあります（上記を参照）。
"""


def readme_text(project_name: str, dims: list, material_label: str) -> str:
    dim_lines = "\n".join(f"  - {k}: {v}" for k, v in dims)
    return f"""SaxSketch 入稿パッケージ
========================================
プロジェクト: {project_name}
用途: 管楽器マウスピース（口に触れる部品）

同梱ファイル:
  - model.stl  … 3Dプリント用メッシュ（単位: mm）
  - model.step … 精密CAD形状（寸法検証用）
  - model.3mf  … 単位情報付きメッシュ
  - spec.html  … 製作仕様書（寸法・印刷推奨条件）
  - bom.csv    … 部品表

主要寸法:
{dim_lines}

推奨材料: {material_label}
注意: 食品接触適合材料を指定してください（口に入れる部品です）。
      レジンは二次硬化と洗浄を十分に。PLA は約 55℃ で変形します。
      寸法・音響指標は推定であり、できあがる物の安全性・耐久性・
      適合性を保証するものではありません。
"""
