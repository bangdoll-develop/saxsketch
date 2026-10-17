"""仕様書 HTML 生成（印刷して PDF 化できる自己完結 HTML）。"""
from __future__ import annotations

from datetime import date
from html import escape as _escape


def _e(value) -> str:
    """HTML へ埋める前に逃がす。

    **プロジェクト名と部品名は利用者が打った文字列**であり、`.wproj` を
    他人から受け取れば他人の文字列でもある。この仕様書は既定ブラウザで開き、
    入稿パッケージの ZIP にも入るので、素通しにすると台本をそのまま同梱する
    ことになる。差し込み口は全部ここを通す —— 1 か所でも素のままにすると、
    そこだけが穴になる。

    逃がさないのは**こちらが組み立てた HTML 片**だけ（断面の SVG、組み上げた
    表の行、節そのもの）。
    """
    return _escape("" if value is None else str(value), quote=True)

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
            f"<tr><th>{_e(t2['labels'][k])}</th><td>{t2[k]:.1f} / 10</td></tr>\n"
            for k in ["brightness", "power", "resistance", "flexibility", "edge"]
            if k in t2)
        return f"""<h2>4. 音響予測（設計時シミュレーション）</h2>
<table>
<tr><th>内容積（実効）</th><td>{_e(t1.get('effective_cc', '-'))} cc（目標 {_e(t1.get('target_cc', '-'))} cc）</td></tr>
<tr><th>音程傾向</th><td>{_e(t1.get('deviation_cents', '-'))} セント（{_e(t1.get('advice', ''))}）</td></tr>
{tone_rows}
</table>
<p class="note">※ 指標は文献傾向に基づく推定値。絶対値ではなく設計比較の目安。</p>"""

    blocks = ""
    for card in sim.get("cards", []):
        rows = "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>\n"
                       for k, v in card["rows"])
        big = f"<p><b>{_e(card['big'])}</b></p>\n" if card.get("big") else ""
        blocks += (f"<h3>{_e(card['title'])}</h3>\n{big}<table>{rows}</table>\n"
                   f"<p class=\"note\">{_e(card.get('advice', ''))}</p>\n")
    if not blocks:
        return ""
    return f"<h2>4. 設計時シミュレーション</h2>\n{blocks}"


_STYLE = """
 body { font-family: "Yu Gothic UI", "Meiryo", sans-serif; margin: 32px; color: #222; }
 h1 { font-size: 22px; border-bottom: 3px solid #0066cc; padding-bottom: 6px; }
 h1.part { margin-top: 42px; border-bottom-color: #7fa8d8; }
 h2 { font-size: 16px; border-left: 5px solid #0066cc; padding-left: 8px; margin-top: 28px; }
 table { border-collapse: collapse; width: 100%; font-size: 13px; }
 th, td { border: 1px solid #bbb; padding: 5px 9px; text-align: left; }
 th { background: #eef4fb; white-space: nowrap; }
 .meta td { border: none; padding: 2px 12px 2px 0; color: #555; }
 .note { color: #777; font-size: 12px; }
 @media print { body { margin: 12mm; } }
"""

_DATA_SECTION = """<h2>7. 入稿データ</h2>
<ul>
 <li>STL: 汎用（全サービス対応）。単位 mm</li>
 <li>STEP: 精密加工・寸法検証用（ロスレス）</li>
 <li>3MF: 単位・メタ情報付き（対応サービス向け）</li>
</ul>"""


def _page(title: str, meta: str, body: str) -> str:
    """自己完結 HTML の外枠。**単体もセットも同じ枠**（体裁が 2 つに割れない）。"""
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<title>仕様書 - {_e(title)}</title>
<style>{_STYLE}</style></head><body>
<h1>製作仕様書　{_e(title)}</h1>
{meta}
{body}
</body></html>"""


def _member_body(component_label: str, params: dict, specs: list, dimensions: list,
                 bom_rows: list[dict], sim: dict, sections: list[dict],
                 material: str, heading: str = "") -> str:
    """部品 1 つぶんの本文（見出し 1〜6）。

    **単体の仕様書もセットの仕様書もここを通る。** 体裁を 2 か所に書くと、
    片方だけ直った仕様書が出る。
    """
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
        param_rows += (f"<tr><td>{_e(s.category)}</td><td>{_e(s.label)}</td>"
                       f"<td>{_e(disp)}</td></tr>\n")

    dim_rows = "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>\n"
                       for k, v in dimensions)
    bom_body = "".join(
        f"<tr><td>{_e(r['type'])}</td><td>{_e(r['name'])}</td><td>{_e(r['qty'])}</td>"
        f"<td>{_e(r['material'])}</td><td>{_e(r['note'])}</td></tr>\n" for r in bom_rows)
    rec_items = "".join(f"<li>{_e(i)}</li>\n" for i in rec["items"])
    # `svg` は**こちらが組んだ HTML 片**なのでそのまま。題だけ逃がす。
    section_html = "\n".join(f"<h3>{_e(s['title'])}</h3>\n{s['svg']}" for s in sections) \
        or '<p class="note">この部品には断面図がありません。</p>'
    title = f'<h1 class="part">{_e(heading)}</h1>\n' if heading else ""

    return f"""{title}<h2>1. 主要寸法</h2>
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

