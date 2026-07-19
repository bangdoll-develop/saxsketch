"""仕様書 HTML 生成（印刷して PDF 化できる自己完結 HTML）。"""
from __future__ import annotations

from datetime import date

PRINT_RECOMMENDATIONS = {
    "resin": {
        "label": "レジン（光造形 SLA/DLP）",
        "items": [
            "積層ピッチ 0.05mm、造形向き: シャンク端を下、テーブル面をサポートから逃がす",
            "洗浄: IPA 2槽洗浄後、UV二次硬化を十分に（未硬化レジンの残留は不可）",
            "口に触れる部品のため、食品接触適合（BPAフリー/歯科用等）レジンを推奨",
            "テーブル面を#600→#1000で軽く平面出しするとリードの密着が向上",
        ],
    },
    "pla": {
        "label": "PLA（FDM）",
        "items": [
            "積層ピッチ 0.08〜0.12mm、ノズル 0.4mm、壁4周以上・充填率100%",
            "造形向き: ビークを上、テーブル面を横向きにしてサポート痕を避ける",
            "気密性向上のため薄く食品用シーラント/エポキシでのコーティング推奨",
            "耐熱が低い（〜55℃）。車内放置・熱湯洗浄は変形の原因",
        ],
    },
    "petg": {
        "label": "PETG（FDM）",
        "items": [
            "積層ピッチ 0.08〜0.12mm、壁4周以上・充填率100%",
            "PLAより耐熱・耐久性が高く実用向き。ただし糸引きに注意",
            "食品接触グレードのフィラメントを選定、印刷後の洗浄を徹底",
        ],
    },
    "nylon_sls": {
        "label": "ナイロン PA12（SLS・外注推奨）",
        "items": [
            "オンライン印刷サービス（JLC3DP/PCBWay/Shapeways等）でSLS/MJF指定",
            "サポート不要で内部形状の再現性が最も高い。表面はやや多孔質",
            "染色（黒）+ 表面シーリングを併用すると吸湿・衛生面で有利",
        ],
    },
}


def _svg_section(profile: dict, width_px: int = 760) -> str:
    """side_profile_polylines の出力から断面 SVG を組み立てる。"""
    pts_all = (profile["outer_top"] + profile["outer_bot"]
               + profile["cavity_top"] + profile["cavity_bot"])
    zs = [z for z, _ in pts_all]
    ys = [y for _, y in pts_all]
    z0, z1 = min(zs), max(zs)
    y0, y1 = min(ys) - 2, max(ys) + 2
    scale = (width_px - 40) / (z1 - z0)
    h_px = int((y1 - y0) * scale) + 40

    def path(pts):
        d = " ".join(f"{'M' if i == 0 else 'L'}{20 + (z - z0) * scale:.1f},"
                     f"{h_px - 20 - (y - y0) * scale:.1f}" for i, (z, y) in enumerate(pts))
        return d

    ty = profile["table_y"]
    table_line = path([(z0, ty), (z1 * 0.63, ty)])
    return f"""<svg viewBox="0 0 {width_px} {h_px}" xmlns="http://www.w3.org/2000/svg"
     style="background:#fff;border:1px solid #ccc">
  <path d="{path(profile['outer_top'])}" fill="none" stroke="#222" stroke-width="1.5"/>
  <path d="{path(profile['outer_bot'])}" fill="none" stroke="#222" stroke-width="1.5"/>
  <path d="{path(profile['cavity_top'])}" fill="none" stroke="#0066cc" stroke-width="1.2" stroke-dasharray="5 3"/>
  <path d="{path(profile['cavity_bot'])}" fill="none" stroke="#0066cc" stroke-width="1.2" stroke-dasharray="5 3"/>
  <path d="{table_line}" fill="none" stroke="#cc3300" stroke-width="0.8" stroke-dasharray="2 2"/>
  <text x="24" y="16" font-size="11" fill="#555">側面断面図（実線=外形 / 青破線=内部空洞 / 赤破線=テーブル面） 単位:mm</text>
</svg>"""


