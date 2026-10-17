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

import functools
import io
import math
import wave

import numpy as np

from saxsketch.instruments.saxophone.components import profiles
from saxsketch.acoustics import volume as ac_volume

from saxsketch import i18n

# ------------------------------------------------------------------ 物理定数（空気, 20℃前後）
# 返す共鳴ピークの本数。時間領域シミュは高次レジスタで鳴くことがあり、
# 実測 f0 をピーク集合と照合するには 8 本では足りない。
MAX_PEAKS = 12

#: 管内の空気温度 [℃]。**音速の唯一の出所**。
#:
#: ここを 1 箇所にしてある理由: 共鳴管の全長は `build_resonator` が
#: `c/(2·f1)` で作る（＝音速に直結する）。ソルバと違う音速でジオメトリを組むと、
#: 管の長さがそのぶん狂って**全体が音速比のぶん平行移動する**。
#: 実際そうなっていた —— 定数は 343.0（20℃相当）なのに OpenWind へは
#: `temperature=25.0`（音速 347.13）を渡しており、同じジオメトリを
#: 2 エンジンで解くと soprano +23.9 / alto +24.7 / tenor +26.0 セント違った。
#: うち 20.7 セントが音速比 347.13/343 そのもの。揃えると差は 2.9/4.1/5.6 セント
#: （＝損失と放射モデルの違いだけ）に落ちる。
TEMPERATURE_C = 25.0
#: OpenWind の `Physics` 既定値。音速の式が湿度と CO2 を含むので、同じ値を使う。
HUMIDITY = 0.5
CARBON_DIOXIDE = 4e-4


def sound_speed(temp_c: float = TEMPERATURE_C,
                humidity: float = HUMIDITY,
                carbon: float = CARBON_DIOXIDE) -> float:
    """空気中の音速 [m/s]。原典は Zuckerwar の展開式（下の `h` の行に出典）で、
    OpenWind の `Physics`（既定 `ref_phy_coef='RR'`）も同じ原典に拠る。

    ここに式を置いてあるのは、OpenWind 未導入の環境（TMM だけが走る）でも同じ音速を
    使うため。「20.05·√T」のような教科書式では OpenWind の値を再現できない
    （20℃ 343.9878 / 25℃ 347.1324 で、係数が一定にならない）ので推測しない。
    OpenWind があるときは `Physics(TEMPERATURE_C).c(0)` と一致することを
    テストで確かめている。
    """
    t0 = 273.15
    t20 = t0 + 20.0
    t_k = temp_c + t0
    # 水蒸気のモル分率（Zuckerwar Handbook 16.3.3 の展開式）
    h = humidity * 10.0 ** (5.21899 - 5.8294 * t20 / t_k - 1.0252 * (t20 / t_k) ** 2)
    dh = h - 1.1571e-2          # 20℃・湿度 50% を基準に取る
    dco2 = carbon - 4.2e-4      # 420ppm を基準に取る
    dt = t_k / t20 - 1.0
    return 343.986 * math.sqrt(
        t_k / t20 * (1.0 + 0.314 * dh - 0.520 * dco2
                     + 0.25 * dco2 ** 2 - 0.16 * dco2 * dt))


#: 音速 [m/s]。import 時に 1 回だけ評価する（`TEMPERATURE_C` から導出）。
C_SOUND = sound_speed()

# 以下は 20℃ 公称のまま。共鳴の**位置**ではなく損失（ピークの幅と高さ）と放射に
# しか入らないので、温度に追従させていない。追従させるなら OpenWind の
# `Physics` から rho/mu も取ること。
RHO = 1.2          # 密度 kg/m^3
MU = 1.85e-5       # 粘性係数 Pa·s
GAMMA = 1.4        # 比熱比
PR = 0.71          # プラントル数

#: マウスピースのボアからネック小端へ絞る区間の長さ [m]。実物は段差だが、
#: x 単調増加のジオメトリ表現では段差を書けないので短いテーパで代用する。
NECK_STEP = 0.0005

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


# ================================================================== 基準管の校正

#: 校正用の理想円錐を頂点で切る半径 [m]。頂点そのものは断面積 0 で扱えない。
#: 切り詰めた分は一次では効かない（切り詰め円錐の共鳴条件 k·l + arctan(k·x_start) = π
#: で、l が x_start だけ短くなる分と arctan 項がちょうど打ち消す）ので、この値の
#: 選び方に結果は鈍い。
_CAL_TRUNC_R = 3e-4


def ideal_cone_geometry(size_info: dict,
                        use_openwind: bool | None = None) -> list[list[float]]:
    """マウスピースを**理想の欠損円錐に戻した**基準管 [[x_m, r_m], ...]。

    「この楽器のマウスピースが完璧だったら」の管。`build_resonator` が返す管と
    同じ延長円錐を持ち、頂点〜ネック小端の区間だけが実マウスピースではなく
    欠損円錐そのものになっている。差を取ればマウスピース由来の音程だけが残る。
    """
    cone = ac_volume.missing_cone(size_info)
    tan_theta = cone["tan_theta"]
    x0 = cone["apex_distance_mm"] / 1000.0
    l_ext = _calibrate_extension(
        float(size_info["low_note_sounding_hz"]), x0, tan_theta, C_SOUND,
        HAS_OPENWIND if use_openwind is None else use_openwind)
    return _cone_pts(x0, tan_theta, l_ext)


def _cone_pts(x0_m: float, tan_theta: float, l_ext_m: float) -> list[list[float]]:
    x_start = _CAL_TRUNC_R / tan_theta
    span = (x0_m + l_ext_m) - x_start
    return [[0.0, _CAL_TRUNC_R], [span, _CAL_TRUNC_R + tan_theta * span]]


def ideal_cone_hole_x(size_info: dict, s_mm: float) -> float:
    """管体の弧長 s [mm] → `ideal_cone_geometry` 上の x [m]。

    物差しの円錐は頂点を `_CAL_TRUNC_R` で切ってあるので x=0 は頂点ではない。
    スロート（＝ネック小端＝弧長 s の原点）は頂点から `apex_distance_mm` の位置に
    あるので、切り詰めた分を引いた x_throat から s を足す。

    **押し込み量に依らない。** 物差しの側にはマウスピースが無い（`cork_depth` が
    入らない）ので、管体のカードはチューニングと分離して読める。
    """
    cone = ac_volume.missing_cone(size_info)
    x_start = _CAL_TRUNC_R / cone["tan_theta"]
    return (cone["apex_distance_mm"] / 1000.0 - x_start) + s_mm / 1000.0


