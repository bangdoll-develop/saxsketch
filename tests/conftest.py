"""テスト全体の下ごしらえ。

**設定を実ユーザーのホームから切り離す。** `saxsketch.server.state` は import 時に
`~/.saxsketch/settings.json` を読み書きする単一オブジェクト `STATE` を作るので、
テストを走らせるだけで利用者の設定が書き換わっていた。実害も出ていて、
「最近使ったプロジェクト」が pytest の一時ディレクトリ 10 件で埋まり、
実際に開いたプロジェクトが全部押し出されていた。

環境変数はモジュールの読み込み前に立てる必要がある（fixture では遅い）。
conftest はテストモジュールより先に import されるので、ここが最も早い場所。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

_TEST_HOME = Path(tempfile.mkdtemp(prefix="saxsketch-test-home-"))
os.environ["SAXSKETCH_HOME"] = str(_TEST_HOME)

# 出力先も固定する。空のままだと既定が環境から導かれ、out_dir を渡し忘れた
# テストが**実際のドキュメントフォルダ**へ書いてしまう。
(_TEST_HOME / "settings.json").write_text(
    json.dumps({"export_root": str(_TEST_HOME / "export")}), encoding="utf-8")


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TEST_HOME, ignore_errors=True)
