"""Desktop background remover. All photo processing runs on this computer."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageOps, ImageTk
from portrait import MODEL_PATH, PortraitRemover, AutomaticPortraitRemover, format_portrait, load_photo, save_portrait
from photo_clipboard import load_clipboard_photo
from windows_branding import set_taskbar_identity, sync_installed_shortcuts
from app_version import VERSION
from changelog import show_changelog
from portrait_crop import CropPreview
from photo_naming import ask_person_name, portrait_filename, available_photo_path


class PortraitApp:
    def __init__(self, root):
        set_taskbar_identity()
        self.root = root
        self.photo = self.result = self.path = None
        self.person_name = ""
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.remover = PortraitRemover()
        fine_hair = PortraitRemover(mode="fine_hair")
        self.removers = {"Auto": AutomaticPortraitRemover(self.remover, fine_hair),
                         "Protect person": self.remover, "Fine hair": fine_hair}
        self.removal_mode = tk.StringVar(root, value="Auto")
        self.active_mode = None
        self.future = None
        self.busy = False
        root.title(f"IDFrame v{VERSION} — Offline Background Remover")
        assets = Path(__file__).resolve().parent / "assets"
        self.window_icon = tk.PhotoImage(master=root, file=str(assets / "portrait-studio.png"))
        root.iconphoto(True, self.window_icon)
        if os.name == "nt":
            icon_path = str(assets / "portrait-studio.ico")
            root.iconbitmap(default=icon_path)
            root.iconbitmap(icon_path)
        root.geometry("960x700")
        root.minsize(900, 620)
        root.configure(bg="#f3f5f8")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f8")
        style.configure("TLabel", background="#f3f5f8", foreground="#17243b", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"))
        style.configure("TButton", padding=(16, 11), font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#235ce0", foreground="white")
        page = ttk.Frame(root, padding=30)
        page.pack(fill="both", expand=True)
        header = ttk.Frame(page)
        header.pack(fill="x")
        ttk.Label(header, text=f"IDFrame  v{VERSION}", style="Title.TLabel").pack(side="left")
        self.changelog_window = None
        self.changelog_button = ttk.Button(header, text="Changelog", command=self.open_changelog)
        self.changelog_button.pack(side="right")
        description = "Remove portrait backgrounds. Keep every photo on your computer."
        ttk.Label(page, text=description).pack(anchor="w", pady=(5, 20))
        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x")
        self.open_button = ttk.Button(toolbar, text="1  Open photo", command=self.open_photo)
        self.open_button.pack(side="left")
        self.paste_button = ttk.Button(toolbar, text="Paste photo (Ctrl+V)", command=self.paste_photo)
        self.paste_button.pack(side="left", padx=(10, 0))
        self.remove_button = ttk.Button(toolbar, text="2  Remove background", style="Accent.TButton", command=self.remove, state="disabled")
        self.remove_button.pack(side="left", padx=10)
        self.save_button = ttk.Button(toolbar, text="3  Save PNG", command=self.save, state="disabled")
        self.save_button.pack(side="left")
        mode_bar = ttk.Frame(page)
        mode_bar.pack(fill="x", pady=(10, 0))
        ttk.Label(mode_bar, text="Removal mode").pack(side="left", padx=(0, 8))
        self.mode_selector = ttk.Combobox(mode_bar, textvariable=self.removal_mode,
                                          values=tuple(self.removers), state="readonly", width=17)
        self.mode_selector.pack(side="left")
        self.mode_selector.bind("<<ComboboxSelected>>", self.mode_changed)
        ttk.Label(mode_bar, text="Auto checks both results. Manual modes remain available.",
                  font=("Segoe UI", 9)).pack(side="left", padx=12)
        previews = ttk.Frame(page)
        previews.pack(fill="both", expand=True, pady=24)
        previews.columnconfigure((0, 1), weight=1, uniform="preview")
        previews.rowconfigure(1, weight=1)
        ttk.Label(previews, text="ORIGINAL").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(previews, text="2 × 2 CROP · WHITE BACKGROUND").grid(row=0, column=1, sticky="w", padx=(16, 0), pady=(0, 8))
        self.before = tk.Label(previews, text="Open or paste a portrait photo", bg="white", fg="#77849a", font=("Segoe UI", 11))
        self.crop = CropPreview(previews)
        self.before.grid(row=1, column=0, sticky="nsew")
        self.crop.grid(row=1, column=1, sticky="nsew", padx=(16, 0))
        ttk.Label(page, text="EXPORT   2 × 2 inches · 1200 × 1200 pixels · 600 DPI · White PNG").pack(anchor="w")
        ttk.Label(page, text="Zoom and drag the finished photo to frame your portrait. Original files are preserved.").pack(anchor="w", pady=(5, 14))
        self.progress = ttk.Progressbar(page, mode="indeterminate")
        self.progress.pack(fill="x")
        self.status = tk.StringVar(value="Ready — offline processing" if MODEL_PATH.exists() else "Model missing — run setup.bat once before processing.")
        if MODEL_PATH.exists() and os.environ.get("PORTRAIT_UPDATE_STATUS"):
            self.status.set(os.environ["PORTRAIT_UPDATE_STATUS"] + " · ready")
        ttk.Label(page, textvariable=self.status, wraplength=820).pack(anchor="w", pady=(10, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-v>", self.paste_photo)
        root.bind("<Control-V>", self.paste_photo)
        self.branding_future = self.pool.submit(sync_installed_shortcuts, assets)

    def open_changelog(self):
        self.changelog_window = show_changelog(self.root, VERSION, self.changelog_window)

    def mode_changed(self, event=None):
        if not self.is_processing() and self.photo is not None and self.result is not None:
            self.remove()

    def is_processing(self):
        return self.busy or (self.future is not None and not self.future.done())

    def show_image(self, label, image):
        preview = ImageOps.contain(image, (330, 330))
        display = ImageTk.PhotoImage(preview)
        label.configure(image=display, text="")
        label.image = display

    def open_photo(self):
        if self.is_processing():
            return
        path = filedialog.askopenfilename(filetypes=[("Photos", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"), ("All files", "*.*")])
        if not path:
            return
        try:
            photo = load_photo(path)
        except Exception as error:
            messagebox.showerror("Cannot open photo", str(error))
            return
        self.set_photo(photo, Path(path), f"Opened {Path(path).name}")

    def paste_photo(self, event=None):
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
        self.path, self.photo, self.result = path, photo, None
        self.person_name = ""
        self.show_image(self.before, photo)
        self.crop.set_image(None)
        self.remove_button.configure(state="normal")
        self.save_button.configure(state="disabled")
        self.status.set(description)

    def remove(self):
        self.busy = True
        self.active_mode = self.removal_mode.get()
        self.mode_selector.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.paste_button.configure(state="disabled")
        self.remove_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.crop.set_image(None)
        self.progress.start(12)
        self.status.set("Comparing portrait modes locally…" if self.active_mode == "Auto" else
                        "Removing background locally… The first photo takes a little longer.")
        self.future = self.pool.submit(self.process, self.photo.copy(), self.active_mode)
        self.root.after(100, self.poll)

    def process(self, photo, mode="Auto"):
        return self.removers[mode].remove(photo)

    def poll(self):
        if not self.future.done():
            self.root.after(100, self.poll)
            return
        self.progress.stop()
        self.busy = False
        self.mode_selector.configure(state="readonly")
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
            prefix = "Auto selected " + ("Protect person" if selected == "protected" else "Fine hair") + " · "
        self.status.set(prefix + "Drag and zoom to frame your photo, then save — 2 × 2 inches, 600 DPI.")

    def save(self):
        person_name = ask_person_name(self.root, self.person_name)
        if person_name is None:
            return
        try:
            filename = portrait_filename(person_name)
        except ValueError as error:
            messagebox.showerror("Invalid name", str(error))
            return
        self.person_name = person_name
        path = filedialog.asksaveasfilename(defaultextension=".png", initialfile=filename,
                                           confirmoverwrite=False, filetypes=[("PNG image", "*.png")])
        if not path:
            return
        if self.path is not None and Path(path).resolve() == self.path.resolve():
            messagebox.showerror("Choose a different filename", "Save the finished portrait to a new file to preserve your original.")
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
        self.status.set(f"Saved {destination.name} — 2 × 2 inches, 1200 × 1200 pixels, 600 DPI, white background.")

    def close(self):
        if self.future is not None and not self.future.done():
            self.status.set("Please wait for the current photo to finish before closing.")
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