def _lowest_peak_hz(freqs: np.ndarray, z: np.ndarray) -> float:
    """|Z| の**局所極大のうち最も低い**周波数（放物線補間つき）。

    帯域内の `argmax` ではない。頂点近傍で駆動した円錐は入口断面積が極小なので
    |Z| の包絡が周波数とともに上がり、argmax は共鳴ではなく**帯域の上端**を拾う
    （実測: alto で共鳴 134.6Hz に対し argmax が 235.6Hz。校正の反復が発散した）。
    """
    mag = np.abs(z)
    y_db = 20.0 * np.log10(mag / np.max(mag) + 1e-12)
    inner = np.arange(1, len(y_db) - 1)
    local = inner[(y_db[1:-1] > y_db[:-2]) & (y_db[1:-1] > y_db[2:])]
    i = int(local[0]) if len(local) else int(np.argmax(y_db))
    return _interp_peak(freqs, y_db, i)


def _first_peak_hz(geometry: list[list[float]], f_lo: float, f_hi: float,
                   n: int = 200, use_openwind: bool | None = None) -> float:
    """帯域 [f_lo, f_hi] の**最も低い**共鳴を補間して返す（校正用の軽い版）。

    `_analyze` を使わないのは、ここでは第1共鳴 1 本だけが要るため。格子も 200 点で
    足りる（対数格子 + 放物線補間）。ピークの拾い方は `_lowest_peak_hz`。
    """
    freqs = np.geomspace(f_lo, f_hi, n)
    want_ow = HAS_OPENWIND if use_openwind is None else use_openwind
    z = None
    if want_ow:
        try:  # pragma: no cover - 環境依存
            from openwind import ImpedanceComputation
            z = np.asarray(ImpedanceComputation(
                freqs, geometry, temperature=TEMPERATURE_C,
                source_location='entrance').impedance)
        except Exception:
            z = None
    if z is None:
        z = _tmm_impedance(geometry, freqs)
    return _lowest_peak_hz(freqs, z)


@functools.lru_cache(maxsize=None)
def _calibrate_extension(f1: float, x0_m: float, tan_theta: float,
                         c_sound: float, use_openwind: bool) -> float:
    """延長円錐の長さ [m] を、**理想円錐が実際に f1 で鳴る**ように決める。

    以前は `l_ext = c/(2·f1) − x0` と置いていた。これは**開口端の放射補正がゼロの
    理想円錐**の式で、ソルバ（OpenWind も自作 TMM も）は開口端の放射を含むので、
    この長さでは管が常に長すぎた。マウスピースを外して理想円錐だけを鳴らすと
    soprano −52.3 / alto −48.2 / tenor −44.5 セント低く、**マウスピースが 1 本も
    刺さっていないのに 50 セント近く外れている**状態だった。報告していた残差は
    ほとんどこれで、形状の話ではなかった。

    これは「検証したいモデルからの逆算」ではない。延長円錐はトーンホールもベルも
    無い**作り物の胴**で、実在の寸法を持たない。作り物が目的の音を鳴らすように
    合わせて初めて、残差が「マウスピースのせい」だけになる。合わせているのは
    検証対象（マウスピース）ではなく物差しの側。

    解き方: 円錐の共鳴は実効長に反比例するので、測った f から必要な長さの差を
    `c/2·(1/f1 − 1/f)` で直接出す。2〜3 回で 0.05 セントに入る。サイズ・音速・
    エンジンごとに 1 回だけ走ればよいのでキャッシュする。
    """
    l_ext = max(c_sound / (2.0 * f1) - x0_m, 0.05)
    for _ in range(8):
        f = _first_peak_hz(_cone_pts(x0_m, tan_theta, l_ext), 0.6 * f1, 1.7 * f1,
                           use_openwind=use_openwind)
        if abs(1200.0 * math.log2(f / f1)) < 0.05:
            break
        l_ext = max(l_ext + c_sound / 2.0 * (1.0 / f1 - 1.0 / f), 0.05)
    return l_ext


# ================================================================== ジオメトリ

def build_resonator(params: dict, size_info: dict,
                    use_openwind: bool | None = None) -> list[list[float]]:
    """組み立て共鳴管ジオメトリ [[x_m, r_m], ...]（ティップ→ベル）。

    構成:
      (a) マウスピース内部空洞: cavity_stations の各断面積 → 等価半径 sqrt(A/pi)
      (b) 円筒ボア: シャンク端まで
      (c) 欠損円錐延長: スロート断面から本体側へ広がる円錐。
          taper は descriptor の半頂角そのもの、全長は `_calibrate_extension` が
          「マウスピースを理想の欠損円錐に戻したら f1 で鳴る」長さとして決める。

    `use_openwind` は延長円錐の校正に使うエンジンを指定する（既定は実際に走る方）。
    Tier1 は速い方（TMM）で一貫させたいので False を渡す。ここを固定しないと、
    OpenWind が入っている環境と入っていない環境で Tier1 の値が変わる。
    """
    return _assemble_resonator(_cavity_points(params), params, size_info,
                               float(params["cork_depth"]), use_openwind)


def _cavity_points(params: dict) -> tuple[list[float], list[float]]:
    """共鳴管のうち**マウスピース空洞だけ**（各断面 → 等価半径）。単位 m。

    断面積は形状依存（馬蹄/フラットサイドウォールも正しく計上）なので断面
    ポリゴンから求める。ここは **リード面で切った実効断面積** を使う:
    ロフト用ステーションは窓を開けるためカット面より下へはみ出しており、その
    はみ出しは気柱ではない（リードが塞ぐ）。`cavity_volume_cc` は同じ切り直しを
    しているので、素の `section_area` を使うと Tier1 と Tier3 の前提が食い違う。

    組み立ての残り（ボアと延長円錐）から分けてあるのは `cork_depth` に依らない
    ため。`cavity_stations` は list を返すので `profiles` のキャッシュに載って
    おらず（呼び出し側の書き換えでキャッシュが汚れるため意図的に外してある）、
    挿し込み量を振るたびに組み直すと 1 回 6〜9ms を毎回払うことになる。
    """
    xs: list[float] = []
    rs: list[float] = []
    for s in profiles.cavity_stations(params):
        area_mm2 = profiles.effective_section_area(params, s)
        r_eq = math.sqrt(max(area_mm2, 1e-6) / math.pi)  # mm
        xs.append(s["z"] / 1000.0)
        rs.append(r_eq / 1000.0)
    return xs, rs


