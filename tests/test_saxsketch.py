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


def test_all_templates_build():
    reg = get_registry()
    for tmpl in ["soprano", "alto", "tenor"]:
        comp = reg.get("saxophone").make_component("mouthpiece", tmpl)
        p = {s.key: s.default for s in comp.param_specs()}
        part = comp.build(p)
        assert part.is_valid and part.volume > 5000


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
    assert abs(narrow[5]["freq"] - base[5]["freq"]) > 5.0     # 上位共鳴が動く
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
