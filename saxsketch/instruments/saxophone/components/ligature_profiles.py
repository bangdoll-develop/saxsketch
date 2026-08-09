"""リガチャーの断面プロファイル（純数学・OCCT非依存）。

マウスピース外形（`profiles.outer_radius` / `profiles.table_plane_y` /
`profiles.ligature_seat_range`）を**そのまま参照**して内周を生成する。これが
「マウスピース外形との自動整合」の実体で、参照マウスピースのボディ径を変えれば
リガチャー内周が追従する。

座標系はマウスピースと共通:
  Z: 軸方向（マウスピース先端 z=0 基準）。Y: +Y がビーク側、-Y がテーブル側。

断面の形:
  上側（ビーク側）はマウスピース外形の円弧。テーブル面の高さから下は、
  **リードを収めるタブ**（幅=リード幅、深さ=リード厚）が円の外へ張り出す。
  アルト標準ではテーブル面 y=-11.8 に対し外形半径が 13.8mm なので、厚さ 2.8mm の
  リードの裏面（y=-14.6）は円の下端より外に出る。円を切り落とす D 形にすると
  リードが入らない。締め代のスリットとネジ座はビーク側（+Y）に置く。

**タブは弦幅で切り詰めない。** 実物ではリード幅＝テーブルの弦幅（テナー実測で
7.328 / 7.400mm ＝ 比 0.99）なので、「タブをテーブル面の弦に収める」規則にすると
3サイズとも必ず 0.02mm 足りずに「リードが入りません」を出す。タブは箱として
**円の外へ張り出してよい**（側面が円と交わる y でそのまま円弧へ繋げば自己交差しない）。
唯一の上限は外形半径そのもの。

**テーブルはボア軸に対し 4.18° 傾いている**（`profiles.table_plane_y`）。帯幅
18mm では前後で 1.3mm 落ちるので、断面ごとにその z のテーブル平面を引く。
単一の `table_y` を全長に使うと、後端でリードの裏面がタブの底を突き抜ける。

逆締め（ネジがリード側にくる方式）は、スリットがリード接触面を横切るため
圧力プレートで橋渡しする別機構になる。Phase 3 では扱わない。
"""
from __future__ import annotations

import math

from . import profiles


def seat_range(ref_p: dict, lig_p: dict) -> tuple[float, float]:
    """リガチャーが実際に載る z 範囲。座の前端 + オフセットから帯幅ぶん。"""
    seat0, seat1 = profiles.ligature_seat_range(ref_p)
    z0 = seat0 + lig_p["seat_offset"]
    z1 = z0 + lig_p["band_width"]
    if z1 > seat1:  # 座からはみ出さないよう後端で止める
        z1 = seat1
        z0 = max(seat0, z1 - lig_p["band_width"])
    return z0, z1


def reed_face_y(ref_p: dict, lig_p: dict, reed_thickness: float, z: float) -> float:
    """z でリードを挟む面の Y 座標（テーブル平面からリード厚 + 逃げだけ離れた位置）。

    テーブルが傾いている以上この面も傾く。呼び出し側は必ず z を渡すこと。
    """
    return (profiles.table_plane_y(ref_p, z)
            - reed_thickness - lig_p["reed_clearance"])


def _shelf_y(radius: float, table_y: float) -> float:
    """テーブル面の棚の Y。円と必ず交わるようにクランプする。"""
    return max(min(table_y, radius - 0.5), -(radius - 0.5))


def _shelf_half_width(radius: float, table_y: float) -> float:
    """テーブル面での弦の半幅（円と y=テーブル の交点の x）。"""
    yt = _shelf_y(radius, table_y)
    return math.sqrt(max(radius * radius - yt * yt, 0.0))


#: タブ側面と外形の間に残す肉 [mm]。タブ半幅の唯一の上限。
_TAB_EDGE_MARGIN = 0.2


def _clamp_tab_hw(radius: float, tab_hw: float) -> float:
    """要求タブ半幅を**外形半径**に収まる範囲へ制限する。

    以前はテーブル面の弦半幅で切り詰めていたが、タブは円の外へ張り出す箱なので
    弦は上限ではない（上限は外形半径そのもの）。断面生成と適合判定の唯一の出所。
    """
    return min(tab_hw, radius - _TAB_EDGE_MARGIN)


