"""SaxSketch 結合テスト: ジオメトリ・音響・プロジェクトI/O・API。"""
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
    # アルトだけ公表実測（SBA 217.5mm）があるのでそれを採る。導出すると 242mm で
    # 11% 長い（ネック内径をテノン外径からの一律規則で推定しているため）。
    # 実測がある箇所だけ差し替え、無い箇所は導出のまま残す方針。
    alto_cone = ac_volume.missing_cone(_size_info("alto"))
    assert alto_cone["source"] == "measured"
    assert alto_cone["apex_distance_mm"] == pytest.approx(217.5)
    assert alto_cone["derived_apex_mm"] == pytest.approx(241.7, abs=1.0)
    # 採用した頂点距離と広がりが自己矛盾しないこと（共鳴管の生成が同じ値を使う）
    assert alto_cone["throat_radius_mm"] / alto_cone["tan_theta"] == pytest.approx(217.5)
    assert ac_volume.missing_cone(_size_info("tenor"))["source"] == "derived"

    # サイズ順に単調（ソプラノ < アルト < テナー）
    ccs = [ac_volume.missing_cone(_size_info(t))["cc"] for t in SIZES]
    assert ccs[0] < ccs[1] < ccs[2]


# 実測した残差 [cent]。テナーだけ届かない。
#
# 空洞を外殻に封じ込めた（Phase 3.6）結果、実物寸法の胴に入る容積が上限になった。
# テナーは目標 18.0cc に対し到達上限が 13.7cc しかない。以前は封じ込め拘束が無く、
# チェンバーが本体の外へ膨らんだ分まで体積積分が数えて「-0.1 cent」と表示していた。
# 合格の方が嘘だったので、緩めるのではなく事実を記録する。
#
# 目標側の疑いも残る: テナーのネック小端内径 15.4mm はテノン外径からの推定値で、
# 公表実測が無い（アルトは 217.5mm の実測があり、導出値より 11% 短かった）。
# ユーザーが自分のネックをノギスで測れば（Phase 4-A）解消しうる。
TIER1_RESIDUAL_CENTS = {"soprano": -1.0, "alto": -0.5, "tenor": 53.9}


def test_tier1_matches_recorded_residual():
    """Tier1 の残差が記録値どおりであること。良好かどうかではなく、変化の検知が目的。"""
    from saxsketch.acoustics import volume as ac_volume
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        rep = ac_volume.tier1_report(profiles.cavity_volume_cc(p), _size_info(tid),
                                     saturated=profiles.chamber_saturated(p))
        assert rep["deviation_cents"] == pytest.approx(
            TIER1_RESIDUAL_CENTS[tid], abs=2.0), (tid, rep)
    # ソプラノとアルトは実際に良好。テナーは正直に sharp を出す。
    def status(tid):
        p = _template_params("mouthpiece", tid)
        return ac_volume.tier1_report(profiles.cavity_volume_cc(p), _size_info(tid))["status"]
    assert status("soprano") == "ok"
    assert status("alto") == "ok"
    assert status("tenor") == "sharp"


def test_tier1_advice_admits_saturation():
    """届かないのに「チェンバーを広げろ」とだけ言わないこと。

    肉厚制限で頭打ちならスライダを上げても形は変わらない。効かない操作を勧めるのは
    ユーザーの時間を捨てさせる。
    """
    from saxsketch.acoustics import volume as ac_volume
    p = _template_params("mouthpiece", "tenor")
    assert profiles.chamber_saturated(p)
    rep = ac_volume.tier1_report(profiles.cavity_volume_cc(p), _size_info("tenor"),
                                 saturated=True)
    assert "頭打ち" in rep["advice"]


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


def test_beak_taper_spans_body():
    """ビークがティップからショルダーまで本体を切り続けること。

    ビーク面を直線にしていたときは、`beak_height` が胴の全高に近い既定値だったため
    全長の 1/4 で外形を追い越し、テーパが消えてただの円筒になっていた。
    同時に空洞天井の clamp（`beak_y - min_wall`）まで無効化されていた。
    """
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        L = p["overall_length"]
        for t in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
            z = t * L
            assert profiles.beak_y(p, z) < profiles.outer_radius(p, z), (tid, t)
        # 単調に立ち上がる（くさび→バイトポイント→ショルダー）
        ys = [profiles.beak_y(p, t * L) for t in (0.0, 0.15, 0.3, 0.45)]
        assert all(a < b for a, b in zip(ys, ys[1:])), (tid, ys)


