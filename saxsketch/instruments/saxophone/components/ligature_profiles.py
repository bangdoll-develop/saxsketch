"""リガチャーの断面プロファイル（純数学・OCCT非依存）。

マウスピース外形（`profiles.outer_radius` / `profiles.table_y` /
`profiles.ligature_seat_range`）を**そのまま参照**して内周を生成する。これが
「マウスピース外形との自動整合」の実体で、参照マウスピースのボディ径を変えれば
リガチャー内周が追従する。

座標系はマウスピースと共通:
  Z: 軸方向（マウスピース先端 z=0 基準）。Y: +Y がビーク側、-Y がテーブル側。

断面の形:
  上側（ビーク側）はマウスピース外形の円弧。テーブル面の高さから下は、
  **リードを収めるタブ**（幅=リード幅、深さ=リード厚）が円の外へ張り出す。
  アルト標準ではテーブル面 y=-11.0 に対し外形半径が 13.75mm なので、厚さ 2.8mm の
  リードの裏面（y=-13.8）は円の下端より外に出る。円を切り落とす D 形にすると
  リードが入らない。締め代のスリットとネジ座はビーク側（+Y）に置く。

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


def reed_face_y(ref_p: dict, lig_p: dict, reed_thickness: float) -> float:
    """リードを挟む面の Y 座標（テーブル面からリード厚 + 逃げだけ離れた位置）。"""
    return profiles.table_y(ref_p) - reed_thickness - lig_p["reed_clearance"]


def _wrap_section(radius: float, table_y: float, tab_hw: float, tab_bottom: float,
                  samples: int = 72) -> list[tuple[float, float]]:
    """円弧（テーブル面より上）＋リードのタブ（下）の断面。反時計回り。

    順序を誤ると自己交差してロフトが破綻するため、向きを固定する:
    タブ底辺を +x 方向 → 右の立ち上がり → テーブル面の棚 → 上側の円弧 →
    左の棚と立ち下がり。
    """
    yt = min(table_y, radius - 0.5)
    yt = max(yt, -(radius - 0.5))       # 円と必ず交わるようにする
    x_c = math.sqrt(max(radius * radius - yt * yt, 0.0))
    hw = min(tab_hw, x_c - 0.2)         # タブは棚の幅に収める
    pts = [(-hw, tab_bottom), (hw, tab_bottom), (hw, yt), (x_c, yt)]
    th0 = math.atan2(yt, x_c)           # 負の角度
    span = math.pi - 2.0 * th0          # 上側を回って (-x_c, yt) まで
    n = max(samples - 6, 12)
    for i in range(1, n):
        th = th0 + span * i / n
        pts.append((radius * math.cos(th), radius * math.sin(th)))
    pts += [(-x_c, yt), (-hw, yt)]
    return pts


def _sections(ref_p: dict, lig_p: dict, reed_thickness: float,
              offset: float) -> list[dict]:
    """内周（offset=clearance）／外周（offset=clearance+band_thickness）の断面列。

    テーブル面の基準はマウスピース モデルの `table_y`。モデルではシャンク側で
    テーブルがランプで消えるが、リードとリガチャーはテーブル平面そのものを
    基準にするため、帯の全長で同じ高さを使う（＝角柱状で堅牢）。
    """
    z0, z1 = seat_range(ref_p, lig_p)
    yt = profiles.table_y(ref_p)
    tab_hw = ref_p["reed_width"] / 2.0 + offset
    tab_bottom = reed_face_y(ref_p, lig_p, reed_thickness) - offset
    return [{"z": z,
             "pts": _wrap_section(profiles.outer_radius(ref_p, z) + offset,
                                  yt, tab_hw, tab_bottom)}
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


def flat_half_width(ref_p: dict, lig_p: dict, reed_thickness: float) -> float:
    """リード接触面（タブ底面）の半幅。圧力プレートの寸法根拠。"""
    return ref_p["reed_width"] / 2.0 + lig_p["clearance"]


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


def screw_axis_y(ref_p: dict, lig_p: dict) -> float:
    """ネジ軸の Y 座標（耳の中ほど）。"""
    r = inner_radius(ref_p, lig_p)
    return r + lig_p["band_thickness"] + lig_p["boss_height"] * 0.5


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
    """帯断面図（SVG描画用、単位mm）。軸方向ではなく XY 断面を描く。"""
    inner = inner_sections(ref_p, lig_p, reed_thickness)[1]["pts"]
    outer = outer_sections(ref_p, lig_p, reed_thickness)[1]["pts"]
    return {
        "inner": inner + [inner[0]],
        "outer": outer + [outer[0]],
        "reed_face_y": reed_face_y(ref_p, lig_p, reed_thickness),
        "table_y": profiles.table_y(ref_p),
    }
