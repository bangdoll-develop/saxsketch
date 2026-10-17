# -*- coding: utf-8 -*-
"""英語の表示文字列。**日本語が原本で、ここは訳。**

出典は `docs/glossary.md` の 1 枚きり。**ここで新しい訳語を発明しない** ——
相手はサックス吹きで、用語の誤りで道具の真贋を判断する。語を足すときは
用語表に書いてから、ここへ引く。

構造は `ParamSpec` と**別に**持つ。`label_en` を dataclass へ足す案を採らなかった
理由は 2 つ:

1. 98 本 ×（label・effect・source）で器が読めなくなる。器は「壁と帯の規則」を
   書く場所であって、文章を並べる場所ではない。
2. 言語を足すたびに dataclass を触ることになる。訳は**データ**であって
   スキーマではない。

欠けは `tests/test_i18n.py` が落とす（98 本すべてに label がある、など）。
"""
from __future__ import annotations

#: 画面・書き出しの一般の文。**鍵は日本語そのもの**（`i18n.t` の引数）。
#: 差し込みの `{}` は訳の側も同じ名前を持つ —— `tests/test_i18n.py` が突き合わせる。
MESSAGES: dict[str, str] = {
    # 楽器カタログ（`descriptor.json` / `templates/*.json` の label）
    "サクソフォン": "Saxophone",
    "アルトサクソフォン": "Alto saxophone",
    "ソプラノサクソフォン": "Soprano saxophone",
    "テナーサクソフォン": "Tenor saxophone",
    "マウスピース一式（MP＋リガチャー＋リード）":
        "Mouthpiece set (mouthpiece + ligature + reed)",
    "セット": "Set",

    # サーバのエラー文（`HTTPException(detail=...)`）
    "プロジェクトが開かれていません": "No project is open",
    "知らない楽器です: {what}": "Unknown instrument: {what}",
    "未知のセットです": "Unknown set",
    "このセットの部品に未実装のものがあります":
        "Some of the parts in this set are not implemented yet",
    "このコンポーネントは未実装です（後フェーズで追加予定）":
        "This component is not implemented yet (planned for a later phase)",
    "ファイルが見つかりません": "File not found",
    "ファイルが存在しません": "The file does not exist",
    "読み込み失敗: {why}": "Could not read it: {why}",
    "読み込みに失敗しました: {why}": "Loading failed: {why}",
    "形状生成に失敗: {why}": "Could not build the shape: {why}",
    "解析に失敗しました: {why}": "Analysis failed: {why}",
    "測定に失敗: {why}": "Measurement failed: {why}",
    "このコンポーネントは参照を重ねて表示できません":
        "This component cannot overlay a reference",
    "この部品はセットにありません": "This part is not in the set",
    "このコンポーネントに断面編集はありません":
        "This component has no section editing",
    "先に「凍結して編集用エクスポート」を実行してください":
        "Run “Freeze and export for editing” first",
    "編集済みモデルは未登録です": "No edited model is registered",
    "この形式は既定アプリで開きません: {ext}":
        "This format is not opened with the default app: {ext}",
    "{tool} が見つかりません。設定画面で実行パスを登録してください。":
        "{tool} was not found. Register its executable path under Settings.",
    "{tool} の実行ファイルが見つかりません: {path}":
        "The {tool} executable was not found: {path}",
    "知らない設定キー: {keys}": "Unknown setting keys: {keys}",
    "external_tools は辞書": "external_tools must be an object",
    "知らない外部ツール: {names}": "Unknown external tools: {names}",
    "「{part}」は凍結後にパラメータ（または参照する部品）が"
    "変更されています。編集済みモデルは古い形状です。"
    "外部編集をやり直すか、派生モデルを破棄してください。":
        "“{part}” had parameters (or a referenced part) changed after the freeze, so the "
        "edited model is an old shape. Redo the external edit, or discard the derived "
        "model.",
    "Host {host} は許可されていません。SaxSketch はローカル専用です。":
        "Host {host} is not allowed. SaxSketch is local-only.",
    "他のサイトからは操作できません。": "Other sites cannot drive this app.",

    # ---- 書き出し: 仕様書（spec.html）
    "仕様書": "Specification",
    "製作仕様書": "Build specification",
    "主要寸法": "Key dimensions",
    "断面図": "Sections",
    "設計パラメータ全値": "All design parameters",
    "カテゴリ": "Category",
    "パラメータ": "Parameter",
    "値": "Value",
    "部品表（BOM）": "Bill of materials (BOM)",
    "区分": "Kind",
    "品名": "Item",
    "数量": "Qty",
    "材料": "Material",
    "備考": "Note",
    "部品": "Part",
    "部品表 - {name}": "Bill of materials - {name}",
    "3Dプリント推奨条件": "Recommended 3D printing settings",
    "入稿データ": "Files for the print service",
    "STL: 汎用（全サービス対応）。単位 mm":
        "STL: universal (every service takes it). Units are mm",
    "STEP: 精密加工・寸法検証用（ロスレス）":
        "STEP: for precision machining and dimension checking (lossless)",
    "3MF: 単位・メタ情報付き（対応サービス向け）":
        "3MF: carries units and metadata (for services that accept it)",
    "設計時シミュレーション": "Simulation at design time",
    "音響予測（設計時シミュレーション）": "Acoustic prediction (simulated at design time)",
    "内容積（実効）": "Internal volume (effective)",
    "目標": "target",
    "音程傾向": "Pitch tendency",
    "セント": "cents",
    "指標は文献傾向に基づく推定値。絶対値ではなく設計比較の目安。":
        "The figures are estimates based on trends in the literature. Use them to compare "
        "designs, not as absolute values.",
    "この部品には断面図がありません。": "This part has no section drawing.",
    "楽器": "Instrument",
    "コンポーネント": "Component",
    "テンプレート": "Template",
    "構成": "Contents",
    "発行日": "Issued",
    "作成": "Produced by",
    "同梱の構成": "What is included",
    "セットの適合（部品どうし）": "How the set fits together (part to part)",
    "部品ごとに": "The parts are split into the folders",
    "のフォルダへ分かれています。": ".",
    "口に入れる部品です。": "This part goes in your mouth. ",
    "材料の食品接触適合性と、印刷後の洗浄・二次硬化を必ず確認してください。"
    "未硬化のレジンは皮膚感作性があります。PLA は約 55℃ で変形するため"
    "熱湯洗浄は不可。使用前に毎回、割れ・欠け・鋭い縁を点検してください。":
        "Check that the material is food-contact safe, and that the part is washed and "
        "post-cured after printing. Uncured resin is a skin sensitiser. PLA deforms at "
        "about 55 °C, so no boiling water. Inspect for cracks, chips and sharp edges "
        "before every use.",
    "この仕様書の寸法と音響指標は SaxSketch による推定であり、":
        "The dimensions and acoustic figures in this sheet are estimates made by "
        "SaxSketch, and ",
    "できあがる物の安全性・耐久性・適合性を保証するものではありません。":
        "nothing is warranted about the safety, durability or fitness of what you make.",
    "製作と使用は利用者の責任で行ってください。":
        "Making it and using it is at your own risk.",

    # ---- 書き出し: 印刷の推奨条件（`spec.PRINT_RECOMMENDATIONS`）
    "レジン（光造形 SLA/DLP）": "Resin (SLA/DLP)",
    "PLA（FDM）": "PLA (FDM)",
    "PETG（FDM）": "PETG (FDM)",
    "フレキシブルレジン（光造形）": "Flexible resin (SLA/DLP)",
    "ポリプロピレン（FDM・上級者向け）": "Polypropylene (FDM, for the experienced)",
    "ケーン（切削・参考）": "Cane (machined, for reference)",
    "ナイロン PA12（SLS・外注推奨）": "Nylon PA12 (SLS, best outsourced)",
    "積層ピッチ 0.05mm、造形向き: シャンク端を下、テーブル面をサポートから逃がす":
        "0.05 mm layers; orient with the shank end down and keep supports off the table "
        "face",
    "洗浄: IPA 2槽洗浄後、UV二次硬化を十分に（未硬化レジンの残留は不可）":
        "Washing: two IPA baths, then a full UV post-cure (no uncured resin may remain)",
    "口に触れる部品のため、食品接触適合（BPAフリー/歯科用等）レジンを推奨":
        "It touches the mouth, so a food-contact-safe resin (BPA-free, dental grade and "
        "the like) is recommended",
    "テーブル面を#600→#1000で軽く平面出しするとリードの密着が向上":
        "Lightly flatting the table at #600 then #1000 improves how the reed seats",
    "積層ピッチ 0.08〜0.12mm、ノズル 0.4mm、壁4周以上・充填率100%":
        "0.08–0.12 mm layers, 0.4 mm nozzle, 4+ perimeters, 100% infill",
    "造形向き: ビークを上、テーブル面を横向きにしてサポート痕を避ける":
        "Orient beak up with the table face sideways, to keep support marks off it",
    "気密性向上のため薄く食品用シーラント/エポキシでのコーティング推奨":
        "A thin food-safe sealant or epoxy coating is recommended for air-tightness",
    "耐熱が低い（〜55℃）。車内放置・熱湯洗浄は変形の原因":
        "Low heat resistance (~55 °C). Leaving it in a car or washing it in boiling water "
        "will deform it",
    "積層ピッチ 0.08〜0.12mm、壁4周以上・充填率100%":
        "0.08–0.12 mm layers, 4+ perimeters, 100% infill",
    "PLAより耐熱・耐久性が高く実用向き。ただし糸引きに注意":
        "More heat-resistant and durable than PLA, so more practical — but watch for "
        "stringing",
    "食品接触グレードのフィラメントを選定、印刷後の洗浄を徹底":
        "Choose a food-contact-grade filament and wash the part thoroughly after printing",
    "積層ピッチ 0.03〜0.05mm。薄い先端部を造形するため最小ピッチを推奨":
        "0.03–0.05 mm layers. The thin tip needs the finest layers you can print",
    "造形向き: リードを寝かせず立て、テーブル面をサポートから逃がす":
        "Stand the reed up rather than laying it flat, and keep supports off the table face",
    "二次硬化を過剰にかけると硬化して柔軟性が失われる。時間管理を厳密に":
        "Over-curing makes it stiff and kills the flexibility — time the post-cure strictly",
    "口に触れる部品のため、食品接触適合（歯科用等）レジンを選定すること":
        "It touches the mouth, so choose a food-contact-safe resin (dental grade and the "
        "like)",
    "反りが強く定着が難しい。PP専用ビルドシート必須":
        "It warps badly and is hard to make stick. A PP-specific build sheet is required",
    "積層ピッチ 0.10mm、庫内温度を保てる密閉プリンタを推奨":
        "0.10 mm layers, and an enclosed printer that holds chamber temperature",
    "耐薬品性・耐疲労性が高く、繰り返し曲がるリードに向く":
        "Good chemical and fatigue resistance, which suits a reed that flexes constantly",
    "3Dプリントではなく切削・成形が前提。出力データは形状の参照用":
        "Meant to be machined or formed rather than 3D printed. The exported data is a "
        "shape reference",
    "モデルの寸法はリードメイキングマシンの型出しに使用できる":
        "The model's dimensions can be used to cut a template for a reed-making machine",
    "オンライン印刷サービス（JLC3DP/PCBWay/Shapeways等）でSLS/MJF指定":
        "Order SLS/MJF from an online service (JLC3DP, PCBWay, Shapeways and the like)",
    "サポート不要で内部形状の再現性が最も高い。表面はやや多孔質":
        "No supports needed and the best reproduction of the internal shape; the surface "
        "is a little porous",
    "染色（黒）+ 表面シーリングを併用すると吸湿・衛生面で有利":
        "Dyeing (black) plus surface sealing helps with moisture pickup and hygiene",

    # ---- 書き出し: 入稿 ZIP の README
    "  主要寸法:\n": "  Key dimensions:\n",
    "  推奨材料: {material}\n": "  Recommended material: {material}\n",
    "SaxSketch 入稿パッケージ（セット）\n"
    "========================================\n"
    "プロジェクト: {name}\n"
    "用途: 管楽器のマウスピース一式（口に触れる部品）\n"
    "\n"
    "構成:\n"
    "{blocks}\n"
    "共通ファイル:\n"
    "  - spec.html  … 製作仕様書（全部品＋部品どうしの適合）\n"
    "  - bom.csv    … 部品表（先頭列がどの部品かを示す）\n"
    "\n"
    "各部品フォルダの中身:\n"
    "  - model.stl  … 3Dプリント用メッシュ（単位: mm）\n"
    "  - model.step … 精密CAD形状（寸法検証用）\n"
    "  - model.3mf  … 単位情報付きメッシュ\n"
    "\n"
    "注意: 食品接触適合材料を指定してください（口に入れる部品です）。\n"
    "      レジンは二次硬化と洗浄を十分に。PLA は約 55℃ で変形します。\n"
    "      寸法・音響指標は推定であり、できあがる物の安全性・耐久性・\n"
    "      適合性を保証するものではありません。\n"
    "部品ごとに推奨材料が違うことがあります（上記を参照）。\n":
        "SaxSketch print package (set)\n"
        "========================================\n"
        "Project: {name}\n"
        "For: a woodwind mouthpiece set (parts that touch the mouth)\n"
        "\n"
        "Contents:\n"
        "{blocks}\n"
        "Shared files:\n"
        "  - spec.html  … build specification (all parts, plus how they fit together)\n"
        "  - bom.csv    … bill of materials (the first column says which part)\n"
        "\n"
        "Inside each part's folder:\n"
        "  - model.stl  … mesh for 3D printing (units: mm)\n"
        "  - model.step … precise CAD shape (for checking dimensions)\n"
        "  - model.3mf  … mesh carrying unit information\n"
        "\n"
        "Note: specify a food-contact-safe material (these parts go in the mouth).\n"
        "      Post-cure and wash resin thoroughly. PLA deforms at about 55 °C.\n"
        "      The dimensions and acoustic figures are estimates; nothing is\n"
        "      warranted about the safety, durability or fitness of what you make.\n"
        "The recommended material can differ per part (see above).\n",
    "SaxSketch 入稿パッケージ\n"
    "========================================\n"
    "プロジェクト: {name}\n"
    "用途: 管楽器マウスピース（口に触れる部品）\n"
    "\n"
    "同梱ファイル:\n"
    "  - model.stl  … 3Dプリント用メッシュ（単位: mm）\n"
    "  - model.step … 精密CAD形状（寸法検証用）\n"
    "  - model.3mf  … 単位情報付きメッシュ\n"
    "  - spec.html  … 製作仕様書（寸法・印刷推奨条件）\n"
    "  - bom.csv    … 部品表\n"
    "\n"
    "主要寸法:\n"
    "{dims}\n"
    "\n"
    "推奨材料: {material}\n"
    "注意: 食品接触適合材料を指定してください（口に入れる部品です）。\n"
    "      レジンは二次硬化と洗浄を十分に。PLA は約 55℃ で変形します。\n"
    "      寸法・音響指標は推定であり、できあがる物の安全性・耐久性・\n"
    "      適合性を保証するものではありません。\n":
        "SaxSketch print package\n"
        "========================================\n"
        "Project: {name}\n"
        "For: a woodwind mouthpiece (a part that touches the mouth)\n"
        "\n"
        "Files included:\n"
        "  - model.stl  … mesh for 3D printing (units: mm)\n"
        "  - model.step … precise CAD shape (for checking dimensions)\n"
        "  - model.3mf  … mesh carrying unit information\n"
        "  - spec.html  … build specification (dimensions, printing settings)\n"
        "  - bom.csv    … bill of materials\n"
        "\n"
        "Key dimensions:\n"
        "{dims}\n"
        "\n"
        "Recommended material: {material}\n"
        "Note: specify a food-contact-safe material (this part goes in the mouth).\n"
        "      Post-cure and wash resin thoroughly. PLA deforms at about 55 °C.\n"
        "      The dimensions and acoustic figures are estimates; nothing is\n"
        "      warranted about the safety, durability or fitness of what you make.\n",
}

