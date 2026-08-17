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

**4-C.2b で「平面視の輪郭そのもの」の検査（`_outline_defect`）を足した。**
上の 4 つは全部通るのに、最先端の断面だけ全幅のまま残って前へ平たいヒレが
張り出す不具合を**この掃引が素通りさせた**（ユーザーが 3D ビューで見つけた）。
bbox は幅が正しい側の値を拾うので、形の破綻を bbox で見張るのには限界がある。

**4-C.2d で先端厚の下限が 0.15 → 0.08 に下がった。** 光造形の解像度（積層 0.02×3
= 0.06）と実物のケーン（0.11）を域内に入れるためで、既定は動いていない。ただし
`side_rail_thin` の下限 0.20 と重ねると側端が 0.016mm まで薄くなる（いままでの
最薄は 0.030mm）ので、その組を 1 本足してある。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/reed/sweep_reed.py
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/reed/sweep_reed.py alto
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/reed/sweep_reed.py alto 8 6

リードのビルドはマウスピースや管体よりずっと軽い（**ロフト 1 回だけ**。4-C.2c で
ファイルドがブーリアンでなくなった）ので、3 サイズ通しでも VM は落ちない。それでも
pytest と同時には走らせないこと（OCCT の連続負荷で WSL2 の VM ごと落ちた実績がある）。
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
        # ファイルド × 深い円弧 × 先端幅 > 踵幅。**1 パラメータの端値では届かない**
        # 領域で、表皮を落とす面がテーブル面より下へ潜る組（4-C.2c で発見）。
        ("ファイルド×深い円弧×先端広", dict(base, heel_edge_thickness=0.3,
                                            tip_width=base["heel_width"] + 1.0,
                                            file_cut="filed")),
        # 4-C.2d で先端厚の下限が 0.08 に下がった。側端の薄化と重なると
        # 側端厚が 0.08 × 0.20 = 0.016mm になる（従来の最薄 0.030 の半分）。
        ("薄い先端×薄い側端", dict(base, tip_thickness=0.08, side_rail_thin=0.20)),
    ]
    for k in SWEEP_KEYS:
        s = specs.get(k)
        if s is None or s.min is None or s.max is None:
            continue
        for tag, v in (("min", s.min), ("max", s.max)):
            out.append((f"{k}={tag}({v:g})", dict(base, **{k: v})))
    return out


def _outline_defect(p: dict) -> str | None:
    """平面視の輪郭が単調非減少で、傾きが跳ね上がらないこと。

    **この掃引が 4-C.2 のヒレを素通りさせた。** ソリッド数・水密・bbox・頂点数は
    全部通るのに、最先端の断面だけ全幅のまま残って前へ板が張り出していた
    （`width()` の円弧クランプが z=0 を含んでいなかった）。bbox は幅が正しい側の
    値を拾うので気づけない。**輪郭そのものを見る検査を足す。**
    """
    h = 1e-4
    z_hi = rp.tip_full_width_z(p) + 0.5
    taper = (p["heel_width"] - p["tip_width"]) / (2.0 * p["reed_length"])
    # 先端は 1µm 刻み、その先はテーパーの直線なので 0.5mm 刻みで足りる。
    zs = [i * 0.001 for i in range(int(z_hi / 0.001) + 1)]
    zs += [z_hi + i * 0.5 for i in range(int((p["reed_length"] - z_hi) / 0.5) + 1)]
    zs.append(p["reed_length"])
    prev_w, prev_slope, worst = -1.0, None, None
    for z in zs:
        w = rp.width(p, z)
        if w < prev_w - 1e-9:
            return f"*** NG 輪郭が z={z:.3f} で {prev_w:.3f} → {w:.3f} と細る"
        prev_w = w
        if 0.02 <= z <= z_hi:
            slope = (rp.half_width(p, z + h) - rp.half_width(p, z)) / h
            if prev_slope is not None and slope - prev_slope > max(taper, 0.0) + 1e-3:
                worst = f"*** NG 輪郭の傾きが z={z:.3f} で {slope - prev_slope:+.3f} 跳ぶ"
            prev_slope = slope
    return worst


def _check(comp, p: dict, tmp: Path) -> tuple[bool, str]:
    defect = _outline_defect(p)
    if defect is not None:
        return False, defect
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
