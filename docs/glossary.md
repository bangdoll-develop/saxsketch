# 用語表 — Glossary (日本語 ↔ English)

**この表が英訳の唯一の出典。** 画面・仕様書・部品表・入稿 ZIP に出る英語は、すべてここから引く。
**ここに無い語を、その場で訳さない。** 相手はサックス吹きで、用語の誤りで道具の真贋を判断する
（`side rail` を `side guide` と書いた時点で読むのをやめる）。新しい語が要るときは、
まずこの表に足してから使う。

This table is the single source of truth for every English string the app shows or writes.
Do not invent a translation at the call site; add it here first.

**訳さないもの** —— 固有名（Jody Jazz / Vandoren / WindyCity / Légère …）、
サイズ名（soprano / alto / tenor）、ファイル拡張子、パラメータの `key`。

---

## 1. 部位 — Parts

| 日本語 | English | 備考 |
|---|---|---|
| マウスピース | mouthpiece | |
| リード | reed | |
| リガチャー | ligature | |
| ネック | neck | |
| 本体・管体 | body | サックスの管の部分。`tube` は使わない |
| テーブル | table | リードが載る平面 |
| 窓・ウィンドウ | window | テーブルに開いた長穴 |
| ティップレール | tip rail | 窓の先端側の細い縁 |
| サイドレール | side rail | 窓の両側の縁 |
| バッフル | baffle | |
| チェンバー | chamber | |
| スロート | throat | チェンバーからボアへの絞り |
| ボア | bore | |
| シャンク | shank | ネックに挿す筒 |
| ビーク | beak | 上歯が載る面 |
| 肩 | shoulder | ビークからボディへの移り |
| ヴァンプ | vamp | リードの削られた部分 |
| 踵 | heel | リードの根元側 |
| 背骨 | spine | ヴァンプ中央の厚い帯 |
| テノン | tenon | 挿し込む側の筒 |
| ソケット・受け | socket | 挿される側の穴 |
| コルク | cork | |
| ボウ | bow | 管の U 字部 |
| ベル | bell | |
| フレア | flare | ベルの広がり |
| トーンホール・側孔 | tone hole | |
| チムニー | chimney | トーンホールの立ち上がり |
| 指孔 | finger hole | |
| 親指孔 | thumb hole | |
| オクターブベント | octave vent | |

## 2. パラメータ — Parameters

`key` は元から英語なのでそのまま。訳すのは `label`（つまみの名前）と `category`（まとめの見出し）。
**本数は実行時のスキーマ（104 本）に合わせてある** —— ソースを正規表現で数えると
真偽値ヘルパ経由の 6 本を落とす（実際に落として、テストに拾われた）。

### 2.1 マウスピース — Mouthpiece (33)

| category | key | 日本語 | English |
|---|---|---|---|
| フェイシング / Facing | `tip_opening` | ティップ開き | Tip opening |
| | `facing_length` | フェイシング長 | Facing length |
| | `facing_curve` | カーブ種別 | Facing curve |
| | `tip_rail_width` | ティップレール幅 | Tip rail width |
| | `tip_rail_thickness` | ティップレール厚 | Tip rail thickness |
| | `tip_chamfer` | ティップ前縁の面取り | Tip front-edge chamfer |
| | `side_rail_width` | サイドレール幅 | Side rail width |
| | `table_angle` | テーブル傾斜 | Table angle |
| バッフル / Baffle | `baffle_type` | バッフル種別 | Baffle type |
| | `baffle_height` | バッフル高さ | Baffle height |
| | `baffle_plateau` | バッフル平坦長 | Baffle plateau length |
| | `baffle_step_rise` | 段の立ち上がり | Step rise |
| | `baffle_curvature` | カーブ量 | Baffle curvature |
| | `rollover_radius` | ロールオーバー半径 | Rollover radius |
| チェンバー / Chamber | `throat_ratio` | スロート断面積比 | Throat area ratio |
| | `chamber_ratio` | チェンバー断面積比 | Chamber area ratio |
| | `chamber_shape` | チェンバー形状 | Chamber shape |
| ボア / Bore | `bore_dia` | ボア径 | Bore diameter |
| | `bore_length` | ボア長 | Bore length |
| | `cork_depth` | コーク挿入深さ | Cork insertion depth |
| ウィンドウ / Window | `window_length` | ウィンドウ長 | Window length |
| | `chamber_to_bore_mm` | チェンバー→ボアの遷移 | Chamber-to-bore transition |
| | `reed_width` | リード幅（規格の呼び） | Reed width (nominal) |
| 外形 / Outline | `beak_height` | ビーク高さ | Beak height |
| | `body_dia` | ボディ径 | Body diameter |
| | `shank_dia` | シャンク径 | Shank diameter |
| | `shank_length` | シャンク長 | Shank length |
| | `shoulder_ratio` | 肩の長さ比 | Shoulder length ratio |
| | `body_waist` | 胴の膨らみ | Body waist |
| | `shoulder_fullness` | 肩の張り | Shoulder fullness |
| | `overall_length` | 全長 | Overall length |
| 製造 / Manufacturing | `min_wall` | 最小肉厚 | Minimum wall thickness |
| | `material` | 材料プリセット | Material preset |

