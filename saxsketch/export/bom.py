"""部品表（BOM）出力。"""
from __future__ import annotations

import csv
import io

from saxsketch import i18n

#: 表計算ソフトが**数式として解釈してしまう**先頭文字。
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _cell(value) -> str:
    """CSV の 1 セル。数式に化ける文字列の先頭にアポストロフィを置く。

    BOM にはプロジェクト名と部品名が入り、どちらも利用者が打った文字列
    （他人から `.wproj` をもらえば他人の文字列）である。この CSV は
    **入稿 ZIP に入って印刷業者の Excel で開かれる**ので、`=HYPERLINK(...)` や
    `=cmd|...` を素通しにすると、こちらが仕込んだのと変わらない。

    **数として読める値は触らない。** 数量や寸法は負になることがあり、
    `-1.5` にアポストロフィを付けると Excel で文字列になって合計が狂う。
    危ないのは「数式に見えるのに数ではない」セルだけ。
    """
    s = "" if value is None else str(value)
    if not s.startswith(_FORMULA_LEAD):
        return s
    try:
        float(s)
    except ValueError:
        return "'" + s
    return s


def bom_csv(rows: list[dict], project_name: str) -> str:
    """BOM を CSV 文字列にする。ファイル保存時は utf-8-sig（Excel互換）で書くこと。"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([_cell(i18n.t("部品表 - {name}", name=project_name))])
    w.writerow([i18n.t("区分"), i18n.t("品名"), i18n.t("数量"),
                i18n.t("材料"), i18n.t("備考")])
    for r in rows:
        w.writerow([_cell(r["type"]), _cell(r["name"]), _cell(r["qty"]),
                    _cell(r["material"]), _cell(r["note"])])
    return buf.getvalue()


def bom_csv_set(rows_by_member: list[tuple[str, list[dict]]], set_name: str) -> str:
    """セット 1 式の BOM。**先頭に部品の列を足す**（どの部品の行かが消えない）。

    列を足すだけで行の中身は単体と同じ —— 発注側が見るのは同じ表で、違いは
    「どの部品のぶんか」だけ。
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([_cell(i18n.t("部品表 - {name}", name=set_name))])
    w.writerow([i18n.t("部品"), i18n.t("区分"), i18n.t("品名"),
                i18n.t("数量"), i18n.t("材料"), i18n.t("備考")])
    for label, rows in rows_by_member:
        for r in rows:
            w.writerow([_cell(label), _cell(r["type"]), _cell(r["name"]),
                        _cell(r["qty"]), _cell(r["material"]), _cell(r["note"])])
    return buf.getvalue()
