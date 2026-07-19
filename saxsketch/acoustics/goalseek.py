"""目標逆算（ゴールシーク）: 目標の音色指標からパラメータを逆算する。

Tier2 回帰 + Tier1 容積モデル上で scipy により最適化する。
結果は「提案」であり、UI 側で差分表示 → ユーザー承認後に適用する。
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from . import brightness as br
from . import volume as vol

# 最適化対象の連続パラメータ
OPT_KEYS = ["tip_opening", "facing_length", "baffle_height", "throat_ratio"]


def goal_seek(params: dict, specs: list, targets: dict, size_info: dict,
              volume_fn) -> dict:
    """targets 例: {"brightness": 7.0, "power": 6.0, "pitch_neutral": true}

    volume_fn(params) -> {"total_cc", "effective_cc"}（コンポーネント側の体積計算）
    Returns: {proposal: {param: value}, predicted: metrics, residual: float}
    """
    spec_map = {s.key: s for s in specs}
    keys = [k for k in OPT_KEYS if k in spec_map]
    x0 = np.array([float(params[k]) for k in keys])
    bounds = [(spec_map[k].min, spec_map[k].max) for k in keys]

    metric_targets = {k: v for k, v in targets.items()
                      if k in br.METRIC_KEYS and v is not None}
    pitch_neutral = bool(targets.get("pitch_neutral", False))

    def apply_x(x):
        q = dict(params)
        for k, xv in zip(keys, x):
            q[k] = float(xv)
        return q

    def objective(x):
        q = apply_x(x)
        m = br.tone_metrics(q)
        err = sum((m[k] - t) ** 2 for k, t in metric_targets.items())
        if pitch_neutral:
            t1 = vol.tier1_report(volume_fn(q), size_info)
            err += (t1["deviation_cents"] / 25.0) ** 2  # 25セントで指標1相当
        # 現在値からの逸脱ペナルティ（最小変更で目標を達成する）
        err += 0.01 * float(np.sum(((x - x0) / (np.array([b[1] - b[0] for b in bounds]))) ** 2))
        return err

    res = minimize(objective, x0, method="Nelder-Mead",
                   options={"maxiter": 400, "xatol": 1e-3, "fatol": 1e-4})
    x = np.clip(res.x, [b[0] for b in bounds], [b[1] for b in bounds])
    q = apply_x(x)

    # ステップ刻みに丸める
    proposal = {}
    for k, xv in zip(keys, x):
        step = spec_map[k].step or 0.01
        proposal[k] = round(round(float(xv) / step) * step, 4)
    q.update(proposal)

    predicted = br.tone_metrics(q)
    t1 = vol.tier1_report(volume_fn(q), size_info)
    return {
        "proposal": proposal,
        "current": {k: params[k] for k in keys},
        "predicted_metrics": predicted,
        "predicted_tier1": t1,
        "residual": round(float(res.fun), 4),
        "note": "推定モデル上の逆算提案です。適用前に差分を確認してください。",
    }
