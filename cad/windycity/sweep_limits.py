# -*- coding: utf-8 -*-
"""パラメータの**本当の壁**を測る（Phase 4-E）。

`ParamSpec.min`/`max` は「勧める帯」で、越えられない壁は `hard_min`/`hard_max`。
その `hard_*` に入れる数字を**掃引で測る**ためのスクリプト。帯の外に何があるか
誰も測っていなかったので、広げる前にここで測る ——**広げる根拠を発明しない。**

判定は 3 段。上から順に安いので、落ちた段で止める:

  1. `comp.params_error(p)` が `None`（成立条件。楽器側しか知らない）
  2. `profiles.cavity_stations(p)` が例外を出さず、枚数と先端高さが退化しない
  3. **OCCT ビルドがソリッド 1 個**。`is_valid` は当てにしない（True のまま
     割れる前例がある。`outer_layout_error` の docstring）ので体積も見る

1〜2 は速いので端から端まで刻んで走らせ、**3 は境界の周りだけ**で確かめる
（1 点 4.5 秒。全点で回すと 1 パラメータで数分かかる）。

**「通った」と「効いた」は別物。** 値を動かしても形が 1 ビットも変わらない帯が
あり（`window_length_effective` の死んだ帯がその実例）、そこを掃引すると
「壁が無い」という嘘の結論が出る —— 実際 `chamber_to_bore_mm` は既定の
`window_length` では**負にしても何も起きない**（`min()` の反対側が勝つ）。
各点で形が動いたかを見て、動いていなければそう言う。

**さらに「効いた」にも程度がある。** 形の指紋は動くのに応答がほとんど無い帯が
あり、そこまで広げてもつまみが空回りするだけ。そこで壁を決める前に
**固定グリッド**（σ 等分。ステーション数に依らない）で空洞の平均高さの傾きを
測り、**帯の端での傾きに対して 5% を割ったら死に帯**として報告する。
`baffle_height` の負側がこれで、ソリッドは −4.0 でも 1 個できるのに
**alto はそこで帯の端の 4%** しか動かない（効くのは −2.3 まで）。
死に帯と判定したときは**どこまでなら効くか**も探して出す ＝ それが
`hard_min` / `hard_max` に入れる値。

拘束が効く条件を作るには `--with key=value` を重ねる:
  ... sweep_limits.py chamber_to_bore_mm --with window_length=44

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_limits.py tip_opening
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_limits.py tip_opening alto
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_limits.py --all --no-build
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_limits.py chamber_to_bore_mm --with window_length=44

**長い連続実行はこの環境では通らない**（`cad/body/README.md`）。パラメータは
1 本ずつ回すこと。`--no-build` は段 3 を飛ばす下見用で、**その結果を `hard_*`
に入れてはいけない** —— 幾何が成立してもソリッドが割れる組がある。
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

#: 帯の外へ何段まで歩くか。帯幅に対する倍率で、`min − STEPS·step` まで見る。
OUT_STEPS = 40

#: ステーションが退化したとみなす閾値。既定 3 サイズは 34〜43 枚、先端 0.60〜0.70mm。
MIN_STATIONS = 20
MAX_TIP_H_MM = 1.5

#: 応答を測る固定グリッドの分割数（σ 等分）。**ステーション数に依らないこと**が
#: 要点 —— 指紋のほうは枚数が変わると跳ねるので、程度の判定には使えない。
RESP_GRID = 200

#: 「死に帯」とみなす傾き（帯の端での傾きに対する比）。
DEAD_SLOPE_RATIO = 0.05


def _shape_key(p: dict) -> tuple:
    """形の指紋。**この値が動かなければパラメータは効いていない。**

    ステーション枚数・先端高さ・最大高さ・窓の後端・ボアの始まりの 5 つ。
    形が変わればこのどれかは必ず動く（空洞ロフトはこの列から生える）。
    """
    st = pf.cavity_stations(p)
    hs = [s["h"] for s in st]
    return (len(st), round(hs[0], 6), round(max(hs), 6),
            round(pf.window_end_z(p), 6), round(pf.bore_start_z(p), 6))


def _mean_height(p: dict, grid: list[float]) -> float:
    """固定グリッドでの空洞の平均高さ [mm]。**応答の大きさを測る量。**"""
    return sum(cavity_h(p, z) for z in grid) / len(grid)


def cavity_h(p: dict, z: float) -> float:
    return pf.cavity_roof_y(p, z) - pf.cavity_floor_y(p, z)


#: 応答として意味のある傾きの上限 [mm / 単位]。これを超えたら測れていない。
#: 実際 `tip_opening` を 0 に寄せると天井と床がどちらも発散して 1e18 が出る
#: （`cavity_stations` は通ってしまうので `_cheap_ok` では捕まらない）。
#: **段 1〜2 を通ったからといって量が測れているとは限らない。**
MAX_SANE_SLOPE = 1e3


def _slope(comp, base: dict, key: str, v: float, step: float,
           grid: list[float]) -> float | None:
    """`key = v` の周りでの応答の傾き（平均高さ / 単位）。測れなければ `None`。"""
    lo, hi = dict(base, **{key: v - step}), dict(base, **{key: v + step})
    if _cheap_ok(comp, lo) or _cheap_ok(comp, hi):
        return None
    try:
        s = (_mean_height(hi, grid) - _mean_height(lo, grid)) / (2.0 * step)
    except Exception:                                     # noqa: BLE001
        return None
    if s != s or abs(s) > MAX_SANE_SLOPE:                  # NaN / 発散
        return None
    return s


def _cheap_ok(comp, p: dict) -> str | None:
    """段 1〜2。通れば `None`、駄目なら理由。"""
    err = comp.params_error(p)
    if err is not None:
        return f"params_error: {err[:70]}"
    try:
        st = pf.cavity_stations(p)
    except Exception as exc:                              # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"[:80]
    if len(st) < MIN_STATIONS:
        return f"ステーション {len(st)} 枚（< {MIN_STATIONS}）"
    h0 = st[0]["h"]
    if not (h0 == h0) or h0 > MAX_TIP_H_MM:               # NaN も弾く
        return f"先端の空洞高さ {h0:.3f}mm（> {MAX_TIP_H_MM}）"
    return None


def _build_ok(comp, p: dict) -> str | None:
    """段 3。OCCT を通す。通れば `None`。"""
    try:
        part = comp.build(p)
    except Exception as exc:                              # noqa: BLE001
        return f"RAISED {type(exc).__name__}: {exc}"[:80]
    solids = len(part.solids())
    if solids != 1:
        return f"ソリッド {solids} 個"
    if not (part.volume > 100.0):
        return f"体積 {part.volume:.1f}mm3"
    return None


def _walk(comp, base: dict, key: str, step: float,
          sign: int) -> tuple[float, str, float | None]:
    """帯の端から外へ 1 段ずつ歩く。

    返すのは（最後に通った値、止まった理由、**最後に形が動いた値**）。
    3 つ目が `None` なら、その向きへは**歩いても形が変わらなかった** ＝
    このパラメータはそこで効いていない。壁が無いのではなく、拘束が
    別のところで決まっている。
    """
    last = base[key]
    why = f"{OUT_STEPS} 段まで通った（打ち切り。壁はもっと外）"
    k0 = _shape_key(base)
    live = None
    for i in range(1, OUT_STEPS + 1):
        v = base[key] + sign * step * i
        p = dict(base, **{key: v})
        bad = _cheap_ok(comp, p)
        if bad is not None:
            why = f"{v:g} で止まった: {bad}"
            break
        if _shape_key(p) != k0:
            live = v
        last = v
    return last, why, live


def sweep(key: str, sizes=SIZES, do_build: bool = True,
          extra: dict | None = None) -> None:
    reg = get_registry()
    for size in sizes:
        comp = reg.get("saxophone").make_component("mouthpiece", size)
        base = {s.key: s.default for s in comp.param_specs()}
        spec = next((s for s in comp.param_specs() if s.key == key), None)
        if spec is None or spec.min is None or spec.max is None:
            print(f"== {size} / {key}: 数値パラメータではない。飛ばす", flush=True)
            continue
        if extra:
            base.update({k: v for k, v in extra.items() if k in base})
        step = spec.step or (spec.max - spec.min) / 40.0
        print(f"== {size} / {key} ==  帯 {spec.min:g}〜{spec.max:g}{spec.unit} "
              f"既定 {base[key]:g} 刻み {step:g}  [{spec.limit_kind}]"
              + (f"  拘束: {extra}" if extra else ""), flush=True)

        # 段 1〜2 で帯の外を歩く。**帯の端を起点にする** —— 帯の中は現行どおり
        # 通ることが前提で、そこが通らないならテンプレート側の問題。
        lo_base = dict(base, **{key: spec.min})
        hi_base = dict(base, **{key: spec.max})
        for edge, b, sign in (("下", lo_base, -1), ("上", hi_base, +1)):
            t0 = time.time()
            last, why, live = _walk(comp, b, key, step, sign)
            if live is None:
                # 歩いても形が動かない。**壁が無いのではなく効いていない。**
                print(f"  {edge}へ: {spec.min if sign < 0 else spec.max:g}"
                      f"{spec.unit} から先は**形が動かない**（この向きでは"
                      f"効いていない。拘束は別のところで決まっている）", flush=True)
                continue
            if live != last:
                print(f"  {edge}へ: 幾何は {last:g}{spec.unit} まで通るが、"
                      f"**形が動くのは {live:g}{spec.unit} まで**（その先は死に帯）"
                      f"  ({time.time() - t0:.1f}s)  {why}", flush=True)
                last = live
            else:
                print(f"  {edge}へ: 幾何は {last:g}{spec.unit} まで通る "
                      f"({time.time() - t0:.1f}s)  {why}", flush=True)
            # **応答の程度。** 「ソリッドが 1 個できる」は壁の条件であって、
            # つまみが効く条件ではない。帯の端と壁とで傾きを比べる。
            zb = pf.bore_start_z(base)
            grid = [zb * i / RESP_GRID for i in range(1, RESP_GRID + 1)]
            edge_v = spec.min if sign < 0 else spec.max
            s_edge = _slope(comp, base, key, edge_v, step, grid)
            s_wall = _slope(comp, base, key, last, step, grid)
            if s_edge and abs(s_edge) > 1e-12 and s_wall is not None:
                ratio = abs(s_wall) / abs(s_edge)
                print(f"    応答: 帯の端 {edge_v:g} で {s_edge:+.5f} / "
                      f"壁 {last:g} で {s_wall:+.5f} ＝ {ratio * 100:.0f}%",
                      flush=True)
                if ratio < DEAD_SLOPE_RATIO:
                    # 壁まで開けても空回りする。**どこまでなら効くか**を返す ——
                    # これが `hard_*` に入れるべき値（`baffle_height` の負側がこれ）。
                    live = edge_v
                    n = int(abs(last - edge_v) / step)
                    for i in range(1, n + 1):
                        v = edge_v + sign * step * i
                        s = _slope(comp, base, key, v, step, grid)
                        if s is None or abs(s) / abs(s_edge) < DEAD_SLOPE_RATIO:
                            break
                        live = v
                    print(f"    → **死に帯**（つまみが空回りする）。"
                          f"効くのは {live:g}{spec.unit} まで ＝ "
                          f"**hard_{'min' if sign < 0 else 'max'} はここ**",
                          flush=True)
            if not do_build:
                continue
            # 段 3 は境界の周りだけ。通った端・1 段内側・1 段外側の 3 点。
            for tag, v in (("内側", last - sign * step), ("端", last),
                           ("外側", last + sign * step)):
                p = dict(b, **{key: v})
                cheap = _cheap_ok(comp, p)
                if cheap is not None:
                    print(f"    {tag} {v:g}: 幾何で弾かれる（{cheap}）", flush=True)
                    continue
                t1 = time.time()
                bad = _build_ok(comp, p)
                warn = len(pf.cavity_warnings(p))
                print(f"    {tag} {v:g}: {'ok' if bad is None else '*** ' + bad}"
                      f"  ({time.time() - t1:.1f}s, 注意 {warn} 件)", flush=True)


def main(argv: list[str]) -> int:
    rest, flags, extra = [], set(), {}
    it = iter(argv[1:])
    for a in it:
        if a == "--with":
            k, _, v = next(it, "").partition("=")
            extra[k] = float(v)
        elif a.startswith("--"):
            flags.add(a)
        else:
            rest.append(a)
    if not rest and "--all" not in flags:
        print(__doc__)
        return 1
    reg = get_registry()
    comp = reg.get("saxophone").make_component("mouthpiece", "alto")
    if "--all" in flags:
        keys = [s.key for s in comp.param_specs() if s.min is not None]
    else:
        keys = [rest[0]]
    sizes = tuple(a for a in rest[1:] if a in SIZES) or SIZES
    for key in keys:
        sweep(key, sizes, do_build="--no-build" not in flags, extra=extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