### 2.2 リード — Reed (15)

| category | key | 日本語 | English |
|---|---|---|---|
| 寸法 / Dimensions | `reed_length` | リード全長 | Reed length |
| | `tip_width` | 先端幅 | Tip width |
| | `heel_width` | 踵幅 | Heel width |
| プロファイル / Profile | `tip_thickness` | 先端厚（中央） | Tip thickness (centre) |
| | `heel_thickness` | 踵厚 | Heel thickness |
| | `heel_edge_thickness` | 踵の側端厚 | Heel edge thickness |
| | `vamp_length` | ヴァンプ長 | Vamp length |
| | `profile_curve` | プロファイル曲線 | Profile curve |
| | `spine_ratio` | 背骨の広さ | Spine width ratio |
| レール / Rails | `side_rail_thin` | サイドレール比 | Side rail thinning ratio |
| | `tip_corner_r` | 先端角の丸み | Tip corner radius |
| | `tip_curve_depth` | 先端カーブ | Tip curve depth |
| カット / Cut | `file_cut` | カット種別 | Cut type |
| 製造 / Manufacturing | `material` | 材料プリセット | Material preset |
| | `min_layer` | 積層ピッチ | Layer height |

### 2.3 リガチャー — Ligature (15)

| category | key | 日本語 | English |
|---|---|---|---|
| バンド / Band | `band_width` | バンド幅 | Band width |
| | `band_thickness` | バンド厚 | Band thickness |
| | `seat_setback` | 座位置（最大径から前へ） | Seat setback (from max diameter) |
| | `clearance` | はめあい隙間 | Fit clearance |
| | `reed_clearance` | リード逃げ | Reed clearance |
| 締結 / Closure | `closure` | 締結方式 | Closure type |
| | `press_depth` | 押し込み量 | Press depth |
| | `screw_count` | ネジ本数 | Screw count |
| | `screw_size` | ネジ呼び径 | Screw size |
| | `boss_height` | ネジ座の高さ | Screw boss height |
| | `slit_width` | スリット幅 | Slit width |
| 接触 / Contact | `contact_type` | リードへの当たり方 | Reed contact type |
| | `contact_count` | 接触の数（x方向） | Contact count (across) |
| 製造 / Manufacturing | `material` | 材料プリセット | Material preset |
| | `min_wall` | 最小肉厚 | Minimum wall thickness |

### 2.4 ネック — Neck (19)

| category | key | 日本語 | English |
|---|---|---|---|
| 寸法 / Dimensions | `neck_length` | ネック全長（弧長） | Neck length (arc) |
| | `bore_small_id` | 小端ボア内径 | Small-end bore ID |
| | `wall_thickness` | 肉厚 | Wall thickness |
| | `tenon_od` | テノン外径 | Tenon OD |
| | `tenon_length` | テノン長 | Tenon length |
| | `cork_thickness` | コルク厚（片側） | Cork thickness (per side) |
| | `body_tenon_length` | 本体挿入部長 | Body tenon length |
| テーパ / Taper | `taper_from_cone` | 円錐角からテーパ導出 | Derive the taper from the cone angle |
| | `bore_large_id` | 大端ボア内径 | Large-end bore ID |
| ベンド / Bend | `bend_angle` | 曲げ角 | Bend angle |
| | `bend_start` | 曲げ開始位置 | Bend start |
| オクターブベント / Octave vent | `octave_vent` | オクターブベント | Octave vent |
| | `vent_position` | ベント位置（弧長比） | Vent position (arc fraction) |
| | `vent_dia` | ベント径 | Vent diameter |
| | `chimney_height` | チムニー高さ | Chimney height |
| | `seat_flat` | パッド座を平坦化 | Flatten the pad seat |
| | `key_mount_bosses` | キー取付ボス | Key mounting bosses |
| 製造 / Manufacturing | `min_wall` | 最小肉厚（検査） | Minimum wall thickness (check) |
| | `material` | 材料プリセット | Material preset |

