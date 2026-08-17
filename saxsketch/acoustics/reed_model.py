"""リードの機械特性モデル（片持ち梁近似）。

リード形状 → 曲げ剛性 → 1次共振周波数 f_reed と「硬さ相当値」を算出する。
f_reed は `openwind_bridge._reed_player` の `pulsation` に流し込まれ、リード設計の
変更が物理モデル音に反映される（Phase 3 の価値の核）。

免責: 片持ち梁近似＋文献ヤング率のため**絶対値は当てにならない**。Tier2 と同じく
「パラメータを動かしたときにどちらへ動くか」を見るための指標として扱うこと。
"""
from __future__ import annotations

import math

#: 材料表の唯一の出所: key → (表示名, ヤング率 E [MPa], 密度 ρ [kg/m³],
#: 実用上の最小造形厚 [mm])。UI の選択肢も BOM の材料名もここから引く
#: （物性と表示名が別々の表にあると、片方だけ増やしても実行時エラーにならず
#: 黙って既定材料の物性が使われる）。
MATERIALS: dict[str, tuple[str, float, float, float]] = {
    "pla": ("PLA(FDM)", 3500.0, 1240.0, 0.35),
    "petg": ("PETG(FDM)", 2000.0, 1270.0, 0.40),
    "resin_flex": ("フレキシブルレジン(光造形)", 1200.0, 1150.0, 0.30),
    "pp": ("ポリプロピレン", 1400.0, 905.0, 0.45),
    "cane": ("ケーン（参考値・切削前提）", 9000.0, 450.0, 0.07),
}
DEFAULT_MATERIAL = "pla"


def material_label(key: str) -> str:
    return MATERIALS.get(key, (key,))[0]


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
    """(E, ρ, 最小造形厚)。表示名は material_label() で引く。"""
    return MATERIALS.get(key, MATERIALS[DEFAULT_MATERIAL])[1:]


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
    # 1kPa × 先端の実効幅 [N/mm]。**`width(p, 0.0)` ではない** —— 前縁カーブを
    # 入れると z=0 は幅ゼロの尖点になり、荷重が 1/27 に落ちて硬さが振り切れる。
    w = 0.001 * rp.tip_load_width(p)
    dz = l_eff / samples
    defl, area = 0.0, 0.0
    for i in range(samples):
        z = l_eff * (i + 0.5) / samples
        inertia = max(rp.second_moment(p, z), 1e-12)
        defl += w * z ** 3 / (2.0 * e_mpa * inertia) * dz
        area += rp.cross_area(p, z)
    inertia_eq = w * l_eff ** 4 / (8.0 * e_mpa * max(defl, 1e-12))
    return defl, inertia_eq, area / samples


def reed_properties(p: dict, ref_mp: dict) -> dict:
    """リードの機械特性。

    Returns: f_reed_hz, strength_equiv, strength_label, ei_n_mm2,
             l_eff_mm, tip_compliance_mm_per_kpa, printable, min_thickness_mm
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
    return {
        "f_reed_hz": f_reed,
        "strength_equiv": strength,
        "strength_label": _strength_label(strength),
        "ei_n_mm2": ei * 1e6,                             # N·mm²（表示用）
        "l_eff_mm": l_eff,
        "tip_compliance_mm_per_kpa": tip_defl_mm,
        "min_thickness_mm": min_t,
        "printable": p.get("material") == "cane" or p["tip_thickness"] >= min_t,
        "recommended_tip_mm": tip_thickness_for_strength(p, ref_mp),
    }


def tip_thickness_for_strength(p: dict, ref_mp: dict,
                               target: float = _CALIB_STRENGTH) -> float:
    """指定の硬さ相当値になる先端厚を解く [mm]。

    材料ごとの推奨先端厚を表で持たない理由: ヤング率だけでなく形状（ヴァンプ長・
    背骨比・幅）にも依存するので、表にすると他のパラメータを動かした瞬間に嘘になる。
    硬さは先端厚に対し単調増加なので二分法で解ける。

    ケーンの 0.11mm が 3.0 という校正基準（_CALIB_*）と同じ土俵に乗るため、
    「この材料で 3番相当にするなら何mm か」が直接出る。
    """
    _, _, min_t = _material(p.get("material", DEFAULT_MATERIAL))
    lo, hi = 0.02, 1.20

    def strength(t: float) -> float:
        q = dict(p, tip_thickness=t)
        l_eff = effective_length(q, ref_mp)
        return _strength_equiv(_bending(q, l_eff, _material(
            q.get("material", DEFAULT_MATERIAL))[0])[0])

    if strength(hi) < target:
        return hi
    if strength(lo) > target:
        return lo
    for _ in range(32):
        mid = (lo + hi) / 2.0
        if strength(mid) < target:
            lo = mid
        else:
            hi = mid
    # 造形下限を割る解は印刷できないので下限へ丸める（カード側で警告する）
    return max((lo + hi) / 2.0, min_t)


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
        return f"硬さ {v:.1f}（市販番手レンジ外）"
    half = round(v * 2.0) / 2.0
    whole = int(half)
    return f"{whole}½ 相当" if half - whole >= 0.5 else f"{whole} 相当"


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
