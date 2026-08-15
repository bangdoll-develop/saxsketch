"""サクソフォン 管体の幾何（純数学・OCCT非依存）。

`neck_profiles.py` と同じ方針で、build123d に依存しない座標計算だけを持つ。
ソリッド生成は `body.py` 側が本モジュールの返す点列を使う。

座標系:
  - **弧長 s の原点は円錐のスロート**（＝ネックの小端＝マウスピースが載る側の管端）。
    部品がどこから始まるかは `part_start()` が返す。一体型は 0、別体はネックの弧長。
  - 曲げ（ボウ）は XZ 平面内。`neck_profiles` と同じ約束。
  - 断面リングは局所接線に直交する 2 軸 a(面内)・b=+Y(面外) で張る。

**ネックの幾何はここで書き直さない。** 一体型（`neck_joint == "integrated"`）の
ネック区間は `neck_profiles` の関数をそのまま呼び、リングも `neck_profiles.stations`
の同じ列に置く。ネックのパラメータは `REQUIRES_REF = "neck"` の参照スナップショット
から来る（`body.py` が渡す）ので、body 側に `neck_*` を再掲していない。同じ量が
2 か所にあると必ず食い違う。

**「ボア」が 2 つある。** 音響から見た気柱（`bore_radius_at`）と、実際に削れて
いる内面（`wall_inner_radius_at`）は別物。別体のソケット区間ではネックの
スピゴットが内側に入るので、内面はスピゴットを受けるぶん広いが、気柱は
ネックのボアのまま連続している。混ぜると音響が受け口のぶん太くなる。

**円錐の傾きは `volume.missing_cone` と同じ値を使う**（`neck_profiles` は
`cone_half_angle_deg` の生値を使っており、アルトだけ 4.52% 食い違う ——
アルトには頂点距離の実測 217.5 があって `missing_cone` はそちらを優先するため）。
管体が Tier1 と違う円錐を持つと別の楽器になるので、こちらを採る。一体型では
ネック区間のテーパを本体の円錐に合わせて張り直す（`_fused_neck`）ので継ぎ目に
折れは出ない。食い違いそのものは `body.py` の接続カードが数字で出す。
"""
from __future__ import annotations

import math

from saxsketch.acoustics import volume as ac_volume

from . import neck_profiles as npf

_RING_N = 48            # 断面リングの点数（全リング一定＝ロフト堅牢性）
#: ステーション間隔 [mm]。直管は円錐なので粗くてよい（母線が直線なので 2 リングで厳密）。
#: 曲げとベルだけ細かくする。
#:
#: **刻みを詰めても速くならない。** 測ると、時間の 75% はロフトではなく**差分
#: ブーリアン**が食っている（アルトでロフト 1.2s ×2 に対し差分 8.2s）。
#: リングの点数を 48→24 に落としても 8.2→5.7s にしかならない。
#: 4/3mm → 6/5mm はリングを 102→70 枚に減らして 9.50→7.85s になり、
#: 体積の変化は 256.3→256.2cc（0.04%）なので**ここは採った**。
#: 8/6mm（59 枚・7.05s）は伸びが小さい割にベルの曲率が粗くなるので採らない。
_STEP_STRAIGHT_MM = 40.0
_STEP_BOW_MM = 6.0
_STEP_BELL_MM = 5.0


# --------------------------------------------------------------------------- 円錐

def cone_tan(si: dict) -> float:
    """本体円錐の tanθ。`volume.missing_cone` と**同じ値**を使う。"""
    return ac_volume.missing_cone(si)["tan_theta"]


def neck_cone_tan(si: dict) -> float:
    """`neck_profiles` が使っている tanθ。比較して食い違いを出すためだけの値。"""
    return math.tan(math.radians(si["cone_half_angle_deg"]))


def throat_radius(si: dict) -> float:
    """円錐スロート（ネック小端）のボア半径 [mm]。"""
    return si["neck_bore_id_mm"] / 2.0


