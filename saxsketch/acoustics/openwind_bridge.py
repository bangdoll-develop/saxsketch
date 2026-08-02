"""Tier3: 共鳴管インピーダンス & 物理モデル音合成（Phase 2）。

マウスピース内部空洞の軸方向断面積プロファイルを抽出し、サックス本体相当の
欠損円錐を結合した「組み立て共鳴管」を作る。その入力インピーダンス Z(f) を
計算し、共鳴ピーク（音程・倍音整列度）を提示する。さらに OpenWind が使える
環境ではリード結合の時間領域シミュで実発音を WAV 合成する。

エンジン二層構成:
  - OpenWind 導入時: `ImpedanceComputation`（周波数領域）＋時間領域リードシミュ。
  - 未導入時: 自作 TMM（伝達行列法・numpy のみ）でインピーダンスを算出。
    → インピーダンス表示は OpenWind の有無に関わらず必ず成立する。
    音合成は OpenWind 必須（未導入時は上位でフロントの印象合成にフォールバック）。

座標系: x はティップ（リード端, x=0, 音響的入力）→ シャンク→本体→ベル開口。
単位は SI（m）。profiles は mm なので変換する。
"""
from __future__ import annotations

import io
import math
import wave

import numpy as np

from saxsketch.instruments.saxophone.components import profiles
from saxsketch.acoustics import volume as ac_volume

# ------------------------------------------------------------------ 物理定数（空気, 20℃前後）
# 返す共鳴ピークの本数。時間領域シミュは高次レジスタで鳴くことがあり、
# 実測 f0 をピーク集合と照合するには 8 本では足りない。
MAX_PEAKS = 12

RHO = 1.2          # 密度 kg/m^3
C_SOUND = 343.0    # 音速 m/s
#: マウスピースのボアからネック小端へ絞る区間の長さ [m]。実物は段差だが、
#: x 単調増加のジオメトリ表現では段差を書けないので短いテーパで代用する。
NECK_STEP = 0.0005
MU = 1.85e-5       # 粘性係数 Pa·s
GAMMA = 1.4        # 比熱比
PR = 0.71          # プラントル数

# ------------------------------------------------------------------ 時間領域シミュの調律点
# dt は CFL で決まり、最小セグメント長が律速する。既定メッシュだと 234倍実時間
# （1.2s の音に 280秒）。order を落とし、時間領域用にジオメトリを粗視化して
# 20倍実時間まで短縮する。インピーダンス計算は元の細かいジオメトリのまま。
SIM_ORDER = 2        # 空間離散化次数（時間領域のみ）
SIM_MIN_DX = 0.008   # 時間領域用ジオメトリの最小セグメント長 [m]
SIM_SR = 44100       # 出力 WAV のサンプルレート

# OpenWind は遅延 import（重い・環境依存）。存在フラグだけ先に判定。
try:  # pragma: no cover - 環境依存
    import openwind  # noqa: F401
    HAS_OPENWIND = True
except Exception:  # pragma: no cover
    HAS_OPENWIND = False


# ================================================================== ジオメトリ

