import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Harmonics } from "../api";

const NOTES = [
  { label: "ラ (A3) 220Hz", freq: 220 },
  { label: "ド (C4) 262Hz", freq: 261.63 },
  { label: "ミ (E4) 330Hz", freq: 329.63 },
  { label: "ラ (A4) 440Hz", freq: 440 },
];

// 物理モデルは音高を指定できない（トーンホール無しの固定ボアは自前の共鳴しか
// 鳴らない）。レジスタを決めるのはリード共振＝アンブシュアの締め具合なので、
// それを選ばせ、実際に立った共鳴はサーバの実測値を表示する。
// 高さは変わらない（鳴るのはこの管の第1共鳴で、3 つとも同じ）。変わるのは
// 立ち上がりと倍音の重み。以前は「低い/高いレジスタ」と書いていたが、それは
// 共鳴管が非調和になっていたときの挙動で、`_coarsen` を直したら消えた。
const EMBOUCHURES = [
  { label: "アンブシュア 緩め", key: "loose" },
  { label: "アンブシュア 標準", key: "normal" },
  { label: "アンブシュア 締め", key: "tight" },
];

interface Snapshot { name: string; harmonics: Harmonics }

interface Engine {
  ctx: AudioContext; master: GainNode;
  oscs: OscillatorNode[]; gains: GainNode[];
  noiseGain: GainNode; stop: () => void;
}

function buildEngine(h: Harmonics, freq: number): Engine {
  const ctx = new AudioContext();
  const master = ctx.createGain();
  master.gain.value = 0;
  master.connect(ctx.destination);

  const norm = h.amplitudes.reduce((a, b) => a + b, 0) || 1;
  const oscs: OscillatorNode[] = [];
  const gains: GainNode[] = [];
  h.amplitudes.forEach((amp, i) => {
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = freq * (i + 1);
    const g = ctx.createGain();
    g.gain.value = (amp / norm) * 0.85;
    osc.connect(g); g.connect(master);
    osc.start();
    oscs.push(osc); gains.push(g);
  });

  // ビブラート（各倍音の detune を LFO で揺らす）
  const lfo = ctx.createOscillator();
  lfo.frequency.value = h.vibrato_hz;
  const lfoGain = ctx.createGain();
  lfoGain.gain.value = h.vibrato_depth * 1200; // セント換算
  lfo.connect(lfoGain);
  oscs.forEach((o) => lfoGain.connect(o.detune));
  lfo.start();

  // 息成分（ホワイトノイズ → バンドパス）
  const len = ctx.sampleRate * 2;
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  const noise = ctx.createBufferSource();
  noise.buffer = buf; noise.loop = true;
  const bp = ctx.createBiquadFilter();
  bp.type = "bandpass"; bp.frequency.value = freq * 4; bp.Q.value = 0.8;
  const noiseGain = ctx.createGain();
  noiseGain.gain.value = h.breathiness * 0.5;
  noise.connect(bp); bp.connect(noiseGain); noiseGain.connect(master);
  noise.start();

  master.gain.linearRampToValueAtTime(0.55, ctx.currentTime + Math.max(h.attack_sec, 0.02));

  const stop = () => {
    master.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.08);
    setTimeout(() => ctx.close(), 150);
  };
  return { ctx, master, oscs, gains, noiseGain, stop };
}

function updateEngine(e: Engine, h: Harmonics) {
  const norm = h.amplitudes.reduce((a, b) => a + b, 0) || 1;
  h.amplitudes.forEach((amp, i) => {
    if (e.gains[i]) {
      e.gains[i].gain.linearRampToValueAtTime(
        (amp / norm) * 0.85, e.ctx.currentTime + 0.06);
    }
  });
  e.noiseGain.gain.linearRampToValueAtTime(
    h.breathiness * 0.5, e.ctx.currentTime + 0.06);
}

interface PhysHandle { ctx: AudioContext; src: AudioBufferSourceNode }