def is_integrated(p: dict) -> bool:
    return p["neck_joint"] == "integrated"


def part_start(p: dict, np_: dict) -> float:
    """この部品の始端が、スロートから弧長で何 mm 下流か [mm]。"""
    return 0.0 if is_integrated(p) else float(np_["neck_length"])


def part_end(p: dict, np_: dict) -> float:
    """この部品の終端（ベル出口）の、スロートからの弧長 [mm]。

    **一体型でも別体でも同じ**。だから音響から見た管も同じになる。
    """
    return float(np_["neck_length"]) + float(p["body_arc_length"])


def part_arc(p: dict, np_: dict) -> float:
    """この部品自身の弧長 [mm]（印刷の分割数はこれで決まる）。"""
    return part_end(p, np_) - part_start(p, np_)


def _r_throat(p: dict, si: dict) -> float:
    if p["taper_from_cone"] == "on":
        return throat_radius(si)
    return p["bore_small_id"] / 2.0


def _tan(p: dict, si: dict, np_: dict) -> float:
    if p["taper_from_cone"] == "on":
        return cone_tan(si)
    return (p["bore_large_id"] / 2.0 - p["bore_small_id"] / 2.0) / part_end(p, np_)


def cone_radius_at(s: float, p: dict, si: dict, np_: dict) -> float:
    """スロートからの弧長 s における**円錐だけ**のボア半径 [mm]（フレアを含まない）。"""
    return _r_throat(p, si) + _tan(p, si, np_) * s


def cone_end_dia(p: dict, si: dict, np_: dict) -> float:
    """ベルのフレアが無かった場合の終端ボア内径 [mm]。"""
    return 2.0 * cone_radius_at(part_end(p, np_), p, si, np_)


# --------------------------------------------------------------------------- 一体型のネック区間

def _fused_neck(p: dict, si: dict, np_: dict) -> dict:
    """一体型でネック区間を作るための、張り直したネックパラメータ。

    3 点だけ差し替える。
      - テーパ: 本体の円錐にちょうど乗るよう大端径を与えて `taper_from_cone` を off に
        する。生の半頂角のままだとアルトで 4.52% 食い違い、継ぎ目に折れが出る。
      - 肉厚: 1 個の印刷部品なので本体側に揃える。別々だと外形に段差が出る。
      - 本体挿入部: 一体型に継手は無い。`neck_profiles.outer_radius_at` は
        `L - body_tenon_length` 以降を細くするので、**負値**を渡して区間ごと消す。
    """
    neck_len = float(np_["neck_length"])
    return dict(np_,
                taper_from_cone="off",
                bore_large_id=2.0 * cone_radius_at(neck_len, p, si, np_),
                wall_thickness=p["wall_thickness"],
                body_tenon_length=-1.0)


def neck_throat_gap_mm(np_: dict, si: dict) -> float:
    """参照ネックの小端ボアが、円錐スロートからどれだけずれているか [mm]。

    ここがずれていると、一体型でも別体でも円錐の先端側が食い違う。
    """
    return float(np_["bore_small_id"]) - 2.0 * throat_radius(si)


# --------------------------------------------------------------------------- ベル

def bell_rise(s: float, p: dict, si: dict, np_: dict) -> float:
    """ベル区間で**円錐に上乗せする**半径 [mm]。

    円錐を下限にして足す形にしてある。基点を「ベル始端の円錐半径」に置いて
    t**power で伸ばす形にすると、ベルが長く出口が小さい組合せで**円錐より細い
    区間**ができる（実物のベルは細らない）。K.0 の測定でその非単調が実際に出た。

    **このフレアは 3 サイズとも未実測。** べき乗も出口径も仮定で、実物照合は
    付いていない。だから 4-B.2a では音響へ接続しない（接続すると全閉の
    第1共鳴が +38〜+106 セント動く）。
    """
    L = part_end(p, np_)
    bl = float(p["bell_length"])
    if bl <= 0.0 or s <= L - bl:
        return 0.0
    t = min(1.0, (s - (L - bl)) / bl)
    rise = p["bell_exit_dia"] / 2.0 - cone_radius_at(L, p, si, np_)
    return max(rise, 0.0) * (t ** float(p["flare_power"]))


