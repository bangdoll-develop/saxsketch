"""リガチャーの断面プロファイル（純数学・OCCT非依存）。

マウスピース外形（`profiles.outer_radius` / `profiles.table_plane_y` /
`profiles.ligature_seat_range`）を**そのまま参照**して内周を生成する。これが
「マウスピース外形との自動整合」の実体で、参照マウスピースのボディ径を変えれば
リガチャー内周が追従する。

座標系はマウスピースと共通:
  Z: 軸方向（マウスピース先端 z=0 基準）。Y: +Y がビーク側、-Y がテーブル側。

断面の形:
  上側（ビーク側）はマウスピース外形の円弧。テーブル面の高さから下は、
  **リードを収めるタブ**（幅=リード幅、深さ=リード厚）が円の外へ張り出す。
  アルト標準ではテーブル面 y=-11.8 に対し外形半径が 13.8mm なので、厚さ 2.8mm の
  リードの裏面（y=-14.6）は円の下端より外に出る。円を切り落とす D 形にすると
  リードが入らない。

**タブは弦幅で切り詰めない。** 実物ではリード幅＝テーブルの弦幅（テナー実測で
7.328 / 7.400mm ＝ 比 0.99）なので、「タブをテーブル面の弦に収める」規則にすると
3サイズとも必ず 0.02mm 足りずに「リードが入りません」を出す。タブは箱として
**円の外へ張り出してよい**（側面が円と交わる y でそのまま円弧へ繋げば自己交差しない）。
唯一の上限は外形半径そのもの。

**テーブルはボア軸に対し 4.18° 傾いている**（`profiles.table_plane_y`）。帯幅
18mm では前後で 1.3mm 落ちるので、断面ごとにその z のテーブル平面を引く。
単一の `table_y` を全長に使うと、後端でリードの裏面がタブの底を突き抜ける。

**リードの背面はカマボコ**（Phase 4-C.2 で入れたケーンの円弧）。平らな接触面は
中央の 1 本線でしか当たらない —— 実測の締め代は中央 0.15mm に対し、旧「2点レール」
の位置で 0.83〜1.04mm、全面プレートの端で 1.55〜1.88mm 離れていた。だから接触要素の
**頂点は `rp.cane_top` から起こす**（`contact_top_y`）。締め代は全 x で
`reed_clearance` に揃う。

**接触は別ソリッドではなく内周断面の凸**として持つ（`contact_bottom_pts`）。
材料は「外周ロフト − 内周ロフト」なので、空洞のタブ床を上へ凸にすればそれが
そのまま接触要素になる: 浮いたソリッドが生まれず、テーブルの傾斜にも自動で従い、
断面図にもそのまま出る。唯一の例外が逆締めの**橋**（`bridge_sections`）で、
これはスリットが接触面を割るため片側から張り出す構造部材として別に作る。

締結方式（`closure`）は 3 通り: `screw_beak`（ビーク側スリット＋ネジ）、
`screw_reed`（逆締め。スリットをリード側に置き、圧力プレートで橋渡しする）、
`elastic`（スリットもネジも無い一連リング）。
"""
from __future__ import annotations

import math

from . import profiles
from . import reed_profiles as rp


def seat_range(ref_p: dict, lig_p: dict) -> tuple[float, float]:
    """リガチャーが実際に載る z 範囲。**後端で止め、前へは伸ばす。**

    後端の壁は物理: `ligature_seat_range` の後端は胴の最大径（`heel_z`）で、
    そこから先は胴が細くなるので、頂点を跨いだ帯は掴めない。

    **前端は丸めない。** 座の長さは `_SEAT_LENGTH_RATIO = 0.23`（実測のリガチャー帯
    ≈18mm / heel 79mm、テナー 1 本由来）から作った**公称値**であって壁ではない。
    以前はここで帯を座へ丸め込んでいたので、幅を上げても z 範囲が動かず、
    **STL がビット一致して 3D が更新されなかった**（素のアルトは 16.5mm 以降が
    全部同じ形。閾値は参照マウスピースの `heel_z × 0.23` なので機体ごとに動く）。
    「典型的なリガチャーの幅」で座を定義しておいて、その座より広いリガチャーを
    禁じる ——**定義が循環していた**。

    `seat_offset` は後端に当たると飽和する（既定 3 サイズとも可動域 0〜15 のうち
    生きているのは 0〜0.17mm）。これは物理の壁なので消せない。**黙って飲まず、
    `effective_seat_offset` を適合カードに出す。**
    """
    seat0, seat1 = profiles.ligature_seat_range(ref_p)
    z1 = min(seat0 + lig_p["seat_offset"] + lig_p["band_width"], seat1)
    return z1 - lig_p["band_width"], z1