def test_table_reaches_reed_heel():
    """テーブル平面がリード踵より後ろまで届くこと。

    外形プロファイルのリガチャー座を動かしたとき、テーブル終端の比率リテラルを
    置き忘れてリードの後端 20mm が宙に浮いていた。比率は profiles が単独で持つ。
    """
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        heel = _size_info(tid)["reed_std_length_mm"]
        assert profiles.table_cut_end_z(p) > heel, tid
        # 踵の直前ではまだ平面（ランプが始まっていない）
        assert profiles.cut_top_y(p, heel - 1.0) == pytest.approx(profiles.table_y(p))


def test_bore_clears_corked_tenon():
    """ボアがコルクを巻いたテノンに挿さること。

    以前は bore_dia がテノン外径そのものだった。コルク分の隙間が無く、実物の
    ネックには物理的に入らないマウスピースが出ていた。照合カードもテノン外径と
    直接比べて「一致」と言っていたので誤りが固定されていた。
    """
    from saxsketch.instruments.saxophone.components import reference_check
    for tid in SIZES:
        si = _size_info(tid)
        p = _template_params("mouthpiece", tid)
        need = reference_check.required_bore_dia(si)
        assert need == pytest.approx(si["neck_tenon_od_mm"]
                                     + 2.0 * si["neck_cork_thickness_mm"])
        assert p["bore_dia"] >= need - 0.05, (tid, p["bore_dia"], need)
        # コルク厚は neck_bore_id_mm の導出とも整合していること（前提が二つに割れない）
        assert si["neck_bore_id_mm"] == pytest.approx(
            si["neck_tenon_od_mm"] - 2.0 * (si["neck_cork_thickness_mm"] + 0.4))
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


def test_ligature_seat_matches_reed_heel():
    """全長はリード規格長から決まる。座の後端に踵が来ること。"""
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        _, seat1 = profiles.ligature_seat_range(p)
        assert seat1 == pytest.approx(_size_info(tid)["reed_std_length_mm"], abs=1.5)


def test_cavity_station_roles():
    """空洞は 窓→チェンバー(最大)→スロート(最狭)→ボア の三段であること。"""
    for tid in SIZES:
        p = _template_params("mouthpiece", tid)
        st = profiles.cavity_stations(p)
        assert all("role" in s for s in st)
        assert [s["role"] for s in st][-3:] == ["chamber", "throat", "bore"]

        def area(s):
            return profiles.superellipse_area(s["w"], s["h"], s["n"])

        # チェンバー最大部はスロートより広い。窓直後のステーションはビークの下で
        # 外殻に切り詰められスロートより狭くなりうるので、index でなく最大部を見る。
        chamber = profiles.chamber_max_station(st)
        throat = profiles.stations_by_role(st, "throat")[0]
        assert area(throat) < area(chamber), tid
        # スロートはチェンバー最大部からボアまでの最狭部
        after = [s for s in st if s["z"] >= chamber["z"]]
        assert min(after, key=area) is throat, (tid, [(s["role"], round(area(s))) for s in after])
        # throat_ratio は面積比。半径比で定義していたとき、指数の違う真円ボアとの間で
        # 比 1.0 でもスロートの方が 1.8% 広くなり、最狭部が最狭でなくなっていた。
        p10 = dict(p, throat_ratio=1.0)
        st10 = profiles.cavity_stations(p10)
        th10 = profiles.stations_by_role(st10, "throat")[0]
        bo10 = profiles.stations_by_role(st10, "bore")[0]
        assert area(th10) == pytest.approx(area(bo10), rel=1e-6), tid
        # z は単調増加（ロフトが潰れない）
        assert all(a["z"] < b["z"] for a, b in zip(st, st[1:])), tid


