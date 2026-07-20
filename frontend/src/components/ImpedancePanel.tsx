import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Impedance } from "../api";

export default function ImpedancePanel({ paramsKey }: { paramsKey: string }) {
  const [imp, setImp] = useState<Impedance | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // パラメータが変わったら「再計算が必要」を示す
  useEffect(() => { if (imp) setStale(true); }, [paramsKey]); // eslint-disable-line

  const compute = useCallback(async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.impedance();
      setImp(r); setStale(false);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  // 曲線描画
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv || !imp) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
    const g = cv.getContext("2d")!;
    g.scale(dpr, dpr);
    const W = cv.clientWidth, H = cv.clientHeight;
    g.clearRect(0, 0, W, H);

    const f = imp.freqs, z = imp.z_db;
    const fmin = f[0], fmax = f[f.length - 1];
    const zmin = -60, zmax = 3;
    const px = (freq: number) => ((freq - fmin) / (fmax - fmin)) * (W - 8) + 4;
    const py = (db: number) =>
      H - 16 - ((Math.max(db, zmin) - zmin) / (zmax - zmin)) * (H - 24);

    // グリッド（周波数目盛）
    g.strokeStyle = "#2a3140"; g.fillStyle = "#8b96a6"; g.lineWidth = 1;
    g.font = "9px sans-serif";
    for (let fr = 0; fr <= fmax; fr += 250) {
      if (fr < fmin) continue;
      const x = px(fr);
      g.beginPath(); g.moveTo(x, 4); g.lineTo(x, H - 16); g.stroke();
      g.fillText(`${fr}`, x + 2, H - 4);
    }

    // ピーク縦線＋ラベル
    imp.peaks.forEach((pk, i) => {
      const x = px(pk.freq);
      g.strokeStyle = i === 0 ? "#7ec8a8" : "#3d5a7a";
      g.beginPath(); g.moveTo(x, 6); g.lineTo(x, H - 16); g.stroke();
      if (i < 4) {
        g.fillStyle = i === 0 ? "#7ec8a8" : "#8b96a6";
        g.fillText(pk.note.split(" ")[0], x + 2, 12 + i * 10);
      }
    });

    // Z(f) 曲線
    g.strokeStyle = "#4da3ff"; g.lineWidth = 1.6;
    g.beginPath();
    for (let i = 0; i < f.length; i++) {
      const x = px(f[i]), y = py(z[i]);
      i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
    }
    g.stroke();
  }, [imp]);

  return (
    <div className="simcard">
      <h3>インピーダンス（Tier3・共鳴解析）</h3>
      <div className="soundrow">
        <button className="primary" onClick={compute} disabled={busy}>
          {busy ? "計算中…" : imp ? "🔄 再計算" : "📈 インピーダンス計算"}
        </button>
        {imp && (
          <span className="engine-badge" style={{ fontSize: 11, color: "#8b96a6" }}>
            {imp.engine === "openwind" ? "OpenWind" : "簡易TMM"}
          </span>
        )}
      </div>

      {err && <div className="advice" style={{ color: "#e08a8a" }}>計算失敗: {err}</div>}
      {stale && imp && (
        <div className="advice" style={{ color: "#d9a441" }}>
          パラメータが変更されました。「再計算」で更新してください。
        </div>
      )}

      {imp && (
        <>
          <canvas ref={canvasRef} className="scope" style={{ height: 150 }} />
          <table>
            <tbody>
              <tr><td>第1共鳴</td><td className="num">{imp.first_note}</td></tr>
              <tr><td>目標（記譜最低音の実音）</td><td className="num">{imp.target_note}</td></tr>
              {imp.inharmonicity_cents != null && (
                <tr><td>倍音整列度（ずれRMS）</td>
                  <td className="num">{imp.inharmonicity_cents} cent</td></tr>
              )}
            </tbody>
          </table>
          <div className="peaklist" style={{ fontSize: 12, marginTop: 4 }}>
            {imp.peaks.slice(0, 6).map((pk, i) => (
              <span key={i} style={{ marginRight: 10, color: "#9fb0c4" }}>
                f{i + 1}: {pk.freq}Hz <b>{pk.note.split(" ")[0]}</b>
              </span>
            ))}
          </div>
          <div className="advice">{imp.note}</div>
        </>
      )}
    </div>
  );
}
