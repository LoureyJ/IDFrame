"""Dependency-free desktop palettes and per-user appearance preferences."""

import json
import logging
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

PALETTES = {
    "Light": {
        "app": "#f3f5f8",
        "card": "#ffffff",
        "field": "#f0f3f8",
        "text": "#17243b",
        "muted": "#596b85",
        "border": "#dbe2ec",
        "accent": "#1765eb",
        "hover": "#0b51ca",
        "accent_text": "#ffffff",
        "selection": "#dceaff",
        "disabled": "#e8ecf2",
        "disabled_text": "#738095",
        "preview": "#e8edf4",
        "error": "#b42318",
    },
    "Dark": {
        "app": "#171b22",
        "card": "#222832",
        "field": "#2c3441",
        "text": "#eef2f8",
        "muted": "#abb8cc",
        "border": "#3b4656",
        "accent": "#28d0c5",
        "hover": "#54e0d7",
        "accent_text": "#102522",
        "selection": "#204f55",
        "disabled": "#303744",
        "disabled_text": "#8996aa",
        "preview": "#13171d",
        "error": "#ffb4ab",
    },
}


def preferences_file():
    """Locate user settings outside the application payload so OTA cannot replace them."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".config")
    return base / "IDFrame" / "preferences.json"


def _read_preferences(path):
    """Read a preference object, treating missing or malformed files as empty settings."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def load_theme(path=None):
    """Return a supported persisted appearance, defaulting safely to Light."""
    name = _read_preferences(path or preferences_file()).get("theme")
    return name if isinstance(name, str) and name in PALETTES else "Light"


def save_theme(name, path=None):
    """Atomically remember appearance without making persistence failures fatal."""
    if name not in PALETTES:
        return False
    path = Path(path or preferences_file())
    temporary = None
    try:
        settings = _read_preferences(path)
        settings["theme"] = name
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".appearance-", dir=path.parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(settings, output, indent=2)
        os.replace(temporary, path)
        return True
    except OSError:
        logging.getLogger(__name__).warning("Could not remember appearance preference")
        return False
    finally:
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def palette_for(widget):
    """Find the active root palette for a widget or auxiliary window."""
    return PALETTES.get(
        getattr(widget._root(), "_idframe_theme", "Light"), PALETTES["Light"]
    )


def style_plain_widgets(widget, colors):
    """Recolor Tk surfaces recursively without changing image pixels or widget state."""
    if isinstance(widget, ttk.Combobox):
        # These listboxes belong to Tcl, not Python's widget tree. Recolor an
        # existing popup as well as setting defaults for future ones.
        try:
            popup = widget.tk.call("ttk::combobox::PopdownWindow", str(widget))
            widget.tk.call(
                str(popup) + ".f.l",
                "configure",
                "-background",
                colors["field"],
                "-foreground",
                colors["text"],
                "-selectbackground",
                colors["selection"],
                "-selectforeground",
                colors["text"],
            )
        except tk.TclError:
            pass
    elif isinstance(widget, (tk.Tk, tk.Toplevel)):
        widget.configure(background=colors["app"])
    elif isinstance(widget, tk.Canvas):
        widget.configure(background=colors[getattr(widget, "theme_surface", "preview")])
    elif isinstance(widget, tk.Label):
        widget.configure(background=colors["preview"], foreground=colors["muted"])
    elif isinstance(widget, (tk.Text, tk.Listbox)):
        widget.configure(
            background=colors["card"],
            foreground=colors["text"],
            selectbackground=colors["selection"],
            selectforeground=colors["text"],
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )
        if isinstance(widget, tk.Text):
            widget.configure(insertbackground=colors["text"])
    for child in widget.winfo_children():
        style_plain_widgets(child, colors)


