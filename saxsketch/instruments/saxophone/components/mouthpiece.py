"""サクソフォン マウスピース コンポーネント。

ジオメトリ構成（実在マウスピースの実測に基づく構造。詳細は profiles.py）:
  1. 外形回転体（ボア軸回りの真円。ノーズ→最大径→シャンク肩→シャンク平行部）
  2. ビークカット（18°の直線ランプ＋円筒面。x 方向に曲率を持つので断面ロフトで切る）
  3. テーブル/フェイシングカット（ボア軸に対し傾いた平面＋フェイシングカーブ）
  4. 内部空洞（窓〜バッフル〜チェンバーのロフト + ボア円筒）を減算
"""
from __future__ import annotations

import math

from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec
from saxsketch.geometry.builders import (
    extrude_arc_prism,
    loft_arc_sections,
    loft_sections,
    loft_spline_sections,
    revolve_profile,
    revolve_spline_profile,
    yz_profile_cut_solid,
    yz_profile_cut_solid_curved,
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
        f("tip_rail_thickness", "ティップレール厚", "フェイシング", "mm", 0.8, 2.5, 0.05,
          "先端に残る肉厚。薄いほど鳴りは軽いが欠けやすい。ビークの傾きもここから決まる"),
        f("tip_chamfer", "ティップ前縁の面取り", "フェイシング", "mm", 0.0, 1.2, 0.05,
          "先端をリード面側から落とす量。実物は前面が 0.25mm しか残らない。"
          "0 にすると tip_rail_thickness ぶんの角ばった壁が先端に立つ", advanced=True),
        f("side_rail_width", "サイドレール幅", "フェイシング", "mm", 0.6, 2.0, 0.1,
          "狭いほど効率よく鳴るがリードミスに敏感になる"),
        f("table_angle", "テーブル傾斜", "フェイシング", "度", 2.0, 7.0, 0.1,
          "テーブル平面のボア軸に対する傾き。実物は約4.2°で、これが胴の中でリードを"
          "どこまで深く座らせるかを決める", advanced=True),
        # --- バッフル ---
        ParamSpec(key="baffle_type", label="バッフル種別", category="バッフル",
                  type="choice", default=t["baffle_type"],
                  choices=[Choice("straight", "ストレート"),
                           Choice("step", "ステップ"),
                           Choice("curve", "カーブ"),
                           Choice("rollover", "ロールオーバー")],
                  effect="音色の性格を決める最重要要素。ストレート=暗くソフトな音／"
                         "ステップ=バランスのとれた音色（実測 WindyCity がこれ）／"
                         "カーブ=メタリックでアグレッシブな音／"
                         "ロールオーバー=ストレートの肩を丸めた中間"),
        f("baffle_height", "バッフル高さ", "バッフル", "mm", 0.0, 5.0, 0.1,
          "リード直上の天井をどれだけ下げるか。高いほど明るくエッジの効いた音、"
          "0でクラシカルなダークトーン"),
        # 以下3つは「断面」タブのハンドルで直接ドラッグできる。実効範囲は
        # バッフル種別で変わる（型の特徴を壊さないため。profiles._PLATEAU_RANGE）ので、
        # ここの min/max は全型を覆う広い値。正確な可動域は断面タブが示す。
        f("baffle_plateau", "バッフル平坦長", "バッフル", "比", 0.02, 0.75, 0.01,
          "リード直上の天井が平坦なまま続く長さ（ボア開始位置に対する比）。"
          "ステップ/ロールオーバーで有効。長いほど棚がはっきりする。"
          "ストレート/カーブでは型の定義上ごく短い範囲に制限される"),
        f("baffle_step_rise", "段の立ち上がり", "バッフル", "比", 0.0, 0.85, 0.05,
          "ステップで有効。棚の終わりで天井がどれだけ一気に立ち上がるか。"
          "0 は実測どおりのなだらかな肩、大きいほど切り立った段差になる"),
        f("baffle_curvature", "カーブ量", "バッフル", "比", -1.0, 1.0, 0.05,
          "カーブで有効。正で天井が低いまま粘って気道を絞る（明るくアグレッシブ）、"
          "負で早く開くスクープ（ダーク）、0 でストレートと同じ直線"),
        f("rollover_radius", "ロールオーバー半径", "バッフル", "mm", 3.0, 20.0, 0.5,
          "ロールオーバーで有効。肩の丸み。小さいほどエッジ感が強い", advanced=True),
        # --- チェンバー ---
        f("throat_ratio", "スロート断面積比", "チェンバー", "比", 0.60, 1.35, 0.01,
          "ボア断面積に対する最狭部の比。小=明るく抵抗感増、大=ダークで太い"),
        f("chamber_ratio", "チェンバー断面積比", "チェンバー", "比", 1.00, 3.00, 0.05,
          "スロート最狭部に対するチェンバー最大部の断面積比。大=内容積が増えダークで太い"),
        ParamSpec(key="chamber_shape", label="チェンバー形状", category="チェンバー",
                  type="choice", default=t["chamber_shape"],
                  choices=[Choice("round", "ラウンド"), Choice("square", "スクエア"),
                           Choice("horseshoe", "馬蹄"),
                           Choice("flat_sidewall", "フラットサイドウォール")],
                  effect="ラウンド=滑らかな倍音／スクエア=ヴィンテージ系の複雑な倍音／"
                         "馬蹄=太くまとまる／フラットサイドウォール=芯のある明るさ"),
        # --- ボア ---
        f("bore_dia", "ボア径", "ボア", "mm", t["bore_dia"] - 1.0, t["bore_dia"] + 1.0, 0.05,
          "ネックコルクとの適合寸法。音程の基準に直結", advanced=True),
        # レンジをテンプレート基準にするのは `bore_dia` と同じ理由に加えて、
        # **絶対値の 18〜60 が 3 サイズ共通だと単独で形状を潰せる**ため。
        # ボアの始まり = 全長 − ボア長 で、これが窓の手前へ来ると空洞が消える
        # （`profiles.cavity_layout_error`）。テナー既定 57.5 に対し上限 60 は
        # 全長 107.5 なら無害だが、全長側の下限 60 と組むと成立しない。
        f("bore_length", "ボア長", "ボア", "mm",
          round(0.5 * t["bore_length"]), round(1.25 * t["bore_length"]), 1.0,
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
        # レンジの下限はソプラノ実測（全長 71.4 / シャンク径 15.3 / シャンク長 6.4）が
        # 入るところまで下げてある。`ParamSpec.validate` は範囲外を**黙ってクランプ**
        # するので、下限が実物より上にあるとテンプレートに書いた値が別物にすり替わる。
        f("body_dia", "ボディ径", "外形", "mm", 18.0, 34.0, 0.1,
          "リガチャー適合寸法（最大径）", advanced=True),
        f("shank_dia", "シャンク径", "外形", "mm", 14.0, 28.0, 0.1,
          "ネックへ差す平行部の外径。肩の段差量を決める", advanced=True),
        f("shank_length", "シャンク長", "外形", "mm", 5.0, 30.0, 0.5,
          "シャンク平行部の長さ。長いほどロングシャンク仕様。テーブル踵の位置は"
          "全長からこれを引いて決まるので、リードの座りにも効く"),
        f("shoulder_ratio", "肩の長さ比", "外形", "比", 0.02, 0.25, 0.005,
          "最大径からシャンク径へ絞る肩の長さ（最大径位置に対する比）。"
          "最大径の位置は 全長 −（シャンク長 ＋ 肩）で決まるので、"
          "シャンク長とこの比の組が最大径の位置を決める。テナー実測 0.139", advanced=True),
        # ここも実測基準の ±25%。以前は 3 サイズ共通の 60〜130 で、**テナーを
        # 下限 60 にするだけで空洞が消えた**（既定ボア長 57.5 が全長を食い切る）。
        # サイズを跨いだ絶対レンジは「ソプラノの長さのテナー」を許してしまう。
        f("overall_length", "全長", "外形", "mm",
          round(0.75 * t["overall_length"] * 2) / 2,
          round(1.25 * t["overall_length"] * 2) / 2, 0.5,
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
        with profiles.params_scope(params):
            return self._build(params)

    def _build(self, params: dict):
        p = params

        # 1) 外形回転体。刻みの根拠は `profiles.body_stations`（FreeCAD 側の
        #    `cad/windycity/build_base.py` と同じ列を使う）。
        zs = profiles.body_stations(p)
        body = revolve_profile([(z, profiles.outer_radius(p, z)) for z in zs])

        # 2) ビークカット（上面）。稜線は直線でも横断面が円弧なので、YZ プリズムでは
        #    表現できない。各 z の「ビーク面より上」の断面をロフトして切除ソリッドにする。
        z_bk = profiles.beak_cut_stations(p)
        beak_cut = loft_sections([
            {"z": z, "pts": profiles.beak_cut_section(p, z, half_width=p["body_dia"])}
            for z in z_bk])

        # 3) テーブル/フェイシングカット（下面）。傾斜平面は踵より後ろで自然に胴の
        #    外へ出るため、全長ぶん伸ばしても余計な切除は起きない。
        facing_cut = yz_profile_cut_solid(profiles.facing_cut_points(p),
                                          half_width=p["body_dia"])

        # 4) 内部空洞（任意断面ロフト + ボア円筒）。窓/スロート/ボアの円形断面と
        #    チェンバーの非対称断面（馬蹄/フラットサイドウォール）を点数一定で通す。
        cavity = loft_sections(profiles.cavity_sections(p))
        bore = self._bore_solid(p)

        part = body - beak_cut - facing_cut - cavity - bore
        return part

    def _bore_solid(self, p: dict):
        from build123d import Pos, Solid
        zb = profiles.bore_start_z(p)
        r = profiles.bore_radius(p)
        return Pos(0, 0, zb) * Solid.make_cylinder(r, p["overall_length"] - zb + 1.5)

    def build_cad(self, params: dict):
        """STEP 出力用。`build()` と**同じ形**を、1面ずつのプリミティブで張り直す。

        `build()` の結果はテナーで 2547 面・微小エッジ 5000本超あり、FreeCAD で
        外周面を1クリックで選ぶことも外周エッジへフィレットを掛けることもできない
        （`docs/manual-edit-workflow.md` の L1 が事実上使えない）。ここでは同じ
        `profiles.py` の値から、面の張り方だけを替えて 100 面未満に畳む。

        法則は一切変えない。断面 z も多角形版と同じ列を使うので、体積・寸法とも
        多角形版と一致する（`test_mp_cad_matches_build` が担保）。残る差は多角形版
        自身の近似（母線の弦誤差・ルールドの断面間補間）で、向きは常に
        「こちらの方が法則に近い」。実測でテナーの材料体積が +0.1%。

        ブーリアンが 4 倍以上遅い（4.6s → 20s）ので、対話中に走る `build()` とは
        別経路にしてある。落ちたときは黙って `build()` へ落とす —— STEP が重くなる
        だけで、出力自体は失われない。
        """
        try:
            return self._build_cad(params)
        except Exception:                      # noqa: BLE001 - 形状生成の失敗全般
            import logging
            logging.getLogger(__name__).warning(
                "build_cad が失敗したため build() の表現で STEP を出力します",
                exc_info=True)
            return self.build(params)

    def _build_cad(self, params: dict):
        p = params
        hw = p["body_dia"]

        # 1) 外形回転体。母線は C1 の折れ目で区切る（区切らないと面取りの端で
        #    スプラインがうねる。根拠は `profiles.body_segments`）。
        part = revolve_spline_profile(profiles.body_segments(p))

        # 2) ビークカット。直線ランプの区間は「一定半径の円弧を直線に沿って
        #    平行移動した面」そのものなので、斜めプリズムで厳密に作れる。
        #    胴へ溶けるブレンド区間だけは断面の曲率半径が z で変わるのでロフト。
        cap = profiles.beak_cut_cap_y(p)
        breaks = profiles.beak_prism_breaks(p)
        for za, zb in zip(breaks, breaks[1:]):
            slope = (profiles.beak_apex_y(p, zb) - profiles.beak_apex_y(p, za)) / (zb - za)
            part = part - extrude_arc_prism(
                profiles.beak_cut_arc(p, za, half_width=hw), cap,
                direction=(0.0, slope, 1.0),
                length=(zb - za) * math.hypot(1.0, slope))
        part = part - loft_arc_sections(
            [profiles.beak_cut_arc(p, z, half_width=hw)
             for z in profiles.beak_blend_stations(p)], cap)

        # 3) テーブル/フェイシングカット。テーブル＝平面1面、フェイシング＝曲面1面。
        part = part - yz_profile_cut_solid_curved(profiles.facing_cut_segments(p),
                                                  half_width=hw)

        # 4) 内部空洞。断面は多角形版と同じで、ワイヤだけ周期スプラインにする
        #    （`ruled=True` のままなので断面間の補間＝形は変わらない）。
        #
        #    ボアはここでは別の円筒にせず、**ロフトをそのまま延長して**作る。
        #    空洞の最終断面はちょうどボア円なので、別ソリッドにすると円筒と
        #    円周まるごとで接して交わる＝OCCT が最も苦手な条件になり、実測で
        #    0.5mm² 未満のスリバー面が 35 枚出た（多角形版は 72角形が円に内接して
        #    いるので横断して交わり、この問題が起きない）。同じ断面をもう一枚
        #    後ろに置けば区間は厳密な円筒のままで、ブーリアンが1回減る。
        secs = profiles.cavity_sections(p)
        secs.append({"z": p["overall_length"] + 1.5, "pts": secs[-1]["pts"]})
        return part - loft_spline_sections(secs)

    # ------------------------------------------------------------ シミュレーション

    def params_error(self, params: dict) -> str | None:
        """空洞の並びが成立するか。全長・ボア長・ウィンドウ長の**組**で決まる。"""
        return profiles.cavity_layout_error(params)

    def simulate(self, params: dict) -> dict:
        with profiles.params_scope(params):
            return self._simulate(params)

    def _simulate(self, params: dict) -> dict:
        # `sensitivity` は各 ParamSpec を摂動した `{**params, k: v}` で回すが、
        # そちらは別 dict なので上のスコープのキャッシュには当たらない（当たったら
        # 摂動が効かず壊れる）。スコープが効くのは tier1/tier2 と本体側だけ。
        # 「容積を増やせ」という助言を出す前に、スライダ上限まで上げて本当に届くのかを
        # 数えておく。上限は ParamSpec が唯一の出所（profiles は spec を知らない）。
        cr_max = next(s.max for s in self.param_specs() if s.key == "chamber_ratio")
        # 判定は「合う挿し込み量が実用域に入るか」。コーク挿入深さは寸法ではなく
        # 演奏者が抜き差しするチューニングなので、固定した状態のセントで判定すると
        # 寸法の誤差とチューニングの自由度が混ざる（`ac_volume.tier1_report`）。
        # 既定の速い経路は共鳴を 2 回だけ解く（simulate の予算は 50ms）。
        from saxsketch.acoustics import openwind_bridge as ob
        tier1 = ac_volume.tier1_report(
            profiles.cavity_volume_cc(params), self.size_info,
            ob.tuning_position(params, self.size_info),
            headroom_cc=profiles.chamber_headroom_cc(params, cr_max))
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

    def section(self, params: dict) -> dict:
        """中央面 x=0 の断面とバッフルのドラッグハンドル。

        バッフル種別ごとに `active` なハンドルが変わる（型の形状的特徴を壊す
        操作をそもそも出さない）。可動域は `profiles._PLATEAU_RANGE` などの
        法則側の実効範囲そのままで、UI に閾値を持たせない。
        """
        return {
            "z_range": [0.0, params["overall_length"]],
            "curves": profiles.section_curves(params),
            "handles": profiles.baffle_handles(params),
            "warnings": profiles.cavity_warnings(params),
            "baffle_type": params.get("baffle_type", "step"),
            "title": "側面断面（中央面）— バッフルの丸ポチをドラッグ",
        }

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

    def survey_measure_mesh(self, mesh) -> dict:
        """外部マウスピース メッシュ（3mf/STL）から外形バルク寸法だけを実測。

        座標非依存に整列（align.axis_align）し、軸対称的に確実に測れる寸法のみ返す:
        全長 / ボディ最大外径 / シャンク内径(→bore_dia)。ティップ開き・フェイシング・
        レール幅・窓・バッフル・チェンバー等はリード面の向き特定と設計プロファイル
        prior が要り、外部モデルからは一意に測れない → 空のまま（ノギス実測へ誘導）。
        ネック系 size_info はマウスピースではなくネック部品の寸法なので測らない。
        """
        import numpy as np
        from saxsketch.analysis import align

        aligned, _, info = align.axis_align(mesh)
        av = np.asarray(aligned.vertices)
        z = av[:, 2]
        zmin, zmax = float(z.min()), float(z.max())
        L = zmax - zmin

        measured: dict[str, float] = {}
        confidence: dict[str, str] = {}
        notes: list[str] = list(info.get("warnings", []))

        # ---- 全長（軸方向 bbox）: 向き符号に非依存で最も確実
        if info["axis_conf"] != "low":
            measured["overall_length"] = round(L, 2)
            confidence["overall_length"] = info["axis_conf"]
        else:
            notes.append("主軸が不確実なため全長も参考値です。")
            measured["overall_length"] = round(L, 2)
            confidence["overall_length"] = "low"

        # ---- ボディ最大外径（中央 30–82% 帯の外周 p99。テーブル平面側は小さく出るが
        #      最大半径は丸い外周（リガチャー座付近が最大）を拾う）
        mid = (z > zmin + 0.30 * L) & (z < zmin + 0.82 * L)
        if mid.sum() >= 100:
            r = np.hypot(av[mid, 0], av[mid, 1])
            measured["body_dia"] = round(2.0 * float(np.percentile(r, 99.0)), 2)
            confidence["body_dia"] = "high" if info["axis_conf"] == "high" else "med"

        # ---- シャンク内径（開口ボア。シャンク端 = +Z 側の円筒プラトーを実測）
        if info["shank_conf"] != "low":
            res = align.shank_bore_diameter(
                aligned, av, zmax, L, info["outer_radius_mm"])
            if res is not None:
                measured["bore_dia"] = round(res[0], 2)
                confidence["bore_dia"] = res[1]
        if "bore_dia" not in measured:
            notes.append("シャンク内径を確実に測れませんでした（ノギス実測を推奨）。")

        notes.append(
            "ティップ開き・フェイシング長・レール幅・窓長・バッフル・チェンバーは"
            "外部モデルから一意に測れません。ノギス実測して手入力してください。")
        return {"measured": measured, "measured_size": {},
                "confidence": confidence, "notes": notes}

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
        import math

        from saxsketch.export.svg import polyline_svg
        pr = profiles.side_profile_polylines(params)
        deg = math.degrees(profiles.table_angle(params))
        # テーブルは傾斜平面。以前はここだけ水平の破線を引いていて、仕様書の断面図が
        # 唯一 4.18° を無視した図になっていた。
        return polyline_svg([
            {"pts": pr["outer_top"], "stroke": "#222", "width": 1.5},
            {"pts": pr["outer_bot"], "stroke": "#222", "width": 1.5},
            {"pts": pr["cavity_top"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": pr["cavity_bot"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": pr["table_plane"], "stroke": "#cc3300",
             "width": 0.8, "dash": "2 2"},
        ], f"側面断面図（実線=外形 / 青破線=内部空洞 / "
           f"赤破線=テーブル平面 傾斜{deg:.2f}°） 単位:mm")

    def spec_extras(self, params: dict) -> dict:
        from saxsketch.acoustics import openwind_bridge as ob
        p = params
        vol = profiles.cavity_volume_cc(p)
        # 仕様書は 1 回しか作らないので厳密解（零点を包んで詰める）を使う。
        # UI 側は速い線形推定（`ob.tuning_position` の既定）。
        tune = ob.tuning_position(p, self.size_info, exact=True)
        dims = [
            ("全長", f"{p['overall_length']:.1f} mm"),
            ("ティップ開き", f"{p['tip_opening']:.2f} mm"),
            ("フェイシング長", f"{p['facing_length']:.1f} mm"),
            ("ボア径", f"φ{p['bore_dia']:.2f} mm"),
            ("ボディ径（リガチャー座）", f"φ{p['body_dia']:.1f} mm"),
            # 実効値で出す。`window_length` は「ボアの始まり −4.0mm」で頭打ちに
            # なることがあり、その帯では指定値が形に出ない。仕様書は納品物なので、
            # 部品が持っていない寸法を書いてはいけない（`window_length_effective`）。
            ("ウィンドウ長 × 窓幅",
             f"{profiles.window_length_effective(p):.1f} × "
             f"{profiles.window_width(p):.1f} mm"
             + (f"（指定 {p['window_length']:.1f}mm はボアの始まりに阻まれて "
                f"{profiles.window_length_shortfall(p):.1f}mm 届いていません）"
                if profiles.window_length_shortfall(p) > 0.05 else "")),
            ("内容積（全体/実効）", f"{vol['total_cc']:.1f} / {vol['effective_cc']:.1f} cc"),
            # コーク挿入深さは寸法ではなくチューニング量。設計値として意味があるのは
            # 「目標音で鳴らせる挿し込み量が実際に届く範囲にあるか」の方。
            # **基準条件での値**であって実演奏の位置の予測ではない（volume.py の
            # モジュール docstring）。仕様書は単独で読まれるので条件をラベルに書く。
            (f"目標音が出る挿し込み量（{ob.TEMPERATURE_C:.0f}°C 基準）",
             f"{tune['in_tune_mm']:.1f} mm"
             f"（実用域 {tune['range_mm'][0]:.0f}〜{tune['range_mm'][1]:.0f} mm、"
             f"1mm 押し込むと {tune['cents_per_mm']:+.2f} セント）"),
        ]
        # 各部名称（参照サイト準拠）を寸法表に畳み込む。コア（spec.py）は dimensions と
        # sections しか知らないので、部品側で行として組み立てる（「コアは楽器を知らない」）。
        dims.append(("― 各部名称（z範囲）―", ""))
        dims += [(a["part"], f"z {a['z0']:.1f}–{a['z1']:.1f} mm")
                 for a in profiles.anatomy_regions(p)]
        return {"dimensions": dims,
                "sections": [{"title": "断面図", "svg": self._section_svg(p)}]}