def _wrap_section(radius: float, table_y: float, tab_hw: float, tab_bottom: float,
                  samples: int = 72) -> list[tuple[float, float]]:
    """円弧（上側）＋リードのタブ（下側）の断面。反時計回り。

    順序を誤ると自己交差してロフトが破綻するため、向きを固定する:
    タブ底辺を +x 方向 → 右の立ち上がり → （棚）→ 上側の円弧 → 左の（棚と）立ち下がり。

    タブがテーブル面の弦より狭ければ棚（テーブル面の水平部）が出る。広ければ棚は
    無く、タブ側面 `x = ±hw` が円と交わる `y = -√(r²-hw²)`（テーブル面より上）で
    そのまま円弧へ繋ぐ。どちらも同じ式で書ける。
    """
    yt = _shelf_y(radius, table_y)
    x_c = _shelf_half_width(radius, table_y)
    hw = _clamp_tab_hw(radius, tab_hw)
    x_a = max(hw, x_c)                          # 円弧の開始 x
    y_a = -math.sqrt(max(radius * radius - x_a * x_a, 0.0))   # その x で円に乗る y
    shelf = x_a > hw + 1e-9                     # 棚が出るのはタブが弦より狭いときだけ
    pts = [(-hw, tab_bottom), (hw, tab_bottom), (hw, y_a)]
    if shelf:
        pts.append((x_a, y_a))
    th0 = math.atan2(y_a, x_a)          # 負の角度
    span = math.pi - 2.0 * th0          # 上側を回って (-x_a, y_a) まで
    n = max(samples - 6, 12)
    for i in range(1, n):
        th = th0 + span * i / n
        pts.append((radius * math.cos(th), radius * math.sin(th)))
    if shelf:
        pts.append((-x_a, y_a))
    pts.append((-hw, y_a))
    return pts


def _sections(ref_p: dict, lig_p: dict, reed_thickness: float,
              offset: float) -> list[dict]:
    """内周（offset=clearance）／外周（offset=clearance+band_thickness）の断面列。

    テーブル面の基準はマウスピース モデルの `table_plane_y(z)`。**断面ごとに引く**。
    傾斜 4.18° は帯幅 18mm で 1.3mm 落ちるので、1点で代表するとリードの裏面が
    後端でタブの底を突き抜ける。3断面のルールドロフトなので、傾いた平面は
    そのまま平面として出る（近似誤差なし）。
    """
    z0, z1 = seat_range(ref_p, lig_p)
    tab_hw = ref_p["reed_width"] / 2.0 + offset
    return [{"z": z,
             "pts": _wrap_section(
                 profiles.outer_radius(ref_p, z) + offset,
                 profiles.table_plane_y(ref_p, z), tab_hw,
                 reed_face_y(ref_p, lig_p, reed_thickness, z) - offset)}
            for z in (z0, (z0 + z1) / 2.0, z1)]


def inner_sections(ref_p: dict, lig_p: dict, reed_thickness: float) -> list[dict]:
    return _sections(ref_p, lig_p, reed_thickness, lig_p["clearance"])


def outer_sections(ref_p: dict, lig_p: dict, reed_thickness: float) -> list[dict]:
    return _sections(ref_p, lig_p, reed_thickness,
                     lig_p["clearance"] + lig_p["band_thickness"])


def inner_radius(ref_p: dict, lig_p: dict) -> float:
    """帯中央での内周半径（適合チェック・仕様書用）。"""
    z0, z1 = seat_range(ref_p, lig_p)
    return profiles.outer_radius(ref_p, (z0 + z1) / 2.0) + lig_p["clearance"]


def requested_tab_half_width(ref_p: dict, lig_p: dict) -> float:
    """リードを収めるのに必要なタブ半幅（クランプ前）。"""
    return ref_p["reed_width"] / 2.0 + lig_p["clearance"]


def flat_half_width(ref_p: dict, lig_p: dict, reed_thickness: float) -> float:
    """リード接触面（タブ底面）の**実際の**半幅。圧力プレートの寸法根拠。

    外形半径に収まらない要求幅は断面生成側で切り詰められる。ここで同じクランプを
    通しておかないと、プレートがタブの外に置かれて側壁を突き抜ける。
    """
    z0, z1 = seat_range(ref_p, lig_p)
    radius = profiles.outer_radius(ref_p, (z0 + z1) / 2.0) + lig_p["clearance"]
    return _clamp_tab_hw(radius, requested_tab_half_width(ref_p, lig_p))


# ---------------------------------------------------------------- ネジ・スリット

SCREW_SPECS = {          # (呼び径 mm, バカ穴径 mm, 頭部径 mm)
    "m2.5": (2.5, 2.8, 5.0),
    "m3": (3.0, 3.4, 6.0),
}
#: 市販の一般的な首下長さ [mm]（BOM でこの中から選ぶ）
STOCK_SCREW_LENGTHS = [6, 8, 10, 12, 16, 20]


