# -*- coding: utf-8 -*-
"""助言カード・警告・採寸の文の英訳。**`en.MESSAGES` へ合流する。**

`en.py` から分けてあるのは量のため（700 本超）。中身の規則は同じ ——
**msgid は日本語そのもの**で、`{}` の名前は両言語で一致していなければならない
（`tests/test_i18n.py` が突き合わせる）。

訳語は `docs/glossary.md` が唯一の出典。ここで新しい訳を発明しない。
"""
from __future__ import annotations

MESSAGES: dict[str, str] = {}

#: `acoustics/` —— 音響の指標・OpenWind の橋渡し・内容積。
MESSAGES.update({
    "相対比較用の推定指標（文献傾向ベース）。数値の絶対値ではなく変化方向を参考に。":
        "Estimated figures for comparing designs, based on trends in the "
        "literature. Read the direction they move, not the absolute numbers.",
    " がモデルの有効範囲の外にあります。**この指標はそこで頭打ちになっていて、"
    "動かしても変わりません（回帰を当てた範囲の外なので外挿していません）。"
    "形そのものは変わっているので、断面タブと寸法を見てください。":
        " is outside the range the model was fitted over. **The figure is "
        "pinned there and will not move**, because we do not extrapolate past "
        "the range the regression was fitted to. The shape itself is still "
        "changing, so look at the section tab and the dimensions.",
    "明るさ": "Brightness",
    "パワー": "Power",
    "抵抗感": "Resistance",
    "柔軟性": "Flexibility",
    "エッジ": "Edge",
    "{label} {v}{unit}（有効範囲 {lo}〜{hi}{unit2}）":
        "{label} {v}{unit} (valid range {lo}–{hi}{unit2})",

    "推定モデル上の逆算提案です。適用前に差分を確認してください。":
        "A suggestion solved back through the estimating model. Check the "
        "differences before you apply it.",

    "印象プレビュー（簡易加算合成）。物理的な発音は上のタブ"
    "「物理モデル(OpenWind)」で試聴できます。":
        "An impression preview (simple additive synthesis). For a physical "
        "model of the sound, use the \"Physical model (OpenWind)\" tab above.",

    "側孔は弧長の昇順で渡すこと（区間の切れ目が決まらない）":
        "Tone holes must be passed in ascending arc length, otherwise the "
        "segment boundaries are undefined",
    " 絶対音程でなくパラメータ変化の方向を参考に。":
        " Read the direction the parameters move it, not the absolute pitch.",
    "発振しませんでした（吹圧を上げてください）":
        "It did not oscillate (raise the blowing pressure)",
    "OpenWind の録音に {key} がありません: {list}":
        "The OpenWind recording has no {key}: {list}",
    "OpenWind 未導入のため物理モデル音合成は利用できません":
        "OpenWind is not installed, so physical-model synthesis is unavailable",
    "側孔 {label} が管の外にあります (x={x}m, 管は {lo}〜{hi}m)":
        "Tone hole {label} falls outside the tube (x={x} m, tube is "
        "{lo}–{hi} m)",
    "OpenWind（周波数領域）による共鳴ピーク。":
        "Resonance peaks from OpenWind (frequency domain).",
    "簡易TMM（自作・伝達行列法）による推定。相対比較用。":
        "Estimated with our own simple transfer-matrix method (TMM). For "
        "comparing designs only.",
    "運指 {len} 通りに対し目標音が {len2} 個":
        "{len} fingerings but {len2} target notes",
    "穴の位置が違う変種は区間行列を使い回せません":
        "A variant with the holes in different places cannot reuse the "
        "segment matrices",

    "硬さ {v}（市販番手レンジ外）": "Strength {v} (outside the range sold)",
    "{whole}½ 相当": "about {whole}½",
    "{whole} 相当": "about {whole}",

    "全閉": "all closed",
    "{k}孔開": "{k} open",

    "合う挿し込み量は**基準条件での値**で、実際に挿す深さの予測ではない: "
    "気温 {ob}°C（音速 {ob2} m/s）で第1共鳴が {low_note_label} "
    "{low_note_sounding_hz}Hz に合う位置。実際の位置はリード・リガチャー・"
    "マウスピース個体・アンブシュアでも動き、それらはモデルに入っていない。":
        "The push-on depth that fits is **a figure under reference "
        "conditions**, not a prediction of how far you will actually push the "
        "mouthpiece on: it is where the first resonance lands on "
        "{low_note_label} {low_note_sounding_hz} Hz at {ob} °C (speed of "
        "sound {ob2} m/s). The real position also moves with the reed, the "
        "ligature, the individual mouthpiece and the embouchure, none of "
        "which are in the model.",
    "（実効容積 {effective}cc は欠損円錐 {target}cc の {ratio}%。"
    "マウスピースは代替する円錐より短いので、容積差はそのまま音程差にはならない。）":
        "(The effective volume {effective} cc is {ratio}% of the missing cone "
        "{target} cc. The mouthpiece is shorter than the cone it stands in "
        "for, so the difference in volume is not a difference in pitch.)",
    "目標音で鳴らせる挿し込み量が**無い**。1mm 押し込んでも音程は {slope} "
    "セントしか動かず、実用域 {lo}〜{hi}mm の両端でも目標音を挟まない。"
    "チューニングでは合わせられないので形状側を直す必要がある。":
        "There is **no** push-on depth that sounds the target note. Pushing "
        "on 1 mm moves the pitch only {slope} cents, and neither end of the "
        "usable range {lo}–{hi} mm brackets the target. Tuning cannot cover "
        "this, so the shape has to change.",
    "チェンバー断面積比を上限まで上げても増えるのは +{headroom_cc}cc"
    "（{effective}cc）までで、欠損円錐 {target}cc には**届かない**。"
    "頭打ちの主因は外殻の肉厚で、これ以上増やすにはボディ径を上げるか"
    "最小肉厚を下げる必要がある。":
        "Even at the top of its range the chamber area ratio only adds "
        "+{headroom_cc} cc ({effective} cc), which **does not reach** the "
        "missing cone of {target} cc. What caps it is the wall thickness of "
        "the shell: to gain more you have to raise the body diameter or lower "
        "the minimum wall.",
    "欠損円錐長は descriptor の {apex_distance_mm}mm を採用"
    "（同じネック内径 {neck_bore_id_mm}mm と半頂角 {cone_half_angle_deg}° "
    "から導出すると {derived_apex_mm}mm で {derived_apex_mm2}% ずれる）。"
    "**この値は出典未記録の借り物**で、代わりの半頂角も補間なので"
    "どちらも実測ではない。落としても判定は動かないことは確認済み。":
        "The missing cone length is the descriptor's {apex_distance_mm} mm "
        "(deriving it from the same neck bore {neck_bore_id_mm} mm and half "
        "angle {cone_half_angle_deg}° gives {derived_apex_mm} mm, "
        "{derived_apex_mm2}% away). **This value is borrowed and its source "
        "was never recorded**, and the half angle that would replace it is "
        "interpolated, so neither is measured. Dropping it has been checked "
        "not to move any verdict.",
    "欠損円錐長は半頂角 {cone_half_angle_deg}°・ネック小端内径 "
    "{neck_bore_id_mm}mm から導出（頂点まで {apex_distance_mm}mm）。"
    "このサイズには公表実測が無い。":
        "The missing cone length is derived from the half angle "
        "{cone_half_angle_deg}° and the neck's small-end bore "
        "{neck_bore_id_mm} mm ({apex_distance_mm} mm to the apex). No "
        "published measurement exists for this size.",
    "目標音で鳴らせる挿し込み量が {z}mm で、実用域 {lo}〜{hi}mm の外にある"
    "（{side}挿さないと合わない）。チューニングでは埋められないので"
    "形状側を直す必要がある。":
        "The push-on depth that sounds the target note is {z} mm, outside the "
        "usable range {lo}–{hi} mm (you would have to push it on {side}). "
        "Tuning cannot cover this, so the shape has to change.",
    "挿し込み {z}mm で目標音に合う（実用域 {lo}〜{hi}mm）。1mm 押し込むと "
    "{slope} セント動くので、高い側へ約 {in_mm} / 低い側へ約 {out_mm} "
    "セントのチューニング幅がある。":
        "Pushed on {z} mm it sounds the target note (usable range {lo}–{hi} "
        "mm). Pushing on 1 mm moves it {slope} cents, giving about {in_mm} "
        "cents of tuning room sharp and about {out_mm} flat.",
    "深く": "further",
    "浅く": "less far",
    "ただし実用域の端まで 2mm を切っている。深い側の {hi}mm は":
        "But it is within 2 mm of the end of the usable range. The far end, "
        "{hi} mm, is",
    "数字で詰めずに、実物のマウスピースを止まるまで押し込んで"
    "どこで止まるかを確かめること。":
        "Do not settle this on paper: push a real mouthpiece on until it "
        "stops and see where that is.",
    "ネック小端内径は3サイズとも実測値（descriptor の "
    "neck_dimensions_source に測った個体がある）。セントは容積からの換算では"
    "なく、この形状の共鳴管を伝達行列法で解いた第1共鳴。deviation_cents は"
    "**いまの挿し込み量での**値で、判定そのものは合う挿し込み量が実用域に"
    "入るかで出している。":
        "The neck's small-end bore is measured on all three sizes (the "
        "instrument measured is named in the descriptor's "
        "neck_dimensions_source). The cents are not converted from volume: "
        "they are the first resonance of this shape solved with the transfer-"
        "matrix method. deviation_cents is the value **at the current push-on "
        "depth**, while the verdict itself is whether a push-on depth that "
        "fits falls inside the usable range.",
    "**実測**だが、これは機械的な止まりではなく「これ以上押し込んだらまずい」"
    "という判断で、しかもネック単独でもマウスピース単独でもなく**組**の性質。"
    "コルクを巻き直しても銘柄を替えても動く。":
        "**Measured**, but it is not a mechanical stop: it is a judgement "
        "that pushing further would be bad, and it belongs to the **pair**, "
        "not to the neck or the mouthpiece alone. Re-corking the neck or "
        "changing brand moves it.",
    "コルク帯長からの**推定**で、そこは厳しい公差の掛かった部位ではない"
    "（帯の幅は周方向でも一定でない）。しかも実測した 3 サイズはいずれも"
    "推定と食い違い、向きすら揃っていない。":
        "**Estimated** from the length of the cork band, which is not a "
        "closely toleranced feature (its width is not even constant around "
        "the neck). All three sizes that were measured disagreed with the "
        "estimate, and not even in the same direction.",

    "形状が十分に細長くないため、主軸の向きが不確実です。":
        "The shape is not elongated enough, so the direction of the principal "
        "axis is uncertain.",
    "両端の太さが近く、シャンク方向を特定できません。":
        "The two ends are too close in thickness to tell which way the shank "
        "faces.",

    "変化あり": "changed",
    "判定不可": "cannot tell",
    "変化なし": "unchanged",
    "ファイルが大きすぎます: %.1fMB（上限 %dMB）":
        "The file is too large: %.1f MB (limit %d MB)",
    "面が多すぎます: %d 面（上限 %d 面）":
        "Too many faces: %d (limit %d)",
    "未対応の形式です: {suffix}（STL / 3MF / STEP に対応）":
        "Unsupported format: {suffix} (STL, 3MF and STEP are supported)",

    "寸法線を逃がす向きがゼロベクトルです":
        "The direction to offset the dimension line is a zero vector",
})

#: `core/` —— プロジェクト、部品の台帳、スキーマ（壁と帯の報告）。
MESSAGES.update({
    "無題プロジェクト": "Untitled project",
    "このプロジェクトは新しいバージョン(v{version})で作成されています。"
    "アプリを更新してください。":
        "This project was made with a newer version (v{version}). Please "
        "update the app.",
    "%s が大きすぎます: %.1fMB（上限 %dMB）":
        "%s is too large: %.1f MB (limit %d MB)",
    "%s の展開後が大きすぎます（上限 %dMB）":
        "%s is too large once unpacked (limit %d MB)",
    "最後の 1 部品は取り外せません": "The last part cannot be removed",
    "component_id か members のどちらかが必要です":
        "Either component_id or members is required",

    "{self}にはインピーダンス計算がありません":
        "{self} has no impedance calculation",
    "{self}には音合成がありません": "{self} has no sound synthesis",
    "セット定義がありません: {set_id}": "No such set: {set_id}",

    "下限": "lower end",
    "上限": "upper end",
    "記載なし": "not recorded",
    "{by}で決まる壁の{side}（{by2}を動かすとここも動きます）":
        "the {side} of a hard limit set by {by} (change {by2} and this moves "
        "too)",
    "越えられない壁の{side}{band}": "the {side} of a hard limit{band}",
    "{kind}の{side}": "the {side} of {kind}",
    "{self} {req} → {v}{unit} に丸めました（{why}、出所: {src}）":
        "{self} {req} → rounded to {v}{unit} ({why}, source: {src})",
    "{self}に不明な値 {value} が来たので既定 {self2} に戻しました":
        "{self} was given an unknown value {value}, so it fell back to the "
        "default {self2}",
    "（勧める帯は {self}〜{self2}{unit}）":
        " (the recommended band is {self}–{self2}{unit})",

    "未対応の形式: {fmt}": "Unsupported format: {fmt}",
    "{caption}（描画データなし）": "{caption} (nothing to draw)",
})