### 2.5 本体 — Body (22)

| category | key | 日本語 | English |
|---|---|---|---|
| 寸法 / Dimensions | `body_arc_length` | 本体管長（弧長） | Body tube length (arc) |
| | `wall_thickness` | 肉厚 | Wall thickness |
| 接続 / Joint | `neck_joint` | ネックの繋ぎ方 | Neck joint |
| | `socket_length` | ネック受け深さ | Socket depth |
| | `socket_clearance` | はめあい隙間 | Fit clearance |
| テーパ / Taper | `taper_from_cone` | 円錐からテーパ導出 | Derive the taper from the cone |
| | `bore_small_id` | 小端ボア内径 | Small-end bore ID |
| | `bore_large_id` | 大端ボア内径 | Large-end bore ID |
| ボウ / Bow | `bow_angle` | ボウ曲げ角 | Bow angle |
| | `bow_start` | ボウ開始位置 | Bow start |
| | `bow_radius` | ボウ曲率半径 | Bow radius |
| ベル / Bell | `bell_length` | ベル長（弧長） | Bell length (arc) |
| | `bell_exit_dia` | ベル出口内径 | Bell exit ID |
| | `flare_power` | フレアの鋭さ | Flare power |
| 側孔 / Tone holes | `finger_holes` | 指孔の本数 | Finger hole count |
| | `hole_dia` | 指孔径 | Finger hole diameter |
| | `hole_chimney` | チムニー高さ | Chimney height |
| | `thumb_vent` | 親指孔 | Thumb hole |
| | `thumb_offset` | 親指孔オフセット | Thumb hole offset |
| | `thumb_dia` | 親指孔径 | Thumb hole diameter |
| 製造 / Manufacturing | `min_wall` | 最小肉厚（検査） | Minimum wall thickness (check) |
| | `material` | 材料プリセット | Material preset |

## 3. 選択肢 — Choices

| key | 日本語 | English |
|---|---|---|
| `elliptic` | 楕円 | Elliptical |
| `radial` | 円弧 | Radial |
| `straight` | ストレート | Straight |
| `step` | ステップ | Step |
| `curve` | カーブ | Curved |
| `rollover` | ロールオーバー | Rollover |
| `round` | ラウンド | Round |
| `square` | スクエア | Square |
| `horseshoe` | 馬蹄 | Horseshoe |
| `flat_sidewall` | フラットサイドウォール | Flat sidewall |
| `linear` | 直線 | Linear |
| `parabolic` | 放物（フレンチ系） | Parabolic (French) |
| `concave` | 凹（アメリカン系） | Concave (American) |
| `unfiled` | アンファイルド | Unfiled |
| `filed` | ファイルド（表皮を一直線まで剥がす） | Filed |
| `separate` | 別体（テノンで挿す） | Separate (tenon joint) |
| `integrated` | 一体（ネックまで1部品） | Integrated (one piece with neck) |
| `on` | 有効 | On |
| `off` | 無効 | Off |
| `m2.5` | M2.5 | M2.5 |
| `m3` | M3 | M3 |
| `resin` | レジン(光造形) | Resin (SLA/DLP) |
| `pla` | PLA(FDM) | PLA (FDM) |
| `petg` | PETG(FDM) | PETG (FDM) |
| `nylon_sls` | ナイロンPA12(SLS) | Nylon PA12 (SLS) |
| `resin_rigid` | 標準レジン(光造形) | Standard rigid resin (SLA/DLP) |
| `tpu` | TPU95A(FDM・弾性) | TPU 95A (FDM, elastic) |
| `resin_flex` | フレキシブルレジン(光造形) | Flexible resin (SLA/DLP) |
| `pp` | ポリプロピレン | Polypropylene |
| `cane` | ケーン(切削・参考) | Cane (machined, for reference) |
| `screw_beak` | ネジ（ビーク側） | Screws on the beak side |
| `screw_reed` | ネジ（リード側・逆締め） | Screws on the reed side (inverted) |
| `taper` | テーパ圧入（ネジなし） | Tapered press fit (no screws) |
| `elastic` | 弾性バンド（ネジなし） | Elastic band (no screws) |
| `line` | 線（軸方向のレール） | Line (rails along the axis) |
| `point` | 点（前後2列） | Point (two rows, front and back) |
| `face` | 面（背面に密着） | Face (flat against the back) |
| `none` | なし（バンド直接） | None (the band itself) |

