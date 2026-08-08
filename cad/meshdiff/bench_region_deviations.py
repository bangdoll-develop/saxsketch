# -*- coding: utf-8 -*-
"""`meshdiff.region_deviations` の実時間と判定を測る（ベンチ兼・目視検証）。

pytest 側は「遠い点が厳密計算へ入らないこと」を不変条件として見るだけで、
速いかどうかは見ていない（壁時計に頼ると他の重い処理と並行しただけで落ちる）。
数字が要るときはこちらを回す。

測るケース:
  同一        ref と ref。**未編集のモデルを取り込んだ**状況。全ゾーン「変化なし」が正解
  微小平行移動 z を +0.05mm。座標系だけずれた状況。同じく「変化なし」が正解
  既知の編集   バッフル高さを +0.30mm。その数字がそのまま出るのが正解
  別座標系     +200mm。取り違えた外部モデル。全ゾーン「変化あり」＋厳密計算 0 点が正解

段ごとの内訳（サンプリング / 見積り / 厳密化）と厳密化した点数も出す。

実行:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/meshdiff/bench_region_deviations.py
  ... --sizes tenor --k 8 --est-tol 0.25    # 定数を振って比較する
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.analysis import meshdiff  # noqa: E402
from saxsketch.core.registry import get_registry  # noqa: E402

VERDICTS = ("変化なし", "軽微", "変化あり", "判定不可")


class Probe:
    """`meshdiff` の内部関数を包んで段ごとの時間と厳密化点数を数える。"""

    def __init__(self) -> None:
        self.t = {"sample": 0.0, "estimate": 0.0, "exact": 0.0}
        self.n_exact = 0
        self._orig = (meshdiff._sample, meshdiff._estimate_dist, meshdiff._exact_dist)

    def __enter__(self) -> "Probe":
        o_sample, o_est, o_exact = self._orig

        def sample(m):
            t0 = time.time()
            try:
                return o_sample(m)
            finally:
                self.t["sample"] += time.time() - t0

        def estimate(*a):
            t0 = time.time()
            try:
                return o_est(*a)
            finally:
                self.t["estimate"] += time.time() - t0

        def exact(pts, other, sel):
            t0 = time.time()
            self.n_exact += len(sel)
            try:
                return o_exact(pts, other, sel)
            finally:
                self.t["exact"] += time.time() - t0

        meshdiff._sample = sample
        meshdiff._estimate_dist = estimate
        meshdiff._exact_dist = exact
        return self

    def __exit__(self, *exc) -> None:
        meshdiff._sample, meshdiff._estimate_dist, meshdiff._exact_dist = self._orig


def _cases(size: str):
    """(ラベル, ref, other, regions, 期待) を並べる。"""
    comp = get_registry().get("saxophone").make_component("mouthpiece", size)
    params = {s.key: s.default for s in comp.param_specs()}
    ref = meshdiff.part_to_mesh(comp.build(params), tolerance=0.03)
    regions = comp.regions(params)

    shifted = ref.copy()
    shifted.apply_translation([0.0, 0.0, 0.05])
    foreign = ref.copy()
    foreign.apply_translation([200.0, 200.0, 0.0])

    edited_p = dict(params)
    edited_p["baffle_height"] = params["baffle_height"] + 0.30
    edited = meshdiff.part_to_mesh(comp.build(edited_p), tolerance=0.03)

    return regions, [
        ("同一（未編集の取込）", ref, "全ゾーン 変化なし"),
        ("微小平行移動 z+0.05mm", shifted, "全ゾーン 変化なし"),
        ("既知の編集 バッフル+0.30mm", edited, "バッフル側 0.30±0.05"),
        ("別座標系 +200mm", foreign, "全ゾーン 変化あり・厳密化 0 点"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", default=["tenor", "alto"])
    ap.add_argument("--k", type=int, help="_CAND_K（候補にする最近傍サンプル点の数）")
    ap.add_argument("--est-tol", type=float, help="_EST_TOL（厳密化する帯の幅 mm）")
    ap.add_argument("--refine-max", type=float, help="_REFINE_MAX（厳密化の上限距離 mm）")
    ap.add_argument("--samples", type=int, help="SAMPLE_COUNT")
    args = ap.parse_args()

    for attr, val in (("_CAND_K", args.k), ("_EST_TOL", args.est_tol),
                      ("_REFINE_MAX", args.refine_max), ("SAMPLE_COUNT", args.samples)):
        if val is not None:
            setattr(meshdiff, attr, val)

    print("SAMPLE_COUNT=%d  _CAND_K=%d  _FAR_CAP=%.1f  _REFINE_MIN=%.2f  "
          "_REFINE_MAX=%.1f  _EST_TOL=%.2f  _MAX_EXACT=%d"
          % (meshdiff.SAMPLE_COUNT, meshdiff._CAND_K, meshdiff._FAR_CAP,
             meshdiff._REFINE_MIN, meshdiff._REFINE_MAX, meshdiff._EST_TOL,
             meshdiff._MAX_EXACT))
    print()
    header = ("%-10s %-26s %7s %7s %7s %7s %8s  %-24s %s"
              % ("サイズ", "ケース", "合計s", "標本s", "見積s", "厳密s",
                 "厳密点数", "判定", "最大偏差mm"))
    print(header)
    print("-" * len(header))

    ok = True
    for size in args.sizes:
        regions, cases = _cases(size)
        for label, other, expect in cases:
            ref = cases[0][1]
            with Probe() as p:
                t0 = time.time()
                out = meshdiff.region_deviations(ref, other, regions)
                total = time.time() - t0
            counts = {v: sum(1 for r in out if r["verdict"] == v) for v in VERDICTS}
            shown = " ".join(f"{v}{counts[v]}" for v in VERDICTS if counts[v])
            top = max((r["max_dev_mm"] for r in out
                       if r["max_dev_mm"] is not None), default=float("nan"))
            print("%-10s %-26s %7.2f %7.2f %7.2f %7.2f %8d  %-24s %.3f"
                  % (size, label, total, p.t["sample"], p.t["estimate"],
                     p.t["exact"], p.n_exact, shown, top))

            # 期待と突き合わせる（README の表がそのまま回帰チェックになるように）
            judged = [r for r in out if r["max_dev_mm"] is not None]
            if label.startswith(("同一", "微小")):
                bad = [r for r in judged if r["verdict"] != "変化なし"]
                if bad:
                    ok = False
                    print("    ! 期待 %s / 出た: %s"
                          % (expect, ", ".join(f"{r['label']}={r['max_dev_mm']}"
                                               for r in bad[:3])))
            elif label.startswith("既知"):
                z = next((r for r in out if "baffle_height" in r["params"]), None)
                if z is None or abs(z["max_dev_mm"] - 0.30) > 0.05:
                    ok = False
                    print("    ! 期待 %s / 出た: %s" % (expect, z and z["max_dev_mm"]))
            else:
                if p.n_exact or any(r["verdict"] != "変化あり" for r in judged):
                    ok = False
                    print("    ! 期待 %s / 厳密点数 %d" % (expect, p.n_exact))

    print()
    print("ALL_PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
