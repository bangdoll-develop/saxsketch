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
    "cork_depth": "組立条件であり形状に現れない。そもそも寸法ではなく"
                  "演奏者が抜き差しするチューニング量（acoustics.volume 参照）",
    "shoulder_ratio": "最大径の位置とシャンク平行部の開始の両方が要る。逆算は未実装"
                      "（実物ではシャンク端からの 2 点をノギスで測る）",
    # この 2 つは**原理的には解ける**（外形の母線を実測形と突き合わせて残差から
    # 1 パラメータを最小二乗すればよい）。実装していないだけなので、他の項目と
    # 同じ「一意復元できない」とは書かない。区別が消えると、後で誰かが
    # 「測れない量」だと思って諦める。
    "body_waist": "母線と実測プロファイルの残差から解けるが逆算は未実装。"
                  "領域偏差（胴）では変化を検出できる",
    "shoulder_fullness": "同上（肩の区間で解く）。逆算は未実装",
    "min_wall": "全面の肉厚走査は未対応",
    "material": "材料は形状に現れない",
}

#: `baffle_height` を逆に解くときの探索範囲 [mm]（スライダの可動域）。
_BAFFLE_RANGE = (0.0, 5.0)
#: この幅だけ天井が動かない z では baffle を解かない [mm]。
_BAFFLE_MIN_SPAN = 0.3


def _roof_above_face(p: dict, z: float, hb: float) -> float:
    """`baffle_height=hb` としたときの、**リード面から測った**空洞天井の高さ [mm]。"""
    q = dict(p, baffle_height=hb)
    return profiles.cavity_roof_y(q, z) - profiles.table_plane_y(q, z)


def _baffle_from_ceiling(p: dict, z: float, roof_above_face: float) -> float | None:
    """リード面から測った空洞天井の高さから `baffle_height` を解く（数値逆関数）。

    **絶対 Y ではなくリード面からの高さで解く**のが要点。`tip_opening` が凍結時から
    変わっていると（手編集の主目的のひとつ）テーブル平面ごと下がるので、絶対 Y で
    突き合わせると tip の変化ぶんがそのままバッフルの誤差として乗る。`baffle_height`
    の定義自体が「リード面からの高さ」なので、こちらが本来の突き合わせ方。

    天井は `baffle_height` に対して単調に下がるが**線形ではない**（ティップ側の
    soft-min と、天井が床に届いてからの頭打ち）。法則そのものを持っているので、
    割り算ではなく二分法で解く。線形補正だと 1.2mm の変化で 0.4mm ずれた。
    """
    lo, hi = _BAFFLE_RANGE
    if (_roof_above_face(p, z, lo) < roof_above_face
            or _roof_above_face(p, z, hi) > roof_above_face):
        return None            # 可動域では説明できない天井（形が法則から外れている）
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if _roof_above_face(p, z, mid) > roof_above_face:
            lo = mid           # まだ天井が高い ＝ もっと baffle を上げる
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _tip_from_rise(p: dict, z: np.ndarray, rise: np.ndarray) -> np.ndarray:
    """フェイシング面の持ち上がり量から `tip_opening` を逆に解く（`facing_rise` の逆関数）。

    旧実装は楕円カーブの係数 `1-√(1-t²)` で割っていたが、実測フィットで採用したのは
    **円弧(radial)** で、こちらは持ち上がりが `tip` に比例しない
    （半径 `R = (fl²+tip²)/(2·tip)` が `tip` に依存する）。比例と見なすと
    テナー既定で 12% ずれる。円弧は 2 段で厳密に反転できる:

        持ち上がり h と ティップからの距離 d=fl−z から  R = (h² + d²) / (2h)
        R から                                          tip = R − √(R² − fl²)
    """
    fl = p["facing_length"]
    ok = rise > 1e-3
    z, rise = z[ok], rise[ok]
    d = fl - z
    if p.get("facing_curve", "radial") == "elliptic":
        t = np.clip(d / fl, 0.0, 1.0)
        coef = 1.0 - np.sqrt(np.clip(1.0 - t * t, 1e-6, 1.0))
        return rise / np.maximum(coef, 0.30)
    r_arc = (rise * rise + d * d) / (2.0 * rise)
    good = r_arc > fl                    # R ≤ fl は円弧として成立しない（外れ点）
    r_arc = r_arc[good]
    return r_arc - np.sqrt(r_arc * r_arc - fl * fl)


