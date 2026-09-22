"""リードの断面プロファイル（純数学・OCCT非依存）。

`profiles.py`（マウスピース）と同じ方針: ジオメトリ生成・剛性計算・断面SVG・
音響モデルがすべて本モジュールを共用する。

座標系:
  Z: 軸方向。z=0 が先端（ティップ）、z=L が踵（ヒール）。
  Y: テーブル面（マウスピース接地面）が **y=0**。ブレードは y>0 側のみ。
  X: 幅方向（中心 0）。

テーブル面を y=0 に置くのは、(a) マウスピースへの密着面を厳密な平面にするため、
(b) 3Dビューアの領域ハイライトが y の符号で上下面を判定するため（リードは全体が
y>=0 なので side は "top" / "all" のみ使う）。
"""
from __future__ import annotations

import functools
import math


# ---------------------------------------------------------------- 基本量

def vamp_start_z(p: dict) -> float:
    """削り始め（バーク端）の z。ここから踵側は未削の一定厚。"""
    return min(p["vamp_length"], p["reed_length"] - 2.0)


def tip_curve_depth(p: dict) -> float:
    """前縁カーブの落ち込み [mm]。中央を 0 として、角がどれだけ後ろに来るか。

    実物の前縁はマウスピースのティップレールに沿った曲線で、直線ではない
    （`profiles.tip_contour_z` で解いた輪郭は角が中央より 1.27〜1.57mm 後ろ）。
    0 にすると前縁は z=0 の直線に戻る。
    """
    return max(p.get("tip_curve_depth", 0.0), 0.0)


def tip_arc_radius(p: dict) -> float:
    """前縁カーブの半径。(0, 0) と (±先端幅/2, depth) を通す円。"""
    d = tip_curve_depth(p)
    hw = p["tip_width"] / 2.0
    return (hw * hw + d * d) / (2.0 * d) if d > 0.0 else 0.0


def taper_half_width(p: dict, z: float) -> float:
    """側面テーパーだけの半幅（角の丸みも前縁カーブも掛かっていない素の値）。"""
    t = min(max(z / p["reed_length"], 0.0), 1.0)
    return (p["tip_width"] + (p["heel_width"] - p["tip_width"]) * t) / 2.0


def _nose_discriminant(radius: float, r: float, b: float, s: float) -> float:
    """フィレット中心の 2 次方程式の判別式（÷4）。負なら前縁アークが側面に届かない。

    (1 + s²)z² + 2(sb − R)z + b² + 2Rr − r² = 0 の (sb − R)² − (1 + s²)(b² + 2Rr − r²)
    を整理したもの。`_nose_geometry` と `nose_depth_limit` が同じ式を使う。
    """
    return ((radius - r) ** 2 - b * b - 2.0 * s * b * radius
            - s * s * r * (2.0 * radius - r))