def _assemble_resonator(cavity: tuple[list[float], list[float]], params: dict,
                        size_info: dict, cork_mm: float,
                        use_openwind: bool | None) -> list[list[float]]:
    """空洞に円筒ボアと欠損円錐延長を継いで共鳴管にする。挿し込み量は引数で受ける。"""
    p = params
    xs = list(cavity[0])
    rs = list(cavity[1])

    # (b) 円筒ボア。終端はシャンク端ではなく**コーク線**（= overall_length - cork_depth）。
    # シャンク端までを空気柱として数えると、ネックのテノンが埋めている体積まで
    # 気柱に含めてしまう（ソプラノで 3.6cc ＝ マウスピース内容積の 44%）。
    # cavity_volume_cc() は同じ分を neck_occupied として差し引いており、こちらだけ
    # 数えていて Tier1 と Tier3 が食い違っていた。
    r_bore = profiles.bore_radius(p) / 1000.0
    x_cork = max(p["overall_length"] - cork_mm, xs[-1] * 1000.0) / 1000.0
    if x_cork > xs[-1]:
        xs.append(x_cork)
        rs.append(r_bore)

    # (c) 欠損円錐延長
    # 円錐管の第1共鳴は**頂点から**測った全長で決まる。マウスピースが代替するのは
    # 欠損円錐（頂点〜ネック小端）なので、差し引くのはマウスピースの物理長ではなく
    # 欠損円錐長。物理長を引くと管が欠損円錐長との差だけ長くなり、アルトで
    # 161mm 過長 ≒ 270 セント低く出る（3サイズとも同じ量ずれるので系統誤差と分かる）。
    #
    # 長さは `c/(2·f1) − x0` という理想円錐の式ではなく、**同じソルバで理想円錐が
    # f1 に鳴る長さ**を採る（`_calibrate_extension`）。理想式は開口端の放射補正を
    # 持たないので、マウスピースを外した基準管だけで 45〜52 セント低く出ていた。
    cone = ac_volume.missing_cone(size_info)
    f1 = float(size_info["low_note_sounding_hz"])

    # 円錐の半頂角は descriptor の実測文献値をそのまま使う
    # （体積定数から逆算していたのをやめた。出所が一本化される）
    tan_theta = cone["tan_theta"]
    l_ext = _calibrate_extension(
        f1, cone["apex_distance_mm"] / 1000.0, tan_theta, C_SOUND,
        HAS_OPENWIND if use_openwind is None else use_openwind)

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


def _span_matrix(geometry: list[list[float]], freqs: np.ndarray):
    """区間 1 本の伝達行列 (m11, m12, m21, m22) と、末端スライスの半径。

    **側孔があっても、この行列は運指で変わらない。** 変わるのは分岐行列だけなので、
    穴の位置で管を切っておけば区間行列は 1 回作れば使い回せる
    （`tmm_fingerings`）。実測でここが費用のほぼ全部（アルト既定で 557 スライス ×
    200 周波数 ＝ 12.5ms/回）なので、運指ごとに作り直すと音階 8 音で 100ms 超えて
    `simulate` の予算 50ms を割る。
    """
    n_f = len(freqs)
    if len(geometry) < 2 or geometry[-1][0] - geometry[0][0] <= 1e-12:
        # 穴が同じ位置に 2 つあると零長の区間ができる。単位行列で通す
        # （成立しない配置は `body_profiles.hole_layout_error` が別に弾く）。
        return ((np.ones(n_f, dtype=complex), np.zeros(n_f, dtype=complex),
                 np.zeros(n_f, dtype=complex), np.ones(n_f, dtype=complex)),
                float(geometry[-1][1]))
    _, seg_l, seg_r = _resample(geometry)

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

    return (m11, m12, m21, m22), float(seg_r[-1])


def _mat_mul(a, b):
    """2×2 の伝達行列の積（各要素は周波数配列）。"""
    a11, a12, a21, a22 = a
    b11, b12, b21, b22 = b
    return (a11 * b11 + a12 * b21, a11 * b12 + a12 * b22,
            a21 * b11 + a22 * b21, a21 * b12 + a22 * b22)


def _radius_at(geometry: list[list[float]], x: float) -> float:
    """区分線形ジオメトリの x [m] における半径 [m]（外側はクランプ）。

    **式で持たない。** 共鳴管の点列にはネック小端への段差（`NECK_STEP`）が
    入っているので、`tan_theta · s` で持つと同じ半径が 2 通りできる。
    """
    xs = [g[0] for g in geometry]
    if x <= xs[0]:
        return float(geometry[0][1])
    if x >= xs[-1]:
        return float(geometry[-1][1])
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            x0, x1 = xs[i], xs[i + 1]
            r0, r1 = geometry[i][1], geometry[i + 1][1]
            if x1 - x0 <= 0:
                return float(r1)
            return float(r0 + (r1 - r0) * (x - x0) / (x1 - x0))
    return float(geometry[-1][1])


def _split_geometry(geometry: list[list[float]],
                    xs: list[float]) -> list[list[list[float]]]:
    """x の昇順リストでジオメトリを切り分ける（各断片は両端の点を持つ）。"""
    if not xs:
        return [[list(pt) for pt in geometry]]
    chunks: list[list[list[float]]] = []
    cur = [list(geometry[0])]
    idx = 0
    for i in range(1, len(geometry)):
        x_prev, x_cur = geometry[i - 1][0], geometry[i][0]
        while idx < len(xs) and x_prev < xs[idx] <= x_cur:
            cut = [xs[idx], _radius_at(geometry, xs[idx])]
            if cut[0] > cur[-1][0] + 1e-12:
                cur.append(list(cut))
            chunks.append(cur)
            cur = [list(cut)]
            idx += 1
        if geometry[i][0] > cur[-1][0] + 1e-12:
            cur.append(list(geometry[i]))
    chunks.append(cur)
    return chunks


def _tmm_parts(geometry: list[list[float]], freqs: np.ndarray, holes):
    """運指に依らない部分。(区間行列の列, 各穴の本管半径, 放射インピーダンス)。"""
    xs = [float(h["x_m"]) for h in holes]
    lo, hi = geometry[0][0], geometry[-1][0]
    for h, x in zip(holes, xs):
        if not lo < x <= hi:
            raise ValueError(
                i18n.t(
                    "側孔 {label} が管の外にあります (x={x}m, 管は "
                    "{lo}〜{hi}m)",
                    label=f"{h.get('label', '?')}", x=f"{x:.4f}",
                    lo=f"{lo:.4f}", hi=f"{hi:.4f}"))
    if xs != sorted(xs):
        raise ValueError(i18n.t("側孔は弧長の昇順で渡すこと（区間の切れ目が決まらない）"))
    chunks = _split_geometry(geometry, xs)
    spans, last_r = [], None
    for c in chunks:
        m, last_r = _span_matrix(c, freqs)
        spans.append(m)
    return (spans, [_radius_at(geometry, x) for x in xs],
            _radiation_impedance(freqs, last_r))


def _tmm_from_parts(parts, holes, open_flags, freqs) -> np.ndarray:
    """区間行列＋分岐行列 → 入力インピーダンス。運指ごとにここだけ回す。"""
    from saxsketch.acoustics import toneholes

    spans, r_mains, z_rad = parts
    m = spans[0]
    for i, h in enumerate(holes):
        m = _mat_mul(m, toneholes.junction_matrix(
            freqs, r_mains[i], float(h["radius_m"]), float(h["chimney_m"]),
            bool(open_flags[i])))
        m = _mat_mul(m, spans[i + 1])
    m11, m12, m21, m22 = m
    # [P_tip; U_tip] = M [P_end; U_end], Z_end = P_end/U_end = z_rad
    return (m11 * z_rad + m12) / (m21 * z_rad + m22)


