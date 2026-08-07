# -*- coding: utf-8 -*-
"""断面エディタが実際に描くものを SVG として書き出す（ドキュメント用）。

`MouthpieceComponent.section()` の返り値だけを使って、フロントの
`SectionEditor.tsx` と同じ線・同じ色で描く。アプリを起動しなくても
「編集画面に何が出るか」を確認・添付できるようにするためのもの。

出力: section_ui.svg（バッフル3型を縦に並べたもの）

実行:
  PYTHONPATH=. ~/mp_design/.venv/bin/python cad/baffle/render_section_ui.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from saxsketch.core.registry import get_registry  # noqa: E402

OUT = _HERE / "section_ui.svg"

#: SectionEditor.tsx / styles.css と同じ色。図とアプリの見た目を揃えるための写し。
STYLE = {
    "outer": ("#2b3442", "#55637a", 1.2),
    "limit": ("none", "#6b7a90", 1.0),
    "reed": ("none", "#e07a7a", 1.4),
    "roof": ("none", "#4da3ff", 2.0),
    "floor": ("none", "#7ec8a8", 1.4),
}
BG, HANDLE, TEXT, MUTED = "#14171c", "#e6b45a", "#dde4ee", "#8b96a6"


def _d(pts, close_with=None) -> str:
    """[z, y] の列を SVG パスへ。y は上向きなので符号を反転する。"""
    out = " ".join(f"{'M' if i == 0 else 'L'}{z:.3f},{-y:.3f}"
                   for i, (z, y) in enumerate(pts))
    if close_with is not None:
        out += " " + " ".join(f"L{z:.3f},{-y:.3f}" for z, y in reversed(close_with)) + " Z"
    return out


def panel(sec: dict, label: str, width: float) -> tuple[str, float]:
    """1型ぶんの <g> と、その高さ（mm）を返す。"""
    c = sec["curves"]
    zb = c["bore_top"][0][0]
    ys = [y for k in ("outer_top", "outer_bot") for z, y in c[k] if z <= zb + 2]
    y_hi, y_lo = max(ys) + 1.0, min(ys) - 1.0
    parts = [f'<rect x="-1.5" y="{-y_hi:.2f}" width="{width:.2f}" '
             f'height="{y_hi - y_lo:.2f}" fill="{BG}"/>']
    f, s, w = STYLE["outer"]
    parts.append(f'<path d="{_d(c["outer_top"], c["outer_bot"])}" fill="{f}" '
                 f'stroke="{s}" stroke-width="{w}" vector-effect="non-scaling-stroke"/>')
    parts.append(f'<path d="{_d(c["roof"], c["floor"])}" fill="{BG}" stroke="none"/>')
    for key, dash in (("limit", ' stroke-dasharray="5 4"'), ("reed", ""),
                      ("roof", ""), ("floor", "")):
        name = {"limit": "shell_top", "reed": "reed"}.get(key, key)
        f, s, w = STYLE[key]
        parts.append(f'<path d="{_d(c[name])}" fill="none" stroke="{s}" '
                     f'stroke-width="{w}"{dash} vector-effect="non-scaling-stroke"/>')
    for h in sec["handles"]:
        if not h["active"]:
            continue
        a, b = h["span"]
        line = (f'<line x1="{a:.2f}" y1="{-h["y"]:.2f}" x2="{b:.2f}" y2="{-h["y"]:.2f}"'
                if h["axis"] == "z" else
                f'<line x1="{h["z"]:.2f}" y1="{-a:.2f}" x2="{h["z"]:.2f}" y2="{-b:.2f}"')
        parts.append(line + f' stroke="{STYLE["roof"][1]}" stroke-width="1" '
                            'stroke-dasharray="3 3" opacity="0.45" '
                            'vector-effect="non-scaling-stroke"/>')
        parts.append(f'<circle cx="{h["z"]:.2f}" cy="{-h["y"]:.2f}" r="0.75" '
                     f'fill="{HANDLE}" stroke="#10151c" stroke-width="1.5" '
                     'vector-effect="non-scaling-stroke"/>')
    chips = "  ".join(f'{h["label"]} {h["value"]:.2f}{h["unit"]}'
                      for h in sec["handles"] if h["active"])
    parts.append(f'<text x="0" y="{-y_hi + 1.9:.2f}" fill="{TEXT}" font-size="1.6" '
                 f'font-family="Meiryo, sans-serif">{label}</text>')
    parts.append(f'<text x="0" y="{-y_lo - 0.7:.2f}" fill="{MUTED}" font-size="1.25" '
                 f'font-family="Meiryo, sans-serif">{chips}</text>')
    return "".join(parts), y_hi - y_lo


def main() -> int:
    comp = get_registry().get("saxophone").make_component("mouthpiece", "tenor")
    base = {s.key: s.default for s in comp.param_specs()}
    cases = [("ステップ型（既定）", {}),
             ("ストレート型", {"baffle_type": "straight"}),
             ("カーブ型", {"baffle_type": "curve"}),
             ("ステップ型（段を立てて棚を後ろへ）",
              {"baffle_plateau": 0.60, "baffle_step_rise": 0.85})]
    width = 54.0
    body, y = [], 0.0
    for label, kw in cases:
        sec = comp.section(dict(base, **kw))
        g, h = panel(sec, label, width)
        body.append(f'<g transform="translate(0,{y + h / 2:.2f})">{g}</g>')
        y += h + 1.2
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" '
           f'height="{1100 * y / width:.0f}" viewBox="-1.5 0 {width} {y:.2f}">'
           f'<rect x="-1.5" y="0" width="{width}" height="{y:.2f}" fill="{BG}"/>'
           + "".join(body) + "</svg>")
    OUT.write_text(svg, encoding="utf-8")
    print(f"→ {OUT}  ({len(svg)} bytes, {len(cases)} 面)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
