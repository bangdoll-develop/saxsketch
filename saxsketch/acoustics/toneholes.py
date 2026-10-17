"""側孔 1 個の音響（Phase 4-B.2b）。純数学・OCCT 非依存。

**新しい物理ではない。** 式の原典は Dubos ら 1999（`length_corrections` に
書誌を挙げた）で、OpenWind 0.12.4 の `JunctionTjoint` も同じ原典に拠る。
ここは原典の式から書いてある。`sound_speed()` が Zuckerwar の式を置いてあるのと
同じ理由 —— 教科書式で推測すると 2 つのエンジンが違う楽器を解く。
合っているかは文献を読んだだけでは決めず、**OpenWind と突き合わせて測る**
（`cad/body/sweep_holes.py` とテスト）。

側孔は 3 つの部品でできている:

  1. **接合部の質量**（分岐そのものが持つ慣性）。直列 `m_a` と並列 `m_s`。
     OpenWind の `JunctionTjoint.__compute_length_corr` と同じ長さ補正から出す。
  2. **チムニー**（管壁＋外へ立ち上げたピップ）。半径 `r_side` の短い管。
  3. **終端**。開なら放射、閉なら剛体。

**チムニーの長さは「外に出ている高さ」ではない。** ボア内面から天面までで、
壁の厚みを必ず含む（`body_profiles.hole_chimney_mm`）。ここで二重計上すると、
肉厚を動かしたときに音響が黙って置き去りになる。

損失と放射は**管と同じモデル**を使う（`openwind_bridge._complex_wavenumber` /
`_radiation_impedance`）。側孔だけ別の近似を使うと、どこで差が出たのか
分からなくなる。循環 import を避けるため関数の中で読む。
"""
from __future__ import annotations

import math

import numpy as np

#: 接合部の「合流体積」を質量に含めるか。**OpenWind の既定は False** なので
#: 揃えてある。ここを True にするなら OpenWind 側にも `matching_volume=True` を
#: 渡すこと（片方だけ変えると 2 エンジンが違う楽器を解く）。
MATCHING_VOLUME = False

#: 全閉から順に開けたときの目標音（半音）。リコーダと同じ並びで、
#: **最もベル寄りの穴が +2 半音**、最も上（マウスピース寄り）が +12 半音。
#: 長音階（ドレミファソラシド）。7 本より少ないときは先頭から採る。
SCALE_STEPS: tuple[int, ...] = (2, 4, 5, 7, 9, 11, 12)


def length_corrections(
        r_main: float, r_side: float,
        matching_volume: bool = MATCHING_VOLUME) -> tuple[float, float, float]:
    """接合部の長さ補正 (t_i, t_mv, t_a) [m]。

    原典は Dubos, Kergomard, Khettabi, Dalmont, Keefe, Nederveen (1999),
    "Theory of sound propagation in a duct with a branched tube using modal
    decomposition", Acta Acustica 85(2), 153-169。
    OpenWind の `JunctionTjoint` も同じ原典の式を使っており、両者の値が
    一致することをテストで確かめている。

    δ = r_side / r_main。短いチムニー近似の範囲でしか正しくない。
    """
    d = r_side / r_main
    t_i = r_side * (0.82 - 0.193 * d - 1.09 * d ** 2 + 1.27 * d ** 3 - 0.71 * d ** 4)
    t_mv = r_side * d / 8.0 * (1.0 + 0.207 * d ** 3) if matching_volume else 0.0
    t_a = r_side * (-0.37 + 0.087 * d) * d ** 2
    return t_i, t_mv, t_a


def junction_masses(r_main: float, r_side: float, rho: float,
                    matching_volume: bool = MATCHING_VOLUME) -> tuple[float, float]:
    """接合部の音響質量 (m_s, m_a) [kg/m^4]。

    `m_s` は分岐側（並列）、`m_a` は本管側（直列）。**`m_a` は負**
    （t_a の括弧が δ < 4.25 で負）。直列インピーダンスが負の慣性になるのは
    側孔の既知の性質で、符号ミスではない。
    """
    t_i, t_mv, t_a = length_corrections(r_main, r_side, matching_volume)
    m_s = rho * (t_i + t_mv) / (math.pi * r_side * r_side)
    m_a = rho * t_a / (math.pi * r_main * r_main)
    return m_s, m_a