def build_resonator(params: dict, size_info: dict) -> list[list[float]]:
    """組み立て共鳴管ジオメトリ [[x_m, r_m], ...]（ティップ→ベル）。

    構成:
      (a) マウスピース内部空洞: cavity_stations の各断面積 → 等価半径 sqrt(A/pi)
      (b) 円筒ボア: シャンク端まで
      (c) 欠損円錐延長: スロート断面から本体側へ広がる円錐。
          taper は descriptor の半頂角そのもの、全長は記譜最低音の実音で決める
          （組み立て管の第1共鳴が実低音付近に来るように）。
    """
    p = params
    xs: list[float] = []
    rs: list[float] = []

    # (a) マウスピース空洞（各断面 → 等価半径）。断面積は形状依存（馬蹄/フラット
    #     サイドウォールも正しく計上）なので断面ポリゴンから求める。
    #     ここは **リード面で切った実効断面積** を使う: ロフト用ステーションは窓を
    #     開けるためカット面より下へはみ出しており、そのはみ出しは気柱ではない
    #     （リードが塞ぐ）。cavity_volume_cc は同じ切り直しをしているので、
    #     素の section_area を使うと Tier1 と Tier3 の前提が食い違う。
    stations = profiles.cavity_stations(p)
    for s in stations:
        area_mm2 = profiles.effective_section_area(p, s)
        r_eq = math.sqrt(max(area_mm2, 1e-6) / math.pi)  # mm
        xs.append(s["z"] / 1000.0)
        rs.append(r_eq / 1000.0)

    # (b) 円筒ボア。終端はシャンク端ではなく**コーク線**（= overall_length - cork_depth）。
    # シャンク端までを空気柱として数えると、ネックのテノンが埋めている体積まで
    # 気柱に含めてしまう（ソプラノで 3.6cc ＝ マウスピース内容積の 44%）。
    # cavity_volume_cc() は同じ分を neck_occupied として差し引いており、こちらだけ
    # 数えていて Tier1 と Tier3 が食い違っていた。
    r_bore = profiles.bore_radius(p) / 1000.0
    x_cork = max(p["overall_length"] - p["cork_depth"], xs[-1] * 1000.0) / 1000.0
    if x_cork > xs[-1]:
        xs.append(x_cork)
        rs.append(r_bore)

    # (c) 欠損円錐延長
    # 円錐管の第1共鳴は**頂点から**測った全長で決まる。マウスピースが代替するのは
    # 欠損円錐（頂点〜ネック小端）なので、差し引くのはマウスピースの物理長ではなく
    # 欠損円錐長。物理長を引くと管が欠損円錐長との差だけ長くなり、アルトで
    # 161mm 過長 ≒ 270 セント低く出る（3サイズとも同じ量ずれるので系統誤差と分かる）。
    cone = ac_volume.missing_cone(size_info)
    f1 = float(size_info["low_note_sounding_hz"])
    l_total = C_SOUND / (2.0 * f1)                     # 頂点からベルまでの音響長
    l_ext = max(l_total - cone["apex_distance_mm"] / 1000.0, 0.05)

    # 円錐の半頂角は descriptor の実測文献値をそのまま使う
    # （体積定数から逆算していたのをやめた。出所が一本化される）
    tan_theta = cone["tan_theta"]

    # 延長円錐はコーク線の**ネック小端内径**から始まる。マウスピースのボア径は
    # コルクを逃がすぶん太いので、そこから広げ始めると管全体が太くなる。
    # l_ext は「ネック小端からベルまで」として求めた長さなので、始端半径も
    # 同じ r0 でなければ円錐が自己矛盾する。
    # x 単調増加のリストでは段差を表せないので、テノン端の絞りを短いテーパで表す。
    r_neck = cone["throat_radius_mm"] / 1000.0
    xs.append(x_cork + NECK_STEP)
    rs.append(r_neck)
    r_bell = r_neck + tan_theta * l_ext
    xs.append(x_cork + l_ext)
    rs.append(r_bell)

    # x 単調増加を保証（数値誤差で潰れた区間を除去）
    pts: list[list[float]] = []
    for x, r in zip(xs, rs):
        if pts and x <= pts[-1][0] + 1e-6:
            continue
        pts.append([float(x), float(max(r, 1e-4))])
    return pts


def _resample(geometry: list[list[float]], max_slice_m: float = 0.002):
    """区分線形ジオメトリを微小円筒スタックへ離散化。

    Returns: (x_mid, length, radius) の numpy 配列（各スライス）。
    """
    xs = np.array([g[0] for g in geometry])
    rs = np.array([g[1] for g in geometry])
    seg_x, seg_l, seg_r = [], [], []
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        r0, r1 = rs[i], rs[i + 1]
        seg_len = x1 - x0
        n = max(int(math.ceil(seg_len / max_slice_m)), 1)
        dl = seg_len / n
        for k in range(n):
            xa = x0 + dl * k
            xb = xa + dl
            r_mid = r0 + (r1 - r0) * ((xa + xb) / 2 - x0) / seg_len
            seg_x.append((xa + xb) / 2)
            seg_l.append(dl)
            seg_r.append(max(r_mid, 1e-4))
    return np.array(seg_x), np.array(seg_l), np.array(seg_r)


