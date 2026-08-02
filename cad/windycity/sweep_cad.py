# -*- coding: utf-8 -*-
"""STEP 用プリミティブ表現（`build_cad`）のブーリアン健全性をパラメータ掃引で確かめる。

プリミティブ化で一番怖いのは**面と面が接する条件**（フェイシング円弧とテーブル平面の
接点、ビークブレンドと胴の G1 接続、空洞末端とボア）で、OCCT のブーリアンはここが
最も苦手。多角形＋ルールドの表現はまさにそれを避けるための選択だったので、
極端なパラメータで壊れないことを実際に振って確かめる。

落ちても `build_cad` は `build()` へフォールバックするので出力は失われないが、
フォールバックが起きた組合せは把握しておく（STEP が重いままになる）。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_cad.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.core.registry import get_registry  # noqa: E402

#: 端に振る設計パラ。形が接する所へ効くものを選ぶ。
SWEEP_KEYS = ["tip_opening", "facing_length", "tip_rail_width", "tip_rail_thickness",
              "tip_chamfer", "side_rail_width", "baffle_height", "table_angle"]


def _cases(comp, base: dict) -> list[tuple[str, dict]]:
    specs = {s.key: s for s in comp.param_specs()}
    out: list[tuple[str, dict]] = [("既定", dict(base))]
    for shape in ["round", "square", "horseshoe", "flat_sidewall"]:
        out.append((f"chamber={shape}", dict(base, chamber_shape=shape)))
    for bt in ["straight", "rollover", "step", "curve"]:
        out.append((f"baffle={bt}", dict(base, baffle_type=bt)))
    for curve in ["radial", "elliptic"]:
        out.append((f"facing={curve}", dict(base, facing_curve=curve)))
    for k in SWEEP_KEYS:
        s = specs.get(k)
        if s is None or s.min is None or s.max is None:
            continue
        for tag, v in (("min", s.min), ("max", s.max)):
            out.append((f"{k}={tag}({v:g})", dict(base, **{k: v})))
    return out


def main() -> int:
    reg = get_registry()
    bad: list[str] = []
    for size in ("tenor", "alto", "soprano"):
        comp = reg.get("saxophone").make_component("mouthpiece", size)
        base = {s.key: s.default for s in comp.param_specs()}
        print(f"== {size} ==", flush=True)
        for label, p in _cases(comp, base):
            t0 = time.time()
            try:
                # フォールバックを挟まない生の経路。壊れたらここで例外になる。
                part = comp._build_cad(p)
                solids = len(part.solids())
                good = bool(part.is_valid) and solids == 1 and part.volume > 1000.0
                note = "" if good else f"*** NG valid={part.is_valid} solids={solids}"
            except Exception as exc:                      # noqa: BLE001
                good, note = False, f"*** RAISED {type(exc).__name__}: {exc}"
            if not good:
                bad.append(f"{size} / {label}: {note}")
            print("  %-28s %5.1fs %s" % (label, time.time() - t0, note or "ok"),
                  flush=True)
    print()
    if bad:
        print("FALLBACK が要る組合せ:")
        for b in bad:
            print("  -", b)
        print("SOME_FAIL")
        return 1
    print("ALL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
