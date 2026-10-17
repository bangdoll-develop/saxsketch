// 英語の訳。**鍵は日本語そのもの**（`i18n.ts` の `t()` の引数）。
// 用語は `docs/glossary.md` から引く —— ここで新しい訳語を作らない。
//
// `t(変数)` で引くもの（`CONF_LABEL` / `KIND_LABEL` / `LABELS` / 音名 /
// サーバが返す判定語）も、鍵が日本語である点は同じ。抜けは
// `tests/test_i18n.py::test_the_frontend_has_english_for_every_message` が落とす。
const EN: Record<string, string> = {
  // ---- ツールバー / App
  "SaxSketch — 管楽器設計スタジオ": "SaxSketch — wind instrument design studio",
  "新規 / 開く": "New / Open",
  "保存": "Save",
  "名前を付けて保存": "Save as",
  "📐 採寸": "📐 Survey",
  "🛠 外部編集": "🛠 External edit",
  "📤 エクスポート / 入稿": "📤 Export / print package",
  "⚙ 設定": "⚙ Settings",
  "{part} — 丸ポチをドラッグ（タブでバッフル / 外形を切替）":
    "{part} — drag the dots (the tabs switch baffle / outline)",
  "外部取込モデル（整列後の形状）": "Imported model (after alignment)",
  "外部編集済みモデル（凍結時の形状ベース）":
    "Externally edited model (based on the frozen shape)",
  "{part} — ドラッグで回転 / ホイールで拡大縮小":
    "{part} — drag to rotate, wheel to zoom",
  "　⏳ 形状を再生成中…": "　⏳ rebuilding the shape…",
  "　⏳ 他の部品を生成中…": "　⏳ building the other parts…",
  "　⏳ 参照を生成中…": "　⏳ building the reference…",
  "プロジェクトを作成してください": "Create a project to start",
  "断面": "Section",
  "設計形状": "Designed shape",
  "取込モデル": "Imported model",
  "編集済み": "Edited",
  " ⚠旧": " ⚠old",
  "セットの他の部品を組んだ位置に重ねる":
    "Overlay the other parts of the set in their assembled positions",
  "🧩 セット": "🧩 Set",
  "参照マウスピースを半透明で重ねる": "Overlay the reference mouthpiece, semi-transparent",
  "🫥 参照MP": "🫥 Ref. MP",
  "パラメータの寸法を図示する": "Draw the parameter dimensions",
  "📏 寸法": "📏 Dimensions",
  "🟠 変更部位: ": "🟠 Affected region: ",
  "⚠ このページは古いアプリのまま動いています。": "⚠ This page is running an old build. ",
  "再読み込み": "Reload",
  "してください（Ctrl+Shift+R）。3D の表示が実際の設計と食い違うことがあります。":
    " it (Ctrl+Shift+R). The 3D view can disagree with the actual design.",
  "⚠ 凍結後にパラメータを変更しました。登録済みの編集済みモデルは古い形状になります（入稿には使用されません）。「🛠 外部編集」から再凍結してやり直してください。":
    "⚠ Parameters changed after the freeze. The registered edited model is now an old "
    + "shape (it will not be used for the print package). Re-freeze from “🛠 External edit”.",
  "⚠ 保存時から変わったパラメータを変換しました:":
    "⚠ Converted parameters that changed since the file was saved:",
  "⚠ 壁に当たったので値を丸めました:": "⚠ Values were rounded at a hard limit:",

  // ---- ダイアログ（新規）
  "サーバに接続できません": "Cannot reach the server",
  "新規プロジェクト": "New project",
  "楽器": "Instrument",
  "サイズテンプレート": "Size template",
  "作り方": "Build as",
  "セット（一式）": "A set",
  "単体": "A single part",
  "セット構成": "Set",
  "コンポーネント": "Component",
  "（任意・後から追加）": " (optional, can be added later)",
  "。土台は{master}で、下流の部品はその設計値に追従します。":
    ". The {master} is the master; the downstream parts follow its design values.",
  "先頭の部品": "first part",
  "キャンセル": "Cancel",
  "既存プロジェクトを開く…": "Open an existing project…",
  "作成": "Create",
  "最近使ったプロジェクト": "Recent projects",

  // ---- ゴールシーク
  "目標から逆算（ゴールシーク）": "Solve back from a target (goal seek)",
  "音程ニュートラルを維持": "Keep the pitch neutral",
  "閉じる": "Close",
  "計算中…": "Computing…",
  "逆算する": "Solve",
  "パラメータ": "Parameter",
  "現在": "Current",
  "提案": "Proposed",
  "予測: 明るさ {bright} / パワー {power} / チューニング位置 {pos}":
    "Predicted: brightness {bright} / power {power} / tuning position {pos}",
  "破棄": "Discard",
  "提案を適用": "Apply the proposal",

  // ---- エクスポート
  "エクスポート / 入稿データ生成": "Export / build the print package",
  "出力範囲": "Scope",
  "セット一式（": "The whole set (",
  "）": ")",
  "いま編集中の部品だけ": "Only the part being edited",
  "3Dモデル形式": "3D model formats",
  "出力先": "Output folder",
  "（既定: {dir}）": "(default: {dir})",
  "（既定の場所）": "(the default location)",
  "参照…": "Browse…",
  "部品ごとのフォルダに分かれ、仕様書と部品表は": "One folder per part; the spec sheet and the bill of materials come out as ",
  "1 式で 1 枚": "a single document for the whole set",
  "にまとまります。": ".",
  "仕様書(spec.html)・部品表(bom.csv)・入稿パッケージZIPも同時に生成されます。ZIPはオンライン3Dプリントサービス（JLC3DP / PCBWay / Shapeways 等）へそのままアップロードできます。":
    "A spec sheet (spec.html), a bill of materials (bom.csv) and a print-package ZIP are "
    + "produced at the same time. The ZIP can be uploaded as-is to an online 3D printing "
    + "service (JLC3DP, PCBWay, Shapeways and the like).",
  "生成中…（数十秒かかることがあります）": "Generating… (this can take tens of seconds)",
  "生成する": "Generate",
  "✓ 生成完了": "✓ Done",
  " — STL水密性: {ok} / 体積 {cc} cc": " — STL watertight: {ok} / volume {cc} cc",
  "OK": "OK",
  "要確認": "needs checking",
  "開く": "Open",
  "スライサーで開く": "Open in the slicer",
  "FreeCADで開く": "Open in FreeCAD",
  "フォルダを開く": "Open the folder",

  // ---- 設定
  "設定 — 外部ツール連携": "Settings — external tools",
  "FreeCAD パス": "FreeCAD path",
  "スライサー パス": "Slicer path",
  "既定の出力先": "Default output folder",
  "（自動: {dir}）": "(automatic: {dir})",
  "（自動）": "(automatic)",
  "既定の出力先は空にしておくと環境から自動で決まります（WSL で動かしている場合は Windows 側のドキュメントフォルダ）。PrusaSlicer / OrcaSlicer / Bambu Studio 等、STL を開けるスライサーを登録できます。":
    "Leave the default output folder empty and it is chosen from the environment (under "
    + "WSL, the Documents folder on the Windows side). Any slicer that opens STL — "
    + "PrusaSlicer, OrcaSlicer, Bambu Studio and so on — can be registered here.",

  // ---- インピーダンス
  "インピーダンス（Tier3・共鳴解析）": "Impedance (Tier 3, resonance analysis)",
  "🔄 再計算": "🔄 Recompute",
  "📈 インピーダンス計算": "📈 Compute impedance",
  "簡易TMM": "Simple TMM",
  "計算失敗": "Computation failed",
  "パラメータが変更されました。「再計算」で更新してください。":
    "The parameters have changed. Press Recompute to update.",
  "第1共鳴": "1st resonance",
  "目標（記譜最低音の実音）": "Target (concert pitch of the lowest written note)",
  "倍音整列度（ずれRMS）": "Harmonic alignment (RMS deviation)",

  // ---- 外部編集
  "凍結値": "Frozen",
  "実測(逆算)": "Measured (back-solved)",
  "判定": "Verdict",
  "測定方法": "Method",
  "測定不能なパラメータ（{n}件）": "Parameters that cannot be measured ({n})",
  "水密:": "Watertight:",
  "面数:": "Faces:",
  "体積:": "Volume:",
  "パラメータ逆算（凍結値との比較）": "Back-solved parameters (against the frozen values)",
  "領域別の形状偏差（分解能 約±0.15mm）":
    "Shape deviation by region (resolution about ±0.15 mm)",
  "部位": "Region",
  "最大偏差": "Max deviation",
  "FreeCADの自動起動に失敗: {why}　⚙設定でFreeCADのパスを登録すると次回から自動起動します。":
    "Could not launch FreeCAD: {why}　Register the FreeCAD path under ⚙ Settings and it "
    + "will launch automatically next time.",
  "凍結してSTEP/STLをエクスポート中…": "Freezing and exporting STEP/STL…",
  "FreeCADを起動中…": "Launching FreeCAD…",
  "✓ FreeCADでmodel.stepを開きました。編集後は上書き保存してください。":
    "✓ Opened model.step in FreeCAD. Save over the same file when you are done.",
  "解析中…（形状比較とパラメータ逆算。十数秒かかります）":
    "Analysing… (shape comparison and parameter back-solving; this takes some seconds)",
  "外部モデルを読み込み中…（整列と外形採寸。十数秒かかります）":
    "Loading the external model… (alignment and outline survey; this takes some seconds)",
  "取込モデルを登録中…": "Registering the imported model…",
  "外部編集（FreeCAD / Blender 連携）": "External editing (FreeCAD / Blender)",
  "⚠ 凍結後にパラメータが変更されています。編集済みモデルは古い形状です。再度「凍結してエクスポート」からやり直すか、パラメータを凍結時に戻してください。":
    "⚠ Parameters changed after the freeze, so the edited model is an old shape. Either "
    + "run “Freeze and export” again, or put the parameters back to the frozen values.",
  "① 設計を凍結して編集用にエクスポート": "① Freeze the design and export it for editing",
  "🔒 凍結中 — ": "🔒 Frozen — ",
  " / 実体積 {cc} cc": " / solid volume {cc} cc",
  "出力先:": "Output folder:",
  "パラメータ設計が完了したら凍結します。STEP（FreeCAD編集用）とSTLを出力し、現在のパラメータをスナップショットとして記録します。":
    "Freeze once the parametric design is finished. This writes STEP (for FreeCAD) and "
    + "STL, and records the current parameters as a snapshot.",
  "凍結解除（派生モデルも破棄）": "Unfreeze (also discards the derived model)",
  "🚀 FreeCADで開く": "🚀 Open in FreeCAD",
  "再凍結してエクスポート": "Re-freeze and export",
  "🔒 凍結してエクスポート": "🔒 Freeze and export",
  "✓ 出力完了: ": "✓ Written to: ",
  " — model.step を FreeCAD / Blender で編集してください。":
    " — edit model.step in FreeCAD or Blender. ",
  "テーブル・フェイシング面と内部空洞には触れないこと":
    "Do not touch the table, the facing surface or the internal cavity",
  "（詳細は docs/manual-edit-workflow.md）。": " (see docs/manual-edit-workflow.md).",
  "② 編集済みモデルを取込・検証": "② Import and check the edited model",
  "📥 登録済み — ": "📥 Registered — ",
  "元ファイル:": "Source file:",
  "体積": "Volume",
  " — 以後のエクスポートはこのモデルのSTLを入稿に使います。":
    " — from now on the print package uses this model's STL.",
  "外部ツールで編集した STL / STEP / 3MF を取り込むと、水密検査・凍結形状との領域別偏差・パラメータ逆算を自動実行します。（ファイル選択は凍結出力フォルダから始まります）":
    "Import an STL / STEP / 3MF edited in an external tool and it is checked for "
    + "watertightness, compared region by region against the frozen shape, and its "
    + "parameters are back-solved. (The file picker starts in the freeze output folder.)",
  "派生モデルを破棄": "Discard the derived model",
  "📥 編集済みモデルを取込…": "📥 Import the edited model…",
  "先に ① の凍結が必要です。": "Freeze in step ① first.",
  "外部モデルを読み込む（表示・採寸・FreeCAD編集）":
    "Load an external model (view, survey, edit in FreeCAD)",
  "市販の完成品など": "Loads a 3mf / STL / STEP ",
  "本アプリ以外で作られた 3mf / STL / STEP": "made outside this app",
  "を読み込みます（凍結不要）。正準姿勢へ整列して3D表示し、確実に測れる外形寸法だけ採寸します。差分照合とパラメータ逆算は行いません（座標系・内部形状が別物のため）。継続編集は FreeCAD で元ファイルを開いて行い、編集後に再度ここで読み込んでください。":
    ", such as a commercial part (no freeze needed). It is aligned to the canonical pose, "
    + "shown in 3D, and only the outline dimensions that can be measured reliably are "
    + "surveyed. No deviation comparison and no parameter back-solving are done, because "
    + "the coordinate frame and the internal shape are a different thing. To keep editing, "
    + "open the original file in FreeCAD and load it here again afterwards.",
  "📂 外部モデルを読み込む…": "📂 Load an external model…",
  " / 体積 {cc} cc": " / volume {cc} cc",
  "面数": "Faces",
  "外形寸法（信頼度）:": "Outline dimensions (confidence):",
  "なし": "none",
  "{key} {val}（{conf}）": "{key} {val} ({conf})",
  "この取込モデルを登録（表示・入稿に使用）":
    "Register this imported model (used for the view and the print package)",
  "解析レポート": "Analysis report",
  "このモデルを登録（入稿に使用）": "Register this model (used for the print package)",

  // ---- パラメータ欄
  "参照マウスピース": "Reference mouthpiece",
  "このセットの設計値に追従中": "Following this set's design values",
  "テンプレート既定値（取込元なし）": "Template defaults (nothing imported)",
  "既定に戻す": "Back to defaults",
  ".wproj から取込": "Import from .wproj",
  "同じセットの部品なので、あちらを編集すればここも変わります。":
    "It is a part of the same set, so editing it there changes it here too.",
  "取込時点の寸法で固定されます。参照元を後から編集しても自動追従しません。":
    "Fixed at the dimensions as imported. Editing the source later does not follow through.",
  "・": ", ",
  "勧める帯は {lo}〜{hi}{unit}。いまはその外です（越えられる壁ではありません）":
    "The recommended band is {lo}–{hi}{unit}. The value is outside it "
    + "(this is not a hard limit)",
  "帯の外": "outside the band",
  "壁 {lo}〜{hi}{unit}（{by}で動きます） ／ 勧める帯 {blo}〜{bhi}{unit}":
    "Hard limit {lo}–{hi}{unit} (moves with {by}) ／ recommended band {blo}–{bhi}{unit}",
  "勧める帯 {blo}〜{bhi}{unit}（越えられます。壁は {lo}〜{hi}{unit}）":
    "Recommended band {blo}–{bhi}{unit} (can be exceeded; the hard limit is {lo}–{hi}{unit})",
  "{kind} {blo}〜{bhi}{unit}": "{kind} {blo}–{bhi}{unit}",
  " ／ 出所: ": " ／ source: ",
  "記載なし": "not stated",
  "▾ 詳細パラメータを隠す": "▾ Hide advanced parameters",
  "▸ 詳細パラメータを表示": "▸ Show advanced parameters",

  // ---- 断面エディタ
  "断面を取得できません: {why}": "Cannot fetch the section: {why}",
  "断面を計算中…": "Computing the section…",
  "（指定 {n}）": " (set to {n})",
  "バッフル": "Baffle",
  "外形（全体）": "Outline (whole)",
  "このバッフル種別に断面ハンドルはありません": "This baffle type has no section handles",
  "この部品に外形ハンドルはありません": "This part has no outline handles",
  "⏳ 3D を再生成中…": "⏳ rebuilding the 3D…",
  "⚠ 断面の更新に失敗しました: ": "⚠ Could not update the section: ",
  "⚠ この位置での注意:": "⚠ At this position:",

  // ---- セットの部品タブ
  "部品構成": "Parts",
  "セットから外す": "Remove from the set",
  "{part}をこのセットに追加する": "Add the {part} to this set",
  "この部品を書出": "Export this part",
  "セットの中では設計中の値がそのまま下流の部品へ渡ります（取込み直しは要りません）。★ が土台の部品です。":
    "Inside a set the values you are designing with flow straight to the downstream parts "
    + "(no re-import needed). ★ marks the master part.",
  "部品を足すとセットになります。足した部品は、いま設計している値にそのまま追従します。":
    "Adding a part turns this into a set. The added part follows the values you are "
    + "designing with.",

  // ---- 警告・安全
  "⚠ 注意": "⚠ Note",
  "⚠ 口に入れる部品です": "⚠ This part goes in your mouth",
  "材料は": "Specify a ",
  "食品接触適合のもの": "food-contact-safe material",
  "を指定してください。": ".",
  "レジンは二次硬化と洗浄を十分に。": "Post-cure and wash resin thoroughly. ",
  "未硬化のレジンは皮膚感作性があります": "Uncured resin is a skin sensitiser",
  "。": ".",
  "PLA は約 55℃ で変形します。熱湯での洗浄・車内放置は不可。":
    "PLA deforms at about 55 °C. No boiling water, and never leave it in a car.",
  "使う前に": "Before each use, inspect for ",
  "割れ・欠け・鋭い縁": "cracks, chips and sharp edges",
  "を点検してください。印刷物は割れます。": ". Printed parts do break.",
  "ここに出る寸法と音響指標は推定です。できあがる物の安全性・耐久性・適合性は保証しません（詳しくは SAFETY.md）。製作と使用は自己責任で。":
    "The dimensions and acoustic figures shown here are estimates. Nothing is warranted "
    + "about the safety, durability or fitness of what you make (see SAFETY.md). You make "
    + "it and use it at your own risk.",

  // ---- チューニング / 音色
  "チューニング位置": "Tuning position",
  "合う位置が無い": "no position fits",
  "実用域の内側": "inside the usable range",
  "端に寄っている": "close to the edge",
  "実用域の外": "outside the usable range",
  "基準条件（25°C・目標音）で合う位置。実演奏の位置はリード・リガチャー・アンブシュアでも動く":
    "The position that fits under the reference conditions (25 °C, target note). In real "
    + "playing it also moves with the reed, the ligature and the embouchure",
  "実用域（挿し込み）": "Usable range (insertion)",
  "{lo}〜{hi}": "{lo}–{hi}",
  "感度（1mm 押し込んだときの第1共鳴）":
    "Sensitivity (1st resonance per 1 mm pushed on)",
  "セント/mm": "cents/mm",
  "現在 {mm} mm でのズレ": "Deviation at the current {mm} mm",
  "セント": "cents",
  "実効内容積": "Effective internal volume",
  "目標（欠損円錐）": "Target (missing cone)",
  "音色レーダー": "Tone radar",
  "{metric}を上げるなら → ": "To raise {metric} → ",
  "（効果 {per}/step）": " (effect {per}/step)",
  "🎯 目標から逆算（ゴールシーク）": "🎯 Solve back from a target (goal seek)",

  // ---- 音プレビュー
  "実際に鳴った音: {note} ({hz}Hz)": "Note that actually sounded: {note} ({hz} Hz)",
  "物理モデル音合成に失敗（{why}）。印象合成に切替えました。":
    "Physical-model synthesis failed ({why}). Switched to the impression synth.",
  "倍音 1→16": "Harmonics 1→16",
  "音プレビュー": "Sound preview",
  "印象合成（即時）": "Impression synth (instant)",
  "物理モデル(OpenWind)": "Physical model (OpenWind)",
  "合成中… (最大40秒)": "Synthesising… (up to 40 s)",
  "▶ 再生": "▶ Play",
  "■ 停止": "■ Stop",
  "🎵 スケール": "🎵 Scale",
  "物理モデル音は OpenWind の時間領域リードシミュで合成（単音 約12秒・スケール 約35秒）。トーンホールの無い共鳴管なので":
    "The physical-model sound is synthesised with OpenWind's time-domain reed simulation "
    + "(about 12 s for a note, 35 s for a scale). The tube has no tone holes, so ",
  "音高は指定できず": "you cannot choose the pitch",
  "、アンブシュア（リード共振）でどの共鳴が立つかが決まる。実際に鳴った音は上に表示。":
    "; the embouchure (reed resonance) decides which resonance speaks. The note that "
    + "actually sounded is shown above.",
  "A案": "A",
  "現在をAに記録": "Store current as A",
  "B案": "B",
  "現在をBに記録": "Store current as B",
  "現在の設計": "Current design",
  "ラ (A3) 220Hz": "A3 220 Hz",
  "ド (C4) 262Hz": "C4 262 Hz",
  "ミ (E4) 330Hz": "E4 330 Hz",
  "ラ (A4) 440Hz": "A4 440 Hz",
  "アンブシュア 緩め": "Embouchure: loose",
  "アンブシュア 標準": "Embouchure: normal",
  "アンブシュア 締め": "Embouchure: tight",

  // ---- 採寸
  "採寸": "Survey",
  "3Dモデルを測定中…（整列とレイキャスト。十数秒かかります）":
    "Measuring the 3D model… (alignment and ray casting; this takes some seconds)",
  "実測値を1つ以上入力してください。": "Enter at least one measured value.",
  "採寸を反映中…": "Applying the survey…",
  "採寸時点へ復元中…": "Restoring to the survey point…",
  "採寸を破棄中…": "Discarding the survey…",
  "採寸（実物の実測をプロジェクトへ反映）":
    "Survey (feed measurements of the real part into the project)",
  "手元の実物をノギスで測った値を入力すると、その項目だけ設計に反映されます（空欄は計算値のまま）。確定すると":
    "Type in what you measured on the real part with callipers and only those entries go "
    + "into the design (blanks keep the computed value). Committing records a ",
  "復元点": "restore point",
  "が記録され、以後に設計をいじって破綻しても「採寸時点へ戻す」で戻せます。":
    ", so if a later edit breaks the design you can go back with “Return to the survey point”.",
  "実物の 3mf / STL / STEP から外形寸法を自動測定して埋める":
    "Measure the outline from a real 3mf / STL / STEP and fill the fields in",
  "📥 3mf/STLから測定…": "📥 Measure from 3mf/STL…",
  "測定できた項目（信頼度）:": "Measured entries (confidence):",
  "測定値は下の入力欄に入りました。確認・修正して「採寸を確定」してください。":
    "The measurements are in the fields below. Check them, correct them, then press "
    + "“Commit the survey”.",
  "📐 採寸済み — ": "📐 Surveyed — ",
  "設計寸法（実測 → 設計パラメータに反映）":
    "Design dimensions (measured → into the design parameters)",
  "音響基準（実測 → ネック等の基準寸法に反映）":
    "Acoustic reference (measured → into reference dimensions such as the neck)",
  "公表値の無い基準寸法。実測するとこのプロジェクトの音程計算に効きます（descriptor は書き換えず、プロジェクト内だけの上書き）。":
    "Reference dimensions nobody publishes. Measuring them changes the pitch calculation "
    + "for this project (the descriptor is not rewritten; the override lives in the "
    + "project only).",
  "メモ": "Note",
  "採寸の対象・条件など": "what was measured, under what conditions…",
  "採寸を破棄": "Discard the survey",
  "↩ 採寸時点へ戻す": "↩ Return to the survey point",
  "📐 採寸を確定": "📐 Commit the survey",

  // ---- パス入力（`pathPicker` の LABELS。`t(変数)` で引く）
  "保存先を指定": "Choose where to save",
  "保存先のパス": "Path to save to",
  "拡張子 .wproj は省略できます。": "The .wproj extension can be left off.",
  "プロジェクトを開く": "Open a project",
  "プロジェクトファイルのパス": "Path to the project file",
  "サーバから見えるパスを入力してください。": "Enter a path the server can see.",
  "モデルファイルを指定": "Choose a model file",
  "モデルファイルのパス": "Path to the model file",
  "stl / step / stp / 3mf / obj / ply が読めます。":
    "stl / step / stp / 3mf / obj / ply can be read.",
  "出力先フォルダを指定": "Choose the output folder",
  "フォルダのパス": "Path to the folder",
  "存在しないフォルダは書き出し時に作成されます。":
    "A folder that does not exist is created when exporting.",
  "この環境ではOSのファイルダイアログを使えません（サーバが手元の画面を持っていない構成です）。サーバから見えるパスを直接入力してください。":
    "The OS file dialog is not usable here (the server has no screen in front of you). "
    + "Type a path the server can see.",
  "ファイルダイアログを開けませんでした。パスを直接入力してください。":
    "Could not open the file dialog. Type the path instead.",
  "決定": "OK",

  // ---- `t(変数)` で引く短い語
  "高": "high",
  "中": "med",
  "低": "low",
  "幾何の成立条件": "geometric requirement",
  "製造の制約": "manufacturing constraint",
  "慣習の推奨帯": "conventional range",
  "未分類の壁": "unclassified limit",
  "一致": "match",
  "変化なし": "unchanged",
  "軽微": "minor",
  "乖離": "off",
  "変化あり": "changed",
  "測定不能": "not measurable",
  "判定不可": "no verdict",
  "?": "?",
};

export default EN;
