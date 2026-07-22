"""サクソフォン マウスピース コンポーネント。

ジオメトリ構成:
  1. 外形回転体（Z軸回り、アウターR プロファイル）
  2. ビークカット（上面の斜めカット）
  3. テーブル/フェイシングカット（下面。フェイシングカーブ含む）
  4. 内部空洞（窓〜バッフル〜チェンバーのスーパー楕円ロフト + ボア円筒）を減算
"""
from __future__ import annotations

import math

from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec
from saxsketch.geometry.builders import (
    loft_stations,
    revolve_profile,
    yz_profile_cut_solid,
)
from . import profiles
from . import reference_check
from saxsketch.acoustics import brightness as ac_brightness
from saxsketch.acoustics import harmonics as ac_harmonics
from saxsketch.acoustics import volume as ac_volume


def _specs(t: dict) -> list[ParamSpec]:
    """テンプレート値 t を初期値としてスキーマを構築。"""
    def f(key, label, cat, unit, lo, hi, step, effect, advanced=False):
        return ParamSpec(key=key, label=label, category=cat, type="float", unit=unit,
                         default=t[key], min=lo, max=hi, step=step, effect=effect,
                         advanced=advanced)

    return [
        # --- フェイシング ---
        f("tip_opening", "ティップ開き", "フェイシング", "mm", 1.0, 3.2, 0.05,
          "大きいほど自由に鳴り音量が出るが、コントロールと息の量が必要になる"),
        f("facing_length", "フェイシング長", "フェイシング", "mm", 16.0, 30.0, 0.5,
          "明るさへの影響が最大の要素。長いほど倍音が豊かでオープンな響き"),
        ParamSpec(key="facing_curve", label="カーブ種別", category="フェイシング",
                  type="choice", default=t["facing_curve"],
                  choices=[Choice("elliptic", "楕円"), Choice("radial", "円弧")],
                  effect="吹奏感の性格。楕円=現代的で反応が速い、円弧=クラシカル"),
        f("tip_rail_width", "ティップレール幅", "フェイシング", "mm", 0.5, 2.0, 0.1,
          "狭いほどレスポンスが速いが雑音が出やすい"),
        f("side_rail_width", "サイドレール幅", "フェイシング", "mm", 0.6, 2.0, 0.1,
          "狭いほど効率よく鳴るがリードミスに敏感になる"),
        # --- バッフル ---
        ParamSpec(key="baffle_type", label="バッフル種別", category="バッフル",
                  type="choice", default=t["baffle_type"],
                  choices=[Choice("straight", "ストレート"),
                           Choice("rollover", "ロールオーバー"),
                           Choice("step", "ステップ"),
                           Choice("high", "ハイバッフル")],
                  effect="音色の性格を決める最重要要素。ハイ=ブライト/パワー、ストレート=ダーク"),
        f("baffle_height", "バッフル高さ", "バッフル", "mm", 0.0, 5.0, 0.1,
          "高いほど明るくエッジの効いた音。0でクラシカルなダークトーン"),
        f("rollover_radius", "ロールオーバー半径", "バッフル", "mm", 3.0, 20.0, 0.5,
          "ロールオーバー時の肩の丸み。小さいほどエッジ感が強い", advanced=True),
        # --- チェンバー ---
        f("throat_ratio", "スロート断面積比", "チェンバー", "比", 0.60, 1.35, 0.01,
          "ボア断面積に対する最狭部の比。小=明るく抵抗感増、大=ダークで太い"),
        f("chamber_ratio", "チェンバー断面積比", "チェンバー", "比", 1.00, 3.00, 0.05,
          "スロート最狭部に対するチェンバー最大部の断面積比。大=内容積が増えダークで太い"),
        ParamSpec(key="chamber_shape", label="チェンバー形状", category="チェンバー",
                  type="choice", default=t["chamber_shape"],
                  choices=[Choice("round", "ラウンド"), Choice("square", "スクエア")],
                  effect="ラウンド=滑らかな倍音、スクエア=ヴィンテージ系の複雑な倍音"),
        # --- ボア ---
        f("bore_dia", "ボア径", "ボア", "mm", t["bore_dia"] - 1.0, t["bore_dia"] + 1.0, 0.05,
          "ネックコルクとの適合寸法。音程の基準に直結", advanced=True),
        f("bore_length", "ボア長", "ボア", "mm", 18.0, 60.0, 1.0,
          "円筒ボア部の長さ。コーク挿入深さ＋数mm が下限", advanced=True),
        f("cork_depth", "コーク挿入深さ", "ボア", "mm", 12.0, 32.0, 1.0,
          "ネックの標準挿入量。音程チェックの基準位置"),
        # --- ウィンドウ ---
        f("window_length", "ウィンドウ長", "ウィンドウ", "mm", 24.0, 44.0, 0.5,
          "リード振動部の長さ。長いほど低音が豊か"),
        f("reed_width", "リード幅", "ウィンドウ", "mm", 10.0, 18.0, 0.1,
          "使用リード規格の幅。テーブル・窓幅の基準", advanced=True),
        # --- 外形 ---
        # レンジをボディ径基準にするのは、胴の全高 0.9·body_dia を超える値が形状として
        # 意味を持たない（ビーク面が本体の外に出る）ため。既定 0.55·body_dia は幾何的な
        # 暫定値で実測ではない → ノギスでの上書きが本筋。
        f("beak_height", "ビーク高さ", "外形", "mm",
          round(0.35 * t["body_dia"], 1), round(0.75 * t["body_dia"], 1), 0.5,
          "バイトポイント（ティップから全長の1/4）でのテーブル面からの高さ。"
          "くわえたときの口の開き量。既定は暫定値なので実測での上書きを推奨"),
        f("body_dia", "ボディ径", "外形", "mm", 20.0, 34.0, 0.1,
          "リガチャー適合寸法", advanced=True),
        f("overall_length", "全長", "外形", "mm", 70.0, 130.0, 0.5,
          "マウスピース全長", advanced=True),
        # --- 製造 ---
        f("min_wall", "最小肉厚", "製造", "mm", 1.2, 4.0, 0.1,
          "3Dプリント強度の下限。レジン2mm以上推奨", advanced=True),
        ParamSpec(key="material", label="材料プリセット", category="製造",
                  type="choice", default=t["material"],
                  choices=[Choice("resin", "レジン(光造形)"),
                           Choice("pla", "PLA(FDM)"),
                           Choice("petg", "PETG(FDM)"),
                           Choice("nylon_sls", "ナイロンPA12(SLS)")],
                  effect="仕様書の印刷推奨条件と食品接触の注意書きに反映"),
    ]


