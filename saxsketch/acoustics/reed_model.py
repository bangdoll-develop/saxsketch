"""リードの機械特性モデル（片持ち梁近似）。

リード形状 → 曲げ剛性 → 1次共振周波数 f_reed と「硬さ相当値」を算出する。
f_reed は `openwind_bridge._reed_player` の `pulsation` に流し込まれ、リード設計の
変更が物理モデル音に反映される（Phase 3 の価値の核）。

免責: 片持ち梁近似＋文献ヤング率のため**絶対値は当てにならない**。Tier2 と同じく
「パラメータを動かしたときにどちらへ動くか」を見るための指標として扱うこと。
"""
from __future__ import annotations

import math

from saxsketch import i18n

#: 材料表の唯一の出所: key → (表示名, ヤング率 E [MPa], 密度 ρ [kg/m³],
#: 実用強度の下限厚 [mm], 工程)。UI の選択肢も BOM の材料名もここから引く
#: （物性と表示名が別々の表にあると、片方だけ増やしても実行時エラーにならず
#: 黙って既定材料の物性が使われる）。
#:
#: **E と ρ は文献値、下限厚は出典未記録の仮定。** 前者はモジュール冒頭の免責の
#: とおり絶対値を当てにしない。後者は「この材料でこの薄さの梁が屈曲に耐えるか」で、
#: **解像度の下限（`min_layer × 3`）とは別の量**。決着させるのは実際に印刷して
#: 折れるまで曲げること —— 寸法の実測では決まらない。
#:
#: 工程は**説明とカードの文面にだけ使う。クランプには使わない** —— 材料を選び直した
#: 瞬間に他のパラメータが黙って動く経路を作らないため（この repo が繰り返し
#: 踏んでいる穴）。`min_layer` の可動域も工程で切り替えず、1 本に広げてある。
MATERIALS: dict[str, tuple[str, float, float, float, str]] = {
    "pla": ("PLA(FDM)", 3500.0, 1240.0, 0.35, "fdm"),
    "petg": ("PETG(FDM)", 2000.0, 1270.0, 0.40, "fdm"),
    "resin_rigid": ("標準レジン(光造形)", 2400.0, 1180.0, 0.20, "msla"),
    "resin_flex": ("フレキシブルレジン(光造形)", 1200.0, 1150.0, 0.30, "msla"),
    "pp": ("ポリプロピレン", 1400.0, 905.0, 0.45, "fdm"),
    "cane": ("ケーン（参考値・切削前提）", 9000.0, 450.0, 0.07, "cut"),
}
DEFAULT_MATERIAL = "pla"

#: 工程の表示名。`MATERIALS` の 5 列目を人が読む形にするだけ。
PROCESS_LABELS = {"fdm": "FDM", "msla": "光造形", "cut": "切削"}

#: 先端厚とヴァンプ長の可動域。**`ParamSpec` とソルバの唯一の出所**
#: （2 か所に書くと食い違い、ソルバが UI で設定できない値を勧める）。
#:
#: 先端厚の下限を 0.15 → **0.08** へ下げてある。光造形の解像度下限（積層 0.02 × 3
#: = 0.06）と実物のケーン（0.11。この repo の校正基準 `_CALIB_PARAMS` そのもの）が
#: どちらも域内に入る。テンプレート既定は 3 サイズとも 0.38 以上なので、
#: **黙ったクランプは起きない**。
TIP_THICKNESS_RANGE = (0.08, 0.90)
VAMP_LENGTH_RANGE = (18.0, 48.0)
#: 積層ピッチ。下限 0.04 → **0.02**（光造形）。既定 0.08 は不変。
MIN_LAYER_RANGE = (0.02, 0.20)


def material_label(key: str) -> str:
    # 表はモジュール直下にあるので、訳すのは**引く所**（取り込み時に
    # 固めない）。`i18n.CHOICES` が同じ鍵で英語を持っている。
    return i18n.choice_label(key, MATERIALS.get(key, (key,))[0])


