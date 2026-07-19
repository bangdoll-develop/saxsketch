#!/usr/bin/env bash
# SaxSketch — WSL サーバ起動スクリプト
#
# 使い方（WSL Ubuntu シェルで）:
#   bash ~/mp_design/scripts/wsl_run.sh
#
# 起動後、Windows 側ブラウザで http://localhost:8712 を開く。
# 停止は Ctrl+C。
#
# 環境変数で上書き可: WF_DST（WSL 稼働コピー）
set -euo pipefail

WF_DST="${WF_DST:-$HOME/mp_design}"
cd "$WF_DST"

if [ ! -d ".venv" ]; then
  echo "✗ .venv 無し。先に: bash scripts/wsl_sync.sh --deps" >&2; exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f "frontend/dist/index.html" ]; then
  echo "⚠ frontend/dist 未ビルド。UI が出ない場合は: bash scripts/wsl_sync.sh" >&2
fi

echo "▶ SaxSketch 起動 → http://localhost:8712 （停止: Ctrl+C）"
exec python -m saxsketch.server.app