#: `components/body.py` —— 管体のカード（音階・指の届く範囲・ネック接続・
#: 円錐リーチ・印刷）。**ベルは音響に接続していない**ので、音程の文言は
#: どれも「判定していない」と言い切る形で訳す。
MESSAGES.update({
    "**調律の保証ではありません。** 4-B.2b の穴位置は 0 次規則"
    "（開孔位置＝その音が鳴る円錐長）で置いた**暫定値**で、実測でも解でも"
    "ありません。有限径の穴は完全な開口端ではないので、実際の共鳴は"
    "0 次の予測より低く出ます。ここに出ているセントは「設計が外れている量」"
    "ではなく、**4-B.2c のソルバが潰す残差**そのものです。評価は理想"
    "マウスピース＋直線円錐（ベル未接続）の上で、TMM 固定・全閉が目標音"
    "ちょうどになる物差しで行っています。":
        "**This is not a promise about intonation.** The hole positions from "
        "4-B.2b are **provisional**, placed by the zeroth-order rule (a hole "
        "sits where the cone is as long as that note needs). They are "
        "neither measured nor solved. A hole of finite diameter is not a "
        "perfect open end, so the real resonance comes out lower than the "
        "zeroth-order prediction. The cents here are not \"how wrong the "
        "design is\": they are **the residual the 4-B.2c solver will take "
        "out**. Everything is evaluated on an ideal mouthpiece plus a "
        "straight cone with no bell attached, with the TMM fixed and the "
        "all-closed note landing exactly on target.",
    "スパンは音程で決まります —— 実効長が 1/f に比例する管（円錐も円筒もそう）"
    "では、全閉から 1 オクターブ上までの位置比は`f_高/f_低` そのもので、"
    "頂点から測った管の 44.1% にあたります。だから**「穴を寄せる」ことは"
    "できません**。目安の {bpf}mm はリコーダ（約200）とクラリネット"
    "（7孔で約230）の実測から採った値で、物理ではありません。":
        "The span is fixed by pitch. In any tube whose effective length goes "
        "as 1/f — cones and cylinders alike — the distance from all-closed to "
        "the octave above is exactly the ratio f_high/f_low, which is 44.1% "
        "of the tube measured from the apex. So **the holes cannot be moved "
        "closer together**. The {bpf} mm guide comes from measuring recorders "
        "(about 200) and clarinets (about 230 over seven holes); it is a "
        "convention, not physics.",
    "**ベルは音響へ接続していません。** フレアは 3 サイズとも未実測で、"
    "入れると全閉の第1共鳴が +38〜+106 セント動きます。未実測の仮定で"
    "音程の記録値を動かさないため、共鳴管は校正済みの直線円錐のままに"
    "してあります。したがってこのカードは**鳴る音程を判定していません**。"
    "曲げの影響も入っていません（弧長近似）。":
        "**The bell is not connected to the acoustics.** The flare is "
        "unmeasured on all three sizes, and adding it moves the all-closed "
        "first resonance by +38 to +106 cents. Rather than let an unmeasured "
        "assumption move the recorded pitches, the resonator is left as the "
        "calibrated straight cone. This card therefore **passes no judgement "
        "on the pitch you will hear**. The bend is not included either (arc "
        "length approximation).",
    "管体は層間の気密が要ります。FDM では層間ポロシティで漏れやすいので、"
    "レジン（光造形）か印刷後のシーリングを推奨します。":
        "A tube has to be airtight between layers. FDM leaks through "
        "inter-layer porosity, so use resin (SLA/DLP) or seal the part after "
        "printing.",
    "音階（側孔・暫定配置）": "Scale (tone holes, provisional placement)",
    "最大 {cents} c（{name}）": "worst {cents} c ({name})",
    "最大 {cents} c": "worst {cents} c",
    "指の届く範囲": "Reach of the hands",
    "届きます": "they reach",
    "届きません": "they do not reach",
    "テノン継手が無いので漏れ経路とボアの段差が 1 つ減ります。代わりに"
    "**姿勢を調整できません** —— 実機のネックは回して銜え角を合わせます。"
    "ストレートソプラノは元からそうなので実害は小さいですが、曲げのある"
    "サイズでは奏者ごとの角度差を吸収できません。壊れたときに全部作り直しに"
    "なる点も別体との違いです。**音響はどちらでも同じ**です"
    "（継ぎ目はモデルに入っていません）。":
        "With no tenon joint there is one less leak path and one less step in "
        "the bore. In exchange **the angle cannot be adjusted** — on a real "
        "instrument you rotate the neck to set the angle at the mouth. A "
        "straight soprano is like that anyway, so little is lost, but on the "
        "bent sizes you cannot take up the difference between players. It "
        "also means remaking the whole part if it breaks. **The acoustics are "
        "the same either way** (the joint is not in the model).",
    "ネック接続": "Neck joint",
    "噛み合い可": "it mates",
    "受けが浅い": "the socket is too shallow",
    "印刷品でいちばん気密が出ないのが継手です。はめあい隙間は実測で詰めて"
    "ください。一体型（ネックまで1部品）にするとこの継手ごと無くなります "
    "—— **音響は変わりません**。":
        "On a printed instrument the joint is the hardest place to make "
        "airtight. Close the fit clearance against measurements. Choosing the "
        "one-piece form (the neck included) removes the joint altogether — "
        "**and changes nothing acoustically**.",
    "円錐リーチ（音響は未接続）": "Cone reach (acoustics not connected)",
    " 弧長がベッド目安を超えるので **{segs} 分割**になります。分割そのものは"
    "後段 4-B.3 で、いまは出力しません。一体型を選んだから分割が要るのでは"
    "なく、**別体でも要ります** （一体型が増やすのはネックの弧長ぶんだけ）。":
        " The arc length exceeds the build-plate guide, so it needs "
        "**{segs} pieces**. Splitting itself comes in 4-B.3 and is not "
        "written out yet. Choosing the one-piece form is not what makes "
        "splitting necessary — **a separate neck needs it too** (one piece "
        "only adds the neck's own arc length).",
    " 一体型では継手を曲げの内部に置けないので、分割線は曲げの前後に"
    "限られます（4-B.3 への制約）。":
        " In the one-piece form the joint cannot sit inside the bend, so the "
        "split lines are limited to before and after it (a constraint for "
        "4-B.3).",
    "印刷・肉厚・気密": "Printing, wall thickness, air-tightness",
    "造形可": "printable",
    "管体＋ネック一体": "Body with the neck in one piece",
    "管体": "Body",
    "側面断面図（実線=外形 / 青破線=ボア） 単位:mm":
        "Side section (solid = outline, blue dashed = bore), mm",
    "ネック全長（弧長）": "Neck length (arc)",
    "小端ボア内径": "Small-end bore",
    "本体挿入部長": "Length inserted into the body",
    "曲げ角": "Bend angle",
    "{name}（目標 {target_note}）": "{name} (target {target_note})",
    "0 次配置のままだと {name} が {cents} セント外れます。"
    "チムニーと穴径の効きは上の 2 行です。 ":
        "Left at the zeroth-order placement, {name} is {cents} cents off. The "
        "two rows above show how much the chimney and the hole diameter move "
        "it. ",
    "指孔の本数": "Number of finger holes",
    "指孔の弧長スパン": "Finger-hole span (arc)",
    "両手の実用スパン目安": "Practical span for two hands",
    "載る区間": "Where they sit",
    "指孔径 / ふさげる目安": "Finger-hole diameter / coverable guide",
    "{bpf}mm に収まる本数": "How many fit within {bpf} mm",
    "{fit} 本（＝全閉を入れて {fit2} 音）":
        "{fit} (that is {fit2} notes counting all-closed)",
    "指孔が両手のスパンに収まります。ボウやベルに載った穴は面が傾くので、"
    "実物では押さえにくいことがあります。 ":
        "The finger holes fit within the span of two hands. Holes that land "
        "on the bow or the bell sit on a sloping surface, so they can be "
        "awkward to cover on the real thing. ",
    "一体型": "one piece",
    "繋ぎ方": "Joint",
    "別体（テノンで挿す）": "Separate (tenon joint)",
    "ネックのスピゴット外径": "Neck spigot outside diameter",
    "受け穴内径": "Socket bore",
    "φ{sock_id} mm（片側隙間 {socket_clearance}）":
        "φ{sock_id} mm (clearance {socket_clearance} per side)",
    "受け深さ / スピゴット長": "Socket depth / spigot length",
    "部品の弧長": "Arc length of the part",
    "受け深さ {socket_length}mm がネックの挿入部 {body_tenon_length}mm より"
    "浅く、スピゴットが底突きします。受けを深くするか、ネック側の挿入部を"
    "短くしてください。":
        "The socket depth {socket_length} mm is less than the neck's "
        "insertion length {body_tenon_length} mm, so the spigot bottoms out. "
        "Deepen the socket or shorten the neck's insertion.",
    "円錐リーチ（スロート→出口）": "Cone reach (throat to exit)",
    "合う長さ（低音 {low_note_label} {low_note_sounding_hz}Hz）":
        "Length that fits (low {low_note_label} {low_note_sounding_hz} Hz)",
    "差": "Difference",
    "円錐終端 → ベル出口": "End of cone → bell exit",
    "円錐は届いている": "the cone reaches",
    "円錐が短い": "the cone is short",
    "円錐が長い": "the cone is long",
    "円錐が {d}mm 足りません。円錐は長さで音程が決まるので、このままだと"
    "**約 {self} セント**高くなります。**ネックを省いて詰めた形に"
    "なっていないか**を疑ってください —— 一体型は『ネックが本体と 1 部品』で"
    "あって『ネックを外す』ことではありません。外して詰めると円錐の先端側が"
    "消え、アルトなら約 +346 セント（ほぼ短3度上）で別の楽器になります。":
        "The cone is {d} mm short. A cone's pitch is set by its length, so as "
        "it stands it will sound **about {self} cents** sharp. Check whether "
        "**the neck has been left out and the rest closed up** — one piece "
        "means \"the neck is part of the body\", not \"there is no neck\". "
        "Take the neck away and close the gap and the narrow end of the cone "
        "disappears: on an alto that is about +346 cents, nearly a minor "
        "third, which is a different instrument.",
    "円錐が {d}mm 余ります。このままだと**約 {self} セント**低くなります。"
    "本体管長を詰めてください。":
        "The cone is {d} mm too long. As it stands it will sound **about "
        "{self} cents** flat. Shorten the body.",
    "実用ベッド長の目安": "Practical build-plate length",
    "分割の見込み": "Pieces expected",
    "{segs} 分割": "{segs} pieces",
})

#: `components/body.py` の続き（寸法の行・部品表・側孔）と
#: `components/body_profiles.py`（形が成立しないときの理由）。
MESSAGES.update({
    "肉厚 / 下限": "Wall thickness / minimum",
    "材料体積 / 概算質量": "Material volume / rough mass",
    "肉厚不足": "wall too thin",
    "肉厚が下限 {min_wall}mm を下回ります。管壁が薄いと気密と強度が"
    "出ません。肉厚を上げてください。":
        "The wall is under the {min_wall} mm minimum. A thin tube wall is "
        "neither airtight nor strong. Increase the wall thickness.",
    "ソプラノ": "Soprano",
    "アルト": "Alto",
    "テナー": "Tenor",
    "3Dプリント": "3D printing",
    "ネックの繋ぎ方": "How the neck joins",
    "スロート → 円錐終端": "Throat → end of cone",
    "ベル": "Bell",
    "長さ {bell_length} mm / 出口 φ{bell_exit_dia} mm":
        "{bell_length} mm long / exit φ{bell_exit_dia} mm",
    "ボウ": "Bow",
    "{bow_angle} ° / 半径 {bow_radius} mm":
        "{bow_angle}° / radius {bow_radius} mm",
    "肉厚": "Wall thickness",
    "材料体積": "Material volume",
    "チムニー +1mm": "Chimney +1 mm",
    "指孔径 +1mm": "Finger-hole diameter +1 mm",
    "{len} 本": "{len}",
    "最上 → 最下（スロートから）": "Top → bottom (from the throat)",
    "注意": "Warning",
    "指では塞ぎきれない太さです": "Too wide for a finger to cover",
    "指孔が {span}mm に広がっており、両手では押さえられません"
    "（目安の {span2} 倍）。**これは配置の失敗ではなく、このサイズで"
    "キーレス全音階が成立しないという結論です。** 逃げ道は 3 つ ——"
    "(1) 音階の段数を減らす（このサイズなら {fit} 孔まで）、"
    "(2) フォーク運指で穴を減らす、(3) もっと小さい楽器にする。"
    "**キー機構で延ばす**のは 4-B.4 の話で、そうすると「キーレス」では"
    "なくなります。 ":
        "The finger holes are spread over {span} mm, which two hands cannot "
        "cover ({span2}× the guide). **This is not a placement failure: it "
        "is the conclusion that a keyless full scale does not work at this "
        "size.** There are three ways out — (1) use fewer steps of the scale "
        "(up to {fit} holes at this size), (2) use fork fingerings to cut "
        "the number of holes, (3) build a smaller instrument. **Extending "
        "the reach with keywork** belongs to 4-B.4, and at that point it is "
        "no longer keyless. ",
    "一体（ネックまで1部品）": "One piece (the neck included)",
    "ネック区間の弧長": "Arc length of the neck section",
    "テノン外径 ＋ コルク": "Tenon outside diameter + cork",
    "φ{need} mm（自由状態）": "φ{need} mm (uncompressed)",
    "合うマウスピースのボア径": "Bore of a mouthpiece that fits",
    "参照ネックの小端ボアのずれ":
        "Offset of the reference neck's small-end bore",
    "{gap} mm（スロート基準）": "{gap} mm (relative to the throat)",
    "材料体積 約{vol_cc}cc・弧長 {arc}mm。ベッド目安では {segs} 分割"
    "（分割は 4-B.3）":
        "About {vol_cc} cc of material, {arc} mm of arc. On the build-plate "
        "guide that is {segs} pieces (splitting comes in 4-B.3)",
    "市販品": "Off the shelf",
    "テノン コルクストリップ": "Tenon cork strip",
    "コルク": "Cork",
    "厚 {cork_thickness}mm（マウスピース勘合）":
        "{cork_thickness} mm thick (for the mouthpiece fit)",
    "ネック接合 コルク／Oリング": "Neck joint cork or O-ring",
    "コルク/NBR": "Cork / NBR",
    "受け口の気密": "Sealing the socket",
    "一体（1部品）": "One piece",
    "別体（テノン）": "Separate (tenon)",
    "側孔": "Tone holes",
    "側孔の弧長（スロートから）": "Tone-hole positions (arc from the throat)",
    "平均 {sum} c （{min}〜{max}）": "mean {sum} c ({min} to {max})",
    "＋親指孔": "+ thumb hole",
    "{k} {v}本": "{k} {v}",
    "。側孔 {len} 個（一体造形・後加工なし）":
        ". {len} tone holes, printed in place with no post-machining",
    "指孔 {len} 本 φ{hole_dia} / チムニー {hole_chimney} mm":
        "{len} finger holes, φ{hole_dia}, chimney {hole_chimney} mm",
    "（0 次規則の暫定配置）": " (provisional, zeroth-order placement)",

    "直管": "Straight",
    "ボウが本体管に収まりません: 曲げまでの直管 {bow_start}mm ＋ 曲げの弧長 "
    "{arc}mm（半径 {bow_radius} × {bow_angle}°）＝ {used}mm が本体管 {l}mm を"
    "超えています。本体管を伸ばすか、曲げ半径・曲げ角・曲げ開始位置を"
    "下げてください。":
        "The bow does not fit in the body: {bow_start} mm of straight tube "
        "before the bend plus {arc} mm of bend (radius {bow_radius} × "
        "{bow_angle}°) is {used} mm, more than the {l} mm body. Lengthen the "
        "body, or reduce the bend radius, the bend angle or where the bend "
        "starts.",
    "ベルがボウと重なります: 曲げの終わり {used}mm ＋ ベル {bell}mm ＝ "
    "{used2}mm が本体管 {l}mm を超えています。ベルを短くするか、本体管を"
    "伸ばしてください。":
        "The bell overlaps the bow: the bend ends at {used} mm and the bell "
        "adds {bell} mm, giving {used2} mm against a {l} mm body. Shorten "
        "the bell or lengthen the body.",
    "ベル出口が円錐の終端より細くなっています （出口 φ{bell_exit_dia} < "
    "円錐終端 φ{end_dia}）。実物のベルは細りません。出口径を φ{end_dia2} "
    "以上にしてください。":
        "The bell exit is narrower than the end of the cone (exit "
        "φ{bell_exit_dia} < cone end φ{end_dia}). Real bells do not narrow. "
        "Set the exit to at least φ{end_dia2}.",
    "折り返した管が自分に当たっています（弧長 {sa}mm と {sb}mm の位置で"
    "軸間 {d}mm に対し外半径の和が {need}mm）。ボウの曲率半径を大きくするか、"
    "ベルを小さくしてください。180° のボウでは行きと帰りの脚が "
    "2×曲率半径＝{bow_radius}mm しか離れません。":
        "The folded tube runs into itself (at {sa} mm and {sb} mm of arc the "
        "axes are {d} mm apart while the outer radii add up to {need} mm). "
        "Increase the bow radius or make the bell smaller. With a 180° bow "
        "the two legs are only 2 × the radius = {bow_radius} mm apart.",
    "側孔 {label} が管の外（{where}、弧長 {s}mm）に出ます。この部品は弧長 "
    "{s_lo}〜{s_hi}mm です。本体管長を伸ばすか、指孔の本数を減らして"
    "ください。":
        "Tone hole {label} falls outside the tube ({where}, at {s} mm of "
        "arc). This part spans {s_lo}–{s_hi} mm. Lengthen the body or use "
        "fewer finger holes.",
    "側孔 {label} の径 φ{dia_mm} が、その位置のボア径 φ{r_bore} 以上です。"
    "分岐の式（短いチムニー近似）が成り立たないうえ、管が輪切りになります。"
    "穴を細くするか、もっとベル寄りへ動かしてください。":
        "Tone hole {label} is φ{dia_mm}, as wide as or wider than the "
        "φ{r_bore} bore at that point. The branch model (short-chimney "
        "approximation) stops holding, and the hole cuts the tube in two. "
        "Make the hole smaller or move it toward the bell.",
    "側孔 {label} のチムニーが壁を貫いていません （{chimney_mm}mm）。"
    "肉厚を確認してください。":
        "The chimney of tone hole {label} does not get through the wall "
        "({chimney_mm} mm). Check the wall thickness.",
    "側孔 {label} と {label2} が重なります（弧長 {s_mm} と {s_mm2}、"
    "縁の隙間 {gap}mm）。穴を細くするか、親指孔のオフセットを広げて"
    "ください。":
        "Tone holes {label} and {label2} overlap (at {s_mm} mm and {s_mm2} "
        "mm of arc, {gap} mm between their edges). Make the holes smaller or "
        "widen the thumb-hole offset.",
    "ボウの曲率半径 {bow_radius}mm が管の外半径 {r_out}mm 以下です。"
    "曲率中心が管の中に入るので断面が内側で折り返して自己交差します。"
    "半径を {r_out2}mm より大きくするか、肉厚・ボアを細くしてください。":
        "The bow radius {bow_radius} mm is no larger than the tube's outer "
        "radius {r_out} mm. The centre of curvature falls inside the tube, "
        "so the section folds back on itself. Use a radius greater than "
        "{r_out2} mm, or a thinner wall or bore.",
    "ネック受けの肉厚が下限を割ります（受け穴 φ{sock_r} に対し "
    "外径が足りない）。肉厚を上げるか、はめあい隙間を詰めてください。":
        "The wall around the neck socket is under the minimum (the outside "
        "diameter is too small for a φ{sock_r} socket). Increase the wall "
        "thickness or close up the fit clearance.",
    "本体管": "Body tube",
    "テーパ": "Taper",
    "小端ボア": "Small-end bore",
    "大端ボア": "Large-end bore",
})

