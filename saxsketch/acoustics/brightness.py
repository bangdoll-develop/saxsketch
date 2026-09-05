"""Tier2: 音色指標の回帰モデルと感度ガイド。

根拠: Acta Acustica 2021「Towards 3D printed saxophone mouthpiece
personalization」— スペクトル重心（明るさ）に有効なのはフェイシング長・
バッフル高・スロート断面積。ここに市場知見（ティップ開き→音量、
チェンバー→ダーク等）を重ねた 0-10 の指標セット。
係数は文献の傾向を反映した経験的モデルであり、絶対値ではなく
「パラメータを動かしたときの相対変化」を読むためのもの。
"""
from __future__ import annotations


def _norm(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.5
    return min(max((x - lo) / (hi - lo), 0.0), 1.0)


#: 各入力の**モデルの有効範囲**。`ParamSpec` の「勧める帯」と数値は同じだが、
#: 意味が違う ——こちらは回帰を当てた範囲で、外挿する根拠が無い。帯を広げても
#: ここは広げない（広げたら文献の裏付けの無い外挿になる）。代わりに
#: **外にいることを `note` で言う**。黙って平らになるのが一番まずい。
_MODEL_RANGE = {
    "tip_opening": (1.0, 3.2, "ティップ開き", "mm"),
    "facing_length": (16.0, 30.0, "フェイシング長", "mm"),
    "baffle_height": (0.0, 5.0, "バッフル高さ", "mm"),
    "throat_ratio": (0.60, 1.35, "スロート断面積比", ""),
}


def _outside_model(p: dict) -> list[str]:
    """モデルの有効範囲の外にある入力（表示用の文字列）。"""
    out = []
    for k, (lo, hi, label, unit) in _MODEL_RANGE.items():
        v = p.get(k)
        if v is None:
            continue
        if v < lo or v > hi:
            out.append(f"{label} {v:g}{unit}（有効範囲 {lo:g}〜{hi:g}{unit}）")
    return out


_BAFFLE_BONUS = {"straight": 0.0, "rollover": 0.06, "step": 0.14, "curve": 0.24}
#: チェンバー断面形状のエッジ寄与。角断面ほど倍音が複雑でエッジが出る。
_CHAMBER_EDGE = {"round": 0.0, "square": 0.06, "horseshoe": 0.0, "flat_sidewall": 0.03}


def _baffle_shape_bonus(p: dict) -> float:
    """バッフルの作り込み（断面ハンドル）ぶんの明るさ寄与。

    `_BAFFLE_BONUS` の型別一律だけだと、断面エディタでハンドルを動かしても
    指標が微動だにしない＝画面が形を説明していないことになる。向きは
    「気道を絞るほど明るい」で統一する:
      - 棚が長い（`baffle_plateau` 大）ほどリード直上の絞りが長く続く
      - 段が切り立つ（`baffle_step_rise` 大）ほど衝突が強い
      - カーブが正（`baffle_curvature` > 0）ほどティップ側で絞る
    係数は `_BAFFLE_BONUS` と同じく**経験値**で実測の裏付けは無い。
    実効値（型ごとのクランプ後）を使うため `profiles` の関数を借りる。
    """
    from saxsketch.instruments.saxophone.components import profiles

    kind = p.get("baffle_type", "step")
    bonus = 0.0
    if kind in ("step", "rollover"):
        bonus += 0.10 * (profiles.baffle_plateau(p) - 0.36) / 0.34
    if kind == "step":
        bonus += 0.12 * min(max(p.get("baffle_step_rise", 0.0), 0.0), 0.85) / 0.85
    if kind == "curve":
        bonus += 0.10 * min(max(p.get("baffle_curvature", 0.0), -1.0), 1.0)
    return bonus


def tone_metrics(p: dict) -> dict:
    """音色指標（0-10）。

    **入力が `_MODEL_RANGE` の外だと指標はそこで頭打ちになる。** 回帰を当てた
    範囲の外なので、外挿せずクランプする。ただし黙ってはいけない ——
    スライダを動かしてもレーダーが動かないのは、この repo で何度も踏んでいる
    「効いていないのに気づけない」型そのもの。`note` に外にいる入力を並べる。
    """
    n_tip = _norm(p["tip_opening"], *_MODEL_RANGE["tip_opening"][:2])
    n_facing = _norm(p["facing_length"], *_MODEL_RANGE["facing_length"][:2])
    n_baffle = min(max(_norm(p["baffle_height"], *_MODEL_RANGE["baffle_height"][:2])
                       + _BAFFLE_BONUS.get(p.get("baffle_type", "step"), 0.0)
                       + _baffle_shape_bonus(p), 0.0), 1.0)
    n_throat_small = 1.0 - _norm(p["throat_ratio"], *_MODEL_RANGE["throat_ratio"][:2])
    square_bonus = _CHAMBER_EDGE.get(p.get("chamber_shape", "round"), 0.0)

    brightness = 10.0 * (0.34 * n_baffle + 0.28 * n_facing
                         + 0.24 * n_throat_small + 0.14 * n_tip)
    power = 10.0 * (0.45 * n_tip + 0.35 * n_baffle + 0.20 * n_throat_small)
    resistance = 10.0 * (0.55 * n_tip + 0.25 * n_throat_small + 0.20 * n_facing)
    flexibility = 10.0 * (0.50 * n_facing + 0.30 * n_tip
                          + 0.20 * (1.0 - n_throat_small))
    edge = min(10.0 * (0.60 * n_baffle + 0.34 * n_throat_small + square_bonus), 10.0)

    return {
        "brightness": round(brightness, 2),
        "power": round(power, 2),
        "resistance": round(resistance, 2),
        "flexibility": round(flexibility, 2),
        "edge": round(edge, 2),
        "labels": {
            "brightness": "明るさ",
            "power": "パワー",
            "resistance": "抵抗感",
            "flexibility": "柔軟性",
            "edge": "エッジ",
        },
        "note": _note(p),
    }


def _note(p: dict) -> str:
    base = "相対比較用の推定指標（文献傾向ベース）。数値の絶対値ではなく変化方向を参考に。"
    out = _outside_model(p)
    if not out:
        return base
    return (base + " **" + " / ".join(out) + " がモデルの有効範囲の外にあります。**"
            "この指標はそこで頭打ちになっていて、動かしても変わりません"
            "（回帰を当てた範囲の外なので外挿していません）。"
            "形そのものは変わっているので、断面タブと寸法を見てください。")


# 感度計算の対象パラメータ（連続値のみ）
SENSITIVITY_KEYS = ["tip_opening", "facing_length", "baffle_height", "throat_ratio"]
METRIC_KEYS = ["brightness", "power", "resistance", "flexibility", "edge"]


def sensitivity(p: dict, specs: list) -> dict:
    """各パラメータを1ステップ動かしたときの指標変化（数値偏微分）。

    Returns: {param_key: {metric: delta, ...}, ...} と、指標ごとの最効率パラメータ提案。
    """
    spec_map = {s.key: s for s in specs}
    base = tone_metrics(p)
    table: dict[str, dict] = {}
    for key in SENSITIVITY_KEYS:
        spec = spec_map.get(key)
        if spec is None:
            continue
        step = spec.step or 0.1
        # **止める先は帯ではなく壁**（`ParamSpec.bounds`）。帯の外の値を選んで
        # いる利用者では、帯で止めると 1 段が「+0.05」ではなく「−0.8」になって
        # 感度の符号ごと壊れる（`tip_opening` は帯 3.2 に対し壁 5.2）。
        lo, hi = spec.bounds()
        q = dict(p)
        q[key] = min(p[key] + step, hi) if hi is not None else p[key] + step
        if q[key] == p[key]:  # 上限に張り付いている場合は下方向
            q[key] = max(p[key] - step, lo) if lo is not None else p[key] - step
            step = -step
        m = tone_metrics(q)
        table[key] = {
            "step": step,
            "label": spec.label,
            "unit": spec.unit,
            "deltas": {k: round(m[k] - base[k], 3) for k in METRIC_KEYS},
        }

    # 指標ごとに「上げたいならどのパラメータが最効率か」
    suggestions = {}
    for metric in METRIC_KEYS:
        best_key, best_val = None, 0.0
        for key, row in table.items():
            v = abs(row["deltas"][metric])
            if v > best_val:
                best_key, best_val = key, v
        if best_key:
            row = table[best_key]
            d = row["deltas"][metric]
            direction = "+" if (d > 0) == (row["step"] > 0) else "-"
            suggestions[metric] = {
                "param": best_key,
                "label": row["label"],
                "direction": direction,
                "per_step": round(abs(d), 3),
                "step": abs(row["step"]),
                "unit": row["unit"],
            }
    return {"table": table, "suggestions": suggestions}
