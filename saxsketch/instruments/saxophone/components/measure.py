"""取込メッシュからマウスピース パラメータを逆算（実測）する。

手法: 構成数式（profiles.py）を既知として、メッシュの断面・レイキャスト・
表面サンプルから各特徴寸法を実測し、パラメータ値へ逆変換する。

前提: 外部編集時に座標系（z=0 がティップ、Y+ がビーク）を移動していないこと。
移動を検出した場合は逆算を中止し警告のみ返す。

実測可能: 全長 / ボディ径 / ビーク高さ / ティップ開き / フェイシング長 /
ボア径 / ウィンドウ長(実効) / リード幅 / バッフル高さ / スロート断面積比
実測不能（幾何から一意に復元できない）: カーブ種別・レール幅・ロールオーバー
半径・チェンバー形状・ボア長・コーク挿入深さ・最小肉厚・材料
"""
from __future__ import annotations

import math

import numpy as np
import trimesh

from . import profiles

# 逆算対象外のパラメータとその理由
UNMEASURABLE = {
    "facing_length": "フェイシング面の露出が先端部のみで、カーブ全長は一意復元できない",
    "reed_width": "窓開口はスーパー楕円断面のため設計窓幅と一致せず一意復元できない"
                  "（変化は領域偏差で検出）",
    "facing_curve": "曲線種別は形状から一意判別できない",
    "tip_rail_width": "レール幅は分解能不足（±0.15mm）",
    "side_rail_width": "レール幅は分解能不足（±0.15mm）",
    "rollover_radius": "バッフル肩の曲率は直接測定できない",
    "chamber_shape": "断面指数は直接測定できない",
    "bore_length": "ボア開始位置の遷移が緩やかで一意に定まらない",
    "cork_depth": "組立条件であり形状に現れない",
    "min_wall": "全面の肉厚走査は未対応",
    "material": "材料は形状に現れない",
}


def _first_hit_dists(mesh: trimesh.Trimesh, origins: list, dirs: list) -> list[float | None]:
    """各レイの最初のヒットまでの距離。ヒットなしは None。"""
    o = np.asarray(origins, dtype=float)
    d = np.asarray(dirs, dtype=float)
    locs, idx_ray, _ = mesh.ray.intersects_location(o, d)
    out: list[float | None] = [None] * len(origins)
    for loc, ir in zip(locs, idx_ray):
        dist = float(np.linalg.norm(loc - o[ir]))
        if out[ir] is None or dist < out[ir]:
            out[ir] = dist
    return out


