# -*- coding: utf-8 -*-
"""表示言語。**日本語が原本で、英語は訳。**

## 2 つの引き方があるのは、原本の置き場所が違うから

1. **パラメータの `label` / `effect` / `source`** —— 日本語は
   `components/*.py` の定義のすぐ横にある。壁と帯の根拠を書いた長い散文と
   ひと続きなので、**動かさない**。英語だけ `en.PARAMS` から引く。
2. **それ以外の画面・書き出しの文** —— `t("日本語")` で包む。
   **msgid が日本語そのもの**（gettext と同じ）。鍵を発明しないので、
   コードを読んだときに何が出るか分かるし、訳が無ければ日本語のまま出る。

**訳が無いときは黙って日本語を返す。** 落とすのはテスト
（`tests/test_i18n.py`）の仕事で、実行時に画面を壊す理由は無い。

## 言語の決まり方

リクエストごとに `set_lang()`（`server/app.py` のミドルウェアが `?lang=` か
`X-Lang` から読む）。既定は日本語。`ContextVar` なので**並行リクエストで
混ざらない**し、書き出し（仕様書・部品表・入稿 ZIP）も同じリクエストの中で
走るので、UI で選んだ言語がそのまま出る。

ブラウザの `Accept-Language` は**見ない**。書き出しは「画面で見ていた言語」に
従うべきで、ブラウザの申告とは別物だから（画面で英語に切り替えた日本語話者が
日本語の仕様書を受け取ると説明が付かない）。
"""
from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterable, Iterator

from . import en as _en

#: 原本の言語。訳が無いときはここへ落ちる。
DEFAULT_LANG = "ja"
SUPPORTED = ("ja", "en")

_lang: ContextVar[str] = ContextVar("saxsketch_lang", default=DEFAULT_LANG)


def normalize(lang: str | None) -> str:
    """`ja-JP` / `EN` / 未知 を `ja` / `en` に丸める。未知は既定へ。"""
    if not lang:
        return DEFAULT_LANG
    head = str(lang).strip().lower().replace("_", "-").split("-")[0]
    return head if head in SUPPORTED else DEFAULT_LANG


def get_lang() -> str:
    return _lang.get()


def set_lang(lang: str | None) -> str:
    norm = normalize(lang)
    _lang.set(norm)
    return norm


@contextmanager
def use(lang: str | None) -> Iterator[str]:
    """一時的に言語を変える（テストと書き出しの単体呼び出し用）。"""
    token = _lang.set(normalize(lang))
    try:
        yield _lang.get()
    finally:
        _lang.reset(token)


# ---------------------------------------------------------------- 一般の文

def t(message: str, /, **kw: Any) -> str:
    """画面・書き出しに出る文。**引数の日本語がそのまま msgid**。

    `{}` の差し込みはここでやる（`.format`）。**訳の側も同じ名前の `{}` を
    持たなければならない** —— `tests/test_i18n.py` が突き合わせる。
    """
    if _lang.get() == "ja":
        out = message
    else:
        out = _en.MESSAGES.get(message, message)
    return out.format(**kw) if kw else out


# ---------------------------------------------------------------- 部品と壁

def component_label(component_id: str, ja: str) -> str:
    if _lang.get() == "ja":
        return ja
    return _en.COMPONENTS.get(component_id, ja)


def choice_label(value: str, ja: str) -> str:
    """選択肢の表示名。材料プリセットのように `ParamSpec` の外で引く表もある。"""
    if _lang.get() == "ja":
        return ja
    return _en.CHOICES.get(value, ja)


def limit_kind_label(kind: str, ja: str) -> str:
    if _lang.get() == "ja":
        return ja
    return _en.LIMIT_KINDS.get(kind, ja)


# ---------------------------------------------------------------- パラメータ

def _param_entry(component_id: str, key: str) -> dict[str, str]:
    return _en.PARAMS.get(component_id, {}).get(key, {})


def localize_specs(component_id: str, specs: Iterable[Any]) -> list[Any]:
    """`ParamSpec` を訳した**複製**で返す。原本は触らない。

    複製にするのは、`param_specs()` が毎回作り直すとは限らないから
    （クラス属性やキャッシュに載っていると、訳した値が次のリクエストへ漏れる）。
    """
    specs = list(specs)
    if _lang.get() == "ja":
        return specs
    out = []
    for s in specs:
        e = _param_entry(component_id, s.key)
        changes: dict[str, Any] = {}
        if e.get("label"):
            changes["label"] = e["label"]
        if e.get("effect") and getattr(s, "effect", ""):
            changes["effect"] = e["effect"]
        if e.get("source") and getattr(s, "source", ""):
            changes["source"] = e["source"]
        cat = _en.CATEGORIES.get(getattr(s, "category", ""))
        if cat:
            changes["category"] = cat
        unit = _en.UNITS.get(getattr(s, "unit", ""))
        if unit:
            changes["unit"] = unit
        choices = getattr(s, "choices", None)
        if choices:
            changes["choices"] = [
                dataclasses.replace(c, label=_en.CHOICES.get(c.value, c.label))
                for c in choices
            ]
        out.append(dataclasses.replace(s, **changes) if changes else s)
    return out


def localize_spec_dicts(component_id: str, dicts: Iterable[dict]) -> list[dict]:
    """`ParamSet.schema_dicts()` の出力を訳す（ブラウザへ出る形）。"""
    dicts = list(dicts)
    if _lang.get() == "ja":
        return dicts
    out = []
    for d in dicts:
        d = dict(d)
        e = _param_entry(component_id, d.get("key", ""))
        if e.get("label"):
            d["label"] = e["label"]
        if e.get("effect") and d.get("effect"):
            d["effect"] = e["effect"]
        if e.get("source") and d.get("source"):
            d["source"] = e["source"]
        cat = _en.CATEGORIES.get(d.get("category", ""))
        if cat:
            d["category"] = cat
        unit = _en.UNITS.get(d.get("unit", ""))
        if unit:
            d["unit"] = unit
        if d.get("choices"):
            d["choices"] = [
                {**c, "label": _en.CHOICES.get(c.get("value", ""), c.get("label", ""))}
                for c in d["choices"]
            ]
        out.append(d)
    return out