def effective_seat_offset(ref_p: dict, lig_p: dict) -> float:
    """座の前端から帯の前端までの**実際の**距離 [mm]。

    要求どおりなら `seat_offset` と一致する。後端で止まっているぶんだけ小さくなる。
    """
    seat0, _ = profiles.ligature_seat_range(ref_p)
    return seat_range(ref_p, lig_p)[0] - seat0


# ---------------------------------------------------------------- リード側の接触

#: 接触要素を置ける半幅の比（タブ半幅に対して）。旧「全面プレート」と同じ。
_CONTACT_SPAN = 0.92
#: 接触要素 1 個の幅の上限 [mm]（旧「2点レール」のリブ幅と同じ）。
_RAIL_W_MAX = 2.0
#: 線／点の山の丸み（サジッタ）[mm]。半径は `cane_radius` と同じ式 (a²+s²)/(2s) で
#: 出て 2.1mm 級 —— リード背面の円弧（13.8〜15.2mm）よりずっと小さいので、
#: **接触は必ず 1 本の線（点接触なら 1 点）**になる。
_RAIL_SAG = 0.25
#: 山の頂点から床までの最小の逃げ [mm]。`_RAIL_SAG` と同じにすると裾がちょうど
#: 床に着く。テンプレート既定の `clearance` も 0.25 なので**既定の床は動かない**。
_CONTACT_RELIEF = 0.25
#: 山の裾に必ず残す立ち上がり [mm]。0 にすると裾の点が床の点と重なって
#: ロフトが縮退する（既定は頂点−床がちょうど `_RAIL_SAG` になる）。
_MIN_SKIRT = 0.05
#: 山の円弧を刻む点数（奇数。両端と頂点を含む）。
_ARC_PTS = 5
#: 面接触でリード背面をなぞる点数。
_FACE_PTS = 10
#: 逆締めの橋と、反対側の床との隙間 [mm]。ここが 0 だと締め代が殺される。
_BRIDGE_GAP = 0.3
#: 橋を片側の床へ食い込ませる量 [mm]。面が接するだけのブーリアンを避ける。
_BRIDGE_MERGE = 0.05
#: 橋の下に残す床の最小厚 [mm]（`params_error` の判定に使う）。
_BRIDGE_MIN_FLOOR = 0.2


def contact_top_y(ref_p: dict, lig_p: dict, reed_p: dict,
                  x: float, z: float) -> float:
    """接触要素の頂点 Y ＝ リード背面（カマボコ）から締め代ぶん離れた高さ。

    `rp.cane_top(reed_p, 0) == heel_thickness` なので、x=0 では平らな接触面
    （旧 `reed_face_y`）と厳密に一致する。x が外へ行くほどリードは薄いので
    頂点は上がる —— これが「全 x で締め代を `reed_clearance` に揃える」の実体。
    """
    xc = min(abs(x), reed_p["heel_width"] / 2.0)
    return (profiles.table_plane_y(ref_p, z) - rp.cane_top(reed_p, xc)
            - lig_p["reed_clearance"])


