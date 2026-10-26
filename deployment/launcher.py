"""Stable desktop entry point: check host, then start the installed application."""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from deployment.updater import apply_update, recover
from deployment.trust import PUBLIC_KEY
from windows_branding import set_taskbar_identity
from launcher_refresh import refresh_launcher


def set_window_icon(window, root_path):
    """Apply the installed camera icon to an updater or message window on Windows."""
    icon = root_path / "payload" / "assets" / "portrait-studio.ico"
    if os.name == "nt" and icon.is_file():
        window.iconbitmap(default=str(icon))
        window.iconbitmap(str(icon))


def check_updates(
    root_path, logger, progress=lambda text: None, transfer_progress=None
):
    # Recovery failures propagate; never run a partially installed release.
    """Recover interrupted updates, then check the host with an offline fallback."""
    recover(root_path)
    try:
        config = json.loads((root_path / "client.json").read_text(encoding="utf-8-sig"))
        status = apply_update(
            root_path,
            config["host_url"],
            PUBLIC_KEY,
            progress=progress,
            transfer_progress=transfer_progress,
        )
        logger.info(status)
        return status
    except Exception:
        logger.exception("Update skipped; retaining installed version")
        recover(root_path)
        return "Host unavailable or update rejected · using installed version"


def acquire_lock(root):
    """Acquire the client session lock or return None when another copy holds it."""
    import msvcrt

    handle = (root / ".client.lock").open("a+b")
    handle.seek(0)
    if not handle.read(1):
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def create_update_dialog(root_path):
    """Build and center the update window with its logo, status, and progress bar."""
    window = tk.Tk()
    window.withdraw()
    set_window_icon(window, root_path)
    window.title("Checking Updates")
    window.resizable(False, False)
    window.protocol("WM_DELETE_WINDOW", lambda: None)
    frame = ttk.Frame(window, padding=24)
    frame.pack(fill="both", expand=True)
    logo = root_path / "payload" / "assets" / "portrait-studio.png"
    if logo.is_file():
        from PIL import Image, ImageOps, ImageTk

        with Image.open(logo) as source:
            window.logo = ImageTk.PhotoImage(
                ImageOps.contain(source.convert("RGBA"), (96, 96))
            )
        ttk.Label(frame, image=window.logo).pack(pady=(0, 12))
    ttk.Label(frame, text="Checking Updates", font=("Segoe UI", 15, "bold")).pack()
    text = tk.StringVar(value="Connecting to your update host…")
    ttk.Label(frame, textvariable=text, anchor="center", wraplength=392).pack(
        fill="x", pady=(10, 16)
    )
    progress = ttk.Progressbar(frame, mode="indeterminate", maximum=100)
    progress.pack(fill="x")
    progress.start(12)
    window.update_idletasks()
    width, height = 450, max(190, window.winfo_reqheight())
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.deiconify()
    return window, text, progress


def main():
    """Handle launcher refresh, smoke tests, or the normal locked update-and-launch session."""
    set_taskbar_identity()
    root_path = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1] / "dist" / "client"
    )
    if sys.argv[1:] == ["--refresh-launcher"]:
        root_path = Path(sys.executable).resolve().parent.parent
    logger = logging.getLogger("updates")
    logger.setLevel(logging.INFO)
    logger.addHandler(
        RotatingFileHandler(
            root_path / "update.log",
            maxBytes=1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
    )
    if sys.argv[1:] == ["--refresh-launcher"]:
        try:
            refresh_launcher(root_path, PUBLIC_KEY, acquire_lock)
        except Exception:
            logger.exception("Launcher refresh rejected")
        return
    lock = acquire_lock(root_path)
    if lock is None:
        if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
            raise RuntimeError("Another instance is running")
        window = tk.Tk()
        set_window_icon(window, root_path)
        window.withdraw()
        messagebox.showinfo(
            "IDFrame",
            "IDFrame is already running. Close it before opening another copy.",
        )
        window.destroy()
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        try:
            status = check_updates(root_path, logger)
            environment = os.environ.copy()
            environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            executable = root_path / "payload" / "PortraitRuntime.exe"
            subprocess.run(
                [str(executable), "--smoke-test", sys.argv[2]],
                cwd=executable.parent,
                env=environment,
                check=True,
                timeout=60,
            )
            Path(sys.argv[2]).with_suffix(".update.json").write_text(
                json.dumps({"status": status})
            )
        finally:
            lock.close()
        return
    window, text, progress = create_update_dialog(root_path)
    events = queue.Queue()

    def worker():
        """Run update I/O off the UI thread and enqueue progress or completion events."""
        try:
            status = check_updates(
                root_path,
                logger,
                progress=lambda value: events.put(("progress", value)),
                transfer_progress=lambda completed, total: events.put(
                    ("bytes", (completed, total))
                ),
            )
        except Exception:
            logger.exception("Could not recover interrupted installation")
            events.put(
                (
                    "fatal",
                    "An interrupted update could not be restored. Reinstall IDFrame or contact your host administrator.",
                )
            )
            return
        events.put(("done", status))

    child = []

    def poll():
        """Apply queued status changes on the UI thread and start the runtime after updates finish."""
        while not events.empty():
            kind, value = events.get_nowait()
            if kind == "progress":
                text.set(value)
            elif kind == "bytes":
                completed, total = value
                progress.stop()
                progress.configure(
                    mode="determinate", value=95 * completed / max(total, 1)
                )
            elif kind == "fatal":
                messagebox.showerror("IDFrame", value)
                window.destroy()
                return
            else:
                progress.stop()
                progress.configure(mode="determinate", value=100)
                executable = root_path / "payload" / "PortraitRuntime.exe"
                if not executable.is_file():
                    messagebox.showerror(
                        "IDFrame",
                        "Application files are missing. Reinstall the program.",
                    )
                    window.destroy()
                    return
                environment = os.environ.copy()
                environment["PORTRAIT_UPDATE_STATUS"] = value
                environment["PORTRAIT_STUDIO_LAUNCHER"] = "1"
                environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
                try:
                    child.append(
                        subprocess.Popen(
                            [str(executable)],
                            cwd=executable.parent,
                            env=environment,
                            creationflags=(
                                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                            ),
                        )
                    )
                except OSError:
                    logger.exception("Could not start application")
                    messagebox.showerror(
                        "IDFrame",
                        "Could not start the installed application. See update.log or reinstall.",
                    )
                window.destroy()
                return
        window.after(75, poll)

    threading.Thread(target=worker, daemon=True).start()
    window.after(75, poll)
    window.mainloop()
    if child:
        child[0].wait()
    lock.close()


if __name__ == "__main__":
    main()
