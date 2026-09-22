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
**固定グリッド**（ステーション数に依らない）で応答の傾きを測り、
**帯の端での傾きに対して 5% を割ったら死に帯**として報告する。
`baffle_height` の負側がこれで、ソリッドは −4.0 でも 1 個できるのに
**alto はそこで帯の端の 4%** しか動かない（効くのは −2.3 まで）。
死に帯と判定したときは**どこまでなら効くか**も探して出す ＝ それが
`hard_min` / `hard_max` に入れる値。

**そして「効いた」を見る目にも向きがある（Phase B-0 で判明）。** 初版の指紋と
応答量は**空洞の高さと z しか見ていなかった**ので、幅・断面積で効くパラメータ
（`side_rail_width` / `throat_ratio` / `chamber_ratio`）と外形で効くパラメータ
（`shank_dia` / `shoulder_fullness` / `tip_chamfer`）が、実際には形を動かして
いるのに**「効いていない」と誤判定される**。この掃引器が捕まえるために作られた
型に、掃引器自身が嵌まっていた。いまは 5 軸を見る:

  cavity_h / cavity_w / cavity_a … ステーション列を固定 z グリッドへ内挿
  outer_r  / beak_y              … 外形。**先端 0〜3mm は 0.05 刻み**
                                   （`tip_chamfer` の面取り長は 0.29mm しかなく、
                                    全長 60 等分のグリッドでは跨がれて消える）

**どの軸で測るかは決め打たない。** 帯の端で応答している軸をすべて拾い、
死に帯かどうかは**その中の最大の比**で判定する（`_ratios`）——1 本に決めてから
比べると、その軸だけが鈍っていた場合に「死に帯」と誤って報告してしまう。
どの軸で何 % だったかは必ず印字する ——**何で測ったかがログに残らない測定は
根拠にならない。** 1 軸だけで見たいときは `--axis` で絞れる。

拘束が効く条件を作るには `--with key=value` を重ねる。**choice も渡せる**
（`baffle_curvature` は `baffle_type=curve` のときだけ、`rollover_radius` は
`rollover` のときだけ生きる。既定は `step` なので、指定しないと永久に測れない）:

  ... sweep_limits.py chamber_to_bore_mm --with window_length=44
  ... sweep_limits.py baffle_curvature --with baffle_type=curve

**打ち切りは「段数 × 刻み」で決まる。** 既定 40 段なので、刻みの細い
パラメータは短い綱でしか歩けない ——`bore_dia` は刻み 0.05mm なので帯の端から
**2.0mm しか外へ出られず**、シャンクが残る限界が決める壁（実測で 3.8〜6.4mm 先）へ届かないまま
「40 段まで通った（打ち切り）」で終わる。**打ち切りを壁と読み違えないこと。**
綱は `--steps` で伸ばす（段 1〜2 は速いので伸ばしても数秒。段 3 は境界の
周りだけなので増えない）:

  ... sweep_limits.py bore_dia --steps 200

実行（WSL2 の SaxSketch 環境。リポジトリ直下で）:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_limits.py tip_opening
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_limits.py tip_opening alto
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_limits.py --all --no-build
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/sweep_limits.py tip_chamfer --axis outer_r

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

#: 帯の外へ何段まで歩くかの**既定**（`--steps` で上書き）。`min − STEPS·step`
#: まで見る。**届く距離は段数 × 刻み**なので、刻みの細いパラメータではここが
#: そのまま「未測定の始まる場所」になる（`bore_dia` は 0.05×40 ＝ 2.0mm）。
OUT_STEPS = 40

#: ステーションが退化したとみなす閾値。既定 3 サイズは 34〜43 枚、先端 0.60〜0.70mm。
MIN_STATIONS = 20
MAX_TIP_H_MM = 1.5

#: 応答を測る固定グリッドの分割数（空洞は 0〜bore_start_z を等分）。
#: **ステーション数に依らないこと**が要点 —— 指紋のほうは枚数が変わると
#: 跳ねるので、程度の判定には使えない。
RESP_GRID = 200

#: 外形グリッド。先端は密（`tip_chamfer` の面取り長 0.29mm を跨がないため）、
#: 胴は全長の等分。粗いグリッドだけだと `tip_chamfer` は「何も動かない」と出る。
TIP_GRID_N = 60
TIP_GRID_DZ = 0.05
OUTER_GRID_N = 60

