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
    base = ob.impedance(p, si)["peaks"][0]["freq"]
    narrow = dict(p); narrow["throat_ratio"] = 0.7
    moved = ob.impedance(narrow, si)["peaks"][0]["freq"]
    assert abs(moved - base) > 1.0       # スロート変更でピークが動く


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
        "component_id": "reed"})
    assert r.status_code == 400  # 未実装コンポーネント

    r = c.get("/api/model.stl?quality=preview")
    assert r.status_code == 200 and len(r.content) > 10000
