"""サクソフォン 管体コンポーネント（Phase 4-B.2a）。

円錐管＋ボウ（曲げ）＋ベルを生成する。ネックの繋ぎ方を 2 通り持つ:

  - `separate`（既定）… ネックは別部品。本体は受け口（ソケット）を持つ。
  - `integrated` … **ネックが本体と 1 部品**（テノン継手が無い）。ストレート
    ソプラノに多い作り。ネック区間の幾何は `neck_profiles` へ委譲する。

**一体型でも音響は変わらない。** 現行の共鳴管（`openwind_bridge.build_resonator`）は
マウスピース → 円筒ボア → 欠損円錐で、そもそも「ネック」という区間を持っていない。
継ぎ目もテノンもモデルに入っていないので、一体化しても音程・インピーダンスは動かない
（`acoustic_geometry` が両モードで一致することをテストで固定してある）。
「一体型のほうが音が良い/悪い」とは**言えない** —— モデルは差を持たない。
実利は継手が 1 つ減ること（漏れ経路とボアの段差）と、テーパの突き合わせが消えること。
代償は姿勢を調整できないこと（実機のネックは回して銜え角を合わせる）と、壊れたときに
全部作り直しになること。

**正直な範囲（4-B.2b）**:
  - **側孔は付いたが、位置は解いていない。** 0 次規則（開孔位置＝その音が鳴る
    円錐長）で置いた暫定値で、実測でも最適解でもない。実際に解いた共鳴が各音で
    何セント外れるかは音階カードが出す —— それが 4-B.2c のソルバが潰す残差。
  - 運指表は「全閉 → ベル寄りから順に開ける」だけ。フォーク運指は無い。
  - 親指孔は**胴側のオクターブベントの幾何だけ**で、キー機構は無い（4-B.4）。
  - **ベルのフレアは 3 サイズとも未実測**。形も出口径も仮定で、実物照合は無い。
    だから**音響へ接続していない** —— 接続すると全閉の第1共鳴が +38〜+106 セント
    動く（K.0 の測定）。共鳴管は今までどおり校正済みの直線円錐のまま。
  - 曲げが音程に与える影響はモデルに入っていない（弧長近似）。
  - キー機構は無い（4-B.4）。分割は無い（4-B.3）——3 サイズとも 1 パーツでは
    印刷できない長さ。
"""
from __future__ import annotations

from saxsketch.acoustics import toneholes
from saxsketch.core.registry import Component
from saxsketch.core.schema import Choice, ParamSpec