#: 「死に帯」とみなす傾き（帯の端での傾きに対する比）。
DEAD_SLOPE_RATIO = 0.05

#: 応答を測る軸。**1 本に決めず、応答している軸すべてで比べる**（`_ratios`）。
AXES = ("cavity_h", "cavity_w", "cavity_a", "outer_r", "beak_y")

#: 軸を「動いた」とみなす相対変化の下限。これを下回る軸しか無ければ、
#: 形は動いていても**平均では捉えられない**ということなので、そう言う。
PICK_MIN_REL = 1e-9

#: 判定に使う軸の足切り（最も応答した軸の相対変化に対する比）。
#: **ほとんど動かない軸の「比」は当てにならない** —— 実測で
#: `chamber_to_bore_mm` の cavity_w は傾き 1e-4 しか無いのに比だけ 5396% と出て、
#: 最大を採ると本命の cavity_h（104%）を覆い隠した。桁の違う軸は最初から除く。
AXIS_KEEP = 0.5


def _interp(xs: list[float], ys: list[float], x: float) -> float:
    """ステーション列を固定 z グリッドへ内挿する（端は定数外挿）。

    ステーションは枚数も z も p によって変わるので、そのまま平均すると
    「枚数が変わっただけ」で応答が跳ねる。固定グリッドへ載せ替えて初めて
    **同じ物差しで**比べられる。
    """
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    t = (x - xs[lo]) / (xs[hi] - xs[lo])
    return ys[lo] + (ys[hi] - ys[lo]) * t


def _grids(p: dict) -> dict:
    """固定グリッド。**base の形から作り、掃引中は動かさない。**"""
    zb = pf.bore_start_z(p)
    length = p["overall_length"]
    cav = [zb * i / RESP_GRID for i in range(1, RESP_GRID + 1)]
    tip = [0.001 + TIP_GRID_DZ * i for i in range(TIP_GRID_N)]
    body = [length * i / OUTER_GRID_N for i in range(1, OUTER_GRID_N + 1)]
    return {"cav": cav, "outer": tip + body}


def _axes(p: dict, grids: dict) -> dict:
    """5 軸のベクトル ＋ 指紋専用の離散量。

    `outer_r` / `beak_y` は `min(z, L − ε)` で当該形状の端に丸める ——
    `overall_length` 自身を掃引するときにグリッドが部品の外へ出るため。

    **`beak_y` は胴の頂点で頭打ちにする（Phase B-4b で直した）。**
    `pf.beak_y` はビーク稜線の**解析式**で、稜線が胴の外へ出ても線形に伸び
    続ける ——だが部品の上面は `min(稜線, 外半径)` なので、そこから先は
    形が 1 ビットも動かない。直す前は `beak_height` を既定の 4 倍
    （soprano 48.8mm）まで上げても「beak_y 100% 生きている」と報告して
    いた。実際には 0.53〜0.58·`body_dia` から先は死んでいる。
    **式を測っていて形を測っていない**型で、同じ日に `sweep_outer.py` の
    主張 (1) でも出た（あちらは `heel_z` の式）。

    既定では稜線は胴の内側にあるので、この頭打ちは B-1〜B-4a の掃引には
    掛からない（`tip_opening` を回し直して committed ログと一致を確認済み。
    `docs/sweeps/b4b-outer-curves.txt` の §3）。
    """
    st = pf.cavity_stations(p)
    zs = [s["z"] for s in st]
    hs = [s["h"] for s in st]
    ws = [s["w"] for s in st]
    ar = [pf.section_area(s) for s in st]
    cav = grids["cav"]
    lim = p["overall_length"] - 1e-6
    return {
        "cavity_h": tuple(_interp(zs, hs, z) for z in cav),
        "cavity_w": tuple(_interp(zs, ws, z) for z in cav),
        "cavity_a": tuple(_interp(zs, ar, z) for z in cav),
        "outer_r": tuple(pf.outer_radius(p, min(z, lim)) for z in grids["outer"]),
        "beak_y": tuple(min(pf.beak_y(p, min(z, lim)),
                            pf.outer_radius(p, min(z, lim)))
                        for z in grids["outer"]),
        "_disc": (float(len(st)), pf.window_end_z(p), pf.bore_start_z(p)),
    }


def _mean(v) -> float:
    return sum(v) / len(v)