@functools.lru_cache(maxsize=64)
def _nose_geometry(d: float, r: float, tip_w: float, heel_w: float, length: float):
    """先端の平面視輪郭を決める (R, z_t, z_f, x_t, a_f)。純スカラなので lru_cache。

    輪郭は**区間が 3 つの 1 本の曲線**:

        前縁アーク（半径 R）  z < z_t
        角のフィレット（半径 r）  z_t ≤ z < z_f
        側面テーパー          z ≥ z_f

    フィレットは前縁アークと側面の両方に内接する円。中心は側面から r だけ内側
    （x = a(z_f) − r。側面は z_f で局所的に垂直とみなす）なので、中心は
    「アーク中心 (0, R) から R − r の円」と「直線 x = b + s·z」（b = 先端半幅 − r、
    s = テーパーの片側の傾き）の交点 ＝ 2 次方程式の**小さいほうの根**:

        (b + s·z)² + (z − R)² = (R − r)²

    **以前は a の再代入を 5 回で打ち切っていて、深いカーブで収束していなかった。**
    「テーパーは片側 0.02mm/mm 以下」はテンプレートの傾き（旧既定 +0.004〜0.005 /
    実測アルト −0.015）で確かめた仮定で、壁が許す傾きは 9/110 = 0.082 まである。
    収縮率 |s|(a − r)/(R − z_f) は折れて見えた組で 0.135〜0.238 に達し、残差
    2.6e-5〜5.0e-4mm が**アークとフィレットの継ぎ目 z_t に段**を作っていた ——
    掃引の「輪郭の傾きが跳ぶ」（先端 9.0 × 踵 ≥ 15.4 の 5 通り、+0.11〜+1.73）は
    全部これで、幾何の破綻ではなかった（2026-09-23 実測。閉形式にすると
    成立する 15,582 通りで 1 通りも折れない。テンプレートは 3 サイズとも ≤ 7e-11mm
    しか動かない）。根は「積 ÷ 大きいほうの根」で取る —— カーブが浅いと R が
    大きく、差の形では桁が落ちる。s = 0 なら旧式と同じ式。

    **`tip_curve_depth = 0` で現行式に戻る**: R が無くなって z_t = 0 / z_f = r と
    なり、輪郭は「z=0 の直線 → 半径 r のフィレット → 側面」＝ 4-C.2 以前の形。

    **根が無い（判別式 < 0）＝前縁アークが側面に届かない**のが本当の幾何の壁で、
    `nose_depth_limit` が深さに解き、`nose_error` が断る。起きるのは踵が先端より
    広い組だけ（**テーパーは向きを仮定しない** —— 実物は先端のほうが広かった。
    アルト 5 本・ソプラノ 5 本、2026-09-21 / 22 実測。狭まる側は半円まで届く）。
    判別式を 0 で下から押さえるのは、壁の外を覗く呼び出し（二分法の端など）で
    落ちないためだけで、**そこで返る値は形ではない**。
    """
    def a_at(z: float) -> float:
        t = min(max(z / length, 0.0), 1.0)
        return (tip_w + (heel_w - tip_w) * t) / 2.0

    if d <= 0.0:
        a_f = a_at(r)
        return 0.0, 0.0, r, a_f - r, a_f
    hw = tip_w / 2.0
    radius = (hw * hw + d * d) / (2.0 * d)
    s = (heel_w - tip_w) / (2.0 * length)
    b = hw - r
    disc = _nose_discriminant(radius, r, b, s)
    # 壁の内側で z_f ≤ 9.0（半円 ＝ 先端幅の上限の半分）。全長の下限 55 よりずっと
    # 手前なので、a(z) はここでは直線のまま。
    z_f = (b * b + 2.0 * radius * r - r * r) / ((radius - s * b)
                                                 + math.sqrt(max(disc, 0.0)))
    a = a_at(z_f)
    # アークとの接点は中心間を結ぶ線上、アーク中心から距離 R の所。
    z_t = radius - radius * (radius - z_f) / (radius - r)
    x_t = radius * (a - r) / (radius - r)
    return radius, z_t, z_f, x_t, a


def _nose(p: dict):
    return _nose_geometry(tip_curve_depth(p), p.get("tip_corner_r", 0.8),
                          p["tip_width"], p["heel_width"], p["reed_length"])


def nose_depth_limit(p: dict) -> float:
    """前縁アークが側面へ届く最も深い `tip_curve_depth` [mm] ＝ 先端カーブの壁。

    `_nose_discriminant` ≥ 0 を R について解くと R ≥ R* = c + √(c² − (1 + s²)r² + b²)
    （c = r(1 + s²) + s·b）。R = (hw² + d²)/(2d) は d ≤ hw で d について減るので、
    深さでは d ≤ hw² / (R* + √(R*² − hw²))。R* ≤ hw なら半円（d = hw）まで届く ——
    **踵が先端より広くない組は常にこちら**で、実物 10 本は全部そう（2026-09-21 / 22）。
    それより深い前縁は半円を越えて閉じない。

    壁が動くのは踵が広がる組だけ: 先端幅で増え、踵幅で減り、全長で増え、丸みで
    わずかに減る（丸み 0.3 → 2.0 で 0.01mm）。**帯の上限 2.8 はどの組でも内側**
    （最小 2.976 ＝ 先端 9.0 × 踵 18.0 × 全長 55 × 丸み 2.0、2026-09-23）。
    以前に試した「半幅 − 丸み」は、踵が大きく広がる組では壁より外（先端 9.0 ×
    踵 18.0 × 丸み 1.2 で 3.3 に対し 2.98）、ほかでは半円より手前で止めていた。
    """
    r = p.get("tip_corner_r", 0.8)
    hw = p["tip_width"] / 2.0
    s = (p["heel_width"] - p["tip_width"]) / (2.0 * p["reed_length"])
    b = hw - r
    c = r * (1.0 + s * s) + s * b
    r_star = c + math.sqrt(max(c * c - (1.0 + s * s) * r * r + b * b, 0.0))
    if r_star <= hw:
        return hw
    return hw * hw / (r_star + math.sqrt(r_star * r_star - hw * hw))


def nose_error(p: dict) -> str | None:
    """先端カーブが `nose_depth_limit` より深い組を説明つきで弾く。

    壁ちょうどは通す（1e-9 の遊びは `profiles.cavity_layout_error` と同じ ——
    相手の壁は二分法で解くので、返した端で計算し直すと最後の桁で断りうる）。
    """
    d = tip_curve_depth(p)
    if d <= 0.0:
        return None
    limit = nose_depth_limit(p)
    if d <= limit + 1e-9:
        return None
    if p["heel_width"] > p["tip_width"]:
        why = "踵へ広がる側面に前縁の円弧が届きません"
        how = "先端カーブを浅くするか、踵幅を狭く・先端幅を広く・全長を長くしてください"
    else:
        why = "前縁の円弧が半円を越えて閉じません"
        how = "先端カーブを浅くするか、先端幅を広くしてください"
    return (f"先端カーブ {d:.2f} mm では{why}: 先端幅 {p['tip_width']:.1f}・"
            f"踵幅 {p['heel_width']:.1f}・全長 {p['reed_length']:.1f} では "
            f"{limit:.2f} mm まで。{how}。")


