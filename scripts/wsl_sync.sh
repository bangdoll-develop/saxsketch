#!/usr/bin/env bash
# SaxSketch — WSL 同期 & ビルド確認スクリプト
#
# Windows 正本 (/mnt/c/...) → WSL 稼働コピー (~/mp_design) を同期し、
# 依存/フロントをビルドして OCP import と IS_WSL を検証する。
#
# 使い方（WSL Ubuntu シェルで）:
#   bash /mnt/c/HOME/<user>/develop/claude/mp_design/scripts/wsl_sync.sh [--deps] [--test]
#     --deps : pip の依存を入れ直す（pyproject.toml を変えた時）＋ npm install
#     --test : 同期後に pytest を実行
#
# 環境変数で上書き可: WF_SRC（Windows 正本）, WF_DST（WSL 稼働コピー）
set -euo pipefail

WF_SRC="${WF_SRC:-/mnt/c/HOME/<user>/develop/claude/mp_design}"
WF_DST="${WF_DST:-$HOME/mp_design}"

DO_DEPS=0
DO_TEST=0
for arg in "$@"; do
  case "$arg" in
    --deps) DO_DEPS=1 ;;
    --test) DO_TEST=1 ;;
    *) echo "不明な引数: $arg" >&2; exit 2 ;;
  esac
done

# ---- 事前チェック
if [ ! -d "$WF_SRC" ]; then
  echo "✗ 正本が見つからない: $WF_SRC" >&2; exit 1
fi
if [ "$(readlink -f "$WF_SRC")" = "$(readlink -f "$WF_DST")" ]; then
  echo "✗ SRC と DST が同一。~/mp_design から実行していないか確認。" >&2; exit 1
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "✗ rsync 未導入。一度だけ: sudo apt install -y rsync" >&2; exit 1
fi

echo "▶ 同期  $WF_SRC  →  $WF_DST"
mkdir -p "$WF_DST"
# ソースのみ同期。Windows 側 .venv / node_modules / dist / キャッシュは持ち込まない。
rsync -a --delete \
  --exclude '.venv/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.git/' \
  --exclude '.pytest_cache/' \
  "$WF_SRC/" "$WF_DST/"

cd "$WF_DST"

# ---- venv
if [ ! -d ".venv" ]; then
  echo "▶ venv 無し → 作成（python3.12）"
  python3.12 -m venv .venv
  DO_DEPS=1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [ "$DO_DEPS" -eq 1 ]; then
  echo "▶ Python 依存をインストール（-e .[dev]）"
  pip install --upgrade pip >/dev/null
  pip install -e ".[dev]"
  # OpenWind（Tier3 音響）は任意。失敗しても簡易TMMで継続するため非致命的に扱う。
  echo "▶ OpenWind（音響・任意）を試行"
  if pip install "openwind>=0.9"; then
    echo "  ✓ OpenWind 導入成功（物理モデル音合成が有効）"
  else
    echo "  ⚠ OpenWind 導入失敗 → 簡易TMMで継続（インピーダンス表示は可、物理モデル音は無効）"
  fi
fi

# ---- フロント
# nvm は .bashrc（対話シェル）でしか読まれないため、非対話実行では明示的に読む。
# これを怠ると PATH の Windows 版 npm（/mnt/c/Program Files/nodejs）に落ちて
# UNC パスで tsc が失敗する。
if ! command -v npm >/dev/null 2>&1 || case "$(command -v npm)" in /mnt/c/*) true ;; *) false ;; esac; then
  # shellcheck disable=SC1090,SC1091
  [ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh"
fi
if case "$(command -v npm)" in /mnt/c/*) true ;; *) false ;; esac; then
  echo "✗ Linux 版 npm が見つからない（Windows 版 $(command -v npm) を検出）。" >&2
  echo "  nvm を導入するか PATH を確認。" >&2; exit 1
fi

if [ ! -d "frontend/node_modules" ] || [ "$DO_DEPS" -eq 1 ]; then
  echo "▶ npm install"
  ( cd frontend && npm install )
fi
echo "▶ フロントビルド（vite）"
( cd frontend && npm run build )

# ---- 検証
echo "▶ OCP / IS_WSL 検証"
python - <<'PY'
import build123d, OCP  # noqa: F401
from saxsketch.server import app
print(f"  OCP ok: build123d {build123d.__version__}")
print(f"  IS_WSL = {app.IS_WSL}")
assert app.IS_WSL, "IS_WSL が False。WSL 上で実行しているか確認。"
PY

if [ "$DO_TEST" -eq 1 ]; then
  echo "▶ pytest"
  pytest
fi

echo "✓ 同期・ビルド完了。起動は: bash scripts/wsl_run.sh"
