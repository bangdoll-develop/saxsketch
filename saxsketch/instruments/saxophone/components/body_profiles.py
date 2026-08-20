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

**円錐の傾きは `volume.missing_cone` と同じ値を使う。** 管体が Tier1 と違う円錐を
持つと別の楽器になる。`neck_profiles.bore_large_id` も同じ関数を読むので、
**1 つの楽器に円錐は 1 本**（以前はネックだけ `cone_half_angle_deg` の生値を使っており、
頂点距離の値を持つアルトだけ 4.52% 食い違っていた）。
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
    """本体円錐の tanθ。`volume.missing_cone` と**同じ値**を使う。

    `neck_profiles.bore_large_id` も同じ値から大端径を出す（テストで固定してある）。
    """
    return ac_volume.missing_cone(si)["tan_theta"]


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
        する。傾き自体はネック側も同じ `missing_cone` を読むので今は一致するが、
        **ユーザーが小端ボアを動かすとずれる**（ネックは自分の小端から、本体は
        スロートから広げるため）。ここを固定しておかないと継ぎ目に折れが出る。
      - 肉厚: 1 個の印刷部品なので本体側に揃える。別々だと外形に段差が出る。
      - 本体挿入部: 一体型に継手は無い。`neck_profiles.outer_radius_at` は
        `L - body_tenon_length` 以降を細くするので、**負値**を渡して区間ごと消す。
        `neck_profiles.shoulder_zs` もこれを見るので、消えた段のステーションは
        置かれない（半径の同じリングが 1μm 間隔で 2 枚並ぶのを避ける）。
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

def stations(p: dict, si: dict, np_: dict) -> list[float]:
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
        # 渡すのは `_fused_neck` —— 半径を出すのに使っているのと同じパラメータでないと、
        # 一体型では消えている本体挿入部の肩にステーションが 2 枚置かれる（半径の同じ
        # リングが 1μm 間隔で並ぶ＝スライバ面のもと）。
        zs.update(npf.stations(_fused_neck(p, si, np_)))

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
            for s in stations(p, si, np_)]


def bore_rings(p: dict, si: dict, np_: dict) -> list[list[tuple[float, float, float]]]:
    return [_ring(*_cab(s, p, np_), wall_inner_radius_at(s, p, si, np_))
            for s in stations(p, si, np_)]


# --------------------------------------------------------------------------- 側孔

#: 指孔をふさげる指の実用上限 [mm]。これを超えると押さえきれない。判定は
#: `ParamSpec.max` ではなくカード（人差し指と小指で違うし、奏者で違う）。
FINGER_PAD_DIA_MM = 12.0
#: 両手で押さえられる指孔の実用スパン [mm]。**目安であって物理ではない。**
#: リコーダ（約 200mm）とクラリネット（7 孔で約 230mm）の実測から採った。
HAND_SPAN_MM = 200.0


def is_holed(p: dict) -> bool:
    return int(p["finger_holes"]) > 0 or p["thumb_vent"] == "on"


def _cone_length_for(si: dict, f_hz: float) -> float:
    """その周波数が鳴る円錐のスロート→開口長 [mm]（**0 次規則**）。

    `openwind_bridge._calibrate_extension` をそのまま使う。管体の円錐長を
    決めているのと**同じ関数**なので、円錐が 2 本になる経路が無い。
    サイズ・音速・エンジンごとに `lru_cache` されるので、7 本ぶんの追加費用は初回だけ。
    """
    from saxsketch.acoustics import openwind_bridge as ob

    cone = ac_volume.missing_cone(si)
    return 1000.0 * ob._calibrate_extension(
        float(f_hz), cone["apex_distance_mm"] / 1000.0, cone["tan_theta"],
        ob.C_SOUND, False)


