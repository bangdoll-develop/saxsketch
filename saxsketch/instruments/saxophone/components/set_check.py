"""セット（マウスピース＋リガチャー＋リード）の適合カード。

**部品どうしでしか出せない量だけを扱う。** 1 部品の中で完結する照合は各部品の
カードが持っている（`reference_check` のマウスピース/リード、`ligature` の
はめあい）。ここに同じ行を並べると、しきい値が 2 か所に散って片方だけ厳しくなる
—— テナーの「座の後端」が実際にそうなっていた（`reference_check.SEAT_REACH_TOL`
の注記）。

いま出している 4 行はどれも「リガチャーの帯がどこを掴んでいるか」で、これは
**マウスピース（座の位置とテーブルの実幅）・リガチャー（帯幅と座位置）・
リード（全長・踵幅・削り始め）の 3 つが揃わないと決まらない**。

**座標系**: リードもマウスピースも z=0 が先端なので、そのまま比べてよい
（リードは組んだとき先端をティップレールに合わせる）。厳密にはティップ輪郭の
落ち込みぶん（0.1mm 級）ずれるが、ここで見ているのは 1mm 級の量。
"""
from __future__ import annotations

from . import ligature_profiles as lp
from . import profiles
from . import reed_profiles as rp
from . import reed_seat
from .reference_check import SEAT_REACH_TOL, _finish, _verdict

#: 帯の前端がリードの削り始め（バーク端）より前へ出てよい量 [mm]。
#: 削った部分を締めると、リードは厚みが足りないぶん動く（鳴りが死ぬ）。
#: 0 を基準に、ノギスの読み取り差の桁だけ許す。
VAMP_CLEAR_TOL = 0.5
#: 同上、「軽微」までの食い込み [mm]。
VAMP_CLEAR_TOL_MINOR = 3.0

#: 帯の下のリード厚が、リガチャーが想定した厚みからずれてよい量 [mm]。
#: **これは公差ではなく、想定と実物が同じ物を指しているかの確認**。ずれるのは
#: ヴァンプが帯の下まで伸びているときだけで、そのときは締まり方が変わる。
THICKNESS_TOL = 0.05
THICKNESS_TOL_MINOR = 0.30


