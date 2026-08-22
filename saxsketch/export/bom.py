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


def bom_csv_set(rows_by_member: list[tuple[str, list[dict]]], set_name: str) -> str:
    """セット 1 式の BOM。**先頭に部品の列を足す**（どの部品の行かが消えない）。

    列を足すだけで行の中身は単体と同じ —— 発注側が見るのは同じ表で、違いは
    「どの部品のぶんか」だけ。
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([f"部品表 - {set_name}"])
    w.writerow(["部品", "区分", "品名", "数量", "材料", "備考"])
    for label, rows in rows_by_member:
        for r in rows:
            w.writerow([label, r["type"], r["name"], r["qty"],
                        r["material"], r["note"]])
    return buf.getvalue()
