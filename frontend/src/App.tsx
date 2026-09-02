import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api, type Dimension, type ManualEdit, type ProjectData, type Region,
  type SetPlacement, type Simulation,
} from "./api";
import type { ExtraPart } from "./components/Viewer3D";
import ParamPanel from "./components/ParamPanel";
import SetPanel from "./components/SetPanel";
import SectionEditor from "./components/SectionEditor";
import SimPanel from "./components/SimPanel";
import Viewer3D from "./components/Viewer3D";
import {
  ExportDialog, GoalSeekDialog, NewProjectDialog, SettingsDialog,
} from "./components/Dialogs";
import { ManualEditDialog } from "./components/ManualEdit";
import { SurveyDialog } from "./components/SurveyPanel";
import { usePathPicker } from "./pathPicker";

type DialogKind = null | "new" | "goalseek" | "export" | "settings" | "manual" | "survey";

/** 合わせ表示で他の部品に着ける色。**部品名では引かない** —— どの部品が
 *  セットに入るかは楽器の事情（descriptor の `sets`）なので、UI は並び順で配る。 */
const PART_COLORS = [0xd8b48c, 0x9fd8a8, 0xd89fb4, 0xc0b4e0];

export default function App() {
  const [project, setProject] = useState<ProjectData | null>(null);
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [sim, setSim] = useState<Simulation | null>(null);
  const [modelVersion, setModelVersion] = useState(0);
  const [modelBusy, setModelBusy] = useState(false);
  // 参照マウスピースの重ね表示。既定オフ・UI 状態（プロジェクトには保存しない）
  const [showRef, setShowRef] = useState(false);
  const [refBusy, setRefBusy] = useState(false);
  // セットの合わせ表示。**既定オフ** —— 3 部品ぶん作り直すので、マウスピースを
  // 触ると 5.6〜6.2 秒 ＋ リガチャー 1.3 秒 ＋ リードを払うことになる。
  const [showSet, setShowSet] = useState(false);
  const [placement, setPlacement] = useState<SetPlacement | null>(null);
  // 寸法の図示。既定オフ・UI 状態で、**3D と断面が同じ 1 個を共有する**
  // （ビューを行き来しても設定が残る）。プロジェクトには保存しない。
  const [showDims, setShowDims] = useState(false);
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [dialog, setDialog] = useState<DialogKind>("new");
  const [error, setError] = useState("");
  const [regions, setRegions] = useState<Record<string, Region>>({});
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [manualEdit, setManualEdit] = useState<ManualEdit | null>(null);
  const [viewDerived, setViewDerived] = useState(false);
  const [staleWarn, setStaleWarn] = useState(false);
  // 旧プロジェクトのパラメータ変換報告（サーバが `notices` で返す）
  const [notices, setNotices] = useState<string[]>([]);
  // このページがサーバの配っているアプリより古いか（下の useEffect を参照）
  const [staleApp, setStaleApp] = useState(false);
  const [viewMode, setViewMode] = useState<"3d" | "section">("3d");

  const [hasSection, setHasSection] = useState(false);
  // ドラッグ中の未確定値。断面ハンドルを掴んでいる間だけ非 null になる。
  // 左のパラメータ欄はこれを重ねて表示するので、確定（PUT）を待たずに数値が
  // 追随する。非 null の間は 3D を作り直さない（1回のビルドが数秒かかるので、
  // ドラッグ中に走らせると GIL を奪われて断面まで固まる）。
  const [preview, setPreview] = useState<Record<string, number> | null>(null);

  const pickPath = usePathPicker();

  const paramTimer = useRef<number>(0);
  const modelTimer = useRef<number>(0);
  const previewRef = useRef<Record<string, number> | null>(null);
  const pendingParams = useRef<Record<string, unknown>>({});
  const manualEditRef = useRef<ManualEdit | null>(null);
  useEffect(() => { manualEditRef.current = manualEdit; }, [manualEdit]);

  useEffect(() => {
    // 起動時: サーバに既存セッションがあれば復元、なければ新規ダイアログのまま
    api.getProject().then((p) => {
      setProject(p); setParams(p.params); setSim(p.simulation);
      setManualEdit(p.manual_edit);
      // 変換報告はサーバ側に残っている（利用者が値を触るまで消えない）。ここで
      // 拾わないと、旧プロジェクトを開いた後に**再読み込みしただけで報告が消える**。
      setNotices(p.notices ?? []);
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
    if (notices.length === 0) return;
    const t = setTimeout(() => setNotices([]), 12000);
    return () => clearTimeout(t);
  }, [notices]);

  useEffect(() => {
    // 影響領域は形状パラメータに依存 → モデル更新のたびに再取得
    if (!project) return;
    api.regions().then(setRegions).catch(() => {});
    // 寸法も同じ周期で取り直す（断面はドラッグ中も追従させたいので、そちらは
    // `/api/section` の応答に載ってくるぶんを使う。定義はサーバ側で同じ 1 か所）。
    api.dimensions().then(setDimensions).catch(() => setDimensions([]));
  }, [modelVersion, project]);

  useEffect(() => {
    // 合わせ表示の配置。形が変われば置き場所（テーブルの傾きなど）も変わる。
    if (!project?.set) { setPlacement(null); return; }
    api.setPlacement().then(setPlacement).catch(() => setPlacement(null));
  }, [modelVersion, project]);

  useEffect(() => {
    // 断面編集を持つコンポーネントかはサーバに聞く（404 なら持たない）。
    // UI に「マウスピースだけ」という楽器固有の知識を置かないため。
    if (!project) { setHasSection(false); return; }
    api.section()
      .then(() => setHasSection(true))
      .catch(() => { setHasSection(false); setViewMode("3d"); });
  }, [project]);

  useEffect(() => {
    // **このページが古くないか。** 殻は `no-store` で配っているので再読み込み
    // すれば必ず最新になるが、開きっぱなしのタブはそれでは入れ替わらない。
    // 古いまま動くと**エラーにならず、それらしく組み上がった絵が出る**ので
    // 気付けない（2026-09-03: フロントが `flip_z` を落とし、セット表示で
    // リードがマウスピースの反対側に付いて見えた）。だから明示的に出す。
    //
    // 突き合わせるのは**実際に読み込んだスクリプトの名前**。開発サーバでは
    // `/assets/` 配下ではないので null になり、何も言わない。
    const el = document.querySelector<HTMLScriptElement>(
      'script[type="module"][src*="/assets/"]');
    const mine = el?.src.split("/").pop() ?? null;
    if (!mine) return;
    api.capabilities()
      .then((c) => setStaleApp(!!c.asset && c.asset !== mine))
      .catch(() => {});
  }, []);

  const regionKeys = useMemo(() => new Set(Object.keys(regions)), [regions]);
  const highlight = hoverKey ? regions[hoverKey] ?? null : null;

  // 重ねられるかはコンポーネントが宣言する（`reference.overlay`）。取込モデルの
  // 表示中は重ねない —— 外部モデルは別の整列で入っているので基準が違う。
  const canOverlay = !!project?.reference?.overlay && !viewDerived;
  // 合わせ表示に出せる部品があるかもサーバが決める（`assembly_placement`）。
  const canSetView = !!project?.set && (placement?.parts.length ?? 0) > 0
    && !viewDerived;

  // 一緒に描く部品。**セット表示が優先** —— そちらはマウスピースを実体で
  // 出すので、参照の重ねを足しても同じ形が二重になるだけ。
  const extras = useMemo<ExtraPart[]>(() => {
    if (canSetView && showSet) {
      return placement!.parts.map((p, i) => ({
        id: p.component_id,
        src: `/api/set/model.stl?member=${p.component_id}&v=${p.hash}`,
        origin: p.origin, rotateXDeg: p.rotate_x_deg, flipZ: p.flip_z,
        color: PART_COLORS[i % PART_COLORS.length], opacity: 0.6,
      }));
    }
    if (canOverlay && showRef) {
      return [{ id: "ref", src: `/api/ref/model.stl?v=${project!.reference!.hash}`,
                color: 0xa8c0d8, opacity: 0.25 }];
    }
    return [];
  }, [canSetView, showSet, placement, canOverlay, showRef, project]);

  // 寸法を持つかもサーバの答えで決める（UI に「どの部品が持つか」を書かない）。
  // 取込モデルの表示中は出さない —— 外部モデルは別の整列で入っているので、
  // 設計形状の寸法を重ねる根拠が無い（重ね表示と同じ判断）。
  const canDims = dimensions.length > 0 && !viewDerived;
  const shownDims = canDims && showDims ? dimensions : null;

  // 右上のタブは段で重ねる。**段の番号は数えて出す** —— 決め打ちにすると
  // 段が 3 つになった瞬間に重なる（`.view-tabs` / `.second` / `.third`）。
  const tabRowClass = (i: number) =>
    "view-tabs" + (i === 1 ? " second" : i === 2 ? " third" : "");
  const derivedRow = hasSection ? 1 : 0;
  const overlayRow = derivedRow + (manualEdit?.derived && viewMode === "3d" ? 1 : 0);

  // サーバが返したプロジェクト状態を画面へ載せる。**部品切替も新規/開くも
  // 同じ経路**を通す（切替だけ別に書くと、片方にしか無い更新が必ず出る）。
  const applyProject = useCallback((p: ProjectData) => {
    setProject(p); setParams(p.params); setSim(p.simulation);
    setManualEdit(p.manual_edit);
    setNotices(p.notices ?? []);
    setViewDerived(false);
    setShowRef(false);          // 部品が変われば重ねの意味も変わる
    setPreview(null);
    setModelVersion((v) => v + 1);
  }, []);

  const loadProject = useCallback(async () => {
    applyProject(await api.getProject());
    setDialog(null);
  }, [applyProject]);

  // セットの部品操作。**失敗しても画面の状態は動かさない**（サーバが弾いた
  // 時点で何も変わっていないので、エラーだけ出せばよい）。
  const runSetAction = useCallback(async (fn: () => Promise<ProjectData>) => {
    try { applyProject(await fn()); }
    catch (e) { setError(String((e as Error).message)); }
  }, [applyProject]);

  // 採寸ダイアログの操作後: パラメータ・シミュ・形状まで更新（ダイアログは開いたまま）
  const onSurveyApplied = useCallback((p: ProjectData) => {
    setProject(p); setParams(p.params); setSim(p.simulation);
    setManualEdit(p.manual_edit);
    setViewDerived(false);
    setModelVersion((v) => v + 1);
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
        setSim(r.simulation);
        // サーバ側でクランプされた値だけ拾い直す。丸ごと入れ替えると、値が
        // 同じでもオブジェクトが変わって断面が無駄に取り直される。
        setParams((prev) => {
          const diff = Object.entries(r.params)
            .filter(([k, v]) => prev[k] !== v);
          return diff.length ? { ...prev, ...Object.fromEntries(diff) } : prev;
        });
        const prev = manualEditRef.current;
        if (prev && r.stale && !prev.stale) setStaleWarn(true);  // 陳腐化した瞬間に警告
        if (prev && prev.stale !== r.stale) setManualEdit({ ...prev, stale: r.stale });
      } catch (e) {
        setError(String((e as Error).message));
        // 値の組が成立せずサーバが弾いた場合、サーバ側は前の値のまま。楽観更新した
        // ぶんを**送ったキーだけ**戻す。戻さないと画面の値とサーバの値が食い違い、
        // 断面リクエスト（画面の値をクエリで渡す）が同じ理由で落ち続ける。
        try {
          const p = await api.getProject();
          setParams((prev) => ({
            ...prev,
            ...Object.fromEntries(Object.keys(payload).map((k) => [k, p.params[k]])),
          }));
        } catch { /* 取り直せないときは楽観値のまま。次の操作で復帰する */ }
      }
    }, 250);
    // 形状再生成のデバウンスは PUT と**並行**に数える。await の後ろに置くと
    // 「250ms + PUT の往復 + 500ms」が直列に積算して、連続操作のたびに伸びる。
    window.clearTimeout(modelTimer.current);
    modelTimer.current = window.setTimeout(() => {
      if (previewRef.current) return;   // ドラッグ中は作り直さない
      setModelVersion((v) => v + 1);
    }, 750);
  }, []);

  const onParamChange = useCallback((key: string, value: unknown) => {
    setParams((prev) => ({ ...prev, [key]: value }));  // 楽観更新
    pushParams({ [key]: value });
  }, [pushParams]);

  // 複数キーをまとめて確定する。断面ハンドルは 1 本で 2 つのパラメータを書くことが
  // あり（`SectionHandle.also`）、ゴールシークの提案も同じ形なので経路を共有する。
  const applyParams = useCallback((updates: Record<string, number>) => {
    setParams((prev) => ({ ...prev, ...updates }));    // 楽観更新
    pushParams(updates);
  }, [pushParams]);

  // 断面ハンドルのドラッグ中。値は画面にだけ反映し、サーバへは送らない。
  const onPreview = useCallback((updates: Record<string, number> | null) => {
    previewRef.current = updates;
    setPreview(updates);
  }, []);

  // 表示に使う値。ドラッグ中は未確定値を重ねる（確定すると preview が消えて
  // params 側に同じ値が入っているので、切り替わりで数値が飛ばない）。
  const shownParams = useMemo(
    () => (preview ? { ...params, ...preview } : params), [params, preview]);

  const saveProject = useCallback(async (saveAs: boolean) => {
    if (!project) return;
    let path = project.path;
    if (saveAs || !path) {
      const picked = await pickPath("save", `${project.name}.wproj`);
      if (!picked) return;
      path = picked;
    }
    try {
      const res = await api.save(path);
      setProject({ ...project, path: res.path });
    } catch (e) { setError(String((e as Error).message)); }
  }, [project, pickPath]);

  // 参照マウスピースの差替え（リード/リガチャーのみ）。寸法が変わるので形状も作り直す
  const setReference = useCallback(async (path: string | null) => {
    if (!project) return;
    try {
      const p = await api.setReference(
        project.reference?.component_id ?? "mouthpiece", path);
      setProject(p); setParams(p.params); setSim(p.simulation);
      // 参照が変われば形状も凍結との関係も変わる（陳腐化バッジの更新に必要）
      setManualEdit(p.manual_edit);
      setViewDerived(false);
      setModelVersion((v) => v + 1);
    } catch (e) { setError(String((e as Error).message)); }
  }, [project]);

  const pickReference = useCallback(async () => {
    const path = await pickPath("open");
    if (path) setReference(path);
  }, [setReference, pickPath]);

  const importMember = useCallback(async () => {
    const path = await pickPath("open");
    if (path) runSetAction(() => api.importMember(path));
  }, [pickPath, runSetAction]);

  const exportMember = useCallback(async () => {
    if (!project?.set) return;
    const cid = project.set.active;
    const label = project.set.members.find((m) => m.component_id === cid)?.name
      ?? project.component_label;
    const path = await pickPath("save", `${label}.wproj`);
    if (!path) return;
    try { await api.exportMember(cid, path); }
    catch (e) { setError(String((e as Error).message)); }
  }, [project, pickPath]);

  return (
    <>
      <div className="toolbar">
        <span className="logo">🎷 SaxSketch</span>
        <button onClick={() => setDialog("new")}>新規 / 開く</button>
        <button onClick={() => saveProject(false)} disabled={!project}>保存</button>
        <button onClick={() => saveProject(true)} disabled={!project}>名前を付けて保存</button>
        <button onClick={() => setDialog("survey")} disabled={!project}>
          📐 採寸
          {project?.survey?.has_checkpoint && " ✓"}
        </button>
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
          {project?.set && (
            <SetPanel info={project.set}
                      onSelect={(cid) => runSetAction(() => api.setActive(cid))}
                      onAdd={(cid) => runSetAction(() => api.addMember(cid))}
                      onRemove={(cid) => runSetAction(() => api.removeMember(cid))}
                      onImport={importMember}
                      onExport={exportMember} />
          )}
          {project && (
            <ParamPanel schema={project.schema} params={shownParams} onChange={onParamChange}
                        onHover={setHoverKey} regionKeys={regionKeys}
                        reference={project.reference}
                        onPickReference={pickReference}
                        onResetReference={() => setReference(null)} />
          )}
        </div>
        <div className="viewer">
          {/* 3D は常にマウントしたままにする（アンマウントするとカメラ位置と
              読み込み済みメッシュを毎回捨てることになる）。ResizeObserver が
              あるので表示に戻したときに正しくリサイズされる。 */}
          {project && (
            <div className="view-pane"
                 style={{ display: viewMode === "3d" ? "block" : "none" }}>
              <Viewer3D modelVersion={modelVersion} highlight={highlight}
                        srcOverride={viewDerived && manualEdit?.derived
                          ? `/api/manual/model.stl?t=${manualEdit.derived.imported_at}`
                          : null}
                        extras={extras}
                        dimensions={shownDims} hoverKey={hoverKey}
                        onBusy={setModelBusy} onOverlayBusy={setRefBusy} />
            </div>
          )}
          {project && viewMode === "section" && (
            <SectionEditor params={params} onChange={applyParams}
                           onPreview={onPreview} modelBusy={modelBusy}
                           showDims={showDims} hoverKey={hoverKey}
                           onToggleDims={() => setShowDims((v) => !v)} />
          )}
          <div className="badge">
            {project
              ? (viewMode === "section"
                  ? `${project.component_label} — 丸ポチをドラッグ（タブでバッフル / 外形を切替）`
                  : viewDerived
                    ? (manualEdit?.derived?.kind === "external"
                        ? "外部取込モデル（整列後の形状）"
                        : "外部編集済みモデル（凍結時の形状ベース）")
                    : `${project.component_label} — ドラッグで回転 / ホイールで拡大縮小`) +
                (modelBusy && viewMode === "3d" ? "　⏳ 形状を再生成中…" : "") +
                (refBusy && viewMode === "3d"
                  ? (showSet ? "　⏳ 他の部品を生成中…" : "　⏳ 参照を生成中…") : "")
              : "プロジェクトを作成してください"}
          </div>
          {project && hasSection && (
            <div className="view-tabs">
              <button className={viewMode === "3d" ? "active" : ""}
                      onClick={() => setViewMode("3d")}>3D</button>
              <button className={viewMode === "section" ? "active" : ""}
                      onClick={() => setViewMode("section")}>断面</button>
            </div>
          )}
          {manualEdit?.derived && viewMode === "3d" && (
            <div className={tabRowClass(derivedRow)}>
              <button className={viewDerived ? "" : "active"}
                      onClick={() => setViewDerived(false)}>設計形状</button>
              <button className={viewDerived ? "active" : ""}
                      onClick={() => setViewDerived(true)}>
                {manualEdit.derived.kind === "external" ? "取込モデル" : "編集済み"}
                {manualEdit.derived.kind !== "external" && manualEdit.stale ? " ⚠旧" : ""}
              </button>
            </div>
          )}
          {(canOverlay || canDims || canSetView) && viewMode === "3d" && (
            <div className={tabRowClass(overlayRow)}>
              {canSetView && (
                <button className={showSet ? "active" : ""}
                        onClick={() => setShowSet((v) => !v)}
                        title="セットの他の部品を組んだ位置に重ねる">
                  🧩 セット
                </button>
              )}
              {canOverlay && !showSet && (
                <button className={showRef ? "active" : ""}
                        onClick={() => setShowRef((v) => !v)}
                        title="参照マウスピースを半透明で重ねる">
                  🫥 参照MP
                </button>
              )}
              {canDims && (
                <button className={showDims ? "active" : ""}
                        onClick={() => setShowDims((v) => !v)}
                        title="パラメータの寸法を図示する">
                  📏 寸法
                </button>
              )}
            </div>
          )}
          {highlight && !viewDerived && viewMode === "3d" && (
            <div className="badge region-badge">
              🟠 変更部位: {highlight.label}
            </div>
          )}
        </div>
        <div className="panel right">
          {sim && (
            <SimPanel sim={sim} setCard={project?.set_card}
                      paramsKey={JSON.stringify(shownParams)}
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
                        onApply={applyParams} onClose={() => setDialog(null)} />
      )}
      {dialog === "export" && (
        <ExportDialog onClose={() => setDialog(null)}
                      setInfo={project?.set?.is_set ? project.set : null} />
      )}
      {dialog === "settings" && <SettingsDialog onClose={() => setDialog(null)} />}
      {dialog === "manual" && manualEdit && (
        <ManualEditDialog manualEdit={manualEdit}
                          onChanged={refreshManualEdit}
                          onClose={() => setDialog(null)} />
      )}
      {dialog === "survey" && project && (
        <SurveyDialog survey={project.survey}
                      onApplied={onSurveyApplied}
                      onClose={() => setDialog(null)} />
      )}
      {staleApp && (
        <div className="err-toast warn-toast">
          ⚠ このページは古いアプリのまま動いています。<b>再読み込み</b>してください
          （Ctrl+Shift+R）。3D の表示が実際の設計と食い違うことがあります。
        </div>
      )}
      {error && <div className="err-toast">{error}</div>}
      {staleWarn && (
        <div className="err-toast warn-toast">
          ⚠ 凍結後にパラメータを変更しました。登録済みの編集済みモデルは古い形状になります
          （入稿には使用されません）。「🛠 外部編集」から再凍結してやり直してください。
        </div>
      )}
      {notices.length > 0 && !staleWarn && (
        <div className="err-toast warn-toast">
          ⚠ 保存時から変わったパラメータを変換しました:
          {notices.map((n, i) => <div key={i}>・{n}</div>)}
        </div>
      )}
    </>
  );
}