<h2>6. 3Dプリント推奨条件 — {_e(rec['label'])}（{_e(component_label)}）</h2>
<ul>{rec_items}</ul>
<p class="note">※ <b>口に入れる部品です。</b>材料の食品接触適合性と、印刷後の洗浄・二次硬化を
必ず確認してください。未硬化のレジンは皮膚感作性があります。PLA は約 55℃ で変形するため
熱湯洗浄は不可。使用前に毎回、割れ・欠け・鋭い縁を点検してください。</p>
<p class="note">※ この仕様書の寸法と音響指標は SaxSketch による推定であり、
<b>できあがる物の安全性・耐久性・適合性を保証するものではありません。</b>
製作と使用は利用者の責任で行ってください。</p>
"""


def spec_html(project_name: str, instrument_label: str, component_label: str,
              template_label: str, params: dict, specs: list, dimensions: list,
              bom_rows: list[dict], sim: dict, sections: list[dict],
              material: str) -> str:
    """部品 1 つの仕様書（従来どおり）。"""
    meta = f"""<table class="meta"><tr>
 <td>楽器: {_e(instrument_label)}</td><td>コンポーネント: {_e(component_label)}</td>
 <td>テンプレート: {_e(template_label)}</td><td>発行日: {date.today().isoformat()}</td>
 <td>作成: SaxSketch</td></tr></table>"""
    body = _member_body(component_label, params, specs, dimensions, bom_rows,
                        sim, sections, material) + "\n" + _DATA_SECTION
    return _page(project_name, meta, body)


def _card_table(card: dict) -> str:
    rows = "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>\n"
                   for k, v in card["rows"])
    big = f"<p><b>{_e(card['big'])}</b></p>\n" if card.get("big") else ""
    return (f"<h3>{_e(card['title'])}</h3>\n{big}<table>{rows}</table>\n"
            f'<p class="note">{_e(card.get("advice", ""))}</p>')


def spec_html_set(set_name: str, instrument_label: str, template_label: str,
                  members: list[dict], set_card: dict | None) -> str:
    """セット 1 式ぶんの仕様書。部品ごとの本文を 1 枚に並べる。

    Args:
        members: `_member_body` の引数一式に `label`（部品の種類名）・`name`
                 （プロジェクト上の名前）・`dir`（出力先サブフォルダ）を足した dict の列。
        set_card: 部品どうしの適合カード（`set_check.set_card`）。無ければ省く。
    """
    parts = "、".join(_e(m["label"]) for m in members)
    meta = f"""<table class="meta"><tr>
 <td>楽器: {_e(instrument_label)}</td><td>構成: {parts}</td>
 <td>テンプレート: {_e(template_label)}</td><td>発行日: {date.today().isoformat()}</td>
 <td>作成: SaxSketch</td></tr></table>"""

    listing = "".join(f"<tr><th>{_e(m['label'])}</th><td>{_e(m['name'])}</td>"
                      f"<td>{_e(m['dir'])}/model.*</td></tr>" for m in members)
    body = f"<h2>0. 同梱の構成</h2>\n<table>{listing}</table>\n"
    if set_card:
        body += f"<h2>0-2. セットの適合（部品どうし）</h2>\n{_card_table(set_card)}\n"
    for m in members:
        body += _member_body(
            m["label"], m["params"], m["specs"], m["dimensions"], m["bom_rows"],
            m["sim"], m["sections"], m["material"],
            heading=f"{m['label']} — {m['name']}") + "\n"
    body += _DATA_SECTION + (
        '\n<p class="note">部品ごとに '
        + "、".join(f"{_e(m['dir'])}/" for m in members)
        + " のフォルダへ分かれています。</p>")
    return _page(set_name, meta, body)
