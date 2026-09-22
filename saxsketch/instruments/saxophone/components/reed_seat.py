"""リードがマウスピースに載るか —— **裏面が密着するか**を面で測る。

判定したいのは 3 つ ——**① 裏面が密着するか（漏れないか）／② 振動部が妨害されないか
／③ リガチャーで固定できるか**。このモジュールが持つのは①だけで、②③はリガチャーが
要るので `set_check` にある（部品どうしでしか出せない量はそちら、という既存の分担）。

**「載る」は 1 点では決まらない。** いままでこれを見ていた行は、帯の中央 1 点で幅を
比べるか（`set_check`）、z だけ比べるか（`reference_check` の「テーブル終端 /
リード全長域」）、面を 1 つも決めていない公称値 `reed_width` を相手にしていた。
z の全域で、リードの縁が**レール帯 `[open_half, face_half]` の中にあるか**を見る。

    z 区間          相手         量                      扱い
    窓が開いている  open_half    reed_half − open_half   かかり代（負なら漏れる）
    窓終端〜帯後端  face_half    reed_half − face_half   はみ出し（正なら浮く）
    帯後端〜踵      face_half    reed_half − face_half   **参考**（後ろは害が無い）

**区間の切り方をここ 1 か所に置く** —— これが「無害なはみ出し」と「漏れるはみ出し」を
分けている唯一の規則。既定値のテナーは帯の前端 61.0 の直後 z=61.9 から踵まで
16mm ぜんぶ縁がテーブルの外にあるが、ソプラノ・アルトのはみ出しは全部帯より後ろに
落ちる —— 同じ「+2.5mm はみ出す」でも意味が逆になるので、量だけ見ても判定できない。

**しきい値を 1 つも持たない。** ゼロは自然に決まる（縁がレール帯の中か外か）ので
発明が要らず、判定の段（一致/軽微/乖離）はカード側が持つ。

**窓のかかり代は実測で判定へ上げた**（2026-09-21、アルト）。それまで参考に
留めていた理由は「実物テナーでも負に出る」だったが、あれは**実物の窓 × 未実測の
規格リード幅**の比較だった。アルトで両方を測ると 2 MP × 2 リード × 4 z の 16 組が
すべて +0.40〜+1.33、リードを載せて光にかざす試験も 10 組すべて「縁がレールの上」。
負を出していたのはリード幅の借り物（13.4、出所なし。実測 15.85〜16.4）のほう。
**ソプラノも翌日測って判定へ上げた**（2026-09-22）: 刻印 4 / Metal 7 × リード 2 本 ×
z 3 点の 12 組すべて +0.90〜+2.12、光 10 組とも「縁がレールの上」。ただしソプラノの
負は**半分が窓の側**だった —— 窓の法則がテンプレートの基準そのもの（刻印 4）より
一様に 1.3mm 広く、`side_rail_width` を 0.89 → 1.55 に直している。
**判定するのはリードの先端幅が実測されたサイズだけ**（`cover_row`）——
テナーの規格リード幅は同じ出所の借り物のまま。

座標系はマウスピースと同じ（z=0 がティップ）。リードは組んだとき先端を
ティップレールへ合わせるので、そのまま比べてよい —— 厳密にはティップ輪郭の
落ち込みぶん（0.1mm 級）ずれるが、ここで見ているのは 0.1〜数 mm の量
（`set_check` の座標系の注記と同じ）。
"""
from __future__ import annotations

from . import profiles
from . import reed_profiles as rp

#: 区間のラベル。
NOSE, WINDOW, TABLE, TAIL = "nose", "window", "table", "tail"

#: 画面に出す名前。
LABELS = {NOSE: "ティップレール", WINDOW: "窓",
          TABLE: "窓の終端〜帯の後端", TAIL: "帯の後端〜踵"}


def default_seat_end(m: dict) -> float:
    """帯の後端の既定。リガチャーが居ないとき（マウスピース単体）に使う。

    実物のリガチャーが居れば `ligature_profiles.seat_range()[1]` を渡すこと ——
    座を前後に振れるので、区間の境目はリガチャー次第で動く。
    """
    return profiles.ligature_seat_range(m)[1]