# --------------------------------------------------------------------------- 半径

def bore_radius_at(s: float, p: dict, si: dict, np_: dict) -> float:
    """**音響から見た**気柱の半径 [mm]（円錐＋ベルのフレア）。

    ソケットの受け口は含めない —— そこはネックのスピゴットが埋めていて、
    気柱はネックのボアのまま連続している。
    """
    return cone_radius_at(s, p, si, np_) + bell_rise(s, p, si, np_)


def socket_bore_radius(p: dict, si: dict, np_: dict) -> float:
    """別体のとき、ネックのスピゴットを受ける穴の半径 [mm]。"""
    spigot_r = npf.outer_radius_at(float(np_["neck_length"]), np_, si)
    return spigot_r + p["socket_clearance"]


def wall_inner_radius_at(s: float, p: dict, si: dict, np_: dict) -> float:
    """**実際に削れている内面**の半径 [mm]。"""
    if is_integrated(p):
        neck_len = float(np_["neck_length"])
        if s <= neck_len:
            return npf.bore_radius_at(s, _fused_neck(p, si, np_), si)
        return bore_radius_at(s, p, si, np_)
    r = bore_radius_at(s, p, si, np_)
    if s <= part_start(p, np_) + p["socket_length"]:
        return max(r, socket_bore_radius(p, si, np_))
    return r


def outer_radius_at(s: float, p: dict, si: dict, np_: dict) -> float:
    """外形半径 [mm]。一体型のネック区間はテノン（コルク座）を持つので委譲する。"""
    if is_integrated(p):
        neck_len = float(np_["neck_length"])
        if s <= neck_len:
            return npf.outer_radius_at(s, _fused_neck(p, si, np_), si)
    return wall_inner_radius_at(s, p, si, np_) + p["wall_thickness"]


# --------------------------------------------------------------------------- センターライン

def _bow(p: dict):
    """(straight_len, arc_len, Rb, ang_rad)。Rb=None ならストレート。

    弧長は**クランプしない**。収まらない組合せは `body.py` の `params_error` が
    弾く。黙って頭打ちにすると、スライダを動かしても形が変わらない死んだ帯が
    できる（Stage I の `window_length` がそれだった）。
    """
    ang = math.radians(p["bow_angle"])
    s0 = float(p["bow_start"])
    if p["bow_angle"] <= 0.0 or p["bow_radius"] <= 0.0:
        return s0, 0.0, None, 0.0
    return s0, p["bow_radius"] * ang, float(p["bow_radius"]), ang


def _local_centerline(s: float, p: dict):
    """**本体ローカル**の弧長 s（本体管の始端が 0）の (point, tangent, a)。"""
    s0, arc, Rb, ang = _bow(p)
    if Rb is None or s <= s0:
        return (0.0, 0.0, s), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)
    phi = min((s - s0) / Rb, ang)
    x = Rb - Rb * math.cos(phi)
    z = s0 + Rb * math.sin(phi)
    tangent = (math.sin(phi), 0.0, math.cos(phi))
    a = (math.cos(phi), 0.0, -math.sin(phi))
    if s > s0 + arc:                       # ボウの後の直管
        d = s - (s0 + arc)
        x += d * tangent[0]
        z += d * tangent[2]
    return (x, 0.0, z), tangent, a


