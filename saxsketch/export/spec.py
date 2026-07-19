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
    "resin_flex": {
        "label": "フレキシブルレジン（光造形）",
        "items": [
            "積層ピッチ 0.03〜0.05mm。薄い先端部を造形するため最小ピッチを推奨",
            "造形向き: リードを寝かせず立て、テーブル面をサポートから逃がす",
            "二次硬化を過剰にかけると硬化して柔軟性が失われる。時間管理を厳密に",
            "口に触れる部品のため、食品接触適合（歯科用等）レジンを選定すること",
        ],
    },
    "pp": {
        "label": "ポリプロピレン（FDM・上級者向け）",
        "items": [
            "反りが強く定着が難しい。PP専用ビルドシート必須",
            "積層ピッチ 0.10mm、庫内温度を保てる密閉プリンタを推奨",
            "耐薬品性・耐疲労性が高く、繰り返し曲がるリードに向く",
        ],
    },
    "cane": {
        "label": "ケーン（切削・参考）",
        "items": [
            "3Dプリントではなく切削・成形が前提。出力データは形状の参照用",
            "モデルの寸法はリードメイキングマシンの型出しに使用できる",
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


def _acoustics_section(sim: dict) -> str:
    """音響予測セクション。マウスピースは Tier1/2 の表、他は汎用カードの表。"""
    t1 = sim.get("tier1")
    t2 = sim.get("tier2", {})
    if t1:
        tone_rows = "".join(
            f"<tr><th>{t2['labels'][k]}</th><td>{t2[k]:.1f} / 10</td></tr>\n"
            for k in ["brightness", "power", "resistance", "flexibility", "edge"]
            if k in t2)
        return f"""<h2>4. 音響予測（設計時シミュレーション）</h2>
<table>
<tr><th>内容積（実効）</th><td>{t1.get('effective_cc', '-')} cc（目標 {t1.get('target_cc', '-')} cc）</td></tr>
<tr><th>音程傾向</th><td>{t1.get('deviation_cents', '-')} セント（{t1.get('advice', '')}）</td></tr>
{tone_rows}
</table>
<p class="note">※ 指標は文献傾向に基づく推定値。絶対値ではなく設計比較の目安。</p>"""

    blocks = ""
    for card in sim.get("cards", []):
        rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>\n" for k, v in card["rows"])
        big = f"<p><b>{card['big']}</b></p>\n" if card.get("big") else ""
        blocks += (f"<h3>{card['title']}</h3>\n{big}<table>{rows}</table>\n"
                   f"<p class=\"note\">{card.get('advice', '')}</p>\n")
    if not blocks:
        return ""
    return f"<h2>4. 設計時シミュレーション</h2>\n{blocks}"


def spec_html(project_name: str, instrument_label: str, component_label: str,
              template_label: str, params: dict, specs: list, dimensions: list,
              bom_rows: list[dict], sim: dict, sections: list[dict],
              material: str) -> str:
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
    section_html = "\n".join(f"<h3>{s['title']}</h3>\n{s['svg']}" for s in sections) \
        or '<p class="note">この部品には断面図がありません。</p>'

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
{section_html}

<h2>3. 設計パラメータ全値</h2>
<table><tr><th>カテゴリ</th><th>パラメータ</th><th>値</th></tr>
{param_rows}</table>

{_acoustics_section(sim)}

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
