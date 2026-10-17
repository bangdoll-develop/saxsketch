// 表示言語。**日本語が原本で、英語は訳。**
//
// サーバ側（`saxsketch/i18n/`）と同じ約束で動く:
//
//   - **msgid は日本語そのもの**（gettext と同じ）。鍵を発明しないので、
//     コードを読めば何が出るか分かるし、訳が無ければ日本語のまま出る。
//   - 訳の抜けは**テストで落とす**（`tests/test_i18n.py` がサーバ側を、
//     `npm run lint` の型が差し込みのずれを拾う）。実行時に画面を壊さない。
//
// **i18next は入れない。** 要るのは「辞書を引く」だけで、複数形も日付書式も
// 相対時刻も使っていない。依存とバンドルを増やす理由が無い。
import { useSyncExternalStore } from "react";
import EN from "./i18n.en";

export type Lang = "ja" | "en";

const KEY = "saxsketch.lang";

/** ブラウザの言語から決める。**`ja` 以外は英語**（原本が読めない人のほうが多い）。 */
function detect(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "ja" || saved === "en") return saved;
  } catch { /* プライベートウィンドウなど。既定へ落ちればよい */ }
  const nav = (navigator.languages?.[0] ?? navigator.language ?? "").toLowerCase();
  return nav.startsWith("ja") ? "ja" : "en";
}

let current: Lang = detect();
const listeners = new Set<() => void>();

export function getLang(): Lang { return current; }

export function setLang(next: Lang): void {
  if (next === current) return;
  current = next;
  try { localStorage.setItem(KEY, next); } catch { /* 保存できなくても動く */ }
  listeners.forEach((f) => f());
}

/** 言語を変えたら描き直す。**`t()` を呼ぶコンポーネントは必ず呼ぶ** ——
 *  呼ばないとそのコンポーネントだけ前の言語のまま残る。 */
export function useLang(): Lang {
  return useSyncExternalStore(subscribe, getLang, getLang);
}

/** `useSyncExternalStore` 用。 */
export function subscribe(f: () => void): () => void {
  listeners.add(f);
  return () => { listeners.delete(f); };
}

/**
 * 画面に出す文。**引数の日本語が msgid**。
 *
 * 差し込みは `{name}` で、第 2 引数に値を渡す。訳の側も同じ名前を持つこと。
 */
export function t(ja: string, vars?: Record<string, string | number>): string {
  const s = current === "ja" ? ja : (EN[ja] ?? ja);
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}