#: 部品名。`Component.label`。
COMPONENTS = {
    "mouthpiece": "Mouthpiece",
    "reed": "Reed",
    "ligature": "Ligature",
    "neck": "Neck",
    "body": "Body",
}

#: `ParamSpec.unit`。**記号はそのまま**（mm / °）で、日本語の語だけ訳す。
UNITS = {
    "比": "ratio",
    "度": "°",
    "指数": "exp.",
    "本": "holes",
}

#: `ParamSpec.category`。日本語のカテゴリ名で引く（部品をまたいで共有する）。
CATEGORIES = {
    "フェイシング": "Facing",
    "バッフル": "Baffle",
    "チェンバー": "Chamber",
    "ボア": "Bore",
    "ウィンドウ": "Window",
    "外形": "Outline",
    "製造": "Manufacturing",
    "寸法": "Dimensions",
    "プロファイル": "Profile",
    "レール": "Rails",
    "カット": "Cut",
    "バンド": "Band",
    "締結": "Closure",
    "接触": "Contact",
    "テーパ": "Taper",
    "ベンド": "Bend",
    "オクターブベント": "Octave vent",
    "接続": "Joint",
    "ボウ": "Bow",
    "ベル": "Bell",
    "側孔": "Tone holes",
}

#: `Choice.label`。`value` で引く（部品をまたいで共有する）。
CHOICES = {
    "elliptic": "Elliptical",
    "radial": "Radial",
    "straight": "Straight",
    "step": "Step",
    "curve": "Curved",
    "rollover": "Rollover",
    "round": "Round",
    "square": "Square",
    "horseshoe": "Horseshoe",
    "flat_sidewall": "Flat sidewall",
    "linear": "Linear",
    "parabolic": "Parabolic (French)",
    "concave": "Concave (American)",
    "unfiled": "Unfiled",
    "filed": "Filed (bark cut straight across)",
    "separate": "Separate (tenon joint)",
    "integrated": "Integrated (one piece with the neck)",
    "on": "On",
    "off": "Off",
    "m2.5": "M2.5",
    "m3": "M3",
    "resin": "Resin (SLA/DLP)",
    "pla": "PLA (FDM)",
    "petg": "PETG (FDM)",
    "nylon_sls": "Nylon PA12 (SLS)",
    "tpu": "TPU 95A (FDM, elastic)",
    "resin_flex": "Flexible resin (SLA/DLP)",
    "pp": "Polypropylene",
    "cane": "Cane (machined, for reference)",
    "resin_rigid": "Standard rigid resin (SLA/DLP)",
    "screw_beak": "Screws on the beak side",
    "screw_reed": "Screws on the reed side (inverted)",
    "taper": "Tapered press fit (no screws)",
    "elastic": "Elastic band (no screws)",
    "line": "Line (rails along the axis)",
    "point": "Point (two rows, front and back)",
    "face": "Face (flat against the back)",
    "none": "None (the band itself)",
}