def reed_face_y(ref_p: dict, lig_p: dict, reed_p: dict, z: float) -> float:
    """z でリードの**中央**を挟む面の Y 座標。タブ床の基準。

    テーブルが傾いている以上この面も傾く。呼び出し側は必ず z を渡すこと。

    式としては `contact_top_y(…, x=0, …)` と同じ量だが、そちらは
    `heel_thickness - R + sqrt(R²)` を通るので**丸めで 1〜2 ULP ずれる**
    （アルトで 7e-16）。床は接触を入れる前と 1 ビットも変わってはいけないので、
    ここは中央厚を直接引く。
    """
    return (profiles.table_plane_y(ref_p, z)
            - reed_p["heel_thickness"] - lig_p["reed_clearance"])


def contact_kind(lig_p: dict) -> str:
    return str(lig_p.get("contact_type", "none"))


def contact_n(lig_p: dict) -> int:
    """x 方向の接触要素の数。`none`/`face` は要素を持たない（0）。"""
    if contact_kind(lig_p) in ("none", "face"):
        return 0
    return max(1, int(lig_p.get("contact_count", 1)))


def contact_span(hw: float) -> float:
    """接触が届く端の x [mm]（タブ半幅の比）。面接触の幅そのもの。"""
    return _CONTACT_SPAN * hw


def contact_width(hw: float, n: int) -> float:
    """接触要素 1 個の幅 [mm]。隣と融合しない上限まで。"""
    if n <= 1:
        return min(_RAIL_W_MAX, hw * 0.4)
    pitch0 = 2.0 * _CONTACT_SPAN * hw / (n - 1)
    return min(_RAIL_W_MAX, hw * 0.4, pitch0 * 0.7)


def contact_xs(hw: float, n: int) -> list[float]:
    """接触要素の x 位置。**対称は式から恒等的に成り立つ**（判定で弾かない）。

    `xs[i] == -xs[n-1-i]` が n と hw だけの関数として決まるので、非対称な並びを
    作れる経路が存在しない。
    """
    if n <= 1:
        return [0.0]
    x_end = _CONTACT_SPAN * hw - contact_width(hw, n) / 2.0   # 端がタブから出ない
    pitch = 2.0 * x_end / (n - 1)
    return [(i - (n - 1) / 2.0) * pitch for i in range(n)]


def contact_rows(ref_p: dict, lig_p: dict) -> list[float]:
    """点接触の z 位置（帯の前後 2 か所）。線／面／なし では空。

    1 列だとリードが首を振るので 2 列にする。総接触数は 2n。
    """
    if contact_kind(lig_p) != "point":
        return []
    z0, z1 = seat_range(ref_p, lig_p)
    w = z1 - z0
    return [z0 + 0.25 * w, z0 + 0.75 * w]


def section_zs(ref_p: dict, lig_p: dict) -> list[float]:
    """内周断面を取る z。点接触のときだけ行の位置を足す（山を z 方向にも丸める）。"""
    z0, z1 = seat_range(ref_p, lig_p)
    return sorted([z0, (z0 + z1) / 2.0, z1] + contact_rows(ref_p, lig_p))


def _z_droop(ref_p: dict, lig_p: dict, z: float) -> float:
    """点接触の z 方向の落ち込み [mm]。行の位置で 0、その中間で `_RAIL_SAG`。

    ルールドロフトなので z 方向は区分直線 ＝ 行を頂点とするテントになり、
    リード背面（z 方向には平ら）と当たるのは**行の位置の 1 点だけ**になる。
    """
    rows = contact_rows(ref_p, lig_p)
    if not rows:
        return 0.0
    z0, z1 = seat_range(ref_p, lig_p)
    reach = (z1 - z0) / 4.0
    if reach <= 0.0:
        return 0.0
    return _RAIL_SAG * min(1.0, min(abs(z - r) for r in rows) / reach)


def contact_relief(lig_p: dict) -> float:
    """接触の頂点から床までの逃げ [mm]。接触が無ければ 0（床は従来どおり）。"""
    kind = contact_kind(lig_p)
    if kind == "none":
        return 0.0
    if kind == "point":
        return _CONTACT_RELIEF + _RAIL_SAG   # z 方向の丸みぶんも沈める
    return _CONTACT_RELIEF


