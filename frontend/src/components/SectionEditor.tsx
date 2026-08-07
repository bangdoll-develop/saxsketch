import { useCallback, useEffect, useRef, useState } from "react";
import { api, type SectionData, type SectionHandle } from "../api";

interface Props {
  /** 画面が持っている現在のパラメータ。そのままサーバへ渡して断面を描く */
  params: Record<string, unknown>;
  /** 確定時にパラメータへ反映する（App のデバウンス経路に乗る） */
  onChange: (key: string, value: number) => void;
}

/** クエリに載せられる値だけ抜く（数値と選択肢）。 */
function primitives(params: Record<string, unknown>): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(params)) {
    if (typeof v === "number" || typeof v === "string") out[k] = v;
  }
  return out;
}

/** SVG は y 下向き。形状は y 上向きなので符号を反転して描く。 */
const path = (pts: [number, number][]) =>
  pts.map(([z, y], i) => `${i ? "L" : "M"}${z.toFixed(3)},${(-y).toFixed(3)}`).join(" ");

/** 2本のポリラインで囲まれた帯（上側→下側を逆順に辿って閉じる） */
const band = (top: [number, number][], bot: [number, number][]) =>
  path(top) + " " +
  bot.slice().reverse().map(([z, y]) => `L${z.toFixed(3)},${(-y).toFixed(3)}`).join(" ") +
  " Z";

/** 断面座標 → パラメータ値。span は [値が min のときの座標, max のときの座標] */
function valueAt(h: SectionHandle, coord: number): number {
  const [s0, s1] = h.span;
  if (Math.abs(s1 - s0) < 1e-9) return h.value;
  const t = Math.min(Math.max((coord - s0) / (s1 - s0), 0), 1);
  const v = h.min + t * (h.max - h.min);
  const step = h.step || 0.01;
  return Math.min(Math.max(Math.round(v / step) * step, h.min), h.max);
}