#: `components/body_profiles.py` の区間名と `components/ligature.py` のカード。
MESSAGES.update({
    "ボウ（曲げ）": "Bow (the bend)",
    "ボウまでの直管": "Straight tube before the bow",
    "ネック受け": "Neck socket",
    "指孔": "Finger holes",
    "親指孔": "Thumb hole",
    "マウスピース側": "the mouthpiece end",
    "ベル出口の先": "past the bell exit",

    "マウスピース外形に追従した内周です。参照マウスピースのボディ径を"
    "変えると内周も自動で追従します。接触の頂点はリード背面（カマボコ）に"
    "沿うので、締め代は全接触で揃います。":
        "The inside follows the outside of the mouthpiece. Change the body "
        "diameter of the reference mouthpiece and it follows automatically. "
        "The crests of the contacts follow the curved back of the reed, so "
        "the interference is the same at every contact.",
    "ネジは市販品です。ナットは使わず、片側の耳をタップ"
    "（下穴を開けてねじ立て）しても組めます。":
        "The screws are off the shelf. You can skip the nuts and tap one ear "
        "instead (drill and thread it).",
    "帯の断面（実線=外周 / 青破線=内周（接触の凸を含む） / 赤破線=テーブル面 "
    "/ 緑破線=リード裏面の中央） 単位:mm":
        "Section through the band (solid = outside, blue dashed = inside "
        "including the contact crests, red dashed = table plane, green "
        "dashed = centre of the back of the reed), mm",
    "帯の断面（実線=外周 / 青破線=内周 / 紫=橋（圧力プレート） / "
    "赤破線=テーブル面 / 緑破線=リード裏面の中央） 単位:mm":
        "Section through the band (solid = outside, blue dashed = inside, "
        "purple = bridge (pressure plate), red dashed = table plane, green "
        "dashed = centre of the back of the reed), mm",
    "テーパ圧入は正のはめあい隙間から始めて押し込みます。隙間を 0 以上に"
    "するか、負の隙間で嵌めたいなら締結方式を弾性バンドにしてください。":
        "A tapered press fit starts from a positive clearance and is pushed "
        "on. Set the clearance to 0 or more, or switch to an elastic band if "
        "you want to fit it with a negative clearance.",
    "リード側の肉が {wall}mm しか残りません（最小肉厚 {min_wall}mm）。"
    "接触の逃げがはめあい隙間より深いので、バンド厚を上げるか隙間を"
    "広げてください。":
        "Only {wall} mm of material is left on the reed side (minimum wall "
        "{min_wall} mm). The relief at the contact is deeper than the fit "
        "clearance, so increase the band thickness or widen the clearance.",
    "旧の圧力プレート設定（{was}）を接触形状「{contact_labels}」×{count} へ"
    "移しました。接触の頂点はリード背面（カマボコ）に沿うので、体積と"
    "部品表が変わります。":
        "The old pressure-plate setting ({was}) has been moved to contact "
        "type \"{contact_labels}\" × {count}. The crests follow the curved "
        "back of the reed, so the volume and the bill of materials change.",
    "座位置の測り方を変えました（旧「座の前端から {old}mm 後ろ」→"
    "新「最大径から前へ 0.0mm」）。旧の値は帯の後端が最大径の壁で"
    "止まっていて実効 0.17mm 以下だったので、**形は変わりません**。"
    "いまはスライダの 0〜15mm が全部効きます。":
        "The seat position is now measured differently (was \"{old} mm back "
        "from the front of the seat\", now \"0.0 mm forward from the widest "
        "point\"). Under the old measure the back of the band was stopped by "
        "the widest point and never moved more than 0.17 mm, so **the shape "
        "does not change**. The slider's whole 0–15 mm now does something.",
    "帯は公称の座より {seat0}mm 前へ出ていますが、座の長さ（最大径の 23%）は"
    "典型的なリガチャー幅から作った公称値なので、これ自体は不都合では"
    "ありません。":
        "The band sits {seat0} mm ahead of the nominal seat, but the seat "
        "length (23% of the widest diameter) is itself a nominal figure "
        "taken from typical ligature widths, so this is not a problem in "
        "itself.",
    "座位置は最大径から {seat_setback}mm 前を要求していますが、これ以上前へ"
    "出すと帯が胴から落ちるため実効 {lp}mm です。":
        "The seat is asked to sit {seat_setback} mm forward of the widest "
        "point, but any further and the band would fall off the body, so the "
        "effective value is {lp} mm.",
    "スリットもネジも無い一連のリングです。市販ねじは部品表に載りません。":
        "One continuous ring, with no slit and no screws. No off-the-shelf "
        "screws appear in the bill of materials.",
    "逆締めではスリットがリード接触面を割るので、片側から張り出した橋が"
    "反対側に重なって押さえます（橋は構造部材なので、当たり方を「なし」には"
    "できません）。":
        "On an inverted ligature the slit cuts through the reed contact "
        "face, so a bridge reaching over from one side laps onto the other "
        "and presses there. The bridge is structural, so the contact type "
        "cannot be \"none\".",
    "締結": "Clamping",
    "円錐とリードの両方に当たっています。掴んでいるのはフープの伸びでは"
    "なく**リングの楕円化**（直径方向のたわみ）なので、伸びない樹脂でも"
    "成立します。挟み力・応力はリングだけの見積りで、実物はリード背面が"
    "潰れるぶん柔らかい ＝ **硬め側に外れます**。決着させるのは印刷して"
    "押し込むこと。":
        "It touches both the cone and the reed. What grips is not hoop "
        "stretch but **the ring going oval** (deflection across a diameter), "
        "so it works in a plastic that does not stretch. The clamping force "
        "and the stresses are estimated for the ring alone; the real thing "
        "is softer because the back of the reed yields, so **the estimate "
        "errs stiff**. Settle it by printing one and pushing it on.",
    "印刷強度": "Printed strength",
    "良好": "good",
    "積層方向はバンドの周方向に対して垂直（軸方向を積層方向にしない）に"
    "すると層間剥離を避けられます。":
        "Print with the layers across the band rather than along the axis to "
        "avoid splitting between layers.",
    "ボディ径（リガチャー座）": "Body diameter (at the ligature seat)",
    "座での外形径": "Outside diameter at the seat",
    "リガチャー座の範囲": "Extent of the ligature seat",
    "テーブル面 Y（座の前端→後端）":
        "Table plane Y (front to back of the seat)",
    "テーブル傾斜": "Table angle",
    "想定リード踵厚（中央 / 側端）":
        "Assumed reed heel thickness (centre / edge)",
    "リード背面の円弧（導出）": "Arc of the reed's back (derived)",
    "逆締めはスリットがリード接触面を必ず割るので、橋渡しする接触形状が"
    "要ります。当たり方を「面 / 線 / 点」から選んでください。":
        "On an inverted ligature the slit always cuts the reed contact face, "
        "so a contact that bridges it is required. Choose face, line or "
        "point.",
    "参照マウスピースが未設定のためリガチャーを生成できません":
        "No reference mouthpiece is set, so the ligature cannot be built",
    "リードへの当たり方": "How it contacts the reed",
    "接触の x 位置": "x positions of the contacts",
    "締め代（全接触）": "Interference (all contacts)",
    "（平らな面なら）": " (if the face were flat)",
    "リード踵幅 / タブ幅": "Reed heel width / tab width",
    "マウスピース適合": "Fit to the mouthpiece",
    "参照マウスピースが未設定です。": "No reference mouthpiece is set.",
    "マウスピースの外形径に対してリードが幅広く、収納幅が {lp}mm に"
    "切り詰められています。リードが入りません。タブは外形の外へ張り出せ"
    "ますが、外形径そのものは超えられません。ボディ径の大きいマウスピースを"
    "参照するか、はめあい隙間を減らしてください。":
        "The reed is wide for this mouthpiece's outside diameter, so the "
        "space for it has been cut back to {lp} mm and the reed will not go "
        "in. The tabs can reach outside the body, but not past its diameter. "
        "Use a reference mouthpiece with a larger body, or reduce the fit "
        "clearance.",
    "弾性バンドなのにはめあい隙間が正です。伸ばして嵌める方式では隙間が"
    "締め代になるので、負の値（-0.2〜-0.4mm）にしてください。":
        "This is an elastic band but the fit clearance is positive. In a "
        "stretch-on design the clearance is the interference, so make it "
        "negative (−0.2 to −0.4 mm).",
    "剛体バンド（ネジ締め）で隙間が負です。リングは伸びないのでマウスピースに"
    "入りません。隙間を 0 以上にするか、締結方式を弾性バンドにしてください。":
        "This is a rigid screwed band but the clearance is negative. The ring "
        "does not stretch, so it will not go onto the mouthpiece. Set the "
        "clearance to 0 or more, or switch to an elastic band.",
    "はめあい隙間が小さく、印刷公差では入らない可能性があります。"
    "0.20〜0.30mm を推奨します。":
        "The fit clearance is small and printing tolerances may stop it "
        "going on. 0.20–0.30 mm is recommended.",
    "胴の円錐に押し込んで楔で止めます。掴んでいるのは伸びではなくリングの"
    "楕円化（直径方向のたわみ）なので、伸びない樹脂でも成立します。"
    "詳細はテーパ圧入のカードへ。":
        "It is pushed onto the cone of the body and wedges there. What grips "
        "is not stretch but the ring going oval (deflection across a "
        "diameter), so it works in a plastic that does not stretch. See the "
        "tapered press fit card for the detail.",
    "伸ばして嵌めるので、締め代（負の隙間）と材料の伸びが締結の実体に"
    "なります。":
        "It is stretched over, so the interference (a negative clearance) "
        "and the stretch of the material are what actually clamp it.",
    "ネジなし": "no screws",
    "締結方式": "Clamping method",
    "ネジ": "Screws",
    "M{nominal} × {screw_count} 本": "M{nominal} × {screw_count}",
    "必要な首下長さ": "Length needed under the head",
    "{need} mm 以上": "{need} mm or more",
    "推奨する市販長さ": "Stock length to buy",
    "バカ穴径": "Clearance-hole diameter",
    "耳の厚み": "Ear thickness",
    "ネジ座の高さ / 下限": "Boss height / minimum",
    "ネジ座が低くバカ穴（φ{hole_d}）が耳から出ます。閉じた穴にならず"
    "ネジが抜けます。ネジ座の高さを {need_boss}mm 以上にするか、ネジを"
    "細くしてください。":
        "The boss is too low and the φ{hole_d} clearance hole breaks out of "
        "the ear. It is not a closed hole, so the screw pulls through. Raise "
        "the boss to at least {need_boss} mm or use a thinner screw.",
    "市販レンジで必要長さを満たせません。スリット幅かバンド厚を減らして"
    "ください。":
        "No stock length is long enough. Reduce the slit width or the band "
        "thickness.",
    "テーパ圧入": "Tapered press fit",
    "楔半角（円錐 / テーブル）": "Wedge half angle (cone / table)",
    "押し込み量": "Push-on depth",
    "円錐側の締め代": "Interference on the cone side",
    "{ir_cone} mm（当たり始め {cone_at} mm）":
        "{ir_cone} mm (first touches at {cone_at} mm)",
    "リード側の締め代": "Interference on the reed side",
    "{ir_reed} mm（当たり始め {reed_at} mm）":
        "{ir_reed} mm (first touches at {reed_at} mm)",
    "押し込み {press_depth}mm ではどこにも当たりません（リードは {reed_at}mm、"
    "円錐は {cone_at}mm から）。リングはすべり嵌めのまま抜け落ちます。":
        "At {press_depth} mm it touches nothing (the reed starts at "
        "{reed_at} mm, the cone at {cone_at} mm). The ring is still a slip "
        "fit and will fall off.",
    "リードには当たっていますが円錐が {ir_cone}mm 浮いています。リングの上が"
    "支えられないので首を振ります。押し込みを {cone_at}mm 以上にするか、"
    "はめあい隙間を {reed_clearance}mm 以下にして（テーブル 4.18° は円錐 "
    "{math}° より急なので、隙間 ≤ {cs}×リード逃げ で同時に当たります）"
    "ください。":
        "It touches the reed but stands {ir_cone} mm off the cone. With "
        "nothing supporting its top the ring rocks. Push it on to at least "
        "{cone_at} mm, or bring the fit clearance to {reed_clearance} mm or "
        "less (the table's 4.18° is steeper than the cone's {math}°, so a "
        "clearance ≤ {cs} × the reed relief makes both touch at once).",
    "押し込みに {axial}N 要ります（手で押せる目安 {self}N）。押し込み量を"
    "減らすか、バンド厚を薄くしてリングを柔らかくしてください。":
        "It takes {axial} N to push on (about {self} N is what a hand can "
        "manage). Reduce the push-on depth, or thin the band so the ring is "
        "softer.",
})

