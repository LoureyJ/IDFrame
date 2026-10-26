"""Person-based Windows filenames and a small offline name prompt."""

from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk
from ui_theme import palette_for, style_plain_widgets


def portrait_filename(person_name):
    """Validate a person's name and produce a portable PersonName_2x2.png filename."""
    name = "_".join(person_name.split()).strip("._ ")
    if not name:
        raise ValueError("Enter the person's name.")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError(
            'Names cannot contain < > : " / \\ | ? * or control characters.'
        )
    if len(name) > 100:
        raise ValueError("Use a name with at most 100 characters.")
    if name.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *[f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)],
    }:
        name = "Photo_" + name
    return name + "_2x2.png"


def available_photo_path(path):
    """Find an unused destination by adding numbered suffixes to duplicate filenames."""
    path = Path(path)
    if not path.exists():
        return path
    sequence = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{sequence:03d}{path.suffix}")
        if not candidate.exists():
            return candidate
        sequence += 1


def ask_person_name(parent, initial=""):
    """Show a centered modal name prompt with validation and a live filename preview."""
    window = tk.Toplevel(parent)
    window.withdraw()
    window.title("Name this portrait")
    window.transient(parent)
    window.resizable(False, False)
    result = []
    page = ttk.Frame(window, padding=22)
    page.pack(fill="both", expand=True)
    ttk.Label(page, text="Person's name", font=("Segoe UI", 13, "bold")).pack(
        anchor="w"
    )
    ttk.Label(page, text="Example: Juan Dela Cruz").pack(anchor="w", pady=(4, 10))
    name = tk.StringVar(window, value=initial)
    entry = ttk.Entry(page, textvariable=name, width=45)
    entry.pack(fill="x")
    preview = tk.StringVar(window)
    ttk.Label(page, textvariable=preview, wraplength=420).pack(anchor="w", pady=(10, 0))
    error = tk.StringVar(window)
    ttk.Label(page, textvariable=error, style="Error.TLabel", wraplength=420).pack(
        anchor="w", pady=(4, 12)
    )
    buttons = ttk.Frame(page)
    buttons.pack(fill="x")

    def confirm(event=None):
        """Accept a valid person name and close the modal prompt."""
        try:
            portrait_filename(name.get())
        except ValueError:
            return
        result.append(name.get().strip())
        window.destroy()

    accept = ttk.Button(buttons, text="Continue", command=confirm)
    accept.pack(side="right")
    ttk.Button(buttons, text="Cancel", command=window.destroy).pack(
        side="right", padx=8
    )

    def validate(*args):
        """Refresh the filename preview and disable confirmation for invalid names."""
        try:
            filename = portrait_filename(name.get())
        except ValueError as problem:
            preview.set("Filename: —")
            error.set(str(problem) if name.get().strip() else "")
            accept.configure(state="disabled")
        else:
            preview.set("Filename: " + filename)
            error.set("")
            accept.configure(state="normal")

    name.trace_add("write", validate)
    validate()
    window.bind("<Return>", confirm)
    window.bind("<Escape>", lambda event: window.destroy())
    window.update_idletasks()
    parent.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
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
    window.geometry(f"+{x}+{y}")
    style_plain_widgets(window, palette_for(parent))
    window.deiconify()
    window.grab_set()
    entry.focus_set()
    entry.selection_range(0, "end")
    window.wait_window()
    return result[0] if result else None
