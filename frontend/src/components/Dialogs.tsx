import { useEffect, useState } from "react";
import {
  api, type ExportResult, type GoalSeekResult, type InstrumentSummary,
  type ParamSpec, type Tier2,
} from "../api";
import { useCapabilities, usePathPicker } from "../pathPicker";

export function Backdrop({ children, onClose }: {
  children: React.ReactNode; onClose?: () => void;
}) {
  return (
    <div className="dialog-backdrop"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="dialog">{children}</div>
    </div>
  );
}

// ------------------------------------------------------------------ 新規プロジェクト

export function NewProjectDialog({ onCreated, onClose, allowClose }: {
  onCreated: () => void; onClose: () => void; allowClose: boolean;
}) {
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);
  const [instrumentId, setInstrumentId] = useState("saxophone");
  const [templateId, setTemplateId] = useState("alto");
  const [componentId, setComponentId] = useState("mouthpiece");
  // セットで作るか単体で作るか。**既定はセット** —— 一式を作るのが主目的で、
  // 単体はそこから外れる作り方（管体・ネックは当面ずっと単体）。
  const [asSet, setAsSet] = useState(true);
  const [setId, setSetId] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const pickPath = usePathPicker();

  useEffect(() => {
    api.instruments().then(setInstruments).catch(() => setErr("サーバに接続できません"));
    api.recent().then(setRecent).catch(() => {});
  }, []);

  const inst = instruments.find((i) => i.id === instrumentId);
  const sets = inst?.sets ?? [];
  // セットを持たない楽器では単体しか作れない（UI に楽器名を書かないための分岐）
  const canSet = sets.length > 0;
  const chosenSet = sets.find((s) => s.id === setId) ?? sets[0];

  const create = async () => {
    try {
      await api.newProject(
        canSet && asSet
          ? { instrument_id: instrumentId, template_id: templateId,
              set_id: chosenSet?.id }
          : { instrument_id: instrumentId, template_id: templateId,
              component_id: componentId });
      onCreated();
    } catch (e) { setErr(String((e as Error).message)); }
  };

  const openPath = async (path: string) => {
    try { await api.open(path); onCreated(); }
    catch (e) { setErr(String((e as Error).message)); }
  };

  const browseOpen = async () => {
    const path = await pickPath("open");
    if (path) await openPath(path);
  };

  return (
    <Backdrop onClose={allowClose ? onClose : undefined}>
      <h2>新規プロジェクト</h2>
      <div className="drow">
        <label>楽器</label>
        <select value={instrumentId} onChange={(e) => setInstrumentId(e.target.value)}>
          {instruments.map((i) => <option key={i.id} value={i.id}>{i.label}</option>)}
        </select>
      </div>
      <div className="drow">
        <label>サイズテンプレート</label>
        <select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
          {inst?.templates.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
      </div>
      {canSet && (
        <div className="drow">
          <label>作り方</label>
          <label style={{ minWidth: 0 }}>
            <input type="radio" checked={asSet} onChange={() => setAsSet(true)} />
            {" "}セット（一式）
          </label>
          <label style={{ minWidth: 0 }}>
            <input type="radio" checked={!asSet} onChange={() => setAsSet(false)} />
            {" "}単体
          </label>
        </div>
      )}
      {canSet && asSet ? (
        <div className="drow">
          <label>セット構成</label>
          <select value={chosenSet?.id ?? ""} onChange={(e) => setSetId(e.target.value)}>
            {sets.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
      ) : (
        <div className="drow">
          <label>コンポーネント</label>
          <select value={componentId} onChange={(e) => setComponentId(e.target.value)}>
            {inst?.components.map((c) => (
              <option key={c.id} value={c.id} disabled={!c.available}>{c.label}</option>
            ))}
          </select>
        </div>
      )}
      {canSet && asSet && chosenSet && (
        <div className="note">
          {chosenSet.members.map((m) => m.label
            + (m.required ? "" : "（任意・後から追加）")).join(" ＋ ")}
          。土台は{chosenSet.members.find((m) => m.master)?.label ?? "先頭の部品"}で、
          下流の部品はその設計値に追従します。
        </div>
      )}
      {err && <div style={{ color: "var(--err)" }}>{err}</div>}
      <div className="actions">
        {allowClose && <button onClick={onClose}>キャンセル</button>}
        <button onClick={browseOpen}>既存プロジェクトを開く…</button>
        <button className="primary" onClick={create}>作成</button>
      </div>
      {recent.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ color: "var(--muted)", marginBottom: 4 }}>最近使ったプロジェクト</div>
          {recent.map((p) => (
            <button key={p} className="recent-item" onClick={() => openPath(p)}>{p}</button>
          ))}
        </div>
      )}
    </Backdrop>
  );
}

// ------------------------------------------------------------------ ゴールシーク

const GS_METRICS = ["brightness", "power", "resistance", "flexibility", "edge"] as const;