#: `components/ligature.py` の続き（印刷強度・寸法の行・部品表）と
#: `components/ligature_profiles.py`。
MESSAGES.update({
    "{material_labels} は楔で掴む方式に向きません（柔らかすぎて締め代が"
    "力にならない）。伸ばして嵌めたいなら締結方式を弾性バンドにして"
    "ください。":
        "{material_labels} is a poor choice for wedging: it is too soft for "
        "the interference to turn into force. If you want to stretch it on, "
        "switch to an elastic band.",
    "バンド厚": "Band thickness",
    "材料別の推奨下限": "Recommended minimum for this material",
    "耳の厚み / ネジ頭径": "Ear thickness / screw head diameter",
    "要注意": "take care",
    "{material_labels} では {need}mm 以上を推奨します。締結荷重で"
    "層間剥離（FDM）や割れ（レジン）が起きやすい厚みです。":
        "{need} mm or more is recommended in {material_labels}. At this "
        "thickness the clamping load tends to split the layers (FDM) or "
        "crack the part (resin).",
    "リガチャー本体（{size_label}）": "Ligature body ({size_label})",
    "バンド幅 × 厚み": "Band width × thickness",
    "なし": "none",
    "全面": "whole face",
    "2点レール": "two-point rails",
    "締め代": "Interference",
    "接触なし（バンドの床が直接当たる）":
        "No contacts (the floor of the band touches directly)",
    "内周径": "Inside diameter",
    "マウスピース ボディ径": "Mouthpiece body diameter",
    "装着位置 z": "Fitted at z",
    "リガチャー座（公称）": "Ligature seat (nominal)",
    "座位置・最大径から前へ（要求/実効）":
        "Seat forward of the widest point (asked / effective)",
    "リード収納幅（要求/実際)": "Width for the reed (asked / actual)",
    "座位置を小さく（最大径寄りに）してください。":
        "Reduce the seat offset so it sits nearer the widest point.",
    "橋（圧力プレート）の厚み": "Bridge (pressure plate) thickness",
    "橋の下に残る床": "Floor left under the bridge",
    "リングの楕円化剛性": "Stiffness of the ring against going oval",
    "{k} N/mm（{material_labels}・E {e} MPa）":
        "{k} N/mm ({material_labels}, E {e} MPa)",
    "挟み力（リードを押す力）": "Clamping force on the reed",
    "帯の曲げ応力": "Bending stress in the band",
    "リードが滑り出す軸力": "Axial force that makes the reed slip",
    "{force} N（μ={self} の仮定）": "{force} N (assuming μ={self})",
    "押し込む / 抜く軸力（概算）":
        "Axial force to push on / pull off (rough)",
    "{axial} / {force} N（保持 ÷ 挿入 = {grip}。比は μ と楔角だけで決まり"
    "寸法にも材料にも依らない）":
        "{axial} / {force} N (holding ÷ fitting = {grip}; the ratio depends "
        "only on μ and the wedge angle, not on the size or the material)",
    "停止位置 ±{self} mm ＝ 挟み力 ±{k} N":
        "±{self} mm in where it stops = ±{k} N of clamping force",
    "伸びる材料か": "Does the material stretch",
    "不可": "no",
    "{material_labels} のリングは伸びません。ネジなしで嵌めるには {tpu} の"
    "ような弾性材料が要ります（薄いバンドなら成立する余地はあるので、"
    "形状としては作れます）。":
        "A ring in {material_labels} does not stretch. Fitting without "
        "screws needs an elastic material such as {tpu}. A thin band might "
        "still work, so the shape is left buildable.",
    "内周 φ{lp}mm": "inside φ{lp} mm",
    "なべ小ねじ M{nominal}×{lp}": "Pan head screw M{nominal}×{lp}",
    "ステンレス": "Stainless steel",
    "締結用。頭部は+または六角穴":
        "For clamping. Cross or hex socket head",
    "リード接触": "Reed contact",
    "本体と一体": "Part of the body",
    "橋（圧力プレート）": "Bridge (pressure plate)",
    "厚み {lp}mm・片持ち": "{lp} mm thick, cantilevered",
    "押し込み {press_depth}mm（締め代 円錐 {ic} / リード {ir} mm）":
        "pushed on {press_depth} mm (interference: cone {ic} mm, reed "
        "{ir} mm)",
    "スリット幅": "Slit width",
    "M{lp} × {screw_count} 本 （首下 {lp2}mm）":
        "M{lp} × {screw_count} ({lp2} mm under the head)",
    "橋の厚み / 残る床": "Bridge thickness / floor left",
    "締め代（円錐 / リード）": "Interference (cone / reed)",
    "当たり始め（円錐 / リード）": "First contact (cone / reed)",
    "帯の断面": "Section through the band",
    "帯の前端 {z0}mm が窓の後端 {win}mm より前に出ます。"
    "リガチャーが窓（リードが振動する開口）に掛かるので、":
        "The front of the band at {z0} mm is ahead of the back of the window "
        "at {win} mm, so the ligature covers the window the reed vibrates "
        "over.",
    "押し込み {press_depth} mm ぶん": "{press_depth} mm of push-on",
    "負のはめあい隙間 {clearance} mm":
        "a negative fit clearance of {clearance} mm",
    "印刷公差 ±%.2fmm の影響": "Effect of a ±%.2f mm printing tolerance",
    "はい": "yes",
    "いいえ": "no",
    "バンド幅を {z1}mm 以下にするか、":
        "Either bring the band width to {z1} mm or less, or ",
    "（総数 {n}）": " (of {n} in total)",

    "逆締めの橋（厚み {bridge_thickness}mm）と逃げ {bridge_gap}mm が"
    "バンド厚に収まりません（必要 {need}mm 以上 / いま {band_thickness}mm）。"
    "バンド厚を上げるか最小肉厚を下げてください。":
        "The inverted ligature's bridge ({bridge_thickness} mm thick) plus "
        "{bridge_gap} mm of relief does not fit in the band ({need} mm "
        "needed, {band_thickness} mm available). Increase the band thickness "
        "or lower the minimum wall.",
    "バンド（帯）": "Band",
    "リード接触面": "Reed contact face",
    "ネジ座（耳）": "Screw boss (ear)",
    "逆締めの耳はリード形状（reed_p）が要ります":
        "The ears of an inverted ligature need the reed's shape (reed_p)",
    "スリット（締め代）": "Slit (interference)",
})

#: `components/measure.py`（採寸の逆算）と `components/mouthpiece.py`。
MESSAGES.update({
    "バウンディングボックス": "bounding box",
    "モデルが Z 方向に {mm}mm 移動しています。z=0 基準に補正して"
    "測定します。":
        "The model is displaced {mm} mm along Z. It will be measured against "
        "z=0 after correcting for that.",
    "モデルが X 方向に移動しており座標系が崩れています。パラメータ逆算を"
    "中止しました。外部ツールで移動・回転させずに編集してください。":
        "The model is displaced along X, so the coordinate system no longer "
        "holds and solving the parameters back has been abandoned. Edit it "
        "in the external tool without moving or rotating it.",
    "テーブル平面を検出できませんでした。フェイシング系の逆算を"
    "省略します。":
        "The table plane could not be found, so nothing in the facing group "
        "was solved back.",
    "テーブル平面の直線フィット": "straight-line fit to the table plane",
    "座での外形比の上側percentile":
        "upper percentile of the outline ratio at the seat",
    "軸上放射レイ": "rays cast outward from the axis",
    "スロート幅レイ": "ray across the throat",
    "チェンバー幅レイ": "ray across the chamber",
    "下方レイ走査": "scan of rays from below",
    "空洞天井レイ(3断面)": "rays to the cavity roof (3 sections)",
    "ティップレール面(凍結fl仮定)":
        "tip rail face (assuming the frozen facing length)",
    "ビーク斜面p95回帰": "regression on the 95th percentile of the beak",
    "チェンバーが肉厚制限で頭打ちのため、断面積比は形状から逆算"
    "できません。":
        "The chamber is capped by the wall thickness, so its area ratio "
        "cannot be solved back from the shape.",
    "⚠ リード密着面／ウィンドウの寸法が凍結時から変わっています。"
    "音響シミュレーション結果は無効です。パラメータで再設計してください。":
        "⚠ The reed seating face or the window has changed since the model "
        "was frozen. The acoustic results are void. Redesign through the "
        "parameters.",
    "⚠ 内部空洞（バッフル/チェンバー/ボア）が変わっています。"
    "音程・音色はシミュレーション表示と乖離します。":
        "⚠ The inner cavity (baffle, chamber or bore) has changed. The pitch "
        "and tone will differ from what the simulation shows.",
    "座標系不一致": "coordinate system does not match",
    "テーブル平面が未検出": "The table plane was not found",
    "バッフル形状が設計プロファイルと不整合です（断面間のばらつき大）。":
        "The baffle does not match the designed profile (it varies a lot "
        "between sections).",
    "この形状からは測定できない": "cannot be measured from this shape",

    "側面断面（中央面）— 丸ポチをドラッグ":
        "Side section (centre plane) — drag the dots",
    "採寸 vs 設計": "Survey vs design",
    "実測をプロジェクトへ反映しました。設計をいじって破綻したら"
    "「採寸時点へ戻す」で復元できます。":
        "The measurements are now in the project. If editing breaks the "
        "design, \"revert to the survey\" puts it back.",
    "ティップ開き・フェイシング長・レール幅・窓長・バッフル・チェンバーは"
    "外部モデルから一意に測れません。ノギス実測して手入力してください。":
        "Tip opening, facing length, rail widths, window length, baffle and "
        "chamber cannot be measured unambiguously from an external model. "
        "Measure them with calipers and type them in.",
    "レジン(光造形)": "Resin (SLA/DLP)",
    "ナイロンPA12(SLS)": "Nylon PA12 (SLS)",
    "側面断面図（実線=外形 / 青破線=内部空洞 / 赤破線=テーブル平面 "
    "傾斜{deg}°） 単位:mm":
        "Side section (solid = outline, blue dashed = inner cavity, red "
        "dashed = table plane at {deg}°), mm",
    "最大径からシャンク端まで一直線（円錐・平行部なし）":
        "Straight from the widest point to the end of the shank (a cone, no "
        "parallel section)",
    "平行部 {shank_length} mm / 肩 {profiles} mm":
        "{shank_length} mm parallel / {profiles} mm shoulder",
    "胴の膨らみ {waist}": "body fullness {waist}",
    "外形（実測形からの変更）": "Outline (changed from the measured shape)",
    "主軸が不確実なため全長も参考値です。":
        "The principal axis is uncertain, so the overall length is for "
        "reference only.",
    "シャンク内径を確実に測れませんでした（ノギス実測を推奨）。":
        "The shank bore could not be measured reliably (use calipers).",
    "マウスピース本体（{size_label}）": "Mouthpiece body ({size_label})",
    "食品接触面。印刷後に洗浄・シーリング推奨（仕様書参照）":
        "Touches the mouth. Wash and seal after printing (see the spec "
        "sheet)",
    "リード（{size_label}用）": "Reed (for {size_label})",
    "ケーン/樹脂": "Cane or synthetic",
    "幅 {reed_width}mm 規格": "{reed_width} mm wide, standard",
    "リガチャー（{size_label}用）": "Ligature (for {size_label})",
    "ボディ径 φ{body_dia}mm 適合品": "To fit a φ{body_dia} mm body",
    "マウスピースパッチ": "Mouthpiece patch",
    "シリコン": "Silicone",
    "ビーク保護（任意）": "Protects the beak (optional)",
    "全長": "Overall length",
    "ティップ開き": "Tip opening",
    "フェイシング長": "Facing length",
    "ボア径": "Bore diameter",
    "ウィンドウ長 × 窓幅": "Window length × width",
    "内容積（全体/実効）": "Internal volume (total / effective)",
    "目標音が出る挿し込み量（{ob}°C 基準）":
        "Push-on depth that sounds the target note (at {ob} °C)",
    "― 各部名称（z範囲）―": "— Names of the parts (z range) —",
    "build_cad が失敗したため build() の表現で STEP を出力します":
        "build_cad failed, so the STEP is written from what build() produced",
    "テーブル実幅": "Table flat width",
    "（実用域 {range_mm}〜{range_mm2} mm、1mm 押し込むと {cents_per_mm} "
    "セント）":
        " (usable range {range_mm}–{range_mm2} mm; 1 mm of push-on is "
        "{cents_per_mm} cents)",
    "肩の張り {full}": "shoulder fullness {full}",
    "（指定 {window_length}mm はボアの始まりに阻まれて {profiles}mm "
    "届いていません）":
        " (the {window_length} mm asked for is blocked by the start of the "
        "bore and falls {profiles} mm short)",
    "**無し**": "**none**",
    "（母線が直線）": " (the generating line is straight)",
})

