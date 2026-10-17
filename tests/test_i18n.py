# -*- coding: utf-8 -*-
"""表示言語の網。**訳の抜けは実行時に黙る**ので、ここで落とす。

`i18n.t()` も `localize_specs()` も、訳が無ければ日本語をそのまま返す。
画面を壊さないためにはそれが正しいが、そのぶん**抜けても誰も気付かない**。
だからここが唯一の検出器になる。

部品を import する網は OCCT を引くので、Windows の Smart App Control 環境では
動かない（`test_saxsketch.py` と同じ）。import を関数の中に置いてあるのは、
**AST を読むだけの網（`t()` の msgid 検査）を OCCT 無しでも走らせる**ため。
"""
from __future__ import annotations

import ast
import re
import string
from pathlib import Path

import pytest

from saxsketch import i18n
from saxsketch.i18n import en

_PKG = Path(__file__).resolve().parent.parent / "saxsketch"
_JP = re.compile("[぀-ヿ一-鿿]")


def _components():
    from saxsketch.instruments.saxophone.components import COMPONENTS
    return COMPONENTS


def _specs_of(cid: str):
    """`param_specs()` はインスタンスメソッドなので、器を 1 つ作って呼ぶ。

    テンプレートは alto 固定。**どのサイズでもスキーマの顔ぶれは同じ**で、
    違うのは既定値と帯だけなので、訳の網としては 1 サイズで足りる。
    """
    from saxsketch.core.registry import get_registry
    inst = get_registry().get("saxophone")
    return inst.make_component(cid, "alto").param_specs()


# ------------------------------------------------------------ 言語の決まり方

@pytest.mark.parametrize("given,want", [
    ("ja", "ja"), ("en", "en"), ("EN", "en"), ("ja-JP", "ja"), ("en-US", "en"),
    ("fr", "ja"), ("", "ja"), (None, "ja"), ("en_GB", "en"),
])
def test_normalize_falls_back_to_the_original_language(given, want):
    """**未知の言語は日本語へ落とす。** 原本が日本語だから。

    英語へ落とすと、訳の無い文が混ざったときに「英語のページに日本語が出る」
    のではなく「日本語しか無い文が英語のページに出る」ことになり、
    どちらの言語としても読めない画面ができる。
    """
    assert i18n.normalize(given) == want


def test_use_restores_the_previous_language():
    """`use()` を抜けたら元に戻る。**書き出しだけ英語**のような使い方をする。"""
    assert i18n.get_lang() == "ja"
    with i18n.use("en"):
        assert i18n.get_lang() == "en"
        with i18n.use("ja"):
            assert i18n.get_lang() == "ja"
        assert i18n.get_lang() == "en"
    assert i18n.get_lang() == "ja"


# ------------------------------------------------------------ パラメータの訳

def test_every_parameter_has_an_english_label():
    """**98 本すべてに英語のラベルがある。**

    1 本でも欠けるとそこだけ日本語で出る。画面は壊れないが、英語の利用者から
    見ると「訳し忘れ」ではなく「読めない項目」になる。
    """
    missing = []
    for cid in _components():
        for s in _specs_of(cid):
            if not en.PARAMS.get(cid, {}).get(s.key, {}).get("label"):
                missing.append(f"{cid}.{s.key}")
    assert missing == [], "英語ラベルが無い: " + ", ".join(missing)


def test_effect_and_source_are_translated_exactly_where_japanese_has_them():
    """`effect` と `source` は**日本語側と過不足なく**一致する。

    足りなければ訳し忘れ。余っていれば、日本語を消したのに訳が残っている
    （＝画面に出ない文を保守し続けることになる）。**出所を発明しない**という
    約束も、ここで守られる —— 日本語に出所が無いなら英語にも無い。
    """
    bad = []
    for cid in _components():
        for s in _specs_of(cid):
            t = en.PARAMS.get(cid, {}).get(s.key, {})
            for field in ("effect", "source"):
                ja = bool(getattr(s, field, ""))
                has = bool(t.get(field))
                if ja and not has:
                    bad.append(f"{cid}.{s.key}: {field} の訳が無い")
                if has and not ja:
                    bad.append(f"{cid}.{s.key}: {field} は日本語に無いのに訳がある")
    assert bad == [], "\n  ".join([""] + bad)


def test_every_category_and_choice_has_a_translation():
    missing = []
    for cid in _components():
        for s in _specs_of(cid):
            if s.category and s.category not in en.CATEGORIES:
                missing.append(f"category {s.category!r}（{cid}.{s.key}）")
            for c in getattr(s, "choices", []) or []:
                if c.value not in en.CHOICES:
                    missing.append(f"choice {c.value!r}（{cid}.{s.key}）")
    assert sorted(set(missing)) == [], "訳が無い: " + ", ".join(sorted(set(missing)))


