# 基準形状の出所（WindyCity Tenor 3MF）

このフォルダの道具は、**他人が作って CC BY-NC-SA で公開した 3D モデル**を実測して、
SaxSketch のマウスピース構成式を起こすためのものである。出所をここ 1 か所に置く。

## 原典

| 項目 | 値 |
|---|---|
| 題 | Windy City Woodwinds "72" Tenor Saxophone Mouthpiece |
| 作者 | WindyCityWoodwinds（Windy City Woodwinds） |
| 公開 | 2024-06-03 |
| URL | https://www.thingiverse.com/thing:6645240 |
| ライセンス | **Creative Commons — Attribution · Non-Commercial · Share Alike (CC BY-NC-SA)** |
| 取得 | 2026-07-20（ファイル名 `WindyCity-Tenor-72-100-LS.3mf`、240,658 bytes） |

Windy City Woodwinds は 2024 年半ばに廃業し、そのときに設計を公開した。
上の Thingiverse 投稿がその公開である（Series 56 / 64 / 72 の各サイズが
別々の thing として出ている）。

## 来歴（どう手元に来たか）

**2026-10-15 に確認した証跡**:

1. ダウンロード元は NTFS 代替データストリームに残っていた ——
   `Downloads/WindyCity-Tenor-72-100-LS.3mf:Zone.Identifier` が
   `[ZoneTransfer] ZoneId=3 HostUrl=https://www.thingiverse.com/`。
2. 手元のファイルは**原作者の投稿そのものではなく、誰かが Bambu Studio で
   開いて書き出し直した版**である。`Metadata/model_settings.config` に
   第三者のローカルパス
   `C:\Users\<第三者>\OneDrive\Documents\Printables\Printable Mpc -  SAX\WindyCity-Tenor-72-100-LS.3mf`
   が残っている（Printables 経由で入手した物を再書き出ししたらしい）。
   **利用者名は伏せた** —— 来歴の論点は「Printables 経由の再書き出し
   である」ことであって、見ず知らずの人の名前ではない（原本は手元の 3mf にある）。
3. **その経路でメッシュは改変されていない** ——
   `mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0"
   facets_reversed="0" backwards_edges="0"`。
4. 3MF に埋め込まれた `License` / `Designer` / `Copyright` は**すべて空**。
   `Title` は `Alto_64_0.072` だが、これは別案件から持ち越された残りかすで、
   形状は全長 107.5mm のテナー（ファイル名の「Series 72 / .100" / Long Shank」と整合）。

→ ライセンスの根拠は**原作者本人のアカウントにある同じ型の投稿**（上の URL）に置く。
再書き出し経路のライセンス表記は空なので、そちらは根拠にしない。

## このリポジトリでの扱い

### 配っていない物

モデルのファイルそのものは**リポジトリに入れていない**（116 コミットの履歴にも
一度も入っていない）。`.gitignore` で `*.3mf` `*.stl` `*.step` `*.stp` `*.FCStd` を
除外し、トラックされていないことを `tests/test_saxsketch.py` が固定している。
具体的には次の 3 つがローカル生成物として存在するが、どれも非公開である:

| ファイル | なぜ配れないか |
|---|---|
| `reference_aligned.stl` | 原メッシュを整列しただけ。複製そのもの |
| `base_tenor.FCStd` | **原メッシュを同梱している**（重ね表示のため） |
| `WindyCity-Tenor-72-100-LS.3mf` | 原ファイル |

### CC BY-NC-SA で提供する画像（5 枚）

次の 5 つは `reference_aligned.stl` から直接描いた図なので、
**リポジトリ本体の Apache-2.0 ではなく、原典と同じ CC BY-NC-SA** で提供する。

- `overlay_base.png` —— 表面 20 万点の散布（`render_overlay.py`）
- `sections_xy.png` —— Z 一定の横断面 10 枚（`render_sections.py`）
- `sections_yz_xz.png` —— 縦断面・水平断面
- `window_outline.png` —— リード面から見た開口の輪郭
- `tip_rail.png` —— ティップレールの平面視・レール幅・先端の縦断面

同じ `cad/` の下でも、**モデル自身の形状しか描いていない図は Apache-2.0 のまま**
である（`cad/ligature/ref_overlay.png`、`cad/baffle/baffle_types.png`、
`cad/baffle/baffle_handles.png`、`cad/reed/*.png`）。これらは
`comp.build(params)` が作った SaxSketch のメッシュを描いている。

### 構成式の数表について

`profiles.py` の `_CAVITY_W` / `_CAVITY_C` / `_CAVITY_D`、`table_angle = 4.18`、
`templates/*.json` の既定値は、上のメッシュを**測って得た数値**である。
寸法は事実であり、σ 正規化の取り方・station の置き方・33 本のパラメータ化は
こちらの表現なので、これらを CC BY-NC-SA の適応物としては扱っていない。
ただしこの読みは争える余地があり、**収益化するなら賭けない**ことにしている
（下記）。

## 再現したい人へ

`align_reference.py` は環境変数 `WINDYCITY_3MF` で原ファイルの場所を受け取る。

```bash
export WINDYCITY_3MF=/path/to/WindyCity-Tenor-72-100-LS.3mf
PYTHONPATH=. python cad/windycity/align_reference.py
```

ファイルは上の Thingiverse から各自入手すること。こちらからは配れない
（NC-SA の再配布は可能だが、原作者の配布ページを迂回させる理由が無く、
版の取り違えも起きる）。

## 収益化するときに必要なこと

NC 条項があるので、**この基準に依存したまま有償化はできない**。
決着させる道は 1 つで、**手元にある個体（Jody Jazz GIANT 6☆）で基準を取り直す**こと。

- 4 点の実測ではモデルとの差が +0.52 / −0.13 / −0.42 / −0.73 と符号を変えるので、
  一様なずれ（`side_rail_width` 1 本で吸える）か形の誤りかが分けられない。
  `cad/inspection/survey_sheet.py` が出す採寸シートは、そのために z を 10 点へ密にしてある。
- `_CAVITY_W` は σ で正規化した 1 つの表を 3 サイズが共有しているので、
  形の誤りだった場合は「表をサイズごとに分けるか」も同時に決まる。
- 取り直したら、このフォルダは歴史記述へ退避し、**上の 5 枚は撮り直して差し替える**。

関連: `../../NOTICE` / `../../THIRD-PARTY.md` / `README.md` / `../../docs/reed-seat.md`
