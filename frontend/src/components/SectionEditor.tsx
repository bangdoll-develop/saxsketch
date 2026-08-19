import { useCallback, useEffect, useRef, useState } from "react";
import { api, inSectionPlane, type SectionData, type SectionHandle } from "../api";

interface Props {
  /** 画面が持っている現在のパラメータ。そのままサーバへ渡して断面を描く */
  params: Record<string, unknown>;
  /** 確定時にパラメータへ反映する（App のデバウンス経路に乗る）。
   *  1 本のハンドルが複数キーを書くことがあるので dict で渡す（`also`）。 */
  onChange: (updates: Record<string, number>) => void;
  /** ドラッグ中の未確定値を App へ流す。null で解除。
   *  左のパラメータ欄がこれを重ねて表示するので、離す前から数値が追随する。 */
  onPreview: (updates: Record<string, number> | null) => void;
  /** 3D 形状の再生成中か。断面タブからでも「まだ計算中」だと分かるように出す */
  modelBusy?: boolean;
  /** 寸法を図示するか。状態は App が持ち、3D と共有する */
  showDims?: boolean;
  onToggleDims?: () => void;
  /** hover 中のパラメータキー。一致する寸法だけ色を変える */
  hoverKey?: string | null;
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

/** 断面座標 → このハンドルが書くパラメータ一式。
 *  span は [値が min のときの座標, max のときの座標]。
 *
 *  **主パラメータだけを step へ丸め、従属側は丸めた t から線形に引き直す。**
 *  従属値は主から解いた値なので、独立に丸めると解が崩れる（肩の終わりハンドルで
 *  肩比を 0.005 刻みに丸めると、保つはずの最大径の位置が 0.13〜0.17mm 動く）。 */
function valuesAt(h: SectionHandle, coord: number): Record<string, number> {
  const [s0, s1] = h.span;
  const span = h.max - h.min;
  if (Math.abs(s1 - s0) < 1e-9 || Math.abs(span) < 1e-12) {
    return { [h.key]: h.value };
  }
  const t = Math.min(Math.max((coord - s0) / (s1 - s0), 0), 1);
  const step = h.step || 0.01;
  const v = Math.min(Math.max(Math.round((h.min + t * span) / step) * step,
                              Math.min(h.min, h.max)),
                     Math.max(h.min, h.max));
  const out: Record<string, number> = { [h.key]: v };
  const tt = (v - h.min) / span;          // 丸めたあとの実際の位置
  for (const a of h.also) out[a.key] = a.min + tt * (a.max - a.min);
  return out;
}

export default function SectionEditor({
  params, onChange, onPreview, modelBusy, showDims, onToggleDims, hoverKey,
}: Props) {
  const [data, setData] = useState<SectionData | null>(null);
  const [err, setErr] = useState("");
  const [zoomAll, setZoomAll] = useState(false);
  const [dragKey, setDragKey] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragging = useRef<SectionHandle | null>(null);
  // ドラッグ中の未確定値。1 本のハンドルが複数キーを書くので dict で持つ。
  const pending = useRef<Record<string, number> | null>(null);
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

  // アンマウント（タブ切替）でドラッグが宙に浮くと、App 側の未確定値が
  // 残り続けて数値が固まる。必ず解除する。
  useEffect(() => () => { onPreview(null); }, [onPreview]);

  // 画面座標 → mm の逆行列は**掴んだ瞬間に固定する**。
  // 値によって警告メッセージの数が変わり、その高さぶん SVG がリサイズされる。
  // 毎回 getScreenCTM() を取り直すと、同じ場所を指しているのに mm が変わり、
  // 図がカーソルの下で跳ねる（実測: 同じ画面 y が -4.48mm → -6.57mm → -4.79mm）。
  const dragCtm = useRef<DOMMatrix | null>(null);

  const toMm = (e: React.PointerEvent) => {
    const m = dragCtm.current ?? svgRef.current?.getScreenCTM()?.inverse();
    if (!m) return { z: 0, y: 0 };
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m);
    return { z: p.x, y: -p.y };
  };

