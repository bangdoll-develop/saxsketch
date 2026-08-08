# -*- coding: utf-8 -*-
"""マウスピース設計パラメータのプリセット（サイズ別）。

出所: saxsketch/instruments/saxophone/templates/{soprano,alto,tenor}.json の
"mouthpiece" ブロック。3 つの FreeCAD 生成マクロ（variant_a/b/c）が共有する。

寸法を 1 箇所に集約しているので、サイズを変えたいときは各マクロ先頭の
`SIZE = "tenor"` を "alto" / "soprano" に変えるだけでよい。個別に寸法を
いじりたいときは各マクロ内でプリセットを読んだ後に上書きするか、下の値を
直接編集する（アプリ本体には影響しない。ここは FreeCAD 用の独立コピー）。

座標系（全マクロ共通・アプリ準拠）:
  Z: 軸方向。z=0 がティップ（先端）、z=overall_length がシャンク端。
  Y: +Y がビーク（上面）、-Y がテーブル（リード側）。
  X: 幅方向。
単位はすべて mm。
"""

PRESETS = {
    "soprano": {
        "tip_opening": 1.4, "facing_length": 18.0, "facing_curve": "elliptic",
        "tip_rail_width": 0.9, "side_rail_width": 0.9,
        "baffle_type": "rollover", "baffle_height": 2.2, "rollover_radius": 6.0,
        "throat_ratio": 0.62, "chamber_shape": "round", "chamber_ratio": 1.1,
        "bore_dia": 14.2, "bore_length": 28.0, "cork_depth": 23.0,
        "window_length": 33.0, "reed_width": 12.9,
        "beak_height": 12.9, "body_dia": 23.5, "overall_length": 72.2,
        "min_wall": 1.8, "material": "resin",
    },
    "alto": {
        "tip_opening": 1.8, "facing_length": 21.0, "facing_curve": "elliptic",
        "tip_rail_width": 1.0, "side_rail_width": 1.0,
        "baffle_type": "rollover", "baffle_height": 2.0, "rollover_radius": 8.0,
        "throat_ratio": 1.0, "chamber_shape": "round", "chamber_ratio": 1.45,
        "bore_dia": 17.5, "bore_length": 26.0, "cork_depth": 22.0,
        "window_length": 29.0, "reed_width": 13.4,
        "beak_height": 13.8, "body_dia": 25.0, "overall_length": 81.2,
        "min_wall": 2.0, "material": "resin",
    },
    "tenor": {
        "tip_opening": 2.2, "facing_length": 23.0, "facing_curve": "elliptic",
        "tip_rail_width": 1.1, "side_rail_width": 1.1,
        "baffle_type": "rollover", "baffle_height": 1.8, "rollover_radius": 10.0,
        "throat_ratio": 1.0, "chamber_shape": "round", "chamber_ratio": 1.5,
        "bore_dia": 19.4, "bore_length": 26.0, "cork_depth": 22.0,
        "window_length": 33.0, "reed_width": 14.8,
        "beak_height": 15.1, "body_dia": 27.5, "overall_length": 88.6,
        "min_wall": 2.2, "material": "resin",
    },
}


def preset(size):
    """サイズ名からパラメータ辞書のコピーを返す。"""
    if size not in PRESETS:
        raise KeyError("unknown size %r (choose from %s)"
                       % (size, ", ".join(PRESETS)))
    return dict(PRESETS[size])
