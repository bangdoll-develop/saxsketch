import { useState } from "react";
import {
  api, type ProjectData, type SimCard, type SurveyField, type SurveyMeasure,
  type SurveyState,
} from "../api";
import { getLang, t, useLang } from "../i18n";
import { Backdrop } from "./Dialogs";
import { usePathPicker } from "../pathPicker";

const CONF_LABEL: Record<string, string> = { high: "高", med: "中", low: "低" };

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString(getLang() === "ja" ? "ja-JP" : "en-GB");
  } catch { return iso; }
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
              {t("採寸")} {prev[f.key]}
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
  useLang();
  const [state, setState] = useState<SurveyState>(survey);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [sizeInputs, setSizeInputs] = useState<Record<string, string>>({});
  const [note, setNote] = useState(survey.note);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const pickPath = usePathPicker();
  const [measure, setMeasure] = useState<SurveyMeasure | null>(null);

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

  const measureFromModel = async () => {
    setErr("");
    const path = await pickPath("open_model", "");
    if (!path) return;
    setBusy(t("3Dモデルを測定中…（整列とレイキャスト。十数秒かかります）"));
    try {
      const m = await api.surveyMeasure(path);
      setMeasure(m);
      // 実測できた項目だけ入力欄へプレフィル。空欄項目は計算値のまま。
      const pre: Record<string, string> = {};
      for (const [k, v] of Object.entries(m.measured)) pre[k] = String(v);
      setInputs((p) => ({ ...p, ...pre }));
      const preS: Record<string, string> = {};
      for (const [k, v] of Object.entries(m.measured_size)) preS[k] = String(v);
      setSizeInputs((p) => ({ ...p, ...preS }));
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  const commit = async () => {
    const measured = collect(inputs);
    const measured_size = collect(sizeInputs);
    if (Object.keys(measured).length === 0 && Object.keys(measured_size).length === 0) {
      setErr(t("実測値を1つ以上入力してください。")); return;
    }
    setBusy(t("採寸を反映中…")); setErr("");
    try {
      const p = await api.surveyCommit({ measured, measured_size, note });
      setState(p.survey);
      setInputs({}); setSizeInputs({});
      onApplied(p);
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  const revert = async () => {
    setBusy(t("採寸時点へ復元中…")); setErr("");
    try {
      const p = await api.surveyRevert();
      setState(p.survey); setInputs({}); setSizeInputs({});
      onApplied(p);
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  const clear = async () => {
    setBusy(t("採寸を破棄中…")); setErr("");
    try {
      const p = await api.surveyClear();
      setState(p.survey); setInputs({}); setSizeInputs({}); setNote("");
      onApplied(p);
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  // `t` は訳の関数なので `tg`（名前を取り合わない）
  const tg = state.targets;

  return (
    <Backdrop onClose={onClose}>
      <h2>{t("採寸（実物の実測をプロジェクトへ反映）")}</h2>
      <div className="note" style={{ lineHeight: 1.6 }}>
        {t("手元の実物をノギスで測った値を入力すると、その項目だけ設計に反映されます（空欄は計算値のまま）。確定すると")}
        <b>{t("復元点")}</b>
        {t("が記録され、以後に設計をいじって破綻しても「採寸時点へ戻す」で戻せます。")}
      </div>

      {/* 外部3Dモデルからの採寸プレフィル */}
      <div className="simcard" style={{ margin: "8px 0" }}>
        <div className="drow" style={{ alignItems: "center", justifyContent: "space-between" }}>
          <span>{t("実物の 3mf / STL / STEP から外形寸法を自動測定して埋める")}</span>
          <button onClick={measureFromModel} disabled={!!busy}>{t("📥 3mf/STLから測定…")}</button>
        </div>
        {measure && (
          <div className="note" style={{ marginTop: 6, lineHeight: 1.6 }}>
            {t("測定できた項目（信頼度）:")}{" "}
            {Object.keys(measure.measured).length + Object.keys(measure.measured_size).length === 0
              ? t("なし")
              : [...Object.entries(measure.measured), ...Object.entries(measure.measured_size)]
                  .map(([k, v]) => t("{key} {val}（{conf}）", { key: k, val: String(v),
                      conf: t(CONF_LABEL[measure.confidence[k]] ?? "?") }))
                  .join(" / ")}
            <br />
            {t("水密:")} {measure.quality.watertight ? "OK" : "NG"}
            {measure.quality.volume_cc != null && t(" / 体積 {cc} cc", { cc: measure.quality.volume_cc.toFixed(1) })}
            {measure.notes.map((n, i) => (
              <div key={i} style={{ color: "var(--warn)" }}>・{n}</div>
            ))}
            {t("測定値は下の入力欄に入りました。確認・修正して「採寸を確定」してください。")}
          </div>
        )}
      </div>

      {state.surveyed_at && (
        <div className="note" style={{ color: "var(--accent2)" }}>
          {t("📐 採寸済み — ")}{fmtDate(state.surveyed_at)}
          {state.note && <> / {state.note}</>}
        </div>
      )}

      {/* 系統A: 設計パラメータ */}
      <div className="simcard" style={{ margin: "8px 0" }}>
        <h3>{t("設計寸法（実測 → 設計パラメータに反映）")}</h3>
        <FieldRows fields={tg.params} prev={state.measured}
                   inputs={inputs} onInput={setInput} />
      </div>

      {/* 系統B: 音響基準定数 */}
      {tg.size.length > 0 && (
        <div className="simcard" style={{ margin: "8px 0" }}>
          <h3>{t("音響基準（実測 → ネック等の基準寸法に反映）")}</h3>
          <div className="note">
            {t("公表値の無い基準寸法。実測するとこのプロジェクトの音程計算に効きます（descriptor は書き換えず、プロジェクト内だけの上書き）。")}
          </div>
          <FieldRows fields={tg.size} prev={state.measured_size}
                     inputs={sizeInputs} onInput={setSizeInput} />
        </div>
      )}

      <div className="drow" style={{ margin: "8px 0", alignItems: "center", gap: 8 }}>
        <span>{t("メモ")}</span>
        <input value={note} onChange={(e) => setNote(e.target.value)}
               placeholder={t("採寸の対象・条件など")} style={{ flex: 1 }} />
      </div>

      {busy && <div className="busy" style={{ margin: "8px 0" }}>⏳ {busy}</div>}
      {err && <div style={{ color: "var(--err)" }}>{err}</div>}

      {state.card && <Card card={state.card} />}

      <div className="actions" style={{ marginTop: 8 }}>
        <button onClick={onClose}>{t("閉じる")}</button>
        {state.has_checkpoint && (
          <button onClick={clear} disabled={!!busy}>{t("採寸を破棄")}</button>
        )}
        {state.has_checkpoint && (
          <button onClick={revert} disabled={!!busy}>{t("↩ 採寸時点へ戻す")}</button>
        )}
        <button className="primary" onClick={commit} disabled={!!busy}>
          {t("📐 採寸を確定")}
        </button>
      </div>
    </Backdrop>
  );
}