#: `components/neck.py` と `components/neck_profiles.py`。
MESSAGES.update({
    "ネックは楽器全体で最も細いスロートで、ボア径は音程の基準になります。"
    "テーパは直線円錐近似のため音程は近似です。手元の実物ネックを採寸校正"
    "すると実用域に寄ります。":
        "The neck is the narrowest throat in the whole instrument, and its "
        "bore sets the reference for pitch. The taper is approximated by a "
        "straight cone, so the pitch is approximate too. Surveying a real "
        "neck of your own brings it closer to something usable.",
    "管体は層間の気密が要ります。FDM では層間ポロシティで漏れやすいので、"
    "レジン（光造形）か、印刷後のシーリングを推奨します。":
        "A tube has to be airtight between layers. FDM leaks through "
        "inter-layer porosity, so use resin (SLA/DLP) or seal the part after "
        "printing.",
    "ボア・テーパー／ベンド": "Bore, taper and bend",
    "オクターブベント（注意）": "Octave vent (take care)",
    "キー機構は非実装": "no keywork",
    "ベント孔の幾何のみです。キー／パッド機構はありません。孔が常時開だと"
    "低音域が漏れて鳴りません。奏者が指で塞ぐ、またはプラグで塞ぐ運用が"
    "前提です。正確な第2レジスタ運用にはパッド付きキー（後段フェーズ）が"
    "必要です。『キー取付ボス』を有効にすると後段のキー機構をネック再設計"
    "なしで載せられます。":
        "This is the geometry of the vent hole only. There is no key or pad. "
        "Left open, the hole leaks and the low register will not speak, so "
        "the assumption is that you cover it with a finger or a plug. Using "
        "the second register properly needs a padded key, which comes in a "
        "later phase. Turning on \"key mounting boss\" lets that keywork be "
        "fitted later without redesigning the neck.",
    " 全長が実用ベッド目安 {bed_hint_mm}mm を超えています。造形サイズ"
    "自動分割（後段 4-B.3）で対応予定です。":
        " The overall length exceeds the {bed_hint_mm} mm build-plate guide. "
        "Automatic splitting to fit the plate comes in 4-B.3.",
    "実測をプロジェクトへ反映しました。破綻したら「採寸時点へ戻す」で"
    "復元できます。":
        "The measurements are now in the project. If it breaks, \"revert to "
        "the survey\" puts it back.",
    "曲げネックでは主軸長＝弦長のため、全長（弧長）は実際よりやや短めに"
    "出ます。":
        "On a bent neck the principal axis measures the chord, so the "
        "overall length comes out a little shorter than the real arc.",
    "テノン外径": "Tenon outside diameter",
    "コルク厚（片側）": "Cork thickness (one side)",
    "コルク込み外径（自由状態）":
        "Outside diameter over the cork (uncompressed)",
    "{need} mm（締め代 {fit}mm）": "{need} mm (interference {fit} mm)",
    "規格テノン外径（descriptor）":
        "Standard tenon diameter (from the descriptor)",
    "規格テノン径に整合": "matches the standard tenon",
    "テノンが規格より太い": "the tenon is thicker than standard",
    "テノンが規格より細い": "the tenon is thinner than standard",
    "規格より {dv}mm 太く、市販マウスピースが入らない恐れがあります。"
    "テノン外径を {neck_tenon_od_mm}mm に近づけてください。":
        "It is {dv} mm thicker than standard, so a shop-bought mouthpiece "
        "may not go on. Bring the tenon diameter nearer "
        "{neck_tenon_od_mm} mm.",
    "規格より {dv}mm 細く、コルクを厚めに巻かないとガタつきます。"
    "コルク厚での調整、またはテノン外径を上げてください。":
        "It is {dv} mm thinner than standard and will be loose unless the "
        "cork is wound thicker. Adjust the cork thickness or raise the tenon "
        "diameter.",
    "大端ボア内径": "Large-end bore",
    "円錐半頂角（descriptor）":
        "Cone half angle (from the descriptor)",
    "大端径を直接指定中（円錐角から導出していません）。":
        "The large end is set directly, not derived from the cone angle.",
    "ベント位置（弧長比）": "Vent position (fraction of the arc)",
    "ベント径": "Vent diameter",
    "チムニー高さ": "Chimney height",
    "パッド座平坦化": "Flat for the pad seat",
    "キー取付ボス": "Key mounting boss",
    "最小肉厚（下限）": "Minimum wall",
    "概算質量": "Rough mass",
    "全長（弧長）": "Overall length (arc)",
    "{s} 実測/設計": "{s} measured / designed",
    "ボア内径を確実に測れませんでした（ノギス実測を推奨）。":
        "The bore could not be measured reliably (use calipers).",
    "ネック本体（{size_label}）": "Neck body ({size_label})",
    "材料体積 約{vol_cc}cc。気密のためレジン/シーリング推奨":
        "About {vol_cc} cc of material. Use resin or seal it, for "
        "air-tightness",
    "小端 → 大端ボア": "Small-end → large-end bore",
    "テノン外径 × 長さ": "Tenon diameter × length",
    "マウスピース側のボアが {0:.1f}mm 前後なら勘合します（自由状態の"
    "コルク込み {1:.1f}mm を {2:.1f}mm 潰して食いつかせる）。規格テノン径に"
    "一致しているので市販マウスピースが使えます。":
        "A mouthpiece with a bore around {0:.1f} mm will fit (the "
        "uncompressed {1:.1f} mm over the cork is squeezed {2:.1f} mm to "
        "grip). The tenon is on the standard diameter, so shop-bought "
        "mouthpieces work.",
    "有効": "on",
    "無効": "off",
    "オクターブベント プラグ／パッチ": "Octave vent plug or patch",
    "常時開防止（キー化までの暫定。奏者が塞ぐ）":
        "Keeps it from being open all the time (until there is a key; the "
        "player covers it)",
    "オクターブベント": "Octave vent",
    "φ{vent_dia} mm @ 弧長比 {vent_position}":
        "φ{vent_dia} mm at {vent_position} of the arc",
    "ストレート": "straight",
    "グースネック": "gooseneck",

    "テノン（コルク座）": "Tenon (cork seat)",
    "コルク厚": "Cork thickness",
    "ネック全長": "Neck length",
    "曲げ区間": "Bend section",
    "本体挿入部": "Part inserted into the body",
})

#: `components/profiles.py` —— 形が成立しないときの理由と、各部の区間名。
#: **「形は通ってしまう」と書いてある文はそのまま訳す** —— そこが要点で、
#: 「不正です」に丸めると何を警告しているのか消える。
MESSAGES.update({
    "空洞の並び（窓→チェンバー→スロート→ボア）が成立しません: 窓が z "
    "{z0}→{z_we}mm ＝ 長さ {z_we2}mm しか残らず、最低 "
    "{min_window_span_mm}mm 要ります。ボアの始まり（全長 {overall_length} "
    "− ボア長 {bore_length} ＝ {zb}mm）が手前すぎるためで、"
    "「チェンバー→ボアの遷移」を縮める / ボア長を短く / 全長を長く すれば"
    "直ります（ウィンドウ長 {window_length}mm はこの場合効きません —— "
    "窓の後端は {zb2} − チェンバー→ボアの遷移 {chamber_to_bore_mm} で"
    "頭打ちになっています）。":
        "The cavity cannot be laid out in order (window → chamber → throat "
        "→ bore): the window only runs z {z0}→{z_we} mm, which is "
        "{z_we2} mm, and at least {min_window_span_mm} mm is needed. The "
        "bore starts too far forward (overall length {overall_length} − "
        "bore length {bore_length} = {zb} mm). Shorten the chamber-to-bore "
        "transition, shorten the bore, or lengthen the mouthpiece. The "
        "window length {window_length} mm will not help here: the back of "
        "the window is pinned at {zb2} − the chamber-to-bore transition "
        "{chamber_to_bore_mm}.",
    "チェンバー→ボアの遷移が {gap}mm ＝ 長さを持ちません。ウィンドウの後端と"
    "ボアの始まりが同じ位置になり、チェンバーの区間が消えます。0 より"
    "大きい値にしてください。":
        "The chamber-to-bore transition is {gap} mm, which is no length at "
        "all. The back of the window and the start of the bore land on the "
        "same place and the chamber disappears. Use a value greater than 0.",
    "ティップ開きが {tip_opening}mm ＝ リードとの隙間がありません。"
    "フェイシングの円弧が定義できず、息の入口も閉じます。0 より大きい値に"
    "してください。":
        "The tip opening is {tip_opening} mm, which leaves no gap for the "
        "reed. The facing arc cannot be defined and the air inlet is shut. "
        "Use a value greater than 0.",
    "ボア長が {bore_length}mm ＝ 長さを持ちません。ボアの始まり z={zb}mm が"
    "全長 {overall_length}mm の外にあり、円筒が 1 ビットも削りません。"
    "0 より大きい値にしてください。":
        "The bore length is {bore_length} mm, which is no length at all. Its "
        "start at z={zb} mm falls outside the {overall_length} mm body, so "
        "the cylinder removes nothing. Use a value greater than 0.",
    "シャンクの肉厚が {wall}mm ＝ 最小肉厚 {mw}mm を下回っています"
    "（シャンク径 φ{r_sh} に対しボア径 φ{bore_dia}）。形は指定どおり"
    "出ますが、この厚みでは印刷したシャンクが割れます。ボア径を "
    "φ{r_sh2}mm 以下にするか、シャンク径を φ{bore_dia2}mm 以上にして"
    "ください。":
        "The shank wall is {wall} mm, under the {mw} mm minimum (bore "
        "φ{bore_dia} inside a φ{r_sh} shank). The shape still builds as "
        "asked, but a printed shank this thin will crack. Bring the bore to "
        "φ{r_sh2} mm or less, or the shank to φ{bore_dia2} mm or more.",
    "ボア径がシャンク径以上です: ボア径 φ{bore_dia} ≥ シャンク径 φ{r_sh} "
    "mm。ボアの円筒がシャンクを丸ごと削り、ネックに挿す部分が無くなります"
    "（肉厚 {r_sh2}mm）。ボア径を φ{r_sh3}mm 未満にするか、シャンク径を "
    "φ{bore_dia2}mm より太くしてください。":
        "The bore is as wide as the shank or wider: φ{bore_dia} ≥ φ{r_sh} "
        "mm. The bore cylinder removes the whole shank and nothing is left "
        "to push onto the neck (wall {r_sh2} mm). Bring the bore under "
        "φ{r_sh3} mm, or the shank over φ{bore_dia2} mm.",
    "最大径がシャンク径より細くなっています: 最大径 φ{body_dia} < "
    "シャンク径 φ{r_sh} mm。肩が最大径からシャンクへ**太る**向きになり、"
    "「最大径」の位置（z={heel_z}mm）が最大でなくなります。最大径を "
    "φ{r_sh2}mm 以上にするか、シャンク径を φ{body_dia2}mm 以下にして"
    "ください。":
        "The widest diameter is narrower than the shank: φ{body_dia} < "
        "φ{r_sh} mm. The shoulder then **grows** from the widest point "
        "toward the shank, so the \"widest point\" at z={heel_z} mm is no "
        "longer the widest. Bring the body to φ{r_sh2} mm or more, or the "
        "shank to φ{body_dia2} mm or less.",
    "肩の長さ比が {shoulder_ratio} ＝ −1 以下です。踵の位置 "
    "(全長 − シャンク長)/(1 + 肩比) の分母が 0 以下になり、形が定義"
    "できません。肩の長さ比を 0 より大きくしてください。":
        "The shoulder length ratio is {shoulder_ratio}, which is −1 or "
        "less. The denominator of the heel position, (length − shank)/(1 + "
        "ratio), goes to zero or below and the shape is undefined. Use a "
        "ratio greater than 0.",
    "シャンク平行部と肩が全長を食い尽くしています: 踵（最大径の位置）が "
    "z={raw}mm ＝ 全長 {overall_length}mm の{heel_floor_ratio}%"
    "（{floor}mm）より前に来ます。この先は踵が {floor2}mm で頭打ちになり、"
    "**シャンク長も肩比も形を動かさなくなります**（寸法図だけが与えた数字を"
    "印字し続けます）。シャンク長を {shank_length_at_heel_floor}mm 以下、"
    "または肩の長さ比を {shoulder_ratio_at_heel_floor} 以下にしてください。":
        "The parallel shank and the shoulder have eaten the whole length: "
        "the heel (the widest point) falls at z={raw} mm, ahead of "
        "{heel_floor_ratio}% of the {overall_length} mm body ({floor} mm). "
        "Past this the heel pins at {floor2} mm and **neither the shank "
        "length nor the shoulder ratio moves the shape any more** — only "
        "the dimension drawing goes on printing the numbers you typed. "
        "Bring the shank to {shank_length_at_heel_floor} mm or less, or the "
        "shoulder ratio to {shoulder_ratio_at_heel_floor} or less.",
    "胴の膨らみ {w} では母線が単調でなくなります: {why}。「最大径に向かって"
    "単調に太る」が崩れると、リガチャー座（`ligature_seat_range`）が"
    "最大径ではない所に置かれます——**形は通り、OCCT もソリッド 1 個を"
    "返す**ので、出来上がりを見ても気づけません。{w_lo}〜{w_hi} の範囲に"
    "してください。":
        "At a body fullness of {w} the generating line stops being "
        "monotonic: {why}. Once \"it widens steadily toward the widest "
        "point\" fails, the ligature seat (`ligature_seat_range`) is placed "
        "somewhere that is not the widest point — and **the shape still "
        "builds, with OCCT returning a single solid**, so looking at the "
        "result will not tell you. Keep it between {w_lo} and {w_hi}.",
    "肩の張り {k} では母線が単調でなくなります: {why}。「最大径から"
    "シャンクへ単調に細る」が崩れます ——**形は通り、OCCT もソリッド 1 個を"
    "返す**ので、出来上がりを見ても気づけません。{k_lo}〜{k_hi} の範囲に"
    "してください。":
        "At a shoulder fullness of {k} the generating line stops being "
        "monotonic: {why}. \"It narrows steadily from the widest point to "
        "the shank\" fails — and **the shape still builds, with OCCT "
        "returning a single solid**, so looking at the result will not tell "
        "you. Keep it between {k_lo} and {k_hi}.",
    "ティップ開きが {tip} なのでフェイシングの円弧半径が定まりません"
    "（radial は y(0)=tip となる R を解くので tip > 0 が要ります）。":
        "With a tip opening of {tip} the facing arc has no radius (the "
        "radial curve solves for the R that gives y(0)=tip, which needs "
        "tip > 0).",
    "バッフル型": "Baffle type",
    "ボア長": "Bore length",
    "最大径が踵（z={heel}mm）ではなく z={az}mm へ移ります":
        "the widest point moves to z={az} mm instead of the heel at "
        "z={heel} mm",
    "胴が z={body_dip}mm で太るのをやめます":
        "the body stops widening at z={body_dip} mm",
    "肩の途中の最小半径 {dr}mm がシャンク半径 {r_sh}mm を下回り、"
    "えぐれます ——**最薄の肉厚がシャンクではなくそこ**になるので、"
    "肉厚の注意の数字も甘くなります":
        "partway along the shoulder the radius dips to {dr} mm, under the "
        "shank's {r_sh} mm, leaving a hollow — **the thinnest wall is then "
        "there rather than at the shank**, so the wall-thickness warning "
        "understates it",
    "肩が z={shoulder_bulge}mm で細るのをやめます":
        "the shoulder stops narrowing at z={shoulder_bulge} mm",
    "ビーク高さ {bh}mm がバイトポイント（z={z_bite}mm）での胴の全高 "
    "{top}mm を超えています。ビークは切除ソリッドなので、稜線が胴の外へ"
    "出ると**そこは何も削られず**、上面は胴のままになります ——"
    "「くわえたときの口の開き量」という `beak_height` の定義が成り立た"
    "なくなり、寸法図だけが与えた数字を印字し続けます。{top2}mm 以下に"
    "するか、最大径か全長を大きくしてください。":
        "A beak height of {bh} mm exceeds the body's full height of {top} "
        "mm at the bite point (z={z_bite} mm). The beak is a cutting solid, "
        "so once its ridge leaves the body **nothing is removed there** and "
        "the top stays as the body — `beak_height` no longer means \"how "
        "far the mouth opens around it\", and only the dimension drawing "
        "goes on printing the number you typed. Bring it to {top2} mm or "
        "less, or raise the widest diameter or the overall length.",
    "ビーク高さ {bh}mm ではビーク稜線が**前下がり**になります（水平になるのは "
    "{flat}mm）。ティップ側の頂点はテーブル＋ティップ開き＋ティップレール厚で"
    "決まっているので、これを下回るとビークがティップから後ろへ向かって"
    "低くなります ——実測 18.0° の「ティップからバイトへ立ち上がる直線ランプ」"
    "ではもはやありません。{flat2}mm 以上にしてください。":
        "At a beak height of {bh} mm the beak ridge **falls toward the "
        "front** (it is level at {flat} mm). The tip end of the ridge is "
        "fixed by the table plus the tip opening plus the tip rail, so "
        "below that the beak drops going back from the tip — it is no "
        "longer the straight ramp rising from tip to bite that was measured "
        "at 18.0°. Use {flat2} mm or more.",
    "シャンク径": "Shank diameter",
    "最大径": "Widest diameter",
    "肩の長さ比と全長": "Shoulder length ratio and overall length",
    "シャンク長と全長": "Shank length and overall length",
    "テーブル角とティップ開き": "Table angle and tip opening",
    "最大径と全長": "Widest diameter and overall length",
    "フェイシング（ティップ〜カーブ終端）":
        "Facing (tip to the end of the curve)",
    "フェイシングカーブ": "Facing curve",
    "ティップレール": "Tip rail",
    "ティップレール厚": "Tip rail thickness",
    "ティップ前縁の面取り": "Chamfer on the leading edge of the tip",
    "サイドレール（窓の両脇）": "Side rails (either side of the window)",
    "テーブル平面（傾き）": "Table plane (its angle)",
    "バッフル（窓の天井）": "Baffle (the roof of the window)",
    "バッフルの棚とランプ": "Baffle shelf and ramp",
    "バッフルの段": "Baffle step",
    "バッフルのカーブ": "Baffle curve",
    "バッフル肩の丸み": "Radius of the baffle shoulder",
    "スロート（最狭部）": "Throat (the narrowest point)",
    "チェンバー（最大部）": "Chamber (the widest point)",
    "チェンバー断面": "Chamber section",
    "ボア（円筒部）": "Bore (the cylindrical part)",
    "シャンク（ネック挿入部）": "Shank (what goes onto the neck)",
    "ウィンドウ（リード開口）": "Window (the opening the reed covers)",
    "テーブル・窓幅": "Table and window width",
    "ビーク（上面）": "Beak (the top face)",
    "ボディ（リガチャー座）": "Body (the ligature seat)",
    "シャンク": "Shank",
    "シャンク平行部": "Parallel part of the shank",
    "肩（最大径→シャンク径）":
        "Shoulder (widest diameter → shank diameter)",
    "胴（ティップ〜最大径）": "Body (tip to the widest diameter)",
    "全体": "Whole part",
    "全体（肉厚）": "Whole part (wall thickness)",
    "ビーク": "Beak",
    "フェイシング": "Facing",
    "テーブル": "Table",
    "ウィンドウ": "Window",
    "サイドレール": "Side rail",
    "バッフル": "Baffle",
})