def spec_html(project_name: str, instrument_label: str, component_label: str,
              template_label: str, params: dict, specs: list, dimensions: list,
              bom_rows: list[dict], sim: dict, profile: dict, material: str) -> str:
    rec = PRINT_RECOMMENDATIONS.get(material, PRINT_RECOMMENDATIONS["resin"])

    spec_map = {s.key: s for s in specs}
    param_rows = ""
    for key, value in params.items():
        s = spec_map.get(key)
        if s is None:
            continue
        if s.type == "choice":
            label_map = {c.value: c.label for c in s.choices}
            disp = label_map.get(value, str(value))
        elif s.type == "float":
            disp = f"{value:.2f} {s.unit}".strip()
        else:
            disp = f"{value} {s.unit}".strip()
        param_rows += f"<tr><td>{s.category}</td><td>{s.label}</td><td>{disp}</td></tr>\n"

    dim_rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>\n" for k, v in dimensions)
    bom_body = "".join(
        f"<tr><td>{r['type']}</td><td>{r['name']}</td><td>{r['qty']}</td>"
        f"<td>{r['material']}</td><td>{r['note']}</td></tr>\n" for r in bom_rows)
    rec_items = "".join(f"<li>{i}</li>\n" for i in rec["items"])

    t1 = sim.get("tier1", {})
    t2 = sim.get("tier2", {})
    tone_rows = "".join(
        f"<tr><th>{t2['labels'][k]}</th><td>{t2[k]:.1f} / 10</td></tr>\n"
        for k in ["brightness", "power", "resistance", "flexibility", "edge"]
        if k in t2)

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<title>仕様書 - {project_name}</title>
<style>
 body {{ font-family: "Yu Gothic UI", "Meiryo", sans-serif; margin: 32px; color: #222; }}
 h1 {{ font-size: 22px; border-bottom: 3px solid #0066cc; padding-bottom: 6px; }}
 h2 {{ font-size: 16px; border-left: 5px solid #0066cc; padding-left: 8px; margin-top: 28px; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
 th, td {{ border: 1px solid #bbb; padding: 5px 9px; text-align: left; }}
 th {{ background: #eef4fb; white-space: nowrap; }}
 .meta td {{ border: none; padding: 2px 12px 2px 0; color: #555; }}
 .note {{ color: #777; font-size: 12px; }}
 @media print {{ body {{ margin: 12mm; }} }}
</style></head><body>
<h1>製作仕様書　{project_name}</h1>
<table class="meta"><tr>
 <td>楽器: {instrument_label}</td><td>コンポーネント: {component_label}</td>
 <td>テンプレート: {template_label}</td><td>発行日: {date.today().isoformat()}</td>
 <td>作成: SaxSketch</td></tr></table>

<h2>1. 主要寸法</h2>
<table>{dim_rows}</table>

<h2>2. 断面図</h2>
{_svg_section(profile)}

<h2>3. 設計パラメータ全値</h2>
<table><tr><th>カテゴリ</th><th>パラメータ</th><th>値</th></tr>
{param_rows}</table>

<h2>4. 音響予測（設計時シミュレーション）</h2>
<table>
<tr><th>内容積（実効）</th><td>{t1.get('effective_cc', '-')} cc（目標 {t1.get('target_cc', '-')} cc）</td></tr>
<tr><th>音程傾向</th><td>{t1.get('deviation_cents', '-')} セント（{t1.get('advice', '')}）</td></tr>
{tone_rows}
</table>
<p class="note">※ 指標は文献傾向に基づく推定値。絶対値ではなく設計比較の目安。</p>

<h2>5. 部品表（BOM）</h2>
<table><tr><th>区分</th><th>品名</th><th>数量</th><th>材料</th><th>備考</th></tr>
{bom_body}</table>

<h2>6. 3Dプリント推奨条件 — {rec['label']}</h2>
<ul>{rec_items}</ul>
<p class="note">※ 口に触れる部品です。材料の食品接触適合性・洗浄を必ず確認してください。</p>

<h2>7. 入稿データ</h2>
<ul>
 <li>STL: 汎用（全サービス対応）。単位 mm</li>
 <li>STEP: 精密加工・寸法検証用（ロスレス）</li>
 <li>3MF: 単位・メタ情報付き（対応サービス向け）</li>
</ul>
</body></html>"""
