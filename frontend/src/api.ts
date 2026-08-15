// SaxSketch API クライアント

export interface Choice { value: string; label: string }
export interface ParamSpec {
  key: string; label: string; category: string; type: string; unit: string;
  default: unknown; min: number | null; max: number | null; step: number | null;
  choices: Choice[]; effect: string; advanced: boolean;
}
export interface Tier1 {
  total_cc: number; effective_cc: number; target_cc: number;
  // deviation_cents は「いまの挿し込み量での」ズレ。判定そのものは in_tune_mm が
  // cork_range_mm に入るかで出ている（コーク挿入深さは寸法ではなくチューニング）。
  deviation_cents: number;
  in_tune_mm: number; cork_range_mm: [number, number];
  cents_per_mm: number; current_mm: number; tuning_method: string;
  status: string; advice: string; note: string;
}
export interface Tier2 {
  brightness: number; power: number; resistance: number; flexibility: number;
  edge: number; labels: Record<string, string>; note: string;
}
export interface Harmonics {
  amplitudes: number[]; breathiness: number; vibrato_hz: number;
  vibrato_depth: number; attack_sec: number; note: string;
}
export interface Suggestion {
  param: string; label: string; direction: string; per_step: number;
  step: number; unit: string;
}
/** 汎用シミュレーション カード（リード/リガチャー/ネック/管体） */
export interface SimCard {
  title: string; big: string | null; status: "ok" | "warn" | "bad";
  rows: [string, string][]; advice: string;
}
export interface MouthpieceSimulation {
  kind: "mouthpiece";
  tier1: Tier1; tier2: Tier2; harmonics: Harmonics;
  sensitivity: { table: Record<string, unknown>; suggestions: Record<string, Suggestion> };
  /** 規格・実物との照合。リード/リガチャーの cards と同じ形式 */
  cards?: SimCard[];
}
export interface CardSimulation {
  kind: "reed" | "ligature" | "neck" | "body";
  cards: SimCard[];
  /** リードのみ。音プレビュー（印象合成）用 */
  harmonics?: Harmonics;
}
export type Simulation = MouthpieceSimulation | CardSimulation;
export interface ProjectData {
  name: string; notes: string; path: string | null;
  instrument_id: string; template_id: string; component_id: string;
  component_label: string;
  params: Record<string, unknown>; schema: ParamSpec[]; simulation: Simulation;
  manual_edit: ManualEdit;
  /** 参照コンポーネント（リード/リガチャーのみ非 null） */
  reference: ReferenceInfo | null;
  survey: SurveyState;
}
/** 採寸ワークフロー（Phase 4-A） */
export interface SurveyField {
  key: string; label: string; unit: string;
  min?: number | null; max?: number | null; step?: number | null;
  current: number | null;
}
export interface SurveyState {
  targets: { params: SurveyField[]; size: SurveyField[] };
  measured: Record<string, number>;
  measured_size: Record<string, number>;
  has_checkpoint: boolean;
  card: SimCard | null;
  surveyed_at: string | null;
  note: string;
}
/** 外部3Dモデルからの採寸プレフィル（/api/survey/measure） */
export interface SurveyMeasure {
  measured: Record<string, number>;
  measured_size: Record<string, number>;
  confidence: Record<string, "high" | "med" | "low">;
  notes: string[];
  quality: { watertight: boolean; faces: number; volume_cc: number | null };
}
/** 外部（本アプリ非由来）モデルの読み込み結果（/api/external/load） */
export interface AlignInfo {
  elongation: number; axis_conf: string; shank_conf: string;
  length_mm: number; outer_radius_mm: number; warnings: string[];
}
export interface ExternalLoad {
  kind: "external";
  quality: MeshQuality;
  measured: Record<string, number>;
  measured_size: Record<string, number>;
  confidence: Record<string, "high" | "med" | "low">;
  notes: string[];
  align: AlignInfo;
}
export interface ReferenceInfo {
  component_id: string; label: string; source: string | null;
  dims: [string, string][];
}
export interface InstrumentSummary {
  id: string; label: string;
  templates: { id: string; label: string }[];
  components: { id: string; label: string; available: boolean }[];
}
export interface GoalSeekResult {
  proposal: Record<string, number>; current: Record<string, number>;
  predicted_metrics: Tier2; predicted_tier1: Tier1; residual: number; note: string;
}
export interface Region {
  z0: number; z1: number; side: "top" | "bottom" | "all"; label: string;
}
/** 断面エディタのドラッグハンドル。span はパラメータ min/max に対応する断面座標 */
export interface SectionHandle {
  key: string; label: string; axis: "z" | "y";
  z: number; y: number;
  value: number; min: number; max: number; span: [number, number];
  unit: string; step: number; active: boolean;
}
export interface SectionData {
  z_range: [number, number];
  curves: Record<string, [number, number][]>;
  handles: SectionHandle[];
  warnings: string[];
  baffle_type: string;
  title: string;
}
export interface ManualEdit {
  frozen: { frozen_at: string; export_dir: string | null;
            solid_volume_cc: number | null } | null;
  derived: { imported_at: string; source_file: string;
             quality: MeshQuality; kind?: "edited" | "external" } | null;
  stale: boolean;
}
export interface MeshQuality {
  watertight: boolean; winding_consistent: boolean; faces: number;
  volume_cc: number | null;
}
export interface ParamEstimate {
  key: string; label: string; unit: string;
  frozen: number | null; estimated: number | null; delta: number | null;
  verdict: string; method: string;
}
export interface ZoneDeviation {
  label: string; params: string[]; z0: number; z1: number; side: string;
  max_dev_mm: number | null; verdict: string;
}
export interface ImportAnalysis {
  quality: MeshQuality;
  volume: { frozen_cc: number; edited_cc: number; delta_pct: number } | null;
  regions: ZoneDeviation[];
  params: ParamEstimate[];
  warnings: string[];
}
export interface ImpedancePeak {
  freq: number; note: string; cents_vs_target: number;
}
export interface Impedance {
  engine: "openwind" | "tmm";
  freqs: number[]; z_db: number[];
  peaks: ImpedancePeak[];
  first_note: string; first_cents_vs_target: number | null;
  inharmonicity_cents: number | null; target_note: string; note: string;
}
export interface ExportResult {
  out_dir: string; files: Record<string, string>; package: string | null;
  mesh_quality: { watertight: boolean; faces: number; volume_cc: number | null } | null;
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* noop */ }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

