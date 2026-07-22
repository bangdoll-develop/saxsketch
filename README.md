# SaxSketch — 管楽器設計・3Dプリント統合開発環境

サクソフォンを題材に、管楽器とアクセサリ（マウスピース／リード／リガチャー／ネック／本体）を
パラメトリック設計し、設計時の音響シミュレーションを行いながら、3Dプリント入稿データ・
部品表・仕様書までワンストップで生成するローカルWebアプリ。

現在の実装範囲（Phase 0+1）: **サクソフォン マウスピース** の完全な設計〜出力。

## 主な機能

- **パラメトリック設計**: フェイシング（ティップ開き・フェイシング長・カーブ）、バッフル
  （種別・高さ）、チェンバー（スロート断面積比・形状）、ボア、ウィンドウ、外形など20項目。
  各パラメータに音・演奏性への効果を明記。
- **リアルタイム3Dプレビュー**: パラメータ変更 → build123d で形状再生成 → ブラウザに表示。
- **設計時シミュレーション**
  - 音程チェック: 内容積 vs 欠損円錐体積（Benade理論）でセント偏差を推定。
  - 音色レーダー: 明るさ・パワー・抵抗感・柔軟性・エッジを Acta Acustica 2021 の
    知見に基づく回帰モデルで表示。
  - 感度ガイド: 「明るくしたいならこのパラメータを＋」を数値偏微分で常時提案。
  - ゴールシーク: 目標指標からパラメータを逆算（scipy）。差分プレビュー→承認で適用。
  - 音プレビュー: 音色指標から倍音列を合成し Web Audio で即再生。波形＋スペクトル表示、
    A/B聴き比べ。
- **プロジェクト管理**: `.wproj`（ZIP）形式で保存/読込。スキーマバージョン管理・最近使った
  ファイル対応。
- **出力**: STL / STEP / 3MF、部品表(CSV)、仕様書(HTML・断面図SVG付き・印刷推奨条件)、
  入稿パッケージ(ZIP)。オンライン3Dプリントサービスへそのまま渡せる。
- **外部ツール連携**: FreeCAD / スライサーを設定登録し「開く」ボタンで直接起動。
- **外部編集ワークフロー**: パラメータで表現できない個別調整（名入れ・フィレット・
  スカルプト）を FreeCAD / Blender で行い、アプリに再取込。凍結スナップショット・
  水密検査・領域別偏差・**パラメータ逆算**（編集がどのパラメータをどれだけ変えたか
  自動判定）・陳腐化警告つき。→ [docs/manual-edit-workflow.md](docs/manual-edit-workflow.md)

## セットアップ

### 前提ソフトウェア

| ツール | 必要バージョン | 用途 | 確認コマンド |
|---|---|---|---|
| Python | 3.11 以上（開発は 3.12 で検証） | バックエンド・CAD・音響計算 | `python --version` |
| uv | 0.11 以上 | Python仮想環境・依存管理（pip より高速） | `uv --version` |
| Node.js | 20 以上（開発は 24 で検証） | フロントエンドのビルド | `node --version` |
| npm | Node同梱 | フロント依存の取得 | `npm --version` |