def material_process(key: str) -> str:
    """工程の表示名（「FDM」/「光造形」/「切削」）。"""
    row = MATERIALS.get(key, MATERIALS[DEFAULT_MATERIAL])
    return i18n.choice_label(row[4], PROCESS_LABELS.get(row[4], row[4]))


def _rp():
    """`reed_profiles` を遅延 import する。

    モジュール先頭で読むと `components/__init__` の初期化中に本モジュールを
    import できず循環になる（`reed.py` はここから材料表を引く）。
    `mouthpiece.py` が `openwind_bridge` をメソッド内 import しているのと同じ形。
    """
    from saxsketch.instruments.saxophone.components import reed_profiles
    return reed_profiles


#: 硬さスケールの校正基準。ケーン材で先端厚 0.11mm の標準プロファイルを「3.0」とする。
_CALIB_STRENGTH = 3.0
_CALIB_PARAMS = {
    "reed_length": 71.5, "tip_width": 14.5, "heel_width": 14.8,
    "tip_thickness": 0.11, "heel_thickness": 2.80, "vamp_length": 32.0,
    # 校正基準は**実物のケーン**なので、上面の円弧も前縁カーブも持つ側が正しい。
    # 値そのものは校正には効かない（`_strength_equiv` はこのリード自身のたわみとの
    # 比なので、基準の 3.0 は定義上いつでも 3.0）。効くのは他のリードとの相対位置。
    "heel_edge_thickness": 0.9, "tip_curve_depth": 1.3,
    "profile_curve": "parabolic", "spine_ratio": 1.15,
    "side_rail_thin": 0.55, "tip_corner_r": 0.8,
    "file_cut": "unfiled", "material": "cane", "min_layer": 0.08,
}
_CALIB_L_EFF = 23.0  # アルト標準マウスピースのフェイシング長 [mm]


def _material(key: str) -> tuple[float, float, float]:
    """(E, ρ, 実用強度の下限厚)。表示名は material_label() / material_process() で引く。

    **スライスではなく明示のインデックス**で取る —— 表に列を足したときに
    タプルのアンパックが黙って壊れないようにする。
    """
    row = MATERIALS.get(key, MATERIALS[DEFAULT_MATERIAL])
    return row[1], row[2], row[3]


def effective_length(p: dict, ref_mp: dict) -> float:
    """リードの自由振動長 [mm] ＝ マウスピースの**フェイシング長**。

    リードはテーブル面に密着しており、浮いて曲げられるのはフェイシングカーブが
    始まる点から先端までの区間だけ。ウィンドウ長（窓の長さ）を使うと自由長を
    30〜40%過大に取ることになり、f_reed が実測相場（2000〜3000Hz）の 1/5 に
    なることを実測で確認したため、フェイシング長を採る。
    """
    rp = _rp()
    if ref_mp:
        return max(min(ref_mp["facing_length"], rp.vamp_start_z(p)), 5.0)
    return max(rp.vamp_start_z(p) * 0.7, 5.0)


def _bending(p: dict, l_eff: float, e_mpa: float, samples: int = 48
             ) -> tuple[float, float, float]:
    """自由振動区間の曲げ挙動 → (先端たわみ δ [mm/kPa], 等価 I [mm⁴], 平均 A [mm²])。

    リードは踵側で固定され先端が自由な片持ち梁。等分布荷重を受けたときの先端
    たわみを単位荷重法で数値積分する:

        δ = ∫₀^L  w · z³ / (2·E·I(z))  dz      （z は先端からの距離＝固定端まで L）

    重みが z³ なので**固定端側（厚い部分）が支配する**。断面二次モーメントの
    調和平均で代表させると薄い先端を過大評価してしまい、印刷リードの硬さが
    実態から大きく外れる（実測で判明）。

    等価 I は、この δ を一様断面の閉形式 δ = w·L⁴/(8·E·I) に当てはめて逆算する
    （共振周波数の算出と指標が同じ剛性を指すようにするため）。
    """
    rp = _rp()
    w = 0.001 * rp.tip_load_width(p)
    defl = _tip_deflection(p, l_eff, e_mpa, samples)
    # **`sum()` を使わない。** Python 3.12 の `sum()` は浮動小数で Neumaier の
    # 補正和になるため、素朴な `+=` と結果が 1 ULP 変わる。それだけで f_reed の
    # 記録値が動く（実測: 3 サイズ中 3 例で末尾 1 桁）。より正確な和のほうが
    # 「良い」が、ここは理由の説明できない差を作らないほうを取る。
    area = 0.0
    for i in range(samples):
        area += rp.cross_area(p, l_eff * (i + 0.5) / samples)
    inertia_eq = w * l_eff ** 4 / (8.0 * e_mpa * max(defl, 1e-12))
    return defl, inertia_eq, area / samples


