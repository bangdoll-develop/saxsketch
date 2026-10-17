# 第三者のソフトウェアとデータ

SaxSketch 本体は Apache-2.0（`LICENSE`）。ここに挙げるのは**同梱していないが
動かすのに要る物**と、**数値の出所**である。参照形状（CC BY-NC-SA）の帰属は
`NOTICE` と `cad/windycity/ATTRIBUTION.md` にある。

ライセンス表記は導入済みパッケージの `*.dist-info/METADATA` から読んだ実測
（2026-10-15、`.venv` / Python 3.12）。バージョンは確認時点のもの。

## Python（実行時）

| パッケージ | 版 | ライセンス | 役割 |
|---|---|---|---|
| build123d | 0.11.1 | Apache-2.0 | CAD カーネルの上位 API。`saxsketch/geometry/builders.py` |
| cadquery-ocp-novtk (OCP) | 7.9.3.1.1 | Apache-2.0（**下の注記**） | OpenCASCADE の Python バインディング |
| cadquery-ocp-proxy | 7.9.3.1.1 | Apache-2.0 | 同上 |
| ocp-gordon | 0.2.2 | Apache-2.0 | build123d 経由 |
| ocpsvg | 0.6.0 | Apache-2.0（METADATA に表記なし／同梱 `LICENSE` 本文で確認） | build123d 経由 |
| trimesh | 4.12.2 | MIT | メッシュ読み込み・採寸・差分 |
| numpy | 2.5.1 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | 全般 |
| scipy | 1.18.0 | BSD-3-Clause | ゴールシーク・近傍探索 |
| fastapi | 0.139.2 | MIT | サーバ |
| starlette | 1.3.1 | BSD-3-Clause | 同上 |
| uvicorn[standard] | 0.51.0 | BSD-3-Clause | 同上（websockets / httptools / uvloop / PyYAML / python-dotenv を連れてくる） |
| pydantic / pydantic-core | 2.13.4 / 2.46.4 | MIT | API のスキーマ |
| networkx | 3.6.1 | BSD-3-Clause | trimesh の 3MF ローダ |
| lxml | 6.1.1 | BSD-3-Clause | 同上 |
| rtree | 1.4.1 | MIT | trimesh の近傍探索 |
| requests | 2.34.2 | Apache-2.0 | build123d 経由 |
| certifi | 2026.6.17 | **MPL-2.0** | requests 経由（推移・未改変） |
| matplotlib | 3.11.1 | Matplotlib License（PSF 派生・BSD 互換） | `cad/` の作図のみ。製品には不要 |

**OCCT の注記。** `cadquery-ocp-novtk` が Apache-2.0 を名乗るのは**バインディング**
についてであり、その中の OpenCASCADE Technology 本体は
**LGPL-2.1 + Open CASCADE exception** である。wheel にライセンス本文は
同梱されていない（`site-packages` を走査して 0 件）。本リポジトリは OCP も OCCT も
同梱していないのでソース配布としての義務は軽いが、**バイナリやインストーラを
作って配るときは LGPL の表示義務がこちらに来る**。

## Python（任意・開発）

| パッケージ | ライセンス | 扱い |
|---|---|---|
| **openwind** 0.12.4 | **GPL-3.0**（Inria） | **同梱しない。** `[acoustics]` extra。未導入なら自作 TMM へ自動フォールバックする（`saxsketch/acoustics/openwind_bridge.py:97-102`）。`scripts/wsl_sync.sh` が入れているのは**開発環境の構築**であって配布ではない。**インストーラやバンドルを作るときに巻き込まないこと**（結合著作物が GPL-3 になる） |
| pytest / httpx | MIT / BSD-3-Clause | `[dev]` extra |
| av (PyAV) | BSD-3-Clause（同梱 FFmpeg は LGPL-2.1+） | `[inspection]` extra。`cad/inspection/analyze_recording.py` が関数の中で import する |

## 外部プログラム（import せず、プロセスとして呼ぶ）

| 物 | ライセンス | 使うところ |
|---|---|---|
| **FreeCAD** 1.1 | LGPL-2.1-or-later | `cad/freecad/*.py` と `cad/windycity/build_base.py` は `freecadcmd` の中で走る。アプリからは `/api/tools/open` で起動するだけ |
| スライサ（任意） | 各社 | `/api/tools/open` で起動するだけ |
| PowerShell | — | ファイルダイアログを別プロセスで出す（`saxsketch/server/filedialog.py`） |

## JavaScript（フロントエンド）

`frontend/package-lock.json` が正本。内訳は MIT 66 / MPL-2.0 12 / Apache-2.0 3 /
ISC 1 / BSD-3-Clause 1 / 0BSD 1。GPL・AGPL・LGPL・非商用条項は無い。

| 主なもの | ライセンス |
|---|---|
| react / react-dom 19.2.7 | MIT |
| three 0.185.1 | MIT |
| @dimforge/rapier3d-compat | Apache-2.0（three 経由） |
| typescript | Apache-2.0 |
| vite / @vitejs/plugin-react / oxlint | MIT |
| lightningcss ＋ 12 のプラットフォーム版 | **MPL-2.0**（vite 経由・開発時のみ・未改変） |

CDN からは何も読み込まない。`frontend/index.html` が読むのは `/src/main.tsx` だけで、
ビルド済みのアセットは同じサーバから配る。

## 数値の出所（コードではないもの）

| 何 | 出所 | どこで使うか |
|---|---|---|
| マウスピース基準形状 | **CC BY-NC-SA / `NOTICE` 参照** | `profiles.py` の構成式、`templates/*.json` |
| 側孔の長さ補正係数 | Dubos, Kergomard, Khettabi, Dalmont, Keefe, Nederveen (1999), "Theory of sound propagation in a duct with a branched tube using modal decomposition", *Acta Acustica* 85(2), 153-169 | `saxsketch/acoustics/toneholes.py` |
| 空気中の音速の式 | Zuckerwar, *Handbook of the Speed of Sound in Real Gases* 16.3.3 | `saxsketch/acoustics/openwind_bridge.py` |
| 音色指標の回帰 | *Acta Acustica* 2021, "Towards 3D printed saxophone mouthpiece personalization" | `saxsketch/acoustics/brightness.py` |
| フェイシング長のレンジ | 各社公表フェイシングチャート（Meyer / Vandoren V16 / Otto Link） | `instruments/saxophone/descriptor.json` |
| 材料の E・ρ | 文献値（個別の出典は未記録） | `saxsketch/acoustics/reed_model.py` |
| 欠損円錐長 217.5mm | **出典未記録**（`descriptor.json` に「文献名も URL も測定者も日付も残っていない」と明記してある） | `saxsketch/acoustics/volume.py` |
| 市販個体・リードの寸法 | 本プロジェクトでノギスを当てた実測 | `cad/inspection/inspection_values.py` |

上 2 つの式は OpenWind（GPL-3）も同じ原典の式を使っており、**値が一致することを
テストで確かめている**（`tests/test_saxsketch.py`）。実装は原典の式から書いたもので、
OpenWind のソースを配布物に取り込んではいない。

## 商標

製品名・ブランド名はいずれも各社の商標であり、**ノギスを当てた個体を特定するため**
に挙げている。本プロジェクトは各社と提携関係にない。`NOTICE` 参照。
