# -*- coding: utf-8 -*-
"""実物を採寸するときの「どの変数がどこか」の図を SVG で書き出す。

ノギスを当てる位置とパラメータ名の対応が分からないと、実測を入れる作業そのものが
できない。テンプレートの現在値から `profiles` の形状関数で描くので、実測を
入れ替えたあと再生成すれば新旧の比較図がそのまま出る。

2 枚出す:
  側面断面    軸方向の寸法（全長・ボア長・ウィンドウ長・フェイシング長・
              コーク挿入深さ・シャンク長・ビーク高さ・ティップ開き）
  リード面平面図  径と幅（ボディ径・シャンク径・ボア径・リード幅）

**軸方向の基準は 2 つある。** `facing_length` / `window_length` はティップ（z=0）
から、`bore_length` / `cork_depth` / `shank_length` はシャンク端から測る。
図でもそれが読めるように寸法線の向きを分けてある。

出力: measure_<size>.svg

実行:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/measure_soprano.py
  ... --size tenor
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.core.registry import get_registry  # noqa: E402
from saxsketch.core.schema import ParamSet  # noqa: E402
from saxsketch.instruments.saxophone.components import profiles  # noqa: E402

BG, INK, MUTED, DIM = "#ffffff", "#2b3442", "#8b96a6", "#d85a30"
CAVITY, TABLE = "#378add", "#d85a30"
#: 図の余白 [px] と左端の原点
PAD_X, WIDTH = 46.0, 680.0


def _fmt(pts) -> str:
    return " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}"
                    for i, (x, y) in enumerate(pts))


def _width(s: str, fs: int) -> float:
    """文字列の描画幅の見積り [px]。全角は 11px 固定、半角は字送り 0.58em。"""
    return sum(11.0 if ord(c) > 0x2000 else fs * 0.58 for c in s)


def _text(x: float, y: float, s: str, anchor: str = "middle", fs: int = 12,
          fill: str = INK) -> str:
    """図の左右にはみ出さない位置へ寄せてからテキストを置く。

    ラベルは寸法線の中央に置きたいが、シャンク側の寸法は右端に寄るので素直に
    中央寄せすると viewBox の外へ出る（実際に `shank_length` と `bore_dia` が
    出ていた）。寄せる向きだけ変えて、線との対応はリーダー線が保つ。
    """
    w = _width(s, fs)
    x0 = x if anchor == "start" else (x - w / 2 if anchor == "middle" else x - w)
    x0 = min(max(x0, 8.0), WIDTH - 8.0 - w)
    return (f'<text x="{x0:.1f}" y="{y:.1f}" text-anchor="start" '
            f'font-size="{fs}" fill="{fill}">{s}</text>')


def _dim_h(x0, x1, y, label, tick=4.0) -> str:
    """水平寸法線（両端に短いティック、ラベルは線の上）。"""
    return (f'<path d="M{x0:.1f},{y:.1f} L{x1:.1f},{y:.1f} '
            f'M{x0:.1f},{y - tick:.1f} L{x0:.1f},{y + tick:.1f} '
            f'M{x1:.1f},{y - tick:.1f} L{x1:.1f},{y + tick:.1f}" '
            f'fill="none" stroke="{DIM}" stroke-width="1.2"/>\n'
            + _text((x0 + x1) / 2, y - 9, label))


def _dim_v(x, y0, y1, label, ly, tick=7.0) -> str:
    """垂直寸法線。`ly` はラベルのベースライン（呼び出し側が図の上下端から決める）。"""
    return (f'<path d="M{x:.1f},{y0:.1f} L{x:.1f},{y1:.1f} '
            f'M{x - tick:.1f},{y0:.1f} L{x + tick:.1f},{y0:.1f} '
            f'M{x - tick:.1f},{y1:.1f} L{x + tick:.1f},{y1:.1f}" '
            f'fill="none" stroke="{DIM}" stroke-width="1.3"/>\n'
            + _text(x, ly, label))


def _lead(x, y0, y1) -> str:
    return (f'<path d="M{x:.1f},{y0:.1f} L{x:.1f},{y1:.1f}" fill="none" '
            f'stroke="{MUTED}" stroke-width="0.7" stroke-dasharray="2 3"/>')


def side_view(p: dict, s: float, cy: float) -> tuple[str, float]:
    """側面断面（軸方向の寸法）。返り値は (svg断片, 図の下端 y)。"""
    L = p["overall_length"]

    def X(z):
        return PAD_X + z * s

    def Y(y):
        return cy - y * s

    n = 90
    zs = [L * i / n for i in range(n + 1)]
    top = [(X(z), Y(min(profiles.beak_apex_y(p, z), profiles.outer_radius(p, z))))
           for z in zs]
    bot = [(X(z), Y(max(-profiles.outer_radius(p, z), profiles.cut_top_y(p, z))))
           for z in zs]
    body = _fmt(top + bot[::-1]) + " Z"

    st = profiles.cavity_stations(p)
    r_bore = profiles.bore_radius(p)
    cav = ([(X(q["z"]), Y(q["yc"] + q["h"] / 2)) for q in st] + [(X(L), Y(r_bore))]
           + [(X(L), Y(-r_bore))]
           + [(X(q["z"]), Y(max(q["yc"] - q["h"] / 2, profiles.cut_top_y(p, q["z"]))))
              for q in reversed(st)])

    tce = profiles.table_cut_end_z(p)
    heel = profiles.heel_z(p)
    zb = profiles.bore_start_z(p)
    z_we = profiles.window_end_z(p)
    z_wf = profiles.window_front_z(p)
    bite = 0.25 * L
    y_bot = max(y for _, y in bot)
    # ラベル帯は**実際に描いた図の上端**から決める。ビーク稜線は最大半径より上へ
    # 出るので、`body_dia/2` から逆算すると図に食い込む。
    y_lab = min(y for _, y in top) - 10.0

    out = [
        f'<path d="{body}" fill="{MUTED}" fill-opacity="0.16" stroke="{INK}" '
        f'stroke-width="1.6" stroke-linejoin="round"/>',
        f'<path d="{_fmt(cav)} Z" fill="{CAVITY}" fill-opacity="0.16" '
        f'stroke="{CAVITY}" stroke-width="1.3" stroke-linejoin="round"/>',
        f'<path d="M{X(0):.1f},{Y(profiles.table_plane_y(p, 0.0)):.1f} '
        f'L{X(tce):.1f},{Y(profiles.table_plane_y(p, tce)):.1f}" fill="none" '
        f'stroke="{TABLE}" stroke-width="1.2" stroke-dasharray="5 3"/>',
    ]

    # 縦の寸法（テーブル平面が基準）。ラベルは 2 段に分けて重なりを避ける。
    y_beak = Y(profiles.beak_apex_y(p, bite))
    y_tab = Y(profiles.table_plane_y(p, bite))
    out.append(_dim_v(X(bite), y_beak, y_tab, f"beak_height {p['beak_height']:.2f}",
                      ly=y_lab))
    out.append(_lead(X(bite), y_lab + 4, y_beak - 3))
    y_t0 = Y(profiles.table_plane_y(p, 0.0))
    y_tip = Y(-profiles.outer_radius_nominal(p, 0.0))
    out.append(_dim_v(X(0.0), y_tip, y_t0, f"tip_opening {p['tip_opening']:.2f}",
                      ly=y_lab - 16.0))
    out.append(_lead(X(0.0), y_lab - 12.0, y_tip - 3))
    out.append(_text(X(heel), y_lab - 16.0, "最大径 ＝ リード踵"))
    out.append(_lead(X(heel), y_lab - 12.0, Y(profiles.outer_radius(p, heel)) - 3))

    # 軸方向の寸法。ティップ基準 → シャンク端基準の順に下へ積む
    base = y_bot + 12.0
    rows = [
        (0.0, p["facing_length"], f"facing_length {p['facing_length']:.1f}"),
        # 引いている線は z_wf→z_we（実際に開く窓）なので、数字も実効値で出す。
        # 指定値はボアの始まりで頭打ちになることがある（window_length_effective）。
        (z_wf, z_we, f"window_length {profiles.window_length_effective(p):.2f}"),
        (zb, L, f"bore_length {p['bore_length']:.1f}"),
        (L - p["cork_depth"], L, f"cork_depth {p['cork_depth']:.1f}"),
        (L - profiles.shank_length(p), L,
         f"shank_length {profiles.shank_length(p):.2f}"),
        (0.0, L, f"overall_length {L:.1f}"),
    ]
    for i, (a, b, label) in enumerate(rows):
        y = base + 22.0 * i + (4.0 if i == len(rows) - 1 else 0.0)
        out.append(_dim_h(X(a), X(b), y, label))
    last_y = base + 22.0 * (len(rows) - 1) + 4.0
    for z in (0.0, p["facing_length"], z_we, zb, L - p["cork_depth"],
              L - profiles.shank_length(p), L):
        out.append(_lead(X(z), y_bot + 2, last_y - 6))
    return "\n".join(out), last_y


def plan_view(p: dict, s: float, cy: float) -> tuple[str, float]:
    """リード面から見た図（径と幅）。"""
    L = p["overall_length"]

    def X(z):
        return PAD_X + z * s

    def Y(w):
        return cy - w * s

    n = 90
    zs = [L * i / n for i in range(n + 1)]
    sil = ([(X(z), Y(profiles.outer_radius(p, z))) for z in zs]
           + [(X(z), Y(-profiles.outer_radius(p, z))) for z in reversed(zs)])
    tce = profiles.table_cut_end_z(p)
    zt = [tce * i / 70 for i in range(71)]
    tab = ([(X(z), Y(profiles.reed_chord(p, z) / 2)) for z in zt]
           + [(X(z), Y(-profiles.reed_chord(p, z) / 2)) for z in reversed(zt)])

    z0, z1 = profiles.window_open_z(p), profiles.window_end_z(p)
    hw = profiles.window_width(p) / 2.0
    win_t, win_b, taper = [], [], 6.0
    for i in range(81):
        z = z0 + (z1 - z0) * i / 80
        h = min(profiles.cavity_half_width(p, z), hw)
        if z > z1 - taper:
            u = (z - (z1 - taper)) / taper
            h *= math.sqrt(max(1.0 - u * u, 0.0))
        win_t.append((X(z), Y(h)))
        win_b.append((X(z), Y(-h)))

    zb = profiles.bore_start_z(p)
    heel = profiles.heel_z(p)
    r_bore = profiles.bore_radius(p)
    r_sh = profiles.shank_radius(p)
    z_sh = 0.5 * (profiles.shank_start_z(p) + L)
    reed_w = p["reed_width"] / 2.0

    y_top = min(y for _, y in sil) - 10.0
    y_bot = max(y for _, y in sil) + 26.0

    out = [
        f'<path d="{_fmt(sil)} Z" fill="{MUTED}" fill-opacity="0.12" stroke="{INK}" '
        f'stroke-width="1.6" stroke-linejoin="round"/>',
        f'<path d="{_fmt(tab)} Z" fill="{MUTED}" fill-opacity="0.16" stroke="{INK}" '
        f'stroke-width="0.9"/>',
        f'<path d="M{X(zb):.1f},{Y(r_bore):.1f} L{X(L):.1f},{Y(r_bore):.1f} '
        f'M{X(zb):.1f},{Y(-r_bore):.1f} L{X(L):.1f},{Y(-r_bore):.1f} '
        f'M{X(zb):.1f},{Y(r_bore):.1f} L{X(zb):.1f},{Y(-r_bore):.1f}" fill="none" '
        f'stroke="{CAVITY}" stroke-width="1" stroke-dasharray="6 4" opacity="0.85"/>',
        f'<path d="{_fmt(win_t + win_b[::-1])} Z" fill="{CAVITY}" fill-opacity="0.22" '
        f'stroke="{CAVITY}" stroke-width="1.2"/>',
        _text(X(0.5 * (z0 + z1)), cy + 4, "ウィンドウ（窓）"),
    ]
    # 上段 = body_dia / bore_dia、下段 = reed_width / shank_dia。同じ段では z が
    # 離れているものだけを並べる（ラベル幅は 100〜120px あるので近いと必ず重なる）。
    top = Y(profiles.outer_radius(p, heel))
    bottom = Y(-profiles.outer_radius(p, heel))
    out.append(_dim_v(X(heel), top, bottom, f"body_dia φ{p['body_dia']:.2f}",
                      ly=y_top - 16.0))
    out.append(_lead(X(heel), y_top - 12.0, top - 3))
    out.append(_dim_v(X(L * 0.985), Y(r_bore), Y(-r_bore),
                      f"bore_dia φ{p['bore_dia']:.2f}", ly=y_top))
    out.append(_lead(X(L * 0.985), y_top + 4, Y(r_bore) - 3))
    z_rw = 0.5 * (z1 + tce)
    out.append(_dim_v(X(z_rw), Y(reed_w), Y(-reed_w),
                      f"reed_width {p['reed_width']:.2f}", ly=y_bot))
    out.append(_lead(X(z_rw), Y(-reed_w) + 3, y_bot - 10.0))
    out.append(_dim_v(X(z_sh), Y(r_sh), Y(-r_sh), f"shank_dia φ{p['shank_dia']:.2f}",
                      ly=y_bot + 16.0))
    out.append(_lead(X(z_sh), Y(-r_sh) + 3, y_bot + 6.0))
    return "\n".join(out), y_bot + 16.0


def render(size: str) -> Path:
    comp = get_registry().get("saxophone").make_component("mouthpiece", size)
    p = dict(ParamSet(comp.param_specs(), comp.template["mouthpiece"]).values)
    L = p["overall_length"]
    s = (WIDTH - 2 * PAD_X - 28.0) / L          # 等尺。右に寸法ラベルの余白を残す
    r_max = p["body_dia"] / 2.0

    # ビーク稜線は最大半径より上へ出るので、側面図の上端は body_dia からは決まらない。
    # ラベル 2 段（32px）ぶんの余白を上に確保してから図を置く。
    side, side_bottom = side_view(p, s, 84.0 + p["beak_height"] * s)
    gap = side_bottom + 60.0
    plan, plan_bottom = plan_view(p, s, gap + 32.0 + r_max * s)
    height = plan_bottom + 54.0

    # SVG の <text> は折り返さないので、行は自分で分ける。
    legend = "ティップ（左端）基準: facing_length / window_length"
    legend2 = "シャンク端（右端）基準: bore_length / cork_depth / shank_length"
    legend3 = (f"赤破線 ＝ テーブル平面（軸に {p['table_angle']:.2f}° 傾く）／"
               f"青 ＝ 内部空洞・ボア")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH:.0f}" \
height="{height:.0f}" viewBox="0 0 {WIDTH:.0f} {height:.0f}">
<rect width="100%" height="100%" fill="{BG}"/>
<text x="{PAD_X:.0f}" y="24" font-size="14" fill="{INK}">\
{comp.template['label']} マウスピース 採寸図 — 単位 mm</text>
<text x="{PAD_X:.0f}" y="{gap - 8:.1f}" font-size="12" fill="{MUTED}">\
リード面から見た図（径と幅）</text>
{side}
{plan}
<text x="{PAD_X:.0f}" y="{height - 38:.1f}" font-size="11" fill="{MUTED}">{legend}</text>
<text x="{PAD_X:.0f}" y="{height - 24:.1f}" font-size="11" fill="{MUTED}">{legend2}</text>
<text x="{PAD_X:.0f}" y="{height - 10:.1f}" font-size="11" fill="{MUTED}">{legend3}</text>
</svg>
"""
    out = _HERE / f"measure_{size}.svg"
    out.write_text(svg, encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="soprano", choices=["soprano", "alto", "tenor"])
    args = ap.parse_args()
    path = render(args.size)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