from . import body_profiles as bpf
from . import neck_profiles as npf
from . import reference_check
from .neck import BED_HINT_MM, MAT_DENSITY, MAT_LABELS


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
        f("body_arc_length", "本体管長（弧長）", "寸法", "mm", 200.0, 1600.0, 1.0,
          "ネックの大端からベル出口までの管中心長。円錐の長さ＝音程の骨格"),
        f("wall_thickness", "肉厚", "寸法", "mm", 1.2, 4.0, 0.1,
          "管壁厚。気密と強度に直結。レジンで2mm前後推奨"),
        # --- 接続 ---
        ParamSpec(key="neck_joint", label="ネックの繋ぎ方", category="接続",
                  type="choice", default=t["neck_joint"],
                  choices=[Choice("separate", "別体（テノンで挿す）"),
                           Choice("integrated", "一体（ネックまで1部品）")],
                  effect=("一体はストレートソプラノに多い作り。継手が減るが姿勢を"
                          "調整できない。音響はどちらでも同じ")),
        f("socket_length", "ネック受け深さ", "接続", "mm", 8.0, 50.0, 0.5,
          "別体のとき、ネックのスピゴットを受ける穴の深さ", adv=True),
        f("socket_clearance", "はめあい隙間", "接続", "mm", 0.05, 0.60, 0.01,
          "別体のとき、受け穴とスピゴットの片側隙間", adv=True),
        # --- テーパ ---
        onoff("taper_from_cone", "円錐からテーパ導出", "テーパ",
              "有効=descriptor の欠損円錐と同じ傾きを使う／無効=両端の径を直接指定"),
        f("bore_small_id", "小端ボア内径", "テーパ", "mm", 8.0, 30.0, 0.1,
          "円錐スロート（マウスピース側の管端）の内径。テーパ導出が無効のとき使用",
          adv=True),
        f("bore_large_id", "大端ボア内径", "テーパ", "mm", 20.0, 140.0, 0.5,
          "ベルのフレアを含まない終端の内径。テーパ導出が無効のとき使用", adv=True),
        # --- ボウ（曲げ） ---
        f("bow_angle", "ボウ曲げ角", "ボウ", "°", 0.0, 180.0, 1.0,
          "0でストレート（ストレートソプラノ／ストレートアルト）。180でU字に折り返す"),
        f("bow_start", "ボウ開始位置", "ボウ", "mm", 20.0, 1400.0, 1.0,
          "本体管の始端から曲げ始めるまでの直線長"),
        f("bow_radius", "ボウ曲率半径", "ボウ", "mm", 15.0, 150.0, 1.0,
          "折り返しの半径。**管の外半径より大きくないと断面が内側で折り返す**"
          "（下限はサイズと肉厚で変わるのでスライダの最小値では表せない。"
          "成立しない値は理由付きで弾く）"),
        # --- ベル ---
        f("bell_length", "ベル長（弧長）", "ベル", "mm", 0.0, 320.0, 1.0,
          "円錐から広がり始める区間の長さ。0でフレア無し（円錐のまま）"),
        f("bell_exit_dia", "ベル出口内径", "ベル", "mm", 30.0, 220.0, 1.0,
          "開口の内径。円錐終端より細くはできない（実物のベルは細らない）"),
        f("flare_power", "フレアの鋭さ", "ベル", "-", 1.0, 6.0, 0.1,
          "大きいほど終端近くで急に開く。1で直線的に広がる"),
        # --- 側孔 ---
        ParamSpec(key="finger_holes", label="指孔の本数", category="側孔",
                  type="int", unit="本", default=t["finger_holes"],
                  min=0, max=len(toneholes.SCALE_STEPS), step=1,
                  effect=("全閉から順に開けて音階を作る（リコーダと同じ並び）。"
                          "0 で穴なし＝管だけ。上限は音階の段数で決まる")),
        f("hole_dia", "指孔径", "側孔", "mm", 4.0, 14.0, 0.1,
          "太いほど開けたときの音が高く（＝完全な開口端に近く）なる。"
          f"指でふさげる実用上限は φ{bpf.FINGER_PAD_DIA_MM:.0f} 前後"),
        f("hole_chimney", "チムニー高さ", "側孔", "mm", 0.0, 8.0, 0.1,
          "外面からの立ち上がり。高いほど開孔音が下がる。**位置を動かせない"
          "キーレスで音程を合わせる主なつまみ**（4-B.2c）"),
        onoff("thumb_vent", "親指孔", "側孔",
              "胴側のオクターブベント（左親指）。実機は 1 つのキーでネック側と"
              "切り替える。音階の段ではないので運指表では常に閉じたまま扱う"),
        f("thumb_offset", "親指孔オフセット", "側孔", "mm", 0.0, 60.0, 0.5,
          "オクターブ（+12半音）の位置から上流へ。指孔の本数には依らない", adv=True),
        f("thumb_dia", "親指孔径", "側孔", "mm", 2.0, 8.0, 0.1,
          "レジスタ用なので指孔より細い", adv=True),
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


#: 円錐リーチ（スロート→ベル出口の弧長）が目標からこれ以上ずれたら警告 [mm]。
#: 20mm はアルトで約 31 セントに当たる。半音（100 セント）の 1/3。
CONE_REACH_TOL_MM = 20.0

#: チムニーの縁の肉 [mm]（穴の縁から外周まで）。ネックのベント（`neck.py`）が
#: パッド座ありで 1.6 / なしで 0.9 を使っているのに合わせ、キーレスの指孔は
#: パッドが載らないので 0.9 側を採る。
CHIMNEY_RIM_MM = 0.9

#: 音階のずれがこれ以内なら ok 扱い [セント]。**調律の保証ではない** ——
#: 4-B.2b の穴位置は 0 次規則の暫定値なので、ここに出るのは
#: 「4-B.2c のソルバが潰す残差」。
SCALE_TOL_CENTS = 10.0