def tab_floor_y(ref_p: dict, lig_p: dict, reed_p: dict, z: float) -> float:
    """タブ床（空洞の底）の Y。接触があるときは頂点から必ず逃がす。

    `clearance` が小さい／負（弾性バンド）でも床は頂点より下に留まる ——
    さもないと線／点が「押されない凹み」になる。既定は `clearance` 0.25 ＝
    `_CONTACT_RELIEF` なので**床は 1 ビットも動かない**。
    """
    face = reed_face_y(ref_p, lig_p, reed_p, z)
    floor = face - lig_p["clearance"]
    relief = contact_relief(lig_p)
    return min(floor, face - relief) if relief > 0.0 else floor


def tab_outer_y(ref_p: dict, lig_p: dict, reed_p: dict, z: float) -> float:
    """タブ外面（リード側の一番外）の Y。耳とスリットの基準。"""
    return (reed_face_y(ref_p, lig_p, reed_p, z)
            - lig_p["clearance"] - lig_p["band_thickness"])


def contact_bottom_pts(ref_p: dict, lig_p: dict, reed_p: dict,
                       hw: float, z: float) -> list[tuple[float, float]]:
    """タブ床の折れ線のうち**両端の角を除いた内側の点**（x 昇順）。

    要素は「床から立ち上がる裾 → サジッタ `_RAIL_SAG` の円弧 → 裾」の 7 点。
    `face` はリード背面をそのままなぞる（丸めない）ので、名前どおり面で当たる。
    """
    kind = contact_kind(lig_p)
    if kind == "none":
        return []
    floor = tab_floor_y(ref_p, lig_p, reed_p, z)
    span = contact_span(hw)
    if kind == "face":
        pts = [(-span, floor)]
        for i in range(_FACE_PTS):
            x = -span + 2.0 * span * i / (_FACE_PTS - 1)
            pts.append((x, contact_top_y(ref_p, lig_p, reed_p, x, z)))
        pts.append((span, floor))
        return pts

    n = contact_n(lig_p)
    a = contact_width(hw, n) / 2.0
    droop = _z_droop(ref_p, lig_p, z)
    out: list[tuple[float, float]] = []
    for xc in contact_xs(hw, n):
        crest = contact_top_y(ref_p, lig_p, reed_p, xc, z) - droop
        sag = min(_RAIL_SAG, max(crest - floor - _MIN_SKIRT, 0.0))
        r = (a * a + sag * sag) / (2.0 * sag) if sag > 0.0 else 0.0
        out.append((xc - a, floor))
        for i in range(_ARC_PTS):
            u = -1.0 + 2.0 * i / (_ARC_PTS - 1)
            dy = r - math.sqrt(max(r * r - (a * u) ** 2, 0.0)) if r > 0.0 else 0.0
            out.append((xc + a * u, crest - dy))
        out.append((xc + a, floor))
    return out


def bridge_thickness(lig_p: dict) -> float:
    """逆締めの橋の厚み [mm]。印刷の最小肉厚そのもの。"""
    return float(lig_p["min_wall"])


def bridge_floor_error(lig_p: dict) -> str | None:
    """橋の逃げがバンド厚に収まらない組を説明つきで弾く。"""
    need = (bridge_thickness(lig_p) + _BRIDGE_MERGE + _BRIDGE_GAP
            + _BRIDGE_MIN_FLOOR)
    if lig_p["band_thickness"] < need:
        return (f"逆締めの橋（厚み {bridge_thickness(lig_p):.1f}mm）と逃げ "
                f"{_BRIDGE_GAP:.1f}mm がバンド厚に収まりません（必要 "
                f"{need:.2f}mm 以上 / いま {lig_p['band_thickness']:.1f}mm）。"
                f"バンド厚を上げるか最小肉厚を下げてください。")
    return None