def _tmm_impedance(geometry: list[list[float]], freqs: np.ndarray,
                   holes=(), open_flags=None) -> np.ndarray:
    """微小円筒スタックの伝達行列を連結して入力インピーダンス Zin(f) を得る。

    `holes` を渡すと側孔の分岐行列を挟む（`toneholes.junction_matrix`）。
    **穴が無いときは以前とビットで同じ**経路を通る（区間が 1 本になるだけ）。
    """
    holes = list(holes)
    if open_flags is None:
        open_flags = [False] * len(holes)
    return _tmm_from_parts(_tmm_parts(geometry, freqs, holes), holes,
                           open_flags, freqs)


def tmm_fingerings(geometry: list[list[float]], freqs: np.ndarray, holes,
                   fingerings) -> dict[str, np.ndarray]:
    """運指ごとの Zin(f)。**区間行列は 1 回しか作らない。**

    `fingerings` は [(表示名, 各穴の開閉タプル), …]（`toneholes.successive_fingerings`）。
    """
    holes = list(holes)
    parts = _tmm_parts(geometry, freqs, holes)
    return {name: _tmm_from_parts(parts, holes, flags, freqs)
            for name, flags in fingerings}


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


def _hz_to_note_name(freq: float) -> str:
    """いちばん近い平均律の音名だけ（セントを付けない）。

    目標音のラベルに使う。目標は `f_low·2^(n/12)` で作った**厳密な**音程なので、
    「(+0c)」を毎行付けても情報が無い（実測側は `_hz_to_note` でセントを出す）。
    """
    if freq <= 0:
        return "-"
    m = int(round(69 + 12 * math.log2(freq / 440.0)))
    return f"{_NOTE_NAMES[m % 12]}{m // 12 - 1}"


def _cents(f: float, f_ref: float) -> float:
    if f <= 0 or f_ref <= 0:
        return 0.0
    return 1200.0 * math.log2(f / f_ref)


