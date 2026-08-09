"""Tier1: 欠損円錐（missing cone）の導出と、第1共鳴による音程チェック。

サクソフォンは円錐管の頂点側が切り落とされており、マウスピース内容積が
その「欠損円錐」を代替する（Benade）。`missing_cone()` はその円錐を半頂角と
ネック小端内径から導出する。

**音程の判定は容積からは作らない。** 以前はここに
`cents = -250 × (実効容積 - 欠損円錐容積) / 欠損円錐容積` という一行の経験則を
置いていたが、実測で外れることが確かめられた:

- テナー実測形状の実効容積は欠損円錐より **+23%**（13.69cc vs 11.09cc）。この規則は
  -81 セントと言う。同じ形状を共鳴管として解くと **+0.3 セント**（TMM）／
  **+1.3 セント**（OpenWind）。
- 理由は、マウスピースが**代替する欠損円錐より 161mm 短い**（実効 85.5mm vs
  246.8mm）こと。「太い」ぶんと「短い」ぶんが相殺する。容積 1 個から音程を作る
  規則は、この相殺を構造的に表せない。
- 係数を引き直しても直らない。等価円錐 `x0·(V/Vc)^(1/3)` を代入する案は 1.7 倍
  過小、集中コンプライアンス（切り詰め円錐の厳密アドミタンス）は 8 倍過小で、
  どれも 1 個の数字からは出せなかった。

いまは `openwind_bridge.first_resonance_cents()`（TMM、実測 31〜52ms）が解いた
第1共鳴を受け取る。Tier2 との違いはエンジンだけで、モデルは同じ。
容積の比較（`effective_cc` / `target_cc`）は**理由の説明**として残す。

楽器非依存: 体積計算はコンポーネント側（profiles）が行い、結果 dict を受け取る。
"""
from __future__ import annotations

import math


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


def tier1_report(cavity_vol: dict, size_info: dict, cents: float,
                 headroom_cc: float | None = None) -> dict:
    """cavity_vol: {"total_cc": float, "effective_cc": float}

    cents: 組み立て共鳴管の第1共鳴が目標低音から外れているセント数
    （`openwind_bridge.first_resonance_cents`）。**呼び出し側が渡す。**
    `openwind_bridge` がこのモジュールの `missing_cone` を使っているので、
    ここから import すると循環になる。

    headroom_cc: `chamber_ratio` をスライダ上限まで上げたときに**まだ増やせる**実効
    容積 [cc]（`profiles.chamber_headroom_cc`）。容積を増やす助言を出しておいて、実は
    上限まで上げても届かない、という状態を避けるために使う。None なら助言しない。

    以前はここに真偽値 `saturated`（＝チェンバー断面が全部外殻に接している）を
    渡していたが、実測から起こした形状ではそれが永久に False で、分岐ごと到達不能
    だった。判定すべきは幾何の接触ではなく「上限まで上げて目標に届くか」。
    """
    cone = missing_cone(size_info)
    target = cone["cc"]
    effective = cavity_vol["effective_cc"]
    ratio = (effective - target) / target

    if abs(cents) < 10:
        status, advice = "ok", "音程バランス良好。コーク標準位置で使用できます。"
    elif cents > 0:
        status = "sharp"
        advice = ("第1共鳴が目標より高い。コークを浅め（抜き気味）にするか、"
                  "スロート断面積比/ウィンドウ長の拡大を検討。")
        if headroom_cc is not None and effective + headroom_cc < target:
            advice += (f"ただしチェンバー断面積比を上限まで上げても増えるのは "
                       f"+{headroom_cc:.2f}cc（{effective + headroom_cc:.1f}cc）までで、"
                       f"欠損円錐 {target:.1f}cc には**届かない**。頭打ちの主因は外殻の"
                       f"肉厚で、これ以上増やすにはボディ径を上げるか最小肉厚を"
                       f"下げる必要がある。")
    else:
        status = "flat"
        advice = ("第1共鳴が目標より低い。コークを深めに挿すか、"
                  "スロート断面積比の縮小を検討。")

    # 容積の比較は**判定ではなく理由**として出す。両者は一対一で動かない:
    # マウスピースは代替する欠損円錐より短いので、容積が数十%多くても音程が
    # 合うことがある（テナー実測形状は +23% で +0.3 セント）。
    advice += (f"（実効容積 {effective:.2f}cc は欠損円錐 {target:.2f}cc の "
               f"{ratio * 100:+.0f}%。マウスピースは代替する円錐より短いので、"
               f"容積差はそのまま音程差にはならない。）")

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
        "note": (origin + "ネック小端内径は3サイズとも実測値（descriptor の "
                 "neck_dimensions_source に測った個体がある）。セントは容積からの"
                 "換算ではなく、この形状の共鳴管を伝達行列法で解いた第1共鳴。"),
    }
