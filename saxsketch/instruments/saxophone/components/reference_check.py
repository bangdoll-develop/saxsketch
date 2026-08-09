"""実物・規格との照合カード（純データ比較・OCCT非依存）。

`profiles.py` と同じ「純数学」方針。3部品が共用する。

**照合先に選んだ量の基準**: 出所が確かで、かつ設計値から独立に決まるものだけを使う。
  - リードの規格寸法（全長・先端幅）… 市販品の規格。descriptor の reed_std_*
  - ネックのテノン外径＋コルク厚 … はめあい寸法。ボアがこれ未満だと装着できない
  - フェイシング長の公表レンジ … 各社フェイシングチャートの実測公表値
  - リガチャー座の後端 vs リード全長 … 踵が座に収まるという幾何拘束

**採らなかったもの**: マウスピースの全長・ボディ径・チェンバー寸法。どのメーカーも
公表しておらず（ティップ開きとフェイシング長しか出さない）、こちらで「実物値」を
決め打つと、テンプレートを校正した自分の値を写して照合するだけの循環になる。
これらは Phase 4 の採寸ワークフローでユーザーが実測した基準物と比べる。
"""
from __future__ import annotations

from . import profiles


#: 「リード踵がリガチャー座の後端に届いているか」の許容差 [mm]。
#: 実測のテナーは座の後端 79.0mm に対し規格リード 78.0mm で、**1.0mm 後ろに出る**のが
#: 正しい姿（座はバンド幅より広いので締まる）。ここが 2 箇所に別々の数字で書いてあり、
#: リード側だけ 1.0mm だったため、テナー既定が **0.02mm 差**で警告を出していた。
#: 判定するのは同じ幾何なので、しきい値も 1 箇所から配る。
SEAT_REACH_TOL = 1.5
#: 同上、「軽微」までの許容差 [mm]。
SEAT_REACH_TOL_MINOR = 4.0

#: コルクの締め代 [mm]。マウスピースのボアは「テノン外径＋2×コルク厚」**より細い**。
#: コルクは圧縮して食いつくので、自由状態のコルク込み外径ぴったりだと抜ける。
#: 出所は実測。3サイズでネックとマウスピースの両方を実測してあるのはテナーだけで、
#: WindyCity の実測ボア 17.0mm に対し Selmer SA80 II のネックは
#: テノン 15.0 ＋ コルク 1.10×2 ＝ 17.2mm（descriptor の neck_dimensions_source）。
INTERFERENCE_FIT_MM = 0.2
#: ボア径の許容差 [mm]。締め代を引いた狙い値からのずれで測る。
BORE_TOL = 0.3
#: 同上、「軽微」までの許容差 [mm]。
BORE_TOL_MINOR = 1.0


def _verdict(delta: float, tol_ok: float, tol_minor: float) -> str:
    a = abs(delta)
    if a <= tol_ok:
        return "一致"
    return "軽微" if a <= tol_minor else "乖離"


def _row(label: str, value: float, ref: float, unit: str,
         tol_ok: float, tol_minor: float) -> tuple[list, str]:
    v = _verdict(value - ref, tol_ok, tol_minor)
    return ([label, f"{value:.1f} / {ref:.1f} {unit}  {v}"], v)


def required_bore_dia(size_info: dict) -> float:
    """自由状態のコルクを巻いたテノンの外径 [mm]。

    テノン外径そのものではマウスピースは挿さらない。コルクを巻いた分だけ太い。
    """
    return size_info["neck_tenon_od_mm"] + 2.0 * size_info["neck_cork_thickness_mm"]


def nominal_bore_dia(size_info: dict) -> float:
    """コルクを巻いたテノンに嵌まるマウスピースのボア径 [mm]。

    `required_bore_dia` から締め代を引く。ここが「ボアはコルク込み外径以上でなければ
    挿さらない」という以前の考え方との違いで、実物はむしろ **少し細い**（コルクを
    潰して食いつかせる）。テナー実測 17.0 に対しコルク込み外径 17.2 でその差 0.2mm。
    """
    return required_bore_dia(size_info) - INTERFERENCE_FIT_MM


def mouthpiece_card(p: dict, size_info: dict) -> dict:
    """マウスピースの規格照合。設計値 / 規格値 と判定を並べる。"""
    rows, verdicts = [], []

    # ボアだけは判定が非対称。太い側はコルクを厚く巻けば埋まるが、細い側は
    # コルクの圧縮しろを超えると物理的に挿さらない。対称公差で「軽微」と言ってはいけない。
    aim = nominal_bore_dia(size_info)
    bore = p["bore_dia"]
    if bore < aim - BORE_TOL:
        v = "乖離"
    else:
        v = _verdict(bore - aim, BORE_TOL, BORE_TOL_MINOR)
    rows.append(["ボア径 / テノン＋コルク−締め代",
                 f"{bore:.2f} / {aim:.2f} mm  {v}"])
    verdicts.append(v)

    for r, v in (
        _row("テーブル幅 / 規格リード先端幅", p["reed_width"],
             size_info["reed_std_tip_width_mm"], "mm", 0.3, 0.8),
        _row("リガチャー座の後端 / 規格リード全長",
             profiles.ligature_seat_range(p)[1],
             size_info["reed_std_length_mm"], "mm",
             SEAT_REACH_TOL, SEAT_REACH_TOL_MINOR),
    ):
        rows.append(r)
        verdicts.append(v)

    lo, hi = size_info["facing_length_range_mm"]
    fl = p["facing_length"]
    v = "一致" if lo <= fl <= hi else ("軽微" if lo - 2 <= fl <= hi + 2 else "乖離")
    rows.append(["フェイシング長 / 公表チャート域",
                 f"{fl:.1f} / {lo:.0f}〜{hi:.0f} mm  {v}"])
    verdicts.append(v)

    return _finish("実物・規格との照合", rows, verdicts,
                   "全長・ボディ径・チェンバーは各社とも公表していないため照合対象外。"
                   "手元の実物と比べたい場合は採寸して基準に取り込んでください。")


def reed_card(p: dict, size_info: dict) -> dict:
    """リードの規格照合。"""
    rows, verdicts = [], []
    for r, v in (
        _row("全長 / 規格", p["reed_length"], size_info["reed_std_length_mm"],
             "mm", 1.0, 3.0),
        _row("先端幅 / 規格", p["tip_width"], size_info["reed_std_tip_width_mm"],
             "mm", 0.3, 0.8),
    ):
        rows.append(r)
        verdicts.append(v)
    return _finish("規格リードとの照合", rows, verdicts,
                   "規格から外すと市販リガチャー・マウスピースに合わなくなります。"
                   "厚みプロファイルは規格が無いため照合対象外。")


def _finish(title: str, rows: list, verdicts: list, note: str) -> dict:
    if "乖離" in verdicts:
        status, big = "bad", "規格から外れています"
    elif "軽微" in verdicts:
        status, big = "warn", "わずかに規格から外れています"
    else:
        status, big = "ok", "規格に一致しています"
    return {"title": title, "big": big, "status": status,
            "rows": rows, "advice": note}
