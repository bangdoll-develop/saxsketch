// SaxSketch API クライアント

export interface Choice { value: string; label: string }
export interface ParamSpec {
  key: string; label: string; category: string; type: string; unit: string;
  /** min/max は「勧める帯」。越えられない壁は hard_min/hard_max（null なら帯が壁）。 */
  default: unknown; min: number | null; max: number | null; step: number | null;
  choices: Choice[]; effect: string; advanced: boolean;
  /** geometry | manufacturing | convention | unclassified */
  limit_kind: string;
  /** 帯の出所。空なら「出所の記載なし」と出す（発明しない） */
  source: string;
  hard_min: number | null; hard_max: number | null;
}

/** 帯／壁で丸めた 1 項目。**黙ってクランプしないための経路**（既知 8 例目）。 */
export interface ParamAdjustment {
  key: string; label: string; unit: string;
  requested: number | string; applied: number | string;
  /** edge: min|max。at: 帯（band）と壁（wall）のどちらに当たったか */
  edge: string; at?: string; limit_kind: string; source: string; message: string;
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
  /** いまのパラメータについての注意。**空なら警告カードを出さない**。
   *  出所はサーバの `Component.warnings()` 1 か所で、`simulate()` の便に
   *  乗ってくる（＝スライダ 1 目盛ごとに更新される）。 */
  warnings?: string[];
  tier1: Tier1; tier2: Tier2; harmonics: Harmonics;
  sensitivity: { table: Record<string, unknown>; suggestions: Record<string, Suggestion> };
  /** 規格・実物との照合。リード/リガチャーの cards と同じ形式 */
  cards?: SimCard[];
}
export interface CardSimulation {
  kind: "reed" | "ligature" | "neck" | "body";
  cards: SimCard[];
  /** `MouthpieceSimulation.warnings` と同じ。持たない部品では空。 */
  warnings?: string[];
  /** インピーダンス曲線を出せるか。**UI に部品名を書かない**ため、
   *  「どの部品が音響を持つか」はサーバ（コンポーネント）が宣言する。 */
  has_impedance?: boolean;
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
  /** セット情報（単体プロジェクトでは null。UI は部品タブの有無をこれで決める） */
  set: SetInfo | null;
  /** 部品どうしでしか出せない量の判定。単体では null */
  set_card: SimCard | null;
  survey: SurveyState;
  /** 旧プロジェクトを開いたときのパラメータ変換報告（黙って値を変えないため） */
  notices?: string[];
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
/** セットの構成部品 1 行。`present=false` は「まだ足していない部品」 */
export interface SetMember {
  component_id: string; label: string; name: string | null;
  present: boolean; required: boolean; master: boolean;
}
export interface SetInfo {
  set_id: string | null; label: string;
  /** 実際に組になっているか。false = 単体だが部品を足せる状態 */
  is_set: boolean;
  active: string;
  members: SetMember[];
  /** まだ居ない部品のID（「＋追加」に出す） */
  addable: string[];
}
/** 合わせ表示の配置 1 部品ぶん。**編集中の部品を基準にした相対変換**で、
 *  `rotate_x_deg` → `origin` の順に適用する。 */
export interface PlacedPart {
  component_id: string; label: string;
  origin: [number, number, number]; rotate_x_deg: number;
  /** Z 軸まわり 180°（裏返し）を先に掛けるか。リードのように、載る相手の
   *  外向き法線と肉の向きが逆な部品で true になる */
  flip_z: boolean;
  hash: string;
}
export interface SetPlacement {
  active: string | null;
  parts: PlacedPart[];
  /** 置き場所を宣言していない部品の表示名（合わせ表示に出せない） */
  unplaced: string[];
}
export interface ReferenceInfo {
  component_id: string; label: string; source: string | null;
  /** セットの兄弟メンバーから束ねた参照か（true なら設計中の値に追従する） */
  live: boolean;
  dims: [string, string][];
  /** 参照の形をそのまま重ねられるか（座標系が一致するコンポーネントだけ true） */
  overlay: boolean;
  /** 参照の同一性。重ね表示のURLの `?v=`（サーバのキャッシュ鍵と同じ値） */
  hash: string | null;
}
export interface InstrumentSummary {
  id: string; label: string;
  templates: { id: string; label: string }[];
  components: { id: string; label: string; available: boolean }[];
  /** セットで組める構成（descriptor の sets）。無い楽器では空配列 */
  sets: {
    id: string; label: string;
    members: { component: string; label: string;
               required: boolean; master: boolean }[];
  }[];
}
export interface GoalSeekResult {
  proposal: Record<string, number>; current: Record<string, number>;
  predicted_metrics: Tier2; predicted_tier1: Tier1; residual: number; note: string;
}
export interface Region {
  z0: number; z1: number; side: "top" | "bottom" | "all"; label: string;
}
/** ハンドルが主パラメータと一緒に書く従属パラメータ。
 *  主と**同じ t**（span 上の位置）で線形に決まる。step を持たないのは、
 *  従属値が主から解いた値だから — 丸めると解が崩れる（サーバ側の注記を参照）。 */
export interface HandleLinked { key: string; min: number; max: number }
/** 断面エディタのドラッグハンドル。span はパラメータ min/max に対応する断面座標 */
export interface SectionHandle {
  key: string; label: string; axis: "z" | "y";
  z: number; y: number;
  value: number; min: number; max: number; span: [number, number];
  unit: string; step: number; active: boolean;
  /** どのタブで出すか。バッフルは拡大表示、外形は全体表示にしかない */
  group: "baffle" | "outer";
  also: HandleLinked[];
}
export interface SectionData {
  z_range: [number, number];
  curves: Record<string, [number, number][]>;
  handles: SectionHandle[];
  warnings: string[];
  baffle_type: string;
  title: string;
  /** 寸法。断面はドラッグ中もこれで追従する（3D は `/api/dimensions`） */
  dimensions: Dimension[];
}
/** パラメータの寸法線 1 本。座標はコンポーネント自身のモデル座標。
 *  `value` は **|b − a|**（サーバが両端から測る）ので、ラベルの数字と
 *  引かれる線の長さが食い違わない。`requested` はスライダの公称値で、
 *  step 1 目盛より大きく食い違うときだけ付く（＝黙ったクランプがそのまま出る）。 */
export interface Dimension {
  key: string; label: string; unit: string; value: number;
  a: [number, number, number]; b: [number, number, number];
  dir: [number, number, number]; level: number;
  requested?: number;
}
/** x=0 の断面へそのまま写せるか。**宣言ではなく座標から導く**（サーバ側の
 *  `dimension.in_section_plane` と同じ判定。両方に書くのは判定が 3 行で、
 *  往復を増やさずに描画側が決められるほうが速いから）。 */
export const inSectionPlane = (d: Dimension) =>
  Math.abs(d.a[0]) < 1e-9 && Math.abs(d.b[0]) < 1e-9 && Math.abs(d.dir[0]) < 1e-9;
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
  /** 何を出したか（"set" = 一式、"member" = 編集中の部品だけ） */
  scope?: "set" | "member";
  members?: string[];
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
  /** サーバがいま配っているアプリの世代（`index-XXXX.js`）。dist 無し（開発
   *  サーバ）なら null。自分が読み込んだスクリプト名と違えば、このページは古い。 */
  asset: string | null;
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
    req<{ params: Record<string, unknown>; simulation: Simulation; stale: boolean;
          adjustments: ParamAdjustment[] }>(
      "/api/project/params", { ...json({ params }), method: "PUT" }),
  putMeta: (b: object) => req("/api/project/meta", { ...json(b), method: "PUT" }),
  save: (path: string) => req<{ ok: boolean; path: string }>("/api/project/save", json({ path })),
  open: (path: string) => req<ProjectData>("/api/project/open", json({ path })),
  recent: () => req<string[]>("/api/recent"),
  setReference: (component: string, path: string | null) =>
    req<ProjectData>("/api/project/reference", json({ component, path })),
  setActive: (component_id: string) =>
    req<ProjectData>("/api/set/active", json({ component_id })),
  addMember: (component_id: string) =>
    req<ProjectData>("/api/set/member/add", json({ component_id })),
  removeMember: (component_id: string) =>
    req<ProjectData>("/api/set/member/remove", json({ component_id })),
  importMember: (path: string) =>
    req<ProjectData>("/api/set/member/import", json({ path })),
  exportMember: (component_id: string, path: string) =>
    req<{ ok: boolean; path: string }>(
      "/api/set/member/export", json({ component_id, path })),
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
  setPlacement: () => req<SetPlacement>("/api/set/placement"),
  regions: () => req<Record<string, Region>>("/api/model/regions"),
  dimensions: () => req<Dimension[]>("/api/dimensions"),
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
