"""部品表（BOM）出力。"""
from __future__ import annotations

import csv
import io


def bom_csv(rows: list[dict], project_name: str) -> str:
    """BOM を CSV 文字列にする。ファイル保存時は utf-8-sig（Excel互換）で書くこと。"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([f"部品表 - {project_name}"])
    w.writerow(["区分", "品名", "数量", "材料", "備考"])
    for r in rows:
        w.writerow([r["type"], r["name"], r["qty"], r["material"], r["note"]])
    return buf.getvalue()
