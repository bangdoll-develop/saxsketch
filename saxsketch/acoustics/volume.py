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

    公表実測の頂点距離が `missing_cone_length_mm` にあればそれを優先する。導出は
    半頂角とネック内径の推定に二重に依存し、アルトでは実測 217.5mm に対し 241.7mm と
    11% 長く出る。実測がある箇所だけ差し替え、無い箇所は導出のまま残して食い違いを表示する
    （無い箇所を実測に合わせて逆算すると、どの量が間違っていたのか分からなくなる）。

    Returns: {"cc", "apex_distance_mm", "throat_radius_mm", "tan_theta", "source",
              "derived_apex_mm"}
    """
    r0 = size_info["neck_bore_id_mm"] / 2.0
    derived = r0 / math.tan(math.radians(size_info["cone_half_angle_deg"]))
    measured = size_info.get("missing_cone_length_mm")
    x0 = float(measured) if measured else derived
    return {
        "cc": math.pi * r0 * r0 * x0 / 3.0 / 1000.0,
        "apex_distance_mm": x0,
        "throat_radius_mm": r0,
        # 採用した頂点距離と整合する広がり。実測を採ると半頂角は公称と少しずれるが、
        # 円錐として自己矛盾しない方を優先する（共鳴管の生成が同じ値を使うため）。
        "tan_theta": r0 / x0,
        "source": "measured" if measured else "derived",
        "derived_apex_mm": derived,
    }


def tier1_report(cavity_vol: dict, size_info: dict,
                 headroom_cc: float | None = None) -> dict:
    """cavity_vol: {"total_cc": float, "effective_cc": float}

    headroom_cc: `chamber_ratio` をスライダ上限まで上げたときに**まだ増やせる**実効
    容積 [cc]（`profiles.chamber_headroom_cc`）。容積を増やす助言を出しておいて、実は
    上限まで上げても届かない、という状態を避けるために使う。None なら助言しない。

    以前はここに真偽値 `saturated`（＝チェンバー断面が全部外殻に接している）を
    渡していたが、実測から起こした形状ではそれが永久に False で、分岐ごと到達不能
    だった。判定すべきは幾何の接触ではなく「上限まで上げて目標に届くか」。
    """
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
        if headroom_cc is not None and effective + headroom_cc < target:
            advice += (f"ただしチェンバー断面積比を上限まで上げても増えるのは "
                       f"+{headroom_cc:.2f}cc（{effective + headroom_cc:.1f}cc）までで、"
                       f"目標 {target:.1f}cc には**届かない**。頭打ちの主因は外殻の肉厚で、"
                       f"これ以上増やすにはボディ径を上げるか最小肉厚を下げる必要がある。")
    else:
        status = "flat"
        advice = (f"実効容積が欠損円錐より約{ratio * 100:.0f}%大きく低め傾向。"
                  f"コークを深めに挿すか、スロート断面積比の縮小を検討。")

    if cone["source"] == "measured":
        origin = (f"欠損円錐長は公表実測 {cone['apex_distance_mm']:.1f}mm を採用"
                  f"（同じネック内径 {size_info['neck_bore_id_mm']}mm と半頂角 "
                  f"{size_info['cone_half_angle_deg']}° から導出すると "
                  f"{cone['derived_apex_mm']:.0f}mm で "
                  f"{(cone['apex_distance_mm'] / cone['derived_apex_mm'] - 1) * 100:+.0f}% ずれる）。")
    else:
        origin = (f"欠損円錐長は半頂角 {size_info['cone_half_angle_deg']}°・ネック小端内径 "
                  f"{size_info['neck_bore_id_mm']}mm から導出（頂点まで "
                  f"{cone['apex_distance_mm']:.0f}mm）。このサイズには公表実測が無い。")

    return {
        "total_cc": round(cavity_vol["total_cc"], 2),
        "effective_cc": round(effective, 2),
        "target_cc": round(target, 2),
        "deviation_cents": round(cents, 1),
        "status": status,
        "advice": advice,
        "note": (origin + "ネック内径はテノン外径からの推定値なので、自分のネック小端を"
                 "ノギスで測って置き換えるのが最も確実（±は目安）。"),
    }
