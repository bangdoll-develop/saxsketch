"""SaxSketch 結合テスト: ジオメトリ・音響・プロジェクトI/O・API。"""
import collections
import json
import math
from pathlib import Path

import pytest

from saxsketch.core.registry import get_registry
from saxsketch.core.project import Project
from saxsketch.instruments.saxophone.components import profiles


@pytest.fixture(scope="module")
def alto():
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    params = {s.key: s.default for s in comp.param_specs()}
    return comp, params


# ------------------------------------------------------------------ 実物基準の校正（Phase 3.5）

SIZES = ("soprano", "alto", "tenor")


def _size_info(template_id: str) -> dict:
    return get_registry().get("saxophone").make_component(
        "mouthpiece", template_id).size_info


def test_missing_cone_derived_not_constant():
    """欠損円錐は半頂角とネック内径から導出され、定数を持たないこと。"""
    from saxsketch.acoustics import volume as ac_volume
    for tid in SIZES:
        si = _size_info(tid)
        assert "missing_cone_volume_cc" not in si     # 定数は廃止
        cone = ac_volume.missing_cone(si)
        assert cone["cc"] > 0 and cone["apex_distance_mm"] > 0
    # アルトだけ頂点距離 217.5mm が入っているのでそれを採る。実測ネック内径 12.7mm から
    # 導出すると 227.3mm で 4.5% 長い。内径をテノン外径からの一律規則で推定していた頃は
    # 241.7mm ＝ 11% だったので、ネックを実測したぶんだけ食い違いが縮んだ。
    # 値がある箇所だけ差し替え、無い箇所は導出のまま残す方針は変えない。導出値を
    # 217.5 へ合わせに行かない（合わせると半頂角が実測の顔をした逆算値になる）。
    # **217.5 自体は出典未記録の借り物**（2026-08-15 に出所を追跡）。代わりの半頂角も
    # 補間なのでどちらも実測ではなく、落としても判定は動かない（アルトの in_tune_mm は
    # 13.58 → 11.58mm で実用域の内側、status は ok のまま）。だから値は動かさない。
    alto_cone = ac_volume.missing_cone(_size_info("alto"))
    assert alto_cone["source"] == "measured"
    assert alto_cone["apex_distance_mm"] == pytest.approx(217.5)
    assert alto_cone["derived_apex_mm"] == pytest.approx(227.3, abs=1.0)
    # 採用した頂点距離と広がりが自己矛盾しないこと（共鳴管の生成が同じ値を使う）
    assert alto_cone["throat_radius_mm"] / alto_cone["tan_theta"] == pytest.approx(217.5)
    assert ac_volume.missing_cone(_size_info("tenor"))["source"] == "derived"

    # サイズ順に単調（ソプラノ < アルト < テナー）
    ccs = [ac_volume.missing_cone(_size_info(t))["cc"] for t in SIZES]
    assert ccs[0] < ccs[1] < ccs[2]


# 実測した残差 [cent]。Tier1 = 組み立て共鳴管の第1共鳴を伝達行列法で解いた値
# （`openwind_bridge.first_resonance_cents`、TMM 固定）。
#
# 直前の値は {-320.4, -73.8, -81.2} で、Tier2 と 4 倍食い違っていた。Stage B は
# それを「Tier1 の校正定数が怪しい」と記録して閉じたが、**食い違いの主因は
# 物差しの側にあった**。Stage E で 2 つ直した:
#
# 1. 音速の食い違い。ジオメトリの全長を `C_SOUND = 343.0`（20℃相当）で作りながら、
#    OpenWind へは `temperature=25.0`（音速 347.13）を渡していた。同じジオメトリを
#    2 エンジンで解くと 23.9 / 24.7 / 26.0 セント違い、うち 20.7 は音速比そのもの。
# 2. 延長円錐が長すぎた。`l_ext = c/(2·f1) − x0` は**開口端の放射補正がゼロの
#    理想円錐**の式。ソルバは放射を含むので、**マウスピースを外して理想円錐だけを
#    鳴らしても -52.3 / -48.2 / -44.5 セント**低かった。報告していた残差はほとんど
#    これで、形状の話ではなかった。いまは同じソルバで理想円錐が f1 に鳴る長さを
#    求めている（`_calibrate_extension`、実測で 0.02〜0.03 セントに収束）。
#
# 直した結果、**alto と tenor のマウスピースは欠損円錐の代替として ±1 セントで
# 成立している**。実物 WindyCity の実測形状 ＋ 実測ネックという、推定値が 1 つも
# 残っていない組が、正しく「合っている」と出るようになった。
#
# 容積の一行規則を捨てた理由もここにある。テナーの実効容積は欠損円錐より +23%
# あるのに音程は +0.3 セント。マウスピースが**代替する円錐より 161mm 短い**
# （85.5mm vs 246.8mm）ので、太いぶんと短いぶんが相殺する。容積 1 個からは出せない。
#
# Stage E はここに「ソプラノの -31 だけが本物のマウスピース由来の残差」と書いた。
# **それも違った。** ソプラノの実物（ヤナギサワ、刻印 4）を measure すると全長は
# 71.4mm で、テンプレートの 87.52mm（テナー実測 × リード規格長比 0.8141）より
# 16.1mm 短かった。**その 0.8141 は 63.5/78.0 で、分子の 63.5 自体が違っていた**
# （Stage G の実測でソプラノのリードは 59.1〜62.0）。正しい 59.1 で引き直しても
# 0.7577 で実比 0.6642 には届かないので、「全長はリード規格長から決まる」という
# 立て方そのものが成立しない。そして本質はもっと手前にあった:
#
# **`cork_depth` はマウスピースの寸法ではない。** 気温・リード・合わせる音程で
# 演奏者が抜き差しするチューニングそのものである。それを固定した状態のセントを
# 記録すると、寸法の誤差とチューニングの自由度が混ざる。-31 セントの正体は
# 「全長 71.4mm の胴に 17.91mm という当て推量の挿し込みを固定していた」ことだった。
#
# なので Stage F からは**合う挿し込み量**を記録する（`IN_TUNE_INSERTION_MM`）。
# セントは「テンプレートの `cork_depth` での値」として残すが、判定には使わない。
TIER1_RESIDUAL_CENTS = {"soprano": -0.1, "alto": 0.0, "tenor": 0.3}

# 目標低音が鳴る挿し込み量 [mm]（`openwind_bridge.tuning_position`、TMM 固定）。
# 3 サイズとも実用域の内側に入る。浅い側はフェルール＋コルクが噛む下限、深い側は
# **押し込み限界の実測**（`insertion_limit_mm` = 27.1 / 36.4 / 36.0mm、2026-08-13）。
# 実用域は soprano 5.7〜27.1 / alto 3.0〜36.4 / tenor 3.0〜36.0 で、そこでの
# チューニング幅は soprano −27.5〜+4.6 / alto −10.5〜+10.3 / tenor −7.5〜+4.7 セント。
#
# アルトの 19.2 → 13.6 は形状が動いたぶん（Wood Stone PHROX の実測で全長が
# 98.54 → 91.7mm）。胴が短くなれば空洞が減るので、同じ音に合わせるには
# **浅く**挿すことになる。
# アルトの 13.6 → 17.4 → **14.4** は 2026-09-05 に 2 段階で動いた。
# (1) PHROX の窓の実測（window_length 35.02 → 38.67 / bore_length 49.05 → 48.30 を
#     組で入れた）。`cork_depth` は**その形で第1共鳴が合う位置**なので引き直す
#     ——導出値であって寸法ではない。引き直しを忘れると速い線形推定が厳密解を
#     1.15mm 外し、`test_fast_tuning_estimate_tracks_the_bracketed_solve` が落ちる。
# (2) その 17.4 は**`cavity_floor_y` の特異点で床が 3.5 倍深く出ていた形**での値
#     だった（`test_window_length_does_not_touch_the_tip`）。特異点を直したら
#     空洞が実物の深さへ戻り、合う位置も 14.4 へ戻った。
#     **形が変われば零点も動く、を 1 セッションで 2 回踏んだ。**
IN_TUNE_INSERTION_MM = {"soprano": 23.5, "alto": 14.4, "tenor": 20.9}

# **その挿し込み量での**実効容積 / 欠損円錐（soprano +25 / alto +21 / tenor +26%）。
# 0 ではないのがこの模型の要点で、マウスピースは代替する円錐より短いぶん太くて
# 釣り合う。挿し込み量と容積比という独立な 2 つの指標が同じことを言っている。
#
# **この「揃い」はアルトの実測で壊れた**（2026-09-05）: soprano +25.5 /
# alto **+20.4** / tenor +23.4%。**+21〜26% で揃うという観察は、アルトが未実測
# だったから成立していた。**
#
# 同じ日にいったん alto +13.3 と記録したが、あれは `cavity_floor_y` の特異点で
# 床が 3.5 倍深く出ていたぶんを含んでいた。特異点を直すと +20.4 に戻り、散らばりは
# 12.2 ポイント → 5.1 ポイントになる。**壊れたという結論は変わらない**（alto だけ
# 21% を割る）が、**壊れ方の大きさは実測ではなくバグが決めていた**。
# 帯は 0.15〜0.30 に戻す ―― 3 サイズとも入るので、そのほうが検知が細かい。
IN_TUNE_VOLUME_RATIO = (0.15, 0.30)


def _tier1(tid: str) -> dict:
    from saxsketch.acoustics import openwind_bridge as ob
    from saxsketch.acoustics import volume as ac_volume
    p = _template_params("mouthpiece", tid)
    si = _size_info(tid)
    return ac_volume.tier1_report(profiles.cavity_volume_cc(p), si,
                                  ob.tuning_position(p, si))


def test_tier1_matches_recorded_residual():
    """Tier1 の記録値どおりであること。良好かどうかではなく、変化の検知が目的。"""
    for tid in SIZES:
        rep = _tier1(tid)
        assert rep["in_tune_mm"] == pytest.approx(
            IN_TUNE_INSERTION_MM[tid], abs=0.5), (tid, rep)
        assert rep["deviation_cents"] == pytest.approx(
            TIER1_RESIDUAL_CENTS[tid], abs=2.0), (tid, rep)
    # 3 サイズとも実用域の内側。容積の一行規則だった頃はどれも到達不能で、
    # Stage E では soprano だけ flat だった。
    assert [_tier1(t)["status"] for t in SIZES] == ["ok", "ok", "ok"]


def test_in_tune_insertion_is_inside_the_usable_range():
    """合う挿し込み量が実用域に入り、そこで容積比が 3 サイズとも同じ帯に入ること。

    判定の主指標がセントから挿し込み量へ移ったことの不変条件。深い側の上限は
    ボアでもコルク帯でもなく、**押し込み限界の実測**（`insertion_limit_mm`）。
    ここは `test_in_tune_is_inside_the_measured_stop` で外部照合として別に張る。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    from saxsketch.acoustics import volume as ac_volume
    lo_r, hi_r = IN_TUNE_VOLUME_RATIO
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        si = _size_info(tid)
        t = ob.tuning_position(p, si)
        lo, hi = t["range_mm"]
        assert lo < t["in_tune_mm"] < hi, (tid, t)
        assert t["reachable"], (tid, t)
        # 感度は 3 サイズとも「押し込むと高くなる」。符号が反転したらモデルが壊れている。
        assert t["cents_per_mm"] > 0.1, (tid, t)
        target = ac_volume.missing_cone(si)["cc"]
        eff = profiles.cavity_volume_cc({**p, "cork_depth": t["in_tune_mm"]})["effective_cc"]
        assert lo_r < (eff - target) / target < hi_r, (tid, eff, target)


def test_usable_range_counts_the_ferrule_that_has_no_cork():
    """実用域の両端が**コルクの在る区間**から決まること。

    ネックの先端はコルクの無い真鍮のフェルール（補強リング）で、ソプラノの
    実測は 2.7mm（Yanagisawa S-902、2026-08-13）。ここを勘定に入れないと
    両端が同じだけずれる:

    - 浅い側: 「3mm 挿してある」が実際にはコルクが 0.3mm しか噛んでいない状態を
      域の内側と数えてしまう。
    - 深い側: コルクの奥端は端面から 2.7 + 31.0 = 33.7mm で、31.0 ではない。

    以前の推定値 26.0（neck テンプレートの `tenon_length` を写しただけ）は
    7.7mm 短かった。**浅い側はいまもここが決めている。**（深い側は実測の
    押し込み限界に置き換わった —— 下の `test_in_tune_is_inside_the_measured_stop`）
    """
    from saxsketch.acoustics import openwind_bridge as ob
    p = _template_params("mouthpiece", "soprano")
    si = _size_info("soprano")
    ferrule = si["neck_ferrule_length_mm"]
    lo, _ = ob.usable_insertion_range(p, si)
    assert lo == pytest.approx(ferrule + ob._CORK_MIN_MM)

    # 未実測のサイズは 0 として扱う。無い値を推定で埋めると、入っている数字が
    # どこから来たのか分からなくなる（`_ferrule_mm`）。
    for tid in ("alto", "tenor"):
        si2 = _size_info(tid)
        assert "neck_ferrule_length_mm" not in si2, tid
        lo2, _ = ob.usable_insertion_range(_template_params("mouthpiece", tid), si2)
        assert lo2 == pytest.approx(ob._CORK_MIN_MM), tid


def test_in_tune_is_inside_the_measured_stop():
    """合う挿し込み量が**実測の押し込み限界**の内側に入ること。

    `in_tune_mm` は共鳴管と目標低音だけから解いていて、押し込み限界は一切
    入っていない。独立に決めた 2 つが矛盾しないので、これは循環ではなく
    **モデル唯一の外部照合**になる（典型値との一致では検証できない ——
    気温・リード・リガチャー・アンブシュアはモデルに入っていない）。

    実測（2026-08-13、ネック端面からシャンク端面まで）:
      soprano 27.1（S-902 ＋ ヤナギサワ 4番）
      alto    36.4（YAS-875 ＋ Wood Stone PHROX）
      tenor   36.0（SA80 II ＋ Jody Jazz Giant 6*）

    **推定は 3 サイズとも外れていて、しかも向きが揃っていない**（推定は
    33.7 / 30.0 / 32.0）。値ではなく**内包**を張るので、校正が動いても意味を保つ。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        si = _size_info(tid)
        stop = si["insertion_limit_mm"]
        lo, hi = ob.usable_insertion_range(p, si)
        assert hi == pytest.approx(stop), tid          # 実測が深い側を決めている
        z = ob.tuning_position(p, si, exact=True)["in_tune_mm"]
        assert lo < z < stop, (tid, z, lo, stop)


def test_soprano_stops_short_of_both_the_cork_and_the_bore():
    """ソプラノの止まりが、コルク帯でもボアでも説明できないこと。

    コルクは端面から 2.7 + 31.0 = 33.7mm まで在り、ボアは 38.3mm 深いのに、
    実物は **27.1mm** で止まる。つまり効いているのは第 3 の何か（S-902 は
    ネックと管体が一体なので、コルクの載る部分のテーパで先に噛んでいると見られる）。

    ここが崩れる＝どちらかの推定が実測を追い越したときは、`usable_insertion_range`
    の「実測を優先する」という立て方ごと見直す必要がある。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    p = _template_params("mouthpiece", "soprano")
    si = _size_info("soprano")
    stop = si["insertion_limit_mm"]
    assert stop < si["neck_ferrule_length_mm"] + si["neck_cork_length_mm"]
    assert stop < p["bore_length"] - ob._CORK_BORE_MARGIN_MM


def test_measured_stop_brings_tip_opening_back_into_the_verdict():
    """実測の止まりの下では `tip_opening` が再び判定を動かすこと。

    Stage I 前半は推定の上界 33.7mm で見て「ティップ開きはもう判定を動かさない」と
    結論した。実測の 27.1mm で掃引し直すと**逆戻りする** —— 2.65 で余裕 0.03mm、
    2.93 以上では合う挿し込み位置が止まりの外へ出る。既定の 1.95 は余裕 3.6mm で
    問題ない。**上界で判定して安心することの危うさ**がそのまま出た例なので、
    「広げても平気」に戻ったらここで落とす。

    値ではなく**向きと到達**を張る: 広げるほど深く挿すことになり、可動域の上端では
    届かなくなり、そのとき黙って ok を返さない。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    from saxsketch.acoustics import volume as ac_volume
    comp = get_registry().get("saxophone").make_component("mouthpiece", "soprano")
    si = comp.size_info
    spec = {s.key: s for s in comp.param_specs()}
    p = {k: s.default for k, s in spec.items()}
    tip = spec["tip_opening"]

    zs = [ob.tuning_position(dict(p, tip_opening=v), si, exact=True)["in_tune_mm"]
          for v in (tip.min, p["tip_opening"], tip.max)]
    assert zs[0] < zs[1] < zs[2], zs          # 広げるほど深く挿す

    stop = si["insertion_limit_mm"]
    assert zs[1] < stop, zs                    # 既定は届く
    assert zs[2] > stop, (zs, stop)            # 可動域の上端は届かない
    # 届かないときに黙って ok を返さないこと。
    wide = dict(p, tip_opening=tip.max)
    t = ob.tuning_position(wide, si, exact=True)
    rep = ac_volume.tier1_report(profiles.cavity_volume_cc(wide), si, t)
    assert not t["reachable"], t
    assert rep["status"] == "unreachable", rep


def test_bore_length_is_the_same_fraction_of_overall_length():
    """ボア長が全長の一定割合であること（実測 2 本が根拠）。

    アルトのマウスピースは**ボア長を測れなかった**（円筒ボアの明確な終端が
    見えない）。代わりに全長から導出しているが、その根拠は独立に実測した
    2 本で割合が一致すること —— soprano 38.3/71.4 = 0.5364、
    tenor 57.5/107.5 = 0.5349 で **0.3% 差**。

    アルトの値はこの割合で作ってあるので、ここが落ちるときは
    「全長だけ直してボア長を置き忘れた」か「実測 2 本の一致が崩れた」。
    """
    fracs = {tid: (_template_params("mouthpiece", tid)["bore_length"]
                   / _template_params("mouthpiece", tid)["overall_length"])
             for tid in SIZES}
    # 独立に実測した 2 本が一致することがそもそもの根拠。
    assert fracs["soprano"] == pytest.approx(fracs["tenor"], rel=0.01), fracs
    for tid in ("soprano", "tenor"):
        assert 0.53 < fracs[tid] < 0.54, (tid, fracs[tid])
    # **アルトはもうこの規則から来ていない。** PHROX のティップ端→窓の後縁の実測
    # 39.4mm が、窓の後端とボアの始まりのあいだに要る 4.0mm と両立しなくなり、
    # bore_length を 49.05（＝この割合）から 48.30 へ下げた（2026-09-05、
    # docs/print-inspection.md §11.4）。**上限であって実測ではない**ので、
    # ここは「割合の外に出たこと」だけを固定する —— 割合へ戻ったなら、それは
    # 実測のほうを落としたということ。
    assert fracs["alto"] == pytest.approx(48.3 / 91.7, abs=0.001), fracs
    assert fracs["alto"] < 0.53, fracs


def test_tight_verdict_does_not_claim_precision_it_lacks():
    """深い側がきつい時の助言が、持っていない分解能で合否を言わないこと。

    深い側の上限は実測になったが、その実測は「これ以上押し込んだらまずい」と
    いう**演奏者の判断**であり、しかもネック単独でもマウスピース単独でもなく
    **組**の性質（コルクを巻き直しても銘柄を替えても動く）。「余裕は n mm」と
    数字で詰めてよい量ではない。言うべきは実物で確かめること。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    from saxsketch.acoustics import volume as ac_volume
    p = _template_params("mouthpiece", "soprano")
    si = _size_info("soprano")
    # 合う挿し込み量の 1mm 奥で切る＝ 届いてはいるが余裕が 2mm を切る状態。
    # 定数で書かずに解から作るので、校正が動いてもこのテストは意味を保つ。
    z = ob.tuning_position(p, si, exact=True)["in_tune_mm"]
    cap = z - si["neck_ferrule_length_mm"] + 1.0
    t = ob.tuning_position(p, si, cork_max_mm=cap, exact=True)
    rep = ac_volume.tier1_report(profiles.cavity_volume_cc(p), si, t)
    assert rep["status"] == "tight", rep
    assert "止まるまで押し込んで" in rep["advice"], rep["advice"]
    assert "組" in rep["advice"], rep["advice"]
    # 実際に効いている上限を指すこと（descriptor の実測値をそのまま印字すると、
    # 掃引や設計途中で別の上限が効いている場面で嘘になる）。
    assert f"{t['range_mm'][1]:.1f}mm" in rep["advice"], rep["advice"]


def test_in_tune_insertion_is_a_reference_not_a_prediction():
    """合う挿し込み量が「どの条件での値か」を必ず添えて出すこと。

    ユーザーの指摘: 実演奏の挿し込み量に**典型値は存在しない**。マウスピース・
    リード・リガチャー・気温・アンブシュアすべてに影響される。モデルが持って
    いるのはこのうち気温（`TEMPERATURE_C`）と合わせる音程（`low_note_sounding_hz`）
    の 2 つだけで、残り 3 つは入っていない。

    条件を書かずに mm だけ出すと「あなたはここに挿すことになる」という主張に
    読める。それは主張できないので、条件を消したらここで落ちる。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    for tid in SIZES:
        si = _size_info(tid)
        note = _tier1(tid)["note"]
        assert f"{ob.TEMPERATURE_C:.0f}°C" in note, (tid, note)
        assert si["low_note_label"] in note, (tid, note)
        assert "予測ではない" in note, (tid, note)
        # モデルに入っていない 3 つを名指しすること（入っている 2 つと区別が付く）
        for absent in ("リード", "リガチャー", "アンブシュア"):
            assert absent in note, (tid, absent)


def test_fast_tuning_estimate_tracks_the_bracketed_solve():
    """速い線形推定が厳密解と 0.2mm 以内で一致すること。

    `simulate` の予算は 50ms（`cad/perf/bench_ui_latency.BUDGET`）で、`simulate`
    自体が既に 20〜31ms 使っている。零点を包んで詰める厳密解は共鳴を 10 回前後
    解き、テナーで 335ms かかって入らない。代わりに現在位置とその 1mm 奥から
    局所の傾きを取って線形に推している。テンプレートの `cork_depth` は零点の
    0.1〜1.1mm 手前にあるので常用状態では効く、というのがこのテストの主張。

    **実用域の両端を結ぶ線形近似では代用できない。** そちらは零点を
    テナーで 2.68mm 外す（帯域内の非線形が 1.20 セントある）。効くのは
    「解の近くで測った局所の傾き」であって「線形だから」ではない。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        si = _size_info(tid)
        fast = ob.tuning_position(p, si)
        exact = ob.tuning_position(p, si, exact=True)
        assert fast["method"] == "linear" and exact["method"] == "solved", tid
        assert fast["in_tune_mm"] == pytest.approx(
            exact["in_tune_mm"], abs=0.2), (tid, fast, exact)
        # 厳密解のときだけ実用域の両端のセントが付く（速い経路は 2 回しか解かない）
        assert fast["cents_at_range"] is None, tid
        assert exact["cents_at_range"][0] < 0.0 < exact["cents_at_range"][1], tid


def test_fast_tuning_never_cries_unreachable_on_its_own():
    """速い推定が「実用域の外」と言いかけたら、必ず解き直してから答えること。

    「この形状はチューニングでは合わせられない」は形状側を直せという強い主張で、
    線形推定の粗さで言ってはいけない。実測で誤警報が出た組合せを固定してある:
    テナーのボアを 38mm（既定 57.5）にして `cork_depth` を上限 32mm へ持っていくと、
    推定は 1.25mm（実用域 3〜35 の外）だが厳密解は 9.72mm で**域内**。
    **8.47mm ぶんの誤警報**を厳密解が救っている。

    以前ここはボア 46mm（推定 1.61 → 厳密 5.05）を使っていた。`cavity_floor_y` の
    特異点を直して床が実物の深さへ戻ったら、46mm では推定が域内（22.08）に収まって
    ガードを踏まなくなった。**ガードが消えたのではなく、この設定が当たらなくなった
    だけ** —— 38mm 以下では今も踏む（掃引で確認）。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    p = dict(_template_params("mouthpiece", "tenor"), bore_length=38.0, cork_depth=32.0)
    si = _size_info("tenor")
    t = ob.tuning_position(p, si)
    assert t["method"] == "solved", t          # 域外に出かけたので解き直している
    assert t["reachable"], t
    assert t["in_tune_mm"] == pytest.approx(9.72, abs=0.5), t
    # 本当に域外の形状は域外のまま返す（解き直しても救われない）。
    # 全長を下限 80.5mm まで詰めると零点が −6.15mm ＝ 実用域を**下に**外れる。
    # 両端のセントが同符号で挟めないので `method` は "linear" のまま
    # （そこは `tuning_position` の設計どおり ―― 伝えたいのは reachable=False）。
    far = dict(p, overall_length=80.5)
    tf = ob.tuning_position(far, si)
    assert not tf["reachable"], tf


def test_tier1_advice_admits_saturation():
    """届かないのに「チェンバーを広げろ」とだけ言わないこと。

    肉厚制限で頭打ちならスライダを上げても目標に届かない。効かない操作を勧めるのは
    ユーザーの時間を捨てさせる。

    判定条件を差し替えてある。以前は「チェンバー断面が**全部**外殻に接しているか」
    (`chamber_saturated`) だったが、実測から起こした形状では窓寄りの断面が先に当たる
    ことが無く、スライダ可動域の全域（比 3.0 × 最小肉厚 4.0）で永久に False
    ＝ この助言は到達不能コードだった。見るべきは幾何の接触ではなく
    **上限まで上げて目標に届くか**（`chamber_headroom_cc`）。
    """
    from saxsketch.acoustics import volume as ac_volume
    comp = get_registry().get("saxophone").make_component("mouthpiece", "tenor")
    cr_max = next(s.max for s in comp.param_specs() if s.key == "chamber_ratio")
    p = _template_params("mouthpiece", "tenor")

    # (a) 幾何の事実: 上限まで上げても実効容積は 1cc も増えない（外殻の肉厚が効く）
    head = profiles.chamber_headroom_cc(p, cr_max)
    assert 0.0 < head < 1.0, head

    # (b) 助言のロジック: 足りないときだけ「届かない」と言う。テンプレートの数字に
    #     依存しないよう、目標に足りない容積と「実用域の外」のチューニング結果を
    #     その場で作って渡す。この助言が出るのは形状側を直すしかない状態のときだけで、
    #     チューニングで埋まるなら容積を増やせと言う理由が無い。
    si = _size_info("tenor")
    target = ac_volume.missing_cone(si)["cc"]
    short = {"total_cc": target, "effective_cc": 0.7 * target}
    far = {"in_tune_mm": 45.0, "method": "linear", "range_mm": [3.0, 32.0],
           "cents_at_range": None, "cents_per_mm": 0.3, "current_mm": 22.0,
           "cents_at_current": 40.0, "reachable": False, "headroom_mm": [42.0, -13.0]}
    rep = ac_volume.tier1_report(short, si, far, headroom_cc=head)
    assert rep["status"] == "unreachable"
    assert "届かない" in rep["advice"]
    assert "届かない" not in ac_volume.tier1_report(
        short, si, far, headroom_cc=99.0)["advice"]
    assert "届かない" not in ac_volume.tier1_report(short, si, far)["advice"]


# ------------------------------------------------------- 外殻への封じ込め（Phase 3.6）

def _breaches(p: dict) -> list[str]:
    """外殻を突き抜けているステーションを列挙する。"""
    bad = []
    for s in profiles.cavity_stations(p):
        lim = profiles.shell_limit(p, s["z"])
        top, bot = s["yc"] + s["h"] / 2.0, s["yc"] - s["h"] / 2.0
        if s["w"] / 2.0 > lim["half_width"] + 1e-6:
            bad.append(f"{s['role']}@{s['z']:.1f} 幅 {s['w']/2:.2f}>{lim['half_width']:.2f}")
        if top > lim["top"] + 1e-6:
            bad.append(f"{s['role']}@{s['z']:.1f} 天井 {top:.2f}>{lim['top']:.2f}")
        # 窓の下端だけは自由（テーブルカット面より下へ抜けて開口になる）
        if s["role"] != "window" and bot < lim["bot"] - 1e-6:
            bad.append(f"{s['role']}@{s['z']:.1f} 床 {bot:.2f}<{lim['bot']:.2f}")
    return bad


def test_cavity_inside_shell():
    """空洞がどのパラメータ組合せでも本体を貫通しないこと。

    Phase 3.5 で外形だけ実物寸法へ縮めた結果、チェンバーが本体の左右と上を突き抜け、
    しかも体積積分が外へ出た分まで数えて Tier1 が「合格」した。マウスピースとして
    成立しないモデルが既定値で出ていた。このテスト1本がその再発を構造的に防ぐ。
    """
    keys = ("chamber_ratio", "throat_ratio", "baffle_height", "window_length",
            "beak_height", "min_wall", "body_dia", "bore_length")
    for tid in SIZES:
        comp = get_registry().get("saxophone").make_component("mouthpiece", tid)
        specs = {s.key: s for s in comp.param_specs()}
        base = _template_params("mouthpiece", tid)
        assert _breaches(base) == [], (tid, "既定値", _breaches(base))
        for k in keys:
            spec = specs[k]
            for v in (spec.min, spec.default, spec.max):
                p = dict(base, **{k: v})
                assert _breaches(p) == [], (tid, k, v, _breaches(p))


def test_every_slider_end_still_builds_stations():
    """どのスライダーを片端まで振ってもステーション生成が落ちないこと。

    `_station_zs` は最後に `keep = [out[0]]` を書く。刻む区間が空だと
    `IndexError: list index out of range` になり、理由がどこにも出ない。
    上の `test_cavity_inside_shell` は 8 個のキーだけを見ているので、
    ここは **`param_specs()` にある全部の数値パラメータ × min/max** を舐める。
    """
    for tid in SIZES:
        comp = get_registry().get("saxophone").make_component("mouthpiece", tid)
        base = _template_params("mouthpiece", tid)
        for spec in comp.param_specs():
            if spec.min is None or spec.max is None:
                continue
            for end, v in (("min", spec.min), ("max", spec.max)):
                p = dict(base, **{spec.key: v})
                assert profiles.cavity_layout_error(p) is None, (tid, spec.key, end)
                assert profiles.cavity_stations(p), (tid, spec.key, end)


def test_impossible_layout_says_why_instead_of_crashing():
    """成立しないパラメータの**組**を、理由付きで弾くこと。

    `ParamSpec` はパラメータを 1 本ずつしか見ないので、各自のレンジ内なのに
    組み合わせると潰れる値の組が作れる。`overall_length` を下限 60.0、
    `bore_length` を上限 60.0 にすると `bore_start_z = 0` で窓が残らず、
    以前はここが `IndexError: list index out of range` だった。**UI の
    2 本のスライダから到達できる**ので、理由の無い例外にしてはいけない。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = _template_params("mouthpiece", tid)
        # ボアが全長をほぼ食い切る＝窓の残らない組。`ParamSpec.validate` は
        # 範囲外を黙ってクランプするだけなので、幾何の側で弾けないといけない。
        bad = dict(base, bore_length=base["overall_length"] - 1.0)
        why = profiles.cavity_layout_error(bad)
        assert why and "窓" in why and "ボア長" in why, (tid, why)
        # 部品からも同じ理由が取れる（サーバはこれを見て値を保存せずに弾く）
        assert comp.params_error(bad) == why, tid
        with pytest.raises(ValueError, match="成立しません"):
            profiles.cavity_stations(bad)
        # 既定は当然成立する。成立するのに弾いていたら誤検出。
        assert comp.params_error(base) is None, tid


def test_slider_ranges_alone_cannot_close_the_hole():
    """レンジを実測基準にしても、2 本の組合せまでは塞がらないこと。

    `overall_length` / `bore_length` のレンジをテンプレート比（±25% / −50〜+25%）に
    したことで**単独のスライダーでは潰せなくなった**（以前はテナーの全長を下限
    60.0 にするだけで潰れた）。それでもソプラノは下限の全長 × 上限のボア長で
    まだ届く —— レンジは 1 本ずつしか効かないので、**組の検査は別に要る**。
    このテストが落ちるようになったら `cavity_layout_error` の呼び出しを外して
    よいか判断できる。
    """
    comp = get_registry().get("saxophone").make_component("mouthpiece", "soprano")
    specs = {s.key: s for s in comp.param_specs()}
    bad = dict(_template_params("mouthpiece", "soprano"),
               overall_length=specs["overall_length"].min,
               bore_length=specs["bore_length"].max)
    assert profiles.cavity_layout_error(bad) is not None


def test_window_length_says_when_it_stops_doing_anything():
    """`window_length` が効かなくなったら黙らずに言うこと。

    `window_end_z` は `min(前縁 + window_length, zb − 4.0)` で、後者が効くと
    **スライダを上げても形が一切変わらない**。`cavity_layout_error` は窓が
    `_MIN_WINDOW_SPAN_MM` を割るまで黙っているので、その手前に「落ちないし
    壊れてもいないが、操作が届いていない」帯がある。しかも**可動域から到達できる**:
    測ると soprano は 24〜44mm のうち 28.6mm 以上が丸ごと死んでいた（可動域の 77%）。

    `ParamSpec.validate` の黙ったクランプ（Stage F、`test_template_values_survive_
    the_schema_unclamped`）と同じ種類だが、こちらは**導出側で起きるのでレンジを
    見ても分からない**。だから量として公開し、警告に出す。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = _template_params("mouthpiece", tid)
        # 既定は届いている。ここが落ちたらテンプレートの側の問題。
        assert profiles.window_length_shortfall(base) == pytest.approx(0.0), tid
        assert profiles.window_length_effective(base) == pytest.approx(
            base["window_length"], abs=1e-6), tid
        assert not any("ウィンドウ長" in w for w in profiles.cavity_warnings(base)), tid

        # スライダ上限まで上げる。届かないなら理由を言う（黙って頭打ちにしない）。
        wl_max = next(s.max for s in comp.param_specs() if s.key == "window_length")
        wide = dict(base, window_length=wl_max)
        short = profiles.window_length_shortfall(wide)
        if short > 0.05:
            assert profiles.window_length_effective(wide) < wl_max, tid
            why = [w for w in profiles.cavity_warnings(wide) if "ウィンドウ長" in w]
            assert why and "ボアの始まり" in why[0], (tid, why)
        # 形が成立している側のままであること（クランプは壊れ方ではない）
        assert profiles.cavity_layout_error(wide) is None, tid


#: 既定テンプレートでの `window_length` の凍る点 [mm]
#: （= `bore_start_z − chamber_to_bore_mm − window_front_z`）。
#: **本文に焼くのをやめてここへ移した数字。** 3 つの項がどれもテンプレート
#: ぶら下がりなので、テンプレートを直すたびに散らばった散文だけが古くなる ——
#: `window_length_effective` の docstring は 2 世代連続で腐った。ここが落ちたら
#: 値を書き換えるだけでなく、下の `_WINDOW_FREEZE_DOCS` の 3 か所も直すこと。
_WINDOW_FREEZE_MM = {"soprano": 28.54, "alto": 38.67, "tenor": 45.15}

#: 上の数字を散文で持っている場所。テストは中身までは見ない（読む人への地図）。
_WINDOW_FREEZE_DOCS = (
    "saxsketch/instruments/saxophone/components/mouthpiece.py（window_length のコメント）",
    "cad/windycity/README.md（寸法図示で食い違った量の表）",
    "docs/param-limits.md（Phase 4-E の帯と壁の表）",
)


def test_the_window_freeze_point_is_where_the_docs_say_it_is():
    """**ウィンドウ長が効かなくなる点を数字で釘打つ。**

    「窓の後端はボアに阻まれる」という規則そのものは
    `test_window_length_says_when_it_stops_doing_anything` が見ている。ここが
    見るのは**どこで阻まれるか** —— 散文が持っていて腐った数字のほう。

    腐り方はいつも同じで、`bore_length` なりテンプレートなりが実測で動き、
    形とテストは追随するのに**散文だけ置き去りになる**。実際この数字は
    4-C.5 で 1 度直され（41.1 → 37.92）、9/05 の `bore_length` 実測でまた
    動いた（→ 38.67）のに、docstring も README も 4-C.5 のままだった。
    テンプレートが動いたらこのテストが落ちて新しい値を教える。

    **アルトが既定でちょうど凍る点に載っているのは事故ではない。**
    `bore_length` を PHROX 実測が許す上限 48.30 に置いた帰結で、
    `docs/print-inspection.md` に「承知のうえで踏んだ」と記録がある。
    だから既定は「届いている」（不足 0）と「1 目盛り上げたら効かない」を
    同時に満たす —— 両方ここで固定する。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        p = _template_params("mouthpiece", tid)
        freeze = (profiles.bore_start_z(p) - p["chamber_to_bore_mm"]
                  - profiles.window_front_z(p))
        assert freeze == pytest.approx(_WINDOW_FREEZE_MM[tid], abs=0.01), (
            tid, freeze, "散文の数字も直すこと:", _WINDOW_FREEZE_DOCS)
        # 凍る点は「指定した窓長が実効値と一致する上限」でもある。
        assert profiles.window_length_effective(
            dict(p, window_length=freeze + 5.0)) == pytest.approx(freeze, abs=1e-6), tid

        spec = next(s for s in comp.param_specs() if s.key == "window_length")
        live = min(freeze, spec.max) - spec.min
        assert live > 0.0, (tid, "帯が丸ごと死んでいる")

    # アルトだけ、既定がちょうど天井に載っている（意図的）。
    alto = _template_params("mouthpiece", "alto")
    assert profiles.window_length_shortfall(alto) == pytest.approx(0.0), "既定は届く"
    up = dict(alto, window_length=alto["window_length"] + 0.5)
    assert profiles.window_length_effective(up) == pytest.approx(
        alto["window_length"], abs=1e-6), "1 目盛り上げても 1 ビットも動かない"

    # **ステーションの等値比較はしない。** `window_end_z` は
    # `min(前縁 + 窓長, zb − gap)` で、既定はちょうど両辺が並ぶ点なので
    # どちらの式で計算したかによって答えが 1 ULP ずれ、`s_we = z_we/zb` を
    # 通った `_section_exponents` の指数に nx 6.0 対 6.000000000000001 として
    # 出る。**形の違いではなく、同じ数の別の計算経路**（OCCT の三角形分割は
    # 一致する）。だから許容付きで見る。
    def _same(a, b, tol=1e-9):
        return len(a) == len(b) and all(
            set(x) == set(y) and all(
                (x[k] == y[k]) if isinstance(x[k], str) else abs(x[k] - y[k]) <= tol
                for k in x)
            for x, y in zip(a, b))

    assert _same(profiles.cavity_stations(up), profiles.cavity_stations(alto))
    # 下げるほうは生きている（凍っているのは上だけ、と言い切れること）
    down = dict(alto, window_length=alto["window_length"] - 0.5)
    assert not _same(profiles.cavity_stations(down), profiles.cavity_stations(alto))

    # そして「見た目のモデル」そのもので 1 度だけ確かめる —— 利用者が見るのは
    # ステーションではなくソリッド。帯の上端まで上げても体積が動かないこと。
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    v_default = comp.build(alto).volume
    v_top = comp.build(dict(alto, window_length=44.0)).volume
    assert v_top == pytest.approx(v_default, abs=1e-6), "既定から上は形が動かない"


def test_the_window_warning_names_the_gap_that_is_actually_stopping_it():
    """**警告は「いま止めている量」を言うこと。直値を書かない。**

    以前ここは「ボアの始まり 43.4 − 4.0mm」と書いていた。その 4.0 は
    Phase 4-A で `chamber_to_bore_mm` になっているので、利用者がそれを 0.5 に
    縮めて窓が実際に伸びても、**文面だけ 4.0 と言い続ける**。しかも直し方に
    本命のつまみが挙がっておらず（全長 / ボア長しか出てこない）、
    `window_length` の説明文だけが「これを縮める」と言っていた ——
    **説明文と、実際に読まれる警告が食い違っていた。**

    代理変数が 1 か所直しても終わらない型（`min`/`max` がスキーマの外で
    4 か所消費されていたのと同じ）。ここは文面に数字を持たせず `p` から読む。
    """
    p = _template_params("mouthpiece", "alto")
    wide = dict(p, window_length=44.0)

    def why(q):
        return [w for w in profiles.cavity_warnings(q) if "ウィンドウ長" in w]

    for gap, eff in ((4.0, 38.67), (2.0, 40.67), (0.5, 42.17)):
        q = dict(wide, chamber_to_bore_mm=gap)
        assert profiles.window_length_effective(q) == pytest.approx(eff, abs=0.01)
        msg = why(q)
        assert len(msg) == 1, (gap, msg)
        assert f"{gap:.1f}mm" in msg[0], (gap, msg[0])
        # 効いていない量を名指ししない。4.0 のときだけは値が一致するので除く。
        if gap != 4.0:
            assert "− 4.0mm" not in msg[0], (gap, msg[0])
        # 直し方に本命が入っている。
        assert "「チェンバー→ボアの遷移」を縮める" in msg[0], (gap, msg[0])

    # 実効値も文面の中で更新されること（実際の頭打ちを書く）。
    assert "42.2mm" in why(dict(wide, chamber_to_bore_mm=0.5))[0]

    # **同じ直値が `cavity_layout_error` にもあった。** こちらは注意ではなく
    # エラーで、窓が `_MIN_WINDOW_SPAN_MM` を割ったときに出る文。1 か所直して
    # 終わりにしないこと（代理変数の型）。
    # 遷移を縮めれば直る側に居ると当然エラーが消えるので、どちらの gap でも
    # 割るところまでボアを伸ばす（88.0 は gap 0.5 なら成立してしまう）。
    for gap in (4.0, 0.5):
        broke = dict(p, bore_length=90.0, chamber_to_bore_mm=gap)
        err = profiles.cavity_layout_error(broke)
        assert err is not None and "チェンバー→ボアの遷移" in err, (gap, err)
        assert f"チェンバー→ボアの遷移 {gap:.1f}" in err, (gap, err)


def test_window_length_does_not_touch_the_tip():
    """**ウィンドウ長は先端の形に効いてはいけない。**

    窓を伸ばすことは「床が上がってくる位置が後ろへ動く」ことであって、
    「空洞全体が深くなる」ことではない。この 1 行を守っていなかったのが
    `cavity_floor_y` の旧実装で、実測テーブル `_CAVITY_D` を**振幅方向の
    アフィン** `a·(D(σ) − t0)`（`a = target/(D(1) − D(s_we))`）で端条件へ
    合わせていた。`_CAVITY_D` は σ=`_CAVITY_D_ZERO` で 0 を横切るので、
    s_we がそこに載っている間だけ a≈1 になる —— そして 3 サイズともたまたま
    載っていた（soprano 0.8408 / tenor 0.8380 / 旧 alto 0.8382）。

    **「揃い」に幾何コードが荷重を掛けていた。** アルトの窓を実測へ直した
    （35.02 → 38.67）とたんに s_we が 0.9078 へ動き、分母が −0.367 → −0.098 に
    縮んで a=3.48。床が丸ごと 3.5 倍深くなり、先端の落とし込み D(0)=0.100 が
    2.73mm に化けて**ティップレールのくさびが消えた**（空洞高さ 0.60 → 4.44mm）。
    利用者が 3D ビューで見つけた —— テストも掃引も素通りしていた。

    いまは σ を写像して合わせるので、σ=0 は必ず 0 へ写り先端は動かない。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = _template_params("mouthpiece", tid)
        spec = next(s for s in comp.param_specs() if s.key == "window_length")
        tips = []
        wl = spec.min
        while wl <= spec.max + 1e-9:
            p = dict(base, window_length=wl)
            assert profiles.cavity_layout_error(p) is None, (tid, wl)
            tips.append(profiles.cavity_stations(p)[0]["h"])
            wl += 2.0
        # 先端の空洞高さは可動域全域で動かない（実測 D(0) がそのまま出る）。
        assert max(tips) - min(tips) < 0.02, (tid, min(tips), max(tips))
        # 旧実装はここで 4.44mm まで開いた。1.0mm は「くさびが立っている」の側。
        assert max(tips) < 1.0, (tid, max(tips))


def test_cavity_floor_meets_both_end_conditions():
    """床は窓の終端で D=0、ボアの始まりで F=−bore_radius。

    写像で合わせているので、s_we がどこにあっても両方が成り立つ。旧実装は
    振幅を掛けて合わせており、`a` が s_we → 1 で**発散**した（窓の後端から
    ボアまでの間隔で見ると 6.9mm で a=0.97 / 4.0mm で 3.48 / 1.0mm で 12.30）。
    `window_end_z` の `zb − 4.0` が唯一の歯止めになっていた。
    """
    for tid in SIZES:
        base = _template_params("mouthpiece", tid)
        # 窓の後端をボアへ寄せていく（旧実装が壊れた向き）。
        for gap in (10.0, 8.0, 6.0, 5.0, 4.0):
            zb0 = profiles.bore_start_z(base)
            p = dict(base, bore_length=base["overall_length"]
                     - (profiles.window_end_z(base) + gap))
            if profiles.cavity_layout_error(p) is not None:
                continue
            rb, zb = profiles.bore_radius(p), profiles.bore_start_z(p)
            z_we = profiles.window_end_z(p)
            d_we = (profiles.cut_top_y(p, z_we)
                    - profiles.cavity_floor_y(p, z_we)) / rb
            # 窓はそこで閉じる（`_soft_max` の丸めぶんだけ残る）
            assert abs(d_we) < 0.01, (tid, gap, d_we)
            # ボアの始まりで床はボア半径ぶん下（同じく丸めぶん）
            assert profiles.cavity_floor_y(p, zb) == pytest.approx(-rb, abs=0.05), (tid, gap)
            # 先端は間隔に依らない
            assert profiles.cavity_stations(p)[0]["h"] < 1.0, (tid, gap)
            assert zb0 > 0


def test_airway_never_narrows_behind_the_tip_by_default():
    """息の通り道は入口（ティップ）がいちばん狭くあること。

    リード先端から入った息が奥でさらに絞られては吹けない。**比較の相手は
    入口自身**なので、この判定には閾値が要らない（この repo で根拠の無い
    丸い数字を増やさずに済む数少ない判定）。3 サイズとも既定では最狭部が
    z=0 ＝ 入口そのもので、警告は出ない。

    バッフルを上げると奥が絞れて警告が出る。**ティップ開きを広げるのは
    対策にならない** —— 上がるのは入口だけで奥は動かないので、比はかえって
    悪くなる。助言がそちらを勧めないことも見る。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        base = _template_params("mouthpiece", tid)
        ent, h_min, z_min = profiles.airway_min(base)
        assert z_min == pytest.approx(0.0), (tid, z_min)
        assert h_min == pytest.approx(ent), (tid, h_min, ent)
        assert not [w for w in profiles.cavity_warnings(base) if "通り道" in w], tid

        comp = reg.make_component("mouthpiece", tid)
        bh_max = next(s.max for s in comp.param_specs() if s.key == "baffle_height")
        high = dict(base, baffle_height=bh_max)
        ent2, h2, z2 = profiles.airway_min(high)
        assert z2 > 0.0 and h2 < ent2, (tid, h2, ent2)
        why = [w for w in profiles.cavity_warnings(high) if "通り道" in w]
        assert why, tid
        assert "ティップ開きを広げると悪くなります" in why[0], (tid, why)


def test_pchip_rejects_duplicate_knots_by_name():
    """**同じ x を 2 つ渡したら、名指しで落ちること。**

    `_pchip_table` は区間幅 `h[i]` で割る。x が重なると `ZeroDivisionError` が
    リスト内包の奥から出るだけで、**どの表が壊れたか分からない**。
    `profiles` には `s_we` / `s_th` / `s_ch` から動的に組む表が 6 か所あり、
    どれも退化しうる（実際 `_floor_limit` が踏んでいた）ので、犯人が言える形にする。
    """
    with pytest.raises(ValueError) as e:
        profiles._pchip([(0.0, 0.0), (0.5, 1.0), (0.5, 2.0), (1.0, 3.0)], 0.3)
    assert "0.5" in str(e.value)
    # 正常な表は今までどおり通る（ガードが素通りを壊していないこと）
    assert profiles._pchip([(0.0, 0.0), (0.5, 1.0), (1.0, 2.0)], 0.5) == pytest.approx(1.0)


def test_floor_limit_survives_a_window_that_reaches_the_bore():
    """**窓の後端がボアに寄っても床の許容下限が落ちないこと。**

    `_floor_limit` は `(0,0) (s_we,0) (min(s_we+0.06,1),1) (1,1)` という表を組んで
    いた。`s_we >= 0.94` で第 3・第 4 節点が x=1.0 で衝突し、`_pchip_table` が
    `ZeroDivisionError`。閾値は `gap <= 0.06*zb` なのでサイズで変わり、
    **tenor は現在の壁 `zb − 4.0` から 1.0mm しか離れていなかった**
    （soprano 1.99 / alto 2.60 / tenor 3.00mm でクラッシュ）。

    `5fb0bf4` で消した `cavity_floor_y` の特異点と**同じ型**（区間幅で割る式が
    退化する）で、**同じ壁の裏に 2 つ並んでいた**。`zb − 4.0` は幾何の壁ではなく
    バグを覆っていた蓋だったので、蓋を外す前にこちらを塞ぐ。
    """
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        zb = profiles.bore_start_z(p)
        for s_we in (0.80, 0.90, 0.9399, 0.94, 0.9401, 0.97, 0.99, 0.999):
            q = dict(p, chamber_to_bore_mm=zb * (1.0 - s_we), window_length=60.0)
            assert profiles.window_end_z(q) / zb == pytest.approx(s_we, abs=1e-9), tid
            for z in (0.0, 0.5 * zb, 0.99 * zb, zb):
                profiles._floor_limit(q, z)      # 例外を出さないことが主張
            st = profiles.cavity_stations(q)
            assert len(st) > 20, (tid, s_we, len(st))
            assert st[0]["h"] < 1.0, (tid, s_we, st[0]["h"])


def test_chamber_to_bore_is_a_parameter_and_its_default_changes_nothing():
    """`zb − 4.0` をパラメータにしても既定形状が 1 ビットも動かないこと。

    この壁は「チェンバー→ボアの遷移区間を残す」という慣習で、**幾何の成立条件
    ではない**（成立条件は `cavity_layout_error` が別に見ている）。可動域を
    広げるために表へ出すが、既定 4.0 のままなら形は変わってはいけない。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        spec = next(s for s in comp.param_specs() if s.key == "chamber_to_bore_mm")
        assert spec.limit_kind == "convention"
        p = _template_params("mouthpiece", tid)
        assert p["chamber_to_bore_mm"] == pytest.approx(4.0), tid
        # 明示しない古いプロジェクトでも同じ形になること（既定で埋まる）
        bare = {k: v for k, v in p.items() if k != "chamber_to_bore_mm"}
        st_a = profiles.cavity_stations(dict(p))
        st_b = profiles.cavity_stations(dict(bare, chamber_to_bore_mm=4.0))
        assert len(st_a) == len(st_b), tid
        for a, b in zip(st_a, st_b):
            assert a["h"] == pytest.approx(b["h"], abs=1e-12), tid


def test_every_mouthpiece_param_says_where_its_wall_came_from():
    """**壁は 3 つに分類されていて、分類していないものが残っていないこと。**

    実測由来の壁（`body_dia` の下限＝ソプラノ実測）と、誰も測っていない暫定値
    （`beak_height` の既定は自認で「幾何的な暫定値」）と、幾何の成立条件
    （`shoulder_fullness` の ±1 は定義域そのもの）が、コード上まったく同じ顔を
    していた。分類を必須にして、**出所が無いものは「無い」と言わせる**
    ——空欄を埋めるために出所を発明しない。
    """
    from saxsketch.core.schema import LIMIT_KINDS
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        specs = comp.param_specs()
        assert len(specs) == 33, (tid, len(specs))
        for s in specs:
            assert s.limit_kind in LIMIT_KINDS, (tid, s.key, s.limit_kind)
            # 分類されていないパラメータを残さない（既定のままにしない）
            assert s.limit_kind != "unclassified", (tid, s.key)
            # 壁を緩めた側は必ず帯の外にある（緩めていないなら None のまま）
            if s.hard_min is not None:
                assert s.min is not None and s.hard_min <= s.min, (tid, s.key)
            if s.hard_max is not None:
                assert s.max is not None and s.hard_max >= s.max, (tid, s.key)


def test_walls_without_hard_bounds_still_clamp_exactly_as_before():
    """**`hard_*` を入れていないパラメータの挙動は 1 ビットも変えない。**

    分類を足しただけで可動域が動いてしまうと、「分類する」作業が黙って設計を
    変える作業になる。`hard_*` が `None` のものは帯がそのまま壁。
    """
    reg = get_registry().get("saxophone")
    comp = reg.make_component("mouthpiece", "alto")
    for s in comp.param_specs():
        if s.type not in ("float", "int") or s.min is None or s.max is None:
            continue
        if s.hard_min is None:
            assert s.validate(s.min - 10.0) == pytest.approx(s.min), s.key
        if s.hard_max is None:
            assert s.validate(s.max + 10.0) == pytest.approx(s.max), s.key


def test_a_widened_wall_lets_the_value_leave_the_band():
    """`hard_*` を入れた帯は**外へ出られる**こと（出られなければ広げた意味がない）。

    `chamber_to_bore_mm` が Phase A で唯一実際に広げたパラメータ。
    壁は掃引で測った値で、帯（2〜10mm）はその内側にある。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        s = next(x for x in comp.param_specs() if x.key == "chamber_to_bore_mm")
        assert s.hard_min is not None and s.hard_max is not None, tid
        assert s.hard_min < s.min and s.hard_max > s.max, tid
        # 帯の外だがまだ壁の内側 —— **丸めない**
        assert s.validate(s.min - 0.5) == pytest.approx(s.min - 0.5), tid
        assert s.validate(s.max + 5.0) == pytest.approx(s.max + 5.0), tid
        # 壁の外 —— 丸める
        assert s.validate(s.hard_min - 1.0) == pytest.approx(s.hard_min), tid
        assert s.validate(s.hard_max + 1.0) == pytest.approx(s.hard_max), tid


def test_clamping_is_never_silent():
    """**丸めたら必ず何をしたか言うこと**（黙ったクランプの 8 例目を塞ぐ）。

    以前は `ParamSpec.validate` が範囲外を無言で丸め、フロントは差分を拾って
    値を戻すだけだった。利用者にはスライダが勝手に戻ったようにしか見えない。
    報告には**値・単位・壁の種別・出所**が入る。
    """
    from saxsketch.core.schema import ParamSet
    reg = get_registry().get("saxophone")
    comp = reg.make_component("mouthpiece", "alto")
    ps = ParamSet(comp.param_specs(), comp.template.get("mouthpiece", {}))

    ps.apply({"min_wall": 0.2})                     # 製造の壁（下限 1.2）
    assert len(ps.adjustments) == 1
    a = ps.adjustments[0]
    assert a["key"] == "min_wall" and a["edge"] == "min"
    assert a["applied"] == pytest.approx(1.2) and a["requested"] == pytest.approx(0.2)
    assert a["limit_kind"] == "manufacturing"
    for frag in ("最小肉厚", "0.2", "1.2", "mm", "製造の制約", "出所:"):
        assert frag in a["message"], (frag, a["message"])

    # 帯の中なら黙っていてよい（報告は「丸めたとき」だけ）
    ps.apply({"min_wall": 2.0})
    assert ps.adjustments == []

    # 出所が無いものは「記載なし」と言う。発明しない。
    ps.apply({"tip_opening": 9.0})
    assert "記載なし" in ps.adjustments[0]["message"], ps.adjustments[0]["message"]

    # 直前の適用ぶんだけが残る（積み上がらない）
    ps.apply({"tip_opening": 2.4})
    assert ps.adjustments == []


def test_api_reports_clamping_to_the_browser(tmp_path):
    """クランプ報告が**画面まで届く**こと。端から端までの固定。

    サーバが丸めてもフロントに届かなければ黙ったのと同じ。空でも必ずキーを
    返す（フロントは前回の報告を消す判断をこのキーだけで行う）。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    assert c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "alto",
        "component_id": "mouthpiece"}).status_code == 200

    r = c.put("/api/project/params", json={"params": {"min_wall": 0.2}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["params"]["min_wall"] == pytest.approx(1.2)
    assert len(body["adjustments"]) == 1
    assert "最小肉厚" in body["adjustments"][0]["message"]

    # 帯の中へ戻したら報告は消える（キーは残る）
    r = c.put("/api/project/params", json={"params": {"min_wall": 2.0}})
    assert r.json()["adjustments"] == []

    # 成立しない組で弾かれたときは**丸めの話をしない**（値は保存されていない）。
    # `body_dia` 下限と `shank_dia` 上限はどちらも各自の帯の中なので丸めは起きず、
    # 組で `outer_layout_error` に当たる ——「弾いた」と「丸めた」が混ざらないこと。
    r = c.put("/api/project/params",
              json={"params": {"body_dia": 18.0, "shank_dia": 28.0}})
    assert r.status_code == 400, r.text
    assert "最大径" in r.json()["detail"]
    # 弾かれたあとサーバ側は前の値のまま（丸めの報告も残っていない）
    r = c.put("/api/project/params", json={"params": {"min_wall": 2.0}})
    assert r.json()["adjustments"] == []
    assert r.json()["params"]["body_dia"] == pytest.approx(29.1)


def test_the_warning_reaches_every_tab_not_just_the_section(alto):
    """**警告の出る場所がタブに依らないこと。**

    `cavity_warnings` は `Component.section()` の戻り値に埋まっていて、それを
    読むのは断面タブ（`/api/section`）だけだった —— 3D タブでウィンドウ長を
    上げると「形が動かない・理由も出ない」になる（2026-09-06 に報告して
    残した穴）。いまは `simulate()` の便に載るので、どのタブを見ていても
    右パネルの「⚠ 注意」カードに出る。

    出所は `Component.warnings()` 1 つで、3 経路が同じ 1 本を運ぶ。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app

    comp, base = alto
    c = TestClient(app)
    assert c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "alto",
        "component_id": "mouthpiece"}).status_code == 200

    def window_lines(ws):
        return [w for w in ws if "ウィンドウ長" in w]

    # **既定でも 1 行出ている**（天井がビーク下の肉厚で頭打ち ——
    # `docs/print-inspection.md` の既知の状態）ので、「空か否か」ではなく
    # ウィンドウ長の行で見る。
    assert window_lines(c.get("/api/project").json()["simulation"]["warnings"]) == []

    # 凍る点（alto 38.67 ＝ `_WINDOW_FREEZE_MM`）より上へ
    body = c.put("/api/project/params", json={"params": {"window_length": 44.0}}).json()
    line = window_lines(body["simulation"]["warnings"])
    assert len(line) == 1, body["simulation"]["warnings"]
    assert "38.7" in line[0]

    # 開き直しても、断面タブでも、同じ 1 本
    assert window_lines(c.get("/api/project").json()["simulation"]["warnings"]) == line
    assert window_lines(c.get("/api/section").json()["warnings"]) == line

    # 断面はクエリ上書きで**指を離す前に**動く（右カードは PUT を待つ）。
    # ここが断面側に警告を残してある唯一の理由。
    assert window_lines(c.get("/api/section",
                              params={"window_length": 30.0}).json()["warnings"]) == []

    # 帯の中へ戻せば消える（＝カードから行が消える）
    back = c.put("/api/project/params", json={"params": {"window_length": 30.0}}).json()
    assert window_lines(back["simulation"]["warnings"]) == []

    # 警告を持たない部品では空 —— UI はこれを見てカードごと出さない。
    # 「どの部品が警告を持つか」を UI に書かないための既定フック。
    for cid in ("reed", "ligature"):
        assert c.post("/api/project/new", json={
            "instrument_id": "saxophone", "template_id": "alto",
            "component_id": cid}).status_code == 200
        assert c.get("/api/project").json()["simulation"]["warnings"] == [], cid

    # 出所は `profiles` の 2 つだけ（代理変数を作らない）。`Component.warnings`
    # は繋ぐだけで、判定は書かない —— B-3 でシャンクの肉厚が 2 つ目になった。
    p = dict(base, window_length=44.0)
    assert comp.warnings(p) == (profiles.cavity_warnings(p)
                                + profiles.shank_warnings(p))


def test_widening_a_band_does_not_leave_the_analysis_silently_flat():
    """**帯の外へ出たとき、動かない指標は「動かない」と言うこと。**

    Tier2 は文献傾向に当てた回帰で、有効範囲は帯とほぼ同じ。壁を広げたぶん
    その外へ出られるようになったが、**外挿する根拠は無い**ので指標は頭打ちに
    なる。黙って平らになるのはこの repo で何度も踏んでいる型（スライダを
    動かしても何も起きないのに気づけない）なので、`note` で言う。
    """
    from saxsketch.acoustics import brightness as br
    reg = get_registry().get("saxophone")
    comp = reg.make_component("mouthpiece", "alto")
    p = _template_params("mouthpiece", "alto")

    inside = br.tone_metrics(p)
    assert "有効範囲の外" not in inside["note"]

    out = br.tone_metrics(dict(p, tip_opening=4.0))
    assert "有効範囲の外" in out["note"]
    assert "ティップ開き" in out["note"] and "4" in out["note"]
    # 頭打ちなので値は帯の端と同じ
    edge = br.tone_metrics(dict(p, tip_opening=3.2))
    for k in br.METRIC_KEYS:
        assert out[k] == pytest.approx(edge[k]), k

    # **感度表は壁で止める**（帯で止めると 1 段が符号ごと壊れる）
    t = br.sensitivity(dict(p, tip_opening=4.0), comp.param_specs())
    assert t["table"]["tip_opening"]["step"] == pytest.approx(0.05)


def test_survey_form_accepts_measurements_outside_the_band():
    """採寸フォームは**壁**で受けること。実物は帯の外にあることがある。

    帯で受けると測った値が別物にすり替わる —— `body_dia` の下限を
    ソプラノ実測が入るまで下げた経緯がまさにそれ。
    """
    reg = get_registry().get("saxophone")
    comp = reg.make_component("mouthpiece", "alto")
    tg = {d["key"]: d for d in comp.survey_targets()["params"]}
    specs = {s.key: s for s in comp.param_specs()}
    for key, d in tg.items():
        lo, hi = specs[key].bounds()
        assert d["min"] == lo and d["max"] == hi, key
    # 実際に広げた 3 本は帯より広いこと（＝この経路が壁を見ている証拠）
    assert tg["tip_opening"]["min"] < specs["tip_opening"].min
    assert tg["baffle_height"]["min"] < specs["baffle_height"].min
    assert tg["window_length"]["min"] < specs["window_length"].min


def test_goalseek_never_drags_a_deliberate_value_back_into_the_band():
    """ゴールシークは帯の中を探すが、**利用者が既に外にいるなら含めて探す**。

    含めないと、提案を受け入れた瞬間に帯の中へ黙って引き戻される ——
    利用者が意図して選んだ値を消すことになる。
    """
    from saxsketch.acoustics import goalseek as gs
    reg = get_registry().get("saxophone")
    comp = reg.make_component("mouthpiece", "alto")
    specs = comp.param_specs()
    spec_map = {s.key: s for s in specs}
    p = _template_params("mouthpiece", "alto")

    def bounds_for(params):
        keys = [k for k in gs.OPT_KEYS if k in spec_map]
        out = {}
        for k in keys:
            s, v = spec_map[k], float(params[k])
            out[k] = (min(s.min, v) if s.min is not None else None,
                      max(s.max, v) if s.max is not None else None)
        return out

    assert bounds_for(p)["tip_opening"] == (spec_map["tip_opening"].min,
                                            spec_map["tip_opening"].max)
    wide = dict(p, tip_opening=4.0)
    assert bounds_for(wide)["tip_opening"][1] == pytest.approx(4.0)
    # 実際に走らせても提案が現在値を下回らない（帯へ引き戻さない）
    r = gs.goal_seek(wide, specs, {"power": 9.0}, comp.size_info,
                     lambda q: comp.cavity_volume(q))
    assert r["proposal"]["tip_opening"] >= 3.2 - 1e-9


def _sweeper():
    """`cad/windycity/sweep_limits.py` を読み込む（パッケージではないので直読み）。

    掃引器は出荷物ではなく道具だが、**壁の根拠を作っているのはこの道具**なので、
    目が利くかどうかはテストで押さえる。
    """
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "cad" / "windycity" / "sweep_limits.py"
    spec = importlib.util.spec_from_file_location("sweep_limits_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_sweeper_measures_more_than_the_cavity_height():
    """**掃引器の目が盲だったことの回帰テスト（Phase B-0）。**

    初版の指紋は「ステーション枚数・先端高さ・最大高さ・窓の後端・ボアの
    始まり」だけを見ていた。だから**幅でしか効かない** `side_rail_width` と、
    **外形の先端 0.29mm でしか効かない** `tip_chamfer` を「形が動かない ＝
    このパラメータは効いていない」と誤判定する。掃引器が捕まえるために
    作られた型に、掃引器自身が嵌まっていた。

    ここで主張するのは 2 つ: 旧指紋の成分（`cavity_h` と離散量）は本当に
    動かないこと（＝ 誤判定は本物だったこと）と、新しい指紋なら動くこと。
    """
    sw = _sweeper()
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    base = {s.key: s.default for s in comp.param_specs()}
    grids = sw._grids(base)
    specs = {s.key: s for s in comp.param_specs()}
    for key, want in (("side_rail_width", "cavity_w"), ("tip_chamfer", "outer_r")):
        spec = specs[key]
        probe = sw._probe(comp, base, key, spec.default, spec.step, grids)
        assert probe is not None, key
        _slopes, rels = probe
        assert sw._kept(rels, None)[0] == want, (key, rels)
        a0 = sw._axes(base, grids)
        a1 = sw._axes(dict(base, **{key: base[key] + 2.0 * spec.step}), grids)
        assert a0["cavity_h"] == a1["cavity_h"], key      # 旧指紋は動かない
        assert a0["_disc"] == a1["_disc"], key
        assert sw._fingerprint(a0) != sw._fingerprint(a1), key


def test_the_tip_chamfer_disappears_on_a_coarse_grid():
    """**先端の面取りは粗いグリッドでは消える。**

    アルトの面取り長は `tip_chamfer` 既定で 0.07mm、上限 1.2mm でも 0.29mm。
    全長を 60 等分すると最初の標本は 1.3mm 先なので、**面取りを跨いで
    「何も動かない」と出る**。掃引器の外形グリッドが先端だけ 0.05mm 刻みなのは
    このため —— 物差しの目盛りが測る対象より粗いと、無いのと同じ。
    """
    sw = _sweeper()
    p = _template_params("mouthpiece", "alto")
    q = dict(p, tip_chamfer=1.2)
    assert profiles.tip_chamfer_len(q) < 0.35, profiles.tip_chamfer_len(q)
    length = p["overall_length"]
    coarse = [length * i / sw.OUTER_GRID_N for i in range(1, sw.OUTER_GRID_N + 1)]
    assert ([profiles.outer_radius(p, z) for z in coarse]
            == [profiles.outer_radius(q, z) for z in coarse])
    dense = [0.001 + sw.TIP_GRID_DZ * i for i in range(sw.TIP_GRID_N)]
    assert ([profiles.outer_radius(p, z) for z in dense]
            != [profiles.outer_radius(q, z) for z in dense])


def test_the_sweeper_can_pin_a_choice_parameter():
    """**choice を固定できないと測れないパラメータが 2 本ある。**

    `baffle_curvature` は `baffle_type="curve"` のとき、`rollover_radius` は
    `"rollover"` のときにしか形を動かさない。テンプレートの既定は `"step"` なので、
    `--with` が float しか受けない初版では、この 2 本は永久に
    「効いていない」としか出なかった。
    """
    sw = _sweeper()
    rest, flags, extra, axis, steps = sw.parse_args(
        ["baffle_curvature", "alto", "--no-build",
         "--with", "baffle_type=curve", "--with", "window_length=44",
         "--axis", "cavity_a"])
    assert rest == ["baffle_curvature", "alto"]
    assert flags == {"--no-build"}
    assert extra == {"baffle_type": "curve", "window_length": 44.0}
    assert axis == "cavity_a"
    assert steps == sw.OUT_STEPS                     # 既定は据え置き

    # B-3 で足した `--steps`。**届く距離は段数 × 刻み**なので、刻みの細い
    # パラメータ（`bore_dia` は 0.05mm）では既定 40 段が打ち切りになる。
    _r, _f, _e, _a, steps = sw.parse_args(["bore_dia", "--steps", "200"])
    assert steps == 200

    p = _template_params("mouthpiece", "alto")
    for key, kind in (("baffle_curvature", "curve"), ("rollover_radius", "rollover")):
        step = 0.2 if key == "baffle_curvature" else 2.0
        for baffle, moves in ((kind, True), ("step", False)):
            a = profiles.cavity_stations(dict(p, baffle_type=baffle))
            b = profiles.cavity_stations(dict(p, baffle_type=baffle,
                                              **{key: p[key] + step}))
            same = all(x["h"] == pytest.approx(y["h"], abs=1e-12)
                       for x, y in zip(a, b))
            assert same != moves, (key, baffle)


def test_tip_opening_zero_is_rejected_with_a_reason():
    """**開き 0 は素の `ZeroDivisionError` ではなく理由で断ること。**

    radial のフェイシングは `y(0)=tip` となる円弧半径を
    `r = (fl² + tip²) / (2·tip)` で解くので、`tip_opening = 0` で落ちる。
    落ちる場所は `facing_rise` の奥（`cavity_stations` → `_roof_base_y` →
    `tip_roof_y` → `cut_top_y`）で、**`params_error` は `None` を返していた**。
    掃引 `sweep_limits.py tip_opening` が下限へ歩いてちょうど 0 で踏んだ
    ——`_pchip_table` の節点衝突と同じ型（退化する割り算）で、これで 4 つ目。
    """
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    base = {s.key: s.default for s in comp.param_specs()}
    err = comp.params_error(dict(base, tip_opening=0.0))
    assert err is not None and "ティップ開き" in err
    assert comp.params_error(dict(base, tip_opening=0.05)) is None
    with pytest.raises(ValueError) as e:
        profiles.facing_rise(dict(base, tip_opening=0.0), 0.0)
    assert "ティップ開き" in str(e.value)
    # 楕円カーブは割り算をしないので落ちない（ここも 0 は断るが、理由は上流）
    assert profiles.facing_rise(
        dict(base, tip_opening=0.0, facing_curve="elliptic"), 0.0) == 0.0


#: Phase B-1 で掃引した「フェイシング」6 本。
_B1_FACING = ("facing_length", "tip_rail_width", "tip_rail_thickness",
              "tip_chamfer", "side_rail_width", "table_angle")


def test_the_facing_walls_hold_up_as_geometry():
    """**B-1 で測った壁が 3 サイズとも幾何として成立していること。**

    掃引はソリッドまで確かめている（生ログは `docs/param-limits.md`）が、
    OCCT はここでは 1 点 15 秒かかるので、テストは段 1〜2（成立条件と
    ステーションの退化）を押さえる。**壁の数字を書き写すのではなく、
    壁で形が成立することを主張する** —— 数字を写すテストは、値を変えた
    ときに一緒に書き換わるだけで何も守らない。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        specs = {s.key: s for s in comp.param_specs()}
        for key in _B1_FACING:
            spec = specs[key]
            lo, hi = spec.bounds()
            assert lo is not None and hi is not None, key
            assert lo < spec.min or hi > spec.max, key       # 帯より広いこと
            for v in (lo, hi):
                p = dict(base, **{key: v})
                assert comp.params_error(p) is None, (tid, key, v)
                st = profiles.cavity_stations(p)
                assert len(st) > 20, (tid, key, v, len(st))
                assert st[0]["h"] < 1.6, (tid, key, v, st[0]["h"])


def test_the_widened_facing_band_is_not_a_dead_band():
    """**広げた先でつまみが空回りしていないこと。**

    「ソリッドが 1 個できる」は壁の条件であって、つまみが効く条件ではない。
    帯の端から壁まで動かして、形が実際に変わることを主張する ——
    `side_rail_width` は**幅でしか効かない**ので、空洞の高さしか見ていな
    かった初版の掃引器はここを「効いていない」と誤判定していた（Phase B-0）。
    """
    def shape(p):
        st = profiles.cavity_stations(p)
        return ([round(x["h"], 9) for x in st], [round(x["w"], 9) for x in st],
                [round(profiles.section_area(x), 9) for x in st])

    reg = get_registry().get("saxophone")
    comp = reg.make_component("mouthpiece", "alto")
    base = {s.key: s.default for s in comp.param_specs()}
    specs = {s.key: s for s in comp.param_specs()}
    checked = 0
    for key in _B1_FACING:
        spec = specs[key]
        lo, hi = spec.bounds()
        for edge, wall in ((spec.min, lo), (spec.max, hi)):
            if wall == edge:
                continue                      # その向きへは広げていない
            assert shape(dict(base, **{key: edge})) !=                 shape(dict(base, **{key: wall})), (key, edge, wall)
            checked += 1
    assert checked == 11, checked            # tip_chamfer の下だけ広げていない


def test_the_facing_walls_clamp_and_say_which_wall():
    """帯の外は通し、壁の外は丸めて**壁だと名乗る**こと。

    Phase A で `at` を「帯」と「壁」に分けたのは、同じ丸めでも利用者にとって
    意味が違うから。B-1 で広げた 6 本でもそれが効いていることを見る。
    """
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    spec = next(s for s in comp.param_specs() if s.key == "facing_length")
    assert (spec.hard_min, spec.hard_max) == (3.0, 50.0)
    # 帯の外・壁の内 —— 丸めない
    v, rep = spec.validate_report(10.0)
    assert v == pytest.approx(10.0) and rep is None
    # 壁の外 —— 丸めて、壁だと言う
    v, rep = spec.validate_report(1.0)
    assert v == pytest.approx(3.0) and rep is not None
    assert rep["at"] == "wall" and rep["applied"] == pytest.approx(3.0)
    assert "越えられない壁" in rep["message"]
    # 下限を広げていない `tip_chamfer` は帯のままクランプし、帯だと言う
    ch = next(s for s in comp.param_specs() if s.key == "tip_chamfer")
    assert ch.hard_min is None and ch.hard_max == 3.2
    v, rep = ch.validate_report(-0.5)
    assert v == pytest.approx(0.0) and rep["at"] == "band"


def test_the_lifted_baffle_clamps_reach_the_shape():
    """**外した掛け金が本当に外れていることの回帰テスト（Phase B-2）。**

    `baffle_step_rise` は `_v_step` の中で 0.85 に、`baffle_curvature` は
    `_v_curve` の中で ±1 に頭打ちにされていた。**スキーマの帯と同じ数字が
    コードの中にもう 1 部あった**ので、`hard_max` だけ広げてもつまみは
    空回りする。ここで見るのは「旧クランプの外で天井が動くこと」。

    下限のほうは外していない。`baffle_step_rise` が負のときは
    `if r <= 0.0: return base` が実測どおりの肩を返すので、**分岐そのものが
    下限 0 の理由**（測定ではない）。それも一緒に固定する。
    """
    p = _template_params("mouthpiece", "alto")
    zb = profiles.bore_start_z(p)

    def roof(**kw):
        return [profiles.cavity_roof_y(dict(p, **kw), zb * i / 40.0)
                for i in range(41)]

    assert roof(baffle_type="step", baffle_step_rise=1.2) !=         roof(baffle_type="step", baffle_step_rise=0.85)
    assert roof(baffle_type="curve", baffle_curvature=1.5) !=         roof(baffle_type="curve", baffle_curvature=1.0)
    assert roof(baffle_type="curve", baffle_curvature=-1.5) !=         roof(baffle_type="curve", baffle_curvature=-1.0)
    # 負の段は構造として効かない（クランプではなく分岐）
    assert roof(baffle_type="step", baffle_step_rise=-0.5) ==         roof(baffle_type="step", baffle_step_rise=0.0)


def test_the_rollover_fillet_saturates_by_arithmetic_not_by_a_clamp():
    """ロールオーバーの肩は **w ≥ 1 で式そのものが飽和する**。

    `f(u) = u²/(2w) (u<w) / u−w/2 (u≥w)` を `f(t)/f(1)` で正規化しているので、
    `w = rollover_radius / span` が 1 を超えると t は常に w 未満 ＝ `t²` に
    なり、**w が消える**。外した 0.9 のクランプはこの飽和のすぐ内側にいた
    だけで、壁を作っていたのは掛け金ではなく算数のほう。

    下限 0.02 は残してある —— `u²/(2w)` の割り算が w→0 で発散する。
    `_pchip_table` の節点衝突・`cavity_floor_y` の特異点・`_chamber_weight`・
    `facing_rise` の円弧半径に続く、同じ型の 5 つ目。
    """
    p = dict(_template_params("mouthpiece", "alto"), baffle_type="rollover")
    zb = profiles.bore_start_z(p)
    span = (1.0 - profiles.baffle_plateau(p)) * zb

    def roof(r):
        return [profiles.cavity_roof_y(dict(p, rollover_radius=r), zb * i / 40.0)
                for i in range(41)]

    assert roof(span) == pytest.approx(roof(5.0 * span), abs=1e-9)   # w≥1 で飽和
    assert roof(0.999 * span) != roof(span)        # その手前はまだ動く
    assert roof(0.0) == pytest.approx(roof(0.02 * span), abs=1e-9)   # 下はガードで一定
    for r in (0.0, 1e-9, 0.01 * span):             # 発散しない
        assert all(abs(y) < 1e3 for y in roof(r)), r


def test_the_brightness_cap_is_policy_not_a_missed_edit():
    """`brightness` が壁の外で頭打ちなのは**わざと**。

    `baffle_step_rise` の 0.85 は 3 か所にあった —— スキーマの `max`、
    `_v_step` のクランプ、そして `brightness._baffle_bonus` の正規化 `/0.85`。
    幾何の掛け金は外したが、**あちらは回帰の有効範囲**であって幾何の壁では
    ないので外さない（Phase A の Tier2 と同じ扱い）。数値が同じでも意味が違う。

    これを書いておかないと、次に読む人が「片方だけ直し忘れ」として直す。
    """
    from saxsketch.acoustics import brightness
    p = dict(_template_params("mouthpiece", "alto"), baffle_type="step")
    at_band = brightness.tone_metrics(dict(p, baffle_step_rise=0.85))["brightness"]
    for v in (1.5, 2.85):
        assert brightness.tone_metrics(
            dict(p, baffle_step_rise=v))["brightness"] == at_band, v
    # 形のほうは動いている（＝ 頭打ちなのは音響モデルだけ）
    zb = profiles.bore_start_z(p)
    assert (profiles.cavity_roof_y(dict(p, baffle_step_rise=2.85), 0.9 * zb)
            != profiles.cavity_roof_y(dict(p, baffle_step_rise=0.85), 0.9 * zb))


def test_the_throat_ratio_is_invisible_to_the_old_fingerprint():
    """**B-0 で足した軸が無いと `throat_ratio` は測れない。**

    初版の指紋は「ステーション枚数・先端高さ・最大高さ・窓の後端・ボアの
    始まり」の 5 つのスカラーだった。`throat_ratio` は空洞の**途中**を相似に
    絞るだけなので、この 5 つは 1 ビットも動かない ——「効いていない」と
    誤判定される。掃引の実測でも本命の軸は `cavity_a`（応答 117〜118%）。

    `chamber_ratio` のほうは最大高さが動くので旧指紋でも見えていた。
    **同じ節のパラメータでも、見える／見えないは別々に決まる。**
    """
    p = _template_params("mouthpiece", "alto")

    def coarse(q):
        st = profiles.cavity_stations(q)
        return (len(st), st[0]["h"], max(s["h"] for s in st),
                profiles.window_end_z(q), profiles.bore_start_z(q))

    def areas(q):
        return [profiles.section_area(s) for s in profiles.cavity_stations(q)]

    assert coarse(dict(p, throat_ratio=0.7)) == coarse(p)      # 旧指紋は盲
    assert areas(dict(p, throat_ratio=0.7)) != areas(p)        # 新しい軸は見える
    assert coarse(dict(p, chamber_ratio=1.6)) != coarse(p)     # こちらは見えていた


def test_the_baffle_plateau_band_is_a_union_across_types():
    """`baffle_plateau` の帯は**どの型のものでもない**（Phase B-2 の実測）。

    実効範囲は `_PLATEAU_RANGE` が型ごとに決めていて、スキーマの帯
    0.02〜0.75 は 4 型を覆う和集合。だから**どの型で見てもスライダの端は
    死んでいる** —— straight / curve では上側の 86%、step / rollover では
    合わせて 18% が動かない。掃引も 3 サイズ全部で「帯の端から先は形が
    動かない」と出た（＝ 壁はスキーマではなく型の定義の側にある）。

    `_PLATEAU_RANGE` は外さない。「長い棚を許せばそれはもうストレートでは
    なくステップ」という**理由が書いてある**掛け金だから ——理由が
    「未測定」「出所なし」「循環」だった 3 本とはそこが違う。
    """
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    spec = next(s for s in comp.param_specs() if s.key == "baffle_plateau")
    assert (spec.hard_min, spec.hard_max) == (None, None)      # 広げていない
    base = {s.key: s.default for s in comp.param_specs()}
    zb = profiles.bore_start_z(base)

    def roof(bt, v):
        return [profiles.cavity_roof_y(
            dict(base, baffle_type=bt, baffle_plateau=v), zb * i / 40.0)
            for i in range(41)]

    for bt in ("step", "straight", "curve", "rollover"):
        lo, hi = profiles._PLATEAU_RANGE[bt]
        assert spec.min < lo or spec.max > hi, bt        # 帯のほうが広い
        assert roof(bt, spec.min) == roof(bt, lo)        # 端は型の実効範囲へ丸まる
        assert roof(bt, spec.max) == roof(bt, hi)
        assert roof(bt, lo) != roof(bt, hi)              # 実効範囲の中では効く


#: Phase B-2 で掃引して壁を書いた「バッフル ＋ チェンバー」5 本と、
#: それが生きるバッフル型。`baffle_plateau` は**わざと入っていない** ——
#: 壁が `_PLATEAU_RANGE`（型の定義）の側にあると測定で分かったので広げていない。
_B2_WALLED = (("baffle_step_rise", "step"), ("baffle_curvature", "curve"),
              ("rollover_radius", "rollover"), ("throat_ratio", "step"),
              ("chamber_ratio", "step"))


def test_the_baffle_and_chamber_walls_hold_up_as_geometry():
    """**B-2 で測った壁が 3 サイズとも幾何として成立していること。**

    B-1 と同じ流儀 —— 壁の数字を書き写すのではなく、壁で形が成立することを
    主張する。掃引はここで OCCT のソリッドまで確かめている（生ログは
    `docs/sweeps/b2-baffle-chamber.txt`）が、テストは段 1〜2 を押さえる。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        specs = {s.key: s for s in comp.param_specs()}
        for key, kind in _B2_WALLED:
            spec = specs[key]
            lo, hi = spec.bounds()
            assert lo is not None and hi is not None, key
            assert lo < spec.min or hi > spec.max, key       # 帯より広いこと
            for v in (lo, hi):
                p = dict(base, baffle_type=kind, **{key: v})
                assert comp.params_error(p) is None, (tid, key, v)
                st = profiles.cavity_stations(p)
                assert len(st) > 20, (tid, key, v, len(st))
                assert st[0]["h"] < 1.6, (tid, key, v, st[0]["h"])


def test_the_widened_baffle_band_is_not_a_dead_band():
    """**広げた先でつまみが効いていること。**

    B-2 は 4 本で「壁がスキーマではなくコードの中にあった」ので、
    `hard_*` を広げただけでは足りない ——`profiles` 側の掛け金を外して
    初めて形が動く。ここはその両方が揃っていることの回帰。

    型ごとに効く本が違うので、`_B2_WALLED` の型を当ててから比べる
    （既定の `step` のままだと `baffle_curvature` と `rollover_radius` は
    どちらの端でも同じ形になり、テストが素通りする）。
    """
    def shape(p):
        st = profiles.cavity_stations(p)
        return ([round(x["h"], 9) for x in st], [round(x["w"], 9) for x in st],
                [round(profiles.section_area(x), 9) for x in st])

    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    base = {s.key: s.default for s in comp.param_specs()}
    specs = {s.key: s for s in comp.param_specs()}
    checked = 0
    for key, kind in _B2_WALLED:
        spec = specs[key]
        lo, hi = spec.bounds()
        for edge, wall in ((spec.min, lo), (spec.max, hi)):
            if wall == edge:
                continue                      # その向きへは広げていない
            assert shape(dict(base, baffle_type=kind, **{key: edge})) !=                 shape(dict(base, baffle_type=kind, **{key: wall})), (key, edge, wall)
            checked += 1
    assert checked == 9, checked      # baffle_step_rise の下だけ広げていない


def test_the_baffle_walls_clamp_and_say_which_wall():
    """帯の外は通し、壁の外は丸めて**壁だと名乗る**こと（B-2 の 5 本）。"""
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    specs = {s.key: s for s in comp.param_specs()}

    ro = specs["rollover_radius"]
    assert (ro.hard_min, ro.hard_max) == (0.5, 21.0)
    v, rep = ro.validate_report(20.5)                 # 帯の外・壁の内
    assert v == pytest.approx(20.5) and rep is None
    v, rep = ro.validate_report(40.0)                 # 壁の外
    assert v == pytest.approx(21.0) and rep["at"] == "wall"
    assert "越えられない壁" in rep["message"]

    # 下だけ広げていない `baffle_step_rise` は、下は帯・上は壁と名乗り分ける
    sr = specs["baffle_step_rise"]
    assert sr.hard_min is None and sr.hard_max == 2.85
    assert sr.validate_report(-0.5)[1]["at"] == "band"
    assert sr.validate_report(4.0)[1]["at"] == "wall"

    # 広げていない `baffle_plateau` は両側とも帯のまま
    pl = specs["baffle_plateau"]
    assert (pl.hard_min, pl.hard_max) == (None, None)
    assert pl.validate_report(0.9)[1]["at"] == "band"


def test_the_bore_walls_are_relations_not_numbers():
    """**ボア 2 本の壁は他のパラメータとの関係で決まる（Phase B-3）。**

    - `bore_dia` 上 …… シャンクが残ること（`bore_dia` < `shank_dia`）
    - `bore_length` 上 …… 窓が 2.0mm 残ること。止まる位置は 3 サイズとも
      **ボアの始まり zb ＝ 6.2〜6.4mm** で揃い、`overall_length` を動かすと
      壁も同じだけ動く。**`window_length` を動かしても動かない** ——
      窓の後端は既に `zb − chamber_to_bore_mm` で頭打ちなので、この向きで
      相手になるのは全長のほう。

    掛け金の数字だけを書き写すと、相手が動いたときに嘘になる。だからここは
    **関係のほうを主張する**（数字は `hard_*` が持ち、成立条件は
    `outer_layout_error` / `cavity_layout_error` が 1 か所ずつ持つ）。
    """
    reg = get_registry().get("saxophone")

    def top(comp, base):
        """`params_error` が通る最大の `bore_length`（0.1mm 刻み）。"""
        v = base["bore_length"]
        while comp.params_error(dict(base, bore_length=round(v + 0.1, 1))) is None:
            v = round(v + 0.1, 1)
        return v

    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        specs = {s.key: s for s in comp.param_specs()}

        # --- bore_dia: 壁はシャンク径の 1 段手前 ＝ シャンクが残る限界
        bd = specs["bore_dia"]
        assert bd.hard_max == pytest.approx(round(base["shank_dia"] - 0.05, 2))
        assert comp.params_error(dict(base, bore_dia=bd.hard_max)) is None, tid
        err = comp.params_error(dict(base, bore_dia=base["shank_dia"]))
        assert err is not None and "シャンク径" in err, tid
        # 下は帯の端から 10mm（掃引で 3 サイズともソリッド 1 個まで確認した）
        assert bd.hard_min == pytest.approx(round(base["bore_dia"] - 11.0, 2))
        assert comp.params_error(dict(base, bore_dia=bd.hard_min)) is None, tid

        # --- bore_length: 壁を決めているのは長さではなく zb
        t_def = top(comp, base)
        zb = round(base["overall_length"] - t_def, 2)
        assert 6.0 <= zb <= 6.6, (tid, zb)
        assert specs["bore_length"].hard_max <= t_def, tid      # 掛け金は内側
        short = specs["overall_length"].min
        t_short = top(comp, dict(base, overall_length=short))
        assert short - t_short == pytest.approx(zb, abs=0.15), tid
        assert t_short < t_def - 1.0, tid                       # 壁が動いた
        # ウィンドウ長は**この向きでは相手にならない**
        assert top(comp, dict(base, window_length=44.0)) == pytest.approx(t_def)


def test_the_bore_cylinder_ignores_min_wall_and_the_card_says_so():
    """**空洞は `min_wall` を守るのに、ボアの円柱は守らない（B-3 の実測）。**

    `shell_limit` は空洞を `ro − min_wall` に収めるが、`_bore_solid` は素の
    円柱を引く。**同じ法則が片方にしか掛かっていない**ので、肉厚 0 でも
    −1.0mm でも `params_error` は `None`、OCCT もソリッド 1 個を返した
    （体積だけが soprano 11776 → 4541mm3 と 61% 落ちる ＝ シャンクが丸ごと
    消えている）。段 3 は「1 個か」しか見ないので掃引では捕まらない。

    線引き:
      肉厚 ≤ 0        → `outer_layout_error`（壁。越えさせない）
      0 < 肉厚 < 壁厚 → 注意カード（形は指定どおり出るが刷れない）
      肉厚 ≥ 壁厚     → 何も言わない
    """
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    base = {s.key: s.default for s in comp.param_specs()}
    sh, mw = base["shank_dia"], base["min_wall"]

    # ちょうど min_wall では言わない（浮動小数の縁で立たせない）
    assert profiles.shank_warnings(dict(base, bore_dia=sh - 2.0 * mw)) == []
    thin = dict(base, bore_dia=round(sh - 2.0 * mw + 0.5, 2))
    w = profiles.shank_warnings(thin)
    assert len(w) == 1 and "シャンクの肉厚" in w[0] and "1.55mm" in w[0]
    # カードへ届く経路（`Component.warnings` が 2 つの出所を繋ぐ）
    assert w[0] in comp.warnings(thin)
    # 肉厚 0 は注意ではなく壁
    assert profiles.shank_warnings(dict(base, bore_dia=sh)) == []
    assert comp.params_error(dict(base, bore_dia=sh)) is not None
    # 空洞のほうは同じ肉厚を守っている（片方にしか掛かっていなかったことの記録）
    z = profiles.bore_start_z(base) * 0.5
    assert profiles.shell_limit(base, z)["half_width"] == pytest.approx(
        profiles.outer_radius(base, z) - mw)


def test_a_bore_without_length_is_rejected_before_occt_sees_it():
    """**ボアは長さを持たなければならない（B-3）。**

    `bore_length <= 0` は「ボアが部品の外から始まる」。円柱が 1 ビットも
    削らないので体積が逆に増え、−1.5 を割ると `Solid.make_cylinder` が
    `Null TopoDS_Shape` を返してビルドが素の `ValueError` で落ちる
    （掃引で 3 サイズとも −1.5 までソリッド 1 個、−2.0 で落ちた）。

    書く前は**段 1〜2 が −21mm まで素通りしていた** —— `cavity_stations` は
    平然とステーションを返し、掃引器の段 3 で初めて落ちた（生ログ
    `docs/sweeps/b3-bore-window.txt`）。条件を `cavity_layout_error` に
    1 か所書いたので、いまは `params_error` と `cavity_stations` の
    **両方が同じ理由**を返す。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        spec = next(s for s in comp.param_specs() if s.key == "bore_length")
        assert spec.hard_min == 1.0
        assert comp.params_error(dict(base, bore_length=1.0)) is None, tid
        assert len(profiles.cavity_stations(dict(base, bore_length=1.0))) > 20
        for v in (0.0, -1.0, -2.0):
            err = comp.params_error(dict(base, bore_length=v))
            assert err is not None and "ボア長" in err, (tid, v)
            # 出所は 1 つ ——ステーション側も同じ理由で断る
            with pytest.raises(ValueError, match="ボア長"):
                profiles.cavity_stations(dict(base, bore_length=v))


def test_no_wall_value_makes_the_analysis_emit_something_json_cannot_carry():
    """**壁まで開けた値で `simulate()` が JSON になること。**

    B-3 で `bore_length` の壁を 1.0mm まで広げたら、そこで
    `tier1.in_tune_mm` が **NaN** になり `PUT /api/project/params` が 500 で
    落ちた —— ボアがほとんど無いとコーク線が空洞の終端でクランプされ、
    1mm 押しても音程が動かない（傾き 0）。零点が出ないのを NaN で表していた。

    いまは `None`（＝「合う挿し込み量が無い」）を返す。**壁を広げると下流が
    壊れる**のは Phase A で 4 か所出た型なので、ここは 1 本ずつではなく
    **壁を持つ全パラメータ × 3 サイズ**をまとめて見る。

    **B-4a で「壁に立てない」組が出た。** 径 2 本の壁は相手との関係
    （ボア径 < シャンク径 ≤ 最大径）で、掛け金は相手を壁まで寄せたときに
    届く所に置いてある。だから既定の相手のままだと `hard_min` に立てない ——
    それは壊れているのではなく**関係だから**なので、通らないときは理由が
    相手の名前を挙げていることだけ確かめて数えない。
    """
    reg = get_registry().get("saxophone")
    checked, relational = 0, 0
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {sp.key: sp.default for sp in comp.param_specs()}
        for spec in comp.param_specs():
            for wall in (spec.hard_min, spec.hard_max):
                if wall is None:
                    continue
                p = dict(base, **{spec.key: wall})
                err = comp.params_error(p)
                if err is not None:
                    # 関係で決まる壁だけが既定の相手で立てない。理由が相手を
                    # 名指ししていることを確かめる（黙って通さない）。
                    assert spec.key in ("body_dia", "shank_dia"), (tid, spec.key)
                    assert ("ボア径" in err or "最大径" in err
                            or "シャンク径" in err), (tid, spec.key, err)
                    relational += 1
                    continue
                res = comp.simulate(p)
                # allow_nan=False —— FastAPI の JSON 化と同じ厳しさで見る
                json.dumps(res, allow_nan=False, default=str)
                checked += 1
    assert checked >= 30, checked
    assert relational == 9, relational


def test_the_outer_diameter_walls_are_relations_not_numbers():
    """**径 2 本の壁は相手で決まる（Phase B-4a）。**

    測ったのは「通る範囲そのもの」で、帯の外へ歩く掃引では出せない ——
    帯の端が既に弾かれている組があるため（下のテスト）。範囲の端は 3 サイズとも
    ぴったり相手の値になる:

        ボア径 < シャンク径 ≤ 最大径

    ここでも数字ではなく**関係**を主張する。掛け金（`hard_*`）は相手を壁まで
    寄せたときに届く所に置いてあるだけで、成立条件は `outer_layout_error` が
    1 か所で持つ。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}

        def span(key, lo, hi, step, b=None, _c=comp, _base=base):
            """`params_error` が通る値の最小と最大（総当たり）。"""
            b = _base if b is None else b
            ok = [round(lo + step * i, 3)
                  for i in range(int(round((hi - lo) / step)) + 1)
                  if _c.params_error(
                      dict(b, **{key: round(lo + step * i, 3)})) is None]
            return (ok[0], ok[-1]) if ok else (None, None)

        # --- 最大径: 下はシャンク径そのもの。上はこの範囲では見つからない
        lo, hi = span("body_dia", 10.0, 40.0, 0.1)
        assert lo == pytest.approx(base["shank_dia"], abs=0.1), (tid, lo)
        assert hi == pytest.approx(40.0), (tid, hi)
        # 相手を動かすと壁も動く（数字ではない）
        lo2, _ = span("body_dia", 10.0, 40.0, 0.1,
                      dict(base, shank_dia=20.0, bore_dia=15.0))
        assert lo2 == pytest.approx(20.0, abs=0.1), (tid, lo2)

        # --- シャンク径: 下はボア径、上は最大径。**両端とも関係**
        lo, hi = span("shank_dia", 8.0, 40.0, 0.1)
        assert lo == pytest.approx(base["bore_dia"] + 0.1, abs=0.1), (tid, lo)
        assert hi == pytest.approx(base["body_dia"], abs=0.1), (tid, hi)
        lo2, hi2 = span("shank_dia", 8.0, 40.0, 0.1,
                        dict(base, bore_dia=12.0, body_dia=34.0))
        assert lo2 == pytest.approx(12.1, abs=0.1), (tid, lo2)
        assert hi2 == pytest.approx(34.0, abs=0.1), (tid, hi2)


def test_a_relation_wall_leaves_band_ends_that_cannot_be_reached():
    """**帯の端が壁の外へはみ出すことがある（B-4a の実測）。**

    径 2 本の帯は 3 サイズ共通の絶対レンジ（18〜34 / 14〜28）で、既定の相手の
    ままだと **12 端（2 本 × 2 端 × 3 サイズ）のうち 6 端が弾かれる** ——
    最大径の下端 18.0 は 3 サイズとも、シャンク径の下端 14.0 はアルトと
    テナー、上端 28.0 はソプラノ。これは帯の数字が下手なのではなく、
    **相手で動く壁を静的な帯で表せない**ということ ——相手を一緒に動かせば
    どの端も届く。

    大事なのは黙って丸めないこと。`hard_*` を入れた今は、帯の端に置いた値は
    クランプされず、通らないときは**理由つきで断られる**（相手の名前が文面に
    出る）。

    なお 18.0 / 14.0 という数字は `f1e79e8` で「ソプラノ実測 シャンク径 15.3mm
    が入る位置」として下げたものだが、**その 15.3 はもう存在しない**（旧軸
    スケール 0.664 の導出値で、テンプレートの note 自身が「肉厚 0.74mm で
    min_wall を割る」と否定している）。理由の消えた追従。
    """
    reg = get_registry().get("saxophone")
    dead = 0
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        specs = {s.key: s for s in comp.param_specs()}
        for key, partner in (("body_dia", "シャンク径"),
                             ("shank_dia", "ボア径")):
            spec = specs[key]
            for edge in (spec.min, spec.max):
                # 帯の端は**壁の内側**なので、まずクランプされない
                v, rep = spec.validate_report(edge)
                assert v == pytest.approx(edge) and rep is None, (tid, key)
                err = comp.params_error(dict(base, **{key: edge}))
                if err is None:
                    continue
                dead += 1
                assert partner in err or "最大径" in err, (tid, key, edge, err)
    assert dead == 6, dead


def test_the_heel_floor_is_a_stated_wall_not_a_silent_clamp():
    """**踵の床を黙ったクランプから壁へ（Phase B-4a、8 例目）。**

    `heel_z` は `max(heel_raw, 0.30·全長)` で床を持つ。掃引は
    `shank_length` を 110mm まで、`shoulder_ratio` を 2.45 まで素通りさせ、
    段 1〜3 が全部 ok を返した —— **形は床から先で 1 ビットも動かないのに**。
    寸法図と仕様書は与えた数字を印字し続けるので、図と形が食い違う。

    ここで見るのは 3 つ: 壁の内側では踵が式どおり動くこと、床の外は理由つきで
    断られること、そして**断らなければ形が凍っていたこと**（＝ 壁の必要性）。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        specs = {s.key: s for s in comp.param_specs()}
        for key, step in (("shank_length", 0.5), ("shoulder_ratio", 0.005)):
            wall = specs[key].hard_max
            assert wall is not None and wall > specs[key].max, (tid, key)
            assert comp.params_error(dict(base, **{key: wall})) is None, (tid, key)
            # 壁の内側では踵が床ではなく式で決まる
            p_wall = dict(base, **{key: wall})
            assert profiles.heel_raw(p_wall) > profiles.heel_floor(p_wall), tid
            assert profiles.heel_z(p_wall) == pytest.approx(
                profiles.heel_raw(p_wall)), (tid, key)
            # 床の外は理由つきで断る
            cross = (profiles.shank_length_at_heel_floor(base)
                     if key == "shank_length"
                     else profiles.shoulder_ratio_at_heel_floor(base))
            assert wall < cross, (tid, key, wall, cross)     # 掛け金は 1 段内側
            over = round(cross + 2 * step, 4)
            err = comp.params_error(dict(base, **{key: over}))
            assert err is not None and "食い尽くし" in err, (tid, key, err)
            # 断らなかったら踵が凍っていた（壁の必要性そのもの）
            a = dict(base, **{key: over})
            b = dict(base, **{key: round(over + 10 * step, 4)})
            assert profiles.heel_z(a) == pytest.approx(profiles.heel_z(b)), tid
            # **凍り方は 2 本で違う。** `shank_length` は外形まで丸ごと凍る
            # （踵も肩の長さも動かない）。`shoulder_ratio` は踵が凍っても
            # 肩の長さ ＝ 比 × 踵 が伸び続けるので母線は変わる —— それでも
            # 「最大径位置に対する比」という**この量の意味が成り立たない**
            # ので壁にした。掃引の応答が 0% にならなかったのはこのため。
            z = 0.6 * base["overall_length"]
            same = profiles.outer_radius(a, z) == pytest.approx(
                profiles.outer_radius(b, z))
            assert same == (key == "shank_length"), (tid, key)
        # **2 本の壁は互いに「相手が既定のとき」の値**（ブラウザで踏んだ）。
        # 床は 2 本の組で決まるので、両方を壁へ置くと当然その先へ出る ——
        # 掛け金は静的な数字なのでそれを表せない。径 2 本とまったく同じ形で、
        # 断るときに理由が出ることだけを確かめる（黙って丸めない）。
        both = dict(base, shank_length=specs["shank_length"].hard_max,
                    shoulder_ratio=specs["shoulder_ratio"].hard_max)
        err = comp.params_error(both)
        assert err is not None and "食い尽くし" in err, (tid, err)


def test_a_shoulder_ratio_of_minus_one_is_refused_before_the_division():
    """**踵の分母が 0 になる点を素の例外にしない（B-4a、割り算 7 例目）。**

    掃引が `shoulder_ratio` を下へ歩いて −1 ちょうどで
    `ZeroDivisionError: float division by zero` を踏んだ。手前（−0.99）は
    段 1〜2 を素通りして**段 3 でソリッドが 2〜3 個**に割れる。

    帯の下限 0.02 があるので UI からは届かないが、**出所の分からない例外が
    上がるのがいちばん悪い**ので理由を返すようにした。下限は広げない ——
    負の肩比は形の意味を持たない。
    """
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    base = {s.key: s.default for s in comp.param_specs()}
    spec = next(s for s in comp.param_specs() if s.key == "shoulder_ratio")
    assert spec.hard_min is None and spec.min == pytest.approx(0.02)
    for v in (-1.0, -1.5):
        p = dict(base, shoulder_ratio=v)
        err = comp.params_error(p)                       # 例外ではなく理由
        assert err is not None and "−1 以下" in err, (v, err)
        assert math.isfinite(profiles.heel_z(p))         # 呼んでも落ちない
    # 帯の下限そのものは通る
    assert comp.params_error(dict(base, shoulder_ratio=spec.min)) is None


def test_the_sweeper_says_when_the_band_edge_itself_fails():
    """**掃引器が「効いていない」と「壁がある」を取り違えないこと（B-4a）。**

    `_walk` は帯の端を起点に外へ歩くだけなので、初版は 2 つの別の話を同じ
    「形が動かない ＝ この向きでは効いていない」にまとめていた:

      (a) 1 段目で `params_error` に弾かれた（＝ すぐ外に壁がある）
      (b) 歩けたのに指紋が変わらない（＝ 本当に効いていない）

    さらに**帯の端そのもの**は一度も試していなかった。`shank_dia` の帯の
    下端 14.0 はアルト（ボア 15.8）でその端自体が通らないのに、ログには
    「1 段外で壁」としか出なかった。道具が測った理由を捨てるのは、測って
    いないのと同じ。
    """
    sw = _sweeper()
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    base = {s.key: s.default for s in comp.param_specs()}
    specs = {s.key: s for s in comp.param_specs()}
    grids = sw._grids(base)

    # (a) 帯の端そのものが通らない
    edge = dict(base, shank_dia=specs["shank_dia"].min)
    assert sw._cheap_ok(comp, edge) is not None
    # (b) 端が通る向きは歩けて、止まった理由が残る
    top = dict(base, shank_dia=specs["shank_dia"].max)
    assert sw._cheap_ok(comp, top) is None
    last, why, live = sw._walk(comp, top, "shank_dia", 0.1, +1, grids, steps=40)
    assert live is not None and last == pytest.approx(base["body_dia"], abs=0.1)
    assert "最大径" in why, why
    # (c) 1 段目で弾かれると `last` は起点のまま ＝ すぐ外が壁
    near = dict(base, shank_dia=round(base["bore_dia"] + 0.1, 2))
    last2, why2, live2 = sw._walk(comp, near, "shank_dia", 0.1, -1, grids,
                                  steps=40)
    assert live2 is None and last2 == pytest.approx(near["shank_dia"])
    assert "ボア径" in why2, why2
    # 注意の件数は**部品に聞く**（`cavity_warnings` を直に数えない）
    thin = dict(base, shank_dia=round(base["bore_dia"] + 1.0, 2))
    assert len(profiles.cavity_warnings(thin)) < len(comp.warnings(thin))


def test_the_apex_is_a_claim_the_formula_can_never_check():
    """**「最大径は踵」は主張であって計算結果ではない（Phase B-4b）。**

    `heel_z` は (全長 − シャンク長)/(1 + 肩比) という**軸方向の式**なので、
    形を歪める 2 本では定義上 1 ビットも動かない ——つまり `heel_z` を見張って
    いる限り、この 2 本が頂点を壊しても**永久に検出できない**。
    `cad/windycity/sweep_outer.py` の主張 (1) は B-4b までそれだった。

    ここで固定するのは 3 つ:
      1. 壁の内側では形の頂点（`outer_apex`）が踵と一致する
      2. 壁の 1 段外では**一致しなくなる**（形が壊れている）
      3. そのあいだ `heel_z` は**どちらでも動かない**（古い目が盲だった証拠）
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        specs = {s.key: s for s in comp.param_specs()}
        heel = profiles.heel_z(base)
        for key in ("body_waist", "shoulder_fullness"):
            spec = specs[key]
            for edge, out in ((spec.hard_min, spec.hard_min - spec.step),
                              (spec.hard_max, spec.hard_max + spec.step)):
                inside = dict(base, **{key: edge})
                outside = dict(base, **{key: out})
                # (3) 式はどちらでも動かない
                assert profiles.heel_z(inside) == pytest.approx(heel)
                assert profiles.heel_z(outside) == pytest.approx(heel)
                # (1) 壁の内側では形が主張どおり
                az, _ = profiles.outer_apex(inside)
                _, dr = profiles.shoulder_dip(inside)
                assert az == pytest.approx(heel, abs=1e-3), (tid, key, edge)
                assert dr >= profiles.shank_radius(inside) - 1e-9, (tid, key)
                assert profiles.body_dip(inside)[1] == pytest.approx(0.0)
                assert profiles.shoulder_bulge(inside)[1] == pytest.approx(0.0)
                # (2) 1 段外では壊れる。**壊れ方は 4 通りあって、どの目も
                #     少なくとも 1 つを見落とす** ——頂点が移る（waist 上）、
                #     胴が凹む（waist 下）、肩がえぐれる（fullness 下）、
                #     肩が膨らむだけ（fullness 上。最大径は超えずシャンク径も
                #     割らないので `outer_apex` も `shoulder_dip` も無言）。
                #     主張そのものは 1 つ「母線は単調」で、それを見るのが
                #     `body_dip` と `shoulder_bulge`。
                az2, _ = profiles.outer_apex(outside)
                _, dr2 = profiles.shoulder_dip(outside)
                _, drop2 = profiles.body_dip(outside)
                _, bulge2 = profiles.shoulder_bulge(outside)
                broke = (abs(az2 - heel) > 1e-3
                         or dr2 < profiles.shank_radius(outside) - 1e-9
                         or drop2 > 1e-9 or bulge2 > 1e-9)
                assert broke, (tid, key, out, az2, dr2, drop2, bulge2)
                # 単調の 2 つは**必ず**どちらかが鳴る（症状の 2 つと違って）
                assert drop2 > 1e-9 or bulge2 > 1e-9, (tid, key, out)


def test_the_curve_walls_come_from_the_measured_profile_tables():
    """**壁の数字はどこにも書いていない（実測表から解く）。**

    `body_waist` / `shoulder_fullness` の限界は `r/r_max` に正規化した形の
    性質なので **3 サイズ共通・他のパラメータに依らない**。だから
    `profiles.*_limits()` が `_BODY_PROFILE` / `_SHOULDER_PROFILE` から解き、
    `mouthpiece._inside` が刻みへ寄せるだけ ——数字を書き写すと、表を
    差し替えたときに片方だけ古くなる（この設計で繰り返し出ている型）。

    **主張は 1 つ「母線は単調」** ——胴は最大径へ太る一方、肩はシャンクへ細る
    一方。肩では単調のほうが「値が [0,1] を出る」より先に破れる。
    """
    lo_w, hi_w = profiles.body_waist_limits()
    lo_k, hi_k = profiles.shoulder_fullness_limits()

    def apex_u(w):
        n = 4000
        best_u, best_r = 1.0, 1.0
        for i in range(n + 1):
            u = i / n
            r = (profiles._pchip(profiles._BODY_PROFILE, u)
                 * (1.0 + w * profiles._waist_bump(u)))
            if r > best_r:
                best_u, best_r = u, r
        return best_u

    # 別解法で答え合わせ（閉じた式ではなく素の走査）
    assert apex_u(hi_w - 1e-4) == pytest.approx(1.0)
    assert apex_u(hi_w + 1e-3) < 0.999
    assert lo_w == pytest.approx(-0.161380, abs=1e-5)
    assert hi_w == pytest.approx(0.072572, abs=1e-5)
    assert lo_k == pytest.approx(-0.360730, abs=1e-5)
    assert hi_k == pytest.approx(1.863339, abs=1e-5)

    reg = get_registry().get("saxophone")
    walls = set()
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        specs = {s.key: s for s in comp.param_specs()}
        for key in ("body_waist", "shoulder_fullness"):
            sp = specs[key]
            walls.add((key, sp.hard_min, sp.hard_max))
            lo, hi = (lo_w, hi_w) if key == "body_waist" else (lo_k, hi_k)
            assert lo < sp.hard_min and sp.hard_max < hi, (tid, key)
    # 3 サイズで同じ壁（形の正規化量なのでサイズに依らない）
    assert len(walls) == 2, sorted(walls)


def test_the_shoulder_band_no_longer_crosses_its_own_wall():
    """**帯の下端 −1.0 は壁の外にあった（B-4b で発覚）。**

    B-4a の径 2 本は「相手で動く壁を静的な帯で表せない」ので端が届かなくて
    よかったが、こちらは**相手がいない**（形の正規化量だけで決まる）ので、
    帯が壁を跨いでいるのは端的に帯の欠陥。いまは 3 本とも帯の端が全部通る。

    −1.0 が何をしていたかも固定する ——肩の中ほど（s≈0.73）がシャンク径を
    下回る「えぐれ」で、しかも**えぐれは必ずボアの上に来る**ので
    `shank_warnings` が言う肉厚（シャンク径 − ボア径）が最薄でなくなる。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        specs = {s.key: s for s in comp.param_specs()}
        for key in ("body_waist", "shoulder_fullness", "beak_height"):
            sp = specs[key]
            assert sp.hard_min <= sp.min and sp.max <= sp.hard_max, (tid, key)
            for edge in (sp.min, sp.max):
                v, rep = sp.validate_report(edge)
                assert v == pytest.approx(edge) and rep is None, (tid, key)
                assert comp.params_error(dict(base, **{key: edge})) is None
        # 旧下端 −1.0 が壊していたもの
        old = dict(base, shoulder_fullness=-1.0)
        dz, dr = profiles.shoulder_dip(old)
        assert dr < profiles.shank_radius(old) - 1e-3, tid
        assert dz >= profiles.bore_start_z(old), tid
        # 壁の外なので、いまは丸められて**壁だと名乗る**
        v, rep = specs["shoulder_fullness"].validate_report(-1.0)
        assert v == pytest.approx(specs["shoulder_fullness"].hard_min)
        assert rep is not None and rep["at"] == "wall"


def test_the_beak_height_wall_is_where_the_number_stops_describing_the_part():
    """**`beak_height` の壁は「壊れる点」ではなく「定義が壊れる点」（B-4b）。**

    定義は「バイトポイントでのテーブル面からの高さ ＝ 口の開き量」。稜線が
    そこで胴の頂点を越えると、上面は胴のままになって**与えた数字が部品の
    どこにも現れない**。旧コメントはそこを「胴の全高 0.9·body_dia」と書いて
    いたが、実測は 0.72〜0.75·body_dia で、**比は一定ですらない**
    （旧レンジの上端 0.75 倍は 3 サイズとも壁の外だった）。

    OCCT が割れるのは 0.5mm で、壁（4.5 / 5.5 / 6.0）のずっと下。
    掃引器の「−21.2mm まで通る」は段 1〜2 の打ち切りで、そこを
    「割れる点」と読むと嘘になる。
    """
    reg = get_registry().get("saxophone")
    ratios = set()
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        base = {s.key: s.default for s in comp.param_specs()}
        sp = next(s for s in comp.param_specs() if s.key == "beak_height")
        z_bite = profiles._BEAK_BITE * base["overall_length"]
        top = profiles.beak_height_at_body_top(base)
        flat = profiles.beak_height_flat(base)
        ratios.add(round(top / base["body_dia"], 3))
        # 壁は両方とも landmark の内側、刻み 0.5 の格子に乗る
        assert flat < sp.hard_min <= sp.min, tid
        assert sp.max == sp.hard_max < top, tid
        assert sp.hard_max % 0.5 == pytest.approx(0.0), tid
        # 壁の内側では稜線が胴の中、1 段外では外へ出て切除が効かない
        inside = dict(base, beak_height=sp.hard_max)
        outside = dict(base, beak_height=sp.hard_max + sp.step)
        assert (profiles.beak_y(inside, z_bite)
                <= profiles.outer_radius(inside, z_bite) + 1e-9), tid
        assert (profiles.beak_y(outside, z_bite)
                > profiles.outer_radius(outside, z_bite)), tid
        # 下側は「稜線が前下がり」——壁ではまだ上向き、下れば負になる
        assert profiles.beak_angle(dict(base, beak_height=sp.hard_min)) > 0.0
        below = dict(base, beak_height=sp.hard_min - 2.0 * sp.step)
        assert profiles.beak_angle(below) < 0.0, tid
        # 旧レンジの上端 0.75 倍は壁の外だった
        assert round(0.75 * base["body_dia"], 1) > sp.hard_max, tid
        # **この壁は「関係」**（B-3・B-4a と同じ型）——`hard_*` はテンプレート
        # 値での掛け金でしかなく、相手を動かせば壁も動く。だから成立条件は
        # `outer_layout_error` が 1 か所で持つ。
        wide = dict(base, body_dia=base["body_dia"] + 6.0)
        assert profiles.beak_height_at_body_top(wide) > top + 3.0, tid
        assert comp.params_error(dict(base, beak_height=sp.hard_max + sp.step))
        assert comp.params_error(dict(wide, beak_height=sp.hard_max
                                      + sp.step)) is None, tid
    # **比は一定ではない**（0.9 という単一の数字では書けない）
    assert len(ratios) == 3, sorted(ratios)


def test_the_beak_axis_measures_the_part_not_the_formula():
    """**掃引器の `beak_y` 軸が式を測っていた（B-4b で直した）。**

    `pf.beak_y` はビーク稜線の解析式で、稜線が胴の外へ出ても線形に伸び続ける。
    部品の上面は `min(稜線, 外半径)` なので、そこから先は形が動かない。
    直す前は `beak_height` を既定の 4 倍まで上げても「100% 生きている」と
    報告していた。`sweep_outer.py` の主張 (1) と**同じ型の盲目**。

    既定では稜線は胴の内側にあるので、この頭打ちは B-0〜B-4a の掃引には
    掛からない（`tip_opening` を回し直して committed ログと一致を確認済み。
    `docs/sweeps/b4b-outer-curves.txt` の §3）。
    """
    import importlib.util
    spec_f = importlib.util.spec_from_file_location(
        "sweep_limits", "cad/windycity/sweep_limits.py")
    sw = importlib.util.module_from_spec(spec_f)
    spec_f.loader.exec_module(sw)

    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    base = {s.key: s.default for s in comp.param_specs()}
    grids = sw._grids(base)
    lim = base["overall_length"] - 1e-6
    # 既定では頭打ちは効かない（＝過去の掃引と比較できる）
    axes = sw._axes(base, grids)
    raw = tuple(profiles.beak_y(base, min(z, lim)) for z in grids["outer"])
    assert axes["beak_y"] == raw
    # 稜線が胴の外へ出る高さでは、式と形が食い違う
    high = dict(base, beak_height=3.0 * base["body_dia"])
    axes_h = sw._axes(high, grids)
    raw_h = tuple(profiles.beak_y(high, min(z, lim)) for z in grids["outer"])
    assert axes_h["beak_y"] != raw_h
    assert all(a <= b + 1e-12 for a, b in zip(axes_h["beak_y"], raw_h))


def test_reed_and_spec_use_the_window_that_exists():
    """リード適合と仕様書は**実際に開く窓**を見ること。

    リードのヴァンプは「窓に届いているか」で判定する。相手は形であって
    スライダの値ではないので、頭打ちのときに指定値と比べると、存在しない窓に
    対して合格／不合格を出すことになる。仕様書も同じ理由で実効値を書く
    （納品物に部品が持っていない寸法を載せない）。
    """
    reg = get_registry().get("saxophone")
    comp = reg.make_component("mouthpiece", "soprano")
    base = _template_params("mouthpiece", "soprano")
    wl_max = next(s.max for s in comp.param_specs() if s.key == "window_length")
    wide = dict(base, window_length=wl_max)
    eff = profiles.window_length_effective(wide)
    assert eff < wl_max - 1.0                     # このサイズは確実に頭打ちになる

    spec = comp.spec_extras(wide)
    row = next(v for k, v in spec["dimensions"] if k == "ウィンドウ長 × 窓幅")
    assert f"{eff:.1f}" in row and "届いていません" in row
    assert not row.startswith(f"{wl_max:.1f}")


def test_impossible_params_are_not_saved():
    """成立しない値は保存しないこと。保存するとセッションが戻せなくなる。

    `simulate` も `build` も同じ空洞から作るので、潰れた値を保存すると以後の
    描画が全部同じ理由で落ちる —— スライダーを戻すための画面ごと出せなくなる。
    """
    from saxsketch.server.state import STATE
    # ソプラノを使うのは、レンジを実測基準にした後も**スライダーだけで**到達
    # できる唯一のサイズだから（`test_slider_ranges_alone_cannot_close_the_hole`）。
    STATE.new_project("saxophone", "soprano", "mouthpiece")
    before = dict(STATE.paramset.values)
    specs = {s.key: s for s in STATE.component.param_specs()}
    with pytest.raises(ValueError, match="成立しません"):
        STATE.apply_params({"overall_length": specs["overall_length"].min,
                            "bore_length": specs["bore_length"].max})
    assert dict(STATE.paramset.values) == before      # 1 つも動いていない
    assert STATE.project.params == before             # 保存側も動いていない
    STATE.simulate()                                   # まだ描ける


# ------------------------------------------------------------------ ファイルダイアログ
# 「名前を付けて保存でダイアログが固まる」の再発防止。ダイアログは必ず別プロセスで
# 出し、切られたら殺す。ここでは**本物の窓を出さない**（バックエンドを差し替える）。

def _fake_dialog_backend(monkeypatch, *, script: str):
    """`filedialog` の子プロセスを、窓を出さない python に差し替える。"""
    import sys
    from saxsketch.server import filedialog
    monkeypatch.setattr(filedialog, "_backend_argv",
                        lambda mode, suggested: [sys.executable, "-c", script])


def test_dialog_always_returns_even_if_nobody_answers(monkeypatch):
    """誰も応答しなくても必ず返ること。

    ここが返らないと `POST /api/dialog` を待っている画面が固まる。以前は
    `asyncio.to_thread` で tkinter を呼んでいたため、閉じられるまで永久に待った。
    """
    import asyncio
    from saxsketch.server import filedialog
    _fake_dialog_backend(monkeypatch, script="import time; time.sleep(60)")
    path, reason = asyncio.run(filedialog.pick("save", "x.wproj", timeout=1.0))
    assert (path, reason) == (None, "timeout")


def test_cancelled_dialog_leaves_no_process(monkeypatch, tmp_path):
    """リクエストが切られたら子プロセスも死ぬこと。

    これが本丸。`asyncio.to_thread` は走り出したワーカーを中断できないので、
    ブラウザが切って `CancelledError` になってもダイアログの窓とスレッドは残り、
    押し直すたびに増えていた（実測: Windows 側の powershell.exe が積み上がる）。
    """
    import asyncio
    import sys
    from saxsketch.server import filedialog

    pidfile = tmp_path / "child.pid"
    script = (f"import os, time; open({str(pidfile)!r}, 'w').write(str(os.getpid()));"
              " time.sleep(60)")
    monkeypatch.setattr(filedialog, "_backend_argv",
                        lambda mode, suggested: [sys.executable, "-c", script])

    async def run():
        task = asyncio.create_task(filedialog.pick("open", timeout=60.0))
        for _ in range(200):                        # 子が名乗るまで最大 10 秒
            if pidfile.exists():
                break
            await asyncio.sleep(0.05)
        pid = int(pidfile.read_text())
        assert not _process_gone(pid), "子プロセスが起動していない"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        for _ in range(200):                        # 死ぬまで最大 10 秒
            if _process_gone(pid):
                # ゾンビも「終了」と数えているので、親（`_reap`）が回収して
                # パイプを閉じるまで一息置く。ここを待たずにループを畳むと
                # GC が閉じたループに触って PytestUnraisableExceptionWarning になる。
                await asyncio.sleep(0.3)
                return pid, True
            await asyncio.sleep(0.05)
        return pid, False

    pid, gone = asyncio.run(run())
    assert gone, f"キャンセル後も子プロセス {pid} が生きている"


def _process_gone(pid: int) -> bool:
    """終了済みか。**ゾンビも終了扱い**（親が回収する前に見ることがある）。

    **見る場所が OS で違う。** 以前は `/proc/<pid>/stat` だけを見ていたので、
    `/proc` の無い **Windows では常に「もう死んでいる」**を返していた。これを
    使う `test_cancelled_dialog_leaves_no_process` は
    **Windows で powershell.exe が積み上がるのを捕まえるために書いたテスト**
    なのに、その判定が Windows でだけ動かない —— 起動確認の assert で落ちて、
    肝心の「キャンセル後に死ぬか」まで一度も到達していなかった。

    **`os.kill(pid, 0)` は使ってはいけない。** Windows の `os.kill` は signal を
    見ずに `TerminateProcess` を呼ぶので、生存確認のつもりで相手を殺す。
    """
    import sys
    if sys.platform == "win32":
        import ctypes
        # 終了済みでもハンドルは開けるので、開けたかではなく**終了コード**で見る
        # （STILL_ACTIVE = 259）。実際に 259 で終わったプロセスは生存と誤るが、
        # ここの子は sleep か強制終了なのでその値は出ない。
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return True
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True
            return code.value != 259
        finally:
            k32.CloseHandle(h)
    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists():
        return True
    try:
        return stat.read_text().rsplit(") ", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return True


def test_dialog_backend_reports_cancel_and_pick(monkeypatch, tmp_path):
    """子プロセスの 1 行プロトコルを往復できること（日本語パスを含む）。"""
    import asyncio
    import base64
    from saxsketch.server import filedialog

    _fake_dialog_backend(monkeypatch, script="print('CANCEL')")
    assert asyncio.run(filedialog.pick("open")) == (None, "cancelled")

    picked = str(tmp_path / "アルト マウスピース.wproj")
    b64 = base64.b64encode(picked.encode("utf-8")).decode("ascii")
    _fake_dialog_backend(monkeypatch, script=f"print('OK {b64}')")
    path, reason = asyncio.run(filedialog.pick("save", "x.wproj"))
    assert reason == "ok"
    assert path.endswith("アルト マウスピース.wproj")


def test_powershell_dialog_script_parses(tmp_path):
    """生成した PowerShell が 4 モードとも構文として通ること。

    日本語のタイトル・フィルタと `C:\\` を含むパスが、WSL の exec 境界・
    PowerShell のパーサ・埋め込み C#（`Add-Type -MemberDefinition`）の 3 層を
    通る。ここは目視では守れないので、実物のパーサに読ませて確かめる。
    """
    import subprocess
    from saxsketch.server import filedialog, hostenv

    exe = hostenv.powershell_exe()
    if exe is None:
        pytest.skip("PowerShell が無い環境")

    for mode in filedialog.MODES:
        script = filedialog._ps_script(mode, str(tmp_path / "テスト.wproj"))
        f = tmp_path / f"{mode}.ps1"
        f.write_text(script, encoding="utf-8")
        win = hostenv.to_win_path(str(f))
        out = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command",
             f"[void][ScriptBlock]::Create("
             f"(Get-Content -Raw -Encoding UTF8 '{win}')); 'PARSE_OK'"],
            capture_output=True, timeout=90)
        assert b"PARSE_OK" in out.stdout, (
            f"{mode}: {out.stdout[-400:]!r} {out.stderr[-400:]!r}")


def test_remote_client_gets_no_native_dialog():
    """サーバから離れた画面には、OS のダイアログを出さないと申告すること。

    出しても**サーバの机の前**に現れるだけで、利用者からは無反応に見える。
    ループバック以外は「誰も見ていない」とみなす。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server import filedialog
    from saxsketch.server.app import app

    local = TestClient(app, client=("127.0.0.1", 51000))
    remote = TestClient(app, client=("192.168.1.50", 51000))
    # ローカルは「この環境で出せるか」がそのまま出る（CI にはどちらも無い）
    assert (local.get("/api/capabilities").json()["native_dialogs"]
            is filedialog.available())
    assert remote.get("/api/capabilities").json()["native_dialogs"] is False
    # 直接叩かれてもダイアログは開かない（開くと誰も閉じられない）
    assert remote.post("/api/dialog", json={"mode": "save"}).json() == {
        "path": None, "reason": "unavailable"}


def test_settings_live_outside_the_user_home():
    """テストが実ユーザーの設定を書き換えないこと。

    以前は `~/.saxsketch/settings.json` を直接触っていて、「最近使ったプロジェクト」
    が pytest の一時ディレクトリ 10 件で埋まっていた（実際に起きた）。
    """
    import os
    from saxsketch.server import state
    assert os.environ.get("SAXSKETCH_HOME")
    assert state.settings_dir() == Path(os.environ["SAXSKETCH_HOME"])
    assert Path.home() / ".saxsketch" != state.settings_dir()


def test_legacy_export_root_is_migrated_once(tmp_path, monkeypatch):
    """旧版が書いた出力先は一度だけ捨て、選び直した値は残ること。

    WSL では旧既定 `~/Documents/SaxSketch` は Windows から辿れない場所だが、
    そのフォルダは書き出した結果**実在する**ので「実在しなければ捨てる」では
    条件が成立しない。かといって値の一致だけで毎回捨てると、同じ場所を自分で
    選び直した設定が永久に保存できなくなる。だから版で一度きりにする。
    """
    import json as _json
    from saxsketch.server import state as st

    monkeypatch.setenv("SAXSKETCH_HOME", str(tmp_path))
    monkeypatch.setattr(st, "IS_WSL", True)
    legacy = str(st._LEGACY_EXPORT_ROOT)

    # 版 1（= 版キーが無い）の設定を読むと捨てられる
    (tmp_path / "settings.json").write_text(
        _json.dumps({"export_root": legacy}), encoding="utf-8")
    assert st.AppState._load_settings(None)["export_root"] == ""

    # 版 2 として保存された同じ値は尊重される（利用者が選び直した場合）
    (tmp_path / "settings.json").write_text(
        _json.dumps({"export_root": legacy, "settings_version": 2}), encoding="utf-8")
    assert st.AppState._load_settings(None)["export_root"] == legacy


def test_recent_projects_drop_paths_that_vanished(tmp_path):
    """消えたプロジェクトは保存側でも落ちること。

    `/api/recent` は表示時に濾していたが保存側が素通しだったので、一度混ざった
    ゴミが 10 件の枠を占めたまま残り、実際に開いたものを押し出していた。
    """
    from saxsketch.server.state import STATE
    alive = tmp_path / "alive.wproj"
    alive.write_text("{}", encoding="utf-8")
    before = list(STATE.settings.get("recent_projects", []))
    try:
        STATE.settings["recent_projects"] = [str(tmp_path / "gone.wproj")]
        STATE.push_recent(str(alive))
        assert STATE.settings["recent_projects"] == [str(alive)]
    finally:
        STATE.settings["recent_projects"] = before


def test_template_values_survive_the_schema_unclamped():
    """テンプレートに書いた数値がスキーマ範囲で黙って書き換えられないこと。

    `ParamSpec.validate` は範囲外を**例外にせずクランプする**（`core/schema.py`）。
    つまりレンジの下限が実物より上にあると、テンプレートに実測値を書いても
    モデルは別の形を作り、どこにも警告が出ない。Stage F でソプラノを実測へ
    差し替えたとき、`shank_dia` 18.67（下限 16.0 は満たす）は通ったが、
    軸を実測比で縮めた最初の版の 15.28 は 16.0 へ化けていた。数字が黙って
    変わる経路は、実測を入れる作業そのものを無効にする。
    """
    from saxsketch.core.schema import ParamSet
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        for cid in ("mouthpiece", "reed", "ligature", "neck", "body"):
            comp = reg.make_component(cid, tid)
            specs = {s.key: s for s in comp.param_specs()}
            applied = ParamSet(comp.param_specs(), comp.template.get(cid, {})).values
            for k, raw in comp.template.get(cid, {}).items():
                if k not in specs or not isinstance(raw, (int, float)):
                    continue
                assert float(applied[k]) == pytest.approx(float(raw), abs=1e-9), (
                    tid, cid, k, raw, applied[k],
                    f"レンジ [{specs[k].min}, {specs[k].max}] にクランプされた")


def test_beak_taper_spans_body():
    """ビークがティップからブレンド終端まで本体を切り続けること。

    ビーク面を直線にしていたときは、`beak_height` が胴の全高に近い既定値だったため
    全長の 1/4 で外形を追い越し、テーパが消えてただの円筒になっていた。
    同時に空洞天井の clamp（`beak_y - min_wall`）まで無効化されていた。

    実測のビークは胴へ**溶けて終わる**（`beak_blend_end_z` ≒ 0.386·L、実測 34.2→41.5mm）。
    そこから後ろは定義上 `beak_y == outer_radius` になるので、旧アサートの
    「0.5·L まで切り続けろ」は直線ビーク時代の前提。バイトポイント（0.25·L）より
    十分後ろまで切っていることを、ブレンド終端そのもので見る。
    """
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        L = p["overall_length"]
        z_end = profiles.beak_blend_end_z(p)
        assert z_end > 0.30 * L, (tid, z_end / L)     # バイトポイント(0.25L)より後ろ
        for t in (0.0, 0.2, 0.4, 0.6, 0.8, 0.95):
            z = t * z_end
            assert profiles.beak_y(p, z) < profiles.outer_radius(p, z), (tid, t)
        # 終端では胴と一致する（そこから後ろは切らない）
        assert profiles.beak_y(p, z_end) == pytest.approx(
            profiles.outer_radius(p, z_end), abs=1e-6), tid
        # 単調に立ち上がる（くさび→バイトポイント→ショルダー）
        ys = [profiles.beak_y(p, t * L) for t in (0.0, 0.15, 0.3, 0.45)]
        assert all(a < b for a, b in zip(ys, ys[1:])), (tid, ys)


#: ソプラノで「テーブル平坦部の終端 < リード全長」になる長いリードの食み出し [mm]。
#:
#: Stage F はここに `SOPRANO_TABLE_SHORTFALL_MM = 3.5` を置き、原因の候補を 3 つ
#: 並べていた。**候補 ①「`reed_std_length_mm = 63.5` が違う」が当たった。**
#: 実測（2026-08-11）はバンドーレン 3番（ケーン）**59.1** / レジェール アメリカン
#: カット（樹脂）**62.0** で、63.5 はどちらからも 1.5mm 以上外れていた。ちょうど
#: 2.5 インチの丸い値で、サイズ別の出所が descriptor に無かったのがそのまま答え。
#:
#: 残るのは**銘柄差そのもの**。テーブル終端 60.0 はケーンの 59.1 を 0.9mm 上回るが、
#: 樹脂の 62.0 には 2.0mm 足りない。**実物のテーブル終端を測ったら 60.2mm だった**
#: （ヤナギサワ 刻印 4、2026-08-13。モデルの導出値 60.00 と 0.2mm 差）。つまり
#: この「軽微」はモデルの粗さではなく**実物の性質**で、長いリードの踵は実際に
#: 1.8mm はみ出す。踵の数 mm はリガチャー座（〜57.1）の外側で密着させる必要が
#: 無いため、`reference_check` はここを「軽微」に留める。
SOPRANO_LONG_REED_OVERHANG_MM = 2.0

#: ソプラノのテーブル平坦部の終端 [mm]（先端から）。**実測**（2026-08-13）。
#: モデルは 60.00 を実測を見ずに解いている（傾斜テーブル 4.18° ＋「ティップが
#: z=0 に立つ」）。`body_dia` を 22→28mm 振っても 0.4mm しか動かないので、
#: この一致が効いているのは `table_angle` と `tip_opening`。0.2mm の差は
#: `tip_opening` に直すと 0.12mm 相当なので、**未確認だったチャート値 1.95 が
#: ±0.12mm で追認された**ことになる。過剰適合になるので値は動かさない。
SOPRANO_TABLE_END_MEASURED_MM = 60.2


def test_table_reaches_reed_heel():
    """テーブル平面がリード踵より後ろまで届くこと。

    外形プロファイルのリガチャー座を動かしたとき、テーブル終端の比率リテラルを
    置き忘れてリードの後端 20mm が宙に浮いていた。比率は profiles が単独で持つ。

    **硬い不変条件はリガチャー座の側**。締める範囲が全部平坦であることは外部
    データを要らない自己整合で、全サイズで成り立たなければならない。リードとの
    比較は外部データなので、**リード全長が実測されているサイズだけ**で見る ——
    未実測の 1 点は位置が数 mm 分からず（ソプラノで同じ出所の 63.5 が実測
    59.1/62.0 から 4.4mm 外れた実績）、1mm 級の不足を「浮いている」と呼ぶ根拠が無い。
    """
    from saxsketch.instruments.saxophone.components import reference_check
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        seat_end = profiles.ligature_seat_range(p)[1]
        # 自己整合: 座の後端まで平坦であること。20mm 級の取り違えはここで落ちる。
        assert profiles.table_cut_end_z(p) >= seat_end - 0.05, tid
        heel, longest = reference_check.reed_length_range(_size_info(tid))
        if not reference_check.reed_length_is_measured(_size_info(tid)):
            continue
        assert profiles.table_cut_end_z(p) > heel, tid
        # 踵の直前はフェイシングの持ち上がりがゼロ＝素のテーブル平面そのもの。
        # 比較先は `table_y`（座中央の 1 点）ではなく **その z のテーブル平面**。
        # テーブルは軸に 4.18° 傾いているので単一の Y では表せない。
        assert profiles.cut_top_y(p, heel - 1.0) == pytest.approx(
            profiles.table_plane_y(p, heel - 1.0)), tid
        if tid == "soprano":
            # 記録値。実物のテーブル終端は 60.2mm（実測）で、モデルの 60.00 とは
            # 0.2mm 差。この「はみ出し」は実物にも在る。
            assert longest - profiles.table_cut_end_z(p) == pytest.approx(
                SOPRANO_LONG_REED_OVERHANG_MM, abs=0.5), tid
            assert profiles.table_cut_end_z(p) == pytest.approx(
                SOPRANO_TABLE_END_MEASURED_MM, abs=0.5), tid


#: アルトのテーブル平坦部の終端 [mm]。**実測ではなく実測から出る量**
#: （最大径の位置 21.4・シャンク径・傾斜テーブルの構成式）。どの実測にも直接は
#: 現れない。**2026-09-05 に 73.0 → 73.87 へ動いた** —— `shank_dia` が
#: 21.08（テナーからの径比）から実測 23.20 になり、肩の段差が半径 4.01 → 2.95mm と
#: 浅くなったため。テーブルの構成式は変えていない。
ALTO_TABLE_END_MM = 73.87

#: 同じ終端を、`shank_length` を借り物（テナー比 0.1628 × 全長 = 14.93）へ
#: 戻したときの値 [mm]。差 2.57mm が退行の検出量。
ALTO_TABLE_END_BORROWED_MM = 71.30


def test_alto_needed_both_measurements_to_stay_in_spec():
    """片方の実測だけでは実在しない不足を記録してしまうこと。

    2026-08-15 にアルトの実測が 2 件同時に届いた（最大径の位置 21.4 / リード全長
    70.2〜71.1）。**リード側だけを入れると**テーブル終端 70.3 が域の上端に 0.8mm
    足りず「軽微」が出る。だがこれは実在しない不足で、原因はモデルのテーブルでは
    なく**テナーから借りたシャンク比**のほう —— 踵を 2.9mm 手前に置いていた。
    最大径の位置が入ると終端は 73.0 になり「一致」へ戻る。

    ここが warn に戻ったら `shank_length` が借り物へ差し戻された疑いがある。
    未実測の借り物が判定を汚す 3 例目（コルク帯 26.0→33.7、挿し込み限界
    33.7→27.1 に続く）を、逆戻りしないように固定する。

    **2026-09-05: その warn による検出は効かなくなった。**
    `shank_dia` が借り物 21.08 から実測 23.20 になって肩の段差が浅くなり、
    テーブル終端が 73.04 → **73.87** へ後退した。借り物へ戻したときの終端も
    70.31 → **71.30** に上がり、リード上端 71.10 を **0.20mm 上回る**ので
    **もう warn が出ない**。元の余裕が 0.79mm しか無かったところへ、
    **まったく別の量の実測が 0.83mm 押した**だけで検出器が沈黙した。

    だから残す検出量は warn ではなく**終端の落ち込み**（借り物にすると 2.57mm
    手前に来る）にする。**warn が出なくなったこと自体も固定する** ——
    黙って消すと「昔から出ていなかった」と読めてしまう。
    """
    from saxsketch.instruments.saxophone.components import reference_check
    si = _size_info("alto")
    p = _template_params("mouthpiece", "alto")
    assert reference_check.reed_length_is_measured(si)
    _, reed_hi = reference_check.reed_length_range(si)

    assert profiles.table_cut_end_z(p) == pytest.approx(ALTO_TABLE_END_MM, abs=0.1)
    assert profiles.table_cut_end_z(p) > reed_hi
    assert reference_check.mouthpiece_card(p, si)["status"] == "ok"

    # 借り物（テナー比 0.1628 × 全長 91.7 = 14.93）に戻すと終端が 2.57mm 手前へ来る。
    # **これが退行の検出量**。card の status では、もう分かれない（docstring）。
    borrowed = dict(p, shank_length=14.93)
    assert profiles.table_cut_end_z(borrowed) == pytest.approx(
        ALTO_TABLE_END_BORROWED_MM, abs=0.1)
    assert profiles.table_cut_end_z(p) - profiles.table_cut_end_z(borrowed) ==         pytest.approx(ALTO_TABLE_END_MM - ALTO_TABLE_END_BORROWED_MM, abs=0.1)

    # **検出器が沈黙したことを固定する。** 借り物でもリード上端をわずかに超えるので
    # warn が出ない。余裕は 0.20mm しかなく、**次の実測でまた裏返りうる**。
    assert profiles.table_cut_end_z(borrowed) > reed_hi
    assert profiles.table_cut_end_z(borrowed) - reed_hi < 0.3
    assert reference_check.mouthpiece_card(borrowed, si)["status"] == "ok"


def test_bore_clears_corked_tenon():
    """ボアがコルクを巻いたテノンに嵌まること。

    以前は bore_dia がテノン外径そのものだった。コルク分の隙間が無く、実物の
    ネックには物理的に入らないマウスピースが出ていた。照合カードもテノン外径と
    直接比べて「一致」と言っていたので誤りが固定されていた。

    それを直した後も、しきい値は「コルク込み外径以上」（`need - 0.05`）のままだった。
    実物は逆に**少し細い** — コルクは圧縮して食いつくので、隙間があると抜ける。
    ネックとマウスピースの両方を実測してある唯一のサイズがテナーで、その差 0.2mm が
    `INTERFERENCE_FIT_MM`（自由状態のコルク込み 17.2 に対し実測ボア 17.0）。
    """
    from saxsketch.instruments.saxophone.components import reference_check
    for tid in SIZES:
        si = _size_info(tid)
        p = _template_params("mouthpiece", tid)
        aim = reference_check.nominal_bore_dia(si)
        assert aim == pytest.approx(si["neck_tenon_od_mm"]
                                    + 2.0 * si["neck_cork_thickness_mm"]
                                    - reference_check.INTERFERENCE_FIT_MM)
        assert p["bore_dia"] == pytest.approx(
            aim, abs=reference_check.BORE_TOL), (tid, p["bore_dia"], aim)
        # ネックの 3 値は実測で、導出規則で埋めていないこと。以前は「管肉厚 0.4mm」を
        # 仮定して内径をテノン外径から引いていたが、実測の肉厚は 0.90〜1.25mm だった。
        assert "neck_dimensions_source" in si, tid
        wall = (si["neck_tenon_od_mm"] - si["neck_bore_id_mm"]) / 2.0
        assert 0.5 < wall < 1.5, (tid, wall)
        # 外壁の肉厚が残ること
        assert p["body_dia"] / 2.0 - p["bore_dia"] / 2.0 > p["min_wall"], tid


def test_undersized_bore_is_rejected_not_excused():
    """小さすぎるボアを「軽微」で済ませないこと。

    判定は非対称。大きすぎればコルクが潰れて収まるが、小さいと挿さらない。
    """
    from saxsketch.instruments.saxophone.components import reference_check
    si = _size_info("alto")
    p = dict(_template_params("mouthpiece", "alto"),
             bore_dia=reference_check.required_bore_dia(si) - 0.6)
    card = reference_check.mouthpiece_card(p, si)
    assert card["status"] == "bad", card["rows"]
    # 同じだけ大きい側は挿さるので bad にはしない
    p2 = dict(p, bore_dia=reference_check.required_bore_dia(si) + 0.6)
    assert reference_check.mouthpiece_card(p2, si)["status"] != "bad"


#: 「リガチャー座の後端（＝最大径）に踵が来る」を各サイズで測った量 [mm]。
#: `seat1 − リード全長`。**これは設計則ではなく観測。** 記録値であって合格の証ではない。
#:
#: Stage B.1 はこれを設計則として使い、テナー実測 × リード規格長比で soprano/alto の
#: 全長を作った。Stage F でソプラノの実物が 71.4mm（18% 短い）と分かって崩れ、
#: Stage G でリード実測が入って**符号が反転する**ことがはっきりした:
#:
#:   - tenor  +1.0 … 座の後端が踵より 1.0mm 後ろ（実測マウスピース × 未実測リード）
#:   - soprano −2.0（ケーン 59.1）〜 −4.9（樹脂 62.0）… **踵が座の後端より後ろへ出る**
#:   - alto   −0.8〜+0.1 … **ほぼ 0**（マウスピースもリードも実測、2026-08-15）
#:
#: **アルトだけが「実測マウスピース × 実測リード」の組**で、そこでは差がほぼ 0 に
#: なる。ただしこれを設計則の証拠と読んではいけない —— ソプラノも同じく両方実測で、
#: そちらは −2.0〜−4.9 と大きく外れる。正のままなのはテナーだけで、そのテナーは
#: リードが未実測の代表値。
#:
#: この行は途中で 2 度動いた。B.1 のスケール値（全長 98.54mm）では +0.9、Stage I で
#: 実物 PHROX（91.7mm）に替えて −4.1、最大径の位置を実測して踵が 2.9mm 後ろへ
#: 動いて −0.8〜+0.1。**借り物の定数が入っているあいだは符号すら当てにならない。**
#: 判定はこの等値では出さず、`reference_check` の 2 本（テーブル終端 vs 座の後端 /
#: vs リード全長域）が持つ。後者はリード全長が実測のサイズでしか判定しない。
SEAT_MINUS_REED_MM = {"soprano": (-4.9, -2.0), "alto": (-0.80, 0.10), "tenor": (1.02, 1.02)}

#: 最大径の位置（シャンク端から）[mm]。**ノギスでの実測**。
#: soprano ヤナギサワ刻印4（2026-08-10）/ alto Wood Stone PHROX（2026-08-15）。
#: テナーは基準の WindyCity を STEP から測ってあり、テンプレートがその値そのもの。
MAX_DIA_FROM_SHANK_MM = {"soprano": 14.3, "alto": 21.4}


def test_ligature_seat_matches_reed_heel():
    """座の後端と踵の位置関係を記録する（判定はしない。上の定数を見ること）。"""
    from saxsketch.instruments.saxophone.components import reference_check
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        _, seat1 = profiles.ligature_seat_range(p)
        reed_lo, reed_hi = reference_check.reed_length_range(_size_info(tid))
        want_lo, want_hi = SEAT_MINUS_REED_MM[tid]
        assert seat1 - reed_hi == pytest.approx(want_lo, abs=0.5), (tid, seat1)
        assert seat1 - reed_lo == pytest.approx(want_hi, abs=0.5), (tid, seat1)


def test_max_diameter_position_matches_the_caliper():
    """最大径の位置が実測に一致すること（実測してあるサイズ）。

    `heel_z` は最大径＝リード踵＝テーブル平面が胴に接する z で、外形・リガチャー座・
    `table_cut_end_z` が全部ここに乗る。実測は「シャンク端から」なので全長から引く。

    **`shank_length` はここからの逆算でしか決まらない。** 実測 1 点では
    `shank_length` と `shoulder_ratio` の組が一意にならないので（`profiles` の
    `_SHOULDER_RATIO` のコメント）、比を固定して長さの側を解いている。ここが動いたら
    実測を書き換えたということなので、テンプレート側を疑うこと。
    """
    for tid, want in MAX_DIA_FROM_SHANK_MM.items():
        p = _template_params("mouthpiece", tid)
        got = p["overall_length"] - profiles.heel_z(p)
        assert got == pytest.approx(want, abs=0.1), (tid, got)


def test_shank_fraction_is_not_constant_across_sizes():
    """`shank_length / overall_length` はサイズ間で移らないこと。

    3 サイズとも最大径の位置が実測になり、比が 0.089 / 0.127 / 0.163 と**一定で
    ないことが確定した**。テナーの 0.163 をアルトに当てた借り物は 14.93 で、実測から
    解いた 11.63 に対し 28% 過大だった。**「サイズ間で比が移る」を書き戻さないため
    の番人**で、移ると踵が数 mm ずれて `table_cut_end_z` とリガチャー座が一緒に動く。
    """
    fr = {tid: _template_params("mouthpiece", tid)["shank_length"]
          / _template_params("mouthpiece", tid)["overall_length"] for tid in SIZES}
    assert fr["soprano"] < fr["alto"] < fr["tenor"], fr
    # いちばん近い 2 つでも 25% 以上違う（誤差ではなくサイズごとの性質）
    assert fr["tenor"] / fr["alto"] > 1.25, fr
    assert fr["alto"] / fr["soprano"] > 1.25, fr


def test_outer_shape_handles_do_not_cross_the_max_diameter():
    """外形を歪める 2 つが**最大径（頂点）を跨がない**こと。

    `body_waist` は z < heel_z、`shoulder_fullness` は z > heel_z しか動かさない。
    どちらも境の半径 `r_max` を動かさない（動かすのは `body_dia` だけ）。

    **これが崩れると何が壊れるか**: 前方が動けばテーブル平面の基準
    （`table_plane_y` は `outer_radius_nominal(0)` から引く）とリガチャー座が動き、
    肩を触っただけでティップ開きと音程が変わる。後方が動けばシャンクのはめあいが
    胴の膨らみに引きずられる。ビット一致で見るのは、この 2 つが**構造的に**
    別の区間しか触っていないことの確認だから（誤差ではなく分離の主張）。
    """
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        heel, length = profiles.heel_z(p), p["overall_length"]
        lo, hi = dict(p, shoulder_fullness=-1.0), dict(p, shoulder_fullness=1.0)
        for i in range(201):                       # 頂点まで（肩を端から端まで振る）
            z = heel * i / 200.0
            assert (profiles.outer_radius_nominal(lo, z)
                    == profiles.outer_radius_nominal(hi, z)), (tid, z)
        thin, fat = dict(p, body_waist=-0.06), dict(p, body_waist=0.06)
        for i in range(201):                       # 頂点から後ろ（胴を端から端まで振る）
            z = heel + (length - heel) * i / 200.0
            assert (profiles.outer_radius_nominal(thin, z)
                    == profiles.outer_radius_nominal(fat, z)), (tid, z)
        # 頂点そのものは 4 通りとも同じ（＝ r_max）
        rs = {profiles.outer_radius_nominal(q, heel)
              for q in (lo, hi, thin, fat)}
        assert rs == {p["body_dia"] / 2.0}, (tid, rs)


def test_max_diameter_must_actually_be_the_maximum():
    """`body_dia` < `shank_dia` を組として弾き、成立する側では最大径が本当に最大なこと。

    2 つは各自のレンジが独立していて `ParamSpec` は 1 本ずつしか見ないので、
    **UI のスライダ 2 本から逆転に到達できる**。逆転すると肩が外向きに開き、
    テーブル平面（`outer_radius_nominal(0)` から引く）が痩せた胴を斜めに抜けて
    **テナー既定 ＋ `body_dia` 下限 18.0 でソリッドが 2 個に割れる**
    （`cad/windycity/sweep_outer.py` で発見。`is_valid` は True のまま返るので
    妥当性フラグだけ見ていても気づけない）。ソプラノとアルトは割れずに残るが、
    3 サイズとも逆転自体は起きているので、割れなかったほうが偶然。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        p = _template_params("mouthpiece", tid)
        assert comp.params_error(p) is None, tid

        bad = dict(p, body_dia=p["shank_dia"] - 0.1)
        msg = comp.params_error(bad)
        assert msg is not None and "最大径" in msg, (tid, msg)

        # 境界（等しい）は成立する側。肩の段差が 0 になるだけで形は壊れない。
        edge = dict(p, body_dia=p["shank_dia"])
        assert comp.params_error(edge) is None, tid

        # 成立する側では heel_z が本当に外半径の最大を取る
        for q in (p, edge):
            heel, length = profiles.heel_z(q), q["overall_length"]
            r_heel = profiles.outer_radius_nominal(q, heel)
            for i in range(201):
                z = length * i / 200.0
                assert profiles.outer_radius_nominal(q, z) <= r_heel + 1e-9, (tid, z)


def test_shoulder_end_handle_keeps_the_max_diameter_in_place():
    """「肩の終わり」ハンドルは平行部だけ伸縮し、最大径の位置を動かさないこと。

    `heel_z = (全長 − シャンク長) / (1 + 肩比)` は導出値なので、`shank_length` を
    単独で動かすと**最大径ごと動いて前方の形まで相似に伸縮する**。ハンドルは
    2 つを一緒に解いて（`profiles.shoulder_end_span` の式）これを防ぐ。

    フロント（`SectionEditor.valuesAt`）と**同じ計算**をここでなぞる: 主キーだけ
    step へ丸め、従属キーは丸めたあとの t から引き直す。**従属側も独立に step へ
    丸めると最大径が 0.13〜0.17mm 動く**（実測）—— それを防いでいることの確認なので、
    しきい値は残る誤差（ハンドル payload の丸めぶん、実測 1e-7mm 台）より少し上に置く。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("mouthpiece", tid)
        p = _template_params("mouthpiece", tid)
        h = next(x for x in comp.section(p)["handles"]
                 if x["key"] == "shank_length" and x["group"] == "outer")
        heel, length = profiles.heel_z(p), p["overall_length"]
        link = h["also"][0]
        assert link["key"] == "shoulder_ratio", (tid, h["also"])
        seen = []
        for i in range(41):
            t = i / 40.0
            v = h["min"] + t * (h["max"] - h["min"])
            v = min(max(round(v / h["step"]) * h["step"], h["min"]), h["max"])
            tt = (v - h["min"]) / (h["max"] - h["min"])
            q = dict(p, shank_length=v,
                     shoulder_ratio=link["min"] + tt * (link["max"] - link["min"]))
            assert profiles.heel_z(q) == pytest.approx(heel, abs=1e-5), (tid, v)
            seen.append(length - profiles.shank_start_z(q))   # 平行部の長さ
        # 端では平行部が消える＝最大径からシャンク端まで一続きの肩になる
        assert min(seen) == pytest.approx(0.0, abs=1e-6), (tid, min(seen))
        assert max(seen) > 10.0, (tid, max(seen))


def test_shoulder_can_be_an_exact_cone_to_the_shank_end():
    """肩の張り +1 ＋ 平行部 0 で、最大径からシャンク端まで**厳密な直線**になること。

    「円錐シャンク」はブレンドの端がたまたま直線に近いのではなく、
    `shoulder_shape` の直線項が k=1 で丸ごと残るという式の性質。残差を
    浮動小数の桁で見るのはそのため。STEP 側も母線を 2 点で出す（＝円錐面 1 枚）。
    """
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        heel, length = profiles.heel_z(p), p["overall_length"]
        q = dict(p, shank_length=0.0, shoulder_ratio=(length - heel) / heel,
                 shoulder_fullness=1.0)
        assert profiles.shoulder_is_straight(q)
        r_max, r_sh = p["body_dia"] / 2.0, profiles.shank_radius(q)
        for i in range(201):
            t = i / 200.0
            got = profiles.outer_radius_nominal(q, heel + (length - heel) * t)
            assert got == pytest.approx(r_max + (r_sh - r_max) * t, abs=1e-9), (tid, t)
        # 母線が線分なので STEP は 2 点で出す（44 点のスプラインにしない）
        shoulder = profiles.body_segments(q)[-1]
        assert len(shoulder) == 2, (tid, [len(s) for s in profiles.body_segments(q)])


def test_cavity_station_roles():
    """空洞は 窓→チェンバー→スロート→ボア の順に並び、比 1.0 では単調にボアへ開く。

    実測（WindyCity Tenor）のリファレンスは **チェンバーの膨らみもスロートの狭窄も
    持たない**。断面積は窓の終端からボアまで単調に増える。以前はここで
    「スロートはチェンバーより狭い」を無条件に要求していたが、それは比 1.0 でも
    くびれがある前提で、実物と食い違っていた（ソプラノで実際に落ちていた）。
    くびれは `throat_ratio < 1.0` を指定したときに現れるべきもの。
    """
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        st = profiles.cavity_stations(p)
        assert all("role" in s for s in st)
        # role は z 範囲のラベル。出現順が 窓→チェンバー→スロート→ボア であること
        seen = [r for i, r in enumerate([s["role"] for s in st])
                if i == 0 or r != st[i - 1]["role"]]
        assert seen == ["window", "chamber", "throat", "bore"], (tid, seen)
        assert all(a["z"] < b["z"] for a, b in zip(st, st[1:])), tid   # ロフトが潰れない

        area = profiles.section_area
        # 比 1.0 では**くびれが無い**こと。実物の断面積は窓の終端からボアまで
        # 208→227mm² と増えるだけで、最狭部は存在しない。
        # 単調増加までは要求しない: 窓区間の断面は側壁が立った角丸長方形、
        # チェンバーは丸なので、その形状係数の移り変わりで数 % の上下は出る
        # （実物との断面積差は窓直後で最大 20%、z=45 以降は 3% 以内）。天井の
        # 横アーチ（`_TOP_ARCH`）が抜ける区間でも同じ程度の上下が出る。
        after = [s for s in st if s["role"] != "window"]
        a_bore = area(profiles.stations_by_role(st, "bore")[0])
        assert min(area(s) for s in after) >= 0.95 * a_bore, (
            tid, [(s["role"], round(area(s))) for s in after])

        # throat_ratio を絞ると本当にスロートが最狭部になる
        narrow = profiles.cavity_stations(dict(p, throat_ratio=0.70))
        chamber = profiles.chamber_max_station(narrow)
        throat = profiles.stations_by_role(narrow, "throat")[0]
        assert area(throat) < area(chamber), tid
        tail = [s for s in narrow if s["z"] >= chamber["z"]]
        assert min(tail, key=area)["role"] == "throat", (
            tid, [(s["role"], round(area(s))) for s in tail])
        # chamber_ratio を上げるとチェンバーが太る
        wide = profiles.cavity_stations(dict(p, chamber_ratio=1.6))
        assert area(profiles.chamber_max_station(wide)) > area(chamber), tid


#: マウスピースの照合カードで「軽微」が出る行。**どちらも実物の性質であって
#: モデルの粗さではない**ので、消さずに 1 行ずつ理由込みで記録する。
#:
#:   soprano  テーブル終端 60.0mm はケーン 59.1 を上回るが樹脂 62.0 に 2.0mm 足りない
#:            （`SOPRANO_LONG_REED_OVERHANG_MM`）。長いリードの踵は実際にはみ出す。
#:   tenor    基準機 WindyCity の最大径 30.8 が Jody Jazz Giant 6* の実測 30.0 を
#:            0.8 超える。アルトと違い**市販リガチャーで入るか確認していない**ので、
#:            上限を 30.8 へ緩めずに「軽微」で残す（緩めると根拠が「自分の基準機が
#:            そうだから」になり実物照合が循環する。descriptor の
#:            `ligature_max_dia_source`）。
_MP_CARD_MINOR = {"soprano": "リード全長域", "tenor": "最大径"}


def test_reference_card_all_match():
    """規格照合カードの「軽微」が想定の 1 行に閉じ、乖離が 1 行も出ないこと。

    **軽微はカードが仕事をしている状態で、消してはいけない**（理由は
    `_MP_CARD_MINOR`）。アルトだけ全行一致になる。リード側は 3 サイズとも一致。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        mp = reg.make_component("mouthpiece", tid)
        cards = mp.simulate({s.key: s.default for s in mp.param_specs()})["cards"]
        card = next(c for c in cards if "照合" in c["title"])
        assert not [r for r in card["rows"] if "乖離" in r[1]], (tid, card["rows"])
        minor = [r for r in card["rows"] if "軽微" in r[1]]
        want = _MP_CARD_MINOR.get(tid)
        if want is not None:
            assert len(minor) == 1 and want in minor[0][0], (tid, card["rows"])
            assert card["status"] == "warn", (tid, card["rows"])
        else:
            assert not minor and card["status"] == "ok", (tid, card["rows"])

        # リード側は 3 サイズとも一致（ソプラノのテンプレートは実測 59.1 に置いてある）
        reed = reg.make_component("reed", tid)
        reed.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", tid)}})
        cards = reed.simulate({s.key: s.default for s in reed.param_specs()})["cards"]
        card = next(c for c in cards if "照合" in c["title"])
        assert card["status"] == "ok", (tid, card["rows"])


def test_reed_recommended_tip_matches_cane_reality(alto_reed):
    """ケーンの推奨先端厚が実物のケーンリード（約0.10mm）付近に出ること。

    材料表に推奨厚を書かず二分法で解いているので、これは物理モデルの検算になる。
    """
    from saxsketch.acoustics import reed_model
    comp, p = alto_reed
    m = comp.ref_params()
    cane = reed_model.reed_properties(dict(p, material="cane"), m)
    assert 0.07 < cane["recommended_tip_mm"] < 0.15
    # 硬い材料ほど薄くないと同じ硬さにならない（単調性）
    pla = reed_model.reed_properties(dict(p, material="pla"), m)
    petg = reed_model.reed_properties(dict(p, material="petg"), m)
    assert cane["recommended_tip_mm"] < pla["recommended_tip_mm"] \
        < petg["recommended_tip_mm"]


def test_reed_cane_with_printed_thickness_warns(alto_reed):
    """cane + 印刷用の厚さ（0.40mm）はレンジ外なので警告すること。"""
    comp, p = alto_reed
    sim = comp.simulate(dict(p, material="cane", tip_thickness=0.40))
    card = next(c for c in sim["cards"] if c["title"] == "硬さ・剛性")
    assert card["status"] == "warn"
    assert "0.1" in card["advice"] or "0.09" in card["advice"]


# ------------------------------------------------------------------ プロファイル（純数学）

def test_facing_rise_boundary(alto):
    _, p = alto
    assert profiles.facing_rise(p, p["facing_length"]) == 0.0
    assert profiles.facing_rise(p, 0.0) == pytest.approx(p["tip_opening"], abs=1e-9)


def test_cavity_volume_reasonable(alto):
    _, p = alto
    vol = profiles.cavity_volume_cc(p)
    # アルトMPの内容積はおおむね 8〜16cc（実測レンジ）
    assert 8.0 < vol["total_cc"] < 16.0
    assert vol["effective_cc"] < vol["total_cc"]


def test_param_regions(alto):
    """影響領域: 全キーがパラメータ実在キー、z0<=z1、範囲内。"""
    comp, p = alto
    regions = comp.regions(p)
    keys = {s.key for s in comp.param_specs()}
    for k, r in regions.items():
        assert k in keys
        assert 0.0 <= r["z0"] <= r["z1"] <= p["overall_length"]
        assert r["side"] in ("top", "bottom", "all")
        assert r["label"]
    assert "material" not in regions  # 形状非依存パラメータは領域なし
    assert "tip_opening" in regions and "baffle_height" in regions


def test_stations_monotonic_and_sane(alto):
    _, p = alto
    st = profiles.cavity_stations(p)
    zs = [s["z"] for s in st]
    assert zs == sorted(zs)
    for s in st:
        assert s["h"] > 0.5 and s["w"] > 0.5


# ------------------------------------------------------------------ 汎用ビルダー

def test_reed_section_bottom_is_flat(alto_reed):
    """底面が厳密に平坦であること（リードのテーブル密着の前提）。"""
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    _, p = alto_reed
    for s in rp.sections(p):
        ys = [y for _, y in s["pts"]]
        assert min(ys) == 0.0
        assert [y for y in ys if y == 0.0] == [0.0, 0.0]  # 底辺は2点ちょうど
        assert max(ys) == pytest.approx(rp.thickness(p, s["z"], 0.0))
        xs = [x for x, _ in s["pts"]]
        hw = rp.width(p, s["z"]) / 2.0
        assert min(xs) == pytest.approx(-hw) and max(xs) == pytest.approx(hw)


def test_reed_sections_keep_one_vertex_count_across_shapes():
    """点数が形状パラメータによらず一定であること。

    `loft_sections` のルールドロフトはパラメータ対応で面を張るため、断面ごとに
    点数が変わると角の位置が辺の途中に写像されて面がねじれる。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    comp = get_registry().get("saxophone").make_component("reed", "alto")
    base = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
    counts = set()
    for over in ({}, {"tip_curve_depth": 0.0}, {"tip_curve_depth": 2.5},
                 {"heel_edge_thickness": 0.3}, {"heel_edge_thickness": 1.6},
                 {"side_rail_thin": 0.20}, {"side_rail_thin": 1.00}):
        counts |= {len(s["pts"]) for s in rp.sections({**base, **over})}
    assert counts == {21}          # 底辺 2 ＋ 上面 19（中央の稜線を含む奇数個）


def test_loft_sections_volume_and_watertight(tmp_path):
    """一定断面のロフト体積が解析値と一致し、水密であること。"""
    from saxsketch.geometry.builders import loft_sections
    from saxsketch.export.models import check_mesh, export_model
    pts = [(-5.0, 0.0), (5.0, 0.0), (5.0, 2.0), (0.0, 2.0), (-5.0, 2.0)]
    solid = loft_sections([{"z": 0.0, "pts": pts}, {"z": 20.0, "pts": pts}])
    assert solid.is_valid
    assert solid.volume == pytest.approx(10.0 * 2.0 * 20.0, rel=0.02)
    f = tmp_path / "slab.stl"
    export_model(solid, f, "stl")
    assert check_mesh(f)["watertight"]


# ------------------------------------------------------------------ リード

@pytest.fixture(scope="module")
def alto_reed():
    comp = get_registry().get("saxophone").make_component("reed", "alto")
    comp.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", "alto")}})
    return comp, {s.key: s.default for s in comp.param_specs()}


def _template_params(component_id: str, template_id: str) -> dict:
    from saxsketch.core.schema import ParamSet
    comp = get_registry().get("saxophone").make_component(component_id, template_id)
    return dict(ParamSet(comp.param_specs(),
                         comp.template.get(component_id, {})).values)


def test_reed_profile_shape(alto_reed):
    """厚みは先端→踵で単調増加、側端は中央以下、バークは全幅一定。"""
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    _, p = alto_reed
    zv = rp.vamp_start_z(p)
    ts = [rp.thickness(p, zv * i / 20.0) for i in range(21)]
    assert ts == sorted(ts)
    assert ts[0] == pytest.approx(p["tip_thickness"])
    assert rp.thickness(p, zv) == pytest.approx(p["heel_thickness"])
    for z in (0.0, zv * 0.5, zv * 0.99):
        assert rp.edge_thickness(p, z) <= rp.thickness(p, z, 0.0) + 1e-9


def test_reed_bark_is_kamaboko_not_a_rectangle(alto_reed):
    """バークは「全幅一定の長方形」ではなくケーンの円弧が残ったカマボコ。

    旧実装はここで `heel_thickness` を全 x に返していた（踵の断面が 14.0×2.8 の
    長方形）。実物は円筒のケーンから D 形に切り出すので上面に円弧が残る。
    """
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    _, p = alto_reed
    zb = (rp.vamp_start_z(p) + p["reed_length"]) / 2.0
    hw = p["heel_width"] / 2.0
    assert rp.thickness(p, zb, 0.0) == pytest.approx(p["heel_thickness"])
    assert rp.thickness(p, zb, hw) == pytest.approx(p["heel_edge_thickness"], abs=1e-9)
    # 踵の端面では幅がちょうど `heel_width` なので、側端厚がそのまま出る
    assert rp.edge_thickness(p, p["reed_length"]) == pytest.approx(
        p["heel_edge_thickness"], abs=1e-9)
    assert rp.edge_thickness(p, zb) < rp.thickness(p, zb, 0.0) - 1.0
    # 中央から側端へ単調に下がる
    ts = [rp.thickness(p, zb, hw * i / 12.0) for i in range(13)]
    assert ts == sorted(ts, reverse=True)


def test_reed_cane_arc_is_the_original_tube(alto_reed):
    """上面の円弧は 3 つの規格量を厳密に通り、**z に依らない**（管はまっすぐ）。"""
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    _, p = alto_reed
    hw = p["heel_width"] / 2.0
    assert rp.cane_top(p, 0.0) == pytest.approx(p["heel_thickness"], abs=1e-9)
    assert rp.cane_top(p, hw) == pytest.approx(p["heel_edge_thickness"], abs=1e-9)
    # 半径は円の定義から一意。中央厚との差が小さいほど大きな管になる
    thin = rp.cane_radius({**p, "heel_edge_thickness": 1.6})
    thick = rp.cane_radius({**p, "heel_edge_thickness": 0.3})
    assert thin > rp.cane_radius(p) > thick
    # バーク側では厚み＝円弧そのもの（削り面が上に居ない）
    for z in (rp.vamp_start_z(p) + 1.0, p["reed_length"]):
        for x in (0.0, hw * 0.5, hw):
            assert rp.thickness(p, z, x) == pytest.approx(rp.cane_top(p, x), abs=1e-9)


def test_reed_blank_must_fit_in_the_cane_tube(alto_reed):
    """管より広いブランクを弾くこと（掃引で見つけた組合せ）。

    上面がケーンの円弧になったので、リードが管より広いと円弧がテーブル面より下へ
    潜って断面が裏返る（`tip_width=18` で断面の最小 y = −0.45、`heel_width=9` で
    −3.48、後者はソリッドが `is_valid=False`）。**2 つのパラメータの関係**なので
    `ParamSpec` の範囲では表せない —— 幅を狭くしても側端厚を上げても成立する。
    """
    comp, p = alto_reed
    assert comp.params_error(p) is None
    assert comp.params_error({**p, "tip_width": 18.0}) is not None
    assert comp.params_error({**p, "heel_width": 9.0}) is not None
    # 側端厚を上げて円弧を浅くすれば**同じ幅のまま**成立する（幅だけの制限ではない）
    assert comp.params_error({**p, "tip_width": 18.0,
                              "heel_edge_thickness": 1.6}) is None


def test_reed_sections_follow_the_thickness_law(alto_reed):
    """断面ポリゴンの面積が厚みの法則の積分と一致すること。

    旧実装は角丸長方形で近似していて、**先端断面で 15% 太かった**（印刷される形と
    BOM・剛性が読む法則が別物だった）。断面はもう近似形を経由しない。
    """
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    _, p = alto_reed

    def poly_area(pts):
        a = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            a += x0 * y1 - x1 * y0
        return abs(a) / 2.0

    for s in rp.sections(p):
        law = rp._area(p, s["z"], samples=400)
        assert poly_area(s["pts"]) == pytest.approx(law, rel=0.005), s["z"]


def test_reed_solid_valid(alto_reed, tmp_path):
    from saxsketch.export.models import check_mesh, export_model
    comp, p = alto_reed
    part = comp.build(p)
    assert part.is_valid
    f = tmp_path / "reed.stl"
    export_model(part, f, "stl")
    q = check_mesh(f)
    assert q["watertight"] and q["winding_consistent"]
    # 全長・幅・厚みがバウンディングボックスと一致
    bb = part.bounding_box()
    assert bb.max.Z - bb.min.Z == pytest.approx(p["reed_length"], abs=0.1)
    assert bb.max.Y - bb.min.Y == pytest.approx(p["heel_thickness"], abs=0.05)
    assert bb.min.Y == pytest.approx(0.0, abs=1e-6)  # テーブル面が y=0 で平坦


def test_reed_tip_thickness_dimension(alto_reed):
    """先端近傍を薄板で切り出し、実測の中央厚が指定値に一致すること。"""
    from build123d import Pos, Solid
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    comp, p = alto_reed
    part = comp.build(p)
    z0, z1 = 0.4, 0.9
    probe = Pos(-1.0, -1.0, z0) * Solid.make_box(2.0, 5.0, z1 - z0)  # 中央のみ
    slab = part & probe
    bb = slab.bounding_box()
    # 区間内の最大厚（z1 側）と一致するはず
    assert bb.max.Y == pytest.approx(rp.thickness(p, z1, 0.0), abs=0.02)
    assert bb.min.Y == pytest.approx(0.0, abs=1e-6)


def test_reed_builds_for_all_templates():
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        comp.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", tid)}})
        p = {s.key: s.default for s in comp.param_specs()}
        assert comp.build(p).is_valid
        sim = comp.simulate(p)
        assert sim["kind"] == "reed" and sim["cards"]
        # 既定同士は適合しているはず（テンプレートの整合性テスト）
        fit = next(c for c in sim["cards"] if c["title"] == "マウスピース適合")
        assert fit["status"] == "ok", fit["advice"]


def test_reed_sections_uniform_vertex_count():
    """全ステーションの頂点数が揃っていること（ロフトのねじれ防止）。"""
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        p = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
        counts = {len(s["pts"]) for s in rp.sections(p)}
        assert len(counts) == 1, f"{tid}: 頂点数が不揃い {counts}"


#: 前縁の円弧が参照マウスピースのティップ輪郭からどれだけ離れるか [mm]。
#: **円弧では 0.1mm より近づけない** —— 実物の輪郭は真円ではないので、既定同士でも
#: soprano 0.094 / alto 0.103 / tenor 0.118 残る。ここはその残差の上限。
TIP_CONTOUR_ARC_RESIDUAL_MM = 0.15
#: 前縁を直線にしたとき角がティップレールから前へ張り出す量 [mm]。
#: 比べるのは**前縁アークが効く区間だけ**（角の丸みが効く所はリードが意図的に
#: 逃げている）。実測 soprano 1.012 / alto 0.990 / tenor 1.202。
TIP_STRAIGHT_OVERHANG_MM = 0.9


def _tip_rail_gap(rp, pp, m, x_max, samples=40):
    """リード前縁と参照MPのティップ輪郭の最大ずれ（負＝リードが前へ張り出す）。"""
    z0 = profiles.tip_contour_z(m, 0.0)
    out = 0.0
    for i in range(samples + 1):
        x = x_max * i / samples
        gap = rp.front_edge_z(pp, x) - (profiles.tip_contour_z(m, x) - z0)
        out = gap if abs(gap) > abs(out) else out
    return out


def test_reed_tip_curve_follows_the_mouthpiece_tip_rail():
    """既定の前縁カーブがマウスピースのティップ輪郭に乗ること。

    直線の前縁（`tip_curve_depth = 0`）だと 1.0〜1.2mm 前へ張り出す。これが
    この パラメータが要る理由なので、両方向を固定する。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        m = _template_params("mouthpiece", tid)
        p = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
        hw = min(p["tip_width"], m["reed_width"]) / 2.0
        flat = {**p, "tip_curve_depth": 0.0}

        assert abs(_tip_rail_gap(rp, p, m, min(rp.arc_end_x(p), hw))) \
            < TIP_CONTOUR_ARC_RESIDUAL_MM, tid
        # 直線の前縁は角でレールより前へ出る（負＝張り出し）
        assert _tip_rail_gap(rp, flat, m, min(rp.arc_end_x(flat), hw)) \
            < -TIP_STRAIGHT_OVERHANG_MM, tid


def test_reed_tip_curve_zero_is_the_old_shape(alto_reed):
    """`tip_curve_depth = 0` で**幅も断面もロフトのステーションも**旧式と一致すること。

    新しい特徴が既定の形を汚していないことの固定。輪郭を「前縁アーク → 角の
    フィレット → 側面」の 1 本に書き直しても、カーブ 0 ならアークが消えて
    フィレットが z=0 起点に戻り、旧式と**演算順まで**同じ式になる
    （`(w − 2r) + 2s` へ整理すると 2 ULP ずれるので、そこは整理しないこと）。
    """
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    _, p = alto_reed
    flat = {**p, "tip_curve_depth": 0.0}

    def old_width(z):
        t = min(max(z / p["reed_length"], 0.0), 1.0)
        w = p["tip_width"] + (p["heel_width"] - p["tip_width"]) * t
        r = p["tip_corner_r"]
        if 0.0 < z < r:
            w -= 2.0 * (r - math.sqrt(max(r * r - (r - z) ** 2, 0.0)))
        elif z <= 0.0:
            w -= 2.0 * r
        return max(w, 0.5)

    for i in range(2001):
        z = p["reed_length"] * i / 2000.0
        assert rp.width(flat, z) == old_width(z), z
    # 先端ステーションを足すのはカーブがあるときだけ（旧形状はロフトも不変）
    assert rp.nose_station_zs(flat) == []
    assert rp.sections(flat) == [
        {"z": z, "pts": [(-old_width(z) / 2.0, 0.0), (old_width(z) / 2.0, 0.0)]
         + [(q * old_width(z) / 2.0, rp.thickness(flat, z, q * old_width(z) / 2.0))
            for q in rp._TOP_QS]}
        for z in rp.station_zs(flat)]


def test_reed_outline_never_widens_toward_the_tip():
    """平面視の輪郭が z について単調非減少であること。

    4-C.2 は `if 0.0 < z < d` で **z=0 を円弧クランプから漏らして**いた。最先端の
    断面だけ全幅（soprano 11.5 / alto 11.8 / tenor 13.0）のまま残り、次の
    ステーションで 5.1〜5.9 まで絞られるので、前縁から厚さ 0.4mm の平たいヒレが
    前へ張り出していた（輪郭の垂直ずれ 2.31〜2.68mm）。**掃引もテストも
    `width(p, 0)` を depth>0 で評価していなかったので素通りした。**
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        base = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
        for d in (0.0, 0.4, base["tip_curve_depth"], 2.5):
            p = {**base, "tip_curve_depth": d}
            prev = -1.0
            for i in range(4001):
                w = rp.width(p, base["reed_length"] * i / 4000.0)
                assert w >= prev - 1e-12, (tid, d, i)
                prev = w
            if d > 0.0:      # カーブがあれば最先端は下限まで細る
                assert rp.width(p, 0.0) == 0.5, (tid, d)


def test_reed_outline_is_one_smooth_curve():
    """輪郭の傾き dx/dz が跳ね上がらないこと（区間の継ぎ目に段や折れが無い）。

    4-C.2 は角の丸みを円弧の**後ろに積んで**いたので、輪郭が
    「円弧 → 平行帯 → 傾きの跳び → 2 つめの膨らみ」の 4 区間に割れていた
    （alto で dx/dz が 0.004 から 5.57 へ跳ぶ）。跳ね上がる量の実測は
    旧 +118〜+134 / 新 +0.0023〜+0.0044。上限は側面テーパー自身の傾き。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    h = 1e-4
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        base = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
        taper = (base["heel_width"] - base["tip_width"]) / (2.0 * base["reed_length"])
        for d in (0.0, 0.4, base["tip_curve_depth"], 2.5):
            p = {**base, "tip_curve_depth": d}
            zs = [0.02 + i * h for i in range(int((rp.tip_full_width_z(p) + 0.5) / h))]
            slopes = [(rp.half_width(p, z + h) - rp.half_width(p, z)) / h for z in zs]
            jump = max((slopes[i] - slopes[i - 1] for i in range(1, len(slopes))),
                       default=0.0)
            assert jump <= taper + 1e-3, (tid, d, jump)


def test_reed_front_edge_matches_the_solid_outline():
    """`front_edge_z(x)` が輪郭 `half_width(z)` の逆関数になっていること。

    4-C.2 は前縁アークの閉形式だけを返していて、**角のフィレットを取りこぼして**
    いた（角の近くで実際の輪郭と 0.28〜0.56mm 食い違い、適合カードの許容差
    0.3mm より大きい）。カードはこの式で印刷される形を測るので、両者は同じ
    曲線でなければならない。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        base = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
        for d in (0.0, base["tip_curve_depth"], 2.5):
            p = {**base, "tip_curve_depth": d}
            for i in range(1, 200):
                x = rp.taper_half_width(p, 0.0) * i / 200.0
                z = rp.front_edge_z(p, x)
                # その z ではもう幅が足りている
                assert rp.half_width(p, z) >= x - 1e-9, (tid, d, x)
                # かつ、それより前では足りていない（＝最小の z）
                if z > 1e-9:
                    assert rp.half_width(p, z - 1e-4) < x, (tid, d, x)


def test_reed_stiffness_does_not_depend_on_the_tip_curve(alto_reed):
    """前縁カーブを入れても硬さ相当が跳ばないこと。

    等分布荷重の幅を `width(p, 0.0)` で取っていたときは、カーブを入れると z=0 が
    幅ゼロの尖点になって荷重が 1/27 に落ち、**硬さが上限 20.0 へ振り切れて**
    推奨先端厚が 0.02mm になっていた。荷重幅は先端の実効幅で取る。
    """
    from saxsketch.acoustics import reed_model
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    comp, p = alto_reed
    m = comp.ref_params()
    flat = {**p, "tip_curve_depth": 0.0}
    assert rp.tip_load_width(p) == rp.tip_load_width({**p, "tip_curve_depth": 2.5})
    assert rp.tip_load_width(flat) == rp.width(flat, 0.0)
    base = reed_model.reed_properties(flat, m)["strength_equiv"]
    curved = reed_model.reed_properties(p, m)["strength_equiv"]
    assert curved == pytest.approx(base, rel=0.05)


def test_reed_flow_width_does_not_depend_on_the_tip_curve(alto_reed):
    """物理モデル音へ渡す流路幅が前縁カーブで動かないこと。

    **`_bending` と同じ代理変数の穴が `reed_override` にもあった。** `width_mm` は
    OpenWind のリード流路の幅で、息が通るのは「先端がティップレールと向き合って
    いる幅」。z=0 の断面の幅を渡すと、前縁カーブを入れたとたん下限 0.5mm へ潰れて
    流れが線形域に落ち、**合成音が倍音を失って純正弦になる**
    （`test_reed_override_changes_sound` の倍音比 L1 差が 1.42 → 0.0006）。

    4-C.2 で見落としたのは、当時 `width(p, 0.0)` が z=0 を円弧クランプから漏らして
    いて**たまたま `tip_load_width` と同じ値を返していた**から —— 1 つのバグが
    もう 1 つのバグを覆い隠していた。
    """
    from saxsketch.acoustics import reed_model
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    comp, p = alto_reed
    m = comp.ref_params()

    def flow_width(depth):
        pp = {**p, "tip_curve_depth": depth}
        return reed_model.reed_override(
            reed_model.reed_properties(pp, m), pp)["width_mm"]

    assert flow_width(0.0) == flow_width(2.5) == rp.tip_load_width(p)
    # リードそのものの幅を変えれば当然動く（定数に潰していないことの確認）
    narrow = {**p, "tip_width": p["tip_width"] - 2.0}
    assert reed_model.reed_override(
        reed_model.reed_properties(narrow, m), narrow)["width_mm"] \
        == pytest.approx(rp.tip_load_width(p) - 2.0)


def test_reed_heel_reaches_seat_end(alto_reed):
    """踵がリガチャー座の後端に届かない設定を警告すること。

    許容差は判定側と**同じ 1 個の値**（`reference_check.SEAT_REACH_TOL`）で見る。
    実測の踵位置は規格リード長より 0.8〜1.0mm 後ろに来るのが正しい姿なので、
    ここで許容ゼロの厳密比較をすると、既定テンプレートが必ず落ちる。
    """
    comp, p = alto_reed
    m = comp.ref_params()
    from saxsketch.instruments.saxophone.components import profiles
    from saxsketch.instruments.saxophone.components import reference_check
    _, seat1 = profiles.ligature_seat_range(m)
    # 既定は届いている（判定と同じ許容差の内側）
    assert p["reed_length"] >= seat1 - reference_check.SEAT_REACH_TOL

    def fit(**over):
        sim = comp.simulate({**p, **over})
        return next(c for c in sim["cards"] if c["title"] == "マウスピース適合")

    assert fit()["status"] == "ok"
    short = fit(reed_length=seat1 - 5.0)
    assert short["status"] == "warn" and "後端" in short["advice"]


def test_reed_stiffness_directions(alto_reed):
    """硬さ相当・共振周波数の変化方向（絶対値ではなく単調性を検証する）。"""
    from saxsketch.acoustics import reed_model
    comp, p = alto_reed
    m = comp.ref_params()

    def props(**over):
        return reed_model.reed_properties({**p, **over}, m)

    base = props()
    thick = props(tip_thickness=p["tip_thickness"] + 0.2)
    thin = props(tip_thickness=p["tip_thickness"] - 0.1)
    assert thin["strength_equiv"] < base["strength_equiv"] < thick["strength_equiv"]
    assert thin["f_reed_hz"] < base["f_reed_hz"] < thick["f_reed_hz"]

    # ヴァンプを伸ばす＝削り面が長い＝柔らかい
    assert props(vamp_length=p["vamp_length"] + 8.0)["strength_equiv"] \
        < base["strength_equiv"]
    # 柔らかい材料ほど柔らかい
    assert props(material="resin_flex")["strength_equiv"] < base["strength_equiv"]
    # 校正: ケーンの標準リードが 3 前後になること（スケールの妥当性）
    calib = reed_model.reed_properties(
        dict(reed_model._CALIB_PARAMS), {"facing_length": reed_model._CALIB_L_EFF})
    assert 2.5 < calib["strength_equiv"] < 3.5


def test_reed_printability_flag(alto_reed):
    from saxsketch.acoustics import reed_model
    comp, p = alto_reed
    m = comp.ref_params()
    assert reed_model.reed_properties({**p, "tip_thickness": 0.40}, m)["printable"]
    assert not reed_model.reed_properties(
        {**p, "tip_thickness": 0.20, "material": "pla"}, m)["printable"]


def test_reed_recommended_values_are_never_a_clamped_lie():
    """推奨値は「そこへ持っていけば**本当に**その硬さになる値」であること。

    4-C.2d 以前は二分法の端をそのまま返し、さらに材料表の下限で `max()` して
    いたので、3 サイズ × 5 材料の 15 通りのうち **6 通りが解ではない値**だった
    （tenor/petg は「先端厚 1.20mm で 3番相当」と書いていたが、1.20mm でも
    2.72 にしかならない）。黙って域内へ潰さないことを全組合せで固定する。
    """
    from saxsketch.acoustics import reed_model
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        comp.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", tid)}})
        m = comp.ref_params()
        p = {s.key: s.default for s in comp.param_specs()}
        for mat in reed_model.MATERIALS:
            props = reed_model.reed_properties({**p, "material": mat}, m)
            for key, rec, lim in (
                    ("tip_thickness", "recommended_tip_mm", "recommended_tip_limit"),
                    ("vamp_length", "recommended_vamp_mm", "recommended_vamp_limit")):
                v = props[rec]
                if v is None:
                    # 届かないときは「どこまで行けるか」を必ず添える
                    edge, got = props[lim]
                    assert abs(got - 3.0) > 0.01, (tid, mat, key)
                    continue
                assert props[lim] is None, (tid, mat, key)
                s = reed_model.reed_properties(
                    {**p, "material": mat, key: v}, m)["strength_equiv"]
                assert s == pytest.approx(3.0, abs=0.05), (tid, mat, key, v, s)


def test_reed_recommended_tip_is_none_when_out_of_reach(alto_reed):
    """先端厚だけでは届かない材料で、数値ではなく「届かない」と言うこと。

    先端厚はいちばん弱いレバーなので、柔らかい材料では可動域いっぱいでも
    3番相当にならない。カードに偽の数値が出ないことまで見る。
    """
    from saxsketch.acoustics import reed_model
    comp, p = alto_reed
    soft = {**p, "material": "resin_flex"}
    props = reed_model.reed_properties(soft, comp.ref_params())
    assert props["recommended_tip_mm"] is None
    edge, got = props["recommended_tip_limit"]
    assert edge == pytest.approx(reed_model.TIP_THICKNESS_RANGE[1])
    assert got < 3.0
    # ヴァンプ長のほうは届く（＝「硬くできない」ではなくレバーの選び方の話）
    assert props["recommended_vamp_mm"] is not None

    card = next(c for c in comp.simulate(soft)["cards"] if c["title"] == "硬さ・剛性")
    tip_row = next(r for r in card["rows"] if "3番相当にする先端厚" in r[0])
    assert "届かない" in tip_row[1] and "mm（現在" not in tip_row[1]


def test_reed_vamp_is_a_stronger_lever_than_the_tip(alto_reed):
    """硬さを決めているのは先端厚ではなく自由振動長のつけ根の厚み。

    たわみは `∫ w·z³/(2EI) dz` で z³ の重みなので固定端側が支配する。
    ここが崩れると硬さカードの助言（ヴァンプ長を名指しする）が嘘になる。
    """
    from saxsketch.acoustics import reed_model
    comp, p = alto_reed
    m = comp.ref_params()
    bands = reed_model.deflection_bands(p, m)
    assert sum(bands) == pytest.approx(100.0)
    assert bands[0] < 10.0, bands              # 先端 1/4 の寄与
    assert bands[-1] > 3.0 * bands[0], bands   # 根元 1/4 のほうがずっと重い

    def s(**over):
        return reed_model.reed_properties({**p, **over}, m)["strength_equiv"]

    base = s()
    d_tip = max(abs(s(tip_thickness=p["tip_thickness"] + 0.1) - base),
                abs(s(tip_thickness=p["tip_thickness"] - 0.1) - base))
    d_vamp = max(abs(s(vamp_length=p["vamp_length"] + 6.0) - base),
                 abs(s(vamp_length=p["vamp_length"] - 6.0) - base))
    assert d_vamp > d_tip, (d_tip, d_vamp)


def test_reed_thin_tip_can_still_be_a_normal_strength():
    """実物並みに薄い先端（0.11mm）でも 3番相当を作れること。

    印刷リードのテンプレート既定 0.38〜0.42 は**造形の都合**であって、
    「印刷リードは先端を厚くするしかない」ではない。誰かがその思い込みで
    先端厚を唯一のレバーに戻さないよう、可動域内に解があることを固定する。
    """
    from saxsketch.acoustics import reed_model
    lo, hi = reed_model.VAMP_LENGTH_RANGE
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        comp.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", tid)}})
        m = comp.ref_params()
        p = {s.key: s.default for s in comp.param_specs()}
        thin = {**p, "tip_thickness": 0.11}
        assert reed_model.TIP_THICKNESS_RANGE[0] <= 0.11
        v, limit = reed_model.vamp_length_for_strength(thin, m)
        assert v is not None and lo <= v <= hi, (tid, v)
        got = reed_model.reed_properties({**thin, "vamp_length": v}, m)
        assert got["strength_equiv"] == pytest.approx(3.0, abs=0.05), (tid, got)


def test_reed_print_floors_are_both_reported(alto_reed):
    """印刷の下限が 2 つとも出て、どちらが効いているかが 1 つだけ立つこと。

    4-C.2d 以前は解像度（`min_layer × 3`）とハードコードの 0.35 をカードが見て、
    `reed_properties` の `printable` は材料表の値を見ていて**表示されていな
    かった**（tip=0.30 でカードは「要注意」・フラグは False）。
    """
    from saxsketch.acoustics import reed_model
    comp, p = alto_reed

    def card(q):
        return next(c for c in comp.simulate(q)["cards"] if c["title"] == "印刷可否")

    c0 = card(p)
    labels = [r[0] for r in c0["rows"]]
    assert any("解像度の下限" in x for x in labels), labels
    assert any("実用強度の下限" in x for x in labels), labels
    assert sum("効いている" in r[1] for r in c0["rows"]) == 1, c0["rows"]
    props = reed_model.reed_properties(p, comp.ref_params())
    assert (c0["big"] == "造形可") == props["printable"]

    # 工程を変えると「造形不可（解像度）」が「要注意（強度は未確認）」に変わる。
    # **「造形可」にはならない** —— 誰も 0.11mm の印刷リードが屈曲に耐えることを
    # 示していないので、モデルは「不可能」をやめて「未確認」と言うだけ。
    thin = {**p, "tip_thickness": 0.11}
    assert card(thin)["big"] == "造形不可"
    assert card({**thin, "material": "resin_rigid", "min_layer": 0.03})["big"] == "要注意"


def test_reed_parameter_ranges_have_one_source(alto_reed):
    """可動域が `reed_model` の定数と一致すること（2 か所に書かない）。

    ソルバと `ParamSpec` で域が食い違うと、カードが UI で設定できない値を
    勧める（4-C.2d 以前は上限 1.20 対 0.90 でずれていた）。
    """
    from saxsketch.acoustics import reed_model
    comp, _ = alto_reed
    spec = {s.key: s for s in comp.param_specs()}
    for key, span in (("tip_thickness", reed_model.TIP_THICKNESS_RANGE),
                      ("vamp_length", reed_model.VAMP_LENGTH_RANGE),
                      ("min_layer", reed_model.MIN_LAYER_RANGE)):
        assert (spec[key].min, spec[key].max) == span, key


def test_reed_override_changes_sound(alto_reed):
    """リード実形状が物理モデル音に効いていること（Phase 3 の価値の核）。

    **観測量を音高から音色へ移した。** 以前は「リード共振を変えるとレジスタが
    変わる」として f0 が 5% 以上動くことを見ていたが、それは `_coarsen` が
    共鳴管を非調和にしていた頃の挙動で、直すとリードの硬さに関わらず
    **第1共鳴が鳴る**（それが正しい。ビーティングリードはリード共振よりずっと
    低い管の共鳴に乗る）。実測 tip 0.30 → 137.5Hz / 0.55 → 137.7Hz で差は 0.15%。

    効くのは音色のほう。同じ実測で倍音比（f0 の 1〜8 倍、基音で正規化）が

      tip 0.30 (f_reed 1847Hz)  1.00 / 0.35 / 0.71 / 0.24 / 0.29 / 0.12 / ...
      tip 0.55 (f_reed 2154Hz)  1.00 / 0.01 / 0.25 / 0.00 / 0.06 / 0.01 / ...

    と大きく変わる（L1 差 1.42。硬いほど偶数倍音が落ちる）。

    **duration は既定のまま。** 0.3s では両方ともほぼ正弦で L1 差 0.006 しか
    出ない —— 音高は 0.36s で定まるが、音色はそれより遅れて立つ。
    OpenWind 必須なので WSL でのみ実行される。
    """
    pytest.importorskip("openwind")
    import io
    import wave

    import numpy as np
    from saxsketch.acoustics import openwind_bridge as ob
    from saxsketch.acoustics import reed_model
    comp, p = alto_reed
    m = comp.ref_params()
    f1 = ob._first_peak_hz(ob.build_resonator(m, comp.size_info),
                           0.6 * comp.size_info["low_note_sounding_hz"],
                           1.7 * comp.size_info["low_note_sounding_hz"])

    def play(tip):
        pp = {**p, "material": "cane", "tip_thickness": tip}
        ov = reed_model.reed_override(reed_model.reed_properties(pp, m), pp)
        wav, meta = ob.synthesize(m, comp.size_info, "normal", override=ov)
        with wave.open(io.BytesIO(wav)) as w:
            a = np.frombuffer(w.readframes(w.getnframes()),
                              dtype="<i2").astype(float)
        seg = a[int(0.6 * a.size):]
        seg = seg - seg.mean()
        spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size)))
        freqs = np.fft.rfftfreq(seg.size, 1.0 / ob.SIM_SR)
        h = [float(spec[np.argmin(abs(freqs - k * meta["f0"]))]) for k in range(1, 9)]
        return meta["f0"], ov["f_reed"], [x / max(h[0], 1e-12) for x in h]

    (f_soft, r_soft, h_soft), (f_hard, r_hard, h_hard) = play(0.30), play(0.55)
    assert r_hard > r_soft * 1.1, (r_soft, r_hard)      # 硬い＝リード共振が高い
    # どちらも自励発振し、**どちらも第1共鳴**で鳴っている
    for f in (f_soft, f_hard):
        assert f == pytest.approx(f1, rel=0.03), (f, f1)
    # 音色は大きく違う（実測 1.42。半分を下回ったらリード形状が効いていない）
    assert sum(abs(a - b) for a, b in zip(h_soft, h_hard)) > 0.5, (h_soft, h_hard)


def test_reed_filed_cut_removes_material(alto_reed):
    comp, p = alto_reed
    unfiled = comp.build({**p, "file_cut": "unfiled"}).volume
    filed = comp.build({**p, "file_cut": "filed"}).volume
    assert filed < unfiled


def test_reed_filed_cut_is_in_the_thickness_law():
    """ファイルドが**厚みの法則の中**にあること。

    4-C.2b まではバーク端の前後をブーリアンで削っていたので、印刷される形だけが
    変わって `blade_volume_mm3`（BOM・印刷カードが読む）も `second_moment`（硬さ）も
    ファイルドを 1 ビットも見ていなかった —— 実ソリッドが 7.4〜8.5mm³ 減るのに
    法則側の差は **+0.0** だった。上の `..._removes_material` は実ソリッドしか
    見ないのでこの穴を通してしまう。

    いまは「表皮を一直線まで剥がす」を `thickness()` の天井として持っている。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.acoustics import reed_model
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        m = _template_params("mouthpiece", tid)
        base = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
        u = {**base, "file_cut": "unfiled"}
        f = {**base, "file_cut": "filed"}
        # 材料体積は 1.2〜1.4% 減る（実測。ブーリアン時代はここが 0.0 だった）
        vu, vf = rp.blade_volume_mm3(u), rp.blade_volume_mm3(f)
        assert 0.008 < (vu - vf) / vu < 0.02, (tid, vu, vf)
        # 断面二次モーメントも帯の中で下がる（硬さが動く）
        zb = rp.vamp_start_z(base) * 0.95
        assert rp.second_moment(f, zb) < rp.second_moment(u, zb) * 0.95, tid
        su = reed_model.reed_properties(u, m)["strength_equiv"]
        sf = reed_model.reed_properties(f, m)["strength_equiv"]
        assert sf < su, (tid, su, sf)


def test_reed_filed_band_is_a_straight_line_at_the_vamp_end():
    """ファイルドの境は**全幅にわたる一直線**で、落差は表皮の厚みちょうど。

    「単なる切込み」ではないことの固定 —— 溝なら帯の前側にも段が出る。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        base = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
        p = {**base, "file_cut": "filed"}
        zv, bark = rp.vamp_start_z(p), rp.bark_thickness(p)
        hw = p["heel_width"] / 2.0
        for i in range(9):
            x = hw * i / 8.0
            step = rp.thickness(p, zv + 0.001, x) - rp.thickness(p, zv - 0.001, x)
            assert step == pytest.approx(bark, abs=1e-9), (tid, x, step)
        # 帯の前側は削り面へ連続して溶ける（段が無い ＝ 溝ではない）
        z0 = rp.filed_band_start_z(p, 0.0)
        assert rp.thickness(p, z0 - 0.05, 0.0) \
            == pytest.approx(rp.thickness(p, z0 + 0.05, 0.0), abs=0.01), tid


def test_reed_filed_band_narrows_toward_the_centre():
    """「表皮を削った部分」が三日月になること（中央が細く側端が太い）。

    削り面が中央でいちばん後ろまで伸びているからで、解説図の形そのもの。
    実測 中央 2.3〜2.5mm → 側端 16.9〜23.4mm。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("reed", tid)
        base = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
        p = {**base, "file_cut": "filed"}
        zv, hw = rp.vamp_start_z(p), p["heel_width"] / 2.0
        widths = [zv - rp.filed_band_start_z(p, hw * i / 10.0) for i in range(11)]
        assert widths == sorted(widths), (tid, widths)
        assert 2.0 < widths[0] < 3.0, (tid, widths[0])
        assert 15.0 < widths[-1] < 25.0, (tid, widths[-1])


def test_reed_filed_needs_bark_to_remove():
    """ファイルドは**表皮ぶんの余裕**が要ることを `params_error` が知っていること。

    表皮を落とす面がテーブル面より下へ行くと断面が裏返る。管の限界近くで
    先端幅 > 踵幅 にすると起きる（直す前は 252 通りで最小 y = −0.16）。
    **掃引は 1 パラメータの端値しか振らないのでこの領域に届かない。**
    `params_error` を通った組は 1 つ残らず断面が y ≥ 0 でなければならない。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    comp = get_registry().get("saxophone").make_component("reed", "alto")
    base = dict(ParamSet(comp.param_specs(), comp.template["reed"]).values)
    checked = 0
    for het in (0.3, 0.9, 1.6):
        for ht in (1.8, 2.8, 3.6):
            for heel_w in (9.0, 12.0, 15.0, 18.0):
                # その組で `params_error` を通る最大の先端幅を二分法で出す
                lo, hi = heel_w, 18.0
                for _ in range(40):
                    mid = (lo + hi) / 2.0
                    p = {**base, "heel_edge_thickness": het, "heel_thickness": ht,
                         "tip_width": mid, "heel_width": heel_w, "file_cut": "filed"}
                    lo, hi = (lo, mid) if comp.params_error(p) else (mid, hi)
                p = {**base, "heel_edge_thickness": het, "heel_thickness": ht,
                     "tip_width": lo, "heel_width": heel_w, "file_cut": "filed"}
                if comp.params_error(p) is not None:
                    continue
                checked += 1
                ys = [y for s in rp.sections(p) for _, y in s["pts"]]
                assert min(ys) >= -1e-9, (het, ht, heel_w, lo, min(ys))
    assert checked >= 20, checked

    # アンファイルドは狭まっていない。上限を両方とも解いて、その**間の幅**が
    # 「アンファイルドなら成立、ファイルドなら弾かれる」ことを見る。
    wide = {**base, "heel_edge_thickness": 0.9, "heel_width": 9.0}

    def max_tip_width(file_cut):
        lo, hi = 9.0, 18.0
        for _ in range(40):
            mid = (lo + hi) / 2.0
            lo, hi = ((lo, mid) if rp.cane_layout_error(
                {**wide, "tip_width": mid, "file_cut": file_cut}) else (mid, hi))
        return lo

    w_unfiled, w_filed = max_tip_width("unfiled"), max_tip_width("filed")
    assert w_filed < w_unfiled, (w_unfiled, w_filed)
    between = (w_unfiled + w_filed) / 2.0
    assert rp.cane_layout_error({**wide, "tip_width": between,
                                 "file_cut": "unfiled"}) is None
    assert rp.cane_layout_error({**wide, "tip_width": between,
                                 "file_cut": "filed"}) is not None


def test_reed_unfiled_is_untouched_by_the_file_cut(alto_reed):
    """アンファイルドの断面が天井の追加で 1 ビットも動かないこと。"""
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    _, p = alto_reed
    u = {**p, "file_cut": "unfiled"}
    assert rp.station_zs(u) == rp.station_zs({k: v for k, v in u.items()
                                              if k != "file_cut"})
    for s in rp.sections(u):
        for x, y in s["pts"]:
            assert y == min(rp._vamp_thickness(u, s["z"], x), rp.cane_top(u, x)) \
                or y == 0.0, (s["z"], x, y)


# ------------------------------------------------------------------ リガチャー

@pytest.fixture(scope="module")
def alto_ligature():
    comp = get_registry().get("saxophone").make_component("ligature", "alto")
    comp.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", "alto")}})
    return comp, {s.key: s.default for s in comp.param_specs()}


def test_ligature_inner_follows_mouthpiece(alto_ligature):
    """内周が参照マウスピースの**座での外形**＋はめあい隙間に一致し、追従すること。

    座は最大径の位置ではない。実測の胴は踵（＝最大径）へ向かって単調に太るので、
    座の中央では外形が `body_dia/2` より 2.6% 細い（`r_seat/r_max` = 0.974）。
    以前はここで `body_dia/2` との等号を要求していたが、それは「座に r=r_max の
    平坦区間がある」という旧プロファイルの前提。追従を検証するという意図は変えず、
    **比例**で見る。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    from saxsketch.instruments.saxophone.components import profiles
    comp, p = alto_ligature
    m = comp.ref_params()
    z0, z1 = lp.seat_range(m, p)
    zm = (z0 + z1) / 2.0
    expect = profiles.outer_radius(m, zm) + p["clearance"]
    assert lp.inner_radius(m, p) == pytest.approx(expect, abs=1e-9)
    ratio = profiles.outer_radius(m, zm) / (m["body_dia"] / 2.0)
    assert 0.95 < ratio < 1.0, ratio        # 座は最大径より細いが、極端には細くない
    # ボディ径を変えると内周が同じ比で追従する（＝自動整合）
    comp.set_refs({"mouthpiece": {"params": {**m, "body_dia": m["body_dia"] + 2.0}}})
    assert lp.inner_radius(comp.ref_params(), p) == pytest.approx(
        lp.inner_radius(m, p) + ratio * 1.0, abs=0.02)
    comp.set_refs({"mouthpiece": {"params": m}})   # 後続テストのため戻す


def test_ligature_solid_valid(alto_ligature, tmp_path):
    from saxsketch.export.models import check_mesh, export_model
    comp, p = alto_ligature
    for n in (1, 2):
        part = comp.build({**p, "screw_count": n})
        assert part.is_valid
        assert part.volume > 100.0
        f = tmp_path / f"lig{n}.stl"
        export_model(part, f, "stl")
        assert check_mesh(f)["watertight"]


def test_ligature_contact_types_add_material(alto_ligature):
    """当たり方で体積が順序どおり（なし < 点 < 線 < 面）になること。

    接触は**内周断面の凸**なので、要素が増えるほど空洞が減って材料が増える。
    ソリッドが常に 1 個であることも見る（浮いた要素が生まれない設計の担保）。
    """
    comp, p = alto_ligature
    vols = {}
    for k in ("none", "point", "line", "face"):
        part = comp.build({**p, "contact_type": k, "contact_count": 2})
        assert len(part.solids()) == 1, k
        vols[k] = part.volume
    assert vols["none"] < vols["point"] < vols["line"] < vols["face"], vols


def test_ligature_contacts_are_symmetric_by_construction():
    """接触の x 位置が**式から**対称であること（判定で弾くのではない）。

    生成式が n とタブ半幅だけの関数なので、非対称な並びを作れる経路が無い。
    幅も「隣と融合しない」上限を守る。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    for hw in (4.0, 6.70, 6.95, 7.65, 12.0):
        for n in range(1, 7):
            xs = lp.contact_xs(hw, n)
            w = lp.contact_width(hw, n)
            assert len(xs) == n
            for i in range(n):
                assert xs[i] == -xs[n - 1 - i], (hw, n, xs)   # ビット一致
            assert abs(xs[-1]) + w / 2.0 <= lp.contact_span(hw) + 1e-12
            for a, b in zip(xs, xs[1:]):
                assert b - a > w, (hw, n, w)                  # 隣と融合しない


def test_ligature_contacts_actually_touch_the_reed():
    """接触要素の頂点が「リード背面（カマボコ）− リード逃げ」に乗ること。

    4-C.2 でリードの背面が円弧になったのに接触面は平面のままだったので、
    **既定の「2点レール」はリードに 1 か所も当たっていなかった**
    （締め代 0.15 のはずが、レール位置で 0.83〜1.04mm 離れていた）。
    断面ポリラインから直接読んで、その穴をふさぐ。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("ligature", tid)
        m = _template_params("mouthpiece", tid)
        comp.set_refs({"mouthpiece": {"params": m}})
        base = {s.key: s.default for s in comp.param_specs()}
        r = comp.reed_params()
        for kind in ("face", "line", "point"):
            for n in (1, 2, 3, 6):
                p = {**base, "contact_type": kind, "contact_count": n}
                rows = lp.contact_rows(m, p)
                z0, z1 = lp.seat_range(m, p)
                zc = rows[0] if rows else (z0 + z1) / 2.0
                hw = lp.flat_half_width(m, p)
                floor = lp.tab_floor_y(m, p, r, zc)
                # 断面の先頭がタブ床の折れ線（残りは上側＝ビーク側の円弧）
                nb = len(lp.tab_bottom_pts(m, p, r, hw, zc))
                sec = next(s for s in lp.inner_sections(m, p, r)
                           if abs(s["z"] - zc) < 1e-9)["pts"][:nb]

                def back(x):
                    return (profiles.table_plane_y(m, zc)
                            - rp.cane_top(r, abs(x)) - p["reed_clearance"])

                if kind == "face":
                    # 面は背面に密着 → 床より上のタブ床の点が全部カマボコに乗る
                    touched = [(px, py) for px, py in sec
                               if abs(px) <= lp.contact_span(hw) + 1e-9
                               and py > floor + 1e-9]
                    assert len(touched) >= 8, (tid, n)
                    for px, py in touched:
                        assert py == pytest.approx(back(px), abs=1e-9)
                else:
                    for x in lp.contact_xs(hw, n):
                        crest = max(py for px, py in sec if abs(px - x) < 1e-9)
                        assert crest == pytest.approx(back(x), abs=1e-9), \
                            (tid, kind, n, x)


def test_ligature_contact_none_is_the_old_shape():
    """`contact_type="none"` の内周が接触を入れる前と同じ形であること。

    実装時に HEAD の `inner_sections` とビット一致を確認したうえで、その形を
    決めている 3 つ（頂点数 71 / タブ床が 2 点で「テーブル − 踵厚 − リード逃げ
    − はめあい隙間」ちょうど / 残りが厳密に円上）をここで固定する。
    既定の当たり方（線）でも**床の高さは動かない**ことも見る。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("ligature", tid)
        m = _template_params("mouthpiece", tid)
        comp.set_refs({"mouthpiece": {"params": m}})
        base = {s.key: s.default for s in comp.param_specs()}
        r = comp.reed_params()
        p = {**base, "contact_type": "none"}
        for s in lp.inner_sections(m, p, r):
            pts, z = s["pts"], s["z"]
            assert len(pts) == 71, tid
            floor = (profiles.table_plane_y(m, z) - r["heel_thickness"]
                     - p["reed_clearance"] - p["clearance"])
            assert pts[0][1] == floor and pts[1][1] == floor    # ビット一致
            assert pts[0][0] == -pts[1][0]
            radius = profiles.outer_radius(m, z) + p["clearance"]
            for x, y in pts[2:]:
                assert math.hypot(x, y) == pytest.approx(radius, abs=1e-9) \
                    or abs(x) == pytest.approx(abs(pts[0][0]), abs=1e-9)
        # 接触を入れても床は動かない（逃げ 0.25 ＝ テンプレートの隙間 0.25）
        for kind in ("face", "line"):
            q = {**base, "contact_type": kind}
            assert lp.tab_floor_y(m, q, r, 50.0) == lp.tab_floor_y(m, p, r, 50.0)


def test_ligature_band_width_always_changes_the_shape():
    """バンド幅を動かすと**必ず**形が変わること（黙ったクランプの再発防止）。

    以前は `seat_range` が帯を「リガチャー座」へ丸め込んでいたので、座より広い
    幅では z 範囲が動かず、STL がビット一致して 3D が更新されなかった
    （素のアルトは 16.5mm 以降が全部同じ。閾値は参照マウスピースの
    `heel_z × 0.23` なので機体ごとに動く）。スライダの可動域 8.0〜28.0 を
    0.5 刻みで全部踏んで、断面が毎回変わることを見る。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("ligature", tid)
        m = _template_params("mouthpiece", tid)
        comp.set_refs({"mouthpiece": {"params": m}})
        base = {s.key: s.default for s in comp.param_specs()}
        r = comp.reed_params()
        seen = {}
        widths = [8.0 + 0.5 * i for i in range(41)]
        for bw in widths:
            p = {**base, "band_width": bw}
            key = repr(lp.inner_sections(m, p, r))
            assert key not in seen, f"{tid}: 幅 {bw} と {seen.get(key)} が同じ形"
            seen[key] = bw
            z0, z1 = lp.seat_range(m, p)
            assert z1 - z0 == pytest.approx(bw, abs=1e-12), tid
        # 上限いっぱいでもタブは収まり、窓にも掛からない（実測: 前端 29.1/42.3/51.0
        # に対し窓の後端 27.8/35.8/41.9）
        wide = {**base, "band_width": 28.0}
        assert lp.flat_half_width(m, wide) >= lp.requested_tab_half_width(m, wide)
        assert lp.seat_range(m, wide)[0] > profiles.window_end_z(m), tid


def test_ligature_band_is_anchored_at_the_max_diameter():
    """帯の後端が最大径（`heel_z`）から `seat_setback` だけ前へ来ること。

    後端の壁は物理（そこから先は胴が細くなるので頂点を跨いだ帯は掴めない）。
    前端は丸めない —— 座の長さ 0.23·heel_z は「典型的なリガチャー幅」から作った
    公称値であって壁ではない。既定 3 サイズの装着位置は**旧 `seat_offset` 時代の
    記録値と一致する**（測り方を変えても既定の形は動かさない）。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    reg = get_registry().get("saxophone")
    recorded = {"soprano": (44.102722, 57.102722), "alto": (54.298507, 70.298507),
                "tenor": (61.016681, 79.016681)}
    for tid in SIZES:
        comp = reg.make_component("ligature", tid)
        m = _template_params("mouthpiece", tid)
        comp.set_refs({"mouthpiece": {"params": m}})
        base = {s.key: s.default for s in comp.param_specs()}
        assert base["seat_setback"] == 0.0          # 既定は最大径に密着
        z0, z1 = lp.seat_range(m, base)
        assert (z0, z1) == pytest.approx(recorded[tid], abs=5e-6), tid
        seat1 = profiles.ligature_seat_range(m)[1]
        assert seat1 == profiles.heel_z(m)          # 座の後端 ＝ 最大径
        for bw in (8.0, 16.0, 28.0):
            a, b = lp.seat_range(m, {**base, "band_width": bw})
            assert b == seat1                       # 後端は幅に依らず壁に張り付く
            assert a == b - bw                      # 前だけ伸びる（丸めない）
        # **スライダの全域が生きる**（旧定義では 0〜0.17mm しか動かなかった）
        for off in (0.0, 5.0, 10.0, 15.0):
            a, b = lp.seat_range(m, {**base, "seat_setback": off})
            assert b == pytest.approx(seat1 - off, abs=1e-9), (tid, off)
            assert lp.effective_seat_setback(
                m, {**base, "seat_setback": off}) == pytest.approx(off, abs=1e-9)


def test_old_seat_offset_migrates_without_changing_the_shape(alto_ligature):
    """旧 `seat_offset` を `seat_setback` へ移しても、**形が 1 ビットも動かない**こと。

    旧定義は「座の前端から後ろ向き」で、帯の後端が胴の最大径の壁に必ず当たって
    いた（実効 0.17mm 以下）。新定義の 0.0 がその「最大径に密着」なので、旧値が
    何であれ 0.0 へ移すと保存されていた形と一致する。

    **キーごと変えている**のは、値の意味だけ変えると旧値と新値を区別できず、
    利用者が意図して入れた値を黙って 0 へ戻す経路ができるから。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    comp, p = alto_ligature
    m = comp.ref_params()
    for old in (3.0, 4.0, 4.5, 15.0):
        v, notes = comp.migrate_params({**p, "seat_offset": old})
        assert "seat_offset" not in v
        assert v["seat_setback"] == 0.0
        assert len(notes) == 1 and "形は変わりません" in notes[0]
        # 装着位置は旧実装の記録値（4-C.3b）とビット一致
        assert lp.seat_range(m, v) == (54.29850746268657, 70.29850746268657)
    # 新しいキーが入っていれば触らない（利用者の値を黙って戻さない）
    v2, notes2 = comp.migrate_params({**p, "seat_setback": 8.0})
    assert v2["seat_setback"] == 8.0 and notes2 == []


def test_ligature_reports_the_effective_seat_setback(alto_ligature):
    """飲まれた座位置を、黙って飲まずカードに出すこと。

    新しい測り方では既定（0.0 ＝ 最大径に密着）で飲みは起きない。飲むのは
    「前へ出しすぎて帯が胴から落ちる」ときだけなので、そこで報告が出る。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    comp, p = alto_ligature
    m = comp.ref_params()
    assert lp.effective_seat_setback(m, p) == pytest.approx(0.0, abs=1e-9)
    card = next(c for c in comp.simulate(p)["cards"]
                if c["title"] == "マウスピース適合")
    row = next(r for r in card["rows"] if "座位置" in r[0])
    assert "0.0" in row[1]
    assert "実効" not in card["advice"]
    # 前へ出しすぎると胴から落ちる手前で飲まれ、実効値がそれを報告する
    # （この域では帯が窓に掛かるので、カードの警告はそちらが先に出る）
    q = {**p, "seat_setback": 200.0}
    assert lp.effective_seat_setback(m, q) < q["seat_setback"] - 1.0
    assert lp.seat_range(m, q)[0] == pytest.approx(0.0, abs=1e-9)
    card2 = next(c for c in comp.simulate(q)["cards"]
                 if c["title"] == "マウスピース適合")
    assert card2["status"] == "warn" and "窓" in card2["advice"]


def test_ligature_reverse_screw_needs_a_contact(alto_ligature):
    """逆締めが成立しない組を `params_error` が弾くこと（既定は通る）。

    スリットが必ずタブ床を割るので、橋渡しする接触が無いと接触面が真っ二つに
    なる。橋がバンド厚に収まらない組も同じ理由で形にならない。
    """
    comp, p = alto_ligature
    assert comp.params_error(p) is None
    assert comp.params_error({**p, "closure": "screw_reed"}) is None
    bad = comp.params_error({**p, "closure": "screw_reed", "contact_type": "none"})
    assert bad and "橋渡し" in bad
    thick = comp.params_error({**p, "closure": "screw_reed", "min_wall": 2.0})
    assert thick and "バンド厚" in thick
    # 3 サイズとも既定の逆締めは成立する（橋 1.6 ＋ 逃げ 0.35 ＋ 床 0.2 = 2.15）
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        c = reg.make_component("ligature", tid)
        c.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", tid)}})
        q = {s.key: s.default for s in c.param_specs()}
        assert c.params_error({**q, "closure": "screw_reed"}) is None, tid


def test_ligature_elastic_has_no_screw(alto_ligature):
    """弾性バンドがスリットもネジ座も持たない一連リングになること。"""
    from saxsketch.geometry.builders import loft_sections
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    comp, base = alto_ligature
    p = {**base, "closure": "elastic", "clearance": -0.30, "material": "tpu"}
    m = comp.ref_params()
    r = comp.reed_params()
    part = comp.build(p)
    assert len(part.solids()) == 1 and part.is_valid
    ring = (loft_sections(lp.outer_sections(m, p, r))
            - loft_sections(lp.inner_sections(m, p, r)))
    assert part.volume == pytest.approx(ring.volume, rel=1e-9)   # 切除も加算も無い
    assert lp.has_screws(p) is False
    assert not [b for b in comp.bom(p) if b["type"] == "市販品"]
    card = next(c for c in comp.simulate(p)["cards"] if c["title"] == "締結")
    assert card["big"] == "ネジなし" and "M" not in str(card["big"])


def test_ligature_elastic_needs_a_stretchy_material(alto_ligature):
    """伸びない材料の一連リングを印刷強度カードが `bad` と言うこと。

    形としては作れる（薄いバンドなら成立する余地がある）ので `params_error`
    にはしない —— そこは設計者の判断。剛体バンドで隙間が負なら適合カードが警告する。
    """
    comp, base = alto_ligature
    p = {**base, "closure": "elastic", "clearance": -0.30}

    def card(q, title):
        return next(c for c in comp.simulate(q)["cards"] if c["title"] == title)

    assert card({**p, "material": "petg"}, "印刷強度")["status"] == "bad"
    assert card({**p, "material": "tpu"}, "印刷強度")["status"] == "ok"
    assert card({**p, "material": "tpu"}, "マウスピース適合")["status"] == "ok"
    # 剛体バンド × 負の隙間 → 入らない
    rigid = card({**base, "clearance": -0.30}, "マウスピース適合")
    assert rigid["status"] == "warn" and "伸びない" in rigid["advice"]
    # 弾性 × 正の隙間 → 掴めない
    loose = card({**p, "clearance": 0.25, "material": "tpu"}, "マウスピース適合")
    assert loose["status"] == "warn" and "締め代" in loose["advice"]


def test_ligature_taper_zero_press_is_the_plain_ring():
    """押し込み 0 のテーパ圧入が、ネジなしリング（弾性）と**ビット一致**すること。

    テーパは「`z - press_depth` の胴で引いた輪を `z` に置く」だけなので、
    押し込み 0 では `ref_z` が恒等になり既存形状を 1 ビットも汚さない。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("ligature", tid)
        m = _template_params("mouthpiece", tid)
        comp.set_refs({"mouthpiece": {"params": m}})
        base = {s.key: s.default for s in comp.param_specs()}
        r = comp.reed_params()
        ring = {**base, "closure": "elastic"}
        taper = {**base, "closure": "taper", "press_depth": 0.0}
        assert lp.ref_z(taper, 12.5) == 12.5                  # 恒等
        assert lp.inner_sections(m, ring, r) == lp.inner_sections(m, taper, r), tid
        assert lp.outer_sections(m, ring, r) == lp.outer_sections(m, taper, r), tid
        # 押し込むと内周は必ず小さくなる（手前の細い胴で引くので）
        deep = {**taper, "press_depth": 5.0}
        assert lp.inner_radius(m, deep) < lp.inner_radius(m, ring)


def test_ligature_taper_presses_both_the_cone_and_the_reed():
    """押し込み量が円錐とリードの締め代を**同じ 1 つのシフト**から出すこと。

    テーブル傾斜 4.18° は円錐 2.5〜2.9° より急なので、当たるのは必ずリードが先
    （実測: リード 2.05mm に対し円錐 5.03 / 5.32 / 5.65mm）。しきい値で符号が
    変わり、そこから先は押し込みに比例して増える。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        comp = reg.make_component("ligature", tid)
        m = _template_params("mouthpiece", tid)
        comp.set_refs({"mouthpiece": {"params": m}})
        base = {s.key: s.default for s in comp.param_specs()}
        p = {**base, "closure": "taper"}
        cone_at, reed_at = lp.press_engagement(m, p)
        assert reed_at == pytest.approx(2.05, abs=0.02), tid   # 3 サイズ共通
        assert 5.0 < cone_at < 5.7, tid
        assert reed_at < cone_at, tid          # リードが先に当たる
        prev = (-9e9, -9e9)
        for d in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0):
            ic, ir = lp.press_interference(m, {**p, "press_depth": d})
            assert ic > prev[0] and ir > prev[1], tid          # 単調
            assert (ic > 0.0) == (d > cone_at), (tid, d)       # しきい値で符号
            assert (ir > 0.0) == (d > reed_at), (tid, d)
            prev = (ic, ir)
        # 既定は両方当たっている（テンプレートの press_depth は円錐のしきい値の上）
        assert min(lp.press_interference(m, p)) > 0.0, tid


def test_ligature_taper_allows_rigid_materials(alto_ligature):
    """テーパ圧入では伸びない樹脂が通り、弾性バンドでは通らないこと。

    掴んでいるのはフープの伸びではなくリングの楕円化なので、`STRETCHY_MATERIALS`
    の縛りは `elastic` にだけ掛かる。TPU は逆に柔らかすぎて楔が効かない。
    """
    from saxsketch.instruments.saxophone.components import ligature as lig_mod
    comp, p = alto_ligature
    taper = {**p, "closure": "taper", "material": "pla"}
    assert comp.params_error(taper) is None
    cards = {c["title"]: c for c in comp.simulate(taper)["cards"]}
    assert cards["印刷強度"]["status"] == "ok"
    assert cards["テーパ圧入"]["status"] == "ok"
    assert cards["締結"]["big"] == "ネジなし"
    # 同じ材料でも弾性バンドは伸びないので bad のまま
    el = {**p, "closure": "elastic", "clearance": -0.3, "material": "pla"}
    assert next(c for c in comp.simulate(el)["cards"]
                if c["title"] == "印刷強度")["status"] == "bad"
    # TPU はテーパ圧入に向かない（弾性率表に載せない ＝ 見積りの対象外）
    assert "tpu" not in lig_mod.MATERIAL_E_MPA
    tpu = next(c for c in comp.simulate({**taper, "material": "tpu"})["cards"]
               if c["title"] == "テーパ圧入")
    assert tpu["status"] == "warn" and "弾性バンド" in tpu["advice"]
    # 負の隙間からは押し込めない
    bad = comp.params_error({**taper, "clearance": -0.2})
    assert bad and "テーパ圧入" in bad
    # 部品表に市販ねじが載らない
    assert not any(r["type"] == "市販品" for r in comp.bom(taper))


def test_ligature_taper_warns_when_the_cone_floats(alto_ligature):
    """リードにだけ当たって円錐が浮く押し込みを、黙って通さないこと。

    既定の隙間 0.25 では円錐は 5.32mm から当たる。その手前ではリングの上が
    支えられないので首を振る —— 助言は「隙間 ≤ 0.64 × リード逃げ」を出す。
    """
    comp, p = alto_ligature
    taper = {**p, "closure": "taper", "material": "pla"}

    def card(q):
        return next(c for c in comp.simulate(q)["cards"] if c["title"] == "テーパ圧入")

    loose = card({**taper, "press_depth": 3.0})
    assert loose["status"] == "warn" and "浮いて" in loose["advice"]
    assert "0.10" in loose["advice"] or "0.09" in loose["advice"]
    assert card({**taper, "press_depth": 1.0})["status"] == "bad"   # どこにも当たらない
    # 隙間を詰めれば同じ押し込みで両方当たる
    assert card({**taper, "press_depth": 3.0, "clearance": 0.09})["status"] == "ok"
    # 厚い帯は手で押し込めない（剛性が t³ で効く）
    hard = card({**taper, "press_depth": 10.0, "band_thickness": 4.0})
    assert hard["status"] == "warn" and "手で押せる" in hard["advice"]


def test_ligature_ring_stiffness_is_the_ovalising_one(alto_ligature):
    """帯の剛性を**楕円化**で測り、一様内圧のフープで測らないこと。

    リードが下から・胴が上から押す直径方向の 2 点荷重なので、効くのは楕円化
    （δ = 0.149·P·r³/EI）。フープ（E·t·W/r）で見積もると 68〜76 倍硬く出て、
    「閉じた剛体リングでは押し込み 2mm に 1.6kN 要る ＝ 成立しない」という
    誤った結論になる（計画中に実際に踏んだ）。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    from saxsketch.instruments.saxophone.components import ligature as lig_mod
    comp, p = alto_ligature
    m = comp.ref_params()
    e = lig_mod.MATERIAL_E_MPA["pla"]
    q = {**p, "closure": "taper"}
    k = lp.ring_stiffness(m, q, e)
    z0, z1 = lp.seat_range(m, q)
    hoop = e * p["band_thickness"] * (z1 - z0) / lp.inner_radius(m, q)
    assert k < hoop / 60.0
    assert k == pytest.approx(119.0, rel=0.05)
    # 剛性は厚みの 3 乗（曲げ）で効く。断面積の 1 乗（フープ）ではない
    k2 = lp.ring_stiffness(m, {**q, "band_thickness": 2.0 * p["band_thickness"]}, e)
    assert k2 / k == pytest.approx(8.0, rel=0.25)


def test_ligature_legacy_plate_type_migrates(alto_ligature):
    """旧 `plate_type` が変換され、**変換したことが 1 行返る**こと。

    `ParamSet` は未知キーを黙って捨てるので、フックが無いと「全面プレート」に
    してあったプロジェクトが黙って線接触に変わる。既定のフックは恒等であることも
    見る（コアは楽器を知らないまま）。
    """
    comp, p = alto_ligature
    # 旧 .wproj には新キーが無い（存在しなかった）ので、その形で渡す
    legacy = {k: v for k, v in p.items()
              if k not in ("closure", "contact_type", "contact_count")}
    for old, kind, count in (("none", "none", 1), ("plain", "face", 1),
                             ("rail", "line", 2)):
        values, notices = comp.migrate_params({**legacy, "plate_type": old})
        assert "plate_type" not in values
        assert values["contact_type"] == kind and values["contact_count"] == count
        assert values["closure"] == "screw_beak"
        assert len(notices) == 1 and "圧力プレート" in notices[0]
    assert comp.migrate_params(dict(p)) == (p, [])       # 旧キーが無ければ素通し
    reed = get_registry().get("saxophone").make_component("reed", "alto")
    assert reed.migrate_params({"a": 1}) == ({"a": 1}, [])   # 既定は恒等


def test_ligature_screw_hole_inside_boss():
    """ネジ穴が耳の中に収まること（全テンプレート×ネジ径×ネジ座下限）。"""
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("ligature", tid)
        comp.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", tid)}})
        m = comp.ref_params()
        specs = {s.key: s for s in comp.param_specs()}
        base = dict(ParamSet(comp.param_specs(), comp.template["ligature"]).values)
        for size in ("m2.5", "m3"):
            p = {**base, "screw_size": size,
                 "boss_height": specs["boss_height"].min}   # スキーマ下限
            assert p["boss_height"] >= lp.min_boss_height(p), \
                f"{tid}/{size}: ネジ座の下限がネジ径に足りない"
            ear_base = lp.inner_radius(m, p) + p["band_thickness"]
            ear_top = ear_base + p["boss_height"]
            axis = lp.screw_axis_y(m, p)
            _, hole_d, _ = lp.screw_spec(p)
            assert ear_base <= axis - hole_d / 2.0, f"{tid}/{size}: 穴が下へ抜ける"
            assert axis + hole_d / 2.0 <= ear_top, f"{tid}/{size}: 穴が上へ抜ける"


def test_ligature_tab_matches_plate(alto_ligature):
    """圧力プレートの幅が実際のタブ幅を超えないこと、超える設定は警告すること。"""
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    comp, p = alto_ligature
    m = comp.ref_params()
    assert lp.flat_half_width(m, p) <= lp.requested_tab_half_width(m, p) + 1e-9

    def fit(mp):
        comp.set_refs({"mouthpiece": {"params": mp}})
        sim = comp.simulate(p)
        return next(c for c in sim["cards"] if c["title"] == "マウスピース適合")

    try:
        assert fit(m)["status"] == "ok"
        # ボディ径を外形径 < リード幅まで絞るとタブが張り出しきれずリードが入らない
        # → 黙って切り詰めず警告する。タブは円の外へ出られるので、しきい値は
        # 「テーブル面の弦」ではなく**外形径そのもの**（アルトのリード 13.4mm に対し
        # 座の外形は 0.974·body_dia なので body_dia < 14.2mm で入らなくなる）。
        narrow = {**m, "body_dia": 13.0}
        assert lp.flat_half_width(narrow, p) \
            < lp.requested_tab_half_width(narrow, p)
        card = fit(narrow)
        assert card["status"] == "warn" and "収納幅" in card["advice"]
    finally:
        comp.set_refs({"mouthpiece": {"params": m}})


def test_ligature_sections_never_self_intersect():
    """帯の断面がどのパラメータ組合せでも自己交差しないこと。

    タブがテーブル面の弦より広いとき、以前は幅を切り詰めて回避していた（そのせいで
    実物どおり「リード幅＝弦幅」のテンプレートが必ず警告になっていた）。いまはタブを
    円の外へ張り出させるので、**順序を間違えると多角形が自分と交差してロフトが破綻する**。
    切り詰めをやめた根拠がこの不変条件なので、ここで固定する。棚が出る側
    （タブ<弦）と出ない側の両方を踏む組合せになっている。
    """
    import itertools

    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp

    def crosses(a, b, c, d):
        def cr(o, p, q):
            return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
        d1, d2, d3, d4 = cr(c, d, a), cr(c, d, b), cr(a, b, c), cr(a, b, d)
        return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))

    def self_intersection(pts):
        n = len(pts)
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                if crosses(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n]):
                    return i, j
        return None

    def signed_area(pts):
        n = len(pts)
        return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1]
                         - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))

    def check(sections, tag):
        # ルールドロフトの前提: 1 本のロフトの中で頂点数が一定であること。
        # 棚（テーブル面の水平部）は弦とタブ幅の大小で決まるので、帯の中で z に
        # よって出たり消えたりする —— そこで点数が変わると面がねじれる。
        assert len({len(s["pts"]) for s in sections}) == 1, (tag, "頂点数")
        for s in sections:
            pts = s["pts"]
            hit = self_intersection(pts)
            assert hit is None, (tag, s["z"], hit)
            assert signed_area(pts) > 0, (tag, s["z"])          # 反時計回り
            dup = [i for i in range(len(pts))
                   if pts[i] == pts[(i + 1) % len(pts)]]
            assert not dup, (tag, s["z"], dup)                  # 点が重ならない

    reg = get_registry().get("saxophone")
    shelf_cases = 0
    for tid in SIZES:
        lig = reg.make_component("ligature", tid)
        m0 = _template_params("mouthpiece", tid)
        specs = {s.key: s for s in lig.param_specs()}
        base = dict(ParamSet(lig.param_specs(), lig.template["ligature"]).values)
        r0 = lig.reed_params()
        rt0 = r0["heel_thickness"]
        for bd, cl, rc, rt in itertools.product(
                (m0["body_dia"] * 0.6, m0["body_dia"], m0["body_dia"] * 1.4),
                (specs["clearance"].min, specs["clearance"].max),
                (specs["reed_clearance"].min, specs["reed_clearance"].max),
                (rt0 * 0.6, rt0, rt0 * 1.5)):
            m = dict(m0, body_dia=bd)
            p = dict(base, clearance=cl, reed_clearance=rc)
            r = dict(r0, heel_thickness=rt)
            z0, z1 = lp.seat_range(m, p)
            zm = (z0 + z1) / 2.0
            r_in = profiles.outer_radius(m, zm) + cl
            if lp.requested_tab_half_width(m, p) < lp._shelf_half_width(
                    r_in, profiles.table_plane_y(m, zm)):
                shelf_cases += 1
            check(lp.inner_sections(m, p, r), (tid, bd, cl, rc, rt, "内周"))
            check(lp.outer_sections(m, p, r), (tid, bd, cl, rc, rt, "外周"))
        # 接触の組合せ（凸を入れても自己交差しないことがそのまま新機能の守り）
        for closure, kind, n in itertools.product(
                ("screw_beak", "screw_reed", "elastic"),
                ("none", "face", "line", "point"), (1, 2, 3, 6)):
            p = dict(base, closure=closure, contact_type=kind, contact_count=n)
            if lig.params_error(p):
                continue
            tag = (tid, closure, kind, n)
            check(lp.inner_sections(m0, p, r0), tag + ("内周",))
            check(lp.outer_sections(m0, p, r0), tag + ("外周",))
            if closure == "screw_reed":
                check(lp.bridge_sections(m0, p, r0), tag + ("橋",))
    assert shelf_cases > 0, "棚が出る側（タブ<弦）を1つも踏んでいない"


def test_ligature_screw_length_is_stock(alto_ligature):
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    comp, p = alto_ligature
    stock = lp.stock_screw_length(p)
    assert stock in lp.STOCK_SCREW_LENGTHS
    assert stock >= lp.required_screw_length(p)


def test_export_all_components(tmp_path):
    """3部品とも 出力一式（STL・仕様書・BOM）が通ること。

    仕様書は断面図とシミュレーション節をコンポーネントごとに切り替える。
    """
    import re
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    for comp in ("mouthpiece", "reed", "ligature"):
        r = c.post("/api/project/new", json={
            "instrument_id": "saxophone", "template_id": "alto",
            "component_id": comp})
        assert r.status_code == 200, r.text
        assert (r.json()["reference"] is None) == (comp == "mouthpiece")
        e = c.post("/api/export", json={
            "formats": ["stl"], "out_dir": str(tmp_path / comp),
            "make_package": False})
        assert e.status_code == 200, e.text
        assert e.json()["mesh_quality"]["watertight"]
        html = Path(e.json()["files"]["spec.html"]).read_text(encoding="utf-8")
        # 図の枚数は部品ごと。リードは厚みプロファイルに加えて踵の断面（カマボコ）
        # を出す —— 上面がケーンの円弧であることは軸方向の図には現れないため。
        assert html.count("<svg") == (2 if comp == "reed" else 1)
        heads = re.findall(r"<h2>(.*?)</h2>", html)
        assert any("音響予測" in h for h in heads) == (comp == "mouthpiece")
        assert any("シミュレーション" in h for h in heads)
        assert Path(e.json()["files"]["bom.csv"]).exists()


def test_spec_sections_contract():
    """各コンポーネントが spec_extras で sections を自前で組み立てること。

    共通の export/svg.py が部品固有のキーを知らずに済む形（コアは楽器を知らない）。
    """
    from saxsketch.core.schema import ParamSet
    reg = get_registry().get("saxophone")
    for cid in ("mouthpiece", "reed", "ligature"):
        comp = reg.make_component(cid, "alto")
        if comp.REQUIRES_REF:
            comp.set_refs({"mouthpiece":
                           {"params": _template_params("mouthpiece", "alto")}})
        p = dict(ParamSet(comp.param_specs(), comp.template[cid]).values)
        sections = comp.spec_extras(p)["sections"]
        assert sections, cid
        for s in sections:
            assert s["title"] and s["svg"].lstrip().startswith("<svg")


def test_reed_material_table_is_single_source():
    """材料の選択肢が reed_model.MATERIALS だけから来ること。"""
    from saxsketch.acoustics import reed_model
    comp = get_registry().get("saxophone").make_component("reed", "alto")
    spec = next(s for s in comp.param_specs() if s.key == "material")
    assert [c.value for c in spec.choices] == list(reed_model.MATERIALS)
    assert [c.label for c in spec.choices] == \
        [v[0] for v in reed_model.MATERIALS.values()]


def test_ligature_builds_for_all_templates():
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("ligature", tid)
        comp.set_refs({"mouthpiece": {"params": _template_params("mouthpiece", tid)}})
        p = {s.key: s.default for s in comp.param_specs()}
        assert comp.build(p).is_valid
        sim = comp.simulate(p)
        assert sim["kind"] == "ligature"
        # 既定同士は適合しているはず（テンプレートの整合性テスト）
        assert all(c["status"] == "ok" for c in sim["cards"]), sim["cards"]
        assert any("なべ小ねじ" in r["name"] for r in comp.bom(p))


# ------------------------------------------------------------------ ジオメトリ

@pytest.fixture(scope="module")
def alto_part(alto):
    comp, params = alto
    return comp.build(params)


def test_solid_valid_watertight(alto_part, tmp_path_factory):
    assert alto_part.is_valid
    assert alto_part.volume > 10000  # 実体のあるソリッド

    from saxsketch.export.models import export_model, check_mesh
    f = tmp_path_factory.mktemp("stl") / "mp.stl"
    export_model(alto_part, f, "stl")
    q = check_mesh(f)
    assert q["watertight"]
    assert q["winding_consistent"]


def test_tip_opening_dimension(alto, alto_part):
    """フェイシング面: z=0.2 断面の最下点が解析カーブと一致するか（弦誤差込み±0.12）。"""
    _, p = alto
    bb = alto_part.bounding_box()
    from build123d import Plane
    z_probe = 0.2
    section = alto_part.intersect(Plane.XY.offset(z_probe))
    shapes = list(section) if not hasattr(section, "bounding_box") else [section]
    min_y = min(s.bounding_box().min.Y for s in shapes)
    assert min_y == pytest.approx(profiles.cut_top_y(p, z_probe), abs=0.12)
    # 全長
    assert bb.max.Z - bb.min.Z == pytest.approx(p["overall_length"], abs=0.5)


def test_all_templates_build(tmp_path):
    """3サイズとも水密なソリッドになること。

    空洞が外殻を突き抜けていれば非水密になるので、`test_cavity_inside_shell` の
    解析的な判定に対する独立した裏取りになる。
    """
    from saxsketch.export.models import check_mesh, export_model
    reg = get_registry()
    for tmpl in ["soprano", "alto", "tenor"]:
        comp = reg.get("saxophone").make_component("mouthpiece", tmpl)
        p = {s.key: s.default for s in comp.param_specs()}
        part = comp.build(p)
        assert part.is_valid and part.volume > 5000
        f = tmp_path / f"{tmpl}.stl"
        export_model(part, f, "stl")
        q = check_mesh(f)
        assert q["watertight"] and q["winding_consistent"], (tmpl, q)


# ------------------------------------------------------------------ STEP 用プリミティブ表現


@pytest.fixture(scope="module")
def alto_part_cad(alto):
    comp, params = alto
    return comp.build_cad(params)


def test_mp_body_segments_cover_and_join(alto):
    """胴の母線区間が端点を共有して全長を覆い、C1 の折れ目で切れていること。

    区間の切れ目がずれるとスプライン母線が折れ目をまたいでうねる（実測で
    0.58mm のオーバーシュート）。ここは OCCT を呼ばずに列だけで確かめる。
    """
    _, p = alto
    segs = profiles.body_segments(p)
    assert segs[0][0][0] == pytest.approx(0.0)
    assert segs[-1][-1][0] == pytest.approx(p["overall_length"])
    for a, b in zip(segs, segs[1:]):
        assert a[-1] == pytest.approx(b[0])              # 端点を共有
    breaks = {round(s[0][0], 6) for s in segs[1:]}
    wanted = [profiles.heel_z(p), profiles.shank_start_z(p)]
    if profiles.tip_chamfer_len(p) > 0.0:      # 面取り 0 なら折れ目も無い
        wanted.append(profiles.tip_chamfer_len(p))
    for z in wanted:
        assert round(z, 6) in breaks, z
    # 各区間の半径は法則そのもの（サンプルし直しても一致する）
    for seg in segs:
        for z, r in seg:
            assert r == pytest.approx(profiles.outer_radius(p, z), abs=1e-9)


def test_mp_body_spline_stays_on_the_law(alto):
    """区間ごとのスプライン母線が、サンプル点の**間**でも法則から外れないこと。

    全区間を1本のスプラインで内挿していた試作では、ティップ面取りの折れ目で
    0.58mm オーバーシュートして胴の体積が 1.3% 痩せた。刻みを 0.05mm まで詰めても
    直らない（標本化ではなく折れ目の問題）ので、区切りが正しいかはここで見る。
    ソリッドを作らないので速い。
    """
    from build123d import Edge, Vector

    _, p = alto
    for seg in profiles.body_segments(p):
        if len(seg) < 3:
            continue                       # 直線区間は法則そのもの
        edge = Edge.make_spline([Vector(r, 0.0, z) for (z, r) in seg])
        for i in range(201):
            v = edge.position_at(i / 200.0)
            assert v.X == pytest.approx(profiles.outer_radius(p, v.Z), abs=0.01), (
                seg[0][0], seg[-1][0], v.Z, v.X)


def test_mp_cad_face_count(alto_part_cad):
    """STEP 用表現が「面を選べる」粒度に畳まれていること。

    多角形版は 2547 面・微小エッジ 5000本超で、FreeCAD では外周面を1クリックで
    選ぶこともフィレットを掛けることもできない。畳んだ後の実測は 60 面。
    """
    faces = alto_part_cad.faces()
    assert len(faces) < 100, len(faces)
    slivers = [f for f in faces if f.area < 0.5]
    assert len(slivers) < 5, [(f.area, str(f.geom_type)) for f in slivers]
    kinds = collections.Counter(str(f.geom_type) for f in faces)
    # 胴＝回転体、ビークの直線ランプ＝押出、テーブル＝平面が1枚ずつ残っていること
    assert kinds["GeomType.REVOLUTION"] >= 1, kinds
    assert kinds["GeomType.EXTRUSION"] >= 1, kinds
    assert kinds["GeomType.PLANE"] >= 1, kinds


def test_generatrix_chord_error_is_bounded():
    """胴の母線（多角形）が法則からどれだけ内側を通るかを縛る。

    **これはメッシュ許容では消えない誤差**。`revolve_profile` は多角形の母線を
    回すので、周方向は解析曲面でも母線方向は折れ線で、その弦誤差はソリッド自体に
    焼き込まれている。STL/3MF に紋様が出て STEP に出ない理由の片方がこれ
    （STEP は `body_segments` のスプライン母線）。

    実測: 旧刻み（ノーズ 0.25/0.45mm・肩 12 分割）で 0.083 / 0.133 / 0.127mm。
    現刻み（ノーズ 0.10/0.25mm・肩 24 分割）で 0.029 / 0.026 / 0.034mm。
    CAD を組まずに法則だけで測れるので、掃引にも耐える。
    """
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        with profiles.params_scope(p):
            zs = profiles.body_stations(p)
            worst = 0.0
            for a, b in zip(zs, zs[1:]):
                ra, rb = profiles.outer_radius(p, a), profiles.outer_radius(p, b)
                for i in range(1, 40):
                    t = i / 40.0
                    d = profiles.outer_radius(p, a + (b - a) * t) - (ra + (rb - ra) * t)
                    worst = max(worst, d)
        # 設計クリアランス 0.25mm の刻み 0.05mm より小さいこと
        assert worst < 0.05, (tid, worst)


def test_stl_and_3mf_are_the_same_mesh(alto_part, tmp_path):
    """STL と 3MF が**同じ Part を同じ許容で**メッシュ化していること。

    入稿の 3 形式のうち、この 2 つが食い違う理由は無い（どちらも `export_model`
    が同じ許容で `part` を割る）。3MF を直接パースして三角形数・頂点数まで見る
    —— 「同じはず」を根拠にせず、実際に一致することを固定する。
    """
    import re
    import zipfile
    from saxsketch.export.models import export_model

    f_stl = tmp_path / "m.stl"
    f_3mf = tmp_path / "m.3mf"
    export_model(alto_part, f_stl, "stl")
    export_model(alto_part, f_3mf, "3mf")

    import trimesh
    stl = trimesh.load(str(f_stl), force="mesh")
    with zipfile.ZipFile(f_3mf) as z:
        xml = z.read(next(n for n in z.namelist() if n.endswith(".model"))).decode()
    tri = len(re.findall(r"<triangle ", xml))
    vtx = len(re.findall(r"<vertex ", xml))
    assert tri == len(stl.faces)
    assert vtx == len(stl.vertices)


def test_export_mesh_is_fine_enough_to_look_round(alto_part, tmp_path):
    """出力メッシュの周方向の刻みが、目に見える紋様にならない細かさであること。

    **周方向を割っているのは `angular_tolerance` のほうで、linear はほとんど
    効かない**（0.05 → 0.01 で面数 8,444 → 8,976、刻みは 4.49° のまま）。
    0.3 のままだと胴が 80 角柱で画面にはっきり紋様が出る。

    測り直すときの注意: OCCT は三角形分割を形状に持ち回り、linear が細かく
    なったときしか作り直さない。1 プロセスで許容を振ると angular の効きが
    消えて見えるので `BRepTools.Clean_s` を挟むこと。
    """
    import math

    import numpy as np
    import trimesh
    from saxsketch.export.models import export_model

    f = tmp_path / "m.stl"
    export_model(alto_part, f, "stl")
    mesh = trimesh.load(str(f), force="mesh")
    p = _template_params("mouthpiece", "alto")
    with profiles.params_scope(p):
        z = profiles.heel_z(p) * 0.885            # リガチャー座の中
        rt = profiles.outer_radius(p, z)
    v, e = mesh.vertices, mesh.edges_unique
    a, b = v[e[:, 0]], v[e[:, 1]]
    dz = b[:, 2] - a[:, 2]
    t01 = np.where(np.abs(dz) < 1e-12, np.nan,
                   (z - a[:, 2]) / np.where(np.abs(dz) < 1e-12, 1, dz))
    k = (t01 > 0) & (t01 < 1)
    P = a[k] + (b[k] - a[k]) * t01[k, None]
    R = np.hypot(P[:, 0], P[:, 1])
    on_arc = np.abs(R - rt) < 0.05
    ang = np.sort(np.unique(np.round(np.arctan2(P[on_arc, 1], P[on_arc, 0]), 6)))
    d = np.diff(ang)
    step = float(np.median(d[d > 1e-5]))
    assert math.degrees(step) < 1.5                       # 実測 0.86°
    # 弦誤差は設計クリアランスの刻み 0.05mm より 2 桁小さい（実測 0.0004mm）
    assert rt * (1 - math.cos(step / 2)) < 0.005


def test_mp_cad_matches_build(alto, alto_part, alto_part_cad, tmp_path):
    """プリミティブ表現が `build()` と**同じ形**であること。

    面の張り方だけを替えるのが Stage C-2 の趣旨なので、ここがこのステージの
    防波堤になる。残る差はすべて `build()` 側の近似（多角形母線の弦誤差・
    ルールドロフトの断面間補間）で、向きは常に「プリミティブ版の方が法則に近い」。
    実測（alto/tenor）: 体積差 +0.11%、表面距離 p95 0.045 / 最大 0.18mm。
    最大が出るのはビークが胴へ溶けるブレンド区間（多角形版が 1.9mm 刻みの
    ルールドで内側を通る所）と肩のテーパ。
    """
    import numpy as np
    import trimesh
    from saxsketch.analysis import meshdiff
    from saxsketch.export.models import check_mesh, export_model

    _, p = alto
    assert alto_part_cad.is_valid
    assert len(alto_part_cad.solids()) == 1
    f = tmp_path / "cad.stl"
    export_model(alto_part_cad, f, "stl")
    q = check_mesh(f)
    assert q["watertight"] and q["winding_consistent"], q

    dv = (alto_part_cad.volume - alto_part.volume) / alto_part.volume
    assert abs(dv) < 0.0025, dv

    ma = meshdiff.part_to_mesh(alto_part, tolerance=0.02)
    mb = meshdiff.part_to_mesh(alto_part_cad, tolerance=0.02)
    # bbox は `Shape.bounding_box()` ではなくテッセレーション後の頂点で測る。
    # 曲面の外接箱は制御点から取る緩いもので、回転体では実形状より大きく出る。
    assert np.abs(np.asarray(mb.bounds) - np.asarray(ma.bounds)).max() < 0.05

    d = trimesh.proximity.closest_point(ma, mb.vertices)[1]
    assert np.percentile(d, 95) < 0.08, np.percentile(d, 95)
    assert d.max() < 0.25, d.max()

    # 材料は増える側にしかずれない（多角形母線の弦が内側を通るぶん、多角形版が痩せている）
    assert dv > 0, dv


# ------------------------------------------------------------------ 仕様変更: 実物解剖

def test_mp_chamber_shapes_build_watertight(tmp_path):
    """4チェンバー形状 × 3サイズが水密ソリッドになる。"""
    from saxsketch.export.models import check_mesh, export_model
    reg = get_registry()
    for tmpl in ["soprano", "alto", "tenor"]:
        comp = reg.get("saxophone").make_component("mouthpiece", tmpl)
        base = {s.key: s.default for s in comp.param_specs()}
        for shape in ["round", "square", "horseshoe", "flat_sidewall"]:
            p = dict(base, chamber_shape=shape)
            part = comp.build(p)
            assert part.is_valid and part.volume > 5000, (tmpl, shape)
            f = tmp_path / f"{tmpl}_{shape}.stl"
            export_model(part, f, "stl")
            q = check_mesh(f)
            assert q["watertight"] and q["winding_consistent"], (tmpl, shape, q)


#: バッフル型 × ハンドル極値。掃引の種になる（型ごとに効くハンドルだけ振る）。
_BAFFLE_CASES = [
    ("straight", {}),
    ("rollover", {}),
    ("rollover", {"rollover_radius": 3.0}),
    ("rollover", {"rollover_radius": 20.0}),
    ("step", {}),
    ("step", {"baffle_plateau": 0.10}),
    ("step", {"baffle_plateau": 0.70}),
    ("step", {"baffle_step_rise": 0.85}),
    ("curve", {}),
    ("curve", {"baffle_curvature": -1.0}),
    ("curve", {"baffle_curvature": 1.0}),
]


def test_mp_baffle_types_build_watertight(tmp_path):
    """4バッフル型 × ハンドル極値が水密。段は `baffle_step_rise` で立てる。"""
    from saxsketch.export.models import check_mesh, export_model
    from saxsketch.instruments.saxophone.components import profiles as pf
    reg = get_registry()
    comp = reg.get("saxophone").make_component("mouthpiece", "tenor")
    base = {s.key: s.default for s in comp.param_specs()}
    for bt, kw in _BAFFLE_CASES:
        p = dict(base, baffle_type=bt, **kw)
        name = bt + "".join(f"_{k}{v}" for k, v in kw.items())
        part = comp.build(p)
        assert part.is_valid and part.volume > 5000, name
        f = tmp_path / f"baffle_{name}.stl"
        export_model(part, f, "stl")
        q = check_mesh(f)
        assert q["watertight"] and q["winding_consistent"], (name, q)

    # 段差はステーション間隔に依存しないよう、高さではなく**勾配**で見る。
    def max_ceiling_slope(**kw):
        win = [s for s in pf.cavity_stations(dict(base, **kw))
               if s["role"] == "window"]
        c = [(s["z"], s["yc"] + s["h"] / 2.0) for s in win]
        return max((b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(c, c[1:]))

    # 既定の step は実測どおりのなだらかな肩。段は rise を上げて初めて立つ。
    s_flat = max_ceiling_slope(baffle_type="step")
    s_sharp = max_ceiling_slope(baffle_type="step", baffle_step_rise=0.85)
    assert s_sharp > 2.0, s_sharp                     # 準垂直の段差面
    assert s_sharp > 2.5 * s_flat, (s_sharp, s_flat)
    # ストレートは棚の後ろが一定勾配＝勾配のばらつきが小さい（型の特徴）。
    st = [s for s in pf.cavity_stations(dict(base, baffle_type="straight"))
          if s["z"] > pf.baffle_plateau_end_z(dict(base, baffle_type="straight")) + 1.0
          and s["z"] < pf.window_end_z(base)]
    c = [(s["z"], s["yc"] + s["h"] / 2.0) for s in st]
    slopes = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(c, c[1:])]
    assert max(slopes) - min(slopes) < 0.05, slopes


def test_mp_baffle_progress_endpoints_and_monotone():
    """v(σ) は 4 型 × ハンドル極値で v(0)=0 / v(1)=1 / 単調非減少。

    単調性は「天井が z に対して逆流しない」＝ロフト面が折り返さないための
    必要条件。ここが破れると `_contain` の安全網が発動して形が折れる。
    """
    from saxsketch.instruments.saxophone.components import profiles as pf
    base = _template_params("mouthpiece", "tenor")
    for bt, kw in _BAFFLE_CASES:
        p = dict(base, baffle_type=bt, **kw)
        vs = [pf._baffle_progress(p, i / 1500.0) for i in range(1501)]
        assert vs[0] == pytest.approx(0.0, abs=1e-12), (bt, kw)
        assert vs[-1] == pytest.approx(1.0, abs=1e-12), (bt, kw)
        assert min(b - a for a, b in zip(vs, vs[1:])) >= -1e-12, (bt, kw)


def test_mp_baffle_step_default_is_the_measured_curve():
    """既定（step / plateau 0.36 / rise 0）は実測 `_CAVITY_C` と厳密に一致する。

    型の作り直しで**既定形状が動いていない**ことの担保。ここがずれると
    `cad/windycity/verify_base.py` の全項目（気柱 18.686cc 等）が一斉に動く。
    """
    from saxsketch.instruments.saxophone.components import profiles as pf
    p = _template_params("mouthpiece", "tenor")
    assert p["baffle_type"] == "step"          # テンプレート既定がステップ型
    err = max(abs(pf._baffle_progress(p, i / 2000.0)
                  - pf._pchip(pf._CAVITY_C, i / 2000.0)) for i in range(2001))
    assert err < 1e-12, err


def test_mp_baffle_plateau_clamped_per_type():
    """棚の長さは型ごとに制限される＝「型の形状的特徴」が構造的に保たれる。"""
    from saxsketch.instruments.saxophone.components import profiles as pf
    base = _template_params("mouthpiece", "tenor")
    for bt in ("straight", "curve"):
        assert pf.baffle_plateau(dict(base, baffle_type=bt, baffle_plateau=0.75)) <= 0.12
    for bt in ("step", "rollover"):
        assert pf.baffle_plateau(dict(base, baffle_type=bt, baffle_plateau=0.75)) == 0.70
        assert pf.baffle_plateau(dict(base, baffle_type=bt, baffle_plateau=0.0)) == 0.10


def test_mp_baffle_keeps_tip_rail_law():
    """どの型・どのハンドル値でも「窓の開き始め＝ティップレール幅」が保たれる。

    棚の下限を 0 にしない理由がこれ（`profiles._PLATEAU_RANGE`）。ティップ側で
    ランプを立てると天井がリード面を横切る z が前へずれ、指定より細いレールになる。
    """
    from saxsketch.instruments.saxophone.components import profiles as pf
    for tmpl in ("soprano", "alto", "tenor"):
        base = _template_params("mouthpiece", tmpl)
        for bt, kw in _BAFFLE_CASES:
            p = dict(base, baffle_type=bt, **kw)
            d = pf.window_open_z(p) - pf.window_front_z(p)
            assert abs(d) < 0.10, (tmpl, bt, kw, d)


def test_mp_chamber_area_ratio_holds():
    """chamber_ratio（面積比）がクランプ前で全形状 成立する。"""
    from saxsketch.instruments.saxophone.components import profiles as pf
    p0 = _template_params("mouthpiece", "tenor")
    for shape in ["round", "square", "horseshoe", "flat_sidewall"]:
        p = dict(p0, chamber_shape=shape)
        w_ch, h_ch = pf.chamber_size(p)
        a_ch = pf.section_area({"yc": 0.0, "h": h_ch, "w": w_ch,
                                "n": pf._chamber_n(p), "shape": shape})
        r_t = pf.throat_radius(p)
        a_th = pf.superellipse_area(2 * r_t, 2 * r_t, pf._throat_n(p))
        assert a_ch / a_th == pytest.approx(p["chamber_ratio"], rel=1e-3), shape


def test_mp_section_area_matches_shoelace():
    """section_area は非対称形でシューレース一致、round/square は解析式と一致。"""
    from saxsketch.instruments.saxophone.components import profiles as pf
    for shape in ["horseshoe", "flat_sidewall"]:
        s = {"yc": 1.0, "h": 8.0, "w": 12.0, "n": 2.6, "shape": shape}
        assert pf.section_area(s) == pytest.approx(pf._polygon_area(pf.section_pts(s)))
    for shape, n in [("round", 2.2), ("square", 3.8)]:
        s = {"yc": 0.0, "h": 8.0, "w": 12.0, "n": n, "shape": shape}
        assert pf.section_area(s) == pytest.approx(pf.superellipse_area(12.0, 8.0, n))
    # 断面点数は全形状で一定（ルールドロフトがねじれない前提）
    counts = {len(pf.section_pts({"yc": 0.0, "h": 8.0, "w": 12.0, "n": 2.6,
                                  "shape": sh}))
              for sh in ["round", "square", "horseshoe", "flat_sidewall"]}
    assert counts == {pf._SECTION_SAMPLES}


def test_mp_tier1_round_baseline():
    """round/rollover テナーの内容積が基準と一致（校正保全）。

    基準値は **実物 WindyCity Tenor .100" LS の実測 18.59cc** に対して 1% 以内。
    以前の 19.636747 は実物実測へ作り直す前の形状のもので、Stage A で形状が
    変わったあと更新されていなかった（ずっと落ちていた）。ここが動いたら
    音響 Tier1 の校正が動いたということなので、意図した変更か必ず確認すること。
    18.7757 → 18.6862 は Stage C-1b（天井の横アーチとティップの管幅）で
    意図的に動かした分。実測 18.59 との差は 1.0% → 0.5% へ縮んでいる。
    """
    from saxsketch.instruments.saxophone.components import profiles as pf
    p = _template_params("mouthpiece", "tenor")
    v = pf.cavity_volume_cc(p)
    assert v["total_cc"] == pytest.approx(18.6862, abs=2e-3)
    assert v["total_cc"] == pytest.approx(18.59, rel=0.02)   # 実測との一致
    assert v["effective_cc"] == pytest.approx(v["total_cc"] - 4.9938, abs=2e-3)


def test_mp_shape_enums():
    """バッフルは curve を含み high を含まない。チェンバーは4形状。"""
    reg = get_registry()
    specs = {s.key: s for s in
             reg.get("saxophone").make_component("mouthpiece", "tenor").param_specs()}
    bvals = [c.value for c in specs["baffle_type"].choices]
    assert "curve" in bvals and "high" not in bvals
    cvals = {c.value for c in specs["chamber_shape"].choices}
    assert cvals == {"round", "square", "horseshoe", "flat_sidewall"}


def test_mp_anatomy_regions():
    """各部名称マップにランプ/バレル/ウォールが含まれ z∈[0,L]。"""
    from saxsketch.instruments.saxophone.components import profiles as pf
    p = _template_params("mouthpiece", "tenor")
    regs = pf.anatomy_regions(p)
    parts = {r["part"] for r in regs}
    assert {"ランプ", "バレル", "ウォール"} <= parts
    L = p["overall_length"]
    for r in regs:
        assert 0.0 <= r["z0"] <= r["z1"] <= L + 1e-6, r


# ------------------------------------------------------------------ 音響

def test_tier2_directions(alto):
    from saxsketch.acoustics.brightness import tone_metrics
    _, p = alto
    base = tone_metrics(p)
    hi = dict(p); hi["baffle_height"] = 5.0
    assert tone_metrics(hi)["brightness"] > base["brightness"]
    big_throat = dict(p); big_throat["throat_ratio"] = 1.35
    assert tone_metrics(big_throat)["brightness"] < base["brightness"]


def test_goalseek_moves_toward_target(alto):
    from saxsketch.acoustics.goalseek import goal_seek
    comp, p = alto
    result = goal_seek(p, comp.param_specs(), {"brightness": 8.0},
                       comp.goal_seek_size_info(), comp.cavity_volume)
    from saxsketch.acoustics.brightness import tone_metrics
    q = dict(p); q.update(result["proposal"])
    assert tone_metrics(q)["brightness"] > tone_metrics(p)["brightness"]


def test_harmonics_shape(alto):
    comp, p = alto
    sim = comp.simulate(p)
    amps = sim["harmonics"]["amplitudes"]
    assert len(amps) == 16
    assert max(amps) == pytest.approx(1.0)


# ------------------------------------------------------------------ 音響 Tier3（インピーダンス）

def test_build_resonator_geometry(alto):
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    geom = ob.build_resonator(p, comp.goal_seek_size_info())
    xs = [x for x, _ in geom]
    rs = [r for _, r in geom]
    assert xs == sorted(xs)              # x 単調増加
    assert all(r > 0 for r in rs)        # 半径は正
    assert xs[-1] > 0.5                  # 組み立て管はアルトで ~1m 級
    assert rs[-1] > rs[0]                # ベル側が広い（円錐拡張）


def test_tmm_impedance_peaks(alto):
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    res = ob.impedance(p, comp.goal_seek_size_info())
    assert res["engine"] in ("tmm", "openwind")
    assert len(res["freqs"]) == len(res["z_db"]) > 0
    assert res["freqs"] == sorted(res["freqs"])   # 周波数格子は単調
    assert len(res["peaks"]) >= 1
    assert 40.0 < res["peaks"][0]["freq"] < 500.0  # 第1ピークは実音域


def test_impedance_param_sensitivity(alto):
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    si = comp.goal_seek_size_info()
    # スロートはマウスピース内部だけを変える。組み立て管 1.1m のうち 81mm しか
    # 占めないので第1共鳴はほとんど動かず、上位共鳴ほど大きく動く（実物と同じ振る舞い）。
    # Phase 2 では throat_ratio が本体の円錐テーパーまで書き換えていたため
    # 第1ピークが大きく動いていた。それは欠損円錐を体積定数から逆算していた副作用。
    base = ob.impedance(p, si)["peaks"]
    narrow = ob.impedance(dict(p, throat_ratio=0.7), si)["peaks"]
    # 単一ピークで見ない: 個々の移動量は 0.5〜0.8Hz と小さく、上位共鳴の総和で
    # 見るほうが「ノブが効いているか」の判定として安定する。
    #
    # しきい値 1.5Hz は**実測形状で実際に出る量**（3.01Hz）の半分から取っている。
    #
    # 直前の 3.0Hz は 4.9Hz という観測から取ったものだったが、あの 4.9 は周波数
    # 格子の量子化産物だった。当時の `impedance()` は線形格子 2.44Hz 刻みでピークを
    # 格子点のまま読んでいて、ピーク別の移動量が 0.00 / 0.00 / 2.40 / 2.40 / 0.00 /
    # 2.50 / 0.00 / 0.00 と**全部 0 か 1 格子ちょうど**に張り付いていた。対数格子＋
    # ピーク補間（`openwind_bridge._interp_peak`）に直すと 0.08 / 0.26 / 0.53 / 0.70 /
    # 0.62 / 0.53 / 0.78 / 0.39 と揃い、総和が 4.90 → 3.01Hz になる。
    # 導出手順（実測値から取る）は変えずに、直った実測値でやり直した値がこれ。
    #
    # さらに以前の 12.0Hz は旧形状の値で、当時はボア長がアルトで 26mm しかなく、
    # チェンバー〜スロートの区間が 3 倍長かった。実測の WindyCity はボアが全長の
    # 半分以上を占めるので、スロートは短い局所的な絞りにしかならない。合格させに
    # 行くのではなく「ノブが死んでいない」ことだけを見る。
    #
    # **2026-09-05: 3.01 → 1.372Hz。** アルトへ PHROX の窓の実測が入って
    # `window_length` が 35.02 → 38.67 になったぶん。窓が長いほどチェンバー〜
    # スロートの区間が短くなり、`throat_ratio` の梃子が短くなる。**床の特異点を
    # 直したぶんではない**（旧テンプレで 2.854 → 2.853 と 0.001 しか動かない）。
    #
    # なお 06e67ab の間はここが 2.588 で通っていたが、**そのときピークは 8 本しか
    # 出ていなかった**（特異点で床が 3.5 倍深く、高次が平たくなって検出から落ちた）。
    # 直すと 12 本に戻り、同じ 12 本どうしで比べた値が 1.372。**06e67ab で
    # 「共鳴 12 → 8 は窓の長さの効果」と書いたのは誤りで、あれはバグだった。**
    # 閾値は従来どおり観測値の半分に置く。
    shift = sum(abs(narrow[i]["freq"] - base[i]["freq"]) for i in range(3, 8))
    assert len(base) == len(narrow) == 12, (len(base), len(narrow))
    assert shift > 0.68, [(b["freq"], n["freq"]) for b, n in zip(base, narrow)]
    assert abs(narrow[0]["freq"] - base[0]["freq"]) < 1.0     # 第1共鳴はほぼ不変


def test_acoustics_impedance_endpoint():
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "alto",
        "component_id": "mouthpiece"})
    r = c.get("/api/acoustics/impedance")
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] in ("tmm", "openwind")
    assert len(body["peaks"]) >= 1


def test_openwind_first_peak_reasonable(alto):
    pytest.importorskip("openwind")
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    res = ob.impedance(p, comp.goal_seek_size_info())
    assert res["engine"] == "openwind"
    assert 40.0 < res["peaks"][0]["freq"] < 400.0


# Tier2（インピーダンス）で実測した第1共鳴の残差 [cent]。
#
# **±20 セント以内という判定はやめた。** 以前の記録値 -53.6 / -40.1 / -43.5 は
# 周波数格子に張り付いた数字で、形状の測定値ではなかった。`impedance()` が
# `linspace(50, 2000, 800)` を張り（ΔF = 2.441Hz）、ピークを格子点のまま読んで
# いたため、低音の 1 目盛りが soprano 20.9 / alto 30.9 / tenor 41.2 セント。
# **3 サイズとも「±20 セント」が 1 目盛りより細かく**、格子がたまたま乗ったときしか
# 通らなかった。ずれの向きがサイズごとにバラバラだったのも量子化の証拠。
#
# 対数格子＋ピーク補間（`_interp_peak`）に直したうえで取り直した値が下。細格子
# 0.02Hz で確かめた真値 -61.5 / -26.3 / -22.3 との差は 0.3 / 1.2 / 0.9 セント。
#
# 主張を「20 セント以内に収まる」から「この値である」へ変えてある。閾値の緩和では
# なく、TIER1_RESIDUAL_CENTS と同じ「変化の検知」に揃えた。
#
# Stage E で 2 度目の取り直し。-61.2 / -27.5 / -23.2 には**物差し側の偏りが 2 つ**
# 乗っていた（詳細は TIER1_RESIDUAL_CENTS のコメント）: ジオメトリとソルバの音速の
# 食い違い（+20.7 セント）と、放射端補正を持たない延長円錐長（-44〜-52 セント）。
# どちらもマウスピースの形状とは無関係な量。
#
# Stage F で 3 度目。soprano だけ動いた（-30.5 → -2.1）。形状ではなく実測が入った
# ため: 全長 87.52（テナー実測 × リード規格長比 0.8141）→ **71.4（実測）**、
# ボア長 46.81 → **38.3（実測）**、コーク挿入深さ 17.91（当て推量）→ 23.5
# （目標音が鳴る挿し込み量）。alto/tenor は触っていないので動いていない。
TIER2_RESIDUAL_CENTS = {"soprano": -2.1, "alto": 0.9, "tenor": 1.3}


def test_resonator_extension_replaces_missing_cone():
    """気柱がコーク線で終わり、延長円錐がネック小端内径から始まること。

    かつて延長長にマウスピースの**物理長**を使っていて 3サイズとも約 270 セント
    低かった。それを欠損円錐長に直した後も -44〜-96 セント残っていたが、原因は
    気柱をシャンク端まで数えていたこと（ネックのテノンが埋めている体積を空気として
    数えていた。ソプラノで 3.6cc ＝ マウスピース内容積の 44%）と、円錐の始端が
    マウスピースのボア半径だったこと（コルクを逃がすぶん太い）。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    from saxsketch.acoustics import volume as ac_volume
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        si = _size_info(tid)
        geo = ob.build_resonator(p, si)
        cone = ac_volume.missing_cone(si)
        x_cork = (p["overall_length"] - p["cork_depth"]) / 1000.0
        # 気柱はコーク線で終わり、そこから先が延長円錐
        assert geo[-2][0] == pytest.approx(x_cork + ob.NECK_STEP, abs=1e-6), tid
        # 円錐の始端はネック小端内径。マウスピースのボアより細い
        r_neck = cone["throat_radius_mm"] / 1000.0
        assert geo[-2][1] == pytest.approx(r_neck, abs=1e-6), tid
        assert r_neck < profiles.bore_radius(p) / 1000.0, tid

        # 延長円錐は naive な `c/(2·f1) − x0` より**短い**。差が開口端の放射補正で、
        # 実測 soprano 25.4 / alto 35.2 / tenor 43.1mm。ここが 0 に戻ったら
        # `_calibrate_extension` が効いていない（＝基準管が 45〜52 セント低い状態）。
        naive = (ob.C_SOUND / (2.0 * si["low_note_sounding_hz"])
                 - cone["apex_distance_mm"] / 1000.0)
        assert 0.015 < naive - (geo[-1][0] - x_cork) < 0.060, tid

        res = ob.impedance(p, si)
        assert res["first_cents_vs_target"] == pytest.approx(
            TIER2_RESIDUAL_CENTS[tid], abs=3.0), (tid, res["first_note"])


def test_ideal_cone_reference_sounds_the_target_note():
    """マウスピースを理想の欠損円錐に戻した基準管が、実際に目標低音で鳴ること。

    これが延長円錐の長さの**定義**になっている。以前は `l_ext = c/(2·f1) − x0` と
    置いていたが、これは開口端の放射補正がゼロの理想円錐の式で、実際のソルバは
    放射を含む。マウスピースが 1 本も刺さっていない基準管だけで
    soprano -52.3 / alto -48.2 / tenor -44.5 セント低く、報告していた残差の
    ほとんどがこれだった。

    ここが 0 でないと、Tier1/Tier2 の残差が「マウスピースのせい」ではなくなる。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    for tid in SIZES:
        si = _size_info(tid)
        f1 = si["low_note_sounding_hz"]
        for use_ow in (False, True):
            if use_ow and not ob.HAS_OPENWIND:
                continue
            geo = ob.ideal_cone_geometry(si, use_openwind=use_ow)
            f = ob._first_peak_hz(geo, 0.6 * f1, 1.7 * f1, use_openwind=use_ow)
            assert 1200.0 * math.log2(f / f1) == pytest.approx(0.0, abs=0.5), (
                tid, use_ow, f, f1)


def test_tier1_and_tier2_agree():
    """同じ形状で、速いエンジン（Tier1=TMM）と正確なエンジン（Tier2=OpenWind）の
    第1共鳴が一致すること。

    このテストは Stage E まで書けなかった。ジオメトリを音速 343 で組みながら
    OpenWind を 25℃（347.13）で走らせていたので、**同じジオメトリなのに
    23.9 / 24.7 / 26.0 セント**離れていた。音速を 1 箇所（`TEMPERATURE_C`）に
    してから 1 セント以内に入る。

    延長円錐の校正はエンジンごとに別々に走る（基準管が 0 セントになる長さ）ので、
    一致すること自体は自明ではない —— 校正が固定するのは**理想円錐**で、実測形状の
    マウスピースが刺さった管はどちらのエンジンも独立に解いている。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    if not ob.HAS_OPENWIND:
        pytest.skip("OpenWind 未導入（両者が同じ TMM になり検証にならない）")
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        si = _size_info(tid)
        tmm = ob.first_resonance_cents(p, si)
        ow = ob.impedance(p, si)["first_cents_vs_target"]
        assert ow == pytest.approx(tmm, abs=3.0), (tid, tmm, ow)


def test_sound_speed_matches_openwind_physics():
    """自前の `sound_speed()` が OpenWind の `Physics` と一致すること。

    式を写してあるのは OpenWind 未導入の環境でも同じ音速を使うため。写し間違えると
    ジオメトリの全長（`c/(2·f1)` 由来）とソルバがまた食い違う ——
    343.0 と 347.13 の差 1.2% が 20.7 セントになったのが Stage E の出発点。
    """
    pytest.importorskip("openwind")
    from openwind.continuous.physics import Physics
    from saxsketch.acoustics import openwind_bridge as ob
    for t in (0.0, 20.0, ob.TEMPERATURE_C, 37.0):
        assert ob.sound_speed(t) == pytest.approx(float(Physics(t).c(0)), rel=1e-12)
    assert ob.C_SOUND == pytest.approx(ob.sound_speed(ob.TEMPERATURE_C))


# ------------------------------------------------------------------ 音響 Tier3（音合成）

def test_coarsen_keeps_the_bore_step(alto):
    """間引いても**段差は残る**こと（零長の不連続として）。

    以前ここは「最終セグメント以外は最小間隔 `SIM_MIN_DX` を満たす」と主張して
    いた。**それがまさに間違っていた不変条件**で、その規則がマウスピースのボアから
    ネック小端への段差（alto で 7.90 → 6.35mm、前の点の 0.5mm 後ろ）を捨てていた。
    捨てると第1共鳴が −67 セントずれ、共鳴列が非調和になる
    （`test_coarsen_preserves_the_resonance_ladder`）。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    geom = ob.build_resonator(p, comp.goal_seek_size_info())
    co = ob._coarsen(geom)
    assert co[0] == list(geom[0]) and co[-1] == list(geom[-1])
    assert len(co) <= len(geom)
    # 段差はちょうど 1 本、零長で入っていること（零長でないと CFL が 2 倍痛む）
    steps = [i for i in range(len(co) - 1) if co[i + 1][0] == co[i][0]]
    assert len(steps) == 1, [(round(x, 5), round(r, 5)) for x, r in co]
    i = steps[0]
    assert co[i + 1][1] < co[i][1], co[i:i + 2]          # ボア → ネック小端は細る
    # 段差以外は最小間隔を満たす（末尾は両端保持のため例外）
    gaps = [co[k + 1][0] - co[k][0] for k in range(len(co) - 2) if k != i]
    assert all(g >= ob.SIM_MIN_DX for g in gaps)


def test_coarsen_preserves_the_resonance_ladder(alto):
    """間引いた管の共鳴列が生の管と一致すること。**H.1 の再発防止の本体。**

    段差を落とすと共鳴列が引き伸ばされて非調和になり（alto で n3 が 3.006 →
    3.162 ＝ 5% シャープ）、高次モードの Q が 10〜40 倍に膨らむ。その状態では
    基音より上のレジームが安定できず、リードがモードを渡り歩く。音程が合って
    いるかだけでは捕まらないので、**比**まで見る。

    実測（3 サイズ、段差を残した場合の 生 → 間引き後）:
      soprano 207.47 → 207.19 (−0.13%) / alto 138.69 → 138.58 (−0.08%)
      tenor   103.92 → 103.79 (−0.13%)
    """
    pytest.importorskip("openwind")
    import numpy as np
    from openwind import ImpedanceComputation
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    freqs = np.geomspace(60.0, 900.0, 3000)

    def ladder(geo):
        z = np.abs(np.asarray(ImpedanceComputation(
            freqs, geo, temperature=ob.TEMPERATURE_C,
            source_location="entrance").impedance))
        y = 20.0 * np.log10(z / np.max(z) + 1e-12)
        peaks = [i for i in range(1, len(y) - 1)
                 if y[i] > y[i - 1] and y[i] > y[i + 1]][:3]
        return [float(freqs[i]) for i in peaks]

    geom = ob.build_resonator(p, comp.goal_seek_size_info())
    raw, co = ladder(geom), ladder(ob._coarsen(geom))
    assert co[0] == pytest.approx(raw[0], rel=0.005), (raw, co)
    for k in (1, 2):
        assert co[k] / co[0] == pytest.approx(raw[k] / raw[0], rel=0.01), (raw, co)


def test_embouchures_share_the_blowing_ratio(alto):
    """3 アンブシュアの吹奏比 γ が揃っていること（OpenWind 不要の純計算）。

    以前は吹圧をプリセットごとの定数で持っていて、`pulsation` だけ書き換えて
    `mass` / `section` を CLARINET のまま残していたので、静的ビーティング圧
    `p_M = ω₀²·(M/S)·y₀` が ω₀² で動き、γ が **1.14 / 0.70 / 0.30** とばらけて
    いた。γ>1 は静的変位が静止開口を超える領域。「締め具合」を選ばせている
    つもりで、実際に選ばせていたのは吹きすぎ具合だった。
    """
    pytest.importorskip("openwind")
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    for emb, f_base in ob.EMBOUCHURES.items():
        _, mouth_pa = ob._reed_player(p, emb)
        f_reed = f_base * (23.0 / p["facing_length"])
        p_m = ob.beating_pressure(f_reed, 4e-4 * (p["tip_opening"] / 1.8))
        assert mouth_pa / p_m == pytest.approx(ob.BLOWING_RATIO, rel=1e-9), emb
    # 締めるほどリード共振が高い（名前と物理の向きが一致していること）
    assert (ob.EMBOUCHURES["loose"] < ob.EMBOUCHURES["normal"]
            < ob.EMBOUCHURES["tight"])


def test_synthesize_returns_playable_wav(alto):
    pytest.importorskip("openwind")
    import io
    import wave
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    si = comp.goal_seek_size_info()
    # duration は既定のまま。短くすると定常に達せず高次モードで鳴いてしまう。
    wav, meta = ob.synthesize(p, si, embouchure="normal")
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getframerate() == ob.SIM_SR
        assert w.getnframes() > 0
    # **鳴るのはこの管の第1共鳴。** Stage F ではこの主張を外していた（当時の
    # 実測は loose 1220 / normal 951 / tight 133Hz と 3 通りばらけ、上位成分が
    # 5 本あり、duration を 0.6→1.2s にすると支配成分が 950 → 1083Hz へ移って
    # いた）。原因は `_coarsen` がボア → ネック小端の段差を落として共鳴列を
    # 非調和にしていたことで、直すと 3 アンブシュアとも第1共鳴に落ち着く。
    # 外していた主張が戻せる状態になったので戻す —— これが `_coarsen` の
    # 退行に対する一番効く検査になる。
    #
    # 3 サイズ × 3 アンブシュアの実測（f0 / 第1共鳴、セント）:
    #
    #   alto     loose −13.6  normal  −7.3  tight  −4.8
    #   tenor    loose  −0.4  normal  −2.1  tight  −2.1
    #   soprano  loose  ****  normal −21.5  tight −11.4
    #
    # **9 通り中 8 通りが第1共鳴。soprano の loose だけ 67.8Hz ＝ f1 の 0.327 倍**
    # （207.47/3 = 69.2 に近い）で、周期 3 倍化のレジームに落ちている。γ を
    # 揃えても残るので `_coarsen` の話ではなく、リード共振（soprano loose は
    # f_reed 2070Hz ＝ f1 の 10.0 倍）と非線形の組合せ。ここでは既定の
    # alto/normal だけを検査し、soprano loose は既知として記録に留める。
    f1 = ob._first_peak_hz(ob.build_resonator(p, si),
                           0.6 * si["low_note_sounding_hz"],
                           1.7 * si["low_note_sounding_hz"])
    assert meta["f0"] == pytest.approx(f1, rel=0.03), (meta, f1)


# ------------------------------------------------------------------ プロジェクトI/O

def test_project_roundtrip(tmp_path):
    proj = Project(instrument_id="saxophone", template_id="alto",
                   component_id="mouthpiece", name="テスト",
                   params={"tip_opening": 2.1})
    f = tmp_path / "t.wproj"
    proj.save(f)
    loaded = Project.load(f)
    assert loaded.name == "テスト"
    assert loaded.params["tip_opening"] == 2.1


def test_project_refs_roundtrip(tmp_path):
    """参照スナップショットの往復と、refs 無しの旧 .wproj の後方互換。"""
    import json
    import zipfile
    refs = {"mouthpiece": {"source": "/tmp/mp.wproj", "label": "M5",
                           "params": {"body_dia": 27.5}}}
    proj = Project(instrument_id="saxophone", template_id="alto",
                   component_id="reed", name="リード", params={"tip_thickness": 0.5},
                   refs=refs)
    f = tmp_path / "r.wproj"
    proj.save(f)
    assert Project.load(f).refs == refs

    # refs キーが無い旧形式（Phase 2 以前の .wproj）
    old = tmp_path / "old.wproj"
    with zipfile.ZipFile(old, "w") as zf:
        zf.writestr("project.json", json.dumps({
            "schema_version": 1, "instrument_id": "saxophone",
            "template_id": "alto", "component_id": "mouthpiece",
            "name": "旧", "params": {"tip_opening": 1.9}}))
    loaded = Project.load(old)
    assert loaded.refs == {} and loaded.params["tip_opening"] == 1.9


def test_open_reports_migrated_params(tmp_path):
    """旧 `plate_type` の .wproj を開くと変換され、**報告が応答に載る**こと。

    `ParamSet.apply` は未知キーを黙って捨てるので、フックが無いと利用者の設定が
    理由も無く既定へ落ちる。「黙って値が変わらない」ことの端から端までの固定。
    """
    import json
    import zipfile
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)

    old = tmp_path / "legacy_lig.wproj"
    with zipfile.ZipFile(old, "w") as zf:
        zf.writestr("project.json", json.dumps({
            "schema_version": 1, "instrument_id": "saxophone",
            "template_id": "alto", "component_id": "ligature",
            "name": "旧リガチャー",
            "params": {"band_width": 16.0, "plate_type": "plain"}}))
    r = c.post("/api/project/open", json={"path": str(old)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["params"]["contact_type"] == "face"          # 全面 → 面接触
    assert body["params"]["closure"] == "screw_beak"
    assert "plate_type" not in body["params"]
    assert len(body["notices"]) == 1 and "圧力プレート" in body["notices"][0]
    # 値を触ったら報告は役目を終える（トーストが残り続けない）
    assert c.put("/api/project/params",
                 json={"params": {"band_width": 15.5}}).status_code == 200
    assert c.get("/api/project").json()["notices"] == []

    # 新規プロジェクトには報告が付かない
    r = c.post("/api/project/new", json={"instrument_id": "saxophone",
                                         "template_id": "alto",
                                         "component_id": "ligature"})
    assert r.json()["notices"] == []


def test_reference_endpoint(tmp_path):
    """参照マウスピースの差替えが寸法に伝播し、不正な .wproj は 400 になること。"""
    from fastapi.testclient import TestClient
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)

    # 差し替え元: ボディ径を広げたマウスピース プロジェクト
    src = tmp_path / "wide.wproj"
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "mouthpiece"})
    c.put("/api/project/params", json={"params": {"body_dia": 30.0}})
    c.post("/api/project/save", json={"path": str(src)})

    r = c.post("/api/project/new", json={"instrument_id": "saxophone",
                                         "template_id": "alto",
                                         "component_id": "ligature"})
    assert r.status_code == 200
    ref = r.json()["reference"]
    assert ref["component_id"] == "mouthpiece" and ref["source"] is None
    p = dict(STATE.paramset.values)
    before = lp.inner_radius(STATE.component.ref_params(), p)

    r = c.post("/api/project/reference", json={"component": "mouthpiece",
                                               "path": str(src)})
    assert r.status_code == 200
    assert r.json()["reference"]["source"] == str(src)
    after = lp.inner_radius(STATE.component.ref_params(), p)
    base_m = _template_params("mouthpiece", "alto")
    base_dia = base_m["body_dia"]
    # 座は最大径の位置ではないので、内周は `body_dia` の差そのものではなく
    # **座での外形比**（0.974）を掛けた分だけ動く。伝播したことの検証が目的。
    s0, s1 = profiles.ligature_seat_range(base_m)
    ratio = profiles.outer_radius(base_m, (s0 + s1) / 2.0) / (base_dia / 2.0)
    assert after == pytest.approx(before + ratio * (30.0 - base_dia) / 2.0, abs=0.02)

    # 既定へ戻す
    assert c.post("/api/project/reference",
                  json={"component": "mouthpiece", "path": None}).status_code == 200
    assert lp.inner_radius(STATE.component.ref_params(), p) == pytest.approx(
        before, abs=1e-9)

    # マウスピース以外の .wproj は受け付けない
    bad = tmp_path / "bad.wproj"
    c.post("/api/project/save", json={"path": str(bad)})   # 現在=リガチャー
    assert c.post("/api/project/reference",
                  json={"component": "mouthpiece",
                        "path": str(bad)}).status_code == 400


def test_ref_overlay_is_declared_by_the_component():
    """重ねられるかは**コンポーネントが宣言する**こと（UI に楽器固有の知識を置かない）。

    リガチャーの断面はマウスピースの z でそのまま張られているので重ねられる。
    リードは参照を持つが**自分の座標系**（テーブル面が y=0・先端が z=0）なので
    重ねられない —— 参照の有無ではなく座標系で分かれる、が要点。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)

    def new(component_id):
        return c.post("/api/project/new",
                      json={"instrument_id": "saxophone", "template_id": "alto",
                            "component_id": component_id}).json()

    assert new("mouthpiece")["reference"] is None      # 参照を持たない
    assert new("reed")["reference"]["overlay"] is False
    ref = new("ligature")["reference"]
    assert ref["overlay"] is True
    assert isinstance(ref["hash"], str) and len(ref["hash"]) == 12


def test_ref_model_is_404_without_a_shared_frame():
    """座標系が一致しないコンポーネントでは参照モデルを出さないこと。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)

    for component_id in ("mouthpiece", "reed"):
        c.post("/api/project/new",
               json={"instrument_id": "saxophone", "template_id": "alto",
                     "component_id": component_id})
        assert c.get("/api/ref/model.stl").status_code == 404


def test_ref_model_is_the_reference_mouthpiece(tmp_path):
    """`/api/ref/model.stl` が**マウスピース**を返すこと（リガチャーではない）。

    どちらも「それらしい」STL なので、取り違えは目では気づけない。量で切り分ける
    —— マウスピースは全長 91.7mm・半径 14.55mm、リガチャーの帯は 16mm 幅。
    """
    from fastapi.testclient import TestClient
    from saxsketch.analysis import meshdiff
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)

    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "ligature"})
    r = c.get("/api/ref/model.stl")
    assert r.status_code == 200
    f = tmp_path / "ref.stl"
    f.write_bytes(r.content)
    lo, hi = meshdiff.load_mesh(str(f)).bounds

    m = _template_params("mouthpiece", "alto")
    assert hi[2] - lo[2] == pytest.approx(m["overall_length"], abs=0.2)
    assert hi[0] == pytest.approx(m["body_dia"] / 2.0, abs=0.2)
    # リガチャーの帯（16mm）を返していないこと
    assert hi[2] - lo[2] > 4.0 * STATE.paramset.values["band_width"]


def test_ref_model_is_cached_by_the_reference(tmp_path, monkeypatch):
    """参照 STL は**参照が変わったときだけ**作ること。

    マウスピースのビルドは 5.7 秒（リガチャー本体の 4.4 倍）。スライダーを
    動かすたびに作り直すと、ワーカが 1 本しか無いので本体の再生成まで待たされる。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE, AppState
    c = TestClient(app)

    built = []
    original = AppState._build_stl

    def counting(self, spec):
        built.append(spec["component_id"])
        return original(self, spec)

    monkeypatch.setattr(AppState, "_build_stl", counting)

    # 差し替え用に body_dia だけ違うアルトのマウスピース
    wide = tmp_path / "wide.wproj"
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "mouthpiece"})
    c.put("/api/project/params", json={"params": {"body_dia": 30.0}})
    c.post("/api/project/save", json={"path": str(wide)})

    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "ligature"})
    before = STATE.ref_hash()
    built.clear()
    assert c.get("/api/ref/model.stl").content == c.get("/api/ref/model.stl").content
    assert built == ["mouthpiece"]                 # 2 回叩いてビルドは 1 回

    # パラメータを動かしても参照は作り直さない（鍵は refs だけで決まる）
    c.put("/api/project/params", json={"params": {"band_width": 15.5}})
    assert c.get("/api/ref/model.stl").status_code == 200
    assert built == ["mouthpiece"]

    # 参照を差し替えたら鍵が変わり、作り直す
    c.post("/api/project/reference", json={"component": "mouthpiece",
                                           "path": str(wide)})
    assert STATE.ref_hash() != before
    assert c.get("/api/ref/model.stl").status_code == 200
    assert built == ["mouthpiece", "mouthpiece"]


def test_frozen_refs_marks_stale(tmp_path):
    """参照差替えが凍結を陳腐化させ、入稿に古い編集モデルが混ざらないこと。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)

    # 差替え用に body_dia だけ違うアルトのマウスピースを用意
    wide = tmp_path / "wide.wproj"
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "mouthpiece"})
    c.put("/api/project/params", json={"params": {"body_dia": 30.0}})
    c.post("/api/project/save", json={"path": str(wide)})

    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "ligature"})
    e = c.post("/api/export", json={"formats": ["stl"], "make_package": False,
                                    "out_dir": str(tmp_path / "frozen"),
                                    "freeze": True})
    assert e.status_code == 200 and not STATE.is_stale()

    r = c.post("/api/project/reference", json={"component": "mouthpiece",
                                               "path": str(wide)})
    assert r.status_code == 200
    assert STATE.is_stale(), "参照を差し替えたのに陳腐化していない"
    assert r.json()["manual_edit"]["stale"] is True

    # 編集済みモデルを登録した状態なら入稿が止まる
    STATE.project.derived_stl = b"dummy"
    STATE.project.derived = {"imported_at": "x", "source_file": "x",
                             "quality": {}, "analysis": {}}
    blocked = c.post("/api/export", json={"formats": ["stl"],
                                          "out_dir": str(tmp_path / "blocked"),
                                          "make_package": False})
    assert blocked.status_code == 409


def test_frozen_without_refs_is_backward_compatible():
    """refs キーを持たない Phase 3 以前の凍結でも例外にならず陳腐化しない。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "ligature"})
    STATE.project.frozen = {"frozen_at": "2026-01-01T00:00:00Z",
                            "params": dict(STATE.paramset.values),
                            "solid_volume_cc": None, "export_dir": None}
    assert STATE.is_stale() is False


# ------------------------------------------------------------------ セット（Phase 4-D）


def _new_set(c, template_id="alto"):
    return c.post("/api/project/new", json={"instrument_id": "saxophone",
                                            "template_id": template_id,
                                            "set_id": "mouthpiece_set"})


def test_set_new_creates_required_members_only():
    """セット新規は**必須メンバーだけ**作り、土台を選択状態にすること。

    任意の部品（リード）を先に作ると、設計していない物の寸法が設計値の顔をして
    従属部品へ流れる。「まだ設計していない」が正しい初期状態。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    r = _new_set(c)
    assert r.status_code == 200
    info = r.json()["set"]
    assert info["active"] == "mouthpiece"
    present = {m["component_id"]: m["present"] for m in info["members"]}
    assert present == {"mouthpiece": True, "ligature": True, "reed": False}
    assert info["addable"] == ["reed"]
    assert list(STATE.project.members) == ["mouthpiece", "ligature"]
    # 単体で作ったマウスピースは「まだセットではないが育てられる」状態
    # （`is_set` が False。部品タブには ＋リガチャー / ＋リード が出る）
    single = c.post("/api/project/new", json={"instrument_id": "saxophone",
                                              "template_id": "alto",
                                              "component_id": "mouthpiece"})
    info = single.json()["set"]
    assert info["is_set"] is False and info["addable"] == ["ligature", "reed"]


def test_single_project_can_grow_into_a_set():
    """単体で作った部品に、あとから部品を足してセットにできること。

    セットを持たない部品（管体・ネック）では部品タブを出さない ——
    「どの部品が組になるか」は descriptor の `sets` だけが決める。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    r = c.post("/api/project/new", json={"instrument_id": "saxophone",
                                         "template_id": "alto",
                                         "component_id": "mouthpiece"})
    info = r.json()["set"]
    assert info is not None and info["is_set"] is False
    assert info["addable"] == ["ligature", "reed"]
    c.put("/api/project/params", json={"params": {"body_dia": 29.8}})

    added = c.post("/api/set/member/add", json={"component_id": "ligature"})
    assert added.status_code == 200
    assert added.json()["set"]["is_set"] is True
    assert STATE.project.set_id == "mouthpiece_set"     # セットとして名乗る
    # 足した部品は、いま設計している値にそのまま追従する
    assert STATE.component.refs["mouthpiece"]["params"]["body_dia"] == 29.8

    # どのセットにも属さない部品では部品タブを出さない
    body = c.post("/api/project/new", json={"instrument_id": "saxophone",
                                            "template_id": "alto",
                                            "component_id": "body"})
    assert body.json()["set"] is None


def test_set_reference_is_live():
    """セット内の参照は**取込操作なしで**マウスピースの現在値に追従すること。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    _new_set(c)
    c.put("/api/project/params", json={"params": {"body_dia": 30.0}})

    r = c.post("/api/set/active", json={"component_id": "ligature"})
    assert r.status_code == 200
    ref = STATE.component.refs["mouthpiece"]
    assert ref["source"] == "set"
    assert ref["params"]["body_dia"] == 30.0
    assert r.json()["reference"]["live"] is True

    # 参照が変われば従属部品のキャッシュ鍵も変わる（無効化の条件を別に書かない）
    before = STATE._member_key("ligature")
    c.post("/api/set/active", json={"component_id": "mouthpiece"})
    c.put("/api/project/params", json={"params": {"body_dia": 28.0}})
    assert STATE._member_key("ligature") != before
    c.post("/api/set/active", json={"component_id": "ligature"})
    assert STATE.component.refs["mouthpiece"]["params"]["body_dia"] == 28.0


def test_set_reference_import_is_refused_inside_set():
    """セットに本体が居る参照は取込めないこと（正が 2 つになる）。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    _new_set(c)
    c.post("/api/set/active", json={"component_id": "ligature"})
    r = c.post("/api/project/reference",
               json={"component": "mouthpiece", "path": None})
    assert r.status_code == 400
    assert "セット" in r.json()["detail"]


def test_set_roundtrip(tmp_path):
    """3 メンバーの保存 → 読込で、値・active・生きた参照が保たれること。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    _new_set(c)
    c.put("/api/project/params", json={"params": {"body_dia": 29.7}})
    c.post("/api/set/member/add", json={"component_id": "reed"})
    c.put("/api/project/params", json={"params": {"tip_thickness": 0.11}})
    c.post("/api/set/active", json={"component_id": "ligature"})
    c.put("/api/project/params", json={"params": {"band_width": 13.5}})

    f = tmp_path / "set.wproj"
    assert c.post("/api/project/save", json={"path": str(f)}).status_code == 200
    r = c.post("/api/project/open", json={"path": str(f)})
    assert r.status_code == 200
    assert r.json()["set"]["active"] == "ligature"
    assert STATE.project.member("mouthpiece").params["body_dia"] == 29.7
    assert STATE.project.member("reed").params["tip_thickness"] == 0.11
    assert STATE.paramset.values["band_width"] == 13.5
    assert STATE.component.refs["mouthpiece"]["params"]["body_dia"] == 29.7


def test_set_member_export_freezes_reference(tmp_path):
    """部品を単体 .wproj へ書き出すと、束ねた参照が凍結値として残ること。

    参照が空のまま出すと、単体で開いた瞬間にテンプレート既定値へ落ちて、
    書き出した本人が見ていた形と違う物が出てくる。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    _new_set(c)
    c.put("/api/project/params", json={"params": {"body_dia": 30.2}})
    c.post("/api/set/active", json={"component_id": "ligature"})

    out = tmp_path / "lig.wproj"
    r = c.post("/api/set/member/export",
               json={"component_id": "ligature", "path": str(out)})
    assert r.status_code == 200 and out.exists()

    opened = c.post("/api/project/open", json={"path": str(out)})
    assert opened.status_code == 200
    assert opened.json()["set"]["is_set"] is False       # 単体として開く
    ref = STATE.component.refs["mouthpiece"]
    assert ref["source"] is None                          # もう追従しない
    assert ref["params"]["body_dia"] == 30.2
    assert opened.json()["reference"]["live"] is False

    # 書き出した単体にマウスピースを足すと、以後はセット側が正になる。
    # **形が変わるので黙ってやらない**（凍結値 30.2 → テンプレート既定）。
    added = c.post("/api/set/member/add", json={"component_id": "mouthpiece"})
    assert any("追従します" in n for n in added.json()["notices"])
    c.post("/api/set/active", json={"component_id": "ligature"})
    assert STATE.component.refs["mouthpiece"]["source"] == "set"
    assert STATE.component.refs["mouthpiece"]["params"]["body_dia"] != 30.2


def test_set_member_import(tmp_path):
    """既存の単体 .wproj をセットのメンバーとして取り込めること。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    # 先に単体のリードを作って保存
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "reed"})
    c.put("/api/project/params", json={"params": {"tip_thickness": 0.13}})
    src = tmp_path / "reed.wproj"
    c.post("/api/project/save", json={"path": str(src)})

    _new_set(c)
    r = c.post("/api/set/member/import", json={"path": str(src)})
    assert r.status_code == 200
    assert STATE.project.member("reed").params["tip_thickness"] == 0.13
    assert STATE.project.active == "reed"

    # 既にある部品は**黙って置き換えない**（今の設計が戻せないまま消える）
    dup = c.post("/api/set/member/import", json={"path": str(src)})
    assert dup.status_code == 400 and "既に" in dup.json()["detail"]

    # サイズ違いは弾く（セットはテンプレートを 1 か所しか持たない）
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "tenor",
                                     "component_id": "reed"})
    other = tmp_path / "tenor_reed.wproj"
    c.post("/api/project/save", json={"path": str(other)})
    _new_set(c)
    bad = c.post("/api/set/member/import", json={"path": str(other)})
    assert bad.status_code == 400 and "テナー" in bad.json()["detail"]


def test_set_remove_blocked_when_depended_on():
    """必須参照の相手（マウスピース）は、従属部品が居るうちは外せないこと。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    _new_set(c)
    r = c.post("/api/set/member/remove", json={"component_id": "mouthpiece"})
    assert r.status_code == 400
    assert "従属" in r.json()["detail"]
    # 任意メンバーは外せる
    c.post("/api/set/member/add", json={"component_id": "reed"})
    assert c.post("/api/set/member/remove",
                  json={"component_id": "reed"}).status_code == 200


def test_set_required_member_can_still_be_removed():
    """**必須メンバー（リガチャー）も外せること。**

    `required` は「新規セットで最初から作る」の意味しか持たない。これを
    「外せない」に流用すると、リガチャーを外す操作がどこにも無くなる
    （実際にそうなっていた —— サーバは外せるのに UI が × を描かなかった）。
    外せるかどうかを決めるのは従属関係だけで、リガチャーには従属部品が居ない。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    _new_set(c)
    info = c.get("/api/project").json()["set"]
    lig = next(m for m in info["members"] if m["component_id"] == "ligature")
    assert lig["required"] is True and lig["master"] is False

    assert c.post("/api/set/member/remove",
                  json={"component_id": "ligature"}).status_code == 200
    after = c.get("/api/project").json()["set"]
    # 1 部品に戻ったらセットを名乗らない（出力の既定範囲も 3D も単体に戻る）
    assert after["is_set"] is False
    assert [m["component_id"] for m in after["members"] if m["present"]] == ["mouthpiece"]
    # ＋ボタンは残る（育て直せる）
    assert "ligature" in after["addable"]
    assert c.post("/api/set/member/add",
                  json={"component_id": "ligature"}).status_code == 200
    assert c.get("/api/project").json()["set"]["is_set"] is True


def test_v1_project_opens_as_single_member_set(tmp_path):
    """v1 の .wproj が、値・凍結・採寸・編集済みモデルを保ったまま開けること。"""
    import json
    import zipfile
    from saxsketch.core.project import Project
    old = tmp_path / "v1.wproj"
    with zipfile.ZipFile(old, "w") as zf:
        zf.writestr("project.json", json.dumps({
            "schema_version": 1, "instrument_id": "saxophone",
            "template_id": "tenor", "component_id": "ligature", "name": "旧",
            "params": {"band_width": 12.5},
            "refs": {"mouthpiece": {"source": "/tmp/mp.wproj", "label": "M",
                                    "params": {"body_dia": 30.8}}},
            "notes": "メモ",
            "frozen": {"frozen_at": "2026-01-01T00:00:00Z",
                       "params": {"band_width": 12.5}, "solid_volume_cc": 3.0,
                       "export_dir": None},
            "derived": {"imported_at": "2026-01-02T00:00:00Z",
                        "source_file": "x.stl", "quality": {}, "analysis": {}},
            "survey": {"surveyed_at": "2026-01-03T00:00:00Z", "note": "n",
                       "measured": {}, "measured_size": {}, "checkpoint": {},
                       "card": None}}, ensure_ascii=False))
        zf.writestr("derived/model.stl", b"STLBYTES")

    p = Project.load(old)
    assert p.schema_version == 2 and list(p.members) == ["ligature"]
    assert p.is_set is False                      # 単体は単体のまま
    assert p.params["band_width"] == 12.5
    assert p.refs["mouthpiece"]["params"]["body_dia"] == 30.8
    assert p.notes == "メモ" and p.frozen["solid_volume_cc"] == 3.0
    assert p.survey["note"] == "n" and p.derived_stl == b"STLBYTES"

    # v2 で保存し直しても中身が保たれる（derived は部品ごとの場所へ移る）
    new = tmp_path / "v2.wproj"
    p.save(new)
    with zipfile.ZipFile(new) as zf:
        assert "derived/ligature/model.stl" in zf.namelist()
    q = Project.load(new)
    assert q.params == p.params and q.derived_stl == b"STLBYTES"
    assert q.refs == p.refs and q.frozen == p.frozen


def test_future_schema_version_is_refused(tmp_path):
    """未来バージョンの .wproj は理由付きで拒否されること。"""
    import json
    import zipfile
    from saxsketch.core.project import Project
    f = tmp_path / "future.wproj"
    with zipfile.ZipFile(f, "w") as zf:
        zf.writestr("project.json", json.dumps({
            "schema_version": 99, "instrument_id": "saxophone",
            "template_id": "alto", "members": {}, "active": ""}))
    with pytest.raises(ValueError, match="新しいバージョン"):
        Project.load(f)


def test_set_freeze_stales_on_master_edit(tmp_path):
    """セットで凍結後にマウスピースを触ると、従属部品の凍結が陳腐化すること。

    参照が「生きた」ぶん、取込操作をしなくても形が変わる。凍結が追いつかないと
    古い外部編集モデルが入稿に混ざる。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    _new_set(c)
    c.post("/api/set/active", json={"component_id": "ligature"})
    e = c.post("/api/export", json={"formats": ["stl"], "make_package": False,
                                    "out_dir": str(tmp_path / "frozen"),
                                    "freeze": True})
    assert e.status_code == 200 and not STATE.is_stale()

    c.post("/api/set/active", json={"component_id": "mouthpiece"})
    c.put("/api/project/params", json={"params": {"body_dia": 30.4}})
    r = c.post("/api/set/active", json={"component_id": "ligature"})
    assert STATE.is_stale(), "マウスピースを変えたのに凍結が陳腐化していない"
    assert r.json()["manual_edit"]["stale"] is True


def test_ligature_uses_set_reed_dimensions():
    """リガチャーの当たり面が、セットのリードの実寸に従うこと。

    以前はテンプレート固定で、実際に設計したリードと接触寸法が食い違ったまま
    作れてしまった（`ligature.reed_params` の注記）。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    _new_set(c)
    c.post("/api/set/member/add", json={"component_id": "reed"})
    c.put("/api/project/params", json={"params": {"heel_thickness": 3.2,
                                                  "heel_width": 12.5}})
    c.post("/api/set/active", json={"component_id": "ligature"})
    lig = STATE.component
    assert lig.reed_is_from_set() is True
    assert lig.reed_params()["heel_thickness"] == 3.2
    assert lig.reed_params()["heel_width"] == 12.5

    # リードを外せばテンプレート既定へ戻る（＝規則は 1 か所だけ）
    c.post("/api/set/member/remove", json={"component_id": "reed"})
    c.post("/api/set/active", json={"component_id": "ligature"})
    tmpl = STATE.component.template["reed"]
    assert STATE.component.reed_is_from_set() is False
    assert STATE.component.reed_params()["heel_thickness"] == tmpl["heel_thickness"]


def test_adding_reed_notifies_shape_change():
    """リードの足し引きで形が変わることを**黙って**やらないこと。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    _new_set(c)
    added = c.post("/api/set/member/add", json={"component_id": "reed"}).json()
    assert any("リガチャー" in n and "リード" in n for n in added["notices"])
    removed = c.post("/api/set/member/remove",
                     json={"component_id": "reed"}).json()
    assert any("テンプレート" in n for n in removed["notices"])


def test_template_reed_in_set_is_bit_identical():
    """セットのリードがテンプレート値のとき、リガチャーの形が従来と一致すること。

    出所を変えた（テンプレート → セットのリード）だけで、**同じ値なら同じ形**で
    なければならない。ここが崩れると、既存プロジェクトの形が理由なく変わる。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)

    _new_set(c)                                    # リード無し（テンプレート想定）
    c.post("/api/set/active", json={"component_id": "ligature"})
    p = dict(STATE.paramset.values)
    without = STATE.component.build(p)
    sec_without = STATE.component.section(p)
    dim_without = STATE.component.dimensions(p)

    c.post("/api/set/member/add", json={"component_id": "reed"})   # 既定値のまま
    c.post("/api/set/active", json={"component_id": "ligature"})
    assert STATE.component.reed_is_from_set() is True
    with_reed = STATE.component.build(p)

    assert with_reed.volume == without.volume
    assert len(with_reed.vertices()) == len(without.vertices())
    assert STATE.component.section(p) == sec_without
    assert STATE.component.dimensions(p) == dim_without

    # 3 サイズとも「テンプレート値」と「ParamSet を通した既定値」が一致すること。
    # ここがずれると、リードを足しただけでリガチャーの形が黙って変わる
    # （`ParamSpec.validate` はレンジ外を黙ってクランプする）。
    from saxsketch.core.schema import ParamSet
    for tid in SIZES:
        reed = get_registry().get("saxophone").make_component("reed", tid)
        raw = reed.template["reed"]
        normalized = ParamSet(reed.param_specs(), raw).values
        for k in ("heel_thickness", "heel_width", "heel_edge_thickness"):
            assert raw[k] == normalized[k], f"{tid}.{k} がクランプされている"


def test_set_card_rows_and_source():
    """セットの適合カードが、部品どうしでしか出せない量と想定リードの出所を出すこと。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    r = _new_set(c)
    card = r.json()["set_card"]
    assert card is not None
    labels = [row[0] for row in card["rows"]]
    assert "想定リード" in labels
    assert "テンプレート" in dict(card["rows"])["想定リード"]

    r = c.post("/api/set/member/add", json={"component_id": "reed"})
    card = r.json()["set_card"]
    rows = dict(card["rows"])
    assert "このセットのリード" in rows["想定リード"]
    assert "リード全長 / 帯の後端" in rows
    assert "リード踵幅 / テーブル実幅（帯の中央）" in rows
    assert card["status"] == "ok"

    # 踵をテーブルからはみ出させると乖離が出る（マウスピース側の実幅で判定する）
    c.put("/api/project/params", json={"params": {"heel_width": 18.0}})
    bad = c.get("/api/project").json()["set_card"]
    assert bad["status"] == "bad"
    assert "乖離" in dict(bad["rows"])["リード踵幅 / テーブル実幅（帯の中央）"]

    # 単体プロジェクトでは出さない（部品が 1 つでは決まらない）
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "ligature"})
    assert c.get("/api/project").json()["set_card"] is None
    assert STATE.set_card() is None


def test_set_card_table_width_not_reed_width():
    """テーブル幅の判定に `reed_width` を使っていないこと。

    `reed_width` は窓幅の公称値で、マウスピースの面を 1 つも決めていない
    （`profiles.table_flat_width` の注記）。実幅は z で変わる。
    """
    from saxsketch.instruments.saxophone.components import profiles, set_check
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    reg = get_registry().get("saxophone")
    lig = reg.make_component("ligature", "alto")
    m = _template_params("mouthpiece", "alto")
    p = _template_params("ligature", "alto")
    reed = _template_params("reed", "alto")
    lig.set_refs({"mouthpiece": {"params": m}, "reed": {"params": reed}})

    card = set_check.set_card(lig.size_info, {
        "mouthpiece": {"params": m, "component": reg.make_component("mouthpiece", "alto")},
        "ligature": {"params": p, "component": lig},
        "reed": {"params": reed, "component": reg.make_component("reed", "alto")},
    })
    z_mid = sum(lp.seat_range(m, p)) / 2.0
    flat = profiles.table_flat_width(m, z_mid)
    assert f"{flat:.2f}" in dict(card["rows"])["リード踵幅 / テーブル実幅（帯の中央）"]
    assert abs(flat - m["reed_width"]) > 0.5      # 公称と実幅は別物


def test_reed_assembly_placement_lies_on_table():
    """リードの配置が、底面をテーブル平面に載せること。

    向きも位置も `table_plane_y` から出しているので、**平面の定義が変われば
    置き場所も一緒に動く**。ここが符号だけ別に決め打たれていると、片方だけ
    直った状態が作れる。
    """
    import math
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        m = _template_params("mouthpiece", tid)
        reed = reg.make_component("reed", tid)
        reed.set_refs({"mouthpiece": {"params": m}})
        r = _template_params("reed", tid)
        pl = reed.assembly_placement(r)
        th = math.radians(pl["rotate_x_deg"])
        # 傾きはテーブル平面の傾き（実測 4.18°）と一致する
        assert pl["rotate_x_deg"] == pytest.approx(
            math.degrees(profiles.table_angle(m)), abs=1e-6)
        # 底面（リード局所 y=0）の各点がテーブル平面の上に来る
        for length in (0.0, 10.0, 30.0, r["reed_length"]):
            y = pl["origin"][1] - length * math.sin(th)
            z = pl["origin"][2] + length * math.cos(th)
            assert y == pytest.approx(profiles.table_plane_y(m, z), abs=1e-9)
        # 先端はティップレールの前縁（中央）に合う
        assert pl["origin"][2] == pytest.approx(profiles.tip_contour_z(m, 0.0))

    # 参照マウスピースが無ければ置き場所は決まらない（出さない）
    bare = reg.make_component("reed", "alto")
    bare.set_refs({})
    assert bare.assembly_placement(_template_params("reed", "alto")) is None


def test_reed_assembly_places_the_blade_outside_the_table():
    """リードの肉が**テーブルの外側**に出ること（胴へ潜らない）。

    リードのモデルは底面 y=0 から **+y** へ肉が付く（`reed_profiles.sections`）が、
    テーブル平面は胴の下（`table_plane_y` は負で、マウスピースの材料はその上）。
    載る側の外向き法線は −y なので、裏返さずに置くと**肉が丸ごと胴の中へ入る**。
    実際にそうなっていて、アルトで +2.807mm ＝ リード厚 2.800 とほぼ一致していた。

    ここは配置の**全点**を見る（底面の 4 点だけを見ていた前のテストは、肉が
    どちら側に付くかを一度も確かめていなかったので裏返りを素通りさせた）。
    """
    import math
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        m = _template_params("mouthpiece", tid)
        reed = reg.make_component("reed", tid)
        reed.set_refs({"mouthpiece": {"params": m}})
        r = _template_params("reed", tid)
        pl = reed.assembly_placement(r)
        assert pl["flip_z"] is True, tid
        th = math.radians(pl["rotate_x_deg"])
        c, sn = math.cos(th), math.sin(th)
        worst, deep = -1e9, 1e9
        for sec in rp.sections(r):
            for (x, y) in sec["pts"]:
                X, Y, Z = -x, -y, sec["z"]              # flip_z（Z 軸 180°）
                y2 = Y * c - Z * sn + pl["origin"][1]   # R_x
                z2 = Y * sn + Z * c + pl["origin"][2]
                d = y2 - profiles.table_plane_y(m, z2)
                worst, deep = max(worst, d), min(deep, d)
        # 底面はテーブルにぴったり、肉は反対側（負）にだけ伸びる
        assert worst == pytest.approx(0.0, abs=1e-9), tid
        thick = max(rp.thickness(r, sec["z"], 0.0) for sec in rp.sections(r))
        assert deep == pytest.approx(-thick, abs=0.02), tid


def _apply_placement(pl: dict, v: tuple) -> tuple:
    """配置 1 件を点へ適用する: `R_x(θ)·F^f·v + t`（`F` は Z 軸まわり 180°）。"""
    import math
    x, y, z = v
    if pl.get("flip_z"):
        x, y = -x, -y
    th = math.radians(pl["rotate_x_deg"])
    c, s = math.cos(th), math.sin(th)
    y, z = y * c - z * s, y * s + z * c
    return (x + pl["origin"][0], y + pl["origin"][1], z + pl["origin"][2])


def test_set_placement_is_relative_to_active():
    """配置が編集中の部品を基準にした相対変換で、基準を替えても同じ組になること。

    **「逆変換 ＝ 角の符号反転」ではない。** 変換は `R_x(θ)·F^f` の形で、裏返しが
    入ると `(R_x(θ)·F)² = I` ＝ **自分自身が逆変換**になる（`F·R_x(θ)·F = R_x(−θ)`）。
    だから符号で見ると落ちる。見るべきは**部品どうしの相対位置が基準に依らない**こと。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    _new_set(c)
    c.post("/api/set/member/add", json={"component_id": "reed"})

    c.post("/api/set/active", json={"component_id": "mouthpiece"})
    from_mp = c.get("/api/set/placement").json()
    assert from_mp["active"] == "mouthpiece" and from_mp["unplaced"] == []
    parts = {p["component_id"]: p for p in from_mp["parts"]}
    assert set(parts) == {"ligature", "reed"}
    # 同じ座標系の部品は恒等（リガチャーは参照 MP の z でそのまま張られている）
    assert parts["ligature"]["rotate_x_deg"] == 0.0
    assert parts["ligature"]["origin"] == [0.0, 0.0, 0.0]
    assert parts["ligature"]["flip_z"] is False
    assert parts["reed"]["flip_z"] is True          # リードは裏返して載る

    c.post("/api/set/active", json={"component_id": "reed"})
    from_reed = {p["component_id"]: p
                 for p in c.get("/api/set/placement").json()["parts"]}
    IDENT = {"origin": [0.0, 0.0, 0.0], "rotate_x_deg": 0.0, "flip_z": False}
    probes = [(0.0, 0.0, 0.0), (3.0, 2.0, 10.0), (-4.0, 1.5, 40.0)]
    for v in probes:
        # マウスピース基準で見たリード上の点 と リード基準で見た同じ点
        a_mp = _apply_placement(parts["reed"], v)          # 基準=MP のときのリード
        a_rd = _apply_placement(IDENT, v)                  # 基準=リード のときのリード
        # 同じ点を「基準=リードの系」へ移すと一致するはず
        back = _apply_placement(from_reed["mouthpiece"], a_mp)
        assert back == pytest.approx(a_rd, abs=1e-9), v


def test_the_app_shell_is_never_cached_but_assets_are():
    """殻は毎回取り直し、資産は永久にキャッシュしてよいこと。

    **古いページが黙って動き続ける経路を塞ぐ。** サーバだけ新しい状態は
    エラーにならず、それらしく組み上がった絵が出るので気付けない
    （2026-09-03: フロントが `flip_z` を落とし、リードがマウスピースの
    反対側に付いて見えた）。資産は内容ハッシュ付きの名前なので、殻さえ
    取り直せば必ず現行の世代になる。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server import app as appmod
    if not appmod.FRONTEND_DIST.exists():
        pytest.skip("frontend/dist が無い（未ビルド）")
    c = TestClient(appmod.app)
    r = c.get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"

    asset = appmod.frontend_asset()
    assert asset and asset.endswith(".js")
    a = c.get(f"/assets/{asset}")
    assert a.status_code == 200
    assert "immutable" in a.headers["cache-control"]


def test_capabilities_reports_the_running_app_generation():
    """`/api/capabilities` の `asset` が、殻が実際に読む名前と一致すること。

    **ビルド時に別途仕込まない** —— `index.html` の実物から読む。埋め込むと
    「配っている物」と「世代を名乗る値」が別々に古くなれるので、食い違いを
    見つけるための値が自分で食い違える。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server import app as appmod
    if not appmod.FRONTEND_DIST.exists():
        pytest.skip("frontend/dist が無い（未ビルド）")
    c = TestClient(appmod.app)
    asset = c.get("/api/capabilities").json()["asset"]
    assert asset and f'src="/assets/{asset}"' in c.get("/").text


def test_set_view_keeps_the_reed_on_the_table_side():
    """どの部品を基準にしても、リードは**テーブル側**に付くこと。

    4-D.5 のテストは「肉が胴へ潜らないこと」しか見ていなかった。**潜っていないが
    反対側（ビーク側）に付く**という状態が実在する —— 実際 2026-09-03 に
    「セット表示でリードが胴の反対側」と報告が出た（原因は配置ではなく、
    古いページが `flip_z` を落としていたこと）。そのとき組んだ姿は
    マウスピース y[-25.468, +2.817] で、リード y[0.000, 2.800] は**潜っていない**
    ——「潜っていない」だけでは合否が分けられなかった。

    見るのは**テーブル平面に対してリードの肉とビークが反対側にあるか**。
    リードもマウスピースも軸上（x≈0）にあるので、射影は `y·cos(方位)` になり
    **符号は視点に依らない**。だから画面でも同じ判定が使える。
    """
    from fastapi.testclient import TestClient
    from saxsketch.instruments.saxophone.components import profiles
    from saxsketch.instruments.saxophone.components import reed_profiles as rp
    from saxsketch.server.app import app
    c = TestClient(app)

    for tid in SIZES:
        _new_set(c, tid)
        c.post("/api/set/member/add", json={"component_id": "reed"})
        m = _template_params("mouthpiece", tid)
        r = _template_params("reed", tid)
        z = 40.0                      # 3 部品すべてが在る中ほど
        probes = {
            "table": (0.0, profiles.table_plane_y(m, z), z),
            "beak": (0.0, profiles.outer_radius(m, z), z),
            "meat": (0.0, rp.thickness(r, z, 0.0), z),
        }
        for active in ("mouthpiece", "ligature", "reed"):
            c.post("/api/set/active", json={"component_id": active})
            pl = {p["component_id"]: p
                  for p in c.get("/api/set/placement").json()["parts"]}
            pl[active] = {"origin": [0.0, 0.0, 0.0],
                          "rotate_x_deg": 0.0, "flip_z": False}
            table = _apply_placement(pl["mouthpiece"], probes["table"])
            beak = _apply_placement(pl["mouthpiece"], probes["beak"])
            meat = _apply_placement(pl["reed"], probes["meat"])
            flat = _apply_placement(pl["reed"], (0.0, 0.0, z))
            # リードの平らな底面はテーブル平面に載る
            assert flat[1] == pytest.approx(table[1], abs=0.05), (tid, active)
            # 肉とビークはテーブルの**反対側**
            assert (meat[1] - table[1]) * (beak[1] - table[1]) < 0, (tid, active)
            # 肉の伸びはリード厚ぶん（潜っていない、かつ離れてもいない）
            assert abs(meat[1] - table[1]) == pytest.approx(
                rp.thickness(r, z, 0.0), abs=0.05), (tid, active)


def test_set_member_stl_endpoint(tmp_path):
    """合わせ表示用に部品ごとの STL が取れ、居ない部品は 404 になること。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    _new_set(c)
    c.post("/api/set/active", json={"component_id": "mouthpiece"})
    r = c.get("/api/set/model.stl?member=ligature")
    assert r.status_code == 200 and len(r.content) > 1000
    assert c.get("/api/set/model.stl?member=reed").status_code == 404

    # 単体プロジェクトでは配置が空（UI はトグルを出さない）
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "mouthpiece"})
    empty = c.get("/api/set/placement").json()
    assert empty["parts"] == []


def test_set_export_one_folder(tmp_path):
    """セット出力が 1 フォルダに部品ごとのサブフォルダ＋共通の仕様書/BOM/ZIP を作ること。"""
    import zipfile
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    _new_set(c)
    c.post("/api/set/member/add", json={"component_id": "reed"})

    r = c.post("/api/export", json={"formats": ["stl"], "scope": "set",
                                    "out_dir": str(tmp_path), "make_package": True})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["scope"] == "set"
    assert set(res["members"]) == {"mouthpiece", "ligature", "reed"}

    out = Path(res["out_dir"])
    for cid in ("mouthpiece", "ligature", "reed"):
        assert (out / cid / "model.stl").exists(), cid
    assert (out / "spec.html").exists() and (out / "bom.csv").exists()

    # 仕様書は 1 枚に 3 部品ぶん。部品どうしの適合カードも入る。
    html = (out / "spec.html").read_text(encoding="utf-8")
    for label in ("マウスピース", "リガチャー", "リード"):
        assert f'<h1 class="part">{label}' in html
    assert "セットの適合" in html

    # 部品表は先頭列でどの部品の行かが分かる
    csv_text = (out / "bom.csv").read_bytes().decode("utf-8-sig")
    assert csv_text.splitlines()[1].startswith("部品,区分,")
    assert any(line.startswith("リード,") for line in csv_text.splitlines())

    # 入稿 ZIP は 1 本で、中もサブフォルダ構成
    with zipfile.ZipFile(res["package"]) as zf:
        names = zf.namelist()
    assert "mouthpiece/model.stl" in names and "reed/model.stl" in names
    assert "spec.html" in names and "README.txt" in names


def test_member_scope_export_is_unchanged(tmp_path):
    """単体範囲の出力は従来どおり（サブフォルダを作らない）こと。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    _new_set(c)
    r = c.post("/api/export", json={"formats": ["stl"], "scope": "member",
                                    "out_dir": str(tmp_path), "make_package": False})
    assert r.status_code == 200
    out = Path(r.json()["out_dir"])
    assert r.json()["scope"] == "member"
    assert (out / "model.stl").exists()
    assert not (out / "mouthpiece").exists()
    html = (out / "spec.html").read_text(encoding="utf-8")
    assert '<h1 class="part">' not in html      # 部品見出しは付かない


def test_set_export_blocked_by_stale_member(tmp_path):
    """セット出力でも、陳腐化した編集済みモデルを持つ部品があれば止まること。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)
    _new_set(c)
    c.post("/api/set/active", json={"component_id": "ligature"})
    c.post("/api/export", json={"formats": ["stl"], "make_package": False,
                                "out_dir": str(tmp_path / "f"), "freeze": True})
    STATE.project.derived_stl = b"dummy"
    STATE.project.derived = {"imported_at": "x", "source_file": "x",
                             "quality": {}, "analysis": {}}

    # マウスピースを動かすとリガチャーの凍結が古くなる
    c.post("/api/set/active", json={"component_id": "mouthpiece"})
    c.put("/api/project/params", json={"params": {"body_dia": 30.6}})
    r = c.post("/api/export", json={"formats": ["stl"], "scope": "set",
                                    "out_dir": str(tmp_path / "s"),
                                    "make_package": False})
    assert r.status_code == 409
    assert "リガチャー" in r.json()["detail"]


def test_impedance_unsupported_returns_422():
    """音響を持たないコンポーネントは 500 ではなく 422 を返すこと。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "ligature"})
    r = c.get("/api/acoustics/impedance")
    assert r.status_code == 422
    assert "インピーダンス" in r.json()["detail"]
    assert c.get("/api/acoustics/sound.wav").status_code == 422


def test_reference_size_mismatch_rejected(tmp_path):
    """サイズ違いのマウスピースを参照に取れないこと。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    tenor = tmp_path / "tenor_mp.wproj"
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "tenor",
                                     "component_id": "mouthpiece"})
    c.post("/api/project/save", json={"path": str(tenor)})

    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "component_id": "reed"})
    r = c.post("/api/project/reference", json={"component": "mouthpiece",
                                               "path": str(tenor)})
    assert r.status_code == 400
    assert "テナー" in r.json()["detail"] and "アルト" in r.json()["detail"]


def test_project_future_version_rejected(tmp_path):
    import json, zipfile
    f = tmp_path / "future.wproj"
    with zipfile.ZipFile(f, "w") as zf:
        zf.writestr("project.json", json.dumps({
            "schema_version": 999, "instrument_id": "saxophone",
            "template_id": "alto", "component_id": "mouthpiece", "params": {}}))
    with pytest.raises(ValueError):
        Project.load(f)


# ------------------------------------------------------------------ 外部編集（凍結・再取込・逆算）

def test_manual_edit_flow(tmp_path):
    """凍結 → 編集模擬 → 取込解析（逆算・領域検出）→ 登録 → 陳腐化 → 保存往復。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.export.models import export_model
    c = TestClient(app)

    r = c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "alto",
        "component_id": "mouthpiece"})
    assert r.status_code == 200
    frozen_params = r.json()["params"]

    # 凍結（エクスポート + スナップショット）
    r = c.post("/api/export", json={
        "formats": ["stl"], "make_package": False, "freeze": True,
        "out_dir": str(tmp_path)})
    assert r.status_code == 200
    assert r.json()["manual_edit"]["frozen"] is not None

    # 「外部編集」を模擬: バッフル+1.2 / ティップ+0.4 の別形状を編集済みSTLとして用意
    from saxsketch.core.registry import get_registry
    comp = get_registry().get("saxophone").make_component("mouthpiece", "alto")
    edited_p = dict(frozen_params)
    edited_p["baffle_height"] = frozen_params["baffle_height"] + 1.2
    edited_p["tip_opening"] = frozen_params["tip_opening"] + 0.4
    edited_stl = tmp_path / "model_edited.stl"
    export_model(comp.build(edited_p), edited_stl, "stl", tolerance=0.02)

    # 取込解析
    r = c.post("/api/manual/import", json={"path": str(edited_stl)})
    assert r.status_code == 200
    rep = r.json()
    rows = {x["key"]: x for x in rep["params"]}
    # 逆算: ティップ開きの実測が編集後の値に近い
    assert rows["tip_opening"]["estimated"] == pytest.approx(
        edited_p["tip_opening"], abs=0.2)
    assert rows["tip_opening"]["verdict"] == "乖離"
    # バッフルも増加方向を検出
    assert rows["baffle_height"]["estimated"] > frozen_params["baffle_height"] + 0.4
    # 未編集パラメータは一致
    assert rows["overall_length"]["verdict"] == "一致"
    assert rows["body_dia"]["verdict"] == "一致"
    # 領域検出: フェイシング領域が変化あり
    facing_zone = next(z for z in rep["regions"] if "tip_opening" in z["params"])
    assert facing_zone["verdict"] in ("軽微", "変化あり")
    # 音響面の警告が出る
    assert any("リード密着面" in w or "内部空洞" in w for w in rep["warnings"])

    # 登録 → 陳腐化 → エクスポート拒否
    r = c.post("/api/manual/commit")
    assert r.status_code == 200 and r.json()["derived"] is not None
    r = c.put("/api/project/params", json={"params": {"tip_opening": 2.0}})
    assert r.json()["stale"] is True
    r = c.post("/api/export", json={"formats": ["stl"], "make_package": False,
                                    "out_dir": str(tmp_path)})
    assert r.status_code == 409  # 陳腐化した派生モデルでの入稿は拒否

    # パラメータを凍結時に戻すと stale 解除、派生STLで出力される
    r = c.put("/api/project/params",
              json={"params": {"tip_opening": frozen_params["tip_opening"]}})
    assert r.json()["stale"] is False
    r = c.post("/api/export", json={"formats": ["stl"], "make_package": False,
                                    "out_dir": str(tmp_path)})
    assert r.status_code == 200 and r.json()["used_derived"] is True
    assert "model_edited.stl" in r.json()["files"]

    # 保存 → 読込往復で派生モデル維持
    f = tmp_path / "manual.wproj"
    r = c.post("/api/project/save", json={"path": str(f)})
    assert r.status_code == 200
    r = c.post("/api/project/open", json={"path": str(f)})
    me = r.json()["manual_edit"]
    assert me["frozen"] is not None and me["derived"] is not None


# ------------------------------------------------------------------ API

def test_api_flow(tmp_path):
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)

    assert c.get("/api/instruments").status_code == 200
    r = c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "tenor",
        "component_id": "mouthpiece"})
    assert r.status_code == 200

    # 上限にクランプ。**止まるのは「勧める帯」の 3.2 ではなく「壁」の 5.2**
    # （Phase 4-E で `tip_opening` の壁を掃引で測って広げた。`docs/param-limits.md`）。
    # 帯と壁を分けた以上、ここで 3.2 に戻ったら広げた意味が無い。
    r = c.put("/api/project/params", json={"params": {"tip_opening": 99.0}})
    body = r.json()
    assert body["params"]["tip_opening"] == 5.2
    # **黙って丸めない。** 何をしたかが応答に載る
    assert len(body["adjustments"]) == 1
    assert "ティップ開き" in body["adjustments"][0]["message"]
    assert body["adjustments"][0]["at"] == "wall"

    # 知らないコンポーネントは 400。`available()` が False のものも同じ経路を通る
    # （4-B.2a で `body` が実装され、いま `_Planned` のコンポーネントは 1 つも無い）。
    r = c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "alto",
        "component_id": "keywork"})
    assert r.status_code == 400

    r = c.get("/api/model.stl?quality=preview")
    assert r.status_code == 200 and len(r.content) > 10000

    # `body` は 4-B.2a で `_Planned` を卒業した。STL を取ったあとに置いてあるのは、
    # ここでプロジェクトを差し替えると上の model.stl が管体のビルド（アルトで 12 秒）
    # になってしまうため。
    r = c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "alto",
        "component_id": "body"})
    assert r.status_code == 200
    assert r.json()["simulation"]["kind"] == "body"


# ------------------------------------------------------------------ ポート競合

def test_port_fallback():
    """占有ポートを検出し、空きへ退避するヘルパーの挙動。main() は起動しない。"""
    import socket

    from saxsketch.server import app as srv

    host = "127.0.0.1"
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.bind((host, 0))
    # **backlog は現実的な深さを取る。** 1 にすると `_in_use` の 1 回目の接続が
    # accept されないまま溜まってキューが埋まり、**2 回目の接続が拒否されて
    # 「空いている」に見える**（Windows で実測。1 回目 True → 以後ずっと False）。
    # 本番の相手は uvicorn なので深い。1 にするのは相手が非現実的なだけで、
    # `_free_port` の契約（使用中のポートを飛ばす）は変わらない。
    lsock.listen(128)
    busy = lsock.getsockname()[1]
    try:
        assert srv._in_use(host, busy) is True
        # listen 中ポートは避けて別番号を返す
        chosen = srv._free_port(host, busy)
        assert chosen is not None and chosen != busy
        assert srv._in_use(host, chosen) is False
        # 素のソケット相手は SaxSketch ではない（HTTP を話さない）
        assert srv._is_saxsketch(host, busy) is False
    finally:
        lsock.close()


# ------------------------------------------------------------------ 採寸ワークフロー（Phase 4-A）

def _new_client(template_id="alto", component_id="mouthpiece"):
    from fastapi.testclient import TestClient

    from saxsketch.server.app import app
    c = TestClient(app)
    r = c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": template_id,
        "component_id": component_id})
    assert r.status_code == 200
    return c


def test_survey_design_param():
    """設計パラの実測が params に反映され、復元点へ戻せること。"""
    c = _new_client("alto")
    proj = c.get("/api/project").json()
    assert proj["survey"]["has_checkpoint"] is False
    keys = {f["key"] for f in proj["survey"]["targets"]["params"]}
    assert {"tip_opening", "body_dia", "overall_length"} <= keys

    cur = proj["params"]["tip_opening"]
    target = round(cur + 0.5, 2)  # 1.0–3.2 の範囲内・設計値と乖離する量
    r = c.post("/api/survey/commit", json={
        "measured": {"tip_opening": target}, "measured_size": {}, "note": "実測テスト"})
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["tip_opening"] == target
    assert body["survey"]["has_checkpoint"] is True
    assert body["survey"]["measured"]["tip_opening"] == target
    card = body["survey"]["card"]
    assert card is not None and card["rows"] and card["status"] == "bad"  # Δ0.5 は乖離

    # 設計を破綻させてから採寸時点へ戻す
    c.put("/api/project/params", json={"params": {"tip_opening": 3.0}})
    r = c.post("/api/survey/revert")
    assert r.json()["params"]["tip_opening"] == target


def test_survey_size_override():
    """音響基準(ネック内径)の実測が Tier1 目標に効き、clear で descriptor 既定へ戻る。"""
    c = _new_client("tenor")
    t0 = c.get("/api/project").json()["simulation"]["tier1"]
    base_bore = _size_info("tenor")["neck_bore_id_mm"]

    # ネック内径を大きく実測 → 欠損円錐(目標容積)は増え、テナーはさらに高め方向へ
    r = c.post("/api/survey/commit", json={
        "measured": {}, "measured_size": {"neck_bore_id_mm": base_bore + 2.0},
        "note": ""})
    t1 = r.json()["simulation"]["tier1"]
    assert t1["target_cc"] > t0["target_cc"]
    assert t1["deviation_cents"] > t0["deviation_cents"]

    # descriptor は不変（別インスタンスは既定値のまま）
    assert _size_info("tenor")["neck_bore_id_mm"] == base_bore

    # clear で基準・目標が既定へ戻る
    r = c.post("/api/survey/clear")
    t2 = r.json()["simulation"]["tier1"]
    assert t2["target_cc"] == t0["target_cc"]
    assert r.json()["survey"]["has_checkpoint"] is False


def _tenor_mesh():
    """整列・採寸テスト用のテナー マウスピース メッシュ。"""
    from saxsketch.analysis import meshdiff
    comp = get_registry().get("saxophone").make_component("mouthpiece", "tenor")
    params = {s.key: s.default for s in comp.param_specs()}
    return comp, params, meshdiff.part_to_mesh(comp.build(params), tolerance=0.03)


def test_align_canonical():
    """乱雑に回転・平行移動した外部メッシュでも主軸を +Z に整列し、全長が復元されること。"""
    import numpy as np
    import trimesh
    from saxsketch.analysis import align

    _, _, mesh = _tenor_mesh()
    true_len = float(mesh.extents.max())  # 最長軸（＝マウスピース長）

    T = trimesh.transformations.random_rotation_matrix()
    T[:3, 3] = [41.0, -18.0, 63.0]
    moved = mesh.copy()
    moved.apply_transform(T)

    aligned, _, info = align.axis_align(moved)
    z = np.asarray(aligned.vertices)[:, 2]
    aligned_len = float(z.max() - z.min())
    assert aligned_len == pytest.approx(true_len, rel=0.02)
    assert info["axis_conf"] in ("high", "med")


def test_survey_measure_prefill():
    """外部メッシュ測定は確実に測れる外形寸法だけを返し、測れない項目は含めないこと。"""
    comp, params, mesh = _tenor_mesh()
    res = comp.survey_measure_mesh(mesh)

    measured = res["measured"]
    # 全長・ボディ外径は実測できる
    assert measured["overall_length"] == pytest.approx(
        float(mesh.extents.max()), rel=0.03)
    assert measured["body_dia"] == pytest.approx(params["body_dia"], abs=3.0)

    # 採寸ターゲット以外のキーは混ざらない
    target_keys = {f["key"] for f in comp.survey_targets()["params"]}
    assert set(measured) <= target_keys
    # リード面・空洞系は外部モデルからは測れない → 含めない
    assert "tip_opening" not in measured
    assert "facing_length" not in measured
    # マウスピース メッシュからネック系 size は測らない
    assert res["measured_size"] == {}
    # 各実測値に信頼度が付く
    assert set(measured) <= set(res["confidence"])
    assert res["notes"]  # 測れない項目の案内が入る


def test_survey_measure_commit(tmp_path):
    """/api/survey/measure→commit で外形寸法が設計へ反映され、revert で戻ること。"""
    from saxsketch.export.models import export_model

    comp, params, mesh = _tenor_mesh()
    model = tmp_path / "external.stl"
    export_model(comp.build(params), model, "stl", tolerance=0.03)

    c = _new_client("tenor")
    r = c.post("/api/survey/measure", json={"path": str(model)})
    assert r.status_code == 200
    measured = r.json()["measured"]
    assert "overall_length" in measured

    before = c.get("/api/project").json()["params"]["overall_length"]
    r = c.post("/api/survey/commit", json={
        "measured": {"overall_length": measured["overall_length"]},
        "measured_size": {}, "note": "3mf採寸"})
    assert r.status_code == 200
    assert r.json()["params"]["overall_length"] == measured["overall_length"]

    # 破綻させてから採寸時点へ戻す
    c.put("/api/project/params", json={"params": {"overall_length": before + 5.0}})
    r = c.post("/api/survey/revert")
    assert r.json()["params"]["overall_length"] == measured["overall_length"]


def test_region_deviations_foreign_bounded(monkeypatch):
    """別座標系（ほぼ重ならない）メッシュでは、厳密計算の経路に一切入らないこと。

    trimesh の `on_surface` は近い点なら 0.12ms/点だが、離れた点だと 5.4ms/点になる
    （`nearby_faces` が最近傍頂点までの距離を半径に rtree を引くので、遠い点では
    メッシュの全面が候補になる）。以前はここへ全サンプル点が流れ込んで 26 秒かかり、
    他の重い処理と並行しただけで壁時計の上限を割っていた。遠い点の厳密値は
    「変化あり」判定に何も足さないので、`_REFINE_MAX` で落として経路に入れない。

    壁時計は性能テストではなく**ハングしていないこと**の最後の砦として残してある
    （実測 0.6 秒に対して桁違いの上限）。守りたい性質は点数 0 の方で見る。
    """
    import time

    from trimesh.proximity import ProximityQuery

    from saxsketch.analysis import meshdiff

    exact_pts = 0
    original = ProximityQuery.on_surface

    def counting(self, points):
        nonlocal exact_pts
        exact_pts += len(points)
        return original(self, points)

    monkeypatch.setattr(ProximityQuery, "on_surface", counting)

    comp, params, ref = _tenor_mesh()
    foreign = ref.copy()
    foreign.apply_translation([200.0, 200.0, 0.0])  # 全く重ならない位置へ
    regions = comp.regions(params)

    t = time.time()
    out = meshdiff.region_deviations(ref, foreign, regions)
    assert exact_pts == 0                 # 遠い点は厳密計算に回さない
    assert time.time() - t < 120.0        # ハングしない（実測 0.6 秒）
    assert out                            # ゾーンは返る
    # 重なっていないので大きな偏差＝「変化あり」判定になる（誤って「変化なし」にしない）
    assert any(z["verdict"] == "変化あり" for z in out)


def test_build_worker_stl_matches_inproc():
    """常駐ワーカで作った STL が、親プロセスで作ったものと**バイト一致**すること。

    アプリはワーカ経由、テストは親経由（`TestClient` を素で作ると lifespan が
    走らないのでワーカは上がらない）と経路が分かれるので、その差が形に出ない
    ことをここで押さえる。ワーカを起動できない環境では skip する。
    """
    from saxsketch.server.buildworker import WORKER, build_from_spec
    from saxsketch.server.state import STATE

    if not WORKER.start():
        pytest.skip("この環境ではビルドワーカを起動できません")
    try:
        STATE.new_project("saxophone", "tenor", "mouthpiece", None)
        spec = STATE.build_spec(0.05)
        assert WORKER.build_stl(spec) == build_from_spec(spec)
    finally:
        WORKER.stop()


def test_region_deviations_identical_is_unchanged():
    """未編集のモデルを取り込んだら全ゾーン「変化なし」になること。

    点対点の最近傍だけで測っていた頃は、サンプル間隔（tenor で 0.25mm）ぶん必ず
    過大評価するので**同じメッシュ同士でも最大 0.51mm**が出て、「変化あり」8 ゾーン・
    「軽微」11 ゾーンという嘘の判定になっていた。領域別偏差は外部編集モデルの
    判断根拠なので、ここが素通りするとレポート全体が信用できない。
    """
    from saxsketch.analysis import meshdiff

    comp, params, ref = _tenor_mesh()
    out = meshdiff.region_deviations(ref, ref, comp.regions(params))

    judged = [z for z in out if z["max_dev_mm"] is not None]
    assert judged
    assert max(z["max_dev_mm"] for z in judged) <= meshdiff.DEV_UNCHANGED
    assert all(z["verdict"] == "変化なし" for z in judged)


def test_region_deviations_matches_known_edit():
    """既知の編集量（バッフル +0.30mm）が、その数字のまま報告されること。"""
    from saxsketch.analysis import meshdiff

    comp, params, ref = _tenor_mesh()
    edited_p = dict(params)
    edited_p["baffle_height"] = params["baffle_height"] + 0.30
    edited = meshdiff.part_to_mesh(comp.build(edited_p), tolerance=0.03)

    out = meshdiff.region_deviations(ref, edited, comp.regions(params))
    zone = next(z for z in out if "baffle_height" in z["params"])
    assert zone["max_dev_mm"] == pytest.approx(0.30, abs=0.05)
    assert zone["verdict"] == "軽微"


def test_external_load_view_and_export(tmp_path):
    """外部モデルを凍結なしで読込→整列STL表示→登録→入稿STL差し替え。差分/逆算はしない。"""
    from saxsketch.export.models import export_model

    comp, params, mesh = _tenor_mesh()
    model = tmp_path / "market_product.stl"
    export_model(comp.build(params), model, "stl", tolerance=0.03)

    c = _new_client("tenor")
    # 凍結していない状態でも外部読込できる
    r = c.post("/api/external/load", json={"path": str(model)})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "external"
    assert body["quality"]["watertight"] is True
    assert "overall_length" in body["measured"]      # 外形採寸は入る
    assert "align" in body                            # 整列情報

    # 登録すると「取込モデル」として表示・入稿に使える
    assert c.post("/api/manual/commit").status_code == 200
    me = c.get("/api/project").json()["manual_edit"]
    assert me["derived"]["kind"] == "external"
    assert me["stale"] is False                       # 外部モデルは陳腐化しない

    # 表示用STL（派生スロット）が配信される
    stl = c.get("/api/manual/model.stl")
    assert stl.status_code == 200 and len(stl.content) > 0

    # 入稿エクスポートは取込モデルのSTLを使う（use_derived）
    out = c.post("/api/export", json={
        "formats": ["stl"], "make_package": False, "out_dir": str(tmp_path / "out")})
    assert out.status_code == 200
    assert out.json()["used_derived"] is True


def test_survey_persist(tmp_path):
    """採寸状態が save→open で往復し、旧 .wproj(survey 欠落)も読めること。"""
    c = _new_client("tenor")
    base_bore = _size_info("tenor")["neck_bore_id_mm"]
    r = c.post("/api/survey/commit", json={
        "measured": {"body_dia": c.get("/api/project").json()["params"]["body_dia"]},
        "measured_size": {"neck_bore_id_mm": base_bore - 1.0}, "note": "往復"})
    target_cc = r.json()["simulation"]["tier1"]["target_cc"]

    f = tmp_path / "survey.wproj"
    assert c.post("/api/project/save", json={"path": str(f)}).status_code == 200
    body = c.post("/api/project/open", json={"path": str(f)}).json()
    assert body["survey"]["has_checkpoint"] is True
    assert body["survey"]["note"] == "往復"
    # 音響基準の上書きが復元され、目標容積が一致する
    assert body["simulation"]["tier1"]["target_cc"] == pytest.approx(target_cc, abs=0.01)

    # survey フィールドを持たない旧 .wproj は None で読める（後方互換）
    p = Project(instrument_id="saxophone", template_id="alto",
                component_id="mouthpiece", params={})
    assert p.survey is None
    g = tmp_path / "old.wproj"
    p.save(g)
    assert Project.load(g).survey is None


# ============================================================ ネック（Phase 4-B.1）

def _neck_params(tid, **override):
    from saxsketch.core.schema import ParamSet
    comp = get_registry().get("saxophone").make_component("neck", tid)
    vals = dict(ParamSet(comp.param_specs(), comp.template["neck"]).values)
    vals.update(override)
    return comp, dict(ParamSet(comp.param_specs(), vals).values)


def test_neck_param_roundtrip_and_wall():
    """全 ParamSpec.key がテンプレートに存在し、中央の肉厚が指定値に一致すること。"""
    from saxsketch.instruments.saxophone.components import neck_profiles as npf
    for tid in ("soprano", "alto", "tenor"):
        comp = get_registry().get("saxophone").make_component("neck", tid)
        keys = {s.key for s in comp.param_specs()}
        missing = keys - set(comp.template["neck"].keys())
        assert not missing, f"{tid} テンプレート欠落キー: {missing}"
        _, p = _neck_params(tid)
        s = 0.5 * p["neck_length"]
        wall = npf.outer_radius_at(s, p, comp.size_info) - npf.bore_radius_at(s, p, comp.size_info)
        assert wall == pytest.approx(p["wall_thickness"], abs=1e-6)


#: ネックの大端ボア内径 [mm]（`taper_from_cone = "on"` の導出値）。
#: アルトだけ 24.990 から動いた —— 頂点距離の値を持つのがアルトだけで、そこだけ
#: `missing_cone` の tanθ が生の半頂角と食い違っていたため。
NECK_LARGE_ID_MM = {"soprano": 18.613, "alto": 25.546, "tenor": 26.368}


def test_neck_taper_is_the_same_cone_as_the_body():
    """ネックと管体が**同じ円錐**を使うこと（1 つの楽器に円錐は 1 本）。

    以前はネックだけ `cone_half_angle_deg` の生値を使っており、頂点距離の値を持つ
    アルトだけ 4.52% 食い違って、別体では継ぎ目の気柱に φ0.56 の段ができていた。
    まずいのは「アルトが急なこと」ではなく、**食い違いが物理ではなくデータの有無で
    決まっていた**こと —— ソプラノに頂点距離が入った日に、ソプラノも黙って
    食い違い始める規則だった。UI の表示行ではなくここで見張る。
    """
    from saxsketch.core.schema import ParamSet
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    from saxsketch.instruments.saxophone.components import neck_profiles as npf
    for tid in SIZES:
        comp, p = _neck_params(tid)
        si = comp.size_info
        large = npf.bore_large_id(p, si)
        slope = (large - p["bore_small_id"]) / 2.0 / p["neck_length"]
        assert slope == pytest.approx(bpf.cone_tan(si), abs=1e-12), tid
        assert large == pytest.approx(NECK_LARGE_ID_MM[tid], abs=0.001), tid
    # 別体でも継ぎ目の気柱が連続すること（ネック大端の半径＝本体円錐の同じ位置の半径）
    for tid in SIZES:
        comp, p = _neck_params(tid)
        bc = get_registry().get("saxophone").make_component("body", tid)
        n = bc._neck()
        bp = dict(ParamSet(bc.param_specs(), bc.template["body"]).values)
        assert (npf.bore_radius_at(p["neck_length"], p, comp.size_info)
                == pytest.approx(bpf.cone_radius_at(float(n["neck_length"]), bp,
                                                    bc.size_info, n), abs=1e-9)), tid


def test_neck_taper_toggle_does_not_jump_the_shape():
    """`taper_from_cone` を off にしても形が跳ばないこと。

    on のとき `bore_large_id` パラメータは幾何に使われないが、**スライダはその値を
    表示し、`survey_card` は実測をその値と比べる**。導出値とずれていると、実測が
    「設計に一致」と出るのに作られる形は別、という状態になる。
    """
    from saxsketch.instruments.saxophone.components import neck_profiles as npf
    for tid in SIZES:
        comp, p = _neck_params(tid)
        on = npf.bore_large_id(dict(p, taper_from_cone="on"), comp.size_info)
        off = npf.bore_large_id(dict(p, taper_from_cone="off"), comp.size_info)
        assert on == pytest.approx(off, abs=0.05), (tid, on, off)


def test_neck_bent_shoulder_is_a_step_not_a_ramp():
    """曲げネックでもテノン肩・本体挿入部の肩が**段**であること。

    等間隔の `stations()` は段差の位置を持たないので、そのまま使うと肩が 1 区間ぶん
    寝る。ストレート経路（`_straight_zs`）だけが肩を明示していたため、**同じ
    パラメータで曲げ角 0 と 24° から違う形が出ていた**（alto で 5.6mm、tenor で
    6.4mm のスロープ）。
    """
    from saxsketch.instruments.saxophone.components import neck_profiles as npf
    for tid in ("alto", "tenor"):                    # 曲げのあるサイズ
        comp, p = _neck_params(tid)
        assert p["bend_angle"] > 0.0, tid
        ss = npf.stations(p)
        for z in npf.shoulder_zs(p):
            assert any(s == pytest.approx(z, abs=1e-9) for s in ss), (tid, z)
        # 肩の 2 点の間で半径が跳び、その幅は刻みではなく eps
        tl = p["tenon_length"]
        r0 = npf.outer_radius_at(tl, p, comp.size_info)
        r1 = npf.outer_radius_at(tl + npf._SHOULDER_EPS_MM, p, comp.size_info)
        assert abs(r1 - r0) > 0.5, (tid, r0, r1)
        assert npf._SHOULDER_EPS_MM < 0.01
        # ストレート経路と同じ肩を持つ（片方だけが肩を持っている状態に戻さない）
        zs = npf._straight_zs(p)
        for z in npf.shoulder_zs(p):
            assert any(s == pytest.approx(z, abs=1e-9) for s in zs), (tid, z)


def test_neck_available_not_planned():
    from saxsketch.instruments.saxophone.components import NeckComponent
    assert NeckComponent.available() is True


def test_neck_builds_valid_all_sizes():
    for tid in ("soprano", "alto", "tenor"):
        comp, p = _neck_params(tid)
        part = comp.build(p)
        assert part.is_valid
        assert part.volume > 0
        sim = comp.simulate(p)
        assert sim["kind"] == "neck" and sim["cards"]


def test_neck_watertight_configs(tmp_path):
    """ストレート / ベンド / ベント有無 のいずれも水密ソリッドになること。"""
    from saxsketch.export.models import check_mesh, export_model
    comp, base = _neck_params("tenor")
    configs = {
        "straight": dict(base, bend_angle=0.0),
        "bent_vent": dict(base),
        "vent_off": dict(base, octave_vent="off"),
    }
    for label, p in configs.items():
        part = comp.build(p)
        f = tmp_path / f"neck_{label}.stl"
        export_model(part, f, "stl", tolerance=0.05)
        q = check_mesh(f)
        assert q["watertight"] and q["winding_consistent"], (label, q)
    # ストレートは主軸 bbox 長 ≈ 全長（弧長）
    part = comp.build(configs["straight"])
    bb = part.bounding_box()
    assert bb.max.Z - bb.min.Z == pytest.approx(base["neck_length"], abs=0.5)


def test_neck_octave_vent_bores_hole():
    """ベント有効（チムニー0）はベント無効より材料体積が小さい＝孔が空いている。"""
    comp, base = _neck_params("tenor")
    on = comp.build(dict(base, octave_vent="on", chimney_height=0.0))
    off = comp.build(dict(base, octave_vent="off"))
    assert on.volume < off.volume - 20.0   # 貫通孔ぶん減る
    # ベント注意カードが出る／出ない
    titles_on = [c["title"] for c in comp.simulate(dict(base, octave_vent="on"))["cards"]]
    titles_off = [c["title"] for c in comp.simulate(dict(base, octave_vent="off"))["cards"]]
    assert any("オクターブベント" in t for t in titles_on)
    assert not any("オクターブベント" in t for t in titles_off)


def test_neck_fit_card_asymmetry():
    """テノン外径が規格に一致で ok、規格から外すと warn。"""
    comp, base = _neck_params("tenor")
    std = comp.size_info["neck_tenon_od_mm"]
    ok = next(c for c in comp.simulate(dict(base, tenon_od=std))["cards"]
              if c["title"] == "マウスピース適合")
    assert ok["status"] == "ok", ok["advice"]
    warn = next(c for c in comp.simulate(dict(base, tenon_od=std + 1.5))["cards"]
                if c["title"] == "マウスピース適合")
    assert warn["status"] == "warn"


def test_neck_survey_measure(tmp_path):
    """外部ネック メッシュから全長・ボアを実測し、採寸ターゲット外キーを含めないこと。"""
    from saxsketch.analysis import meshdiff
    from saxsketch.export.models import export_model
    comp, p = _neck_params("tenor", bend_angle=0.0)   # 直管＝主軸長が全長に一致
    part = comp.build(p)
    f = tmp_path / "neck.stl"
    export_model(part, f, "stl", tolerance=0.05)
    mesh = meshdiff.load_mesh(f)
    out = comp.survey_measure_mesh(mesh)
    targets = {t["key"] for t in comp.survey_targets()["params"]}
    assert set(out["measured"]).issubset(targets)
    assert out["measured"]["neck_length"] == pytest.approx(p["neck_length"], abs=15.0)


def test_neck_acoustic_sanity():
    """ボアテーパから TMM で共鳴を算出し、物理的に妥当な帯域に第1共鳴が乗ること。

    調律保証ではなく、寸法（mm/m 取り違え等）が破綻していないことのサニティ。
    """
    import numpy as np
    from saxsketch.acoustics import openwind_bridge as ob
    from saxsketch.instruments.saxophone.components import neck_profiles as npf
    comp, p = _neck_params("tenor", bend_angle=0.0)
    geo = [[z / 1000.0, max(r, 1e-4) / 1000.0]
           for (z, r) in npf.bore_stations(p, comp.size_info)]
    freqs = np.linspace(50.0, 2000.0, 600)
    z = np.abs(ob._tmm_impedance(geo, freqs))
    from scipy.signal import find_peaks
    idx, _ = find_peaks(z, prominence=np.max(z) * 0.05)
    fpk = [float(freqs[i]) for i in idx]
    assert any(120.0 <= f <= 1600.0 for f in fpk), fpk


def test_neck_export_endpoint(tmp_path):
    """/api/project/new component=neck → STL/STEP/3MF 出力・仕様書・BOM が通る。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    r = c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "tenor", "component_id": "neck"})
    assert r.status_code == 200, r.text
    assert r.json()["reference"] is None
    assert r.json()["simulation"]["kind"] == "neck"
    e = c.post("/api/export", json={
        "formats": ["stl", "step", "3mf"], "out_dir": str(tmp_path / "neck"),
        "make_package": False})
    assert e.status_code == 200, e.text
    assert e.json()["mesh_quality"]["watertight"]
    assert Path(e.json()["files"]["bom.csv"]).exists()
    html = Path(e.json()["files"]["spec.html"]).read_text(encoding="utf-8")
    assert html.count("<svg") == 1


# ------------------------------------------------------------------ 断面編集（バッフル）

def test_pchip_table_cache_is_bit_identical():
    """`_pchip` の係数表キャッシュが結果を 1 ビットも変えないこと。

    ドラッグ応答のために入れた高速化なので、形が動いたら意味がない
    （既定形状は実物 WindyCity の実測に合わせて校正してある）。
    """
    from saxsketch.instruments.saxophone.components import profiles as pf

    def uncached(pts, x):
        if x <= pts[0][0]:
            return pts[0][1]
        if x >= pts[-1][0]:
            return pts[-1][1]
        xs, ys, h, m = pf._pchip_table(pts)
        k = next(i for i in range(len(xs) - 1) if xs[i] <= x <= xs[i + 1])
        t = (x - xs[k]) / h[k]
        t2, t3 = t * t, t * t * t
        return (ys[k] * (2 * t3 - 3 * t2 + 1) + h[k] * m[k] * (t3 - 2 * t2 + t)
                + ys[k + 1] * (-2 * t3 + 3 * t2) + h[k] * m[k + 1] * (t3 - t2))

    tables = [pf._BODY_PROFILE, pf._SHOULDER_PROFILE, pf._CAVITY_W, pf._CAVITY_C,
              pf._CAVITY_D, pf._RAIL_WEIGHT, pf._TOP_ARCH]
    for tab in tables:
        lo, hi = tab[0][0], tab[-1][0]
        for i in range(501):
            x = lo + (hi - lo) * i / 500
            assert pf._pchip(tab, x).hex() == uncached(tab, x).hex(), (tab[0], x)


def test_params_scope_does_not_leak_across_dicts():
    """スコープ中でも**別の dict** を渡した呼び出しはキャッシュを素通りすること。

    `sensitivity()` は `{**p, key: v}` で摂動した dict を渡す。ここが素通り
    しないと摂動が効かず、感度表が全部ゼロになる（音色レーダーが嘘になる）。
    """
    from saxsketch.instruments.saxophone.components import profiles as pf

    p = _template_params("mouthpiece", "tenor")
    other = {**p, "overall_length": p["overall_length"] + 10.0}
    with pf.params_scope(p):
        a = pf.heel_z(p)
        b = pf.heel_z(other)
        assert b != a
        assert pf.heel_z(p) == a        # 元の p は汚れていない
    assert pf.heel_z(p) == a            # スコープを出ても同じ


def test_simulate_sensitivity_still_moves():
    """スコープ導入後も感度（摂動）が効いていること。"""
    comp = get_registry().get("saxophone").make_component("mouthpiece", "tenor")
    p = {s.key: s.default for s in comp.param_specs()}
    table = comp.simulate(p)["sensitivity"]["table"]
    moved = [k for k, row in table.items()
             if any(abs(v) > 1e-9 for v in row["deltas"].values())]
    assert len(moved) >= 3, table


def test_mp_section_curves_are_consistent():
    """断面の輪郭が「材料の中に空洞がある」形になっている。"""
    from saxsketch.instruments.saxophone.components import profiles as pf
    p = _template_params("mouthpiece", "tenor")
    c = pf.section_curves(p)
    for key in ("outer_top", "outer_bot", "reed", "roof", "floor",
                "shell_top", "bore_top", "bore_bot"):
        assert len(c[key]) >= 2, key
        zs = [z for z, _ in c[key]]
        assert zs == sorted(zs), key                      # z 昇順
    # 天井は床より上。天井は外殻の上限を（soft-min のバイアスぶんを見て）超えない。
    for (z, roof), (_, floor), (_, lim) in zip(c["roof"], c["floor"], c["shell_top"]):
        assert roof > floor, (z, roof, floor)
        assert roof <= lim + 1e-6, (z, roof, lim)
    # 折れ目（棚の終わり）が標本に必ず入っている＝描画で段が丸まらない
    assert any(abs(z - pf.baffle_plateau_end_z(p)) < 1e-6 for z, _ in c["roof"])


def test_mp_baffle_handles_span_and_activity():
    """ハンドルは型ごとに出し分けられ、span が線形写像として使える形になっている。"""
    from saxsketch.instruments.saxophone.components import profiles as pf
    base = _template_params("mouthpiece", "tenor")
    expect = {
        "straight": {"baffle_height"},
        "step": {"baffle_height", "baffle_plateau", "baffle_step_rise"},
        "curve": {"baffle_height", "baffle_curvature"},
        "rollover": {"baffle_height", "baffle_plateau", "rollover_radius"},
    }
    for bt, keys in expect.items():
        hs = pf.baffle_handles(dict(base, baffle_type=bt))
        assert {h["key"] for h in hs if h["active"]} == keys, bt
        for h in hs:
            if not h["active"]:
                continue
            assert h["min"] < h["max"], (bt, h["key"])
            assert h["axis"] in ("z", "y"), (bt, h["key"])
            # span が潰れているとドラッグ→値の逆写像が作れない
            assert abs(h["span"][1] - h["span"][0]) > 0.3, (bt, h["key"], h["span"])
            assert h["min"] <= h["value"] <= h["max"], (bt, h["key"])


def test_mp_baffle_handle_drag_moves_the_roof():
    """span の端まで動かすと天井が実際にその向きへ動く（ハンドルが効いている）。"""
    from saxsketch.instruments.saxophone.components import profiles as pf
    base = _template_params("mouthpiece", "tenor")
    for bt, key in [("step", "baffle_step_rise"), ("curve", "baffle_curvature"),
                    ("step", "baffle_plateau"), ("straight", "baffle_height")]:
        p = dict(base, baffle_type=bt)
        h = next(x for x in pf.baffle_handles(p) if x["key"] == key)
        lo = pf.cavity_roof_y(dict(p, **{key: h["min"]}), h["z"])
        hi = pf.cavity_roof_y(dict(p, **{key: h["max"]}), h["z"])
        assert abs(hi - lo) > 0.3, (bt, key, lo, hi)


def test_section_endpoint_and_preview_override():
    """/api/section が断面を返し、クエリの上書きは状態を変えない。"""
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)
    c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "tenor",
        "component_id": "mouthpiece"})
    r = c.get("/api/section")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["baffle_type"] == "step"
    assert len(body["curves"]["roof"]) > 50
    base_end = next(h for h in body["handles"] if h["key"] == "baffle_plateau")["z"]

    prev = c.get("/api/section?baffle_plateau=0.60")
    assert prev.status_code == 200
    moved = next(h for h in prev.json()["handles"]
                 if h["key"] == "baffle_plateau")["z"]
    assert moved > base_end + 5.0                      # プレビューは動いている
    # プロジェクトのパラメータは変わっていない
    assert c.get("/api/project").json()["params"]["baffle_plateau"] == 0.36
    assert next(h for h in c.get("/api/section").json()["handles"]
                if h["key"] == "baffle_plateau")["z"] == base_end
    # 断面を持たないコンポーネントは 404
    c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "tenor", "component_id": "reed"})
    assert c.get("/api/section").status_code == 404


def test_mp_baffle_handles_move_tone_metrics():
    """断面ハンドルを動かすと Tier2 の指標が動く（画面が形を説明している）。"""
    from saxsketch.acoustics import brightness as br
    base = _template_params("mouthpiece", "tenor")
    b0 = br.tone_metrics(base)["brightness"]
    assert br.tone_metrics(dict(base, baffle_step_rise=0.85))["brightness"] > b0 + 0.2
    assert br.tone_metrics(dict(base, baffle_plateau=0.70))["brightness"] > b0 + 0.2
    cv = dict(base, baffle_type="curve")
    assert (br.tone_metrics(dict(cv, baffle_curvature=1.0))["brightness"]
            > br.tone_metrics(dict(cv, baffle_curvature=-1.0))["brightness"] + 0.4)


# ============================================================ 管体（Phase 4-B.2a）

#: 3 サイズの円錐リーチ [mm]（スロート＝ネック小端からベル出口まで）。
#: `openwind_bridge._calibrate_extension` が「低音がその音で鳴る」長さとして解いた値で、
#: Tier1 の延長円錐と**同じもの**。ここがずれたら管体と音響が違う楽器になっている。
CONE_REACH_MM = {"soprano": 652.6, "alto": 997.3, "tenor": 1378.0}
#: ネックを省いて詰めたときのセント（＝(B) の落とし穴の大きさ）。頂点距離を含めた比。
NECK_DROPPED_CENTS = {"soprano": 355.0, "alto": 346.0, "tenor": 289.0}


def _body(tid, **override):
    """(comp, params, neck_params)。"""
    from saxsketch.core.schema import ParamSet
    comp = get_registry().get("saxophone").make_component("body", tid)
    vals = dict(ParamSet(comp.param_specs(), comp.template["body"]).values)
    vals.update(override)
    return comp, dict(ParamSet(comp.param_specs(), vals).values), comp._neck()


def test_body_template_has_every_param_and_is_available():
    from saxsketch.instruments.saxophone.components import BodyComponent
    assert BodyComponent.available() is True
    for tid in SIZES:
        comp = get_registry().get("saxophone").make_component("body", tid)
        missing = {s.key for s in comp.param_specs()} - set(comp.template["body"].keys())
        assert not missing, f"{tid} テンプレート欠落キー: {missing}"


def test_body_cone_reaches_the_calibrated_length():
    """管体の円錐が、音響が使っている延長円錐と同じ長さに届いていること。

    別に持つと「管体は届いているのに Tier1 は別の長さで解いている」状態になり、
    どちらが正しいのか誰にも分からなくなる。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    for tid, want in CONE_REACH_MM.items():
        comp, p, n = _body(tid)
        assert bpf.cone_reach_mm(p, n) == pytest.approx(want, abs=0.1), tid
        assert comp._target_cone_mm() == pytest.approx(want, abs=0.5), tid
        assert comp._cone_card(p)["status"] == "ok", tid


def test_body_integrated_and_separate_are_the_same_instrument():
    """一体型（ネックまで1部品）と別体で**気柱が完全に一致**すること。

    継ぎ目もテノンも音響モデルに入っていない（共鳴管はマウスピース→円筒ボア→
    欠損円錐で、「ネック」という区間を持たない）。だから一体化しても音程は
    動かない。**「一体型のほうが音が良い/悪い」とは言えない**という主張を、
    ここで固定する。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    for tid in SIZES:
        comp, sep, n = _body(tid, neck_joint="separate")
        _c, integ, _n = _body(tid, neck_joint="integrated")
        si = comp.size_info
        assert (bpf.acoustic_geometry(sep, si, n)
                == bpf.acoustic_geometry(integ, si, n)), tid
        # 部品の弧長だけが違う（一体型はネックのぶん長い）
        assert bpf.part_arc(integ, n) - bpf.part_arc(sep, n) == pytest.approx(
            float(n["neck_length"]), abs=1e-9), tid
        # 円錐は同じ位置から始まる
        assert bpf.cone_reach_mm(sep, n) == bpf.cone_reach_mm(integ, n), tid


def test_body_integrated_starts_at_the_throat_bore():
    """一体型の管はスロート（ネック小端）のボア径から始まること。

    ここが `neck_bore_id_mm` でなくなると、それは「ネックを省いた」形で、
    円錐の先端側が消えて別の楽器になる。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    for tid in SIZES:
        comp, p, n = _body(tid, neck_joint="integrated")
        si = comp.size_info
        assert (2.0 * bpf.bore_radius_at(0.0, p, si, n)
                == pytest.approx(si["neck_bore_id_mm"], abs=1e-6)), tid
        assert bpf.neck_throat_gap_mm(n, si) == pytest.approx(0.0, abs=0.05), tid


def test_body_dropping_the_neck_is_caught_as_a_short_cone():
    """(B)「ネックを外して詰める」は**弾かれない。形としては成立するから。**

    成立しないのではなく**別の楽器になる**（円錐の先端側が消えて高くなる）ので、
    `params_error` ではなくカードの warn で出す。`params_error` で弾くと
    「成立しない値は保存しない」規約に引っかかって実験そのものができなくなる。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    for tid in SIZES:
        # ボウは畳んだままだと短くした管に収まらず、**別の理由**で弾かれてしまう。
        # ここで見たいのは円錐の長さだけなので、ストレートにして切り分ける。
        # 側孔も同じ理由で外す —— 管を 1 本ぶん詰めるとベル寄りの穴が管の外へ
        # 出て、`hole_layout_error` が（正しく）弾いてしまう。穴が弾くこと自体は
        # `test_body_hole_layout_errors_instead_of_clamping` が見ている。
        comp, p, n = _body(tid, neck_joint="integrated", bow_angle=0.0,
                           finger_holes=0, thumb_vent="off")
        dropped = dict(p, body_arc_length=p["body_arc_length"] - float(n["neck_length"]))
        assert comp.params_error(dropped) is None, tid       # 形としては作れる
        card = comp._cone_card(dropped)
        assert card["status"] == "warn" and card["big"] == "円錐が短い", tid
        reach = bpf.cone_reach_mm(dropped, n)
        assert comp._cents_for(reach, comp._target_cone_mm()) == pytest.approx(
            NECK_DROPPED_CENTS[tid], abs=2.0), tid


def test_body_cents_include_the_apex_distance():
    """セント換算が**頂点距離を足してから**比を取っていること。

    鳴っている管は「マウスピースが代替する欠損円錐（頂点〜スロート）＋実物の管」。
    リーチだけの比で出すと頂点のぶんを落として過大になる（アルトのネック省略で
    +431 と出るが、正しくは +346）。
    """
    import math

    from saxsketch.acoustics import volume as ac_volume
    comp, _p, n = _body("alto")
    target = comp._target_cone_mm()
    dropped = target - float(n["neck_length"])
    apex = ac_volume.missing_cone(comp.size_info)["apex_distance_mm"]
    naive = -1200.0 * math.log2(dropped / target)
    assert naive == pytest.approx(431.0, abs=3.0)            # 頂点を落とした値
    assert comp._cents_for(dropped, target) == pytest.approx(346.0, abs=2.0)
    assert comp._cents_for(dropped, target) == pytest.approx(
        -1200.0 * math.log2((apex + dropped) / (apex + target)), abs=1e-9)


def test_body_bow_angle_does_not_change_the_air_column():
    """曲げても弧長が同じなら気柱は動かないこと（弧長近似の裏返し）。

    「折り位置を自由にできる」と言えるのはこの範囲まで。**曲げが音程に与える
    実際の影響はモデルに入っていない**ので、モデルが動かないことは
    「実物でも動かない」という意味ではない。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    comp, straight, n = _body("alto", bow_angle=0.0)
    _c, bent, _n = _body("alto", bow_angle=180.0)
    si = comp.size_info
    assert bpf.part_arc(straight, n) == bpf.part_arc(bent, n)
    assert bpf.acoustic_geometry(straight, si, n) == bpf.acoustic_geometry(bent, si, n)
    # 曲げたぶん、実際の背丈（z 方向）は縮む
    z_straight = bpf.centerline_point(bpf.part_end(straight, n), straight, n)[0][2]
    z_bent = bpf.centerline_point(bpf.part_end(bent, n), bent, n)[0][2]
    assert z_bent < z_straight - 100.0


def test_body_layout_errors_instead_of_clamping():
    """成立しない組は**理由を返して弾く**こと（黙って頭打ちにしない）。

    `ParamSpec` はパラメータを 1 本ずつしか見ないので、各自のレンジ内なのに
    組み合わせると成立しない値が作れる。黙ってクランプするとスライダを動かしても
    形が変わらない死んだ帯ができる（Stage I の `window_length` がそれだった）。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    comp, p, n = _body("alto")
    assert comp.params_error(p) is None
    # ボウが本体管に収まらない
    err = comp.params_error(dict(p, bow_start=750.0))
    assert err is not None and "ボウが本体管に収まりません" in err
    # ベルがボウと重なる
    err = comp.params_error(dict(p, bell_length=320.0))
    assert err is not None and "ベルがボウと重なります" in err
    # ベルが円錐より細い（実物のベルは細らない）
    end_dia = bpf.cone_end_dia(p, comp.size_info, n)
    err = comp.params_error(dict(p, bell_exit_dia=end_dia - 5.0))
    assert err is not None and "細くなっています" in err
    assert comp.params_error(dict(p, bell_exit_dia=end_dia + 0.5)) is None
    # 曲げ半径が管の外半径以下 → 断面が内側で折り返して自己交差する。
    # **これを弾かずに OCCT へ渡すと返ってこず、WSL の VM ごと落ちた。**
    # `ParamSpec` の下限（15.0）では表せない（成立する下限がサイズと肉厚で変わる）
    # ので、スライダの範囲内なのに成立しない値が作れる。組で見るしかない。
    err = comp.params_error(dict(p, bow_radius=15.0))
    assert err is not None and "折り返して自己交差" in err
    # 半径を上げるだけでは通らない。上げると弧長が伸びてベルと重なり、
    # さらに脚の間隔（2×半径）とベルの太さの兼ね合いも効く（下のテスト）。
    # ここは 3 つとも満たす組で「通る」ことを見る。
    assert comp.params_error(dict(p, bow_radius=50.0, bow_start=400.0)) is None


def test_body_folded_tube_does_not_hit_itself():
    """180° のボウで、ベルが行きの脚に当たる組を弾くこと。

    ロフトは通るのに `is_valid` が False のソリッドになる（掃引で
    `bell_exit_dia=max(220)` が実際にそうなった）。行きと帰りの脚は
    **2×曲率半径**しか離れないので、ベルを広げると当たる。

    **既定のアルトは 3mm しか余裕が無い**（軸間 90mm に対し外半径の和 87mm）。
    実機はベルを外へ振って逃がしているが、モデルはベルを帰りの脚と同軸に
    置いているので、ここは実機より不利な形になっている。
    """
    comp, p, _n = _body("alto")
    assert comp.params_error(p) is None                      # 既定（φ120）は通る
    err = comp.params_error(dict(p, bell_exit_dia=150.0))
    assert err is not None and "折り返した管が自分に当たっています" in err
    # 曲率半径を上げれば脚が離れるので通る
    assert comp.params_error(dict(p, bell_exit_dia=150.0, bow_radius=60.0,
                                  bow_start=400.0)) is None
    # ストレートは折り返さないので、いくら広げても当たらない
    comp_s, ps, _ns = _body("soprano")
    assert comp_s.params_error(dict(ps, bell_exit_dia=220.0)) is None


def test_body_integrated_has_no_phantom_tenon_shoulder():
    """一体型に**消えた段のステーション**が置かれていないこと。

    一体型のネック区間は `_fused_neck`（`body_tenon_length = -1.0`）で作るので、
    別体なら段になる `neck_length - body_tenon_length` に段は無い。生のネック
    パラメータで `npf.stations` を呼ぶと、そこに**半径の同じリングが 1μm 間隔で
    2 枚**並ぶ（スライバ面のもと）。テノン肩のほうは一体型にも在るので置かれる。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    for tid in SIZES:
        comp, p, n = _body(tid, neck_joint="integrated")
        ss = bpf.stations(p, comp.size_info, n)
        phantom = float(n["neck_length"]) - float(n["body_tenon_length"])
        assert not any(abs(s - phantom) < 0.01 for s in ss), (tid, phantom)
        tl = float(n["tenon_length"])
        assert sum(1 for s in ss if abs(s - tl) < 0.01) == 2, tid   # 肩は残る


def test_body_print_card_counts_segments_for_both_joints():
    """分割が要るのは一体型のせいではないこと（別体でも要る）を数で示す。"""
    from saxsketch.instruments.saxophone.components.neck import BED_HINT_MM
    for tid in SIZES:
        comp, sep, n = _body(tid, neck_joint="separate")
        _c, integ, _n = _body(tid, neck_joint="integrated")
        for p in (sep, integ):
            rows = dict(tuple(r) for r in comp._print_card(p)["rows"])
            segs = int(rows["分割の見込み"].replace(" 分割", ""))
            assert segs >= 2, (tid, p["neck_joint"], rows)   # どの構成でも 1 枚では出ない
        assert float(sep["body_arc_length"]) > BED_HINT_MM


# ------------------------------------------------------------------ 寸法の図示（Phase 4-C.5）


def _dim_component(component_id: str, template_id: str):
    """寸法を測るためのコンポーネントと現在値。参照が要る部品には付けて返す。"""
    comp = get_registry().get("saxophone").make_component(component_id, template_id)
    if comp.REQUIRES_REF:
        comp.set_refs({comp.REQUIRES_REF: {
            "params": _template_params(comp.REQUIRES_REF, template_id)}})
    return comp, _template_params(component_id, template_id)


def test_dimensions_measure_what_they_draw():
    """**値は線の両端から測られている**こと。

    ラベルの数字と実際に引かれる線の長さが食い違う経路を殺す。`value` を
    引数で渡せる設計だと、そこが必ず食い違いの入口になるので、
    `dimension.dim()` は a・b からしか値を作らない。
    """
    for cid in ("mouthpiece", "reed", "ligature"):
        for tid in SIZES:
            comp, p = _dim_component(cid, tid)
            dims = comp.dimensions(p)
            assert dims, (cid, tid)
            for d in dims:
                a, b, u = d["a"], d["b"], d["dir"]
                assert len(a) == len(b) == len(u) == 3
                assert d["value"] == pytest.approx(math.dist(a, b), abs=1e-9), (cid, d)
                assert d["value"] > 1e-9, (cid, d)          # 潰れた寸法は出さない
                assert math.isclose(math.dist(u, (0, 0, 0)), 1.0, abs_tol=1e-12)
                # 逃がす向きは寸法線と直交（斜めに逃がすと補助線が交差する）
                seg = [b[i] - a[i] for i in range(3)]
                assert abs(sum(u[i] * seg[i] for i in range(3))) < 1e-9, (cid, d)
                assert d["label"] and d["key"] and d["unit"]
                assert isinstance(d["level"], int) and d["level"] >= 0


def test_dimensions_report_the_frozen_window():
    """窓長は**実効値**を測り、スライダの指定と違えば併記すること。

    `window_end_z` は `bore_start_z − 4.0` 側でも頭打ちになるので、ソプラノは
    可動域 24〜44mm のうち 28.5mm 以上が丸ごと死んでいる（アルトは 37.9mm 以上、
    テナーは全域が効く）。図がスライダの値を書き写す実装だと、この帯で
    **形と数字が食い違ったまま**になる。
    """
    # **アルトの天井は既定値そのものになった**（2026-09-05）。PHROX の窓の実測で
    # window_length 38.67 / bore_length 48.30 を組で入れた結果、既定がちょうど
    # 天井に載っている ＝ **スライダを 1 目盛り上げた瞬間からクランプ**。
    # 選択の副作用ではなく実測の帰結（bore_length を上限より下げれば余地は
    # 増えるが、その値には根拠が無い）。
    frozen = {"soprano": 28.54, "alto": 38.67}
    for tid in SIZES:
        comp, base = _dim_component("mouthpiece", tid)
        d = next(x for x in comp.dimensions(base) if x["key"] == "window_length")
        assert "requested" not in d, tid          # 既定は届いている
        assert d["value"] == pytest.approx(base["window_length"])

        p = {**base, "window_length": 44.0}
        d = next(x for x in comp.dimensions(p) if x["key"] == "window_length")
        assert d["value"] == pytest.approx(profiles.window_length_effective(p))
        if tid in frozen:
            assert d["value"] == pytest.approx(frozen[tid], abs=0.01), tid
            assert d["requested"] == 44.0, tid
        else:
            assert "requested" not in d, tid      # tenor は 44 まで本当に開く


def test_dimensions_report_the_effective_seat_setback():
    """座位置は実効値を測り、飲まれたときだけ要求値を併記すること（4-C.3b）。

    測り方を最大径起点へ直したので、既定（0.0）では飲みが起きず併記も出ない。
    前へ出しすぎて帯が胴から落ちる手前で止まったときだけ、**黙って飲むのでは
    なく報告する**（4-C.3b の答えは変わらない。飲む条件のほうが変わった）。
    """
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    for tid in SIZES:
        comp, p = _dim_component("ligature", tid)
        m = comp.ref_params()
        # 既定は最大径に密着 ＝ 長さ 0 なので線ごと出さない（潰れた寸法は描かない）
        assert lp.effective_seat_setback(m, p) == pytest.approx(0.0, abs=1e-9), tid
        assert all(x["key"] != "seat_setback" for x in comp.dimensions(p)), tid
        # 可動域の中ほどでは図の値が要求どおり動く（旧定義では動かなかった）
        q = {**p, "seat_setback": 10.0}
        d2 = next(x for x in comp.dimensions(q) if x["key"] == "seat_setback")
        assert d2["value"] == pytest.approx(10.0, abs=1e-9), tid
        assert d2["value"] == pytest.approx(
            lp.effective_seat_setback(m, q), abs=1e-9), tid
        assert "requested" not in d2, tid           # 飲んでいないので併記しない
        # 出しすぎたときだけ実効値と要求値が割れ、指定値が併記される
        r = {**p, "seat_setback": 200.0}
        d3 = next(x for x in comp.dimensions(r) if x["key"] == "seat_setback")
        assert d3["requested"] == pytest.approx(200.0), tid
        assert d3["value"] < 200.0 - 1.0, tid


def test_dimensions_are_not_nominal_values():
    """ソリッドに存在しない量を寸法線にしないこと。

    `reed_width` はテーブルの幅ではない —— テーブルは平面カットなので実幅は
    半径とカット深さから決まり、**z によって変わる**（座中央で 13.98 / 15.14 /
    14.66mm）。`reed_width` が決めているのは窓幅の公称値とリガチャーのタブ幅
    だけで、マウスピースの面を 1 つも決めていない。
    """
    want = {"soprano": 13.9835, "alto": 15.1423, "tenor": 14.6565}
    for tid in SIZES:
        comp, p = _dim_component("mouthpiece", tid)
        dims = comp.dimensions(p)
        assert not any(x["value"] == pytest.approx(p["reed_width"], abs=1e-9)
                       for x in dims), tid
        s0, s1 = profiles.ligature_seat_range(p)
        d = next(x for x in dims if x["key"] == "table_flat_width")
        assert d["value"] == pytest.approx(
            profiles.table_flat_width(p, (s0 + s1) / 2.0), abs=1e-9)
        assert d["value"] == pytest.approx(want[tid], abs=0.001), tid


def test_dimensions_section_plane_is_derived():
    """断面へ写せるかは**宣言ではなく座標から導く**こと。

    幅方向（x）の寸法は中央面に写らないので自動的に落ちる。宣言にすると
    「書き忘れ」と「書き間違い」の 2 つの穴が空く。
    """
    from saxsketch.core.dimension import in_section_plane
    for cid in ("mouthpiece", "reed", "ligature"):
        for tid in SIZES:
            comp, p = _dim_component(cid, tid)
            for d in comp.dimensions(p):
                flat = abs(d["a"][0]) < 1e-9 and abs(d["b"][0]) < 1e-9                     and abs(d["dir"][0]) < 1e-9
                assert in_section_plane(d) is flat, (cid, d["key"])
    comp, p = _dim_component("mouthpiece", "alto")
    sec = [d["key"] for d in comp.dimensions(p) if in_section_plane(d)]
    assert "table_flat_width" not in sec        # 幅方向なので断面には出ない
    assert "overall_length" in sec and "body_dia" in sec


def test_dimensions_do_not_build():
    """寸法は **CAD ビルドを伴わない**こと（断面と同じ要件）。

    断面はドラッグ中に毎フレーム叩かれ、寸法はその応答に相乗りする。ここで
    ビルドに触ると 1 本 5 秒の OCCT がドラッグの経路に入る。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    from saxsketch.server.state import STATE
    c = TestClient(app)

    def boom(*_a, **_k):
        raise AssertionError("寸法の経路が CAD ビルドを呼んだ")

    for cid in ("mouthpiece", "reed", "ligature"):
        assert c.post("/api/project/new",
                      json={"instrument_id": "saxophone", "template_id": "alto",
                            "component_id": cid}).status_code == 200
        STATE.component.build = boom          # インスタンス属性で覆う
        STATE.component.build_cad = boom
        assert c.get("/api/dimensions").status_code == 200
        sec = c.get("/api/section")
        assert sec.status_code in (200, 404)
    # 覆ったビルドを残さない（STATE はプロセスに 1 個なので後続へ漏れる）
    assert c.post("/api/project/new",
                  json={"instrument_id": "saxophone", "template_id": "alto",
                        "component_id": "mouthpiece"}).status_code == 200


def test_section_and_dimensions_agree():
    """2 つの経路が同じ定義を読んでいること。

    3D は `/api/dimensions`、断面は `/api/section` の応答に相乗りする（ドラッグ中も
    形と同じフレームで動かすため）。運び方が 2 通りでも**定義は 1 か所**。
    """
    from fastapi.testclient import TestClient
    from saxsketch.server.app import app
    c = TestClient(app)

    def new(component_id, template_id="alto"):
        return c.post("/api/project/new",
                      json={"instrument_id": "saxophone", "template_id": template_id,
                            "component_id": component_id})

    assert new("mouthpiece").status_code == 200
    dims = c.get("/api/dimensions").json()
    assert c.get("/api/section").json()["dimensions"] == dims
    assert len(dims) == 11

    # ligature が 5 本なのは、既定（`seat_setback` 0.0 ＝ 最大径に密着）で
    # 座位置の寸法線が長さ 0 になるので出さないから（4-D.5）。
    for cid, n in (("reed", 8), ("ligature", 5)):
        assert new(cid).status_code == 200
        assert len(c.get("/api/dimensions").json()) == n, cid
        assert c.get("/api/section").status_code == 404       # 断面は持たない

    # 寸法を持たない部品は空。UI はこれを見てトグルを出さない。
    for cid in ("neck", "body"):
        assert new(cid).status_code == 200
        assert c.get("/api/dimensions").json() == []


# ------------------------------------------------------------------ 側孔（Phase 4-B.2b）

#: 0 次配置（開孔位置＝その音が鳴る円錐長）のまま解いたときの、最も外れる運指の
#: セント。**これは「設計が外れている量」ではなく 4-B.2c のソルバが潰す残差**。
#: 全部マイナス（低い）なのは物理で、有限径の穴は完全な開口端ではないうえ、
#: ベル寄りの開孔列が実効長を伸ばすため。
ZEROTH_ORDER_WORST_CENTS = {"soprano": -177.0, "alto": -225.0, "tenor": -246.0}

#: 指孔のスパン [mm]（最上と最下の指孔の弧長差）。**両手（目安 200mm）に
#: 収まらない。** これは配置の失敗ではなく、このサイズでキーレス全音階が
#: 成立しないという結論。
HOLE_SPAN_MM = {"soprano": 317.0, "alto": 476.0, "tenor": 637.0}


def test_holes_do_not_move_anything_that_was_already_recorded():
    """側孔を足しても、**穴を持たない管の数字は 1 つも動かない**こと。

    `_tmm_impedance` を区間行列＋分岐行列へ組み替えたので、穴が無いときに
    以前と違う経路を通っていないかをここで固定する。マウスピース・リードの
    記録値（`TIER1_RESIDUAL_CENTS` など）はこの上に載っている。
    """
    import numpy as np

    from saxsketch.acoustics import openwind_bridge as ob
    for tid in SIZES:
        si = _size_info(tid)
        p = _template_params("mouthpiece", tid)
        geo = ob.build_resonator(p, si, use_openwind=False)
        freqs = np.geomspace(50.0, 2000.0, 200)
        a = ob._tmm_impedance(geo, freqs)
        b = ob._tmm_impedance(geo, freqs, holes=[])
        assert np.array_equal(a, b), tid                     # ビット一致
        assert ob.first_resonance_cents(p, si) == pytest.approx(
            TIER1_RESIDUAL_CENTS[tid], abs=2.0), tid


def test_tone_hole_junction_matrix_is_reciprocal():
    """分岐行列の行列式が恒等的に 1（可逆・相反）であること。

    T 型の 2 本の直列腕が同じ Za/2 になっていない、といった組み立て間違いは
    ここに出る。物理の当否ではなく**式の写し間違い**を捕まえる網。
    """
    import numpy as np

    from saxsketch.acoustics import toneholes
    freqs = np.geomspace(80.0, 1600.0, 40)
    for open_ in (False, True):
        a11, a12, a21, a22 = toneholes.junction_matrix(
            freqs, 0.012, 0.004, 0.003, open_)
        det = a11 * a22 - a12 * a21
        assert np.allclose(det, 1.0, atol=1e-12), (open_, det[:3])


def test_tone_hole_model_adds_no_engine_disagreement():
    """**TMM と OpenWind が同じ側孔を解いていること。**

    合っているかは文献ではなく OpenWind と突き合わせて測る（`sound_speed()` が
    `Physics` の式を写しているのと同じ扱い）。見るのは差の絶対値ではなく、
    **穴を足したことで差が増えるか**。穴が無くても 2 エンジンは 3 セント前後
    違う（損失と放射モデルの違い）ので、そこを基準にする。
    """
    import math

    import numpy as np

    from saxsketch.acoustics import openwind_bridge as ob
    if not ob.HAS_OPENWIND:
        pytest.skip("OpenWind 未導入")
    from openwind import ImpedanceComputation
    si = _size_info("alto")
    f1 = float(si["low_note_sounding_hz"])
    geo = ob.ideal_cone_geometry(si, use_openwind=False)
    freqs = np.geomspace(0.6 * f1, 3.0 * f1, 600)
    holes = [{"label": "h1", "role": "finger",
              "x_m": ob.ideal_cone_hole_x(si, 600.0),
              "radius_m": 0.004, "chimney_m": 0.002}]
    rows = ob.ow_hole_rows(holes)
    chart = [["label", "closed", "open"], ["h1", "x", "o"]]

    def diff(flags, hs, kw):
        ft = ob._lowest_peak_hz(freqs, ob._tmm_impedance(geo, freqs, hs, flags))
        r = ImpedanceComputation(freqs, geo, temperature=ob.TEMPERATURE_C,
                                 source_location="entrance", **kw)
        fo = ob._lowest_peak_hz(freqs, np.asarray(r.impedance))
        return 1200.0 * math.log2(ft / fo)

    base = diff([], [], {})
    for note, flags in (("closed", [False]), ("open", [True])):
        d = diff(flags, holes,
                 {"holes_valves": rows, "fingering_chart": chart, "note": note})
        assert abs(d - base) < 1.5, (note, d, base)


def test_open_hole_raises_chimney_lowers_width_raises():
    """**4-B.2c が使うつまみが 3 本とも効いていること**（向きの拘束）。

    開けると上がる／チムニーを足すと下がる／太くすると上がる。どれか 1 本でも
    効かなければ 2c は解けない。値ではなく向きだけを固定する。
    """
    comp, base, _n = _body("alto")
    solver, holes = comp._solver(base)
    closed = solver.scale()[0]["freq"]
    one_open = solver.scale()[1]["freq"]
    assert one_open > closed * 1.01                          # 開けると上がる
    taller = solver.scale(comp._shifted(holes, d_chimney_mm=2.0))[1]["freq"]
    assert taller < one_open                                 # チムニーで下がる
    wider = solver.scale(comp._shifted(holes, d_dia_mm=2.0))[1]["freq"]
    assert wider > one_open                                  # 太いと上がる


def test_zeroth_order_placement_is_flat_and_by_how_much():
    """0 次配置の残差を記録値に固定する。**2c が潰す量そのもの。**

    向きは 3 サイズとも**低い側**（有限径の穴は完全な開口端ではなく、しかも
    ベル寄りの開孔列が実効長を伸ばす）。ここが正になったら物理ではなく実装の
    バグを疑うこと。
    """
    for tid in SIZES:
        comp, base, _n = _body(tid)
        rows = comp._solver(base)[0].scale()
        assert abs(rows[0]["cents"]) < 3.0, (tid, rows[0])   # 全閉は物差しどおり
        worst = min(r["cents"] for r in rows)
        assert worst == pytest.approx(ZEROTH_ORDER_WORST_CENTS[tid], abs=8.0), tid
        assert all(r["cents"] < 0.0 for r in rows[1:]), tid


def test_hole_chimney_is_measured_from_the_bore_not_from_the_outside():
    """音響のチムニー長が**壁の厚みを含む**こと（二重計上・置き去りの検出）。

    `hole_chimney` は外面からの立ち上がりで、音響のチムニー長ではない。
    肉厚を動かしたときに音響が黙って置き去りになる経路が無いことを見る。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    comp, base, n = _body("alto")
    si = comp.size_info
    s = bpf.hole_layout(base, si, n)[0]["s_mm"]
    c0 = bpf.hole_chimney_mm(s, base, si, n)
    assert c0 == pytest.approx(base["wall_thickness"] + base["hole_chimney"], abs=1e-6)
    thick = dict(base, wall_thickness=base["wall_thickness"] + 1.0)
    assert bpf.hole_chimney_mm(s, thick, si, n) == pytest.approx(c0 + 1.0, abs=1e-6)
    tall = dict(base, hole_chimney=base["hole_chimney"] + 2.0)
    assert bpf.hole_chimney_mm(s, tall, si, n) == pytest.approx(c0 + 2.0, abs=1e-6)


def test_hole_span_is_set_by_the_interval_not_by_the_layout():
    """**指孔のスパンは音程で決まる。穴を寄せることはできない。**

    全閉から 1 オクターブ上までの位置比はボア形に依らず f_高/f_低 そのもので、
    頂点から測った管の 1 − 2^(-10/12) = 44.1% にあたる。だから「届かない」は
    配置の失敗ではなく**このサイズでキーレス全音階が成立しないという結論**。
    カードがそう言うことを、数字の側から固定する。
    """
    from saxsketch.acoustics import volume as ac_volume
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    for tid in SIZES:
        comp, base, n = _body(tid)
        si = comp.size_info
        span = bpf.hole_span_mm(base, si, n)
        assert span == pytest.approx(HOLE_SPAN_MM[tid], rel=0.02), tid
        apex = ac_volume.missing_cone(si)["apex_distance_mm"]
        lowest = max(h["s_mm"] for h in bpf.hole_layout(base, si, n)
                     if h["role"] == "finger")
        assert span / (apex + lowest) == pytest.approx(
            1.0 - 2.0 ** (-10.0 / 12.0), rel=0.01), tid
        assert span > bpf.HAND_SPAN_MM, tid                  # 3 サイズとも届かない
        assert comp._reach_card(base)["big"] == "届きません", tid


def test_body_hole_layout_errors_instead_of_clamping():
    """成立しない穴の組は**理由を返して弾く**（黙ってクランプしない）。"""
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    comp, base, _n = _body("alto")
    assert comp.params_error(base) is None
    # 管を詰めるとベル寄りの穴が外へ出る（ボウは**別の理由**で先に弾かれるので
    # ストレートにして切り分ける）
    err = comp.params_error(dict(base, body_arc_length=400.0, bow_angle=0.0))
    assert err is not None and "管の外" in err
    # 親指孔を指孔にぶつける
    err = comp.params_error(dict(base, thumb_offset=0.0))
    assert err is not None and "重なります" in err
    # 穴がその位置のボアより太い（ソプラノの上の方は細い）
    comp_s, ps, ns = _body("soprano")
    top = min(h["s_mm"] for h in bpf.hole_layout(ps, comp_s.size_info, ns))
    r_bore = bpf.wall_inner_radius_at(top, ps, comp_s.size_info, ns)
    err = comp_s.params_error(dict(ps, hole_dia=2.0 * r_bore + 1.0))
    assert err is not None and "ボア径" in err


def test_body_without_holes_touches_no_boolean():
    """穴が 0 本のとき、ソリッドに**手を触れない**こと。

    `finger_holes=0` かつ親指孔 off は 4-B.2a の形そのもの。ここで空の融合や
    空の差分を回すと、ブーリアンの費用と壊れ方だけが増える。
    """
    comp, _p, _n = _body("alto")
    p0 = _body("alto", finger_holes=0, thumb_vent="off")[1]
    sentinel = object()
    assert comp._apply_holes(sentinel, p0) is sentinel
    assert [c["title"] for c in comp.simulate(p0)["cards"]] == [
        "ネック接続", "円錐リーチ（音響は未接続）", "印刷・肉厚・気密"]


def test_body_holes_are_actually_bored():
    """穴が実際にソリッドから材料を抜いていること（ストレートで軽く回す）。"""
    comp, p, _n = _body("soprano")
    holed = comp.build(p)
    assert len(holed.solids()) == 1
    plain = comp.build(dict(p, finger_holes=0, thumb_vent="off"))
    assert plain.volume > holed.volume + 100.0               # 8 穴ぶん減っている


def test_scale_reuses_the_span_matrices():
    """運指・穴径・チムニーを振っても**区間行列は 1 回しか作らない**こと。

    ここが壊れると音階カードが `simulate` の予算（50ms）を割る。実測で区間行列が
    費用のほぼ全部（アルト既定で 557 スライス × 400 周波数）。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    comp, base, _n = _body("alto")
    calls = {"n": 0}
    orig = ob._span_matrix

    def counted(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    ob._span_matrix = counted
    try:
        solver, holes = comp._solver(base)
        after_init = calls["n"]
        solver.scale()
        solver.scale(comp._shifted(holes, d_chimney_mm=1.0))
        solver.scale(comp._shifted(holes, d_dia_mm=1.0))
    finally:
        ob._span_matrix = orig
    assert after_init == len(holes) + 1                      # 穴の数 + 1 区間
    assert calls["n"] == after_init                          # そのあと 1 回も作らない


def test_hole_variant_with_a_moved_hole_is_refused():
    """**位置を変えた変種は使い回せない**ことを明示的に拒むこと。

    区間の切れ目が変わるので、黙って古い区間行列を使うと嘘の答えが出る。
    """
    comp, base, _n = _body("alto")
    solver, holes = comp._solver(base)
    moved = [dict(h) for h in holes]
    moved[0]["x_m"] += 0.01
    with pytest.raises(ValueError):
        solver.scale(moved)


def test_chimney_rises_from_the_bore_side_not_from_the_outer_surface():
    """チムニーの円柱が**ボア内面から**始まること。

    外面に接する平面から立てると、管が曲面なので底の円盤は接点以外どこも管の
    外に浮く（サジッタは既定アルトで 0.36〜0.62mm）。融合が接触だけになり、
    **掃引でボウの上の 2 本が実際にちぎれてソリッドが 3 個になった**
    （アルト・チムニー 8mm）。内面から立てれば必ず肉の中で重なり、しかも
    `x ≥ inner_r` の円柱は気柱に入らない（軸から外れるほど中心線からの距離は
    伸びるため）。

    **ここで見るのは規則だけ。** 実体（ソリッドが 1 個か）はビルドが 13 秒
    かかるので `cad/body/sweep_holes.py build alto` の仕事。
    """
    import math

    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    from saxsketch.instruments.saxophone.components.body import CHIMNEY_RIM_MM
    comp, base, n = _body("alto", hole_chimney=8.0)
    si = comp.size_info
    for hp in bpf.hole_placement(base, si, n):
        assert hp["chimney_base_r"] == pytest.approx(hp["inner_r"], abs=1e-9)
        # 天面の高さは「外面 + 立ち上がり」のまま（内面から立てても外へは伸びない）
        assert hp["chimney_base_r"] + hp["chimney_len"] == pytest.approx(
            hp["outer_r"] + hp["chimney_height"], abs=1e-9)
        # 底の円盤の縁は気柱の外（＝肉の中）にある
        rim = hp["dia"] / 2.0 + CHIMNEY_RIM_MM
        assert math.hypot(hp["chimney_base_r"], rim) >= hp["inner_r"]
        # 肉を跨いで重なっている（接触だけではない）
        assert hp["chimney_base_r"] < hp["outer_r"]


#: 両手（200mm）に収まる指孔の本数。**設計値ではなくサイズと音階の性質。**
#: 全閉を入れると soprano 5 音 / alto 4 音 / tenor 3 音まで。
HOLES_THAT_FIT = {"soprano": 4, "alto": 3, "tenor": 2}


def test_how_many_holes_fit_in_two_hands():
    """「段数を減らせ」と言うなら**何段まで減らせるか**を数字で出すこと。

    スパンは音程だけで決まるので、これは設計値ではなくサイズと音階の並びの性質。
    4-B.2c はここから始まる（位置を解く前に、解ける本数が決まっている）。
    """
    from saxsketch.instruments.saxophone.components import body_profiles as bpf
    for tid in SIZES:
        comp, base, n = _body(tid)
        si = comp.size_info
        fit = bpf.max_finger_holes_in_span(si)
        assert fit == HOLES_THAT_FIT[tid], tid
        # その本数なら実際に収まり、1 本足すと溢れる
        assert bpf.hole_span_mm(dict(base, finger_holes=fit), si, n) <= bpf.HAND_SPAN_MM
        assert bpf.hole_span_mm(dict(base, finger_holes=fit + 1), si, n) > bpf.HAND_SPAN_MM
        # カードにも出る
        rows = dict(tuple(r) for r in comp._reach_card(base)["rows"])
        assert f"{fit} 本" in rows[f"{bpf.HAND_SPAN_MM:.0f}mm に収まる本数"], tid
