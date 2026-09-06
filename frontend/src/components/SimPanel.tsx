import type { SimCard, Simulation, Tier2 } from "../api";
import RadarChart from "./RadarChart";
import SoundPreview from "./SoundPreview";
import ImpedancePanel from "./ImpedancePanel";

const METRIC_ORDER = ["brightness", "power", "resistance", "flexibility", "edge"] as const;

/** いまのパラメータについての注意。**警告があるときだけ現れる**。
 *
 *  ここが唯一の常設の出口 —— 以前は断面タブ（`SectionEditor`）にしか出て
 *  おらず、3D タブでスライダを上げると「形が動かない・理由も出ない」だった。
 *  右パネルはどのタブを見ていても出ているので、出る場所がタブに依らなくなる。
 *
 *  **出来事の報告（壁で丸めた・旧プロジェクト変換・凍結後に触った）は
 *  ここに入れないこと。** あれは「いま起きた」話で、常設カードに貼ると
 *  いつの話か分からなくなる（`App.tsx` のトーストのまま）。 */
function WarningsCard({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="simcard warncard">
      <h3>⚠ 注意</h3>
      {items.map((w, i) => <div className="warnline" key={i}>{w}</div>)}
    </div>
  );
}

/** 汎用カード（リード/リガチャー）。マウスピースの .simcard スタイルを流用する */
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

export default function SimPanel({ sim, setCard, compare, paramsKey, onGoalSeek }: {
  sim: Simulation; setCard?: SimCard | null;
  compare?: Tier2 | null; paramsKey: string; onGoalSeek: () => void;
}) {
  // セットの適合は**どの部品を見ていても同じ**（3 部品が揃わないと決まらない量）
  // なので、部品ごとのカードより先に出す。
  const setCardEl = setCard ? <Card card={setCard} /> : null;
  if (sim.kind !== "mouthpiece") {
    // リード/リガチャー/ネック/管体: 汎用カード。リードのみ音プレビューを出す
    // （ゴールシークはマウスピース設計の機能なので出さない）。
    // インピーダンスは **サーバが has_impedance を立てた部品だけ** ——
    // どの部品が音響を持つかを UI 側に書くと、部品が増えるたびにここを直す
    // ことになる（断面タブを 404 で出し分けているのと同じ約束）。
    return (
      <div>
        <WarningsCard items={sim.warnings} />
        {setCardEl}
        {sim.cards.map((c) => <Card key={c.title} card={c} />)}
        {sim.has_impedance && <ImpedancePanel paramsKey={paramsKey} />}
        {sim.harmonics && <SoundPreview harmonics={sim.harmonics} />}
      </div>
    );
  }

  const t1 = sim.tier1;
  const sugg = sim.sensitivity?.suggestions ?? {};
  return (
    <div>
      {/* 警告はいちばん上。スクロールで通り過ぎられる位置に置かない。 */}
      <WarningsCard items={sim.warnings} />
      {setCardEl}
      <div className="simcard">
        {/* 主指標はセントではなく「合う挿し込み量」。コーク挿入深さは寸法ではなく
            演奏者が抜き差しするチューニングそのものなので、固定した状態のセントを
            前面に出すと寸法の誤差とチューニングの自由度が混ざる。
            容積の行は判定の理由として並べてある（両者は一対一で動かない）。 */}
        <h3>チューニング位置</h3>
        <div className={`big ${t1.status}`}>
          {t1.in_tune_mm === null ? "—" : `${t1.in_tune_mm.toFixed(1)} mm`}
          <span style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
            {t1.in_tune_mm === null ? "合う位置が無い" :
             t1.status === "ok" ? "実用域の内側" :
             t1.status === "tight" ? "端に寄っている" : "実用域の外"}
          </span>
        </div>
        {/* 基準条件での値であって「あなたが実際に挿す深さ」ではない。実際の位置は
            リード・リガチャー・気温・アンブシュアで動き、後ろ 2 つはモデルに無い。
            条件は advice の下の note に出ている。 */}
        <div className="hint">基準条件（25°C・目標音）で合う位置。実演奏の位置は
          リード・リガチャー・アンブシュアでも動く</div>
        <table>
          <tbody>
            <tr><td>実用域（挿し込み）</td>
                <td className="num">{t1.cork_range_mm[0]}〜{t1.cork_range_mm[1]} mm</td></tr>
            <tr><td>感度（1mm 押し込んだときの第1共鳴）</td>
                <td className="num">{t1.cents_per_mm > 0 ? "+" : ""}{t1.cents_per_mm} セント/mm</td></tr>
            <tr><td>現在 {t1.current_mm} mm でのズレ</td>
                <td className="num">{t1.deviation_cents > 0 ? "+" : ""}{t1.deviation_cents} セント</td></tr>
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

      {sim.cards?.map((c) => <Card key={c.title} card={c} />)}

      <ImpedancePanel paramsKey={paramsKey} />

      <SoundPreview harmonics={sim.harmonics} />
    </div>
  );
}