def _interp_peak(freqs: np.ndarray, y_db: np.ndarray, i: int) -> float:
    """ピーク位置を格子の間へ補間する（log-f 上の 3 点パラボラ）。

    格子点をそのまま読むと、共鳴周波数の分解能が ΔF/f で決まってしまう。
    `impedance()` の対数格子（比が一定）なら log-f 上で等間隔なので、
    そこで放物線を当てて頂点を取る。

    以前は線形格子 `linspace(50, 2000, 800)` を格子点のまま読んでいて、
    低音の 1 目盛りが soprano 20.9 / alto 30.9 / tenor **41.2 セント**あった。
    「±20 セント以内」の判定が 1 目盛りより細かく、格子がたまたま乗ったときしか
    通らない状態だった。線形格子のままで補間だけ足しても直らない（格子幅が
    ピーク幅 ≒ 2.5Hz と同程度で、放物線近似の前提が崩れる）ので、
    対数格子と対で使う。
    """
    if i <= 0 or i >= len(freqs) - 1:
        return float(freqs[i])
    den = y_db[i - 1] - 2.0 * y_db[i] + y_db[i + 1]
    if den == 0:
        return float(freqs[i])
    delta = 0.5 * (y_db[i - 1] - y_db[i + 1]) / den
    if not (-1.0 < delta < 1.0):  # 放物線が外れた（肩が単調など）
        return float(freqs[i])
    lg = math.log(float(freqs[i]))
    step = math.log(float(freqs[i + 1])) - lg
    return math.exp(lg + delta * step)


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
        # 0.1Hz へ丸めない。テナーの第1共鳴 102Hz では 0.1Hz = 1.7 セントあり、
        # 補間で稼いだ分解能を丸めで捨てることになる。表示は _hz_to_note が行う。
        fp = _interp_peak(freqs, mag_db, int(i))
        peaks.append({
            "freq": round(fp, 3),
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
        "note": (i18n.t("OpenWind（周波数領域）による共鳴ピーク。")
                 if engine == "openwind" else
                 i18n.t("簡易TMM（自作・伝達行列法）による推定。相対比較用。"))
        + i18n.t(" 絶対音程でなくパラメータ変化の方向を参考に。"),
    }


# ================================================================== OpenWind 経路

def ow_hole_rows(holes) -> list[list]:
    """OpenWind の holes ファイル形式（の list 版）。

    列名は `label position radius length` で、`length` が**チムニー長**。
    ファイルに書き出さずに list をそのまま渡せる（`InstrumentGeometry` の docstring）。
    """
    rows: list[list] = [["label", "position", "radius", "length"]]
    for h in holes:
        rows.append([str(h["label"]), float(h["x_m"]), float(h["radius_m"]),
                     float(h["chimney_m"])])
    return rows


def ow_fingering_rows(holes, fingerings) -> list[list]:
    """OpenWind の fingering chart 形式。1 行 = 1 つの穴、1 列 = 1 つの運指。"""
    rows: list[list] = [["label"] + [name for name, _f in fingerings]]
    for i, h in enumerate(holes):
        rows.append([str(h["label"])]
                    + ["o" if flags[i] else "x" for _n, flags in fingerings])
    return rows


def _openwind_impedance(geometry, freqs, size_info, holes=(),
                        note=None):  # pragma: no cover - 環境依存
    from openwind import ImpedanceComputation
    # geometry: [[x, r], ...]（m）。OpenWind は [x, r] のリストを受け付ける。
    holes = list(holes)
    kw = {}
    if holes:
        from saxsketch.acoustics import toneholes
        fings = toneholes.successive_fingerings(holes)
        kw = {"holes_valves": ow_hole_rows(holes),
              "fingering_chart": ow_fingering_rows(holes, fings),
              "note": note or fings[0][0]}
    result = ImpedanceComputation(freqs, geometry, temperature=TEMPERATURE_C,
                                  source_location='entrance', **kw)
    z = np.asarray(result.impedance)
    return _analyze(np.asarray(freqs, dtype=float), z, size_info, "openwind")


# ================================================================== 公開: インピーダンス

def first_resonance_cents(params: dict, size_info: dict) -> float:
    """組み立て共鳴管の第1共鳴が目標低音から何セント外れているか（**TMM 固定**）。

    Tier1（`acoustics.volume.tier1_report`）が使う速い経路。Tier2 の
    `impedance()` と同じジオメトリ・同じ物理で、エンジンだけが違う。
    実測 31〜52ms（`profiles.cavity_volume_cc` が既に 10.7ms 払っている）。

    TMM に固定する理由は 2 つ。OpenWind は 0.5〜0.8s かかりスライダ操作の裏では
    重すぎること、そして**環境によって Tier1 の値が変わらないようにする**こと
    （OpenWind の有無で数字が動くと記録値テストが環境依存になる）。
    """
    geo = build_resonator(params, size_info, use_openwind=False)
    f1 = float(size_info["low_note_sounding_hz"])
    f = _first_peak_hz(geo, 0.6 * f1, 1.7 * f1, use_openwind=False)
    return _cents(f, f1)


#: **コルクが噛むのに要る長さ** [mm]。挿し込み量の探索下限はこれ単体ではなく、
#: フェルール長を足したもの（下の `usable_insertion_range`）。
_CORK_MIN_MM = 3.0
#: ボアの奥に残す余裕 [mm]。ネックは円筒ボアが終わる段で止まるが、コルクは
#: 潰れながら効くので実際はその手前で噛む。
_CORK_BORE_MARGIN_MM = 3.0
#: 収束条件 [セント]。0.05 だとテナー（0.27 セント/mm）で 0.19mm 残り、速い経路の
#: 線形推定（実測 0.029mm）より粗くなる。厳密解の方が粗いのでは名前負けする。
_TUNE_TOL_CENTS = 0.02
#: 反復の上限。実測では 2〜3 回で収束する。
_TUNE_MAX_ITER = 6
#: 感度を測る差分幅 [mm]。「1mm 押し込むと何セント上がるか」をそのまま返したいので 1.0。
_TUNE_SLOPE_MM = 1.0
#: 傾きの 2 点も**全帯域 200 点のまま**解く。第1共鳴の周り ±3% だけを 60 点で
#: 探れば 1 回 17ms → 1ms になるが、**精度が落ちる**（実測: 零点の誤差が
#: 0.03mm → 1.87mm、テナーの感度が 0.271 → 0.378 セント/mm）。共鳴の山が広いので
#: 格子を細かくすると放物線あてはめに使う 3 点がほぼ一直線になり、条件が悪くなる。
#: 「細かい格子ほど正確」はここでは成り立たない。測って不採用にした。


def _ferrule_mm(size_info: dict) -> float:
    """ネック端面からコルクが始まるまで [mm]。未実測のサイズは 0（＝従来どおり）。

    実物の先端は真鍮のフェルール（補強リング）で、そこにはコルクが無い。
    **3 サイズとも同じ作り**（ユーザー確認、2026-08-13）だが、実測してあるのは
    ソプラノの 2.7mm だけ。未実測のサイズに推定値を入れると、いま入っている
    値がどこから来たのか分からなくなるので 0 のまま置く。
    """
    return float(size_info.get("neck_ferrule_length_mm", 0.0))


def usable_insertion_range(params: dict, size_info: dict,
                           cork_max_mm: float | None = None) -> tuple[float, float]:
    """マウスピースを挿せる範囲 [mm]（ネック端面から測る）。

    浅い側 = フェルール長 ＋ コルクが噛むのに要る長さ。フェルールの上には
    コルクが無いので、そこを足さないと「3mm 挿してある」が実際には
    0.3mm しか噛んでいない、という状態を域の内側と数えてしまう。

    深い側は **実測（`insertion_limit_mm`）があればそれを採る**。無いサイズだけ
    フェルール長 ＋ コルク帯長から推す。**推定は当てにならない** —— 3 サイズとも
    実測してみると推定と食い違い、しかも向きが揃っていない:

      soprano  推定 33.7（＝ボア 38.3 側でもない）に対し **実測 27.1**
      alto     推定 30.0 に対し **実測 36.4**
      tenor    推定 32.0 に対し **実測 36.0**

    ソプラノがコルクの 6.6mm 手前で止まるのは、コルク帯でもボアでもない何か
    （一体型ネックのテーパ）が噛んでいるため。**計算では出せないので押して測る。**

    **この上限は硬いしきい値ではない。** 実測そのものが「これ以上押し込んだら
    まずい」という演奏者の判断で、コルク帯も厳しい公差の掛かった部位ではない
    （幅は周方向でも一定でない。descriptor の `neck_cork_length_source`）。
    境目に近い判定を出すときは、数字の精度ではなく**実物で確かめること**を言う。

    `cork_max_mm` を渡した場合はコルク帯長として扱い、実測より優先する
    （掃引・テストで上限を仮定して振るための入口）。
    """
    ferrule = _ferrule_mm(size_info)
    lo = ferrule + _CORK_MIN_MM
    hi = float(params["bore_length"]) - _CORK_BORE_MARGIN_MM
    if cork_max_mm is not None:
        hi = min(hi, ferrule + float(cork_max_mm))
    elif size_info.get("insertion_limit_mm") is not None:
        hi = min(hi, float(size_info["insertion_limit_mm"]))
    elif size_info.get("neck_cork_length_mm") is not None:
        hi = min(hi, ferrule + float(size_info["neck_cork_length_mm"]))
    return lo, max(hi, lo + 1.0)


def tuning_position(params: dict, size_info: dict,
                    cork_max_mm: float | None = None,
                    exact: bool = False) -> dict:
    """目標低音が合う挿し込み量を解く（**TMM 固定**）。

    `cork_depth` はマウスピースの寸法ではない。気温・リード・合わせる音程で
    演奏者が抜き差しする量、すなわちチューニングそのものである。固定値として
    持ってそこからのズレをセントで報告すると、**寸法の誤差とチューニングの
    自由度が混ざる**。Stage E がソプラノに付けた −31 セントはまさにそれで、
    全長 71.4mm の実物に 17.91mm という当て推量の挿し込みを固定していたぶん
    だった（実測を入れて解き直すと 3 サイズとも実用域の内側に入る）。

    返す量:
      in_tune_mm      合う挿し込み量。**存在しないときは `None`**（1mm 押しても
                      音程が動かず、実用域の両端でも目標音を挟まない形）。
                      NaN では返さない ——JSON にできず API が 500 になる
                      （B-3 で `bore_length` の壁を 1.0mm まで広げたら踏んだ）
      method          "linear"（既定の速い経路）/ "solved"（`exact=True`、または
                      速い経路の推定が実用域の外へ出て解き直したとき）
      range_mm        実用域 [浅い側, 深い側]
      cents_at_range  実用域の両端でのセント。`exact=True` のときだけ。速い経路では None
      cents_per_mm    現在位置で 1mm 押し込んだときのセント変化
      current_mm      params["cork_depth"]
      cents_at_current
      reachable       in_tune_mm が実用域に入っているか
      headroom_mm     [抜ける余裕, 押し込める余裕]

    実用域は `usable_insertion_range` が決める。深い側の上限は**3 サイズとも実測**
    （`insertion_limit_mm` = 27.1 / 36.4 / 36.0）で、ボアでもコルク帯でもない。
    しかも**硬いしきい値ではない**（実測自体が演奏者の「これ以上はまずい」の判断）。
    `cork_max_mm` を渡した場合だけコルク帯長からの推定に戻る。

    **既定の経路は共鳴を 2 回しか解かない。** `simulate` の予算は 50ms
    （`cad/perf/bench_ui_latency.BUDGET`）で、`simulate` 自体が既に 20〜31ms
    使っている。零点を包んで詰める厳密解は 10 回前後（テナーで 335ms）かかり、
    どう刻んでも入らない。代わりに現在位置とその 1mm 奥を解いて**局所の傾き**を
    取り、そこから線形に零点を推す。テンプレートの `cork_depth` は零点の
    0.1〜1.1mm 手前にあるので、常用状態ではこの推定が効く（誤差はテストで記録）。
    大きく外れた形状を触っているときは推定も粗くなる（実測で最大 3.4mm）。
    **その粗さで「実用域に入らない」と言わないよう、推定が域外に出たときだけ
    自動で解き直す。** 仕様書とテストは常に `exact=True` を使う。

    ここではキャッシュしない —— 引数が dict でキーにできず、
    `server.state.simulate` が `_params_key()` で同じ粒度のキャッシュを既に持つ。
    """
    lo, hi = usable_insertion_range(params, size_info, cork_max_mm)

    # 空洞部は挿し込み量に依らないので 1 回だけ組む（1 回 6〜9ms）。
    cavity = _cavity_points(params)
    f1 = float(size_info["low_note_sounding_hz"])

    def cents_at(mm: float) -> float:
        geo = _assemble_resonator(cavity, params, size_info, mm, False)
        return _cents(_first_peak_hz(geo, 0.6 * f1, 1.7 * f1, use_openwind=False), f1)

    cur = float(params["cork_depth"])
    c_cur = cents_at(cur)
    # 傾きを測る足場は**実用域の中へ寄せる**。`cork_depth` が実用域より深いと
    # （`bore_length` 最小 × `cork_depth` 最大のようなスライダの端）コーク線が
    # 空洞の終端でクランプされ、2 点とも同じジオメトリになって傾きが 0 になる。
    # 刻みが 1.0mm なのは「1mm 押し込むと何セント上がるか」をそのまま返すため。
    base = min(max(cur, lo), hi - _TUNE_SLOPE_MM)
    c_base = c_cur if abs(base - cur) < 1e-9 else cents_at(base)
    slope = (cents_at(base + _TUNE_SLOPE_MM) - c_base) / _TUNE_SLOPE_MM
    # 傾きが取れないときは **None**。ボアがほとんど無い形（B-3 で壁を 1.0mm まで
    # 広げた先）では、コーク線が空洞の終端でクランプされて 1mm 押しても音程が
    # 動かない。ここで NaN を入れると `round()` を通って API の JSON 化で落ちる。
    z = base - c_base / slope if abs(slope) > 1e-9 else None
    method = "linear"
    c_range = None

    # 推定が実用域の外へ出たときは**必ず**厳密に解き直す。「この形状はチューニング
    # では合わせられない」は強い主張で、線形推定の粗さで言ってはいけない。実測で
    # 誤警報が出ている: テナーのボアを 38mm にすると推定 1.25mm（域外）に対し
    # 厳密解は 9.72mm（域内）＝ **8.47mm ぶんの誤警報**。追加のコストを払うのは
    # 悪い知らせを出す直前だけ。（この例は以前ボア 46mm・1.61 → 5.05 だったが、
    # `cavity_floor_y` の特異点を直して床が実物の深さへ戻ったら 46mm では
    # 推定が域内に収まった。ガードが消えたのではなく設定が当たらなくなっただけ。）
    if exact or z is None or not lo <= z <= hi:
        c_lo, c_hi = cents_at(lo), cents_at(hi)
        c_range = [c_lo, c_hi]
        if c_lo * c_hi <= 0.0:
            # 割線法で包んだまま詰める。実用域の両端を結ぶ線形近似は零点を最大
            # 2.68mm 外す（tenor で実測）ので、1 発では決めない。
            a, ca, b, cb = lo, c_lo, hi, c_hi
            for _ in range(_TUNE_MAX_ITER):
                z = b - cb * (b - a) / (cb - ca) if abs(cb - ca) > 1e-12 else 0.5 * (a + b)
                z = min(max(z, lo), hi)
                cz = cents_at(z)
                if abs(cz) < _TUNE_TOL_CENTS:
                    break
                if ca * cz < 0.0:
                    b, cb = z, cz
                else:
                    a, ca = z, cz
            method = "solved"
        elif z is None:
            # 傾きも取れず、実用域の両端でも目標音を挟まない ＝
            # **合う挿し込み量が無い**。数字を作らずにそう言う。
            method = "unsolved"
        # 挟まないなら零点は実用域の外。速い経路の線形外挿をそのまま残す
        # （どこまで要るかは出るが、reachable=False の方が伝えたいこと）。

    return {
        "in_tune_mm": z,
        "method": method,
        "range_mm": [lo, hi],
        "cents_at_range": c_range,
        "cents_per_mm": slope,
        "current_mm": cur,
        "cents_at_current": c_cur,
        "reachable": z is not None and bool(lo <= z <= hi),
        "headroom_mm": [None, None] if z is None else [z - lo, hi - z],
    }


#: 音階を解くときの周波数格子の点数。全閉の 0.6 倍から最高音の 1.8 倍まで
#: 対数等間隔で張る。既定の 7 孔（+12 半音まで）だと比が約 6 になり、400 点で
#: 7.8 セント/格子 —— 校正用の 200 点（9.05 セント/格子）より細かい。
_SCALE_GRID_N = 400


class HoleSolver:
    """側孔つきの管を、**穴の位置が同じ変種なら区間行列を作り直さずに**解く。

    運指・穴径・チムニー高さのどれを変えても、変わるのは分岐行列だけで
    区間行列（＝費用のほぼ全部）は変わらない。だから

      - 音階 8 運指
      - 「チムニーを 1mm 足したら何セント動くか」
      - 「穴径を 1mm 太くしたら何セント動くか」

    が**全部あわせて 1 回ぶん**の費用で出る。感度は 4-B.2c が使うつまみの効きで、
    ここが安くないとカードに載せられない（`simulate` の予算は 50ms）。

    **位置を変えた変種は渡せない**（区間の切れ目が変わる）。渡されたら例外。
    """

    def __init__(self, geometry: list[list[float]], holes, f_low: float, steps):
        from saxsketch.acoustics import toneholes

        self.holes = list(holes)
        self.f_low = float(f_low)
        self.fingerings = toneholes.successive_fingerings(self.holes)
        self.targets = [self.f_low] + [self.f_low * 2.0 ** (st / 12.0) for st in steps]
        if len(self.targets) != len(self.fingerings):
            raise ValueError(
                i18n.t(
                    "運指 {len} 通りに対し目標音が {len2} 個",
                    len=f"{len(self.fingerings)}", len2=f"{len(self.targets)}"))
        self.freqs = np.geomspace(0.6 * self.f_low, 1.8 * max(self.targets),
                                  _SCALE_GRID_N)
        self.parts = _tmm_parts(geometry, self.freqs, self.holes)

    def resonances(self, holes=None) -> dict[str, float]:
        """運指ごとの第1共鳴 [Hz]（**TMM 固定**）。"""
        holes = self.holes if holes is None else list(holes)
        def key(hs):
            return [round(float(h["x_m"]), 12) for h in hs]

        if key(holes) != key(self.holes):
            raise ValueError(i18n.t("穴の位置が違う変種は区間行列を使い回せません"))
        return {name: _lowest_peak_hz(
            self.freqs, _tmm_from_parts(self.parts, holes, flags, self.freqs))
            for name, flags in self.fingerings}

    def scale(self, holes=None) -> list[dict]:
        """全閉から順に開けたときの音階。1 行 1 運指。

        Returns: [{"name", "target_hz", "target_note", "freq", "note", "cents"}, …]
        `cents` は**目標音からのずれ**（正で高い）。

        **調律の保証ではない。** 穴の位置は 0 次規則で置いた暫定値なので、ここに
        出る `cents` は「設計が外れている量」ではなく **4-B.2c のソルバが潰すべき
        残差**そのもの。
        """
        got = self.resonances(holes)
        rows = []
        for (name, _flags), tgt in zip(self.fingerings, self.targets):
            f = got[name]
            rows.append({"name": name, "target_hz": tgt,
                         "target_note": _hz_to_note_name(tgt), "freq": f,
                         "note": _hz_to_note(f), "cents": _cents(f, tgt)})
        return rows


def hole_scale(geometry: list[list[float]], holes, f_low: float,
               steps) -> list[dict]:
    """`HoleSolver(...).scale()` の 1 行版（変種を要らないとき）。"""
    return HoleSolver(geometry, holes, f_low, steps).scale()


def impedance(params: dict | None, size_info: dict,
              fmin: float = 50.0, fmax: float = 2000.0, n: int = 800,
              geometry: list[list[float]] | None = None, holes=(),
              use_openwind: bool | None = None) -> dict:
    """入力インピーダンス Z(f) とピーク解析を返す。

    `geometry` を渡すと `params` からは組み立てない（管体は「理想マウスピース」の
    物差し円錐＋側孔で評価するので、マウスピースのパラメータを持たない）。
    `holes` を渡すと側孔つきで解く（運指は全閉）。

    `use_openwind` は `build_resonator` と同じ意味（None ＝ 入っている方）。
    記録値を張るテストは False で固定する。**ピークの本数はエンジンで違う** ——
    alto 既定で TMM 12 本 / OpenWind 10 本（OpenWind は高次の損失が大きく、11・12 本目の
    prominence が最大の 1.85 / 1.76% で `_analyze` の下限 2% を割る。TMM では 2.85 / 2.66%）。

    格子は**対数等間隔**。線形等間隔だと 1 目盛りの音程幅が ΔF/f で効き、
    50–2000Hz を 800 点で張ると低音側が 41 セント刻み・高音側が 4 セント刻みという
    2 桁の偏りが出る。対数なら全域 7.99 セント/格子で揃い、点数が同じなので
    計算時間も変わらない。`_interp_peak` の放物線補間もここが等間隔である前提。
    """
    freqs = np.geomspace(fmin, fmax, n)
    want_ow = HAS_OPENWIND if use_openwind is None else use_openwind
    if geometry is None:
        geometry = build_resonator(params or {}, size_info, use_openwind=want_ow)
    holes = list(holes)
    if want_ow:
        try:  # pragma: no cover
            return _openwind_impedance(geometry, freqs, size_info, holes)
        except Exception:
            pass  # OpenWind 失敗時は TMM へ
    z = _tmm_impedance(geometry, freqs, holes)
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


#: 「段差」と見なす母線の傾き |Δr/Δx|。
#: 実測（alto 既定の共鳴管 43 セグメント）で 2.0 を超えるのは**ネック小端への
#: 段差 1 本だけ**（3.1）。次に急なのはティップ近傍の 0.86 で、間に 3.6 倍の
#: 開きがある。テーパの細かい刻みと本物の不連続は、間隔ではなく傾きで分かれる。
_STEP_SLOPE = 2.0
#: 段差と見なす最大の x 幅 [m]。長い急テーパは段差ではない（上の実測では 0.5mm）。
_STEP_MAX_DX = 0.001


def _coarsen(geometry: list[list[float]],
             min_dx: float = SIM_MIN_DX) -> list[list[float]]:
    """時間領域シミュ用にジオメトリを間引く。**段差だけは零長で残す。**

    CFL 条件より dt ∝ 最小セグメント長なので、x 方向には間引きたい。以前は
    「`min_dx` 以上離れた点だけ残す」だけで、docstring には「2kHz 以下では
    数 mm の刻み差は音響的にほぼ効かない」と書いてあった。**刻みについては
    正しいが、落としていたのは刻みではなかった。**

    alto 既定で 44 点 → 8 点になり、そのとき消えていたのが `[0.07887, 0.00635]`
    —— マウスピースのボア 7.90mm からネック小端 6.35mm への**段差**で、前の点の
    0.5mm 後ろにあるため `min_dx = 8mm` に引っかかっていた。測ると:

    ==================  =============  =============  =============
    ..                  生の管 (44点)  旧 (8点)       いま (9点)
    ==================  =============  =============  =============
    第1共鳴             138.69 Hz      133.43 Hz      138.58 Hz
    共鳴比 n2 / n3      1.993 / 3.006  2.055 / 3.162  1.994 / 3.008
    5次のQ              0.7            26.5           —
    ==================  =============  =============  =============

    段差を落とすと **−67 セント**ずれるうえ、共鳴列が引き伸ばされて非調和になり
    （3次が 5% シャープ）、高次モードの Q が 10〜40 倍に膨らむ。その状態では
    基音より上のレジームが安定できず、リードがモードを渡り歩いていた。
    段差 1 本を戻すだけで **−1.4 セント / 比は 0.1% 以内**まで戻る ——
    ティップ側の刻みは本当に効いていない。

    **段差は零長にする。** 0.5mm のまま残すと CFL が効いて 1,183,109 ステップ
    （2 倍）になる。零長なら 562,050 ステップで**旧と同じ**。

    **速くはならない。** 一度、半径が跳ぶ点を無条件に残す版を書いたら 8.3 倍
    速くなったが、それは連続した跳びが同じ x に積み上がって**ティップの
    テーパが階段に潰れていた**からで、速さはその歪みそのものだった
    （メッシャーが急テーパを刻み直さなくなる）。測って捨てた。

    両端点は必ず保持する。
    """
    if len(geometry) <= 2:
        return [list(pt) for pt in geometry]
    out = [list(geometry[0])]
    for i in range(1, len(geometry) - 1):
        prev, pt = geometry[i - 1], geometry[i]
        dx = pt[0] - prev[0]
        if dx <= _STEP_MAX_DX and abs(pt[1] - prev[1]) >= _STEP_SLOPE * max(dx, 1e-12):
            out.append([out[-1][0], pt[1]])   # 段差＝零長の不連続。CFL を痛めない
        elif pt[0] - out[-1][0] >= min_dx:
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
        raise RuntimeError(i18n.t("発振しませんでした（吹圧を上げてください）"))
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

    立ち上がりは高次モードが暴れるので前半を捨て、**後半 40%** だけを見る。
    以前は後半 50% だった。0.6s だと緩め・標準がその窓の中で過渡（3次共鳴）から
    基音へ移るので、duration を変えると報告する f0 が動いていた。実測では
    どのアンブシュアも 60% 地点までに基音へ落ちている。
    さらに放物線補間でビン幅以下の精度を出す（0.6s のシミュでビン幅 ~4Hz）。
    """
    sig = np.asarray(sig, dtype=float)
    seg = sig[int(0.6 * sig.size):]
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


#: 吹奏比 γ ＝ 吹圧 / 静的ビーティング圧 `p_M`。
#:
#: `p_M = ω₀²·(M_r/S_r)·y₀` はリードが静止開口ぶん動く圧力で、**ω₀² で動く**。
#: 以前はプリセットごとに吹圧を独立の定数で与えていたため、γ が
#: loose 1.14 / normal 0.70 / tight 0.30 とばらけていた（CLARINET プリセットの
#: 既定は 0.40）。γ>1 は静的変位が静止開口を超える領域で、まともな発振領域ではない。
#: **そして「締め具合」を選ばせているつもりで、実際に選ばせていたのは吹きすぎ具合
#: だった** —— tight（リード共振が最も高い＝最も硬い）が γ 最小で一番きれいに
#: 基音が出る、という名前と逆の並びの正体がこれ。3 プリセットで揃える。
BLOWING_RATIO = 0.30

#: アンブシュア＝リード共振 [Hz]。**締めるほど高い。**
#:
#: 吹圧はここに書かない。`_reed_player` が `f_reed` を決めた後に `p_M` から
#: 導出する（`BLOWING_RATIO`）。そうすると `tip_opening`（`opening` 経由で
#: p_M ∝ y₀）と `facing_length`（f_reed 経由で p_M ∝ ω₀²）が吹圧に効くようになる
#: —— 定数で持っていた頃は設計値を動かしても吹圧が変わらなかった。
#: `override` でリード実形状の f_reed が来る経路でも γ が保たれる。
EMBOUCHURES: dict[str, float] = {
    "loose":  1800.0,
    "normal": 2700.0,
    "tight":  3700.0,
}
DEFAULT_EMBOUCHURE = "normal"


def beating_pressure(f_reed_hz: float, opening_m: float) -> float:
    """静的ビーティング圧 `p_M = ω₀²·(M_r/S_r)·y₀` [Pa]。

    `M_r`（実効質量）と `S_r`（実効振動面積）は CLARINET プリセットの値を
    **上書きしていない 2 つ**なので、マジックナンバーを写さずプリセットから読む。
    どれを上書きしてどれを残しているかがコードから読めるようにするため。
    """
    from openwind.technical.default_excitator_parameters import CLARINET
    omega = 2.0 * math.pi * f_reed_hz
    return omega * omega * (CLARINET["mass"] / CLARINET["section"]) * opening_m


def _reed_player(params: dict, embouchure: str,
                 override: dict | None = None):  # pragma: no cover - 環境依存
    """マウスピース設計値を反映した有次元 1自由度リード奏者。

    `CLARINET` プリセット（Bilbao 2008）を基点に、設計値は**相対倍率**で効かせる。
    絶対値で上書きするとプリセットの校正が壊れて持続発振しなくなる（実測済み）。
    無次元版（WOODWIND_REED_SCALED）は本ジオメトリで発振しないため採らない。

    `override`（リード コンポーネントから渡る）があれば、リード共振はアンブシュア
    プリセットではなく**リード実形状から算出した f_reed** を使う。幅も実寸に置く。
    リードを設計している以上、リードの物理はリード側の値が正となる。

    吹圧は定数ではなく `BLOWING_RATIO × p_M` で導出する。`p_M` は f_reed と
    `opening` から決まるので、どの経路（プリセット / リード実形状）でも
    吹奏比が揃う。
    """
    from openwind import Player
    from openwind.technical.default_excitator_parameters import (
        constant_with_initial_ramp)

    f_base = EMBOUCHURES.get(embouchure, EMBOUCHURES[DEFAULT_EMBOUCHURE])
    player = Player("CLARINET")

    # 設計パラメータ連動：これが無いと設計を変えても音が変わらない
    opening = 4e-4 * (params.get("tip_opening", 1.8) / 1.8)
    player.update_curve("opening", opening)
    reed_w = (override or {}).get("width_mm", params.get("reed_width", 14.5))
    player.update_curve("width", 3e-2 * (reed_w / 14.5))
    if override and override.get("f_reed"):
        f_reed = float(override["f_reed"])
    else:
        # フェイシングが長い＝リードの有効長が長い＝リード共振が低い
        f_reed = f_base * (23.0 / max(params.get("facing_length", 23.0), 1.0))
    player.update_curve("pulsation", 2 * math.pi * f_reed)
    player.update_curve("dissip", 3000.0 * f_reed / 3700.0)

    # `pulsation` だけ書き換えて `mass` / `section` を CLARINET のまま残している
    # ので、p_M は ω₀² で動く。吹圧を定数で持つと吹奏比がプリセットごとにばらける。
    mouth_pa = BLOWING_RATIO * beating_pressure(f_reed, opening)
    player.update_curve("mouth_pressure",
                        constant_with_initial_ramp(mouth_pa, 0.02))
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
        temperature=TEMPERATURE_C,
        record_energy=False,
        verbosity=0,
    )
    key = 'bell_radiation_pressure'
    if key not in rec.values:
        raise RuntimeError(
            i18n.t(
                "OpenWind の録音に {key} がありません: {list}",
                key=f"{key}", list=f"{list(rec.values.keys())}"))
    audio = _to_audio(np.asarray(rec.values[key]), 1.0 / rec.dt)
    return audio, _measure_f0(audio), mouth_pa


def synthesize(params: dict, size_info: dict,
               embouchure: str = DEFAULT_EMBOUCHURE,
               duration: float = 0.6,
               override: dict | None = None) -> tuple[bytes, dict]:
    """単音の物理モデル音（OpenWind 必須）。

    音高は指定できない。トーンホールの無い固定ボアは自前の共鳴しか鳴らないので、
    鳴るのは**この管の第1共鳴**。3 アンブシュアとも同じ高さに落ち着き、違うのは
    立ち上がりと倍音の重みだけ（`BLOWING_RATIO` で吹奏比を揃えてあるため）。
    実際に鳴った f0 を meta で返す。`override` はリード コンポーネントからの
    リード実形状の反映値。
    """
    if not HAS_OPENWIND:
        raise RuntimeError(i18n.t("OpenWind 未導入のため物理モデル音合成は利用できません"))
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
    """緩め→標準→締めを順に鳴らす（OpenWind 必須）。

    **倍音レジスタではない。** 以前はレジスタが変わるつもりで並べていたが、
    それは共鳴管が非調和になっていたせい（`_coarsen` が段差を落としていた）で、
    直すと 3 つとも第1共鳴に落ち着く。いま並べているのは**同じ音の 3 通りの
    締め具合**で、違うのは立ち上がりと倍音の重み。

    リード共振は時間変化させられない（OpenWind の Reed1dof は mouth_pressure 以外
    定数のみ）ため、1音ずつシミュして連結する。
    """
    if not HAS_OPENWIND:
        raise RuntimeError(i18n.t("OpenWind 未導入のため物理モデル音合成は利用できません"))
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
