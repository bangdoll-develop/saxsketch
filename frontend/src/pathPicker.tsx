/** パス選択の入口を 1 本にする。
 *
 *  OS のファイルダイアログは **サーバの画面** に出る。サーバと利用者が同じ机に
 *  居るとき（いまのローカル運用・WSL 運用）は本物のダイアログを出し、そうでない
 *  ときは出しても誰にも見えないので、この場で入力してもらう。
 *
 *  以前は 7 箇所すべてが `api.dialog()` を直接呼び、返りが null なら
 *  `if (!path) return;` で黙って何もしていなかった。ダイアログを出せない環境では
 *  ボタンが完全に無反応になり、README が約束していた「パスを手入力すれば動作する」
 *  も実装されていなかった。
 */
import {
  createContext, useCallback, useContext, useEffect, useRef, useState,
} from "react";
import { api, type Capabilities, type DialogMode } from "./api";

export type PickPath = (mode: DialogMode, suggested?: string) => Promise<string | null>;

const PathPickerCtx = createContext<PickPath>(async () => null);
const CapabilitiesCtx = createContext<Capabilities | null>(null);

/** パスを 1 つ選ばせる。キャンセルまたは未入力なら null。 */
export const usePathPicker = (): PickPath => useContext(PathPickerCtx);
/** 稼働環境の申告。取得前・取得失敗時は null。 */
export const useCapabilities = (): Capabilities | null => useContext(CapabilitiesCtx);

const LABELS: Record<DialogMode, { title: string; label: string; hint: string }> = {
  save: { title: "保存先を指定", label: "保存先のパス",
          hint: "拡張子 .wproj は省略できます。" },
  open: { title: "プロジェクトを開く", label: "プロジェクトファイルのパス",
          hint: "サーバから見えるパスを入力してください。" },
  open_model: { title: "モデルファイルを指定", label: "モデルファイルのパス",
                hint: "stl / step / stp / 3mf / obj / ply が読めます。" },
  dir: { title: "出力先フォルダを指定", label: "フォルダのパス",
         hint: "存在しないフォルダは書き出し時に作成されます。" },
};

type Pending = {
  mode: DialogMode; suggested: string; resolve: (v: string | null) => void;
};

export function PathPickerProvider({ children }: { children: React.ReactNode }) {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  // 取得中に押されても待てるよう、state とは別に約束そのものを持つ。
  // 初期表示の「新規 / 開く」は起動直後に開くので、ここが未取得だと
  // ネイティブダイアログを出せる環境でも一度目だけ手入力に落ちてしまう。
  const capsOnce = useRef<Promise<Capabilities | null> | null>(null);

  const loadCaps = useCallback(() => {
    capsOnce.current ??= api.capabilities()
      .then((c) => { setCaps(c); return c; })
      .catch(() => null);
    return capsOnce.current;
  }, []);

  useEffect(() => { void loadCaps(); }, [loadCaps]);

  const pick = useCallback<PickPath>(async (mode, suggested = "") => {
    const ready = caps ?? await loadCaps();
    if (ready?.native_dialogs) {
      try {
        const r = await api.dialog(mode, suggested);
        if (r.reason === "ok") return r.path;
        // 閉じたのは利用者。代わりの入力欄を出すと「閉じたのに出てくる」になる。
        if (r.reason === "cancelled") return null;
      } catch { /* 通信失敗。下の手入力へ落とす */ }
    }
    return new Promise<string | null>((resolve) => {
      setPending({ mode, suggested, resolve });
    });
  }, [caps, loadCaps]);

  const finish = (value: string | null) => {
    pending?.resolve(value);
    setPending(null);
  };

  return (
    <CapabilitiesCtx.Provider value={caps}>
      <PathPickerCtx.Provider value={pick}>
        {children}
        {pending && (
          <PathPrompt mode={pending.mode} suggested={pending.suggested}
                      remote={!caps?.native_dialogs} onDone={finish} />
        )}
      </PathPickerCtx.Provider>
    </CapabilitiesCtx.Provider>
  );
}

function PathPrompt({ mode, suggested, remote, onDone }: {
  mode: DialogMode; suggested: string; remote: boolean;
  onDone: (v: string | null) => void;
}) {
  const [value, setValue] = useState(suggested);
  const t = LABELS[mode];
  const submit = () => onDone(value.trim() ? value.trim() : null);

  // Dialogs.tsx の Backdrop と同じ見た目。あちらを import すると
  // Dialogs → pathPicker → Dialogs の循環になるので、ここは自前で持つ。
  return (
    <div className="dialog-backdrop"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onDone(null); }}>
     <div className="dialog">
      <h2>{t.title}</h2>
      <div className="note">
        {remote
          ? "この環境ではOSのファイルダイアログを使えません（サーバが手元の画面を"
            + "持っていない構成です）。サーバから見えるパスを直接入力してください。"
          : "ファイルダイアログを開けませんでした。パスを直接入力してください。"}
      </div>
      <div className="drow">
        <label>{t.label}</label>
        {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
        <input type="text" style={{ flex: 1 }} value={value} autoFocus
               onChange={(e) => setValue(e.target.value)}
               onKeyDown={(e) => {
                 if (e.key === "Enter") submit();
                 if (e.key === "Escape") onDone(null);
               }} />
      </div>
      <div className="note">{t.hint}</div>
      <div className="actions">
        <button onClick={() => onDone(null)}>キャンセル</button>
        <button className="primary" onClick={submit} disabled={!value.trim()}>決定</button>
      </div>
     </div>
    </div>
  );
}
