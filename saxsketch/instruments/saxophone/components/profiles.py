"""マウスピースの断面プロファイル（純数学・OCCT非依存）。

座標系:
  Z: ボア軸。z=0 がティップ（先端）、z=L がシャンク端。
  Y: +Y がビーク（上面）、-Y がテーブル（リード側）。
  X: 幅方向。

構成式は実在マウスピース（WindyCity Tenor .100" Long Shank）を
ボア軸基準で実測して起こしたもの。実測で判明した3つの構造がこのモジュールの骨格:

  1. **テーブルはボア軸に平行ではなく、約 4.2° 傾いた平面**（実測の平面度 rms 0.035mm）。
     最大径の位置（リード踵 = `heel_z`）で胴の下面に接し、そこで自然に消える。
     旧実装は `table_y = -0.40·body_dia` の定数平面で、これが実物と最も食い違っていた。
  2. **外形はボア軸まわりの真円の回転体**（円フィット rms 0.01〜0.2mm、中心は軸上 ±0.08mm）。
     見かけの「卵形」はテーブルカットが下側を削った結果で、胴そのものは真円。
  3. **ビークは直線ランプ＋円筒面**。頂線はティップからバイトポイントまで完全な直線
     （実測 18.0°、4mm 刻みで ±0.02mm）、横断面は半径 ≈0.81·body_dia の円弧。
     0.44〜0.54·heel_z で胴の丸みへブレンドして消える。

したがって「リード側は傾いたテーブル面基準、ボア側はボア軸基準」で全量を定義する。
内部空洞（バッフル天井）も**ボア軸に平行な平面**から始まり、smoothstep でボア天井へ
立ち上がる（実測とほぼ一致）。リード面から見た天井高さが z とともに増えるのは、
天井が上がるからではなくテーブルが下がるためである。

断面はスーパー楕円 |2x/w|^nx + |2(y-yc)/h|^ny = 1 で表現する
（n=2 かつ w=h で真円、n が大きいほど角形）。ロフトが安定し自己交差しない。
**上半分だけ別の x 指数**（`nx_top`）を使い、実測どおり天井を横方向にアーチさせる。
ny>1 なら上下どちらの半分も X=±1 で接線が垂直なので、赤道は G1 のまま繋がる。
"""
from __future__ import annotations

import functools
import math
import threading


# ---------------------------------------------------------------- 同一 p のあいだのキャッシュ
#
# このモジュールは「p と z を受け取って数を返す」小さな関数の集まりで、そのうち
# **z に依存しないもの**（`heel_z` など）が z のサンプルごとに呼び直されている。
# 断面 1 枚（6 曲線 × 245 点）で `heel_z` が 8,357 回、`_pchip` が 8,285 回。
# ドラッグ中は毎フレームこれが走るので、そのぶんがそのまま応答の遅れになる。
#
# キャッシュが効くのは **`params_scope()` に渡した dict オブジェクトと `is` で
# 同一のときだけ**。`{**p, key: v}` で作った別オブジェクト（`sensitivity()` の
# 摂動や `_roof_at()`）は自動的に素通りするので、摂動計算が元の値を拾う事故が
# 構造的に起きない。値の同一性ではなくオブジェクトの同一性で見ているのが要点。

_SCOPE = threading.local()


class _ParamScope:
    __slots__ = ("p", "cache")

    def __init__(self, p: dict) -> None:
        self.p = p
        self.cache: dict = {}


class params_scope:
    """`p` を変えないと分かっている区間で、`p` だけに依存する値を使い回す。

    入れ子にしてよい（内側が優先され、抜けると外側へ戻る）。区間の中で `p` を
    書き換えてはいけない — 書き換えるなら新しい dict を作ること（そうすれば
    `is` 判定で自動的にキャッシュ外になる）。
    """

    __slots__ = ("_scope", "_prev")

    def __init__(self, p: dict) -> None:
        self._scope = _ParamScope(p)

    def __enter__(self) -> "params_scope":
        prev = getattr(_SCOPE, "cur", None)
        self._prev = prev
        # 同じ `p` で入れ子になったら外側のキャッシュをそのまま使う。入口を
        # 二重に張っても（component.section → section_curves）損をしないように。
        if prev is not None and prev.p is self._scope.p:
            self._scope = prev
        _SCOPE.cur = self._scope
        return self

    def __exit__(self, *exc) -> None:
        _SCOPE.cur = self._prev


def _pcached(fn):
    """`p` を第1引数に取る純関数の結果を、スコープ中の同一 `p` についてだけ覚える。"""
    name = fn.__name__

    @functools.wraps(fn)
    def wrap(p, *args):
        sc = getattr(_SCOPE, "cur", None)
        if sc is None or sc.p is not p:
            return fn(p, *args)
        key = (name, args)
        hit = sc.cache.get(key, _MISS)
        if hit is _MISS:
            hit = sc.cache[key] = fn(p, *args)
        return hit

    wrap.__wrapped__ = fn      # キャッシュ無しの実体（テストが素の値と突き合わせる）
    return wrap


def _scoped(fn):
    """第1引数の `p` で `params_scope` を張ってから実行する（同じ `p` を何度も
    標本化する入口用）。返り値そのものはキャッシュしない — list/dict を返す
    関数に付けるので、呼び出し側が書き換えても安全なままにしておく。"""
    @functools.wraps(fn)
    def wrap(p, *args, **kw):
        with params_scope(p):
            return fn(p, *args, **kw)
    return wrap


_MISS = object()


# ---------------------------------------------------------------- 補間ユーティリティ

def _smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _soft_min(a: float, b: float, k: float = 0.35) -> float:
    """C∞ な最小値（常に `min(a, b)` 以下、最大 k/2 だけ下）。

    形状の頭打ちに素の `min()` を使うと、**発動が切り替わる z で傾きが折れる**。
    その折れは面の上に稜線として残り、実物には無い棚・段差になる（旧実装の
    `chord_lim` / `_contain` がこれだった）。`min` 以下を返すので外殻への
    封じ込めは保証したまま、角だけが取れる。
    """
    return 0.5 * (a + b - math.sqrt((a - b) ** 2 + k * k))


def _soft_max(a: float, b: float, k: float = 0.35) -> float:
    """`_soft_min` の対。常に `max(a, b)` 以上を返す。"""
    return -_soft_min(-a, -b, k)


def _pchip_table(pts: list[tuple[float, float]]) -> tuple[list, list, list, list]:
    """Fritsch–Carlson の傾き `m` を含む係数表。制御点だけで決まるので使い回せる。

    **x が重なった表は名指しで弾く。** 区間幅 `h[i]` で割るので、重なると
    `ZeroDivisionError` がこの関数の奥から出るだけで、**どの表が壊れたのか
    呼び出し側から分からない**。このモジュールには `s_we` / `s_th` / `s_ch` から
    **動的に組む表が 6 か所**あり（`cavity_floor_y` / `_floor_limit` /
    `_section_exponents` ×2 / `_chamber_weight` / `_ratio_scale`）、どれも設計値の
    組み合わせ次第で節点が重なりうる。実際 `_floor_limit` が `s_we ≥ 0.94` で
    踏んでいて、`window_end_z` の `zb − 4.0` がそれを覆う蓋になっていた。
    """
    n = len(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    for i, hi in enumerate(h):
        if hi <= 0.0:
            raise ValueError(
                f"PCHIP の制御点 x が単調増加ではありません: "
                f"pts[{i}]={pts[i]} と pts[{i + 1}]={pts[i + 1]} で "
                f"x が {xs[i]!r} → {xs[i + 1]!r}（幅 {hi!r}）。"
                f"表全体: {pts}")
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0.0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    for i in range(n - 1):
        if d[i] == 0.0:
            m[i] = m[i + 1] = 0.0
    return xs, ys, h, m


#: モジュール定数の表（下の `_register_static_pchip()` が import 時に一度だけ登録）。
#: `id()` キーだが**表そのものへの参照も持つ**ので id が使い回されてすり替わることは
#: なく、登録された表しか入らないので伸びもしない。20 点の表を毎回ハッシュせずに済む。
_PCHIP_STATIC: dict[int, tuple] = {}
#: その場で組み立てる 4〜5 点の表用。同じ `p` の中では毎回同じ表になるので、
#: 値をキーにしても 1 回目以降は全部ヒットする。
_PCHIP_BY_VALUE: dict[tuple, tuple] = {}


def _pchip(pts: list[tuple[float, float]], x: float) -> float:
    """単調保存の3次エルミート補間（Fritsch–Carlson）。

    外形プロファイルを制御点から滑らかに起こすために使う。単調性を保存するので、
    制御点が単調増加なら生成される回転体も単調で、ロフトが自己交差しない。

    係数表（`_pchip_table`）は制御点だけで決まるのでキャッシュする。断面 1 枚で
    8,285 回呼ばれ、毎回この表を作り直していた。**補間の演算そのものは変えて
    いない**ので、同じ入力には同じ浮動小数が返る。
    """
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]

    ent = _PCHIP_STATIC.get(id(pts))
    if ent is not None and ent[0] is pts:
        xs, ys, h, m = ent[1]
    else:
        vkey = tuple(pts)
        tab = _PCHIP_BY_VALUE.get(vkey)
        if tab is None:
            tab = _pchip_table(pts)
            if len(_PCHIP_BY_VALUE) > 512:
                _PCHIP_BY_VALUE.clear()
            _PCHIP_BY_VALUE[vkey] = tab
        xs, ys, h, m = tab

    k = 0
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            k = i
            break
    t = (x - xs[k]) / h[k]
    t2, t3 = t * t, t * t * t
    return (ys[k] * (2 * t3 - 3 * t2 + 1) + h[k] * m[k] * (t3 - 2 * t2 + t)
            + ys[k + 1] * (-2 * t3 + 3 * t2) + h[k] * m[k + 1] * (t3 - t2))


# ---------------------------------------------------------------- 軸方向のランドマーク

#: シャンク肩（最大径→シャンク径）の長さの既定比。テナー実測 11mm / heel_z 79mm。
#:
#: サイズ間で移る保証は無い。ソプラノ実測（全長 71.4 / 最大径がシャンク端から
#: 14.3mm）はこの比と `shank_length` の組でしか表せず、比が 0.139 なら
#: `shank_length` は 6.4mm、段差が 11mm なら比は 0.058 になる。どちらでも
#: `heel_z` は 57.1mm で同じなので音程には効かない（実測 0.00 セント）が、
#: 胴の外形と `table_cut_end_z` は変わる。テンプレートの `shoulder_ratio` で
#: サイズごとに持てるようにしてある。
_SHOULDER_RATIO = 0.139


def shank_length(p: dict) -> float:
    """シャンク平行部の長さ。ロングシャンク/標準シャンクの作り分けに使う。"""
    return p.get("shank_length", 17.5)


def shoulder_ratio(p: dict) -> float:
    return p.get("shoulder_ratio", _SHOULDER_RATIO)


def shank_radius(p: dict) -> float:
    return p.get("shank_dia", 0.747 * p["body_dia"]) / 2.0


#: 最大径の位置の下限（全長に対する比）。**これは床であって設計値ではない** ——
#: シャンク平行部と肩が全長を食い尽くすと踵が原点へ寄って形が潰れるので、
#: そこで止めている。**止めた先では `heel_z` が凍る**（`shank_length` も
#: `shoulder_ratio` も動かしても形が 1 ビットも変わらない）ので、
#: `outer_layout_error` が床に当たる組を弾き、スライダの `hard_max` はその
#: 手前に置いてある（Phase B-4a で実測。黙ったクランプの 8 例目だった）。
HEEL_FLOOR_RATIO = 0.30


def heel_raw(p: dict) -> float:
    """床を掛ける**前**の最大径位置。`heel_z` との差が「床に当たっているか」。

    肩比が −1 以下だと分母が 0 以下になる。掃引（B-4a）は `shoulder_ratio`
    を下へ歩いて **−1 ちょうどで素の `ZeroDivisionError`** を踏んだ
    （割り算が潰れる型の 7 つ目）。ここでは `-inf` を返して
    `outer_layout_error` に理由を言わせる —— 例外の出所が分からないまま
    上がるのがいちばん悪い。
    """
    denom = 1.0 + shoulder_ratio(p)
    if denom <= 0.0:
        return float("-inf")
    return (p["overall_length"] - shank_length(p)) / denom


def heel_floor(p: dict) -> float:
    return HEEL_FLOOR_RATIO * p["overall_length"]


def shank_length_at_heel_floor(p: dict) -> float:
    """`shank_length` がこれを超えると `heel_z` が床で凍る（他は既定のまま）。"""
    return p["overall_length"] * (1.0 - HEEL_FLOOR_RATIO
                                  * (1.0 + shoulder_ratio(p)))


def shoulder_ratio_at_heel_floor(p: dict) -> float:
    """`shoulder_ratio` がこれを超えると `heel_z` が床で凍る（他は既定のまま）。"""
    length = p["overall_length"]
    return (length - shank_length(p)) / (HEEL_FLOOR_RATIO * length) - 1.0


def heel_z(p: dict) -> float:
    """最大径の位置 = リード踵 = テーブル平面が胴に接する z。

    ここから後ろは肩テーパ→シャンク平行部。全長からシャンク構成を引いて決めるので、
    `shank_length` を変えても踵の位置とテーブル長が正しく追従する。

    床（`HEEL_FLOOR_RATIO`）は**もう届かない**はずの守り ——`outer_layout_error`
    が床に当たる組を先に弾く。残してあるのは、部分的な dict で呼ばれる経路
    （`.get` の既定に頼る呼び出し）が素の負値や 0 除算に落ちないようにするため。
    """
    return max(heel_raw(p), heel_floor(p))


def shoulder_length(p: dict) -> float:
    return shoulder_ratio(p) * heel_z(p)


def shank_start_z(p: dict) -> float:
    """シャンク平行部（外径一定）が始まる z。肩テーパの終わり。"""
    return min(heel_z(p) + shoulder_length(p), p["overall_length"])


def bore_radius(p: dict) -> float:
    return p["bore_dia"] / 2.0


def bore_start_z(p: dict) -> float:
    return p["overall_length"] - p["bore_length"]


def ligature_seat_range(p: dict) -> tuple[float, float]:
    """リガチャーが座る z 範囲。最大径付近の帯。

    実物は「最大径に向かって単調に太る」形なので、旧実装のような r/rb==1.0 の
    平坦区間は存在しない。踵（最大径）から前方へリガチャー幅ぶん取った帯を座とする。

    **この「単調に太る」に座の定義が乗っている。** `body_waist` を強く負へ振ると
    胴の中ほど（u≈0.23）に凹みが出て前提が崩れ、座は最大径ではない所に置かれる
    ——`heel_z` は軸方向の式なので何も言わない。Phase B-4b でそこをスライダの壁に
    した（`body_waist_limits`）。
    """
    heel = heel_z(p)
    return heel - _SEAT_LENGTH_RATIO * heel, heel


#: リガチャー座の長さ（踵からの比率）。実測のリガチャー帯 ≈18mm / heel 79mm。
_SEAT_LENGTH_RATIO = 0.23


# ---------------------------------------------------------------- 外形（真円回転体）

#: 胴の外形プロファイル (u = z/heel_z, r/r_max)。実測値そのもの。
#: u=0 の 0.346 は「テーブル面＋ティップ開きに胴の下端がちょうど接する」値で、
#: これによりソリッドのティップが z=0 に立つ（先端は円錐ではなく丸ノーズ）。
_BODY_PROFILE = [
    (0.0000, 0.3457),
    (0.0051, 0.3887),
    (0.0127, 0.5092),
    (0.0253, 0.6343),
    (0.0506, 0.6965),
    (0.0759, 0.7189),
    (0.1266, 0.7525),
    (0.2025, 0.7962),
    (0.3038, 0.8366),
    (0.4051, 0.8612),
    (0.5063, 0.8852),
    (0.6076, 0.9091),
    (0.7089, 0.9336),
    (0.8101, 0.9569),
    (0.9114, 0.9798),
    (1.0000, 1.0000),
]

#: シャンク肩の形 (s = 肩内の進行度, (r - r_shank)/(r_max - r_shank))。実測値。
_SHOULDER_PROFILE = [
    (0.000, 1.000),
    (0.091, 0.886),
    (0.182, 0.706),
    (0.273, 0.568),
    (0.364, 0.419),
    (0.455, 0.311),
    (0.636, 0.145),
    (0.818, 0.053),
    (1.000, 0.000),
]


#: 胴の膨らみの形。両端で厳密に 0 なので、ティップ（u=0）と最大径（u=1）を動かさない。
def _waist_bump(u: float) -> float:
    return math.sin(math.pi * min(max(u, 0.0), 1.0))


def body_waist(p: dict) -> float:
    return p.get("body_waist", 0.0)


def shoulder_fullness(p: dict) -> float:
    return p.get("shoulder_fullness", 0.0)


def body_shape(p: dict, u: float) -> float:
    """胴プロファイル r/r_max（u = z/heel_z）。実測形に両端 0 の膨らみを掛ける。

    掛け算にするのは端点を**厳密に**保つため。実測形の 0.3457（u=0）は
    「ティップがちょうど z=0 に立つ」値で、1.0（u=1）は最大径そのもの。
    どちらかが動くとテーブル位置かリガチャー座が動く。
    """
    return _pchip(_BODY_PROFILE, u) * (1.0 + body_waist(p) * _waist_bump(u))


def shoulder_shape(p: dict, s: float) -> float:
    """肩プロファイル (r − r_shank)/(r_max − r_shank)。実測形と直線のブレンド。

    端点 (0, 1) と (1, 0) はブレンド率に依らず保たれる（直線もそこを通るため）。
    k=+1 で母線が**厳密な直線**＝最大径からシャンクまでが円錐になる。
    """
    k = shoulder_fullness(p)
    return (1.0 - k) * _pchip(_SHOULDER_PROFILE, s) + k * (1.0 - s)


def shoulder_is_straight(p: dict) -> bool:
    """肩の母線が厳密な直線か（STEP で円錐面 1 枚にできる）。"""
    return abs(shoulder_fullness(p) - 1.0) < 1e-12


def outer_radius_nominal(p: dict, z: float) -> float:
    """胴の外半径（ティップ面取りを掛ける前）。ボア軸まわりの真円。

    テーブル位置やビーク稜線の**基準**はこちらで取る。面取りは仕上げの削り代で、
    基準を動かしてはいけない（`outer_radius` を使うと z=0 で 0.7mm ぶん
    テーブルごと下がってティップ開きが狂う）。

    **最大径（`heel_z`）は頂点**で、前後は別々のプロファイルが持つ。形を歪める
    パラメータもこの境を跨がない —— `body_waist` は z < heel_z だけ、
    `shoulder_fullness` は z > heel_z だけを動かし、どちらも境の半径 `r_max` を
    動かさない。動かすのは `body_dia` だけ。実物も滑らかな極大ではなく角で、
    `_SHOULDER_PROFILE` の s=0 の傾きは胴側の傾きと一致しない。

    **ただし「境の半径を動かさない」＝「境が最大」ではない。** 歪みが強いと
    胴の途中や肩の途中がそこを追い越す ——`heel_z` は軸方向の式なので**動かず**、
    OCCT もソリッド 1 個を返すので、Phase B-4b までこれは誰にも見えていなかった。
    いまは母線の単調性（`body_waist_limits` / `shoulder_fullness_limits`）が
    スライダの壁として掛かっていて、範囲内なら頂点は踵にある。壊れていないことを
    直に確かめるのは `outer_apex` / `shoulder_dip`。
    """
    r_max = p["body_dia"] / 2.0
    heel = heel_z(p)
    if z <= heel:
        return r_max * body_shape(p, max(z, 0.0) / heel)
    r_sh = shank_radius(p)
    sl = shoulder_length(p)
    s = (z - heel) / sl if sl > 0 else 1.0
    if s >= 1.0:
        return r_sh
    return r_sh + (r_max - r_sh) * shoulder_shape(p, s)