#: 先端カーブの壁を動かす相手と、壁が立つ側（`nose_depth_limit` の単調性の向き）。
_NOSE_PARTNERS = (("tip_width", "lo"), ("heel_width", "hi"),
                  ("reed_length", "lo"), ("tip_corner_r", "hi"))


def nose_bounds(p: dict, static: dict) -> dict:
    """先端カーブの**相手で動く壁**（`reed.ReedComponent.param_bounds` が繋ぐ）。

    `static` は相手の `ParamSpec.bounds()`（`{key: (lo, hi)}`）。値は**スキーマが
    持ち主**なのでここには書かない（`profiles.outer_bounds` の刻みと同じ）。

    - `tip_curve_depth` の上限 ＝ `nose_depth_limit`
    - 相手（先端幅の下限・踵幅の上限・全長の下限・丸みの上限）は、**静的な端では
      届かないときだけ**返す（踵厚の前例と同じ）。帯の中のカーブ（≤ 2.8）では
      どの相手も静的な端まで届くので、既定では出ない。
    - **相手の壁は相手自身の値に依らない。** `ParamSet.apply` は頼まれた組から
      壁を引くので、踵幅 18 を頼まれた組で「いまの踵幅から」解くと、成立しない
      組から解くことになる。静的な緩い側の端から解き、そこでも届かなければ
      返さない（どの値へ丸めても嘘の壁 —— 理由は `nose_error` に言わせる）。

    `nose_depth_limit` はどの相手についても単調なので二分法で解く
    （`curve_depth_for_full_width_z` と同じ手）。判定は `nose_error` と同じ
    「d ≤ 壁 + 1e-9」なので、返す端は `params_error` の交差点そのもの。
    """
    widening = p["heel_width"] > p["tip_width"]
    out = {"tip_curve_depth": {
        "hi": nose_depth_limit(p),
        "hi_by": "先端幅・踵幅・リード全長・先端角の丸み" if widening else "先端幅"}}
    d = tip_curve_depth(p)
    if d <= 0.0:
        return out

    def holds(key: str, v: float) -> bool:
        return nose_depth_limit({**p, key: v}) + 1e-9 >= d

    for key, side in _NOSE_PARTNERS:
        lo, hi = static.get(key, (None, None))
        end, loose = (lo, hi) if side == "lo" else (hi, lo)
        if end is None or loose is None or holds(key, end) or not holds(key, loose):
            continue
        good, bad = loose, end
        for _ in range(60):
            mid = (good + bad) / 2.0
            if holds(key, mid):
                good = mid
            else:
                bad = mid
        out[key] = {side: good, f"{side}_by": "先端カーブ"}
    return out


def tip_full_width_z(p: dict) -> float:
    """リードが**実際に**全幅へ達する z ＝ フィレットが側面に接する所。

    `tip_curve_depth`（前縁アークの理論的な角）より 0.46〜0.59mm 後ろにある。
    差はフィレット半径ぶんの逃げで、意図した造形。適合カードがこの値を出す。

    **実物のリードで直定規が測るのはこちら**（「側面がまっすぐになる所」、
    2026-09-21 のアルト採寸で実測者に確認）。`tip_curve_depth` そのものは
    丸みを無視した見かけの角なので、ノギスでは当てられない。
    """
    return _nose(p)[2]


def curve_depth_for_full_width_z(p: dict, z_full: float) -> float:
    """全幅に達する z（実物で測れる量）から `tip_curve_depth` を逆算する。

    `tip_full_width_z` は `tip_curve_depth` について単調増加なので二分法で解く
    （`profiles.table_cut_end_z` と同じ手）。丸みだけで届く所（深さ 0 でも
    `tip_corner_r` ぶんは後ろにある）より手前なら 0 を返す。上端は先端カーブの壁
    `nose_depth_limit`（踵が広がらなければ先端半幅）—— **その先では単調ではない**
    （前縁アークが側面に届かず、`_nose_geometry` が返すのは形ではない値）。
    届かなければ上端を返し、範囲の外であることは呼び出し側（`ParamSet` の丸めの
    報告）に言わせる。
    """
    lo, hi = 0.0, nose_depth_limit(p)
    if tip_full_width_z({**p, "tip_curve_depth": lo}) >= z_full:
        return lo
    if tip_full_width_z({**p, "tip_curve_depth": hi}) <= z_full:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if tip_full_width_z({**p, "tip_curve_depth": mid}) < z_full:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def nose_half_width(p: dict) -> float:
    """先端の輪郭が全幅へ達したときの半幅（`tip_full_width_z` での側面）。

    **先端が広いリードではここが最大の半幅**で、そこから後ろは踵へ向かって
    狭まる。`tip_width/2` と同じではない —— 先端幅は z=0 へ延ばしたテーパーの
    値で、全幅の点は z_f ぶん後ろにある。
    """
    return _nose(p)[4]