class BodyComponent(Component):
    id = "body"
    label = "本体・管体"
    #: ネックの寸法は本体の円錐の位置を決める（別体では上流の長さ、一体型では
    #: 本体が作る区間そのもの）。同じ量を body 側に再掲すると必ず食い違うので、
    #: リード/リガチャー → マウスピース と同じ参照スナップショットで受ける。
    REQUIRES_REF = "neck"

    def __init__(self, descriptor: dict, template: dict):
        super().__init__(descriptor, template)
        self.size = template["size"]
        self.size_info = descriptor["sizes"][self.size]

    def param_specs(self) -> list[ParamSpec]:
        return _specs(self.template["body"])

    # ------------------------------------------------------------ 参照ネック

    def _neck(self) -> dict:
        """参照ネックのパラメータ。未設定ならテンプレートのネック既定へ落ちる。"""
        return self.ref_params() or dict(self.template["neck"])

    def ref_dimensions(self) -> list[tuple[str, str]]:
        n = self._neck()
        return [
            ("ネック全長（弧長）", f"{n['neck_length']:.0f} mm"),
            ("小端ボア内径", f"φ{n['bore_small_id']:.1f} mm"),
            ("本体挿入部長", f"{n['body_tenon_length']:.0f} mm"),
            ("曲げ角", f"{n['bend_angle']:.0f} °"),
        ]

    # ------------------------------------------------------------ 形状生成

    def params_error(self, params: dict) -> str | None:
        """管の並びが成立するか。ボウ・ベル・受け口の**組**で決まる。"""
        return bpf.layout_error(params, self.size_info, self._neck())

    def _is_straight(self, p: dict, n: dict) -> bool:
        if p["bow_angle"] > 0.0:
            return False
        return not bpf.is_integrated(p) or n["bend_angle"] <= 0.0

    def build(self, params: dict):
        from saxsketch.geometry.builders import loft_3d_rings, revolve_profile

        p, si, n = params, self.size_info, self._neck()
        if self._is_straight(p, n):
            # 完全なストレート（ストレートソプラノ等）。回転体のほうが軽い。
            s0 = bpf.part_start(p, n)
            outer = revolve_profile([(s - s0, bpf.outer_radius_at(s, p, si, n))
                                     for s in bpf.stations(p, si, n)])
            bore = revolve_profile([(s - s0, bpf.wall_inner_radius_at(s, p, si, n))
                                    for s in bpf.stations(p, si, n)])
        else:
            outer = loft_3d_rings(bpf.outer_rings(p, si, n))
            bore = loft_3d_rings(bpf.bore_rings(p, si, n))
        return self._apply_holes(outer - bore, p)

    def _apply_holes(self, part, params: dict):
        """側孔を開ける。**融合も差分も 1 回ずつしかやらない。**

        曲げのある管のブーリアンは 1 回 7〜17 秒かかり、7〜8 回積むと WSL2 の
        VM ごと落ちる（`cad/body/README.md`）。穴ごとに `part - cyl` を回すと
        本数だけブーリアンが増えるので、チムニーは全部まとめて 1 回の和、
        貫通穴は全部まとめて 1 回の差にする（build123d の `+` / `-` は
        Shape の列を受ける）。
        """
        from build123d import Plane, Solid, Vector

        pls = bpf.hole_placement(params, self.size_info, self._neck())
        if not pls:
            return part
        chimneys, cuts = [], []
        for hp in pls:
            c = Vector(*hp["center"])
            ax = Vector(*hp["axis"])
            r = hp["dia"] / 2.0
            if hp["chimney_height"] > 0.0:
                # **ボア内面から立ち上げる。** 外面に接する平面から立てると、
                # 管が曲面なので底の円盤が接点以外どこも管の外に浮き、融合が
                # 接触だけになって**ちぎれる**（掃引でボウの上の 2 本が実際に
                # 外れ、ソリッドが 3 個になった）。内面から立てれば必ず肉の中で
                # 重なる。ボアへはみ出す心配は無い —— 軸から外れるほど中心線
                # からの距離は伸びるので、`x ≥ inner_r` の円柱は気柱に入らない。
                base = c + ax * hp["chimney_base_r"]
                chimneys.append(Solid.make_cylinder(
                    r + CHIMNEY_RIM_MM, hp["chimney_len"],
                    Plane(origin=base, z_dir=ax)))
            # 中心線から外側へ。反対側の壁には届かない長さに留め、単一孔にする
            cuts.append(Solid.make_cylinder(
                r, hp["cut_len"], Plane(origin=c, z_dir=ax)))
        if chimneys:
            part = part + chimneys
        return part - cuts

    # ------------------------------------------------------------ シミュレーション

    def simulate(self, params: dict) -> dict:
        cards = [self._joint_card(params), self._cone_card(params)]
        if bpf.is_holed(params):
            cards.append(self._scale_card(params))
            cards.append(self._reach_card(params))
        cards.append(self._print_card(params))
        # 側孔が付いて初めて「管体のインピーダンス」に意味が出る（穴が無ければ
        # マウスピース側で見ているのと同じ直線円錐）。UI に部品名を書かないため、
        # 曲線を出せるかどうかはここが宣言する。
        return {"kind": "body", "cards": cards,
                "has_impedance": bpf.is_holed(params)}

    # ------------------------------------------------------------ 側孔（4-B.2b）

    def _ideal_geometry(self) -> list[list[float]]:
        """側孔を載せる物差し（**理想マウスピースの円錐**）。

        管体は `REQUIRES_REF = "neck"` の 1 段しか参照を持たず、マウスピースの
        パラメータを知らない。だから「このマウスピースが完璧だったら」の円錐
        （`ideal_cone_geometry`、Tier1 が既に使っている物差し）の上で穴を評価する。
        全閉の第1共鳴は校正により目標音そのものになるので、音階カードに残るのは
        **穴だけの寄与**になる —— マウスピース由来のずれは混ざらない。

        **ベルは載せない。** 4-B.2a の判断のまま（フレアは 3 サイズとも未実測で、
        接続すると全閉の第1共鳴が +38〜+106 セント動く）。
        """
        from saxsketch.acoustics import openwind_bridge as ob
        return ob.ideal_cone_geometry(self.size_info, use_openwind=False)

    def _solver(self, params: dict):
        from saxsketch.acoustics import openwind_bridge as ob
        holes = bpf.acoustic_holes(params, self.size_info, self._neck())
        return ob.HoleSolver(self._ideal_geometry(), holes,
                             float(self.size_info["low_note_sounding_hz"]),
                             toneholes.scale_steps(int(params["finger_holes"]))), holes

    @staticmethod
    def _shifted(holes: list[dict], d_dia_mm: float = 0.0,
                 d_chimney_mm: float = 0.0) -> list[dict]:
        """穴の**位置はそのまま**に径／チムニーだけ振った変種（感度用）。

        位置が同じなので `HoleSolver` の区間行列をそのまま使える ＝ 感度 2 本が
        ただで出る。
        """
        return [dict(h, radius_m=h["radius_m"] + d_dia_mm / 2000.0,
                     chimney_m=h["chimney_m"] + d_chimney_mm / 1000.0)
                for h in holes]

    def _scale_card(self, params: dict) -> dict:
        """全閉から順に開けたときの音階と、4-B.2c が使うつまみの効き。"""
        solver, holes = self._solver(params)
        rows_scale = solver.scale()
        rows = [[f"{r['name']}（目標 {r['target_note']}）",
                 f"{r['freq']:.1f} Hz  {r['cents']:+.0f} c"] for r in rows_scale]
        opened = [r for r in rows_scale if r["name"] != "全閉"]
        if opened:
            base = [r["cents"] for r in opened]
            for label, kw in (("チムニー +1mm", {"d_chimney_mm": 1.0}),
                              ("指孔径 +1mm", {"d_dia_mm": 1.0})):
                got = solver.scale(self._shifted(holes, **kw))
                d = [g["cents"] - b for g, b in
                     zip([g for g in got if g["name"] != "全閉"], base)]
                rows.append([label,
                             f"平均 {sum(d) / len(d):+.1f} c "
                             f"（{min(d):+.1f}〜{max(d):+.1f}）"])
        worst = max(rows_scale, key=lambda r: abs(r["cents"]))
        note = ("**調律の保証ではありません。** 4-B.2b の穴位置は 0 次規則"
                "（開孔位置＝その音が鳴る円錐長）で置いた**暫定値**で、実測でも解でも"
                "ありません。有限径の穴は完全な開口端ではないので、実際の共鳴は"
                "0 次の予測より低く出ます。ここに出ているセントは「設計が外れている量」"
                "ではなく、**4-B.2c のソルバが潰す残差**そのものです。"
                "評価は理想マウスピース＋直線円錐（ベル未接続）の上で、"
                "TMM 固定・全閉が目標音ちょうどになる物差しで行っています。")
        if abs(worst["cents"]) <= SCALE_TOL_CENTS:
            return {"title": "音階（側孔・暫定配置）",
                    "big": f"最大 {worst['cents']:+.0f} c", "status": "ok",
                    "rows": rows, "advice": note}
        return {"title": "音階（側孔・暫定配置）",
                "big": f"最大 {worst['cents']:+.0f} c（{worst['name']}）",
                "status": "warn", "rows": rows,
                "advice": (f"0 次配置のままだと {worst['name']} が "
                           f"{worst['cents']:+.0f} セント外れます。"
                           f"チムニーと穴径の効きは上の 2 行です。 ") + note}

    def _reach_card(self, params: dict) -> dict:
        """指が届くか。**キーレスで最初に効く拘束はここ。**"""
        p, si, n = params, self.size_info, self._neck()
        holes = bpf.hole_layout(p, si, n)
        fingers = [h for h in holes if h["role"] == "finger"]
        span = bpf.hole_span_mm(p, si, n)
        zones: dict[str, int] = {}
        for h in holes:
            z = bpf.hole_zone(h["s_mm"], p, n)
            zones[z] = zones.get(z, 0) + 1
        rows = [
            ["指孔の本数", f"{len(fingers)} 本"
             + ("＋親指孔" if len(holes) > len(fingers) else "")],
            ["指孔の弧長スパン", f"{span:.0f} mm"],
            ["両手の実用スパン目安", f"{bpf.HAND_SPAN_MM:.0f} mm"],
            ["載る区間", " / ".join(f"{k} {v}本" for k, v in sorted(zones.items()))],
            ["指孔径 / ふさげる目安",
             f"φ{p['hole_dia']:.1f} / φ{bpf.FINGER_PAD_DIA_MM:.0f} mm"],
        ]
        if fingers:
            rows.insert(1, ["最上 → 最下（スロートから）",
                            f"{min(h['s_mm'] for h in fingers):.0f} → "
                            f"{max(h['s_mm'] for h in fingers):.0f} mm"])
        common = ("スパンは音程で決まります —— 実効長が 1/f に比例する管"
                  "（円錐も円筒もそう）では、全閉から 1 オクターブ上までの位置比は"
                  "`f_高/f_低` そのもので、頂点から測った管の 44.1% にあたります。"
                  "だから**「穴を寄せる」ことはできません**。"
                  f"目安の {bpf.HAND_SPAN_MM:.0f}mm はリコーダ（約200）と"
                  "クラリネット（7孔で約230）の実測から採った値で、物理ではありません。")
        if float(p["hole_dia"]) > bpf.FINGER_PAD_DIA_MM and fingers:
            rows.append(["注意", "指では塞ぎきれない太さです"])
        fit = bpf.max_finger_holes_in_span(si)
        rows.append([f"{bpf.HAND_SPAN_MM:.0f}mm に収まる本数",
                     f"{fit} 本（＝全閉を入れて {fit + 1} 音）"])
        if span > bpf.HAND_SPAN_MM:
            return {"title": "指の届く範囲", "big": "届きません", "status": "warn",
                    "rows": rows,
                    "advice": (f"指孔が {span:.0f}mm に広がっており、両手では"
                               f"押さえられません（目安の {span / bpf.HAND_SPAN_MM:.1f} 倍）。"
                               "**これは配置の失敗ではなく、このサイズでキーレス全音階が"
                               "成立しないという結論です。** 逃げ道は 3 つ ——"
                               f"(1) 音階の段数を減らす（このサイズなら {fit} 孔まで）、"
                               "(2) フォーク運指で穴を減らす、"
                               "(3) もっと小さい楽器にする。"
                               "**キー機構で延ばす**のは 4-B.4 の話で、そうすると"
                               "「キーレス」ではなくなります。 ") + common}
        return {"title": "指の届く範囲", "big": "届きます", "status": "ok",
                "rows": rows,
                "advice": ("指孔が両手のスパンに収まります。ボウやベルに載った穴は"
                           "面が傾くので、実物では押さえにくいことがあります。 ") + common}

    def impedance(self, params: dict) -> dict:
        """全閉のインピーダンス曲線（理想マウスピース＋側孔）。

        OpenWind があればそちらで解く（`holes_valves` を渡す）。無ければ TMM。
        """
        from saxsketch.acoustics import openwind_bridge as ob
        return ob.impedance(None, self.size_info,
                            geometry=self._ideal_geometry(),
                            holes=bpf.acoustic_holes(params, self.size_info,
                                                     self._neck()))

    def _joint_card(self, params: dict) -> dict:
        """ネックとの接続。一体型はマウスピース適合まで、別体は受け口の噛み合い。"""
        p, si, n = params, self.size_info, self._neck()
        if bpf.is_integrated(p):
            fit = reference_check.INTERFERENCE_FIT_MM
            need = n["tenon_od"] + 2.0 * n["cork_thickness"]
            rows = [
                ["繋ぎ方", "一体（ネックまで1部品）"],
                ["ネック区間の弧長", f"{n['neck_length']:.0f} mm"],
                ["テノン外径 ＋ コルク", f"φ{need:.2f} mm（自由状態）"],
                ["合うマウスピースのボア径", f"φ{need - fit:.2f} mm"],
                ["部品の弧長", f"{bpf.part_arc(p, n):.0f} mm"],
            ]
            advice = ("テノン継手が無いので漏れ経路とボアの段差が 1 つ減ります。"
                      "代わりに**姿勢を調整できません** —— 実機のネックは回して銜え角を"
                      "合わせます。ストレートソプラノは元からそうなので実害は小さいですが、"
                      "曲げのあるサイズでは奏者ごとの角度差を吸収できません。"
                      "壊れたときに全部作り直しになる点も別体との違いです。"
                      "**音響はどちらでも同じ**です（継ぎ目はモデルに入っていません）。")
            return {"title": "ネック接続", "big": "一体型", "status": "ok",
                    "rows": rows, "advice": advice}

        sock_id = 2.0 * bpf.socket_bore_radius(p, si, n)
        spigot_od = 2.0 * npf.outer_radius_at(float(n["neck_length"]), n, si)
        rows = [
            ["繋ぎ方", "別体（テノンで挿す）"],
            ["ネックのスピゴット外径", f"φ{spigot_od:.2f} mm"],
            ["受け穴内径", f"φ{sock_id:.2f} mm（片側隙間 {p['socket_clearance']:.2f}）"],
            ["受け深さ / スピゴット長", f"{p['socket_length']:.0f} / {n['body_tenon_length']:.0f} mm"],
            ["部品の弧長", f"{bpf.part_arc(p, n):.0f} mm"],
        ]
        if p["socket_length"] + 0.5 < n["body_tenon_length"]:
            return {"title": "ネック接続", "big": "受けが浅い", "status": "warn", "rows": rows,
                    "advice": (f"受け深さ {p['socket_length']:.0f}mm がネックの挿入部 "
                               f"{n['body_tenon_length']:.0f}mm より浅く、スピゴットが底突きします。"
                               f"受けを深くするか、ネック側の挿入部を短くしてください。")}
        return {"title": "ネック接続", "big": "噛み合い可", "status": "ok", "rows": rows,
                "advice": ("印刷品でいちばん気密が出ないのが継手です。はめあい隙間は"
                           "実測で詰めてください。一体型（ネックまで1部品）にすると"
                           "この継手ごと無くなります —— **音響は変わりません**。")}

    def _cone_card(self, params: dict) -> dict:
        """円錐リーチ。**(B)「ネック省略」を検出する唯一の量。**

        音響へは接続していないので、鳴る音程は**判定しない**。判定するのは
        「円錐が目標の長さに届いているか」という幾何の話だけ。
        """
        p, si, n = params, self.size_info, self._neck()
        reach = bpf.cone_reach_mm(p, n)
        target = self._target_cone_mm()
        d = reach - target
        end_dia = bpf.cone_end_dia(p, si, n)
        gap = bpf.neck_throat_gap_mm(n, si)
        rows = [
            ["円錐リーチ（スロート→出口）", f"{reach:.1f} mm"],
            ["合う長さ（低音 "
             f"{si['low_note_label']} {si['low_note_sounding_hz']:.2f}Hz）", f"{target:.1f} mm"],
            ["差", f"{d:+.1f} mm"],
            ["円錐終端 → ベル出口", f"φ{end_dia:.1f} → φ{p['bell_exit_dia']:.1f} mm"],
        ]
        if abs(gap) > 0.05:
            rows.append(["参照ネックの小端ボアのずれ", f"{gap:+.2f} mm（スロート基準）"])
        note = ("**ベルは音響へ接続していません。** フレアは 3 サイズとも未実測で、"
                "入れると全閉の第1共鳴が +38〜+106 セント動きます。未実測の仮定で音程の"
                "記録値を動かさないため、共鳴管は校正済みの直線円錐のままにしてあります。"
                "したがってこのカードは**鳴る音程を判定していません**。曲げの影響も"
                "入っていません（弧長近似）。")
        if abs(d) <= CONE_REACH_TOL_MM:
            return {"title": "円錐リーチ（音響は未接続）", "big": "円錐は届いている",
                    "status": "ok", "rows": rows, "advice": note}
        if d < 0:
            big, extra = "円錐が短い", (
                f"円錐が {abs(d):.0f}mm 足りません。円錐は長さで音程が決まるので、"
                f"このままだと**約 {self._cents_for(reach, target):+.0f} セント**高くなります。"
                "**ネックを省いて詰めた形になっていないか**を疑ってください —— "
                "一体型は『ネックが本体と 1 部品』であって『ネックを外す』ことでは"
                "ありません。外して詰めると円錐の先端側が消え、アルトなら約 +346 セント"
                "（ほぼ短3度上）で別の楽器になります。")
        else:
            big, extra = "円錐が長い", (
                f"円錐が {d:.0f}mm 余ります。このままだと**約 "
                f"{self._cents_for(reach, target):+.0f} セント**低くなります。"
                "本体管長を詰めてください。")
        return {"title": "円錐リーチ（音響は未接続）", "big": big, "status": "warn",
                "rows": rows, "advice": extra + " " + note}

    def _target_cone_mm(self) -> float:
        """低音が合う円錐の実長 [mm]（スロート→開口）。

        `openwind_bridge` が共鳴管の延長円錐に使っているのと**同じ校正値**を読む。
        別に持つと管体と音響が違う楽器になる。
        """
        from saxsketch.acoustics import openwind_bridge as ob
        from saxsketch.acoustics import volume as ac_volume

        cone = ac_volume.missing_cone(self.size_info)
        x0 = cone["apex_distance_mm"] / 1000.0
        l_ext = ob._calibrate_extension(
            float(self.size_info["low_note_sounding_hz"]), x0, cone["tan_theta"],
            ob.C_SOUND, False)
        return l_ext * 1000.0

    def _cents_for(self, reach: float, target: float) -> float:
        """円錐リーチの違いをセントに直す（一次近似）。長いほど低い。

        **頂点距離を足してから比を取る。** 鳴っている管は「マウスピースが代替して
        いる欠損円錐（頂点〜スロート）＋ 実物の管（スロート〜開口）」で、
        f1 ≈ c/(2·全長)。リーチだけの比で出すと頂点のぶんを落として過大になる ——
        アルトでネックを省いた場合、リーチ比だと +431 セントだが、頂点 217.5mm を
        足した 994.8/1214.8 では **+346 セント**が正しい。
        """
        import math

        from saxsketch.acoustics import volume as ac_volume

        apex = ac_volume.missing_cone(self.size_info)["apex_distance_mm"]
        return -1200.0 * math.log2(max(apex + reach, 1e-6) / (apex + target))

    def _print_card(self, params: dict) -> dict:
        p, n = params, self._neck()
        vol_cc = bpf.body_volume_mm3(p, self.size_info, n) / 1000.0
        dens = MAT_DENSITY.get(p["material"], 1.15)
        arc = bpf.part_arc(p, n)
        segs = max(1, int(-(-arc // BED_HINT_MM)))
        rows = [
            ["部品の弧長", f"{arc:.0f} mm"],
            ["実用ベッド長の目安", f"{BED_HINT_MM:.0f} mm"],
            ["分割の見込み", f"{segs} 分割"],
            ["肉厚 / 下限", f"{p['wall_thickness']:.1f} / {p['min_wall']:.1f} mm"],
            ["材料体積 / 概算質量", f"{vol_cc:.1f} cc / {vol_cc * dens:.0f} g"],
        ]
        if p["wall_thickness"] < p["min_wall"]:
            return {"title": "印刷・肉厚・気密", "big": "肉厚不足", "status": "bad", "rows": rows,
                    "advice": (f"肉厚が下限 {p['min_wall']:.1f}mm を下回ります。管壁が薄いと"
                               "気密と強度が出ません。肉厚を上げてください。")}
        advice = ("管体は層間の気密が要ります。FDM では層間ポロシティで漏れやすいので、"
                  "レジン（光造形）か印刷後のシーリングを推奨します。")
        if segs > 1:
            advice += (f" 弧長がベッド目安を超えるので **{segs} 分割**になります。"
                       "分割そのものは後段 4-B.3 で、いまは出力しません。"
                       "一体型を選んだから分割が要るのではなく、**別体でも要ります** "
                       "（一体型が増やすのはネックの弧長ぶんだけ）。")
        if bpf.is_integrated(p) and n["bend_angle"] > 0.0:
            advice += (" 一体型では継手を曲げの内部に置けないので、分割線は曲げの前後に"
                       "限られます（4-B.3 への制約）。")
        return {"title": "印刷・肉厚・気密", "big": "造形可", "status": "ok",
                "rows": rows, "advice": advice}

    # ------------------------------------------------------------ 領域 / BOM / 仕様書

    def regions(self, params: dict) -> dict:
        reg = bpf.param_regions(params, self._neck())
        reg.update(bpf.hole_regions(params, self.size_info, self._neck()))
        return reg

    def bom(self, params: dict) -> list[dict]:
        p, n = params, self._neck()
        size_label = {"soprano": "ソプラノ", "alto": "アルト", "tenor": "テナー"}[self.size]
        vol_cc = bpf.body_volume_mm3(p, self.size_info, n) / 1000.0
        arc = bpf.part_arc(p, n)
        segs = max(1, int(-(-arc // BED_HINT_MM)))
        kind = "管体＋ネック一体" if bpf.is_integrated(p) else "管体"
        rows = [
            {"type": "3Dプリント", "name": f"{kind}（{size_label}）", "qty": 1,
             "material": MAT_LABELS.get(p["material"], p["material"]),
             "note": (f"材料体積 約{vol_cc:.0f}cc・弧長 {arc:.0f}mm。"
                      f"ベッド目安では {segs} 分割（分割は 4-B.3）"
                      + (f"。側孔 {len(bpf.hole_layout(p, self.size_info, n))} 個"
                         f"（一体造形・後加工なし）" if bpf.is_holed(p) else ""))},
        ]
        if bpf.is_integrated(p):
            rows.append({"type": "市販品", "name": "テノン コルクストリップ", "qty": 1,
                         "material": "コルク",
                         "note": f"厚 {n['cork_thickness']:.1f}mm（マウスピース勘合）"})
        else:
            rows.append({"type": "市販品", "name": "ネック接合 コルク／Oリング", "qty": 1,
                         "material": "コルク/NBR", "note": "受け口の気密"})
        return rows

    def _section_svg(self, params: dict) -> str:
        from saxsketch.export.svg import polyline_svg
        pr = bpf.side_profile_polylines(params, self.size_info, self._neck())
        return polyline_svg([
            {"pts": pr["outer_top"], "stroke": "#222", "width": 1.5},
            {"pts": pr["outer_bot"], "stroke": "#222", "width": 1.5},
            {"pts": pr["bore_top"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
            {"pts": pr["bore_bot"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
        ], "側面断面図（実線=外形 / 青破線=ボア） 単位:mm")

    def spec_extras(self, params: dict) -> dict:
        p, n = params, self._neck()
        vol_cc = bpf.body_volume_mm3(p, self.size_info, n) / 1000.0
        holes = bpf.hole_layout(p, self.size_info, n)
        dims = [
            ("ネックの繋ぎ方", "一体（1部品）" if bpf.is_integrated(p) else "別体（テノン）"),
            ("部品の弧長", f"{bpf.part_arc(p, n):.0f} mm"),
            ("円錐リーチ（スロート→出口）", f"{bpf.cone_reach_mm(p, n):.0f} mm"),
            ("スロート → 円錐終端",
             f"φ{2 * bpf.throat_radius(self.size_info):.1f} → "
             f"φ{bpf.cone_end_dia(p, self.size_info, n):.1f} mm"),
            ("ベル", f"長さ {p['bell_length']:.0f} mm / 出口 φ{p['bell_exit_dia']:.0f} mm"),
            ("ボウ", f"{p['bow_angle']:.0f} ° / 半径 {p['bow_radius']:.0f} mm"),
            ("肉厚", f"{p['wall_thickness']:.1f} mm"),
            ("材料体積", f"{vol_cc:.0f} cc"),
        ]
        if holes:
            fingers = [h for h in holes if h["role"] == "finger"]
            dims.append(("側孔", f"指孔 {len(fingers)} 本 φ{p['hole_dia']:.1f} / "
                                 f"チムニー {p['hole_chimney']:.1f} mm"
                                 + ("＋親指孔" if len(holes) > len(fingers) else "")))
            dims.append(("側孔の弧長（スロートから）",
                         " / ".join(f"{h['s_mm']:.0f}" for h in holes) + " mm"
                         + "（0 次規則の暫定配置）"))
        return {"dimensions": dims,
                "sections": [{"title": "断面図", "svg": self._section_svg(p)}]}
