"""仕様書に埋め込む断面図 SVG の生成（コンポーネント非依存）。

各コンポーネントが `spec_extras()` で返したポリライン群を、共通の描画関数で
SVG 化する。マウスピース／リード／リガチャーで同じ見た目・同じ縮尺規則になる。
"""
from __future__ import annotations

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
        return f'<p class="note">{caption}（描画データなし）</p>'
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


def mouthpiece_section(profile: dict) -> str:
    """マウスピース側面断面図（`profiles.side_profile_polylines` の出力）。"""
    ty = profile["table_y"]
    zs = [z for z, _ in profile["outer_top"]]
    return polyline_svg([
        {"pts": profile["outer_top"], "stroke": "#222", "width": 1.5},
        {"pts": profile["outer_bot"], "stroke": "#222", "width": 1.5},
        {"pts": profile["cavity_top"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
        {"pts": profile["cavity_bot"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
        {"pts": [(min(zs), ty), (max(zs) * 0.63, ty)], "stroke": "#cc3300",
         "width": 0.8, "dash": "2 2"},
    ], "側面断面図（実線=外形 / 青破線=内部空洞 / 赤破線=テーブル面） 単位:mm")


def reed_section(profile: dict) -> str:
    """リードの厚みプロファイル図（テーブル面 y=0 基準）。"""
    zv = profile["vamp_start"]
    top = max(y for _, y in profile["center"])
    return polyline_svg([
        {"pts": profile["center"], "stroke": "#222", "width": 1.5},
        {"pts": profile["edge"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
        {"pts": profile["table"], "stroke": "#cc3300", "width": 0.8, "dash": "2 2"},
        {"pts": [(zv, 0.0), (zv, top)], "stroke": "#888", "width": 0.8, "dash": "3 3"},
    ], "厚みプロファイル（実線=中央 / 青破線=側端 / 赤破線=テーブル面 / "
       "灰=ヴァンプ端） 単位:mm")


def ligature_section(section: dict) -> str:
    """リガチャーの帯断面図（XY 断面）。"""
    xs = [x for x, _ in section["outer"]]
    ty, ry = section["table_y"], section["reed_face_y"]
    return polyline_svg([
        {"pts": section["outer"], "stroke": "#222", "width": 1.5},
        {"pts": section["inner"], "stroke": "#0066cc", "width": 1.2, "dash": "5 3"},
        {"pts": [(min(xs), ty), (max(xs), ty)], "stroke": "#cc3300",
         "width": 0.8, "dash": "2 2"},
        {"pts": [(min(xs), ry), (max(xs), ry)], "stroke": "#3aa06a",
         "width": 0.8, "dash": "2 2"},
    ], "帯の断面（実線=外周 / 青破線=内周 / 赤破線=テーブル面 / "
       "緑破線=リード裏面） 単位:mm")


def sections_for(extras: dict) -> list[dict]:
    """`spec_extras()` の戻りから仕様書用の図セクションを組み立てる。

    コンポーネントは図の種類ごとに専用キーを返す（未知のキーは無視される）。
    """
    out: list[dict] = []
    if extras.get("profile"):
        out.append({"title": "断面図", "svg": mouthpiece_section(extras["profile"])})
    if extras.get("reed_profile"):
        out.append({"title": "厚みプロファイル",
                    "svg": reed_section(extras["reed_profile"])})
    if extras.get("ligature_section"):
        out.append({"title": "帯の断面",
                    "svg": ligature_section(extras["ligature_section"])})
    return out
