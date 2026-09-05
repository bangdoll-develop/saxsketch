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

**判定はセントでもない。** `cork_depth`（コーク挿入深さ）はマウスピースの寸法では
なく、気温・リード・合わせる音程で演奏者が抜き差しするチューニングそのものである。
それを固定した状態のセントを判定に使うと、寸法の誤差とチューニングの自由度が混ざる。
Stage E がソプラノに付けた −31 セントはまさにそれで、全長 71.4mm の実物に 17.91mm
という当て推量の挿し込みを固定していたぶんだった。

いまは `openwind_bridge.tuning_position()` が解いた**合う挿し込み量**を受け取り、
それが実用域（浅い側はフェルール＋コルクが噛む下限、深い側は**押し込み限界の実測**
`insertion_limit_mm` = 27.1 / 36.4 / 36.0mm）に入るかで判定する。3 サイズとも入る:

    soprano 23.5mm / alto 13.6mm / tenor 20.9mm

深い側が実測になったことで、これは**モデル唯一の外部照合**になっている ——
合う挿し込み量は共鳴管と目標低音だけから解いていて、押し込み限界は入っていない。

そのとき実効容積は欠損円錐の +20〜26%（**以前は +21〜26% で「3 サイズで揃う」と書いていたが、アルトへ PHROX の窓の実測を入れた 2026-09-05 に崩れた** ——docs/print-inspection.md §11.4）。なお同日いったん alto +13.3% と記録したのは**`cavity_floor_y` の特異点のせいで床が 3.5 倍深く出ていたぶん**を含んでいた。特異点を直したら +20.4% に戻り、散らばりは 12.2 ポイント → 5.1 ポイントになった。**それでも「揃う」とは言えない**（alto だけ 21% を割る）ので、揃いが壊れたという結論そのものは変えない。挿し込み量と容積比という
独立な 2 つの指標が同じことを言っている。
容積の比較（`effective_cc` / `target_cc`）は**理由の説明**として残す。

**この挿し込み量は「あなたが実際に挿す深さ」の予測ではない。** 基準条件
（`openwind_bridge.TEMPERATURE_C` = 25°C、descriptor の `pitch_standard_hz` = 440Hz）で
第1共鳴が目標音に合う位置であって、それ以上のことは言っていない。実際の位置は
気温・リード・リガチャー・マウスピース個体・アンブシュアで動き、**このうち
モデルに入っているのは気温と合わせる音程の 2 つだけ**（リード・リガチャー・
アンブシュアは入っていない）。だから典型値との一致では検証できない。
検証できる形にすると「演奏者が実際に使う挿し込み量の**域**（最も深い位置と
最も浅い位置）に、この値が入るか」になる。

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

    頂点距離が `missing_cone_length_mm` にあればそれを優先する。導出は半頂角と
    ネック内径の推定に二重に依存し、アルトでは 217.5mm に対し 227.3mm と 4.5% 長く出る。
    値がある箇所だけ差し替え、無い箇所は導出のまま残して食い違いを表示する
    （無い箇所を合わせて逆算すると、どの量が間違っていたのか分からなくなる）。

    **アルトの 217.5 は「実測」と呼べない。** 出所を追うと descriptor の一文で
    終わり、文献名も測定者も日付も残っていない（`missing_cone_length_source` に
    追跡結果がある）。代わりの半頂角 1.6° も補間なので、これは**借り物 A と
    借り物 B の選択**であって測定の質では決まらない。落としても判定は動かない
    （アルトの `in_tune_mm` が 13.58 → 11.58mm、実用域の内側で status は ok のまま）
    ことを測ってあるので、値は動かさずに出所の弱さだけ記録してある。

    ここが返す `tan_theta` は `neck_profiles.bore_large_id` と
    `body_profiles.cone_tan` も読む。**1 つの楽器に円錐は 1 本**で、ネックも管体も
    Tier1 も同じ円錐でなければならない。

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


#: 実用域の端からこれだけ離れていないと「余裕が無い」扱いにする [mm]。
TUNING_MARGIN_MM = 2.0


