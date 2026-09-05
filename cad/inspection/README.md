# 実製作品の検品

3Dプリントに出した部品が届いたとき、**実物を測って設計へ返す**ための道具。

手順そのものは `docs/print-inspection.md`。ここにあるのは、そのシートに載せる
数値を `.wproj` から**計算し直す**スクリプト（数字を手で写さないため）。

| ファイル | 内容 |
|---|---|
| `inspection_values.py` | 採寸表の設計値・判定帯・**実測との判定**、フェイシングカーブ表、ビーク高さの測り方（精度要求）とバッフル天井に当たる下限、**対テナー比の散らばり**、ウィンドウ長の上限、**ティップ端→窓の後縁と、そこから派生するティップレール幅**、**`bore_length` と合う挿し込み量**、**実測形状どうしの Δin_tune と「その差を作れるつまみがあるか」の全域掃引**、**実測の挿し込み位置と実用域**、**音別の感度**、篏合と音響の予測値、質量 |
| `analyze_recording.py` | 録音（`.m4a` など）から **F0 と倍音比** |

```bash
.venv/Scripts/python.exe cad/inspection/inspection_values.py <project.wproj>
.venv/Scripts/python.exe cad/inspection/inspection_values.py --size alto
.venv/Scripts/python.exe cad/inspection/analyze_recording.py <file.m4a> [--a4 440] [--notes]
```

**実測値は `inspection_values.py` の `MEASURED` にだけ書く。** 判定・差・比の
一覧はそこと `.wproj` から計算する。シートに手写しの数字を置かないため。

**判定は「印刷した個体の `.wproj`」に対して回す**（`PRINTED_FROM`）。
テンプレートは実測を取り込んで動くので、`--size alto` で回すと印刷品の列が
「外れ」に見える —— 印刷したのは更新前の設計だから当然で、プリンタの話ではない。
相手が違うとスクリプトが警告を出す。

### 録音解析について

**F0 と倍音比の 2 つだけ出す。** 比べる相手（時間領域合成、
`cad/windycity/README.md`「3 サイズ × 3 アンブシュア」）が出しているのがこの 2 つ
だから。

**絶対音程を指標にしない理由は「感度が小さいから」ではない。**
モデルの 0.49 セント/mm は**全閉最低音の値**で、`_assemble_resonator` は
トーンホールを持たない。感度は 1/L で伸びるので、**録音に入っている音では
1.6〜5.0 セント/mm**（`inspection_values.py` の「感度は音ごとに違う」）。
つまり**数 mm の差し直しで 10 セント動く** —— だから挿し込み量を記録しない限り
絶対音程は解釈できない。指標にならない理由はそちら（`docs/print-inspection.md`
§11.6 の訂正）。

- **圧縮録音でよい。** 48kHz / 約 200kbps の AAC なら F0 と f0 の 1〜8 倍は保たれる。
  潰れるのは 16kHz 以上と極小レベルのノイズ床なので、**音程と倍音バランスには
  使えるが、息のノイズ・雑音の比較には使えない**
- **クリップは致命的。** 振り切れた標本が 0.05% を超えたら倍音比を出さない
  ——**クリップが作る高次とマウスピースの倍音は区別できない**（初号機の 1 本目が
  0.85% でこれに当たった）。F0 は読める
- **判定は出さない。** しきい値をここで作らない（シートの規則）
- `av`（PyAV）が要る。**関数の中で import する**ので、無い環境でも
  `inspection_values.py` は動く

```bash
VIRTUAL_ENV="$(pwd)/.venv" uv pip install av
```

**判定帯は自前のしきい値ではない。** `Component.survey_card` が使っているのと
同じ規則（一致 `max(0.6·step, 0.05)` / 軽微 `max(2.5·step, 0.2)`）を読んでいる。
しきい値を 2 か所に置くと必ず食い違うので、ここでは持たない。

図（どの寸法がどこか）は `cad/windycity/measure_soprano.py --size alto` が出す
`cad/windycity/measure_alto.svg`。