export default function SectionEditor({ params, onChange }: Props) {
  const [data, setData] = useState<SectionData | null>(null);
  const [err, setErr] = useState("");
  const [zoomAll, setZoomAll] = useState(false);
  const [dragKey, setDragKey] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragging = useRef<SectionHandle | null>(null);
  const pending = useRef<number | null>(null);   // ドラッグ中の未確定値
  const inflight = useRef(false);
  const seq = useRef(0);

  // 画面が持っている値をそのままサーバへ渡す。App はパラメータを楽観更新してから
  // 250ms のデバウンスで PUT するので、サーバの状態を読みに行くと断面が 1 手ぶん
  // 遅れる（ドラッグを離した直後がまさにそれだった）。値を渡してしまえば
  // PUT の完了とは無関係に常に「いま見えている形」が返る。
  const paramsRef = useRef(params);
  paramsRef.current = params;
  const paramsKey = JSON.stringify(params);

  // 応答が前後しても最後に投げたものだけを採る。ドラッグ中のプレビューと
  // 確定後の再取得が競り、遅れて届いた古いプレビューが確定値を上書きしていた。
  const load = useCallback(async (override?: Record<string, number>) => {
    const my = ++seq.current;
    try {
      const d = await api.section({ ...primitives(paramsRef.current), ...override });
      if (my === seq.current) { setData(d); setErr(""); }
    } catch (e) {
      if (my === seq.current) setErr(String((e as Error).message));
    }
  }, []);

  useEffect(() => { if (!dragging.current) load(); }, [paramsKey, load]);

  const toMm = (e: React.PointerEvent) => {
    const svg = svgRef.current;
    const m = svg?.getScreenCTM();
    if (!svg || !m) return { z: 0, y: 0 };
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    return { z: p.x, y: -p.y };
  };

  const onDown = (h: SectionHandle) => (e: React.PointerEvent) => {
    e.preventDefault();
    // ポインタキャプチャは環境によっては拒否される。掴めなくてもドラッグ自体は
    // svg 上のイベントで成立するので、失敗しても続行する。
    try { svgRef.current?.setPointerCapture(e.pointerId); } catch { /* noop */ }
    dragging.current = h;
    pending.current = h.value;
    setDragKey(h.key);
  };

  const onMove = (e: React.PointerEvent) => {
    const h = dragging.current;
    if (!h) return;
    const pt = toMm(e);
    const v = valueAt(h, h.axis === "z" ? pt.z : pt.y);
    pending.current = v;
    // プレビューは1本だけ飛ばす（応答待ちの間は間引く）。CAD ビルドを伴わない
    // エンドポイントなので、この間引きだけで十分追従する。
    if (!inflight.current) {
      inflight.current = true;
      load({ [h.key]: v }).finally(() => { inflight.current = false; });
    }
  };

  const onUp = (e: React.PointerEvent) => {
    const h = dragging.current;
    if (!h) return;
    try { svgRef.current?.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    dragging.current = null;
    setDragKey(null);
    if (pending.current !== null && pending.current !== h.value) {
      onChange(h.key, pending.current);
    }
    pending.current = null;
  };

  // 取得に失敗しても直前の断面は残す（ドラッグ中の1本が落ちただけで画面が
  // 消えると、何を触っていたか分からなくなる）。
  if (!data) {
    return <div className="sec-msg">{err ? `断面を取得できません: ${err}` : "断面を計算中…"}</div>;
  }

  const c = data.curves;
  const handles = data.handles.filter((h) => h.active);

  // 表示範囲。既定はバッフル（ボア開始まで）に寄せる — 編集対象がそこだから。
  const zHi = zoomAll ? data.z_range[1] : (c.bore_top?.[0]?.[0] ?? data.z_range[1]);
  const z0 = -1.5;
  const z1 = zHi + 1.5;
  const ys = [...c.outer_top, ...c.outer_bot].filter(([z]) => z >= z0 && z <= z1);
  const yMax = Math.max(...ys.map(([, y]) => y)) + 1.0;
  const yMin = Math.min(...ys.map(([, y]) => y)) - 1.0;
  const vb = `${z0} ${-yMax} ${z1 - z0} ${yMax - yMin}`;
  const r = (z1 - z0) / 70;   // ハンドル半径（mm）。表示幅に対しほぼ一定

  return (
    <div className="section-editor">
      <svg ref={svgRef} className="sec-svg" viewBox={vb}
           preserveAspectRatio="xMidYMid meet"
           onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
        {/* 材料（外形からリード面まで） */}
        <path d={band(c.outer_top, c.outer_bot)} className="sec-body" />
        {/* 内部空洞。天井がバッフル */}
        <path d={band(c.roof, c.floor)} className="sec-air" />
        <path d={band(c.bore_top, c.bore_bot)} className="sec-air" />
        {/* 天井の上限（ここに当たるとバッフルを開いても形が変わらない） */}
        <path d={path(c.shell_top)} className="sec-limit" />
        <path d={path(c.reed)} className="sec-reed" />
        <path d={path(c.roof)} className="sec-roof" />
        <path d={path(c.floor)} className="sec-floor" />
        {handles.map((h) => {
          const live = dragKey === h.key;
          return (
            <g key={h.key} className={"sec-handle" + (live ? " live" : "")}>
              {h.axis === "z" ? (
                <line x1={h.span[0]} y1={-h.y} x2={h.span[1]} y2={-h.y}
                      className="sec-rail" />
              ) : (
                <line x1={h.z} y1={-h.span[0]} x2={h.z} y2={-h.span[1]}
                      className="sec-rail" />
              )}
              <circle cx={h.z} cy={-h.y} r={r} onPointerDown={onDown(h)} />
            </g>
          );
        })}
      </svg>

      <div className="sec-legend">
        <div className="sec-tabs">
          <button className={zoomAll ? "" : "active"} onClick={() => setZoomAll(false)}>
            バッフル
          </button>
          <button className={zoomAll ? "active" : ""} onClick={() => setZoomAll(true)}>
            全体
          </button>
        </div>
        {handles.map((h) => (
          <span key={h.key} className={"sec-chip" + (dragKey === h.key ? " live" : "")}>
            {h.label}
            <b>{h.value.toFixed(2)}</b>
            <i>{h.unit}</i>
          </span>
        ))}
        {handles.length === 0 && (
          <span className="sec-chip">この種別に断面ハンドルはありません</span>
        )}
      </div>

      {err && <div className="sec-warn">⚠ 断面の更新に失敗しました: {err}</div>}
      {data.warnings.map((w, i) => (
        <div className="sec-warn" key={i}>⚠ {w}</div>
      ))}
    </div>
  );
}
