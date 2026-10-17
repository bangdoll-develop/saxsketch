# 開発に参加する

個人の研究プロジェクトです。気軽に issue を立ててください。
PR も歓迎しますが、先に issue で向きを合わせてもらえると無駄が減ります。

英語でも日本語でも構いません。コードのコメントと docstring は日本語で書いてあり、
**そこが読み物の本体**なので、できれば日本語のままにしてください
（機械翻訳すると、このプロジェクトの価値そのものが落ちます）。

## 動かす

[README.md](README.md) の「セットアップ」。
**Windows ネイティブは Smart App Control が OCCT を止めるので動きません。**
WSL2 か Linux を使ってください。

```bash
pytest -q                      # 全数（OCCT のビルドが入るので 15 分前後）
pytest tests/test_repo_hygiene.py -q   # 公開の衛生だけ。数秒、OCCT 不要
ruff check .                   # lint（整形はしない）
cd frontend && npm run lint && npm run build
```

## この repo の約束

ここは**測定の台帳**でもあります。コードより先に、次の約束を見てください。

1. **空欄を埋めるために発明しない。** 出所の無い数値は入れない。
   分からないものは「記載なし」「未実測」と書く。
   `source=` に書けない数字は、書けるようになるまで入れない。
2. **数字を 2 か所に書かない。** 表から導ける値を散文やテストへ書き写すと、
   表を直した日に片方だけ古くなる。導出する。
   （この型は実際に何度も起きていて、`docs/param-limits.md` に記録がある。）
3. **黙ってクランプしない。** 値を丸めたら、値・単位・種別・出所つきで報告する。
4. **壁は数字ではなく関係のことがある。** 相手で動く壁は
   `Component.param_bounds()` に置く（`ParamSpec` の `hard_*` は静的な掛け金）。
5. **他人のメッシュを入れない。** `*.3mf` `*.stl` `*.step` `*.FCStd` は
   `.gitignore` 済みで、`tests/test_repo_hygiene.py` が固定している。
   理由は [cad/windycity/ATTRIBUTION.md](cad/windycity/ATTRIBUTION.md)。
6. **個人のパスを書かない。** 同じテストが見ています。
7. **改行は LF。** `.gitattributes` で固定（WSL と Windows の両方で同じファイルを
   触るため。`scripts/*.sh` が CRLF になると WSL の bash が落ちる）。

## 安全について

このツールは**口に入れる部品**を作らせます。材料・洗浄・破損についての記述を
弱める変更は受け付けません。→ [SAFETY.md](SAFETY.md)

## ライセンス

送ってもらった変更は Apache-2.0（[LICENSE](LICENSE)）で取り込みます。
CLA はありません。
