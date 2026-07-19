import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api, type ManualEdit, type ProjectData, type Region, type Simulation,
} from "./api";
import ParamPanel from "./components/ParamPanel";
import SimPanel from "./components/SimPanel";
import Viewer3D from "./components/Viewer3D";
import {
  ExportDialog, GoalSeekDialog, NewProjectDialog, SettingsDialog,
} from "./components/Dialogs";
import { ManualEditDialog } from "./components/ManualEdit";

type DialogKind = null | "new" | "goalseek" | "export" | "settings" | "manual";

export default function App() {
  const [project, setProject] = useState<ProjectData | null>(null);
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [sim, setSim] = useState<Simulation | null>(null);
  const [modelVersion, setModelVersion] = useState(0);
  const [modelBusy, setModelBusy] = useState(false);
  const [dialog, setDialog] = useState<DialogKind>("new");
  const [error, setError] = useState("");
  const [regions, setRegions] = useState<Record<string, Region>>({});
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [manualEdit, setManualEdit] = useState<ManualEdit | null>(null);
  const [viewDerived, setViewDerived] = useState(false);
  const [staleWarn, setStaleWarn] = useState(false);

  const paramTimer = useRef<number>(0);
  const modelTimer = useRef<number>(0);
  const pendingParams = useRef<Record<string, unknown>>({});
  const manualEditRef = useRef<ManualEdit | null>(null);
  useEffect(() => { manualEditRef.current = manualEdit; }, [manualEdit]);

  useEffect(() => {
    // 起動時: サーバに既存セッションがあれば復元、なければ新規ダイアログのまま
    api.getProject().then((p) => {
      setProject(p); setParams(p.params); setSim(p.simulation);
      setManualEdit(p.manual_edit);
      setModelVersion((v) => v + 1); setDialog(null);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(""), 5000);
    return () => clearTimeout(t);
  }, [error]);

  useEffect(() => {
    if (!staleWarn) return;
    const t = setTimeout(() => setStaleWarn(false), 9000);
    return () => clearTimeout(t);
  }, [staleWarn]);

  useEffect(() => {
    // 影響領域は形状パラメータに依存 → モデル更新のたびに再取得
    if (!project) return;
    api.regions().then(setRegions).catch(() => {});
  }, [modelVersion, project]);

  const regionKeys = useMemo(() => new Set(Object.keys(regions)), [regions]);
  const highlight = hoverKey ? regions[hoverKey] ?? null : null;

  const loadProject = useCallback(async () => {
    const p = await api.getProject();
    setProject(p); setParams(p.params); setSim(p.simulation);
    setManualEdit(p.manual_edit);
    setViewDerived(false);
    setModelVersion((v) => v + 1);
    setDialog(null);
  }, []);

  // 外部編集ダイアログの操作後: パラメータは変えず manual_edit 状態のみ更新
  const refreshManualEdit = useCallback(async () => {
    try {
      const p = await api.getProject();
      setManualEdit(p.manual_edit);
      if (!p.manual_edit.derived) setViewDerived(false);
    } catch { /* noop */ }
  }, []);

  const pushParams = useCallback((updates: Record<string, unknown>) => {
    pendingParams.current = { ...pendingParams.current, ...updates };
    // シミュレーションは軽いので短いデバウンス
    window.clearTimeout(paramTimer.current);
    paramTimer.current = window.setTimeout(async () => {
      const payload = pendingParams.current;
      pendingParams.current = {};
      try {
        const r = await api.putParams(payload);
        setParams(r.params); setSim(r.simulation);
        const prev = manualEditRef.current;
        if (prev && r.stale && !prev.stale) setStaleWarn(true);  // 陳腐化した瞬間に警告
        if (prev && prev.stale !== r.stale) setManualEdit({ ...prev, stale: r.stale });
      } catch (e) { setError(String((e as Error).message)); }
      // 形状再生成は重いので長めのデバウンス
      window.clearTimeout(modelTimer.current);
      modelTimer.current = window.setTimeout(
        () => setModelVersion((v) => v + 1), 500);
    }, 250);
  }, []);

  const onParamChange = useCallback((key: string, value: unknown) => {
    setParams((prev) => ({ ...prev, [key]: value }));  // 楽観更新
    pushParams({ [key]: value });
  }, [pushParams]);

  const saveProject = useCallback(async (saveAs: boolean) => {
    if (!project) return;
    let path = project.path;
    if (saveAs || !path) {
      const r = await api.dialog("save", `${project.name}.wproj`);
      if (!r.path) return;
      path = r.path;
    }
    try {
      const res = await api.save(path);
      setProject({ ...project, path: res.path });
    } catch (e) { setError(String((e as Error).message)); }
  }, [project]);

  // 参照マウスピースの差替え（リード/リガチャーのみ）。寸法が変わるので形状も作り直す
  const setReference = useCallback(async (path: string | null) => {
    if (!project) return;
    try {
      const p = await api.setReference(
        project.reference?.component_id ?? "mouthpiece", path);
      setProject(p); setParams(p.params); setSim(p.simulation);
      setModelVersion((v) => v + 1);
    } catch (e) { setError(String((e as Error).message)); }
  }, [project]);

  const pickReference = useCallback(async () => {
    const r = await api.dialog("open");
    if (r.path) setReference(r.path);
  }, [setReference]);

  const applyProposal = useCallback((proposal: Record<string, number>) => {
    setParams((prev) => ({ ...prev, ...proposal }));
    pushParams(proposal);
  }, [pushParams]);

  return (
    <>
      <div className="toolbar">
        <span className="logo">🎷 SaxSketch</span>
        <button onClick={() => setDialog("new")}>新規 / 開く</button>
        <button onClick={() => saveProject(false)} disabled={!project}>保存</button>
        <button onClick={() => saveProject(true)} disabled={!project}>名前を付けて保存</button>
        <button onClick={() => setDialog("manual")} disabled={!project}>
          🛠 外部編集
          {manualEdit?.frozen && (manualEdit.stale ? " ⚠" : " 🔒")}
        </button>
        <button className="primary" onClick={() => setDialog("export")} disabled={!project}>
          📤 エクスポート / 入稿
        </button>
        <span className="spacer" />
        {project && (
          <input className="pname" value={project.name}
                 onChange={(e) => setProject({ ...project, name: e.target.value })}
                 onBlur={(e) => api.putMeta({ name: e.target.value }).catch(() => {})} />
        )}
        {project?.path && <span className="path" title={project.path}>{project.path}</span>}
        <button onClick={() => setDialog("settings")}>⚙ 設定</button>
      </div>

      <div className="main">
        <div className="panel">
          {project && (
            <ParamPanel schema={project.schema} params={params} onChange={onParamChange}
                        onHover={setHoverKey} regionKeys={regionKeys}
                        reference={project.reference}
                        onPickReference={pickReference}
                        onResetReference={() => setReference(null)} />
          )}
        </div>
        <div className="viewer">
          {project && (
            <Viewer3D modelVersion={modelVersion} highlight={highlight}
                      srcOverride={viewDerived && manualEdit?.derived
                        ? `/api/manual/model.stl?t=${manualEdit.derived.imported_at}`
                        : null}
                      onBusy={setModelBusy} />
          )}
          <div className="badge">
            {project
              ? (viewDerived ? "外部編集済みモデル（凍結時の形状ベース）"
                  : `${project.component_label} — ドラッグで回転 / ホイールで拡大縮小`) +
                (modelBusy ? "　⏳ 形状を再生成中…" : "")
              : "プロジェクトを作成してください"}
          </div>
          {manualEdit?.derived && (
            <div className="view-tabs">
              <button className={viewDerived ? "" : "active"}
                      onClick={() => setViewDerived(false)}>設計形状</button>
              <button className={viewDerived ? "active" : ""}
                      onClick={() => setViewDerived(true)}>
                編集済み{manualEdit.stale ? " ⚠旧" : ""}
              </button>
            </div>
          )}
          {highlight && !viewDerived && (
            <div className="badge region-badge">
              🟠 変更部位: {highlight.label}
            </div>
          )}
        </div>
        <div className="panel right">
          {sim && (
            <SimPanel sim={sim} paramsKey={JSON.stringify(params)}
                      onGoalSeek={() => setDialog("goalseek")} />
          )}
        </div>
      </div>

      {dialog === "new" && (
        <NewProjectDialog onCreated={loadProject}
                          onClose={() => setDialog(null)}
                          allowClose={project !== null} />
      )}
      {dialog === "goalseek" && sim?.kind === "mouthpiece" && project && (
        <GoalSeekDialog tier2={sim.tier2} schema={project.schema}
                        onApply={applyProposal} onClose={() => setDialog(null)} />
      )}
      {dialog === "export" && <ExportDialog onClose={() => setDialog(null)} />}
      {dialog === "settings" && <SettingsDialog onClose={() => setDialog(null)} />}
      {dialog === "manual" && manualEdit && (
        <ManualEditDialog manualEdit={manualEdit}
                          onChanged={refreshManualEdit}
                          onClose={() => setDialog(null)} />
      )}
      {error && <div className="err-toast">{error}</div>}
      {staleWarn && (
        <div className="err-toast warn-toast">
          ⚠ 凍結後にパラメータを変更しました。登録済みの編集済みモデルは古い形状になります
          （入稿には使用されません）。「🛠 外部編集」から再凍結してやり直してください。
        </div>
      )}
    </>
  );
}