def hole_chimney_mm(s: float, p: dict, si: dict, np_: dict) -> float:
    """側孔のチムニー長 [mm]。**ボア内面から天面まで**（壁の厚みを含む）。

    `hole_chimney` パラメータは外面からの立ち上がりで、音響のチムニー長では
    ない。ここを二重計上すると肉厚を動かしたときに音響が黙って置き去りになる。
    **形から測る**ので、テーパでも受け口でも自動で正しくなる。
    """
    return (outer_radius_at(s, p, si, np_) + float(p["hole_chimney"])
            - wall_inner_radius_at(s, p, si, np_))


def hole_layout(p: dict, si: dict, np_: dict) -> list[dict]:
    """側孔の並び（**弧長の昇順** ＝ マウスピース寄りが先頭）。

    **4-B.2b の位置は 0 次規則の暫定値**で、実測でも解でもない。穴 k の目標音
    `f_low·2^(step/12)` に対し「その音が鳴る円錐長」をそのまま弧長にしている。
    有限径の穴は完全な開口端ではないので、実際に解いた共鳴はここより**低く**出る。
    その差が 4-B.2c のソルバが潰す残差そのもの（`body.py` の音階カード）。

    親指孔の位置は**指孔の本数に依らない** —— オクターブ（+12 半音）の位置から
    `thumb_offset` だけ上流に置く。本数に紐づけると、本数 0 のときだけ穴が黙って
    消える（この repo が 6 回踏んだ「黙ったクランプ」の形）。

    各穴が `dia_mm` と `chimney_mm` を**個別に**持つのは 2c のため（2b では全穴同値）。
    """
    from saxsketch.acoustics import toneholes

    n = int(p["finger_holes"])
    f_low = float(si["low_note_sounding_hz"])
    out: list[dict] = []
    steps = toneholes.scale_steps(n)
    # ベル寄り（+2 半音）が最も長い。昇順にするので高い音から並べる
    for i, st in enumerate(reversed(steps)):
        f = f_low * 2.0 ** (st / 12.0)
        out.append({"label": f"hole{i + 1}", "role": "finger", "step": st,
                    "target_hz": f, "s_mm": _cone_length_for(si, f),
                    "dia_mm": float(p["hole_dia"]),
                    "chimney_mm": 0.0})
    if p["thumb_vent"] == "on":
        s_oct = _cone_length_for(si, f_low * 2.0) - float(p["thumb_offset"])
        out.append({"label": "thumb", "role": "thumb", "step": None,
                    "target_hz": None, "s_mm": s_oct,
                    "dia_mm": float(p["thumb_dia"]), "chimney_mm": 0.0})
    out.sort(key=lambda h: h["s_mm"])
    for h in out:
        h["chimney_mm"] = hole_chimney_mm(h["s_mm"], p, si, np_)
    return out


def acoustic_holes(p: dict, si: dict, np_: dict) -> list[dict]:
    """`hole_layout` を物差し円錐（`ideal_cone_geometry`）の座標へ写した穴リスト。

    管体は**理想マウスピース**で評価する（`REQUIRES_REF` は neck 1 段だけで、
    マウスピースのパラメータを持たない）。全閉の第1共鳴は校正により目標音に
    合うので、音階カードに残るのは**穴だけの寄与**になる。
    """
    from saxsketch.acoustics import openwind_bridge as ob

    return [{"label": h["label"], "role": h["role"],
             "x_m": ob.ideal_cone_hole_x(si, h["s_mm"]),
             "radius_m": h["dia_mm"] / 2000.0,
             "chimney_m": h["chimney_mm"] / 1000.0}
            for h in hole_layout(p, si, np_)]