# ---------------------------------------------------------------- 頂点は「主張」
#
# 「最大径は踵（`heel_z`）にある」は**設計の主張であって計算結果ではない**。
# `heel_z` は (全長 − シャンク長)/(1 + 肩比) という**軸方向の式**なので、形を歪める
# 2 本（`body_waist` / `shoulder_fullness`）では定義上 1 ビットも動かない ——
# つまり `heel_z` を見張っても、この 2 本が頂点を壊したことは**永久に検出できない**
# （`cad/windycity/sweep_outer.py` の主張 (1) が Phase B-4b までそうだった。
# 式を検算していて形を見ていない）。だから形を直に測る側をここに置く。
#
# 壊れ方は 2 通りあり、**どちらも OCCT はソリッド 1 個を返す**（掃引の段 3 が
# 「1 個か」しか見ていないので素通りする。B-3 の「1 個は必要条件でしかない」の
# 2 例目）:
#
#   - 頂点が胴／肩の途中へ移る → `ligature_seat_range` は `heel_z` 基準なので
#     **リガチャー座の位置そのものが嘘**になる（セット適合の基準でもある）。
#   - 肩の途中が `shank_radius` を下回る → 「最大径からシャンクへ絞る」が破れて
#     **えぐれ（アンダーカット）**になる。単調に細るという前提の上に立っている
#     ものが全部ずれる。
#
# 限界値は `_BODY_PROFILE` / `_SHOULDER_PROFILE` だけで決まる（`r/r_max` に
# 正規化した形の性質なので **3 サイズ共通・他のパラメータに依らない**）。
# **数字を書き写さずに表から解く** —— 実測表を差し替えたら限界も一緒に動く。
# 散文へ焼くと腐るのは Phase B-2 で踏んだとおり。


