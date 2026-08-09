"""サクソフォン ネック コンポーネント（Phase 4-B.1）。

円錐ネック（ストレート／グースネック曲げ）＋オクターブベント孔を生成する。
マウスピース適合は descriptor のネック定数（テノン外径＋コルク厚）から
`reference_check.required_bore_dia` で検証する（ライブ参照不要 → `REQUIRES_REF=None`）。

正直な範囲: オクターブ**キー機構は非実装**（ベント孔幾何のみ・奏者が塞ぐ/プラグ前提）。
ボアテーパは直線円錐近似で音程は近似（採寸校正で実物へ寄せる）。曲げロフトが破綻する
設定ではストレート（bend_angle=0）へ。
"""
from __future__ import annotations

from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec

from . import neck_profiles as npf
from . import reference_check


def _specs(t: dict) -> list[ParamSpec]:
    """テンプレート値 t を初期値としてスキーマを構築。"""
    def f(key, label, cat, unit, lo, hi, step, effect, adv=False):
        return ParamSpec(key=key, label=label, category=cat, type="float", unit=unit,
                         default=t[key], min=lo, max=hi, step=step, effect=effect,
                         advanced=adv)

    def onoff(key, label, cat, effect, adv=False):
        return ParamSpec(key=key, label=label, category=cat, type="choice",
                         default=t[key],
                         choices=[Choice("on", "有効"), Choice("off", "無効")],
                         effect=effect, advanced=adv)

    return [
        # --- 寸法 ---
        f("neck_length", "ネック全長（弧長）", "寸法", "mm", 120.0, 340.0, 1.0,
          "マウスピース側からボディ側までの管中心長。楽器全体の音程に効く"),
        f("bore_small_id", "小端ボア内径", "寸法", "mm", 8.0, 22.0, 0.1,
          "マウスピース側の最細内径。楽器全体で最も細いスロート"),
        f("wall_thickness", "肉厚", "寸法", "mm", 1.2, 4.0, 0.1,
          "管壁厚。気密と強度に直結。レジンで2mm前後推奨"),
        f("tenon_od", "テノン外径", "寸法", "mm", 9.0, 22.0, 0.1,
          "マウスピースが被さる部の外径。コルクを巻く土台"),
        f("tenon_length", "テノン長", "寸法", "mm", 15.0, 45.0, 0.5,
          "コルク座の長さ＝マウスピース挿入代"),
        f("cork_thickness", "コルク厚（片側）", "寸法", "mm", 0.4, 1.6, 0.1,
          "テノンに巻くコルクの片側厚。必要ボア径の算出に使う"),
        f("body_tenon_length", "本体挿入部長", "寸法", "mm", 12.0, 45.0, 0.5,
          "ボディ受けへ差し込む段付き部の長さ", adv=True),
        # --- テーパ ---
        onoff("taper_from_cone", "円錐角からテーパ導出", "テーパ",
              "有効=descriptor の半頂角から大端径を自動算出／無効=大端径を直接指定"),
        f("bore_large_id", "大端ボア内径", "テーパ", "mm", 12.0, 40.0, 0.1,
          "ボディ側の内径。テーパ導出が無効のとき使用", adv=True),
        # --- ベンド ---
        f("bend_angle", "曲げ角", "ベンド", "°", 0.0, 40.0, 1.0,
          "0でストレート。グースネックの傾き。姿勢・見た目を実物へ寄せる"),
        f("bend_start", "曲げ開始位置", "ベンド", "mm", 20.0, 200.0, 1.0,
          "テノン端から曲げ始めるまでの直線長"),
        # --- オクターブベント ---
        onoff("octave_vent", "オクターブベント", "オクターブベント",
              "レジスタ孔を開ける。キー機構は別部品（奏者が塞ぐ/プラグ前提）"),
        f("vent_position", "ベント位置（弧長比）", "オクターブベント", "比", 0.05, 0.95, 0.01,
          "全長に対するベント中心の位置"),
        f("vent_dia", "ベント径", "オクターブベント", "mm", 1.5, 7.0, 0.1,
          "レジスタ孔の径"),
        f("chimney_height", "チムニー高さ", "オクターブベント", "mm", 0.0, 5.0, 0.1,
          "ベント周りの立ち上がり（ピップ／パッド座）。0で無し"),
        onoff("seat_flat", "パッド座を平坦化", "オクターブベント",
              "チムニー上端を平坦なパッド当たり面にする（後段キー対応）", adv=True),
        onoff("key_mount_bosses", "キー取付ボス", "オクターブベント",
              "ベント両脇にポスト座を生成（後段キー機構用。既定無効）", adv=True),
        # --- 製造 ---
        f("min_wall", "最小肉厚（検査）", "製造", "mm", 1.0, 4.0, 0.1,
          "印刷強度の下限。肉厚がこれ未満で警告", adv=True),
        ParamSpec(key="material", label="材料プリセット", category="製造",
                  type="choice", default=t["material"],
                  choices=[Choice("resin", "レジン(光造形)"),
                           Choice("pla", "PLA(FDM)"),
                           Choice("petg", "PETG(FDM)"),
                           Choice("nylon_sls", "ナイロンPA12(SLS)")],
                  effect="気密性と強度。管体は層間気密が要るためレジン推奨"),
    ]