def _outline_width(p: dict, z: float) -> float:
    """平面視輪郭の幅（下限を掛ける前）。`_nose_geometry` の 3 区間をそのまま評価する。

    フィレットの外側基準に 2 つの流儀があり、**前縁カーブの有無で使い分ける**:

    - カーブ有り: 中心を `a_f` に固定した**真円**。アークと厳密に接するので
      継ぎ目に段が出ない（局所テーパーに乗せると 1.6µm 下がって輪郭が一度細る）。
    - カーブ無し: 局所テーパーに乗せる（4-C.2 以前の式そのもの）。アークが無いので
      接する相手が無く、**旧形状をビット単位で据え置く**ほうを取る。

    フィレット区間を `w -= 2·(r − sqrt(…))` の形で書いてあるのも同じ理由で、
    `(w − 2r) + 2s` に整理すると丸めが 2 ULP ずれてビット一致が壊れる。
    """
    r = p.get("tip_corner_r", 0.8)
    radius, z_t, z_f, _x_t, a_f = _nose(p)
    if z < z_t:
        return 2.0 * math.sqrt(max(2.0 * radius * z - z * z, 0.0))
    # 2 で割って 2 倍は IEEE754 で厳密なので、旧式の `tip + (heel-tip)*t` に戻る。
    if z >= z_f:
        return 2.0 * taper_half_width(p, z)
    w = 2.0 * (a_f if radius > 0.0 else taper_half_width(p, z))
    return w - 2.0 * (r - math.sqrt(max(r * r - (z - z_f) ** 2, 0.0)))


def arc_end_x(p: dict) -> float:
    """前縁アークが終わって角のフィレットへ移る |x|。ここより外は意図した逃げ。"""
    return _nose(p)[3]


def half_width(p: dict, z: float) -> float:
    """z 位置の半幅（下限なし）。輪郭の逆関数を解くのに使う。"""
    return _outline_width(p, z) / 2.0


def width(p: dict, z: float) -> float:
    """z 位置の幅。下限 0.5mm は最先端の断面が点に潰れてロフトが縮退しないため。"""
    return max(_outline_width(p, z), 0.5)


def front_edge_z(p: dict, x: float) -> float:
    """幅方向 x で材料が始まる z ＝ 平面視輪郭 `half_width` の逆関数。

    **アークの閉形式では角のフィレットを取りこぼす。** 4-C.2 の実装はアークだけを
    逆に解いていたので、角の近くで実際の輪郭と 0.28〜0.56mm 食い違っていた
    （適合カードの許容差 0.3mm より大きい）。フィレット区間は閉形式にすると
    テーパーの傾きが混ざるので、`half_width` が単調な区間で二分法で解く
    （`profiles.table_cut_end_z` と同じ手）。

    **単調なのは先端から全幅の点 z_f までだけ。** 以前は区間を踵まで取って
    「幅は z で単調非減少」を仮定していた —— 旧既定は 3 サイズとも踵が 0.6 広く、
    その仮定が**一度も測られないまま**成り立っていた。実物のアルトは先端のほうが
    2.2mm 広く（2026-09-21）、入れると踵の端で幅が足りずに「角の位置 71.10mm」
    （＝リード全長）が返った。狭まるリードでは z_f から後ろにそれ以上広い所は
    無いので、区間を z_f で閉じる。
    """
    x = abs(x)
    if x <= 0.0:
        return 0.0
    radius, z_t, z_f, x_t, _a_f = _nose(p)
    if x <= x_t:
        if radius <= 0.0:
            return 0.0            # 前縁カーブなし＝ z=0 の直線
        return radius - math.sqrt(max(radius * radius - x * x, 0.0))
    widening = p["heel_width"] >= p["tip_width"]
    lo, hi = z_t, (p["reed_length"] if widening else z_f)
    if half_width(p, hi) < x:
        return p["reed_length"]   # この幅までリードが広がらない
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if half_width(p, mid) >= x:
            hi = mid
        else:
            lo = mid
    return hi