def seat_profile(m: dict, r: dict, seat_end: float | None = None,
                 n: int = 240) -> list[dict]:
    """z ごとの `{z, band, open_half, reed_half, face_half, cover, over}`。

    `face_half` は `reed_chord/2`。フェイシング区間ではリード面が持ち上がるので
    テーブル平面で測ってはいけない（`profiles.reed_chord` の注記）。平面である区間
    （z ≥ `facing_length`）では `table_flat_width/2` と一致する。

    区間の判定に `window_end_z` を使わず**開口そのもの**（`open_half > 0`）で切る。
    窓の範囲を 2 か所で述べないため。
    """
    if seat_end is None:
        seat_end = default_seat_end(m)
    # テーブル平面が胴から外れる所で打ち切る。そこから先は「載る面」が無いので
    # 幅を比べても意味が無い（踵が越えているかは `reference_check` の z の行が見る）。
    z_end = min(float(r["reed_length"]), profiles.table_cut_end_z(m))
    grid = {z_end * i / n for i in range(n + 1)}
    for z in (profiles.window_end_z(m), seat_end, profiles.window_open_z(m)):
        if 0.0 < z < z_end:
            grid.add(z)
    out = []
    with profiles.params_scope(m):
        for z in sorted(grid):
            oh = profiles.window_open_half_width(m, z)
            out.append({"z": z, "open_half": oh,
                        "face_half": profiles.reed_chord(m, z) / 2.0,
                        "reed_half": rp.width(r, z) / 2.0})
    # **窓より前は判定しない。** そこはティップレールで、リードの前縁と
    # マウスピースのティップ輪郭が合っているかの話（`reed._tip_contour_gap`）。
    # 幅で比べると、先端の面取りで胴が細っているぶんリードの鼻が必ずはみ出して
    # 見える（既定 3 サイズとも z≈0.3 で +0.9〜+1.2mm）。
    opened = [d["z"] for d in out if d["open_half"] > 0.0]
    z_nose = min(opened) if opened else float("inf")
    for d in out:
        d["band"] = (NOSE if d["z"] < z_nose else
                     WINDOW if d["open_half"] > 0.0 else
                     TAIL if d["z"] > seat_end else TABLE)
        d["cover"] = d["reed_half"] - d["open_half"]
        d["over"] = d["reed_half"] - d["face_half"]
    return out


def seat_summary(m: dict, r: dict, seat_end: float | None = None) -> dict:
    """3 区間それぞれの最悪点。

    Returns:
        {"window": {"mm", "z"} | None,   最小のかかり代（負 = 縁が窓の上に浮く）
         （窓より前＝ティップレール区間は判定しない。`seat_profile` の注記）
         "table":  {"mm", "z"} | None,   最大のはみ出し（正 = 縁がテーブルの外）
         "tail":   {"mm", "z"} | None,   同上。**参考**（後ろは害が無い）
         "seat_end": float, "z_end": float, "beyond_table_mm": float}

    `beyond_table_mm` はリードがテーブル平面の消える所より後ろへ出た長さ。
    ここは「載る面」が無いので幅の比較から外してある（0 でないこと自体は
    `reference_check` の「テーブル終端 / リード全長域」が既に見ている）。
    """
    prof = seat_profile(m, r, seat_end)

    def worst(band: str, key: str, pick) -> dict | None:
        pts = [d for d in prof if d["band"] == band]
        if not pts:
            return None
        d = pick(pts, key=lambda d: d[key])
        return {"mm": d[key], "z": d["z"]}

    return {
        # かかり代は**小さいほうが悪い**（負で縁が窓の上）。はみ出しは逆。
        "window": worst(WINDOW, "cover", min),
        "table": worst(TABLE, "over", max),
        "tail": worst(TAIL, "over", max),
        "seat_end": (default_seat_end(m) if seat_end is None else seat_end),
        "z_end": prof[-1]["z"] if prof else 0.0,
        "beyond_table_mm": max(float(r["reed_length"])
                               - profiles.table_cut_end_z(m), 0.0),
    }


# ---------------------------------------------------------------- カード
#
# ここから下は**表示と判定の段**。上の法則はしきい値を 1 つも持たない。

#: はみ出しの判定幅 [mm]。**新しく置いた数字ではない** —— このカードが置き換えた
#: 行（`reference_check` の「テーブル幅 / 規格リード先端幅」と `reed_card` の
#: 「先端幅 / 規格」）が使っていた 0.3 / 0.8 をそのまま引き継ぐ。リード幅に対する
#: 既存の許容がこれで、判定の相手も同じ「リードの縁がどこに来るか」。
OVER_TOL = 0.3
OVER_TOL_MINOR = 0.8