def test_english_specs_carry_no_japanese():
    """英語で引いたスキーマに日本語が 1 文字も残らない。

    上の 3 本は「表に載っているか」を見るだけなので、**引く側の配線が
    間違っていても緑になる**。ここは実際に `localize_spec_dicts()` を通す。
    """
    leftovers = []
    for cid in _components():
        dicts = [s.to_dict() for s in _specs_of(cid)]
        with i18n.use("en"):
            for d in i18n.localize_spec_dicts(cid, dicts):
                for field in ("label", "category", "effect", "source"):
                    if _JP.search(str(d.get(field) or "")):
                        leftovers.append(f"{cid}.{d['key']}.{field}: {d[field]}")
                for c in d.get("choices") or []:
                    if _JP.search(str(c.get("label") or "")):
                        leftovers.append(f"{cid}.{d['key']}.choice:{c['value']}")
    assert leftovers == [], "英語に日本語が残っている:\n  " + "\n  ".join(leftovers)


def test_japanese_output_is_byte_for_byte_what_it_was():
    """**日本語のときは何も変わらない。**

    i18n を入れたせいで既定の画面が変わったら、それは退行であって国際化では
    ない。`localize_*` は ja では同じ物をそのまま返す。
    """
    for cid in _components():
        specs = _specs_of(cid)
        dicts = [s.to_dict() for s in specs]
        with i18n.use("ja"):
            assert i18n.localize_spec_dicts(cid, dicts) == dicts
            assert i18n.localize_specs(cid, specs) == specs


def test_localizing_does_not_mutate_the_original_specs():
    """訳は**複製**に書く。原本を書き換えると次のリクエストへ漏れる。"""
    specs = _specs_of("mouthpiece")
    before = [(s.key, s.label, s.category) for s in specs]
    with i18n.use("en"):
        out = i18n.localize_specs("mouthpiece", specs)
        assert out[0].label != specs[0].label
    assert [(s.key, s.label, s.category) for s in specs] == before


# ------------------------------------------------------------ 一般の文（msgid）