# ================================================================== TMM インピーダンス

def _radiation_impedance(freqs: np.ndarray, r_end: float) -> np.ndarray:
    """開口端（unflanged）放射インピーダンス（低周波近似, Levine–Schwinger）。"""
    s_end = math.pi * r_end * r_end
    z0 = RHO * C_SOUND / s_end
    k = 2.0 * math.pi * freqs / C_SOUND
    ka = k * r_end
    return z0 * (0.25 * ka * ka + 1j * 0.61 * ka)


def _complex_wavenumber(freqs: np.ndarray, a: float) -> np.ndarray:
    """粘性熱損失込みの複素波数（Keefe 近似, 広管）。"""
    omega = 2.0 * math.pi * freqs
    # 境界層による減衰係数 α [1/m]
    alpha = (1.0 / (a * C_SOUND)) * np.sqrt(MU * omega / (2.0 * RHO)) \
        * (1.0 + (GAMMA - 1.0) / math.sqrt(PR))
    # 位相速度も僅かに低下（実部 +α）。e^{j(ωt-kx)} 規約で減衰は虚部 -α。
    return (omega / C_SOUND + alpha) - 1j * alpha


def _tmm_impedance(geometry: list[list[float]], freqs: np.ndarray) -> np.ndarray:
    """微小円筒スタックの伝達行列を連結して入力インピーダンス Zin(f) を得る。"""
    _, seg_l, seg_r = _resample(geometry)

    n_f = len(freqs)
    # 連結行列 M（各要素は周波数配列）。初期は単位行列。
    m11 = np.ones(n_f, dtype=complex)
    m12 = np.zeros(n_f, dtype=complex)
    m21 = np.zeros(n_f, dtype=complex)
    m22 = np.ones(n_f, dtype=complex)

    for length, a in zip(seg_l, seg_r):
        s = math.pi * a * a
        z0 = RHO * C_SOUND / s
        kc = _complex_wavenumber(freqs, a)
        theta = kc * length
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        a11 = cos_t
        a12 = 1j * z0 * sin_t
        a21 = 1j * sin_t / z0
        a22 = cos_t
        # M = M @ A（ティップ側から順に）
        n11 = m11 * a11 + m12 * a21
        n12 = m11 * a12 + m12 * a22
        n21 = m21 * a11 + m22 * a21
        n22 = m21 * a12 + m22 * a22
        m11, m12, m21, m22 = n11, n12, n21, n22

    z_rad = _radiation_impedance(freqs, seg_r[-1])
    # [P_tip; U_tip] = M [P_end; U_end], Z_end = P_end/U_end = z_rad
    zin = (m11 * z_rad + m12) / (m21 * z_rad + m22)
    return zin


# ================================================================== ピーク解析

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _hz_to_note(freq: float) -> str:
    if freq <= 0:
        return "-"
    midi = 69 + 12 * math.log2(freq / 440.0)
    m = int(round(midi))
    name = _NOTE_NAMES[m % 12]
    octave = m // 12 - 1
    cents = round((midi - m) * 100)
    sign = "+" if cents >= 0 else ""
    return f"{name}{octave} ({sign}{cents}c)"


def _cents(f: float, f_ref: float) -> float:
    if f <= 0 or f_ref <= 0:
        return 0.0
    return 1200.0 * math.log2(f / f_ref)


