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

断面はスーパー楕円 |2x/w|^n + |2(y-yc)/h|^n = 1 で表現する
（n=2 かつ w=h で真円、n が大きいほど角形）。ロフトが安定し自己交差しない。
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------- 補間ユーティリティ

def _smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _pchip(pts: list[tuple[float, float]], x: float) -> float:
    """単調保存の3次エルミート補間（Fritsch–Carlson）。

    外形プロファイルを制御点から滑らかに起こすために使う。単調性を保存するので、
    制御点が単調増加なら生成される回転体も単調で、ロフトが自己交差しない。
    """
    n = len(pts)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
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
    k = 0
    for i in range(n - 1):
        if xs[i] <= x <= xs[i + 1]:
            k = i
            break
    t = (x - xs[k]) / h[k]
    t2, t3 = t * t, t * t * t
    return (ys[k] * (2 * t3 - 3 * t2 + 1) + h[k] * m[k] * (t3 - 2 * t2 + t)
            + ys[k + 1] * (-2 * t3 + 3 * t2) + h[k] * m[k + 1] * (t3 - t2))


# ---------------------------------------------------------------- 軸方向のランドマーク

#: シャンク肩（最大径→シャンク径）の長さ。実測 11mm / heel_z 79mm。
_SHOULDER_RATIO = 0.139


def shank_length(p: dict) -> float:
    """シャンク平行部の長さ。ロングシャンク/標準シャンクの作り分けに使う。"""
    return p.get("shank_length", 17.5)


def shank_radius(p: dict) -> float:
    return p.get("shank_dia", 0.747 * p["body_dia"]) / 2.0


def heel_z(p: dict) -> float:
    """最大径の位置 = リード踵 = テーブル平面が胴に接する z。

    ここから後ろは肩テーパ→シャンク平行部。全長からシャンク構成を引いて決めるので、
    `shank_length` を変えても踵の位置とテーブル長が正しく追従する。
    """
    length = p["overall_length"]
    sh = shank_length(p)
    heel = (length - sh) / (1.0 + _SHOULDER_RATIO)
    return max(heel, 0.30 * length)


def shoulder_length(p: dict) -> float:
    return _SHOULDER_RATIO * heel_z(p)


def bore_radius(p: dict) -> float:
    return p["bore_dia"] / 2.0


def bore_start_z(p: dict) -> float:
    return p["overall_length"] - p["bore_length"]