def _compose(base, local):
    """ネック終端フレーム base の上に本体ローカル local を載せる。

    どちらの曲げも XZ 平面内で同じ約束なので、Y 軸まわりの回転＋平行移動で済む。
    """
    (bx, by, bz), (tx, _ty, tz), (ax, _ay, az) = base
    (lx, ly, lz), (ltx, _lty, ltz), (lax, _lay, laz) = local

    def rot(vx, vz):
        """local の +X を base の面内軸 a へ、local の +Z を base の接線 t へ。"""
        return (vx * ax + vz * tx, vx * az + vz * tz)

    px, pz = rot(lx, lz)
    ttx, ttz = rot(ltx, ltz)
    aax, aaz = rot(lax, laz)
    return ((bx + px, by + ly, bz + pz), (ttx, 0.0, ttz), (aax, 0.0, aaz))


def centerline_point(s: float, p: dict, np_: dict):
    """スロートからの弧長 s の (point(x,y,z), tangent(unit), in_plane_axis a(unit))。

    座標原点は**部品の始端**（一体型はスロート、別体はネックの大端）。
    """
    if is_integrated(p):
        neck_len = float(np_["neck_length"])
        if s <= neck_len:
            return npf.centerline_point(s, np_)
        return _compose(npf.centerline_point(neck_len, np_),
                        _local_centerline(s - neck_len, p))
    return _local_centerline(s - part_start(p, np_), p)


def _cab(s: float, p: dict, np_: dict):
    pt, _t, a = centerline_point(s, p, np_)
    return pt, a, (0.0, 1.0, 0.0)


def _ring(center, a, b, r: float, n: int = _RING_N):
    out = []
    for i in range(n):
        th = 2.0 * math.pi * i / n
        c, s = math.cos(th), math.sin(th)
        out.append((center[0] + r * (c * a[0] + s * b[0]),
                    center[1] + r * (c * a[1] + s * b[1]),
                    center[2] + r * (c * a[2] + s * b[2])))
    return out


# --------------------------------------------------------------------------- ステーション

def stations(p: dict, np_: dict) -> list[float]:
    """リングを置く弧長の列（スロート基準）。曲げとベルだけ細かい。"""
    s_lo = part_start(p, np_)
    s_hi = part_end(p, np_)
    body0 = float(np_["neck_length"])
    zs = {s_lo, s_hi, body0}

    def fill(a: float, b: float, step: float) -> None:
        a, b = max(a, s_lo), min(b, s_hi)
        if b <= a:
            return
        n = max(1, int(math.ceil((b - a) / step)))
        for i in range(n + 1):
            zs.add(a + (b - a) * i / n)

    if is_integrated(p):
        # ネック区間は**ネック自身と同じ列**に置く。別に刻むと同じはずの形が 2 通りできる。
        zs.update(npf.stations(np_))
        # テノン（コルク座）の肩を立てる。`npf.stations` は等間隔なので段差の位置を
        # 持っておらず、そのまま使うと肩が 1 区間ぶん寝る。ネック単体のストレート経路は
        # `npf._straight_zs` が同じ 2 点を足している（曲げ経路は足していない ——
        # ネック単体の曲げでは肩が寝たままで、そちらは管体の話ではないので直していない）。
        tl = float(np_["tenon_length"])
        for zb in (tl, tl + 1e-3):
            if 0.0 < zb < float(np_["neck_length"]):
                zs.add(zb)

    b_s0, b_arc, b_rb, _ang = _bow(p)
    bow_a = body0 + b_s0
    bow_b = bow_a + b_arc
    bell_a = s_hi - float(p["bell_length"])
    fill(body0, bow_a, _STEP_STRAIGHT_MM)
    if b_rb is not None:
        zs.update((bow_a, bow_b))
        fill(bow_a, bow_b, _STEP_BOW_MM)
    fill(bow_b, bell_a, _STEP_STRAIGHT_MM)
    if p["bell_length"] > 0.0:
        zs.add(bell_a)
        fill(bell_a, s_hi, _STEP_BELL_MM)
    if not is_integrated(p) and p["socket_length"] > 0.0:
        for sb in (s_lo + p["socket_length"], s_lo + p["socket_length"] + 1e-3):
            if s_lo < sb < s_hi:
                zs.add(sb)
    return sorted(z for z in zs if s_lo - 1e-9 <= z <= s_hi + 1e-9)