def _analyze(freqs: np.ndarray, z: np.ndarray, size_info: dict, engine: str) -> dict:
    mag = np.abs(z)
    mag_db = 20.0 * np.log10(mag / np.max(mag) + 1e-12)

    # ピーク検出（scipy があれば利用、無ければ単純な極大検出）
    try:
        from scipy.signal import find_peaks
        idx, _ = find_peaks(mag, distance=max(len(freqs) // 60, 3),
                            prominence=np.max(mag) * 0.02)
    except Exception:
        idx = [i for i in range(1, len(mag) - 1)
               if mag[i] > mag[i - 1] and mag[i] > mag[i + 1]
               and mag[i] > 0.05 * np.max(mag)]
        idx = np.array(idx, dtype=int)

    f_target = float(size_info["low_note_sounding_hz"])
    peaks = []
    for i in list(idx)[:MAX_PEAKS]:
        fp = float(freqs[i])
        peaks.append({
            "freq": round(fp, 1),
            "note": _hz_to_note(fp),
            "cents_vs_target": round(_cents(fp, f_target), 1),
        })

    # 倍音整列度（高次ピークが第1ピークの整数倍からどれだけずれるか, cent RMS）
    inharm = None
    if len(peaks) >= 2:
        f1 = peaks[0]["freq"]
        devs = []
        for n, pk in enumerate(peaks[1:], start=2):
            ideal = f1 * n
            devs.append(_cents(pk["freq"], ideal))
        inharm = round(float(np.sqrt(np.mean(np.square(devs)))), 1) if devs else None

    first = peaks[0] if peaks else None
    return {
        "engine": engine,
        "freqs": [round(float(f), 1) for f in freqs],
        "z_db": [round(float(v), 2) for v in mag_db],
        "peaks": peaks,
        "first_note": first["note"] if first else "-",
        "first_cents_vs_target": first["cents_vs_target"] if first else None,
        "inharmonicity_cents": inharm,
        "target_note": _hz_to_note(f_target),
        "note": ("OpenWind（周波数領域）による共鳴ピーク。"
                 if engine == "openwind" else
                 "簡易TMM（自作・伝達行列法）による推定。相対比較用。")
        + " 絶対音程でなくパラメータ変化の方向を参考に。",
    }


# ================================================================== OpenWind 経路

def _openwind_impedance(geometry, freqs, size_info):  # pragma: no cover - 環境依存
    from openwind import ImpedanceComputation
    # geometry: [[x, r], ...]（m）。OpenWind は [x, r] のリストを受け付ける。
    result = ImpedanceComputation(freqs, geometry, temperature=25.0,
                                  source_location='entrance')
    z = np.asarray(result.impedance)
    return _analyze(np.asarray(freqs, dtype=float), z, size_info, "openwind")


# ================================================================== 公開: インピーダンス

def impedance(params: dict, size_info: dict,
              fmin: float = 50.0, fmax: float = 2000.0, n: int = 800) -> dict:
    """入力インピーダンス Z(f) とピーク解析を返す。"""
    freqs = np.linspace(fmin, fmax, n)
    geometry = build_resonator(params, size_info)
    if HAS_OPENWIND:
        try:  # pragma: no cover
            return _openwind_impedance(geometry, freqs, size_info)
        except Exception:
            pass  # OpenWind 失敗時は TMM へ
    z = _tmm_impedance(geometry, freqs)
    return _analyze(freqs, z, size_info, "tmm")


# ================================================================== 公開: 音合成（OpenWind 必須）

SAMPLE_RATE = SIM_SR


def _wav_bytes(signal: np.ndarray, rate: int = SAMPLE_RATE) -> bytes:
    """float 信号 [-1,1] → 16bit PCM WAV bytes。"""
    sig = np.clip(signal, -1.0, 1.0)
    pcm = (sig * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _coarsen(geometry: list[list[float]],
             min_dx: float = SIM_MIN_DX) -> list[list[float]]:
    """時間領域シミュ用にジオメトリを間引く。

    CFL 条件より dt ∝ 最小セグメント長。マウスピース部の 2.8mm 刻みが dt を
    律速して計算が 4 倍遅くなるが、2kHz 以下（波長 17cm 超）では数 mm の
    刻み差は音響的にほぼ効かない。両端点は必ず保持する。
    """
    if len(geometry) <= 2:
        return [list(pt) for pt in geometry]
    out = [list(geometry[0])]
    for pt in geometry[1:-1]:
        if pt[0] - out[-1][0] >= min_dx:
            out.append(list(pt))
    out.append(list(geometry[-1]))
    return out


def _to_audio(sig: np.ndarray, sr0: float) -> np.ndarray:
    """シミュ生信号（sr0 は CFL 由来で数百 kHz）→ 44.1kHz 正規化オーディオ。"""
    from fractions import Fraction

    from scipy.signal import resample_poly

    frac = Fraction(SIM_SR / float(sr0)).limit_denominator(200)
    out = resample_poly(np.asarray(sig, dtype=float),
                        frac.numerator, frac.denominator)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak < 1e-9:
        raise RuntimeError("発振しませんでした（吹圧を上げてください）")
    out = out / peak * 0.9
    # 5ms フェードでクリック除去
    nf = min(int(SIM_SR * 0.005), out.size // 2)
    if nf > 1:
        ramp = np.linspace(0.0, 1.0, nf)
        out[:nf] *= ramp
        out[-nf:] *= ramp[::-1]
    return out


def _measure_f0(sig: np.ndarray, sr: int = SIM_SR) -> float:
    """定常部（立ち上がり後）の rFFT ピークから実測基本周波数を返す。

    立ち上がりは高次モードが暴れるので前半を捨て、定常部（後半50%）だけを見る。
    さらに放物線補間でビン幅以下の精度を出す（0.6s のシミュでビン幅 ~3Hz）。
    """
    sig = np.asarray(sig, dtype=float)
    seg = sig[int(0.5 * sig.size):]
    if seg.size < 64:
        return 0.0
    seg = seg - float(np.mean(seg))     # クレッシェンドの DC ドリフトを除去
    spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size)))
    freqs = np.fft.rfftfreq(seg.size, 1.0 / sr)
    lo = int(np.searchsorted(freqs, 50.0))   # 50Hz 未満（DC・ドリフト）は無視
    if lo >= spec.size - 1:
        return 0.0
    i = lo + int(np.argmax(spec[lo:]))
    if 0 < i < spec.size - 1:  # 放物線補間でビン間を補う
        a, b, c = spec[i - 1], spec[i], spec[i + 1]
        denom = a - 2 * b + c
        if denom != 0:
            i = i + 0.5 * (a - c) / denom
    df = float(freqs[1] - freqs[0])
    return float(i * df)