def tip_load_width(p: dict) -> float:
    """先端の実効幅 [mm]。**先端を「面」として見るときの幅はすべてこれ**。

    読み手は 2 つある: 硬さモデルの等分布荷重の幅（`reed_model._bending`）と、
    物理モデル音のリード流路の幅（`reed_model.reed_override` の `width_mm`）。
    後者は 4-C.2 で直し損ねていて、4-C.2b で `width(p, 0.0)` の z=0 漏れを
    直したときに露見した（流路が 0.5mm へ潰れて合成音が純正弦になった）。

    **`width(p, 0.0)` を使ってはいけない。** 前縁カーブを入れると z=0 は幅ゼロの
    尖点になり、荷重が 1/27 まで落ちて硬さ相当が上限 20.0 へ振り切れる（実測）。
    息圧が乗るのは「先端の幅」であって「z=0 の断面の幅」ではないので、テーパー前の
    先端幅から角の丸みだけを引く。カーブが 0 のときは `width(p, 0.0)` と厳密に一致する。
    """
    return max(p["tip_width"] - 2.0 * p.get("tip_corner_r", 0.8), 0.5)


def _profile_shape(kind: str, t: float) -> float:
    """バンプ形状。t∈[0,1]（0=先端, 1=バーク端）→ 厚み上昇率 u∈[0,1]。"""
    t = min(max(t, 0.0), 1.0)
    if kind == "linear":
        return t
    if kind == "concave":
        # アメリカンカット風: 先端側が薄いまま伸び、後半で急に厚くなる
        return t ** 1.8
    return t ** 1.35  # parabolic（既定・フレンチカット寄り）


def heel_edge_thickness(p: dict) -> float:
    """踵の**側端**の厚み [mm]。キーが無ければ中央厚と同じ＝上面が平ら。"""
    return p.get("heel_edge_thickness", p["heel_thickness"])


#: 踵の中央厚 − 側端厚 の下限 [mm]（カマボコの最小の盛り上がり）。**新しい数字では
#: ない** —— 以前は `heel_edge_thickness` の上限 1.6 と `heel_thickness` の下限 1.8
#: の差として 2 本の直値に分けて持っていた（`reed._specs` の旧注記）。実物の側端厚
#: 1.65（2026-09-21、アルト #1）がその上限を越えたので、関係のほうを持つ
#: （`reed.ReedComponent.param_bounds`）。
MIN_CROWN_MM = 0.2


def cane_radius(p: dict) -> float:
    """踵の幅・中央厚・側端厚を通す円弧の半径 ＝ 元のケーン管の外半径 [mm]。

    リードは竹のような円筒（ケーン）から D 形のブランクを切り出して作るので、
    削っていない上面にはその円筒の外周が残る。中央厚と踵幅は規格値なので、
    側端厚を 1 つ測れば円が決まる。0 を返したら円弧なし（上面が平ら）。
    """
    d = p["heel_thickness"] - heel_edge_thickness(p)
    if d <= 0.0:
        return 0.0
    return ((p["heel_width"] / 2.0) ** 2 + d * d) / (2.0 * d)


def cane_top(p: dict, x: float) -> float:
    """素材（ケーン）の上面の高さ [mm]。**z に依らない** —— 管はまっすぐだから。"""
    r = cane_radius(p)
    if r <= 0.0:
        return p["heel_thickness"]
    return p["heel_thickness"] - r + math.sqrt(max(r * r - x * x, 0.0))


#: ケーンの円弧が側端でどれだけ厚みを残していなければならないか [mm]。
#: ここを下回ると断面の側面が潰れ、さらに進むと円弧がテーブル面より下へ潜る。
_MIN_EDGE_THICKNESS = 0.05


def bark_thickness(p: dict) -> float:
    """ファイルドで剥がす表皮（バーク）の厚み [mm]。

    **実測で決まる量ではない** —— 印刷品に本物の表皮は無いので、これは「表皮を
    剥がしたように見える段の深さ」。実物のケーンの表皮も 0.1〜0.3mm 程度で、
    リードの厚みに対して十分小さい。踵厚に比例させて 0.25mm で頭打ちにする。
    """
    return min(0.25, p["heel_thickness"] * 0.12)


