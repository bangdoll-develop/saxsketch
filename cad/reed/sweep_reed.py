# -*- coding: utf-8 -*-
"""リード（Phase 4-C.2）のロフト健全性をパラメータ掃引で確かめる。

**断面の作り方を丸ごと変えたので必須**。旧実装は角丸長方形（`flat_bottom_rect_pts`）
を張っていて、点の並びが `corner_r` に依らず一定になるよう作り込まれていた。
いまは `thickness(p, z, x)` を x 方向に 18 点サンプリングして上面を直接追う:

  - 点数は形状によらず 21（底辺 2 ＋ 上面 19）でなければならない。断面ごとに
    点数が変わるとルールドロフトが角を辺の途中へ写像して面がねじれる。
  - 上面は「削り面」と「ケーンの円弧」の min なので、**両者が交差する x** で
    折れる。折れが断面ごとに動くと、ロフトが自己交差する余地がある。
  - 前縁カーブを入れると z=0 の断面が幅 0.5mm の細片になる。ここが縮退すると
    ロフトが通らない。

したがって端値の組合せを実際にビルドし、ソリッド 1 個・水密・winding 一致・
バウンディングボックスが規格どおりであることまで見る。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/reed/sweep_reed.py
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/reed/sweep_reed.py alto
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/reed/sweep_reed.py alto 8 6

リードのビルドはマウスピースや管体よりずっと軽い（ロフト 1 回＋ファイルドカットの
ブーリアン 1 回）ので、3 サイズ通しでも VM は落ちない。それでも pytest と同時には
走らせないこと（OCCT の連続負荷で WSL2 の VM ごと落ちた実績がある）。
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.export.models import check_mesh, export_model  # noqa: E402
from saxsketch.instruments.saxophone.components import reed_profiles as rp  # noqa: E402

SIZES = ("soprano", "alto", "tenor")

#: 端に振る設計パラ。**断面の形と前縁に効くもの**を選ぶ（材料や積層は形に効かない）。
SWEEP_KEYS = ["tip_curve_depth", "heel_edge_thickness", "side_rail_thin",
              "tip_corner_r", "spine_ratio", "tip_thickness", "heel_thickness",
              "vamp_length", "tip_width", "heel_width", "reed_length"]


def _cases(comp, base: dict) -> list[tuple[str, dict]]:
    specs = {s.key: s for s in comp.param_specs()}
    out: list[tuple[str, dict]] = [
        ("既定", dict(base)),
        ("ファイルド", dict(base, file_cut="filed")),
        # 円弧が最も深い × 前縁が最も後ろ。上面の折れと細片が同時に効く組
        ("深い円弧×深いカーブ", dict(base, heel_edge_thickness=0.3,
                                     tip_curve_depth=2.5)),
        ("前縁直線（旧形状）", dict(base, tip_curve_depth=0.0)),
        ("薄い側端×深いカーブ", dict(base, side_rail_thin=0.20,
                                     tip_curve_depth=2.5, file_cut="filed")),
    ]
    for k in SWEEP_KEYS:
        s = specs.get(k)
        if s is None or s.min is None or s.max is None:
            continue
        for tag, v in (("min", s.min), ("max", s.max)):
            out.append((f"{k}={tag}({v:g})", dict(base, **{k: v})))
    return out


def _check(comp, p: dict, tmp: Path) -> tuple[bool, str]:
    part = comp.build(p)
    solids = len(part.solids())
    if not part.is_valid or solids != 1:
        return False, f"*** NG valid={part.is_valid} solids={solids}"
    bb = part.bounding_box()
    if abs(bb.min.Y) > 1e-6:
        return False, f"*** NG テーブル面が y=0 にない ({bb.min.Y:+.4f})"
    if abs((bb.max.Z - bb.min.Z) - p["reed_length"]) > 0.05:
        return False, f"*** NG 全長 {bb.max.Z - bb.min.Z:.2f} != {p['reed_length']:.2f}"
    if abs(bb.max.Y - p["heel_thickness"]) > 0.05:
        return False, f"*** NG 最大厚 {bb.max.Y:.2f} != {p['heel_thickness']:.2f}"
    f = tmp / "reed.stl"
    export_model(part, f, "stl")
    q = check_mesh(f)
    if not (q["watertight"] and q["winding_consistent"]):
        return False, f"*** NG mesh {q}"
    return True, ""


def main(argv: list[str]) -> int:
    reg = get_registry()
    bad: list[str] = []
    skipped = 0
    sizes = tuple(a for a in argv if a in SIZES) or SIZES
    nums = [int(a) for a in argv if a.isdigit()]
    start = nums[0] if nums else 0
    limit = nums[1] if len(nums) > 1 else 10 ** 6
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for size in sizes:
            comp = reg.get("saxophone").make_component("reed", size)
            base = {s.key: s.default for s in comp.param_specs()}
            cases = _cases(comp, base)
            print(f"== {size} ==  ({start}..{min(start + limit, len(cases)) - 1} / "
                  f"全 {len(cases)} 通り)", flush=True)
            for idx, (label, p) in enumerate(cases):
                if idx < start or idx >= start + limit:
                    continue
                err = comp.params_error(p)
                if err is not None:
                    # 成立しない組は `params_error` が弾くのが正しい挙動。**黙って
                    # クランプしていない**ことの確認でもあるので、弾いた事実を出す。
                    skipped += 1
                    print("  %-30s   ---   弾いた: %s" % (label, err[:70]), flush=True)
                    continue
                t0 = time.time()
                try:
                    good, note = _check(comp, p, tmp)
                except Exception as exc:                      # noqa: BLE001
                    good, note = False, f"*** RAISED {type(exc).__name__}: {exc}"
                if not good:
                    bad.append(f"{size} / {label}: {note}")
                pts = {len(s["pts"]) for s in rp.sections(p)}
                if pts != {21}:
                    bad.append(f"{size} / {label}: 断面の頂点数が {pts}")
                print("  %-30s %6.2fs  断面%3d  頂点%s  %s"
                      % (label, time.time() - t0, len(rp.sections(p)),
                         sorted(pts), note or "ok"), flush=True)
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