export function GoalSeekDialog({ tier2, schema, onApply, onClose }: {
  tier2: Tier2; schema: ParamSpec[];
  onApply: (proposal: Record<string, number>) => void; onClose: () => void;
}) {
  const [targets, setTargets] = useState<Record<string, number>>(
    () => Object.fromEntries(GS_METRICS.map((m) => [m, tier2[m] as number])));
  const [enabled, setEnabled] = useState<Record<string, boolean>>(
    { brightness: true, power: false, resistance: false, flexibility: false, edge: false });
  const [pitchNeutral, setPitchNeutral] = useState(true);
  const [result, setResult] = useState<GoalSeekResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const labelOf = (key: string) => schema.find((s) => s.key === key)?.label ?? key;

  const run = async () => {
    setBusy(true); setErr("");
    try {
      const t: Record<string, unknown> = { pitch_neutral: pitchNeutral };
      for (const m of GS_METRICS) if (enabled[m]) t[m] = targets[m];
      setResult(await api.goalSeek(t));
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <Backdrop onClose={onClose}>
      <h2>目標から逆算（ゴールシーク）</h2>
      {GS_METRICS.map((m) => (
        <div className="drow" key={m}>
          <label>
            <input type="checkbox" checked={enabled[m]}
                   onChange={(e) => setEnabled({ ...enabled, [m]: e.target.checked })} />
            {" "}{tier2.labels[m]}
          </label>
          <input type="range" min={0} max={10} step={0.1} value={targets[m]}
                 disabled={!enabled[m]} style={{ flex: 1, accentColor: "var(--accent)" }}
                 onChange={(e) => setTargets({ ...targets, [m]: Number(e.target.value) })} />
          <span style={{ width: 34, textAlign: "right" }}>{targets[m].toFixed(1)}</span>
        </div>
      ))}
      <div className="drow">
        <label>
          <input type="checkbox" checked={pitchNeutral}
                 onChange={(e) => setPitchNeutral(e.target.checked)} />
          {" "}音程ニュートラルを維持
        </label>
      </div>
      <div className="actions">
        <button onClick={onClose}>閉じる</button>
        <button className="primary" onClick={run} disabled={busy}>
          {busy ? "計算中…" : "逆算する"}
        </button>
      </div>
      {err && <div style={{ color: "var(--err)" }}>{err}</div>}
      {result && (
        <div style={{ marginTop: 14 }}>
          <table>
            <thead><tr><th>パラメータ</th><th>現在</th><th>提案</th></tr></thead>
            <tbody>
              {Object.entries(result.proposal).map(([k, v]) => (
                <tr key={k}>
                  <td>{labelOf(k)}</td>
                  <td>{Number(result.current[k]).toFixed(2)}</td>
                  <td style={{ color: Math.abs(v - Number(result.current[k])) > 1e-6
                                 ? "var(--accent2)" : undefined }}>
                    {v.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="note">
            予測: 明るさ {result.predicted_metrics.brightness.toFixed(1)} /
            パワー {result.predicted_metrics.power.toFixed(1)} /
            チューニング位置 {result.predicted_tier1.in_tune_mm === null ? "—"
              : `${result.predicted_tier1.in_tune_mm.toFixed(1)} mm`} — {result.note}
          </div>
          <div className="actions">
            <button onClick={() => setResult(null)}>破棄</button>
            <button className="primary"
                    onClick={() => { onApply(result.proposal); onClose(); }}>
              提案を適用
            </button>
          </div>
        </div>
      )}
    </Backdrop>
  );
}

// ------------------------------------------------------------------ エクスポート

export function ExportDialog({ onClose, setInfo }: {
  onClose: () => void;
  /** セットなら部品の一覧（単体では null）。範囲の選択を出すかの判断に使う */
  setInfo?: { label: string; members: { label: string; present: boolean }[] } | null;
}) {
  const [formats, setFormats] = useState<Record<string, boolean>>(
    { stl: true, step: true, "3mf": true });
  // セットなら既定は一式。個別に出したいときだけ切り替える。
  const [scope, setScope] = useState<"set" | "member">("set");
  const [outDir, setOutDir] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [err, setErr] = useState("");
  const pickPath = usePathPicker();
  const caps = useCapabilities();

  const browse = async () => {
    const path = await pickPath("dir", outDir);
    if (path) setOutDir(path);
  };

  const run = async () => {
    setBusy(true); setErr(""); setResult(null);
    try {
      setResult(await api.export_({
        formats: Object.keys(formats).filter((f) => formats[f]),
        out_dir: outDir || null, make_package: true,
        scope: setInfo ? scope : "member",
      }));
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <Backdrop onClose={onClose}>
      <h2>エクスポート / 入稿データ生成</h2>
      {setInfo && (
        <div className="drow">
          <label>出力範囲</label>
          <label style={{ minWidth: 0 }}>
            <input type="radio" checked={scope === "set"}
                   onChange={() => setScope("set")} />
            {" "}セット一式（
            {setInfo.members.filter((m) => m.present).map((m) => m.label).join("＋")}
            ）
          </label>
          <label style={{ minWidth: 0 }}>
            <input type="radio" checked={scope === "member"}
                   onChange={() => setScope("member")} />
            {" "}いま編集中の部品だけ
          </label>
        </div>
      )}
      <div className="drow">
        <label>3Dモデル形式</label>
        {(["stl", "step", "3mf"] as const).map((f) => (
          <label key={f} style={{ minWidth: 0 }}>
            <input type="checkbox" checked={formats[f]}
                   onChange={(e) => setFormats({ ...formats, [f]: e.target.checked })} />
            {" "}{f.toUpperCase()}
          </label>
        ))}
      </div>
      <div className="drow">
        <label>出力先</label>
        <input type="text" style={{ flex: 1 }} value={outDir}
               placeholder={caps ? `（既定: ${caps.export_root}）` : "（既定の場所）"}
               onChange={(e) => setOutDir(e.target.value)} />
        <button onClick={browse}>参照…</button>
      </div>
      <div className="note">
        {setInfo && scope === "set" && (
          <>部品ごとのフォルダに分かれ、仕様書と部品表は<b>1 式で 1 枚</b>にまとまります。<br /></>
        )}
        仕様書(spec.html)・部品表(bom.csv)・入稿パッケージZIPも同時に生成されます。
        ZIPはオンライン3Dプリントサービス（JLC3DP / PCBWay / Shapeways 等）へ
        そのままアップロードできます。
      </div>
      <div className="actions">
        <button onClick={onClose}>閉じる</button>
        <button className="primary" onClick={run} disabled={busy}>
          {busy ? "生成中…（数十秒かかることがあります）" : "生成する"}
        </button>
      </div>
      {err && <div style={{ color: "var(--err)" }}>{err}</div>}
      {result && (
        <div style={{ marginTop: 12 }}>
          <div style={{ color: "var(--accent2)", marginBottom: 6 }}>
            ✓ 生成完了
            {result.mesh_quality &&
              ` — STL水密性: ${result.mesh_quality.watertight ? "OK" : "要確認"} / ` +
              `体積 ${result.mesh_quality.volume_cc ?? "-"} cc`}
          </div>
          <div className="filelist">
            {Object.entries(result.files).map(([name, path]) => (
              <div key={name}>
                {name}
                {name === "spec.html" &&
                  <button onClick={() => api.toolOpen("browser", path)}>開く</button>}
                {name === "model.stl" && <>
                  <button onClick={() => api.toolOpen("slicer", path).catch(
                    (e) => alert((e as Error).message))}>スライサーで開く</button>
                  <button onClick={() => api.toolOpen("freecad", path).catch(
                    (e) => alert((e as Error).message))}>FreeCADで開く</button>
                </>}
              </div>
            ))}
            {result.package && <div>📦 {result.package.split("\\").pop()}</div>}
          </div>
          <div className="actions">
            <button onClick={() => api.toolOpen("reveal",
              result.package ?? Object.values(result.files)[0])}>
              フォルダを開く
            </button>
          </div>
        </div>
      )}
    </Backdrop>
  );
}

// ------------------------------------------------------------------ 設定

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [tools, setTools] = useState<Record<string, string>>({ freecad: "", slicer: "" });
  const [exportRoot, setExportRoot] = useState("");
  const pickPath = usePathPicker();
  const caps = useCapabilities();

  useEffect(() => {
    api.settings().then((s) => {
      const t = (s.external_tools ?? {}) as Record<string, string>;
      setTools({ freecad: t.freecad ?? "", slicer: t.slicer ?? "" });
      setExportRoot(String(s.export_root ?? ""));
    });
  }, []);

  const save = async () => {
    await api.putSettings({ external_tools: { ...tools }, export_root: exportRoot });
    onClose();
  };

  return (
    <Backdrop onClose={onClose}>
      <h2>設定 — 外部ツール連携</h2>
      <div className="drow">
        <label>FreeCAD パス</label>
        <input type="text" style={{ flex: 1 }} value={tools.freecad}
               placeholder="例: C:\Program Files\FreeCAD 1.0\bin\FreeCAD.exe"
               onChange={(e) => setTools({ ...tools, freecad: e.target.value })} />
      </div>
      <div className="drow">
        <label>スライサー パス</label>
        <input type="text" style={{ flex: 1 }} value={tools.slicer}
               placeholder="例: C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe"
               onChange={(e) => setTools({ ...tools, slicer: e.target.value })} />
      </div>
      <div className="drow">
        <label>既定の出力先</label>
        <input type="text" style={{ flex: 1 }} value={exportRoot}
               placeholder={caps ? `（自動: ${caps.export_root}）` : "（自動）"}
               onChange={(e) => setExportRoot(e.target.value)} />
        <button onClick={async () => {
          const p = await pickPath("dir", exportRoot || caps?.export_root || "");
          if (p) setExportRoot(p);
        }}>参照…</button>
      </div>
      <div className="note">
        既定の出力先は空にしておくと環境から自動で決まります
        （WSL で動かしている場合は Windows 側のドキュメントフォルダ）。
        PrusaSlicer / OrcaSlicer / Bambu Studio 等、STLを開けるスライサーを登録できます。
        音響シミュレーション（OpenWind）統合は Phase 2 で追加予定です。
      </div>
      <div className="actions">
        <button onClick={onClose}>キャンセル</button>
        <button className="primary" onClick={save}>保存</button>
      </div>
    </Backdrop>
  );
}
