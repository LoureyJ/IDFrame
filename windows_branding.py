"""Keep Windows shortcut and taskbar branding in step with OTA icon assets."""

import ctypes
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

# Retain this identity and executable names for compatibility with existing clients.
APP_ID = "PortraitStudio.Desktop"

# WScript maintains the existing shortcut's launch settings. The property store
# assigns the same taskbar identity as the running Python application.
SHORTCUT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential, Pack=4)]
public struct PortraitKey { public Guid format; public uint id; }
[StructLayout(LayoutKind.Explicit, Size=24)]
public struct PortraitValue {
    [FieldOffset(0)] public ushort type;
    [FieldOffset(8)] public IntPtr text;
}
[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPortraitProperties {
    [PreserveSig] int GetCount(out uint count);
    [PreserveSig] int GetAt(uint index, out PortraitKey key);
    [PreserveSig] int GetValue(ref PortraitKey key, out PortraitValue value);
    [PreserveSig] int SetValue(ref PortraitKey key, ref PortraitValue value);
    [PreserveSig] int Commit();
}
public static class PortraitShortcut {
    [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=true)]
    static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr context,
        uint flags, ref Guid iid, out IPortraitProperties store);
    [DllImport("shell32.dll", CharSet=CharSet.Unicode)]
    static extern void SHChangeNotify(uint change, uint flags, string path, IntPtr other);
    public static void NotifyDeleted(string path) {
        // Remove a missing shortcut from Explorer's cached desktop view.
        SHChangeNotify(0x4, 0x1005, path, IntPtr.Zero);
    }
    public static void NotifyRenamed(string oldPath, string newPath) {
        // Notify both directory entries; updating only the old item leaves a ghost icon.
        NotifyDeleted(oldPath);
        SHChangeNotify(0x2, 0x1005, newPath, IntPtr.Zero);
    }
    public static void SetIdentity(string path, string identity) {
        // Assign the taskbar grouping identity to this already verified owned shortcut.
        Guid iid = typeof(IPortraitProperties).GUID;
        IPortraitProperties store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iid, out store));
        PortraitKey key = new PortraitKey { format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), id = 5 };
        PortraitValue value = new PortraitValue { type = 31, text = Marshal.StringToCoTaskMemUni(identity) };
        try {
            Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
            Marshal.ThrowExceptionForHR(store.Commit());
        } finally {
            Marshal.FreeCoTaskMem(value.text);
            Marshal.ReleaseComObject(store);
        }
        SHChangeNotify(0x2000, 0x1005, path, IntPtr.Zero);
    }
}
'@
$launcher = [IO.Path]::GetFullPath($env:PORTRAIT_BRAND_LAUNCHER)
$runtime = [IO.Path]::GetFullPath($env:PORTRAIT_BRAND_RUNTIME)
$paths = @()
if ($env:PORTRAIT_BRAND_TEST_PATHS) {
    $paths = $env:PORTRAIT_BRAND_TEST_PATHS | ConvertFrom-Json
} else {
    $paths += Join-Path ([Environment]::GetFolderPath('Desktop')) 'Portrait Studio.lnk'
    $paths += Join-Path ([Environment]::GetFolderPath('Desktop')) 'IDFrame.lnk'
    $paths += Join-Path ([Environment]::GetFolderPath('Programs')) 'Portrait Studio\Portrait Studio.lnk'
    $paths += Join-Path ([Environment]::GetFolderPath('Programs')) 'Portrait Studio\IDFrame.lnk'
    $paths += Join-Path ([Environment]::GetFolderPath('Programs')) 'IDFrame\IDFrame.lnk'
    $pins = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
    if (Test-Path -LiteralPath $pins) {
        $paths += @(Get-ChildItem -LiteralPath $pins -Filter '*.lnk' -File | ForEach-Object { $_.FullName })
    }
}
$shell = New-Object -ComObject WScript.Shell
$updated = 0
$pins = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
foreach ($path in $paths) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        if ([IO.Path]::GetFileName($path) -eq 'Portrait Studio.lnk') {
            [PortraitShortcut]::NotifyDeleted($path)
        }
        continue
    }
    $link = $shell.CreateShortcut($path)
    if (-not $link.TargetPath) { continue }
    $target = [IO.Path]::GetFullPath($link.TargetPath)
    if ($target -ne $launcher -and $target -ne $runtime) { continue }
    $link.TargetPath = $launcher
    $link.WorkingDirectory = [IO.Path]::GetDirectoryName($launcher)
    $link.Description = 'IDFrame - Offline Background Remover'
    $link.IconLocation = $env:PORTRAIT_BRAND_ICON + ',0'
    $link.Save()
    [PortraitShortcut]::SetIdentity($path, $env:PORTRAIT_BRAND_APP_ID)
    if ([IO.Path]::GetFileName($path) -eq 'Portrait Studio.lnk' -and
        [IO.Path]::GetDirectoryName($path) -ne $pins) {
        $renamed = Join-Path ([IO.Path]::GetDirectoryName($path)) 'IDFrame.lnk'
        if (-not (Test-Path -LiteralPath $renamed)) {
            Move-Item -LiteralPath $path -Destination $renamed
            [PortraitShortcut]::NotifyRenamed($path, $renamed)
        }
    }
    $updated++
}
Write-Output $updated
"""


def set_taskbar_identity():
    """Assign the stable Windows application identity used by existing client shortcuts."""
    if os.name == "nt":
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        if setter(APP_ID) < 0:
            logging.getLogger(__name__).warning(
                "Windows could not set the IDFrame taskbar identity"
            )


def repair_shortcut_icons(install_root, assets, shortcut_paths=None):
    """Update only shortcuts targeting this installation, retaining other shortcuts."""
    if os.name != "nt":
        return 0
    install_root, assets = Path(install_root).resolve(), Path(assets).resolve()
    launcher = install_root / "PortraitStudio.exe"
    source = assets / "portrait-studio.ico"
    if not launcher.is_file() or not source.is_file():
        return 0
    data = source.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    # A content-specific filename avoids Windows reusing a cached older icon.
    directory = install_root / ".branding"
    directory.mkdir(exist_ok=True)
    state = directory / "state.json"
    expected = {"icon_sha256": checksum, "schema": 3, "app_name": "IDFrame"}
    if shortcut_paths is None and state.exists():
        try:
            if json.loads(state.read_text()) == expected:
                return 0
        except (ValueError, OSError):
            pass
    icon = directory / f"portrait-studio-{checksum[:16]}.ico"
    if not icon.exists():
        temporary = icon.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(icon)
    environment = os.environ.copy()
    environment.update(
        {
            "PORTRAIT_BRAND_LAUNCHER": str(launcher),
            "PORTRAIT_BRAND_RUNTIME": str(
                install_root / "payload" / "PortraitRuntime.exe"
            ),
            "PORTRAIT_BRAND_ICON": str(icon),
            "PORTRAIT_BRAND_APP_ID": APP_ID,
        }
    )
    environment["PORTRAIT_BRAND_TEST_PATHS"] = (
        json.dumps([str(Path(p).resolve()) for p in shortcut_paths])
        if shortcut_paths is not None
        else ""
    )
    powershell = (
        Path(os.environ["SystemRoot"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", SHORTCUT_SCRIPT],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=True,
    )
    count = int(result.stdout.strip())
    if shortcut_paths is None:
        temporary = state.with_suffix(".tmp")
        temporary.write_text(json.dumps(expected))
        temporary.replace(state)
    return count


def sync_installed_shortcuts(assets):
    # Source/dev sessions must not edit the installed user's shortcuts.
    """Refresh owned installed shortcuts while leaving source sessions and other apps alone."""
    if not getattr(sys, "frozen", False):
        return
    install_root = Path(sys.executable).resolve().parent.parent
    try:
        repair_shortcut_icons(install_root, assets)
    except (OSError, ValueError, subprocess.SubprocessError):
        # Branding must never prevent opening a photo or running offline.
        logging.getLogger(__name__).exception(
            "Could not refresh IDFrame shortcut icons"
        )
