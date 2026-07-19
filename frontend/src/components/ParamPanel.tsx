import { useMemo, useState } from "react";
import type { ParamSpec, ReferenceInfo } from "../api";

interface Props {
  schema: ParamSpec[];
  params: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  /** hover/focus 中のパラメータを通知（3D影響部位ハイライト用）。null=解除 */
  onHover?: (key: string | null) => void;
  /** 影響領域が定義されているパラメータのキー集合 */
  regionKeys?: Set<string>;
  /** 参照コンポーネント（リード/リガチャーのみ。マウスピースでは null） */
  reference?: ReferenceInfo | null;
  /** 参照の差替え。ファイル選択ダイアログは呼び出し側が出す */
  onPickReference?: () => void;
  /** 参照をテンプレート既定値へ戻す */
  onResetReference?: () => void;
}

function ReferenceCard({ reference, onPick, onReset }: {
  reference: ReferenceInfo; onPick: () => void; onReset: () => void;
}) {
  return (
    <div className="cat refcard">
      <div className="cat-head"><span>参照マウスピース</span></div>
      <div className="param">
        <div className="row1">
          <label>{reference.label}</label>
        </div>
        <div className="effect" title={reference.source ?? ""}>
          {reference.source ?? "テンプレート既定値（取込元なし）"}
        </div>
        <table className="reftable">
          <tbody>
            {reference.dims.map(([k, v]) => (
              <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>
            ))}
          </tbody>
        </table>
        <div className="abrow">
          <button onClick={onReset} disabled={!reference.source}>既定に戻す</button>
          <button className="primary" onClick={onPick}>.wproj から取込</button>
        </div>
        <div className="effect">
          取込時点の寸法で固定されます。参照元を後から編集しても自動追従しません。
        </div>
      </div>
    </div>
  );
}

function NumberParam({ spec, value, onChange }: {
  spec: ParamSpec; value: number; onChange: (v: number) => void;
}) {
  return (
    <>
      <div className="row1">
        <label>{spec.label}</label>
        <span className="val">
          <input
            type="number" value={value}
            min={spec.min ?? undefined} max={spec.max ?? undefined}
            step={spec.step ?? undefined}
            onChange={(e) => onChange(Number(e.target.value))}
          />
          <span className="unit">{spec.unit}</span>
        </span>
      </div>
      {spec.min !== null && spec.max !== null && (
        <input
          type="range" value={value} min={spec.min} max={spec.max}
          step={spec.step ?? 0.01}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      )}
      {spec.effect && <div className="effect">{spec.effect}</div>}
    </>
  );
}

export default function ParamPanel({
  schema, params, onChange, onHover, regionKeys,
  reference, onPickReference, onResetReference,
}: Props) {
  const [openCats, setOpenCats] = useState<Record<string, boolean>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);

  const categories = useMemo(() => {
    const cats: { name: string; specs: ParamSpec[] }[] = [];
    for (const s of schema) {
      if (s.advanced && !showAdvanced) continue;
      let cat = cats.find((c) => c.name === s.category);
      if (!cat) { cat = { name: s.category, specs: [] }; cats.push(cat); }
      cat.specs.push(s);
    }
    return cats;
  }, [schema, showAdvanced]);

  return (
    <div onMouseLeave={() => onHover?.(null)}>
      {reference && (
        <ReferenceCard reference={reference}
                       onPick={() => onPickReference?.()}
                       onReset={() => onResetReference?.()} />
      )}
      {categories.map((cat) => {
        const open = openCats[cat.name] ?? true;
        return (
          <div className="cat" key={cat.name}>
            <div className="cat-head"
                 onClick={() => setOpenCats({ ...openCats, [cat.name]: !open })}>
              <span>{cat.name}</span><span>{open ? "▾" : "▸"}</span>
            </div>
            {open && cat.specs.map((spec) => {
              const v = params[spec.key];
              const hasRegion = regionKeys?.has(spec.key) ?? false;
              const hoverProps = {
                onMouseEnter: () => onHover?.(hasRegion ? spec.key : null),
                onFocus: () => onHover?.(hasRegion ? spec.key : null),
              };
              const cls = "param" + (hasRegion ? " has-region" : "");
              if (spec.type === "choice") {
                return (
                  <div className={cls} key={spec.key} title={spec.effect} {...hoverProps}>
                    <div className="row1">
                      <label>{spec.label}</label>
                      <select value={String(v)}
                              onChange={(e) => onChange(spec.key, e.target.value)}>
                        {spec.choices.map((c) => (
                          <option key={c.value} value={c.value}>{c.label}</option>
                        ))}
                      </select>
                    </div>
                    {spec.effect && <div className="effect">{spec.effect}</div>}
                  </div>
                );
              }
              return (
                <div className={cls} key={spec.key} title={spec.effect} {...hoverProps}>
                  <NumberParam spec={spec} value={Number(v)}
                               onChange={(nv) => onChange(spec.key, nv)} />
                </div>
              );
            })}
          </div>
        );
      })}
      <div className="adv-toggle" onClick={() => setShowAdvanced(!showAdvanced)}>
        {showAdvanced ? "▾ 詳細パラメータを隠す" : "▸ 詳細パラメータを表示"}
      </div>
    </div>
  );
}