def estimate_params(mesh: trimesh.Trimesh, frozen: dict, specs: list) -> dict:
    """Returns {"params": [row...], "warnings": [str...]}.

    row = {key, label, unit, frozen, estimated, delta, verdict, method}
    verdict: 一致(|Δ|≤max(0.6step,0.05)) / 軽微(≤2.5step) / 乖離 / 測定不能
    """
    p = frozen
    warnings: list[str] = []
    spec_by_key = {s.key: s for s in specs}
    L = p["overall_length"]
    fl = p["facing_length"]
    ty_frozen = profiles.table_y(p)

    # ---- 座標系チェック（z のみ許容シフト、x/y の移動は逆算不能）
    bmin, bmax = mesh.bounds
    z_off = float(bmin[2])
    if abs(z_off) > 0.5:
        warnings.append(
            f"モデルが Z 方向に {z_off:+.1f}mm 移動しています。z=0 基準に補正して測定します。")
    x_center = float((bmin[0] + bmax[0]) / 2.0)
    if abs(x_center) > 0.5:
        warnings.append(
            "モデルが X 方向に移動しており座標系が崩れています。パラメータ逆算を中止しました。"
            "外部ツールで移動・回転させずに編集してください。")
        return {"params": _all_unmeasurable(specs), "warnings": warnings}

    # ---- 表面サンプル（法線つき）
    pts, fidx = trimesh.sample.sample_surface(mesh, 150_000)
    pts = np.asarray(pts) - [0.0, 0.0, z_off]
    normals = mesh.face_normals[np.asarray(fidx)]

    est: dict[str, tuple[float, str]] = {}  # key -> (value, method)

    # ---- 全長
    L_meas = float(bmax[2] - bmin[2])
    est["overall_length"] = (L_meas, "バウンディングボックス")

    # ---- テーブル平面 Y（以降の基準。窓より後方の平坦部の中央値）
    bottom = (normals[:, 1] < -0.9) & (pts[:, 2] < profiles.table_cut_end_z(p) - 2.0)
    flat = bottom & (pts[:, 2] > fl * 1.15) & (np.abs(pts[:, 1] - ty_frozen) < 3.0)
    if flat.sum() < 100:
        warnings.append("テーブル平面を検出できませんでした。フェイシング系の逆算を省略します。")
        ty_meas = None
    else:
        ty_meas = float(np.median(pts[flat, 1]))

    # ---- ティップ開き（ティップレール面 z < z_start のみが確実に露出する。
    #      窓区間の底面は空洞で開いているため使えない。fl は凍結値で固定し、
    #      各サンプル点の「含意ティップ値」 (y-ty)/カーブ係数 の下側パーセンタイルを採る。
    #      面より上の点は含意値が大きく出るので下側が面の真値。）
    if ty_meas is not None:
        z_rail_end = p["tip_rail_width"] + 0.2  # 空洞開始 = レール面の終端
        # レール面はカーブで傾くため法線フィルタは緩め、上方の点は含意値の上位に逃がす
        fz = (normals[:, 1] < -0.6) & (pts[:, 2] < z_rail_end) \
            & (pts[:, 2] > 0.05) & (pts[:, 1] < ty_meas + 5.0)
        if fz.sum() >= 30:
            zz, yy = pts[fz, 2], pts[fz, 1]
            coef = 1.0 - np.sqrt(np.clip(
                1.0 - ((fl - zz) / fl) ** 2, 1e-6, 1.0))  # rise = tip·coef
            implied = (yy - ty_meas) / np.maximum(coef, 0.30)
            tip_est = float(np.percentile(implied, 4.0))
            est["tip_opening"] = (tip_est, "ティップレール面(凍結fl仮定)", 0.10)

    # ---- ビーク高さ（各 z ビンの上端 p95 ＝ビーク斜面。側面フランクの混入を排除し、
    #      勾配によるビン内バイアスは評価点シフト +0.95·幅 で補正して直線回帰）
    if ty_meas is not None:
        top = (normals[:, 1] > 0.5) & (pts[:, 2] > 0.20 * L) & (pts[:, 2] < 0.27 * L)
        if top.sum() >= 60:
            zz, yy = pts[top, 2], pts[top, 1]
            bz, by = [], []
            for b0 in np.arange(0.20 * L, 0.27 * L, 1.0):
                m = (zz >= b0) & (zz < b0 + 1.0)
                if m.sum() >= 15:
                    bz.append(b0 + 0.95)   # p95 は勾配のためビン上端相当
                    by.append(float(np.percentile(yy[m], 95.0)))
            if len(bz) >= 3:
                a, b = np.polyfit(bz, by, 1)
                est["beak_height"] = (
                    float(a * 0.25 * L + b) - ty_meas, "ビーク斜面p95回帰")

    # ---- ボディ径（リガチャー座の最大半径。彫刻は径を減らす方向なので上位percentile）
    mid = (pts[:, 2] > 0.45 * L) & (pts[:, 2] < 0.62 * L)
    if mid.sum() >= 100:
        r = np.hypot(pts[mid, 0], pts[mid, 1])
        est["body_dia"] = (2.0 * float(np.percentile(r, 99.5)), "最大半径")

    # ---- レイキャスト系（ボア・窓・バッフル・スロート）
    zb = profiles.bore_start_z(p)
    rb = profiles.bore_radius(p)

    # ボア径: シャンク端近くの軸上から放射レイ
    o = [0.0, 0.0, L_meas - 2.0 + z_off]
    dists = _first_hit_dists(mesh, [o] * 4,
                             [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]])
    good = [d for d in dists if d is not None and d < rb * 2.0]
    if len(good) >= 3:
        est["bore_dia"] = (2.0 * float(np.mean(good)), "軸上放射レイ")

    if ty_meas is not None:
        # ウィンドウ長(実効): 下方から +Y レイを z 走査し「窓が開いている」範囲を測る。
        # 閉じている z ではカット面(≈ty)にヒット、開いている z では空洞天井
        # (≥ty+0.4、クランプ時でも)にヒットする → しきい値 ty+0.35。
        # ティップレール面はカーブで持ち上がり誤判定するため z_start より後方から走査。
        z_start = p["tip_rail_width"] + 0.2
        z_we_frozen = min(z_start + p["window_length"], zb - 8.0)
        z_scan = np.arange(z_start + 0.5,
                           min(z_start + p["window_length"] + 10.0, zb - 4.0), 1.0)
        origins = [[0.0, ty_meas - 6.0, z + z_off] for z in z_scan]
        hits = _first_hit_dists(mesh, origins, [[0, 1, 0]] * len(origins))
        open_z = [z for z, d in zip(z_scan, hits)
                  if d is not None and (ty_meas - 6.0 + d) > ty_meas + 0.35]
        if len(open_z) >= 3:
            # 窓はステーション補間により t≈0.86 で閉じる → 開口実測長を逆補正
            est["window_length"] = (
                (float(open_z[-1]) + 0.5 - z_start) / 0.86,
                "下方レイ走査(÷開口率0.86)", 1.5)


    # バッフル高さ: 窓区間の空洞天井を実測し、天井式 ceil -= h_b·0.55·(1-t) を逆算
    stations = profiles.cavity_stations(p)
    window_ts = [0.12, 0.25, 0.40]
    st_by_t = {0.12: stations[1], 0.25: stations[2], 0.40: stations[3]}
    deltas = []
    for t in window_ts:
        s = st_by_t[t]
        o = [0.0, s["yc"], s["z"] + z_off]
        d = _first_hit_dists(mesh, [o], [[0, 1, 0]])[0]
        if d is None or d > 25.0:
            continue
        ceil_meas = s["yc"] + d
        ceil_analytic = s["yc"] + s["h"] / 2.0
        # 天井が analytic より Δ 低い → h_b が Δ/(0.55(1-t)) 大きい
        deltas.append((ceil_analytic - ceil_meas) / (0.55 * (1.0 - t)))
    if len(deltas) >= 2:
        hb_est = p["baffle_height"] + float(np.mean(deltas))
        est["baffle_height"] = (max(0.0, min(5.0, hb_est)), "空洞天井レイ(3断面)")
        if float(np.std(deltas)) > 0.6:
            warnings.append("バッフル形状が設計プロファイルと不整合です（断面間のばらつき大）。")

    # スロート断面積比: チェンバー入口断面の幅を実測
    s_c1 = stations[-3]  # チェンバー第1ステーション
    o = [0.0, s_c1["yc"], s_c1["z"] + z_off]
    dx = _first_hit_dists(mesh, [o, o], [[1, 0, 0], [-1, 0, 0]])
    if all(d is not None and d < rb * 2.5 for d in dx):
        r_t_meas = (dx[0] + dx[1]) / 2.1  # w = 2·r_t·1.05
        est["throat_ratio"] = ((r_t_meas / rb) ** 2, "チェンバー入口幅レイ")

    # ---- 判定表の構築
    rows = []
    for s in specs:
        if s.key in est:
            val, method, *rest = est[s.key]
            tol_meas = rest[0] if rest else 0.0  # 測定手法固有の公差
            frozen_v = float(p[s.key])
            delta = val - frozen_v
            step = s.step or 0.1
            tol_match = max(0.6 * step, 0.05, tol_meas)
            tol_minor = max(2.5 * step, 2.0 * tol_meas)
            if abs(delta) <= tol_match:
                verdict = "一致"
            elif abs(delta) <= tol_minor:
                verdict = "軽微"
            else:
                verdict = "乖離"
            rows.append({"key": s.key, "label": s.label, "unit": s.unit,
                         "frozen": round(frozen_v, 3), "estimated": round(val, 3),
                         "delta": round(delta, 3), "verdict": verdict,
                         "method": method})
        else:
            reason = UNMEASURABLE.get(s.key, "この形状からは測定できない")
            rows.append({"key": s.key, "label": s.label, "unit": s.unit,
                         "frozen": p.get(s.key), "estimated": None, "delta": None,
                         "verdict": "測定不能", "method": reason})

    # ---- 音響面違反の集約警告
    acoustic_keys = {"tip_opening", "facing_length", "window_length", "reed_width"}
    cavity_keys = {"baffle_height", "throat_ratio", "bore_dia"}
    div = {r["key"] for r in rows if r["verdict"] == "乖離"}
    if div & acoustic_keys:
        warnings.append(
            "⚠ リード密着面／ウィンドウの寸法が凍結時から変わっています。"
            "音響シミュレーション結果は無効です。パラメータで再設計してください。")
    if div & cavity_keys:
        warnings.append(
            "⚠ 内部空洞（バッフル/チェンバー/ボア）が変わっています。"
            "音程・音色はシミュレーション表示と乖離します。")
    return {"params": rows, "warnings": warnings}


def _all_unmeasurable(specs) -> list[dict]:
    return [{"key": s.key, "label": s.label, "unit": s.unit, "frozen": None,
             "estimated": None, "delta": None, "verdict": "測定不能",
             "method": "座標系不一致"} for s in specs]