#: `components/profiles.py` の残り（ステーション名・黙って頭打ちになる所）と
#: `components/reed.py`。
MESSAGES.update({
    "ランプ": "Ramp",
    "チェンバー": "Chamber",
    "ウォール": "Wall",
    "スロート": "Throat",
    "ボア": "Bore",
    "バレル": "Barrel",
    "胴の膨らみ": "Body fullness",
    "比": "ratio",
    "肩の終わり": "End of the shoulder",
    "肩の張り": "Shoulder fullness",
    "バッフル高さ": "Baffle height",
    "棚の終わり（段の位置）": "End of the shelf (where the step is)",
    "段の立ち上がり": "Rise of the step",
    "カーブ量": "Amount of curve",
    "肩の丸みの終わり": "End of the shoulder radius",
    "z≈{hit}mm から先で天井がビーク下の肉厚上限に当たっています。"
    "これ以上バッフルを開いても形は変わりません"
    "（min_wall / beak_height で決まる上限）":
        "From about z={hit} mm the roof is against the wall-thickness limit "
        "under the beak. Opening the baffle further changes nothing (the "
        "limit comes from min_wall and beak_height)",
    "窓の開き始めが設計値より {d}mm ずれています"
    "（ティップレール幅が指定どおりになりません）":
        "The window starts {d} mm away from where it was designed to (the "
        "tip rail will not come out at the width you asked for)",
    "ウィンドウ長が {short}mm 届いていません（指定 {window_length} → 実際 "
    "{window_length_effective}mm）。窓の後端はチェンバー→ボアの遷移区間を"
    "残すため「ボアの始まり {bore_start_z} − チェンバー→ボアの遷移 "
    "{gap}mm」で頭打ちになります。ここから先へ伸ばすには"
    "「チェンバー→ボアの遷移」を縮める / 全長を長く / ボア長を短くして"
    "ください（ウィンドウ長を上げても形は変わりません）":
        "The window is {short} mm short of what was asked ({window_length} "
        "asked, {window_length_effective} mm actual). To leave room for the "
        "chamber-to-bore transition, the back of the window pins at \"start "
        "of bore {bore_start_z} − transition {gap} mm\". To go past that, "
        "shorten the transition, lengthen the mouthpiece, or shorten the "
        "bore — raising the window length will not change the shape",
    "息の通り道が入口より奥で狭くなっています: 入口（ティップ）{ent}mm に"
    "対し z≈{z_min}mm で {h_min}mm ＝ 入口の {h_min2}%。リード先端から"
    "入った息をここで絞ります。バッフル高さ {baffle_height}mm を下げて"
    "ください（**ティップ開きを広げると悪くなります** —— 上がるのは入口"
    "だけで、奥は動きません）":
        "The air path narrows further in than at the entrance: against "
        "{ent} mm at the tip it is {h_min} mm at about z={z_min} mm, "
        "{h_min2}% of the entrance. This throttles the air coming in past "
        "the reed tip. Lower the baffle height from {baffle_height} mm "
        "(**opening the tip makes it worse** — that raises only the "
        "entrance and leaves the inside where it was)",
    "PCHIP の制御点 x が単調増加ではありません: pts[{i}]={pts} と "
    "pts[{i2}]={pts2} で x が {xs} → {xs2}（幅 {hi}）。表全体: {pts3}":
        "The PCHIP control points are not increasing in x: pts[{i}]={pts} "
        "and pts[{i2}]={pts2} go {xs} → {xs2} (span {hi}). Whole table: "
        "{pts3}",

    "届かない（可動域の端 {edge} mm でも {got}）":
        "out of reach (even at {edge} mm, the end of the travel, it is "
        "{got})",
    "{value} mm（現在 {current}）": "{value} mm (currently {current})",
    "効くのはヴァンプ長とプロファイル曲線です —— たわみは先端からの距離の "
    "3 乗で効くので固定端側が支配し、**先端厚の寄与は {tip_pct}% しか"
    "ありません**。":
        "What moves it is the vamp length and the profile curve: deflection "
        "goes as the cube of the distance from the tip, so the fixed end "
        "dominates and **the tip thickness contributes only {tip_pct}%**.",
    "口に触れる部品。食品接触適合材料を使用のこと（規格長 {span}mm）":
        "Touches the mouth. Use a food-contact-safe material (standard "
        "length {span} mm)",
    "採寸 vs 設計（リード）": "Survey vs design (reed)",
    "実測をプロジェクトへ反映しました。**1 本だけ入れないこと** ——"
    "銘柄・カットで寸法は動くので（全長はソプラノ 58.3〜62.0 / アルト "
    "70.2〜72.8 / テナー 81.05〜82.7 と 2.6〜3.7mm 振れる）、同じサイズを"
    "複数本まとめて測ってから入れてください。先端カーブは「側面がまっすぐに"
    "なる所」まで測った値を入れれば、見かけの角（パラメータ）へ逆算して"
    "取り込みます。設計をいじって破綻したら「採寸時点へ戻す」で復元"
    "できます。":
        "The measurements are now in the project. **Do not enter just one "
        "reed.** Dimensions move with the brand and the cut — overall "
        "length spans 58.3–62.0 on soprano, 70.2–72.8 on alto and "
        "81.05–82.7 on tenor, a spread of 2.6 to 3.7 mm — so measure "
        "several of the same size before entering them. For the tip curve, "
        "enter the value measured to \"where the sides become straight\"; "
        "it is solved back into the apparent corner the parameter uses. If "
        "editing breaks the design, \"revert to the survey\" puts it back.",
    "硬さ・剛性": "Strength and stiffness",
    "マウスピースのテーブル・レールに整合しています。":
        "It matches the mouthpiece's table and rails.",
    "窓の区間（z={z}）でリードの縁がサイドレールに載らず、窓の上に "
    "{mm}mm 浮いています。脇から漏れます。先端幅を広げるか、マウスピースの"
    "窓を狭めてください。":
        "Over the window (at z={z}) the edge of the reed does not land on "
        "the side rail: it floats {mm} mm out over the window, and air "
        "leaks past the side. Widen the reed tip, or narrow the "
        "mouthpiece's window.",
    "解像度": "resolution",
    "実用強度": "usable strength",
    "印刷可否": "Can it be printed",
    "解像度・実用強度の下限をどちらも上回っています。積層方向はリード長手"
    "方向に平行（面内）にしてください。":
        "It clears both the resolution floor and the usable-strength floor. "
        "Print with the layers running along the reed, in its plane.",
    "厚みプロファイル（実線=中央 / 青破線=側端 / 赤破線=テーブル面 / "
    "灰=ヴァンプ端） 単位:mm":
        "Thickness profile (solid = centre, blue dashed = edge, red dashed "
        "= table plane, grey = end of the vamp), mm",
    "踵の断面（上面＝ケーン外径 φ{rp} の円弧 / 赤破線＝テーブル面） 単位:mm":
        "Section at the heel (top = an arc of the φ{rp} cane outside "
        "diameter, red dashed = table plane), mm",
    "テーブル実幅（帯の中央）":
        "Table flat width (at the middle of the band)",
    "リード幅（規格の呼び）": "Reed width (the nominal standard)",
    "ウィンドウ長": "Window length",
    "ティップ輪郭の落ち込み（x=±{reed_width}）":
        "Drop of the tip contour (at x=±{reed_width})",
    "リード共振 f_reed": "Reed resonance f_reed",
    "自由振動長": "Free vibrating length",
    "曲げ剛性 EI": "Bending stiffness EI",
    "先端たわみ": "Tip deflection",
    "たわみの寄与（先端→根元）":
        "Where the deflection comes from (tip → heel)",
    "3番相当にする先端厚（{material}）":
        "Tip thickness for a strength of 3 ({material})",
    "3番相当にするヴァンプ長": "Vamp length for a strength of 3",
    "柔らかすぎます。先端が閉じきって音が詰まりやすく、耐久も落ちます。":
        "Too soft. The tip closes up, the sound chokes, and it will not "
        "last.",
    "ヴァンプ長を {v}mm へ（現在 {rp}）":
        "Take the vamp to {v} mm (currently {rp})",
    "先端厚を {t}mm へ（現在 {tip_thickness}）":
        "Take the tip thickness to {t} mm (currently {tip_thickness})",
    "この材料と形では 3番相当に届きません。プロファイル曲線を「直線」寄りに"
    "するか、材料を硬いものへ変えてください。":
        "This material and shape cannot reach a strength of 3. Move the "
        "profile curve toward straight, or use a stiffer material.",
    "リード先端幅 / 踵幅": "Reed tip width / heel width",
    "ヴァンプ長 / ウィンドウ長": "Vamp length / window length",
    "踵位置 / リガチャー座": "Heel position / ligature seat",
    "先端カーブ / MPの輪郭に最も合う値":
        "Tip curve / the value that best fits the mouthpiece contour",
    "角の位置（リード / MP）": "Corner position (reed / mouthpiece)",
    "{reed_corner} / {mp_corner} mm（丸み {tip_corner_r} ぶん "
    "{reed_corner2}）":
        "{reed_corner} / {mp_corner} mm ({reed_corner2} once the "
        "{tip_corner_r} radius is taken off)",
    "リガチャーが締める区間（z={z}）で縁がテーブルの外へ {over}mm "
    "出ています。押しても密着しないので、そこは漏れます。踵幅を詰めるか、"
    "マウスピースのボディ径を大きくしてください。**後ろへはみ出すぶんは"
    "害がありません** ——締めない区間なので参考値です。":
        "Over the stretch the ligature clamps (at z={z}) the edge stands "
        "{over} mm outside the table. Pressing it will not seat it, so it "
        "leaks there. Narrow the heel, or use a mouthpiece with a larger "
        "body. **Anything overhanging further back does no harm** — nothing "
        "clamps there, so it is given for reference only.",
    "先端厚（中央）": "Tip thickness (centre)",
    "解像度の下限（積層 {min_layer} × 3）":
        "Resolution floor (layer {min_layer} × 3)",
    "実用強度の下限（{mat}）": "Usable-strength floor ({mat})",
    "側端厚": "Edge thickness",
    "造形不可": "cannot be printed",
    "先端厚が解像度の下限（積層 {min_layer} × 3 = {res_floor}mm）を"
    "下回ります。積層を細かくするか先端厚を上げてください。":
        "The tip is under the resolution floor (layer {min_layer} × 3 = "
        "{res_floor} mm). Use finer layers or a thicker tip.",
    "造形はできますが、{mat} の実用強度の下限 {str_floor}mm を下回ります。"
    "**この下限は出典の無い仮定**で、この薄さが屈曲に耐えるかは未確認です"
    "（実物のリードは先端 0.1mm 前後ですが、それはケーンの繊維方向の強さが"
    "あってのものです）。":
        "It will print, but it is under the {str_floor} mm usable-strength "
        "floor for {mat}. **That floor is an assumption with no recorded "
        "source**, and whether something this thin survives bending has not "
        "been checked (a real reed is about 0.1 mm at the tip, but it has "
        "the grain strength of cane behind it).",
    "参照マウスピースが未設定のため音合成できません":
        "No reference mouthpiece is set, so the sound cannot be synthesised",
    "リード（{size_label}）": "Reed ({size_label})",
    "リードケース": "Reed case",
    "反り防止（任意）": "Keeps it from warping (optional)",
    "先端幅 × 踵幅": "Tip width × heel width",
    "先端厚（中央/側端）": "Tip thickness (centre / edge)",
    "踵厚（中央/側端）": "Heel thickness (centre / edge)",
    "ケーン外径（側端厚からの導出）":
        "Cane outside diameter (derived from the edge thickness)",
    "φ{rp} mm（側端厚は未実測）":
        "φ{rp} mm (the edge thickness is not measured)",
    "ヴァンプ長": "Vamp length",
    "先端カーブ / 全幅に達する位置":
        "Tip curve / where it reaches full width",
    "硬さ相当（推定）": "Equivalent strength (estimated)",
    "リード共振 f_reed（推定）": "Reed resonance f_reed (estimated)",
})

