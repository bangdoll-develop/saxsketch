"""実物・規格との照合カード（純データ比較・OCCT非依存）。

`profiles.py` と同じ「純数学」方針。3部品が共用する。

**照合先に選んだ量の基準**: 出所が確かで、かつ設計値から独立に決まるものだけを使う。
  - リードの規格寸法（全長・先端幅）… 市販品の規格。descriptor の reed_std_*
  - ネックのテノン外径＋コルク厚 … はめあい寸法。ボアがこれ未満だと装着できない
  - フェイシング長の公表レンジ … 各社フェイシングチャートの実測公表値
  - テーブル終端 vs リガチャー座の後端 … 締める範囲は平坦でなければならない（自己整合）
  - テーブル終端 vs リード全長域 … 踵まで平坦面が続くかという幾何拘束。
    **リード全長を実測してあるサイズでだけ判定する**（`reed_length_is_measured`）。
    未実測の 1 点は位置が数 mm 分からないので、1mm 級の不足を「乖離」と呼べない。

**リード全長は 1 点ではない。** 実測してある 2 サイズがどちらも域になる:

    soprano  バンドーレン 3番（ケーン）59.1 / レジェール アメリカンカット（樹脂）62.0
    alto     D'Addario Select Jazz（ケーン）71.1 / レジェール Studio Cut（樹脂）70.2

以前ここにあった「リガチャー座の後端 ＝ 規格リード全長」という等値照合は、許容差
`SEAT_REACH_TOL` 1.5mm の倍ぶれる量を 1 点と比べていたので、どのしきい値を選んでも
成立しない。判定は**向きのある拘束**だけで出し、等値は参考値として数字だけ並べる。

**理由は散らばりの大きさではなく、予測できないこと。** アルトの差は 0.9mm で
ソプラノの 2.9mm より小さいが、**向きが逆**（ソプラノは樹脂が長く、アルトはケーンが
長い）。材質やカットから全長を推せないので、実測が無いサイズでは域の幅すら
見積もれない。だから「未実測なら判定しない」であって「未実測なら広めの公差」ではない。

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
#:
#: **いま使っているのは `reed.py` のリード側だけ**（「設計中のリードが座の後端に
#: 届かない」＝本当に締まらない状態の警告）。マウスピース側の等値照合は Stage G で
#: 外した。リード全長が銘柄で 2.9mm 動くので、この 1.5mm では判定できない。
SEAT_REACH_TOL = 1.5

#: テーブル平坦部がリガチャー座の後端に届いているかの判定ゼロ点 [mm]。
#: これは規格との照合ではなく `profiles` 内部の自己整合で、リガチャーが締める範囲は
#: 全部平坦でなければならないという物理条件。以前ここが崩れて「リード後端 20mm が
#: 宙に浮く」形状が出たことがある（tests の `test_table_reaches_reed_heel`）。
#: 浮動小数の丸め以上の不足は許さないので、ゼロ点はほぼ 0。
TABLE_FLAT_EPS = 0.05
#: 同上、「軽微」までの不足 [mm]。これを超えたら座の下に平坦でない面がある。
TABLE_FLAT_TOL_MINOR = 1.0


def reed_length_range(size_info: dict) -> tuple[float, float]:
    """このサイズで実際に使われるリード全長の域 [mm]。

    `reed_length_range_mm` があればそれを、無ければ `reed_std_length_mm` の 1 点を
    上下端の両方に使う。域を持つのは実測が 2 本以上あるサイズだけ
    （いまは soprano / alto。tenor は未実測の代表値 78.0 の 1 点）。
    """
    rng = size_info.get("reed_length_range_mm")
    if rng:
        return float(rng[0]), float(rng[1])
    std = float(size_info["reed_std_length_mm"])
    return std, std


def reed_length_is_measured(size_info: dict) -> bool:
    """このサイズのリード全長が実測されているか。

    未実測の 1 点は**位置が数 mm 分からない**。ソプラノで同じ出所の 63.5 が実測
    2 本（59.1 / 62.0）から 4.4mm 外れていた実績があるので、この点との比較で
    1mm 級の判定を出してはいけない —— 向きのある拘束であっても、比べる相手の
    位置が動くなら結論も動く。判定を出すかどうかの分岐に使う。
    """
    return bool(size_info.get("reed_length_range_mm"))


def _span_text(lo: float, hi: float) -> str:
    """域の表示。1 点しか無いサイズでは「59.1〜59.1」と書かない。"""
    return f"{lo:.1f}" if hi <= lo else f"{lo:.1f}〜{hi:.1f}"


def reed_length_span(size_info: dict) -> str:
    """リード全長域の表示用文字列 [mm]。カード以外（BOM など）からも使う。"""
    return _span_text(*reed_length_range(size_info))

#: コルクの締め代 [mm]。マウスピースのボアは「テノン外径＋2×コルク厚」**より細い**。
#: コルクは圧縮して食いつくので、自由状態のコルク込み外径ぴったりだと抜ける。
#:
#: **出所は基準マウスピース 2 本（n=2）。** どちらもちょうど 0.20 に乗る:
#:   tenor  WindyCity 実測ボア 17.0 / Selmer SA80 II のテノン 15.0 ＋ コルク 1.10×2 ＝ 17.2
#:   alto   Wood Stone PHROX 実測ボア 15.8 / Yamaha YAS-875 のテノン 14.5 ＋ コルク 0.75×2 ＝ 16.0
#: アルトは**テナーの 0.2 とネック実測だけから 15.80 を予言してあり、実測が 15.8**
#: だった（2026-08-13）。狙い値を先に書いてから測って当たった唯一の量。
#:
#: **ただし締め代は 1 点ではない。** 同じネックに載る別銘柄を測ると散る:
#:   alto  Meyer G by Meyer 6番   ボア 16.4 → 締め代 **−0.40**（自由状態より太い）
#:   tenor Jody Jazz Giant 6*     ボア 16.7 → 締め代 **+0.50**
#: 同じアルトのネックに 0.6mm 違うボアの 2 本が載る以上、これは 1 個の定数ではない。
#: 差を吸収しているのは**コルクの厚み**（摩耗する消耗品。このアルトのコルクは 3 サイズで
#: 唯一 1.0mm を割る 0.75 で、巻き直せば狙い値ごと動く）。`cork_depth`・リード全長・
#: コルク帯に続く「一意に決まると思っていた量」の 4 つ目。
INTERFERENCE_FIT_MM = 0.2
#: ボア径の許容差 [mm]。締め代を引いた狙い値からのずれで測る。
#: **実測 4 本の散らばり（−0.40〜+0.50）がそのまま根拠**。ここを 0.2 などに締めると、
#: 実在して実際に装着できているマウスピースを「乖離」と言うことになる。
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

    r, v = _row("テーブル幅 / 規格リード先端幅", p["reed_width"],
                size_info["reed_std_tip_width_mm"], "mm", 0.3, 0.8)
    rows.append(r)
    verdicts.append(v)

    seat1 = profiles.ligature_seat_range(p)[1]
    table_end = profiles.table_cut_end_z(p)
    reed_lo, reed_hi = reed_length_range(size_info)

    # (1) 必須。リガチャーが締める範囲は全部平坦でなければならない。規格ではなく
    #     profiles 内部の自己整合なので、サイズやリードの銘柄に依らず必ず成り立つ。
    slack = table_end - seat1
    if slack >= -TABLE_FLAT_EPS:
        v = "一致"
    else:
        v = "軽微" if slack >= -TABLE_FLAT_TOL_MINOR else "乖離"
    rows.append(["テーブル終端 / リガチャー座の後端",
                 f"{table_end:.1f} / {seat1:.1f} mm  {v}"])
    verdicts.append(v)

    # (2) 踵まで平坦面が続くか。**非対称**に見る。長いリードにだけ足りないなら軽微
    #     （踵の数 mm はリガチャーの外側で、密着させる必要が無い）。域の下端にも
    #     足りなければ、どのリードを使っても踵が浮くので乖離。
    #     伸ばす側は害が無いので上限は見ない。
    #
    #     **リード全長が未実測のサイズでは判定しない。** 比べる相手の位置が数 mm
    #     分からないので、1mm 級の不足を「乖離」と呼ぶ根拠が無い（残るのはテナーで、
    #     テーブル終端 81.6 に対し未実測の 1 点 78.0）。
    #
    #     **アルトがこの分岐の必要性を実証した。** リード実測（70.2〜71.1）だけを
    #     先に入れた時点ではテーブル終端 70.3 で「軽微」が出たが、これは実在しない
    #     不足だった —— 同時に届いた最大径位置の実測でテーブル終端が 73.0 になり
    #     「一致」に戻る。判定を汚していたのはモデルのテーブルではなく、テナーから
    #     借りたシャンク比のほう。片方の実測だけで判定を出してはいけない。
    if reed_length_is_measured(size_info):
        v = "一致" if table_end >= reed_hi else ("軽微" if table_end >= reed_lo else "乖離")
        rows.append(["テーブル終端 / リード全長域",
                     f"{table_end:.1f} / {_span_text(reed_lo, reed_hi)} mm  {v}"])
        verdicts.append(v)
    else:
        rows.append(["（参考）テーブル終端 / リード全長",
                     f"{table_end:.1f} / {reed_lo:.1f} mm　リード全長が未実測のため判定しない"])

    # (3) 参考。**判定しない。** 「踵が最大径の位置に来る」という設計則は、実測どうしで
    #     確かめられる唯一の組（ソプラノ: マウスピース 71.4 / リード 59.1・62.0）で
    #     符号が反転する。モジュール docstring の理由でしきい値を置かない。
    d_lo, d_hi = seat1 - reed_lo, seat1 - reed_hi
    gap = f"{d_lo:+.1f}" if reed_hi <= reed_lo else f"{d_hi:+.1f}〜{d_lo:+.1f}"
    rows.append(["（参考）リガチャー座の後端 − リード全長", f"{gap} mm"])

    lo, hi = size_info["facing_length_range_mm"]
    fl = p["facing_length"]
    v = "一致" if lo <= fl <= hi else ("軽微" if lo - 2 <= fl <= hi + 2 else "乖離")
    rows.append(["フェイシング長 / 公表チャート域",
                 f"{fl:.1f} / {lo:.0f}〜{hi:.0f} mm  {v}"])
    verdicts.append(v)

    return _finish("実物・規格との照合", rows, verdicts,
                   "全長・ボディ径・チェンバーは各社とも公表していないため照合対象外。"
                   "リード全長は銘柄・カット・材質で動くので 1 点ではなく域で"
                   "見ています（descriptor の reed_length_range_mm）。**長短の向きは"
                   "材質から決まりません** —— ソプラノは樹脂が 2.9mm 長く、アルトは"
                   "ケーンが 0.9mm 長い。実測が 1 本も無いサイズ（いまはテナー）では、"
                   "テーブル終端との比較は判定せず参考値として並べます。"
                   "ソプラノのテーブル終端はモデル 60.0mm に対し実物が 60.2mm（実測、"
                   "2026-08-13）で、ここで出る「軽微」はモデルの粗さではなく"
                   "**実物の性質**です —— 長いリード（レジェール 62.0mm）の踵は"
                   "実際に 1.8mm はみ出します。"
                   "手元の実物と比べたい場合は採寸して基準に取り込んでください。")


def reed_card(p: dict, size_info: dict) -> dict:
    """リードの規格照合。"""
    rows, verdicts = [], []

    # 全長は域の外へ出た分だけで測る。域の中はどこでも実在する市販品なので
    # 代表値からの距離では判定しない（ソプラノは 59.1 と 62.0 が両方とも実物）。
    lo, hi = reed_length_range(size_info)
    length = p["reed_length"]
    over = 0.0 if lo <= length <= hi else (length - hi if length > hi else length - lo)
    v = _verdict(over, 1.0, 3.0)
    rows.append(["全長 / 規格域", f"{length:.1f} / {_span_text(lo, hi)} mm  {v}"])
    verdicts.append(v)

    r, v = _row("先端幅 / 規格", p["tip_width"],
                size_info["reed_std_tip_width_mm"], "mm", 0.3, 0.8)
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
