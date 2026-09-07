# -*- coding: utf-8 -*-
"""検品シート（`docs/print-inspection.md`）に載せる数値を `.wproj` から再生成する。

**シートの数字を手で写さないための道具。** 設計を変えたりテンプレートを直したら
ここを回し直して差し替える。出所を追えるように、判定帯は自前のしきい値ではなく
`Component.survey_card` が使っているのと同じ規則（一致 `max(0.6·step, 0.05)` /
軽微 `max(2.5·step, 0.2)`）から出している。

`.wproj` を渡すとその設計、`--size alto` だけ渡すとテンプレート素の値を出す。

実行:
  .venv/Scripts/python.exe cad/inspection/inspection_values.py <project.wproj>
  .venv/Scripts/python.exe cad/inspection/inspection_values.py --size alto
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

# Windows のコンソール既定は CP932 で「—」等が落ちる。出力は必ず UTF-8 にする。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from saxsketch.core.registry import get_registry            # noqa: E402
from saxsketch.instruments.saxophone.components import profiles  # noqa: E402

#: フェイシングカーブを引く隙間 [mm]（隙間ゲージの一般的な板厚）。
FEELERS = (0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 0.75, 1.00, 1.50, 2.00)
#: 質量概算の材料密度 [g/cc]。`neck.MAT_DENSITY` と同じ出所を使う。
from saxsketch.instruments.saxophone.components.neck import MAT_DENSITY  # noqa: E402

#: 実測値 [mm] を (印刷品, PHROX) で持つ。**手で書くのはここだけ。**
#: 判定表・差・径比の候補はすべてここと `.wproj` から計算する。
#:
#: 出所: ノギス 0.05mm で実測（2026-09-02）。印刷品はアルト初号機
#: （`AltoSaxSetTrial1.wproj` を光造形で出したもの）、PHROX は Wood Stone PHROX
#: （アルト）＝ **alto テンプレートの校正基準そのもの**。
#:
#: **組で入れること**（`docs/print-inspection.md` §0）。1 点だけ入れると実在しない
#: 不足を記録することがある。ここに無い項目は「未測」で、空欄とは違う。
MEASURED: dict[str, tuple[float, float]] = {
    "overall_length": (91.90, 91.40),
    "body_dia":       (29.10, 29.20),
    "shank_dia":      (21.10, 23.20),
    "bore_dia":       (15.90, 15.70),
    # 第2便（2026-09-05 未明）。手順は §5.1（ティップ端でノギスをロックして和紙テープ）。
    "beak_height":    (13.60, 11.60),
}

#: **`window_length`（窓の開口長）は 1 度も測っていない。**
#: 09-02 に「ウィンドウ長」として記録した 35.30 / 39.30 は、実測者に確認したところ
#: （2026-09-05）**ティップ端 → 窓の後縁**だった。同じ量を 09-05 にもう 1 度ずつ
#: 測っているので、下の `TIP_TO_WINDOW_REAR` に **2 回の読みとして**入れてある。
#: 窓の前縁は幅 `tip_rail_width` の面で、そこにノギスは当てられない。

#: `alto.json` が**径量**に使っていた借り物の比（規格リード全長 71.5/78.0）。
#: 実測でこの比が存在しないことが確定したあとも、テンプレートを実測で上書きした値が
#: 「何から引かれていたか」を示せるように残す。テンプレートの現在値から逆算すると
#: 上書き済みの量では差が 0 になり、**外れていた幅が見えなくなる**。
LEGACY_DIA_RATIO = 71.5 / 78.0

#: ティップ端 → 窓の後縁 [mm]。**§5.2 の決着用の量。**
#: 設計値はここに書かず `tip_rail_width + window_length` から計算する。
#:
#: **[09-02, 09-05] の 2 回の読み。** 写真は `print_DSC_2001`（印刷品）と
#: 2026-09-05 の PHROX 2 枚。**PHROX は 2 回が 0.10mm で揃い、印刷品は 1.10mm
#: ばらついた** —— 印刷品の窓は角の立った矩形、PHROX は角丸のスロット（§11.5）
#: なので、**ばらつきの向きが形の予想と逆**。理由は分かっていない。
#:
#: PHROX の 39.4 が §5.2 の決着そのもの（予想は「40 付近なら窓は本当に長い、
#: 36 付近なら測っていた量が違った」で、**40 側**）。
TIP_TO_WINDOW_REAR: dict[str, list[float]] = {
    "printed": [35.30, 36.40],
    "phrox":   [39.30, 39.40],
}

#: PHROX の窓の後縁の採用値 [mm]。**実測者が 39.4 を採ると明言した**（2026-09-05）。
#: もう一方の読み 39.30 との差 0.10mm は下の上限を 0.05mm しか動かさない。
PHROX_TTW_MM = 39.40

#: 音が合ったときの挿し込み量 [mm]。ネック小端 → マウスピースのシャンク端面で、
#: `cork_depth` と同じ量（実用域の上限 36.4 もこの測り方の実測）。
#: 2026-09-05 朝、同じ日・同じネック（YAS-875）・同じリード・同じリガチャー・
#: A=442、**2 回の読み**。
#:
#: **これは「音程が一致する位置」ではない。** 奏者の申告をそのまま引く ——
#: 「アンブシュアが完璧に同一になることはなく、音程も完全一致したものではない。
#: リードの位置・リガチャーの固定状態から周囲の体感気温、管体の温度、自身の体調から
#: この辺の位置で合わせておけば演奏時間中最も音程が安定するだろうという位置に
#: 経験的に合わせている（もちろんメーターを目視しながら）」。
#: **逆算の入力に使うときはこの条件ごと引用すること。**
INSERTION_MM: dict[str, float] = {"printed": 35.4, "phrox": 29.4}

#: 前便（2026-09-05 未明）の**目視の申告**「3mm くらい」。**撤回の幅を出すためだけに
#: 残す** —— 実測は 6.0mm で **2 倍**だった。前便はこの 3mm を測定として扱い、
#: 「窓の実測からの逆算と 0.06mm で一致」という見出しを 8 か所に書いた。
INSERTION_DELTA_REPORTED_MM = 3.0

#: `bore_length/overall_length` の実測 2 本。49.05 の**唯一の根拠**がこの揃い。
BORE_RATIO_SOPRANO, BORE_RATIO_TENOR = 0.5364, 0.5349


#: 窓の後端とボアの始まりのあいだに要る余地 [mm]（`profiles.window_length_effective`
#: が使っている設計規則。実測ではない）。
WINDOW_TO_BORE_GAP_MM = 4.0


def insertion_delta() -> float:
    """実測の挿し込み量差 [mm]（印刷品 − PHROX）。**差は持たずに引く。**"""
    return INSERTION_MM["printed"] - INSERTION_MM["phrox"]


def ttw_mean(tag: str) -> float:
    """ティップ端→窓の後縁の 2 回の読みの平均 [mm]。"""
    v = TIP_TO_WINDOW_REAR[tag]
    return sum(v) / len(v)


def ttw_spread(tag: str) -> float:
    """同じ量の読みの幅 [mm]。**判定を出す前にこれを見る。**"""
    v = TIP_TO_WINDOW_REAR[tag]
    return max(v) - min(v)


def window_from_ttw(p: dict, ttw: float) -> float:
    """ティップ端→窓の後縁から窓の開口長を引く。

    **`tip_rail_width` を設計値だと仮定している** —— 実物のティップレール幅は
    印刷品も PHROX も未測。ここが 0.9 なら開口長は 0.17mm 短くなる。
    ボア長の上限のほうは**この仮定に依らない**（後縁の位置だけで決まる）。
    """
    return ttw - p["tip_rail_width"]

#: 実測した個体を出したプロジェクト。**判定はこの設計に対してしか意味がない。**
#: テンプレートは実測を取り込んで動くので（`beak_height` 11.60 / `shank_dia` 23.20、
#: 2026-09-05）、`--size alto` で回すと「印刷品が外れ」に見える —— 印刷したのは
#: 更新前の設計だから当然で、プリンタの話ではない。取り違えないよう毎回明示する。
PRINTED_FROM = "AltoSaxSetTrial1.wproj"

#: 判定を出さない量。**一致帯がノギス 1 目盛りと同じ**で、読み ±1 目盛りで判定が
#: 裏返る（`docs/print-inspection.md` §3）。数字だけ記録する。
NO_VERDICT = ("bore_dia", "tip_opening")


def verdict(d: float, tight: float, loose: float, key: str) -> str:
    """一致 / 軽微 / 外れ。帯は `Component.survey_card` と同じ規則から来る。"""
    if key in NO_VERDICT:
        return "-"
    a = abs(d)
    return "一致" if a <= tight else ("軽微" if a <= loose else "外れ")


def travel(comp, spec, params: dict) -> tuple[float, float]:
    """**その組で実際に動かせる範囲**（Phase 4-E B-5）。

    `min`/`max` は「勧める帯」、`hard_*` は**テンプレート値で作った掛け金**、
    そして関係で決まる 9 本は組ごとに動く ——「可動域」と言いながら帯を読む型は
    Phase A で 4 か所、B-4b でこのファイルの 1 か所（`beak_height` の下端を
    4.3〜5.9mm 取りこぼしていた）を直したところで、**壁が増えるたびに増える**。
    ここを 1 つにして、以後どちらでも読み違えないようにする。
    """
    lo, hi = spec.bounds()
    b = comp.param_bounds(params).get(spec.key)
    if b:
        lo = b["lo"] if b.get("lo") is not None else lo
        hi = b["hi"] if b.get("hi") is not None else hi
    return lo, hi


def bands(spec) -> tuple[float, float]:
    """(一致, 軽微) の帯。**新しいしきい値は作らない** —— `survey_card` と同じ式。"""
    st = spec.step or 0.1
    return max(0.6 * st, 0.05), max(2.5 * st, 0.2)


def load(path: str | None, size: str) -> tuple[dict, dict]:
    """(project_meta, mouthpiece_params) を返す。path が None ならテンプレート素。"""
    inst = get_registry().get("saxophone")
    if path is None:
        return {"name": f"(テンプレート {size} 素)", "template_id": size}, \
               dict(inst.templates[size]["mouthpiece"])
    with zipfile.ZipFile(path) as z:
        d = json.loads(z.read("project.json"))
    if "members" in d:
        params = dict(d["members"]["mouthpiece"]["params"])
    else:                                   # v1（単体プロジェクト）
        params = dict(d["params"])
    return d, params


def template_diff(inst, template_id: str, project: dict) -> dict[str, list]:
    """テンプレートからの変更点。**部品ごとに引く**（テンプレートは部品で入れ子）。"""
    tpl = inst.templates[template_id]
    out: dict[str, list] = {}
    for cid, m in (project.get("members") or {}).items():
        if cid not in tpl:
            continue
        out[cid] = [(k, tpl[cid][k], v) for k, v in m["params"].items()
                    if k in tpl[cid] and tpl[cid][k] != v]
    return out


def facing_distance(p: dict, gap: float) -> float:
    """隙間 `gap` になるティップからの距離 [mm]（`facing_rise` の反転）。"""
    lo, hi = 0.0, p["facing_length"]
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if profiles.facing_rise(p, mid) > gap:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wproj", nargs="?", default=None)
    ap.add_argument("--size", default="alto")
    a = ap.parse_args()

    inst = get_registry().get("saxophone")
    meta, p = load(a.wproj, a.size)
    tid = meta.get("template_id", a.size)
    comp = inst.make_component("mouthpiece", tid)
    specs = {s.key: s for s in comp.param_specs()}

    print(f"# 検品シートの数値 — {meta.get('name', '?')}")
    print(f"保存 {meta.get('saved_at', '-')} / テンプレート {tid}")
    for cid, rows in template_diff(inst, tid, meta).items():
        print(f"  {cid}: " + ("テンプレートと差分なし" if not rows else ""))
        for k, t, v in rows:
            print(f"    {k}: {t} -> {v}")

    print("\n## 採寸表")
    print(f"{'項目':16}{'設計値':>9}{'一致':>8}{'軽微':>8}")
    for k in comp._SURVEY_PARAM_KEYS + ["shank_length", "bore_length"]:
        s = specs.get(k)
        if s is None or k not in p:
            continue
        st = s.step or 0.1
        band = (f"{max(0.6 * st, 0.05):8.2f}{max(2.5 * st, 0.2):8.2f}"
                if k in comp._SURVEY_PARAM_KEYS else f"{'—':>8}{'—':>8}")
        print(f"{s.label:16}{p[k]:9.2f}{band}")
    print(f"{'シャンク径':16}{p['shank_dia']:9.2f}{0.06:8.2f}{0.25:8.2f}")

    print("\n## フェイシングカーブ（隙間 → ティップからの距離）")
    for g in FEELERS:
        print(f"  {g:5.2f} -> {facing_distance(p, g):6.2f}")
    print(f"  {p['tip_opening']:5.2f} ->   0.00  （＝ティップ開き）")

    print("\n## ボディ径を測る向き（落とし穴）")
    z = profiles.heel_z(p)
    r, ty = profiles.outer_radius(p, z), profiles.table_plane_y(p, z)
    print(f"  最大径の位置 z={z:.2f} / テーブルカットが胴から外れる z="
          f"{profiles.table_cut_end_z(p):.2f}")
    print(f"  テーブルと平行に測る      {2 * r:.2f} mm  ← 正")
    print(f"  テーブル面から反対側へ    {r - ty:.2f} mm  ← 誤（差 {2 * r - (r - ty):.2f}）")

    print("\n## ウィンドウの範囲")
    print(f"  ティップから {p['tip_rail_width']:.2f} → "
          f"{p['tip_rail_width'] + p['window_length']:.2f} mm"
          f"（長さ {p['window_length']:.2f}）")

    print("\n## 判定（実測 − 設計値）")
    # **どの設計に対する判定かを毎回書く。** テンプレートは実測で更新されるので、
    # 印刷した個体の判定は `PRINTED_FROM` を読み込んだときだけ正しい。
    if PRINTED_FROM.lower() in str(a.wproj or "").lower():
        print(f"  対象: {PRINTED_FROM} —— **印刷した個体の設計**。判定は有効")
    else:
        print(f"  **注意: 判定の相手が {PRINTED_FROM} ではない。**"
              "「印刷品」の列はプリンタの再現性を表していない")
        print("  （印刷したのは更新前の設計。テンプレートは PHROX 実測を"
              "取り込んで動いている）")
    print(f"{'項目':14}{'設計値':>8}{'印刷品':>8}{'差':>7}{'判定':>5}"
          f"{'PHROX':>8}{'差':>7}{'判定':>5}{'印−PH':>7}")
    for k, (pr, ref) in MEASURED.items():
        s = specs.get(k)
        if s is None or k not in p:
            continue
        tight, loose = bands(s)
        d1, d2 = pr - p[k], ref - p[k]
        print(f"{s.label:14}{p[k]:8.2f}{pr:8.2f}{d1:+7.2f}"
              f"{verdict(d1, tight, loose, k):>5}"
              f"{ref:8.2f}{d2:+7.2f}{verdict(d2, tight, loose, k):>5}"
              f"{pr - ref:+7.2f}")
    miss = [specs[k].label for k in comp._SURVEY_PARAM_KEYS
            if k in specs and k in p and k not in MEASURED]
    print("  未測: " + " / ".join(miss))

    print("\n## ビーク高さを測る（位置決めの精度要求）")
    z_bite = profiles._BEAK_BITE * p["overall_length"]
    ang = profiles.beak_angle(p)
    slope = math.tan(ang)
    tight_b, loose_b = bands(specs["beak_height"])
    print(f"  バイトポイント z={z_bite:.3f}（={profiles._BEAK_BITE} × 全長）")
    print(f"  テーブル平坦部の始まり z={p['facing_length']:.3f}"
          f"（= facing_length。差 {abs(z_bite - p['facing_length']):.3f} mm）")
    print(f"  稜線の傾き {math.degrees(ang):.2f}° (tan {slope:.3f})"
          f" → z を 1mm 外すと高さが {slope:.3f} mm 動く")
    print(f"  一致帯 ±{tight_b:.2f} に収めるのに要る z の精度  ±{tight_b / slope:.2f} mm")
    print(f"  軽微帯 ±{loose_b:.2f} 〃                        ±{loose_b / slope:.2f} mm")
    print("     z    高さ   d高さ/d(beak_height)")
    for z in sorted({10.0, 15.0, 20.0, round(z_bite, 3), 25.0, 30.0, 35.0, 40.0}):
        h = profiles.beak_apex_y(p, z) - profiles.table_plane_y(p, z)
        q = dict(p)
        q["beak_height"] = p["beak_height"] + 1.0
        h2 = profiles.beak_apex_y(q, z) - profiles.table_plane_y(q, z)
        print(f"  {z:6.2f} {h:7.3f}   {h2 - h:6.3f}")

    print("\n## 対テナー比 —— 実測点。**単一の比は存在しない**")
    tt = inst.templates["tenor"]["mouthpiece"]
    rows = sorted(((specs[k].label, ref, tt[k], ref / tt[k])
                   for k, (_pr, ref) in MEASURED.items() if k in tt),
                  key=lambda r: r[3])
    for lab, ref, ten, r in rows:
        print(f"  {lab:14} PHROX {ref:6.2f} / テナー {ten:6.2f} = {r:.4f}")
    print(f"  幅 {rows[0][3]:.4f} 〜 {rows[-1][3]:.4f}"
          f"（{(rows[-1][3] / rows[0][3] - 1) * 100:.1f}% の開き）"
          f" —— 1 本の比では引けない")

    print(f"\n## 借り物の径比 {LEGACY_DIA_RATIO:.4f} で引いた量のうち、測れた 2 つ")
    print("  （`alto.json` の note が『どちらの比を採るか決まらない』と書いていた群）")
    for k in ("shank_dia", "beak_height"):
        if k not in MEASURED:
            continue
        drv, act = tt[k] * LEGACY_DIA_RATIO, MEASURED[k][1]
        print(f"  {specs[k].label:14} 導出 {drv:6.2f} → 実測 {act:6.2f}"
              f"  {act - drv:+6.2f} mm  {(act / drv - 1) * 100:+5.1f}%")
    # note が心配していた不確かさの大きさ。実測の外れ幅と並べるためだけに出す。
    print(f"  **逆向きに外れている。** note が賭けていた不確かさは"
          f" {tt['beak_height'] * (0.9294 - LEGACY_DIA_RATIO):.2f}mm"
          f"（0.9167 と 0.9294 の差）〜"
          f"{tt['beak_height'] * (0.9448 - LEGACY_DIA_RATIO):.2f}mm（同 0.9448）。"
          f"実測の外れは {abs(MEASURED['beak_height'][1] - tt['beak_height'] * LEGACY_DIA_RATIO):.2f}mm"
          " ＝ **1 桁上**")
    print("  測れないまま残る借り物: サイドレール幅 / バッフル高さ /"
          " ロールオーバ半径 / ティップレール厚 / ティップ面取り")

    print("\n## ビーク高さの下限 —— バッフル天井がビーク下の肉厚に当たる")
    sb = specs["beak_height"]

    def roof_hit(bh: float) -> list[str]:
        """**この探索が探しているのは天井の頭打ちだけ。**

        以前は `cavity_warnings` が空かどうかで二分していたが、あの一覧には
        `beak_height` と無関係な警告（窓の後端・息の通り道）も入る。1 つでも
        混ざると下端でも上端でも真になり、「可動域の全域で当たっている」と
        嘘をつく。種類で絞る。
        """
        return [w for w in profiles.cavity_warnings(dict(p, beak_height=bh))
                if "ビーク下の肉厚" in w]

    # **可動域は `bounds()`（壁）であって帯ではない。** Phase B-4b で
    # `beak_height` に壁が付いたので、`min`/`max` を可動域と呼ぶと下側を
    # 4.3〜5.9mm ぶん取りこぼす（`min`/`max` を可動域の代理として読む型の
    # 再発。Phase A で 4 か所直したのと同じ）。
    t_lo, t_hi = travel(comp, sb, p)
    lo, hi = t_lo, t_hi
    if roof_hit(hi):
        print("  可動域の全域で当たっている")
    elif not roof_hit(lo):
        print("  可動域の全域で当たらない")
    else:
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if roof_hit(mid) else (lo, mid)
        print(f"  当たり始める beak_height = {hi:.3f} mm"
              f"（可動域 {t_lo:.1f}〜{t_hi:.1f}"
              f"、勧める帯 {sb.min:.1f}〜{sb.max:.1f}）")
        for tag, bh in (("設計", p["beak_height"]),
                        ("PHROX 実測", MEASURED.get("beak_height", (0.0, 0.0))[1])):
            if not bh:
                continue
            w = roof_hit(bh)
            print(f"  {tag} {bh:6.2f}（閾値の {bh - hi:+.2f}mm）→ "
                  + (w[0] if w else "警告なし"))

    print("\n## ウィンドウ長の上限（実測が可動域の外に出ることがある）")
    wl_phrox = window_from_ttw(p, PHROX_TTW_MM)
    for wl in sorted({p["window_length"], 37.0, 44.0, round(wl_phrox, 2)}):
        q = dict(p)
        q["window_length"] = wl
        print(f"  指定 {wl:6.2f} → 実効 {profiles.window_length_effective(q):6.2f}"
              f"  不足 {profiles.window_length_shortfall(q):5.2f}"
              f"  in_tune {comp.simulate(q)['tier1']['in_tune_mm']:7.3f}")
    zb = p["overall_length"] - p["bore_length"]
    print(f"  ボアの始まり z={zb:.2f}（全長 {p['overall_length']:.2f}"
          f" − bore_length {p['bore_length']:.2f}）。窓はその"
          f" {WINDOW_TO_BORE_GAP_MM:.1f}mm 手前で止まる")
    # **上限は後縁の位置だけで決まる。** tip_rail_width の仮定に依らない。
    need = PHROX_TTW_MM + WINDOW_TO_BORE_GAP_MM
    bl = p["overall_length"] - need
    print(f"  PHROX の後縁 {PHROX_TTW_MM:.2f}（実測）を成立させるには"
          f" ボアの始まり ≥ {need:.2f} ＝ **bore_length ≤ {bl:.2f}**"
          f"（比 {bl / p['overall_length']:.4f}"
          f" / 現行 {p['bore_length'] / p['overall_length']:.4f}）")
    print("  **この上限は tip_rail_width の仮定に依らない** —— 後縁の位置だけで決まる")

    print("\n## ティップ端 → 窓の後縁（§5.2 の決着）")
    design_ttw = p["tip_rail_width"] + p["window_length"]
    tight_w, loose_w = bands(specs["window_length"])
    print(f"  設計 {design_ttw:.2f} = tip_rail_width {p['tip_rail_width']:.2f}"
          f" + window_length {p['window_length']:.2f}"
          f"  （帯は window_length と同じ ±{tight_w:.2f} / ±{loose_w:.2f}）")
    print("  **窓の開口長は 1 度も測っていない** —— 09-02 に「ウィンドウ長」として"
          "記録した値もこの量だった（実測者に確認、2026-09-05）")
    print(f"  {'':6}{'09-02':>8}{'09-05':>8}{'平均':>8}{'幅':>7}"
          f"{'設計との差':>11}{'判定':>6}")
    for tag in ("printed", "phrox"):
        lab = "印刷品" if tag == "printed" else "PHROX"
        a, b = TIP_TO_WINDOW_REAR[tag]
        m, sp = ttw_mean(tag), ttw_spread(tag)
        d = m - design_ttw
        # **読みの幅が一致帯より広ければ判定を出さない。** 1 回の読みを想定した
        # 帯を、幅のある量に当てると持っていない分解能で合否を言うことになる。
        v = verdict(d, tight_w, loose_w, "tip_to_window_rear")
        if sp > tight_w:
            v = "—"
        print(f"  {lab:6}{a:8.2f}{b:8.2f}{m:8.2f}{sp:7.2f}{d:+11.2f}{v:>6}")
    print(f"  **PHROX の幅は {ttw_spread('phrox'):.2f}、印刷品は"
          f" {ttw_spread('printed'):.2f}** —— 印刷品の窓は角の立った矩形、PHROX は"
          "角丸のスロット（§11.5）なので、**ばらつきの向きが形の予想と逆**。理由は未解明")
    print(f"  印刷品は幅 {ttw_spread('printed'):.2f} が軽微帯 ±{loose_w:.2f} と同じ桁で、"
          f"**符号が割れている**（{TIP_TO_WINDOW_REAR['printed'][0] - design_ttw:+.2f} と"
          f" {TIP_TO_WINDOW_REAR['printed'][1] - design_ttw:+.2f}）。判定は出さない")
    print(f"  印−PH（平均どうし） {ttw_mean('printed') - ttw_mean('phrox'):+.2f}")
    print(f"  **PHROX {PHROX_TTW_MM:.2f} が §5.2 の決着** —— 予想は「40 付近なら窓は"
          "本当に長く bore_length が誤り、36 付近なら測っていた量が違った」で、**40 側**")

    print("\n## bore_length と合う挿し込み量（**吹奏と突き合わせる**）")
    print("  `bore_length` 49.05 は実測ではない。ウィンドウ長の実測とも吹奏とも合わない")
    it0 = comp.simulate(p)["tier1"]["in_tune_mm"]
    cav0 = profiles.cavity_volume_cc(p)["effective_cc"]

    def in_tune_of(bl: float, base: dict | None = None) -> float:
        return comp.simulate(dict(base or p, bore_length=bl))["tier1"]["in_tune_mm"]

    print(f"  {'bore_length':>12}{'in_tune':>9}{'Δin_tune':>10}"
          f"{'実効容積':>10}{'Δ容積':>9}")
    for bl in sorted({p["bore_length"], 48.0, 47.67, 47.0, 46.0, 45.0, 44.0, 42.0},
                     reverse=True):
        it = in_tune_of(bl)
        cc = profiles.cavity_volume_cc(dict(p, bore_length=bl))["effective_cc"]
        print(f"  {bl:12.2f}{it:9.2f}{it - it0:+10.2f}{cc:10.3f}{cc - cav0:+9.3f}")

    def solve_bore(delta: float, base: dict, ref: float) -> float | None:
        """Δin_tune = delta を与える bore_length。届かなければ None。"""
        lo, hi, target = 35.0, base["bore_length"], ref - delta
        if not in_tune_of(lo, base) <= target <= ref:
            return None
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if in_tune_of(mid, base) < target else (lo, mid)
        return 0.5 * (lo + hi)

    # **申告と実測を並べる。** 前便は申告 3mm のほうを測定として扱い、窓の逆算と
    # 0.06mm で一致すると書いた。実測 6.0mm は 49.05 の唯一の根拠（3 サイズで比が
    # 0.3% に揃う）を 1 桁大きく外す。**撤回の幅をここで出す。**
    print("  --- 差を与える bore_length（**目視の申告と実測を並べる**）---")
    for tag, d in ((f"前便の目視申告 {INSERTION_DELTA_REPORTED_MM:.0f}mm",
                    INSERTION_DELTA_REPORTED_MM),
                   (f"実測 {insertion_delta():.1f}mm", insertion_delta())):
        bl = solve_bore(d, p, it0)
        if bl is None:
            print(f"  {tag}: 可動域内に解が無い")
            continue
        r = bl / p["overall_length"]
        print(f"  {tag}: bore_length {bl:6.2f}（比 {r:.4f}）"
              f" —— soprano {BORE_RATIO_SOPRANO} / tenor {BORE_RATIO_TENOR} の揃いから"
              f" {(r / BORE_RATIO_TENOR - 1) * 100:+.0f}%")

    bl_wl = p["overall_length"] - (PHROX_TTW_MM + WINDOW_TO_BORE_GAP_MM)
    print(f"  PHROX の窓の後縁 {PHROX_TTW_MM:.2f} が要求する上限"
          f"   **bore_length ≤ {bl_wl:.2f}**"
          f"（比 {bl_wl / p['overall_length']:.4f}）"
          " —— **こちらは音を 1 ビットも使っていない**")

    # 感度。容積で見ると小さいが、**モデルのチェンバー系のつまみでは作れない**
    # （下の掃引）。前便はここで「チェンバー形状の差だけでも出る」と逃げていた。
    d_cc = (cav0 - profiles.cavity_volume_cc(dict(p, bore_length=47.0))["effective_cc"])
    d_it = it0 - in_tune_of(47.0)
    dl = insertion_delta()
    print(f"  感度 {d_cc / d_it:.3f} cc/mm —— 挿し込み {dl:.1f}mm は"
          f" 実効容積 {d_cc / d_it * dl:.2f}cc ＝ 全体の"
          f" {d_cc / d_it * dl / cav0 * 100:.1f}%。**容積では小さいが、"
          "つまみでは作れない**（下の掃引）")

    print("\n## 実測形状どうしで比べる（**モデルは差の向きを外している**）")
    # 印刷品も PHROX も、それぞれの実測を入れた形で組み直す。片方だけ実測を
    # 入れると「どちらの実物か」が混ざる。bore_length など未実測の量は共通のまま。
    # ティップ端→窓の後縁は `window_length` へ直して入れる（tip_rail_width は設計値）。
    tpl_mp = dict(inst.templates[tid]["mouthpiece"])

    def measured_model(base: dict, idx: int, ttw: float | None = None,
                       **kw) -> dict:
        q = dict(base)
        for k, pair in MEASURED.items():
            if k in q:
                q[k] = pair[idx]
        tag = ("printed", "phrox")[idx]
        q["window_length"] = window_from_ttw(
            q, ttw if ttw is not None else ttw_mean(tag))
        q.update(kw)
        return q

    m_pr, m_ph = measured_model(p, 0), measured_model(tpl_mp, 1)
    it_pr = comp.simulate(m_pr)["tier1"]["in_tune_mm"]
    it_ph = comp.simulate(m_ph)["tier1"]["in_tune_mm"]
    dl = insertion_delta()
    print(f"  印刷品（実測形状） in_tune {it_pr:6.2f} /"
          f" PHROX（実測形状） in_tune {it_ph:6.2f}"
          f"  → **モデルの差 {it_pr - it_ph:+.2f}mm**")
    print(f"  実測の差 **{dl:+.2f}mm**"
          f"（印刷品 {INSERTION_MM['printed']} / PHROX {INSERTION_MM['phrox']}、2 回の読み）")
    print("  **mm どうしなら音が違っても比べてよい** —— 形状差が作るセントも"
          "挿し込みが作るセントも同じ 1/L で伸びるので、割り算した mm は音に依らない")

    print("\n## その差を作れるつまみがあるか（PHROX 側を可動域の全域で振る）")
    print("  **「届かない」も結果として残す。** 前便は「チェンバー形状の差だけでも"
          "出る」と書いたが、モデルのつまみでは作れない")
    for k in ("bore_length", "window_length", "chamber_ratio", "baffle_height",
              "throat_ratio", "bore_dia"):
        s = specs.get(k)
        if s is None or k not in m_ph:
            continue
        n = 24
        # **ここも「可動域」と言いながら帯を読んでいた**（代理変数の 7 例目）。
        # `bore_length` / `bore_dia` は相手で動く壁を持つので、帯で振ると
        # 「つまみでは届かない」の判定が実際より狭い範囲で出る。
        v_lo, v_hi = travel(comp, s, m_ph)
        vals = [v_lo + (v_hi - v_lo) * i / n for i in range(n + 1)]
        ds = [it_pr - comp.simulate(dict(m_ph, **{k: v}))["tier1"]["in_tune_mm"]
              for v in vals]
        hits = [(vals[i], vals[i + 1]) for i in range(n)
                if (ds[i] - dl) * (ds[i + 1] - dl) <= 0]
        head = (f"  {s.label:14} 可動域 {v_lo:6.2f}〜{v_hi:6.2f}"
                f" → Δ {min(ds):+6.2f}〜{max(ds):+6.2f}")
        if not hits:
            print(head + "  **届かない**")
            continue
        found = []
        for a, b in hits:
            fa = it_pr - comp.simulate(dict(m_ph, **{k: a}))["tier1"]["in_tune_mm"]
            for _ in range(30):
                mid = 0.5 * (a + b)
                fm = it_pr - comp.simulate(dict(m_ph, **{k: mid}))["tier1"]["in_tune_mm"]
                if (fm < dl) == (fa < dl):
                    a, fa = mid, fm
                else:
                    b = mid
            found.append(0.5 * (a + b))
        note = ""
        if k == "bore_length":
            note = "（比 " + " / ".join(
                f"{v / m_ph['overall_length']:.4f}"
                f"・揃いから{(v / m_ph['overall_length'] / BORE_RATIO_TENOR - 1) * 100:+.0f}%"
                for v in found) + "）"
            if len(found) > 1:
                note += (" ※大きい側の根は**窓のクランプ**"
                         "（ボアを伸ばすと窓が潰れて容積が落ちる）で、形の話ではない")
        print(head + "  → " + " / ".join(f"{v:.2f}" for v in found) + note)
    print(f"  ※ `chamber_ratio` の既定 {m_ph['chamber_ratio']:.2f} は"
          f"**可動域の下限** —— モデルは PHROX のチェンバーを小さくできない")
    print("  言えるのは「**モデルの表現力の外**」まで。"
          "実物のチェンバーが作れないという意味ではない（可動域が狭いのかもしれない）")

    print("\n## 実測の挿し込み位置を実用域に当てる")
    from saxsketch.acoustics.volume import TUNING_MARGIN_MM
    t1_ph = comp.simulate(m_ph)["tier1"]
    lo_r, hi_r = t1_ph["cork_range_mm"]
    print(f"  実用域 {lo_r:.1f}〜{hi_r:.1f}mm"
          f"（上限は同じ PHROX を YAS-875 に押し込んだ実測。余裕の閾値"
          f" {TUNING_MARGIN_MM:.1f}mm）")
    for tag, v in INSERTION_MM.items():
        lab = "印刷品" if tag == "printed" else "PHROX"
        room = hi_r - v
        print(f"  {lab:6} {v:5.1f}mm  深い側の余地 {room:+.1f}mm"
              + ("  ← **閾値を切っている**" if room < TUNING_MARGIN_MM else ""))
    print("  **上限は PHROX を押し込んで測った値。** 印刷品自身の止まりは未測で、"
          "ボアが太く締め代が半減しているぶん、もっと奥まで行きうる（組の性質）")
    print(f"  **`status` は in_tune {t1_ph['in_tune_mm']:.2f} の位置で見るので"
          f" {t1_ph['status']} を返す。** 判定している点と楽器が使われている点が"
          f" {min(INSERTION_MM.values()) - t1_ph['in_tune_mm']:.1f}〜"
          f"{max(INSERTION_MM.values()) - t1_ph['in_tune_mm']:.1f}mm 離れている")

    print("\n## in_tune の絶対照合 —— **比較できる量ではなかった**")
    t1_tpl = comp.simulate(tpl_mp)["tier1"]
    for tag, t1x in (("テンプレート素", t1_tpl), ("PHROX 実測形状", t1_ph)):
        print(f"  {tag:14} in_tune {t1x['in_tune_mm']:6.2f}mm 対 実演奏位置"
              f" {INSERTION_MM['phrox']:.1f}mm ="
              f" **{INSERTION_MM['phrox'] - t1x['in_tune_mm']:+.1f}mm**")
    print("  ただしモデルの胴は**ベルが音響へ接続されていない**"
          "（`alto.json` body_note: 接続すると全閉の第1共鳴が +38〜+106 セント動く）:")
    # **両方の baseline で出す。** cents_per_mm は形で 2.5 倍動く（下）ので、
    # 片方だけ出すと「実物はこれだけ動く」と言ったことになる。
    for c in (38.0, 106.0):
        print(f"    {c:5.0f} セント → "
              + " / ".join(
                  f"{c / t1x['cents_per_mm']:.0f}mm（{tag} {t1x['cents_per_mm']:.2f} ¢/mm）"
                  for tag, t1x in (("素", t1_tpl), ("実測形状", t1_ph)))
              + f" 相当（実用域 {hi_r - lo_r:.1f}mm）")
    print("  トーンホールも無く、気温は 25°C 固定。**免責は脚注ではなく本体**"
          " ——「基準条件での値」の幅が可動域より桁で大きい")
    print("  **差のほうは比較できる**（胴・ベル・気温は差で消える）。その差で"
          f"モデル {it_pr - it_ph:+.2f}mm 対 実測 {dl:+.2f}mm")

    # cents_per_mm は形状で大きく動く。テンプレート素と PHROX 実測形状で 2.6 倍。
    # §11.8 は「1/L 則 1.38 とモデル 0.49 が 2.8 倍食い違う」と書いたが、
    # その 0.49 は**未実測のテンプレート**の値だった。
    import math as _m
    from saxsketch.acoustics import openwind_bridge as _ob
    _k = 1200.0 / _m.log(2.0)
    _L1 = _ob.C_SOUND / (2.0 * float(comp.size_info["low_note_sounding_hz"])) * 1000.0
    print(f"  なお `cents_per_mm` は形で動く: テンプレート素"
          f" {t1_tpl['cents_per_mm']:.2f} → PHROX 実測形状 {t1_ph['cents_per_mm']:.2f}"
          f" ¢/mm（{t1_ph['cents_per_mm'] / t1_tpl['cents_per_mm']:.1f} 倍）。"
          f"同じ音の 1/L 則 {_k / _L1:.2f} との食い違いは"
          f" それぞれ {_k / _L1 / t1_tpl['cents_per_mm']:.1f} 倍 /"
          f" {_k / _L1 / t1_ph['cents_per_mm']:.1f} 倍")
    print(f"  window_length {m_ph['window_length']:.2f} は実効"
          f" {profiles.window_length_effective(m_ph):.2f}"
          f"（不足 {profiles.window_length_shortfall(m_ph):.2f}）")
    print("  **`cents_per_mm` は `cork_depth` での局所の傾き。** `cork_depth` が"
          "零点から離れていると別の点の傾きを読むので、形を変えたら必ず引き直す")

    print("\n## 感度は音ごとに違う（モデルが解いているのは全閉最低音だけ）")
    from saxsketch.acoustics import openwind_bridge as ob
    si = comp.size_info
    f1 = float(si["low_note_sounding_hz"])
    t1s = comp.simulate(p)["tier1"]
    print(f"  モデルの cents_per_mm = {t1s['cents_per_mm']:.2f} セント/mm。"
          f"これは**{si['low_note_label']} {f1:.2f}Hz（全閉）の値**")
    print("  `_assemble_resonator` はトーンホールを持たず、空洞＋円筒ボア＋"
          "欠損円錐延長の 1 本しか組まない（openwind_bridge.py）")
    k = 1200.0 / math.log(2.0)          # Δcents ≈ k·δ/L
    ln1 = ob.C_SOUND / (2.0 * f1) * 1000.0
    print(f"  理想円錐の 1/L 則（Δcents ≈ {k:.0f}·δ/L）だと同じ音で"
          f" {k / ln1:.2f} セント/mm —— **モデルの {t1s['cents_per_mm']:.2f} と"
          f" {k / ln1 / t1s['cents_per_mm']:.1f} 倍食い違う**")
    print("  （挿し込みが縮めるのは円錐の**細い端**で、そこは体積速度が小さい。"
          "1/L 則は端の位置を問わないので過大に出る。どちらが実物かは未検証）")
    print("  **確かなのは比のほう**: 感度は 1/L で伸びるので、短い（高い）音ほど敏感。")
    print(f"  {'音':26}{'L [mm]':>9}{'1/L 則':>10}{'モデル基準':>11}")
    for lab, f in ((f"全閉最低音 {si['low_note_label']} {f1:.2f}Hz", f1),
                   ("録音の下端 E3 163.9Hz", 163.9),
                   ("チューニング音 A=440Hz", 440.0),
                   ("チューニング音 A=442Hz", 442.0),
                   ("録音の上端 B4 497.2Hz", 497.2)):
        ln = ob.C_SOUND / (2.0 * f) * 1000.0
        print(f"  {lab:26}{ln:9.1f}{k / ln:8.2f} ¢/mm"
              f"{t1s['cents_per_mm'] * ln1 / ln:9.2f} ¢/mm")
    print(f"  チューニング音は全閉最低音の {ln1 / (ob.C_SOUND / 880.0 * 1000.0):.1f} 倍敏感"
          " —— 全閉最低音の感度で「絶対位置は弱い指標」と言うと 1 桁外す")

    # §11.6 の「11 セントを挿し込みで説明するには 22mm 要る」を測り直す。
    # **両方の基準で出す。** 片方だけだと「実物はこうだ」と言ったことになる。
    # 09-02 の 2 本の中央値の差。**A=442 基準で測り直した値**（当初は基準を 440 と
    # 仮定して 10.9 と書いていた。基準は中央値を平行移動するだけなので差は動かず、
    # 0.1 の違いは中央値の丸め）。
    for cents in (10.8,):
        lo_l = ob.C_SOUND / (2.0 * 497.2) * 1000.0
        hi_l = ob.C_SOUND / (2.0 * 163.9) * 1000.0
        print(f"  中央値のずれ {cents:.1f} セントを挿し込みで説明するのに要る量"
              "（録音の音域 E3〜B4）:")
        print(f"    1/L 則基準    {cents / (k / lo_l):5.1f} 〜 {cents / (k / hi_l):5.1f} mm")
        print(f"    モデル基準    {cents / (t1s['cents_per_mm'] * ln1 / lo_l):5.1f}"
              f" 〜 {cents / (t1s['cents_per_mm'] * ln1 / hi_l):5.1f} mm")
        print(f"    §11.6 が書いた値（全閉最低音の感度をそのまま当てた）"
              f" {cents / t1s['cents_per_mm']:.0f} mm")


    print("\n## 音響（Tier1）")
    t1 = comp.simulate(p)["tier1"]
    print(f"  合う挿し込み量 {t1['in_tune_mm']:.2f} mm / 感度 {t1['cents_per_mm']:.2f} "
          f"セント/mm / 実用域 {t1['cork_range_mm'][0]:.1f}〜{t1['cork_range_mm'][1]:.1f}")
    cav = profiles.cavity_volume_cc(p)
    print(f"  内部容積 {cav['total_cc']:.2f} cc（実効 {cav['effective_cc']:.2f}）")

    print("\n## 質量（ソリッド体積 × 密度）")
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    part = comp.build(p)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(part.wrapped, props)
    vol_cc = props.Mass() / 1000.0
    dens = MAT_DENSITY.get(p.get("material", "resin"), 1.15)
    print(f"  体積 {vol_cc:.2f} cc × {dens} g/cc = {vol_cc * dens:.1f} g")


if __name__ == "__main__":
    main()
