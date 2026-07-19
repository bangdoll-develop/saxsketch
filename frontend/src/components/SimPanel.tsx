import type { Simulation, Tier2 } from "../api";
import RadarChart from "./RadarChart";
import SoundPreview from "./SoundPreview";
import ImpedancePanel from "./ImpedancePanel";

const METRIC_ORDER = ["brightness", "power", "resistance", "flexibility", "edge"] as const;

export default function SimPanel({ sim, compare, paramsKey, onGoalSeek }: {
  sim: Simulation; compare?: Tier2 | null; paramsKey: string; onGoalSeek: () => void;
}) {
  const t1 = sim.tier1;
  const sugg = sim.sensitivity?.suggestions ?? {};
  return (
    <div>
      <div className="simcard">
        <h3>音程チェック（内容積 vs 欠損円錐）</h3>
        <div className={`big ${t1.status}`}>
          {t1.deviation_cents > 0 ? "+" : ""}{t1.deviation_cents} セント
          <span style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
            {t1.status === "ok" ? "良好" : t1.status === "sharp" ? "高め傾向" : "低め傾向"}
          </span>
        </div>
        <table>
          <tbody>
            <tr><td>実効内容積</td><td className="num">{t1.effective_cc} cc</td></tr>
            <tr><td>目標（欠損円錐）</td><td className="num">{t1.target_cc} cc</td></tr>
          </tbody>
        </table>
        <div className="advice">{t1.advice}</div>
      </div>

      <div className="simcard">
        <h3>音色レーダー</h3>
        <RadarChart tier2={sim.tier2} compare={compare} />
        <div className="sugg">
          {METRIC_ORDER.map((m) => {
            const s = sugg[m];
            if (!s) return null;
            return (
              <div key={m}>
                {sim.tier2.labels[m]}を上げるなら → <b>{s.label} {s.direction}{s.step}{s.unit}</b>
                （効果 {s.per_step}/step）
              </div>
            );
          })}
        </div>
        <div style={{ marginTop: 10 }}>
          <button className="primary" onClick={onGoalSeek}>🎯 目標から逆算（ゴールシーク）</button>
        </div>
        <div className="advice">{sim.tier2.note}</div>
      </div>

      <ImpedancePanel paramsKey={paramsKey} />

      <SoundPreview harmonics={sim.harmonics} />
    </div>
  );
}
