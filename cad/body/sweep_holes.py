# -*- coding: utf-8 -*-
"""側孔（Phase 4-B.2b）を掃引して、3 つを別々に測る。

1. **ブーリアンの費用** —— 穴を開けるとビルドが何秒増えるか。管体のブーリアンは
   1 回 7〜17 秒かかり、7〜8 回積むと WSL2 の VM ごと落ちる（`cad/body/README.md`）。
   `body._apply_holes` はチムニーの和と貫通の差を **1 回ずつ**にまとめてあるが、
   本数を増やしても増えないかは測らないと分からない。
2. **2 つのエンジンが同じ楽器を解いているか** —— TMM の分岐行列は Dubos ら 1999 を
   原典から書いたもの（OpenWind の `JunctionTjoint` も同じ原典）で、
   合っているかは文献を読んだだけでは決めずここで測る。
   **見るのは差の絶対値ではなく、穴を足したことで差が増えるかどうか**
   （穴無しでも 2 エンジンは 2.9〜5.6 セント違う。損失と放射モデルの違い）。
3. **0 次配置の残差と、つまみの効き** —— 4-B.2c が潰す量と、潰すのに使える幅。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/body/sweep_holes.py acoustics
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/body/sweep_holes.py build alto
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/body/sweep_holes.py build alto 3 4

`acoustics` は OCCT を触らないので速い（数秒）。`build` は重いので
**サイズごと・数通りごとに分けて回す**（第 2・第 3 引数が開始番号と本数）。
落ちたら `wsl --shutdown` → 8 秒待つ → 続きの番号から。
**pytest と同時に回さない。**
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.acoustics import openwind_bridge as ob  # noqa: E402
from saxsketch.acoustics import toneholes  # noqa: E402
from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.instruments.saxophone.components import body_profiles as bpf  # noqa: E402

SIZES = ("soprano", "alto", "tenor")


def _comp(size: str):
    comp = get_registry().get("saxophone").make_component("body", size)
    from saxsketch.core.schema import ParamSet
    base = dict(ParamSet(comp.param_specs(), comp.template["body"]).values)
    return comp, base, comp._neck()


# ------------------------------------------------------------------ 1. ビルド

def _build_cases(base: dict) -> list[tuple[str, dict]]:
    out = [("穴なし", dict(base, finger_holes=0, thumb_vent="off")),
           ("親指孔だけ", dict(base, finger_holes=0)),
           ("既定(7孔+親指)", dict(base))]
    for n in (1, 3, 5):
        out.append((f"{n}孔+親指", dict(base, finger_holes=n)))
    out.append(("穴径 max", dict(base, hole_dia=14.0)))
    out.append(("チムニー max", dict(base, hole_chimney=8.0)))
    out.append(("一体型×既定", dict(base, neck_joint="integrated")))
    out.append(("ストレート×既定", dict(base, bow_angle=0.0)))
    return out


def sweep_build(argv: list[str]) -> int:
    sizes = tuple(a for a in argv if a in SIZES) or SIZES
    nums = [int(a) for a in argv if a.isdigit()]
    start = nums[0] if nums else 0
    limit = nums[1] if len(nums) > 1 else 10 ** 6
    bad: list[str] = []
    for size in sizes:
        comp, base, neck = _comp(size)
        cases = _build_cases(base)
        print(f"== {size} ==  ({start}..{min(start + limit, len(cases)) - 1} / "
              f"全 {len(cases)} 通り)", flush=True)
        for idx, (label, p) in enumerate(cases):
            if not (start <= idx < start + limit):
                continue
            err = comp.params_error(p)
            if err is not None:
                print("  %-18s   ---   弾いた: %s" % (label, err[:60]), flush=True)
                continue
            nh = len(bpf.hole_layout(p, comp.size_info, neck))
            t0 = time.time()
            try:
                part = comp.build(p)
                solids = len(part.solids())
                good = bool(part.is_valid) and solids == 1 and part.volume > 1000.0
                note = "" if good else f"*** NG valid={part.is_valid} solids={solids}"
                vol = part.volume / 1000.0
            except Exception as exc:                      # noqa: BLE001
                good, note, vol = False, f"*** RAISED {type(exc).__name__}: {exc}", 0.0
            if not good:
                bad.append(f"{size} / {label}: {note}")
            print("  %-18s %6.2fs  穴%2d  %7.1fcc  %s"
                  % (label, time.time() - t0, nh, vol, note or "ok"), flush=True)
    if bad:
        print("壊れた組合せ:")
        for b in bad:
            print("  -", b)
        print("SOME_FAIL")
        return 1
    print("ALL_PASS")
    return 0


# ------------------------------------------------------------------ 2/3. 音響

def _engine_row(size: str, comp, p: dict, neck: dict) -> None:
    """同じ穴つき管を TMM と OpenWind で解いて並べる。"""
    import numpy as np

    si = comp.size_info
    geo = ob.ideal_cone_geometry(si, use_openwind=False)
    holes = bpf.acoustic_holes(p, si, neck)
    fings = toneholes.successive_fingerings(holes)
    f_low = float(si["low_note_sounding_hz"])
    freqs = np.geomspace(0.6 * f_low, 3.6 * f_low, 600)
    if not ob.HAS_OPENWIND:
        print("  OpenWind 未導入 —— エンジン照合は飛ばす")
        return
    from openwind import ImpedanceComputation
    rows = ob.ow_hole_rows(holes)
    chart = ob.ow_fingering_rows(holes, fings)
    print("  %-8s %10s %10s %8s" % ("運指", "TMM", "OpenWind", "差[c]"))
    for name, flags in fings:
        ft = ob._lowest_peak_hz(freqs, ob._tmm_impedance(geo, freqs, holes, flags))
        r = ImpedanceComputation(freqs, geo, holes_valves=rows, fingering_chart=chart,
                                 temperature=ob.TEMPERATURE_C,
                                 source_location="entrance", note=name)
        fo = ob._lowest_peak_hz(freqs, np.asarray(r.impedance))
        print("  %-8s %9.2fHz %9.2fHz %+8.1f"
              % (name, ft, fo, 1200.0 * math.log2(ft / fo)), flush=True)


def sweep_acoustics(argv: list[str]) -> int:
    sizes = tuple(a for a in argv if a in SIZES) or SIZES
    for size in sizes:
        comp, base, neck = _comp(size)
        si = comp.size_info
        print(f"== {size} ==", flush=True)

        # 0 次配置の残差
        card = comp._scale_card(base)
        print("  0 次配置の残差:", card["big"])
        for r in card["rows"]:
            print("    %-24s %s" % (r[0], r[1]))

        # つまみの効きを広く（カードは +1mm だけ）
        solver, holes = comp._solver(base)
        b = [x["cents"] for x in solver.scale() if x["name"] != "全閉"]
        for label, kw in (("チムニー", "d_chimney_mm"), ("指孔径", "d_dia_mm")):
            cells = []
            for d in (1.0, 2.0, 4.0):
                got = solver.scale(comp._shifted(holes, **{kw: d}))
                dd = [g["cents"] - c for g, c in
                      zip([g for g in got if g["name"] != "全閉"], b)]
                cells.append("%+.0f" % (sum(dd) / len(dd)))
            print("  %s +1/+2/+4mm の平均: %s c" % (label, " / ".join(cells)))

        # 届く範囲
        rc = comp._reach_card(base)
        print("  指の届く範囲:", rc["big"],
              "スパン", "%.0f" % bpf.hole_span_mm(base, si, neck), "mm")

        _engine_row(size, comp, base, neck)
        print(flush=True)
    return 0


def main(argv: list[str]) -> int:
    mode = argv[0] if argv and argv[0] in ("build", "acoustics") else "acoustics"
    rest = [a for a in argv if a != mode]
    return sweep_build(rest) if mode == "build" else sweep_acoustics(rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