  const onDown = (h: SectionHandle) => (e: React.PointerEvent) => {
    e.preventDefault();
    // ポインタキャプチャは環境によっては拒否される。掴めなくてもドラッグ自体は
    // svg 上のイベントで成立するので、失敗しても続行する。
    try { svgRef.current?.setPointerCapture(e.pointerId); } catch { /* noop */ }
    dragCtm.current = svgRef.current?.getScreenCTM()?.inverse() ?? null;
    dragging.current = h;
    pending.current = { [h.key]: h.value };
    setDragKey(h.key);
    onPreview({ [h.key]: h.value });
  };

  const onMove = (e: React.PointerEvent) => {
    const h = dragging.current;
    if (!h) return;
    const pt = toMm(e);
    const vals = valuesAt(h, h.axis === "z" ? pt.z : pt.y);
    pending.current = vals;
    onPreview(vals);   // 左のパラメータ欄をその場で追随させる（従属キーも含む）
    // プレビューは1本だけ飛ばす（応答待ちの間は間引く）。CAD ビルドを伴わない
    // エンドポイントなので、この間引きだけで十分追従する。
    if (!inflight.current) {
      inflight.current = true;
      load(vals).finally(() => { inflight.current = false; });
    }
  };

  const onUp = (e: React.PointerEvent) => {
    const h = dragging.current;
    if (!h) return;
    try { svgRef.current?.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    dragging.current = null;
    dragCtm.current = null;
    setDragKey(null);
    // 先に確定してから未確定値を解除する。逆にすると 1 フレームだけ古い値へ
    // 戻って数値がちらつく。主キーが動いていなければ従属キーも動いていない。
    if (pending.current !== null && pending.current[h.key] !== h.value) {
      onChange(pending.current);
    }
    pending.current = null;
    onPreview(null);
  };

  // 取得に失敗しても直前の断面は残す（ドラッグ中の1本が落ちただけで画面が
  // 消えると、何を触っていたか分からなくなる）。
  if (!data) {
    return <div className="sec-msg">{err ? `断面を取得できません: ${err}` : "断面を計算中…"}</div>;
  }

  const c = data.curves;
  // ハンドルはズームと同じタブで出し分ける。外形のハンドル（最大径・肩・シャンク）は
  // バッフル表示だと画面の外にあり、掴めないのに凡例だけ出ることになる。
  const group = zoomAll ? "outer" : "baffle";
  const handles = data.handles.filter((h) => h.active && h.group === group);

  // 表示範囲。既定はバッフル（ボア開始まで）に寄せる — 編集対象がそこだから。
  const zHi = zoomAll ? data.z_range[1] : (c.bore_top?.[0]?.[0] ?? data.z_range[1]);
  const zb0 = -1.5;
  const zb1 = zHi + 1.5;
  const ys = [...c.outer_top, ...c.outer_bot].filter(([z]) => z >= zb0 && z <= zb1);
  let yMax = Math.max(...ys.map(([, y]) => y)) + 1.0;
  let yMin = Math.min(...ys.map(([, y]) => y)) - 1.0;
  let z0 = zb0;
  let z1 = zb1;

  // 寸法。x=0 に写せるものだけを描く（判定は座標から導く）。逃がし量は
  // **本体の表示幅**から出す（サーバは向きと段だけを持つ）。
  const dimBase = 0.05 * (zb1 - zb0);
  const dims = (showDims ? data.dimensions ?? [] : [])
    .filter(inSectionPlane)
    // **表示中の z 範囲に収まるものだけ。** バッフル表示のまま全長の寸法を描くと、
    // 表示範囲がそれに引きずられて拡大が効かなくなる（ハンドルをタブで
    // 出し分けているのと同じ理由）。
    .filter((d) => Math.min(d.a[2], d.b[2]) >= zb0 && Math.max(d.a[2], d.b[2]) <= zb1)
    .map((d) => {
      const off = dimBase * (d.level + 1);
      const tz = d.dir[2] * dimBase * 0.12;
      const ty = d.dir[1] * dimBase * 0.12;
      return {
        d,
        az: d.a[2] + d.dir[2] * off, ay: d.a[1] + d.dir[1] * off,
        bz: d.b[2] + d.dir[2] * off, by: d.b[1] + d.dir[1] * off,
        tz, ty,
      };
    });
  // **寸法線を表示範囲へ入れる。** 入れないと外へ逃がした線がそのまま画面外で
  // 切れる（範囲は外形ポリラインと ±1.5mm の決め打ちだけから決まっていた）。
  for (const g of dims) {
    z0 = Math.min(z0, g.az, g.bz);
    z1 = Math.max(z1, g.az, g.bz);
    yMin = Math.min(yMin, g.ay, g.by);
    yMax = Math.max(yMax, g.ay, g.by);
  }
  if (dims.length) {
    const pad = dimBase * 0.6;      // 目盛とラベルのぶん
    z0 -= pad; z1 += pad; yMin -= pad; yMax += pad;
  }
  const vb = `${z0} ${-yMax} ${z1 - z0} ${yMax - yMin}`;
  const r = (z1 - z0) / 70;   // ハンドル半径（mm）。表示幅に対しほぼ一定
  const fs = (z1 - z0) / 55;  // 寸法の文字（mm）。等方スケールなので歪まない

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
        {dims.map((g) => (
          <g key={g.d.key}
             className={"sec-dim" + (hoverKey && hoverKey === g.d.key ? " live" : "")}>
            <line x1={g.d.a[2]} y1={-g.d.a[1]}
                  x2={g.az + g.tz} y2={-(g.ay + g.ty)} />
            <line x1={g.d.b[2]} y1={-g.d.b[1]}
                  x2={g.bz + g.tz} y2={-(g.by + g.ty)} />
            <line x1={g.az} y1={-g.ay} x2={g.bz} y2={-g.by} />
            <line x1={g.az - g.tz} y1={-(g.ay - g.ty)}
                  x2={g.az + g.tz} y2={-(g.ay + g.ty)} />
            <line x1={g.bz - g.tz} y1={-(g.by - g.ty)}
                  x2={g.bz + g.tz} y2={-(g.by + g.ty)} />
            <text x={(g.az + g.bz) / 2 + g.tz * 2.2}
                  y={-((g.ay + g.by) / 2 + g.ty * 2.2)}
                  fontSize={fs} textAnchor="middle" dominantBaseline="middle">
              {`${g.d.label} ${g.d.value.toFixed(2)}${g.d.unit ? " " + g.d.unit : ""}`}
              {g.d.requested !== undefined && `（指定 ${g.d.requested.toFixed(2)}）`}
            </text>
          </g>
        ))}
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
            外形（全体）
          </button>
        </div>
        {(data.dimensions ?? []).length > 0 && (
          <button className={"sec-dim-toggle" + (showDims ? " active" : "")}
                  onClick={onToggleDims} title="パラメータの寸法を図示する">
            📏 寸法
          </button>
        )}
        {handles.map((h) => (
          <span key={h.key} className={"sec-chip" + (dragKey === h.key ? " live" : "")}>
            {h.label}
            <b>{h.value.toFixed(2)}</b>
            <i>{h.unit}</i>
          </span>
        ))}
        {handles.length === 0 && (
          <span className="sec-chip">
            {group === "baffle"
              ? "このバッフル種別に断面ハンドルはありません"
              : "この部品に外形ハンドルはありません"}
          </span>
        )}
        {/* 断面と数値は即座に追随するが 3D は数秒遅れる。壊れているのではなく
            まだ計算中だと分かるように、断面タブからも見えるようにしておく。 */}
        {modelBusy && <span className="sec-chip busy">⏳ 3D を再生成中…</span>}
      </div>

      {err && <div className="sec-warn">⚠ 断面の更新に失敗しました: {err}</div>}
      {data.warnings.map((w, i) => (
        <div className="sec-warn" key={i}>⚠ {w}</div>
      ))}
    </div>
  );
}