# レジスタを決めるのは吹圧ではなく**リード共振**（実測: f_reed 1800/2700/3700Hz が
# それぞれ第2/第3/第4共鳴を持続発振させる）。吹圧だけを動かしてもレジスタはほぼ
# 変わらず、上げ過ぎると発振が止まる。よってアンブシュア（＝リードの締め具合＝
# リード共振）を選ばせ、各プリセットに持続を確認済みの吹圧を組で与える。
EMBOUCHURES: dict[str, tuple[float, float]] = {
    "loose":  (1800.0, 1800.0),   # 緩め → 低いレジスタ
    "normal": (2700.0, 2500.0),   # 標準
    "tight":  (3700.0, 2000.0),   # 締め → 高いレジスタ
}
DEFAULT_EMBOUCHURE = "normal"


def _reed_player(params: dict, embouchure: str,
                 override: dict | None = None):  # pragma: no cover - 環境依存
    """マウスピース設計値を反映した有次元 1自由度リード奏者。

    `CLARINET` プリセット（Bilbao 2008）を基点に、設計値は**相対倍率**で効かせる。
    絶対値で上書きするとプリセットの校正が壊れて持続発振しなくなる（実測済み）。
    無次元版（WOODWIND_REED_SCALED）は本ジオメトリで発振しないため採らない。

    `override`（リード コンポーネントから渡る）があれば、リード共振はアンブシュア
    プリセットではなく**リード実形状から算出した f_reed** を使う。幅も実寸に置く。
    リードを設計している以上、リードの物理はリード側の値が正となる。
    """
    from openwind import Player
    from openwind.technical.default_excitator_parameters import (
        constant_with_initial_ramp)

    f_base, mouth_pa = EMBOUCHURES.get(embouchure, EMBOUCHURES[DEFAULT_EMBOUCHURE])
    player = Player("CLARINET")
    player.update_curve("mouth_pressure",
                        constant_with_initial_ramp(mouth_pa, 0.02))

    # 設計パラメータ連動：これが無いと設計を変えても音が変わらない
    player.update_curve("opening", 4e-4 * (params.get("tip_opening", 1.8) / 1.8))
    reed_w = (override or {}).get("width_mm", params.get("reed_width", 14.5))
    player.update_curve("width", 3e-2 * (reed_w / 14.5))
    if override and override.get("f_reed"):
        f_reed = float(override["f_reed"])
    else:
        # フェイシングが長い＝リードの有効長が長い＝リード共振が低い
        f_reed = f_base * (23.0 / max(params.get("facing_length", 23.0), 1.0))
    player.update_curve("pulsation", 2 * math.pi * f_reed)
    player.update_curve("dissip", 3000.0 * f_reed / 3700.0)
    return player, mouth_pa


