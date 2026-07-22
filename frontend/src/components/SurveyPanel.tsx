import { useState } from "react";
import { api, type ProjectData, type SimCard, type SurveyField, type SurveyState } from "../api";
import { Backdrop } from "./Dialogs";

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleString("ja-JP"); } catch { return iso; }
}

/** SimPanel と同じ .simcard スタイルで照合結果を出す */
function Card({ card }: { card: SimCard }) {
  return (
    <div className="simcard">
      <h3>{card.title}</h3>
      {card.big && <div className={`big ${card.status}`}>{card.big}</div>}
      <table>
        <tbody>
          {card.rows.map(([k, v]) => (
            <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>
          ))}
        </tbody>
      </table>
      {card.advice && <div className="advice">{card.advice}</div>}
    </div>
  );
}

/** 実測入力行。空欄なら送らない（＝計算値のまま）。placeholder に現在値を出す。 */
function FieldRows({ fields, prev, inputs, onInput }: {
  fields: SurveyField[];
  prev: Record<string, number>;
  inputs: Record<string, string>;
  onInput: (key: string, value: string) => void;
}) {
  return (
    <>
      {fields.map((f) => (
        <div className="drow" key={f.key} style={{ alignItems: "center", gap: 8 }}>
          <span style={{ flex: 1 }}>{f.label}</span>
          <input
            type="number"
            step={f.step ?? "any"}
            min={f.min ?? undefined}
            max={f.max ?? undefined}
            value={inputs[f.key] ?? ""}
            placeholder={f.current != null ? String(f.current) : ""}
            onChange={(e) => onInput(f.key, e.target.value)}
            style={{ width: 90, textAlign: "right" }}
          />
          <span style={{ width: 28, color: "var(--muted)", fontSize: 12 }}>{f.unit}</span>
          {prev[f.key] != null && (
            <span style={{ width: 60, color: "var(--accent2)", fontSize: 11 }}>
              採寸 {prev[f.key]}
            </span>
          )}
        </div>
      ))}
    </>
  );
}

export function SurveyDialog({ survey, onApplied, onClose }: {
  survey: SurveyState;
  onApplied: (p: ProjectData) => void;  // commit/revert/clear の反映後（プロジェクト全体）
  onClose: () => void;
}) {
  const [state, setState] = useState<SurveyState>(survey);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [sizeInputs, setSizeInputs] = useState<Record<string, string>>({});
  const [note, setNote] = useState(survey.note);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const setInput = (k: string, v: string) =>
    setInputs((p) => ({ ...p, [k]: v }));
  const setSizeInput = (k: string, v: string) =>
    setSizeInputs((p) => ({ ...p, [k]: v }));

  const collect = (raw: Record<string, string>): Record<string, number> => {
    const out: Record<string, number> = {};
    for (const [k, v] of Object.entries(raw)) {
      if (v.trim() === "") continue;
      const n = Number(v);
      if (Number.isFinite(n)) out[k] = n;
    }
    return out;
  };

  const commit = async () => {
    const measured = collect(inputs);
    const measured_size = collect(sizeInputs);
    if (Object.keys(measured).length === 0 && Object.keys(measured_size).length === 0) {
      setErr("実測値を1つ以上入力してください。"); return;
    }
    setBusy("採寸を反映中…"); setErr("");
    try {
      const p = await api.surveyCommit({ measured, measured_size, note });
      setState(p.survey);
      setInputs({}); setSizeInputs({});
      onApplied(p);
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  const revert = async () => {
    setBusy("採寸時点へ復元中…"); setErr("");
    try {
      const p = await api.surveyRevert();
      setState(p.survey); setInputs({}); setSizeInputs({});
      onApplied(p);
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  const clear = async () => {
    setBusy("採寸を破棄中…"); setErr("");
    try {
      const p = await api.surveyClear();
      setState(p.survey); setInputs({}); setSizeInputs({}); setNote("");
      onApplied(p);
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  const t = state.targets;

  return (
    <Backdrop onClose={onClose}>
      <h2>採寸（実物の実測をプロジェクトへ反映）</h2>
      <div className="note" style={{ lineHeight: 1.6 }}>
        手元の実物をノギスで測った値を入力すると、その項目だけ設計に反映されます
        （空欄は計算値のまま）。確定すると<b>復元点</b>が記録され、以後に設計を
        いじって破綻しても「採寸時点へ戻す」で戻せます。
      </div>

      {state.surveyed_at && (
        <div className="note" style={{ color: "var(--accent2)" }}>
          📐 採寸済み — {fmtDate(state.surveyed_at)}
          {state.note && <> / {state.note}</>}
        </div>
      )}

      {/* 系統A: 設計パラメータ */}
      <div className="simcard" style={{ margin: "8px 0" }}>
        <h3>設計寸法（実測 → 設計パラメータに反映）</h3>
        <FieldRows fields={t.params} prev={state.measured}
                   inputs={inputs} onInput={setInput} />
      </div>

      {/* 系統B: 音響基準定数 */}
      {t.size.length > 0 && (
        <div className="simcard" style={{ margin: "8px 0" }}>
          <h3>音響基準（実測 → ネック等の基準寸法に反映）</h3>
          <div className="note">
            公表値の無い基準寸法。実測するとこのプロジェクトの音程計算に効きます
            （descriptor は書き換えず、プロジェクト内だけの上書き）。
          </div>
          <FieldRows fields={t.size} prev={state.measured_size}
                     inputs={sizeInputs} onInput={setSizeInput} />
        </div>
      )}

      <div className="drow" style={{ margin: "8px 0", alignItems: "center", gap: 8 }}>
        <span>メモ</span>
        <input value={note} onChange={(e) => setNote(e.target.value)}
               placeholder="採寸の対象・条件など" style={{ flex: 1 }} />
      </div>

      {busy && <div className="busy" style={{ margin: "8px 0" }}>⏳ {busy}</div>}
      {err && <div style={{ color: "var(--err)" }}>{err}</div>}

      {state.card && <Card card={state.card} />}

      <div className="actions" style={{ marginTop: 8 }}>
        <button onClick={onClose}>閉じる</button>
        {state.has_checkpoint && (
          <button onClick={clear} disabled={!!busy}>採寸を破棄</button>
        )}
        {state.has_checkpoint && (
          <button onClick={revert} disabled={!!busy}>↩ 採寸時点へ戻す</button>
        )}
        <button className="primary" onClick={commit} disabled={!!busy}>
          📐 採寸を確定
        </button>
      </div>
    </Backdrop>
  );
}
