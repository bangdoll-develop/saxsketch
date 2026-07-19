import { useState } from "react";
import {
  api, type ImportAnalysis, type ManualEdit, type ParamEstimate,
} from "../api";
import { Backdrop } from "./Dialogs";

const VERDICT_COLOR: Record<string, string> = {
  "一致": "var(--accent2)",
  "変化なし": "var(--accent2)",
  "軽微": "var(--warn)",
  "乖離": "var(--err)",
  "変化あり": "var(--err)",
  "測定不能": "var(--muted)",
  "判定不可": "var(--muted)",
};

function Verdict({ v }: { v: string }) {
  return <span style={{ color: VERDICT_COLOR[v] ?? "var(--text)", fontWeight: 600 }}>{v}</span>;
}

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleString("ja-JP"); } catch { return iso; }
}

function ParamTable({ rows }: { rows: ParamEstimate[] }) {
  const measured = rows.filter((r) => r.estimated !== null);
  const unmeasured = rows.filter((r) => r.estimated === null);
  const [showUnmeasured, setShowUnmeasured] = useState(false);
  return (
    <>
      <table>
        <thead>
          <tr><th>パラメータ</th><th>凍結値</th><th>実測(逆算)</th><th>Δ</th>
            <th>判定</th><th>測定方法</th></tr>
        </thead>
        <tbody>
          {measured.map((r) => (
            <tr key={r.key}>
              <td>{r.label}</td>
              <td>{r.frozen}{r.unit}</td>
              <td>{r.estimated}{r.unit}</td>
              <td style={{ color: Math.abs(r.delta ?? 0) > 1e-6 ? "var(--warn)" : undefined }}>
                {r.delta !== null && r.delta >= 0 ? "+" : ""}{r.delta}
              </td>
              <td><Verdict v={r.verdict} /></td>
              <td style={{ color: "var(--muted)", fontSize: 11 }}>{r.method}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="adv-toggle" style={{ padding: "6px 0" }}
           onClick={() => setShowUnmeasured(!showUnmeasured)}>
        {showUnmeasured ? "▾" : "▸"} 測定不能なパラメータ（{unmeasured.length}件）
      </div>
      {showUnmeasured && (
        <table>
          <tbody>
            {unmeasured.map((r) => (
              <tr key={r.key}>
                <td>{r.label}</td>
                <td style={{ color: "var(--muted)", fontSize: 11 }}>{r.method}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Report({ rep }: { rep: ImportAnalysis }) {
  return (
    <div style={{ marginTop: 12 }}>
      {rep.warnings.map((w, i) => (
        <div key={i} style={{ color: "var(--err)", margin: "4px 0", lineHeight: 1.5 }}>{w}</div>
      ))}
      <div className="drow" style={{ flexWrap: "wrap" }}>
        <span>水密: <Verdict v={rep.quality.watertight ? "一致" : "乖離"} />
          {rep.quality.watertight ? " OK" : " NG"}</span>
        <span>面数: {rep.quality.faces.toLocaleString()}</span>
        {rep.volume && (
          <span>体積: {rep.volume.frozen_cc} → {rep.volume.edited_cc} cc
            （{rep.volume.delta_pct >= 0 ? "+" : ""}{rep.volume.delta_pct}%）</span>
        )}
      </div>
      <h3 style={{ fontSize: 13, color: "var(--accent)", margin: "12px 0 6px" }}>
        パラメータ逆算（凍結値との比較）
      </h3>
      <ParamTable rows={rep.params} />
      <h3 style={{ fontSize: 13, color: "var(--accent)", margin: "12px 0 6px" }}>
        領域別の形状偏差（分解能 約±0.15mm）
      </h3>
      <table>
        <thead><tr><th>部位</th><th>最大偏差</th><th>判定</th></tr></thead>
        <tbody>
          {rep.regions.map((z, i) => (
            <tr key={i}>
              <td>{z.label}</td>
              <td>{z.max_dev_mm !== null ? `${z.max_dev_mm} mm` : "-"}</td>
              <td><Verdict v={z.verdict} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ManualEditDialog({ manualEdit, onChanged, onClose }: {
  manualEdit: ManualEdit;
  onChanged: () => void;   // 凍結/取込/破棄でプロジェクト状態が変わった
  onClose: () => void;
}) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [report, setReport] = useState<ImportAnalysis | null>(null);
  const [freezeDir, setFreezeDir] = useState<string | null>(null);

  const me = manualEdit;
  const stepPath = freezeDir ? `${freezeDir}\\model.step`
    : me.frozen?.export_dir ? `${me.frozen.export_dir}\\model.step` : null;

  const openInFreecad = async (path: string) => {
    try { await api.toolOpen("freecad", path); return true; }
    catch (e) {
      setNote(`FreeCADの自動起動に失敗: ${(e as Error).message}` +
               "　⚙設定でFreeCADのパスを登録すると次回から自動起動します。");
      return false;
    }
  };

  const freeze = async () => {
    setBusy("凍結してSTEP/STLをエクスポート中…"); setErr(""); setNote("");
    try {
      const r = await api.export_({
        formats: ["step", "stl"], make_package: false, freeze: true,
        use_derived: false,
      });
      setFreezeDir(r.out_dir);
      onChanged();
      setBusy("FreeCADを起動中…");
      const stepFile = r.files["model.step"] ?? `${r.out_dir}\\model.step`;
      if (await openInFreecad(stepFile)) {
        setNote("✓ FreeCADでmodel.stepを開きました。編集後は上書き保存してください。");
      }
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  const importModel = async () => {
    setErr(""); setReport(null);
    const { path } = await api.dialog("open_model", freezeDir ?? me.frozen?.export_dir ?? "");
    if (!path) return;
    setBusy("解析中…（形状比較とパラメータ逆算。十数秒かかります）");
    try { setReport(await api.manualImport(path)); }
    catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(""); }
  };

  const commit = async () => {
    try { await api.manualCommit(); setReport(null); onChanged(); }
    catch (e) { setErr(String((e as Error).message)); }
  };

  const discard = async () => {
    try { await api.manualDiscard(); setReport(null); onChanged(); }
    catch (e) { setErr(String((e as Error).message)); }
  };

  const unfreeze = async () => {
    try { await api.manualUnfreeze(); setReport(null); setFreezeDir(null); onChanged(); }
    catch (e) { setErr(String((e as Error).message)); }
  };

  return (
    <Backdrop onClose={onClose}>
      <h2>外部編集（FreeCAD / Blender 連携）</h2>

      {me.stale && (
        <div style={{ color: "var(--err)", marginBottom: 10, lineHeight: 1.6 }}>
          ⚠ 凍結後にパラメータが変更されています。編集済みモデルは古い形状です。
          再度「凍結してエクスポート」からやり直すか、パラメータを凍結時に戻してください。
        </div>
      )}

      {/* ステップ1: 凍結 */}
      <div className="simcard" style={{ margin: "8px 0" }}>
        <h3>① 設計を凍結して編集用にエクスポート</h3>
        {me.frozen ? (
          <div className="note">
            🔒 凍結中 — {fmtDate(me.frozen.frozen_at)}
            {me.frozen.solid_volume_cc && ` / 実体積 ${me.frozen.solid_volume_cc} cc`}
            {me.frozen.export_dir && <><br />出力先: {me.frozen.export_dir}</>}
          </div>
        ) : (
          <div className="note">
            パラメータ設計が完了したら凍結します。STEP（FreeCAD編集用）とSTLを出力し、
            現在のパラメータをスナップショットとして記録します。
          </div>
        )}
        <div className="actions" style={{ marginTop: 8 }}>
          {me.frozen && <button onClick={unfreeze}>凍結解除（派生モデルも破棄）</button>}
          {stepPath && (
            <button onClick={() => openInFreecad(stepPath)} disabled={!!busy}>
              🚀 FreeCADで開く
            </button>
          )}
          <button className="primary" onClick={freeze} disabled={!!busy}>
            {me.frozen ? "再凍結してエクスポート" : "🔒 凍結してエクスポート"}
          </button>
        </div>
        {freezeDir && (
          <div className="note" style={{ color: "var(--accent2)" }}>
            ✓ 出力完了: {freezeDir} — model.step を FreeCAD / Blender で編集してください。
            <b>テーブル・フェイシング面と内部空洞には触れないこと</b>（詳細は
            docs/manual-edit-workflow.md）。
          </div>
        )}
        {note && <div className="note" style={{ color: "var(--warn)" }}>{note}</div>}
      </div>

      {/* ステップ2: 取込 */}
      <div className="simcard" style={{ margin: "8px 0" }}>
        <h3>② 編集済みモデルを取込・検証</h3>
        {me.derived ? (
          <div className="note">
            📥 登録済み — {fmtDate(me.derived.imported_at)}<br />
            元ファイル: {me.derived.source_file}<br />
            水密: {me.derived.quality.watertight ? "OK" : "NG"} /
            体積 {me.derived.quality.volume_cc ?? "-"} cc
            — 以後のエクスポートはこのモデルのSTLを入稿に使います。
          </div>
        ) : (
          <div className="note">
            外部ツールで編集した STL / STEP / 3MF を取り込むと、水密検査・
            凍結形状との領域別偏差・パラメータ逆算を自動実行します。
            （ファイル選択は凍結出力フォルダから始まります）
          </div>
        )}
        <div className="actions" style={{ marginTop: 8 }}>
          {me.derived && <button onClick={discard}>派生モデルを破棄</button>}
          <button className="primary" onClick={importModel}
                  disabled={!me.frozen || !!busy}>
            📥 編集済みモデルを取込…
          </button>
        </div>
        {!me.frozen && <div className="note">先に ① の凍結が必要です。</div>}
      </div>

      {busy && <div className="busy" style={{ margin: "8px 0" }}>⏳ {busy}</div>}
      {err && <div style={{ color: "var(--err)" }}>{err}</div>}

      {/* 解析レポート */}
      {report && (
        <div className="simcard" style={{ margin: "8px 0" }}>
          <h3>解析レポート</h3>
          <Report rep={report} />
          <div className="actions">
            <button onClick={() => setReport(null)}>破棄</button>
            <button className="primary" onClick={commit}>
              このモデルを登録（入稿に使用）
            </button>
          </div>
        </div>
      )}

      <div className="actions">
        <button onClick={onClose}>閉じる</button>
      </div>
    </Backdrop>
  );
}
