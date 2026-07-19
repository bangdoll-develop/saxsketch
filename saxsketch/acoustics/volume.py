"""Tier1: 内容積 vs 欠損円錐（missing cone）による音程チェック。

サクソフォンは円錐管の頂点側が切り落とされており、マウスピース内容積が
その「欠損円錐」の体積を代替する（Benade）。実効容積が欠損円錐より
小さい→高め傾向、大きい→低め傾向になる。ここでは一次近似として
容積偏差率からセント偏差を推定する（係数は経験的目安）。

楽器非依存: 体積計算はコンポーネント側（profiles）が行い、結果 dict を受け取る。
"""
from __future__ import annotations

# 容積 10% 偏差 ≒ 25 セントの目安（低音域・一次近似）
CENTS_PER_VOLUME_RATIO = 250.0
# リード・唇の等価コンプライアンス分（cc換算の目安）
REED_EQUIVALENT_CC = 1.0


def tier1_report(cavity_vol: dict, size_info: dict) -> dict:
    """cavity_vol: {"total_cc": float, "effective_cc": float}"""
    target = size_info["missing_cone_volume_cc"]
    effective = cavity_vol["effective_cc"] + REED_EQUIVALENT_CC
    ratio = (effective - target) / target
    cents = -CENTS_PER_VOLUME_RATIO * ratio  # 容積過多 → ピッチ低下

    if abs(cents) < 10:
        status, advice = "ok", "音程バランス良好。コーク標準位置で使用できます。"
    elif cents > 0:
        status = "sharp"
        advice = (f"実効容積が欠損円錐より約{-ratio * 100:.0f}%小さく高め傾向。"
                  f"コークを浅め（抜き気味）にするか、スロート断面積比/ウィンドウ長の拡大を検討。")
    else:
        status = "flat"
        advice = (f"実効容積が欠損円錐より約{ratio * 100:.0f}%大きく低め傾向。"
                  f"コークを深めに挿すか、スロート断面積比の縮小を検討。")

    return {
        "total_cc": round(cavity_vol["total_cc"], 2),
        "effective_cc": round(effective, 2),
        "target_cc": round(target, 2),
        "deviation_cents": round(cents, 1),
        "status": status,
        "advice": advice,
        "note": "欠損円錐体積は文献ベースの推定値。楽器実測での校正を推奨（±は目安）。",
    }
