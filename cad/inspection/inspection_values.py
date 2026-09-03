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
}

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

    print("\n## 径比の候補（ビーク高さで見分ける）")
    tt = inst.templates["tenor"]["mouthpiece"]
    # 現行の比は書かずに引く。テンプレートが持っているのは値だけなので、
    # 「どの比で引いたか」は 2 サイズの割り算でしか確かめられない。
    cands = [(f"現行（径比 {p['shank_dia'] / tt['shank_dia']:.4f}・借り物）",
              p["shank_dia"] / tt["shank_dia"])]
    for k in ("bore_dia", "body_dia", "shank_dia"):
        if k not in MEASURED:
            continue
        r = MEASURED[k][1] / tt[k]
        cands.append((f"{specs[k].label}比 {r:.4f}"
                      f"（PHROX {MEASURED[k][1]:.2f} / テナー {tt[k]:.2f}）", r))
    for name, r in cands:
        pred = tt["beak_height"] * r
        print(f"  {name:40} → {pred:7.3f}"
              f"  (現行 {p['beak_height']:.2f} との差 {pred - p['beak_height']:+6.3f})")
    print(f"  ノギス分解能 0.05 / 一致帯 ±{tight_b:.2f}"
          f" —— 差がこれ以下の候補は見分けられない")

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