uv 未導入の場合は [astral.sh/uv](https://docs.astral.sh/uv/) からインストール（Windowsは
PowerShellで `irm https://astral.sh/uv/install.ps1 | iex`）。uv を使いたくなければ
標準の `python -m venv` + `pip` でも代替可（下記「uvを使わない場合」参照）。

### 手順

プロジェクトルート（`pyproject.toml` のあるフォルダ）で順に実行する。

```powershell
# 1) Python仮想環境を作成（.venv フォルダができる）
uv venv

# 2) バックエンド依存をインストール（build123d, fastapi, scipy, trimesh など）
#    -e = 編集可能インストール（ソース変更が即反映）、[dev] = pytest等も含む
uv pip install -e ".[dev]"

# 3) フロントエンドをビルド（frontend/dist/ が生成される）
cd frontend
npm install          # 初回のみ。node_modules を取得
npm run build        # TypeScriptコンパイル + Viteビルド
cd ..
```

各ステップの意味:
- **1〜2**: `build123d`（CADカーネル OCCT）を含むため、初回は数分かかることがある。
  仮想環境 `.venv/` にすべて入り、システムのPythonは汚さない。
- **3**: サーバは `frontend/dist/` を静的配信する。**ここをビルドしないとUIが表示されない**
  （サーバ起動時にトップページが 404 になる）。フロントのソースを編集したら再度
  `npm run build` するか、後述の開発モードを使う。

### uv を使わない場合

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # 仮想環境を有効化（macOS/Linux は source .venv/bin/activate）
pip install -e ".[dev]"
cd frontend; npm install; npm run build; cd ..
```

## 起動

### 通常起動（ビルド済みUIを配信）

```powershell
# 仮想環境のPythonでサーバを起動
.\.venv\Scripts\python.exe -m saxsketch.server.app
```

起動すると `http://127.0.0.1:8712` で待ち受ける。**ブラウザでこのURLを開く**と
アプリが表示される（ローカル専用。外部には公開されない）。

- ポートは `8712` 固定（`saxsketch/server/app.py` の `main()` で変更可）。
- 設定ファイルは `~/.saxsketch/settings.json`（外部ツールのパス・最近使ったファイル・
  既定の出力先）。エクスポートの既定出力先は `ドキュメント\SaxSketch\`。
- 停止は起動ターミナルで `Ctrl+C`。

初回起動時は「新規プロジェクト」ダイアログが開く。楽器=サクソフォン、サイズ=アルト、
コンポーネント=マウスピースを選んで「作成」で設計を開始できる。

### 開発モード（UIを編集しながら使う）

フロントを編集して即反映したい場合は、サーバとViteの開発サーバを**2つ同時に**起動する。

```powershell
# ターミナル1: バックエンド（APIサーバ）
.\.venv\Scripts\python.exe -m saxsketch.server.app

# ターミナル2: フロント開発サーバ（ホットリロード付き）
cd frontend
npm run dev
```

この場合はブラウザで **Viteが表示するURL（通常 `http://localhost:5173`）** を開く。
`/api` へのリクエストは `vite.config.ts` の proxy 設定で自動的に 8712 のサーバへ転送される。
`.tsx` を保存するとブラウザが自動更新される。

### 動作確認

依存が正しく入っているかは、UIを触る前にテストで確認できる。

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

12件すべて green ならジオメトリ生成・音響計算・プロジェクトI/O・APIが正常。

### つまずきやすい点

- **UIが真っ白 / トップページが404** → `frontend/dist/` が無い。`cd frontend && npm run build`
  を実行し忘れていないか確認。
- **`ModuleNotFoundError: saxsketch`** → 仮想環境のPythonで起動していない。`python` ではなく
  `.\.venv\Scripts\python.exe` を使うか、仮想環境を Activate する。
- **`build123d` のインストールが失敗** → Python が 3.11 以上か確認（`python --version`）。
  32bit Python では動かない。
- **ポート 8712 が使用中** → 別プロセスが占有している。`saxsketch/server/app.py` の
  `port=8712` を変更するか、占有プロセスを終了する。
- **エクスポートの「参照」やプロジェクト保存でダイアログが出ない** → OSのファイルダイアログ
  （tkinter）が使えない環境。その場合はパスを手入力すれば動作する。

## 拡張（新しい楽器の追加）

`saxsketch/instruments/<楽器id>/` を追加するだけ。コアは楽器を知らない。

- `descriptor.json` … 楽器の物理定数（調・欠損円錐体積・ネック寸法・リード規格）
- `templates/*.json` … サイズテンプレート（パラメータ初期値）
- `components/` … `Component` 派生クラス（`COMPONENTS` dict で公開）

## アーキテクチャ

- `saxsketch/core/` … スキーマエンジン・プロジェクトI/O・プラグインレジストリ
- `saxsketch/geometry/` … build123d 共通ビルダー
- `saxsketch/acoustics/` … 音程・音色・感度・ゴールシーク・倍音
- `saxsketch/export/` … モデル/BOM/仕様書/入稿パッケージ
- `saxsketch/server/` … FastAPI
- `frontend/` … React + TypeScript + Three.js（日本語UI）

## ロードマップ

- Phase 2: OpenWind 統合（マウスピースのインピーダンス表示・物理モデル音合成）
- Phase 3: リード・リガチャー（マウスピース外形と自動整合）
- Phase 4-A: 採寸ワークフロー（実物の実測をプロジェクト局所で反映・復元点つき）✔
- Phase 4-B: ネック・キーレス管体（トーンホール設計・造形サイズ自動分割）
- Phase 5: 第2楽器（クラリネット等）追加、サービス入稿の自動化

## 注意

口に触れる部品です。3Dプリントには食品接触適合材料を使用し、印刷後の洗浄・
硬化・シーリングを必ず行ってください。音響指標は文献傾向に基づく推定であり、
実楽器での校正を推奨します。
