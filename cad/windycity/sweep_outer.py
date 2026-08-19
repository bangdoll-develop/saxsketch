# -*- coding: utf-8 -*-
"""外形（胴・肩・シャンク）の端値でロフトとブーリアンが通るか確かめる（Phase 4-C.1）。

`sweep_cad.py` は `SWEEP_KEYS` の 1 パラメータずつを端に振る。ここで別に見るのは
**組でしか作れない形**があるから:

  - 円錐シャンク = `shank_length = 0`（平行部なし）＋ 肩比を解いた値
    ＋ `shoulder_fullness = +1`（母線が直線）。3 つ揃って初めて出る形で、
    1 パラメータずつの掃引では一度も通らない。
  - 平行部が消えると `body_segments` の最後の区間（CYLINDER）が**無くなる**。
    区間が 1 本減る経路はここでしか踏まない。

同時に**設計の主張を数字で確かめる**（テストと同じ不変条件だが、こちらは OCCT を
通したソリッドで見る）:

  - 最大径の位置（`heel_z`）が肩の操作で動かないこと
  - 肩が直線のとき STEP 用の母線が **2 点**で出ること（＝ CONICAL_SURFACE 1 枚）

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_outer.py
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_outer.py alto
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_outer.py alto 3 4

**長い連続実行はこの環境では通らない**（`cad/body/README.md` と同じ理由で WSL2 の
VM ごと落ちる）。第 2・第 3 引数が開始番号と本数。`--cad` を付けると STEP 用の
プリミティブ表現でも作る（3〜6 倍遅いので既定は off）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.instruments.saxophone.components import profiles as pf  # noqa: E402

SIZES = ("soprano", "alto", "tenor")


def _cone_params(base: dict) -> dict:
    """最大径からシャンク端まで一直線（円錐シャンク）にした値。

    肩比は `heel_z` を保つ解。断面ハンドル「肩の終わり」を右端まで引いたのと同じ
    状態を、UI を通さずに作る。
    """
    heel = pf.heel_z(base)
    return dict(base, shank_length=0.0,
                shoulder_ratio=(base["overall_length"] - heel) / heel,
                shoulder_fullness=1.0)


def _cases(comp, base: dict) -> list[tuple[str, dict]]:
    specs = {s.key: s for s in comp.param_specs()}

    def ends(key):
        s = specs[key]
        return [(f"{key}={t}({v:g})", dict(base, **{key: v}))
                for t, v in (("min", s.min), ("max", s.max))]

    out: list[tuple[str, dict]] = [("既定", dict(base))]
    out += ends("body_waist")
    out += ends("shoulder_fullness")
    # 平行部なし（肩比は heel_z を保つ解）。`shank_length=0` を単独で入れると
    # 最大径ごと動くので、ハンドルと同じ組で入れる。
    heel = pf.heel_z(base)
    solved = (base["overall_length"] - heel) / heel
    out.append(("平行部なし", dict(base, shank_length=0.0, shoulder_ratio=solved)))
    out.append(("円錐シャンク", _cone_params(base)))
    out += ends("shank_dia")
    out += ends("body_dia")
    # 「最大径 ≥ シャンク径」の**境界ちょうど**。弾かれる側（body_dia=min）だけ
    # 見ても拘束が正しい位置にあるかは分からないので、通る側の端も踏む。
    out.append(("最大径＝シャンク径", dict(base, body_dia=base["shank_dia"])))
    return out


def main(argv: list[str]) -> int:
    reg = get_registry()
    bad: list[str] = []
    want_cad = "--cad" in argv
    sizes = tuple(a for a in argv if a in SIZES) or SIZES
    nums = [int(a) for a in argv if a.isdigit()]
    start = nums[0] if nums else 0
    limit = nums[1] if len(nums) > 1 else 10 ** 6

    for size in sizes:
        comp = reg.get("saxophone").make_component("mouthpiece", size)
        base = {s.key: s.default for s in comp.param_specs()}
        heel0 = pf.heel_z(base)
        cases = _cases(comp, base)
        print(f"== {size} ==  ({start}..{min(start + limit, len(cases)) - 1} / "
              f"全 {len(cases)} 通り)  heel_z={heel0:.3f}", flush=True)
        for idx, (label, p) in enumerate(cases):
            if idx < start or idx >= start + limit:
                continue
            err = comp.params_error(p)
            if err is not None:
                print("  %-24s   ---   弾いた: %s" % (label, err[:60]), flush=True)
                continue
            t0 = time.time()
            try:
                part = comp.build(p)
                solids = len(part.solids())
                good = bool(part.is_valid) and solids == 1 and part.volume > 100.0
                note = "" if good else f"*** NG valid={part.is_valid} solids={solids}"
            except Exception as exc:                      # noqa: BLE001
                good, note = False, f"*** RAISED {type(exc).__name__}: {exc}"
            if not good:
                bad.append(f"{size} / {label}: {note}")
            segs = [len(s) for s in pf.body_segments(p)]
            print("  %-24s %6.2fs  母線区間%-18s %s"
                  % (label, time.time() - t0, segs, note or "ok"), flush=True)

        # --- 設計の主張。ここが崩れたら形が通っていても意味が無い ---
        # (1) この掃引のどの値でも最大径の位置は動かない。**例外を作らない** ——
        #     `body_dia` は半径のスケールなので `heel_z`（軸方向）には効かず、
        #     肩の 2 つは連動して解いてあるので保たれる。1 つでも動いたら
        #     「頂点を跨がない」が崩れている。
        for label, p in cases:
            if abs(pf.heel_z(p) - heel0) > 1e-5:
                bad.append(f"{size} / {label}: 最大径の位置が動いた "
                           f"({pf.heel_z(p):.5f} != {heel0:.5f})")
                print(f"  *** 最大径の位置が動いた: {label}", flush=True)
        # (2) 円錐は母線 2 点＝ CONICAL_SURFACE 1 枚で出る
        cone = _cone_params(base)
        segs = pf.body_segments(cone)
        if len(segs[-1]) != 2:
            bad.append(f"{size}: 円錐なのに母線が {len(segs[-1])} 点 "
                       f"（スプラインになる＝面を選べない）")
            print(f"  *** 円錐の母線が 2 点でない: {[len(s) for s in segs]}", flush=True)
        else:
            print("  円錐の母線: 2 点（CONICAL_SURFACE 1 枚）", flush=True)

        if want_cad:
            t0 = time.time()
            try:
                part = comp.build_cad(cone)
                n = len(part.faces())
                ok = bool(part.is_valid) and len(part.solids()) == 1
                print("  円錐 STEP 表現 %6.2fs  面数 %d  %s"
                      % (time.time() - t0, n, "ok" if ok else "*** NG"), flush=True)
                if not ok:
                    bad.append(f"{size}: 円錐の STEP 表現が壊れた")
            except Exception as exc:                      # noqa: BLE001
                bad.append(f"{size}: 円錐の STEP 表現 RAISED {type(exc).__name__}: {exc}")
                print(f"  *** 円錐の STEP 表現 RAISED {exc}", flush=True)

    print()
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
