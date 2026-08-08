# -*- coding: utf-8 -*-
"""編集画面の応答に効く処理のレイテンシを測る。

断面タブのドラッグ・スライダー操作・3D 再生成が体感で遅い、という報告を追った
ときのベンチ。UI から叩かれる順に並べてある:

  section()   断面タブのドラッグ中に毎フレーム叩かれる（`GET /api/section`）
  simulate()  パラメータ確定のたび（`PUT /api/project/params`）
  regions()   モデル更新のたび（`GET /api/model/regions`）
  build()     3D の作り直し（`GET /api/model.stl`）
  stl()       上のテッセレーション

**いちばん大事なのは最後の「build 中の section」**。OCCT は GIL を離さないので、
3D を作り直している最中は断面もパラメータ更新も巻き添えで止まる。ここが数十 ms に
収まっていないと、他をいくら速くしてもドラッグは引っかかる。

実行:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/perf/bench_ui_latency.py
  ... --sizes tenor --types step curve      # 絞る
  ... --json out.json                       # 前後比較用に保存
  ... --baseline out.json                   # 保存したものと比較して表に差分を出す

**マシンを静かにしてから回すこと。** OCCT を使う他の処理（sweep_cad など）が並走
していると 10 倍以上ぶれる。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.export.models import export_model  # noqa: E402

#: 体感の目安 [ms]。超えたら print で印を付ける（判定はしない。環境で変わるので）
BUDGET = {
    "section": 16.0,        # 60fps の 1 フレーム
    "simulate": 50.0,
    "regions": 16.0,
    "build": 3000.0,
    "stl": 1000.0,
    "section_under_build": 50.0,
}


def _stat(xs: list[float]) -> dict:
    xs = sorted(xs)
    return {
        "n": len(xs),
        "med": statistics.median(xs),
        "p95": xs[max(int(len(xs) * 0.95) - 1, 0)],
        "max": xs[-1],
    }


def _timed(fn, n: int) -> dict:
    fn()                                   # 1 回は捨てる（import や OCCT の遅延初期化）
    xs = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000.0)
    return _stat(xs)


def _section_under_build(comp, p, build_fn) -> tuple[dict, float]:
    """`build_fn()` を走らせながら section() を叩き、待たされ具合を測る。

    サーバでは別スレッドだが、OCCT が GIL を握るのでスレッドでは逃げられない。
    ここで見えるのが、ドラッグ中に 3D 再生成が始まったときの実際の待ち時間。
    `--worker` を付けると別プロセス経由になり、この待ちが消えることを確認できる。
    """
    lat: list[float] = []
    stop = threading.Event()

    def probe():
        while not stop.is_set():
            t = time.perf_counter()
            comp.section(p)
            lat.append((time.perf_counter() - t) * 1000.0)
            stop.wait(0.01)

    th = threading.Thread(target=probe, daemon=True)
    th.start()
    t = time.perf_counter()
    build_fn()
    build_ms = (time.perf_counter() - t) * 1000.0
    stop.set()
    th.join(timeout=10.0)
    return _stat(lat or [0.0]), build_ms


def bench(size: str, baffle_type: str, reps: int, worker=None) -> dict:
    comp = get_registry().get("saxophone").make_component("mouthpiece", size)
    p = {s.key: s.default for s in comp.param_specs()}
    p["baffle_type"] = baffle_type

    out = {
        "section": _timed(lambda: comp.section(p), reps),
        "simulate": _timed(lambda: comp.simulate(p), reps),
        "regions": _timed(lambda: comp.regions(p), reps),
    }

    def build_once():
        comp.build(p)

    out["build"] = _timed(build_once, max(reps // 4, 2))

    part = comp.build(p)

    def stl_once():
        with tempfile.TemporaryDirectory() as td:
            export_model(part, Path(td) / "m.stl", "stl", tolerance=0.05)

    out["stl"] = _timed(stl_once, max(reps // 4, 2))

    if worker is not None:
        spec = {"instrument_id": "saxophone", "template_id": size,
                "component_id": "mouthpiece", "refs": {}, "params": dict(p),
                "tolerance": 0.05, "cad": False}
        def build_fn():
            worker.build_stl(spec)
    else:
        def build_fn():
            comp.build(p)

    under, build_ms = _section_under_build(comp, p, build_fn)
    out["section_under_build"] = under
    out["section_under_build"]["build_ms"] = build_ms
    return out


def _fmt_row(label: str, s: dict, base: dict | None) -> str:
    budget = BUDGET.get(label.split(" ")[0], 0.0)
    mark = "!" if s["med"] > budget else " "
    row = "%s %-20s med %9.2f  p95 %9.2f  max %9.2f" % (
        mark, label, s["med"], s["p95"], s["max"])
    if base:
        r = base["med"] / s["med"] if s["med"] > 0 else float("inf")
        row += "   基準比 %6.2fx (%.2f ms)" % (r, base["med"])
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", default=["tenor", "alto", "soprano"])
    ap.add_argument("--types", nargs="+",
                    default=["step", "straight", "curve", "rollover"])
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--json", help="結果を保存するパス")
    ap.add_argument("--baseline", help="比較する保存済み結果のパス")
    ap.add_argument("--worker", action="store_true",
                    help="ビルドを常駐ワーカ（別プロセス）へ出して測る")
    args = ap.parse_args()

    base = json.loads(Path(args.baseline).read_text()) if args.baseline else None

    worker = None
    if args.worker:
        from saxsketch.server.buildworker import WORKER
        t = time.perf_counter()
        if not WORKER.start():
            print("ビルドワーカを起動できませんでした")
            return 1
        print("ビルドワーカ起動 %.2fs（アプリでは lifespan で先に済ませる）"
              % (time.perf_counter() - t))
        worker = WORKER

    print("reps=%d  （マシンが静かなことを確認してから読むこと）" % args.reps)
    print("! = 目安 %s を超えているもの" % BUDGET)
    print()

    result: dict = {}
    for size in args.sizes:
        for bt in args.types:
            key = f"{size}/{bt}"
            print("=== %s" % key)
            r = bench(size, bt, args.reps, worker)
            result[key] = r
            for name, s in r.items():
                b = (base or {}).get(key, {}).get(name)
                print("   " + _fmt_row(name, s, b))
            print("   （うち build 本体 %.0f ms）" % r["section_under_build"]["build_ms"])
            print()

    if worker is not None:
        worker.stop()
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1))
        print("saved ->", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