def bridge_residual_floor(lig_p: dict) -> float:
    """橋の下に残る床の厚み [mm]（締結カードに出す）。"""
    return (lig_p["band_thickness"] - bridge_thickness(lig_p)
            - _BRIDGE_MERGE - _BRIDGE_GAP)


def _shelf_y(radius: float, table_y: float) -> float:
    """テーブル面の棚の Y。円と必ず交わるようにクランプする。"""
    return max(min(table_y, radius - 0.5), -(radius - 0.5))


def _shelf_half_width(radius: float, table_y: float) -> float:
    """テーブル面での弦の半幅（円と y=テーブル の交点の x）。"""
    yt = _shelf_y(radius, table_y)
    return math.sqrt(max(radius * radius - yt * yt, 0.0))


#: タブ側面と外形の間に残す肉 [mm]。タブ半幅の唯一の上限。
_TAB_EDGE_MARGIN = 0.2


def _clamp_tab_hw(radius: float, tab_hw: float) -> float:
    """要求タブ半幅を**外形半径**に収まる範囲へ制限する。

    以前はテーブル面の弦半幅で切り詰めていたが、タブは円の外へ張り出す箱なので
    弦は上限ではない（上限は外形半径そのもの）。断面生成と適合判定の唯一の出所。
    """
    return min(tab_hw, radius - _TAB_EDGE_MARGIN)


def _wrap_section(radius: float, table_y: float, hw: float,
                  bottom: list[tuple[float, float]],
                  samples: int = 72) -> list[tuple[float, float]]:
    """円弧（上側）＋リードのタブ（下側）の断面。反時計回り。

    順序を誤ると自己交差してロフトが破綻するため、向きを固定する:
    タブ底の折れ線を +x 方向 → 右の立ち上がり → （棚）→ 上側の円弧 →
    左の（棚と）立ち下がり。

    `bottom` はタブ床の折れ線（左端 `(-hw, …)` から右端 `(hw, …)` へ x 昇順）。
    接触の凸も逆締めの逃げ段もここに入るので、**タブ床の形はこの関数の外で決まる**。

    タブがテーブル面の弦より狭ければ棚（テーブル面の水平部）が出る。広ければ棚は
    無く、タブ側面 `x = ±hw` が円と交わる `y = -√(r²-hw²)`（テーブル面より上）で
    そのまま円弧へ繋ぐ。どちらも同じ式で書ける。
    """
    x_c = _shelf_half_width(radius, table_y)
    x_a = max(hw, x_c)                          # 円弧の開始 x
    y_a = -math.sqrt(max(radius * radius - x_a * x_a, 0.0))   # その x で円に乗る y
    shelf = x_a > hw + 1e-9                     # 棚が出るのはタブが弦より狭いときだけ
    pts = list(bottom) + [(hw, y_a)]
    if shelf:
        pts.append((x_a, y_a))
    th0 = math.atan2(y_a, x_a)          # 負の角度
    span = math.pi - 2.0 * th0          # 上側を回って (-x_a, y_a) まで
    # **棚の有無で頂点数を変えない。** 棚は弦とタブ幅の大小で決まるので、帯の中で
    # z によって現れたり消えたりする（弾性バンドの負の隙間 × 厚い帯で実際に起きる）。
    # ルールドロフトは断面ごとの頂点数が一致していることが前提なので、棚が無い側は
    # 円弧の刻みを 2 つ増やして帳尻を合わせる（円は同じなので位相がずれるだけ）。
    n = max(samples - 6, 12) + (0 if shelf else 2)
    for i in range(1, n):
        th = th0 + span * i / n
        pts.append((radius * math.cos(th), radius * math.sin(th)))
    if shelf:
        pts.append((-x_a, y_a))
    pts.append((-hw, y_a))
    return pts


