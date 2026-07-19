"""簡易音プレビュー用の倍音列生成（印象プレビュー）。

Tier2 の音色指標からサックス様の倍音振幅列を合成する。
物理モデルではなく「パラメータ変更が音の印象に与える方向」を
耳で確かめるためのもの。フロントエンドは Web Audio の加算合成で再生する。
"""
from __future__ import annotations

import math

N_HARMONICS = 16


def harmonic_series(metrics: dict) -> dict:
    b = metrics["brightness"] / 10.0   # 0-1
    e = metrics["edge"] / 10.0
    p = metrics["power"] / 10.0

    # 明るさ → スペクトル傾斜（明るい = ロールオフが緩い）
    slope = 2.6 - 1.6 * b
    amps = []
    for n in range(1, N_HARMONICS + 1):
        a = 1.0 / (n ** slope)
        # エッジ → 5〜9次あたりのフォルマント的持ち上げ
        formant = 1.0 + e * 0.9 * math.exp(-((n - 7.0) ** 2) / 8.0)
        # サックスらしさ: 偶数次をわずかに強く
        even = 1.06 if n % 2 == 0 else 1.0
        amps.append(a * formant * even)

    peak = max(amps)
    amps = [round(a / peak, 4) for a in amps]

    return {
        "amplitudes": amps,
        "breathiness": round(0.06 + 0.05 * (1.0 - e), 3),   # 息成分ノイズ量
        "vibrato_hz": 5.0,
        "vibrato_depth": 0.004,
        "attack_sec": round(0.05 - 0.02 * p, 3),
        "note": "印象プレビュー（簡易加算合成）。物理的な発音は上のタブ"
                "「物理モデル(OpenWind)」で試聴できます。",
    }
