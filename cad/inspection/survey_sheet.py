# -*- coding: utf-8 -*-
"""採寸シート（記入用紙）を印刷用 HTML で出す。

**作業台の上で使える受け口が無かった。** 採寸の入り口はブラウザの採寸フォームだけで、
ノギスを持っている間は画面を見ていられない。このスクリプトは印刷して書き込める
用紙を出し、書き込んだ値をそのまま採寸フォーム（`survey_targets` の欄）へ移せる
ように、**欄名も `key` も並び順もフォームと同じ**にしてある。

**数字は手で写さない**（`cad/inspection/README.md` の規則）。設計値・判定帯・
モデルの予測はすべて registry から引く。判定帯は自前のしきい値ではなく
`inspection_values.bands()`（＝`Component.survey_card` と同じ式）を import している。

狙いは `docs/reed-seat.md` §「次に測る」の 1〜4 —— **かかり代の決着**:

  1. リードを複数本（銘柄・カット・材質で寸法は動く）  → 節 A
  2. 先端から 20mm の幅（テーパー直線の仮定の反証）      → 節 B の z=20 行
  3. 実物マウスピースの窓幅を z 数点                     → 節 B
  4. リードを載せて光にかざす                            → 節 C

**節 B が本体。** 同じ z で窓幅とリード幅を並べれば、かかり代 `(リード幅 − 窓幅)/2`
が実物で決まる。

**3 サイズとも測って決着した**（2026-09-21 / 22 / 23、値は `inspection_values.py`
の `REED_SURVEY` ほか）: 2 MP × 2 リードの全組が正（アルト 16 組 +0.40〜+1.33、
ソプラノ 12 組 +0.90〜+2.12、テナー 16 組 +0.50〜+1.45）、光の試験も 30 組すべて ○。
モデルが負を出していたのは規格リード先端幅の借り物（アルト 13.4 / ソプラノ 12.9 /
テナー 14.8、どれも出所なし）のせいで、ソプラノでは**窓の法則も基準個体より 1.3mm
広かった**（`side_rail_width` を直した）。テナーの窓は直していない —— 測った 2 本が
どちらも基準（WindyCity）ではないので、差は法則の誤差か個体差か分けられない。

**3 枚目（マウスピースの外形）は窓を直したサイズだけ**（`MP_SHAPE_SIZES`）。
窓幅だけでは「レールが太い」と「空洞が狭い」を分けられないので、リード面の外幅を
同じ z で測って分ける。z=1〜3 の外幅は MP のティップ輪郭そのもの。

**先端カーブは「側面がまっすぐになる所」まで測る**（実測者に確認した定義）。
欄名は採寸フォームと同じ仮想キー `tip_full_width_z` で、設計値も同じ量で刷る ——
パラメータ `tip_curve_depth`（丸みを無視した見かけの角）はノギスで当てられない。

実行（OCCT が要るので WSL2。出力は Windows 正本へ直接書く）:

  cd ~/mp_design && source .venv/bin/activate
  python cad/inspection/survey_sheet.py \
    --out /mnt/c/HOME/<user>/develop/claude/mp_design/cad/inspection/survey_sheet.html
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import subprocess
import sys
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))
sys.path.insert(0, str(_HERE))

# Windows のコンソール既定は CP932 で「—」等が落ちる。出力は必ず UTF-8 にする。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from inspection_values import bands                              # noqa: E402
from saxsketch.core.registry import get_registry                 # noqa: E402
from saxsketch.instruments.saxophone.components import profiles  # noqa: E402
from saxsketch.instruments.saxophone.components import reed_profiles as rp  # noqa: E402
from saxsketch.instruments.saxophone.components import reed_seat  # noqa: E402
from saxsketch.instruments.saxophone.components import reference_check  # noqa: E402

SIZES = ("soprano", "alto", "tenor")

#: 窓幅を測る z の候補 [mm]（ティップ端からの距離）。**丸い数字にしてある** ——
#: 現場では z をノギスの深さバーで出して印を付けるので、半端な値だと写し間違える。
Z_CANDIDATES = (5.0, 10.0, 20.0, 30.0)
#: 窓の開き始め / 終わりから避ける余裕 [mm]。ジョウが窓の縁に乗ると幅が読めない。
Z_MARGIN_FRONT, Z_MARGIN_REAR = 1.5, 2.0

#: どこへノギスを当てるか。**`docs/print-inspection.md` §6.2 と同じ文**（2 か所に
#: 別の手順を書かないため）。ここに無い欄は測り方が決まっていないということ。
HOWTO = {
    "reed_length": "先端〜踵の端面。銘柄で 1〜3mm 動く",
    "tip_width": "先端の最も広い所（角の丸みの内側）。<b>かかり代を決める</b>",
    "heel_width": "踵の端面。<b>リガチャーのタブ幅を決める</b>",
    "tip_thickness": "先端の中央。当て圧に注意（潰れる）",
    "heel_thickness": "踵の端面の中央（バークの上）",
    "heel_edge_thickness": "踵の端面の<b>側の端</b>。リガチャーの当たり面",
    "vamp_length": "先端〜バークの段差（指で触れば分かる）",
    "tip_full_width_z": "角の丸みが終わって<b>側面がまっすぐになる所</b>に直定規を"
                        "渡し、中央との隙間（丸みを無視した見かけの角ではない）",
}

#: 未実測の欄。**空欄と「未測」が違う**のと同じ理由で、これも書いておく ——
#: 出所は `saxsketch/instruments/saxophone/templates/*.json` の `reed_note`。
#: `MEASURED_SIZES` のサイズでは実測に置き換え済みなので出さない。
UNMEASURED = {
    "heel_edge_thickness": "未実測（テンプレートの `reed_note`）",
    "tip_full_width_z": "未実測（参照マウスピースの輪郭から逆算した値）",
}
#: 上の欄を実物で測ってテンプレートへ入れたサイズ。
MEASURED_SIZES = {"alto": "2026-09-21 に 5 本", "soprano": "2026-09-22 に 5 本",
                  "tenor": "2026-09-23 に 5 本"}
#: 設計値が**そもそも実物のリードの値ではない**欄（サイズに依らない）。
PRINT_SIDE = {
    "tip_thickness": "設計値は印刷側の強度下限から置いた値（実物は 3 サイズとも 0.2〜0.35）",
}

#: 3 枚目（マウスピースの外形）を刷るサイズと、その理由。**窓の法則を実物の窓幅へ
#: 合わせたサイズ**で、合わせたつまみ（`side_rail_width`）が「レールの実幅」なのか
#: 「空洞の寄せ」なのかは窓幅だけでは分からない。
MP_SHAPE_SIZES = {
    "soprano": ('窓がテンプレートの基準（刻印 4）より一様に 1.3mm 広かったので、'
                '<span class="k">side_rail_width</span> を 0.89 → 1.55 にして合わせた'
                '（2026-09-22）。<b>窓幅だけでは「レールが太い」と「空洞が狭い」を'
                '分けられない</b> —— リード面の外幅を同じ z で測れば、レールの実幅 ＝'
                '（外幅 − 窓幅）/ 2 が決まる。最大径 25.0 もボア比で縮めた未実測値'),
}
#: 外幅を測る z [mm]。z=1〜3 は**ティップの輪郭そのもの**（外幅の半分がその z で
#: 前縁が来る x）で、リード前縁との比較（いまは参考）を判定へ戻す鍵。
FACE_Z = (1.0, 2.0, 3.0, 5.0, 10.0, 20.0)
#: 窓幅を足す z。モデルのかかり代が最小になる区間（z≈2〜3）が節 B の z=5 より手前。
WINDOW_Z_EXTRA = (2.0, 3.0)


def git_rev(out_path: str) -> str:
    """生成元のコミット。**シートに出所を残す**（設計は動くので）。

    出力先（＝Windows 正本）の repo を見る。WSL の稼働コピーは rsync で作られていて
    `.git` を持たないので、スクリプト自身の場所から引くと必ず「不明」になる。
    """
    for start in (Path(out_path).resolve().parent, _HERE.parent.parent):
        try:
            r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                               cwd=str(start), capture_output=True,
                               text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    return "(不明)"


def short(text: str, n: int = 170) -> str:
    """出所文字列を 1 行に詰める。**全文は `descriptor.json`。**

    ここで欲しいのは「実測か未実測か・何本か」で、それは先頭に書いてある。
    """
    s = str(text or "").replace("**", "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def z_grid(m: dict) -> list[float]:
    """窓幅を測れる z。**法則から決める**（サイズごとに手で書かない）。"""
    lo = profiles.window_open_z(m) + Z_MARGIN_FRONT
    hi = profiles.window_end_z(m) - Z_MARGIN_REAR
    zs = [z for z in Z_CANDIDATES if lo < z < hi]
    if not zs:
        raise SystemExit(f"窓が {lo:.1f}〜{hi:.1f}mm しかなく、測れる z が無い")
    return zs


def load_params(path: str | None, size: str) -> tuple[dict, dict, str]:
    """(mouthpiece_params, reed_params, 出所ラベル)。

    `.wproj` を渡せばその設計、渡さなければテンプレート素。**印刷した個体の
    判定はその個体の設計に対してしか意味が無い**（`inspection_values` と同じ）。
    """
    inst = get_registry().get("saxophone")
    tpl = inst.templates[size]
    if path is None:
        return dict(tpl["mouthpiece"]), dict(tpl["reed"]), f"テンプレート {size} 素"
    with zipfile.ZipFile(path) as z:
        d = json.loads(z.read("project.json"))
    if "members" in d:
        m = dict(d["members"]["mouthpiece"]["params"])
        r = dict(d["members"].get("reed", {}).get("params", tpl["reed"]))
    else:                                   # v1（単体プロジェクト）
        m, r = dict(d["params"]), dict(tpl["reed"])
    return m, r, f"{d.get('name', Path(path).name)}（{size}）"


# ---------------------------------------------------------------- HTML

CSS = """
@page { size: A4 portrait; margin: 9mm 8mm 8mm; }
* { box-sizing: border-box; }
body { margin: 0; color: #000; background: #fff;
       font: 9pt/1.4 "Yu Gothic", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
h1 { font-size: 13pt; margin: 0 0 1mm; }
h1 small { font-size: 8pt; font-weight: normal; }
h2 { font-size: 9.5pt; margin: 3mm 0 1mm; padding-left: 2mm;
     border-left: 3px solid #000; }
h2 span { font-weight: normal; font-size: 7.6pt; }
table { border-collapse: collapse; width: 100%; font-size: 8.2pt;
        table-layout: fixed; }
th, td { border: 0.4pt solid #555; padding: 0.6mm 1.1mm;
         text-align: left; vertical-align: middle; overflow-wrap: anywhere; }
th { font-weight: 600; background: none; }
td.fill, th.fill { height: 7.5mm; }
.tall td.fill, .tall th.fill { height: 10mm; }
.memo div { border-bottom: 0.4pt solid #555; height: 8mm; }
.num { text-align: right; font-variant-numeric: tabular-nums;
       white-space: nowrap; }
.k { font-family: ui-monospace, Consolas, monospace; font-size: 7.2pt;
     color: #333; }
.note { font-size: 7.2pt; line-height: 1.35; margin: 1mm 0 0; }
.claim { font-size: 7.8pt; border: 0.4pt solid #555; padding: 1.2mm 1.6mm;
         margin: 1mm 0 0; }
.foot { font-size: 7.2pt; line-height: 1.4; margin-top: 2.5mm;
        border-top: 0.4pt solid #555; padding-top: 1.2mm; }
.hdr { display: flex; justify-content: space-between; align-items: flex-end;
       border-bottom: 1pt solid #000; padding-bottom: 1mm; }
.hdr .who { font-size: 7.6pt; text-align: right; white-space: nowrap; }
ul { margin: 0.6mm 0 0 4mm; padding: 0; }
li { margin: 0.3mm 0; }
@media screen {
  body { background: #e9e9e9; padding: 6mm 0; }
  .page { width: 210mm; min-height: 297mm; margin: 0 auto 6mm; padding: 9mm 8mm;
          background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.3); }
}
"""


def esc(x) -> str:
    return html.escape(str(x), quote=False)


def cells(n: int, cls: str = "fill") -> str:
    return "".join(f'<td class="{cls}"></td>' for _ in range(n))


PAGE_OPEN = '<section class="page">'


def head(label: str, src: str, rev: str, part: str) -> str:
    """ページの頭。**1 枚ずつ独立して使える**ように、どの紙にも出所を刷る。"""
    return (PAGE_OPEN + f'<div class="hdr"><h1>採寸シート — {esc(label)}'
            f'<br><small>{esc(part)} ／ 設計値の出所: {esc(src)} ／ '
            f'生成 {dt.date.today()} ({rev})</small></h1>'
            '<div class="who">記入者 ______________　記入日 ____ / ____ / ____'
            '<br>ノギス ____________（分解能 ______ mm）</div></div>')


#: 脚注。**測る前に読む規則**で、`docs/print-inspection.md` §2 と同じもの
#: （新しい規則をここで作らない）。2 枚目は当てる場所の話だけに絞る。
FOOT_MEASURE = (
    '<div class="foot"><b>測る前に</b><ul>'
    '<li><b>0.1mm 未満の差を「差がある」と言わない。</b>'
    'ノギス 1 回の読みの不確かさは ±0.05mm 級。</li>'
    '<li><b>空欄と「未測」は違う。</b>測らなかった欄には「未測」と書く ——'
    '空欄だと「測り忘れ」か「記録し忘れ」か後で分けられない。</li>'
    '<li><b>1 本だけ入れない。</b>同じサイズを複数本まとめて測ってから設計へ返す'
    '（1 本は域の端かもしれない）。</li>'
    '<li>この用紙は <span class="k">cad/inspection/survey_sheet.py</span> が生成する。'
    '設計やテンプレートを変えたら刷り直す（数字を手で写さないため）。</li>'
    '</ul></div>')

FOOT_COMPARE = (
    '<div class="foot"><b>当てる場所</b><ul>'
    '<li><b>z はティップ端から。</b>ティップ端は硬いランドマークで位置決めできる'
    '（窓の前縁は 1mm 弱しかなくノギスが当たらない）。深さバーで z を出して'
    'テーブル面に印を付け、その位置で幅を読む。</li>'
    '<li><b>窓幅は内側ジョウ</b>（窓は貫通した開口なので内測が入る）、'
    '<b>リード幅は外側ジョウ</b>。同じ z で読むこと —— 違う z の 2 つを引き算しても'
    'かかり代にならない。</li>'
    '<li>節 C は道具が要らない。<b>いちばん安い決着</b>なので、時間が無ければ'
    'ここだけでも埋める。</li>'
    '</ul></div>')


def page(size: str, label: str, m: dict, r: dict, src: str,
         reeds: int, mps: int, rev: str) -> str:
    inst = get_registry().get("saxophone")
    comp = inst.make_component("reed", size)
    specs = {s.key: s for s in comp.param_specs()}
    targets = comp.survey_targets()
    si = comp.size_info
    zs = z_grid(m)
    seat = reed_seat.seat_summary(m, r)

    # **1 サイズ 2 ページ。** 1 ページに詰めると記入欄が 6mm を割って鉛筆が入らない。
    # 前半＝個体の同定とリードの採寸（作業台にリードだけ並べる）、
    # 後半＝マウスピースと組み合わせる節（B・C）。作業の順番でもある。
    o = [head(label, src, rev, "① 個体の同定 / リードの採寸")]

    # ---- モデルの言い分（測る前に何を否定しに行くのかを 1 か所に）
    w, t, tl = seat["window"], seat["table"], seat["tail"]
    claim = []
    if w:
        claim.append(f'窓へのかかり代 最小 <b>{w["mm"]:+.2f} mm</b>（z={w["z"]:.1f}）')
    if t:
        claim.append(f'帯までのはみ出し 最大 {t["mm"]:+.2f} mm（z={t["z"]:.1f}）')
    claim.append("帯より後ろ " + (f'{tl["mm"]:+.2f} mm' if tl else "区間なし"))
    # **判定か参考かはサイズで分かれる**（`reed_seat.cover_row` と同じ分岐）。
    if reference_check.reed_tip_width_is_measured(si):
        why = ('このサイズは規格リードの先端幅を実測済みなので<b>判定</b>している'
               f'（{MEASURED_SIZES.get(size, "実測")}）。実物は 2 MP × 2 リードの全組が正だった'
               '（3 サイズとも）—— 測り直すなら、<b>別の銘柄で符号が変わらないか</b>を見る。')
    else:
        why = ('このサイズは<b>規格リードの先端幅が未実測</b>（出所の記録なし）なので参考値。'
               '同じ出所の値は既に測った 3 サイズで 1〜3mm 狭く、負のかかり代はその'
               '借り物のせいだった —— <b>このシートはそれを実物で決めるためのもの。</b>')
    o.append('<p class="claim"><b>モデルの言い分</b>　' + "　／　".join(claim)
             + '。かかり代が負＝<b>リードの縁がサイドレールに載らず窓の上に浮く</b>'
               '（脇から漏れる）。' + why + '</p>')

    # ---- 0 個体の同定
    o.append('<h2>0　個体の同定　<span>先に埋める。<b>1 本だけ測って入れない</b>'
             '（銘柄・カット・材質で寸法は動く）</span></h2>')
    o.append('<table><colgroup><col style="width:13mm">'
             '<col style="width:26%"><col><col><col style="width:18mm">'
             '<col style="width:22mm"></colgroup>'
             '<tr><th>リード</th><th>銘柄</th><th>カット</th><th>材質</th>'
             '<th>硬さ</th><th>入手/備考</th></tr>')
    for i in range(1, reeds + 1):
        o.append(f'<tr><th class="fill">#{i}</th>{cells(5)}</tr>')
    o.append('</table>')
    o.append('<table style="margin-top:1mm"><colgroup><col style="width:13mm">'
             '<col style="width:26%"><col><col><col style="width:18mm">'
             '<col style="width:22mm"></colgroup>'
             '<tr><th>マウスピース</th><th>銘柄</th><th>刻印/開き</th>'
             '<th>材質</th><th>実測/印刷</th><th>入手/備考</th></tr>')
    for i in range(1, mps + 1):
        o.append(f'<tr><th class="fill">#{i}</th>{cells(5)}</tr>')
    o.append('</table>')

    # ---- A リードの採寸
    o.append('<h2>A　リードの採寸　<span>欄名・並び順は採寸フォームと同じ'
             '（そのまま移せる）。帯は刻み由来</span></h2>')
    o.append('<table><colgroup><col style="width:31mm"><col style="width:35mm">'
             '<col style="width:12mm"><col style="width:23mm">'
             + '<col>' * reeds + '</colgroup>')
    o.append('<tr><th>欄</th><th>どこを測るか</th><th class="num">設計値</th>'
             '<th class="num">一致/軽微</th>'
             + "".join(f'<th class="num">#{i}</th>' for i in range(1, reeds + 1))
             + '</tr>')
    for p in targets["params"]:
        k = p["key"]
        # 先端カーブの欄はパラメータではない（測れる量＝全幅に達する位置）。
        # 設計値もその量で刷り、帯は元のパラメータの刻みから引く。
        tip = k == comp.SURVEY_TIP_KEY
        sp = specs["tip_curve_depth" if tip else k]
        ok, minor = bands(sp)
        note = HOWTO.get(k, "")
        if k in PRINT_SIDE:
            note += f'<br><span class="k">{PRINT_SIDE[k]}</span>'
        elif k in UNMEASURED and size not in MEASURED_SIZES:
            note += f'<br><span class="k">{UNMEASURED[k]}</span>'
        design = rp.tip_full_width_z(r) if tip else r[k]
        o.append(f'<tr><th>{esc(p["label"])}<br><span class="k">{k}</span></th>'
                 f'<td class="note">{note}</td>'
                 f'<td class="num">{design:.2f}</td>'
                 f'<td class="num">±{ok:.2f} / ±{minor:.2f}</td>'
                 + cells(reeds) + '</tr>')
    o.append('</table>')
    o.append('<p class="note">規格の全長 <b>'
             + f'{si["reed_std_length_mm"]:.1f} mm</b>'
             + (f'（域 {si["reed_length_range_mm"][0]:.1f}〜'
                f'{si["reed_length_range_mm"][1]:.1f}）'
                if si.get("reed_length_range_mm") else "（域なし）")
             + f' ／ 規格の先端幅 <b>{si["reed_std_tip_width_mm"]:.1f} mm</b>'
             + (f'（域 {si["reed_tip_width_range_mm"][0]:.2f}〜'
                f'{si["reed_tip_width_range_mm"][1]:.2f}）'
                if si.get("reed_tip_width_range_mm") else "（域なし）") + '<br>'
             + f'全長の出所: {esc(short(si.get("reed_std_length_source", "(記載なし)")))}<br>'
             + f'先端幅の出所: {esc(short(si.get("reed_std_tip_width_source", "(記載なし)")))}'
             + '</p>')
    o.append(FOOT_MEASURE)
    o.append('</section>')

    # ================================================================ 2 枚目
    o.append(head(label, src, rev, "② 窓とリードの幅 / 光にかざす"))

    # ---- B 窓とリードの幅
    o.append('<h2>B　窓とリードの幅（同じ z で並べる）　<span>'
             '<b>これが本体。</b>かかり代 =（リード幅 − 窓幅）/ 2。'
             'z はティップ端から（硬いランドマーク）</span></h2>')
    o.append('<table class="tall"><colgroup><col style="width:11mm">'
             '<col style="width:17mm"><col style="width:17mm">'
             '<col style="width:23mm">'
             + '<col>' * (mps + 2) + '</colgroup>')
    o.append('<tr><th rowspan="2" class="num">z<br>[mm]</th>'
             '<th colspan="3">モデルの予測</th>'
             f'<th colspan="{mps}">実測 窓幅（内側ジョウ）</th>'
             '<th colspan="2">実測 リード幅（外側ジョウ）</th></tr>'
             '<tr><th class="num">窓幅</th><th class="num">リード幅</th>'
             '<th class="num">かかり代/片側</th>'
             + "".join(f'<th class="num">MP#{i}</th>' for i in range(1, mps + 1))
             + '<th class="num">リード#1</th><th class="num">リード#2</th></tr>')
    with profiles.params_scope(m):
        for z in zs:
            ow = 2.0 * profiles.window_open_half_width(m, z)
            rw = rp.width(r, z)
            mark = ' ★' if z == 20.0 else ''
            o.append(f'<tr><th class="num fill">{z:.0f}{mark}</th>'
                     f'<td class="num">{ow:.2f}</td><td class="num">{rw:.2f}</td>'
                     f'<td class="num">{(rw - ow) / 2.0:+.2f}</td>'
                     + cells(mps + 2) + '</tr>')
    o.append('</table>')
    o.append('<p class="note">★ <b>z=20 の行は「先端から 20mm の幅」そのもの</b>'
             '（基準定数 <span class="k">reed_width_at20_mm</span>）。'
             'リードの幅テーパーはモデルが<b>先端幅→踵幅の直線</b>と仮定している。'
             '3 サイズの実物では直線はほぼ成立（残差 +0.1 前後）し、<b>先端のほうが'
             ' 1〜2mm 広かった</b>（旧既定は踵のほうを広く置いていた）。'
             '先端幅・踵幅（節 A）と合わせれば、手元のリードでも直線かどうかが言える。</p>')

    # ---- C 光にかざす
    o.append('<h2>C　リードを載せて光にかざす　<span>'
             '<b>かかり代の physical な正解。</b>道具が要らないのに、'
             'いちばん効く</span></h2>')
    o.append('<table class="tall"><colgroup><col style="width:16mm">'
             + '<col>' * mps + '<col style="width:40%"></colgroup>')
    o.append('<tr><th>リード＼MP</th>'
             + "".join(f'<th>#{i}</th>' for i in range(1, mps + 1))
             + '<th>気づいたこと（左右差・浮く位置 z）</th></tr>')
    for i in range(1, reeds + 1):
        o.append(f'<tr><th class="fill">#{i}</th>{cells(mps + 1)}</tr>')
    o.append('</table>')
    o.append('<p class="note"><b>○</b> = リードの縁がサイドレールの上に載っている'
             '（光が漏れない）／<b>×</b> = 縁が窓の上に浮いている（脇に光の筋）／'
             '<b>△</b> = 判別できない。<b>見るのはティップ寄り</b>'
             + (f'（モデルのかかり代が最小になるのは z≈{w["z"]:.0f}mm）' if w else "")
             + '。左右で違えば、それも書く（テーブルの平面度の話になる）。</p>')

    # 2 枚目は 130mm ほど余る。**予想していなかったことを書く場所**に使う ——
    # 欄を用意していない観察（片減り、テーブルの反り、リガチャーの当たり）は
    # 用紙に場所が無いと消える。
    o.append('<h2>D　そのほか気づいたこと　<span>欄が無いものを書く'
             '（片減り・反り・リガチャーの当たり・吹いた感じ）</span></h2>')
    o.append('<div class="memo">' + '<div></div>' * 6 + '</div>')

    o.append(FOOT_COMPARE)
    o.append('</section>')
    if size in MP_SHAPE_SIZES:
        o.append(mp_shape_page(size, label, m, src, mps, rev, w))
    return "\n".join(o)


def mp_shape_page(size: str, label: str, m: dict, src: str, mps: int, rev: str,
                  w: dict | None) -> str:
    """3 枚目: マウスピースの外形。**窓を実物へ合わせたつまみの意味を決める。**"""
    o = [head(label, src, rev, "③ マウスピースの外形（窓を直した根拠の確かめ）")]
    o.append('<p class="claim"><b>なぜ測るか</b>　' + MP_SHAPE_SIZES[size]
             + (f'。モデルのかかり代が最小になるのは z={w["z"]:.1f}（節 B の実測より手前）'
                if w else '') + '。</p>')
    o.append('<h2>E　リード面の外幅と窓幅　<span><b>外幅は外側ジョウをリードが載る面に'
             '沿わせて</b>、その z で面の端から端。窓幅は内側ジョウ（z=5 以降は節 B）'
             '</span></h2>')
    o.append('<table class="tall"><colgroup><col style="width:11mm">'
             '<col style="width:17mm"><col style="width:17mm"><col style="width:17mm">'
             + '<col>' * (2 * mps) + '</colgroup>')
    o.append('<tr><th rowspan="2" class="num">z<br>[mm]</th>'
             '<th colspan="3">モデルの予測</th>'
             f'<th colspan="{mps}">実測 外幅（外側ジョウ）</th>'
             f'<th colspan="{mps}">実測 窓幅（内側ジョウ）</th></tr>'
             '<tr><th class="num">外幅</th><th class="num">窓幅</th>'
             '<th class="num">レール/片側</th>'
             + "".join(f'<th class="num">MP#{i}</th>' for i in range(1, mps + 1)) * 2
             + '</tr>')
    with profiles.params_scope(m):
        for z in FACE_Z:
            face = profiles.reed_chord(m, z)
            ow = 2.0 * profiles.window_open_half_width(m, z)
            win = (cells(mps) if z in WINDOW_Z_EXTRA else
                   f'<td class="num" colspan="{mps}">節 B</td>' if z >= 5.0 else
                   f'<td class="num" colspan="{mps}">—</td>')
            o.append(f'<tr><th class="num fill">{z:.0f}</th>'
                     f'<td class="num">{face:.2f}</td><td class="num">{ow:.2f}</td>'
                     f'<td class="num">{(face - ow) / 2.0:.2f}</td>'
                     + cells(mps) + win + '</tr>')
    o.append('</table>')
    o.append('<p class="note"><b>z=1〜3 の外幅はティップの輪郭そのもの</b>'
             '（外幅の半分の x で前縁がその z に来る）。z=1 は丸みの上なので'
             '深さバーで z を出してから印を付ける。</p>')

    o.append('<h2>F　1 点ずつ　<span>どちらも硬いランドマークから</span></h2>')
    o.append('<table class="tall"><colgroup><col style="width:36mm"><col>'
             '<col style="width:17mm">' + '<col style="width:22mm">' * mps + '</colgroup>')
    o.append('<tr><th>量</th><th>どこを測るか</th><th class="num">モデル</th>'
             + "".join(f'<th class="num">MP#{i}</th>' for i in range(1, mps + 1)) + '</tr>')
    rows = [
        ('最大径<br><span class="k">body_dia</span>',
         "<b>テーブルと平行に</b>挟む（テーブル面から反対側へ当てると小さく出る）",
         m["body_dia"]),
        ("ティップ端 → 窓の後縁",
         'ティップ端に深さバー（<span class="k">docs/print-inspection.md</span>'
         ' §5.2 と同じ手順）',
         profiles.window_end_z(m)),
    ]
    for name, how, val in rows:
        o.append(f'<tr><th class="fill">{name}</th><td class="note">{how}</td>'
                 f'<td class="num">{val:.2f}</td>' + cells(mps) + '</tr>')
    o.append('</table>')
    o.append('<p class="note">最大径と窓の後縁は<b>このサイズでは未実測</b>'
             '（最大径はテナーをボア比で縮めた値、窓の長さはテナーを軸比で縮めた値）。'
             'アルトでは同じ 2 量の実測で、比で引く考え方そのものが壊れた。</p>')
    o.append('<h2>G　そのほか気づいたこと</h2>')
    o.append('<div class="memo">' + '<div></div>' * 4 + '</div>')
    o.append(FOOT_COMPARE)
    o.append('</section>')
    return "\n".join(o)


def build(sizes, project: str | None, reeds: int, mps: int,
          rev: str) -> str:
    inst = get_registry().get("saxophone")
    pages = []
    for size in sizes:
        m, r, src = load_params(project, size)
        label = inst.templates[size].get("label", size)
        pages.append(page(size, label, m, r, src, reeds, mps, rev))
    return ("<!doctype html>\n<html lang=\"ja\"><head><meta charset=\"utf-8\">\n"
            "<title>SaxSketch 採寸シート（マウスピース・リード）</title>\n"
            f"<style>{CSS}</style></head><body>\n"
            + "\n".join(pages) + "\n</body></html>\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="採寸シート（記入用紙）を HTML で出す")
    ap.add_argument("--size", choices=SIZES, action="append",
                    help="既定は 3 サイズぜんぶ")
    ap.add_argument("--project", help=".wproj（既定はテンプレート素）")
    ap.add_argument("--reeds", type=int, default=5, help="リードの記入列数")
    ap.add_argument("--mps", type=int, default=2, help="マウスピースの記入列数")
    ap.add_argument("--out", default=str(_HERE / "survey_sheet.html"))
    a = ap.parse_args()

    doc = build(a.size or list(SIZES), a.project, a.reeds, a.mps,
                git_rev(a.out))
    Path(a.out).write_text(doc, encoding="utf-8")
    print(f"✓ {a.out}（{len(doc):,} bytes / "
          f"{doc.count(PAGE_OPEN)} ページ"
          f"・{len(a.size or SIZES)} サイズ・リード {a.reeds} 本・MP {a.mps} 本）")


if __name__ == "__main__":
    main()
