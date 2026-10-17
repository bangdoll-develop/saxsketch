"""寸法 1 本を組み立てるヘルパ（楽器非依存）。

`Component.dimensions()` が返す線分の形をここだけで決める。**値は線の両端から
測る**ので、ラベルの数字と実際に引かれる線の長さが食い違う経路が存在しない
（`value` を引数で渡せるようにすると、そこが必ず食い違いの入口になる）。

もう 1 つの仕事は**公称値との突き合わせ**。この repo は「スライダの値と実際の形が
違う」穴を 6 回踏んでいる（`window_length` / `tip_thickness_for_strength` /
`seat_range` …）。寸法は形から測るので、スライダの値と `spec.step` 1 目盛より
大きく食い違えば、それがそのまま図に出る。
"""
from __future__ import annotations

import math

from .schema import ParamSpec

from saxsketch import i18n


def dim(a, b, direction, *, spec: ParamSpec | None = None,
        params: dict | None = None, level: int = 0,
        key: str | None = None, label: str | None = None,
        unit: str | None = None) -> dict:
    """寸法 1 本。

    Args:
        a, b: 測る 2 点（コンポーネント自身のモデル座標 [x, y, z]）。
        direction: 寸法線を本体から逃がす向き。正規化して返す（`b - a` と直交
            させるのは呼び出し側の責任。テストで固定してある）。
        spec: 対応する `ParamSpec`。渡すと名前・単位・公称値の閾値がスキーマ
            1 か所から来る。対応するパラメータが無い量は `key`/`label`/`unit` を直接渡す。
        params: 現在値。`spec` と一緒に渡すと、公称値と `spec.step` 1 目盛より
            大きく違うときだけ `requested` を付ける。
        level: 同じ向きへ逃がす寸法の段。0 が本体にいちばん近い。

    Returns:
        {"key", "label", "unit", "value", "a", "b", "dir", "level"[, "requested"]}
        `value` は **|b − a|**。丸めない（UI 側が表示桁を決める）。
    """
    ax, ay, az = (float(v) for v in a)
    bx, by, bz = (float(v) for v in b)
    value = math.dist((ax, ay, az), (bx, by, bz))

    dx, dy, dz = (float(v) for v in direction)
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    if n < 1e-12:
        raise ValueError(i18n.t("寸法線を逃がす向きがゼロベクトルです"))
    dx, dy, dz = dx / n, dy / n, dz / n

    out = {
        "key": key or (spec.key if spec else ""),
        "label": label or (spec.label if spec else ""),
        "unit": unit if unit is not None else (spec.unit if spec else "mm"),
        "value": value,
        "a": [ax, ay, az],
        "b": [bx, by, bz],
        "dir": [dx, dy, dz],
        "level": int(level),
    }
    if spec is not None and params is not None and spec.key in params:
        requested = float(params[spec.key])
        # 閾値はスキーマの刻み。1 目盛より小さい差は「スライダで指せない差」なので
        # 出さない（テーパの端数のような、常に出て意味のない併記を増やさない）。
        if abs(value - requested) > max(spec.step or 0.0, 1e-9):
            out["requested"] = requested
    return out


def in_section_plane(d: dict) -> bool:
    """x=0 の断面へそのまま写せる寸法か。**宣言ではなく座標から導く**。

    両端が中央面にあり、逃がす向きも面内であることが条件。x 方向の寸法
    （テーブル実幅など）はここで自動的に落ちる。
    """
    return abs(d["a"][0]) < 1e-9 and abs(d["b"][0]) < 1e-9 and abs(d["dir"][0]) < 1e-9