def _scale(v) -> float:
    """軸の大きさ。**平均ではなく絶対値の平均**で測る。

    `beak_y` は 0 を跨ぐので平均が 0 近くになり、平均で正規化すると
    相対変化が跳ね上がって**どのパラメータでもこの軸が勝ってしまう**
    （実測: `tip_opening` で beak_y 6.9e-3 vs cavity_h 3.8e-3）。
    軸選びが単位ではなく零点の置き方で決まるのは、測っていることにならない。
    """
    return sum(abs(x) for x in v) / len(v)


def _fingerprint(ax: dict) -> tuple:
    """形の指紋。**この値が動かなければパラメータは効いていない。**

    5 軸すべてと、ステーション枚数・窓の後端・ボアの始まり。初版は空洞の
    高さと z しか見ていなかったので、幅だけ動くパラメータを取り落としていた。
    """
    return tuple(tuple(round(x, 7) for x in ax[k]) for k in AXES) + (
        tuple(round(x, 7) for x in ax["_disc"]),)


#: 応答として意味のある傾きの上限 [単位 / パラメータ単位]。これを超えたら測れていない。
#: 実際 `tip_opening` を 0 に寄せると天井と床がどちらも発散して 1e18 が出る
#: （`cavity_stations` は通ってしまうので `_cheap_ok` では捕まらない）。
#: **段 1〜2 を通ったからといって量が測れているとは限らない。**
MAX_SANE_SLOPE = 1e3


def _pair(comp, base: dict, key: str, v: float, step: float,
          grids: dict) -> tuple[dict, dict, dict] | None:
    """`v ± step` の軸ベクトル（と base の軸）。片方でも幾何が落ちれば `None`。"""
    lo, hi = dict(base, **{key: v - step}), dict(base, **{key: v + step})
    if _cheap_ok(comp, lo) or _cheap_ok(comp, hi):
        return None
    try:
        return _axes(base, grids), _axes(lo, grids), _axes(hi, grids)
    except Exception:                                     # noqa: BLE001
        return None


def _probe(comp, base: dict, key: str, v: float, step: float,
           grids: dict) -> tuple[dict, dict] | None:
    """`key = v` の周りで**全軸まとめて**傾きと相対変化を測る。

    返すのは (軸→傾き, 軸→相対変化)。測れない軸は傾きの側から落ちる
    （NaN・発散。`tip_opening` を 0 に寄せると天井と床が発散して 1e18 が出るが
    `cavity_stations` は通ってしまうので、ここで弾かないと嘘の数字が残る）。

    **1 本の軸を選んで測るのはやめた。** 軸選びは零点の置き方でぶれるし
    （`beak_y` は 0 を跨ぐので平均正規化だと何でもこの軸が勝つ）、そもそも
    知りたいのは「**どの軸で見ても死んでいるか**」だから —— 死に帯の判定は
    応答している軸すべての中の**最大**で下す（`sweep`）。
    """
    trio = _pair(comp, base, key, v, step, grids)
    if trio is None:
        return None
    a0, al, ah = trio
    slopes, rels = {}, {}
    for name in AXES:
        d = _mean(ah[name]) - _mean(al[name])
        rels[name] = abs(d) / (_scale(a0[name]) + 1e-9)
        s = d / (2.0 * step)
        if s == s and abs(s) <= MAX_SANE_SLOPE:            # NaN / 発散を落とす
            slopes[name] = s
    return slopes, rels


def _kept(rels: dict, only: list | None) -> list:
    """判定に使う軸。**帯の端で最も応答した軸（本命）から桁が近いものだけ。**

    本命 1 本だけで判定すると、その軸だけが鈍っていたときに「死に帯」と
    誤報する。逆に全軸の最大を採ると、**傾きが 1e-4 しか無い軸の比**
    （ノイズ）が本命を覆い隠す。間を取って、本命の `AXIS_KEEP` 倍以上
    応答している軸を残し、**本命で判定して残りは並べて出す**。
    """
    if only:
        return list(only)
    live = [(rels.get(n, 0.0), n) for n in AXES if rels.get(n, 0.0) >= PICK_MIN_REL]
    if not live:
        return []
    live.sort(reverse=True)
    top = live[0][0]
    return [n for r, n in live if r >= AXIS_KEEP * top]