def chimney_impedance(freqs: np.ndarray, r_side: float, length_m: float,
                      open_: bool) -> np.ndarray:
    """チムニーを見込むインピーダンス [Pa·s/m^3]（接合部の質量は含まない）。

    開: 半径 `r_side`・長さ `length_m` の管に放射インピーダンスを負荷。
    閉: 同じ管の剛体終端 → -j·Z0·cot(k·l)。

    長さ 0 の極限は、開なら放射そのもの、閉なら無限大（＝穴が無いのと同じ）。
    """
    from saxsketch.acoustics import openwind_bridge as ob

    s = math.pi * r_side * r_side
    z0 = ob.RHO * ob.C_SOUND / s
    kc = ob._complex_wavenumber(freqs, r_side)
    theta = kc * max(length_m, 0.0)
    tan_t = np.tan(theta)
    if not open_:
        # 剛体終端。長さ 0 では発散する（穴が無いのと同じ）ので大きな値で止める。
        with np.errstate(divide="ignore", invalid="ignore"):
            z = -1j * z0 / tan_t
        return np.where(np.isfinite(z), z, 1e12 * z0)
    z_rad = ob._radiation_impedance(freqs, r_side)
    return z0 * (z_rad + 1j * z0 * tan_t) / (z0 + 1j * z_rad * tan_t)


def junction_matrix(freqs: np.ndarray, r_main: float, r_side: float,
                    chimney_m: float, open_: bool):
    """側孔 1 個の伝達行列 (a11, a12, a21, a22)。対称 T 型。

        [[1, Za/2], [0, 1]] · [[1, 0], [1/Zs, 1]] · [[1, Za/2], [0, 1]]

    直列 `Za = jω·m_a`（負の慣性）、並列 `Zs = jω·m_s + Z_chimney`。
    行列式は恒等的に 1（可逆・相反）で、テストで固定してある。
    """
    from saxsketch.acoustics import openwind_bridge as ob

    m_s, m_a = junction_masses(r_main, r_side, ob.RHO)
    omega = 2.0 * math.pi * np.asarray(freqs, dtype=float)
    za = 1j * omega * m_a
    zs = 1j * omega * m_s + chimney_impedance(freqs, r_side, chimney_m, open_)
    half = za / (2.0 * zs)
    return 1.0 + half, za * (1.0 + half / 2.0), 1.0 / zs, 1.0 + half


# --------------------------------------------------------------------------- 運指表

def scale_steps(n_holes: int) -> tuple[int, ...]:
    """指孔 n 本ぶんの目標音（全閉からの半音）。ベル寄りの穴から順。"""
    return SCALE_STEPS[:max(0, int(n_holes))]


def successive_fingerings(holes: list[dict]) -> list[tuple[str, tuple[bool, ...]]]:
    """全閉 → ベル寄りから 1 つずつ開ける運指の列。

    `holes` は**弧長の昇順**（マウスピース寄りが先頭）。指孔だけを開け、
    親指孔（`role == "thumb"`）は全部の運指で閉じたまま扱う ——
    親指孔はレジスタ用のベントで、音階の段ではない。

    Returns: [(表示名, 各穴の開閉タプル), …]。長さは指孔の本数 + 1。
    """
    finger_idx = [i for i, h in enumerate(holes) if h.get("role") != "thumb"]
    out: list[tuple[str, tuple[bool, ...]]] = []
    for k in range(len(finger_idx) + 1):
        flags = [False] * len(holes)
        for i in finger_idx[len(finger_idx) - k:]:      # ベル寄りから k 本
            flags[i] = True
        out.append(("全閉" if k == 0 else f"{k}孔開", tuple(flags)))
    return out