def hole_placement(p: dict, si: dict, np_: dict) -> list[dict]:
    """CAD 用の配置（中心点・軸・外半径）。build123d 非依存の座標だけ。

    **指孔はボウの凸側（曲げの外）に揃える。** ストレートでも同じ規則を使うので、
    曲げ角を変えても穴の面が飛ばない（同じパラメータから 2 通りの形が出る経路を
    作らない）。親指孔はその反対側。

    `inner_r` / `outer_r` は中心線からのボア内面／外面の半径。**チムニーは
    `inner_r` から立ち上げる**（`body._apply_holes`）—— 外面に接する平面から
    立てると、管が曲面なので底の円盤が接点以外どこも管の外に浮き、融合が
    接触だけになる。掃引でボウの上の 2 本が実際に**ちぎれてソリッドが 3 個**に
    なった（アルト・チムニー 8mm）。`inner_r` から立てれば必ず肉の中で重なり、
    しかも `x ≥ inner_r` の円柱はボアへはみ出さない（軸から外れるほど中心線
    からの距離は伸びるため）。
    """
    out = []
    for h in hole_layout(p, si, np_):
        s = h["s_mm"]
        pt, _t, a = centerline_point(s, p, np_)
        sign = 1.0 if h["role"] == "thumb" else -1.0
        ri = wall_inner_radius_at(s, p, si, np_)
        ro = outer_radius_at(s, p, si, np_)
        ch = float(p["hole_chimney"])
        out.append({"label": h["label"], "role": h["role"], "center": pt,
                    "axis": (sign * a[0], sign * a[1], sign * a[2]),
                    "dia": h["dia_mm"], "chimney_height": ch,
                    "inner_r": ri, "outer_r": ro,
                    # チムニーの円柱は中心線から `chimney_base_r` の位置で始まり
                    # `chimney_len` だけ外へ伸びる。**始点は内面**（上の理由）。
                    "chimney_base_r": ri, "chimney_len": ro + ch - ri,
                    # 貫通穴は中心線から。反対側の壁には届かない長さに留める
                    "cut_len": ro + ch + 2.0})
    return out


def hole_layout_error(p: dict, si: dict, np_: dict) -> str | None:
    """側孔の並びが成立しないときに理由を返す（**黙ってクランプしない**）。"""
    if not is_holed(p):
        return None
    s_lo, s_hi = part_start(p, np_), part_end(p, np_)
    holes = hole_layout(p, si, np_)
    for h in holes:
        s = h["s_mm"]
        if not (s_lo < s < s_hi):
            where = "マウスピース側" if s <= s_lo else "ベル出口の先"
            return (f"側孔 {h['label']} が管の外（{where}、弧長 {s:.0f}mm）に出ます。"
                    f"この部品は弧長 {s_lo:.0f}〜{s_hi:.0f}mm です。"
                    f"本体管長を伸ばすか、指孔の本数を減らしてください。")
        r_bore = wall_inner_radius_at(s, p, si, np_)
        if h["dia_mm"] / 2.0 >= r_bore:
            return (f"側孔 {h['label']} の径 φ{h['dia_mm']:.1f} が、その位置のボア径 "
                    f"φ{2 * r_bore:.1f} 以上です。分岐の式（短いチムニー近似）が"
                    f"成り立たないうえ、管が輪切りになります。穴を細くするか、"
                    f"もっとベル寄りへ動かしてください。")
        if h["chimney_mm"] <= float(p["hole_chimney"]) + 1e-9:
            return (f"側孔 {h['label']} のチムニーが壁を貫いていません "
                    f"（{h['chimney_mm']:.2f}mm）。肉厚を確認してください。")
    for i in range(len(holes) - 1):
        a, b = holes[i], holes[i + 1]
        gap = (b["s_mm"] - a["s_mm"]) - (a["dia_mm"] + b["dia_mm"]) / 2.0
        if gap < 1.0:
            return (f"側孔 {a['label']} と {b['label']} が重なります"
                    f"（弧長 {a['s_mm']:.0f} と {b['s_mm']:.0f}、縁の隙間 {gap:.1f}mm）。"
                    f"穴を細くするか、親指孔のオフセットを広げてください。")
    return None


def hole_span_mm(p: dict, si: dict, np_: dict) -> float:
    """最上と最下の**指孔**の弧長差 [mm]。指が届くかはこれで決まる。"""
    fs = [h["s_mm"] for h in hole_layout(p, si, np_) if h["role"] == "finger"]
    return (max(fs) - min(fs)) if len(fs) >= 2 else 0.0