#: 断面積比を逆に解くときの探索範囲（スライダの可動域を含む幅で取る）。
_RATIO_RANGE = (0.05, 4.0)


def _ratio_from_half_width(p: dict, key: str, z: float,
                           half_meas: float) -> float | None:
    """実測した空洞半幅から `throat_ratio` / `chamber_ratio` を解く（数値逆関数）。

    突き合わせ先は **ステーションの幅**（`cavity_stations`）であって
    `cavity_half_width` ではない。比は後者には入らず、`_ratio_scale` として
    ステーション組み立ての段で相似スケールとして掛かり、さらに外殻で clamp される。
    閉じた式を別に持つと前向きの法則を変えたときに黙って合わなくなるので、
    実際に造形される幅そのものを二分探索する。

    外殻で頭打ちの区間では単調性が消えるが、その場合は「説明できる最小の比」に
    収束する（呼び出し側が頭打ちを別途弾く）。
    """
    lo, hi = _RATIO_RANGE

    def w(r: float) -> float:
        q = dict(p, **{key: r})
        s = min(profiles.cavity_stations(q), key=lambda t: abs(t["z"] - z))
        return s["w"] / 2.0

    if w(lo) > half_meas or w(hi) < half_meas:
        return None
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if w(mid) < half_meas:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _measure_half_width(mesh: trimesh.Trimesh, station: dict, z_off: float,
                        limit: float) -> float | None:
    """ステーションの中心から ±X にレイを撃って空洞の半幅を実測する。"""
    o = [0.0, station["yc"], station["z"] + z_off]
    dx = _first_hit_dists(mesh, [o, o], [[1, 0, 0], [-1, 0, 0]])
    if not all(d is not None and d < limit for d in dx):
        return None
    return (dx[0] + dx[1]) / 2.0


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
    L = p["overall_length"]
    fl = p["facing_length"]
    # 凍結モデルのテーブル平面（傾斜平面）。`table_plane_y` はスカラー z しか取らない
    # ので、切片と傾きの 2 定数だけ取り出して配列演算に使う。
    ty0_frozen = profiles.table_plane_y(p, 0.0)
    slope_frozen = profiles.table_plane_y(p, 1.0) - ty0_frozen   # = -tan(傾斜)

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

    # ---- テーブル平面（以降すべての基準）。**傾斜平面なので直線フィット** y = a + b·z。
    #
    # 実物のテーブルはボア軸に対し 4.18° 傾いており、アルトでは z=40 の −10.13 から
    # z=70 の −12.32 まで 2.2mm 落ちる。これを中央値 1 点で代表すると、この面を基準に
    # する推定（ティップ開き・ビーク高さ・窓長）が**すべて同じ量だけずれる**。
    # 実際ティップ開きは「面より上の点を除く」フィルタが効きすぎて推定不能になっていた。
    bottom = (normals[:, 1] < -0.9) & (pts[:, 2] < profiles.table_cut_end_z(p) - 2.0)
    flat = bottom & (pts[:, 2] > fl * 1.15) \
        & (np.abs(pts[:, 1] - (ty0_frozen + slope_frozen * pts[:, 2])) < 1.5)
    if flat.sum() < 100:
        warnings.append("テーブル平面を検出できませんでした。フェイシング系の逆算を省略します。")
        table_fit = None

        def ty(z):
            raise RuntimeError("テーブル平面が未検出")
    else:
        b_fit, a_fit = np.polyfit(pts[flat, 2], pts[flat, 1], 1)
        table_fit = (float(a_fit), float(b_fit))

        def ty(z):
            """実測テーブル平面の Y。スカラーでも配列でも引ける。"""
            return table_fit[0] + table_fit[1] * z

        # 傾きがそのままテーブル傾斜。`table_plane_y = y0 - tan(角度)·z` なので符号は反転。
        est["table_angle"] = (math.degrees(math.atan(-table_fit[1])),
                              "テーブル平面の直線フィット")

    # ---- ティップ開き（ティップレール面 z < z_start のみが確実に露出する。
    #      窓区間の底面は空洞で開いているため使えない。fl は凍結値で固定し、
    #      各サンプル点の「含意ティップ値」の下側パーセンタイルを採る。
    #      面より上の点は含意値が大きく出るので下側が面の真値。）
    if table_fit is not None:
        z_rail_end = profiles.window_front_z(p)   # 窓の前縁 = レール面の終端
        # レール面はカーブで傾くため法線フィルタは緩め、上方の点は含意値の上位に逃がす。
        # 上限は **その z のテーブル平面** から測る。単一の Y だと先端側のレール面
        # （テーブルよりティップ開きぶん高い）が丸ごと落ちて推定不能になっていた。
        fz = (normals[:, 1] < -0.6) & (pts[:, 2] < z_rail_end) \
            & (pts[:, 2] > 0.05) & (pts[:, 1] < ty(pts[:, 2]) + 5.0)
        if fz.sum() >= 30:
            zz, yy = pts[fz, 2], pts[fz, 1]
            implied = _tip_from_rise(p, zz, yy - ty(zz))
            if implied.size >= 30:
                est["tip_opening"] = (float(np.percentile(implied, 4.0)),
                                      "ティップレール面(凍結fl仮定)", 0.10)

    # ---- ビーク高さ（各 z ビンの上端 p95 ＝ビーク斜面。側面フランクの混入を排除し、
    #      勾配によるビン内バイアスは評価点シフト +0.95·幅 で補正して直線回帰）
    if table_fit is not None:
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
                # `beak_height` はバイトポイントでの**テーブル面からの**高さ。
                # 基準はその z のテーブル平面（0.25·L のところ）。
                z_bite = 0.25 * L
                est["beak_height"] = (float(a * z_bite + b) - float(ty(z_bite)),
                                      "ビーク斜面p95回帰")

    # ---- ボディ径（リガチャー座の最大半径。彫刻は径を減らす方向なので上位percentile）
    #      測定帯は座の範囲から取る（外形プロファイルの比率を二重に持たない）。
    #      座は最大径の位置ではない（実測の胴は踵へ向かって単調に太る）ので、測定帯の
    #      後端での外形比で割り戻さないと body_dia が 0.26mm 小さく出て、未編集でも
    #      「乖離」になる。
    seat0, seat1 = profiles.ligature_seat_range(p)
    mid = (pts[:, 2] > seat0 + 2.0) & (pts[:, 2] < seat1 - 2.0)
    if mid.sum() >= 100:
        zz = pts[mid, 2]
        r = np.hypot(pts[mid, 0], pts[mid, 1])
        # 各点を **その z の解析外形半径** で割ってから percentile を取る。生の半径だと
        # 帯の中で解析値自体が 0.55mm 変わるので、percentile が「どの z を見たか」に
        # 依存してしまう（座は最大径の位置ではない）。比にすれば z が割れて、残るのは
        # 「凍結形状からの倍率」だけになる。テーブルカット面の点は比が小さいので
        # 上側 percentile から自然に外れ、彫刻も同じく径を減らす方向で外れる。
        r_ref = np.array([profiles.outer_radius(p, float(z)) for z in zz])
        scale = float(np.percentile(r / r_ref, 99.5))
        est["body_dia"] = (scale * p["body_dia"], "座での外形比の上側percentile")

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

    if table_fit is not None:
        # ウィンドウ長(実効): 下方から +Y レイを z 走査し「窓が開いている」範囲を測る。
        # 閉じている z ではカット面(≈ty(z))にヒット、開いている z では空洞天井
        # (≥ty(z)+0.4、クランプ時でも)にヒットする → しきい値 ty(z)+0.35。
        # **走査 30mm でテーブルが 2mm 以上落ちる**ので、しきい値も原点も z ごとに引く。
        # ティップレール面はカーブで持ち上がり誤判定するため窓の前縁より後方から走査。
        z_start = profiles.window_front_z(p)
        z_scan = np.arange(z_start + 0.5,
                           min(z_start + p["window_length"] + 10.0, zb - 4.0), 1.0)
        y_scan = ty(z_scan)
        origins = [[0.0, y0 - 6.0, z + z_off] for z, y0 in zip(z_scan, y_scan)]
        hits = _first_hit_dists(mesh, origins, [[0, 1, 0]] * len(origins))
        open_z = [z for z, y0, d in zip(z_scan, y_scan, hits)
                  if d is not None and (y0 - 6.0 + d) > y0 + 0.35]
        if len(open_z) >= 3:
            # 窓は床 F(z) がリード面を横切る所で閉じ、それが定義上ちょうど
            # `window_end_z` になる。旧実装はステーション補間の都合で 86% で
            # 閉じていたため ÷0.86 の補正が要ったが、いまは補正なしで一致する。
            est["window_length"] = (float(open_z[-1]) + 0.5 - z_start,
                                    "下方レイ走査", 1.5)

    # バッフル高さ: 窓が開いている z で空洞天井を実測し、天井式から逆算する。
    #
    # レイは**必ずソリッドの外（リード面より下）から**撃つ。旧実装は「凍結形状の空洞
    # 中心から +Y」で撃っていたが、編集で天井が下がるとその原点が材料の中に入り、
    # 当たらない（＝推定不能）か別の面を拾って桁違いの値を返していた。
    #
    # 逆算は `_baffle_from_ceiling`（天井式の数値逆関数）。ハンドメイドの重み関数で
    # 割ると天井の法則を変えたときに黙って合わなくなるうえ、そもそも非線形なので
    # 1.2mm の変化で 0.4mm ずれていた。
    if table_fit is not None:
        z_open = profiles.window_open_z(p)
        z_we = profiles.window_end_z(p)
        hbs = []
        for frac in (0.15, 0.30, 0.45):
            z_want = z_open + frac * (z_we - z_open)
            span = (_roof_above_face(p, z_want, _BAFFLE_RANGE[0])
                    - _roof_above_face(p, z_want, _BAFFLE_RANGE[1]))
            if span < _BAFFLE_MIN_SPAN:  # 天井がほぼボアに達していて baffle が効かない z
                continue
            face = float(ty(z_want))
            y0 = face - 6.0
            d = _first_hit_dists(mesh, [[0.0, y0, z_want + z_off]], [[0, 1, 0]])[0]
            if d is None or d > 25.0:
                continue
            ceil_meas = y0 + d
            if ceil_meas < face + 0.35:   # 窓が閉じていて床を拾った
                continue
            hb = _baffle_from_ceiling(p, z_want, ceil_meas - face)
            if hb is not None:
                hbs.append(hb)
        if len(hbs) >= 2:
            est["baffle_height"] = (float(np.mean(hbs)), "空洞天井レイ(3断面)")
            if float(np.std(hbs)) > 0.6:
                warnings.append("バッフル形状が設計プロファイルと不整合です（断面間のばらつき大）。")

    # スロート / チェンバーの断面積比: 空洞の半幅を実測し、**前向きの法則
    # (`profiles.cavity_half_width`) を数値で逆に解く**。
    #
    # 以前は縦横比 `_CHAMBER_W/_CHAMBER_H` とスーパー楕円指数を仮定した閉じた式で
    # 面積比を組み立てていたが、実測から起こした断面はその族ではない。同じ量に
    # 定義が二つある状態で、**未編集のメッシュでもチェンバー比 0.90〜0.94（＝軽微）**
    # と出ていた。法則を一つにすれば未編集は必ず 1.00 に戻る。
    stations = profiles.cavity_stations(p)
    s_th = profiles.stations_by_role(stations, "throat")[0]
    hw_th = _measure_half_width(mesh, s_th, z_off, rb * 2.5)
    tr = None if hw_th is None else _ratio_from_half_width(
        p, "throat_ratio", s_th["z"], hw_th)
    if tr is not None:
        est["throat_ratio"] = (tr, "スロート幅レイ")

    # チェンバー拡大比。比が効くのは**重みのピーク**（窓の終端とスロートの中間）で、
    # 「断面積が最大のステーション」ではない（比 1.0 では実物どおり単調に開くので、
    # 面積最大はスロート境界に来てしまい、そこでは chamber_ratio が効かない）。
    # 肉厚制限で頭打ちのときは形が比を反映していないので逆算不能（実測しても外殻の
    # 内寸が返るだけ）。黙って小さい値を返さず、測れないと言う。判定は**測った
    # その断面が clamp されているか**で見る（以前の「チェンバー断面が全部接している
    # か」という全称判定は実測形状では永久に成立しなかった）。
    z_ch = 0.5 * (profiles.window_end_z(p) + s_th["z"])
    s_ch = min(stations, key=lambda q: abs(q["z"] - z_ch))
    if profiles.chamber_clamped_at(p, s_ch["z"]):
        warnings.append("チェンバーが肉厚制限で頭打ちのため、断面積比は形状から逆算できません。")
    else:
        hw_ch = _measure_half_width(mesh, s_ch, z_off, rb * 3.0)
        # スロートを解いた値を先に入れてから解く（重みが重なる z で二重に数えない）
        base = p if tr is None else dict(p, throat_ratio=tr)
        cr = None if hw_ch is None else _ratio_from_half_width(
            base, "chamber_ratio", s_ch["z"], hw_ch)
        if cr is not None:
            est["chamber_ratio"] = (cr, "チェンバー幅レイ")

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
