import { useMemo, useState } from "react";
import type { ParamSpec } from "../api";

interface Props {
  schema: ParamSpec[];
  params: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  /** hover/focus 中のパラメータを通知（3D影響部位ハイライト用）。null=解除 */
  onHover?: (key: string | null) => void;
  /** 影響領域が定義されているパラメータのキー集合 */
  regionKeys?: Set<string>;
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

export default function ParamPanel({ schema, params, onChange, onHover, regionKeys }: Props) {
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