def cover_row(window: dict | None, size_info: dict) -> dict:
    """窓へのかかり代の行と判定。**判定はここ 1 か所**（3 枚のカードが読む）。

    幅は**はみ出しと同じ 0.3 / 0.8**（新しい数字を作らない。見ているのは同じ
    「リードの縁がどこに来るか」で、向きが逆なだけ）。足りない側だけ見る ——
    縁がレールの外側へ出るぶんは窓の区間では漏れない。

    **判定するのは規格リードの先端幅が実測されたサイズだけ**
    （`reference_check.reed_tip_width_is_measured`）。未実測のサイズでは規格
    リードの幅が借り物で、その借り物がアルトで 2.5〜3.0mm、ソプラノで 1.0〜1.25mm
    狭かった（ソプラノは窓の法則も 1.3mm 広く、負の半分はそちら ——
    `side_rail_width` を直してから判定へ上げた）。
    `reference_check` がリード全長の未実測サイズで判定しないのと同じ形。

    Returns: {"row": [label, text], "verdict": "一致"|"軽微"|"乖離"|None}
    """
    from .reference_check import _verdict, reed_tip_width_is_measured

    if window is None:
        return {"row": ["（参考）窓へのかかり代 最小", "窓が開いていません"],
                "verdict": None}
    mm = window["mm"]
    text = f"{mm:+.2f} mm（z={window['z']:.1f}）"
    if not reed_tip_width_is_measured(size_info):
        return {"row": ["（参考）窓へのかかり代 最小",
                        text + ("　縁が窓の上に浮いています" if mm < 0 else "")
                        + "　このサイズは規格リード幅が未実測のため判定しない"],
                "verdict": None}
    v = _verdict(max(-mm, 0.0), OVER_TOL, OVER_TOL_MINOR)
    return {"row": ["窓へのかかり代 最小",
                    text + ("　縁が窓の上に浮いています" if mm < 0 else "") + f"  {v}"],
            "verdict": v}


def _seat_finish(title: str, rows: list, verdicts: list, note: str) -> dict:
    """`reference_check._finish` と同じ形。**見出しの文だけ違う。**

    あちらは「規格に一致しています」と言う —— ここで見ているのは規格ではなく
    2 つの部品の当たりなので、そのまま借りると判定の意味がすり替わる。
    """
    if "乖離" in verdicts:
        status, big = "bad", "縁がレールから外れる区間があります"
    elif "軽微" in verdicts:
        status, big = "warn", "縁がわずかにレールから外れる区間があります"
    else:
        status, big = "ok", "帯までは全幅が載っています"
    return {"title": title, "big": big, "status": status,
            "rows": rows, "advice": note}


def seat_card(m: dict, r: dict, size_info: dict, seat_end: float | None = None,
              reed_label: str = "同サイズのテンプレート") -> dict:
    """「リードが載るか」の①（裏面が密着するか）。

    **判定するのは 2 つ**: 窓へのかかり代（規格リードの先端幅が実測されたサイズ
    だけ。`cover_row`）と、「窓の終端〜帯の後端」のはみ出し。
    **帯より後ろのはみ出し**は締めないので害が無く、参考。

    ②振動部が妨害されないか・③リガチャーで固定できるかは、リガチャーが要るので
    `set_check` にある。
    """
    from .reference_check import _verdict

    s = seat_summary(m, r, seat_end)
    rows = [["想定リード",
             f"{reed_label}（先端 {r['tip_width']:.1f} / "
             f"踵 {r['heel_width']:.1f} mm）"],
            ["帯の後端（区間の境目）", f"{s['seat_end']:.1f} mm"]]
    verdicts = []

    cover = cover_row(s["window"], size_info)
    rows.append(cover["row"])
    if cover["verdict"]:
        verdicts.append(cover["verdict"])

    t = s["table"]
    if t is None:
        rows.append(["窓の終端〜帯の後端", "区間がありません"])
    else:
        v = _verdict(max(t["mm"], 0.0), OVER_TOL, OVER_TOL_MINOR)
        rows.append(["帯までのはみ出し 最大",
                     f"{t['mm']:+.2f} mm（z={t['z']:.1f}）  {v}"])
        verdicts.append(v)

    tl = s["tail"]
    rows.append(["（参考）帯より後ろのはみ出し 最大",
                 "リードが帯の後端より短い" if tl is None else
                 f"{tl['mm']:+.2f} mm（z={tl['z']:.1f}）"])
    if s["beyond_table_mm"] > 0.0:
        rows.append(["（参考）テーブルより後ろへ出た長さ",
                     f"{s['beyond_table_mm']:.1f} mm　この区間は載る面が無いので"
                     "幅の比較から外しています"])

    return _seat_finish(
        "リードが載るか（裏面の密着）", rows, verdicts,
        "**窓へのかかり代**は縁が窓の上に浮くと脇から漏れるので判定します"
        "（実物のマウスピース 2 本 × リード 2 本で アルト +0.40〜+1.33mm・ソプラノ"
        " +0.90〜+2.12mm、光にかざして 2 サイズ 20 組とも縁がレールの上）。ただし"
        "規格リードの先端幅が未実測のサイズでは参考です。"
        "**「窓の終端〜帯の後端」**はリガチャーが締める区間なので、縁がテーブルの"
        "外にあると押しても密着しません。"
        "**帯より後ろへはみ出すのは害がありません**（締めないので参考値）。"
        "比べる相手はそのサイズの**規格リード**です —— リードを設計していても"
        "ここは規格で見ます（リードは規格から大きく動かさない前提）。"
        "設計中のリードとの適合はセットのカードにあります。")