def _simulate_reed(geometry, params, embouchure, duration,
                   override=None):  # pragma: no cover
    """OpenWind 時間領域リードシミュ → (44.1kHz オーディオ, 実測f0, 吹圧)。"""
    from openwind import simulate

    player, mouth_pa = _reed_player(params, embouchure, override)
    rec = simulate(
        duration,
        _coarsen(geometry),
        player=player,
        losses='diffrepr',   # 時間領域は False / 'diffrepr' のみ（True は不可）
        order=SIM_ORDER,
        temperature=25.0,
        record_energy=False,
        verbosity=0,
    )
    key = 'bell_radiation_pressure'
    if key not in rec.values:
        raise RuntimeError(
            f"OpenWind の録音に {key} がありません: {list(rec.values.keys())}")
    audio = _to_audio(np.asarray(rec.values[key]), 1.0 / rec.dt)
    return audio, _measure_f0(audio), mouth_pa


def synthesize(params: dict, size_info: dict,
               embouchure: str = DEFAULT_EMBOUCHURE,
               duration: float = 0.6,
               override: dict | None = None) -> tuple[bytes, dict]:
    """単音の物理モデル音（OpenWind 必須）。

    音高は指定できない。トーンホールの無い固定ボアは自前の共鳴しか鳴らないため、
    アンブシュア（リード共振）でどのレジスタが立つかが決まる。実際に鳴った f0 を
    meta で返す。`override` はリード コンポーネントからのリード実形状の反映値。
    """
    if not HAS_OPENWIND:
        raise RuntimeError("OpenWind 未導入のため物理モデル音合成は利用できません")
    geometry = build_resonator(params, size_info)
    audio, f0, pa = _simulate_reed(  # pragma: no cover
        geometry, params, embouchure, duration, override)
    return _wav_bytes(audio), {
        "f0": round(f0, 1), "note": _hz_to_note(f0) if f0 > 0 else "-",
        "duration": round(audio.size / SIM_SR, 3),
        "embouchure": embouchure, "mouth_pa": round(pa),
    }


def scale(params: dict, size_info: dict,
          duration: float = 0.6,
          override: dict | None = None) -> tuple[bytes, dict]:
    """簡易スケール（倍音レジスタ）。緩め→標準→締めを順に鳴らす（OpenWind 必須）。

    リード共振は時間変化させられない（OpenWind の Reed1dof は mouth_pressure 以外
    定数のみ）ため、1音ずつシミュして連結する。
    """
    if not HAS_OPENWIND:
        raise RuntimeError("OpenWind 未導入のため物理モデル音合成は利用できません")
    geometry = build_resonator(params, size_info)
    parts, notes = [], []
    gap = np.zeros(int(SIM_SR * 0.08))
    for emb in ("loose", "normal", "tight"):  # pragma: no cover - 環境依存
        audio, f0, _ = _simulate_reed(geometry, params, emb, duration, override)
        parts.append(audio)
        parts.append(gap)
        notes.append(f"{_hz_to_note(f0)} {f0:.0f}Hz" if f0 > 0 else "-")
    out = np.concatenate(parts) if parts else np.zeros(1)
    return _wav_bytes(out), {
        "f0": 0.0, "note": " / ".join(notes),
        "duration": round(out.size / SIM_SR, 3),
        "embouchure": "loose/normal/tight", "mouth_pa": "-",
    }
