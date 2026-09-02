# 実製作品の検品

3Dプリントに出した部品が届いたとき、**実物を測って設計へ返す**ための道具。

手順そのものは `docs/print-inspection.md`。ここにあるのは、そのシートに載せる
数値を `.wproj` から**計算し直す**スクリプト（数字を手で写さないため）。

| ファイル | 内容 |
|---|---|
| `inspection_values.py` | 採寸表の設計値・判定帯、フェイシングカーブ表、篏合と音響の予測値、質量を出す |

```bash
.venv/Scripts/python.exe cad/inspection/inspection_values.py <project.wproj>
.venv/Scripts/python.exe cad/inspection/inspection_values.py --size alto
```

**判定帯は自前のしきい値ではない。** `Component.survey_card` が使っているのと
同じ規則（一致 `max(0.6·step, 0.05)` / 軽微 `max(2.5·step, 0.2)`）を読んでいる。
しきい値を 2 か所に置くと必ず食い違うので、ここでは持たない。

図（どの寸法がどこか）は `cad/windycity/measure_soprano.py --size alto` が出す
`cad/windycity/measure_alto.svg`。
