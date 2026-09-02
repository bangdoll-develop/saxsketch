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
