import type { SetInfo } from "../api";

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
 *  `SetInfo.members` をそのまま描くだけ。 */
export default function SetPanel({
  info, onSelect, onAdd, onRemove, onImport, onExport,
}: Props) {
  return (
    <div className="cat setpanel">
      <div className="cat-head">
        <span>{info.is_set ? info.label : "部品構成"}</span>
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
              {!m.required && !m.master && (
                <span className="setmember-x" title="セットから外す"
                      onClick={(e) => { e.stopPropagation(); onRemove(m.component_id); }}>
                  ×
                </span>
              )}
            </button>
          ) : (
            <button key={m.component_id} className="setmember add"
                    onClick={() => onAdd(m.component_id)}
                    title={`${m.label}をこのセットに追加する`}>
              ＋ {m.label}
            </button>
          )
        ))}
      </div>
      <div className="abrow">
        <button onClick={onImport}>.wproj から取込</button>
        <button onClick={onExport} disabled={!info.is_set}>この部品を書出</button>
      </div>
      <div className="effect">
        {info.is_set
          ? "セットの中では設計中の値がそのまま下流の部品へ渡ります（取込み直しは要りません）。★ が土台の部品です。"
          : "部品を足すとセットになります。足した部品は、いま設計している値にそのまま追従します。"}
      </div>
    </div>
  );
}