def reference_conditions(size_info: dict) -> str:
    """`in_tune_mm` がどの条件での値かを書いた一文。

    ユーザーから「典型値は提示できない。マウスピース・リード・リガチャー・気温・
    アンブシュアすべてに影響される」という指摘があった。そのとおりで、モデルが
    出しているのは**基準条件での値**でしかない。条件を書かずに mm だけ出すと
    「あなたはここに挿すことになる」という主張に読める。
    """
    from . import openwind_bridge as ob
    return (f"合う挿し込み量は**基準条件での値**で、実際に挿す深さの予測ではない: "
            f"気温 {ob.TEMPERATURE_C:.0f}°C（音速 {ob.C_SOUND:.1f} m/s）で第1共鳴が "
            f"{size_info['low_note_label']} {size_info['low_note_sounding_hz']:.2f}Hz に"
            f"合う位置。実際の位置はリード・リガチャー・マウスピース個体・"
            f"アンブシュアでも動き、それらはモデルに入っていない。")


def tier1_report(cavity_vol: dict, size_info: dict, tuning: dict,
                 headroom_cc: float | None = None) -> dict:
    """cavity_vol: {"total_cc": float, "effective_cc": float}

    tuning: `openwind_bridge.tuning_position()` の結果。**呼び出し側が渡す。**
    `openwind_bridge` がこのモジュールの `missing_cone` を使っているので、
    ここから import すると循環になる。

    headroom_cc: `chamber_ratio` をスライダ上限まで上げたときに**まだ増やせる**実効
    容積 [cc]（`profiles.chamber_headroom_cc`）。容積を増やす助言を出しておいて、実は
    上限まで上げても届かない、という状態を避けるために使う。None なら助言しない。

    判定の主指標は**合う挿し込み量**であってセントではない。`cork_depth` は
    演奏者が抜き差しするチューニングそのものなので、それを固定した状態のセントを
    判定に使うと、寸法の誤差とチューニングの自由度が混ざる。問うべきは
    「目標音で鳴らせる挿し込み量が実際に届く範囲にあるか」。

    `in_tune_mm` は**基準条件での値であって典型値の予測ではない**（モジュールの
    docstring を見ること）。`note` に基準条件を書いて出すのはそのため。
    """
    cone = missing_cone(size_info)
    target = cone["cc"]
    effective = cavity_vol["effective_cc"]
    ratio = (effective - target) / target
    cents = tuning["cents_at_current"]
    z = tuning["in_tune_mm"]
    lo, hi = tuning["range_mm"]
    out_mm, in_mm = tuning["headroom_mm"]
    slope = tuning["cents_per_mm"]

    if not tuning["reachable"]:
        status = "unreachable"
        side = "深く" if z > hi else "浅く"
        advice = (f"目標音で鳴らせる挿し込み量が {z:.1f}mm で、実用域 "
                  f"{lo:.0f}〜{hi:.0f}mm の外にある（{side}挿さないと合わない）。"
                  f"チューニングでは埋められないので形状側を直す必要がある。")
        if headroom_cc is not None and effective + headroom_cc < target:
            advice += (f"チェンバー断面積比を上限まで上げても増えるのは "
                       f"+{headroom_cc:.2f}cc（{effective + headroom_cc:.1f}cc）までで、"
                       f"欠損円錐 {target:.1f}cc には**届かない**。頭打ちの主因は外殻の"
                       f"肉厚で、これ以上増やすにはボディ径を上げるか最小肉厚を"
                       f"下げる必要がある。")
    else:
        tight = min(out_mm, in_mm) < TUNING_MARGIN_MM
        status = "tight" if tight else "ok"
        advice = (f"挿し込み {z:.1f}mm で目標音に合う（実用域 {lo:.0f}〜{hi:.0f}mm）。"
                  f"1mm 押し込むと {slope:+.2f} セント動くので、"
                  f"高い側へ約 {in_mm * slope:+.0f} / 低い側へ約 {-out_mm * slope:+.0f} "
                  f"セントのチューニング幅がある。")
        if tight:
            # ここで「余裕は n mm」と数字を出さない。深い側の上限は実測だが、
            # その実測は「これ以上押し込んだらまずい」という**演奏者の判断**で、
            # しかもネック単独でもマウスピース単独でもなく**組の性質**。
            # コルクを巻き直しても銘柄を替えても動く。この境目に精度を主張すると、
            # 持っていない分解能で「合う／合わない」を言うことになる。
            advice += (f"ただし実用域の端まで 2mm を切っている。深い側の "
                       f"{hi:.1f}mm は")
            if size_info.get("insertion_limit_mm") is not None:
                advice += ("**実測**だが、これは機械的な止まりではなく"
                           "「これ以上押し込んだらまずい」という判断で、しかも"
                           "ネック単独でもマウスピース単独でもなく**組**の性質。"
                           "コルクを巻き直しても銘柄を替えても動く。")
            else:
                advice += ("コルク帯長からの**推定**で、そこは厳しい公差の掛かった"
                           "部位ではない（帯の幅は周方向でも一定でない）。しかも"
                           "実測した 3 サイズはいずれも推定と食い違い、"
                           "向きすら揃っていない。")
            advice += ("数字で詰めずに、実物のマウスピースを"
                       "止まるまで押し込んでどこで止まるかを確かめること。")

    # 容積の比較は**判定ではなく理由**として出す。両者は一対一で動かない:
    # マウスピースは代替する欠損円錐より短いので、容積が数十%多くても音程が
    # 合うことがある（合う挿し込み量では soprano +25.5 / alto +20.4 /
    # tenor +23.4%。**揃っていたのはアルトが未実測だったからで、実測を入れたら崩れた**。
    # 一度 alto +13.3 と記録したが、あれは `cavity_floor_y` の特異点ぶんを含む）。
    advice += (f"（実効容積 {effective:.2f}cc は欠損円錐 {target:.2f}cc の "
               f"{ratio * 100:+.0f}%。マウスピースは代替する円錐より短いので、"
               f"容積差はそのまま音程差にはならない。）")

    if cone["source"] == "measured":
        # 「実測」と書かない。出所を追うと descriptor の一文で終わり、文献名も
        # 測定者も日付も残っていない（descriptor の missing_cone_length_source）。
        origin = (f"欠損円錐長は descriptor の {cone['apex_distance_mm']:.1f}mm を採用"
                  f"（同じネック内径 {size_info['neck_bore_id_mm']}mm と半頂角 "
                  f"{size_info['cone_half_angle_deg']}° から導出すると "
                  f"{cone['derived_apex_mm']:.1f}mm で "
                  f"{(cone['apex_distance_mm'] / cone['derived_apex_mm'] - 1) * 100:+.1f}% ずれる）。"
                  f"**この値は出典未記録の借り物**で、代わりの半頂角も補間なので"
                  f"どちらも実測ではない。落としても判定は動かないことは確認済み。")
    else:
        origin = (f"欠損円錐長は半頂角 {size_info['cone_half_angle_deg']}°・ネック小端内径 "
                  f"{size_info['neck_bore_id_mm']}mm から導出（頂点まで "
                  f"{cone['apex_distance_mm']:.0f}mm）。このサイズには公表実測が無い。")

    return {
        "total_cc": round(cavity_vol["total_cc"], 2),
        "effective_cc": round(effective, 2),
        "target_cc": round(target, 2),
        "deviation_cents": round(cents, 1),
        "in_tune_mm": round(z, 2),
        "cork_range_mm": [round(lo, 1), round(hi, 1)],
        "cents_per_mm": round(slope, 2),
        "current_mm": round(tuning["current_mm"], 2),
        "tuning_method": tuning["method"],
        "status": status,
        "advice": advice,
        "note": (origin + "ネック小端内径は3サイズとも実測値（descriptor の "
                 "neck_dimensions_source に測った個体がある）。セントは容積からの"
                 "換算ではなく、この形状の共鳴管を伝達行列法で解いた第1共鳴。"
                 "deviation_cents は**いまの挿し込み量での**値で、判定そのものは"
                 "合う挿し込み量が実用域に入るかで出している。"
                 + reference_conditions(size_info)),
    }
