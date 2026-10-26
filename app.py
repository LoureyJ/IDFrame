"""Desktop background remover. All photo processing runs on this computer."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageOps, ImageTk
from portrait import (
    MODEL_PATH,
    PortraitRemover,
    AutomaticPortraitRemover,
    format_portrait,
    load_photo,
    save_portrait,
)
from photo_clipboard import load_clipboard_photo
from windows_branding import set_taskbar_identity, sync_installed_shortcuts
from app_version import VERSION
from changelog import show_changelog
from portrait_crop import CropPreview
from ui_theme import apply_theme, load_theme, save_theme
from ui_inspector import InspectorBody
from photo_naming import ask_person_name, portrait_filename, available_photo_path


class PortraitApp:
    """Coordinate the desktop UI while keeping model work outside Tk callbacks."""

    def __init__(self, root, *, preferences_path=None):
        """Initialize photo state, shared model instances, worker, and desktop interface."""
        set_taskbar_identity()
        self.root = root
        self.preferences_path = preferences_path
        self.theme = tk.StringVar(root, value=load_theme(preferences_path))
        self.photo = self.result = self.path = None
        self.person_name = ""
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.remover = PortraitRemover()
        fine_hair = PortraitRemover(mode="fine_hair")
        self.removers = {
            "Auto": AutomaticPortraitRemover(self.remover, fine_hair),
            "Protect person": self.remover,
            "Fine hair": fine_hair,
        }
        self.removal_mode = tk.StringVar(root, value="Auto")
        self.active_mode = None
        self.future = None
        self.busy = False
        self._configure_window()
        self._build_interface()
        self._bind_events()
        apply_theme(root, self.theme.get())
        assets = Path(__file__).resolve().parent / "assets"
        self.branding_future = self.pool.submit(sync_installed_shortcuts, assets)

    def _configure_window(self):
        """Apply the window title, icons, dimensions, and shared widget styles."""
        root = self.root
        root.title(f"IDFrame v{VERSION} — Offline Background Remover")
        assets = Path(__file__).resolve().parent / "assets"
        self.window_icon = tk.PhotoImage(
            master=root, file=str(assets / "portrait-studio.png")
        )
        root.iconphoto(True, self.window_icon)
        if os.name == "nt":
            icon_path = str(assets / "portrait-studio.ico")
            root.iconbitmap(default=icon_path)
            root.iconbitmap(icon_path)
        root.geometry("1240x780")
        root.minsize(980, 680)

    def _build_interface(self):
        """Compose a shared light/dark workspace around two previews and an inspector."""
        page = ttk.Frame(self.root, padding=20, style="App.TFrame")
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        self._build_header(page)
        self._build_toolbar(page)
        self._build_previews(page)
        self._build_export_controls(page)

    def _build_header(self, page):
        """Show application branding, the installed version, and appearance controls."""
        header = ttk.Frame(page, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.brand_icon = self.window_icon.subsample(
            max(1, (self.window_icon.width() + 31) // 32)
        )
        ttk.Label(header, image=self.brand_icon, style="App.TLabel").pack(
            side="left", padx=(0, 10)
        )
        ttk.Label(header, text="IDFrame", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text=f"v{VERSION}", style="App.TLabel").pack(
            side="left", padx=12
        )
        self.changelog_window = None
        self.changelog_button = ttk.Button(
            header, text="Changelog", command=self.open_changelog
        )
        self.changelog_button.pack(side="right")
        appearance = ttk.Frame(header, style="App.TFrame")
        appearance.pack(side="right", padx=(8, 16))
        for name in ("Light", "Dark"):
            ttk.Radiobutton(
                appearance,
                text=name,
                value=name,
                variable=self.theme,
                command=self.change_theme,
                style="Theme.TRadiobutton",
            ).pack(side="left", padx=2)

    def _build_toolbar(self, page):
        """Keep photo input actions easy to reach above the editing workspace."""
        toolbar = ttk.Frame(page, style="App.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        self.open_button = ttk.Button(
            toolbar, text="Open Photo", command=self.open_photo
        )
        self.open_button.pack(side="left")
        self.paste_button = ttk.Button(
            toolbar, text="Paste  ·  Ctrl+V", command=self.paste_photo
        )
        self.paste_button.pack(side="left", padx=10)
        ttk.Label(
            toolbar, text="Your photos stay on this computer", style="App.TLabel"
        ).pack(side="right")

    def _build_previews(self, page):
        """Place source and output cards beside a separate panel of editing controls."""
        workspace = ttk.Frame(page, style="App.TFrame")
        workspace.grid(row=2, column=0, sticky="nsew")
        workspace.columnconfigure(0, weight=1, uniform="photos")
        workspace.columnconfigure(1, weight=1, uniform="photos")
        workspace.columnconfigure(2, minsize=300)
        workspace.rowconfigure(0, weight=1)
        self.original_card = ttk.Frame(workspace, padding=12, style="Card.TFrame")
        self.original_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(self.original_card, text="Original", style="Section.TLabel").pack(
            anchor="w", pady=(0, 12)
        )
        self.before = tk.Label(
            self.original_card,
            text="Open or paste a portrait photo",
            font=("Segoe UI", 10),
        )
        self.before.pack(fill="both", expand=True)
        self.before.bind("<Configure>", self._resize_original)
        self.preview_card = ttk.Frame(workspace, padding=12, style="Card.TFrame")
        self.preview_card.grid(row=0, column=1, sticky="nsew", padx=(0, 12))
        ttk.Label(self.preview_card, text="2 × 2 Preview", style="Section.TLabel").pack(
            anchor="w", pady=(0, 12)
        )
        self.inspector = ttk.Frame(workspace, padding=14, style="Card.TFrame")
        self.inspector.grid(row=0, column=2, sticky="nsew")
        self.inspector.columnconfigure(0, weight=1)
        self.inspector.rowconfigure(0, weight=1)
        self.inspector_body = InspectorBody(self.inspector)
        self.inspector_body.grid(row=0, column=0, sticky="nsew")
        body = self.inspector_body.body
        modes = ttk.Frame(body)
        modes.pack(fill="x")
        ttk.Label(modes, text="Removal mode", style="Section.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        self.mode_buttons = []
        descriptions = {
            "Auto": "Compare both local models",
            "Protect person": "Keep more of the subject",
            "Fine hair": "Detailed curls and wispy hair",
        }
        for name in self.removers:
            button = ttk.Radiobutton(
                modes,
                text=name + "\n" + descriptions[name],
                value=name,
                variable=self.removal_mode,
                command=self.mode_changed,
                style="Mode.TRadiobutton",
            )
            button.pack(fill="x", pady=(0, 4))
            self.mode_buttons.append(button)
        self.remove_button = ttk.Button(
            modes, text="Remove Background", command=self.remove, state="disabled"
        )
        self.remove_button.pack(fill="x", pady=(6, 8))
        ttk.Separator(body).pack(fill="x", pady=(0, 10))
        adjustments = ttk.Frame(body)
        adjustments.pack(fill="x")
        self.crop = CropPreview(self.preview_card, controls_parent=adjustments)
        self.crop.pack(fill="both", expand=True)
        self.save_button = ttk.Button(
            self.inspector,
            text="Save 2×2 Photo",
            style="Accent.TButton",
            command=self.save,
            state="disabled",
        )
        self.save_button.grid(row=1, column=0, sticky="ew", pady=(12, 0))

    def _build_export_controls(self, page):
        """Keep print dimensions, progress, and current status visible below the cards."""
        footer = ttk.Frame(page, style="App.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ttk.Label(
            footer,
            text="2 × 2 inches  ·  1200 × 1200 pixels  ·  600 DPI  ·  White PNG",
            style="App.TLabel",
        ).pack(anchor="w")
        self.progress = ttk.Progressbar(footer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(8, 6))
        self.status = tk.StringVar(
            value=(
                "Ready — offline processing"
                if MODEL_PATH.exists()
                else "Model missing — run setup.bat once before processing."
            )
        )
        if MODEL_PATH.exists() and os.environ.get("PORTRAIT_UPDATE_STATUS"):
            self.status.set(os.environ["PORTRAIT_UPDATE_STATUS"] + " · ready")
        self.status_label = ttk.Label(
            footer, textvariable=self.status, style="App.TLabel", wraplength=920
        )
        self.status_label.pack(anchor="w")

    def change_theme(self, event=None):
        """Recolor the current workspace immediately and remember the user's choice."""
        apply_theme(self.root, self.theme.get())
        save_theme(self.theme.get(), self.preferences_path)
        self.crop.changed()

    def _resize_original(self, event=None):
        """Refit the source photo when its card changes size without changing the source."""
        if self.photo is not None:
            self.show_image(self.before, self.photo)

    def _bind_events(self):
        """Connect window close and clipboard keyboard shortcuts to their handlers."""
        root = self.root
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-v>", self.paste_photo)
        root.bind("<Control-V>", self.paste_photo)

    def open_changelog(self):
        """Open or focus the offline release notes for the installed client version."""
        self.changelog_window = show_changelog(
            self.root, VERSION, self.changelog_window
        )

    def mode_changed(self, event=None):
        """Reprocess the current result when an idle user selects another removal mode."""
        if (
            not self.is_processing()
            and self.photo is not None
            and self.result is not None
        ):
            self.remove()

    def is_processing(self):
        """Report whether a photo task or an unconsumed result still blocks input."""
        return self.busy or (self.future is not None and not self.future.done())

    def show_image(self, label, image):
        """Fit a photo into its preview label and retain the Tk image reference."""
        width = label.winfo_width()
        height = label.winfo_height()
        bounds = (
            (max(1, width - 16), max(1, height - 16))
            if width > 1 and height > 1
            else (330, 330)
        )
        preview = ImageOps.contain(image, bounds)
        display = ImageTk.PhotoImage(preview)
        label.configure(image=display, text="")
        label.image = display

    def open_photo(self):
        """Prompt for a source photo and load it without modifying the original file."""
        if self.is_processing():
            return
        path = filedialog.askopenfilename(
            filetypes=[
                ("Photos", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ]
        )
        if not path:
            return
        try:
            photo = load_photo(path)
        except Exception as error:
            messagebox.showerror("Cannot open photo", str(error))
            return
        self.set_photo(photo, Path(path), f"Opened {Path(path).name}")

    def paste_photo(self, event=None):
        """Load a copied image or photo file while respecting processing and dialog focus."""
        if self.is_processing():
            return "break"
        # Do not intercept Ctrl+V in a file dialog or another child window.
        if event is not None and event.widget.winfo_toplevel() != self.root:
            return
        try:
            photo, path = load_clipboard_photo()
        except Exception as error:
            messagebox.showinfo("Paste photo", str(error))
            return "break"
        description = f"Pasted {path.name}" if path else "Pasted photo from clipboard"
        self.set_photo(photo, path, description)
        return "break"

    def set_photo(self, photo, path, description):
        """Select a new source and clear the previous name, result, and crop framing."""
        self.path, self.photo, self.result = path, photo, None
        self.person_name = ""
        self.show_image(self.before, photo)
        self.crop.set_image(None)
        self.remove_button.configure(state="normal")
        self.save_button.configure(state="disabled")
        self.status.set(description)

    def remove(self):
        """Disable photo actions and submit local background removal to the worker."""
        self.busy = True
        self.active_mode = self.removal_mode.get()
        for button in self.mode_buttons:
            button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.paste_button.configure(state="disabled")
        self.remove_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.crop.set_image(None)
        self.progress.start(12)
        self.status.set(
            "Comparing portrait modes locally…"
            if self.active_mode == "Auto"
            else "Removing background locally… The first photo takes a little longer."
        )
        self.future = self.pool.submit(
            self.process, self.photo.copy(), self.active_mode
        )
        self.root.after(100, self.poll)

    def process(self, photo, mode="Auto"):
        """Run the requested removal mode off the UI thread and return its RGBA cutout."""
        return self.removers[mode].remove(photo)

    def poll(self):
        """Consume a completed worker result and update Tk widgets on the UI thread."""
        if not self.future.done():
            self.root.after(100, self.poll)
            return
        self.progress.stop()
        self.busy = False
        for button in self.mode_buttons:
            button.configure(state="normal")
        self.open_button.configure(state="normal")
        self.paste_button.configure(state="normal")
        self.remove_button.configure(state="normal")
        try:
            cutout = self.future.result()
            self.result = format_portrait(cutout)
        except Exception as error:
            self.status.set("Processing failed. See the message for details.")
            messagebox.showerror("Could not remove background", str(error))
            return
        self.crop.set_image(cutout)
        self.save_button.configure(state="normal")
        prefix = ""
        if self.active_mode == "Auto":
            selected = self.removers["Auto"].last_mode
            prefix = (
                "Auto selected "
                + ("Protect person" if selected == "protected" else "Fine hair")
                + " · "
            )
        self.status.set(
            prefix
            + "Drag and zoom to frame your photo, then save — 2 × 2 inches, 600 DPI."
        )

    def save(self):
        """Ask for a name and save the framed white PNG with exclusive, numbered filenames."""
        person_name = ask_person_name(self.root, self.person_name)
        if person_name is None:
            return
        try:
            filename = portrait_filename(person_name)
        except ValueError as error:
            messagebox.showerror("Invalid name", str(error))
            return
        self.person_name = person_name
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=filename,
            confirmoverwrite=False,
            filetypes=[("PNG image", "*.png")],
        )
        if not path:
            return
        if self.path is not None and Path(path).resolve() == self.path.resolve():
            messagebox.showerror(
                "Choose a different filename",
                "Save the finished portrait to a new file to preserve your original.",
            )
            return
        try:
            result = self.crop.export() if self.crop.cutout is not None else self.result
            while True:
                destination = available_photo_path(path)
                try:
                    save_portrait(result, destination, overwrite=False)
                except FileExistsError:
                    continue
                break
        except Exception as error:
            messagebox.showerror("Could not save", str(error))
            return
        self.status.set(
            f"Saved {destination.name} — 2 × 2 inches, 1200 × 1200 pixels, 600 DPI, white background."
        )

    def close(self):
        """Wait for active processing, schedule a verified launcher refresh, and close the UI."""
        if self.future is not None and not self.future.done():
            self.status.set(
                "Please wait for the current photo to finish before closing."
            )
            return
        try:
            from launcher_refresh import request_launcher_refresh

            request_launcher_refresh()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Could not schedule launcher refresh")
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    PortraitApp(root)
    root.mainloop()
