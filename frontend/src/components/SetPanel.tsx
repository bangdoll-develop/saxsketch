import type { SetInfo } from "../api";
import { t, useLang } from "../i18n";

interface Props {
  info: SetInfo;
  /** 編集対象の部品を切り替える */
  onSelect: (componentId: string) => void;
  /** テンプレート既定値で部品を足す */
  onAdd: (componentId: string) => void;
  /** 部品をセットから外す */
  onRemove: (componentId: string) => void;
  /** 既存の単体 .wproj をメンバーとして取り込む */
  onImport: () => void;
  /** いま見ている部品を単体 .wproj として書き出す */
  onExport: () => void;
}

/** セットの部品タブ。**どの部品が組になるかはサーバが宣言する**（descriptor の
 *  `sets`）ので、ここには楽器固有の知識を置かない —— 並びも必須/任意も
 *  `SetInfo.members` をそのまま描くだけ。
 *
 *  × は**土台（master）以外の全部**に出す。`required` で隠すと、リガチャーを外す
 *  経路がどこにも無くなる —— `required` は「新規セットで最初から作る」の意味で、
 *  外せるかどうかはサーバが従属関係で決める（外せなければ理由が返る）。 */
export default function SetPanel({
  info, onSelect, onAdd, onRemove, onImport, onExport,
}: Props) {
  useLang();
  return (
    <div className="cat setpanel">
      <div className="cat-head">
        <span>{info.is_set ? info.label : t("部品構成")}</span>
      </div>
      <div className="setmembers">
        {info.members.map((m) => (
          m.present ? (
            <button key={m.component_id}
                    className={"setmember" + (m.component_id === info.active ? " active" : "")}
                    onClick={() => onSelect(m.component_id)}
                    title={m.name ?? m.label}>
              <span className="setmember-label">
                {m.master ? "★ " : ""}{m.label}
              </span>
              {!m.master && (
                <span className="setmember-x" title={t("セットから外す")}
                      onClick={(e) => { e.stopPropagation(); onRemove(m.component_id); }}>
                  ×
                </span>
              )}
            </button>
          ) : (
            <button key={m.component_id} className="setmember add"
                    onClick={() => onAdd(m.component_id)}
                    title={t("{part}をこのセットに追加する", { part: m.label })}>
              ＋ {m.label}
            </button>
          )
        ))}
      </div>
      <div className="abrow">
        <button onClick={onImport}>{t(".wproj から取込")}</button>
        <button onClick={onExport} disabled={!info.is_set}>{t("この部品を書出")}</button>
      </div>
      <div className="effect">
        {info.is_set
          ? t("セットの中では設計中の値がそのまま下流の部品へ渡ります（取込み直しは要りません）。★ が土台の部品です。")
          : t("部品を足すとセットになります。足した部品は、いま設計している値にそのまま追従します。")}
      </div>
    </div>
  );
}
