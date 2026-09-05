# -*- coding: utf-8 -*-
"""録音（`.m4a` など）から **F0 と倍音比**を出す。検品シート §11 用。

**なぜこの 2 つか** —— 時間領域合成（`cad/windycity/README.md`「3 サイズ × 3
アンブシュアの実測」）がモデル側で出しているのがまさにこの 2 つで、比べる相手が
そこにしかない。

**絶対音程を主指標にしないのは、感度が小さいからではない**（ここには当初
「挿し込み量からの音程は 0.49 セント/mm しか動かない」と書いていた）。
0.49 は `openwind_bridge` が解く**全閉最低音**の値で、トーンホールが無い管の話。
感度は 1/L で伸びるので、**録音に入っている音では 1.6〜5.0 セント/mm**
（`inspection_values.py` の「感度は音ごとに違う」）。つまり**数 mm 差し直すだけで
10 セント動く**ので、挿し込み量を記録しない限り絶対音程は解釈できない
（`docs/print-inspection.md` §11.6 の訂正）。倍音比のほうが情報量があるのは変わらない。

**圧縮録音でよい理由**: 48kHz / 約 200kbps の AAC なら **F0 と f0 の 1〜8 倍は
保たれる**。潰れるのは 16kHz 以上と極小レベルのノイズ床なので、**音程と倍音
バランスには使えるが、息のノイズ・雑音の比較には使えない**。

**判定を出さない。** 数字だけ出す（シートの規則）。しきい値はここで作らない。

実行:
  .venv/Scripts/python.exe cad/inspection/analyze_recording.py <file...> [--a4 440]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

# Windows のコンソール既定は CP932。出力は必ず UTF-8 にする。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: 探す基本周波数の範囲 [Hz]。アルトの実音は D♭3 138.59Hz 付近から上へ。
F0_LO, F0_HI = 60.0, 1200.0
#: 解析フレーム。50ms 級だと F0 60Hz が 3 周期入らないので 85ms 取る。
FRAME, HOP = 4096, 1024
#: 定常とみなす許容 [セント]。これを超えたら別の音として切る。
STABLE_CENTS = 40.0
#: 定常区間の最短 [s]。音色は音高より遅れて立つので短すぎる区間は倍音を出さない。
MIN_SEG_S = 0.18
#: 倍音比を測る次数。
HARMONICS = 8
#: 振り切れた標本の割合の上限。これを超えたら**倍音比を出さない** ——
#: クリップが作る高次倍音とマウスピースの倍音は区別できない。F0 は読める。
CLIP_LIMIT = 0.0005

_NAMES = ("C", "C#", "D", "E♭", "E", "F", "F#", "G", "A♭", "A", "B♭", "B")


def decode(path: Path) -> tuple[np.ndarray, int]:
    """モノラル float の波形と標本化周波数。**PyAV は関数の中で import する**
    （解析用の任意依存なので、無い環境で他の道具まで落とさない）。

    **パケット単位で例外を許す。** スマホ録音の `.m4a` は先頭に 2 バイトの
    プライミングパケットが入っていることがあり、`container.decode()` に任せると
    そこで `InvalidDataError` を投げて 1 標本も取れない（実際にそうなった）。
    落ちたパケットの数は呼び出し側へ返さず、**ここで数えて出す** —— 黙って
    捨てると「短く録れた」のか「読めなかった」のか区別できない。
    """
    import av

    chunks: list[np.ndarray] = []
    dropped = 0
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        sr = int(stream.rate)
        res = av.AudioResampler(format="s16", layout="mono", rate=sr)

        def take(frame) -> None:
            out = res.resample(frame)
            for f in (out if isinstance(out, list) else [out]):
                if f is not None:
                    chunks.append(f.to_ndarray().reshape(-1))

        for packet in container.demux(stream):
            try:
                for frame in packet.decode():
                    take(frame)
            except av.error.InvalidDataError:
                dropped += 1
        take(None)
    if not chunks:
        raise RuntimeError(f"音声が取れなかった: {path}")
    if dropped:
        print(f"  （読めなかったパケット {dropped} 個 —— 先頭のプライミング）")
    return np.concatenate(chunks).astype(np.float64) / 32768.0, sr


def f0_autocorr(x: np.ndarray, sr: int) -> tuple[float, float]:
    """(F0 [Hz], 相関のピーク高さ 0〜1)。自己相関＋放物線補間。

    FFT で自己相関を出す。ピークは**放物線で補間する** —— 補間しないと
    標本 1 個ぶんの丸めがそのまま音程誤差になり、138Hz では 1 標本で 8 セント動く。
    """
    x = x - x.mean()
    if not np.any(x):
        return 0.0, 0.0
    n = 1 << (2 * len(x) - 1).bit_length()
    spec = np.fft.rfft(x * np.hanning(len(x)), n)
    ac = np.fft.irfft(spec * np.conj(spec), n)[:len(x)]
    if ac[0] <= 0:
        return 0.0, 0.0
    ac = ac / ac[0]
    lo, hi = int(sr / F0_HI), min(int(sr / F0_LO), len(ac) - 2)
    if hi <= lo + 1:
        return 0.0, 0.0
    k = lo + int(np.argmax(ac[lo:hi]))
    if k <= 0 or k >= len(ac) - 1:
        return 0.0, 0.0
    a, b, c = ac[k - 1], ac[k], ac[k + 1]
    denom = a - 2 * b + c
    d = 0.5 * (a - c) / denom if denom != 0 else 0.0
    return sr / (k + d), float(b)


def harmonic_ratios(x: np.ndarray, sr: int, f0: float) -> list[float]:
    """f0 の 1〜8 倍の振幅を h1=1.00 に正規化して返す。

    ビンをまたぐので**k·f0 の周り ±2 ビンの最大**を取る。ちょうどのビンだけ見ると
    窓の漏れで倍音が消えて見える。
    """
    w = x * np.hanning(len(x))
    n = 1 << (len(w) - 1).bit_length() + 1
    mag = np.abs(np.fft.rfft(w, n))
    df = sr / n
    out: list[float] = []
    for k in range(1, HARMONICS + 1):
        c = int(round(k * f0 / df))
        if c + 2 >= len(mag):
            out.append(0.0)
            continue
        out.append(float(mag[max(c - 2, 0):c + 3].max()))
    h1 = out[0]
    return [v / h1 for v in out] if h1 > 0 else out


def note_name(f: float, a4: float) -> tuple[str, float]:
    """(音名, 平均律からのずれ [セント])。**実音**（記譜音ではない）。"""
    semi = 12.0 * math.log2(f / a4) + 69.0
    m = int(round(semi))
    return f"{_NAMES[m % 12]}{m // 12 - 1}", (semi - m) * 100.0


def segments(x: np.ndarray, sr: int) -> list[tuple[int, int, np.ndarray]]:
    """定常区間を (開始標本, 終了標本, フレーム F0 列) で返す。

    無音で切ってから**音程で切る** —— レガートで吹かれた音階は 1 つの有声区間に
    なるので、無音だけでは 1 音に分かれない。
    """
    idx = range(0, max(len(x) - FRAME, 0), HOP)
    rms = np.array([np.sqrt(np.mean(x[i:i + FRAME] ** 2)) for i in idx])
    f0s, conf = np.zeros(len(rms)), np.zeros(len(rms))
    for j, i in enumerate(idx):
        f0s[j], conf[j] = f0_autocorr(x[i:i + FRAME], sr)
    if not len(rms):
        return []
    # 有声の判定は**その録音の中の相対値**で決める（録音レベルが分からない）。
    live = (rms > 0.08 * np.percentile(rms, 98)) & (conf > 0.30) & (f0s > 0)

    out, run = [], []
    for j in range(len(live)):
        if live[j] and (not run
                        or abs(1200 * math.log2(f0s[j] / f0s[run[-1]])) < STABLE_CENTS):
            run.append(j)
            continue
        if len(run) * HOP / sr >= MIN_SEG_S:
            out.append((run[0] * HOP, run[-1] * HOP + FRAME, f0s[np.array(run)]))
        run = [j] if live[j] else []
    if len(run) * HOP / sr >= MIN_SEG_S:
        out.append((run[0] * HOP, run[-1] * HOP + FRAME, f0s[np.array(run)]))
    return out


def analyze(path: Path, a4: float, show_notes: bool) -> None:
    x, sr = decode(path)
    clip = float(np.mean(np.abs(x) >= 0.999))
    print(f"\n## {path.name}")
    print(f"  {len(x) / sr:.1f} s / {sr} Hz / ピーク {np.abs(x).max():.3f}"
          f" / 振り切れ {clip * 100:.2f}%")
    clipped = clip > CLIP_LIMIT
    if clipped:
        # クリップは倍音を作る。**足された倍音とマウスピースの倍音は区別できない**
        # ので、合否を出すのではなく**数値を出さない**。出すと比べたくなる。
        print(f"  ⚠ 振り切れが {CLIP_LIMIT * 100:.2f}% を超えたので"
              " **倍音比は出さない**（クリップ自体が高次を作る）。F0 は読める")
    segs = segments(x, sr)
    if not segs:
        print("  定常区間が見つからない")
        return

    rows = []
    for s, e, track in segs:
        # 立ち上がりと切れ際を落として**中央の半分**で測る。音色は音高より
        # 遅れて立つ（0.3s ではまだ正弦に近い）ので、倍音は必ず中央で取る。
        seg = x[s + (e - s) // 4:e - (e - s) // 4]
        if len(seg) < FRAME:
            seg = x[s:e]
        seg = seg[:8 * FRAME]
        f0, _ = f0_autocorr(seg, sr)
        if f0 <= 0:
            continue
        name, cents = note_name(f0, a4)
        spread = 1200 * math.log2(track.max() / track.min()) if track.min() > 0 else 0.0
        rows.append((s / sr, (e - s) / sr, f0, name, cents, spread,
                     [] if clipped else harmonic_ratios(seg, sr, f0)))
    if not rows:
        print("  F0 が取れなかった")
        return

    if show_notes:
        print("    #   開始    長さ      F0      音名   ずれ    揺れ"
              + ("" if clipped else "     倍音比 (h1..h8)"))
        for i, (t, d, f0, name, cents, spread, ratios) in enumerate(rows, 1):
            print(f"  {i:3d} {t:6.2f}s {d:6.2f}s {f0:8.2f} {name:>5}"
                  f" {cents:+6.1f} ¢ {spread:6.1f} ¢   "
                  + " ".join(f"{v:.2f}" for v in ratios))

    # ---- 要約。**既定では 1 音ずつ出さない** —— 旋律を吹いた録音では 1 音
    # 0.3s 級で数十個並び、並べても読めない。比べる相手（Stage H の合成）が
    # 出すのも「音程」と「倍音比」の 2 つだけなので、そこへ揃える。
    f0s = np.array([r[2] for r in rows])
    dev = np.array([r[4] for r in rows])
    steady = [r for r in rows if r[5] < 20.0]
    lo, hi = f0s.min(), f0s.max()
    print(f"  音 {len(rows)} 個 / 実音 {note_name(lo, a4)[0]} {lo:.1f}Hz"
          f" 〜 {note_name(hi, a4)[0]} {hi:.1f}Hz"
          f" = {1200 * math.log2(hi / lo) / 100:.1f} 半音")
    print(f"  平均律からのずれ 中央 {np.median(dev):+.1f} ¢"
          f" / 絶対値の中央 {np.median(np.abs(dev)):.1f} ¢"
          f" / 範囲 {dev.min():+.1f}〜{dev.max():+.1f} ¢")
    print(f"  音程の揺れが 20¢ 未満の音 {len(steady)} 個"
          f"（残りはレガートの渡りかビブラート）")
    if steady and not clipped:
        med = [float(np.median([r[6][k] for r in steady])) for k in range(HARMONICS)]
        print("  倍音比の中央値 (h1..h8)  " + " ".join(f"{v:.2f}" for v in med))
        above = sum(1 for r in steady if r[6][1] > 1.0)
        print(f"  h2 > h1 の音 {above}/{len(steady)} 個"
              f" —— 基音が最強とは限らない（サックスでは普通）")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--a4", type=float, default=440.0,
                    help="チューナー基準 [Hz]。実測時の基準に合わせる")
    ap.add_argument("--notes", action="store_true",
                    help="1 音ずつ出す（既定は要約だけ）")
    a = ap.parse_args()
    print(f"# 録音の F0 と倍音比（A4={a.a4:.1f} Hz・実音）")
    for f in a.files:
        analyze(Path(f), a.a4, a.notes)


if __name__ == "__main__":
    main()
