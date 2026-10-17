# WindyCity Tenor 実測フィット候補 3案

実在マウスピース **WindyCity Tenor .100" Long Shank**（`WindyCity-Tenor-72-100-LS.3mf`）を
実測し、SaxSketch の**パラメータ編集→ライブ再計算できるベースモデル**として使える
パラメータ一式へフィットさせた候補 3 案です。FreeCAD で実物メッシュと重ねて確認し、
採用する案を選んでください。

## ファイル

| ファイル | 内容 |
|---|---|
| `candidate_1_faithful.FCStd` / `.json` | **案1 忠実**: 全パラメータを実測値どおり採用 |
| `candidate_2_playing.FCStd` / `.json` | **案2 演奏面優先**: ティップ開き・フェイシング・窓・ビーク・ボアは実測、内部空洞（バッフル/スロート/チェンバー）は現行テナー校正値を維持 |
| `candidate_3_acoustic.FCStd` / `.json` | **案3 音響優先**: 案1ベース＋バッフルをティップ近傍（音色支配域）重み付きでフィット＋内容積を実測一致に調整 |
| `fit_report.md` | 実測値・採用値・測定方法・クランプ・フィット残差の全記録（自動生成） |
| `reference_aligned.stl` | SaxSketch 座標系へ整列済みの実物メッシュ（FCStd に同梱済み） |
| `fit_windycity.py` | 3mf 整列＋実測＋candidate JSON 生成（WSL2 の SaxSketch 環境で実行） |
| `build_candidates.py` | candidate JSON → FCStd 生成（freecadcmd で実行） |

## FreeCAD での確認

1. `candidate_*.FCStd` をダブルクリックで開く。
2. ツリーに **候補ソリッド**（`Mouthpiece_WC…`）と **実物メッシュ**（`WindyCity_Reference`）が
   同一座標系で重なっている。
3. メッシュを選択 → 表示プロパティの `Transparency` を 50〜70 にすると重なりが見やすい
   （またはスペースキーで交互に表示/非表示）。
4. 特にティップ開き・フェイシング・ビーク・チェンバー断面の乖離を確認する。

## 採用の反映（SaxSketch 側、コード変更ゼロ）

採用する案の JSON をテンプレートとして置くだけです:

```bash
cp cad/windycity/candidate_1_faithful.json saxsketch/instruments/saxophone/templates/tenor_windycity.json
```

テンプレートは `templates/*.json` の自動発見なので、次回起動からプロジェクト作成時に
「テナー WindyCity 案1 忠実フィット」を選べます。全パラメータは通常どおりスライダーで
ライブ編集できます（candidate JSON は `label` / `size` / `mouthpiece` / `reed` /
`ligature` / `neck` を含む完全なテンプレート形式。mouthpiece 以外は現行テナー値）。

その後の FreeCAD 編集・取込（凍結エクスポート → 外部編集 → 取込/採寸）のワークフローは
従来と同じです。

## 3案の違い（要点）

内部空洞だけが違います（演奏面・外形は 3 案とも実測値）:

| | バッフル | throat_ratio | chamber_ratio | 性格 |
|---|---|---|---|---|
| 案1 | 天井プロファイル全域フィット | 実測 0.89 | 実測 | 幾何の全域最小二乗 |
| 案2 | 現行テナー値 (rollover 1.8) | 1.00 | 1.50 | SaxSketch 校正済み音響と整合 |
| 案3 | ティップ近傍重み付きフィット | 実測 0.89 | 体積一致 | 音色支配域と内容積を優先 |

## 実測の要点と既知の限界（詳細は fit_report.md）

- 実測: 全長 108.0 / ボディ径 31.0 / ボア径 16.9 / ティップ開き 3.1 / フェイシング 26
  （カーブは**円弧 radial** が楕円より良く一致）/ ビーク高さ 14.4 / チェンバー round。
- **テーブルが約 6° 傾いている**（ボア軸に対し）。SaxSketch のテーブルは軸平行のため、
  重ね合わせではテーブル側が扇形にずれて見える。リード面基準の寸法で写像しているので
  演奏ジオメトリ（開き・フェイシング・バイト高さ）は保たれる。
- 窓長 46.6 → スキーマ上限 44 に、ボア長 63 → 上限 60 にクランプ。
- ティップ/サイドレール幅は分解能・形状連続性の限界で実測できず現行値を継承。
- 名目 .100"=2.54mm に対しティップ開き実測 3.1mm（3D プリントモデルのエッジ丸み・
  テーブル平面の取り方を含む値。ノギス/フィーラーゲージでの実測上書きが本筋）。

## 再生成

```bash
# 実測とフィット（WSL2）
wsl bash -lc "PYTHONPATH=. ~/mp_design/.venv/bin/python cad/windycity/fit_windycity.py"
```

```bash
# FCStd 生成（Windows FreeCAD）
"C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" cad/windycity/build_candidates.py
```
