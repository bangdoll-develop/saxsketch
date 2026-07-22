"""マウスピースの断面プロファイル（純数学・OCCT非依存）。

座標系:
  Z: 軸方向。z=0 がティップ（先端）、z=L がシャンク端。
  Y: +Y がビーク（上面）、-Y がテーブル（リード側）。
  X: 幅方向。

ジオメトリ生成・体積計算・断面SVG・音響シミュレーションが本モジュールを共用する。
断面はすべてスーパー楕円 |2x/w|^n + |2(y-yc)/h|^n = 1 で表現する
（n=2 かつ w=h で真円、n が大きいほど角形）。ロフトが安定し自己交差しない。
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------- 基本量

def table_y(p: dict) -> float:
    """テーブル平面（リード接地面）の Y 座標。"""
    return -0.40 * p["body_dia"]


def bore_radius(p: dict) -> float:
    return p["bore_dia"] / 2.0


def bore_start_z(p: dict) -> float:
    return p["overall_length"] - p["bore_length"]


def window_width(p: dict) -> float:
    return p["reed_width"] - 2.0 * p["side_rail_width"]


def throat_radius(p: dict) -> float:
    """スロート（チェンバー最狭部）の等価半径。断面積 = throat_ratio × ボア断面積。

    半径比 `r_b·√ratio` では駄目で、面積から解く必要がある。スロートの断面指数は
    チェンバーに合わせた 2.1 前後、ボアは真円 2.0 で形が違うため、同じ半径でも
    断面積が 1.8% ずれ、比 1.0 でスロートがボアより広くなっていた。
    （`chamber_ratio` で同じ誤りを Phase 3.5 で直している。ラベルどおり面積で定義する。）

    真円（指数 2.0）では k = π/4 なので `r_b·√ratio` に一致し、従来の値と変わらない。
    """
    k = _superellipse_shape_factor(_throat_n(p))
    return bore_radius(p) * math.sqrt(p["throat_ratio"] * math.pi / (4.0 * k))


def throat_ratio_from_radius(p: dict, r_t: float) -> float:
    """実測したスロート等価半径から `throat_ratio` を逆算する（`throat_radius` の逆関数）。"""
    k = _superellipse_shape_factor(_throat_n(p))
    rb = bore_radius(p)
    return (r_t / rb) ** 2 * 4.0 * k / math.pi if rb > 0 else 1.0


def _superellipse_shape_factor(n: float) -> float:
    """スーパー楕円の面積係数 k（A = w·h·k）。真円 n=2 で π/4。"""
    g1 = math.gamma(1.0 + 1.0 / n)
    g2 = math.gamma(1.0 + 2.0 / n)
    return (g1 * g1) / g2


# ---------------------------------------------------------------- フェイシング

def facing_rise(p: dict, z: float) -> float:
    """テーブル平面からのフェイシングカーブ持ち上がり量（z<=facing_length で >0）。"""
    fl = p["facing_length"]
    tip = p["tip_opening"]
    if z >= fl:
        return 0.0
    if p.get("facing_curve", "elliptic") == "radial":
        # テーブルに接する円弧。R は y(0)=tip となるよう決定。
        r = (fl * fl + tip * tip) / (2.0 * tip)
        return r - math.sqrt(max(r * r - (fl - z) ** 2, 0.0))
    # 楕円（z=fl で接線水平）
    t = (fl - z) / fl
    return tip * (1.0 - math.sqrt(max(1.0 - t * t, 0.0)))


def cut_top_y(p: dict, z: float) -> float:
    """テーブル/フェイシングカット面の上端 Y。

    テーブルはリード踵（＝リガチャー座の後端）まで平面、その先はランプで胴の丸みに消える。
    ランプ位置を比率リテラルで持たないのは、外形プロファイルを動かしたときに置き忘れて
    テーブルがリードの下まで届かなくなる事故を起こしたため（Phase 3.5）。
    """
    ty = table_y(p)
    ramp_start = ligature_seat_range(p)[1]
    ramp_end = table_cut_end_z(p)
    if z <= ramp_start:
        return ty + facing_rise(p, z)
    if z >= ramp_end:
        return ty - 4.0
    t = (z - ramp_start) / (ramp_end - ramp_start)
    return ty - 4.0 * t


#: テーブル平面をリード踵より後ろへ延ばす余裕 [mm]。踵ちょうどで終わると
#: リードの最後端が宙に浮く。
TABLE_RUNOUT = 2.0


def table_cut_end_z(p: dict) -> float:
    """テーブル終端 z。リード踵（リガチャー座の後端）より必ず後ろにする。"""
    return ligature_seat_range(p)[1] + TABLE_RUNOUT


# ---------------------------------------------------------------- 外形・ビーク

_OUTER_PROFILE = [  # (z/L, r/rb) 制御点
    (0.00, 0.70),
    (0.20, 0.84),
    (0.45, 0.96),
    (0.66, 1.00),   # ← 最大径（リガチャー座）の始まり
    (0.88, 1.00),   # ← 最大径の終わり。リード踵がここに来る
    (0.95, 0.93),
    (1.00, 0.86),
]
# 最大径区間（r/rb == 1.0 の平坦部）がリガチャー座になる。後端を 0.88 に置くのは
# リードの踵がそこへ来るため。逆に言うとテンプレートの全長はこの比から決まる:
# 全長 = リード規格長 / 0.88 → soprano 63.5/72.2、alto 71.5/81.2、tenor 78.0/88.6。


def outer_radius(p: dict, z: float) -> float:
    rb = p["body_dia"] / 2.0
    t = min(max(z / p["overall_length"], 0.0), 1.0)
    pts = _OUTER_PROFILE
    for (t0, r0), (t1, r1) in zip(pts, pts[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            u = u * u * (3 - 2 * u)  # smoothstep で滑らかに
            return rb * (r0 + (r1 - r0) * u)
    return rb * pts[-1][1]


def ligature_seat_range(p: dict) -> tuple[float, float]:
    """リガチャーが座る z 範囲。外形が最大径で一定になる区間。

    比率は `_OUTER_PROFILE` から導出する（数値を二重に持たない）。リガチャーの
    内周生成・リードの踵位置チェック・逆算の測定帯がすべて本関数を共用する。
    """
    flat = [t for t, r in _OUTER_PROFILE if r >= 1.0 - 1e-9]
    length = p["overall_length"]
    return min(flat) * length, max(flat) * length


#: ティップ先端のくさび厚（ティップ開きの上に残る肉）[mm]
_TIP_WEDGE = 2.6
#: ビークが外形の丸みに溶け込む位置（全長比）。ここより後ろは切らない。
_BEAK_SHOULDER = 0.55
#: バイトポイントの目安位置（全長比）
_BEAK_BITE = 0.25


def beak_y(p: dict, z: float) -> float:
    """ビークカット面の Y 座標（この上側を切除）。

    ティップのくさび → バイトポイント → ショルダー（外形に接して消える）の3点を通す。
    直線にしていたときは、`beak_height` が胴の全高 `0.9·body_dia` に近い既定値だったため
    ビーク面が全長の 1/4 で外形を追い越し、テーパが消えるうえに空洞の天井 clamp
    （`beak_y - min_wall`）まで無効化されて本体が貫通した。3点通過なら
    `beak_height` の値によらずショルダーまで必ず本体の内側にある。
    """
    ty = table_y(p)
    length = p["overall_length"]
    y0 = ty + p["tip_opening"] + _TIP_WEDGE
    z_bite = _BEAK_BITE * length
    y_bite = ty + p["beak_height"]
    z_sh = _BEAK_SHOULDER * length
    y_sh = outer_radius(p, z_sh)
    if z <= 0.0:
        return y0 + (y_bite - y0) * (z / z_bite)      # ティップ手前は直線外挿
    if z < z_bite:
        return y0 + (y_bite - y0) * _smoothstep_half(z / z_bite)
    if z < z_sh:
        t = (z - z_bite) / (z_sh - z_bite)
        return y_bite + (y_sh - y_bite) * _smoothstep(t)
    # ショルダーより後ろ: 外形の外側に置いて何も切らない
    return outer_radius(p, z) + 1.0


def _smoothstep_half(t: float) -> float:
    """0で傾き最大・1で水平（smoothstep の後半だけ）。ティップから立ち上がり、
    バイトポイントで傾きが緩む実物のビーク断面に合わせる。"""
    t = min(max(t, 0.0), 1.0)
    return t * (2.0 - t)


# ---------------------------------------------------------------- 内部空洞

def _smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def shell_limit(p: dict, z: float) -> dict:
    """z における空洞の許容包絡 {top, bot, half_width}（すべて min_wall だけ内側）。

    外形回転体とビークカットから決まる「残る材料」の内寸。空洞ステーションは必ず
    ここを通す。Phase 3.5 で外形だけ縮めた結果、チェンバーが本体の左右と上を貫通し、
    しかも体積積分が外へ出た分まで数えて Tier1 が「合格」した事故の再発防止。

    テーブルカットは含めない。窓はカット面より下へ抜けて初めて開口になるので、
    下端まで拘束すると窓が閉じる（`cavity_stations` が role で使い分ける）。
    """
    ro = outer_radius(p, z)
    mw = p["min_wall"]
    return {
        "top": min(ro, beak_y(p, z)) - mw,
        "bot": -(ro - mw),
        "half_width": ro - mw,
    }


#: ステップ バッフルの段差位置（窓区間内の t）。`_window_ts` が段差の直前・直後に
#: 近接ステーションを入れて、ロフトに準垂直の壁（実段差）を張らせる。
_STEP_T = 0.40


def _baffle_progress(p: dict, t: float) -> float:
    """窓区間内 t∈[0,1] に対する天井上昇率 u∈[0,1]。バッフル種別で形が変わる。

    straight=線形スロープ、rollover=凸の肩（放物）、step=実段差、
    curve=凹（早く立ち上がり高天井で張り出す＝メタリック/アグレッシブ）。
    """
    kind = p.get("baffle_type", "rollover")
    if kind == "straight":
        return t
    if kind == "rollover":
        expo = 1.6 + p.get("rollover_radius", 8.0) / 10.0
        return t ** expo
    if kind == "step":
        # 幅 0.05 の急峻な遷移。`_window_ts` が t=_STEP_T±0.02 に点を足すため、
        # 数mm の z 幅で天井が跳ね上がり、ほぼ垂直の段差面になる。
        return 0.06 + 0.94 * _smoothstep((t - (_STEP_T - 0.02)) / 0.05)
    if kind == "curve":
        expo = 1.6 + p.get("rollover_radius", 8.0) / 10.0
        return 1.0 - (1.0 - t) ** expo
    return t


#: 窓断面をサンプルする既定の t 列（ティップ→窓終端）。
_WINDOW_TS = [0.0, 0.12, 0.25, 0.40, 0.55, 0.70, 0.82, 0.92, 1.0]


def _window_ts(p: dict) -> list[float]:
    """窓ステーションの t サンプル列。ステップ時は段差位置に近接点を挿入する。"""
    ts = list(_WINDOW_TS)
    if p.get("baffle_type") == "step":
        ts += [_STEP_T - 0.02, _STEP_T + 0.02]
        ts = sorted(set(ts))
    return ts


#: チェンバー断面の基準形（スロート等価半径に対する 幅・高さ の倍率）。
#: 実物のチェンバーは横長なので幅を取り高さを抑える。
_CHAMBER_W = 2.0 * 1.05
_CHAMBER_H = 1.7

#: チェンバー定断面区間の後端（ボア開始からの距離）[mm]
_CHAMBER_RUN = 8.0
#: スロート狭窄の位置（ボア開始からの距離）[mm]。実物の狭窄は短い。
_THROAT_RUN = 3.0


def chamber_size(p: dict) -> tuple[float, float]:
    """チェンバー最大部の要求 (幅, 高さ) [mm]。外殻による頭打ちは含まない。

    `chamber_ratio` は**断面積比**として定義する（半径比ではない）。チェンバーは
    横長のスーパー楕円、スロートはほぼ円で形が違うため、半径を同じ倍率にしても
    面積が逆転しうる（実際ソプラノで最大部が最狭部より狭くなっていた）。
    音響的に効くのは断面積なので、面積で定義すれば比 1.0 が必ず「同じ広さ」になる。

    実際に生成される寸法は `cavity_stations()` が `shell_limit()` で切り詰めた後の値。
    頭打ちが起きているかは `chamber_saturated()` で判定する。
    """
    r_t = throat_radius(p)
    n_ch = _chamber_n(p)
    a_throat = superellipse_area(2.0 * r_t, 2.0 * r_t, _throat_n(p))
    w0, h0 = _CHAMBER_W * r_t, _CHAMBER_H * r_t
    # 基準断面積を「その形状」で評価する。断面積は (w,h) について2次同次なので、
    # w0,h0 を一律 scale 倍すれば形状によらず断面積が chamber_ratio×a_throat になる。
    # round/square は section_area == superellipse_area(w0,h0,n_ch) で従来式と厳密一致。
    base = {"yc": 0.0, "h": h0, "w": w0, "n": n_ch,
            "shape": p.get("chamber_shape", "round")}
    scale = math.sqrt(p.get("chamber_ratio", 1.15) * a_throat / section_area(base))
    return w0 * scale, h0 * scale


def chamber_saturated(p: dict) -> bool:
    """チェンバーが肉厚制限で頭打ちになっているか。

    True のときは `chamber_ratio` を上げても形が変わらない。UI がスライダの
    効かない範囲を黙って持つのは不親切なので、Tier1 の助言がこれを見て一言添える。

    判定は clamp 条件を書き写すのではなく、比を少し上げて実際に断面積が動くかを見る。
    チェンバーは複数ステーションあり、幅だけ頭打ちで高さにはまだ余地がある、といった
    中間状態を取るので、条件を再実装すると必ずずれる。
    """
    step = 1.05
    now = _chamber_areas(p)
    more = _chamber_areas(dict(p, chamber_ratio=p.get("chamber_ratio", 1.15) * step))
    return all(b - a < 1e-6 for a, b in zip(now, more))


def _chamber_areas(p: dict) -> list[float]:
    return [section_area(s)
            for s in stations_by_role(cavity_stations(p), "chamber")]


def chamber_ratio_from_width(p: dict, w_meas: float, r_t_meas: float) -> float:
    """実測したチェンバー幅とスロート半径から `chamber_ratio` を逆算する。

    `chamber_size()` の逆関数。逆算（measure.py）が断面形の係数を再実装しないよう
    ここに置く。高さは幅と固定比なので幅だけから断面積が決まる。
    """
    h_meas = w_meas * _CHAMBER_H / _CHAMBER_W
    a_ch = section_area({"yc": 0.0, "h": h_meas, "w": w_meas, "n": _chamber_n(p),
                         "shape": p.get("chamber_shape", "round")})
    a_th = superellipse_area(2.0 * r_t_meas, 2.0 * r_t_meas, _throat_n(p))
    return a_ch / a_th if a_th > 0 else 1.0


#: チェンバー断面のスーパー楕円指数。round/square は断面そのものを決め、
#: 馬蹄/フラットサイドウォールでは（断面積はシューレースで別途求めるため）
#: スロート平滑化と逆算 prior の基準としてのみ使う。
_CHAMBER_N = {"round": 2.2, "square": 3.8, "horseshoe": 2.6, "flat_sidewall": 3.0}


def _chamber_n(p: dict) -> float:
    return _CHAMBER_N.get(p.get("chamber_shape", "round"), 3.8)


def _throat_n(p: dict) -> float:
    return (_chamber_n(p) + 2.0) / 2.0


def cavity_stations(p: dict) -> list[dict]:
    """内部空洞ロフトの断面ステーション列。

    各要素: {z, yc, h, w, n, role}（スーパー楕円）。ティップ側→ボア側の順。
    role は "window" / "chamber" / "throat" / "bore"。実物の
    「窓 → チェンバー(最大) → スロート(最狭) → ボア」を再現する。
    逆算（measure.py）は index でなく role でステーションを引く。
    """
    ty = table_y(p)
    z_start = p["tip_rail_width"] + 0.2
    z_we = z_start + p["window_length"]
    zb = bore_start_z(p)
    z_we = min(z_we, zb - _CHAMBER_RUN - 5.0)  # チェンバー区間の余地を確保
    rb_bore = bore_radius(p)
    r_t = throat_radius(p)
    w_ch, h_ch = chamber_size(p)
    w_win = window_width(p)
    h_b = p["baffle_height"]
    min_wall = p["min_wall"]

    # チェンバー最大部（窓の直後）
    z_c1 = z_we + 3.0
    c1_bot = ty + 1.5
    c1_top = c1_bot + h_ch
    # ボア円
    b_bot, b_top = -rb_bore, rb_bore

    # ティップ天井基準
    floor0 = ty + facing_rise(p, z_start) - 0.8
    c_tip = floor0 + 1.6
    ch_top_target = c1_top

    n_window = 3.5
    n_chamber = _chamber_n(p)

    ch_shape = p.get("chamber_shape", "round")

    stations: list[dict] = []
    for t in _window_ts(p):
        z = z_start + t * (z_we - z_start)
        if t <= 0.90:
            floor = ty + facing_rise(p, z) - 0.8   # カット面より下 → 窓が開く
        else:
            floor = ty + 1.2                        # 窓を閉じる
        u = _baffle_progress(p, t)
        ceil_ = c_tip + (ch_top_target - c_tip) * u
        ceil_ -= h_b * 0.55 * (1.0 - t)             # 高バッフル = 天井をリードに近づける
        w = w_win * (0.82 + 0.18 * t)
        stations.append({"z": z, "yc": (floor + ceil_) / 2, "h": ceil_ - floor,
                         "w": w, "n": n_window, "role": "window", "shape": "round"})

    # 窓終端 → チェンバー（定断面区間）→ スロート最狭部 → ボア開始。
    # 実物は「一定断面のチェンバー → 短い狭窄 → ボア」で、狭窄を長く取ると
    # 内容積を無駄に失う。スロートはボア直前に置く。
    # chamber ステーションだけ chamber_shape（round/square/馬蹄/フラットサイドウォール）を
    # 帯び、スロート・ボアは丸（round）に戻す。
    z_c2 = zb - _CHAMBER_RUN
    z_th = zb - _THROAT_RUN
    chamber = [
        (z_c1, c1_bot, c1_top, w_ch, n_chamber, "chamber", ch_shape),
        (z_c2, c1_bot, c1_top, w_ch, n_chamber, "chamber", ch_shape),
        (z_th, -r_t, r_t, 2.0 * r_t, _throat_n(p), "throat", "round"),
        (zb, b_bot, b_top, 2.0 * rb_bore, 2.0, "bore", "round"),
    ]
    for z, bot, top, w, n, role, shape in chamber:
        stations.append({"z": z, "yc": (bot + top) / 2, "h": top - bot,
                         "w": w, "n": n, "role": role, "shape": shape})

    return [_contain(p, s) for s in stations]


def cavity_sections(p: dict) -> list[dict]:
    """内部空洞ロフト用の断面列 [{z, pts}]（ティップ→ボアの z 昇順）。

    `cavity_stations()` を `section_pts()` でポリゴン化したもの。全断面が点数一定・
    同順のため、`builders.loft_sections` で水密ソリッドになる。
    """
    return [{"z": s["z"], "pts": section_pts(s)} for s in cavity_stations(p)]


def _contain(p: dict, s: dict) -> dict:
    """ステーションを `shell_limit()` の内側へ切り詰める。

    窓（role == "window"）の下端だけは拘束しない。窓はテーブルカット面より下へ
    抜けて初めて開口になるので、下端を clamp すると窓が閉じてしまう。下側の材料は
    テーブルカットが除去済みなので、はみ出しても本体は破れない。
    """
    lim = shell_limit(p, s["z"])
    top = min(s["yc"] + s["h"] / 2.0, lim["top"])
    bot = s["yc"] - s["h"] / 2.0
    if s["role"] != "window":
        bot = max(bot, lim["bot"])
    # ロフトが潰れないための下限。天井は外殻の拘束なので、広げるなら床を下げる。
    bot = min(bot, top - 1.0)
    w = min(s["w"], 2.0 * lim["half_width"])
    return {**s, "yc": (top + bot) / 2.0, "h": top - bot, "w": w}


def chamber_max_station(stations: list[dict]) -> dict:
    """チェンバー区間のうち断面積が最大のステーション。

    `chamber_size()` が返すのは「最大部」の寸法だが、窓直後のステーションは
    ビークの下にあって外殻に強く切り詰められ、スロートより狭くなることがある
    （実物も窓の直後は絞られている）。最大部を指す場所は index ではなく
    断面積で選ぶ。逆算（measure）と検証がこの一箇所を共用する。
    """
    ch = stations_by_role(stations, "chamber")
    return max(ch, key=section_area)


def stations_by_role(stations: list[dict], role: str) -> list[dict]:
    """role でステーションを絞る。ステーション構成が変わっても壊れない引き方。"""
    return [s for s in stations if s.get("role") == role]


def superellipse_area(w: float, h: float, n: float) -> float:
    """スーパー楕円の面積。A = w·h·Γ(1+1/n)² / Γ(1+2/n)"""
    return w * h * _superellipse_shape_factor(n)


# ---------------------------------------------------------------- 断面ポリゴン（4形状）

#: 全断面で固定する頂点数。円形の窓/スロート/ボアと非対称チェンバーを同数・同順
#: （+X 始点・反時計回り）で並べ、ルールドロフトがねじれないようにする
#: （`builders.flat_bottom_rect_pts` と同じ堅牢性方針）。
_SECTION_SAMPLES = 96


def _super_pts(yc: float, h: float, w: float, nx: float, ny: float,
               samples: int = _SECTION_SAMPLES) -> list[tuple[float, float]]:
    """異方スーパー楕円 |2x/w|^nx + |2(y-yc)/h|^ny = 1 の点列（+X 始点・反時計回り）。

    nx=ny で従来の等方スーパー楕円（`builders.superellipse_wire` の2D版）。
    nx を大きくすると左右が立ち上がる（フラットサイドウォール）。
    """
    pts = []
    for i in range(samples):
        th = 2.0 * math.pi * i / samples
        c, s = math.cos(th), math.sin(th)
        x = (w / 2.0) * math.copysign(abs(c) ** (2.0 / nx), c)
        y = yc + (h / 2.0) * math.copysign(abs(s) ** (2.0 / ny), s)
        pts.append((x, y))
    return pts


def _superellipse_pts(yc: float, h: float, w: float, n: float,
                      samples: int = _SECTION_SAMPLES) -> list[tuple[float, float]]:
    return _super_pts(yc, h, w, n, n, samples)


def _flat_sidewall_pts(yc: float, h: float, w: float,
                       samples: int = _SECTION_SAMPLES) -> list[tuple[float, float]]:
    """フラットサイドウォール：左右が垂直な平面、上下が丸い断面。

    異方スーパー楕円で幅方向の指数を大きく（=側壁を立てる）、高さ方向は丸く保つ。
    """
    return _super_pts(yc, h, w, 7.0, 2.4, samples)


def _horseshoe_pts(yc: float, h: float, w: float,
                   samples: int = _SECTION_SAMPLES) -> list[tuple[float, float]]:
    """馬蹄：丸い天井・側壁を持ち、底の中央が上へ凹む（U字開口）断面。

    等方に近いスーパー楕円をベースに、下半分の中央（θ≈3π/2）だけ内側へ持ち上げて
    凹みを作る。凹みは中心より浅く保つので星状（中心から見て単調）で自己交差しない。
    """
    hh = h / 2.0
    notch = 0.5 * hh          # 凹みの深さ（中心には届かない）
    width = 0.55              # 凹みの角度幅 [rad]
    pts = []
    for i in range(samples):
        th = 2.0 * math.pi * i / samples
        c, s = math.cos(th), math.sin(th)
        n = 2.6
        x = (w / 2.0) * math.copysign(abs(c) ** (2.0 / n), c)
        y = yc + hh * math.copysign(abs(s) ** (2.0 / n), s)
        if s < 0.0:  # 下半分の中央付近を上へ（凹ませる）
            d = th - 1.5 * math.pi
            y += notch * math.exp(-(d * d) / (2.0 * width * width))
        pts.append((x, y))
    return pts


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    """多角形の符号なし面積（シューレース）。"""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2.0


def section_pts(s: dict) -> list[tuple[float, float]]:
    """ステーション {yc,h,w,n,shape?} → 断面ポリゴンの点列。

    shape 未指定（窓/スロート/ボア）と round/square は等方スーパー楕円、
    horseshoe/flat_sidewall は専用ジェネレータ。全形状とも点数一定・同順。
    """
    shape = s.get("shape", "round")
    yc, h, w = s["yc"], s["h"], s["w"]
    if shape == "horseshoe":
        return _horseshoe_pts(yc, h, w)
    if shape == "flat_sidewall":
        return _flat_sidewall_pts(yc, h, w)
    return _superellipse_pts(yc, h, w, s.get("n", 2.0))


def section_area(s: dict) -> float:
    """ステーションの断面積。round/square は解析式（従来値と厳密一致＝校正保全）、
    非対称形は `section_pts` のシューレース面積。"""
    if s.get("shape") in ("horseshoe", "flat_sidewall"):
        return _polygon_area(section_pts(s))
    return superellipse_area(s["w"], s["h"], s.get("n", 2.0))


def cavity_volume_cc(p: dict) -> dict:
    """内部空洞体積の解析近似（断面積の台形積分 + ボア円筒）。

    Returns: total_cc(空洞全体), effective_cc(コーク位置まで＝ネック挿入分を除く)
    """
    st = cavity_stations(p)
    vol = 0.0
    for a, b in zip(st, st[1:]):
        area_a = section_area(a)
        area_b = section_area(b)
        vol += (area_a + area_b) / 2.0 * (b["z"] - a["z"])
    r = bore_radius(p)
    vol += math.pi * r * r * p["bore_length"]
    total_cc = vol / 1000.0
    neck_occupied = math.pi * r * r * p["cork_depth"] / 1000.0
    return {"total_cc": total_cc, "effective_cc": total_cc - neck_occupied}


# ---------------------------------------------------------------- 影響領域（UIハイライト用）

def param_regions(p: dict) -> dict:
    """各パラメータが影響するモデル領域 {key: {z0, z1, side, label}}。

    side: "top"=ビーク側(y>0) / "bottom"=テーブル側(y<0) / "all"=全周。
    3Dビューアが頂点カラーで該当部を着色するために使う。
    """
    length = p["overall_length"]
    fl = p["facing_length"]
    z_start = p["tip_rail_width"] + 0.2
    zb = bore_start_z(p)
    z_we = min(z_start + p["window_length"], zb - 8.0)
    z_baffle_end = z_start + 0.60 * (z_we - z_start)

    def r(z0, z1, side, label):
        return {"z0": round(max(z0, 0.0), 2), "z1": round(min(z1, length), 2),
                "side": side, "label": label}

    return {
        # フェイシング
        "tip_opening":     r(0.0, fl, "bottom", "フェイシング（ティップ〜カーブ終端）"),
        "facing_length":   r(0.0, fl, "bottom", "フェイシング（ティップ〜カーブ終端）"),
        "facing_curve":    r(0.0, fl, "bottom", "フェイシングカーブ"),
        "tip_rail_width":  r(0.0, max(z_start + 1.0, 2.5), "bottom", "ティップレール"),
        "side_rail_width": r(z_start, z_we, "bottom", "サイドレール（窓の両脇）"),
        # バッフル（窓の天井前半）
        "baffle_type":     r(z_start, z_baffle_end, "all", "バッフル（窓の天井）"),
        "baffle_height":   r(z_start, z_baffle_end, "all", "バッフル（窓の天井）"),
        "rollover_radius": r(z_start, z_start + 0.5 * (z_we - z_start), "all",
                             "バッフル肩の丸み"),
        # チェンバー
        "throat_ratio":    r(zb - 6.0, zb, "all", "スロート（最狭部）"),
        "chamber_ratio":   r(z_we, zb - 4.0, "all", "チェンバー（最大部）"),
        "chamber_shape":   r(z_we, zb, "all", "チェンバー断面"),
        # ボア
        "bore_dia":        r(zb, length, "all", "ボア（円筒部）"),
        "bore_length":     r(zb, length, "all", "ボア（円筒部）"),
        "cork_depth":      r(length - p["cork_depth"], length, "all",
                             "シャンク（ネック挿入部）"),
        # ウィンドウ
        "window_length":   r(z_start, z_we, "bottom", "ウィンドウ（リード開口）"),
        "reed_width":      r(z_start, z_we, "bottom", "テーブル・窓幅"),
        # 外形
        "beak_height":     r(0.0, 0.30 * length, "top", "ビーク（上面）"),
        "body_dia":        r(*ligature_seat_range(p), "all", "ボディ（リガチャー座）"),
        "overall_length":  r(0.0, length, "all", "全体"),
        # 製造
        "min_wall":        r(0.0, length, "all", "全体（肉厚）"),
        # material は形状に影響しない → 領域なし
    }


# ---------------------------------------------------------------- 各部名称（参照サイト準拠）

def anatomy_regions(p: dict) -> list[dict]:
    """マウスピース各部の名称と占有 z 範囲（パラメータ非依存の純名称マップ）。

    参照サイト（satoshiozawa / nonaka 等）の呼称に統一し、仕様書の「各部名称」表と
    3Dの部位説明に使う。`param_regions` がパラメータ→領域なのに対し、こちらは
    部位そのものの一覧。ランプ・バレル・ウォールなど従来ラベルに無かった部位も含む。

    side: "top"=ビーク側 / "bottom"=テーブル側 / "all"=全周。
    """
    length = p["overall_length"]
    fl = p["facing_length"]
    z_start = p["tip_rail_width"] + 0.2
    zb = bore_start_z(p)
    z_we = min(z_start + p["window_length"], zb - _CHAMBER_RUN - 5.0)
    z_baffle_end = z_start + 0.60 * (z_we - z_start)
    z_th = zb - _THROAT_RUN
    seat1 = ligature_seat_range(p)[1]

    def r(part, z0, z1, side):
        return {"part": part, "z0": round(max(z0, 0.0), 2),
                "z1": round(min(z1, length), 2), "side": side}

    return [
        r("ビーク", 0.0, 0.30 * length, "top"),
        r("ティップレール", 0.0, z_start, "bottom"),
        r("フェイシング", 0.0, fl, "bottom"),
        r("テーブル", 0.0, table_cut_end_z(p), "bottom"),
        r("ウィンドウ", z_start, z_we, "bottom"),
        r("サイドレール", z_start, z_we, "bottom"),
        r("バッフル", z_start, z_baffle_end, "top"),
        r("ランプ", z_baffle_end, z_we, "all"),
        r("チェンバー", z_we, z_th, "all"),
        r("ウォール", z_we, z_th, "all"),
        r("スロート", z_th, zb, "all"),
        r("ボア", zb, length, "all"),
        r("バレル", zb, seat1, "all"),
        r("シャンク", seat1, length, "all"),
    ]


# ---------------------------------------------------------------- 断面SVG用

def side_profile_polylines(p: dict, samples: int = 120) -> dict:
    """側面断面図のポリライン群（SVG描画用、単位mm）。"""
    length = p["overall_length"]
    zs = [length * i / (samples - 1) for i in range(samples)]
    outer_top = [(z, min(beak_y(p, z), outer_radius(p, z))) for z in zs]
    outer_bot = [(z, max(-outer_radius(p, z), cut_top_y(p, z))
                  if z < table_cut_end_z(p) else -outer_radius(p, z)) for z in zs]
    stations = cavity_stations(p)
    cavity_top = [(s["z"], s["yc"] + s["h"] / 2) for s in stations]
    cavity_bot = [(s["z"], s["yc"] - s["h"] / 2) for s in stations]
    r = bore_radius(p)
    zb = bore_start_z(p)
    cavity_top += [(length, r)]
    cavity_bot += [(length, -r)]
    return {
        "outer_top": outer_top,
        "outer_bot": outer_bot,
        "cavity_top": cavity_top,
        "cavity_bot": cavity_bot,
        "table_y": table_y(p),
        "bore_start": zb,
    }