def _t_msgids() -> list[tuple[str, str]]:
    """`i18n.t("...")` の第 1 引数が文字列リテラルのものを全部拾う。

    変数を渡している呼び方は拾えない。**だから拾えない呼び方をしない** ——
    msgid が実行時にしか決まらないと、この網がその行だけ見えなくなる。
    """
    found = []
    for path in sorted(_PKG.rglob("*.py")):
        if path.parts[-2:] == ("i18n", "en.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name != "t" or not node.args:
                continue
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                found.append((str(path.relative_to(_PKG)), a.value))
    return found


def test_every_message_in_the_code_has_an_english_translation():
    missing = sorted({f"{f}: {m}" for f, m in _t_msgids() if m not in en.MESSAGES})
    assert missing == [], "訳が無い文:\n  " + "\n  ".join(missing)


def test_placeholders_match_between_japanese_and_english():
    """`{}` の名前が両言語で一致する。ずれると `format` が実行時に落ちる。

    画面に出る文が `KeyError` で落ちるのは、訳が無いより悪い。
    """
    def names(s: str) -> set[str]:
        return {f for _, f, _, _ in string.Formatter().parse(s) if f}

    bad = []
    for ja, en_text in en.MESSAGES.items():
        if names(ja) != names(en_text):
            bad.append(f"{ja!r}: {sorted(names(ja))} vs {sorted(names(en_text))}")
    assert bad == [], "差し込みがずれている:\n  " + "\n  ".join(bad)


def test_no_translation_is_left_in_japanese():
    """訳の側に日本語が残っていない（コピペのし忘れ）。"""
    bad = [k for k, v in en.MESSAGES.items() if _JP.search(v)]
    assert bad == [], "訳が日本語のまま: " + ", ".join(repr(b) for b in bad)


# ------------------------------------------------------------ フロント側

_FRONT = _PKG.parent / "frontend" / "src"

#: `t("...")` の呼び出し。**識別子の末尾が t の関数**（`fillText` /
#: `getContext` / `startsWith`）に当たらないよう、直前を見る。
_T_CALL = re.compile(r'(?<![A-Za-z0-9_$.])t\(\s*"((?:[^"\\]|\\.)*)"')

#: `t(変数)` で引くもの。msgid がソースに literal で出ないので、ここに書く。
#: **書き忘れたらこの網は黙る** —— だから `CONF_LABEL` のような表を新設したら
#: ここへ足す。表そのものを増やさないのが一番安い。
_INDIRECT = (
    # ParamPanel.KIND_LABEL
    "幾何の成立条件", "製造の制約", "慣習の推奨帯", "未分類の壁",
    # SurveyPanel / ManualEdit の CONF_LABEL
    "高", "中", "低", "?",
    # サーバが返す判定語（ManualEdit.VERDICT_COLOR の鍵でもある）
    "一致", "変化なし", "軽微", "乖離", "変化あり", "測定不能", "判定不可",
    # pathPicker.LABELS
    "保存先を指定", "保存先のパス", "拡張子 .wproj は省略できます。",
    "プロジェクトを開く", "プロジェクトファイルのパス",
    "サーバから見えるパスを入力してください。",
    "モデルファイルを指定", "モデルファイルのパス",
    "stl / step / stp / 3mf / obj / ply が読めます。",
    "出力先フォルダを指定", "フォルダのパス",
    "存在しないフォルダは書き出し時に作成されます。",
    # SoundPreview の NOTES / EMBOUCHURES
    "ラ (A3) 220Hz", "ド (C4) 262Hz", "ミ (E4) 330Hz", "ラ (A4) 440Hz",
    "アンブシュア 緩め", "アンブシュア 標準", "アンブシュア 締め",
)


def _frontend_msgids() -> set[str]:
    found = set(_INDIRECT)
    for path in sorted(_FRONT.rglob("*.ts*")):
        if path.name.startswith("i18n"):
            continue
        found |= set(_T_CALL.findall(path.read_text(encoding="utf-8")))
    return found


def _frontend_translations() -> dict[str, str]:
    """`i18n.en.ts` の鍵と値。**TypeScript を実行せずに読む。**

    値は `"..." + "..."` で折り返してあることがあるので、連結して 1 本に戻す。
    """
    src = (_FRONT / "i18n.en.ts").read_text(encoding="utf-8")
    body = src[src.index("{"):src.rindex("}")]
    out: dict[str, str] = {}
    entry = re.compile(
        r'"((?:[^"\\]|\\.)*)"\s*:\s*((?:"(?:[^"\\]|\\.)*"\s*\+?\s*)+),', re.S)
    for m in entry.finditer(body):
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(2))
        out[m.group(1)] = "".join(parts)
    return out


def test_the_frontend_has_english_for_every_message():
    """画面の `t()` に訳がある。**サーバ側と同じ網をフロントにも掛ける。**

    フロントは Python のテストから見えないので放っておくと検出器が片肺になる。
    TypeScript を実行せずに読んでいるのは、そのためだけに node を呼びたくないから
    （CI の lint ジョブは別に走っている）。
    """
    have = _frontend_translations()
    missing = sorted(m for m in _frontend_msgids() if m not in have)
    assert missing == [], "訳が無い（frontend/src/i18n.en.ts）:\n  " + "\n  ".join(missing)


def test_the_frontend_table_has_no_dead_entries():
    """使われていない訳が残っていない（日本語を変えたのに訳を直し忘れた跡）。"""
    used = _frontend_msgids()
    dead = sorted(k for k in _frontend_translations() if k not in used)
    assert dead == [], "どこからも引かれていない訳:\n  " + "\n  ".join(dead)


def test_the_frontend_placeholders_match():
    bad = []
    for ja, en_text in _frontend_translations().items():
        a = set(re.findall(r"\{(\w+)\}", ja))
        b = set(re.findall(r"\{(\w+)\}", en_text))
        if a != b:
            bad.append(f"{ja!r}: {sorted(a)} vs {sorted(b)}")
    assert bad == [], "差し込みがずれている:\n  " + "\n  ".join(bad)


def test_the_print_recommendations_are_translated():
    """印刷の推奨条件は**表を引いて `t()` に渡す**ので、AST では拾えない。

    msgid が literal で出ない呼び方はこの網の盲点になる。だから表そのものを
    読んで突き合わせる —— 手で並べた一覧と違って、表に 1 行足した日に
    自動で検出側も増える。
    """
    from saxsketch.export.spec import PRINT_RECOMMENDATIONS
    missing = []
    for key, d in PRINT_RECOMMENDATIONS.items():
        if d["label"] not in en.MESSAGES:
            missing.append(f"{key}.label: {d['label']}")
        for item in d["items"]:
            if item not in en.MESSAGES:
                missing.append(f"{key}: {item[:40]}")
    assert missing == [], "訳が無い:\n  " + "\n  ".join(missing)