def screw_spec(lig_p: dict) -> tuple[float, float, float]:
    return SCREW_SPECS.get(lig_p.get("screw_size", "m3"), SCREW_SPECS["m3"])


def ear_thickness(lig_p: dict) -> float:
    """ネジ座（耳）の X 方向厚み。頭部径から必要な座面を確保する。"""
    _, _, head_d = screw_spec(lig_p)
    return max(lig_p["band_thickness"], head_d * 0.5)


def screw_zs(ref_p: dict, lig_p: dict) -> list[float]:
    """ネジ軸の z 位置。2本なら帯幅を3等分した位置に置く。"""
    z0, z1 = seat_range(ref_p, lig_p)
    n = int(lig_p["screw_count"])
    if n <= 1:
        return [(z0 + z1) / 2.0]
    return [z0 + (z1 - z0) * (i + 1) / (n + 1) for i in range(n)]


#: ネジ穴の上下に残す肉厚 [mm]
SCREW_WALL = 0.6


def min_boss_height(lig_p: dict) -> float:
    """ネジ穴が耳に収まるのに必要な耳の高さ [mm]。"""
    _, hole_d, _ = screw_spec(lig_p)
    return hole_d + 2.0 * SCREW_WALL


def screw_axis_y(ref_p: dict, lig_p: dict) -> float:
    """ネジ軸の Y 座標。耳の中ほどを狙いつつ、穴が耳から出ないようクランプする。

    中央固定（boss_height×0.5）だと耳が低いときに穴が上へ突き抜け、閉じた穴では
    なく上に開いたスロットになってネジが抜ける。
    """
    base = inner_radius(ref_p, lig_p) + lig_p["band_thickness"]   # 耳の付け根
    top = base + lig_p["boss_height"]                             # 耳の頂点
    _, hole_d, _ = screw_spec(lig_p)
    margin = hole_d / 2.0 + SCREW_WALL
    if top - base < 2.0 * margin:      # 耳が低すぎる（カードが warn を出す）
        return (base + top) / 2.0
    return min(max(base + lig_p["boss_height"] * 0.5, base + margin), top - margin)


def required_screw_length(lig_p: dict) -> float:
    """必要なネジ首下長さ [mm]。両側の耳とスリットを貫通する長さ。"""
    return lig_p["slit_width"] + 2.0 * ear_thickness(lig_p) + 1.0


def stock_screw_length(lig_p: dict) -> int:
    """必要長を満たす最小の市販長さ。"""
    need = required_screw_length(lig_p)
    for s in STOCK_SCREW_LENGTHS:
        if s >= need:
            return s
    return STOCK_SCREW_LENGTHS[-1]


# ---------------------------------------------------------------- 影響領域・断面図

def param_regions(ref_p: dict, lig_p: dict) -> dict:
    z0, z1 = seat_range(ref_p, lig_p)

    def r(side, label):
        return {"z0": round(z0, 2), "z1": round(z1, 2), "side": side, "label": label}

    band = r("all", "バンド（帯）")
    boss = r("top", "ネジ座（耳）")
    return {
        "band_width": band,
        "band_thickness": band,
        "seat_offset": band,
        "clearance": band,
        "reed_clearance": r("bottom", "リード接触面"),
        "screw_count": boss,
        "screw_size": boss,
        "boss_height": boss,
        "slit_width": r("top", "スリット（締め代）"),
        "plate_type": r("bottom", "圧力プレート（リード側）"),
        "min_wall": band,
        # material は形状に影響しない → 領域なし
    }


def section_polylines(ref_p: dict, lig_p: dict, reed_thickness: float) -> dict:
    """帯断面図（SVG描画用、単位mm）。軸方向ではなく XY 断面を描く。

    帯の**中央**の断面を描く。テーブルが傾いているので前後端では図の高さが変わる
    （中央を代表に採るのは、帯の内周径・ネジ座もそこを基準にしているのと同じ理由）。
    """
    z0, z1 = seat_range(ref_p, lig_p)
    zm = (z0 + z1) / 2.0
    inner = inner_sections(ref_p, lig_p, reed_thickness)[1]["pts"]
    outer = outer_sections(ref_p, lig_p, reed_thickness)[1]["pts"]
    return {
        "inner": inner + [inner[0]],
        "outer": outer + [outer[0]],
        "reed_face_y": reed_face_y(ref_p, lig_p, reed_thickness, zm),
        "table_y": profiles.table_plane_y(ref_p, zm),
    }