def _ratios(pe, pw, only: list | None = None):
    """帯の端（`pe`）に対する壁（`pw`）での応答比。

    返すのは (**本命の軸の比**, 本命の軸名, ログ用の内訳, 残りの軸の比)。
    判定は本命で下し、残りは並べて出す —— 軸によって食い違うときに
    それが見えないと、「何で測ったか」がログから消える。
    """
    s_edge, rels = pe
    s_wall, _rw = pw
    out = []
    for n in _kept(rels, only):
        a, b = s_edge.get(n), s_wall.get(n)
        if a is None or b is None or abs(a) <= 1e-12:
            continue
        out.append((rels.get(n, 0.0), abs(b) / abs(a), n, a, b))
    if not out:
        return None
    out.sort(reverse=True)                    # 応答の強い順 ＝ 先頭が本命
    detail = " / ".join(f"{n} {a:+.5f}→{b:+.5f} {r * 100:.0f}%"
                        for _rel, r, n, a, b in out)
    return out[0][1], out[0][2], detail, [(r, n) for _rel, r, n, _a, _b in out[1:]]


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


def _walk(comp, base: dict, key: str, step: float, sign: int,
          grids: dict, steps: int = OUT_STEPS) -> tuple[float, str, float | None]:
    """帯の端から外へ 1 段ずつ歩く。

    返すのは（最後に通った値、止まった理由、**最後に形が動いた値**）。
    3 つ目が `None` なら、その向きへは**歩いても形が変わらなかった** ＝
    このパラメータはそこで効いていない。壁が無いのではなく、拘束が
    別のところで決まっている。
    """
    last = base[key]
    why = (f"{steps} 段まで通った（打ち切り ＝ 帯の端から "
           f"{steps * step:g} 外まで。**その先は未測定**。--steps で伸ばせる）")
    k0 = _fingerprint(_axes(base, grids))
    live = None
    for i in range(1, steps + 1):
        v = base[key] + sign * step * i
        p = dict(base, **{key: v})
        bad = _cheap_ok(comp, p)
        if bad is not None:
            why = f"{v:g} で止まった: {bad}"
            break
        try:
            moved = _fingerprint(_axes(p, grids)) != k0
        except Exception as exc:                          # noqa: BLE001
            why = f"{v:g} で止まった: 指紋 {type(exc).__name__}: {exc}"[:90]
            break
        if moved:
            live = v
        last = v
    return last, why, live


def _build_around(comp, b: dict, key: str, last: float, step: float,
                  sign: int) -> None:
    """段 3 は境界の周りだけ。通った端・1 段内側・1 段外側の 3 点。

    `last` は**死に帯で引き戻したあとの壁**であること —— 引き戻す前の点を
    ビルドすると、検証している場所が結論と違う（一度そうなっていた）。
    """
    for tag, v in (("内側", last - sign * step), ("端", last),
                   ("外側", last + sign * step)):
        p = dict(b, **{key: v})
        cheap = _cheap_ok(comp, p)
        if cheap is not None:
            print(f"    {tag} {v:g}: 幾何で弾かれる（{cheap}）", flush=True)
            continue
        t1 = time.time()
        bad = _build_ok(comp, p)
        # **部品に聞く**（`pf.cavity_warnings` を直に数えない）。注意の出所は
        # `profiles` に複数あり、B-3 で `shank_warnings` が増えたときここだけ
        # 取り残された —— シャンクの肉厚が薄くなる掃引で**まさに出る注意**を
        # 道具が落とす。`Component.warnings` が唯一の集約点（`registry.py`）。
        warn = len(comp.warnings(p))
        print(f"    {tag} {v:g}: {'ok' if bad is None else '*** ' + bad}"
              f"  ({time.time() - t1:.1f}s, 注意 {warn} 件)", flush=True)


