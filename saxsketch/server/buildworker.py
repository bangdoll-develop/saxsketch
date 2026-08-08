"""CAD ビルドを別プロセスで回すための常駐ワーカ。

**なぜプロセスなのか**: OCCT（build123d の下回り）は GIL を離さない。`build()` は
テナー既定で 4.5 秒かかり、その 73% はブーリアン演算の中にいる。スレッドへ逃がしても
GIL を握られたままなので、3D を作り直している最中は `GET /api/section` も
`PUT /api/project/params` も巻き添えで止まる。実測で断面の応答が 7ms → 中央 398ms /
最大 2612ms まで落ちていた。プロセスを分ければインタプリタごと別なので、この待ちは
消える。

**投げるもの**: `(instrument_id, template_id, component_id, refs, params, tolerance)`
だけ。`Component.build()` は params の純関数（`AppState` を見ない）なので、子は
レジストリからコンポーネントを作り直せばよく、親子で状態を持ち合わない。

**捨てる**: 世代番号を持ち、新しい依頼が来た時点で古い結果は読み捨てる。ドラッグや
スライダー連打で依頼が積み上がっても、待ちが直列に伸びない。

**壊れてもいい**: 子が起動できない・落ちた・応答しないときは黙って親プロセス内で
ビルドする。遅くなるだけで機能は失われない。テスト（`SAXSKETCH_NO_BUILD_WORKER=1`）
でも親側の経路を使う。
"""
from __future__ import annotations

import contextlib
import logging
import multiprocessing as mp
import os
import queue
import tempfile
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

#: 1 ビルドの上限 [s]。これを超えたら子を捨てて親側で作り直す。
#: テナーで 4.5 秒、プリミティブ表現（STEP）で 20 秒台なので、その 3 倍強を見る。
_TIMEOUT = 90.0

#: 子の起動待ち [s]。build123d の import に 2〜3 秒かかる。
_BOOT_TIMEOUT = 60.0


def _disabled() -> bool:
    return os.environ.get("SAXSKETCH_NO_BUILD_WORKER") == "1"


# ------------------------------------------------------------------ 子プロセス側

def _child_main(req_q, res_q) -> None:
    """依頼を受けて STL バイト列を返す。例外は文字列にして親へ渡す。"""
    # 起動直後に重い import を済ませておく（最初の依頼にこの 2〜3 秒を払わせない）。
    try:
        import build123d  # noqa: F401
        from saxsketch.core.registry import get_registry
        get_registry()
        res_q.put(("ready", None, None))
    except Exception as e:                     # noqa: BLE001
        res_q.put(("boot_failed", None, f"{type(e).__name__}: {e}"))
        return

    from saxsketch.core.registry import get_registry
    from saxsketch.export.models import export_model

    while True:
        job = req_q.get()
        if job is None:
            return
        gen, spec = job
        try:
            inst = get_registry().get(spec["instrument_id"])
            comp = inst.make_component(spec["component_id"], spec["template_id"])
            if spec.get("refs"):
                comp.set_refs(spec["refs"])
            part = (comp.build_cad(spec["params"]) if spec.get("cad")
                    else comp.build(spec["params"]))
            with tempfile.TemporaryDirectory() as td:
                f = Path(td) / "m.stl"
                export_model(part, f, "stl", tolerance=spec["tolerance"])
                data = f.read_bytes()
            res_q.put(("ok", gen, data))
        except Exception as e:                 # noqa: BLE001 - 形状生成の失敗全般
            res_q.put(("error", gen, f"{type(e).__name__}: {e}"))


# ------------------------------------------------------------------ 親プロセス側

class BuildWorker:
    """常駐する子プロセス 1 本。使えないときは `alive` が False になる。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: mp.process.BaseProcess | None = None
        self._req: mp.Queue | None = None
        self._res: mp.Queue | None = None
        self._gen = 0
        self.alive = False

    # -------------------------------------------------- 起動・停止

    def start(self) -> bool:
        if _disabled():
            return False
        with self._lock:
            return self._start_locked()

    def _start_locked(self) -> bool:
        self._stop_locked()
        try:
            # spawn に統一する。fork だと親が既に OCCT を触っていた場合に
            # そのスレッド状態を引き継いでしまい、環境によって不安定になる。
            ctx = mp.get_context("spawn")
            self._req = ctx.Queue()
            self._res = ctx.Queue()
            self._proc = ctx.Process(
                target=_child_main, args=(self._req, self._res), daemon=True)
            self._proc.start()
            status, detail = self._wait_ready()
            if status != "ready":
                raise RuntimeError(detail or status)
        except Exception as e:                 # noqa: BLE001
            log.warning("ビルドワーカを起動できないので親プロセスで作ります: %s", e)
            self._stop_locked()
            self.alive = False
            return False
        self.alive = True
        return True

    def _wait_ready(self) -> tuple[str, str | None]:
        """準備完了の合図を待つ。**子が死んでいたら待たずに諦める**。

        spawn の子は `__main__` を読み直すので、環境によっては起動直後に落ちる
        （例: 標準入力から流したスクリプト）。そのとき合図は永遠に来ないので、
        待ち切るのではなく生存を見ながら短く刻む。
        """
        deadline = time.monotonic() + _BOOT_TIMEOUT
        while time.monotonic() < deadline:
            try:
                status, _, detail = self._res.get(timeout=0.2)
                return status, detail
            except queue.Empty:
                if self._proc is None or not self._proc.is_alive():
                    return "boot_failed", "子プロセスが起動直後に終了しました"
        return "boot_failed", f"{_BOOT_TIMEOUT:.0f} 秒以内に準備できませんでした"

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        proc, req = self._proc, self._req
        self._proc = self._req = self._res = None
        self.alive = False
        if req is not None:
            with contextlib.suppress(Exception):
                req.put(None)
        if proc is not None and proc.is_alive():
            proc.join(timeout=3.0)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=3.0)

    # -------------------------------------------------- ビルド

    def build_stl(self, spec: dict) -> bytes:
        """STL バイト列。ワーカが使えない／失敗したら RuntimeError。

        呼び出しは `AppState.build_lock` で直列化されている前提。世代番号は
        「前の依頼の残り物を読まない」ためのもので、並行依頼のためではない。
        """
        with self._lock:
            if not self.alive and not self._start_locked():
                raise RuntimeError("ビルドワーカが使えません")
            self._gen += 1
            gen = self._gen
            self._req.put((gen, spec))
            res = self._res
            deadline = time.monotonic() + _TIMEOUT
            while True:
                try:
                    status, got, payload = res.get(
                        timeout=max(deadline - time.monotonic(), 0.0))
                except queue.Empty:
                    # 詰まった子は捨てる。次の依頼で上げ直す。
                    log.warning("ビルドワーカが %.0f 秒で応答しないので作り直します",
                                _TIMEOUT)
                    self._stop_locked()
                    raise RuntimeError("ビルドがタイムアウトしました")
                except (EOFError, OSError) as e:
                    self._stop_locked()
                    raise RuntimeError(f"ビルドワーカが落ちました: {e}")
                if got != gen:
                    continue          # 古い依頼の結果。読み捨てて次を待つ
                if status == "ok":
                    return payload
                raise RuntimeError(payload)


#: プロセスに 1 本。`app.py` の lifespan が上げ下げする。
WORKER = BuildWorker()
