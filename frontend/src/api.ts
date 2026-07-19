// SaxSketch API クライアント

export interface Choice { value: string; label: string }
export interface ParamSpec {
  key: string; label: string; category: string; type: string; unit: string;
  default: unknown; min: number | null; max: number | null; step: number | null;
  choices: Choice[]; effect: string; advanced: boolean;
}
export interface Tier1 {
  total_cc: number; effective_cc: number; target_cc: number;
  deviation_cents: number; status: string; advice: string; note: string;
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
export interface Simulation {
  tier1: Tier1; tier2: Tier2; harmonics: Harmonics;
  sensitivity: { table: Record<string, unknown>; suggestions: Record<string, Suggestion> };
}
export interface ProjectData {
  name: string; notes: string; path: string | null;
  instrument_id: string; template_id: string; component_id: string;
  component_label: string;
  params: Record<string, unknown>; schema: ParamSpec[]; simulation: Simulation;
  manual_edit: ManualEdit;
  /** 参照コンポーネント（リード/リガチャーのみ非 null） */
  reference: ReferenceInfo | null;
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
export interface ManualEdit {
  frozen: { frozen_at: string; export_dir: string | null;
            solid_volume_cc: number | null } | null;
  derived: { imported_at: string; source_file: string;
             quality: MeshQuality } | null;
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
  dialog: (mode: string, suggested = "") =>
    req<{ path: string | null }>("/api/dialog", json({ mode, suggested })),
  regions: () => req<Record<string, Region>>("/api/model/regions"),
  manualUnfreeze: () => req<ManualEdit>("/api/manual/unfreeze", json({})),
  manualImport: (path: string) =>
    req<ImportAnalysis>("/api/manual/import", json({ path })),
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
