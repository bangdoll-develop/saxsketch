"""ファイル選択ダイアログ。**サーバのプロセス内では絶対に開かない。**

以前は `app.py` の中で `asyncio.to_thread` → tkinter を呼んでいた。3 つ壊れていた。

1. **返ってこない。** `POST /api/dialog` はダイアログを閉じるまで応答しないので、
   出した窓が操作しづらい環境（WSLg 越しの X11 など）では UI ごと固まって見える。
2. **キャンセルしても止まらない。** `asyncio.to_thread` は走り出したワーカーを
   中断できない。ブラウザが切ってリクエストが `CancelledError` で落ちても
   **Tk のウィンドウとスレッドは残る**。押し直すたびに別スレッドで Tk interp が
   増え、uvicorn の終了時にも join 待ちになる。
3. **サーバ側の OS のダイアログが出る。** バックエンドは WSL2 なので Linux の
   ダイアログが開き、返るのも Linux パスだった。利用者が見ているのは Windows。

対策は 1 つで足りる ——「**ダイアログは必ず別プロセスで出す**」。プロセスなら
kill できるので 2. が消え、どの OS のダイアログを出すかを選べるので 3. も消える。
1. は呼ぶ側（`/api/dialog` にタイムアウト、UI にフォールバック）で受ける。

なお**リモートのサーバに対しては、どの実装でも正解にならない**。ダイアログは
サーバのデスクトップに出るので、手元のブラウザには何も現れない。ローカル同居の
ときだけ使う機能として `/api/capabilities` の `native_dialogs` で宣言し、
そうでなければ UI 側のパス入力に落とす。
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import importlib.util
import os
import sys
from pathlib import Path

from .hostenv import IS_WSL, powershell_exe, to_win_path, to_wsl_path

#: 呼べるモード。`app.py` の `DialogReq.mode` と対応。
MODES = ("save", "open", "open_model", "dir")

#: 既定の待ち時間 [秒]。利用者がダイアログを開いたまま席を立っても、
#: いつかは必ず返してプロセスを回収する。
DEFAULT_TIMEOUT = 180.0

_TITLES = {
    "save": "プロジェクトを保存",
    "open": "プロジェクトを開く",
    "open_model": "編集済みモデルを取込",
    "dir": "出力先フォルダを選択",
}
_MODEL_EXTS = ("stl", "step", "stp", "3mf", "obj", "ply")

# 親子で受け渡す 1 行プロトコル。パスは UTF-8 を base64 にして渡す
# （日本語のファイル名が WSL⇄Windows のコンソール符号化を通っても壊れない）。
_OK = "OK "
_CANCEL = "CANCEL"


# ------------------------------------------------------------------ 呼び出し口

def available() -> bool:
    """この環境でダイアログを出せるか。`/api/capabilities` が使う。

    **「出せる」は「利用者に見える」を意味しない。** サーバがリモートなら
    ダイアログはサーバの画面に出る。その判定は呼ぶ側（`_is_local_client`）。
    """
    if powershell_exe() is not None:
        return True
    if os.name != "posix":
        return False
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    return importlib.util.find_spec("tkinter") is not None


async def pick(mode: str, suggested: str = "",
               *, timeout: float = DEFAULT_TIMEOUT) -> tuple[str | None, str]:
    """ダイアログを出してパスを 1 つ選ばせる。

    戻り値は `(パス or None, 理由)`。理由は UI がフォールバックを出すかどうかの
    判断に使う:

    - `"ok"` … 選ばれた
    - `"cancelled"` … **利用者が閉じた**。UI は黙って何もしない
    - `"unavailable"` … ダイアログを出せない環境。UI はパス入力へ落とす
    - `"timeout"` … 時間切れ。同上
    """
    if mode not in MODES:
        return None, "unavailable"
    argv = _backend_argv(mode, suggested)
    if argv is None:
        return None, "unavailable"

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except OSError:
        return None, "unavailable"

    try:
        out, _err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        # 時間切れはキャンセルではないので、**死ぬのを見届けてから**返せる。
        await _terminate(proc)
        return None, "timeout"
    except asyncio.CancelledError:
        # ブラウザが切った・サーバが止まる。**ここで殺さないと窓が残る**。
        _kill_nowait(proc)
        raise

    return _parse(out.decode("utf-8", "replace"))


def _parse(text: str) -> tuple[str | None, str]:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line == _CANCEL:
            return None, "cancelled"
        if line.startswith(_OK):
            try:
                path = base64.b64decode(line[len(_OK):]).decode("utf-8")
            except Exception:
                return None, "unavailable"
            if not path:
                return None, "cancelled"
            return (to_wsl_path(path) if IS_WSL else path), "ok"
    return None, "unavailable"


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """殺して回収する。回収まで待つのでパイプも確実に閉じる。"""
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.wait(), 5.0)


def _kill_nowait(proc: asyncio.subprocess.Process) -> None:
    """待たずに殺す。キャンセル経路から呼ぶので `await` してはいけない。"""
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(RuntimeError):
        asyncio.get_running_loop().create_task(_reap(proc))


async def _reap(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(Exception):
        await proc.wait()


# ------------------------------------------------------------------ バックエンド選択

def _backend_argv(mode: str, suggested: str) -> list[str] | None:
    """子プロセスの argv。出せない環境では None。

    テストはここを差し替えて、実際の窓を出さずに timeout / kill を確かめる。
    """
    exe = powershell_exe()
    if exe is not None:
        return [exe, "-NoProfile", "-NonInteractive", "-STA",
                "-EncodedCommand", _encoded(_ps_script(mode, suggested))]
    if os.name == "posix":
        return [sys.executable, "-m", __name__, mode, suggested]
    return None


def _encoded(script: str) -> str:
    """PowerShell の `-EncodedCommand`（UTF-16LE の base64）。

    `-Command` に組み立てた文字列を渡すと、日本語のタイトルと `C:\\` の
    バックスラッシュが WSL の exec 境界と PowerShell のパーサを二重に通って壊れる。
    符号化して渡せばどちらの層にも解釈されない。
    """
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _ps_str(s: str) -> str:
    """PowerShell の単一引用符文字列リテラル（変数展開もエスケープも起きない）。"""
    return "'" + str(s).replace("'", "''") + "'"


#: 窓を最前面へ引き上げる P/Invoke。**これが無いとダイアログは裏に出る。**
#:
#: Windows は「直前の入力を受け取っていないプロセス」の `SetForegroundWindow` を
#: 黙って拒否する（フォアグラウンドロック）。このダイアログを出すのは利用者が
#: 触っていないバックグラウンドのサーバから起動したプロセスなので、必ず拒否される。
#: `AttachThreadInput` で現在の前面スレッドに入力状態を繋ぐと許可される —— 昔からの
#: 定石で、ここでは他に手が無い。合わせて HWND_TOPMOST も立てる。
_RAISE_HELPER = """
Add-Type -Namespace SaxSketch -Name Win -MemberDefinition @'
delegate bool EnumProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] static extern bool EnumThreadWindows(uint tid, EnumProc cb, IntPtr l);
[DllImport("user32.dll", CharSet = CharSet.Unicode)]
static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] static extern bool SetWindowPos(
    IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
[DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool join);
[DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
[DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
[StructLayout(LayoutKind.Sequential)] struct FLASHWINFO {
  public uint cbSize; public IntPtr hwnd; public uint dwFlags;
  public uint uCount; public uint dwTimeout;
}
[DllImport("user32.dll")] static extern bool FlashWindowEx(ref FLASHWINFO fw);
// 自分のスレッドが持つ可視のダイアログ（クラス #32770）。題名では探さない ——
// FolderBrowserDialog の題名は OS 側の文字列で、こちらの Description ではない。
public static IntPtr FindOurDialog() {
  IntPtr found = IntPtr.Zero;
  EnumThreadWindows(GetCurrentThreadId(), delegate(IntPtr h, IntPtr l) {
    var sb = new System.Text.StringBuilder(64);
    GetClassName(h, sb, 64);
    if (sb.ToString() == "#32770" && IsWindowVisible(h)) { found = h; return false; }
    return true;
  }, IntPtr.Zero);
  return found;
}
public static void Raise(IntPtr h) {
  if (h == IntPtr.Zero) { return; }
  SetWindowPos(h, new IntPtr(-1), 0, 0, 0, 0, 0x0003);   // HWND_TOPMOST | NOSIZE | NOMOVE
  uint me = GetCurrentThreadId();
  uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero);
  bool joined = (fg != 0 && fg != me && AttachThreadInput(me, fg, true));
  BringWindowToTop(h);
  SetForegroundWindow(h);
  if (joined) { AttachThreadInput(me, fg, false); }
  // 前面を奪えないことはある（実測でも成功したり失敗したりする）。TOPMOST は
  // 必ず立つのでブラウザの上には見えるが、キーボードは他所へ行ったままなので、
  // せめてタスクバーを点滅させて気づけるようにする。
  if (GetForegroundWindow() != h) {
    FLASHWINFO fi = new FLASHWINFO();
    fi.cbSize = (uint)Marshal.SizeOf(typeof(FLASHWINFO));
    fi.hwnd = h;
    fi.dwFlags = 0x0000000F;   // FLASHW_ALL | FLASHW_TIMERNOFG
    fi.uCount = 3;
    FlashWindowEx(ref fi);
  }
}
'@
"""


def _ps_script(mode: str, suggested: str) -> str:
    """Windows ネイティブのダイアログを出す PowerShell。

    **隠しフォームを owner にして TopMost を立てる**のが要点。コンソールから
    起動したプロセスは前面化を許されないことがあり、owner を渡さないと
    ブラウザの裏に出る —— それは利用者にとって「フリーズ」と区別がつかない。
    """
    # suggested はモードによって「フォルダ」だったり「ファイル名だけ」だったりする。
    # 区切りを含まないものを Path として解決すると、サーバの cwd（WSL 側）が
    # 初期フォルダに化けるので、含むときだけ分ける。
    init_dir, init_file = "", ""
    if mode == "dir":
        init_dir = suggested
    elif suggested:
        src = Path(suggested)
        if "/" in suggested or "\\" in suggested:
            if src.is_dir():
                init_dir = suggested
            else:
                init_dir, init_file = str(src.parent), src.name
        else:
            init_file = suggested   # 「名前だけ」。初期フォルダは OS に任せる
    if init_dir and IS_WSL:
        init_dir = to_win_path(init_dir)

    if mode == "dir":
        body = f"""
$dlg = New-Object System.Windows.Forms.FolderBrowserDialog
$dlg.Description = {_ps_str(_TITLES[mode])}
$dlg.ShowNewFolderButton = $true
if ({_ps_str(init_dir)}) {{ $dlg.SelectedPath = {_ps_str(init_dir)} }}
$result = $dlg.ShowDialog($owner)
$picked = $dlg.SelectedPath
"""
    else:
        if mode == "open_model":
            pats = ";".join(f"*.{e}" for e in _MODEL_EXTS)
            filt = f"3Dモデル ({pats})|{pats}|すべてのファイル (*.*)|*.*"
        else:
            filt = "SaxSketch プロジェクト (*.wproj)|*.wproj"
        kind = "SaveFileDialog" if mode == "save" else "OpenFileDialog"
        extra = ("$dlg.DefaultExt = 'wproj'\n$dlg.AddExtension = $true\n"
                 "$dlg.OverwritePrompt = $true\n" if mode == "save"
                 else "$dlg.CheckFileExists = $true\n")
        body = f"""
$dlg = New-Object System.Windows.Forms.{kind}
$dlg.Title = {_ps_str(_TITLES[mode])}
$dlg.Filter = {_ps_str(filt)}
{extra}if ({_ps_str(init_dir)}) {{ $dlg.InitialDirectory = {_ps_str(init_dir)} }}
if ({_ps_str(init_file)}) {{ $dlg.FileName = {_ps_str(init_file)} }}
$result = $dlg.ShowDialog($owner)
$picked = $dlg.FileName
"""

    return f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
{_RAISE_HELPER}
[System.Windows.Forms.Application]::EnableVisualStyles()
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.Opacity = 0
$owner.Show()
$owner.Activate()
[SaxSketch.Win]::Raise($owner.Handle)
# ダイアログ自身を前面に出す。**所有者を TopMost にしても伝播しない**（実測:
# 出た窓は visible=True TOPMOST=False isForeground=False でブラウザの裏だった）。
# 窓が出るのは ShowDialog の中なので、その中で回るメッセージループに
# タイマーを乗せて掴む。掴めたら 1 回で止める。
$script:wfTimer = New-Object System.Windows.Forms.Timer
$script:wfTimer.Interval = 120
$script:wfTimer.Add_Tick({{
  $h = [SaxSketch.Win]::FindOurDialog()
  if ($h -ne [IntPtr]::Zero) {{ [SaxSketch.Win]::Raise($h); $script:wfTimer.Stop() }}
}})
$script:wfTimer.Start()
try {{
{body}
}} finally {{
  $script:wfTimer.Stop()
  $script:wfTimer.Dispose()
  $owner.Close()
  $owner.Dispose()
}}
if ($result -ne [System.Windows.Forms.DialogResult]::OK -or -not $picked) {{
  [Console]::Out.Write('{_CANCEL}')
  exit 0
}}
$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($picked))
[Console]::Out.Write('{_OK}' + $b64)
exit 0
"""


# ------------------------------------------------------------------ 素の Linux 用（子プロセスとして実行される）

def _tk_pick(mode: str, suggested: str) -> str:
    """tkinter のダイアログ。**この関数はサーバ本体では呼ばれない。**

    `python -m saxsketch.server.filedialog <mode> <suggested>` として
    子プロセスで動く。PowerShell が無い素の Linux デスクトップ向けの退路。
    """
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if mode == "save":
            return filedialog.asksaveasfilename(
                title=_TITLES[mode], defaultextension=".wproj",
                initialfile=Path(suggested).name if suggested else "",
                filetypes=[("SaxSketch プロジェクト", "*.wproj")])
        if mode == "open":
            return filedialog.askopenfilename(
                title=_TITLES[mode],
                filetypes=[("SaxSketch プロジェクト", "*.wproj")])
        if mode == "open_model":
            kwargs = ({"initialdir": suggested}
                      if suggested and Path(suggested).is_dir() else {})
            return filedialog.askopenfilename(
                title=_TITLES[mode],
                filetypes=[("3Dモデル", " ".join(f"*.{e}" for e in _MODEL_EXTS)),
                           ("すべて", "*.*")],
                **kwargs)
        return filedialog.askdirectory(title=_TITLES[mode])
    finally:
        root.destroy()


def _main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "open"
    suggested = argv[2] if len(argv) > 2 else ""
    try:
        picked = _tk_pick(mode, suggested)
    except Exception as e:  # DISPLAY 無し等。親は "unavailable" として扱う
        print(f"filedialog: {e}", file=sys.stderr)
        return 2
    if not picked:
        sys.stdout.write(_CANCEL)
        return 0
    sys.stdout.write(_OK + base64.b64encode(picked.encode("utf-8")).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