def tab_bottom_pts(ref_p: dict, lig_p: dict, reed_p: dict, hw: float, z: float,
                   hw_c: float | None = None) -> list[tuple[float, float]]:
    """内周のタブ床（両端の角を含む折れ線）。

    角は**その z の**タブ半幅 `hw`、接触の配置は帯の中央の半幅 `hw_c`（z ごとに
    変えるとリブが軸方向に傾く）。

    逆締めでは接触を持たず、**橋を受ける逃げ段**になる: -x 側は橋の底とちょうど
    同じ高さ（融合する）、+x 側はさらに `_BRIDGE_GAP` 下げる（締め代を殺さない）。
    段差は x=0 ＝ スリットの中に置くので、切った後には見えない。
    """
    floor = tab_floor_y(ref_p, lig_p, reed_p, z)
    if str(lig_p.get("closure")) == "screw_reed":
        y_m = floor - bridge_thickness(lig_p)
        y_p = y_m - _BRIDGE_MERGE - _BRIDGE_GAP
        return [(-hw, y_m), (0.0, y_m), (0.0, y_p), (hw, y_p)]
    return ([(-hw, floor)]
            + contact_bottom_pts(ref_p, lig_p, reed_p,
                                 hw if hw_c is None else min(hw, hw_c), z)
            + [(hw, floor)])


def _tab_hw(ref_p: dict, lig_p: dict, radius: float, offset: float) -> float:
    return _clamp_tab_hw(radius, ref_p["reed_width"] / 2.0 + offset)


def inner_sections(ref_p: dict, lig_p: dict, reed_p: dict) -> list[dict]:
    """内周（空洞）の断面列。**接触要素はここの凸として入る**。

    テーブル面の基準はマウスピース モデルの `table_plane_y(z)`。**断面ごとに引く**。
    傾斜 4.18° は帯幅 18mm で 1.3mm 落ちるので、1点で代表するとリードの裏面が
    後端でタブの底を突き抜ける。ルールドロフトなので、傾いた平面はそのまま
    平面として出る（近似誤差なし）。
    """
    offset = lig_p["clearance"]
    hw_mid = flat_half_width(ref_p, lig_p)
    out = []
    for z in section_zs(ref_p, lig_p):
        radius = profiles.outer_radius(ref_p, z) + offset
        hw = _tab_hw(ref_p, lig_p, radius, offset)
        out.append({"z": z,
                    "pts": _wrap_section(
                        radius, profiles.table_plane_y(ref_p, z), hw,
                        tab_bottom_pts(ref_p, lig_p, reed_p, hw, z, hw_mid))})
    return out


def outer_sections(ref_p: dict, lig_p: dict, reed_p: dict) -> list[dict]:
    """外周の断面列。接触は内周側の凸なので、外周は常に平らな底のまま。"""
    offset = lig_p["clearance"] + lig_p["band_thickness"]
    z0, z1 = seat_range(ref_p, lig_p)
    out = []
    for z in (z0, (z0 + z1) / 2.0, z1):
        radius = profiles.outer_radius(ref_p, z) + offset
        hw = _tab_hw(ref_p, lig_p, radius, offset)
        y = reed_face_y(ref_p, lig_p, reed_p, z) - offset
        out.append({"z": z,
                    "pts": _wrap_section(radius, profiles.table_plane_y(ref_p, z),
                                         hw, [(-hw, y), (hw, y)])})
    return out


def bridge_sections(ref_p: dict, lig_p: dict, reed_p: dict) -> list[dict]:
    """逆締めの橋（圧力プレート）の断面列。底は平ら、上は接触プロファイル。

    -x 側の床へ `_BRIDGE_MERGE` だけ食い込ませて融合させ、+x 側とは
    `_BRIDGE_GAP` 空ける ＝ 片側の耳から張り出して反対側に重なる片持ち。
    """
    offset = lig_p["clearance"]
    hw_mid = flat_half_width(ref_p, lig_p)
    out = []
    for z in section_zs(ref_p, lig_p):
        radius = profiles.outer_radius(ref_p, z) + offset
        hw = min(_tab_hw(ref_p, lig_p, radius, offset), hw_mid)
        floor = tab_floor_y(ref_p, lig_p, reed_p, z)
        top = ([(-hw, floor)]
               + contact_bottom_pts(ref_p, lig_p, reed_p, hw, z)
               + [(hw, floor)])
        y_bot = floor - bridge_thickness(lig_p) - _BRIDGE_MERGE
        out.append({"z": z, "pts": [(-hw, y_bot), (hw, y_bot)] + top[::-1]})
    return out