def test_reference_card_all_match():
    """規格照合カードが3サイズ×2部品すべてで「一致」になること。"""
    reg = get_registry().get("saxophone")
    for tid in SIZES:
        mp = reg.make_component("mouthpiece", tid)
        cards = mp.simulate({s.key: s.default for s in mp.param_specs()})["cards"]
        card = next(c for c in cards if "照合" in c["title"])
        assert card["status"] == "ok", (tid, card["rows"])

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
    """踵がリガチャー座の後端に届かない設定を警告すること。"""
    comp, p = alto_reed
    m = comp.ref_params()
    from saxsketch.instruments.saxophone.components import profiles
    _, seat1 = profiles.ligature_seat_range(m)
    assert p["reed_length"] >= seat1                  # 既定は届いている

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

    リード共振を大きく変えると発振するレジスタが変わる。OpenWind 必須なので
    WSL でのみ実行される。
    """
    pytest.importorskip("openwind")
    from saxsketch.acoustics import openwind_bridge as ob
    from saxsketch.acoustics import reed_model
    comp, p = alto_reed
    m = comp.ref_params()

    def play(tip):
        pp = {**p, "material": "cane", "tip_thickness": tip}
        ov = reed_model.reed_override(reed_model.reed_properties(pp, m), pp)
        _, meta = ob.synthesize(m, comp.size_info, "normal",
                                duration=0.15, override=ov)
        return meta["f0"]

    soft, hard = play(0.30), play(0.55)
    assert soft > 0 and hard > 0            # どちらも自励発振している
    assert abs(hard - soft) / soft > 0.05   # レジスタ/音高が動いた


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
    """内周が参照マウスピースのボディ径 + はめあい隙間に一致し、追従すること。"""
    from saxsketch.instruments.saxophone.components import ligature_profiles as lp
    from saxsketch.instruments.saxophone.components import profiles
    comp, p = alto_ligature
    m = comp.ref_params()
    z0, z1 = lp.seat_range(m, p)
    expect = profiles.outer_radius(m, (z0 + z1) / 2.0) + p["clearance"]
    assert lp.inner_radius(m, p) == pytest.approx(expect, abs=1e-9)
    assert lp.inner_radius(m, p) == pytest.approx(m["body_dia"] / 2.0 + p["clearance"],
                                                  abs=0.05)
    # ボディ径を変えると内周が追従する（＝自動整合）
    comp.set_refs({"mouthpiece": {"params": {**m, "body_dia": m["body_dia"] + 2.0}}})
    assert lp.inner_radius(comp.ref_params(), p) == pytest.approx(
        lp.inner_radius(m, p) + 1.0, abs=0.02)
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
        # ボディ径を絞ると棚が狭くなりリードが入らない → 黙って切り詰めず警告する
        narrow = {**m, "body_dia": 20.0}
        assert lp.flat_half_width(narrow, p, rt) \
            < lp.requested_tab_half_width(narrow, p)
        card = fit(narrow)
        assert card["status"] == "warn" and "収納幅" in card["advice"]
    finally:
        comp.set_refs({"mouthpiece": {"params": m}})


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
    # 単一ピークで見ない: 周波数グリッドが約2.4Hz刻みなので、実際の移動量が
    # グリッド境界のどちら側に落ちるかで 2.5Hz と 4.9Hz を行き来する。
    # 上位共鳴の総移動量で見れば量子化に左右されない。
    shift = sum(abs(narrow[i]["freq"] - base[i]["freq"]) for i in range(3, 8))
    assert shift > 12.0, [(b["freq"], n["freq"]) for b, n in zip(base, narrow)]
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
        l_total = ob.C_SOUND / (2.0 * si["low_note_sounding_hz"])
        x_cork = (p["overall_length"] - p["cork_depth"]) / 1000.0
        assert geo[-1][0] == pytest.approx(
            x_cork + l_total - cone["apex_distance_mm"] / 1000.0, abs=1e-4), tid
        # 円錐の始端はネック小端内径。マウスピースのボアより細い
        r_neck = cone["throat_radius_mm"] / 1000.0
        assert geo[-2][1] == pytest.approx(r_neck, abs=1e-6), tid
        assert r_neck < profiles.bore_radius(p) / 1000.0, tid

        res = ob.impedance(p, si)
        assert abs(res["first_cents_vs_target"]) < 20.0, (tid, res["first_note"])


# ------------------------------------------------------------------ 音響 Tier3（音合成）

def test_coarsen_keeps_ends_and_spacing(alto):
    from saxsketch.acoustics import openwind_bridge as ob
    comp, p = alto
    geom = ob.build_resonator(p, comp.goal_seek_size_info())
    co = ob._coarsen(geom)
    assert co[0] == list(geom[0]) and co[-1] == list(geom[-1])
    assert len(co) <= len(geom)
    # 最終セグメント以外は最小間隔を満たす（末尾は両端保持のため例外）
    gaps = [co[i + 1][0] - co[i][0] for i in range(len(co) - 2)]
    assert all(g >= ob.SIM_MIN_DX for g in gaps)


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
    assert meta["f0"] > 0
    # 鳴った音はインピーダンス解析の共鳴ピークのいずれか（レジスタは問わない）。
    # 短いシミュは FFT 分解能が粗いので許容は 8%。
    peaks = [pk["freq"] for pk in ob.impedance(p, si)["peaks"]]
    assert any(abs(meta["f0"] - f) / f < 0.08 for f in peaks), (meta["f0"], peaks)


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
    base_dia = _template_params("mouthpiece", "alto")["body_dia"]
    assert after == pytest.approx(before + (30.0 - base_dia) / 2.0, abs=0.02)

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
        "component_id": "neck"})
    assert r.status_code == 400  # 未実装コンポーネント（Phase 4）

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