export type DialogMode = "save" | "open" | "open_model" | "dir";
/** `reason` はフォールバックの分岐用。詳細は `saxsketch/server/filedialog.py`。
 *  `cancelled` は利用者の意思なので、UI は代わりの入力欄を出してはいけない。 */
export type DialogReason = "ok" | "cancelled" | "unavailable" | "timeout";
export interface DialogResult { path: string | null; reason: DialogReason }
/** この稼働環境で UI が使ってよい機能。`native_dialogs` が false なら
 *  OS のダイアログは利用者に見えない（リモート稼働など）ので手入力に落とす。 */
export interface Capabilities {
  native_dialogs: boolean;
  host: "wsl" | "windows" | "linux";
  export_root: string;
}

const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  instruments: () => req<InstrumentSummary[]>("/api/instruments"),
  newProject: (b: object) => req<ProjectData>("/api/project/new", json(b)),
  getProject: () => req<ProjectData>("/api/project"),
  putParams: (params: Record<string, unknown>) =>
    req<{ params: Record<string, unknown>; simulation: Simulation; stale: boolean }>(
      "/api/project/params", { ...json({ params }), method: "PUT" }),
  putMeta: (b: object) => req("/api/project/meta", { ...json(b), method: "PUT" }),
  save: (path: string) => req<{ ok: boolean; path: string }>("/api/project/save", json({ path })),
  open: (path: string) => req<ProjectData>("/api/project/open", json({ path })),
  recent: () => req<string[]>("/api/recent"),
  setReference: (component: string, path: string | null) =>
    req<ProjectData>("/api/project/reference", json({ component, path })),
  survey: () => req<SurveyState>("/api/survey"),
  surveyCommit: (b: { measured: Record<string, number>;
                      measured_size: Record<string, number>; note: string }) =>
    req<ProjectData>("/api/survey/commit", json(b)),
  surveyRevert: () => req<ProjectData>("/api/survey/revert", json({})),
  surveyClear: () => req<ProjectData>("/api/survey/clear", json({})),
  surveyMeasure: (path: string) =>
    req<SurveyMeasure>("/api/survey/measure", json({ path })),
  capabilities: () => req<Capabilities>("/api/capabilities"),
  dialog: (mode: DialogMode, suggested = "") =>
    req<DialogResult>("/api/dialog", json({ mode, suggested })),
  regions: () => req<Record<string, Region>>("/api/model/regions"),
  /** override を渡すと「もしこの値にしたら」の断面を返す（プロジェクトは変えない）。
   *  画面が持っているパラメータをそのまま渡せば、PUT の完了を待たずに常に
   *  「いま画面で見えている値」の断面が得られる。確定は putParams 経由で行う。 */
  section: (override?: Record<string, string | number>) => {
    const q = override
      ? "?" + new URLSearchParams(
          Object.entries(override).map(([k, v]) => [k, String(v)])).toString()
      : "";
    return req<SectionData>("/api/section" + q);
  },
  manualUnfreeze: () => req<ManualEdit>("/api/manual/unfreeze", json({})),
  manualImport: (path: string) =>
    req<ImportAnalysis>("/api/manual/import", json({ path })),
  externalLoad: (path: string) =>
    req<ExternalLoad>("/api/external/load", json({ path })),
  manualCommit: () => req<ManualEdit>("/api/manual/commit", json({})),
  manualDiscard: () => req<ManualEdit>("/api/manual/discard", json({})),
  goalSeek: (targets: Record<string, unknown>) =>
    req<GoalSeekResult>("/api/project/goalseek", json({ targets })),
  export_: (b: object) => req<ExportResult>("/api/export", json(b)),
  toolOpen: (tool: string, file: string) => req("/api/tools/open", json({ tool, file })),
  impedance: () => req<Impedance>("/api/acoustics/impedance"),
  soundWavUrl: (embouchure: string) =>
    `/api/acoustics/sound.wav?embouchure=${embouchure}`,
  scaleWavUrl: () => "/api/acoustics/scale.wav",
  settings: () => req<Record<string, unknown>>("/api/settings"),
  putSettings: (settings: object) =>
    req("/api/settings", { ...json({ settings }), method: "PUT" }),
};