def inner_radius(ref_p: dict, lig_p: dict) -> float:
    """帯中央での内周半径（適合チェック・仕様書用）。"""
    z0, z1 = seat_range(ref_p, lig_p)
    return profiles.outer_radius(ref_p, (z0 + z1) / 2.0) + lig_p["clearance"]


def requested_tab_half_width(ref_p: dict, lig_p: dict) -> float:
    """リードを収めるのに必要なタブ半幅（クランプ前）。"""
    return ref_p["reed_width"] / 2.0 + lig_p["clearance"]


def flat_half_width(ref_p: dict, lig_p: dict) -> float:
    """リード接触面（タブ底面）の**実際の**半幅。接触要素の配置の基準。

    外形半径に収まらない要求幅は断面生成側で切り詰められる。ここで同じクランプを
    通しておかないと、接触がタブの外に置かれて側壁を突き抜ける。
    """
    return _clamp_tab_hw(inner_radius(ref_p, lig_p),
                         requested_tab_half_width(ref_p, lig_p))


# ---------------------------------------------------------------- ネジ・スリット

SCREW_SPECS = {          # (呼び径 mm, バカ穴径 mm, 頭部径 mm)
    "m2.5": (2.5, 2.8, 5.0),
    "m3": (3.0, 3.4, 6.0),
}
#: 市販の一般的な首下長さ [mm]（BOM でこの中から選ぶ）
STOCK_SCREW_LENGTHS = [6, 8, 10, 12, 16, 20]


def has_screws(lig_p: dict) -> bool:
    return str(lig_p.get("closure", "screw_beak")) != "elastic"


def screw_spec(lig_p: dict) -> tuple[float, float, float]:
    return SCREW_SPECS.get(lig_p.get("screw_size", "m3"), SCREW_SPECS["m3"])


def ear_thickness(lig_p: dict) -> float:
    """ネジ座（耳）の X 方向厚み。頭部径から必要な座面を確保する。"""
    _, _, head_d = screw_spec(lig_p)
    return max(lig_p["band_thickness"], head_d * 0.5)


def screw_zs(ref_p: dict, lig_p: dict) -> list[float]:
    """ネジ軸の z 位置。2本なら帯幅を3等分した位置に置く。"""
    z0, z1 = seat_range(ref_p, lig_p)
    n = int(lig_p["screw_count"])
    if n <= 1:
        return [(z0 + z1) / 2.0]
    return [z0 + (z1 - z0) * (i + 1) / (n + 1) for i in range(n)]


#: ネジ穴の上下に残す肉厚 [mm]
SCREW_WALL = 0.6


def min_boss_height(lig_p: dict) -> float:
    """ネジ穴が耳に収まるのに必要な耳の高さ [mm]。"""
    _, hole_d, _ = screw_spec(lig_p)
    return hole_d + 2.0 * SCREW_WALL


def ear_span(ref_p: dict, lig_p: dict,
             reed_p: dict | None = None) -> tuple[float, float]:
    """耳の（付け根, 頂点）の Y。逆締めでは下（リード側）へ伸びる。

    どちら向きでも「付け根から頂点へ `boss_height`」という関係は同じなので、
    ネジ軸のクランプはこの 2 点だけで書ける。
    """
    if str(lig_p.get("closure", "screw_beak")) == "screw_reed":
        if reed_p is None:
            raise ValueError("逆締めの耳はリード形状（reed_p）が要ります")
        z0, z1 = seat_range(ref_p, lig_p)
        base = tab_outer_y(ref_p, lig_p, reed_p, (z0 + z1) / 2.0)
        return base, base - lig_p["boss_height"]
    base = inner_radius(ref_p, lig_p) + lig_p["band_thickness"]
    return base, base + lig_p["boss_height"]


