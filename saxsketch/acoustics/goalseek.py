"""目標逆算（ゴールシーク）: 目標の音色指標からパラメータを逆算する。

Tier2 回帰 + Tier1 容積モデル上で scipy により最適化する。
結果は「提案」であり、UI 側で差分表示 → ユーザー承認後に適用する。
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from saxsketch import i18n

from . import brightness as br
from . import volume as vol

# 最適化対象の連続パラメータ
OPT_KEYS = ["tip_opening", "facing_length", "baffle_height", "throat_ratio"]

#: `pitch_neutral` が目指す実効容積 / 欠損円錐の比。
#:
#: 0 ではない。実測を入れた 3 サイズは、目標音で鳴る挿し込み量のとき
#: soprano +25% / alto +21% / tenor +26% になる。マウスピースは代替する欠損円錐
#: より短いので、太いぶんと短いぶんが釣り合ったところが「合っている」状態で、
#: 容積が一致する点ではない。3 サイズの平均を採る。
PITCH_NEUTRAL_RATIO = 0.24


def goal_seek(params: dict, specs: list, targets: dict, size_info: dict,
              volume_fn) -> dict:
    """targets 例: {"brightness": 7.0, "power": 6.0, "pitch_neutral": true}

    volume_fn(params) -> {"total_cc", "effective_cc"}（コンポーネント側の体積計算）
    Returns: {proposal: {param: value}, predicted: metrics, residual: float}
    """
    spec_map = {s.key: s for s in specs}
    keys = [k for k in OPT_KEYS if k in spec_map]
    x0 = np.array([float(params[k]) for k in keys])
    # **探索は「勧める帯」の中で行う。** ゴールシークは理論側の提案なので、
    # 頼まれてもいないのに慣習の外へ出さない（帯の外へ出るのは利用者の判断で、
    # そのためにスライダの壁を広げてある）。
    # ただし**利用者が既に帯の外にいるときは、そこを含むように広げる** ——
    # 広げないと最適化が黙って帯の中へ引き戻し、利用者の選択を消してしまう。
    bounds = []
    for k in keys:
        s = spec_map[k]
        v = float(params[k])
        lo = s.min if s.min is None else min(s.min, v)
        hi = s.max if s.max is None else max(s.max, v)
        bounds.append((lo, hi))

    metric_targets = {k: v for k, v in targets.items()
                      if k in br.METRIC_KEYS and v is not None}
    pitch_neutral = bool(targets.get("pitch_neutral", False))

    def apply_x(x):
        q = dict(params)
        for k, xv in zip(keys, x):
            q[k] = float(xv)
        return q

    target_cc = vol.missing_cone(size_info)["cc"]

    def objective(x):
        q = apply_x(x)
        m = br.tone_metrics(q)
        err = sum((m[k] - t) ** 2 for k, t in metric_targets.items())
        if pitch_neutral:
            # ここは**容積比**で測る。音程そのもの（第1共鳴）は伝達行列法を解くので
            # 1 回 31〜52ms あり、Nelder-Mead が 400 回まわると 20 秒近くかかる。
            # 最適化に要るのは向きと大小だけで、セントの絶対値ではない。
            # 狙いは比 0 ではなく **+21%**。実測を入れた 3 サイズは、目標音で鳴る
            # 挿し込み量のとき実効容積が欠損円錐の +21〜26% になる（soprano +25 /
            # alto +21 / tenor +26）。0 を目指すのは到達不能な点を目指すこと。
            # 幅 0.1（＝10 ポイント）で指標 1 相当。
            ratio = (volume_fn(q)["effective_cc"] - target_cc) / target_cc
            err += ((ratio - PITCH_NEUTRAL_RATIO) / 0.1) ** 2
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
    # 提案 1 件だけは実際に共鳴を解いて報告する（最適化ループの外なので 1 回で済む）
    from . import openwind_bridge as ob
    t1 = vol.tier1_report(volume_fn(q), size_info,
                          ob.tuning_position(q, size_info))
    return {
        "proposal": proposal,
        "current": {k: params[k] for k in keys},
        "predicted_metrics": predicted,
        "predicted_tier1": t1,
        "residual": round(float(res.fun), 4),
        "note": i18n.t("推定モデル上の逆算提案です。適用前に差分を確認してください。"),
    }