def _min_on_unit(fn, n: int = 4000) -> float:
    """`fn(t)` の最小値を t∈(0,1) で。走査で括ってから黄金分割で詰める。

    端は分母が 0 に落ちるので除く。呼び出し側はどれもキャッシュ付きなので、
    精度側に倒して走査を粗くしない。
    """
    ts = [(i + 1) / (n + 1) for i in range(n)]
    vals = [fn(t) for t in ts]
    k = min(range(n), key=vals.__getitem__)
    a = ts[k - 1] if k > 0 else 0.0
    b = ts[k + 1] if k < n - 1 else 1.0
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = fn(c), fn(d)
    for _ in range(200):
        if b - a < 1e-13:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = fn(c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = fn(d)
    return min(vals[k], fc, fd)


#: 数値微分の刻み（`_pchip` は C1 なので中心差分で十分）。
_D = 1e-6


def _deriv(fn, t: float) -> float:
    a, b = max(t - _D, 0.0), min(t + _D, 1.0)
    return (fn(b) - fn(a)) / (b - a)


@functools.lru_cache(maxsize=1)
def body_waist_limits() -> tuple[float, float]:
    """`body_waist` が「胴は最大径に向かって単調に太る」を保つ範囲。

    `r(u) = P(u)·(1 + w·B(u))` の微分から
    `P' + w·(P·B)' ≥ 0` ——`(P·B)'` の符号で上下に割れるので、
    正のところが上限を、負のところが下限を決める。

    **上限は「頂点が u=1 から外れる点」と同じ事象**（頂点が端から外れるのは、
    端の直前で母線が下り始めることだから）。実測で 0.072573 と 0.072572 が
    一致する。下限のほうは胴の中ほど（u≈0.23）に凹みが出る点で、
    こちらは頂点を見ていても永久に分からない。
    """
    prof = lambda u: _pchip(_BODY_PROFILE, u)          # noqa: E731
    both = lambda u: prof(u) * _waist_bump(u)          # noqa: E731

    def hi(u: float) -> float:
        g = _deriv(both, u)
        return _deriv(prof, u) / -g if g < -1e-12 else float("inf")

    def lo(u: float) -> float:
        g = _deriv(both, u)
        return _deriv(prof, u) / g if g > 1e-12 else float("inf")

    return -_min_on_unit(lo), _min_on_unit(hi)


@functools.lru_cache(maxsize=1)
def shoulder_fullness_limits() -> tuple[float, float]:
    """`shoulder_fullness` が「肩は最大径からシャンクへ単調に細る」を保つ範囲。

    `v(s) = S(s) + k·(L(s) − S(s))`（`L(s) = 1 − s` は直線）の微分から
    `S' + k·(L − S)' ≤ 0`。

    **単調のほうが「値が [0, 1] を出る」より先に破れる**（実測 −0.3607 /
    +1.8633 に対し、シャンク径を割るのは −0.3729、最大径を超えるのは
    +2.6175）ので、こちらを壁にする。+1（母線が直線＝円錐）は内側に残る。
    """
    prof = lambda s: _pchip(_SHOULDER_PROFILE, s)               # noqa: E731
    gap = lambda s: (1.0 - s) - _pchip(_SHOULDER_PROFILE, s)    # noqa: E731

    def hi(s: float) -> float:
        g = _deriv(gap, s)
        return -_deriv(prof, s) / g if g > 1e-12 else float("inf")

    def lo(s: float) -> float:
        g = _deriv(gap, s)
        return _deriv(prof, s) / g if g < -1e-12 else float("inf")

    return -_min_on_unit(lo), _min_on_unit(hi)


def outer_apex(p: dict, n: int = 2000) -> tuple[float, float]:
    """外形の**実際の**最大半径とその z（面取り前の `outer_radius_nominal` 基準）。

    `heel_z` と食い違ったら「最大径は踵」という主張が破れている。**式ではなく
    形を見る**ためのものなので、ここでは閉じた式を使わず素直に走査する
    （`*_limit()` の解と互いの答え合わせになる）。
    """
    heel = heel_z(p)
    sl = shoulder_length(p)
    best_z, best_r = heel, outer_radius_nominal(p, heel)
    for span, base in ((heel, 0.0), (sl, heel)):
        if span <= 0.0:
            continue
        for i in range(n + 1):
            z = base + span * i / n
            r = outer_radius_nominal(p, z)
            if r > best_r:
                best_z, best_r = z, r
    return best_z, best_r


def body_dip(p: dict, n: int = 2000) -> tuple[float, float]:
    """胴（ティップ〜踵）が**太るのをやめる**点と、その落ち込み量 [mm]。

    単調に太っていれば `(heel_z, 0.0)`。`shoulder_dip` が半径を返すのと違って
    第 2 要素は**落ち込み量**（0 なら健全）——凹みは局所的なので、絶対値では
    なく「前より細くなったか」で見るしかない。

    `outer_apex` では捕まらない。負の `body_waist` が作るのは中ほどの凹みで、
    最大径は踵のままだから ——**壊れ方が 3 通りあるので、目も 3 つ要る**。
    """
    heel = heel_z(p)
    if heel <= 0.0:
        return heel, 0.0
    worst_z, worst = heel, 0.0
    prev = outer_radius_nominal(p, 0.0)
    for i in range(1, n + 1):
        z = heel * i / n
        r = outer_radius_nominal(p, z)
        if prev - r > worst:
            worst_z, worst = z, prev - r
        prev = r
    return worst_z, worst


def shoulder_bulge(p: dict, n: int = 2000) -> tuple[float, float]:
    """肩（踵〜シャンク平行部）が**細るのをやめる**点と、その膨らみ量 [mm]。

    単調に細っていれば `(heel_z, 0.0)`。`body_dip` の肩側の相方で、2 つ合わせて
    「母線は単調」という主張そのものになる ——`outer_apex` と `shoulder_dip` は
    その主張が破れたときに**見える症状**でしかなく、症状が出ないまま主張だけが
    破れる帯がある（肩比 1.86〜2.62 は膨らむのに最大径を超えず、シャンク径も
    割らないので、その 2 つは何も言わない）。
    """
    heel, sl = heel_z(p), shoulder_length(p)
    if sl <= 0.0:
        return heel, 0.0
    worst_z, worst = heel, 0.0
    prev = outer_radius_nominal(p, heel)
    for i in range(1, n + 1):
        z = heel + sl * i / n
        r = outer_radius_nominal(p, z)
        if r - prev > worst:
            worst_z, worst = z, r - prev
        prev = r
    return worst_z, worst


def shoulder_dip(p: dict, n: int = 2000) -> tuple[float, float]:
    """肩（踵〜シャンク平行部）の**最小**半径とその z。

    `shank_radius` を下回っていたらえぐれている。
    """
    heel, sl = heel_z(p), shoulder_length(p)
    if sl <= 0.0:
        return heel, outer_radius_nominal(p, heel)
    best_z, best_r = heel + sl, outer_radius_nominal(p, heel + sl)
    for i in range(n + 1):
        z = heel + sl * i / n
        r = outer_radius_nominal(p, z)
        if r < best_r:
            best_z, best_r = z, r
    return best_z, best_r


# ティップ前縁の面取り
#
# 実物はリード面側から削られていて、z=0 の前面は 0.25mm しかない（面取り無しだと
# `tip_rail_thickness` ぶん＝テナーで 1.25mm の角ばった壁が立ち、その両端が
# 90°近い稜線になる）。実測は先端輪郭から勾配 3.4（Δy/Δz）で z 方向 0.13–0.15mm、
# x=0/1/2/3 のどこでも勾配は 3.1–3.6 でほぼ一定＝**先端の弧に沿った面取り**。
#
# 胴は回転体なので、z≈0 で半径を細らせるだけで面取りが弧へ自動で沿う
# （リード面カットは固定平面なので、(x,z) の最下面は max(cut_top, −√(r²−x²))）。
# 削り代そのものはサイズで変わるのでテンプレートの `tip_chamfer`、面取り角は
# 仕上げの定数なのでここに置く。

#: 削り代 ÷ 面取り長。
_TIP_CHAMFER_SLOPE = 4.1
#: 削り代に対するビーク稜線の下げ量。前面高さを実測の 0.25mm にする値。
_TIP_FACE_DROP_RATIO = 0.43


def tip_chamfer_depth(p: dict) -> float:
    """ティップ前縁の面取り代（z=0 での半径の削り量）[mm]。"""
    return max(p.get("tip_chamfer", 0.0), 0.0)


def tip_chamfer_len(p: dict) -> float:
    """面取りが公称半径へ戻るまでの z [mm]。"""
    return tip_chamfer_depth(p) / _TIP_CHAMFER_SLOPE


def _tip_chamfer_ramp(p: dict, z: float) -> float:
    """面取りの効き具合 1→0。z ≥ 面取り長 で 0。"""
    ln = tip_chamfer_len(p)
    if ln <= 0.0 or z >= ln:
        return 0.0
    return 1.0 - max(z, 0.0) / ln


def outer_radius(p: dict, z: float) -> float:
    """胴の外半径（切除前）。ティップ前縁の面取りを含む。"""
    return (outer_radius_nominal(p, z)
            - tip_chamfer_depth(p) * _tip_chamfer_ramp(p, z))


def body_stations(p: dict) -> list[float]:
    """胴の回転体プロファイルを取る z の列。

    母線が区分直線なので、曲率の高い所は弦がその内側を通る（誤差 ≈ κ·dz²/8）。
    ノーズは 1.4mm 刻みだと z=2 で半径が 0.29mm 痩せ、リード面が胴を切る弦＝
    先端輪郭がそのぶん内側へ寄って**ティップレールが 0.3mm 細く見えていた**。
    誤差は dz² で効くので刻みを詰めると落ちる。
    先頭の面取り区間は 0.17mm しかなく、0.25mm 刻みだと丸ごと飛ぶので両端を足す。

    **この弦誤差はソリッド自体に焼き込まれている**（`revolve_profile` は多角形の
    母線を回すので、周方向は解析曲面でも母線方向は折れ線）。だから STL/3MF の
    メッシュ許容をいくら詰めても消えず、STEP（`body_segments` のスプライン版）
    とだけ形が食い違う —— 「STL には紋様が出るが STEP には出ない」の片方の正体。

    刻みの根拠（3 サイズの区間別 実測、`outer_radius` に対する最大内側ずれ）:

      - 旧: ノーズ 0.25/0.45mm・肩 12 分割 → **0.083 / 0.133 / 0.127mm**
        （最悪は soprano/tenor が肩の 1 区間目、alto も肩。次点はノーズ 1.5–1.95）
      - 現: ノーズ 0.10/0.25mm・肩 24 分割 → **0.029 / 0.026 / 0.034mm**
        （48〜49 点 → 75〜76 点）

    ここで止めるのは、さらに詰めても頭打ちだから —— ノーズ 0.06mm・肩 32 分割まで
    行っても 0.017〜0.036mm で、alto は肩の折れ目付近で**むしろ増える**
    （胴→肩の乗り換えは C1 でないので、誤差が dz² で落ちない区間がある）。
    """
    length = p["overall_length"]
    heel = heel_z(p)
    ch = tip_chamfer_len(p)
    zs = {0.0, ch,                                             # 面取りの両端
          *(0.10 * i for i in range(16)),                      # 0.0–1.5 ノーズ
          *(1.5 + 0.25 * i for i in range(1, 13)),             # 1.75–4.50
          *(4.65 + 1.0 * i for i in range(1, 5)),              # 5.65–8.65
          *(z for z in (heel * (i / 24.0) ** 1.6 for i in range(25)) if z > 9.0),
          *(heel + (length - heel) * i / 24.0 for i in range(25))}
    return sorted(zs)


def body_segments(p: dict, n_chamfer: int = 5, n_nose: int = 30,
                  n_shoulder: int = 44) -> list[list[tuple[float, float]]]:
    """胴の母線を **C1 の折れ目で区切った** (z, r) の区間列（STEP 出力用）。

    `revolve_spline_profile` へ渡す。区切るのは、全体を1本のスプラインで内挿すると
    折れ目でうねるため（実測でティップ面取りの端に 0.58mm のオーバーシュートが出て
    胴の体積が 1.3% 痩せた。刻みを 0.05mm まで詰めても減らない）。折れ目は3箇所:

      - `tip_chamfer_len`: 面取りの勾配 −4.1 から本来の立ち上がりへ折れる
      - `heel_z`: 胴プロファイルから肩プロファイルへ切り替わる
      - `shank_start_z`: 肩からシャンク平行部（外径一定）へ

    刻みは `body_stations` を使い回すが、面取り区間・ノーズ・肩は元の列だと粗いので
    区間内で取り直す。折れ目さえ外せばスプラインの内挿誤差は多角形の弦誤差より
    ずっと小さいが、ノーズは曲率が極端（半径が 5mm で 2 倍以上になる）なので
    0.25mm 刻みのままだと 0.024mm 残る。0.08mm まで詰めると 0.005mm に落ちる。
    """
    length = p["overall_length"]
    heel = heel_z(p)
    z_sh = shank_start_z(p)
    ch = tip_chamfer_len(p)
    segs: list[list[float]] = []
    if ch > 0.0:
        segs.append([ch * i / n_chamfer for i in range(n_chamfer + 1)])
    z_start = ch if ch > 0.0 else 0.0
    z_nose = min(0.03 * heel, 0.5 * (heel - z_start))       # テナーで z≈2.4
    mid = {z_start + (z_nose - z_start) * i / n_nose for i in range(n_nose + 1)}
    mid |= {z for z in body_stations(p) if z_nose < z < heel}
    segs.append(sorted(mid) + [heel])
    if z_sh > heel + 1e-9:
        # 肩が厳密な直線なら 2 点だけ返す＝母線が線分＝CONICAL_SURFACE 1 面。
        # 44 点のスプラインで通しても形は同じだが、FreeCAD で「円錐面」として
        # 選べなくなる（`revolve_spline_profile` の 2 点規則）。
        segs.append([heel, z_sh] if shoulder_is_straight(p) else
                    [heel + (z_sh - heel) * i / n_shoulder
                     for i in range(n_shoulder + 1)])
    if length > z_sh + 1e-9:
        segs.append([z_sh, length])          # 2点＝直線母線＝CYLINDER 1面
    return [[(z, outer_radius(p, z)) for z in seg] for seg in segs]


# ---------------------------------------------------------------- テーブル平面（傾斜）

def table_angle(p: dict) -> float:
    """テーブル平面のボア軸に対する傾き [rad]。実測 4.18°。"""
    return math.radians(p.get("table_angle", 4.2))


def table_plane_y(p: dict, z: float) -> float:
    """テーブル平面（リード接地面）の Y 座標。

    位置は魔法定数ではなく **「ティップがちょうど z=0 に立つ」** で決まる。
    先端はノーズ下端とフェイシング面が交わる点なので `-r(0) = table(0) + tip_opening`。
    実測（table(0) = −7.916、r(0) = 5.32、tip_opening 2.6）とこの式は 0.004mm で一致する。
    ティップ開きを広げればテーブルはその分だけ下がり、先端は z=0 に留まる。
    """
    y0 = -outer_radius_nominal(p, 0.0) - p["tip_opening"]
    return y0 - math.tan(table_angle(p)) * z


def table_y(p: dict) -> float:
    """[非推奨] 傾斜する前提が無かった頃の互換 API。

    テーブルは平面ではなく傾いた平面なので、単一の Y 値では表せない。
    リガチャー座の中央での値を返す（リガチャー生成の当座の基準）。新規コードは
    `table_plane_y(p, z)` を使うこと。
    """
    s0, s1 = ligature_seat_range(p)
    return table_plane_y(p, 0.5 * (s0 + s1))


def table_cut_end_z(p: dict) -> float:
    """テーブルカットが胴から外れて消える z（テーブル面が外形の下を通り抜ける点）。

    傾斜平面なので、後方のどこかで必ず胴の外へ出る。旧実装の「ランプで強引に消す」
    処理は不要。位置は形状から解く（実測は肩の途中 z≈81.5 で消える）。
    """
    length = p["overall_length"]
    lo, hi = heel_z(p) * 0.5, length
    if table_plane_y(p, hi) > -outer_radius(p, hi):
        return hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if table_plane_y(p, mid) > -outer_radius(p, mid):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def facing_rise(p: dict, z: float) -> float:
    """テーブル平面からのフェイシングカーブ持ち上がり量（z<=facing_length で >0）。"""
    fl = p["facing_length"]
    tip = p["tip_opening"]
    if z >= fl:
        return 0.0
    if p.get("facing_curve", "radial") == "elliptic":
        t = (fl - z) / fl
        return tip * (1.0 - math.sqrt(max(1.0 - t * t, 0.0)))
    # 円弧（テーブルに接する。R は y(0)=tip となるよう決定）。実物の実測はこちらが一致。
    if tip <= 0.0:
        # **開きが 0 の円弧は半径が定まらない。** `cavity_layout_error` が
        # 先に弾くので通常ここへは来ないが、素の `ZeroDivisionError` が
        # 出所不明のまま上がるのを防ぐ（掃引 `sweep_limits.py tip_opening` が
        # ちょうど 0 で踏んだ。`_pchip_table` の節点衝突と同じ型）。
        raise ValueError(
            f"ティップ開きが {tip!r} なのでフェイシングの円弧半径が定まりません"
            f"（radial は y(0)=tip となる R を解くので tip > 0 が要ります）。")
    r = (fl * fl + tip * tip) / (2.0 * tip)
    return r - math.sqrt(max(r * r - (fl - z) ** 2, 0.0))


def cut_top_y(p: dict, z: float) -> float:
    """テーブル/フェイシングカット面の上端 Y（この下側を切除）。"""
    return table_plane_y(p, z) + facing_rise(p, z)


#: ティップ輪郭を探す z の上限 [mm]。実測の角は 1.3〜1.7 なので十分な余裕がある。
_TIP_CONTOUR_MAX_Z = 8.0


def tip_contour_z(p: dict, x: float) -> float:
    """幅方向 x でティップレールの前縁が来る z [mm]。

    胴（半径 `outer_radius`）をリード面（`cut_top_y`）で切った断面の縁で、x での
    胴の下端 −√(r²−x²) がリード面に達する z を解く。中央（x=0）でも厳密に 0 では
    ない —— ティップ前縁の面取りぶん後ろへ来る（実測 0.103 / 0.117 / 0.130）。
    **角は中央より 1.27〜1.57mm 後ろ**で、これが実物のリードの前縁が直線ではなく
    曲線である理由。リードの前縁（`reed_profiles.front_edge_z`）と突き合わせるために
    公開している。

    リードの座標系はテーブル面基準で軸が 4.18° 傾くが、比べる区間は 2mm 足らずなので
    傾きの効きは 0.004mm。ここでは無視する。
    """
    def gap(z: float) -> float:
        r = outer_radius(p, z)
        return cut_top_y(p, z) + math.sqrt(max(r * r - x * x, 0.0))

    lo, hi = 0.0, _TIP_CONTOUR_MAX_Z
    if gap(lo) >= 0.0:
        return lo
    if gap(hi) < 0.0:
        return hi              # この x には胴が無い（リード面の弦より外）
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if gap(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


#: テーブルカット断面をティップより手前 / シャンクより奥へ出す量 [mm]。
_FACING_CUT_LEAD = 3.0
#: テーブルカット断面の深さ [mm]。胴を確実に下から抜く。
_FACING_CUT_DEPTH = 80.0


def facing_cut_z_range(p: dict) -> tuple[float, float]:
    return -_FACING_CUT_LEAD, p["overall_length"] + _FACING_CUT_LEAD


def facing_cut_points(p: dict, n: int = 56) -> list[tuple[float, float]]:
    """テーブル/フェイシングカット断面（YZ）の閉ポリゴン (z, y)。多角形版。"""
    z_lo, z_hi = facing_cut_z_range(p)
    zs = [z_lo + (z_hi - z_lo) * i / (n - 1) for i in range(n)]
    return ([(z, cut_top_y(p, z)) for z in zs]
            + [(z_hi, -_FACING_CUT_DEPTH), (z_lo, -_FACING_CUT_DEPTH)])


def facing_cut_segments(p: dict,
                        samples: int = 200) -> list[list[tuple[float, float]]]:
    """テーブル/フェイシングカット断面（YZ）の閉ループを**区間ごと**に返す。

    `yz_profile_cut_solid_curved` へ渡すと、テーブルが PLANE 1面・フェイシングが
    BSPLINE 1面になる（多角形版は 56 本の折れ線＝56 面）。

    フェイシングを円筒面にしないのは、テーブルが軸に対して傾いているぶん
    `cut_top_y` が Y 方向にせん断されていて厳密には楕円弧だから（円弧で
    最小二乗フィットすると 0.0024mm 残る。リード密着面なので近似しない）。

    楕円カーブ（`facing_curve == "elliptic"`）だけは z=0 で接線が垂直になるので、
    そこで区間を切り、標本を楕円のパラメータで等間隔に取る（z 等間隔だと
    ティップ側が粗くなってスプラインが暴れる）。z<0 側は持ち上がりが
    `tip_opening` で頭打ちなので直線。
    """
    length = p["overall_length"]
    fl = p["facing_length"]
    z_lo, z_hi = facing_cut_z_range(p)
    segs: list[list[tuple[float, float]]] = []
    if p.get("facing_curve", "radial") == "elliptic":
        zs = sorted(fl * (1.0 - math.sin(0.5 * math.pi * i / (samples - 1)))
                    for i in range(samples))
        segs.append([(z_lo, cut_top_y(p, z_lo)), (0.0, cut_top_y(p, 0.0))])
        segs.append([(z, cut_top_y(p, z)) for z in zs])
    else:
        zs = [z_lo + (fl - z_lo) * i / (samples - 1) for i in range(samples)]
        segs.append([(z, cut_top_y(p, z)) for z in zs])
    segs.append([(fl, cut_top_y(p, fl)), (z_hi, cut_top_y(p, z_hi))])  # テーブル平面
    segs.append([(z_hi, cut_top_y(p, z_hi)), (z_hi, -_FACING_CUT_DEPTH)])
    segs.append([(z_hi, -_FACING_CUT_DEPTH), (z_lo, -_FACING_CUT_DEPTH)])
    segs.append([(z_lo, -_FACING_CUT_DEPTH), (z_lo, cut_top_y(p, z_lo))])
    return segs


# ---------------------------------------------------------------- ビーク

#: ビーク横断面の円弧半径（body_dia 比）。実測 25.0mm / 30.8mm。
_BEAK_RIDGE_RATIO = 0.812
#: バイトポイント位置（全長比）
_BEAK_BITE = 0.25
#: ビークが胴へ溶けるブレンド区間（heel_z 比）。実測 34.2→41.5mm / 79mm。
_BEAK_BLEND0 = 0.433
_BEAK_BLEND1 = 0.525
#: ブレンドの偏り。1.0 で対称（smoothstep）、大きいほど「粘ってから寄る」。
#: 実測の中盤（u(0.5)≒0.18）に合う値。
_BEAK_BLEND_BIAS = 1.9


def _beak_blend(p: dict, z: float) -> float:
    """ビークが胴へ溶ける進行度 u∈[0,1]。

    稜線は y(z) = line(z) + (top(z) − line(z))·u(z)。両端で折れないためには
    **u'(z0) = u'(z1) = 0** が必要十分になる（z0 で線へ、z1 で胴へ接する）。

    旧実装の `u = t**2.5` は u'(0)=0 は満たすが u'(1)=2.5/span ≠ 0 で、
    ビークが胴へ消える所に折れが残っていた。かといって素の `smoothstep`
    （両端0）だと中盤が実測より 1.6mm 浮く。t を先に乗すと **両端の傾き0を保ったまま**
    中盤だけ寝かせられるので、smoothstep(t**bias) で両立させる。
    """
    heel = heel_z(p)
    z0, z1 = _BEAK_BLEND0 * heel, _BEAK_BLEND1 * heel
    if z <= z0:
        return 0.0
    if z >= z1:
        return 1.0
    return _smoothstep(((z - z0) / (z1 - z0)) ** _BEAK_BLEND_BIAS)


def beak_ridge_radius(p: dict) -> float:
    return _BEAK_RIDGE_RATIO * p["body_dia"]


def beak_apex_y0(p: dict) -> float:
    """ティップ端でのビーク頂点 Y。テーブル＋ティップ開き＋ティップレール厚。"""
    return (table_plane_y(p, 0.0) + p["tip_opening"]
            + p.get("tip_rail_thickness", 1.3))


def beak_angle(p: dict) -> float:
    """ビーク頂線の傾き [rad]。`beak_height`（バイトポイントでのテーブル面からの
    高さ）とティップ端の頂点から一意に決まる。実測 18.0°。"""
    z_bite = _BEAK_BITE * p["overall_length"]
    y_bite = table_plane_y(p, z_bite) + p["beak_height"]
    return math.atan2(y_bite - beak_apex_y0(p), z_bite)


def beak_apex_y(p: dict, z: float) -> float:
    """ビーク稜線（x=0）の Y。胴へのブレンドと、ティップ前縁の面取りを含む。

    面取りは半径を細らせるだけでは足りない。z=0 での前面の高さは
    「ビーク稜線 − 細らせた半径」なので、稜線も同じ区間だけ下げないと
    前面が 0.69mm 残る（実測 0.25mm）。
    """
    line = (beak_apex_y0(p) + math.tan(beak_angle(p)) * z
            - _TIP_FACE_DROP_RATIO * tip_chamfer_depth(p)
            * _tip_chamfer_ramp(p, z))
    u = _beak_blend(p, z)
    if u <= 0.0:
        return line
    top = outer_radius(p, z)
    return top if u >= 1.0 else line + (top - line) * u


def beak_section_radius(p: dict, z: float) -> float:
    """ビーク横断面の曲率半径。

    ブレンド区間では胴の半径へ寄せる（実測で z=40 の横断曲率半径が
    14.1mm ≈ 胴半径 13.6mm まで小さくなっていた）。
    """
    r = beak_ridge_radius(p)
    u = _beak_blend(p, z)
    return r + (outer_radius(p, z) - r) * u if u > 0.0 else r


def beak_top_y(p: dict, z: float, x: float = 0.0) -> float:
    """ビーク面の Y（この上側を切除）。稜線から横断面円弧で降りる。"""
    r_ridge = beak_section_radius(p, z)
    ax = min(abs(x), 0.999 * r_ridge)
    return beak_apex_y(p, z) - (r_ridge - math.sqrt(max(r_ridge * r_ridge - ax * ax, 0.0)))


def beak_y(p: dict, z: float) -> float:
    """[互換] ビーク稜線の Y。`beak_top_y(p, z, 0.0)` と同じ。"""
    return beak_apex_y(p, z)


def beak_height_flat(p: dict) -> float:
    """ビーク稜線がティップ〜バイトポイントで**水平**になる `beak_height` [mm]。

    ティップ側の頂点 `beak_apex_y0` は「テーブル＋ティップ開き＋ティップレール厚」
    で固定なので、これを下回ると稜線が**前下がり**になる ——ビークが後ろへ向かって
    低くなる形は、実測 18.0° の「ティップからバイトへ立ち上がる」直線ランプでは
    もはやない。Phase B-4b でスライダの `hard_min` にした。
    """
    return beak_apex_y0(p) - table_plane_y(p, _BEAK_BITE * p["overall_length"])


def beak_height_at_body_top(p: dict) -> float:
    """バイトポイントで稜線が胴の頂点に届く `beak_height` [mm]。

    `beak_height` は「バイトポイントでのテーブル面からの高さ ＝ くわえたときの
    口の開き量」と定義されている。これを超えると**その定義が壊れる** ——
    稜線が胴の外（空中）に出て切除が効かず、バイトポイントの上面は胴のままに
    なるので、与えた数字は部品のどこにも現れない。

    **旧コメントの「胴の全高 0.9·`body_dia`」は外れていた。** 実測すると
    0.723 / 0.734 / 0.746·`body_dia`（3 サイズ）で、**比は一定ですらない** ——
    バイトポイントは全長の 1/4 で、そこの胴の太さは踵までの比で決まるため。
    旧レンジの上端 0.75·`body_dia` は 3 サイズとも**この壁の外**にあった。
    """
    z_bite = _BEAK_BITE * p["overall_length"]
    return outer_radius(p, z_bite) - table_plane_y(p, z_bite)


#: 切除ソリッドをティップより手前へ出す量 [mm]。
_BEAK_CUT_LEAD = 2.0


def beak_cut_range(p: dict) -> tuple[float, float]:
    """ビーク切除ソリッドが覆う z の範囲。"""
    return -_BEAK_CUT_LEAD, heel_z(p) + 2.0


def beak_ramp_end_z(p: dict) -> float:
    """ビークの直線ランプが終わり、胴へのブレンドが始まる z。"""
    return _BEAK_BLEND0 * heel_z(p)


def beak_blend_end_z(p: dict) -> float:
    """ビークが完全に胴へ溶けきる z。"""
    return _BEAK_BLEND1 * heel_z(p)


def beak_cut_stations(p: dict, n: int = 44) -> list[float]:
    """ビーク切除ソリッドの断面を取る z の列。

    ロフトはルールド（断面間が直線）なので、刻みより短い特徴は均されて後ろへ
    伸びる。既定の刻みは 1.9mm あり、長さ 0.17mm のティップ面取りをそのまま
    掛けると稜線の下げが **z=1.9 まで線形に残り、z=0.6 で 0.2mm** 効いていた。
    面取りの折れ目 z=0 と z=面取り長 に断面を入れて閉じ込める。ティップ側では
    稜線も横断面半径も z の一次式なので、この2点だけでルールドロフトが厳密に一致する
    （区間を等分しても得られるものは無く、ロフトとブーリアンが遅くなるだけ）。
    """
    z0, z1 = beak_cut_range(p)
    zs = {z0 + (z1 - z0) * i / (n - 1) for i in range(n)}
    ch = tip_chamfer_len(p)
    if ch > 0.0:
        zs |= {0.0, ch}
    return sorted(zs)


def beak_cut_cap_y(p: dict) -> float:
    """ビーク切除断面を閉じる天井の Y。胴の上を確実に覆う高さ。"""
    return 4.0 * p["body_dia"]


def beak_cut_arc(p: dict, z: float,
                 half_width: float) -> list[tuple[float, float, float]]:
    """ビーク切除断面の下辺（円弧）の3点 (x, y, z)。`beak_cut_section` の曲線版。

    横断面はどの z でも真円の弧なので、3点で厳密に決まる（多角形の 33 点は
    その弧の近似でしかなかった）。

    端の x は**その z での曲率半径**（＝ブレンド後）で決めること。多角形版と同じ
    ブレンド前の半径 25mm で取ると、ブレンド区間では端点が円の外に出て
    `beak_top_y` のクランプ値になり、その3点を通る円が半径 26mm の別物になる
    （実測でモデルが z=39 付近で 0.59mm ずれた）。半径を細らせたぶん切除ソリッドの
    幅も縮むが、u が 1 に近づく所は `_beak_cut_lift` で胴の外へ逃げているので
    削り残しにはならない。
    """
    xa = min(half_width, 0.95 * beak_section_radius(p, z))
    lift = _beak_cut_lift(p, z)
    y_edge = beak_top_y(p, z, xa) + lift
    return [(-xa, y_edge, z), (0.0, beak_apex_y(p, z) + lift, z), (xa, y_edge, z)]


def beak_prism_breaks(p: dict) -> list[float]:
    """ビークの直線ランプを斜めプリズムで作るときの区切り z（STEP 出力用）。

    この区間では `_beak_blend` が 0 なので、ビーク面は「一定半径の円弧を直線に
    沿って平行移動した面」そのもの。稜線の勾配が変わる所だけで切れば、プリズムの
    押出が**厳密に**一致する（ロフトの近似が要らない）。

    勾配が折れるのはティップ面取りの両端だけ。z<0 では面取りのランプが 1.0 で
    クランプされるので勾配は本来のビーク角に戻る（＝z<0 と z>面取り長 は勾配が
    同じでも切片が違う別の面なので、区間は分けたままにする）。
    """
    z0, _ = beak_cut_range(p)
    ch = tip_chamfer_len(p)
    if ch <= 0.0:
        return [z0, beak_ramp_end_z(p)]
    return [z0, 0.0, ch, beak_ramp_end_z(p)]


def beak_blend_stations(p: dict) -> list[float]:
    """ビークが胴へ溶けるブレンド区間の断面 z（STEP 出力用）。

    ここだけは稜線も横断面半径も z の一次式ではないので、プリズムでは作れない。
    刻みは `beak_cut_stations` をそのまま切り出す —— 多角形版とルールドで
    **同じ面**を張るためで、こうしておけばプリミティブ化で形が 1mm も動かない。
    """
    z0 = beak_ramp_end_z(p)
    return [z0] + [z for z in beak_cut_stations(p) if z > z0]


#: ブレンド終端付近で切除ソリッドを胴から逃がす量 [mm]。
_BEAK_CUT_CLEAR = 1.2
#: 逃がしを効かせ始めるブレンド進行度。
_BEAK_CUT_LIFT_U = 0.88


def _beak_cut_lift(p: dict, z: float) -> float:
    """ビーク切除ソリッドを胴の外へ逃がす量 [mm]。

    ブレンド終端では `beak_apex_y == outer_radius` かつ横断面の曲率半径も胴と一致し、
    切除ソリッドの下面が **胴の外周面と完全に一致する**。面と面の一致は OCCT の
    ブーリアンが最も苦手とする条件で、実際にカットが黙って失敗し（胴がそのまま
    返る）ビークがまったく削れないことがあった。ステーション数を 44→60 に変える
    だけで成否が入れ替わる程度に不安定で、`is_valid` が False だったのもこれが原因。

    そこで終端付近だけ切除ソリッドを持ち上げ、常に**横断**（transversal）で交わる
    ようにする。持ち上げによる削り残しは `min(lift, 胴と稜線の差)` で、差の方は
    終端で 0 に収束するので最大でも 0.45mm・z 幅 1mm 程度にとどまる。
    """
    u = _beak_blend(p, z)
    if u <= _BEAK_CUT_LIFT_U:
        return 0.0
    return _BEAK_CUT_CLEAR * _smoothstep(
        (u - _BEAK_CUT_LIFT_U) / (1.0 - _BEAK_CUT_LIFT_U))


def beak_cut_section(p: dict, z: float, half_width: float,
                     samples: int = 33) -> list[tuple[float, float]]:
    """ビーク切除ソリッドの断面（x, y）閉ポリゴン。

    稜線の円弧に沿って下辺を作り、上を y=+H で閉じる。円弧は胴より広く取るので、
    胴の左右も含めて「ビーク面より上」を確実に覆う。ブレンド終端付近では
    `_beak_cut_lift` だけ胴から逃がす（理由はそちらの説明）。
    """
    r_ridge = beak_ridge_radius(p)
    xa = min(half_width, 0.95 * r_ridge)
    lift = _beak_cut_lift(p, z)
    pts = []
    for i in range(samples):
        x = -xa + 2.0 * xa * i / (samples - 1)
        pts.append((x, beak_top_y(p, z, x) + lift))
    h = 4.0 * p["body_dia"]
    pts.append((xa, h))
    pts.append((-xa, h))
    return pts


# ---------------------------------------------------------------- 内部空洞
#
# 空洞は「ウィンドウ（スロット）を彫ったもの」ではなく **1本の滑らかな管** として
# 定義する。実物もそう作られていて、リード面（テーブル＋フェイシング）がこの管を
# 切った所がウィンドウになる。
#
# 旧実装はスロットを明示的に作っていたため、開口幅・床の立ち上がり・閉口後の
# 「鍵穴」解消がそれぞれ別の式になり、**継ぎ目で傾きが飛んで**内部に棚と縦壁が
# 出ていた（実測: d(半幅)/dz が −0.94 → +2.09、d(床)/dz が −0.07 → +0.71）。
#
# 管は3本の曲線だけで決まる。すべて PCHIP（構成上 C1）で、min/max による
# 頭打ちも `_soft_min` に置き換えてあるので、全長にわたって折れが無い:
#
#   W(z) = cavity_half_width(p, z)   半幅
#   C(z) = cavity_roof_y(p, z)       天井（＝バッフル）
#   F(z) = cavity_floor_y(p, z)      床
#
# ウィンドウは **F(z) が cut_top_y(z) を上へ横切る所で自然に閉じる**。開口幅も
# 「管の断面がリード面で切られた弦」として出るので、専用の式を持たない。

#: バッフルが無いときのティップ天井高さ（リード面から）。bore_dia 比。
#: 実測のテナー（`tip_rail_width` 0.85 / `baffle_height` 2.6）で
#: `baffle_plateau_y` と `tip_roof_y` が一致するよう校正した値。
#: これにより既定値では天井が実測どおり「ボア軸に平行な一枚の平面」になる。
_TIP_GAP_FREE_RATIO = 0.2956
#: バッフル天井が平坦なまま続く区間（ボア開始位置 zb 比）。実測 18.0mm / 50.0mm。
#: 天井の法則はボア（zb で必ずボア円になる）を基準にするのが自然なので、
#: ウィンドウ長ではなく zb で正規化する。
_BAFFLE_FLAT = 0.36


def window_width(p: dict) -> float:
    return p["reed_width"] - 2.0 * p["side_rail_width"]


# --- 実測テーブル（WindyCity Tenor .100" LS を σ = z / bore_start_z で正規化）---
#
# σ を zb で正規化するのは、3本とも「z=zb でボア円になる」という共通の終端条件を
# 持つため。終端で必ず一致するので、遷移区間を別式で繋ぐ必要が無い（旧実装の
# `_TRANSITION_TS` + smoothstep がまさにその継ぎ目だった）。

#: 半幅 W / bore_radius。ティップで一気に開いたあとは、z≈31 で 0.865 まで緩く
#: 絞られてボアへ開くだけ。旧実装が「窓が後方で細くなる」と見ていたのは開口の話で、
#: **窓の区間より後ろの管はほぼ一定径**（全変化 1.15mm）だった。
#:
#: σ≲0.08（z≲4）の頭は Stage C-1b で実測から起こし直した。旧値（σ=0.024 で 0.980）は
#: **管ではなく胴の内側を拾っていた**。実物の断面を z 一定で切ると、空洞は z=1.5 で
#: |x|≲4.3、z=2.0 で ≲5.0、z=2.5 で ≲6.0、z=3.0 で ≲7.0、z=4.0 で ≲8.1 までしか無い。
#: ティップレールが先端に沿って一周する以上、管もその分だけ内側へ入る。
#: 旧値だと管がレールの下まで張り出し、**コーナーでレールが 0.02mm まで痩せていた**。
_CAVITY_W = [
    (0.019, 0.480), (0.023, 0.535), (0.025, 0.595), (0.030, 0.705),
    (0.035, 0.770), (0.040, 0.815), (0.045, 0.855), (0.050, 0.890),
    (0.055, 0.905), (0.060, 0.918), (0.065, 0.935), (0.070, 0.948),
    (0.080, 0.953), (0.100, 0.954), (0.140, 0.960), (0.200, 0.951),
    (0.260, 0.935), (0.320, 0.922), (0.380, 0.906), (0.440, 0.895),
    (0.500, 0.890), (0.560, 0.890), (0.620, 0.889), (0.680, 0.898),
    (0.740, 0.913), (0.800, 0.928), (0.860, 0.941), (0.920, 0.961),
    (0.980, 0.985), (1.000, 1.000),
]
#: 天井 C の立ち上がり率 v = (C − y_flat)/(bore_radius − y_flat)。実測は
#: 「平坦 → 傾き一定の直線ランプ → S字でボアへ」。σ=0.36 まで完全に平坦。
_CAVITY_C = [
    (0.000, 0.000), (0.360, 0.000), (0.380, 0.013), (0.410, 0.049),
    (0.440, 0.086), (0.470, 0.123), (0.500, 0.159), (0.530, 0.196),
    (0.560, 0.233), (0.590, 0.270), (0.620, 0.307), (0.650, 0.344),
    (0.680, 0.441), (0.710, 0.572), (0.740, 0.667), (0.770, 0.740),
    (0.800, 0.803), (0.830, 0.853), (0.860, 0.896), (0.890, 0.931),
    (0.920, 0.960), (0.950, 0.982), (0.980, 0.996), (1.000, 1.000),
]
#: 床の「リード面からの落とし込み」 D = (cut_top_y − F)/bore_radius。
#: 正なら窓が開いている。実測の窓幅から断面式を逆に解いて求めた（開口の
#: 直接実測に一致する床は一意に決まる）。σ≈0.838 で 0 を横切る＝そこが窓の終端で、
#: その先はチェンバー床として実測値そのもの。
_CAVITY_D = [
    (0.000, 0.100), (0.120, 0.073), (0.180, 0.087), (0.240, 0.093),
    (0.300, 0.098), (0.360, 0.116), (0.420, 0.138), (0.480, 0.146),
    (0.540, 0.153), (0.600, 0.138), (0.660, 0.120), (0.720, 0.092),
    (0.780, 0.048), (0.838, 0.000), (0.850, -0.085), (0.862, -0.160),
    (0.875, -0.210), (0.900, -0.260), (0.930, -0.288), (0.960, -0.321),
    (0.990, -0.354), (1.000, -0.367),
]
#: `_CAVITY_D` が 0 を横切る σ ＝ **実測品の窓の終端**。`cavity_floor_y` はこの点を
#: 設計の `window_end_z` へ写像する。テーブルを差し替えたらここも引き直すこと。
_CAVITY_D_ZERO = 0.838
#: `side_rail_width` を基準値から動かしたときに W が効く重み。窓の区間で 1、
#: ボアでは 0（ボア径はレール幅と無関係）。
_RAIL_WEIGHT = [(0.000, 1.0), (0.700, 1.0), (0.838, 0.85), (0.940, 0.3),
                (1.000, 0.0)]
#: `_CAVITY_W` を起こした実物のサイドレール幅 [mm]。ここからの差分だけが効く。
_RAIL_REF = 1.1

#: 窓区間の断面指数 (x, y)。x を大きく取ると側壁がほぼ垂直になり、リード面の
#: 高さで開口幅が痩せない。実測（z=6 と z=16 で、2.5mm の高さにわたり半幅の
#: 変化が 0.2mm）に合わせた値。旧実装はここを「直立壁＋フレア」の折れ線で
#: 作っていて、その折れが空洞の全長を走る棚になっていた。
_SECTION_NX = 6.0
_SECTION_NY = 2.4

#: 天井の横アーチ（断面の上半分だけに使う x 指数）。小さいほどアーチが深い。
#: 実測の天井は x=7mm で 0.31mm 下がり、そのサグは z によらずほぼ一定
#: （0.33/0.32/0.31/0.30 @ z=3/5/8/14）。断面高さ h はティップで 0.7mm・
#: z=14 で 4.2mm と 6 倍違うので、**一定サグを保つには指数を σ とともに上げる**。
#: σ≳0.16 では `nx`（=6）へ戻す＝後方の断面は現行のまま（そこはモデルの落差
#: 0.48mm が実測 0.30mm より既に大きく、触ると検証済みの数値が動く）。
_TOP_ARCH = [(0.000, 1.80), (0.060, 1.85), (0.090, 2.10), (0.120, 2.80),
             (0.160, 6.00), (1.000, 6.00)]


def _cav_sigma(p: dict, z: float) -> float:
    zb = bore_start_z(p)
    return z / zb if zb > 1e-9 else 0.0


def reed_chord(p: dict, z: float) -> float:
    """**リード面**（テーブル平面＋フェイシング持ち上がり）が胴を切る弦の長さ。

    窓が開けるのはこの弦の内側まで。テーブル平面で測ってはいけない: ティップ側は
    フェイシングカーブがリード面を最大 2.4mm 持ち上げており、テーブル平面で評価すると
    使える弦が極端に短く出る（z=1.2 で 4.1mm vs 実際 12.2mm）。旧実装はここを
    取り違えていて、窓が先端で点に潰れていた。
    """
    r = outer_radius(p, z)
    d = abs(cut_top_y(p, z))
    return 2.0 * math.sqrt(max(r * r - d * d, 0.0))


def table_chord(p: dict, z: float) -> float:
    """[非推奨] `reed_chord` の旧名。窓幅の上限はリード面で測る。"""
    return reed_chord(p, z)


def table_flat_width(p: dict, z: float) -> float:
    """テーブル（平面カット）の**実際の**幅 [mm]。

    `reed_width` はソリッドの上に存在しない —— 窓幅の公称値とリガチャーのタブ幅に
    使われるだけで、マウスピースの面を 1 つも決めていない。テーブルは平面カットなので
    実幅は「半径」と「カットの深さ」から決まり、**z によって変わる**（既定の
    リガチャー座中央で 13.98 / 15.14 / 14.66mm。`reed_width` は 12.9 / 13.4 / 14.8）。

    `reed_chord` と違ってフェイシングの持ち上がりを含めない: 平面が平面である区間
    （z ≥ `facing_length`）の弦なので、テーブル平面そのもので測る。
    """
    r = outer_radius(p, z)
    d = abs(table_plane_y(p, z))
    return 2.0 * math.sqrt(max(r * r - d * d, 0.0))


#: ロフト前端を窓の前縁より手前へ置く量 [mm]。前端の蓋がリード面より下
#: （フェイシングカットで消える側）に沈むので、窓の前縁は「天井がリード面を
#: 突き抜ける線」だけで決まり、軸に直角な直線の縁ができない。
_LOFT_FRONT_LEAD = 0.45


def window_front_z(p: dict) -> float:
    """設計上の窓前縁 z（＝クラウンでのティップレール幅）。

    先端は z=0 に立つので、窓が開き始める z がそのままレール幅になる。
    天井のティップ高さを `tip_roof_y` でこの点に合わせてあるため、外殻で
    頭打ちにならない限り実際の前縁もここに一致する（実効値は `window_open_z`）。
    """
    return max(p["tip_rail_width"], 0.05)


def window_start_z(p: dict) -> float:
    """空洞ロフトの開始平面。**窓の前縁ではない**。

    旧実装はここが `tip_rail_width + 0.2` の平面で、しかもその平面がリード面より
    上に出ていたため、**窓の前縁が軸に直角な直線**になっていた（x=±5.0 まで
    z=1.20 で一定）。実物の前縁は先端輪郭の等距離オフセットで、レール幅は
    クラウンからコーナーまで 0.83mm 一定。前端を前へ出して蓋を沈める。
    """
    return max(window_front_z(p) - _LOFT_FRONT_LEAD, 0.25)


#: `chamber_to_bore_mm` を持たない古いプロジェクト用の既定。**旧実装の直値**。
_CHAMBER_TO_BORE_DEFAULT_MM = 4.0


def window_end_z(p: dict) -> float:
    """ウィンドウ後端。チェンバー→ボアの遷移区間を必ず残す。

    残す量は `chamber_to_bore_mm`。**以前は直値 4.0 だった**が、これは幾何の
    成立条件ではなく慣習で、しかも `_floor_limit` と `cavity_floor_y` の
    2 つの退化を覆う蓋になっていた（両方とも塞いだ）。パラメータとして表に出す。
    """
    zb = bore_start_z(p)
    gap = p.get("chamber_to_bore_mm", _CHAMBER_TO_BORE_DEFAULT_MM)
    return min(window_front_z(p) + p["window_length"], zb - gap)


def window_length_effective(p: dict) -> float:
    """実際に開く窓の長さ [mm]。指定した `window_length` とは限らない。

    `window_end_z` は `bore_start_z − chamber_to_bore_mm` 側でも頭打ちになる。
    そちらが効くと **`window_length` を上げても形が一切変わらない**。
    `cavity_layout_error` は窓が `_MIN_WINDOW_SPAN_MM` を割るまで黙っているので、
    その手前に「落ちないし壊れてもいないが、スライダが効いていない」帯がある。
    `ParamSpec.validate` の黙ったクランプ（Stage F）と同じ種類だが、こちらは
    **導出側で起きるのでレンジを見ても分からない**。だから量として公開する。

    凍る点は導出できる ——

        window_length_freeze = bore_start_z − chamber_to_bore_mm − window_front_z

    **この数字を docstring に焼くのはやめた。** 3 つの項がどれもテンプレートに
    ぶら下がっているので、テンプレートを直すたびに本文だけが古くなる。実際
    ここは 2 世代連続で腐った（4-C.5 で 41.1/95.0 → 37.92/88.7 に直し、
    9/05 の `bore_length` 実測でまた 38.67/91.70 になった）。いまの値は
    `test_the_window_freeze_point_is_where_the_docs_say_it_is` が持っていて、
    テンプレートが動けばそのテストが落ちて新しい値を教える。
    """
    return window_end_z(p) - window_front_z(p)


def window_length_shortfall(p: dict) -> float:
    """指定した窓長のうち届かなかった分 [mm]。届いていれば 0。"""
    return max(p["window_length"] - window_length_effective(p), 0.0)


def window_open_z(p: dict) -> float:
    """窓が実際に開き始める z（クラウン x=0）。天井がリード面を横切る点。

    設計値は `window_front_z`（＝`tip_rail_width`）。外殻（ビーク下の肉厚）で
    天井が頭打ちになるとここが後ろへずれるので、検証と逆算はこの実効値で見る。
    """
    lo, hi = 0.0, bore_start_z(p)
    if cavity_roof_y(p, hi) <= cut_top_y(p, hi):
        return hi
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if cavity_roof_y(p, mid) > cut_top_y(p, mid):
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def baffle_plateau_end_z(p: dict) -> float:
    """バッフル天井の平坦区間（棚）が終わる z＝段／ランプの起点。"""
    return baffle_plateau(p) * bore_start_z(p)


def baffle_step_end_z(p: dict) -> float:
    """段（ライザー）が終わる z。ステップ型以外では棚の終わりと同じ扱いでよい。"""
    return min((baffle_plateau(p) + _STEP_RISER_W) * bore_start_z(p),
               bore_start_z(p))


def baffle_flat_end_z(p: dict) -> float:
    """[互換] `baffle_plateau_end_z` の旧名。"""
    return baffle_plateau_end_z(p)


#: 天井の頭打ちに使う soft-min の幅。ティップの天井は「窓がどこで開くか」を
#: 直接決めるので、ここのバイアス（最大 k/2）がそのままレール幅の誤差になる。
#: 実際 k=0.35 では 0.12mm 下がって、レールが 0.2mm 以上広がっていた。
_ROOF_SOFT_K = 0.12
#: 天井がレール基準からバッフル基準へ移る区間（σ）。
_TIP_ROOF_SPAN = 0.10


def tip_roof_y(p: dict) -> float:
    """ティップ側の平坦な天井の高さ。`tip_rail_width` から一意に決まる。

    天井がリード面を突き抜ける z がそのままレール幅なので（先端は z=0 に立つ）、
    レール幅を与えれば天井は決まる。`table_plane_y` が「ティップが z=0 に立つ」
    で決まっているのと同じ立て方で、魔法定数を置かずに実測へ合う。
    """
    return cut_top_y(p, window_front_z(p))


def baffle_plateau_y(p: dict) -> float:
    """バッフル区間の平坦な天井の高さ。`baffle_height` から決まる。"""
    gap = _TIP_GAP_FREE_RATIO * p["bore_dia"] - p["baffle_height"]
    gap = max(gap, 0.35 * p["min_wall"])
    return table_plane_y(p, 0.0) + gap


def _roof_base_y(p: dict, sigma: float) -> float:
    """バッフルが立ち上がる前の天井。ティップはレール基準、σ≳0.1 でバッフル基準。

    `_TIP_GAP_FREE_RATIO` は実測のテナーで両者が一致するよう校正してあるので、
    既定値ではこのランプ量はゼロ＝実測どおり「ボア軸に平行な平面」のまま。
    `tip_rail_width` と `baffle_height` を別々に動かしたときだけ、C1 のまま繋ぐ。
    """
    y_tip, y_bf = tip_roof_y(p), baffle_plateau_y(p)
    return y_tip + (y_bf - y_tip) * _smoothstep(sigma / _TIP_ROOF_SPAN)


def cavity_roof_y(p: dict, z: float) -> float:
    """内部空洞の天井 C(z)（ボア軸基準の絶対値、x=0 のクラウン）。

    実測ではティップ側の天井は **ボア軸に平行な平面** で σ=0.36 までフラットに続き、
    そこから傾き一定の直線ランプ、最後に S 字でボア天井へ寄る。リード面から見た
    天井高さが増えるのは、天井が上がるからではなくテーブルが下がるため。

    旧実装は「直線ランプ→指数ブレンド」を継いでいて、継ぎ目で傾きが 0.80 → 2.40 と
    3倍に飛んでいた（バッフルを横切る稜線として見えていた）。ここを実測点列の
    PCHIP にすると、同じ形を C1 のまま通せる。

    横方向のアーチ（サグ）は断面側（`_super_pts` の `nx_top`）が持つ。
    """
    sig = _cav_sigma(p, z)
    y0 = _roof_base_y(p, sig)
    y = y0 + (bore_radius(p) - y0) * _baffle_progress(p, sig)
    return _soft_min(y, shell_limit(p, z)["top"], _ROOF_SOFT_K)


def baffle_roof_y(p: dict, z: float) -> float:
    """[互換] `cavity_roof_y` の旧名。"""
    return cavity_roof_y(p, z)


# `baffle_sensitivity()` はここにあったが削除した。`w(σ)·(1−v(σ))` という手書きの
# 重みで「`baffle_height` を 1mm 上げたとき天井が下がる量」を表すつもりだったが、
# 既定形状では 1.0 を返す一方で**真の割線は 1.33**（ティップ側の soft-min と、天井が
# 床に届いてからの頭打ちで非線形になる）。これを割り算に使っていた逆算は 1.2mm の
# 変化に対して 0.4mm ずれていた。いまは `measure._baffle_from_ceiling` が
# `cavity_roof_y` そのものを二分法で逆に解くので、重み関数は要らない。


def cavity_half_width(p: dict, z: float) -> float:
    """内部空洞の半幅 W(z)。

    実測では管の径はほぼ一定（0.865〜1.00 × ボア半径）。「窓が後方で細くなる」のは
    開口の話で、管そのものは絞られていない。旧実装はこれを取り違えてスロット幅を
    直接絞っており、閉口処理と衝突して z=41 付近にくびれと縦壁を作っていた。

    `side_rail_width` は基準値からの差分だけが効く（レールを広げれば管が細り、
    結果として開口が狭くなる）。ボア端では効かない。
    """
    sig = _cav_sigma(p, z)
    w = bore_radius(p) * _pchip(_CAVITY_W, sig)
    w -= (p["side_rail_width"] - _RAIL_REF) * _pchip(_RAIL_WEIGHT, sig)
    return max(_soft_min(w, shell_limit(p, z)["half_width"]), 0.35)


def cavity_floor_y(p: dict, z: float) -> float:
    """内部空洞の床 F(z)。

    リード面からの落とし込み `D = (cut_top_y − F)/bore_radius` として持つ。D>0 の
    間だけ窓が開き、**D が 0 を横切る z が窓の終端**になる。段差もランプも要らない。

    合わせる端条件は 2 つ:
      - `window_end_z` で D=0（＝窓がそこで閉じる。`window_length` が効く）
      - `bore_start_z` で F = −bore_radius（＝遷移区間を別式で繋がなくてよい）

    **σ を写像して合わせる。振幅を掛けてはいけない。** 旧実装は実測テーブルを
    振幅方向のアフィン `a·(D(σ) − t0)` で合わせていて、`a = target/(D(1) − D(s_we))`
    が **s_we → 1 で特異**だった（s_we = `window_end_z`/`bore_start_z`）。
    `_CAVITY_D` は σ=`_CAVITY_D_ZERO` で 0 を横切るので、s_we がそこに載っている
    間だけ a≈1 になる —— そして 3 サイズともたまたま載っていた
    （soprano 0.8408 / tenor 0.8380 / 旧 alto 0.8382）。**「揃い」に幾何が荷重を
    掛けていた**わけで、アルトの窓を実測（`window_length` 35.02 → 38.67）へ直した
    とたんに s_we が 0.9078 へ動き、分母が −0.367 → −0.098 に縮んで **a=3.48**。
    床が丸ごと 3.5 倍深くなり、先端の落とし込み D(0)=0.100（0.79mm）が 2.73mm に
    化けて**ティップレールのくさびが消えた**（空洞高さ 0.60 → 4.44mm）。
    爆発は連続していて、窓の後端からボアまでの間隔で見ると
    6.9mm で a=0.97 / 4.0mm で 3.48 / 2.0mm で 6.48 / 1.0mm で 12.30 ——
    `window_end_z` の直値 `zb − 4.0` が唯一の歯止めになっていた。
    **その直値の裏には `_floor_limit` の節点衝突も隠れていた**（同じ型の 2 つ目。
    そちらも塞いだうえで `chamber_to_bore_mm` としてパラメータに出した）。

    写像なら割り算が消える。窓を伸ばすことは「床が上がってくる位置が後ろへ動く」
    ことであって、「空洞全体が深くなる」ことではない:

      - M: 0→0, s_we→`_CAVITY_D_ZERO`, 1→1 の単調写像（3 点 PCHIP）
      - 尾側だけ端条件へ寄せる滑らかな重み g: g(0)=1, g(1)=target/D(1)

    先端は σ=0 → M(0)=0 なので **D(0) が実測のまま素通り**（`window_length` は
    先端に一切効かない ＝ 効くべきでない）。窓の終端は D(M(s_we))=0 なので
    **g が何であれ厳密**。PCHIP × 滑らかな重みなので C1 も残る。
    """
    rb = bore_radius(p)
    zb = bore_start_z(p)
    sig = _cav_sigma(p, z)
    # 写像が退化する側だけ止める。手前は `cavity_layout_error` が見ている。
    s_we = min(window_end_z(p) / zb if zb > 1e-9 else 1.0, 0.99)
    d = _pchip(_CAVITY_D, _pchip([(0.0, 0.0), (s_we, _CAVITY_D_ZERO), (1.0, 1.0)], sig))
    target = (cut_top_y(p, zb) + rb) / rb
    k = target / _pchip(_CAVITY_D, 1.0)
    d *= 1.0 + (k - 1.0) * _smoothstep(sig)
    return _soft_max(cut_top_y(p, z) - rb * d, _floor_limit(p, z))


#: 窓の区間で床の下限拘束を外す量 [mm]。
_FLOOR_RELIEF = 6.0

#: 窓の終端から拘束が立ち上がるまでの σ 幅。**このぶんは必ず [s_we, 1] に収まる
#: ように s_we を頭打ちにする** —— 収まらないと制御点が x=1.0 で重なって
#: `_pchip_table` が落ちる（下の docstring）。
_FLOOR_RAMP = 0.06


def _floor_limit(p: dict, z: float) -> float:
    """床の許容下限。**窓が開いている区間では効かせない**。

    `shell_limit["bot"]`（= −(ro − min_wall)）は「胴の底に肉厚を残す」拘束だが、
    窓の区間では胴の底はフェイシングカットで既に無い（残っている最下面はリード面で、
    窓ではそれすら無い）。ティップでは ro が小さいのでこの拘束がリード面より上に来て、
    床が押し上げられて**窓が閉じる**（z=0.85 で bot が cut_top より 0.05mm 上）。
    旧実装がロフトを z=1.2 から始めていたのはこれを避けるためだった。

    **旧実装は窓がボアに寄ると落ちた。** 制御点を
    `(0,0) (s_we,0) (min(s_we+0.06,1),1) (1,1)` と組んでいたので、
    `s_we ≥ 0.94` で第 3・第 4 節点が x=1.0 で衝突し `ZeroDivisionError`。
    閾値は `gap ≤ 0.06·zb` ＝ **サイズで変わる**:

    | | zb | 落ちる gap | 当時の壁 `zb−4.0` からの余裕 |
    |---|---|---|---|
    | soprano | 33.10 | ≤ 1.99mm | 2.01mm |
    | alto | 43.40 | ≤ 2.60mm | 1.40mm |
    | tenor | 50.00 | ≤ 3.00mm | **1.00mm** |

    `cavity_floor_y` の振幅アフィンの特異点（`5fb0bf4`）と**同じ型**で、
    **同じ壁の裏に 2 つ並んでいた**。`zb − 4.0` は幾何の成立条件ではなく、
    この 2 つを覆っていた蓋だったことになる（成立条件は `cavity_layout_error`）。

    直しは 2 つだけ ——**ランプが必ず収まるよう `s_we` を頭打ちにする**のと、
    **ランプの終わりが 1.0 に達したら末尾の節点を置かない**。既定 3 サイズの
    `s_we` は 0.8408 / 0.9078 / 0.8380 なので頭打ちは効かず、**形状は不変**。
    """
    zb = bore_start_z(p)
    s_we = min(window_end_z(p) / zb if zb > 1e-9 else 1.0, 1.0 - _FLOOR_RAMP)
    pts = [(0.0, 0.0), (s_we, 0.0), (s_we + _FLOOR_RAMP, 1.0)]
    if s_we + _FLOOR_RAMP < 1.0 - 1e-9:
        pts.append((1.0, 1.0))
    w = _pchip(pts, _cav_sigma(p, z))
    return shell_limit(p, z)["bot"] - _FLOOR_RELIEF * (1.0 - w)


# --------------------------------------------------------------- バッフル型
#
# バッフル解説図（ストレート型 / ステップ型 / カーブ型）の分類に合わせた 4 型。
# どれも「平坦な棚 → 立ち上がり → ボア天井」という同じ骨格の上に乗っていて、
# 違うのは**立ち上がり方だけ**なので、v(σ) の作り分けだけで表現する。
#
#   step      平坦な棚 → 段 → ボアへ。**実測 WindyCity がこれ**（棚が z=18mm 続く）
#   straight  棚の終わりからボア天井まで一定勾配の直線
#   rollover  ストレートの肩を `rollover_radius` で丸めたもの
#   curve     天井が低いまま粘って後半で開く（気道が絞られる＝明るくアグレッシブ）
#
# 4 型とも **v(0)=0 / v(1)=1 / 単調非減少** を構成上満たす。単調性は「天井が z に
# 対して逆流しない」＝ロフト面が折り返さないための必要条件で、ここが破れると
# `_contain` の安全網が発動して形が折れる。

#: 型ごとの `baffle_plateau`（平坦区間 σ）の実効範囲。
#:
#: 下限を 0 にしないのは、σ < `_TIP_ROOF_SPAN` (=0.10) で天井が「レール基準 →
#: バッフル基準」へ乗り移るため。そこでランプを立てると天井がリード面を横切る z が
#: 前へずれ、`tip_rail_width` の指定より細いティップレールになる（C-1b で立てた
#: 「レール幅＝天井がリード面を突き抜ける z」の関係が壊れる）。
#:
#: straight / curve の上限が短いのは**型の定義そのもの**。長い棚を許せば、それは
#: もうストレートでもカーブでもなくステップになる。UI で型ごとに調整範囲を絞る
#: 根拠はこの 1 テーブルに集約してある。
_PLATEAU_RANGE = {
    "step": (0.10, 0.70), "rollover": (0.10, 0.70),
    "straight": (0.02, 0.12), "curve": (0.02, 0.12),
}
#: ステップ型のライザー（段）の幅 σ。テナー（zb=50）で 3mm。
_STEP_RISER_W = 0.06


def baffle_plateau(p: dict) -> float:
    """平坦な天井が続く区間（σ）。型ごとの実効範囲へクランプした値。"""
    lo, hi = _PLATEAU_RANGE.get(p.get("baffle_type", "step"), (0.10, 0.70))
    return min(max(p.get("baffle_plateau", _BAFFLE_FLAT), lo), hi)


def _plateau_warp(sigma: float, a: float) -> float:
    """σ を「棚の長さ a」から実測基準 `_BAFFLE_FLAT` の尺度へ写す区分線形写像。

    [0, a] → [0, 0.36]、[a, 1] → [0.36, 1]。**a = 0.36 で恒等**なので、既定値では
    実測カーブ `_CAVITY_C` がそのまま出る（既定形状を動かさないための条件）。
    折れ点 σ=a では基準カーブの傾きがほぼ 0（`_CAVITY_C` は 0.36 まで完全に平坦で
    0.38 でようやく 0.013）なので、合成しても実質 C1 のまま。
    """
    f = _BAFFLE_FLAT
    if sigma <= a:
        return f * (sigma / a) if a > 1e-9 else f
    return f + (1.0 - f) * (sigma - a) / (1.0 - a)


def _v_step(p: dict, sigma: float) -> float:
    """ステップ型。`baffle_step_rise` で段の切り立ち具合を足す。

    `baffle_step_rise=0` かつ `baffle_plateau=_BAFFLE_FLAT` のとき、v は
    `_pchip(_CAVITY_C, σ)` と**厳密に一致する**（実測そのもの）。既定値をこれに
    してあるので、型の作り直しで既定形状は 1μm も動かない。
    """
    a = baffle_plateau(p)
    # **上限のクランプは外した**（Phase 4-E B-2）。以前は 0.85 で頭打ちにして
    # いたが、`src` は「上限は未測定」で**止めている理由が無かった**。r は
    # `r·smoothstep + (1−r)·base` の混合重みなので 1 を超えると外挿になるだけで、
    # 式は壊れない。壁は掃引で測って `ParamSpec.hard_max` に置く。
    # 負のほうは下の `if` が `base` を返すので**構造として効かない** ——
    # 下限 0 の理由は測定ではなくこの分岐そのもの。
    r = p.get("baffle_step_rise", 0.0)
    base = _pchip(_CAVITY_C, _plateau_warp(sigma, a))
    if r <= 0.0:
        return base
    return r * _smoothstep((sigma - a) / _STEP_RISER_W) + (1.0 - r) * base


def _v_straight(p: dict, sigma: float) -> float:
    """ストレート型。棚の終わりからボア天井まで一定勾配。

    y = y0 + (bore_r − y0)·v で y0 は棚の区間で定数なので、**v が線形なら
    断面の天井線もそのまま直線**になる（型の特徴がそのまま出る）。
    """
    a = baffle_plateau(p)
    return min(max((sigma - a) / (1.0 - a), 0.0), 1.0)


def _v_rollover(p: dict, sigma: float) -> float:
    """ロールオーバー型。ストレートの肩を `rollover_radius` で丸めた形。

    直線に放物線フィレットを付ける（t<w で t²/2w、以降 t−w/2 を正規化）。
    接線連続なので肩に稜線が残らない。w は肩の丸みを σ 尺度へ直したもの。
    """
    a = baffle_plateau(p)
    span = max((1.0 - a) * bore_start_z(p), 1e-6)
    # 上限 0.9 は外した（Phase 4-E B-2。`src` が空 ＝ 止めている理由が無かった）。
    # **下限 0.02 は残す** —— 下の `f` が `u²/(2w)` で割るので w→0 で発散する。
    # `_pchip_table` の節点衝突・`cavity_floor_y` の特異点・`_chamber_weight`・
    # `facing_rise` の円弧半径に続く、割り算が潰れる同じ型の 5 つ目。
    w = max(p.get("rollover_radius", 8.0) / span, 0.02)
    t = min(max((sigma - a) / (1.0 - a), 0.0), 1.0)

    def f(u: float) -> float:
        return u * u / (2.0 * w) if u < w else u - 0.5 * w

    return f(t) / f(1.0)


def _v_curve(p: dict, sigma: float) -> float:
    """カーブ型。天井が低いまま粘って後半で開く＝ティップ側で気道を絞る。

    `baffle_curvature` > 0 でふくらみ（明るくアグレッシブ）、< 0 でスクープ
    （早く開く＝ダーク）、0 でストレートと同じ直線。

    符号の向きは旧実装と逆。旧実装は `1−(1−t)^n` で**4型のうち最も早く開く**のに、
    `brightness._BAFFLE_BONUS` では最も明るい 0.24 が当たっていた（解説図の
    「メタリックでアグレッシブな音」とも合わない）。幾何と音響の向きをここで揃える。

    スクープ側に `t^m` (m<1) を使わないのは、**t=0 で傾きが発散する**から。
    c=−1 だと棚の直後 0.7mm で天井が 3.4mm 立ち上がる垂直壁になり、ルールドロフトの
    弦誤差が 1.4mm に達した。`1−(1−t)^n` なら t=0 の傾きが n で有限に収まる
    （c=−1 で 0.87mm/mm）。ふくらみ側とスクープ側は、この式で互いの鏡像になる。
    """
    a = baffle_plateau(p)
    # ±1 のクランプは外した（Phase 4-E B-2）。`src` は「パラメータの定義域
    # そのもの」と書いてあったが、n = 2^(1.6|c|) も t^n も |c|>1 で普通に解ける
    # ので、**定義域を定義域で説明した循環**だった。壁は掃引で測る。
    c = p.get("baffle_curvature", 0.5)
    t = min(max((sigma - a) / (1.0 - a), 0.0), 1.0)
    n = 2.0 ** (1.6 * abs(c))
    return t ** n if c >= 0.0 else 1.0 - (1.0 - t) ** n


_V_BUILDERS = {"step": _v_step, "straight": _v_straight,
               "rollover": _v_rollover, "curve": _v_curve}


def _baffle_progress(p: dict, sigma: float) -> float:
    """天井の立ち上がり率 v∈[0,1]（σ=z/zb、σ=1 でボア天井）。"""
    sigma = min(max(sigma, 0.0), 1.0)
    return _V_BUILDERS.get(p.get("baffle_type", "step"), _v_step)(p, sigma)


#: 天井側の肉厚が `tip_rail_thickness` から `min_wall` へ戻るまでの区間（σ）。
_TIP_WALL_SPAN = 0.10


def _top_wall(p: dict, z: float) -> float:
    """天井の上に残す肉厚。ティップでは `tip_rail_thickness` を使う。

    ティップレールは**意図的に min_wall より薄い**（実測 1.25mm vs min_wall 1.8mm）。
    ここを一律 min_wall で拘束すると、天井が beak−min_wall まで押し下げられて
    窓の開き始めが 0.3mm ほど後ろへずれ、クラウンのレール幅が広くなる。
    """
    tip = min(p.get("tip_rail_thickness", p["min_wall"]), p["min_wall"])
    return tip + (p["min_wall"] - tip) * _smoothstep(
        _cav_sigma(p, z) / _TIP_WALL_SPAN)


def shell_limit(p: dict, z: float) -> dict:
    """z における空洞の許容包絡 {top, bot, half_width}。

    胴（真円）とビーク面から決まる「残る材料」の内寸。テーブルカットは含めない —
    窓はカット面より下へ抜けて初めて開口になるので、下端まで拘束すると窓が閉じる。
    天井側だけ肉厚が `_top_wall`（ティップではレール厚）、他は min_wall。
    """
    ro = outer_radius(p, z)
    mw = p["min_wall"]
    return {
        "top": min(ro, beak_apex_y(p, z)) - _top_wall(p, z),
        "bot": -(ro - mw),
        "half_width": ro - mw,
    }


#: スロート（最狭部）が始まる位置（窓終端→ボア開始 を 1 とした比）。
_THROAT_T = 0.75


def _throat_n(p: dict) -> float:
    return (_chamber_n(p) + 2.0) / 2.0


#: チェンバー断面のスーパー楕円指数（面積計算・逆算用の等方値）。
_CHAMBER_N = {"round": 2.2, "square": 3.8, "horseshoe": 2.6, "flat_sidewall": 3.0}
#: チェンバー断面の (x指数, y指数)。フラットサイドウォールだけ異方
#: （左右が垂直な平面・上下が丸い）。ロフトは全長で同じ族を通すので、
#: 形状の作り分けはこの2値の補間だけで行う。
_CHAMBER_NXY = {"round": (2.2, 2.2), "square": (3.8, 3.8),
                "horseshoe": (2.6, 2.6), "flat_sidewall": (7.0, 2.4)}


def _chamber_n(p: dict) -> float:
    return _CHAMBER_N.get(p.get("chamber_shape", "round"), 2.2)


def throat_radius(p: dict) -> float:
    """スロート（遷移部最狭）の等価半径。断面積 = throat_ratio × ボア断面積。"""
    k = _superellipse_shape_factor(_throat_n(p))
    return bore_radius(p) * math.sqrt(p["throat_ratio"] * math.pi / (4.0 * k))


# `throat_ratio_from_radius` / `chamber_ratio_from_width` はここにあったが削除した。
# 断面積比の逆算をスーパー楕円の閉じた式で持つと、実測から起こした断面（`_CAVITY_W`
# と `_section_exponents` の族）とは別物を仮定することになり、**未編集のメッシュでも
# 比 0.90〜0.94 と出ていた**。逆算は `measure._ratio_from_half_width` が
# `cavity_stations` そのものを二分探索する形に一本化してある。


def chamber_size(p: dict) -> tuple[float, float]:
    """チェンバー最大部の要求 (幅, 高さ) [mm]。外殻による頭打ちは含まない。

    実測のリファレンスはチェンバーの膨らみもスロートの狭窄も持たず、断面積が
    単調にボアへ開く（`chamber_ratio = throat_ratio = 1.0`）。比を上げると
    ラージチェンバー系の設計も作れる。
    """
    r_t = throat_radius(p)
    w0, h0 = 2.0 * r_t * _CHAMBER_W, 2.0 * r_t * _CHAMBER_H
    n_ch = _chamber_n(p)
    a_throat = superellipse_area(2.0 * r_t, 2.0 * r_t, _throat_n(p))
    base = {"yc": 0.0, "h": h0, "w": w0, "n": n_ch,
            "shape": p.get("chamber_shape", "round")}
    scale = math.sqrt(p.get("chamber_ratio", 1.0) * a_throat / section_area(base))
    return w0 * scale, h0 * scale


#: チェンバー基準形（スロート等価直径に対する 幅・高さ の倍率）。実測は横長ではなく
#: ほぼボア円のままなので 1.0 に近い。
_CHAMBER_W = 1.02
_CHAMBER_H = 0.98


def chamber_headroom_cc(p: dict, ratio_max: float) -> float:
    """`chamber_ratio` を上限まで上げたときに**まだ増やせる実効容積** [cc]。

    ここにあった `chamber_saturated()` は「チェンバー断面が**全部**外殻に当たって
    いるか」を見ていたが、実測から起こした形状では窓寄りの断面が先に当たることが無く、
    **スライダの可動域全域（比 3.0 × 最小肉厚 4.0）で永久に False** だった。
    それを根拠にしていた「頭打ち」助言は到達不能コードになっていた。

    一方で**ユーザーが困る事実の方は実在する**: テナーは比を上限 3.0 まで上げても
    実効容積が +0.86cc しか増えず、欠損円錐の目標 18.02cc に届かない。判定すべきは
    「断面が外殻に接しているか」という幾何ではなく「**上限まで上げて目標に届くか**」
    という到達可能量。助言の側がその数字を持てるよう、真偽値ではなく cc を返す。
    """
    now = cavity_volume_cc(p)["effective_cc"]
    top = cavity_volume_cc(dict(p, chamber_ratio=ratio_max))["effective_cc"]
    return max(top - now, 0.0)


def chamber_clamped_at(p: dict, z: float) -> bool:
    """その z の断面幅が外殻で頭打ちになっているか（逆算可否の判定に使う）。"""
    s = min(cavity_stations(p), key=lambda q: abs(q["z"] - z))
    return s["w"] >= 2.0 * shell_limit(p, s["z"])["half_width"] - 1e-6


#: 断面をサンプルする z の刻み [mm]。ルールドロフトの弦誤差は κ·dz²/8 で、
#: 天井の曲率が最大の区間（κ≒0.45 /mm）でも 0.09mm に収まる密度。旧実装のように
#: 区間ごとに別の t 列を持たない（列の切り替わり自体が継ぎ目になる）。
_STATION_DZ = 1.6


#: 窓が窓として成立する最小の長さ [mm]。
#:
#: `window_end_z` は既に `bore_start_z − chamber_to_bore_mm` で頭打ちに
#: してあるので、
#: 「窓がボアに飲まれる」側は防いである。防いでいないのは**その頭打ちが
#: 窓の始まりを追い越す**場合で、窓の長さが 0 以下になる。ステーションの
#: 最小間隔 0.40mm を数枚は置ける値として 2.0mm を採る。既定の窓長は
#: soprano 27.6 / alto 37.6 / tenor 41.5mm で、下限まで一桁ある。
_MIN_WINDOW_SPAN_MM = 2.0


def cavity_layout_error(p: dict) -> str | None:
    """空洞の z 配置が成立しないときに理由を返す。成立していれば `None`。

    空洞は **窓 → チェンバー → スロート → ボア** の順に並ぶ。この並びは
    `overall_length` / `bore_length` / `window_length` の 3 つが決めていて、
    **どれか 1 つのレンジでは表せない**。`ParamSpec` はパラメータを 1 本ずつしか
    見ないので、3 つとも各自のレンジ内なのに配置が潰れる組合せが作れる ——
    実際 `overall_length` を下限 60.0、`bore_length` を上限 60.0 にすると
    `bore_start_z = 0` で、窓が始まる前にボアが始まる。**UI の 2 本のスライダから
    到達できる。**

    潰れたまま進むと 2 段階で壊れる:

    - `window_end_z <= window_start_z`: `window_end_z` の `zb − 4.0` 側の頭打ちが
      窓の始まりを追い越し、**窓の無い空洞**ができる。ステーションは生成できて
      しまうので異常が出ない（テナーで `bore_start_z` を 1.0mm まで詰めると
      ステーション 2 枚・実効容積 19.18cc という数字を平然と返す）。
    - `bore_start_z < window_start_z`: 刻む区間そのものが空になり、
      `_station_zs` が `IndexError: list index out of range` で落ちる。

    後者だけ直すと前者が残るので、**成立条件のほうを 1 箇所に書いて弾く**。
    """
    z0, z_we, zb = window_start_z(p), window_end_z(p), bore_start_z(p)
    # チェンバー→ボアの遷移は**長さを持たなければならない**。0 にすると
    # `s_we = s_th = 1` で `_chamber_weight` の制御点が x=1 で重なり、
    # `_pchip_table` が `ValueError` を上げる（掃引 `cad/windycity/sweep_limits.py`
    # で発見。3 サイズとも壁はぴったり 0 で、0.01 は通る）。**上げさせない**
    # ——`ParamSpec.hard_min` でも止めているが、成立条件はここに 1 箇所書く。
    gap = p.get("chamber_to_bore_mm", _CHAMBER_TO_BORE_DEFAULT_MM)
    if gap <= 0.0:
        return (f"チェンバー→ボアの遷移が {gap:.2f}mm ＝ 長さを持ちません。"
                f"ウィンドウの後端とボアの始まりが同じ位置になり、"
                f"チェンバーの区間が消えます。0 より大きい値にしてください。")
    # ティップ開きは**正でなければならない**。0 だと radial のフェイシング
    # 円弧半径が定まらず `facing_rise` が落ちる（掃引で発見。`params_error` は
    # `None` を返していたので、素の `ZeroDivisionError` が上がっていた）。
    # `ParamSpec.hard_min = 0.05` でも止めているが、成立条件はここに 1 箇所書く。
    if p["tip_opening"] <= 0.0:
        return (f"ティップ開きが {p['tip_opening']:.2f}mm ＝ リードとの隙間が"
                f"ありません。フェイシングの円弧が定義できず、息の入口も"
                f"閉じます。0 より大きい値にしてください。")
    # ボアも**長さを持たなければならない**。`bore_length <= 0` は「ボアが部品の
    # 外から始まる」で、削る円柱の高さが `overall_length − zb + 1.5` ＝
    # `bore_length + 1.5` なので、−1.5 を割ると `Solid.make_cylinder` が
    # `Null TopoDS_Shape` を返してビルドが素の `ValueError` で落ちる
    # （B-3 の掃引で発見。3 サイズとも −1.5 までソリッド 1 個、−2.0 で落ちる）。
    # **落ちる手前の 0〜−1.5 も通してはいけない** —— 円柱が 1 ビットも削らない
    # ので「ボア長を縮めるほど体積が増える」逆向きの形になり、しかも
    # `cavity_stations` は平然と通る（段 1〜2 は −21mm まで素通りした）。
    if p["bore_length"] <= 0.0:
        return (f"ボア長が {p['bore_length']:.1f}mm ＝ 長さを持ちません。"
                f"ボアの始まり z={zb:.1f}mm が全長 "
                f"{p['overall_length']:.1f}mm の外にあり、円筒が 1 ビットも"
                f"削りません。0 より大きい値にしてください。")
    if z_we - z0 >= _MIN_WINDOW_SPAN_MM:
        return None
    return (f"空洞の並び（窓→チェンバー→スロート→ボア）が成立しません: "
            f"窓が z {z0:.2f}→{z_we:.2f}mm ＝ 長さ {z_we - z0:+.2f}mm しか残らず、"
            f"最低 {_MIN_WINDOW_SPAN_MM:.1f}mm 要ります。"
            f"ボアの始まり（全長 {p['overall_length']:.1f} − ボア長 "
            f"{p['bore_length']:.1f} ＝ {zb:.2f}mm）が手前すぎるためで、"
            f"「チェンバー→ボアの遷移」を縮める / ボア長を短く / 全長を長く "
            f"すれば直ります"
            f"（ウィンドウ長 {p['window_length']:.1f}mm はこの場合効きません —— "
            f"窓の後端は {zb:.2f} − チェンバー→ボアの遷移 "
            f"{p.get('chamber_to_bore_mm', _CHAMBER_TO_BORE_DEFAULT_MM):.1f} で"
            f"頭打ちになっています）。")


def shank_warnings(p: dict) -> list[str]:
    """シャンクの肉厚についての注意 ＝ **形は指定どおりだが刷れない**側。

    空洞は `shell_limit` が `min_wall` を守らせるのに、**ボアの円柱は素で
    引かれる**（`mouthpiece._bore_solid`）。同じ法則が片方にしか掛かって
    いないので、ボア径を上げるとシャンクの肉厚だけが黙って薄くなる。
    肉厚 0 以下は `outer_layout_error` が弾くので、**ここが受け持つのは
    0 と `min_wall` の間**（B-3 の実測で soprano は帯の上端 φ14.8 が
    肉厚 1.94mm ＝ `min_wall` 1.8 まで 0.14mm しかない）。

    `cavity_warnings` と別にしてあるのは出所が違うから ——
    あちらは空洞の法則、こちらは外形と製造。`mouthpiece.warnings()` が
    2 つを繋いで 1 枚のカードにする。
    """
    r_sh, r_bore, mw = shank_radius(p), bore_radius(p), p["min_wall"]
    wall = r_sh - r_bore
    # **ちょうど `min_wall` は警告しない。** 1e-6 の遊びが無いと、
    # `shank_dia − 2·min_wall`（23.2 − 3.6 = 19.599999999999998）を入れた
    # だけで肉厚が 1.7999999999999972 と出て警告が立つ ——
    # 利用者が「言われたとおりの値」を入れた直後に警告が出ることになる。
    if not (0.0 < wall < mw - 1e-6):
        return []
    return [f"シャンクの肉厚が {wall:.2f}mm ＝ 最小肉厚 {mw:.1f}mm を"
            f"下回っています（シャンク径 φ{r_sh * 2.0:.2f} に対しボア径 "
            f"φ{p['bore_dia']:.2f}）。形は指定どおり出ますが、この厚みでは"
            f"印刷したシャンクが割れます。ボア径を "
            f"φ{r_sh * 2.0 - 2.0 * mw:.2f}mm 以下にするか、シャンク径を "
            f"φ{p['bore_dia'] + 2.0 * mw:.2f}mm 以上にしてください。"]


def outer_layout_error(p: dict) -> str | None:
    """外形の並びが成立しないときに理由を返す。成立していれば `None`。

    条件は 6 つ。前の 3 つは「各自のレンジは守っているのに組で破れる」型で、
    `ParamSpec` は 1 本ずつしか見ないので **UI のスライダ 2 本から到達できる**。

    **(4)(5) は相手のいない 1 本の拘束**（Phase B-4b の「母線は単調」）。
    `ParamSpec.hard_*` でも表せるが、そちらは**スライダの刻みへ丸めた**値
    なので、刻みに乗らない経路（プロジェクトファイル、直に組んだ dict、
    掃引器）はすり抜ける。`hard_*` が刻みの格子で止め、ここが**真の交差**で
    断る ——B-4a の踵の床（`shank_length` / `shoulder_ratio`）と同じ組み方。
    どちらも数字は持たず `body_waist_limits` / `shoulder_fullness_limits` が
    実測プロファイル表から解いた値を使うので、置き場所が 2 つでもずれない。

    **(6) はまた「関係」**（B-3・B-4a で 5 本出たのと同じ型）。`beak_height` の
    上下は `body_dia`・全長・テーブル角・ティップ開き・ティップレール厚で動く
    ので、`hard_*` はテンプレート値での**掛け金**にしかならない ——相手を
    動かせば帯の端が壁の外へ出ることもある。成立条件はここが 1 か所で持つ。

    **(1) 最大径は本当に最大でなければならない**（`body_dia` ≥ `shank_dia`）。
    逆転すると:

    - 肩プロファイルが内向きではなく**外向き**になる。`outer_radius_nominal` は
      `r_sh + (r_max − r_sh)·shape` なので `r_max < r_sh` だと符号が反転し、
      「最大径」の位置（`heel_z`）は最大でなくなる。
    - テーブル面は「ティップがちょうど z=0 に立つ」ように `outer_radius_nominal(0)`
      から引くので、胴が細るとテーブルごと上がり、傾いた平面が痩せた胴を
      斜めに抜ける。**テナー既定 ＋ `body_dia` 下限 18.0 でソリッドが 2 個**に
      割れる（掃引 `cad/windycity/sweep_outer.py` で発見。`is_valid` は True の
      まま返るので、面数や体積を見ているだけでは気づけない）。

    ソプラノとアルトはたまたま割れずに残るが、**3 サイズとも最大径がシャンク径を
    下回っている**（下限 18.0 に対しシャンク径は 18.7 / 21.1 / 23.0）ので、
    割れなかったほうが偶然。サイズで挙動が変わる組合せは弾く側に倒す。

    **(2) ボアはシャンクの中に収まらなければならない**（`bore_dia` <
    `shank_dia`）。ボアの円柱（`mouthpiece._bore_solid`）は**素で引かれる** ——
    空洞のほうは `shell_limit` で `min_wall` を守らせているのに、こちらには
    同じ法則が掛かっていない。B-3 の実測では、肉厚が 0 になっても −1.0mm に
    なっても `params_error` は `None`、OCCT も**ソリッド 1 個**を返す
    （体積だけが soprano 11776 → 4541mm3 と 61% 落ちる ＝ シャンクが丸ごと
    消えて部品が短くなっている）。段 3 が「1 個か」しか見ていないので、
    掃引では捕まらない。0 と `min_wall` の間は `shank_warnings` が注意を出す。

    **(3) 踵が全長の `HEEL_FLOOR_RATIO` より前に来てはならない**（Phase B-4a）。
    `heel_z` は `max(heel_raw, 0.30·全長)` で床を持っていて、**床に当たった先は
    `shank_length` も `shoulder_ratio` も形を 1 ビットも動かさない** ——
    掃引では `shank_length` が 100mm まで、`shoulder_ratio` が 3.0 まで素通りし、
    段 1〜3 が全部 ok を返しながら応答だけが 0% になる（黙ったクランプ 8 例目）。
    しかも寸法図と仕様書は与えた数字を印字し続けるので、**図と形が食い違う**。
    床に当たる点は `shank_length_at_heel_floor` /
    `shoulder_ratio_at_heel_floor` が返し、スライダの `hard_max` は
    そこから 1 目盛り内側に置いてある。
    """
    r_max, r_sh = p["body_dia"] / 2.0, shank_radius(p)
    r_bore = bore_radius(p)
    if r_bore >= r_sh:
        return (f"ボア径がシャンク径以上です: ボア径 φ{p['bore_dia']:.2f} ≥ "
                f"シャンク径 φ{r_sh * 2.0:.2f} mm。ボアの円筒がシャンクを"
                f"丸ごと削り、ネックに挿す部分が無くなります（肉厚 "
                f"{r_sh - r_bore:+.2f}mm）。ボア径を φ{r_sh * 2.0:.2f}mm 未満に"
                f"するか、シャンク径を φ{p['bore_dia']:.2f}mm より太くして"
                f"ください。")
    if r_max < r_sh:
        return (f"最大径がシャンク径より細くなっています: 最大径 "
                f"φ{p['body_dia']:.1f} < シャンク径 φ{r_sh * 2.0:.1f} mm。"
                f"肩が最大径からシャンクへ**太る**向きになり、"
                f"「最大径」の位置（z={heel_z(p):.1f}mm）が最大でなくなります。"
                f"最大径を φ{r_sh * 2.0:.1f}mm 以上にするか、"
                f"シャンク径を φ{p['body_dia']:.1f}mm 以下にしてください。")
    if 1.0 + shoulder_ratio(p) <= 0.0:
        # 肩比 ≤ −1。踵の式の分母が 0 以下になる（掃引が素の ZeroDivisionError
        # を踏んだ点）。ここだけは「踵の z」を出せないので別文にする。
        return (f"肩の長さ比が {shoulder_ratio(p):.3f} ＝ −1 以下です。"
                f"踵の位置 (全長 − シャンク長)/(1 + 肩比) の分母が 0 以下に"
                f"なり、形が定義できません。肩の長さ比を 0 より大きくして"
                f"ください。")
    raw, floor = heel_raw(p), heel_floor(p)
    if raw < floor - 1e-9:
        return (f"シャンク平行部と肩が全長を食い尽くしています: 踵（最大径の"
                f"位置）が z={raw:.1f}mm ＝ 全長 {p['overall_length']:.1f}mm の"
                f"{HEEL_FLOOR_RATIO * 100:.0f}%（{floor:.1f}mm）より前に"
                f"来ます。この先は踵が {floor:.1f}mm で頭打ちになり、"
                f"**シャンク長も肩比も形を動かさなくなります**"
                f"（寸法図だけが与えた数字を印字し続けます）。"
                f"シャンク長を {shank_length_at_heel_floor(p):.1f}mm 以下、"
                f"または肩の長さ比を {shoulder_ratio_at_heel_floor(p):.3f} "
                f"以下にしてください。")
    # (4)(5) 母線は単調（Phase B-4b）。**壊れ方が 4 通りあるので、名指しは
    # 症状の出ているほうを選ぶ** ——壁のすぐ外では逸脱量が 1µm に満たず、
    # 量を印字しても「0.00mm」としか出ない。どこで何が起きるかを言う。
    heel = heel_z(p)
    w_lo, w_hi = body_waist_limits()
    w = body_waist(p)
    if not (w_lo <= w <= w_hi):
        az, _ = outer_apex(p)
        if abs(az - heel) > 1e-3:
            why = (f"最大径が踵（z={heel:.1f}mm）ではなく z={az:.1f}mm へ"
                   f"移ります")
        else:
            why = f"胴が z={body_dip(p)[0]:.1f}mm で太るのをやめます"
        return (f"胴の膨らみ {w:+.3f} では母線が単調でなくなります: {why}。"
                f"「最大径に向かって単調に太る」が崩れると、リガチャー座"
                f"（`ligature_seat_range`）が最大径ではない所に置かれます"
                f"——**形は通り、OCCT もソリッド 1 個を返す**ので、"
                f"出来上がりを見ても気づけません。"
                f"{w_lo:+.3f}〜{w_hi:+.3f} の範囲にしてください。")
    k_lo, k_hi = shoulder_fullness_limits()
    k = shoulder_fullness(p)
    if not (k_lo <= k <= k_hi):
        _, dr = shoulder_dip(p)
        r_sh = shank_radius(p)
        if dr < r_sh - 1e-9:
            why = (f"肩の途中の最小半径 {dr:.3f}mm がシャンク半径 "
                   f"{r_sh:.3f}mm を下回り、えぐれます ——**最薄の肉厚が"
                   f"シャンクではなくそこ**になるので、肉厚の注意の数字も"
                   f"甘くなります")
        else:
            why = f"肩が z={shoulder_bulge(p)[0]:.1f}mm で細るのをやめます"
        return (f"肩の張り {k:+.3f} では母線が単調でなくなります: {why}。"
                f"「最大径からシャンクへ単調に細る」が崩れます ——"
                f"**形は通り、OCCT もソリッド 1 個を返す**ので、"
                f"出来上がりを見ても気づけません。"
                f"{k_lo:+.3f}〜{k_hi:+.3f} の範囲にしてください。")
    bh = p.get("beak_height")
    if bh is not None:
        top, flat = beak_height_at_body_top(p), beak_height_flat(p)
        z_bite = _BEAK_BITE * p["overall_length"]
        if bh > top:
            return (f"ビーク高さ {bh:.2f}mm がバイトポイント（z="
                    f"{z_bite:.1f}mm）での胴の全高 {top:.2f}mm を超えています。"
                    f"ビークは切除ソリッドなので、稜線が胴の外へ出ると"
                    f"**そこは何も削られず**、上面は胴のままになります ——"
                    f"「くわえたときの口の開き量」という `beak_height` の"
                    f"定義が成り立たなくなり、寸法図だけが与えた数字を"
                    f"印字し続けます。{top:.2f}mm 以下にするか、最大径か"
                    f"全長を大きくしてください。")
        if bh < flat:
            return (f"ビーク高さ {bh:.2f}mm ではビーク稜線が**前下がり**に"
                    f"なります（水平になるのは {flat:.2f}mm）。ティップ側の"
                    f"頂点はテーブル＋ティップ開き＋ティップレール厚で"
                    f"決まっているので、これを下回るとビークがティップから"
                    f"後ろへ向かって低くなります ——実測 18.0° の"
                    f"「ティップからバイトへ立ち上がる直線ランプ」ではもはや"
                    f"ありません。{flat:.2f}mm 以上にしてください。")
    return None


def _station_zs(p: dict) -> list[float]:
    """空洞ステーションの z 列（ティップ→ボア）。

    基本は等間隔だが、**曲率が高い2箇所だけ細かく刻む**:
      - ノーズ（z 小）: 外形が急に太るので、空洞の半幅も外殻に押されて速く動く
      - 窓の後端付近: 実物は床がほぼ垂直に立ち上がる（窓のバックウォール）
    ここが疎だとルールドロフトが直線の楔になり、実物には無い折れ面が出る。
    """
    # 刻む前に配置そのものを確かめる。潰れていると下の `out[0]` が IndexError に
    # なるが、その手前に「落ちないが嘘の分解を返す」帯があるので理由ごと弾く。
    bad = cavity_layout_error(p)
    if bad:
        raise ValueError(bad)
    z0 = window_start_z(p)
    zb = bore_start_z(p)
    z_we = window_end_z(p)
    z_th = z_we + _THROAT_T * (zb - z_we)
    n = max(int(math.ceil((zb - z0) / _STATION_DZ)), 8)
    zs = {z0 + (zb - z0) * i / n for i in range(n + 1)}
    zs |= {z_we, z_th, zb}                 # role の境界は必ずステーションを置く
    # ティップ: 管が z=1→4 で半幅 3.5→8.1mm と一気に開く（レールが先端を一周する
    # ぶん管が内側へ入るため）。ここが疎だとロフトが直線の楔になり、窓の縁が
    # 多角形に見える。0.35mm 刻みで z=4.6 まで、その後 0.7mm 刻みで 6.7 まで。
    zs |= {z0 + 0.35 * i for i in range(1, int((4.6 - z0) / 0.35) + 1)}
    zs |= {4.6 + 0.7 * i for i in range(1, int(3.0 / 0.7) + 1)}
    zs |= {z_we - 1.5 + 0.5 * i for i in range(1, int(3.5 / 0.5))}
    # バッフルの棚の終わり。ここで v の傾きが 0 から立ち上がる（型による）。
    z_pl, z_st = baffle_plateau_end_z(p), baffle_step_end_z(p)
    zs |= {z_pl}
    # 切り立った段を作ったときだけ、段の終わりも折れ目として置く。区間の細分は
    # 下の `_refine_for_roof` が弦誤差を見て自動でやる。既定（rise=0）では段が
    # 無いので**足さない** — 足すと STEP 側の面数が理由もなく増える。
    if p.get("baffle_step_rise", 0.0) > 1e-9 and p.get("baffle_type") == "step":
        zs |= {z_st}
    out = sorted(z for z in zs if z0 - 1e-9 <= z <= zb + 1e-9)
    # 近すぎる z は捨てる。ロフトが "Segments do not have sufficient separation" で
    # 落ちるだけでなく、生き残っても薄いセグメントが局所的な面の乱れを作る
    # （窓の輪郭に幅 0.2mm ほどの切り欠きが出ていた）。意図的な最小間隔 0.5mm より
    # 十分小さい 0.4mm を境にする。境界 z は必ず残し、近すぎる隣を置き換える。
    keep = [out[0]]
    for z in out[1:]:
        if z - keep[-1] > 0.40:
            keep.append(z)
        elif z in (z_we, z_th, zb, z_pl, z_st):
            keep[-1] = z
    return _refine_for_roof(p, keep)


#: 天井の弦誤差の許容値 [mm]。**既定（実測 WindyCity）の弦誤差 0.132mm がこの値の
#: すぐ下に来るようにしてある**。既定のステーション列を動かさないためで、ここを
#: 下げると既定の形が変わり、C-1b の校正（ティップレール幅 0.891mm）と
#: `verify_base.py` の全項目、STEP の面数まで一斉に動く。実測形状そのものが
#: 「この粗さで足りる」という基準になっている、という立て方。
_ROOF_CHORD_TOL = 0.14
#: 分割の下限間隔 [mm]。ノーズで既に 0.35mm 刻みを使っていて実績がある値。
_ROOF_MIN_DZ = 0.35


def _refine_for_roof(p: dict, zs: list[float]) -> list[float]:
    """天井が急な区間を二分割する。

    ルールドロフトは断面間を**直線**で結ぶので、等間隔のままだと勾配の大きい所で
    弦が内側へ落ちて実際の形が痩せる（`baffle_curvature=-1` で 1.41mm、
    `baffle_step_rise=0.8` で 0.54mm）。中点で弦との差を見て割るだけの素朴な適応
    分割で、既定の形状には（許容値の立て方により）一切手を入れない。
    """
    out = list(zs)
    i = 0
    while i < len(out) - 1 and len(out) < 400:
        a, b = out[i], out[i + 1]
        m = 0.5 * (a + b)
        sag = abs(cavity_roof_y(p, m)
                  - 0.5 * (cavity_roof_y(p, a) + cavity_roof_y(p, b)))
        if b - a >= 2.0 * _ROOF_MIN_DZ - 1e-9 and sag > _ROOF_CHORD_TOL:
            out.insert(i + 1, m)
        else:
            i += 1
    return out


def _station_role(p: dict, z: float) -> str:
    zb = bore_start_z(p)
    z_we = window_end_z(p)
    if z >= zb - 1e-9:
        return "bore"
    if z >= z_we + _THROAT_T * (zb - z_we) - 1e-9:
        return "throat"
    return "window" if z <= z_we + 1e-9 else "chamber"


def _section_exponents(p: dict, z: float) -> tuple[float, float, float]:
    """断面のスーパー楕円指数 (nx, ny, nx_top)。z に沿って**滑らかに**変える。

    途中で断面の「種類」を切り替えるとロフトが点対応を失ってねじれるので、族は
    ひとつに保ち指数だけを動かす。窓区間は側壁がほぼ垂直（nx 大）、チェンバーは
    `chamber_shape`、スロートとボアは真円寄り。

    `nx_top` は天井の横アーチ（`_TOP_ARCH` 参照）。ティップ側だけ小さくして
    アーチを深くし、σ が進むと `nx` に戻る＝後方は現行どおり。
    """
    zb = bore_start_z(p)
    z_we = window_end_z(p)
    s_we = z_we / zb if zb > 1e-9 else 1.0
    s_th = (z_we + _THROAT_T * (zb - z_we)) / zb if zb > 1e-9 else 1.0
    s_ch = 0.5 * (s_we + s_th)
    nt = _throat_n(p)
    nx_ch, ny_ch = _CHAMBER_NXY.get(p.get("chamber_shape", "round"), (2.2, 2.2))
    sig = _cav_sigma(p, z)
    nx = _pchip([(0.0, _SECTION_NX), (s_we, _SECTION_NX), (s_ch, nx_ch),
                 (s_th, nt), (1.0, 2.0)], sig)
    ny = _pchip([(0.0, _SECTION_NY), (s_we, _SECTION_NY), (s_ch, ny_ch),
                 (s_th, nt), (1.0, 2.0)], sig)
    nx_top = min(_pchip(_TOP_ARCH, sig), nx)
    return nx, ny, nx_top


def _chamber_weight(p: dict, z: float) -> float:
    """チェンバー区間（窓終端→スロート）で 1、その外で 0 になる滑らかな重み。"""
    zb = bore_start_z(p)
    if zb <= 1e-9:
        return 0.0
    s_we = window_end_z(p) / zb
    s_th = (window_end_z(p) + _THROAT_T * (zb - window_end_z(p))) / zb
    return _pchip([(0.0, 0.0), (s_we, 0.0), (0.5 * (s_we + s_th), 1.0),
                   (s_th, 0.0), (1.0, 0.0)], _cav_sigma(p, z))


def _ratio_scale(p: dict, z: float) -> float:
    """`chamber_ratio` / `throat_ratio` を断面の相似スケールとして滑らかに効かせる。

    比 1.0 では実測どおり「単調にボアへ開く」形（実物にはチェンバーの膨らみも
    スロートの狭窄も無い）。比を上げるとその区間だけ相似に太る。ボア端では
    必ず 1.0 に戻る（ボア径はボア径のまま）。

    スロートの重み `w_th` は**窓の終端から**立ち上げる。以前は窓終端とスロートの
    中点から立ち上げていて、効く区間がアルトで 4.6mm しかなかった（実測形状は
    ボアが全長の半分以上を占めるので、チェンバー〜スロートの区間自体が短い）。
    「スロートを 0.7 に絞る」で上位共鳴が 2.5Hz しか動かず、設計ノブとして死んでいた。
    窓終端まで広げると 7.4mm・4.9Hz になる。**比 1.0 では `√1.0−1 = 0` なので
    既定形状は 1 ビットも動かない**（`verify_base` の数値が不変であることで確認）。
    """
    zb = bore_start_z(p)
    if zb <= 1e-9:
        return 1.0
    s_we = window_end_z(p) / zb
    s_th = (window_end_z(p) + _THROAT_T * (zb - window_end_z(p))) / zb
    w_th = _pchip([(0.0, 0.0), (s_we, 0.0), (s_th, 1.0), (1.0, 0.0)],
                  _cav_sigma(p, z))
    ch = math.sqrt(max(p.get("chamber_ratio", 1.0), 0.05)) - 1.0
    th = math.sqrt(max(p.get("throat_ratio", 1.0), 0.05)) - 1.0
    return 1.0 + ch * _chamber_weight(p, z) + th * w_th


def cavity_stations(p: dict) -> list[dict]:
    """内部空洞ロフトの断面ステーション列。

    各要素: {z, yc, h, w, nx, ny, n, role, shape}。ティップ側→ボア側の順。
    role は "window" / "chamber" / "throat" / "bore"（z 範囲から決まるラベルで、
    形状の作り分けではない — 管は最初から最後まで1本の連続体）。
    """
    horseshoe = p.get("chamber_shape", "round") == "horseshoe"
    stations: list[dict] = []
    for z in _station_zs(p):
        floor = cavity_floor_y(p, z)
        ceil_ = cavity_roof_y(p, z)
        half = cavity_half_width(p, z)
        k = _ratio_scale(p, z)
        nx, ny, nx_top = _section_exponents(p, z)
        yc, h = (floor + ceil_) / 2.0, max(ceil_ - floor, 0.6)
        stations.append({
            "z": z, "yc": yc, "h": h * k, "w": 2.0 * half * k,
            "nx": nx, "ny": ny, "n": ny, "nx_top": nx_top,
            "notch": _chamber_weight(p, z) if horseshoe else 0.0,
            "role": _station_role(p, z),
            "shape": p.get("chamber_shape", "round"),
        })
    # ボア端は厳密に真円。ここが一致していないと後段のボア円筒との合わせ目が段になる。
    rb = bore_radius(p)
    stations[-1] = {**stations[-1], "yc": 0.0, "h": 2.0 * rb, "w": 2.0 * rb,
                    "nx": 2.0, "ny": 2.0, "n": 2.0, "nx_top": 2.0,
                    "shape": "round"}
    return [_contain(p, s) for s in stations]


def cavity_sections(p: dict) -> list[dict]:
    """内部空洞ロフト用の断面列 [{z, pts}]（ティップ→ボアの z 昇順）。"""
    return [{"z": s["z"], "pts": section_pts(s)} for s in cavity_stations(p)]


def _contain(p: dict, s: dict) -> dict:
    """[安全網] ステーションを `shell_limit()` の内側へ確実に収める。

    W/C/F は既に `_soft_min` で外殻に収まるよう作ってあるので、通常ここは
    発動しない。極端なパラメータで破れたときだけ効く最後の砦として残す
    （`min`/`max` なので発動すれば折れる。発動＝形状破綻の兆候）。

    窓（role == "window"）の下端だけは拘束しない。窓はテーブルカット面より下へ
    抜けて初めて開口になるので、下端を clamp すると窓が閉じてしまう。
    """
    lim = shell_limit(p, s["z"])
    top = min(s["yc"] + s["h"] / 2.0, lim["top"])
    bot = s["yc"] - s["h"] / 2.0
    if s["role"] != "window":
        bot = max(bot, lim["bot"])
    bot = min(bot, top - 0.6)
    w = min(s["w"], 2.0 * lim["half_width"])
    return {**s, "yc": (top + bot) / 2.0, "h": top - bot, "w": w}


def chamber_max_station(stations: list[dict]) -> dict:
    """チェンバー区間のうち断面積が最大のステーション。"""
    ch = stations_by_role(stations, "chamber")
    if not ch:
        return max(stations, key=section_area)
    return max(ch, key=section_area)


def stations_by_role(stations: list[dict], role: str) -> list[dict]:
    return [s for s in stations if s.get("role") == role]


# ---------------------------------------------------------------- 断面ポリゴン

def _superellipse_shape_factor(n: float) -> float:
    """スーパー楕円の面積係数 k（A = w·h·k）。真円 n=2 で π/4。"""
    g1 = math.gamma(1.0 + 1.0 / n)
    g2 = math.gamma(1.0 + 2.0 / n)
    return (g1 * g1) / g2


def superellipse_area(w: float, h: float, n: float) -> float:
    return w * h * _superellipse_shape_factor(n)


#: 全断面で固定する頂点数（+X 始点・反時計回り）。ルールドロフトがねじれない。
#: ボア円での弦誤差は 72 点でも 0.008mm（メッシュ許容 0.02mm より小さい）。
_SECTION_SAMPLES = 72 


def _super_pts(yc: float, h: float, w: float, nx: float, ny: float,
               samples: int = _SECTION_SAMPLES,
               nx_top: float | None = None) -> list[tuple[float, float]]:
    """スーパー楕円の閉ポリゴン。上半分だけ別の x 指数を使える。

    実測の天井は**横方向にアーチ**していて、そのサグは z によらずほぼ一定
    （x=7mm で 0.31mm、z=3〜16 で 0.33/0.32/0.31/0.30）。上下同じ指数だと
    サグが断面高さ h に比例してしまい、h が 0.7mm しかないティップでは
    落差 0.07mm しか出ない。天井が平板のままだと窓がリード面を一度に
    突き抜けるので、**ティップレールがコーナーで消える**（実測 0.02mm）。

    ny>1 なら上下どちらの半分も X=±1 で接線が垂直になるので、指数を変えても
    赤道で **G1 のまま**繋がる（曲率は不連続。実物も成形の分割線でそうなっている）。
    """
    nxt = nx if nx_top is None else nx_top
    pts = []
    for i in range(samples):
        th = 2.0 * math.pi * i / samples
        c, s = math.cos(th), math.sin(th)
        n = nxt if s > 0.0 else nx
        x = (w / 2.0) * math.copysign(abs(c) ** (2.0 / n), c)
        y = yc + (h / 2.0) * math.copysign(abs(s) ** (2.0 / ny), s)
        pts.append((x, y))
    return pts


def _superellipse_pts(yc, h, w, n, samples=_SECTION_SAMPLES):
    return _super_pts(yc, h, w, n, n, samples)


def _flat_sidewall_pts(yc, h, w, samples=_SECTION_SAMPLES):
    """フラットサイドウォール：左右が垂直な平面、上下が丸い断面。"""
    return _super_pts(yc, h, w, 7.0, 2.4, samples)


def _horseshoe_pts(yc, h, w, samples=_SECTION_SAMPLES, amount: float = 1.0):
    """馬蹄：丸い天井・側壁を持ち、底の中央が上へ凹む（U字）断面。

    `amount` はノッチの効き（0 で普通のスーパー楕円）。ロフトの途中で断面の
    種類を切り替えるとねじれるので、窓→チェンバーではこの量を 0→1 で渡す。
    """
    hh = h / 2.0
    notch = 0.5 * hh * min(max(amount, 0.0), 1.0)
    width = 0.55
    pts = []
    for i in range(samples):
        th = 2.0 * math.pi * i / samples
        c, s = math.cos(th), math.sin(th)
        n = 2.6
        x = (w / 2.0) * math.copysign(abs(c) ** (2.0 / n), c)
        y = yc + hh * math.copysign(abs(s) ** (2.0 / n), s)
        if s < 0.0:
            d = th - 1.5 * math.pi
            y += notch * math.exp(-(d * d) / (2.0 * width * width))
        pts.append((x, y))
    return pts


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2.0


def section_pts(s: dict) -> list[tuple[float, float]]:
    """断面の閉ポリゴン。

    空洞ステーションは `nx`/`ny`（＋馬蹄の `notch`）を持ち、全 z で同じ族を通す。
    `nx` を持たない dict（逆算・仕様書・テストが直接組む形）は旧来の `shape`
    ディスパッチで解釈する。
    """
    yc, h, w = s["yc"], s["h"], s["w"]
    if "nx" in s:
        notch = s.get("notch", 0.0)
        if notch > 1e-6:
            return _horseshoe_pts(yc, h, w, amount=notch)
        return _super_pts(yc, h, w, s["nx"], s["ny"], nx_top=s.get("nx_top"))
    shape = s.get("shape", "round")
    if shape == "horseshoe":
        return _horseshoe_pts(yc, h, w)
    if shape == "flat_sidewall":
        return _flat_sidewall_pts(yc, h, w)
    return _superellipse_pts(yc, h, w, s.get("n", 2.0))


def section_area(s: dict) -> float:
    if "nx" in s:
        iso = (s.get("notch", 0.0) <= 1e-6
               and abs(s["nx"] - s["ny"]) < 1e-9
               and abs(s.get("nx_top", s["nx"]) - s["nx"]) < 1e-9)
        if iso:
            return superellipse_area(s["w"], s["h"], s["nx"])
        return _polygon_area(section_pts(s))
    if s.get("shape") in ("horseshoe", "flat_sidewall"):
        return _polygon_area(section_pts(s))
    return superellipse_area(s["w"], s["h"], s.get("n", 2.0))


def _clip_below(pts: list[tuple[float, float]], y_cut: float):
    """y < y_cut を捨てた閉ポリゴン（半平面での Sutherland–Hodgman）。"""
    out: list[tuple[float, float]] = []
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        in0, in1 = y0 >= y_cut, y1 >= y_cut
        if in0:
            out.append((x0, y0))
        if in0 != in1 and abs(y1 - y0) > 1e-12:
            t = (y_cut - y0) / (y1 - y0)
            out.append((x0 + (x1 - x0) * t, y_cut))
    return out


def effective_section_area(p: dict, s: dict) -> float:
    """リード面（テーブル＋フェイシング）で切った、実際に気柱になる断面積。

    ロフト用ステーションは窓を開けるためカット面より下へはみ出している。そのはみ出しは
    材料でもなければ気柱でもない（リードが塞ぐ）ので、体積にも音響の断面積にも
    数えてはいけない。旧実装は `cavity_volume_cc` だけがテーブル平面で切り直しており、
    Tier3（`openwind_bridge`）は素の `section_area` を使っていて前提が食い違っていた。
    """
    y_cut = cut_top_y(p, s["z"])
    if s["yc"] - s["h"] / 2.0 >= y_cut:
        return section_area(s)
    clipped = _clip_below(section_pts(s), y_cut)
    return _polygon_area(clipped) if len(clipped) >= 3 else 0.0


def cavity_volume_cc(p: dict) -> dict:
    """気柱体積の解析近似（断面積の台形積分 + ボア円筒）。

    Returns: total_cc(気柱全体), effective_cc(コーク位置まで＝ネック挿入分を除く)
    """
    st = cavity_stations(p)
    areas = [effective_section_area(p, s) for s in st]
    vol = 0.0
    for (a, s_a), (b, s_b) in zip(zip(areas, st), zip(areas[1:], st[1:])):
        vol += (a + b) / 2.0 * (s_b["z"] - s_a["z"])
    r = bore_radius(p)
    vol += math.pi * r * r * p["bore_length"]
    total_cc = vol / 1000.0
    neck_occupied = math.pi * r * r * p["cork_depth"] / 1000.0
    return {"total_cc": total_cc, "effective_cc": total_cc - neck_occupied}


# ---------------------------------------------------------------- 影響領域（UI）

def param_regions(p: dict) -> dict:
    """各パラメータが影響するモデル領域 {key: {z0, z1, side, label}}。"""
    length = p["overall_length"]
    fl = p["facing_length"]
    z_start = window_front_z(p)          # 窓の前縁（＝ティップレール後端）
    zb = bore_start_z(p)
    z_we = window_end_z(p)
    z_baffle_end = baffle_flat_end_z(p)
    heel = heel_z(p)

    def r(z0, z1, side, label):
        return {"z0": round(max(z0, 0.0), 2), "z1": round(min(z1, length), 2),
                "side": side, "label": label}

    return {
        "tip_opening":     r(0.0, fl, "bottom", "フェイシング（ティップ〜カーブ終端）"),
        "facing_length":   r(0.0, fl, "bottom", "フェイシング（ティップ〜カーブ終端）"),
        "facing_curve":    r(0.0, fl, "bottom", "フェイシングカーブ"),
        "tip_rail_width":  r(0.0, max(z_start + 1.0, 2.5), "bottom", "ティップレール"),
        "tip_rail_thickness": r(0.0, max(z_start + 1.0, 2.5), "all", "ティップレール厚"),
        "tip_chamfer":     r(0.0, max(tip_chamfer_len(p), 0.05), "all", "ティップ前縁の面取り"),
        "side_rail_width": r(z_start, z_we, "bottom", "サイドレール（窓の両脇）"),
        "table_angle":     r(0.0, heel, "bottom", "テーブル平面（傾き）"),
        "baffle_type":     r(z_start, zb, "all", "バッフル（窓の天井）"),
        "baffle_height":   r(z_start, z_baffle_end, "all", "バッフル（窓の天井）"),
        "baffle_plateau":  r(z_start, zb, "all", "バッフルの棚とランプ"),
        "baffle_step_rise": r(z_baffle_end, baffle_step_end_z(p), "all", "バッフルの段"),
        "baffle_curvature": r(z_baffle_end, zb, "all", "バッフルのカーブ"),
        "rollover_radius": r(z_baffle_end, zb, "all", "バッフル肩の丸み"),
        "throat_ratio":    r(zb - 6.0, zb, "all", "スロート（最狭部）"),
        "chamber_ratio":   r(z_we, zb - 2.0, "all", "チェンバー（最大部）"),
        "chamber_shape":   r(z_we, zb, "all", "チェンバー断面"),
        "bore_dia":        r(zb, length, "all", "ボア（円筒部）"),
        "bore_length":     r(zb, length, "all", "ボア（円筒部）"),
        "cork_depth":      r(length - p["cork_depth"], length, "all",
                             "シャンク（ネック挿入部）"),
        "window_length":   r(z_start, z_we, "bottom", "ウィンドウ（リード開口）"),
        "reed_width":      r(z_start, z_we, "bottom", "テーブル・窓幅"),
        "beak_height":     r(0.0, _BEAK_BLEND1 * heel, "top", "ビーク（上面）"),
        "body_dia":        r(*ligature_seat_range(p), "all", "ボディ（リガチャー座）"),
        "shank_dia":       r(heel, length, "all", "シャンク"),
        "shank_length":    r(length - shank_length(p), length, "all", "シャンク平行部"),
        "shoulder_ratio":  r(heel, shank_start_z(p), "all", "肩（最大径→シャンク径）"),
        # 歪みの 2 つは最大径（頂点）を跨がない。領域もその境で切る。
        "body_waist":      r(0.0, heel, "all", "胴（ティップ〜最大径）"),
        "shoulder_fullness": r(heel, shank_start_z(p), "all", "肩（最大径→シャンク径）"),
        "overall_length":  r(0.0, length, "all", "全体"),
        "min_wall":        r(0.0, length, "all", "全体（肉厚）"),
    }


def anatomy_regions(p: dict) -> list[dict]:
    """マウスピース各部の名称と占有 z 範囲（パラメータ非依存の純名称マップ）。"""
    length = p["overall_length"]
    fl = p["facing_length"]
    z_start = window_front_z(p)          # 窓の前縁（＝ティップレール後端）
    zb = bore_start_z(p)
    z_we = window_end_z(p)
    z_baffle_end = baffle_flat_end_z(p)
    z_th = z_we + _THROAT_T * (zb - z_we)
    heel = heel_z(p)

    def r(part, z0, z1, side):
        return {"part": part, "z0": round(max(z0, 0.0), 2),
                "z1": round(min(z1, length), 2), "side": side}

    return [
        r("ビーク", 0.0, _BEAK_BLEND1 * heel, "top"),
        r("ティップレール", 0.0, z_start, "bottom"),
        r("フェイシング", 0.0, fl, "bottom"),
        r("テーブル", 0.0, heel, "bottom"),
        r("ウィンドウ", z_start, z_we, "bottom"),
        r("サイドレール", z_start, z_we, "bottom"),
        r("バッフル", z_start, z_baffle_end, "top"),
        r("ランプ", z_baffle_end, z_we, "all"),
        r("チェンバー", z_we, z_th, "all"),
        r("ウォール", z_we, z_th, "all"),
        r("スロート", z_th, zb, "all"),
        r("ボア", zb, length, "all"),
        r("バレル", zb, heel, "all"),
        r("シャンク", heel, length, "all"),
    ]


# ---------------------------------------------------------------- 断面SVG用

def side_profile_polylines(p: dict, samples: int = 120) -> dict:
    """側面断面図のポリライン群（SVG描画用、単位mm）。"""
    length = p["overall_length"]
    heel = heel_z(p)
    zs = [length * i / (samples - 1) for i in range(samples)]
    outer_top = [(z, min(beak_apex_y(p, z), outer_radius(p, z))) for z in zs]
    outer_bot = [(z, max(-outer_radius(p, z), cut_top_y(p, z))
                  if z < heel else -outer_radius(p, z)) for z in zs]
    stations = cavity_stations(p)
    cavity_top = [(s["z"], s["yc"] + s["h"] / 2) for s in stations]
    cavity_bot = [(s["z"], max(s["yc"] - s["h"] / 2, cut_top_y(p, s["z"])))
                  for s in stations]
    r = bore_radius(p)
    cavity_top += [(length, r)]
    cavity_bot += [(length, -r)]
    return {
        "outer_top": outer_top,
        "outer_bot": outer_bot,
        "cavity_top": cavity_top,
        "cavity_bot": cavity_bot,
        # テーブルは傾斜平面。スカラーの `table_y` は返さない（図で水平線を引くと
        # 実物と 4.18° 違う嘘の断面になる）。カットが胴から外れる z まで引く。
        "table_plane": [(0.0, table_plane_y(p, 0.0)),
                        (table_cut_end_z(p), table_plane_y(p, table_cut_end_z(p)))],
        "bore_start": bore_start_z(p),
    }


# ------------------------------------------------- 断面エディタ（中央面 x=0）
#
# 上の `side_profile_polylines` は**仕様書用**で、空洞をロフトのステーション列
# （＝実際に造形される表現）で描く。ここから下は**編集用**で、法則そのもの
# （`cavity_roof_y` などの連続関数）を細かく標本化し、外殻の上限線まで返す。
# 用途が違うので別関数にしてある。
#
# 座標はどちらも「z [mm]（ティップ=0）／ y [mm]（ボア軸=0、+がビーク側）」。

#: 断面ポリラインの標本数。SVG 表示用なので tenor(107mm) で 0.45mm 刻み相当。
_SECTION_N = 240


def _section_poly(f, z0: float, z1: float, breaks=(),
                  n: int = _SECTION_N) -> list[list[float]]:
    """[z, f(z)] のポリライン。`breaks` の z は必ず標本に入れる。

    折れ目を等間隔標本の網の目から漏らすと、段や面取りが描画で丸まって
    「UI で見えている形」と「造形される形」がずれる。
    """
    zs = {z0 + (z1 - z0) * i / n for i in range(n + 1)}
    zs |= {b for b in breaks if z0 < b < z1}
    return [[round(z, 4), round(f(z), 4)] for z in sorted(zs)]


def _section_breaks(p: dict) -> tuple[float, ...]:
    """断面で傾きが折れる z（面取り端・棚の端・段の端・窓の終端・踵）。"""
    return (tip_chamfer_len(p), baffle_plateau_end_z(p), baffle_step_end_z(p),
            window_end_z(p), heel_z(p))


def section_curves(p: dict) -> dict:
    """中央面 x=0 の輪郭一式。断面エディタと検証図が同じ関数を見る。

    ここは**表示用の座標を作るだけ**で形状の法則は持たない。法則が UI 側へ
    複製されないようにするための境界で、フロントは返ってきた点を描くだけでよい。

    6 曲線 × 245 点を同じ `p` で標本化するので `params_scope` の中で回す
    （ドラッグ中に毎フレーム叩かれる経路）。
    """
    with params_scope(p):
        length = p["overall_length"]
        zb, rb = bore_start_z(p), bore_radius(p)
        heel = heel_z(p)
        z0 = window_start_z(p)
        brk = _section_breaks(p)

        def bot(z: float) -> float:
            # 踵より後ろはテーブルカットが当たらないので胴の下端そのもの。
            return max(-outer_radius(p, z), cut_top_y(p, z)) if z < heel \
                else -outer_radius(p, z)

        return {
            "outer_top": _section_poly(
                lambda z: min(outer_radius(p, z), beak_apex_y(p, z)), 0.0, length, brk),
            "outer_bot": _section_poly(bot, 0.0, length, brk),
            "reed": _section_poly(lambda z: cut_top_y(p, z), 0.0, heel, brk),
            "roof": _section_poly(lambda z: cavity_roof_y(p, z), z0, zb, brk),
            "floor": _section_poly(lambda z: cavity_floor_y(p, z), z0, zb, brk),
            "shell_top": _section_poly(
                lambda z: shell_limit(p, z)["top"], z0, zb, brk),
            "bore_top": [[round(zb, 4), round(rb, 4)],
                         [round(length, 4), round(rb, 4)]],
            "bore_bot": [[round(zb, 4), round(-rb, 4)],
                         [round(length, 4), round(-rb, 4)]],
        }


#: 断面ハンドルが有効になるバッフル型。ここに無い型では UI に出さない。
_HANDLE_TYPES = {
    "baffle_height": {"straight", "step", "curve", "rollover"},
    "baffle_plateau": {"step", "rollover"},
    "baffle_step_rise": {"step"},
    "baffle_curvature": {"curve"},
    "rollover_radius": {"rollover"},
}


def _roof_at(p: dict, key: str, value, z: float) -> float:
    return cavity_roof_y({**p, key: value}, z)


def _outer_at(p: dict, key: str, value, z: float) -> float:
    return outer_radius({**p, key: value}, z)


#: 胴の膨らみハンドルを置く u（= z/heel_z）。ビークが上面を切らなくなるのが
#: `_BEAK_BLEND1` = 0.525 なので、それより後ろでないと**断面に描かれていない所を
#: 掴む**ことになる。0.60 は離脱直後で、かつ振れ幅が最大に近い（実測 ±0.65〜0.80mm）。
_WAIST_HANDLE_U = 0.60


def shoulder_end_span(p: dict, ranges: dict) -> tuple[float, float]:
    """「肩の終わり」ハンドルが動ける z*（＝平行部の始まり）の範囲 [mm]。

    z* から 2 つのパラメータを解く:

        shank_length   = overall_length − z*
        shoulder_ratio = (z* − heel_z) / heel_z

    **この組は `heel_z` を保つ。** `heel_z = (L − shank) / (1 + ratio)` に入れると
    z* が約分されて heel_z に戻るため。片方だけ動かすと最大径の位置ごと動いて
    前方の形まで相似に伸縮してしまうので、ハンドルは必ず 2 つを一緒に書く
    （`outer_radius_nominal` の「頂点を跨がない」注記を参照）。

    `ranges` は {key: (min, max, step)}。スキーマの可動域はコンポーネント側が
    持っているので、ここでは受け取るだけにして値を二重に書かない。
    """
    length, heel = p["overall_length"], heel_z(p)
    sl_lo, sl_hi, _ = ranges["shank_length"]
    sr_lo, sr_hi, _ = ranges["shoulder_ratio"]
    lo = max(length - sl_hi, heel * (1.0 + sr_lo))
    hi = min(length - sl_lo, heel * (1.0 + sr_hi))
    return lo, max(hi, lo)


@_scoped
def outer_handles(p: dict, ranges: dict) -> list[dict]:
    """外形（胴・肩・シャンク）のドラッグハンドル。`baffle_handles` と同じ形。

    **最大径を跨ぐハンドルは 1 つだけ**（最大径そのもの）。胴の膨らみは
    z < heel_z、肩の張りとシャンク径は z > heel_z しか動かさない。

    `also` は「同じ t で一緒に書くパラメータ」。**step を持たない** ——
    従属側は主パラメータから解いた値なので、独立に丸めると解が崩れる（肩比を
    0.005 刻みに丸めると最大径の位置が 0.13〜0.17mm 動く。実測）。フロントは
    主キーだけ step へ丸め、丸めたあとの t から従属値を引き直すこと。
    """
    length, heel = p["overall_length"], heel_z(p)
    z_sh = shank_start_z(p)
    z_waist = _WAIST_HANDLE_U * heel
    z_should = heel + 0.5 * shoulder_length(p)
    z_shank = max(z_sh, length - 3.0)
    lo, hi = shoulder_end_span(p, ranges)

    def h(key, label, axis, z, unit, span, also=None, limits=None):
        # `limits` を渡すのは、そのハンドルの可動域がスキーマの生レンジより狭い
        # とき（連動ハンドル）。**span の両端と min/max は必ず同じ点を指すこと** ——
        # 片方だけ生レンジのままにすると t が別の値へ写り、連動先が解と合わなくなる。
        v_lo, v_hi = limits if limits else ranges[key][:2]
        step = ranges[key][2]
        return {
            "key": key, "label": label, "axis": axis,
            "z": round(z, 3), "y": round(outer_radius(p, z), 3),
            "value": round(float(p[key]), 4),
            # 表示用の `value` と違い、`min`/`max`/`span` は**フロントが t を
            # 逆算する係数**。桁を落とすと連動先が解からずれる（4 桁だと
            # 最大径の位置が 2.3e-5mm 動く）ので、丸めは浅くしておく。
            "min": round(v_lo, 6), "max": round(v_hi, 6),
            "span": [round(span[0], 6), round(span[1], 6)],
            "unit": unit, "step": step, "active": True,
            "group": "outer", "also": also or [],
        }

    def y_span(key, z):
        """そのパラメータを可動域の端に振ったときの、この z での外半径。"""
        v_lo, v_hi, _ = ranges[key]
        return (_outer_at(p, key, v_lo, z), _outer_at(p, key, v_hi, z))

    return [
        h("body_waist", "胴の膨らみ", "y", z_waist, "比",
          y_span("body_waist", z_waist)),
        h("body_dia", "最大径", "y", heel, "mm", y_span("body_dia", heel)),
        # t=0 が z*=hi（平行部が最短＝シャンク長が最小）、t=1 が z*=lo。
        # **可動域は生レンジより狭い**: この外では肩比が域外になり heel_z を
        # 保てない。全域を振りたければ左のスライダを使う（最大径の位置ごと動く）。
        h("shank_length", "肩の終わり", "z", z_sh, "mm", (hi, lo),
          limits=(length - hi, length - lo),
          also=[{"key": "shoulder_ratio",
                 # ここも解の係数。9 桁まで残すと残差は 1e-7mm 台に収まる。
                 "min": round((hi - heel) / heel, 9),
                 "max": round((lo - heel) / heel, 9)}]),
        h("shoulder_fullness", "肩の張り", "y", z_should, "比",
          y_span("shoulder_fullness", z_should)),
        h("shank_dia", "シャンク径", "y", z_shank, "mm",
          y_span("shank_dia", z_shank)),
    ]


@_scoped
def baffle_handles(p: dict, ranges: dict | None = None) -> list[dict]:
    """断面エディタのドラッグハンドル（断面座標つき）。

    `ranges` はスキーマ側の可動域 `{key: (lo, hi, step)}`（`Mouthpiece.
    _handle_ranges`）。**渡さないと数字がここに二重化する** —— 以前は 0.0/5.0 や
    −1.0/1.0 を直に書いていて、`ParamSpec` の壁を広げてもハンドルだけ帯で
    止まっていた。`baffle_plateau` だけは例外で、可動域が**バッフル型で変わる**
    （`_PLATEAU_RANGE`）ので今までどおり型側を使う。

    各要素:
      key/label/unit/step  対応するパラメータ
      axis                 "z" か "y"。この向きにだけ動かせる
      z, y                 いまの断面上の位置 [mm]
      value, min, max      パラメータの値と**この型での**実効範囲
      span                 [value=min のときの座標, value=max のときの座標]
      active               この型で有効か
      group                UI がどのタブで出すか（"baffle" / "outer"）
      also                 同じ t で一緒に書く従属パラメータ（`outer_handles` を参照）

    `span` を返すのは、フロントが線形補間するだけで値へ戻せるようにするため。
    形状の法則をフロントへ複製しないための仕掛けで、非線形（`_soft_min` が
    効く領域）でも、次に返ってくる `curves` が真値なので描画は自己補正する。
    """
    kind = p.get("baffle_type", "step")
    zb = bore_start_z(p)
    a = baffle_plateau(p)
    pl_lo, pl_hi = _PLATEAU_RANGE.get(kind, (0.10, 0.70))
    z_pl = baffle_plateau_end_z(p)
    rg = ranges or {}

    def lim(key: str, lo: float, hi: float) -> tuple[float, float]:
        """スキーマの可動域。無ければ従来の直値（呼び出し側が渡さない場合）。"""
        r = rg.get(key)
        return (r[0], r[1]) if r else (lo, hi)

    bh_lo, bh_hi = lim("baffle_height", 0.0, 5.0)
    sr_lo, sr_hi = lim("baffle_step_rise", 0.0, 0.85)
    cv_lo, cv_hi = lim("baffle_curvature", -1.0, 1.0)
    ro_lo, ro_hi = lim("rollover_radius", 3.0, 20.0)

    # 高さは棚の途中で掴む。`_TIP_ROOF_SPAN`（天井がレール基準からバッフル基準へ
    # 移り終わる σ）より前で掴むと、`baffle_height` を端から端まで振っても
    # ハンドルが 2mm しか動かず操作にならないので、そこから後ろに置く。
    z_h = min(max(0.5 * z_pl, _TIP_ROOF_SPAN * zb), zb)
    z_rise = min(z_pl + 0.5 * _STEP_RISER_W * zb, zb)
    z_curve = (a + 0.5 * (1.0 - a)) * zb

    def h(key, label, axis, z, lo, hi, unit, step, span):
        return {
            "key": key, "label": label, "axis": axis,
            "z": round(z, 3), "y": round(cavity_roof_y(p, z), 3),
            "value": round(float(p.get(key, 0.0)), 4),
            "min": round(lo, 4), "max": round(hi, 4),
            "span": [round(span[0], 3), round(span[1], 3)],
            "unit": unit, "step": step,
            "active": kind in _HANDLE_TYPES[key],
            "group": "baffle", "also": [],
        }

    return [
        h("baffle_height", "バッフル高さ", "y", z_h, bh_lo, bh_hi, "mm", 0.1,
          (_roof_at(p, "baffle_height", bh_lo, z_h),
           _roof_at(p, "baffle_height", bh_hi, z_h))),
        h("baffle_plateau", "棚の終わり（段の位置）", "z", z_pl, pl_lo, pl_hi, "比", 0.01,
          (pl_lo * zb, pl_hi * zb)),
        h("baffle_step_rise", "段の立ち上がり", "y", z_rise, sr_lo, sr_hi, "比", 0.05,
          (_roof_at(p, "baffle_step_rise", sr_lo, z_rise),
           _roof_at(p, "baffle_step_rise", sr_hi, z_rise))),
        h("baffle_curvature", "カーブ量", "y", z_curve, cv_lo, cv_hi, "比", 0.05,
          (_roof_at(p, "baffle_curvature", cv_lo, z_curve),
           _roof_at(p, "baffle_curvature", cv_hi, z_curve))),
        h("rollover_radius", "肩の丸みの終わり", "z",
          min(z_pl + p.get("rollover_radius", 8.0), zb), ro_lo, ro_hi, "mm", 0.5,
          (min(z_pl + ro_lo, zb), min(z_pl + ro_hi, zb))),
    ]


#: 息の通り道をサンプルする分割数。上の天井の頭打ち検査と同じ密度。
_AIRWAY_SAMPLES = 100


def airway_profile(p: dict, z: float) -> float:
    """息の通り道の高さ [mm]（リードの接地面から空洞の天井まで）。

    リードは `table_plane_y`（テーブル平面）に接して座り、ティップ側では
    マウスピース側のフェイシングがリードから逃げていく。だから息が通れる高さは
    **リード面（`cut_top_y`）ではなく接地面から測る** —— リード面で測ると
    ティップ開きぶんを丸ごと数え落とし、入口の高さが 0 に見える。
    """
    return cavity_roof_y(p, z) - table_plane_y(p, z)


def airway_min(p: dict) -> tuple[float, float, float]:
    """通り道の (入口の高さ, 最狭部の高さ, 最狭部の z)。

    **入口はティップ（z=0）で、そこがいちばん狭くあるべき** —— リード先端から
    入った息が、その奥でさらに絞られてはいけない。だから比較の相手は入口自身で、
    **閾値を置く必要がない**（この repo で根拠の無い丸い数字を増やさずに済む
    数少ない判定）。既定の 3 サイズはいずれも最狭部が z=0 ＝ 入口そのもの。
    """
    z1 = window_end_z(p)
    ent = airway_profile(p, 0.0)
    z_min, h_min = 0.0, ent
    for i in range(1, _AIRWAY_SAMPLES + 1):
        z = z1 * i / _AIRWAY_SAMPLES
        h = airway_profile(p, z)
        if h < h_min:
            z_min, h_min = z, h
    return ent, h_min, z_min


@_scoped
def cavity_warnings(p: dict) -> list[str]:
    """断面エディタに出す注意。エラーではないが利用者が知るべきこと。

    バッフルだけの話ではない（窓の前縁も後端もここで見る）ので `cavity_`。
    2 種類ある:

    - **形が法則どおりに出ていない** —— スライダの値と実際の形が食い違っていて、
      しかもエラーにはならない（天井の頭打ち・窓の前縁・窓の後端）
    - **形は指定どおりだが吹けない** —— 息の通り道が入口より奥で絞られる

    2 つ目は他と性質が違うので、**呼ぶ側が種類で絞れるように**それぞれ固有の
    語を含めてある（`inspection_values.py` は「ビーク下の肉厚」で絞っている）。
    """
    out: list[str] = []
    zb = bore_start_z(p)
    rb = bore_radius(p)
    # 天井が外殻（ビーク下の肉厚）で頭打ちになっている＝これ以上バッフルを
    # 下げても形が変わらない領域。`_soft_min` が効いている境界を素の値で見る。
    hit = None
    for i in range(101):
        z = window_start_z(p) + (zb - window_start_z(p)) * i / 100
        y0 = _roof_base_y(p, _cav_sigma(p, z))
        raw = y0 + (rb - y0) * _baffle_progress(p, _cav_sigma(p, z))
        if raw > shell_limit(p, z)["top"] - 0.02:
            hit = z if hit is None else hit
    if hit is not None:
        out.append(f"z≈{hit:.1f}mm から先で天井がビーク下の肉厚上限に当たっています。"
                   "これ以上バッフルを開いても形は変わりません（min_wall / beak_height で決まる上限）")
    d = window_open_z(p) - window_front_z(p)
    if abs(d) > 0.15:
        out.append(f"窓の開き始めが設計値より {d:+.2f}mm ずれています"
                   "（ティップレール幅が指定どおりになりません）")
    # 窓の後端側。`window_length` を上げても形が変わらない帯があり、しかも
    # スライダの可動域から到達できる（`window_length_effective` を見ること）。
    short = window_length_shortfall(p)
    if short > 0.05:
        # **止めている量を直値で書かないこと。** 以前はここが「ボアの始まり
        # {zb} − 4.0mm」で、その 4.0 は Phase 4-A で `chamber_to_bore_mm` に
        # なっている。直値のままだと、利用者がその値を 0.5 にして窓が実際に
        # 伸びても文面は 4.0 と言い続け、しかも**直し方に本命のつまみが
        # 挙がらない** —— `window_length` の説明文だけが「これを縮める」と
        # 言っていて、実際に読まれる警告が古い、という食い違いだった。
        gap = p.get("chamber_to_bore_mm", _CHAMBER_TO_BORE_DEFAULT_MM)
        out.append(f"ウィンドウ長が {short:.1f}mm 届いていません"
                   f"（指定 {p['window_length']:.1f} → 実際 "
                   f"{window_length_effective(p):.1f}mm）。窓の後端は"
                   f"チェンバー→ボアの遷移区間を残すため「ボアの始まり "
                   f"{bore_start_z(p):.1f} − チェンバー→ボアの遷移 "
                   f"{gap:.1f}mm」で頭打ちになります。ここから先へ伸ばすには"
                   f"「チェンバー→ボアの遷移」を縮める / 全長を長く / "
                   f"ボア長を短くしてください"
                   f"（ウィンドウ長を上げても形は変わりません）")
    # 息の通り道。`_soft_min` の丸め（最大 k/2）は差と見ない。
    ent, h_min, z_min = airway_min(p)
    if ent - h_min > _ROOF_SOFT_K / 2.0:
        out.append(f"息の通り道が入口より奥で狭くなっています: 入口（ティップ）"
                   f"{ent:.2f}mm に対し z≈{z_min:.1f}mm で {h_min:.2f}mm ＝ "
                   f"入口の {h_min / ent * 100:.0f}%。リード先端から入った息を"
                   f"ここで絞ります。バッフル高さ {p['baffle_height']:.1f}mm を"
                   f"下げてください（**ティップ開きを広げると悪くなります** —— "
                   f"上がるのは入口だけで、奥は動きません）")
    return out


# ---------------------------------------------------------------- キャッシュの登録
#
# 定義に直接デコレータを付けず末尾でまとめて包むのは、**何をキャッシュ対象と
# みなしているか**を 1 箇所で読めるようにするため。ここに挙がっていない関数は
# 素のまま呼ばれる。
#
# 載せてよい条件は2つだけ:
#   1. `p`（と挙げた追加引数）だけで決まる純関数であること
#   2. **不変な値を返すこと**。list / dict を返す関数は載せない —
#      呼び出し側が返り値を書き換える（例: `mouthpiece.build_cad` の
#      `secs.append(...)`）とキャッシュごと汚染されるため。

#: `p` だけで決まるスカラ／タプル。断面 1 枚で数千回ずつ呼ばれる。
_PARAM_ONLY = (
    "shank_length", "shoulder_ratio", "shank_radius", "heel_z", "shoulder_length",
    "shank_start_z",
    "bore_radius", "bore_start_z", "ligature_seat_range",
    "tip_chamfer_depth", "tip_chamfer_len",
    "table_angle", "table_y", "table_cut_end_z", "facing_cut_z_range",
    "beak_ridge_radius", "beak_angle", "beak_apex_y0", "beak_cut_range",
    "beak_ramp_end_z", "beak_blend_end_z", "beak_cut_cap_y",
    "window_width", "window_front_z", "window_start_z", "window_end_z",
    "window_open_z",
    "baffle_plateau", "baffle_plateau_end_z", "baffle_step_end_z",
    "baffle_flat_end_z", "tip_roof_y", "baffle_plateau_y",
    "_throat_n", "_chamber_n", "throat_radius", "chamber_size",
    "_section_breaks",
)

#: `(p, z)` で決まるもの。同じ z を複数の呼び出し元が引き直すので効く
#: （`outer_radius_nominal` は 1 断面 7,022 回に対し相異なる z は 245 個）。
_PARAM_AND_Z = (
    "outer_radius_nominal", "outer_radius", "table_plane_y", "cut_top_y",
    "beak_apex_y", "_cav_sigma",
)

for _n in _PARAM_ONLY + _PARAM_AND_Z:
    globals()[_n] = _pcached(globals()[_n])
del _n


def _register_static_pchip() -> None:
    """モジュール定数の制御点表の係数を先に作っておく（`_pchip` の注記を参照）。"""
    for tab in (_BODY_PROFILE, _SHOULDER_PROFILE, _CAVITY_W, _CAVITY_C,
                _CAVITY_D, _RAIL_WEIGHT, _TOP_ARCH):
        _PCHIP_STATIC[id(tab)] = (tab, _pchip_table(tab))


_register_static_pchip()
