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


_BAFFLE_BONUS = {"straight": 0.0, "rollover": 0.06, "step": 0.14, "curve": 0.24}
#: チェンバー断面形状のエッジ寄与。角断面ほど倍音が複雑でエッジが出る。
_CHAMBER_EDGE = {"round": 0.0, "square": 0.06, "horseshoe": 0.0, "flat_sidewall": 0.03}


def tone_metrics(p: dict) -> dict:
    """音色指標（0-10）。"""
    n_tip = _norm(p["tip_opening"], 1.0, 3.2)
    n_facing = _norm(p["facing_length"], 16.0, 30.0)
    n_baffle = min(_norm(p["baffle_height"], 0.0, 5.0)
                   + _BAFFLE_BONUS.get(p.get("baffle_type", "rollover"), 0.0), 1.0)
    n_throat_small = 1.0 - _norm(p["throat_ratio"], 0.60, 1.35)
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
        "note": "相対比較用の推定指標（文献傾向ベース）。数値の絶対値ではなく変化方向を参考に。",
    }


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
        q = dict(p)
        q[key] = min(p[key] + step, spec.max if spec.max is not None else p[key] + step)
        if q[key] == p[key]:  # 上限に張り付いている場合は下方向
            q[key] = max(p[key] - step, spec.min)
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