def screw_axis_y(ref_p: dict, lig_p: dict, reed_p: dict | None = None) -> float:
    """ネジ軸の Y 座標。耳の中ほどを狙いつつ、穴が耳から出ないようクランプする。

    中央固定（boss_height×0.5）だと耳が低いときに穴が上へ突き抜け、閉じた穴では
    なく上に開いたスロットになってネジが抜ける。
    """
    base, top = ear_span(ref_p, lig_p, reed_p)
    _, hole_d, _ = screw_spec(lig_p)
    margin = hole_d / 2.0 + SCREW_WALL
    lo, hi = min(base, top), max(base, top)
    if hi - lo < 2.0 * margin:         # 耳が低すぎる（カードが warn を出す）
        return (lo + hi) / 2.0
    mid = (base + top) / 2.0
    return min(max(mid, lo + margin), hi - margin)


def required_screw_length(lig_p: dict) -> float:
    """必要なネジ首下長さ [mm]。両側の耳とスリットを貫通する長さ。"""
    return lig_p["slit_width"] + 2.0 * ear_thickness(lig_p) + 1.0


def stock_screw_length(lig_p: dict) -> int:
    """必要長を満たす最小の市販長さ。"""
    need = required_screw_length(lig_p)
    for s in STOCK_SCREW_LENGTHS:
        if s >= need:
            return s
    return STOCK_SCREW_LENGTHS[-1]


# ---------------------------------------------------------------- 影響領域・断面図

def param_regions(ref_p: dict, lig_p: dict) -> dict:
    z0, z1 = seat_range(ref_p, lig_p)

    def r(side, label):
        return {"z0": round(z0, 2), "z1": round(z1, 2), "side": side, "label": label}

    band = r("all", "バンド（帯）")
    reed_side = r("bottom", "リード接触面")
    boss = r("bottom" if str(lig_p.get("closure")) == "screw_reed" else "top",
             "ネジ座（耳）")
    return {
        "band_width": band,
        "band_thickness": band,
        "seat_offset": band,
        "clearance": band,
        "reed_clearance": reed_side,
        "closure": boss,
        "screw_count": boss,
        "screw_size": boss,
        "boss_height": boss,
        "slit_width": r("top", "スリット（締め代）") if str(
            lig_p.get("closure")) != "screw_reed" else reed_side,
        "contact_type": reed_side,
        "contact_count": reed_side,
        "min_wall": band,
        # material は形状に影響しない → 領域なし
    }


def section_polylines(ref_p: dict, lig_p: dict, reed_p: dict) -> dict:
    """帯断面図（SVG描画用、単位mm）。軸方向ではなく XY 断面を描く。

    帯の**中央**の断面を描く。テーブルが傾いているので前後端では図の高さが変わる
    （中央を代表に採るのは、帯の内周径・ネジ座もそこを基準にしているのと同じ理由）。
    点接触は行の位置を代表に採る（中央だと山が落ちきった谷が出てしまう）。
    """
    z0, z1 = seat_range(ref_p, lig_p)
    rows = contact_rows(ref_p, lig_p)
    zm = rows[0] if rows else (z0 + z1) / 2.0
    inner = next(s for s in inner_sections(ref_p, lig_p, reed_p)
                 if abs(s["z"] - zm) < 1e-9)["pts"]
    outer = outer_sections(ref_p, lig_p, reed_p)[1]["pts"]
    out = {
        "inner": inner + [inner[0]],
        "outer": outer + [outer[0]],
        "reed_face_y": reed_face_y(ref_p, lig_p, reed_p, zm),
        "table_y": profiles.table_plane_y(ref_p, zm),
        "bridge": None,
    }
    if str(lig_p.get("closure")) == "screw_reed":
        b = next(s for s in bridge_sections(ref_p, lig_p, reed_p)
                 if abs(s["z"] - zm) < 1e-9)["pts"]
        out["bridge"] = b + [b[0]]
    return out