def _tip_deflection(p: dict, l_eff: float, e_mpa: float,
                    samples: int = 48) -> float:
    """先端たわみ δ [mm/kPa] だけ。**`_bending` の第 1 返り値と同じ式・同じ順序。**

    分けてあるのは速度のため —— 硬さのソルバは δ しか見ないのに、`_bending` は
    断面積の積分も毎回回す。二分法で数十回呼ぶと**その半分が丸ごと無駄**になる。
    これと反復数（32 → 20）で、**推奨値を 2 本出しても旧実装が 1 本出すより速い**
    （実測・温まった状態で `reed_properties` が 0.092 秒、旧実装相当は 0.157 秒）。
    """
    rp = _rp()
    # 1kPa × 先端の実効幅 [N/mm]。**`width(p, 0.0)` ではない** —— 前縁カーブを
    # 入れると z=0 は幅ゼロの尖点になり、荷重が 1/27 に落ちて硬さが振り切れる。
    w = 0.001 * rp.tip_load_width(p)
    dz = l_eff / samples
    defl = 0.0
    for i in range(samples):
        z = l_eff * (i + 0.5) / samples
        inertia = max(rp.second_moment(p, z), 1e-12)
        defl += w * z ** 3 / (2.0 * e_mpa * inertia) * dz
    return defl


def reed_properties(p: dict, ref_mp: dict) -> dict:
    """リードの機械特性。

    Returns: f_reed_hz, strength_equiv, strength_label, ei_n_mm2,
             l_eff_mm, tip_compliance_mm_per_kpa, printable, min_thickness_mm,
             deflection_bands,
             recommended_tip_mm / recommended_vamp_mm（**None のことがある**）と
             recommended_*_limit（None のときの「どこまで行けるか」）。
    """
    e_mpa, rho, min_t = _material(p.get("material", DEFAULT_MATERIAL))
    l_eff = effective_length(p, ref_mp)
    tip_defl_mm, inertia, area = _bending(p, l_eff, e_mpa)

    # 片持ち梁 1次固有振動数: f = (1.875²/2π)·sqrt(E·I / (ρ·A·L⁴))
    # 単位を SI へ: E[MPa]=1e6 N/m², I[mm⁴]=1e-12 m⁴, A[mm²]=1e-6 m², L[mm]=1e-3 m
    ei = e_mpa * 1e6 * inertia * 1e-12                    # N·m²
    mu = rho * area * 1e-6                                # kg/m（線密度）
    l_m = l_eff * 1e-3
    f_reed = (1.875 ** 2 / (2.0 * math.pi)) * math.sqrt(ei / (mu * l_m ** 4))

    strength = _strength_equiv(tip_defl_mm)
    tip_mm, tip_limit = tip_thickness_for_strength(p, ref_mp)
    vamp_mm, vamp_limit = vamp_length_for_strength(p, ref_mp)
    return {
        "f_reed_hz": f_reed,
        "strength_equiv": strength,
        "strength_label": _strength_label(strength),
        "ei_n_mm2": ei * 1e6,                             # N·mm²（表示用）
        "l_eff_mm": l_eff,
        "tip_compliance_mm_per_kpa": tip_defl_mm,
        "min_thickness_mm": min_t,
        "printable": p.get("material") == "cane" or p["tip_thickness"] >= min_t,
        # **None のことがある。** 「先端厚だけでは目標の硬さに届かない」は
        # 端の値へ丸めるのではなく、そう言う（下の docstring）。
        "recommended_tip_mm": tip_mm,
        "recommended_tip_limit": tip_limit,
        "recommended_vamp_mm": vamp_mm,
        "recommended_vamp_limit": vamp_limit,
        "deflection_bands": deflection_bands(p, ref_mp),
    }


