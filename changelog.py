"""Offline release notes shipped alongside the application."""

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk


def show_changelog(parent, installed_version, existing=None):
    """Open or reuse an offline version browser, selecting the installed release."""
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_set()
        return existing
    path = Path(__file__).resolve().parent / "assets" / "changelog.json"
    releases = json.loads(path.read_text(encoding="utf-8"))
    releases.sort(
        key=lambda entry: tuple(int(part) for part in entry["version"].split(".")),
        reverse=True,
    )
    window = tk.Toplevel(parent)
    window.withdraw()
    window.title("IDFrame — Changelog")
    window.transient(parent)
    window.minsize(620, 360)
    page = ttk.Frame(window, padding=20)
    page.pack(fill="both", expand=True)
    ttk.Label(page, text="Changelog", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(page, text=f"Installed version: v{installed_version}").pack(
        anchor="w", pady=(4, 16)
    )
    body = ttk.Frame(page)
    body.pack(fill="both", expand=True)
    versions = tk.Listbox(
        body,
        width=16,
        exportselection=False,
        font=("Segoe UI", 11),
        activestyle="none",
        borderwidth=0,
        highlightthickness=1,
    )
    versions.pack(side="left", fill="y", padx=(0, 16))
    notes_frame = ttk.Frame(body)
    notes_frame.pack(side="left", fill="both", expand=True)
    scrollbar = ttk.Scrollbar(notes_frame)
    scrollbar.pack(side="right", fill="y")
    notes = tk.Text(
        notes_frame,
        wrap="word",
        font=("Segoe UI", 11),
        padx=14,
        pady=14,
        borderwidth=0,
        highlightthickness=0,
        yscrollcommand=scrollbar.set,
    )
    notes.pack(fill="both", expand=True)
    scrollbar.configure(command=notes.yview)
    notes.tag_configure("heading", font=("Segoe UI", 14, "bold"), spacing3=16)
    notes.tag_configure("entry", lmargin1=0, lmargin2=16, spacing3=10)
    for release in releases:
        versions.insert("end", f"v{release['version']}")

    def select_release(event=None):
        """Replace the read-only notes pane with the selected version's changes."""
        selection = versions.curselection()
        if not selection:
            return
        release = releases[selection[0]]
        notes.configure(state="normal")
        notes.delete("1.0", "end")
        notes.insert("end", f"Version {release['version']}\n", "heading")
        for change in release["changes"]:
            notes.insert("end", f"• {change}\n", "entry")
        notes.configure(state="disabled")
        notes.yview_moveto(0)

    versions.bind("<<ListboxSelect>>", select_release)
    selected = next(
        (
            i
            for i, release in enumerate(releases)
            if release["version"] == installed_version
        ),
        0,
    )
    versions.selection_set(selected)
    versions.see(selected)
    select_release()
    ttk.Button(page, text="Close", command=window.destroy).pack(
        anchor="e", pady=(16, 0)
    )
    window.bind("<Escape>", lambda event: window.destroy())
    parent.update_idletasks()
    width, height = 720, 460
    x = max(
        0,
        min(
            parent.winfo_rootx() + (parent.winfo_width() - width) // 2,
            parent.winfo_screenwidth() - width,
        ),
    )
    y = max(
        0,
        min(
            parent.winfo_rooty() + (parent.winfo_height() - height) // 2,
            parent.winfo_screenheight() - height,
        ),
    )
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.deiconify()
    return window
