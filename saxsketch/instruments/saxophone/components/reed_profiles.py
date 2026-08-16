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


def front_edge_z(p: dict, x: float) -> float:
    """幅方向 x で材料が始まる z。中央で 0、角（|x|=先端幅/2）で `tip_curve_depth`。"""
    r = tip_arc_radius(p)
    if r <= 0.0:
        return 0.0
    return r - math.sqrt(max(r * r - x * x, 0.0))


def width(p: dict, z: float) -> float:
    """z 位置の幅。先端幅 → 踵幅の線形テーパー＋先端角の丸み＋前縁カーブ。

    前縁が曲線なので、幅は 2 つの制限の小さいほうになる:
      - 側面のテーパー（角の丸みを含む）
      - 前縁カーブより後ろに存在する x の範囲

    角の丸みは **前縁の角**（z = `tip_curve_depth`）を基準に効かせる。カーブが 0 なら
    角は z=0 に戻り、式は従来と完全に一致する（`tip_curve_depth` を 0 にしたリードは
    1 ビットも形が動かない）。
    """
    t = min(max(z / p["reed_length"], 0.0), 1.0)
    w = p["tip_width"] + (p["heel_width"] - p["tip_width"]) * t
    r = p.get("tip_corner_r", 0.8)
    d = tip_curve_depth(p)
    s = z - d        # 前縁の角からの距離
    if 0.0 < s < r:  # 平面視での先端角の丸み（両側から削る）
        w -= 2.0 * (r - math.sqrt(max(r * r - (r - s) ** 2, 0.0)))
    elif s <= 0.0:
        w -= 2.0 * r
    if 0.0 < z < d:  # 前縁カーブの内側。z ≥ d では円弧は全幅に達しているので効かない
        rr = tip_arc_radius(p)
        w = min(w, 2.0 * math.sqrt(max(2.0 * rr * z - z * z, 0.0)))
    return max(w, 0.5)


def tip_load_width(p: dict) -> float:
    """先端の実効幅 [mm]。硬さモデルの等分布荷重の幅（`reed_model._bending`）。

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


def cane_layout_error(p: dict) -> str | None:
    """ブランクが元のケーン管に収まらない組合せを説明つきで弾く。

    上面はケーンの円弧なので、リードが管より広いと**円弧がテーブル面より下へ潜って
    断面が裏返る**（実測: tip_width 18.0 / heel_width 14.0 で断面の最小 y = −0.45、
    heel_width 9.0 で −3.48。後者はソリッドが `is_valid=False` になった）。

    **2 つのパラメータの関係**なので `ParamSpec` の範囲では表せない
    （幅を狭くしても側端厚を上げても成立する）。`Component.params_error` へ回す。
    """
    r = cane_radius(p)
    if r <= 0.0:
        return None                     # 円弧なし（上面が平ら）＝どんな幅でも収まる
    h = p["heel_thickness"] - _MIN_EDGE_THICKNESS
    limit = math.sqrt(max(h * (2.0 * r - h), 0.0))   # 円弧が余裕高さまで来る x
    hw = max(p["tip_width"], p["heel_width"]) / 2.0
    if hw <= limit:
        return None
    return (f"リードが元のケーン管に収まりません: 最大半幅 {hw:.1f} mm に対し、"
            f"外径 φ{2.0 * r:.1f} の管では半幅 {limit:.1f} mm までしか厚みが"
            f"残りません。踵の側端厚（{heel_edge_thickness(p):.2f}）を上げて円弧を"
            f"浅くするか、幅を狭くしてください。")


def thickness(p: dict, z: float, x: float = 0.0) -> float:
    """厚み ＝ **削り面と素材上面の低いほう**（カマボコ断面）。

    実物の作りそのもの: D 形のブランクを取ってからヴァンプを削るので、削っていない
    所はケーンの円弧が残り、削った所は削り面が勝つ。円弧が勝ち始めるのは
    ヴァンプの後ろ半分（実測 z ≈ 14.8 / 16.8 / 17.5）で、先端側は削り面が勝つ。
    """
    return min(_vamp_thickness(p, z, x), cane_top(p, x))


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


def edge_thickness(p: dict, z: float) -> float:
    """側端の厚み（角丸半径の上限に使う）。"""
    return thickness(p, z, width(p, z) / 2.0)


# ---------------------------------------------------------------- ロフト断面

_STATION_TS = [0.0, 0.02, 0.05, 0.10, 0.18, 0.28, 0.40, 0.55, 0.72, 0.88, 1.0]

#: 前縁カーブ区間に置く刻み（`tip_curve_depth` 比）。角（1.0）を必ず含める。
#: ヴァンプ基準の最初の刻みは 0.54〜0.70mm しかなく、1.3mm のカーブを 2 点でしか
#: 通らない。カーブが 0 なら全部 0.0 に潰れて既存の先端ステーションと重複が消える。
_TIP_CURVE_TS = [0.15, 0.35, 0.60, 0.85, 1.0]

#: 断面上面のサンプル位置（x / 半幅）。+1 → −1 の順で、底辺 2 点と合わせて
#: 反時計回りに一周する。**点数は全断面で一定**（`loft_sections` のルールドロフトは
#: 頂点対応ではなくパラメータ対応で面を張るため、断面ごとに点数が変わると面がねじれる）。
#: **奇数個にして q=0 を必ず含める** —— 中央は背骨の稜線（断面の最大高さ）なので、
#: ここを跨いでサンプルすると稜線が全長にわたって平らな面になる。
#: 19 点で断面積の誤差は最悪 0.10%（10 点だと 0.40%、27 点にしても 0.06% までしか
#: 改善しない。端に寄せた分布にしても差は 0.02% 以下だったので等間隔でよい）。
_TOP_QS = [1.0 - 2.0 * i / 18.0 for i in range(19)]


def station_zs(p: dict) -> list[float]:
    """断面を置く z 列。先端側を密にし、バーク端と踵を必ず含める。"""
    zv = vamp_start_z(p)
    zs = [t * zv for t in _STATION_TS]
    zs += [t * tip_curve_depth(p) for t in _TIP_CURVE_TS]   # 前縁カーブ
    zs.append(zv + 0.01)          # バーク段差（削り終わりを明示）
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
        "tip_curve_depth": r(0.0, max(tip_curve_depth(p), 0.5), "all", "前縁カーブ"),
        "vamp_length":    r(0.0, zv, "top", "ヴァンプ（削り面）"),
        "profile_curve":  r(0.0, zv, "top", "ヴァンプ（削り面）"),
        "spine_ratio":    r(0.0, zv, "top", "中央の背骨"),
        "side_rail_thin": r(0.0, zv, "top", "サイドレール（両脇）"),
        "tip_corner_r":   r(0.0, 0.10 * zv, "top", "先端角の丸み"),
        "file_cut":       r(zv - 2.0, zv + 1.0, "top", "ファイルドカット（削り終わり）"),
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