#: `components/reed.py` の残りと `components/reed_profiles.py`。
MESSAGES.update({
    "帯までのはみ出し 最大": "Worst overhang up to the band",
    "先端カーブ（側面がまっすぐになる所まで）":
        "Tip curve (measured to where the sides become straight)",
    "硬すぎます。鳴らすのに強い吹圧が要り、低音が出にくくなります。":
        "Too hard. It takes a lot of blowing pressure, and the low notes "
        "will not speak.",
    "一般的な硬さのレンジです。数値は片持ち梁近似による推定なので、"
    "絶対値ではなくパラメータを動かしたときの変化方向を見てください。":
        "A normal strength. The number is estimated with a cantilever "
        "approximation, so read the direction it moves when you change a "
        "parameter, not the absolute value.",
    "3番相当にするなら ": "To reach a strength of 3, ",
    "区間がありません": "there is no such stretch",
    "{tip_curve_depth} / {best_d} mm（最大ずれ {gap}、合わせると "
    "{best_gap}）":
        "{tip_curve_depth} / {best_d} mm (worst gap {gap}; matched it would "
        "be {best_gap})",
    "ヴァンプがウィンドウ長に対して短く、削り面が窓に届いていません。"
    "振動部が硬くなり鳴りにくくなります。":
        "The vamp is short for this window, so the cut face does not reach "
        "it. The vibrating part is stiff and will not speak easily.",
    "参照マウスピース リード幅（規格の呼び）":
        "Reference mouthpiece reed width (the nominal standard)",
    "先端カーブ / 参照マウスピースの輪郭に最も合う値":
        "Tip curve / the value that best fits the reference mouthpiece's "
        "contour",
    "厚みプロファイル": "Thickness profile",
    "踵の断面（カマボコ）": "Section at the heel (the curved back)",
    " か ": " or ",
    "　参考: MP の輪郭が未実測のため判定しない":
        "  For reference: the mouthpiece contour is not measured, so no "
        "verdict is given",
    "踵がリガチャー座の後端（{seat1}mm）まで届いていません。リガチャーが"
    "リードの無い位置を締めることになり、固定できません。全長を伸ばして"
    "ください。":
        "The heel does not reach the back of the ligature seat "
        "({seat1} mm). The ligature would clamp where there is no reed, so "
        "it cannot hold it. Make the reed longer.",
    "  ← 効いている": "  ← this is the binding one",
    "先端カーブを {best_d}mm にすると最大ずれが {best_gap}mm まで"
    "縮みます。":
        "Setting the tip curve to {best_d} mm brings the worst gap down to "
        "{best_gap} mm.",
    "円弧の前縁ではこの輪郭に {tip_contour_tol}mm 以内まで寄せられません"
    "（いちばん近いのは {best_d}mm で {best_gap}mm）。":
        "An arc at the leading edge cannot come within {tip_contour_tol} mm "
        "of this contour (the closest is {best_d} mm, at {best_gap} mm).",
    "ただし市販のリードは規格品でマウスピース個体に合わせて作られていない"
    "ので、揃えるかどうかは設計の判断です。":
        "That said, shop-bought reeds are standard parts and are not made "
        "to match an individual mouthpiece, so whether to match them is a "
        "design decision.",
    "前縁がマウスピースのティップ輪郭から最大 {gap}mm {vif}。":
        "The leading edge is up to {gap} mm from the mouthpiece's tip "
        "contour: it {vif}.",
    "後退しています（レールが露出）":
        "sits back, leaving the rail exposed",
    "前へ張り出します": "overhangs to the front",

    "先端カーブ {d} mm では{why}: 先端幅 {tip_width}・踵幅 {heel_width}・"
    "全長 {reed_length} では {limit} mm まで。{how}。":
        "At a tip curve of {d} mm, {why}: with a tip width of {tip_width}, "
        "a heel width of {heel_width} and a length of {reed_length}, "
        "{limit} mm is the most. {how}.",
    "リードが元のケーン管に収まりません{extra}: 最大半幅 {hw} mm に対し、"
    "外径 φ{r} の管では半幅 {limit} mm までしか厚みが残りません。"
    "踵の側端厚（{heel_edge_thickness}）を上げて円弧を浅くするか、幅を"
    "狭くしてください。":
        "The reed does not fit in the cane tube it came from{extra}: "
        "against a half width of {hw} mm, a tube of φ{r} leaves material "
        "only out to {limit} mm. Raise the edge thickness at the heel "
        "({heel_edge_thickness}) to flatten the arc, or make it narrower.",
    "踵へ広がる側面に前縁の円弧が届きません":
        "the leading-edge arc does not reach the sides as they widen toward "
        "the heel",
    "先端カーブを浅くするか、踵幅を狭く・先端幅を広く・全長を長くして"
    "ください":
        "Flatten the tip curve, or narrow the heel, widen the tip, or make "
        "it longer",
    "前縁の円弧が半円を越えて閉じません":
        "the leading-edge arc would pass a half circle and never close",
    "先端カーブを浅くするか、先端幅を広くしてください":
        "Flatten the tip curve or widen the tip",
    "先端カーブ": "Tip curve",
    "（ファイルドは表皮 %.2f mm を落とすぶん余分に要る）":
        " (filed needs %.2f mm more, for the bark taken off)",
    "リード全体": "Whole reed",
    "先端（ティップ）": "Tip",
    "踵（ヒール）": "Heel",
    "先端の削り": "Cut at the tip",
    "バーク（未削部）": "Bark (uncut)",
    "ケーンの円弧（カマボコ）": "Arc of the cane (the curved back)",
    "前縁カーブ": "Leading-edge curve",
    "ヴァンプ（削り面）": "Vamp (the cut face)",
    "中央の背骨": "Spine down the middle",
    "サイドレール（両脇）": "Side rails (either side)",
    "先端角の丸み": "Radius at the tip corners",
    "表皮を削った部分（ファイルド）": "Where the bark is removed (filed)",
    "先端幅・踵幅・リード全長・先端角の丸み":
        "Tip width, heel width, reed length and tip corner radius",
    "先端幅": "Tip width",
})

#: `components/reed_seat.py` / `reference_check.py` / `set_check.py` ——
#: 照合カード。判定語そのものは訳さない（`_finish` が status を決める鍵）。
MESSAGES.update({
    "　縁が窓の上に浮いています":
        "  the edge floats out over the window",
    "同サイズのテンプレート": "the template for this size",
    "リードが載るか（裏面の密着）":
        "Does the reed seat (contact on its back)",
    "**窓へのかかり代**は縁が窓の上に浮くと脇から漏れるので判定します"
    "（実物のマウスピース 2 本 × リード 2 本で アルト +0.40〜+1.33mm・"
    "ソプラノ +0.90〜+2.12mm・テナー +0.50〜+1.45mm、光にかざして 3 サイズ "
    "30 組とも縁がレールの上）。ただし規格リードの先端幅が未実測のサイズでは"
    "参考です。**「窓の終端〜帯の後端」**はリガチャーが締める区間なので、"
    "縁がテーブルの外にあると押しても密着しません。**帯より後ろへはみ出すのは"
    "害がありません**（締めないので参考値）。比べる相手はそのサイズの"
    "**規格リード**です —— リードを設計していてもここは規格で見ます"
    "（リードは規格から大きく動かさない前提）。設計中のリードとの適合は"
    "セットのカードにあります。":
        "**Reed overhang at the window** is judged, because an edge "
        "floating over the window leaks at the side (measured on two real "
        "mouthpieces × two reeds: alto +0.40 to +1.33 mm, soprano +0.90 to "
        "+2.12 mm, tenor +0.50 to +1.45 mm, and held up to the light all 30 "
        "pairs across the three sizes had the edge on the rail). On sizes "
        "where the standard reed's tip width is not measured it is given "
        "for reference only. **\"End of the window to the back of the "
        "band\"** is the stretch the ligature clamps, so an edge outside "
        "the table will not seat however hard you press. **Overhang behind "
        "the band does no harm** (nothing clamps there, so it is for "
        "reference). What it is compared against is the **standard reed** "
        "for that size — even if you are designing a reed, this card uses "
        "the standard, on the assumption that reeds do not stray far from "
        "it. The fit against the reed you are designing is on the set's "
        "card.",
    "窓へのかかり代 最小": "Smallest reed overhang at the window",
    "（参考）窓へのかかり代 最小":
        "Smallest reed overhang at the window (reference)",
    "縁がレールから外れる区間があります":
        "there are stretches where the edge leaves the rail",
    "縁がわずかにレールから外れる区間があります":
        "there are stretches where the edge just leaves the rail",
    "帯までは全幅が載っています":
        "the full width is seated as far as the band",
    "想定リード": "Reed assumed",
    "{label}（先端 {tip} / 踵 {heel} mm）":
        "{label} (tip {tip} mm, heel {heel} mm)",
    "帯の後端（区間の境目）":
        "Back of the band (where the stretches divide)",
    "（参考）帯より後ろのはみ出し 最大":
        "Worst overhang behind the band (reference)",
    "窓が開いていません": "the window is not open",
    "窓の終端〜帯の後端": "End of the window to the back of the band",
    "リードが帯の後端より短い":
        "the reed is shorter than the back of the band",
    "（参考）テーブルより後ろへ出た長さ":
        "Length past the end of the table (reference)",
    "{mm} mm　この区間は載る面が無いので幅の比較から外しています":
        "{mm} mm — there is no face to seat on here, so it is left out of "
        "the width comparison",
    "　このサイズは規格リード幅が未実測のため判定しない":
        "  no verdict: the standard reed's width is not measured for this "
        "size",

    "実物・規格との照合": "Checked against the real thing and the standard",
    "全長・ボディ径・チェンバーは各社とも公表していないため照合対象外。"
    "リード全長は銘柄・カット・材質で動くので 1 点ではなく域で見ています"
    "（descriptor の reed_length_range_mm）。**長短の向きは材質から決まり"
    "ません** —— ソプラノは樹脂が 2.9mm 長く、アルトは樹脂どうしで 2.6mm "
    "違い（レジェール 70.2／FIBRACELL 72.8）、ケーン 3 本はその間の "
    "71.1〜71.2。実測が 1 本も無いサイズ（いまはテナー）では、テーブル終端との"
    "比較は判定せず参考値として並べます。ソプラノのテーブル終端はモデル "
    "60.0mm に対し実物が 60.2mm（実測、2026-08-13）で、ここで出る「軽微」は"
    "モデルの粗さではなく**実物の性質**です —— 長いリード（レジェール "
    "62.0mm）の踵は実際に 1.8mm はみ出します。**最大径の上限は市販リガチャーが"
    "受けられる径**であって、実測した市販マウスピースの最大径そのものでは"
    "ありません （アルトの上限 29.0 に対し Meyer G 6 の実測は 28.0。29.0 の"
    "根拠は「29.1 の Wood Stone PHROX が Meyer 向けリガチャーに実際に適合する」"
    "ほうです）。テナーの基準機 WindyCity 30.8 は上限を 0.8 超えますが、"
    "**市販リガチャーで確認できません** —— この基準は物ではなく配布 3mf "
    "なので、リガチャーを嵌めてみる相手が存在しないからです。アルトのような"
    "適合実績は永久に付かないので「軽微」のまま残してあります。決着させるなら"
    "手元の個体（Jody Jazz GIANT 30.0 は上限の内側）で測り直して、そちらを"
    "基準に取り込んでください。":
        "Overall length, body diameter and chamber are not checked: no "
        "maker publishes them. Reed length moves with brand, cut and "
        "material, so it is held as a range rather than one figure (the "
        "descriptor's reed_length_range_mm). **The material does not tell "
        "you which way it goes** — on soprano the synthetic is 2.9 mm "
        "longer, on alto two synthetics differ by 2.6 mm (Légère 70.2, "
        "FIBRACELL 72.8) and three cane reeds sit between them at "
        "71.1–71.2. On a size with no measurements at all (currently "
        "tenor), the comparison against the end of the table is listed for "
        "reference and no verdict is given. On soprano the end of the table "
        "is 60.0 mm in the model against 60.2 mm measured (2026-08-13), so "
        "a \"minor\" here is **a property of the real thing**, not "
        "coarseness in the model: the heel of a long reed (Légère 62.0 mm) "
        "really does overhang by 1.8 mm. **The limit on the widest "
        "diameter is what a shop-bought ligature can take**, not the widest "
        "diameter of any mouthpiece measured (against alto's limit of 29.0, "
        "a Meyer G 6 measures 28.0; the 29.0 comes instead from a 29.1 Wood "
        "Stone PHROX actually fitting a Meyer-sized ligature). The tenor "
        "reference, a WindyCity at 30.8, is 0.8 over the limit, but "
        "**that cannot be checked against a real ligature** — this "
        "reference is a distributed 3mf rather than an object, so there is "
        "nothing to try a ligature on. It can never gain the kind of "
        "fitting record alto has, so it is left as \"minor\". To settle it, "
        "measure a mouthpiece you own (a Jody Jazz GIANT at 30.0 is inside "
        "the limit) and bring that in as the reference.",
    "規格リードとの照合": "Checked against the standard reed",
    "規格から外すと市販リガチャー・マウスピースに合わなくなります。"
    "厚みプロファイルは規格が無いため照合対象外。**幅のテーパーはモデルが"
    "線形を仮定しています** —— 実物の 3 サイズ（各 5 本）でほぼ直線で、"
    "先端のほうが 1〜2mm 広い（踵へ狭まる）ことが分かっています。"
    "先端から 20mm の幅を測れば、手元のリードでも確かめられます。":
        "Stray from the standard and shop-bought ligatures and mouthpieces "
        "stop fitting. The thickness profile is not checked: there is no "
        "standard for it. **The model assumes the width tapers linearly** — "
        "measuring five reeds in each of the three sizes showed it is close "
        "to straight, with the tip 1 to 2 mm wider than the heel. Measure "
        "the width 20 mm from the tip and you can check this on your own "
        "reeds.",
    "ボア径 / テノン＋コルク−締め代":
        "Bore / tenon + cork − interference",
    "リード幅（規格の呼び / 規格リード）":
        "Reed width (nominal standard / standard reed)",
    "テーブル終端 / リガチャー座の後端":
        "End of the table / back of the ligature seat",
    "（参考）リガチャー座の後端 − リード全長":
        "Back of the ligature seat − reed length (reference)",
    "フェイシング長 / 公表チャート域":
        "Facing length / published chart range",
    "{label} 実測/設計": "{label} measured / designed",
    "{label} 実測/従前": "{label} measured / previous",
    "全長 / 規格域": "Overall length / standard range",
    "先端幅 / 規格域": "Tip width / standard range",
    "先端から 20mm の幅 実測/モデル":
        "Width 20 mm from the tip, measured / model",
    "（参考）先端から 20mm の幅":
        "Width 20 mm from the tip (reference)",
    "未実測。採寸フォームで入れると、幅のテーパーが直線かどうかを"
    "ここで確かめられます":
        "Not measured. Enter it in the survey form and this will tell you "
        "whether the width really tapers in a straight line",
    "規格から外れています": "it is outside the standard",
    "わずかに規格から外れています": "it is just outside the standard",
    "規格に一致しています": "it matches the standard",
    "（参考）最大径": "Widest diameter (reference)",
    "最大径 / 市販リガチャーが受ける上限":
        "Widest diameter / what a shop-bought ligature takes",
    "テーブル終端 / リード全長域":
        "End of the table / range of reed lengths",
    "（参考）テーブル終端 / リード全長":
        "End of the table / reed length (reference)",

    "セットの適合（MP＋リガチャー＋リード）":
        "Fit of the set (mouthpiece + ligature + reed)",
    "セットの適合（MP＋リガチャー）":
        "Fit of the set (mouthpiece + ligature)",
    "ここに出るのは**3 部品が揃わないと決まらない量**だけです（帯の位置は"
    "マウスピースの座・リガチャーの幅と座位置・リードの全長で決まります）。"
    "各部品ごとの規格照合はそれぞれのカードにあります。リードの z は"
    "マウスピースと同じく先端が 0 で、組んだときティップレールに合わせる"
    "前提です —— ティップ輪郭の落ち込み（0.1mm 級）は無視しています。"
    "**裏面の密着は 1 点ではなく全長で見ています**（`reed_seat`）—— "
    "判定するのは窓へのかかり代とリガチャーが締める区間で、後ろへはみ出す"
    "ぶんは害が無いので参考値です。かかり代は規格リードの先端幅が実測された"
    "サイズでだけ判定します（実物のアルトで +0.40〜+1.33mm、光にかざして "
    "10 組とも縁がレールの上）。マウスピース単体のカードは**規格リード**で"
    "同じことを見ています。":
        "Only quantities that **need all three parts to be decided** appear "
        "here (where the band sits follows from the mouthpiece's seat, the "
        "ligature's width and seat position, and the reed's length). Each "
        "part's own check against the standard is on its own card. The "
        "reed's z runs from 0 at the tip, as the mouthpiece's does, "
        "assuming the two are lined up at the tip rail when assembled; the "
        "drop of the tip contour, of order 0.1 mm, is ignored. **Seating on "
        "the back is judged over the whole length, not at one point** "
        "(`reed_seat`): the verdicts are on the overhang at the window and "
        "on the stretch the ligature clamps, while overhang behind it does "
        "no harm and is given for reference. The overhang is only judged on "
        "sizes where the standard reed's tip width has been measured (on a "
        "real alto, +0.40 to +1.33 mm, and held up to the light all ten "
        "pairs had the edge on the rail). The mouthpiece's own card checks "
        "the same thing against the **standard reed**.",
    "リガチャー帯の位置（前端→後端）":
        "Where the ligature band sits (front to back)",
    "リードはまだセットにありません。リガチャーの当たり面は**同サイズの"
    "テンプレート リード**を想定して作られています。リードを設計して"
    "セットに足すと、その実寸に合わせた形へ変わります"
    "（変わったことは通知に出ます）。":
        "There is no reed in the set yet. The ligature's contact faces are "
        "built around **the template reed for this size**. Design a reed "
        "and add it to the set and they change to match its actual "
        "dimensions (you will be told when they do).",
    "このセットのリード（踵厚 {heel} / 踵幅 {width} mm）":
        "the reed in this set (heel {heel} mm thick, {width} mm wide)",
    "同サイズのテンプレート値（踵厚 {heel} / 踵幅 {width} mm）":
        "the template for this size (heel {heel} mm thick, {width} mm wide)",
    "リード全長 / 帯の後端": "Reed length / back of the band",
    "接触が当たる最前 / リードの削り始め":
        "Frontmost contact / where the reed's cut begins",
    "帯の下のリード厚 / リガチャーの想定":
        "Reed thickness under the band / what the ligature assumed",
    "（帯の前端は {z}）": " (the front of the band is at {z})",
})