def ligature_seat_range(p: dict) -> tuple[float, float]:
    """リガチャーが座る z 範囲。最大径付近の帯。

    実物は「最大径に向かって単調に太る」形なので、旧実装のような r/rb==1.0 の
    平坦区間は存在しない。踵（最大径）から前方へリガチャー幅ぶん取った帯を座とする。
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


def outer_radius(p: dict, z: float) -> float:
    """胴の外半径（切除前）。ボア軸まわりの真円。"""
    r_max = p["body_dia"] / 2.0
    heel = heel_z(p)
    if z <= heel:
        return r_max * _pchip(_BODY_PROFILE, max(z, 0.0) / heel)
    r_sh = shank_radius(p)
    sl = shoulder_length(p)
    s = (z - heel) / sl if sl > 0 else 1.0
    if s >= 1.0:
        return r_sh
    return r_sh + (r_max - r_sh) * _pchip(_SHOULDER_PROFILE, s)


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
    y0 = -outer_radius(p, 0.0) - p["tip_opening"]
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
    r = (fl * fl + tip * tip) / (2.0 * tip)
    return r - math.sqrt(max(r * r - (fl - z) ** 2, 0.0))


def cut_top_y(p: dict, z: float) -> float:
    """テーブル/フェイシングカット面の上端 Y（この下側を切除）。"""
    return table_plane_y(p, z) + facing_rise(p, z)


# ---------------------------------------------------------------- ビーク

#: ビーク横断面の円弧半径（body_dia 比）。実測 25.0mm / 30.8mm。
_BEAK_RIDGE_RATIO = 0.812
#: バイトポイント位置（全長比）
_BEAK_BITE = 0.25
#: ビークが胴へ溶けるブレンド区間（heel_z 比）。実測 34.2→41.5mm / 79mm。
_BEAK_BLEND0 = 0.433
_BEAK_BLEND1 = 0.525
#: ブレンドの進み方。実測は「長く粘ってから一気に胴へ寄る」形で、
#: smoothstep（対称）では中盤が 1.6mm 浮いた。指数 2.5 で ≤0.1mm に収まる。
_BEAK_BLEND_EXP = 2.5


def _beak_blend(p: dict, z: float) -> float:
    """ビークが胴へ溶ける進行度 u∈[0,1]。"""
    heel = heel_z(p)
    z0, z1 = _BEAK_BLEND0 * heel, _BEAK_BLEND1 * heel
    if z <= z0:
        return 0.0
    if z >= z1:
        return 1.0
    return ((z - z0) / (z1 - z0)) ** _BEAK_BLEND_EXP


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
    """ビーク稜線（x=0）の Y。胴へのブレンドを含む。"""
    line = beak_apex_y0(p) + math.tan(beak_angle(p)) * z
    u = _beak_blend(p, z)
    if u <= 0.0:
        return line
    top = outer_radius(p, z)
    return top if u >= 1.0 else line + (top - line) * u


def beak_top_y(p: dict, z: float, x: float = 0.0) -> float:
    """ビーク面の Y（この上側を切除）。稜線から横断面円弧で降りる。

    ブレンド区間では横断面半径も胴の半径へ寄せる（実測で z=40 の横断曲率半径が
    14.1mm ≈ 胴半径 13.6mm まで小さくなっていた）。
    """
    apex = beak_apex_y(p, z)
    r_ridge = beak_ridge_radius(p)
    u = _beak_blend(p, z)
    if u > 0.0:
        r_ridge = r_ridge + (outer_radius(p, z) - r_ridge) * u
    ax = min(abs(x), 0.999 * r_ridge)
    return apex - (r_ridge - math.sqrt(max(r_ridge * r_ridge - ax * ax, 0.0)))


def beak_y(p: dict, z: float) -> float:
    """[互換] ビーク稜線の Y。`beak_top_y(p, z, 0.0)` と同じ。"""
    return beak_apex_y(p, z)


def beak_cut_section(p: dict, z: float, half_width: float,
                     samples: int = 33) -> list[tuple[float, float]]:
    """ビーク切除ソリッドの断面（x, y）閉ポリゴン。

    稜線の円弧に沿って下辺を作り、上を y=+H で閉じる。円弧は胴より広く取るので、
    胴の左右も含めて「ビーク面より上」を確実に覆う。
    """
    r_ridge = beak_ridge_radius(p)
    xa = min(half_width, 0.95 * r_ridge)
    pts = []
    for i in range(samples):
        x = -xa + 2.0 * xa * i / (samples - 1)
        pts.append((x, beak_top_y(p, z, x)))
    h = 4.0 * p["body_dia"]
    pts.append((xa, h))
    pts.append((-xa, h))
    return pts


# ---------------------------------------------------------------- 内部空洞

#: バッフルが無いときのティップ天井高さ（リード面から）。bore_dia 比。
_TIP_GAP_FREE_RATIO = 0.312
#: バッフル天井が平坦なまま続く区間（ウィンドウ長比）。実測 18mm / 40.5mm。
_BAFFLE_FLAT = 0.44
#: 平坦区間の後の直線ランプが終わる位置（平坦端→ボア開始 を 1 とした比）と、
#: そこまでに稼ぐ立ち上がり量の比。実測（ランプ終端 z=32、天井 −0.71）から。
_BAFFLE_RAMP_T = 0.419
_BAFFLE_RAMP_F = 0.335
#: ランプ後のボア天井への寄り方（1-(1-u)^k）。実測 k=2.1。
_BAFFLE_BLEND_K = 2.1


def window_width(p: dict) -> float:
    return p["reed_width"] - 2.0 * p["side_rail_width"]


#: ウィンドウ開口（リード面のスロット）幅の z 方向プロファイル
#: (t = 窓区間内の進行度, スロット幅 / window_width)。実測: ティップ寄りは
#: 弦いっぱいまで開き（サイドレールがほぼ無い）、後方へ向かってレールが太るぶん
#: 細くなり、最後に丸く閉じる。
_SLOT_WIDTH = [
    (0.00, 1.32), (0.11, 1.25), (0.25, 1.19), (0.34, 1.16), (0.43, 1.11),
    (0.52, 1.08), (0.62, 1.05), (0.71, 1.02), (0.80, 0.95), (0.85, 0.89),
    (0.89, 0.73), (0.93, 0.48), (1.00, 0.25),
]
#: チェンバー幅 / window_width。実測ではスロットが狭まっても内部の幅は
#: ほぼ一定（≈14.7mm）。ティップ寄りはスロットの方が広いので下限として使う。
_CAVITY_WIDTH_RATIO = 1.17


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


def window_start_z(p: dict) -> float:
    return p["tip_rail_width"] + 0.2


def window_end_z(p: dict) -> float:
    """ウィンドウ後端。チェンバー→ボアの遷移区間を必ず残す。"""
    zb = bore_start_z(p)
    return min(window_start_z(p) + p["window_length"], zb - 4.0)


def baffle_roof_y(p: dict, z: float) -> float:
    """内部空洞の天井 Y（ボア軸基準の絶対値）。

    実測ではティップ側の天井は **ボア軸に平行な平面** で、ウィンドウ長の 44% まで
    フラットに続き、そこからボア開始位置に向かって smoothstep でボア天井へ上がる
    （実測とのずれは最大 0.6mm）。リード面から見た天井高さが増えるのは、天井が
    上がるからではなくテーブルが下がるため。
    """
    z_start = window_start_z(p)
    gap = _TIP_GAP_FREE_RATIO * p["bore_dia"] - p["baffle_height"]
    gap = max(gap, 0.35 * p["min_wall"])
    y0 = table_plane_y(p, z_start) + gap
    z_flat = z_start + _BAFFLE_FLAT * p["window_length"]
    zb = bore_start_z(p)
    y_bore = bore_radius(p)
    if z <= z_flat:
        return y0
    if z >= zb:
        return y_bore
    return y0 + (y_bore - y0) * _baffle_progress(p, (z - z_flat) / (zb - z_flat))


def _baffle_progress(p: dict, t: float) -> float:
    """平坦区間の終わり→ボア開始 における天井の立ち上がり率 u∈[0,1]。

    rollover=実測どおりの「直線ランプ＋指数ブレンド」（基準。実測とのずれ ≤0.16mm）、
    straight=線形、step=急峻な段差、curve=早く立ち上がって高天井で張り出す
    （メタリック/アグレッシブ）。
    """
    t = min(max(t, 0.0), 1.0)
    kind = p.get("baffle_type", "rollover")
    if kind == "straight":
        return t
    if kind == "step":
        return 0.06 + 0.94 * _smoothstep((t - 0.18) / 0.10)
    if kind == "curve":
        expo = 1.6 + p.get("rollover_radius", 8.0) / 10.0
        return 1.0 - (1.0 - t) ** expo
    if t <= _BAFFLE_RAMP_T:
        return _BAFFLE_RAMP_F * t / _BAFFLE_RAMP_T          # 直線ランプ
    u = (t - _BAFFLE_RAMP_T) / (1.0 - _BAFFLE_RAMP_T)
    return _BAFFLE_RAMP_F + (1.0 - _BAFFLE_RAMP_F) * (
        1.0 - (1.0 - u) ** _BAFFLE_BLEND_K)


def shell_limit(p: dict, z: float) -> dict:
    """z における空洞の許容包絡 {top, bot, half_width}（すべて min_wall だけ内側）。

    胴（真円）とビーク面から決まる「残る材料」の内寸。空洞ステーションは必ずここを
    通す。テーブルカットは含めない — 窓はカット面より下へ抜けて初めて開口になるので、
    下端まで拘束すると窓が閉じる（`_contain` が role で使い分ける）。
    """
    ro = outer_radius(p, z)
    mw = p["min_wall"]
    return {
        "top": min(ro, beak_apex_y(p, z)) - mw,
        "bot": -(ro - mw),
        "half_width": ro - mw,
    }


#: 窓断面をサンプルする t 列（ティップ→窓終端）。ティップ側と後端を細かく刻む:
#: 弦が急に広がる区間（t<0.1）と丸く閉じる区間（t>0.9）はステーションが疎だと
#: ルールドロフトが直線の楔になり、窓が V 字に尖る。
_WINDOW_TS = [0.0, 0.03, 0.06, 0.10, 0.16, 0.22, 0.35, 0.48, 0.62, 0.72,
              0.80, 0.85, 0.89, 0.92, 0.95, 0.97, 1.0]
#: ここまでは窓が開いている（床がリードカット面より下）。この先はランプで床を
#: 上げて閉じる。段差で閉じると内部にほぼ垂直な棚ができるので必ずランプにする
#: （`_window_floor` 参照）。見た目の開口終端は `window_length` の約 97%。
_WINDOW_OPEN_T = 0.90
#: 開口が実際に閉じ切る t（床がリード面を越える位置）。ここから先は外から見えない
#: 内部断面なので、スロットの細りを止めてチェンバー断面へ戻す。戻さないと閉じた後も
#: 「鍵穴」形の細い首が残り、実物にはない段付きチェンバーになる。
_WINDOW_CLOSE_T = 0.93
#: 窓終端→ボア開始の遷移をサンプルする比率。末尾は 1.0 未満にする
#: （z=ボア開始 のステーションは別に1枚だけ置く。同じ z が2枚あるとロフトが
#: 「Segments do not have sufficient separation」で落ちる）。
_TRANSITION_TS = [0.20, 0.45, 0.68, 0.85]
#: スロート（最狭部）が始まる位置（窓終端→ボア開始 を 1 とした比）。
_THROAT_T = 0.75


def _throat_n(p: dict) -> float:
    return (_chamber_n(p) + 2.0) / 2.0


#: チェンバー断面のスーパー楕円指数。
_CHAMBER_N = {"round": 2.2, "square": 3.8, "horseshoe": 2.6, "flat_sidewall": 3.0}


def _chamber_n(p: dict) -> float:
    return _CHAMBER_N.get(p.get("chamber_shape", "round"), 2.2)


def throat_radius(p: dict) -> float:
    """スロート（遷移部最狭）の等価半径。断面積 = throat_ratio × ボア断面積。"""
    k = _superellipse_shape_factor(_throat_n(p))
    return bore_radius(p) * math.sqrt(p["throat_ratio"] * math.pi / (4.0 * k))


def throat_ratio_from_radius(p: dict, r_t: float) -> float:
    """実測したスロート等価半径から `throat_ratio` を逆算（`throat_radius` の逆関数）。"""
    k = _superellipse_shape_factor(_throat_n(p))
    rb = bore_radius(p)
    return (r_t / rb) ** 2 * 4.0 * k / math.pi if rb > 0 else 1.0


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


def chamber_saturated(p: dict) -> bool:
    """チェンバーが肉厚制限で頭打ちになっているか。"""
    step = 1.05
    now = _chamber_areas(p)
    more = _chamber_areas(dict(p, chamber_ratio=p.get("chamber_ratio", 1.0) * step))
    return all(b - a < 1e-6 for a, b in zip(now, more))


def _chamber_areas(p: dict) -> list[float]:
    return [section_area(s)
            for s in stations_by_role(cavity_stations(p), "chamber")]


def chamber_ratio_from_width(p: dict, w_meas: float, r_t_meas: float) -> float:
    """実測したチェンバー幅とスロート半径から `chamber_ratio` を逆算。"""
    h_meas = w_meas * _CHAMBER_H / _CHAMBER_W
    a_ch = section_area({"yc": 0.0, "h": h_meas, "w": w_meas, "n": _chamber_n(p),
                         "shape": p.get("chamber_shape", "round")})
    a_th = superellipse_area(2.0 * r_t_meas, 2.0 * r_t_meas, _throat_n(p))
    return a_ch / a_th if a_th > 0 else 1.0


def _window_floor(p: dict, t: float, z: float) -> float:
    """ウィンドウ断面の床 Y。

    `_WINDOW_OPEN_T` までは**リードカット面より下**に置く（そうして初めて窓が開く）。
    その先は窓を閉じるが、段差でいきなり上げるとロフトにほぼ垂直な壁ができて
    内部に不自然な棚が見える。閉じ区間はランプで持ち上げ、実物の丸い窓後端に寄せる。
    """
    open_y = cut_top_y(p, z) - _WINDOW_FLOOR_DROP
    if t <= _WINDOW_OPEN_T:
        return open_y
    closed_y = table_plane_y(p, z) + _WINDOW_CLOSED_LIFT
    u = (t - _WINDOW_OPEN_T) / max(1.0 - _WINDOW_OPEN_T, 1e-9)
    return open_y + (closed_y - open_y) * _smoothstep(u)


def cavity_stations(p: dict) -> list[dict]:
    """内部空洞ロフトの断面ステーション列。

    各要素: {z, yc, h, w, n, role, shape}（スーパー楕円）。ティップ側→ボア側の順。
    role は "window" / "chamber" / "throat" / "bore"。

    ウィンドウ区間は「床＝リード面より下（＝開口）／天井＝バッフル天井」、
    そこからボア開始位置に向かって床・天井・幅がボア円へ収束する。
    """
    z_start = window_start_z(p)
    z_we = window_end_z(p)
    zb = bore_start_z(p)
    rb = bore_radius(p)
    r_t = throat_radius(p)
    w_ch, h_ch = chamber_size(p)
    w_win = window_width(p)
    n_window = 3.5
    n_ch = _chamber_n(p)
    ch_shape = p.get("chamber_shape", "round")

    stations: list[dict] = []
    w_cav0 = _CAVITY_WIDTH_RATIO * w_win
    for t in _WINDOW_TS:
        z = z_start + t * (z_we - z_start)
        floor = _window_floor(p, t, z)
        ceil_ = baffle_roof_y(p, z)
        # スロット幅は**リード面**の弦を超えられない（超えるとサイドレールが消える）
        chord_lim = reed_chord(p, z) - 0.8 * p["side_rail_width"]
        w_slot = min(w_win * _pchip(_SLOT_WIDTH, t), chord_lim)
        # チェンバー幅はスロットより狭くしない（狭いと断面が下広がりの逆テーパになる）
        w_cav = min(max(w_cav0, w_slot), chord_lim)
        if t > _WINDOW_CLOSE_T:                # 閉口後は鍵穴を解消してチェンバーへ
            u = (t - _WINDOW_CLOSE_T) / max(1.0 - _WINDOW_CLOSE_T, 1e-9)
            w_slot = w_slot + (w_cav - w_slot) * _smoothstep(u)
        stations.append({"z": z, "yc": (floor + ceil_) / 2.0, "h": ceil_ - floor,
                         "w": w_cav, "w_slot": w_slot,
                         "n": n_window, "role": "window", "shape": "window"})

    # 窓終端 → ボア開始: 床・天井・幅がボア円へ収束する遷移。throat/chamber の比が
    # 1.0 なら実測どおり「単調にボアへ開く」形になり、比を上げるとチェンバーが膨らむ。
    s_end = stations[-1]
    f0 = s_end["yc"] - s_end["h"] / 2.0
    c0 = s_end["yc"] + s_end["h"] / 2.0
    w0 = s_end["w"]
    z_th = z_we + _THROAT_T * (zb - z_we)          # スロート（最狭部）はボア直前
    for t in _TRANSITION_TS:
        z = z_we + t * (zb - z_we)
        u = _smoothstep(t)
        if z >= z_th:
            role, shape, n = ("throat", "round", _throat_n(p))
            w_t, h_t = 2.0 * r_t, 2.0 * r_t
        else:
            role, shape, n = ("chamber", ch_shape, n_ch)
            w_t, h_t = w_ch, h_ch
        floor = f0 + (-h_t / 2.0 - f0) * u
        ceil_ = c0 + (h_t / 2.0 - c0) * u
        w = w0 + (w_t - w0) * u
        stations.append({"z": z, "yc": (floor + ceil_) / 2.0, "h": ceil_ - floor,
                         "w": w, "n": n, "role": role, "shape": shape})
    stations.append({"z": zb, "yc": 0.0, "h": 2.0 * rb, "w": 2.0 * rb,
                     "n": 2.0, "role": "bore", "shape": "round"})
    return [_contain(p, s) for s in stations]


def cavity_sections(p: dict) -> list[dict]:
    """内部空洞ロフト用の断面列 [{z, pts}]（ティップ→ボアの z 昇順）。"""
    return [{"z": s["z"], "pts": section_pts(s)} for s in cavity_stations(p)]


def _contain(p: dict, s: dict) -> dict:
    """ステーションを `shell_limit()` の内側へ切り詰める。

    窓（role == "window"）の下端だけは拘束しない。窓はテーブルカット面より下へ
    抜けて初めて開口になるので、下端を clamp すると窓が閉じてしまう。
    """
    lim = shell_limit(p, s["z"])
    top = min(s["yc"] + s["h"] / 2.0, lim["top"])
    bot = s["yc"] - s["h"] / 2.0
    if s["role"] != "window":
        bot = max(bot, lim["bot"])
    bot = min(bot, top - 1.0)
    w = min(s["w"], 2.0 * lim["half_width"])
    out = {**s, "yc": (top + bot) / 2.0, "h": top - bot, "w": w}
    if "w_slot" in s:
        out["w_slot"] = min(s["w_slot"], w)
    return out


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
_SECTION_SAMPLES = 96


def _super_pts(yc: float, h: float, w: float, nx: float, ny: float,
               samples: int = _SECTION_SAMPLES) -> list[tuple[float, float]]:
    pts = []
    for i in range(samples):
        th = 2.0 * math.pi * i / samples
        c, s = math.cos(th), math.sin(th)
        x = (w / 2.0) * math.copysign(abs(c) ** (2.0 / nx), c)
        y = yc + (h / 2.0) * math.copysign(abs(s) ** (2.0 / ny), s)
        pts.append((x, y))
    return pts


def _superellipse_pts(yc, h, w, n, samples=_SECTION_SAMPLES):
    return _super_pts(yc, h, w, n, n, samples)


def _flat_sidewall_pts(yc, h, w, samples=_SECTION_SAMPLES):
    """フラットサイドウォール：左右が垂直な平面、上下が丸い断面。"""
    return _super_pts(yc, h, w, 7.0, 2.4, samples)


#: ウィンドウ断面のスロット直立区間の高さ [mm]（下限）。空洞の床はリード面より
#: `_WINDOW_FLOOR_DROP` だけ下にあるので、それより高くないと開口幅が痩せる。
_SLOT_WALL_H = 0.55
#: 空洞の床をリード面より下げる量 [mm]。ここが窓を開けるための食い込み代。
_WINDOW_FLOOR_DROP = 0.4
#: 窓が閉じた後の床の高さ（テーブル平面から）[mm]。実測のチェンバー床に合わせる。
_WINDOW_CLOSED_LIFT = 2.0
#: スロット壁の上でチェンバー幅へ開き切るまでの高さ比。
_SLOT_FLARE_V = 0.35


def _window_pts(yc, h, w, w_slot, n, samples=_SECTION_SAMPLES):
    """ウィンドウ断面：リード面のスロットは**直立した側壁**、上はチェンバー幅へ開く。

    スーパー楕円のままだと断面がリード面の高さで細り、開口幅が設計値の 78% ほどに
    痩せていた（実測より最大 4mm 狭い窓になっていた）。実物のスロットはレール厚を
    貫く直立の壁なので、下端は幅 `w_slot` の平坦・直壁にし、その上でチェンバー幅へ
    フレアしてドームで閉じる。

    y の分布はスーパー楕円と同じ角度パラメータのままにしてある。隣接ステーション
    （チェンバー断面）と点の対応が崩れるとルールドロフトがねじれるため。
    """
    if h <= 0.0 or w <= 0.0:
        return _superellipse_pts(yc, h, max(w, 1e-6), n, samples)
    lo, hi = yc - h / 2.0, yc + h / 2.0
    ws2 = min(w_slot, w) / 2.0
    wc2 = w / 2.0
    d = max(_SLOT_WALL_H, min(1.2, 0.45 * h))
    y1 = min(lo + d, hi - 1e-6)

    def hw(y):
        if y <= y1:
            return ws2
        v = (y - y1) / (hi - y1)
        v = min(max(v, 0.0), 1.0)
        flare = ws2 + (wc2 - ws2) * min(1.0, v / _SLOT_FLARE_V)
        return flare * (1.0 - v ** n) ** (1.0 / n)

    pts = []
    for i in range(samples):
        th = 2.0 * math.pi * i / samples
        c, s = math.cos(th), math.sin(th)
        y = yc + (h / 2.0) * math.copysign(abs(s) ** (2.0 / n), s)
        pts.append((math.copysign(hw(y), c) if abs(c) > 1e-12 else 0.0, y))
    return pts


def _horseshoe_pts(yc, h, w, samples=_SECTION_SAMPLES):
    """馬蹄：丸い天井・側壁を持ち、底の中央が上へ凹む（U字）断面。"""
    hh = h / 2.0
    notch = 0.5 * hh
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
    shape = s.get("shape", "round")
    yc, h, w = s["yc"], s["h"], s["w"]
    if shape == "window":
        return _window_pts(yc, h, w, s.get("w_slot", w), s.get("n", 3.5))
    if shape == "horseshoe":
        return _horseshoe_pts(yc, h, w)
    if shape == "flat_sidewall":
        return _flat_sidewall_pts(yc, h, w)
    return _superellipse_pts(yc, h, w, s.get("n", 2.0))


def section_area(s: dict) -> float:
    if s.get("shape") in ("window", "horseshoe", "flat_sidewall"):
        return _polygon_area(section_pts(s))
    return superellipse_area(s["w"], s["h"], s.get("n", 2.0))


def cavity_volume_cc(p: dict) -> dict:
    """気柱体積の解析近似（断面積の台形積分 + ボア円筒）。

    ウィンドウ区間の断面は下側がリード面（テーブル平面）で閉じられた分だけを数える。
    ロフト用ステーションは開口のためカット面より下へはみ出しているので、体積計算では
    リード面で切り直す。

    Returns: total_cc(気柱全体), effective_cc(コーク位置まで＝ネック挿入分を除く)
    """
    st = cavity_stations(p)
    areas = []
    for s in st:
        if s["role"] == "window":
            top = s["yc"] + s["h"] / 2.0
            bot = max(s["yc"] - s["h"] / 2.0, table_plane_y(p, s["z"]))
            areas.append(section_area({**s, "yc": (top + bot) / 2.0,
                                       "h": max(top - bot, 0.0)}))
        else:
            areas.append(section_area(s))
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
    z_start = window_start_z(p)
    zb = bore_start_z(p)
    z_we = window_end_z(p)
    z_baffle_end = z_start + _BAFFLE_FLAT * p["window_length"]
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
        "side_rail_width": r(z_start, z_we, "bottom", "サイドレール（窓の両脇）"),
        "table_angle":     r(0.0, heel, "bottom", "テーブル平面（傾き）"),
        "baffle_type":     r(z_start, z_baffle_end, "all", "バッフル（窓の天井）"),
        "baffle_height":   r(z_start, z_baffle_end, "all", "バッフル（窓の天井）"),
        "rollover_radius": r(z_start, zb, "all", "バッフル肩の丸み"),
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
        "overall_length":  r(0.0, length, "all", "全体"),
        "min_wall":        r(0.0, length, "all", "全体（肉厚）"),
    }


def anatomy_regions(p: dict) -> list[dict]:
    """マウスピース各部の名称と占有 z 範囲（パラメータ非依存の純名称マップ）。"""
    length = p["overall_length"]
    fl = p["facing_length"]
    z_start = window_start_z(p)
    zb = bore_start_z(p)
    z_we = window_end_z(p)
    z_baffle_end = z_start + _BAFFLE_FLAT * p["window_length"]
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
    cavity_bot = [(s["z"], max(s["yc"] - s["h"] / 2, table_plane_y(p, s["z"])))
                  for s in stations]
    r = bore_radius(p)
    cavity_top += [(length, r)]
    cavity_bot += [(length, -r)]
    return {
        "outer_top": outer_top,
        "outer_bot": outer_bot,
        "cavity_top": cavity_top,
        "cavity_bot": cavity_bot,
        "table_y": table_y(p),
        "table_plane": [(0.0, table_plane_y(p, 0.0)), (heel, table_plane_y(p, heel))],
        "bore_start": bore_start_z(p),
    }