def max_finger_holes_in_span(si: dict, span_mm: float = HAND_SPAN_MM) -> int:
    """`span_mm` に収まる指孔の最大本数。**パラメータに依らない。**

    スパンは音程だけで決まるので（実効長が 1/f に比例する管では位置比が
    `f_高/f_低` そのもの）、これは楽器サイズと音階の並びの性質であって設計値では
    ない。「届かないなら段数を減らす」と言うとき、**何段まで減らせるか**を
    数字で出すのがこの関数。

    実測（既定の長音階・両手 200mm）: soprano 4 本 / alto 3 本 / tenor 2 本。
    つまりアルトなら「ド レ ミ ファ」の 4 音まで。
    """
    from saxsketch.acoustics import toneholes

    f_low = float(si["low_note_sounding_hz"])
    steps = toneholes.SCALE_STEPS
    s_low = _cone_length_for(si, f_low * 2.0 ** (steps[0] / 12.0))
    for k in range(len(steps), 0, -1):
        s_hi = _cone_length_for(si, f_low * 2.0 ** (steps[k - 1] / 12.0))
        if s_low - s_hi <= span_mm:
            return k
    return 1


def hole_zone(s: float, p: dict, np_: dict) -> str:
    """その弧長が直管／ボウ／ベルのどれに載るか（キーレスの実現性に効く）。"""
    body0 = float(np_["neck_length"])
    b_s0, b_arc, b_rb, _ang = _bow(p)
    if float(p["bell_length"]) > 0.0 and s >= part_end(p, np_) - float(p["bell_length"]):
        return "ベル"
    if b_rb is not None and body0 + b_s0 <= s <= body0 + b_s0 + b_arc:
        return "ボウ"
    return "直管"


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
    return _self_collision_error(p, si, np_) or hole_layout_error(p, si, np_)


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
    ss = stations(p, si, np_)
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


def hole_regions(p: dict, si: dict, np_: dict) -> dict:
    """側孔まわりの 3D ハイライト用ゾーン（曲げ後の実 z）。

    `param_regions` から分けてあるのは、こちらが `size_info` を要る（穴の位置は
    目標音から決まる）ため。`body.py` が 2 つを合わせて返す。
    """
    if not is_holed(p):
        return {}
    holes = hole_layout(p, si, np_)
    zs = [centerline_point(h["s_mm"], p, np_)[0][2] for h in holes]
    fz = [z for z, h in zip(zs, holes) if h["role"] == "finger"]
    reg: dict = {}
    if fz:
        band = {"z0": min(fz) - 8.0, "z1": max(fz) + 8.0, "side": "all",
                "label": "指孔"}
        for k in ("finger_holes", "hole_dia", "hole_chimney"):
            reg[k] = dict(band)
    tz = [z for z, h in zip(zs, holes) if h["role"] == "thumb"]
    if tz:
        band = {"z0": tz[0] - 8.0, "z1": tz[0] + 8.0, "side": "all",
                "label": "親指孔"}
        for k in ("thumb_vent", "thumb_offset", "thumb_dia"):
            reg[k] = dict(band)
    return reg


def side_profile_polylines(p: dict, si: dict, np_: dict) -> dict:
    """曲げ平面(XZ)での外形・ボア母線。座標は (z, x)（横長に読める向き）。"""
    ot, ob, it, ib = [], [], [], []
    for s in stations(p, si, np_):
        (cx, _cy, cz), _t, a = centerline_point(s, p, np_)
        ro = outer_radius_at(s, p, si, np_)
        ri = wall_inner_radius_at(s, p, si, np_)
        ot.append((cz + ro * a[2], cx + ro * a[0]))
        ob.append((cz - ro * a[2], cx - ro * a[0]))
        it.append((cz + ri * a[2], cx + ri * a[0]))
        ib.append((cz - ri * a[2], cx - ri * a[0]))
    return {"outer_top": ot, "outer_bot": ob, "bore_top": it, "bore_bot": ib}