#: `server/` —— 書き出し、ビルドワーカ、状態の通知。
MESSAGES.update({
    "{name}_入稿パッケージ.zip": "{name}_print_package.zip",
    "[外部編集済みモデル]\nmodel_edited.stl は外部ツールで手動編集した"
    "モデルです。\n印刷にはこのファイルを使用してください。\n"
    "対象: {targets}\n":
        "[Model edited outside the app]\n"
        "model_edited.stl was edited by hand in an external tool.\n"
        "Use that file for printing.\n"
        "Applies to: {targets}\n",
    "読み込み失敗: {e}": "Could not load it: {e}",
    "形状生成に失敗: {e}": "Could not build the shape: {e}",

    "{boot_timeout} 秒以内に準備できませんでした":
        "It was not ready within {boot_timeout} seconds",
    "ビルドワーカを起動できないので親プロセスで作ります: %s":
        "The build worker would not start, so the parent process will "
        "build: %s",
    "ビルドワーカが使えません": "The build worker is unavailable",
    "子プロセスが起動直後に終了しました":
        "The child process exited as soon as it started",
    "ビルドワーカが %.0f 秒で応答しないので作り直します":
        "The build worker has not answered in %.0f seconds, so it is being "
        "restarted",
    "ビルドがタイムアウトしました": "The build timed out",
    "ビルドワーカが落ちました: {e}": "The build worker died: {e}",

    "{tmpl_label} テンプレート既定値": "{tmpl_label} template defaults",
    "この プロジェクト に「{component_id}」はありません":
        "This project has no \"{component_id}\"",
    "このコンポーネントは未実装です": "This component is not implemented",
    "「{cls}」は既にこのセットにあります":
        "\"{cls}\" is already in this set",
    "セットのプロジェクトはメンバーとして取り込めません。取り込みたい部品を"
    "単体 .wproj へ書き出してください。":
        "A set project cannot be brought in as a member. Export the part "
        "you want as a .wproj of its own.",
    "このプロジェクトは「{self}」用です。「{self2}」のものを選んで"
    "ください。":
        "This project is for {self}. Choose one for {self2}.",
    "未知のコンポーネントです: {cid}": "Unknown component: {cid}",
    "このセットには既に「{inst}」があります。取り込んだもので置き換えるなら、"
    "先に今の「{inst2}」を外してください（残しておきたい場合は単体 .wproj へ"
    "書き出してから）。":
        "This set already has \"{inst}\". To replace it with what you are "
        "bringing in, remove the current \"{inst2}\" first (export it as its "
        "own .wproj if you want to keep it).",
    "{self} は「{ref_id}」を参照しません":
        "{self} does not reference \"{ref_id}\"",
    "このセットの{self}が参照元です（設計中の値に追従します）。別のものを"
    "使いたい場合は、セットの{self2}側で取り込んでください。":
        "The {self} in this set is the reference, and it follows the values "
        "you are designing. To use a different one, bring it in on the "
        "set's {self2}.",
    "参照コンポーネントがありません": "There is no reference component",
    "⚠ メッシュが水密ではありません。修復しないと印刷できません。":
        "⚠ The mesh is not watertight. It cannot be printed until it is "
        "repaired.",
    "先に編集済みモデルを取込・解析してください":
        "Import and analyse the edited model first",
    "復元点がありません。先に採寸を確定してください。":
        "There is nothing to revert to. Commit a survey first.",
    "component_id か set_id のどちらかが必要です":
        "Either component_id or set_id is required",
    "「{ms}」が「{inst}」に従属しています。先にそちらを外してください。":
        "\"{ms}\" depends on \"{inst}\". Remove that one first.",
    "「{inst}」はこのセットの土台なので外せません。他の部品が寸法を"
    "ここから取ります。":
        "\"{inst}\" is what this set is built on and cannot be removed. The "
        "other parts take their dimensions from it.",
    "このプロジェクトは「{src}」です。「{ref_id}」の .wproj を選んで"
    "ください。":
        "This project is a {src}. Choose a .wproj for {ref_id}.",
    "このマウスピースは「{self}」用です。「{self2}」のものを選んで"
    "ください。":
        "This mouthpiece is for {self}. Choose one for {self2}.",
    "⚠ 体積が {delta_pct}% 変化しています。削りすぎ／穴あきの疑い。":
        "⚠ The volume has changed by {delta_pct}%. It may have been cut too "
        "far, or holed.",
    "「{ms}」は{label}に従属します。これ以降はセットの{label2}に"
    "追従します":
        "\"{ms}\" now depends on the {label}, and will follow the set's "
        "{label2} from here on",
    "{label}（セットから書出）": "{label} (exported from a set)",
    "（取り込んでいた参照は使われなくなります）":
        " (the reference that was brought in is no longer used)",
    "「{ms}」は{label}の寸法を参照します。":
        "\"{ms}\" takes its dimensions from the {label}.",
    "{label}を外したので、同サイズのテンプレート値へ戻ります":
        "With the {label} removed, it goes back to the template values for "
        "this size",
    "これ以降は設計中の{label}の実寸に合わせた形になります":
        "From here on it takes its shape from the actual dimensions of the "
        "{label} you are designing",
})

#: **判定語。** コードの中では値（`_finish` が status を決める鍵）なので
#: `i18n.t(v)` と**変数で**引かれる —— つまり `t("…")` を AST で数える網には
#: 映らない。抜けても誰も気付かないので、ここに居ることを
#: `tests/test_i18n.py::test_the_verdict_words_are_translated` が固定する。
MESSAGES.update({
    "一致": "match",
    "軽微": "minor",
    "乖離": "off",
    "測定不能": "not measurable",
})

#: 採寸フォームの `_SURVEY_SIZE_FIELDS` の見出し。これも**変数で**引かれる
#: （`i18n.t(f["label"])`）ので AST の網に映らない。
#: `tests/test_i18n.py::test_the_survey_size_fields_are_translated` が固定する。
MESSAGES.update({
    "ネック小端内径": "Neck small-end bore",
    "ネックテノン外径": "Neck tenon outside diameter",
    "欠損円錐長（頂点まで）": "Missing cone length (to the apex)",
    "規格の全長": "Standard overall length",
    "規格の先端幅": "Standard tip width",
    "先端から 20mm の幅": "Width 20 mm from the tip",
    "{deg} °（{kind}）": "{deg}° ({kind})",
})

#: `measure.UNMEASURABLE` —— 逆算できない理由。これも**表を引いて `t()` に渡す**。
#: メッシュが要るので実行時走査にも映らず、**訳が 14 本まるごと抜けていた**のを
#: 変数引きの呼び出しを数え直して見つけた。`brightness._MODEL_RANGE` の見出しも同じ。
MESSAGES.update({
    "フェイシング面の露出が先端部のみで、カーブ全長は一意復元できない":
        "only the tip end of the facing is exposed, so the whole curve "
        "cannot be recovered uniquely",
    "窓開口はスーパー楕円断面のため設計窓幅と一致せず一意復元できない"
    "（変化は領域偏差で検出）":
        "the window opening is a superelliptic section, so it does not "
        "match the designed window width and cannot be recovered uniquely "
        "(changes are still caught by the regional deviation)",
    "曲線種別は形状から一意判別できない":
        "which curve it is cannot be told from the shape",
    "レール幅は分解能不足（±0.15mm）":
        "the rail width is below the resolution (±0.15 mm)",
    "バッフル肩の曲率は直接測定できない":
        "the curvature of the baffle shoulder cannot be measured directly",
    "断面指数は直接測定できない":
        "the section exponent cannot be measured directly",
    "ボア開始位置の遷移が緩やかで一意に定まらない":
        "the bore starts through a gradual transition, so no single "
        "position is defined",
    "組立条件であり形状に現れない。そもそも寸法ではなく演奏者が抜き差しする"
    "チューニング量（acoustics.volume 参照）":
        "it is a condition of assembly and does not appear in the shape. It "
        "is not a dimension at all but how far the player pushes the "
        "mouthpiece on to tune (see acoustics.volume)",
    "最大径の位置とシャンク平行部の開始の両方が要る。逆算は未実装"
    "（実物ではシャンク端からの 2 点をノギスで測る）":
        "it needs both the widest point and where the parallel shank "
        "begins. Solving it back is not implemented (on a real mouthpiece "
        "you take two caliper readings from the end of the shank)",
    "母線と実測プロファイルの残差から解けるが逆算は未実装。"
    "領域偏差（胴）では変化を検出できる":
        "it can be solved from the residual between the generating line and "
        "the measured profile, but solving it back is not implemented. The "
        "regional deviation on the body still catches changes",
    "同上（肩の区間で解く）。逆算は未実装":
        "the same, solved over the shoulder. Not implemented",
    "全面の肉厚走査は未対応":
        "scanning the wall thickness over the whole surface is not "
        "supported",
    "材料は形状に現れない": "the material does not appear in the shape",

    "スロート断面積比": "Throat area ratio",
})

#: **約物。** 語ではないので日本語検出の網に掛からない —— 英語の画面を実際に
#: 読んで見つけた（`15.8〜16.4`、`（z=3.9）`、全角スペース）。数字を組む
#: f 文字列の中に全角記号が残っていると、訳が全部済んでいても日本語に見える。
MESSAGES.update({
    "{lo}〜{hi}": "{lo}–{hi}",
    "{mm} mm（z={z}）": "{mm} mm (z={z})",
    "　判定は「リードが載るか」のカード":
        "  judged on the \"does the reed seat\" card",
    "　このサイズは基準となる市販機が未実測のため判定しない":
        "  no verdict: no shop-bought reference has been measured for this "
        "size",
    "　リード全長が未実測のため判定しない":
        "  no verdict: the reed length is not measured",
})

# ---- ここより下に `MESSAGES.update({...})` を足す（末尾の目印） ----
