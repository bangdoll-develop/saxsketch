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
注意: 食品接触適合材料を指定してください。
"""