export default function SoundPreview({ harmonics }: { harmonics: Harmonics }) {
  const [playing, setPlaying] = useState(false);
  const [freq, setFreq] = useState(261.63);
  const [snapA, setSnapA] = useState<Snapshot | null>(null);
  const [snapB, setSnapB] = useState<Snapshot | null>(null);
  const [active, setActive] = useState<"live" | "A" | "B">("live");
  const [mode, setMode] = useState<"impression" | "physical">("impression");
  const [physNote, setPhysNote] = useState<string | null>(null);
  const [physBusy, setPhysBusy] = useState(false);
  const [embouchure, setEmbouchure] = useState("normal");
  const [played, setPlayed] = useState<string | null>(null);
  const engineRef = useRef<Engine | null>(null);
  const physRef = useRef<PhysHandle | null>(null);
  const waveRef = useRef<HTMLCanvasElement>(null);
  const specRef = useRef<HTMLCanvasElement>(null);

  const current: Harmonics =
    active === "A" && snapA ? snapA.harmonics :
    active === "B" && snapB ? snapB.harmonics : harmonics;

  const stopPhysical = useCallback(() => {
    try { physRef.current?.src.stop(); } catch { /* noop */ }
    physRef.current?.ctx.close().catch(() => { /* noop */ });
    physRef.current = null;
  }, []);

  const stop = useCallback(() => {
    engineRef.current?.stop();
    engineRef.current = null;
    stopPhysical();
    setPlaying(false);
  }, [stopPhysical]);

  const playImpression = useCallback(() => {
    engineRef.current?.stop();
    engineRef.current = buildEngine(current, freq);
    setPlaying(true);
  }, [current, freq]);

  // 物理モデル: サーバの OpenWind 合成 WAV を取得して再生。失敗時は印象合成へ退避。
  const playPhysical = useCallback(async (url: string, loop: boolean) => {
    stop();
    setPhysBusy(true); setPhysNote(null); setPlayed(null);
    try {
      const res = await fetch(url);
      if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json()).detail ?? detail; } catch { /* noop */ }
        throw new Error(detail);
      }
      const f0 = res.headers.get("X-Played-F0");
      const note = res.headers.get("X-Played-Note");
      if (note) setPlayed(`実際に鳴った音: ${note} (${f0}Hz)`);
      const buf = await res.arrayBuffer();
      const ctx = new AudioContext();
      const audio = await ctx.decodeAudioData(buf);
      const src = ctx.createBufferSource();
      src.buffer = audio; src.loop = loop; src.connect(ctx.destination);
      src.onended = () => { setPlaying(false); };
      src.start();
      physRef.current = { ctx, src };
      setPlaying(true);
    } catch (e) {
      setPhysNote(`物理モデル音合成に失敗（${(e as Error).message}）。印象合成に切替えました。`);
      setMode("impression");
    } finally {
      setPhysBusy(false);
    }
  }, [stop]);

  const play = useCallback(() => {
    if (mode === "physical") playPhysical(api.soundWavUrl(embouchure), true);
    else playImpression();
  }, [mode, playPhysical, playImpression, embouchure]);

  // 再生中にパラメータ/スロットが変わったら滑らかに追従
  useEffect(() => {
    if (playing && engineRef.current) updateEngine(engineRef.current, current);
  }, [current, playing]);

  useEffect(() => () => { engineRef.current?.stop(); stopPhysical(); }, [stopPhysical]);

  // 波形（1周期の加算合成）とスペクトル描画
  useEffect(() => {
    const wave = waveRef.current, spec = specRef.current;
    if (!wave || !spec) return;
    const dpr = window.devicePixelRatio || 1;
    for (const cv of [wave, spec]) {
      cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
    }
    const norm = current.amplitudes.reduce((a, b) => a + b, 0) || 1;

    const g1 = wave.getContext("2d")!;
    g1.scale(dpr, dpr);
    const W = wave.clientWidth, H = wave.clientHeight;
    g1.clearRect(0, 0, W, H);
    g1.strokeStyle = "#4da3ff"; g1.lineWidth = 1.6;
    g1.beginPath();
    for (let x = 0; x < W; x++) {
      const t = (x / W) * 2 * Math.PI * 2; // 2周期
      let y = 0;
      current.amplitudes.forEach((a, i) => { y += (a / norm) * Math.sin(t * (i + 1)); });
      const py = H / 2 - y * H * 0.42;
      x === 0 ? g1.moveTo(x, py) : g1.lineTo(x, py);
    }
    g1.stroke();

    const g2 = spec.getContext("2d")!;
    g2.scale(dpr, dpr);
    const W2 = spec.clientWidth, H2 = spec.clientHeight;
    g2.clearRect(0, 0, W2, H2);
    const bw = W2 / current.amplitudes.length;
    current.amplitudes.forEach((a, i) => {
      const h = a * (H2 - 14);
      g2.fillStyle = i === 0 ? "#7ec8a8" : "#4da3ff";
      g2.fillRect(i * bw + 2, H2 - h, bw - 4, h);
    });
    g2.fillStyle = "#8b96a6"; g2.font = "10px sans-serif";
    g2.fillText("倍音 1→16", 4, 10);
  }, [current]);

  return (
    <div className="simcard">
      <h3>音プレビュー</h3>
      <div className="abrow">
        {(["impression", "physical"] as const).map((m) => (
          <button key={m} className={mode === m ? "primary" : ""}
                  onClick={() => { stop(); setMode(m); }}>
            {m === "impression" ? "印象合成（即時）" : "物理モデル(OpenWind)"}
          </button>
        ))}
      </div>
      <div className="soundrow">
        {mode === "physical"
          ? <select value={embouchure} onChange={(e) => setEmbouchure(e.target.value)}>
              {EMBOUCHURES.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
            </select>
          : <select value={freq} onChange={(e) => setFreq(Number(e.target.value))}>
              {NOTES.map((n) => <option key={n.freq} value={n.freq}>{n.label}</option>)}
            </select>}
        {!playing
          ? <button className="primary" onClick={play} disabled={physBusy}>
              {physBusy ? "合成中… (最大40秒)" : "▶ 再生"}
            </button>
          : <button onClick={stop}>■ 停止</button>}
        {mode === "physical" && (
          <button onClick={() => playPhysical(api.scaleWavUrl(), false)}
                  disabled={physBusy || playing}>
            🎵 スケール
          </button>
        )}
      </div>
      {mode === "physical" && played && (
        <div className="advice" style={{ color: "#7ec8a8" }}>{played}</div>
      )}
      {mode === "physical" && !physNote && (
        <div className="advice">
          物理モデル音は OpenWind の時間領域リードシミュで合成（単音 約12秒・スケール 約35秒）。
          トーンホールの無い共鳴管なので<b>音高は指定できず</b>、アンブシュア（リード共振）で
          どの共鳴が立つかが決まる。実際に鳴った音は上に表示。
        </div>
      )}
      {physNote && <div className="advice" style={{ color: "#d9a441" }}>{physNote}</div>}
      <canvas ref={waveRef} className="scope" />
      <canvas ref={specRef} className="scope" style={{ marginTop: 6 }} />
      <div className="abrow">
        <button onClick={() => setSnapA({ name: "A案", harmonics })}>現在をAに記録</button>
        <button onClick={() => setSnapB({ name: "B案", harmonics })}>現在をBに記録</button>
      </div>
      <div className="abrow">
        {(["live", "A", "B"] as const).map((slot) => (
          <button key={slot}
                  className={active === slot ? "primary" : ""}
                  disabled={(slot === "A" && !snapA) || (slot === "B" && !snapB)}
                  onClick={() => setActive(slot)}>
            {slot === "live" ? "現在の設計" : slot === "A" ? "A案" : "B案"}
          </button>
        ))}
      </div>
      <div className="advice">{harmonics.note}</div>
    </div>
  );
}
