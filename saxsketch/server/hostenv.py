"""ホスト環境の差異（WSL ⇄ Windows ⇄ Linux）を吸収する小さな層。

`app.py` に置いていたものを切り出した。切り出す理由は `filedialog.py` と
`state.py` の両方が要るようになったから。`app.py` は `filedialog.py` を import
するので、逆向きの import は循環になる。

**WSL で動かす前提が入っている。** SAC 回避のためバックエンドは WSL2(Linux) で
動くが、利用者は Windows 側のブラウザとエクスプローラを見ている。GUI と
「既定のフォルダ」は Windows 側のものでなければ意味がない。
"""
from __future__ import annotations

import base64
import functools
import os
import platform
import shutil
import subprocess
from pathlib import Path

IS_WSL = "microsoft" in platform.uname().release.lower()

#: PowerShell の探索先。PATH interop が効かない構成でも拾えるよう絶対パスも見る。
_PWSH_CANDIDATES = (
    "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    if IS_WSL else
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
)


def to_win_path(p: str) -> str:
    """WSL パス → Windows パス（wslpath -w）。Windows 実行時/失敗時は原文を返す。"""
    if not IS_WSL:
        return str(p)
    try:
        return subprocess.check_output(["wslpath", "-w", str(p)], text=True).strip()
    except Exception:
        return str(p)


def to_wsl_path(p: str) -> str:
    """Windows パス(C:\\..) → WSL パス(/mnt/c/..)。既に WSL パスなら原文を返す。"""
    if not IS_WSL:
        return str(p)
    try:
        return subprocess.check_output(["wslpath", "-u", str(p)], text=True).strip()
    except Exception:
        return str(p)


def host_kind() -> str:
    """`"wsl"` / `"windows"` / `"linux"`。UI と `/api/capabilities` の表示用。"""
    if IS_WSL:
        return "wsl"
    return "windows" if os.name == "nt" else "linux"


def powershell_exe() -> str | None:
    """Windows PowerShell の実行パス。使えない環境では None。

    WSL からは PATH interop で `powershell.exe` が引ける。interop を切っている
    構成もあるので、見つからなければ標準の絶対パスを直接見る。
    """
    if not (IS_WSL or os.name == "nt"):
        return None
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if found:
        return found
    for cand in _PWSH_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


@functools.lru_cache(maxsize=1)
def windows_documents() -> Path | None:
    """Windows の「ドキュメント」フォルダ（WSL から見えるパス）。使えなければ None。

    `%USERPROFILE%\\Documents` の決め打ちにはしない。OneDrive バックアップを
    有効にしていると実体が `%USERPROFILE%\\OneDrive\\ドキュメント` へ移り、
    決め打ちは**存在しないフォルダ**を指す。シェルに聞けば移動先が返る。
    """
    exe = powershell_exe()
    if exe is None:
        return None
    # **base64 で受け取る。** PowerShell の標準出力はコンソールのコードページ
    # （日本語環境では CP932）で流れてくるので、日本語を含むパス
    # （実測: `C:\Users\<user>\OneDrive\ドキュメント`）を UTF-8 として読むと
    # `UnicodeDecodeError` になり、この関数が黙って None を返していた。
    script = ("$p=[Environment]::GetFolderPath('MyDocuments');"
              "[Console]::Out.Write("
              "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($p)))")
    try:
        raw = subprocess.check_output(
            [exe, "-NoProfile", "-NonInteractive", "-Command", script],
            timeout=20, stderr=subprocess.DEVNULL)
        out = base64.b64decode(raw.strip()).decode("utf-8").strip()
    except Exception:
        return None
    if not out:
        return None
    path = Path(to_wsl_path(out))
    return path if path.is_dir() else None