def deflection_bands(p: dict, ref_mp: dict, bands: int = 4,
                     samples: int = 48) -> list[float]:
    """先端たわみへの寄与の割合 [%]（先端側 → 固定端側に等分）。

    「硬さは材質と厚さで決まるのか」への答えそのもの。`_bending` の被積分関数は
    `z³/I(z)` で、**z³ の重みが固定端側を支配する**ため、先端 1/4 の寄与は
    実測で 6% 前後しかない（ヴァンプ長 20mm で 9.2% / 40mm で 4.2%）。
    先端厚がいちばん弱いレバーなのはこれが理由で、カードはこの内訳を出す。

    **材料に依らない** —— E は積分の外に出るので割合は形だけで決まる。
    刻みは `_bending` と同じにしてある（別の刻みだと表示とモデルがずれる）。
    """
    rp = _rp()
    l_eff = effective_length(p, ref_mp)
    w = 0.001 * rp.tip_load_width(p)
    acc = [0.0] * bands
    for i in range(samples):
        z = l_eff * (i + 0.5) / samples
        d = w * z ** 3 / (2.0 * max(rp.second_moment(p, z), 1e-12))
        acc[min(int(z / l_eff * bands), bands - 1)] += d
    total = sum(acc)
    if total <= 0.0:
        return [0.0] * bands
    return [a / total * 100.0 for a in acc]


def _solve_for_strength(p: dict, ref_mp: dict, key: str,
                        span: tuple[float, float], target: float
                        ) -> tuple[float | None, tuple[float, float] | None]:
    """`key` を `span` 内で振って硬さ `target` を解く。

    Returns: (解, None) か **(None, (いちばん近い端, そこでの硬さ))**。

    **端へ丸めない。** 旧実装は解が無いときに端の値をそのまま返し、さらに
    造形下限で `max()` していたので、カードが「この厚みで 3番相当になります」と
    **ならない値**を出していた（3 サイズ × 5 材料の 15 通りのうち 6 通り）。
    黙って域内へ潰すのはこの repo が繰り返し踏んでいる穴なので、
    届かないことは呼び手に見える形で返す。

    向きは端点から判定する（硬さは先端厚に対し増加、ヴァンプ長に対し減少）。
    """
    lo, hi = span

    def strength(v: float) -> float:
        q = dict(p, **{key: v})
        e_mpa = _material(q.get("material", DEFAULT_MATERIAL))[0]
        # **`_bending` ではない** —— 断面積の積分は硬さに要らない（`_tip_deflection`）。
        return _strength_equiv(
            _tip_deflection(q, effective_length(q, ref_mp), e_mpa))

    s_lo, s_hi = strength(lo), strength(hi)
    if (s_lo - target) * (s_hi - target) > 0.0:
        # 両端とも同じ側 ＝ 域内に解が無い。届く限界（近いほうの端）を返す。
        return (None, (lo, s_lo) if abs(s_lo - target) < abs(s_hi - target)
                else (hi, s_hi))
    inc = s_hi > s_lo
    # 20 回で残差 0.82mm / 2²⁰ ＝ 8e-7 mm。表示は小数 2 桁なので十分すぎる。
    for _ in range(20):
        mid = (lo + hi) / 2.0
        if (strength(mid) < target) == inc:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0, None


def tip_thickness_for_strength(p: dict, ref_mp: dict,
                               target: float = _CALIB_STRENGTH
                               ) -> tuple[float | None, tuple[float, float] | None]:
    """指定の硬さ相当値になる先端厚 [mm]。域内に解が無ければ (None, 限界)。

    材料ごとの推奨先端厚を表で持たない理由: ヤング率だけでなく形状（ヴァンプ長・
    背骨比・幅）にも依存するので、表にすると他のパラメータを動かした瞬間に嘘になる。

    ケーンの 0.11mm が 3.0 という校正基準（_CALIB_*）と同じ土俵に乗るため、
    「この材料で 3番相当にするなら何mm か」が直接出る。ただし**先端厚は
    いちばん弱いレバー**（`deflection_bands` 参照）なので、柔らかい材料では
    可動域いっぱいでも届かない。そのときは None を返す。
    """
    return _solve_for_strength(p, ref_mp, "tip_thickness",
                               TIP_THICKNESS_RANGE, target)