def cane_layout_error(p: dict) -> str | None:
    """ブランクが元のケーン管に収まらない組合せを説明つきで弾く。

    上面はケーンの円弧なので、リードが管より広いと**円弧がテーブル面より下へ潜って
    断面が裏返る**（実測: tip_width 18.0 / heel_width 14.0 で断面の最小 y = −0.45、
    heel_width 9.0 で −3.48。後者はソリッドが `is_valid=False` になった）。

    **ファイルドは表皮ぶんの余裕も要る。** 表皮を落とした面がテーブル面より下へ
    行くと同じことが起きる（実測: 先端幅 > 踵幅 で管の限界近くの 252 通りが
    最小 y = −0.16 になった。**掃引は 1 パラメータの端値しか振らないので届かない**）。
    これは「削る材料が残っていない」という物理そのものなので、アンファイルドまで
    狭めずに `file_cut` で場合分けする。

    **2 つ以上のパラメータの関係**なので `ParamSpec` の範囲では表せない
    （幅を狭くしても側端厚を上げても成立する）。`Component.params_error` へ回す。
    """
    r = cane_radius(p)
    if r <= 0.0:
        return None                     # 円弧なし（上面が平ら）＝どんな幅でも収まる
    keep = _MIN_EDGE_THICKNESS
    if p.get("file_cut") == "filed":
        keep += bark_thickness(p)
    h = p["heel_thickness"] - keep
    limit = math.sqrt(max(h * (2.0 * r - h), 0.0))   # 円弧が余裕高さまで来る x
    hw = max(p["tip_width"], p["heel_width"]) / 2.0
    if hw <= limit:
        return None
    extra = ("（ファイルドは表皮 %.2f mm を落とすぶん余分に要る）"
             % bark_thickness(p)) if p.get("file_cut") == "filed" else ""
    return (f"リードが元のケーン管に収まりません{extra}: 最大半幅 {hw:.1f} mm に対し、"
            f"外径 φ{2.0 * r:.1f} の管では半幅 {limit:.1f} mm までしか厚みが"
            f"残りません。踵の側端厚（{heel_edge_thickness(p):.2f}）を上げて円弧を"
            f"浅くするか、幅を狭くしてください。")


def thickness(p: dict, z: float, x: float = 0.0) -> float:
    """厚み ＝ **削り面と素材上面の低いほう**（カマボコ断面）。

    実物の作りそのもの: D 形のブランクを取ってからヴァンプを削るので、削っていない
    所はケーンの円弧が残り、削った所は削り面が勝つ。円弧が勝ち始めるのは
    ヴァンプの後ろ半分（実測 z ≈ 14.8 / 16.8 / 17.5）で、先端側は削り面が勝つ。

    **ファイルドは素材上面を 1 段下げる**（表皮を一直線の位置まで剥がす加工）。
    残るのは溝ではなく、削り面が下がりきる曲線と直線の間の**三日月形の帯**
    ＝ 解説図の「表皮を削った部分」。溝ではないので、帯の前側に段は出ない。

    ここに入れるのが重要で、**ブーリアンで削ると法則の外になる** —— 4-C.2b まで
    ファイルドは切除ソリッドで作っていたので、`blade_volume_mm3`（BOM・印刷カード）
    も `second_moment`（硬さ）もファイルドを 1 ビットも見ていなかった
    （実ソリッドは −7.4〜−8.5mm³ 減るのに法則側の差は +0.0 だった）。
    """
    top = cane_top(p, x)
    if p.get("file_cut") == "filed" and z < vamp_start_z(p):
        top -= bark_thickness(p)
    return min(_vamp_thickness(p, z, x), top)


def _vamp_thickness(p: dict, z: float, x: float = 0.0) -> float:
    """削り面（ヴァンプ）の高さ。x=0 が中央（背骨）、|x|=w/2 が側端。

    `tip_thickness` / `heel_thickness` は**中央の厚み**を指す（ゲージで測る位置）。
    幅方向は中央を頂点に側端へ向かって薄くなり、その比が `side_rail_thin`。
    `spine_ratio` は薄化の指数で、大きいほど中央の平坦部（背骨）が広くなる。
    薄化はバーク端でゼロに収束させる（削り面はそこで素材の上面に戻る）。

    **これは削り面だけの高さ**で、実際の厚みではない。バーク側は素材の円弧が
    残るので、外へ出す厚みは `thickness()`（円弧との min）を使うこと。
    """
    zv = vamp_start_z(p)
    if z >= zv:
        return p["heel_thickness"]  # 削っていない＝素材の高さまで戻る
    u = _profile_shape(p.get("profile_curve", "parabolic"), z / zv)
    t_center = p["tip_thickness"] + (p["heel_thickness"] - p["tip_thickness"]) * u
    hw = width(p, z) / 2.0
    q = min(abs(x) / hw, 1.0) if hw > 0 else 0.0
    rail = p.get("side_rail_thin", 0.55)
    spine = p.get("spine_ratio", 1.15)
    blend = 1.0 - u  # 先端で最大、バーク端で 0
    return t_center * (1.0 - (1.0 - rail) * blend * q ** (2.0 * spine))


