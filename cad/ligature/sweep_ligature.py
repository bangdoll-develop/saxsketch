# -*- coding: utf-8 -*-
"""リガチャー（Phase 4-C.3）のロフト健全性をパラメータ掃引で確かめる。

**接触を別ソリッドにしない設計の、唯一の外部確認がこれ。** 4-C.3 で
「締結方式（`closure`）× リードへの当たり方（`contact_type` × `contact_count`）」
を入れたが、接触要素は角柱を足すのではなく**内周断面の凸**として持つ:

  - 材料は「外周ロフト − 内周ロフト」なので、空洞のタブ床を上へ凸にすれば
    それがそのまま接触要素になる。要素が増えてもブーリアンは増えない。
  - だから**ソリッドは常に 1 個**でなければならない。角柱を足す作りだと、
    逆締めのスリットが x=0 の要素を割った瞬間に宙に浮いた別ソリッドができる
    （`contact_count` が奇数だと必ず起きる）。**浮いた要素はここでしか捕まらない**
    —— 断面の自己交差テストも水密チェックも「1 個か」を見ていない。
  - ルールドロフトは断面ごとの頂点数が一致していることが前提。点接触は z 方向にも
    山を丸めるので断面が 3 → 5 枚に増える。枚数が変わっても**頂点数は一定**。

逆締めの橋（圧力プレート）は唯一の例外で、片持ちの構造部材として別に足す。
-x 側の床へ `_BRIDGE_MERGE` 食い込ませて融合させているので、ここもソリッド 1 個で
出てこなければ「橋が浮いている」ことになる。

`params_error` で弾いた組は理由つきで出す（**黙ってクランプしていない**ことの確認）。

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/ligature/sweep_ligature.py
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/ligature/sweep_ligature.py alto

リガチャー 1 個のビルドは 0.4〜2.0 秒（逆締めが重い＝ロフト 5 本＋ブーリアン 6 回）。
pytest と同時には走らせないこと（OCCT の連続負荷で WSL2 の VM ごと落ちた実績がある）。
"""
from __future__ import annotations

import itertools
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.core.schema import ParamSet  # noqa: E402
from saxsketch.export.models import check_mesh, export_model  # noqa: E402
from saxsketch.instruments.saxophone.components import ligature_profiles as lp  # noqa: E402

SIZES = ("soprano", "alto", "tenor")


def _cases(comp, base: dict) -> list[tuple[str, dict]]:
    """締結 3 × 当たり方 4 × 数 3 の総当たり ＋ 端値の組。"""
    out: list[tuple[str, dict]] = []
    for closure, kind, n in itertools.product(
            ("screw_beak", "screw_reed", "elastic"),
            ("none", "face", "line", "point"), (1, 3, 6)):
        if kind in ("none", "face") and n != 1:
            continue                      # 要素を持たないので数は効かない
        out.append((f"{closure}/{kind}×{n}",
                    dict(base, closure=closure, contact_type=kind,
                         contact_count=n)))
    specs = {s.key: s for s in comp.param_specs()}
    extra = [
        # 弾性バンドは締め代を「負の隙間」で表す。床が接触より下に留まるか。
        ("弾性×締め代最大", dict(base, closure="elastic", material="tpu",
                                 clearance=-0.60, band_thickness=4.0)),
        # 橋がバンド厚ぎりぎり（残る床 0.20mm）
        ("逆締め×橋ぎりぎり", dict(base, closure="screw_reed",
                                   band_thickness=base["min_wall"] + 0.55)),
        # タブが細い（外形径で切り詰められる側）＋ 接触が 6 個
        ("細い帯×6点", dict(base, band_width=specs["band_width"].min,
                            contact_type="point", contact_count=6)),
        ("厚い帯×6線", dict(base, band_thickness=specs["band_thickness"].max,
                            contact_type="line", contact_count=6)),
        ("隙間最小×面", dict(base, clearance=0.05, contact_type="face")),
    ]
    return out + extra


def _check(comp, p: dict, tmp: Path) -> tuple[bool, str, float]:
    m = comp.ref_params()
    r = comp.reed_params()
    # ルールドロフトの前提: 1 本のロフトの中で頂点数が一定であること
    for name, secs in (("内周", lp.inner_sections(m, p, r)),
                       ("外周", lp.outer_sections(m, p, r))):
        counts = {len(s["pts"]) for s in secs}
        if len(counts) != 1:
            return False, f"*** NG {name}の頂点数が断面ごとに違う {counts}", 0.0
    part = comp.build(p)
    solids = len(part.solids())
    if not part.is_valid or solids != 1:
        return False, f"*** NG valid={part.is_valid} solids={solids}（浮いた要素）", 0.0
    f = tmp / "lig.stl"
    export_model(part, f, "stl")
    q = check_mesh(f)
    if not (q["watertight"] and q["winding_consistent"]):
        return False, f"*** NG mesh {q}", part.volume
    return True, "", part.volume


def main(argv: list[str]) -> int:
    reg = get_registry()
    bad: list[str] = []
    skipped = 0
    sizes = tuple(a for a in argv if a in SIZES) or SIZES
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for size in sizes:
            sax = reg.get("saxophone")
            comp = sax.make_component("ligature", size)
            mp = sax.make_component("mouthpiece", size)
            comp.set_refs({"mouthpiece": {"params": dict(
                ParamSet(mp.param_specs(), mp.template["mouthpiece"]).values)}})
            base = dict(ParamSet(comp.param_specs(),
                                 comp.template["ligature"]).values)
            cases = _cases(comp, base)
            print(f"== {size} ==  (全 {len(cases)} 通り)", flush=True)
            for label, p in cases:
                err = comp.params_error(p)
                if err is not None:
                    skipped += 1
                    print("  %-24s   ---   弾いた: %s" % (label, err[:60]),
                          flush=True)
                    continue
                t0 = time.time()
                try:
                    good, note, vol = _check(comp, p, tmp)
                except Exception as exc:                      # noqa: BLE001
                    good, note, vol = False, \
                        f"*** RAISED {type(exc).__name__}: {exc}", 0.0
                if not good:
                    bad.append(f"{size} / {label}: {note}")
                print("  %-24s %6.2fs  体積 %8.1f mm³  %s"
                      % (label, time.time() - t0, vol, note or "ok"), flush=True)
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