def sweep(key: str, sizes=SIZES, do_build: bool = True,
          extra: dict | None = None, axis: str | None = None,
          steps: int = OUT_STEPS) -> None:
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
        grids = _grids(base)
        # **その組での実効の壁も印字する**（Phase 4-E B-5）。9 本は壁が相手で
        # 動くので、「帯 14〜28」だけ見ていると、この掃引がどこまで歩ける条件で
        # 走ったのかが後から読めない ——何を相手に測ったかがログに残らない測定は
        # 根拠にならない（B-0 で軸について言ったのと同じ）。
        b5 = comp.param_bounds(base).get(key)
        wall = ""
        if b5:
            lo = b5.get("lo")
            hi = b5.get("hi")
            wall = ("  実効の壁 "
                    + (f"{lo:g}" if lo is not None else "—")
                    + "〜" + (f"{hi:g}" if hi is not None else "—")
                    + f"（{'・'.join(dict.fromkeys(x for x in (b5.get('lo_by'), b5.get('hi_by')) if x))}で動く）")
        print(f"== {size} / {key} ==  帯 {spec.min:g}〜{spec.max:g}{spec.unit} "
              f"既定 {base[key]:g} 刻み {step:g}  [{spec.limit_kind}]{wall}"
              + (f"  拘束: {extra}" if extra else ""), flush=True)

        # 段 1〜2 で帯の外を歩く。**帯の端を起点にする** —— 帯の中は現行どおり
        # 通ることが前提で、そこが通らないならテンプレート側の問題。
        lo_base = dict(base, **{key: spec.min})
        hi_base = dict(base, **{key: spec.max})
        for edge, b, sign in (("下", lo_base, -1), ("上", hi_base, +1)):
            t0 = time.time()
            # **帯の端そのものを先に試す。** `_walk` は端を起点にして外へ歩くだけ
            # なので、端が既に弾かれていても「1 段外で壁」としか言えない ——
            # `shank_dia` の帯の下端 14.0 はアルト（ボア 15.8）・テナー（17.0）で
            # **端そのものが通らない**のに、そう読める行が 1 行も出なかった。
            # 帯は「勧める」ものなので、端が通らないなら壁より先に帯が誤り。
            edge_bad = _cheap_ok(comp, b)
            if edge_bad is not None:
                print(f"  {edge}へ: **帯の端 {b[key]:g}{spec.unit} 自体が"
                      f"通らない**（帯が壁の外へはみ出している）: {edge_bad}",
                      flush=True)
                continue
            last, why, live = _walk(comp, b, key, step, sign, grids, steps)
            if live is None:
                # 形が動かないまま終わった。**2 つの別の話が同じ枝に来る** ——
                #   (a) 1 段も進めなかった: 帯の端の**すぐ外に壁がある**。
                #       理由は `why` が持っている（`params_error` の文面）。
                #   (b) 歩けたのに指紋が変わらない: この向きでは効いていない。
                # 初版は (a) にも「効いていない。拘束は別のところで決まって
                # いる」と書いていた。**当たってはいるが、どこで決まっているかを
                # 測ったのに捨てていた** —— `body_dia` を下へ掃くと 1 段目で
                # 「最大径がシャンク径より細い」が返るのに、ログには壁が
                # 1 文字も残らなかった。`last` が起点のままかどうかで分かれる。
                stuck = last == b[key]
                head = (f"  {edge}へ: {spec.min if sign < 0 else spec.max:g}"
                        f"{spec.unit} ")
                if stuck:
                    print(head + f"の 1 段外で**壁**。{why}", flush=True)
                else:
                    print(head + f"から先は**形が動かない**（この向きでは"
                          f"効いていない。拘束は別のところで決まっている）"
                          f"  {why}", flush=True)
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
            edge_v = spec.min if sign < 0 else spec.max
            use = [axis] if axis else None
            pe = _probe(comp, base, key, edge_v, step, grids)
            pw = _probe(comp, base, key, last, step, grids)
            base_ratio = (None if pe is None or pw is None
                          else _ratios(pe, pw, use))
            if pw is None or pe is None:
                # 壁のすぐ外（または帯の端の外）で幾何が落ちるので、中心差分が
                # 取れない。**「応答が測れない」と「応答が無い」は別物** ——
                # ここは前者で、壁は段 1〜2 が決めている。
                where = "壁" if pw is None else "帯の端"
                print(f"    応答: {where}のすぐ外で幾何が落ちるので中心差分が"
                      f"取れない（壁は段 1〜2 が決めている）", flush=True)
                base_ratio = None
            elif base_ratio is None:
                # 形は動いたのに、どの軸の平均でも動かない。**判定を保留する** ——
                # ここで 0 を返すと「死に帯」と嘘をつくことになる。
                print("    応答: **どの軸の平均でも捉えられない**（判定保留）",
                      flush=True)
            if base_ratio is None:
                if do_build:
                    _build_around(comp, b, key, last, step, sign)
                continue
            ratio, prime, detail, alt = base_ratio
            print(f"    応答[本命 {prime}]: 帯の端 {edge_v:g} → 壁 {last:g} で "
                  f"**{ratio * 100:.0f}%**  [{detail}]", flush=True)
            if ratio < DEAD_SLOPE_RATIO and any(r >= DEAD_SLOPE_RATIO
                                                for r, _n in alt):
                # 本命は死んでいるのに別の軸は生きている。**判定を保留する** ——
                # どちらか一方だけ書くと、書かなかったほうが消える。
                alive = ", ".join(f"{n} {r * 100:.0f}%" for r, n in alt
                                  if r >= DEAD_SLOPE_RATIO)
                print(f"    → **軸によって食い違う**（本命 {prime} は死に帯だが "
                      f"{alive} は生きている）。人が決めること", flush=True)
            elif ratio >= DEAD_SLOPE_RATIO and any(r < DEAD_SLOPE_RATIO
                                                   for r, _n in alt):
                # 逆向きの食い違い。**本命が生きていると、死んでいる軸が隠れる** ——
                # `tip_opening` の beak_y のように「どこまでも線形に効く」軸が
                # 本命になると、空洞側が死んでいても 100% と出てしまう。
                dead = ", ".join(f"{n} {r * 100:.0f}%" for r, n in alt
                                 if r < DEAD_SLOPE_RATIO)
                print(f"    → 注意: 本命 {prime} は生きているが "
                      f"{dead} は死に帯。**本命の陰に隠れる**ので人が決めること",
                      flush=True)
            elif ratio < DEAD_SLOPE_RATIO:
                # 壁まで開けても空回りする。**どこまでなら効くか**を返す ——
                # これが `hard_*` に入れるべき値（`baffle_height` の負側がこれ）。
                live = edge_v
                n = int(abs(last - edge_v) / step)
                for i in range(1, n + 1):
                    v = edge_v + sign * step * i
                    pv = _probe(comp, base, key, v, step, grids)
                    r = (None if pv is None
                         else _ratios(pe, pv, use or [prime]))
                    if r is None or r[0] < DEAD_SLOPE_RATIO:
                        break
                    live = v
                print(f"    → **死に帯**（つまみが空回りする）。"
                      f"効くのは {live:g}{spec.unit} まで ＝ "
                      f"**hard_{'min' if sign < 0 else 'max'} はここ**",
                      flush=True)
                # 壁をここへ引き戻す。**でないと段 3 が使いもしない点を
                # ビルドして「ok」と言う** —— 検証している場所が結論と
                # 違うのは、検証していないのと同じ。
                last = live
            if do_build:
                _build_around(comp, b, key, last, step, sign)