## 4. 道具の語 — The tool's own vocabulary

判定と記録のための語。**ここを曖昧に訳すと、この道具が何を主張しているのか読めなくなる。**

| 日本語 | English | 意味 |
|---|---|---|
| 壁 | hard limit | 越えられない境界（`hard_min` / `hard_max`） |
| 帯 | recommended band | 勧める範囲（`min` / `max`）。越えても作れる |
| 可動域 | travel | つまみが実際に形を動かす範囲 |
| 出所 | source | 帯や壁の根拠。**空なら「記載なし」と出す**（発明しない） |
| 実測 | measured | 実物を測った値 |
| 借り物 | borrowed | 別サイズ・別銘柄から比で引いた未実測の値 |
| 掃引 | sweep | パラメータを機械的に振って壁を探すこと |
| 採寸 | survey | 実物を測って設計へ返す画面 |
| 検品 | inspection | 印刷物を測って設計と突き合わせること |
| かかり代 | reed overhang | リードがレールに載る幅の余り |
| 密着 | seating | リードがテーブルに当たっているか |
| 入稿 ZIP | print package | 印刷屋に渡す一式 |
| 仕様書 | spec sheet | |
| 部品表 | bill of materials (BOM) | |
| セット | set | マウスピース＋リガチャー＋リードの組 |
| 安全上の注意 | safety notice | |

## 5. 訳はどこに置いてあるか — Where the English lives

| 置き場 | 何が入っているか |
|---|---|
| `saxsketch/i18n/en.py` | パラメータ（`PARAMS`）・部品名・カテゴリ・選択肢・単位・判定の種別、<br>それに最初に英語化した画面とサーバの文（`MESSAGES`） |
| `saxsketch/i18n/en_cards.py` | **助言カード・警告・採寸・形が成立しない理由の散文**（869 本）。<br>`en.MESSAGES` へ合流する。量のためにファイルを分けただけで規則は同じ |
| `frontend/src/i18n.en.ts` | 画面の文字列（サーバを通らないぶん） |

**msgid は日本語そのもの**（gettext と同じ）。鍵を発明しないので、コードを読めば何が出るか分かる。
`{}` の名前は両言語で一致していなければならない —— ずれると実行時に `KeyError` で画面が落ちる。

### 訳が抜けても画面は落ちない。だから網で落とす

`i18n.t()` は訳が無ければ日本語をそのまま返す。これは画面を壊さないために正しいが、
**抜けても誰も気付かない**。`tests/test_i18n.py` が唯一の検出器で、3 段になっている:

1. **表に載っているか** —— `t("…")` の msgid を AST で拾って `MESSAGES` と突き合わせる。
2. **変数で引く msgid** —— 判定語（`t(v)`）・採寸の見出し（`t(f["label"])`）・印刷の推奨条件は
   AST に映らないので、**表そのものを読んで**突き合わせる。
3. **出てくる物に日本語が無いか** —— 3 サイズ × 全部品の `simulate` / `dimensions` /
   `survey_targets` / `param_bounds` / `bom` と、仕様書・部品表・入稿 ZIP を
   `en` で実際に組み立てて走査する。**これが本物の検出器** —— 1 と 2 は
   「表にあるか」しか見ないので、**引く側の配線が抜けていても緑のまま通る**。
   実際、寸法線・感度表・採寸フォームは素の `param_specs()` を読んでいて、
   表には訳があるのに画面には日本語が出ていた（3 だけが見つけた）。

逆向きの確認もした: **`ja` の出力が英語化の前と 1 バイトも変わらないこと**。
変わったらそれは国際化ではなく退行で、`t()` は `ja` では msgid をそのまま返すのだから
変わるはずがない。869 本を手で包むのは写し間違いが怖いので、包む作業自体を機械に
やらせ、3 サイズ × 全部品の出力を**包む前と後で JSON ごと突き合わせて**確かめた
（差分 0 バイト）。この突き合わせはリポジトリには入れていない —— 比較の相手が
「英語化の前」という一度きりの状態なので、残しても次から意味を持たない。
日本語の文を直したときに守るのは `tests/test_saxsketch.py` の既存の網のほう。