def outer_rings(p: dict, si: dict, np_: dict) -> list[list[tuple[float, float, float]]]:
    return [_ring(*_cab(s, p, np_), outer_radius_at(s, p, si, np_))
            for s in stations(p, np_)]


def bore_rings(p: dict, si: dict, np_: dict) -> list[list[tuple[float, float, float]]]:
    return [_ring(*_cab(s, p, np_), wall_inner_radius_at(s, p, si, np_))
            for s in stations(p, np_)]


# --------------------------------------------------------------------------- 音響

def acoustic_geometry(p: dict, si: dict, np_: dict) -> list[list[float]]:
    """スロートからベル出口までの気柱 [[x_m, r_m], ...]（弧長を直線に展開）。

    **一体型と別体で同じものを返す。** 継手はボアに段差を作らないので、音響から
    見た管は同じ。テストで固定してある。「一体型のほうが音が良い/悪い」とは
    言えない —— モデルは差を持たない。

    曲げの影響は入っていない（弧長近似）。折り位置を変えても弧長が同じなら
    ここは動かない。**4-B.2a ではこれを共鳴管へ接続しない**（ベルが未実測なので
    音程の記録値を未実測の仮定で動かすことになる）。
    """
    L = part_end(p, np_)
    bl = float(p["bell_length"])
    zs = {0.0, L}
    n = max(2, int(math.ceil((L - bl) / 10.0)))
    for i in range(n + 1):
        zs.add((L - bl) * i / n)
    if bl > 0.0:
        for i in range(41):
            zs.add(L - bl + bl * i / 40.0)
    return [[s / 1000.0, bore_radius_at(s, p, si, np_) / 1000.0]
            for s in sorted(z for z in zs if 0.0 <= z <= L)]


def layout_error(p: dict, si: dict, np_: dict) -> str | None:
    """管の並びが成立しないときに理由を返す（`body.py` の `params_error` が使う）。

    `ParamSpec` はパラメータを 1 本ずつしか見ないので、各自のレンジ内なのに
    組み合わせると成立しない値の組が作れる。**黙ってクランプしない** ——
    頭打ちにするとスライダを動かしても形が変わらない死んだ帯ができる
    （Stage I の `window_length` がそれだった）。
    """
    L = float(p["body_arc_length"])
    _s0, arc, rb, _ang = _bow(p)
    # ストレート（曲げ角 0）では `bow_start` は形に効かない。効かない値でベルを
    # 縛らないよう、ボウが無いときは 0 として扱う。
    used = (float(p["bow_start"]) + arc) if rb is not None else 0.0
    if rb is not None and used > L:
        return (f"ボウが本体管に収まりません: 曲げまでの直管 {p['bow_start']:.0f}mm ＋ "
                f"曲げの弧長 {arc:.0f}mm（半径 {p['bow_radius']:.0f} × {p['bow_angle']:.0f}°）"
                f"＝ {used:.0f}mm が本体管 {L:.0f}mm を超えています。"
                f"本体管を伸ばすか、曲げ半径・曲げ角・曲げ開始位置を下げてください。")
    if rb is not None:
        # **曲げ半径は管の外半径より大きくないと断面が内側で折り返す。**
        # Rb ≤ r_outer だと曲率中心が管の中に入り、リングが裏返って自己交差した
        # ロフトになる。OCCT はこれを噛むと返ってこず、**WSL の VM ごと落ちた**
        # （掃引で `bow_radius=min(15)` を踏むたびに再現した）。幾何として成立
        # しないので、作る前に弾く。
        s_bow = float(np_["neck_length"]) + float(p["bow_start"])
        r_out = max(outer_radius_at(s, p, si, np_)
                    for s in (s_bow, s_bow + 0.5 * arc, s_bow + arc))
        if p["bow_radius"] <= r_out * 1.05:
            return (f"ボウの曲率半径 {p['bow_radius']:.0f}mm が管の外半径 "
                    f"{r_out:.1f}mm 以下です。曲率中心が管の中に入るので断面が"
                    f"内側で折り返して自己交差します。半径を {r_out * 1.05:.0f}mm "
                    f"より大きくするか、肉厚・ボアを細くしてください。")
    bell = float(p["bell_length"])
    if bell > 0.0 and used + bell > L:
        return (f"ベルがボウと重なります: 曲げの終わり {used:.0f}mm ＋ ベル {bell:.0f}mm "
                f"＝ {used + bell:.0f}mm が本体管 {L:.0f}mm を超えています。"
                f"ベルを短くするか、本体管を伸ばしてください。")
    end_dia = cone_end_dia(p, si, np_)
    if bell > 0.0 and p["bell_exit_dia"] < end_dia - 1e-6:
        return (f"ベル出口が円錐の終端より細くなっています "
                f"（出口 φ{p['bell_exit_dia']:.1f} < 円錐終端 φ{end_dia:.1f}）。"
                f"実物のベルは細りません。出口径を φ{end_dia:.1f} 以上にしてください。")
    if not is_integrated(p):
        sock_r = socket_bore_radius(p, si, np_)
        if sock_r + p["min_wall"] > outer_radius_at(part_start(p, np_) + 1e-3, p, si, np_):
            return (f"ネック受けの肉厚が下限を割ります（受け穴 φ{2*sock_r:.1f} に対し "
                    f"外径が足りない）。肉厚を上げるか、はめあい隙間を詰めてください。")
    return _self_collision_error(p, si, np_)