def apply_theme(root, name):
    """Update ttk styles and all existing Tk windows while retaining editing state."""
    name = name if name in PALETTES else "Light"
    root._idframe_theme = name
    colors = PALETTES[name]
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        ".", font=("Segoe UI", 10), foreground=colors["text"], background=colors["card"]
    )
    style.configure("TFrame", background=colors["card"])
    style.configure("App.TFrame", background=colors["app"])
    style.configure(
        "Card.TFrame",
        background=colors["card"],
        bordercolor=colors["border"],
        borderwidth=1,
        relief="solid",
    )
    style.configure("TLabel", background=colors["card"], foreground=colors["text"])
    style.configure(
        "Title.TLabel", background=colors["app"], font=("Segoe UI", 23, "bold")
    )
    style.configure("App.TLabel", background=colors["app"], foreground=colors["muted"])
    style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
    style.configure("Muted.TLabel", foreground=colors["muted"])
    style.configure("Error.TLabel", foreground=colors["error"])
    style.configure(
        "TButton",
        padding=(12, 10),
        background=colors["field"],
        foreground=colors["text"],
        bordercolor=colors["border"],
        borderwidth=1,
    )
    style.map(
        "TButton",
        background=[("disabled", colors["disabled"]), ("active", colors["selection"])],
        foreground=[("disabled", colors["disabled_text"])],
    )
    style.configure(
        "Accent.TButton",
        background=colors["accent"],
        foreground=colors["accent_text"],
        font=("Segoe UI", 11, "bold"),
        padding=(12, 13),
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", colors["disabled"]), ("active", colors["hover"])],
        foreground=[
            ("disabled", colors["disabled_text"]),
            ("!disabled", colors["accent_text"]),
        ],
    )
    for widget in ("TCombobox", "TEntry"):
        style.configure(
            widget,
            fieldbackground=colors["field"],
            foreground=colors["text"],
            insertcolor=colors["text"],
            arrowcolor=colors["text"],
            padding=7,
            bordercolor=colors["border"],
        )
        style.map(
            widget,
            fieldbackground=[
                ("disabled", colors["disabled"]),
                ("readonly", colors["field"]),
            ],
            foreground=[
                ("disabled", colors["disabled_text"]),
                ("readonly", colors["text"]),
            ],
            selectbackground=[("!disabled", colors["selection"])],
            selectforeground=[("!disabled", colors["text"])],
        )
        style.map(
            widget,
            background=[
                ("disabled", colors["disabled"]),
                ("active", colors["selection"]),
                ("!disabled", colors["field"]),
            ],
            arrowcolor=[
                ("disabled", colors["disabled_text"]),
                ("!disabled", colors["text"]),
            ],
        )
    style.configure(
        "Horizontal.TScale",
        background=colors["card"],
        troughcolor=colors["field"],
        bordercolor=colors["border"],
        lightcolor=colors["accent"],
        darkcolor=colors["accent"],
    )
    style.configure(
        "Horizontal.TProgressbar",
        background=colors["accent"],
        troughcolor=colors["field"],
        borderwidth=0,
    )
    style.configure("TSeparator", background=colors["border"])
    style.configure(
        "Vertical.TScrollbar",
        background=colors["field"],
        troughcolor=colors["card"],
        arrowcolor=colors["text"],
    )
    for widget in ("Horizontal.TScale", "Vertical.TScrollbar"):
        style.map(
            widget,
            background=[
                ("disabled", colors["disabled"]),
                ("active", colors["selection"]),
                ("!disabled", colors["field"]),
            ],
            arrowcolor=[
                ("disabled", colors["disabled_text"]),
                ("!disabled", colors["text"]),
            ],
        )
    root.option_add("*TCombobox*Listbox.background", colors["field"])
    root.option_add("*TCombobox*Listbox.foreground", colors["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", colors["selection"])
    root.option_add("*TCombobox*Listbox.selectForeground", colors["text"])
    style_plain_widgets(root, colors)
    install_rounded_styles(root, style, colors)


def _shape_photo(root, key, fill, outline=None, *, circle=False, dot=False):
    """Draw a smooth scalable widget surface using the already bundled Pillow core."""
    size = 24 if circle else 36
    scale = 4
    image = Image.new("RGBA", (size * scale, size * scale))
    draw = ImageDraw.Draw(image)
    bounds = (2 * scale, 2 * scale, (size - 2) * scale, (size - 2) * scale)
    if circle:
        draw.ellipse(bounds, fill=fill, outline=outline, width=2 * scale)
        if dot:
            draw.ellipse((8 * scale, 8 * scale, 16 * scale, 16 * scale), fill=outline)
    else:
        draw.rounded_rectangle(
            bounds, radius=10 * scale, fill=fill, outline=outline, width=scale
        )
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    photos = getattr(root, "_idframe_shape_photos", {})
    if key in photos:
        photos[key].paste(image)
    else:
        photos[key] = ImageTk.PhotoImage(image, master=root)
    root._idframe_shape_photos = photos
    return photos[key]


def install_rounded_styles(root, style, colors):
    """Give native accessible ttk controls rounded surfaces and clean circular indicators."""
    definitions = {
        "Button": [
            ("normal", "field", "border"),
            ("active", "selection", "border"),
            ("disabled", "disabled", "disabled"),
            ("focus", "field", "accent"),
        ],
        "Accent": [
            ("normal", "accent", "accent"),
            ("active", "hover", "hover"),
            ("disabled", "disabled", "disabled"),
            ("focus", "accent", "text"),
        ],
        "Card": [("normal", "card", "border")],
        "Mode": [
            ("normal", "card", "card"),
            ("active", "field", "field"),
            ("selected", "selection", "accent"),
            ("disabled", "card", "card"),
            ("focus", "field", "text"),
        ],
        "Theme": [
            ("normal", "field", "border"),
            ("selected", "accent", "accent"),
            ("active", "selection", "border"),
            ("focus", "field", "text"),
        ],
    }
    for kind, variants in definitions.items():
        photos = {
            state: _shape_photo(root, kind + state, colors[fill], colors[border])
            for state, fill, border in variants
        }
        element = "Studio." + kind + ".surface"
        if element not in style.element_names():
            states = [
                (state, photos[state])
                for state in ("disabled", "focus", "selected", "active")
                if state in photos
            ]
            style.element_create(
                element,
                "image",
                photos["normal"],
                *states,
                border=12,
                padding=0,
                sticky="nsew",
            )
    for name, kind in (
        ("TButton", "Button"),
        ("Accent.TButton", "Accent"),
        ("Theme.TRadiobutton", "Theme"),
    ):
        style.layout(
            name,
            [
                (
                    "Studio." + kind + ".surface",
                    {
                        "sticky": "nsew",
                        "children": [
                            (
                                "Button.padding",
                                {
                                    "sticky": "nsew",
                                    "children": [("Button.label", {"sticky": "nsew"})],
                                },
                            )
                        ],
                    },
                )
            ],
        )
    # Transparent image corners must reveal the parent surface, rather than a
    # rectangular native button fill behind the rounded image.
    for name in ("TButton", "Accent.TButton"):
        style.configure(name, background=colors["card"])
        style.map(
            name,
            background=[
                ("disabled", colors["card"]),
                ("active", colors["card"]),
                ("!disabled", colors["card"]),
            ],
        )
    style.configure(
        "Card.TFrame", background=colors["app"], borderwidth=0, relief="flat"
    )
    style.configure("Theme.TRadiobutton", padding=(12, 8))
    style.configure("Theme.TRadiobutton", background=colors["app"])
    style.map(
        "Theme.TRadiobutton",
        foreground=[
            ("focus", colors["text"]),
            ("selected", colors["accent_text"]),
            ("!selected", colors["text"]),
        ],
    )
    style.layout("Card.TFrame", [("Studio.Card.surface", {"sticky": "nsew"})])
    off = _shape_photo(root, "radio-off", colors["card"], colors["muted"], circle=True)
    on = _shape_photo(
        root, "radio-on", colors["selection"], colors["accent"], circle=True, dot=True
    )
    disabled = _shape_photo(
        root, "radio-disabled", colors["card"], colors["disabled_text"], circle=True
    )
    if "Studio.Radio.indicator" not in style.element_names():
        style.element_create(
            "Studio.Radio.indicator",
            "image",
            off,
            ("disabled", disabled),
            ("selected", on),
            sticky="",
        )
    style.layout(
        "Mode.TRadiobutton",
        [
            (
                "Studio.Mode.surface",
                {
                    "sticky": "nsew",
                    "children": [
                        (
                            "Radiobutton.padding",
                            {
                                "sticky": "nsew",
                                "children": [
                                    (
                                        "Studio.Radio.indicator",
                                        {"side": "left", "sticky": ""},
                                    ),
                                    (
                                        "Radiobutton.label",
                                        {"side": "left", "sticky": "w"},
                                    ),
                                ],
                            },
                        )
                    ],
                },
            )
        ],
    )
    style.configure("Mode.TRadiobutton", padding=(8, 5), font=("Segoe UI", 10))
    style.configure("Mode.TRadiobutton", background=colors["card"])
    style.map(
        "Mode.TRadiobutton",
        foreground=[
            ("disabled", colors["disabled_text"]),
            ("!disabled", colors["text"]),
        ],
    )
    knob = _shape_photo(
        root, "scale-knob", colors["accent"], colors["accent"], circle=True
    )
    knob_disabled = _shape_photo(
        root,
        "scale-disabled",
        colors["disabled_text"],
        colors["disabled_text"],
        circle=True,
    )
    knob_focus = _shape_photo(
        root, "scale-focus", colors["accent"], colors["text"], circle=True
    )
    if "Studio.Scale.slider" not in style.element_names():
        style.element_create(
            "Studio.Scale.slider",
            "image",
            knob,
            ("disabled", knob_disabled),
            ("focus", knob_focus),
            sticky="",
        )
    rail_image = Image.new("RGBA", (36, 24))
    ImageDraw.Draw(rail_image).rounded_rectangle(
        (0, 10, 35, 14), radius=2, fill=colors["field"]
    )
    photos = root._idframe_shape_photos
    if "scale-rail" in photos:
        photos["scale-rail"].paste(rail_image)
    else:
        photos["scale-rail"] = ImageTk.PhotoImage(rail_image, master=root)
    if "Studio.Scale.trough" not in style.element_names():
        style.element_create(
            "Studio.Scale.trough",
            "image",
            photos["scale-rail"],
            border=(12, 0),
            sticky="we",
        )
    style.layout(
        "Horizontal.TScale",
        [
            (
                "Studio.Scale.trough",
                {
                    "sticky": "we",
                    "children": [
                        ("Studio.Scale.slider", {"side": "left", "sticky": ""})
                    ],
                },
            )
        ],
    )
    style.configure(
        "Horizontal.TScale", borderwidth=0, troughborderwidth=0, sliderlength=24
    )
    style.map(
        "Horizontal.TScale",
        background=[("disabled", colors["card"]), ("!disabled", colors["card"])],
    )
