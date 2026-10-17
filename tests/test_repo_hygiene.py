"""公開の衛生 —— リポジトリに入れてはいけない物が入っていないか。

**`saxsketch` を import しない。** 理由が 2 つある:

1. ここが見るのは git の中身であって、モデルではない。
2. `test_saxsketch.py` は OCCT を引くので Windows の Smart App Control 環境では
   import すら通らない。この網はそこでも走ってほしい。

逆に `.git` が無いと何も測れないので、WSL の稼働コピー（`scripts/wsl_sync.sh` が
`.git/` を除いて rsync する）では skip になる。**正本か CI で走る網**である。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: リポジトリへ入れてはいけない拡張子。中身が「他人のメッシュそのもの」か
#: 「それを同梱した文書」になりうる形式を並べてある。
_FORBIDDEN_SUFFIXES = (".3mf", ".stl", ".step", ".stp", ".fcstd", ".obj", ".ply")

#: 基準メッシュから直接描いた図。`NOTICE` が CC BY-NC-SA だと名指ししている。
_NC_SA_IMAGES = (
    "cad/windycity/overlay_base.png",
    "cad/windycity/sections_xy.png",
    "cad/windycity/sections_yz_xz.png",
    "cad/windycity/window_outline.png",
    "cad/windycity/tip_rail.png",
)


def _tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=_REPO_ROOT,
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - 環境依存
        pytest.skip("git を実行できない環境")
    if out.returncode != 0:  # pragma: no cover - 稼働コピーには .git が無い
        pytest.skip("git リポジトリではない（WSL の稼働コピー）")
    return out.stdout.splitlines()


def test_no_third_party_geometry_is_tracked():
    """**他人のメッシュをリポジトリへ入れない。**

    マウスピースの基準形状は CC BY-NC-SA の配布 3mf を実測して起こしたもの
    （`NOTICE` / `cad/windycity/ATTRIBUTION.md`）。寸法は事実なので構成式は
    こちらの物だが、**メッシュそのものと、それを同梱した文書は再配布にあたる**。
    具体的には `reference_aligned.stl`（整列しただけの複製）と
    `base_tenor.FCStd`（重ね表示のため原メッシュを同梱している）。

    `.gitignore` で除外してはあるが、**`git add -f` 一回で破れる**。
    履歴に一度入ると取り消せないので、ここで固定する。
    """
    bad = [f for f in _tracked_files() if f.lower().endswith(_FORBIDDEN_SUFFIXES)]
    assert bad == [], (
        "他人のメッシュを含みうる形式がトラックされている。"
        "出所を確認して外すこと（cad/windycity/ATTRIBUTION.md）: %s" % bad)


def test_the_license_paperwork_is_present_and_points_at_real_files():
    """ライセンス一式があり、`NOTICE` の名指しが実在すること。

    **空欄を埋めるために発明しない**のと同じ理由で、**実体の無い帰属も書かない**。
    図を撮り直して名前を変えた日に `NOTICE` だけ古くなると、
    「どのファイルが CC BY-NC-SA なのか」が誰にも分からなくなる。
    """
    for name in ("LICENSE", "NOTICE", "THIRD-PARTY.md",
                 "cad/windycity/ATTRIBUTION.md"):
        assert (_REPO_ROOT / name).exists(), "%s が無い" % name

    notice = (_REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "CC BY-NC-SA" in notice
    assert "thingiverse.com/thing:6645240" in notice

    tracked = set(_tracked_files())
    for img in _NC_SA_IMAGES:
        assert (_REPO_ROOT / img).exists(), "%s が無い" % img
        assert img in tracked, "%s がトラックされていない" % img
        assert img in notice, "%s が NOTICE に載っていない" % img


def test_no_personal_paths_are_tracked():
    """**自分の机の場所をリポジトリに残さない。**

    Windows のユーザー名と正本の絶対パスは、他人には動かないうえに
    「どこに何を置いているか」をそのまま晒す。コマンド例は相対パスで書く。

    **探すのは形（正規表現）で、特定のユーザー名は書かない。** 最初は実際の
    ユーザー名を並べた表で探していたが、それだと (1) **この網自身がその名前を
    公開してしまう**し、(2) 自分の表に自分が当たる。実際このファイルが
    untracked の間だけ緑で、`git add` した瞬間に赤くなった —— 通っていたのでは
    なく、**測る前に自分を外していた**。形で探せば、他人の機械のパスが
    混ざった時も拾える。

    `<user>` や `<repo>` のような差し込み記号には当たらない
    （文字クラスが `<` を除いてあるので、プレースホルダは一致しない）。
    """
    patterns = (
        # C:\Users\<誰か> / C:/Users/<誰か>（JSON などで二重に逃がされた形も）
        re.compile(r'[A-Za-z]:[\/]{1,2}Users[\/]{1,2}([^\/\s"\'<>,)]+)'),
        # C:\HOME\<誰か> —— この企画の正本が置かれていた形
        re.compile(r'[A-Za-z]:[\/]{1,2}HOME[\/]{1,2}([^\/\s"\'<>,)]+)'),
        # WSL から見た同じ場所
        re.compile(r'/mnt/[a-z]/(?:Users|HOME)/([^/\s"\'<>,)]+)'),
    )
    hits: list[str] = []
    for rel in _tracked_files():
        f = _REPO_ROOT / rel
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue          # 画像など
        for pat in patterns:
            for m in pat.finditer(text):
                hits.append("%s: %s" % (rel, m.group(0)))
    assert hits == [], "個人のパスが残っている:\n  " + "\n  ".join(hits)


#: 旧名。他人の**生きた登録商標**（米 4549949 ほか、どちらも第 9 類の
#: ソフトウェア）なので公開物に残さない。**2 つに割ってあるのは細工ではなく
#: 計測の都合** —— 1 つの文字列で書くとこのファイル自身が当たり、上の個人パスで
#: 掘ったのと同じ穴（自分を外さないと緑にならない）をまた掘ることになる。
_OLD_PROJECT_NAME = "wind" "forge"


def test_the_old_project_name_is_gone():
    """**改名したら残りかすを置いていかない。**

    `SaxSketch` は旧名からの改名（2026-10-17）。旧名は他人の登録商標で、
    しかも import パス・コマンド名・URL と 81 ファイルに散っていたので、
    1 か所でも残ると「直したつもり」になる。
    """
    hits: list[str] = []
    for rel in _tracked_files():
        if _OLD_PROJECT_NAME in rel.lower():
            hits.append("%s（パス）" % rel)
        f = _REPO_ROOT / rel
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _OLD_PROJECT_NAME in text.lower():
            hits.append("%s（中身）" % rel)
    assert hits == [], "旧名が残っている:\n  " + "\n  ".join(hits)