def _self_collision_error(p: dict, si: dict, np_: dict) -> str | None:
    """折り返した管が自分自身に当たっていないか。

    180° のボウでは行きと帰りの脚が **2×曲率半径** しか離れない。ベルを大きく
    すると帰りの脚の管が行きの脚に食い込み、ロフトは通るのに**自己交差した
    ソリッド**になる（`is_valid` が False になる）。実機はベルを外側へ振って
    逃がしているが、モデルはベルを帰りの脚と同軸に置いているので当たる。

    曲げの中どうしは当たって見えて当たり前（円弧上の 2 点は近い）なので、
    **弧長でボウ 1 周ぶん以上離れた組だけ**を見る。
    """
    _s0, arc, rb, _ang = _bow(p)
    if rb is None or arc <= 0.0:
        return None
    ss = stations(p, np_)
    pts = [(centerline_point(s, p, np_)[0], outer_radius_at(s, p, si, np_)) for s in ss]
    worst = None
    for i, (pi, ri) in enumerate(pts):
        for j in range(i + 1, len(pts)):
            if ss[j] - ss[i] <= arc:
                continue
            pj, rj = pts[j]
            d = math.dist(pi, pj)
            gap = d - (ri + rj)
            if worst is None or gap < worst[0]:
                worst = (gap, ss[i], ss[j], d, ri + rj)
    if worst is not None and worst[0] < 0.0:
        _gap, sa, sb, d, need = worst
        return (f"折り返した管が自分に当たっています（弧長 {sa:.0f}mm と {sb:.0f}mm の"
                f"位置で軸間 {d:.0f}mm に対し外半径の和が {need:.0f}mm）。"
                f"ボウの曲率半径を大きくするか、ベルを小さくしてください。"
                f"180° のボウでは行きと帰りの脚が 2×曲率半径＝"
                f"{2 * p['bow_radius']:.0f}mm しか離れません。")
    return None


def cone_reach_mm(p: dict, np_: dict) -> float:
    """スロートからベル出口までの弧長 [mm]。

    **(B)「ネック省略」を検出する唯一の量。** ネックを外して詰めると円錐の
    先端側が消えてここが短くなる。アルトでネックの 220mm を落とすと
    円錐全長 1214.8 → 994.8mm で約 **+346 セント**（ほぼ短3度上）＝別の楽器。
    """
    return part_end(p, np_)