def parse_args(argv: list[str]) -> tuple[list, set, dict, str | None, int]:
    """引数を (対象, フラグ, 拘束, 軸) に分ける。

    `--with` は **float でなければ文字列のまま渡す** —— `baffle_curvature` は
    `baffle_type="curve"` のとき、`rollover_radius` は `"rollover"` のときしか
    形を動かさない。既定は `"step"` なので、choice を固定できない掃引器では
    **この 2 本は永久に測れない**（「効いていない」と出るだけ）。
    """
    rest, flags, extra = [], set(), {}
    axis, steps = None, OUT_STEPS
    it = iter(argv)
    for a in it:
        if a == "--with":
            k, _, v = next(it, "").partition("=")
            try:
                extra[k] = float(v)
            except ValueError:
                extra[k] = v
        elif a == "--axis":
            axis = next(it, "")
        elif a == "--steps":
            steps = int(next(it, "") or OUT_STEPS)
        elif a.startswith("--"):
            flags.add(a)
        else:
            rest.append(a)
    return rest, flags, extra, axis, steps


def main(argv: list[str]) -> int:
    # **ログは根拠そのものなので、読める文字で出す。** Windows でリダイレクト
    # すると既定が CP932 になり、`docs/sweeps/` に残した生ログが化けていた。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rest, flags, extra, axis, steps = parse_args(argv[1:])
    if axis is not None and axis not in AXES:
        print(f"--axis は {AXES} のどれか（{axis!r} は無い）")
        return 2
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
        sweep(key, sizes, do_build="--no-build" not in flags, extra=extra,
              axis=axis, steps=steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