def filed_band_start_z(p: dict, x: float) -> float:
    """幅位置 x で「表皮を削った部分」が始まる z（帯の前縁）。

    削り面が表皮を落とした面より低くなる所。**新しい法則ではなく、既存の 2 本の
    曲線の交点**なので、帯の形はパラメータではなく幾何から出てくる。
    中央でいちばん後ろ（帯が細い）、側端でいちばん前（帯が太い）＝ 三日月。
    """
    zv = vamp_start_z(p)
    target = cane_top(p, x) - bark_thickness(p)
    lo, hi = 0.0, zv
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _vamp_thickness(p, mid, x) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def edge_thickness(p: dict, z: float) -> float:
    """側端の厚み（角丸半径の上限に使う）。"""
    return thickness(p, z, width(p, z) / 2.0)


# ---------------------------------------------------------------- ロフト断面

_STATION_TS = [0.0, 0.02, 0.05, 0.10, 0.18, 0.28, 0.40, 0.55, 0.72, 0.88, 1.0]

#: 先端の輪郭に置くステーションの数（前縁アーク側 / 角のフィレット側）。
#: **`tip_curve_depth` に対する比では刻まない** —— 半幅は z の平方根で立ち上がるので
#: 等間隔だと最先端が粗くなる。2 つの円をそれぞれ**等角**で刻めば、弦の逃げが
#: R·Δθ²/8 で一様に押さえられる（実測: 輪郭の垂直ずれが 0.5mm → 最先端の幅の
#: 下限 0.25mm ぶんだけに減る）。
_NOSE_ARC_STEPS = 6
_NOSE_FILLET_STEPS = 4

#: 断面上面のサンプル位置（x / 半幅）。+1 → −1 の順で、底辺 2 点と合わせて
#: 反時計回りに一周する。**点数は全断面で一定**（`loft_sections` のルールドロフトは
#: 頂点対応ではなくパラメータ対応で面を張るため、断面ごとに点数が変わると面がねじれる）。
#: **奇数個にして q=0 を必ず含める** —— 中央は背骨の稜線（断面の最大高さ）なので、
#: ここを跨いでサンプルすると稜線が全長にわたって平らな面になる。
#: 19 点で断面積の誤差は最悪 0.10%（10 点だと 0.40%、27 点にしても 0.06% までしか
#: 改善しない。端に寄せた分布にしても差は 0.02% 以下だったので等間隔でよい）。
_TOP_QS = [1.0 - 2.0 * i / 18.0 for i in range(19)]


def nose_station_zs(p: dict) -> list[float]:
    """先端の輪郭に沿って置く z 列（前縁アーク → 角のフィレット）。

    **前縁カーブが無いときは何も足さない。** 4-C.2 以前の形（`tip_curve_depth = 0`）
    はステーションごと据え置き、新機能が既定形状を 1 ビットも動かさないようにする。
    """
    radius, z_t, z_f, x_t, a_f = _nose(p)
    if radius <= 0.0:
        return []
    r = p.get("tip_corner_r", 0.8)
    th = math.asin(min(x_t / radius, 1.0))
    zs = [radius * (1.0 - math.cos(th * i / _NOSE_ARC_STEPS))
          for i in range(1, _NOSE_ARC_STEPS + 1)]
    a0 = math.atan2(z_t - z_f, x_t - (a_f - r))    # フィレット始点の角（負）
    zs += [z_f + r * math.sin(a0 * (1.0 - i / _NOSE_FILLET_STEPS))
           for i in range(1, _NOSE_FILLET_STEPS + 1)]
    return zs


def station_zs(p: dict) -> list[float]:
    """断面を置く z 列。先端側を密にし、バーク端と踵を必ず含める。"""
    zv = vamp_start_z(p)
    zs = [t * zv for t in _STATION_TS]
    zs += nose_station_zs(p)
    zs.append(zv + 0.01)          # バーク段差（削り終わりを明示）
    if p.get("file_cut") == "filed":
        # ファイルドの一直線。**刻みを置かないと段が斜めになる** —— 手前の刻みは
        # 0.88·zv なので 3.8mm かけて落ち、法則の体積が −5% と出る（実測）。
        zs.append(zv - 0.01)
    zs.append(p["reed_length"])
    return sorted(set(round(z, 4) for z in zs))


def sections(p: dict) -> list[dict]:
    """`loft_sections` 用の断面列。底面は y=0 で厳密に平坦。

    上面は `thickness(p, z, x)` をそのまま点で追う。**近似形（角丸長方形など）に
    置き換えない** —— 同じ法則から BOM の体積も断面二次モーメントも出しているので、
    形だけ別式にすると印刷される物と数値が食い違う。旧実装の角丸長方形は実際に
    先端断面で 15% 太く（alto z=0 で 4.706 vs 法則 4.082 mm²）、全体で +1.6% あった。
    """
    out: list[dict] = []
    for z in station_zs(p):
        hw = width(p, z) / 2.0
        pts = [(-hw, 0.0), (hw, 0.0)]                       # 底辺（テーブル面）
        pts += [(q * hw, thickness(p, z, q * hw)) for q in _TOP_QS]
        out.append({"z": z, "pts": pts})
    return out


