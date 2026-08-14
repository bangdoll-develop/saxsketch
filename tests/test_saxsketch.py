"""SaxSketch 結合テスト: ジオメトリ・音響・プロジェクトI/O・API。"""
import collections
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
    # アルトだけ公表実測（SBA 217.5mm）があるのでそれを採る。実測ネック内径 12.7mm から
    # 導出すると 227.3mm で 4.5% 長い。内径をテノン外径からの一律規則で推定していた頃は
    # 241.7mm ＝ 11% だったので、ネックを実測したぶんだけ食い違いが縮んだ。
    # 実測がある箇所だけ差し替え、無い箇所は導出のまま残す方針は変えない。導出値を
    # 217.5 へ合わせに行かない（合わせると半頂角が実測の顔をした逆算値になる）。
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
IN_TUNE_INSERTION_MM = {"soprano": 23.5, "alto": 13.6, "tenor": 20.9}

# **その挿し込み量での**実効容積 / 欠損円錐（soprano +25 / alto +21 / tenor +26%）。
# 0 ではないのがこの模型の要点で、マウスピースは代替する円錐より短いぶん太くて
# 釣り合う。挿し込み量と容積比という独立な 2 つの指標が同じことを言っている。
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
    for tid, f in fracs.items():
        assert 0.53 < f < 0.54, (tid, f)


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
    テナーのボアを 46mm（既定 57.5）にして `cork_depth` を上限 32mm へ持っていくと、
    推定は 1.61mm（実用域 3〜32 の外）だが厳密解は 5.05mm で**域内**。
    """
    from saxsketch.acoustics import openwind_bridge as ob
    p = dict(_template_params("mouthpiece", "tenor"), bore_length=46.0, cork_depth=32.0)
    si = _size_info("tenor")
    t = ob.tuning_position(p, si)
    assert t["method"] == "solved", t          # 域外に出かけたので解き直している
    assert t["reachable"], t
    assert t["in_tune_mm"] == pytest.approx(5.05, abs=0.5), t
    # 本当に域外の形状は域外のまま返す（解き直しても救われない）
    far = dict(p, bore_length=40.25)
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
    """終了済みか。**ゾンビも終了扱い**（親が回収する前に見ることがある）。"""
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
        for cid in ("mouthpiece", "reed", "ligature", "neck"):
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


#: アルトのテーブル平坦部の終端 [mm]。**実測ではなく実測 2 件から出る量**
#: （最大径の位置 21.4 と傾斜テーブルの構成式）。どちらの実測にも直接は現れない。
ALTO_TABLE_END_MM = 73.0


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
    """
    from saxsketch.instruments.saxophone.components import reference_check
    si = _size_info("alto")
    p = _template_params("mouthpiece", "alto")
    assert reference_check.reed_length_is_measured(si)
    _, reed_hi = reference_check.reed_length_range(si)

    assert profiles.table_cut_end_z(p) == pytest.approx(ALTO_TABLE_END_MM, abs=0.1)
    assert profiles.table_cut_end_z(p) > reed_hi
    assert reference_check.mouthpiece_card(p, si)["status"] == "ok"

    # 借り物（テナー比 0.1628 × 全長 91.7 = 14.93）に戻すと軽微が出る
    borrowed = dict(p, shank_length=14.93)
    assert profiles.table_cut_end_z(borrowed) < reed_hi
    assert reference_check.mouthpiece_card(borrowed, si)["status"] == "warn"


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


def test_reference_card_all_match():
    """規格照合カードが3サイズ×2部品すべてで「一致」になること。

    ソプラノのマウスピースだけ「テーブル終端 / リード全長域」が軽微になる。
    **これはカードが仕事をしている状態で、消してはいけない。** テーブル終端 60.0mm が
    ケーン 59.1 は上回るが樹脂 62.0 に 2.0mm 足りないことを言っている
    （`SOPRANO_LONG_REED_OVERHANG_MM`）。**乖離は 1 行も出ないこと**、軽微は
    その 1 行に閉じていることまで確かめる。
    """
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        mp = reg.make_component("mouthpiece", tid)
        cards = mp.simulate({s.key: s.default for s in mp.param_specs()})["cards"]
        card = next(c for c in cards if "照合" in c["title"])
        assert not [r for r in card["rows"] if "乖離" in r[1]], (tid, card["rows"])
        minor = [r for r in card["rows"] if "軽微" in r[1]]
        if tid == "soprano":
            assert len(minor) == 1 and "リード全長域" in minor[0][0], (tid, card["rows"])
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

def test_flat_bottom_rect_pts_is_flat():
    """底面が厳密に平坦であること（リードのテーブル密着の前提）。"""
    from saxsketch.geometry.builders import flat_bottom_rect_pts
    pts = flat_bottom_rect_pts(w=13.0, h=2.0, y0=0.0, corner_r=0.5)
    ys = [y for _, y in pts]
    xs = [x for x, _ in pts]
    assert min(ys) == 0.0
    assert [y for y in ys if y == 0.0] == [0.0, 0.0]  # 底辺は2点ちょうど
    assert max(ys) == pytest.approx(2.0)
    assert min(xs) == pytest.approx(-6.5) and max(xs) == pytest.approx(6.5)


