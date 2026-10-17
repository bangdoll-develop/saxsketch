"""仕様書に埋め込む断面図 SVG の描画（コンポーネント非依存）。

各コンポーネントが `spec_extras()` の中でこの `polyline_svg()` を呼んで
`{"title", "svg"}` の図セクションを組み立てる。本モジュールは**どの部品の
どんな図か**を一切知らない（`registry.py` の「コアは楽器を知らない」方針）。
これにより部品を増やしても共通側の編集が要らない。
"""
from __future__ import annotations

from saxsketch import i18n

Polyline = list[tuple[float, float]]


def polyline_svg(groups: list[dict], caption: str, width_px: int = 760,
                 pad: float = 2.0, flip_y: bool = True) -> str:
    """ポリライン群を等尺で描画した SVG を返す。

    groups: [{"pts": [(x, y), …], "stroke": "#222", "width": 1.5,
              "dash": "5 3" | None}]
    座標の単位は mm。縦横は同一縮尺（歪めない）。`flip_y` は数学座標系
    （+Y が上）を SVG 座標系（+Y が下）へ反転する。
    """
    pts_all = [p for g in groups for p in g["pts"]]
    if not pts_all:
        return ('<p class="note">'
                + i18n.t("{caption}（描画データなし）", caption=caption)
                + '</p>')
    xs = [x for x, _ in pts_all]
    ys = [y for _, y in pts_all]
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    scale = (width_px - 40) / max(x1 - x0, 1e-6)
    h_px = int((y1 - y0) * scale) + 40

    def path(pts: Polyline) -> str:
        out = []
        for i, (x, y) in enumerate(pts):
            px = 20 + (x - x0) * scale
            py = (h_px - 20 - (y - y0) * scale) if flip_y else (20 + (y - y0) * scale)
            out.append(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}")
        return " ".join(out)

    body = "\n  ".join(
        f'<path d="{path(g["pts"])}" fill="none" stroke="{g.get("stroke", "#222")}"'
        f' stroke-width="{g.get("width", 1.5)}"'
        + (f' stroke-dasharray="{g["dash"]}"' if g.get("dash") else "")
        + "/>"
        for g in groups)
    return f"""<svg viewBox="0 0 {width_px} {h_px}" xmlns="http://www.w3.org/2000/svg"
     style="background:#fff;border:1px solid #ccc">
  {body}
  <text x="24" y="16" font-size="11" fill="#555">{caption}</text>
</svg>"""