def set_card(size_info: dict, members: dict) -> dict | None:
    """セット全体の適合カード。マウスピースとリガチャーが揃っているときだけ出す。

    Args:
        size_info: サイズの音響基準定数（採寸の上書き込み）。
        members: {部品ID: {"params": dict, "component": Component}}。
                 **コンポーネント実体も渡す**のは、「リガチャーが想定している
                 リード」を部品自身に聞くため（セットにリードが居ないときの
                 フォールバック規則を 2 か所に書かない）。
    """
    mp = members.get("mouthpiece")
    lig = members.get("ligature")
    if mp is None or lig is None:
        return None

    m, p = mp["params"], lig["params"]
    reed_entry = members.get("reed")
    # リガチャーが実際に当たり面を作るときに使っているリード寸法。セットにリードが
    # 居ればその実寸、居なければ同サイズのテンプレート値（部品側の規則そのまま）。
    assumed = lig["component"].reed_params()
    reed_p = reed_entry["params"] if reed_entry else None

    rows, verdicts = [], []

    band0, band1 = lp.seat_range(m, p)
    rows.append(["リガチャー帯の位置（前端→後端）", f"{band0:.1f} → {band1:.1f} mm"])

    if reed_p is None:
        rows.append(["想定リード", "同サイズのテンプレート値"
                                   f"（踵厚 {assumed['heel_thickness']:.2f} / "
                                   f"踵幅 {assumed['heel_width']:.1f} mm）"])
        return _finish(
            "セットの適合（MP＋リガチャー）", rows, verdicts,
            "リードはまだセットにありません。リガチャーの当たり面は**同サイズの"
            "テンプレート リード**を想定して作られています。リードを設計して"
            "セットに足すと、その実寸に合わせた形へ変わります"
            "（変わったことは通知に出ます）。")

    rows.append(["想定リード", f"このセットのリード"
                               f"（踵厚 {assumed['heel_thickness']:.2f} / "
                               f"踵幅 {assumed['heel_width']:.1f} mm）"])

    # (1) 踵が帯の後端まで届いているか。**非対称**に見る。届かなければリードの
    #     後端が宙に浮いて締まらない。長い分は帯の外へ出るだけで害が無い。
    length = float(reed_p["reed_length"])
    short = band1 - length
    v = "一致" if short <= SEAT_REACH_TOL else ("軽微" if short <= 3.0 else "乖離")
    rows.append(["リード全長 / 帯の後端",
                 f"{length:.1f} / {band1:.1f} mm  {v}"])
    verdicts.append(v)

    # (2) 帯が削った部分を締めていないか。バーク端より前に**接触が当たる**と、
    #     厚みの薄い所を掴むことになる。**帯の呼び範囲ではなく接触の位置で見る**
    #     （Phase 4-F）—— 点接触は帯の 1/4 と 3/4 に立つので、前端に余裕が無くても
    #     当たっていないことがあるし、その逆は無い。
    vamp = rp.vamp_start_z(reed_p)
    touch = lp.contact_front_z(m, p)
    bite = vamp - touch          # 正 = 接触が削り部へ食い込んでいる
    v = "一致" if bite <= VAMP_CLEAR_TOL else (
        "軽微" if bite <= VAMP_CLEAR_TOL_MINOR else "乖離")
    rows.append(["接触が当たる最前 / リードの削り始め",
                 f"{touch:.1f} / {vamp:.1f} mm  {v}"
                 + ("" if abs(touch - band0) < 1e-9 else f"（帯の前端は {band0:.1f}）")])
    verdicts.append(v)

    # (3) 裏面が密着するか。**1 点では決まらない**（Phase 4-F）—— 以前はここで
    #     帯の中央 1 点の幅を比べていて、テナーの「帯の前端の直後から踵まで
    #     16mm ぜんぶ縁がテーブルの外」を「軽微」と言っていた。
    #
    #     判定するのは**締める区間（窓の終端〜帯の後端）のはみ出しだけ**。
    #     後ろへはみ出すのは締めないので害が無く、窓へのかかり代は実物でも
    #     負に出るのでまだ判定しない（`reed_seat.seat_card` と同じ分担）。
    seat = reed_seat.seat_summary(m, reed_p, band1)
    w = seat["window"]
    rows.append(["（参考）窓へのかかり代 最小",
                 "窓が開いていません" if w is None else
                 f"{w['mm']:+.2f} mm（z={w['z']:.1f}）"])
    t = seat["table"]
    if t is None:
        rows.append(["帯までのはみ出し 最大", "区間がありません"])
    else:
        v = _verdict(max(t["mm"], 0.0), reed_seat.OVER_TOL, reed_seat.OVER_TOL_MINOR)
        rows.append(["帯までのはみ出し 最大",
                     f"{t['mm']:+.2f} mm（z={t['z']:.1f}）  {v}"])
        verdicts.append(v)
    tl = seat["tail"]
    rows.append(["（参考）帯より後ろのはみ出し 最大",
                 "リードが帯の後端より短い" if tl is None else
                 f"{tl['mm']:+.2f} mm（z={tl['z']:.1f}）"])

    # (3b) タブがこのリードを収められるか。**判定はリガチャーのカードが持つ**
    #      （切り詰めの警告は `ligature._fit_card`）。ここは「どのリードで
    #      タブを切ったか」を出すだけ —— しきい値を 2 か所に置かない。
    z_mid = (band0 + band1) / 2.0
    rows.append(["リード踵幅 / タブ幅",
                 f"{reed_p['heel_width']:.1f} / "
                 f"{lp.flat_half_width(m, p, assumed) * 2.0:.1f} mm"])

    # (4) 帯の下の実際のリード厚と、リガチャーが想定した厚み。**普通は一致する**
    #     （帯はバークの上に載るので厚みは一定）。ずれるのはヴァンプが帯の下まで
    #     伸びているときで、そのとき締まり方は想定と別物になる。
    actual = rp.thickness(reed_p, min(z_mid, length - 0.01), 0.0)
    delta = actual - assumed["heel_thickness"]
    a = abs(delta)
    v = "一致" if a <= THICKNESS_TOL else ("軽微" if a <= THICKNESS_TOL_MINOR else "乖離")
    rows.append(["帯の下のリード厚 / リガチャーの想定",
                 f"{actual:.2f} / {assumed['heel_thickness']:.2f} mm  {v}"])
    verdicts.append(v)

    return _finish(
        "セットの適合（MP＋リガチャー＋リード）", rows, verdicts,
        "ここに出るのは**3 部品が揃わないと決まらない量**だけです"
        "（帯の位置はマウスピースの座・リガチャーの幅と座位置・リードの全長で"
        "決まります）。各部品ごとの規格照合はそれぞれのカードにあります。"
        "リードの z はマウスピースと同じく先端が 0 で、組んだときティップレールに"
        "合わせる前提です —— ティップ輪郭の落ち込み（0.1mm 級）は無視しています。"
        "**裏面の密着は 1 点ではなく全長で見ています**（`reed_seat`）—— 判定するのは"
        "リガチャーが締める区間だけで、後ろへはみ出すぶんは害が無いので参考値、"
        "窓へのかかり代は実物のマウスピースでも負に出るのでまだ判定しません。"
        "マウスピース単体のカードは**規格リード**で同じことを見ています。")