def test_flat_bottom_rect_pts_constant_vertex_count():
    """点数が corner_r によらず一定であること。

    `loft_sections` のルールドロフトはパラメータ対応で面を張るため、断面ごとに
    点数が変わると角の位置が辺の途中に写像されて面がねじれる。
    """
    from saxsketch.geometry.builders import flat_bottom_rect_pts
    counts = {len(flat_bottom_rect_pts(13.0, 2.0, 0.0, r))
              for r in (0.0, 1e-9, 0.01, 0.5, 1.0, 5.0)}   # 5.0 は上限クランプ
    assert len(counts) == 1
    # 角丸ゼロ相当でも底面は平坦のまま、上端は h に届く
    pts = flat_bottom_rect_pts(13.0, 2.0, 0.0, 0.0)
    assert min(y for _, y in pts) == 0.0
    assert max(y for _, y in pts) == pytest.approx(2.0, abs=0.01)


def test_loft_sections_volume_and_watertight(tmp_path):
    """一定断面のロフト体積が解析値と一致し、水密であること。"""
    from saxsketch.geometry.builders import flat_bottom_rect_pts, loft_sections
    from saxsketch.export.models import check_mesh, export_model
    pts = flat_bottom_rect_pts(w=10.0, h=2.0, y0=0.0, corner_r=0.0)
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
    # バーク（未削部）は幅方向一定
    zb = (zv + p["reed_length"]) / 2.0
    assert rp.edge_thickness(p, zb) == pytest.approx(rp.thickness(p, zb, 0.0))


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


def test_ligature_plate_types(alto_ligature):
    """プレートの有無で体積が順序どおり（なし < レール < 全面）になること。"""
    comp, p = alto_ligature
    vols = {k: comp.build({**p, "plate_type": k}).volume
            for k in ("none", "rail", "plain")}
    assert vols["none"] < vols["rail"] < vols["plain"]


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
    rt = comp.reed_thickness()
    assert lp.flat_half_width(m, p, rt) <= lp.requested_tab_half_width(m, p) + 1e-9

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
        assert lp.flat_half_width(narrow, p, rt) \
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

    reg = get_registry().get("saxophone")
    shelf_cases = 0
    for tid in SIZES:
        lig = reg.make_component("ligature", tid)
        m0 = _template_params("mouthpiece", tid)
        specs = {s.key: s for s in lig.param_specs()}
        base = dict(ParamSet(lig.param_specs(), lig.template["ligature"]).values)
        rt0 = float(lig.template["reed"]["heel_thickness"])
        for bd, cl, rc, rt in itertools.product(
                (m0["body_dia"] * 0.6, m0["body_dia"], m0["body_dia"] * 1.4),
                (specs["clearance"].min, specs["clearance"].max),
                (specs["reed_clearance"].min, specs["reed_clearance"].max),
                (rt0 * 0.6, rt0, rt0 * 1.5)):
            m = dict(m0, body_dia=bd)
            p = dict(base, clearance=cl, reed_clearance=rc)
            z0, z1 = lp.seat_range(m, p)
            zm = (z0 + z1) / 2.0
            r_in = profiles.outer_radius(m, zm) + cl
            if lp.requested_tab_half_width(m, p) < lp._shelf_half_width(
                    r_in, profiles.table_plane_y(m, zm)):
                shelf_cases += 1
            for sections in (lp.inner_sections(m, p, rt),
                             lp.outer_sections(m, p, rt)):
                for s in sections:
                    hit = self_intersection(s["pts"])
                    assert hit is None, (tid, bd, cl, rt, hit)
                    assert signed_area(s["pts"]) > 0, (tid, bd, cl, rt)  # 反時計回り
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
        assert html.count("<svg") == 1          # 断面図が1枚出ている
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


def test_body_segments_cover_and_join(alto):
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


def test_body_spline_stays_on_the_law(alto):
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
    shift = sum(abs(narrow[i]["freq"] - base[i]["freq"]) for i in range(3, 8))
    assert shift > 1.5, [(b["freq"], n["freq"]) for b, n in zip(base, narrow)]
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

    r = c.put("/api/project/params", json={"params": {"tip_opening": 99.0}})
    assert r.json()["params"]["tip_opening"] == 3.2  # 上限にクランプ

    r = c.post("/api/project/new", json={
        "instrument_id": "saxophone", "template_id": "alto",
        "component_id": "body"})
    assert r.status_code == 400  # 未実装コンポーネント（Phase 4-B.2）

    r = c.get("/api/model.stl?quality=preview")
    assert r.status_code == 200 and len(r.content) > 10000


# ------------------------------------------------------------------ ポート競合

def test_port_fallback():
    """占有ポートを検出し、空きへ退避するヘルパーの挙動。main() は起動しない。"""
    import socket

    from saxsketch.server import app as srv

    host = "127.0.0.1"
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.bind((host, 0))
    lsock.listen(1)
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
    from saxsketch.server.buildworker import WORKER
    from saxsketch.server.state import STATE

    if not WORKER.start():
        pytest.skip("この環境ではビルドワーカを起動できません")
    try:
        STATE.new_project("saxophone", "tenor", "mouthpiece", None)
        spec = STATE.build_spec(0.05)
        assert WORKER.build_stl(spec) == STATE._stl_bytes_inproc(0.05)
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