def vamp_length_for_strength(p: dict, ref_mp: dict,
                             target: float = _CALIB_STRENGTH
                             ) -> tuple[float | None, tuple[float, float] | None]:
    """指定の硬さ相当値になるヴァンプ長 [mm]（先端厚は据え置き）。

    **先端厚を実物並みに薄くしたまま普通の硬さにできる**ことを示すための道。
    実測（alto・先端 0.11mm 固定）: ケーン 32.1 / PLA 24.2 / PETG 20.8 / PP 19.1 で
    どれも硬さ 3.0 に届き、全部可動域の内側。短くするほど自由長のつけ根が厚くなる
    ので硬くなる ＝ 硬さはヴァンプ長に対し**減少**する。
    """
    return _solve_for_strength(p, ref_mp, "vamp_length",
                               VAMP_LENGTH_RANGE, target)


def _strength_equiv(tip_defl_mm: float) -> float:
    """硬さ相当値。柔らかい（よくたわむ）ほど数値が小さい。

    校正基準（ケーン 0.11mm = 3.0）との**たわみ比**から換算する。市販の硬さ番手は
    曲げ剛性におおむね比例するため、剛性比 = たわみ比の逆数を線形に対応させる。
    """
    calib = _calibration_deflection()
    if tip_defl_mm <= 0:
        return 20.0
    # 上限は 20（市販は 5 まで）。振り切れた値でも「どれだけ外れているか」は
    # 設計上の情報なので、頭打ちを高めに取って分解能を残す。
    return max(min(_CALIB_STRENGTH * (calib / tip_defl_mm), 20.0), 0.5)


_calib_cache: float | None = None


def _calibration_deflection() -> float:
    """校正基準リードの先端たわみ [mm/kPa]（初回のみ計算してキャッシュ）。"""
    global _calib_cache
    if _calib_cache is None:
        e_mpa, _, _ = _material("cane")
        _calib_cache = _bending(dict(_CALIB_PARAMS), _CALIB_L_EFF, e_mpa)[0]
    return _calib_cache


def _strength_label(v: float) -> str:
    """市販の硬さ番手表記（1, 1½, 2, 2½ …）へ丸める。番手レンジ外は数値で示す。"""
    if v > 5.25:
        return i18n.t("硬さ {v}（市販番手レンジ外）", v=f"{v:.1f}")
    half = round(v * 2.0) / 2.0
    whole = int(half)
    return i18n.t("{whole}½ 相当", whole=f"{whole}") if half - whole >= 0.5 else i18n.t("{whole} 相当", whole=f"{whole}")


def reed_override(props: dict, p: dict) -> dict:
    """`openwind_bridge._reed_player` へ渡すリード実形状の反映値。

    - f_reed: 片持ち梁共振（アンブシュア プリセットの値を置き換える）
    - opening_scale: ティップ開きに対する相対倍率はマウスピース側が担うので、
      ここでは幅のみリード実寸を渡す。

    **`width(p, 0.0)` ではない**（`_bending` と同じ代理変数の穴。こちらは
    4-C.2 で直し損ねていた）。`width_mm` は OpenWind のリード流路の幅で、息が
    通るのは**先端がティップレールと向き合っている幅**。z=0 の断面の幅ではない
    ので、前縁カーブを入れると 0.5mm へ潰れて流れが線形域に落ち、**合成音が
    倍音を失って純正弦になる**（実測: 倍音比の L1 差 1.42 → 0.0006）。
    4-C.2 で気づかなかったのは、当時 `width(p, 0.0)` が z=0 を円弧クランプから
    漏らしていて**たまたま `tip_load_width` と同じ値を返していた**から。
    """
    return {
        "f_reed": props["f_reed_hz"],
        "width_mm": _rp().tip_load_width(p),
    }
