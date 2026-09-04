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
    "window_length":  (35.30, 39.30),
    # 第2便（2026-09-05）。手順は §5.1（ティップ端でノギスをロックして和紙テープ）。
    "beak_height":    (13.60, 11.60),
}

#: `alto.json` が**径量**に使っていた借り物の比（規格リード全長 71.5/78.0）。
#: 実測でこの比が存在しないことが確定したあとも、テンプレートを実測で上書きした値が
#: 「何から引かれていたか」を示せるように残す。テンプレートの現在値から逆算すると
#: 上書き済みの量では差が 0 になり、**外れていた幅が見えなくなる**。
LEGACY_DIA_RATIO = 71.5 / 78.0

#: 実測の挿し込み量差 [mm]（印刷品 − PHROX、2026-09-05 の吹奏）。印刷品のほうが
#: これだけ**奥**まで差さないと 442Hz に合わなかった。
#: **申告は「3mm くらい」で 1 回の読み。誤差棒はまだ無い**（組の取り方は §11.7）。
INSERTION_DELTA_MM = 3.0

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
    lo, hi = sb.min, sb.max
    if profiles.cavity_warnings(dict(p, beak_height=hi)):
        print("  可動域の全域で当たっている")
    elif not profiles.cavity_warnings(dict(p, beak_height=lo)):
        print("  可動域の全域で当たらない")
    else:
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = ((mid, hi) if profiles.cavity_warnings(dict(p, beak_height=mid))
                      else (lo, mid))
        print(f"  当たり始める beak_height = {hi:.3f} mm"
              f"（可動域 {sb.min:.1f}〜{sb.max:.1f}）")
        for tag, bh in (("設計", p["beak_height"]),
                        ("PHROX 実測", MEASURED.get("beak_height", (0.0, 0.0))[1])):
            if not bh:
                continue
            w = profiles.cavity_warnings(dict(p, beak_height=bh))
            print(f"  {tag} {bh:6.2f}（閾値の {bh - hi:+.2f}mm）→ "
                  + (w[0] if w else "警告なし"))

    print("\n## ウィンドウ長の上限（実測が可動域の外に出ることがある）")
    probes = {p["window_length"], 37.0, 44.0}
    if "window_length" in MEASURED:
        probes.add(MEASURED["window_length"][1])
    for wl in sorted(probes):
        q = dict(p)
        q["window_length"] = wl
        print(f"  指定 {wl:6.2f} → 実効 {profiles.window_length_effective(q):6.2f}"
              f"  不足 {profiles.window_length_shortfall(q):5.2f}"
              f"  in_tune {comp.simulate(q)['tier1']['in_tune_mm']:7.3f}")
    zb = p["overall_length"] - p["bore_length"]
    print(f"  ボアの始まり z={zb:.2f}（全長 {p['overall_length']:.2f}"
          f" − bore_length {p['bore_length']:.2f}）。窓はその 4.0mm 手前で止まる")
    if "window_length" in MEASURED:
        need = profiles.window_front_z(p) + MEASURED["window_length"][1] + 4.0
        bl = p["overall_length"] - need
        print(f"  実測 {MEASURED['window_length'][1]:.2f} を成立させるには"
              f" ボアの始まり ≥ {need:.2f} ＝ bore_length ≤ {bl:.2f}"
              f"（比 {bl / p['overall_length']:.4f}"
              f" / 現行 {p['bore_length'] / p['overall_length']:.4f}）")

    print("\n## bore_length と合う挿し込み量（**吹奏の 3mm と突き合わせる**）")
    print("  `bore_length` 49.05 は実測ではない。ウィンドウ長の実測とも吹奏とも合わない")
    it0 = comp.simulate(p)["tier1"]["in_tune_mm"]
    cav0 = profiles.cavity_volume_cc(p)["effective_cc"]

    def in_tune_of(bl: float) -> float:
        return comp.simulate(dict(p, bore_length=bl))["tier1"]["in_tune_mm"]

    print(f"  {'bore_length':>12}{'in_tune':>9}{'Δin_tune':>10}"
          f"{'実効容積':>10}{'Δ容積':>9}")
    for bl in sorted({p["bore_length"], 48.0, 47.67, 47.0, 46.0}, reverse=True):
        it = in_tune_of(bl)
        cc = profiles.cavity_volume_cc(dict(p, bore_length=bl))["effective_cc"]
        print(f"  {bl:12.2f}{it:9.2f}{it - it0:+10.2f}{cc:10.3f}{cc - cav0:+9.3f}")

    # 実測の挿し込み差を与える bore_length。**これは「犯人が bore_length なら」の値**で、
    # チェンバー形状の差でも同じ挿し込み差は出る（下の感度を見ること）。
    target = it0 - INSERTION_DELTA_MM
    lo, hi = 40.0, p["bore_length"]
    if in_tune_of(lo) <= target <= it0:
        for _ in range(16):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if in_tune_of(mid) < target else (lo, mid)
        bl_ac = 0.5 * (lo + hi)
        print(f"  実測の挿し込み差 {INSERTION_DELTA_MM:.1f}mm を与える bore_length"
              f" = {bl_ac:.2f}（比 {bl_ac / p['overall_length']:.4f}）")
    if "window_length" in MEASURED:
        need = profiles.window_front_z(p) + MEASURED["window_length"][1] + 4.0
        bl_wl = p["overall_length"] - need
        print(f"  ウィンドウ長の実測が要求する上限   bore_length ≤ {bl_wl:.2f}"
              f"（比 {bl_wl / p['overall_length']:.4f}）")
        print("  **この 2 つは独立**（片方はノギスと幾何だけ、片方はチューナーだけ）")

    # 感度。3mm は容積で見るとごく小さい ＝ bore_length 以外でも同じ差が出る。
    d_cc = (cav0 - profiles.cavity_volume_cc(dict(p, bore_length=47.0))["effective_cc"])
    d_it = it0 - in_tune_of(47.0)
    print(f"  感度 {d_cc / d_it:.3f} cc/mm —— 挿し込み {INSERTION_DELTA_MM:.1f}mm は"
          f" 実効容積 {d_cc / d_it * INSERTION_DELTA_MM:.2f}cc ＝ 全体の"
          f" {d_cc / d_it * INSERTION_DELTA_MM / cav0 * 100:.1f}%。"
          "チェンバー形状の差だけでも出る量で、断定はできない")

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
    for cents in (10.9,):
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