class MouthpieceComponent(Component):
    id = "mouthpiece"
    label = "マウスピース"

    def __init__(self, descriptor: dict, template: dict):
        super().__init__(descriptor, template)
        self.size = template["size"]
        self.size_info = descriptor["sizes"][self.size]

    def param_specs(self) -> list[ParamSpec]:
        return _specs(self.template["mouthpiece"])

    # ------------------------------------------------------------ 形状生成

    def build(self, params: dict):
        from build123d import Pos, Solid

        p = params
        length = p["overall_length"]

        # 1) 外形回転体
        n_st = 28
        radii = [(length * i / (n_st - 1), profiles.outer_radius(p, length * i / (n_st - 1)))
                 for i in range(n_st)]
        body = revolve_profile(radii)

        # 2) ビークカット（上面）。曲線なので端点2点では平面になってしまう。
        n_bk = 40
        beak_pts = [(-3.0 + (length + 6.0) * i / (n_bk - 1), 0.0) for i in range(n_bk)]
        beak_pts = [(z, profiles.beak_y(p, z)) for z, _ in beak_pts]
        beak_pts += [(length + 3.0, 80.0), (-3.0, 80.0)]
        beak_cut = yz_profile_cut_solid(beak_pts, half_width=p["body_dia"])

        # 3) テーブル/フェイシングカット（下面）
        z_end = profiles.table_cut_end_z(p)
        n_f = 48
        face_pts = [(-3.0 + (z_end + 3.0) * i / (n_f - 1), 0.0) for i in range(n_f)]
        face_pts = [(z, profiles.cut_top_y(p, z)) for z, _ in face_pts]
        face_pts += [(z_end, -80.0), (-3.0, -80.0)]
        facing_cut = yz_profile_cut_solid(face_pts, half_width=p["body_dia"])

        # 4) 内部空洞（ロフト + ボア円筒）
        cavity = loft_stations(profiles.cavity_stations(p))
        zb = profiles.bore_start_z(p)
        r = profiles.bore_radius(p)
        bore = Pos(0, 0, zb) * Solid.make_cylinder(r, length - zb + 1.5)

        part = body - beak_cut - facing_cut - cavity - bore
        return part

    # ------------------------------------------------------------ シミュレーション

    def simulate(self, params: dict) -> dict:
        tier1 = ac_volume.tier1_report(profiles.cavity_volume_cc(params), self.size_info,
                                       saturated=profiles.chamber_saturated(params))
        tier2 = ac_brightness.tone_metrics(params)
        sens = ac_brightness.sensitivity(params, self.param_specs())
        harm = ac_harmonics.harmonic_series(tier2)
        return {
            "kind": "mouthpiece",
            "tier1": tier1,
            "tier2": tier2,
            "sensitivity": sens,
            "harmonics": harm,
            "cards": [reference_check.mouthpiece_card(params, self.size_info)],
        }

    def cavity_volume(self, params: dict) -> dict:
        return profiles.cavity_volume_cc(params)

    # ------------------------------------------------------------ Tier3（インピーダンス・音合成）

    def impedance(self, params: dict) -> dict:
        from saxsketch.acoustics import openwind_bridge as ob
        return ob.impedance(params, self.size_info)

    def synthesize(self, params: dict, embouchure: str) -> tuple[bytes, dict]:
        from saxsketch.acoustics import openwind_bridge as ob
        return ob.synthesize(params, self.size_info, embouchure)

    def scale(self, params: dict) -> tuple[bytes, dict]:
        from saxsketch.acoustics import openwind_bridge as ob
        return ob.scale(params, self.size_info)

    def goal_seek_size_info(self) -> dict:
        return self.size_info

    def regions(self, params: dict) -> dict:
        return profiles.param_regions(params)

    # ------------------------------------------------------------ 採寸ワークフロー（Phase 4-A）

    #: 採寸可能な設計パラ。比率系(throat/chamber_ratio)と choice/bool は実測できないため除く。
    _SURVEY_PARAM_KEYS = [
        "tip_opening", "facing_length", "tip_rail_width", "side_rail_width",
        "window_length", "reed_width", "beak_height", "body_dia",
        "overall_length", "bore_dia", "cork_depth", "baffle_height",
    ]
    #: 採寸可能な音響基準定数（size_info。descriptor 由来で params の外）。
    _SURVEY_SIZE_FIELDS = [
        {"key": "neck_bore_id_mm", "label": "ネック小端内径", "unit": "mm"},
        {"key": "neck_tenon_od_mm", "label": "ネックテノン外径", "unit": "mm"},
        {"key": "missing_cone_length_mm", "label": "欠損円錐長（頂点まで）", "unit": "mm"},
    ]

    def survey_targets(self) -> dict:
        specs = {s.key: s for s in self.param_specs()}
        params = [
            {"key": k, "label": specs[k].label, "unit": specs[k].unit,
             "min": specs[k].min, "max": specs[k].max, "step": specs[k].step}
            for k in self._SURVEY_PARAM_KEYS if k in specs
        ]
        size = [dict(f) for f in self._SURVEY_SIZE_FIELDS]
        return {"params": params, "size": size}

    def survey_card(self, before_params: dict, before_size: dict,
                    measured_params: dict, measured_size: dict) -> dict | None:
        """採寸値 vs 採寸前の設計/基準値。reference_check の判定基盤を再利用。"""
        specs = {s.key: s for s in self.param_specs()}
        size_meta = {f["key"]: (f["label"], f["unit"]) for f in self._SURVEY_SIZE_FIELDS}
        rows, verdicts = [], []
        for k, mv in measured_params.items():
            s = specs.get(k)
            if s is None or k not in before_params:
                continue
            step = s.step or 0.1
            r, v = reference_check._row(
                f"{s.label} 実測/設計", float(mv), float(before_params[k]),
                s.unit, max(0.6 * step, 0.05), max(2.5 * step, 0.2))
            rows.append(r)
            verdicts.append(v)
        for k, mv in measured_size.items():
            label, unit = size_meta.get(k, (k, "mm"))
            base = before_size.get(k)
            if base is None:
                continue
            r, v = reference_check._row(
                f"{label} 実測/従前", float(mv), float(base), unit, 0.2, 0.6)
            rows.append(r)
            verdicts.append(v)
        if not rows:
            return None
        return reference_check._finish(
            "採寸 vs 設計", rows, verdicts,
            "実測をプロジェクトへ反映しました。設計をいじって破綻したら"
            "「採寸時点へ戻す」で復元できます。")

    def analyze_import(self, frozen_params: dict, ref_mesh, edited_mesh) -> dict:
        """領域別偏差 + 断面実測によるパラメータ逆算。"""
        from saxsketch.analysis import meshdiff
        from . import measure
        result = measure.estimate_params(edited_mesh, frozen_params,
                                         self.param_specs())
        return {
            "regions": meshdiff.region_deviations(
                ref_mesh, edited_mesh, self.regions(frozen_params)),
            "params": result["params"],
            "warnings": result["warnings"],
        }

    # ------------------------------------------------------------ BOM / 仕様書

    def bom(self, params: dict) -> list[dict]:
        mat_labels = {"resin": "レジン(光造形)", "pla": "PLA", "petg": "PETG",
                      "nylon_sls": "ナイロンPA12(SLS)"}
        size_label = {"soprano": "ソプラノ", "alto": "アルト", "tenor": "テナー"}[self.size]
        return [
            {"type": "3Dプリント", "name": f"マウスピース本体（{size_label}）",
             "qty": 1, "material": mat_labels.get(params["material"], params["material"]),
             "note": "食品接触面。印刷後に洗浄・シーリング推奨（仕様書参照）"},
            {"type": "市販品", "name": f"リード（{size_label}用）", "qty": 1,
             "material": "ケーン/樹脂", "note": f"幅 {params['reed_width']:.1f}mm 規格"},
            {"type": "市販品", "name": f"リガチャー（{size_label}用）", "qty": 1,
             "material": "-", "note": f"ボディ径 φ{params['body_dia']:.1f}mm 適合品"},
            {"type": "市販品", "name": "マウスピースパッチ", "qty": 1,
             "material": "シリコン", "note": "ビーク保護（任意）"},
        ]

    def _section_svg(self, params: dict) -> str:
        """側面断面図（外形・内部空洞・テーブル面）。"""
        from saxsketch.export.svg import polyline_svg
        pr = profiles.side_profile_polylines(params)
        ty = pr["table_y"]
        zs = [z for z, _ in pr["outer_top"]]
        return polyline_svg([
            {"pts": pr["outer_top"], "stroke": "#222", "width": 1.5},
            {"pts": pr["outer_bot"], "stroke": "#222", "width": 1.5},
            {"pts": pr["cavity_top"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": pr["cavity_bot"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": [(min(zs), ty), (profiles.table_cut_end_z(params), ty)],
             "stroke": "#cc3300",
             "width": 0.8, "dash": "2 2"},
        ], "側面断面図（実線=外形 / 青破線=内部空洞 / 赤破線=テーブル面） 単位:mm")

    def spec_extras(self, params: dict) -> dict:
        p = params
        vol = profiles.cavity_volume_cc(p)
        dims = [
            ("全長", f"{p['overall_length']:.1f} mm"),
            ("ティップ開き", f"{p['tip_opening']:.2f} mm"),
            ("フェイシング長", f"{p['facing_length']:.1f} mm"),
            ("ボア径", f"φ{p['bore_dia']:.2f} mm"),
            ("ボディ径（リガチャー座）", f"φ{p['body_dia']:.1f} mm"),
            ("ウィンドウ長 × 窓幅",
             f"{p['window_length']:.1f} × {profiles.window_width(p):.1f} mm"),
            ("内容積（全体/実効）", f"{vol['total_cc']:.1f} / {vol['effective_cc']:.1f} cc"),
        ]
        return {"dimensions": dims,
                "sections": [{"title": "断面図", "svg": self._section_svg(p)}]}
