"""Refresh the stable launcher after the installed application has exited."""
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def request_launcher_refresh():
    if not getattr(sys, "frozen", False) or os.environ.get("PORTRAIT_STUDIO_LAUNCHER") != "1":
        return
    root = Path(sys.executable).resolve().parent.parent
    candidate = root / "payload" / "PortraitLauncher.exe"
    current = root / "PortraitStudio.exe"
    if not candidate.is_file() or not current.is_file():
        return
    import hashlib
    if hashlib.sha256(candidate.read_bytes()).digest() == hashlib.sha256(current.read_bytes()).digest():
        return
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(candidate), "--refresh-launcher"], cwd=root, env=environment,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def refresh_launcher(root, public_key, try_lock, timeout=90):
    # These imports are embedded in the frozen launcher, not required by the GUI runtime.
    from deployment.common import digest, safe_path, verify_manifest
    root = Path(root).resolve()
    candidate = safe_path(root / "payload", "PortraitLauncher.exe")
    target = root / "PortraitStudio.exe"
    if target.is_symlink() or not target.is_file():
        raise ValueError("Invalid installed launcher")
    manifest = verify_manifest((root / "installed-manifest.json").read_bytes(), public_key)["payload"]
    expected = manifest["files"]["PortraitLauncher.exe"]
    if candidate.stat().st_size != expected["size"] or digest(candidate) != expected["sha256"]:
        raise ValueError("Launcher failed signed update verification")
    if digest(target) == expected["sha256"]:
        return False
    handle, temporary = tempfile.mkstemp(prefix=".launcher-refresh-", suffix=".exe", dir=root)
    os.close(handle)
    temporary = Path(temporary)
    try:
        shutil.copy2(candidate, temporary)
        if digest(temporary) != expected["sha256"]:
            raise ValueError("Staged launcher failed verification")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            lock = try_lock(root)
            if lock is not None:
                try:
                    # The application lock is held for the entire previous session.
                    # Windows can retain the executable mapping briefly after release.
                    os.replace(temporary, target)
                    return True
                except PermissionError:
                    pass
                finally:
                    lock.close()
            time.sleep(.2)
        logging.getLogger("updates").warning("Launcher refresh deferred until the next session closes")
        return False
    finally:
        temporary.unlink(missing_ok=True)