_MAT_LABELS = {"resin": "レジン(光造形)", "pla": "PLA", "petg": "PETG",
               "nylon_sls": "ナイロンPA12(SLS)"}
#: 材料密度 [g/cc]（質量概算用）。
_MAT_DENSITY = {"resin": 1.15, "pla": 1.24, "petg": 1.27, "nylon_sls": 1.01}
#: 実用ベッド長の目安 [mm]（超過で自動分割の案内を出す。4-B.3）。
_BED_HINT_MM = 250.0


class NeckComponent(Component):
    id = "neck"
    label = "ネック"
    REQUIRES_REF = None   # マウスピース適合は descriptor 定数で検証でき、ライブ参照は不要

    def __init__(self, descriptor: dict, template: dict):
        super().__init__(descriptor, template)
        self.size = template["size"]
        self.size_info = descriptor["sizes"][self.size]

    def param_specs(self) -> list[ParamSpec]:
        return _specs(self.template["neck"])

    # ------------------------------------------------------------ 形状生成

    def build(self, params: dict):
        from saxsketch.geometry.builders import loft_3d_rings, revolve_profile

        p = params
        si = self.size_info
        if p["bend_angle"] <= 0.0:
            outer = revolve_profile(npf.outer_stations(p, si))
            bore = revolve_profile(npf.bore_stations(p, si))
        else:
            outer = loft_3d_rings(npf.outer_rings(p, si))
            bore = loft_3d_rings(npf.bore_rings(p, si))
        part = outer - bore

        vp = npf.octave_vent_placement(p, si)
        if vp is not None:
            part = self._apply_vent(part, vp)
        return part

    def _apply_vent(self, part, vp: dict):
        from build123d import Plane, Solid, Vector

        c = Vector(*vp["center"])
        ax = Vector(*vp["axis"])
        r = vp["dia"] / 2.0
        outer_r = vp["outer_r"]

        # チムニー（ピップ／パッド座）を外面に融合してから孔を貫通させる
        if vp["chimney_height"] > 0.0:
            rim = r + (1.6 if vp["seat_flat"] else 0.9)
            base = c + ax * outer_r
            part = part + Solid.make_cylinder(
                rim, vp["chimney_height"], Plane(origin=base, z_dir=ax))
        # キー取付ボス（後段機構用の座）
        for b in vp["bosses"]:
            bc = Vector(*b["center"]) + Vector(*b["axis"]) * outer_r
            part = part + Solid.make_cylinder(
                2.2, 3.0, Plane(origin=bc, z_dir=Vector(*b["axis"])))
        # 貫通孔: 中心線から外側へ。反対側の壁には届かない長さに留め、単一孔にする
        through = outer_r + vp["chimney_height"] + 2.0
        part = part - Solid.make_cylinder(r, through, Plane(origin=c, z_dir=ax))
        return part

    # ------------------------------------------------------------ シミュレーション

    def simulate(self, params: dict) -> dict:
        cards = [self._fit_card(params), self._taper_card(params),
                 self._print_card(params)]
        vent = self._vent_card(params)
        if vent is not None:
            cards.insert(2, vent)
        return {"kind": "neck", "cards": cards}

    def _fit_card(self, params: dict) -> dict:
        """マウスピース適合（自動整合の可視化）。テノン外径＋コルクが合うボア径を決める。"""
        p = params
        fit = reference_check.INTERFERENCE_FIT_MM
        need = p["tenon_od"] + 2.0 * p["cork_thickness"]
        rows = [
            ["テノン外径", f"{p['tenon_od']:.1f} mm"],
            ["コルク厚（片側）", f"{p['cork_thickness']:.2f} mm"],
            ["コルク込み外径（自由状態）", f"{need:.2f} mm"],
            ["合うマウスピースのボア径", f"{need - fit:.2f} mm（締め代 {fit:.1f}mm）"],
            ["規格テノン外径（descriptor）", f"{self.size_info['neck_tenon_od_mm']:.1f} mm"],
        ]
        # ボアは非対称: 小さいと物理的に挿さらない、大きい分はコルクで吸収できる。
        dv = p["tenon_od"] - self.size_info["neck_tenon_od_mm"]
        if abs(dv) <= 0.4:
            status, big = "ok", "規格テノン径に整合"
            advice = ("マウスピース側のボアが {0:.1f}mm 前後なら勘合します"
                      "（自由状態のコルク込み {1:.1f}mm を {2:.1f}mm 潰して食いつかせる）。"
                      "規格テノン径に一致しているので市販マウスピースが使えます。"
                      ).format(need - fit, need, fit)
        elif dv > 0:
            status, big = "warn", "テノンが規格より太い"
            advice = (f"規格より {dv:.1f}mm 太く、市販マウスピースが入らない恐れがあります。"
                      f"テノン外径を {self.size_info['neck_tenon_od_mm']:.1f}mm に近づけてください。")
        else:
            status, big = "warn", "テノンが規格より細い"
            advice = (f"規格より {abs(dv):.1f}mm 細く、コルクを厚めに巻かないとガタつきます。"
                      f"コルク厚での調整、またはテノン外径を上げてください。")
        return {"title": "マウスピース適合", "big": big, "status": status,
                "rows": rows, "advice": advice}

    def _taper_card(self, params: dict) -> dict:
        p = params
        large = npf.bore_large_id(p, self.size_info)
        rows = [
            ["小端ボア内径", f"{p['bore_small_id']:.1f} mm"],
            ["大端ボア内径", f"{large:.1f} mm"],
            ["円錐半頂角（descriptor）", f"{self.size_info['cone_half_angle_deg']:.2f} °"],
            ["曲げ角", f"{p['bend_angle']:.0f} °（{'ストレート' if p['bend_angle'] <= 0 else 'グースネック'}）"],
        ]
        note = ("ネックは楽器全体で最も細いスロートで、ボア径は音程の基準になります。"
                "テーパは直線円錐近似のため音程は近似です。手元の実物ネックを採寸校正すると"
                "実用域に寄ります。")
        if p["taper_from_cone"] != "on":
            note = "大端径を直接指定中（円錐角から導出していません）。" + note
        return {"title": "ボア・テーパー／ベンド", "big": None, "status": "ok",
                "rows": rows, "advice": note}

    def _vent_card(self, params: dict) -> dict | None:
        p = params
        if p["octave_vent"] != "on":
            return None
        rows = [
            ["ベント位置（弧長比）", f"{p['vent_position']:.2f}"],
            ["ベント径", f"{p['vent_dia']:.1f} mm"],
            ["チムニー高さ", f"{p['chimney_height']:.1f} mm"],
            ["パッド座平坦化", "有効" if p["seat_flat"] == "on" else "無効"],
            ["キー取付ボス", "有効" if p["key_mount_bosses"] == "on" else "無効"],
        ]
        return {"title": "オクターブベント（注意）", "big": "キー機構は非実装", "status": "warn",
                "rows": rows,
                "advice": ("ベント孔の幾何のみです。キー／パッド機構はありません。孔が常時開だと"
                           "低音域が漏れて鳴りません。奏者が指で塞ぐ、またはプラグで塞ぐ運用が前提です。"
                           "正確な第2レジスタ運用にはパッド付きキー（後段フェーズ）が必要です。"
                           "『キー取付ボス』を有効にすると後段のキー機構をネック再設計なしで載せられます。")}

    def _print_card(self, params: dict) -> dict:
        p = params
        vol_cc = npf.neck_volume_mm3(p, self.size_info) / 1000.0
        dens = _MAT_DENSITY.get(p["material"], 1.15)
        rows = [
            ["肉厚", f"{p['wall_thickness']:.1f} mm"],
            ["最小肉厚（下限）", f"{p['min_wall']:.1f} mm"],
            ["材料体積", f"{vol_cc:.1f} cc"],
            ["概算質量", f"{vol_cc * dens:.0f} g"],
            ["全長（弧長）", f"{p['neck_length']:.0f} mm"],
        ]
        if p["wall_thickness"] < p["min_wall"]:
            return {"title": "印刷・肉厚・気密", "big": "肉厚不足", "status": "bad", "rows": rows,
                    "advice": (f"肉厚が下限 {p['min_wall']:.1f}mm を下回ります。管壁が薄いと気密と強度が"
                               "出ません。肉厚を上げてください。")}
        advice = ("管体は層間の気密が要ります。FDM では層間ポロシティで漏れやすいので、"
                  "レジン（光造形）か、印刷後のシーリングを推奨します。")
        if p["neck_length"] > _BED_HINT_MM:
            advice += (f" 全長が実用ベッド目安 {_BED_HINT_MM:.0f}mm を超えています。"
                       "造形サイズ自動分割（後段 4-B.3）で対応予定です。")
        return {"title": "印刷・肉厚・気密", "big": "造形可", "status": "ok",
                "rows": rows, "advice": advice}

    # ------------------------------------------------------------ 採寸ワークフロー（Phase 4-A 再利用）

    _SURVEY_PARAM_KEYS = ["neck_length", "bore_small_id", "bore_large_id", "tenon_od"]

    def survey_targets(self) -> dict:
        specs = {s.key: s for s in self.param_specs()}
        params = [
            {"key": k, "label": specs[k].label, "unit": specs[k].unit,
             "min": specs[k].min, "max": specs[k].max, "step": specs[k].step}
            for k in self._SURVEY_PARAM_KEYS if k in specs
        ]
        return {"params": params, "size": []}

    def survey_card(self, before_params: dict, before_size: dict,
                    measured_params: dict, measured_size: dict) -> dict | None:
        specs = {s.key: s for s in self.param_specs()}
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
        if not rows:
            return None
        return reference_check._finish(
            "採寸 vs 設計", rows, verdicts,
            "実測をプロジェクトへ反映しました。破綻したら「採寸時点へ戻す」で復元できます。")

    def survey_measure_mesh(self, mesh) -> dict:
        """外部ネック メッシュ（3mf/STL）から外形バルク寸法だけを実測。

        座標非依存に整列（align.axis_align）し、確実に測れる寸法のみ返す:
        全長 / 小端・大端ボア内径 / テノン外径。曲げネックでは主軸=弦長なので全長は近似。
        """
        import numpy as np
        from saxsketch.analysis import align

        aligned, _T, info = align.axis_align(mesh)
        av = np.asarray(aligned.vertices)
        z = av[:, 2]
        zmin, zmax = float(z.min()), float(z.max())
        L = zmax - zmin

        measured: dict[str, float] = {}
        confidence: dict[str, str] = {}
        notes: list[str] = list(info.get("warnings", []))

        # ---- 全長（軸方向 bbox）。曲げネックは主軸＝弦長なので近似
        measured["neck_length"] = round(L, 2)
        confidence["neck_length"] = info["axis_conf"]
        if info["axis_conf"] == "low":
            notes.append("主軸が不確実なため全長も参考値です。")
        notes.append("曲げネックでは主軸長＝弦長のため、全長（弧長）は実際よりやや短めに出ます。")

        # ---- 両端の断面リング内径（小端＝-Z 側 / 大端＝シャンク +Z 側）
        outer_r = info["outer_radius_mm"]
        big = align.shank_bore_diameter(aligned, av, zmax, L, outer_r)
        if big is not None:
            measured["bore_large_id"] = round(big[0], 2)
            confidence["bore_large_id"] = big[1]
        # 小端は -Z 端。座標を反転して同じ推定器を使う
        flip = aligned.copy()
        flip.apply_transform(np.diag([1.0, -1.0, -1.0, 1.0]))
        fav = np.asarray(flip.vertices)
        small = align.shank_bore_diameter(flip, fav, float(fav[:, 2].max()), L, outer_r)
        if small is not None:
            measured["bore_small_id"] = round(small[0], 2)
            confidence["bore_small_id"] = small[1]

        # ---- テノン外径（小端付近の最大外径）
        near = z < zmin + min(0.18 * L, 40.0)
        if near.sum() >= 50:
            rr = np.hypot(av[near, 0], av[near, 1])
            measured["tenon_od"] = round(2.0 * float(np.percentile(rr, 96.0)), 2)
            confidence["tenon_od"] = "med"

        if "bore_small_id" not in measured and "bore_large_id" not in measured:
            notes.append("ボア内径を確実に測れませんでした（ノギス実測を推奨）。")
        return {"measured": measured, "measured_size": {},
                "confidence": confidence, "notes": notes}

    # ------------------------------------------------------------ 領域 / BOM / 仕様書

    def regions(self, params: dict) -> dict:
        return npf.param_regions(params)

    def bom(self, params: dict) -> list[dict]:
        p = params
        size_label = {"soprano": "ソプラノ", "alto": "アルト", "tenor": "テナー"}[self.size]
        vol_cc = npf.neck_volume_mm3(p, self.size_info) / 1000.0
        rows = [
            {"type": "3Dプリント", "name": f"ネック本体（{size_label}）", "qty": 1,
             "material": _MAT_LABELS.get(p["material"], p["material"]),
             "note": f"材料体積 約{vol_cc:.1f}cc。気密のためレジン/シーリング推奨"},
            {"type": "市販品", "name": "テノン コルクストリップ", "qty": 1,
             "material": "コルク", "note": f"厚 {p['cork_thickness']:.1f}mm（マウスピース勘合）"},
        ]
        if p["octave_vent"] == "on":
            rows.append({"type": "市販品", "name": "オクターブベント プラグ／パッチ", "qty": 1,
                         "material": "-", "note": "常時開防止（キー化までの暫定。奏者が塞ぐ）"})
        return rows

    def _section_svg(self, params: dict) -> str:
        from saxsketch.export.svg import polyline_svg
        pr = npf.side_profile_polylines(params, self.size_info)
        return polyline_svg([
            {"pts": pr["outer_top"], "stroke": "#222", "width": 1.5},
            {"pts": pr["outer_bot"], "stroke": "#222", "width": 1.5},
            {"pts": pr["bore_top"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": pr["bore_bot"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
        ], "側面断面図（実線=外形 / 青破線=ボア） 単位:mm")

    def spec_extras(self, params: dict) -> dict:
        p = params
        large = npf.bore_large_id(p, self.size_info)
        vol_cc = npf.neck_volume_mm3(p, self.size_info) / 1000.0
        dims = [
            ("全長（弧長）", f"{p['neck_length']:.0f} mm"),
            ("小端 → 大端ボア", f"φ{p['bore_small_id']:.1f} → φ{large:.1f} mm"),
            ("テノン外径 × 長さ", f"φ{p['tenon_od']:.1f} × {p['tenon_length']:.0f} mm"),
            ("曲げ角", f"{p['bend_angle']:.0f} °"),
            ("肉厚", f"{p['wall_thickness']:.1f} mm"),
            ("材料体積", f"{vol_cc:.1f} cc"),
        ]
        if p["octave_vent"] == "on":
            dims.append(("オクターブベント", f"φ{p['vent_dia']:.1f} mm @ 弧長比 {p['vent_position']:.2f}"))
        return {"dimensions": dims,
                "sections": [{"title": "断面図", "svg": self._section_svg(p)}]}