#: `schema.LIMIT_KIND_LABELS`。クランプ報告の文面に入る。
LIMIT_KINDS = {
    "geometry": "geometric requirement",
    "manufacturing": "manufacturing constraint",
    "convention": "conventional range",
    "unclassified": "unclassified limit",
}

#: パラメータ。`PARAMS[component][key]` に `label` / `effect` / `source`。
#: `source` は日本語側が空なら持たない（**空欄を埋めるために出所を発明しない**）。
PARAMS: dict[str, dict[str, dict[str, str]]] = {
    "mouthpiece": {
        "tip_opening": {
            "label": "Tip opening",
            "effect": "Larger blows more freely and gives more volume, but asks for "
                      "more control and more air.",
        },
        "facing_length": {
            "label": "Facing length",
            "effect": "The single largest influence on brightness. Longer gives richer "
                      "overtones and a more open sound.",
            "source": "No stated source for the band. The hard limits were measured by "
                      "sweep (3.0 at the bottom is the edge of the dead band; 50.0 at the "
                      "top is where the sweep stopped = beyond that is unmeasured).",
        },
        "facing_curve": {
            "label": "Facing curve",
            "effect": "Character of the blowing feel. Elliptical = modern and quick to "
                      "respond; Radial = classical.",
        },
        "tip_rail_width": {
            "label": "Tip rail width",
            "effect": "Narrower responds faster but is noisier.",
            "source": "No stated source for the band. The hard limits were measured by "
                      "sweep (0.0 at the bottom is the edge of the dead band; 4.3 at the "
                      "top is just short of where the tip cavity degenerates).",
        },
        "tip_rail_thickness": {
            "label": "Tip rail thickness",
            "effect": "Material left at the tip. Thinner speaks more lightly but chips "
                      "more easily. The beak slope is derived from this as well.",
            "source": "No stated source for the band. 4.5 at the top is where the sweep "
                      "stopped (beyond is unmeasured); 0.0 at the bottom is geometry "
                      "(there is no negative wall).",
        },
        "tip_chamfer": {
            "label": "Tip front-edge chamfer",
            "effect": "How much the tip is cut away from the reed side. On the real part "
                      "only 0.25 mm of front face is left. At 0 a square wall as thick as "
                      "the tip rail stands at the tip.",
            "source": "0 = no chamfer (negative has no shape meaning; the sweep also "
                      "showed the shape stops moving below 0). 3.2 at the top is where the "
                      "sweep stopped = beyond that is unmeasured.",
        },
        "side_rail_width": {
            "label": "Side rail width",
            "effect": "Narrower plays more efficiently but is more sensitive to reed "
                      "mis-speaks.",
            "source": "No stated source for the band. 6.0 at the top is where the sweep "
                      "stopped (beyond is unmeasured); 0.0 at the bottom is geometry "
                      "(there is no negative width; the sweep disagreed depending on the "
                      "axis).",
        },
        "table_angle": {
            "label": "Table angle",
            "effect": "Tilt of the table plane relative to the bore axis. The real part is "
                      "about 4.2°, and it decides how deeply the reed seats inside the "
                      "body.",
            "source": "The WindyCity reference measures 4.18° (cad/windycity/). The hard "
                      "limits are where the sweep stopped (−2.0 / 11.0; beyond either is "
                      "unmeasured).",
        },
        "baffle_type": {
            "label": "Baffle type",
            "effect": "The most important single factor for tonal character. Straight = "
                      "dark and soft / Step = balanced (this is what the WindyCity "
                      "reference measures as) / Curved = metallic and aggressive / "
                      "Rollover = a straight baffle with the shoulder rounded off, in "
                      "between.",
        },
        "baffle_height": {
            "label": "Baffle height",
            "effect": "How far the ceiling immediately above the reed is brought down. "
                      "Higher is brighter and edgier; 0 gives a classical dark tone. "
                      "**Negative raises the ceiling above the reference** (darker still).",
            "source": "0 = no baffle. Above 5.0 and below −2.3 the slider spins free "
                      "(confirmed by sweep; alto is the binding size).",
        },
        "baffle_plateau": {
            "label": "Baffle plateau length",
            "effect": "How long the ceiling above the reed stays flat, as a fraction of "
                      "the bore start. Active for Step and Rollover, where longer makes "
                      "the shelf more pronounced. For Straight and Curved the type "
                      "definition restricts it to a very short range. **The ends of the "
                      "band do nothing on any type** (they round into each type's "
                      "effective range).",
            "source": "A union covering all four types. The effective range is per type "
                      "(profiles._PLATEAU_RANGE), and the sweep also showed no movement "
                      "past the band ends on any of the three sizes.",
        },
        "baffle_step_rise": {
            "label": "Step rise",
            "effect": "Active for Step. How abruptly the ceiling rises at the end of the "
                      "shelf. 0 is the gentle shoulder as measured; larger makes a sharper "
                      "step.",
            "source": "0 = the shoulder as measured (negative is inert in the `_v_step` "
                      "branch). 2.85 at the top is where the sweep stopped = beyond that "
                      "is unmeasured.",
        },
        "baffle_curvature": {
            "label": "Baffle curvature",
            "effect": "Active for Curved. Positive holds the ceiling low and squeezes the "
                      "airway (bright, aggressive); negative opens early into a scoop "
                      "(dark); 0 is the same straight line as Straight.",
            "source": "0 = straight. −1.7 at the bottom is the edge of the dead band "
                      "measured by sweep (soprano/tenor bind); 3.0 at the top is where it "
                      "stopped = beyond that is unmeasured.",
        },
        "rollover_radius": {
            "label": "Rollover radius",
            "effect": "Active for Rollover. Roundness of the shoulder; smaller feels "
                      "edgier. **It stops having any effect once it is large**, because "
                      "the rounding has spread over everything behind the shelf and the "
                      "radius drops out of the formula.",
            "source": "Edges of the dead band measured by sweep (0.5 / 21.0, each set by "
                      "the binding size). The top differs by size, 21.0–31.5 = it scales "
                      "with the bore start.",
        },
        "throat_ratio": {
            "label": "Throat area ratio",
            "effect": "Narrowest cross-section as a ratio of the bore. Small = brighter "
                      "with more resistance; large = darker and fatter.",
            "source": "The WindyCity reference measures 1.0 (no constriction). Both hard "
                      "limits, 0.2 and 1.75, are where the sweep stopped = beyond either "
                      "is unmeasured.",
        },
        "chamber_ratio": {
            "label": "Chamber area ratio",
            "effect": "Largest chamber cross-section as a ratio of the narrowest throat. "
                      "Large = more internal volume, darker and fatter. Below 1 the "
                      "chamber is narrower than the throat (not something the measured "
                      "shape does).",
            "source": "The WindyCity reference measures 1.0 (no bulge). 0.05 at the bottom "
                      "is the lowest ratio that still means anything (the "
                      "`_chamber_weight` guard); 5.0 at the top is where the sweep stopped "
                      "= beyond that is unmeasured.",
        },
        "chamber_shape": {
            "label": "Chamber shape",
            "effect": "Round = smooth overtones / Square = complex, vintage-style "
                      "overtones / Horseshoe = fat and focused / Flat sidewall = bright "
                      "with a core.",
        },
        "bore_dia": {
            "label": "Bore diameter",
            "effect": "The fit onto the neck cork. Directly tied to the pitch reference.",
            "source": "The band is the template's measured value ±1.0 mm. The hard limits "
                      "were measured by sweep (the top is one step below the shank "
                      "diameter = the limit at which a shank still exists; the bottom was "
                      "walked 10 mm past the band end = beyond that is unmeasured).",
        },
        "bore_length": {
            "label": "Bore length",
            "effect": "Length of the cylindrical bore. The cork insertion depth plus a few "
                      "mm is the floor.",
            "source": "The band is 0.5–1.25× the template's measured value (a shared "
                      "absolute range can collapse the shape on its own). The hard limits "
                      "were measured by sweep (the top is just before the window drops "
                      "below 2.0 mm = overall length − 6.5 mm; the bottom is just before "
                      "the bore loses its length).",
        },
        "cork_depth": {
            "label": "Cork insertion depth",
            "effect": "Standard insertion onto the neck. The reference position for pitch "
                      "checks.",
            "source": "Not a dimension but a tuning amount (a band covering the three "
                      "sizes' derived values, 14.4–23.5).",
        },
        "window_length": {
            "label": "Window length",
            "effect": "Length of the vibrating part of the reed. Longer gives richer lows. "
                      "**When raising it changes nothing**, it is being capped by the "
                      "chamber-to-bore transition.",
            "source": "A band covering the three measured sizes, 27.3–41.1 mm (the top end "
                      "is a dead band; confirmed by sweep).",
        },
        "chamber_to_bore_mm": {
            "label": "Chamber-to-bore transition",
            "effect": "The length that must always be left between the back of the window "
                      "and the start of the bore. Window length is capped here, so shrink "
                      "this when the window will not grow. Shorter crowds the chamber; "
                      "longer closes the window sooner.",
            "source": "A bare 4.0 carried over from the old implementation (not a "
                      "geometric requirement).",
        },
        "reed_width": {
            "label": "Reed width (nominal)",
            "effect": "Nominal width of the reed you intend to use. **It does not drive "
                      "the shape** (the actual width and the actual opening are taken "
                      "separately).",
            "source": "The commercial reed standard width. **Measured on five real reeds "
                      "in each of the three sizes** (2026-09-21 / 22 / 23; the "
                      "representative value is cane #1 / #2 / #2).",
        },
        "beak_height": {
            "label": "Beak height",
            "effect": "Height above the table at the bite point (a quarter of the overall "
                      "length back from the tip) — how far your mouth opens on it. The "
                      "default is provisional, so replacing it with a measurement is "
                      "recommended. Above the top end the ridge only moves outside the "
                      "body and the mouth opening stops changing.",
            "source": "The bottom end, 0.35×, is provisional (the 0.55× default is not a "
                      "measurement either). The hard limits were measured in B-4b — the "
                      "top is the full body height at the bite point, the bottom is where "
                      "the ridge starts to slope downward toward the front. The old "
                      "source, '0.9·body_dia', was wrong.",
        },
        "body_dia": {
            "label": "Body diameter",
            "effect": "The fit for the ligature (maximum diameter). **It has to be at "
                      "least the shank diameter** — below that the shoulder swells outward "
                      "and the 'maximum diameter' is no longer the maximum.",
            "source": "Hard limits by sweep (B-4a): the bottom is the shank diameter "
                      "itself (a relation), the top is 54.0 mm, up to which a single solid "
                      "was confirmed (beyond that is unmeasured).",
        },
        "shank_dia": {
            "label": "Shank diameter",
            "effect": "Outside diameter of the parallel section that goes onto the neck. "
                      "It sets the size of the step at the shoulder. **It has to be larger "
                      "than the bore and no larger than the maximum diameter.**",
            "source": "Hard limits by sweep (B-4a): the bottom is the bore diameter, the "
                      "top is the maximum diameter (both relations). The latches are one "
                      "step above the bore-diameter limit, and 54.0 mm.",
        },
        "shank_length": {
            "label": "Shank length",
            "effect": "Length of the parallel shank section. Longer makes it a long-shank "
                      "design. At 0 the parallel section disappears and the taper runs "
                      "from the maximum diameter to the end. The heel of the table is "
                      "placed by subtracting this from the overall length, so it also "
                      "affects how the reed seats.",
            "source": "0 = no parallel section (negative has no shape meaning). The top is "
                      "one step inside the point, found by sweep (B-4a), where the heel "
                      "hits the floor and the shape freezes.",
        },
        "shoulder_ratio": {
            "label": "Shoulder length ratio",
            "effect": "Length of the shoulder tapering from the maximum diameter down to "
                      "the shank, as a fraction of where the maximum diameter sits. That "
                      "position is overall length − (shank length + shoulder), so this "
                      "ratio and the shank length together place the maximum diameter. "
                      "Tenor measures 0.139. The 'end of shoulder' handle in the section "
                      "tab moves the two together, so the parallel section can be "
                      "stretched without moving the maximum diameter.",
            "source": "The top, 0.45, is needed so it can pair with a shank length of 0 "
                      "(tenor measures 0.3605). The hard limit is one step inside the "
                      "point, found by sweep (B-4a), where the heel hits the floor and the "
                      "shape freezes.",
        },
        "body_waist": {
            "label": "Body waist",
            "effect": "How much the body between the tip and the maximum diameter is "
                      "swelled. 0 is the measured shape. Both ends are pinned, so the rise "
                      "at the tip and the maximum diameter do not change (±0.77 mm in the "
                      "middle on alto).",
            "source": "A distortion away from the measured profile (0 is as measured). The "
                      "hard limits do not come from a sweep (B-4b) but from monotonicity "
                      "of the generatrix — at +0.0726 the maximum diameter leaves the "
                      "apex, and at −0.1614 a dip appears in the middle of the body "
                      "(u≈0.23).",
        },
        "shoulder_fullness": {
            "label": "Shoulder fullness",
            "effect": "How the shoulder curves from the maximum diameter down to the "
                      "shank. 0 is the measured shape; +1 makes the generatrix straight, "
                      "i.e. a cone (+0.92 mm in the middle on alto). Negative bows the "
                      "shoulder outward, but below −0.36 the middle of the shoulder "
                      "becomes thinner than the shank. With +1 and a shank length of 0 you "
                      "get a perfect cone from the maximum diameter to the end.",
            "source": "The hard limits come from monotonicity of the generatrix (measured "
                      "in B-4b) — at −0.3607 the shoulder drops below the shank diameter, "
                      "at +1.8633 the middle of the shoulder bulges. The old source, 'the "
                      "domain itself', **was not the domain on either side**.",
        },
        "overall_length": {
            "label": "Overall length",
            "effect": "Overall length of the mouthpiece.",
            "source": "±25% of the template's measured value (an absolute range would "
                      "allow 'a tenor as long as a soprano'). Hard limits by sweep (B-4a): "
                      "the bottom is a relation to the bore length, the top is 1.8×, up to "
                      "which a single solid was confirmed (beyond that is unmeasured).",
        },
        "min_wall": {
            "label": "Minimum wall thickness",
            "effect": "Floor for 3D-print strength. 2 mm or more is recommended for resin.",
            "source": "Floor for 3D-print strength (2 mm or more recommended for resin).",
        },
        "material": {
            "label": "Material preset",
            "effect": "Feeds the recommended print settings and the food-contact warnings "
                      "on the spec sheet.",
        },
    },
    "reed": {
        "reed_length": {
            "label": "Reed length",
            "effect": "Standard length. The heel has to land on the ligature seat.",
        },
        "tip_width": {
            "label": "Tip width",
            "effect": "Match it to the table width of the mouthpiece. If it is off, air "
                      "leaks past the side rails.",
        },
        "heel_width": {
            "label": "Heel width",
            "effect": "Width at the heel. Together with the tip width it sets the taper.",
        },
        "tip_thickness": {
            "label": "Tip thickness (centre)",
            "effect": "Sets how the tip closes and how it starts to speak. **As a lever on "
                      "stiffness it is the weakest there is** (its share of the deflection "
                      "in the front quarter is around 6%). The print floor also lands here.",
        },
        "heel_thickness": {
            "label": "Heel thickness",
            "effect": "Thickness of the bark (uncut) section. A standard dimension. It "
                      "matters for seating against the table.",
        },
        "heel_edge_thickness": {
            "label": "Heel edge thickness",
            "source": "The top of the band is the maximum over fifteen real reeds "
                      "(alto 2026-09-21 / soprano 09-22 / tenor 09-23). The hard limit "
                      "is the heel thickness − 0.2.",
            "effect": "Sets the arc of the original cane tube (the section becomes a "
                      "shallow dome). The larger the difference from the centre thickness, "
                      "the deeper the arc. Real reeds measure 1.5–1.65 over five alto, "
                      "1.0–1.45 over five soprano and 1.35–2.45 over five tenor (the 2.45 "
                      "is synthetic).",
        },
        "vamp_length": {
            "label": "Vamp length",
            "effect": "Where the cut begins. Longer is more flexible and favours the low "
                      "register; shorter adds resistance. **As a lever on stiffness it is "
                      "among the strongest** (±6 mm gives ±45–75%).",
        },
        "profile_curve": {
            "label": "Profile curve",
            "effect": "Character of resistance and response. Concave keeps the tip thin "
                      "and starts quickly.",
        },
        "spine_ratio": {
            "label": "Spine width ratio",
            "effect": "Thinning exponent across the width. Larger leaves a wider flat "
                      "centre (the spine) and a stronger core.",
        },
        "side_rail_thin": {
            "label": "Side rail thinning ratio",
            "effect": "Edge thickness ÷ centre thickness. Smaller is more flexible and "
                      "speaks more easily, but lasts less.",
        },
        "tip_corner_r": {
            "label": "Tip corner radius",
            "effect": "The tip corner seen from above. Match it to the tip rail shape of "
                      "the mouthpiece.",
        },
        "tip_curve_depth": {
            "label": "Tip curve depth",
            "source": "The top of the band is set so that 2.932, the largest value "
                      "back-calculated from fifteen real reeds (2026-09-21 / 22 / 23), "
                      "fits inside it. The hard limit is the depth at which the "
                      "front-edge arc still reaches the sides (half the tip width, as "
                      "long as the heel is no wider).",
            "effect": "How far the front edge drops back — how much further back the "
                      "corners sit than the centre. At 0 the front edge is straight and "
                      "the corners stick out past the tip rail. Back-calculated from real "
                      "reeds: 1.91–2.61 over five alto, 2.48–2.72 over five soprano, "
                      "2.76–2.93 over five tenor.",
        },
        "file_cut": {
            "label": "Cut type",
            "effect": "How far the bark is taken off the cane. Filed removes it back to a "
                      "straight line behind the end of the vamp curve, leaving a band of "
                      "cut bark in between. Tends to be brighter and quicker to respond.",
        },
        "material": {
            "label": "Material preset",
            "effect": "Derives a stiffness-equivalent value and a resonance frequency from "
                      "Young's modulus and density. The practical strength floor for each "
                      "process (FDM / resin / machining) is taken from here too.",
        },
        "min_layer": {
            "label": "Layer height",
            "effect": "Sets the resolution floor (a tip thinner than three times this "
                      "cannot be built). Around 0.02–0.05 for resin, 0.08–0.20 for FDM.",
        },
    },
    "ligature": {
        "band_width": {
            "label": "Band width",
            "effect": "Wider constrains the reed more and gives a more focused sound; "
                      "narrower lets it ring freely.",
        },
        "band_thickness": {
            "label": "Band thickness",
            "effect": "Stiffness. Thinner flexes and rings, but cracks more easily under "
                      "the clamping load.",
        },
        "seat_setback": {
            "label": "Seat setback (from the maximum diameter)",
            "effect": "How far forward the band is pulled from the maximum diameter. "
                      "Further forward is brighter and quicker to respond.",
        },
        "clearance": {
            "label": "Fit clearance",
            "effect": "Gap to the outside of the mouthpiece, allowing for 3D-print "
                      "tolerance. For an elastic band, make it negative so it becomes "
                      "interference.",
        },
        "reed_clearance": {
            "label": "Reed clearance",
            "effect": "Extra relief behind the reed. Smaller leaves more interference.",
        },
        "closure": {
            "label": "Closure type",
            "effect": "Inverted = the screws are on the reed side, and a plate bridging "
                      "the slit holds the reed down. Elastic = no screws; you stretch it "
                      "on.",
        },
        "press_depth": {
            "label": "Press depth",
            "effect": "For a tapered press fit, how far past the no-load resting position "
                      "it is pushed. It sets the interference on both the cone and the "
                      "table.",
        },
        "screw_count": {
            "label": "Screw count",
            "effect": "Two clamps evenly; one is simpler and lighter.",
        },
        "screw_size": {
            "label": "Screw size",
            "effect": "A commercial machine screw. The required length is computed and "
                      "listed on the bill of materials.",
        },
        "boss_height": {
            "label": "Screw boss height",
            "effect": "Height of the ears. Higher is easier to tighten but sticks out; too "
                      "low and the screw hole breaks out of the ear.",
        },
        "slit_width": {
            "label": "Slit width",
            "effect": "The take-up. Wider allows more tightening, but closing it fully "
                      "deforms more.",
        },
        "contact_type": {
            "label": "Reed contact type",
            "effect": "Line or point = few support points, so the centre vibrates freely "
                      "and sounds bright. Face = full contact on the back, giving a "
                      "stronger core.",
        },
        "contact_count": {
            "label": "Contact count (across)",
            "effect": "More spreads the constraint more evenly. Point contacts come in two "
                      "rows, front and back, so the total is doubled.",
        },
        "material": {
            "label": "Material preset",
            "effect": "Strength against the clamping load. Also feeds the recommended "
                      "print settings on the spec sheet.",
        },
        "min_wall": {
            "label": "Minimum wall thickness",
            "effect": "Floor for the printability check. On an inverted ligature it is the "
                      "thickness of the bridge itself.",
        },
    },
    "neck": {
        "neck_length": {
            "label": "Neck length (arc)",
            "effect": "Centre-line length of the tube from the mouthpiece end to the body "
                      "end. It affects the pitch of the whole instrument.",
        },
        "bore_small_id": {
            "label": "Small-end bore ID",
            "effect": "Narrowest inside diameter at the mouthpiece end — the tightest "
                      "throat in the whole instrument.",
        },
        "wall_thickness": {
            "label": "Wall thickness",
            "effect": "Tube wall. Directly tied to air-tightness and strength. Around 2 mm "
                      "is recommended for resin.",
        },
        "tenon_od": {
            "label": "Tenon OD",
            "effect": "Outside diameter of the section the mouthpiece slides over — the "
                      "base the cork is wound onto.",
        },
        "tenon_length": {
            "label": "Tenon length",
            "effect": "Length of the cork seat, i.e. how far the mouthpiece can be pushed "
                      "on.",
        },
        "cork_thickness": {
            "label": "Cork thickness (per side)",
            "effect": "Thickness of the cork wound onto the tenon, per side. Used to work "
                      "out the required bore diameter.",
        },
        "body_tenon_length": {
            "label": "Body tenon length",
            "effect": "Length of the stepped section that goes into the body socket.",
        },
        "taper_from_cone": {
            "label": "Derive the taper from the cone angle",
            "effect": "On = the large-end diameter is computed from the half apex angle "
                      "in the descriptor; Off = give the large-end diameter directly.",
        },
        "bore_large_id": {
            "label": "Large-end bore ID",
            "effect": "Inside diameter at the body end. Used when taper derivation is off.",
        },
        "bend_angle": {
            "label": "Bend angle",
            "effect": "0 is straight. The tilt of a gooseneck — brings the posture and the "
                      "look closer to the real thing.",
        },
        "bend_start": {
            "label": "Bend start",
            "effect": "Straight length from the end of the tenon to where the bend begins.",
        },
        "octave_vent": {
            "label": "Octave vent",
            "effect": "Cuts the register hole. The key mechanism is a separate part "
                      "(the player covers it, or it is plugged).",
        },
        "vent_position": {
            "label": "Vent position (arc fraction)",
            "effect": "Position of the vent centre as a fraction of the overall length.",
        },
        "vent_dia": {
            "label": "Vent diameter",
            "effect": "Diameter of the register hole.",
        },
        "chimney_height": {
            "label": "Chimney height",
            "effect": "The raised collar around the vent (pip / pad seat). 0 for none.",
        },
        "seat_flat": {
            "label": "Flatten the pad seat",
            "effect": "Makes the top of the chimney a flat bearing face for a pad "
                      "(for a key mechanism added later).",
        },
        "key_mount_bosses": {
            "label": "Key mounting bosses",
            "effect": "Generates post seats on either side of the vent (for a key "
                      "mechanism added later; off by default).",
        },
        "min_wall": {
            "label": "Minimum wall thickness (check)",
            "effect": "Floor for print strength. Warns when the wall is thinner than this.",
        },
        "material": {
            "label": "Material preset",
            "effect": "Air-tightness and strength. Tubes need airtight layers, so resin is "
                      "recommended.",
        },
    },
    "body": {
        "body_arc_length": {
            "label": "Body tube length (arc)",
            "effect": "Centre-line length from the large end of the neck to the bell exit. "
                      "The length of the cone is the backbone of the instrument's pitch.",
        },
        "wall_thickness": {
            "label": "Wall thickness",
            "effect": "Tube wall. Directly tied to air-tightness and strength. Around 2 mm "
                      "is recommended for resin.",
        },
        "neck_joint": {
            "label": "Neck joint",
            "effect": "One piece is common on straight sopranos: fewer joints, but the "
                      "posture cannot be adjusted. Acoustically the two are identical.",
        },
        "socket_length": {
            "label": "Socket depth",
            "effect": "For a separate neck, the depth of the hole that receives the neck "
                      "spigot.",
        },
        "socket_clearance": {
            "label": "Fit clearance",
            "effect": "For a separate neck, the gap per side between socket and spigot.",
        },
        "bore_small_id": {
            "label": "Small-end bore ID",
            "effect": "Inside diameter of the cone throat (the tube end on the mouthpiece "
                      "side). Used when taper derivation is off.",
        },
        "bore_large_id": {
            "label": "Large-end bore ID",
            "effect": "Inside diameter at the end, not counting the bell flare. Used when "
                      "taper derivation is off.",
        },
        "taper_from_cone": {
            "label": "Derive the taper from the cone",
            "effect": "On = use the same slope as the missing cone in the descriptor; "
                      "Off = give both end diameters directly.",
        },
        "bow_angle": {
            "label": "Bow angle",
            "effect": "0 is straight (straight soprano / straight alto). 180 folds it back "
                      "into a U.",
        },
        "bow_start": {
            "label": "Bow start",
            "effect": "Straight length from the start of the body tube to where the bend "
                      "begins.",
        },
        "bow_radius": {
            "label": "Bow radius",
            "effect": "Radius of the fold. **It has to be larger than the outer radius of "
                      "the tube, or the section folds back through itself** (the floor "
                      "depends on size and wall thickness, so it cannot be expressed as a "
                      "slider minimum; impossible values are rejected with a reason).",
        },
        "bell_length": {
            "label": "Bell length (arc)",
            "effect": "Length of the section where the flare begins. 0 for no flare (a "
                      "plain cone).",
        },
        "bell_exit_dia": {
            "label": "Bell exit ID",
            "effect": "Inside diameter of the opening. It cannot be narrower than the end "
                      "of the cone (real bells do not taper inward).",
        },
        "flare_power": {
            "label": "Flare power",
            "effect": "Larger opens up more abruptly near the end. 1 flares linearly.",
        },
        "finger_holes": {
            "label": "Finger hole count",
            "effect": "Opened in order from all-closed to make a scale (the same layout as "
                      "a recorder). 0 means no holes — just the tube. The upper limit is "
                      "set by the number of scale steps.",
        },
        "hole_dia": {
            "label": "Finger hole diameter",
            "effect": "Wider raises the pitch of the open hole (i.e. brings it closer to "
                      "a true open end). The practical ceiling for a finger to seal is "
                      "around φ12.",
        },
        "hole_chimney": {
            "label": "Chimney height",
            "effect": "The rise from the outer surface. Higher lowers the pitch of the "
                      "open hole. **The main lever for tuning a keyless instrument, where "
                      "the hole positions cannot move** (4-B.2c).",
        },
        "thumb_vent": {
            "label": "Thumb hole",
            "effect": "The octave vent on the body side (left thumb). On a real "
                      "instrument a single key switches between this and the neck vent. "
                      "It is not a step in the scale, so the fingering chart always "
                      "treats it as closed.",
        },
        "thumb_offset": {
            "label": "Thumb hole offset",
            "effect": "Upstream from the octave (+12 semitone) position. Independent of "
                      "the number of finger holes.",
        },
        "thumb_dia": {
            "label": "Thumb hole diameter",
            "effect": "It is for the register, so it is narrower than a finger hole.",
        },
        "min_wall": {
            "label": "Minimum wall thickness (check)",
            "effect": "Floor for print strength. Warns when the wall is thinner than this.",
        },
        "material": {
            "label": "Material preset",
            "effect": "Air-tightness and strength. Tubes need airtight layers, so resin is "
                      "recommended.",
        },
    },
}


from . import en_cards as _cards   # noqa: E402  （下で合流させるので末尾に置く）

#: 助言カード・警告・採寸の文（便 D 後半）。量が多いので別ファイルに分けてある。
#: **合流先は同じ `MESSAGES`** —— 引く側に 2 つの表があると、どちらに足すかで
#: 迷いが出るし、網（`tests/test_i18n.py`）も 2 か所を見ることになる。
MESSAGES.update(_cards.MESSAGES)