# --------------------------------------------------------------------------- 体積・領域・断面図

def body_volume_mm3(p: dict, si: dict, np_: dict) -> float:
    """管壁の材料体積 [mm^3]（弧長積分の近似）。"""
    s_lo, s_hi = part_start(p, np_), part_end(p, np_)
    n = 200
    ds = (s_hi - s_lo) / n
    vol = 0.0
    for i in range(n):
        s = s_lo + ds * (i + 0.5)
        ro = outer_radius_at(s, p, si, np_)
        ri = wall_inner_radius_at(s, p, si, np_)
        vol += math.pi * (ro * ro - ri * ri) * ds
    return vol


def param_regions(p: dict, np_: dict) -> dict:
    """パラメータ → 3Dハイライト用 z ゾーン（曲げ後の実 z で近似）。"""
    s_lo, s_hi = part_start(p, np_), part_end(p, np_)
    body0 = float(np_["neck_length"])
    b_s0, b_arc, b_rb, _ang = _bow(p)

    def z(s: float) -> float:
        return centerline_point(max(s_lo, min(s_hi, s)), p, np_)[0][2]

    z0, z1 = z(s_lo), z(s_hi)
    reg = {
        "body_arc_length": {"z0": z(body0), "z1": z1, "side": "all", "label": "本体管"},
        "wall_thickness": {"z0": z0, "z1": z1, "side": "all", "label": "肉厚"},
        "taper_from_cone": {"z0": z0, "z1": z1, "side": "all", "label": "テーパ"},
        "bore_small_id": {"z0": z0, "z1": z(body0), "side": "all", "label": "小端ボア"},
        "bore_large_id": {"z0": z(s_hi - 40.0), "z1": z1, "side": "all", "label": "大端ボア"},
        "neck_joint": {"z0": z0, "z1": z(body0), "side": "all", "label": "ネック接続"},
    }
    if p["bell_length"] > 0.0:
        bell = {"z0": z(s_hi - p["bell_length"]), "z1": z1, "side": "all", "label": "ベル"}
        reg["bell_length"] = bell
        reg["bell_exit_dia"] = dict(bell)
        reg["flare_power"] = dict(bell)
    if b_rb is not None:
        bow = {"z0": z(body0 + b_s0), "z1": z(body0 + b_s0 + b_arc),
               "side": "all", "label": "ボウ（曲げ）"}
        reg["bow_angle"] = bow
        reg["bow_radius"] = dict(bow)
        reg["bow_start"] = {"z0": z(body0), "z1": z(body0 + b_s0),
                            "side": "all", "label": "ボウまでの直管"}
    if not is_integrated(p):
        sock = {"z0": z0, "z1": z(s_lo + p["socket_length"]), "side": "all",
                "label": "ネック受け"}
        reg["socket_length"] = sock
        reg["socket_clearance"] = dict(sock)
    return reg


def side_profile_polylines(p: dict, si: dict, np_: dict) -> dict:
    """曲げ平面(XZ)での外形・ボア母線。座標は (z, x)（横長に読める向き）。"""
    ot, ob, it, ib = [], [], [], []
    for s in stations(p, np_):
        (cx, _cy, cz), _t, a = centerline_point(s, p, np_)
        ro = outer_radius_at(s, p, si, np_)
        ri = wall_inner_radius_at(s, p, si, np_)
        ot.append((cz + ro * a[2], cx + ro * a[0]))
        ob.append((cz - ro * a[2], cx - ro * a[0]))
        it.append((cz + ri * a[2], cx + ri * a[0]))
        ib.append((cz - ri * a[2], cx - ri * a[0]))
    return {"outer_top": ot, "outer_bot": ob, "bore_top": it, "bore_bot": ib}