def blade_volume_mm3(p: dict) -> float:
    """ブレード体積（断面積の台形積分）。BOM の材料量・質量推定に使う。"""
    zs = station_zs(p)
    vol = 0.0
    for a, b in zip(zs, zs[1:]):
        vol += (_area(p, a) + _area(p, b)) / 2.0 * (b - a)
    return vol


def _area(p: dict, z: float, samples: int = 12) -> float:
    """幅方向に厚みを積分した断面積。"""
    w = width(p, z)
    acc = 0.0
    for i in range(samples):
        x = -w / 2.0 + w * (i + 0.5) / samples
        acc += thickness(p, z, x)
    return acc * (w / samples)


# ---------------------------------------------------------------- 剛性（音響モデル用）

def second_moment(p: dict, z: float, samples: int = 12) -> float:
    """断面二次モーメント I [mm^4]（曲げ中立軸まわり）。

    厚みが幅方向に変わるため、幅を短冊に分けて平行軸の定理で合成する
    （各短冊は底面 y=0 の矩形だが図心の高さ h/2 が異なるため単純加算できない）。
    """
    w = width(p, z)
    dx = w / samples
    strips = []
    for i in range(samples):
        x = -w / 2.0 + w * (i + 0.5) / samples
        h = thickness(p, z, x)
        strips.append((h, dx))
    area = sum(h * b for h, b in strips)
    if area <= 0:
        return 0.0
    yc = sum(h * b * (h / 2.0) for h, b in strips) / area   # 図心の y
    inertia = 0.0
    for h, b in strips:
        inertia += b * h ** 3 / 12.0 + (h * b) * (h / 2.0 - yc) ** 2
    return inertia


def cross_area(p: dict, z: float) -> float:
    return _area(p, z)


# ---------------------------------------------------------------- 影響領域（UIハイライト用）

def param_regions(p: dict) -> dict:
    """各パラメータが影響するモデル領域 {key: {z0, z1, side, label}}。

    リードは全体が y>=0 にあるため side は "top" / "all" のみ使う
    （Viewer3D は y の符号で上下を判定する）。
    """
    length = p["reed_length"]
    zv = vamp_start_z(p)

    def r(z0, z1, side, label):
        return {"z0": round(max(z0, 0.0), 2), "z1": round(min(z1, length), 2),
                "side": side, "label": label}

    return {
        "reed_length":    r(0.0, length, "all", "リード全体"),
        "tip_width":      r(0.0, 0.15 * length, "all", "先端（ティップ）"),
        "heel_width":     r(zv, length, "all", "踵（ヒール）"),
        "tip_thickness":  r(0.0, 0.12 * zv, "top", "先端の削り"),
        "heel_thickness": r(zv, length, "all", "バーク（未削部）"),
        "heel_edge_thickness": r(zv, length, "top", "ケーンの円弧（カマボコ）"),
        # 角の丸みまで含めた**実際の**先端区間（`tip_full_width_z` はフィレットが
        # 側面に接する所で、`tip_curve_depth` より 0.46〜0.59mm 後ろにある）。
        "tip_curve_depth": r(0.0, max(tip_full_width_z(p), 0.5), "all", "前縁カーブ"),
        "vamp_length":    r(0.0, zv, "top", "ヴァンプ（削り面）"),
        "profile_curve":  r(0.0, zv, "top", "ヴァンプ（削り面）"),
        "spine_ratio":    r(0.0, zv, "top", "中央の背骨"),
        "side_rail_thin": r(0.0, zv, "top", "サイドレール（両脇）"),
        "tip_corner_r":   r(0.0, 0.10 * zv, "top", "先端角の丸み"),
        # 帯の実領域（側端でいちばん前まで伸びる）。決め打ちの ±数 mm ではない。
        "file_cut":       r(filed_band_start_z(p, p["heel_width"] / 2.0), zv,
                            "top", "表皮を削った部分（ファイルド）"),
        # material / min_layer は形状に影響しない → 領域なし
    }


# ---------------------------------------------------------------- 断面SVG用

def side_profile_polylines(p: dict, samples: int = 100) -> dict:
    """厚みプロファイル図のポリライン群（SVG描画用、単位mm）。

    テーブル面（y=0）を基準に、中央（背骨）と側端の厚み曲線を重ねて示す。
    """
    length = p["reed_length"]
    zs = [length * i / (samples - 1) for i in range(samples)]
    return {
        "table": [(0.0, 0.0), (length, 0.0)],
        "center": [(z, thickness(p, z, 0.0)) for z in zs],
        "edge": [(z, edge_thickness(p, z)) for z in zs],
        "plan": [(z, width(p, z) / 2.0) for z in zs],
        "vamp_start": vamp_start_z(p),
    }
