"""Tier1: 内容積 vs 欠損円錐（missing cone）による音程チェック。

サクソフォンは円錐管の頂点側が切り落とされており、マウスピース内容積が
その「欠損円錐」の体積を代替する（Benade）。実効容積が欠損円錐より
小さい→高め傾向、大きい→低め傾向になる。ここでは一次近似として
容積偏差率からセント偏差を推定する（係数は経験的目安）。

楽器非依存: 体積計算はコンポーネント側（profiles）が行い、結果 dict を受け取る。
"""
from __future__ import annotations

import math

# 容積 10% 偏差 ≒ 25 セントの目安（低音域・一次近似）
CENTS_PER_VOLUME_RATIO = 250.0
# リード・唇の等価コンプライアンス分（cc換算の目安）
REED_EQUIVALENT_CC = 1.0


def missing_cone(size_info: dict) -> dict:
    """欠損円錐の長さと体積を、円錐の半頂角とネック小端の内径から導出する。

    サックスのボアは円錐で頂点側が切り落とされている。切断面（＝ネック小端）の
    半径 r0 と半頂角 θ から、頂点までの距離 x0 = r0 / tanθ、体積 V = π r0² x0 / 3。

    体積を定数で持たない理由: 定数だと出所も検算手段も失われる。半頂角は実測の
    文献値（ソプラノ 1.74° / テナー 1.52°）、ネック小端内径はユーザーがノギスで
    測れる量なので、どちらも後から実測で置き換えられる。

    Returns: {"cc", "apex_distance_mm", "throat_radius_mm", "tan_theta"}
    """
    r0 = size_info["neck_bore_id_mm"] / 2.0
    tan_theta = math.tan(math.radians(size_info["cone_half_angle_deg"]))
    x0 = r0 / tan_theta
    return {
        "cc": math.pi * r0 * r0 * x0 / 3.0 / 1000.0,
        "apex_distance_mm": x0,
        "throat_radius_mm": r0,
        "tan_theta": tan_theta,
    }


def tier1_report(cavity_vol: dict, size_info: dict) -> dict:
    """cavity_vol: {"total_cc": float, "effective_cc": float}"""
    cone = missing_cone(size_info)
    target = cone["cc"]
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
        "note": (f"欠損円錐は半頂角 {size_info['cone_half_angle_deg']}°・ネック小端内径 "
                 f"{size_info['neck_bore_id_mm']}mm から導出（頂点まで "
                 f"{cone['apex_distance_mm']:.0f}mm）。どちらも実測で校正できる（±は目安）。"),
    }
