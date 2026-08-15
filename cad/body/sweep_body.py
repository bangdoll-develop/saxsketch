# -*- coding: utf-8 -*-
"""管体（Phase 4-B.2a）のロフト健全性とビルド時間をパラメータ掃引で確かめる。

管体はマウスピースと壊れ方が違う。怖いのは面の接触ではなく **長さ** ——
弧長 502〜1378mm の管に何枚リングを置くかで、ロフトの重さが桁で変わる。
`body_profiles` は直管を粗く（40mm 間隔）、曲げとベルだけ細かく（4 / 3mm）刻んで
リングを 51〜168 枚に抑えているが、それで足りるか・遅すぎないかは測らないと
分からないので、**ビルド時間を必ず表で出す**。

同時に、一体型（ネックまで 1 部品）と別体で:
  - ロフトが両方通ること
  - **気柱（`acoustic_geometry`）がビット一致すること** ＝ 一体化しても音程は動かない
を確かめる。継ぎ目はモデルに入っていないので、ここが一致しないなら実装のバグ。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/body/sweep_body.py
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/body/sweep_body.py alto        # 1 サイズ
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/body/sweep_body.py alto 8 6    # 8 番から 6 通り

**長い連続実行はこの環境では通らない。** 曲げのある管のブーリアンは 1 回 9〜15 秒
かかり、7〜8 通り積んだあたりで **WSL2 の VM ごと落ちる**（`dmesg` に OOM は無く、
ファイルシステムのマウントし直しだけが残る＝プロセスではなく VM が死んでいる）。
アルトで 2 回とも同じところまで進んで落ちたので、負荷の総量で決まっている。
サイズごと・数通りごとに分けて回すこと。第 2・第 3 引数が開始番号と本数。

測定の読み方と、分割ビルド案を測って不採用にした経緯は `cad/body/README.md`。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.instruments.saxophone.components import body_profiles as bpf  # noqa: E402

SIZES = ("soprano", "alto", "tenor")

#: 端に振る設計パラ。長さと曲げに効くものを選ぶ。
SWEEP_KEYS = ["body_arc_length", "bow_angle", "bow_radius", "bell_length",
              "bell_exit_dia", "flare_power", "wall_thickness"]


def _cases(comp, base: dict) -> list[tuple[str, dict]]:
    specs = {s.key: s for s in comp.param_specs()}
    out: list[tuple[str, dict]] = [
        ("既定", dict(base)),
        ("一体型", dict(base, neck_joint="integrated")),
        ("ストレート", dict(base, bow_angle=0.0)),
        ("一体型×ストレート", dict(base, neck_joint="integrated", bow_angle=0.0)),
        ("ベル無し", dict(base, bell_length=0.0)),
        ("テーパ直接指定", dict(base, taper_from_cone="off")),
    ]
    for k in SWEEP_KEYS:
        s = specs.get(k)
        if s is None or s.min is None or s.max is None:
            continue
        for tag, v in (("min", s.min), ("max", s.max)):
            out.append((f"{k}={tag}({v:g})", dict(base, **{k: v})))
    return out


def main(argv: list[str]) -> int:
    reg = get_registry()
    bad: list[str] = []
    skipped = 0
    sizes = tuple(a for a in argv if a in SIZES) or SIZES
    nums = [int(a) for a in argv if a.isdigit()]
    start = nums[0] if nums else 0
    limit = nums[1] if len(nums) > 1 else 10 ** 6
    for size in sizes:
        comp = reg.get("saxophone").make_component("body", size)
        base = {s.key: s.default for s in comp.param_specs()}
        neck = comp._neck()
        cases = _cases(comp, base)
        print(f"== {size} ==  ({start}..{min(start + limit, len(cases)) - 1} / "
              f"全 {len(cases)} 通り)", flush=True)
        for idx, (label, p) in enumerate(cases):
            if idx < start or idx >= start + limit:
                continue
            err = comp.params_error(p)
            if err is not None:
                # 成立しない組は `params_error` が弾くのが正しい挙動。**黙って
                # クランプしていない**ことの確認でもあるので、飛ばした事実を出す。
                skipped += 1
                print("  %-30s   ---   弾いた: %s" % (label, err[:60]), flush=True)
                continue
            rings = len(bpf.stations(p, comp.size_info, neck))
            t0 = time.time()
            try:
                part = comp.build(p)
                solids = len(part.solids())
                good = bool(part.is_valid) and solids == 1 and part.volume > 1000.0
                note = "" if good else f"*** NG valid={part.is_valid} solids={solids}"
            except Exception as exc:                      # noqa: BLE001
                good, note = False, f"*** RAISED {type(exc).__name__}: {exc}"
            if not good:
                bad.append(f"{size} / {label}: {note}")
            print("  %-30s %6.2fs  リング%4d  %s"
                  % (label, time.time() - t0, rings, note or "ok"), flush=True)

        # 一体型と別体で気柱が一致すること（継ぎ目は音響に無い）
        sep = dict(base, neck_joint="separate")
        integ = dict(base, neck_joint="integrated")
        ga = bpf.acoustic_geometry(sep, comp.size_info, neck)
        gb = bpf.acoustic_geometry(integ, comp.size_info, neck)
        if ga != gb:
            bad.append(f"{size}: 一体型と別体で気柱が違う（継ぎ目は音響に無いはず）")
            print("  *** 気柱が一致しない", flush=True)
        else:
            print("  気柱: 一体型 == 別体（%d 点）" % len(ga), flush=True)
    print()
    print(f"弾いた組合せ: {skipped}")
    if bad:
        print("壊れた組合せ:")
        for b in bad:
            print("  -", b)
        print("SOME_FAIL")
        return 1
    print("ALL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
