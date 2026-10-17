# -*- coding: utf-8 -*-
"""サンプルプロジェクトを作り直す。

**テンプレートのまま**にしてある。設計の味を付けると「これが推奨値だ」と
読まれてしまうが、推奨値は `templates/*.json` 側の仕事で、サンプルの仕事は
「3 部品が揃ったセットはこう見えるか」を 1 クリックで見せることだけ。

**アプリ自身に作らせる。** `Project` を直に組み立てると、セットの約束
（必須メンバー・役割・既定の選択）をここへ書き写すことになり、
約束を変えた日にサンプルだけが古くなる（＝この repo で何度も出ている型）。

実行（OCCT が要るので WSL2。リポジトリ直下から）:

  wsl bash -lc "PYTHONPATH=. ~/mp_design/.venv/bin/python examples/make_example.py"
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else _HERE / "alto-set.wproj"

# 実ユーザーの `~/.saxsketch/settings.json` を汚さない（「最近使った」が
# サンプル生成で埋まる。テストの conftest が同じ理由で同じことをしている）。
os.environ.setdefault(
    "SAXSKETCH_HOME", tempfile.mkdtemp(prefix="saxsketch-example-home-"))

from fastapi.testclient import TestClient            # noqa: E402
from saxsketch.core.project import Project           # noqa: E402
from saxsketch.server.app import app                 # noqa: E402

# Host 検査（`app._local_only`）があるので、ブラウザと同じ Host で叩く。
c = TestClient(app, base_url="http://127.0.0.1:8712")


def main() -> None:
    c.post("/api/project/new", json={"instrument_id": "saxophone",
                                     "template_id": "alto",
                                     "set_id": "mouthpiece_set"}).raise_for_status()
    # リードは任意メンバー。サンプルは「3 部品揃った姿」を見せる物なので入れる。
    c.post("/api/set/member/add", json={"component_id": "reed"}).raise_for_status()
    # **メモより先に選択を戻す。** `project.notes` は active メンバーへ委譲される
    # （`Project._delegated`）ので、リードを足した直後に書くとリードに付く。
    # 名前はプロジェクト本体の属性なので、こちらは順番に関係しない。
    c.post("/api/set/active", json={"component_id": "mouthpiece"}).raise_for_status()
    c.put("/api/project/meta", json={
        "name": "アルト一式（サンプル）",
        "notes": ("テンプレートのままのセット。マウスピース＋リガチャー＋リードが"
                  "どう組み合わさるかを見るためのもので、推奨値ではない。"
                  "値はすべて templates/alto.json の既定。"),
    }).raise_for_status()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    c.post("/api/project/save", json={"path": str(OUT)}).raise_for_status()

    # 読み戻せるところまで確かめる（壊れた物を配らない）
    p = Project.load(OUT)
    print("saved: %s (%d bytes)" % (OUT, OUT.stat().st_size))
    print("  楽器 %s / テンプレート %s / セット %s"
          % (p.instrument_id, p.template_id, p.set_id))
    print("  部品 %s" % sorted(p.members))
    print("  名前 %s" % p.name)


if __name__ == "__main__":
    main()
