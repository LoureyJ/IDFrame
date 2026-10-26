"""Interactive 2x2 framing; inference is never repeated when zooming or dragging."""

import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from portrait import MAX_BRIGHTNESS, MIN_BRIGHTNESS, frame_portrait
from ui_theme import palette_for


class CropPreview(ttk.Frame):
    """Keep zoom and position in frame-relative coordinates for preview and export."""

    def __init__(self, parent, controls_parent=None):
        """Create the crop canvas, zoom controls, and pointer event bindings."""
        super().__init__(parent)
        self.cutout = None
        self.offset = (0.0, 0.0)
        self.drag = None
        self.pending = None
        self.frame_side = 1
        self.zoom = tk.DoubleVar(self, value=1.0)
        self.zoom_text = tk.StringVar(self, value="100%")
        self.brightness = tk.DoubleVar(self, value=1.0)
        self.brightness_text = tk.StringVar(self, value="100%")
        self.canvas = tk.Canvas(
            self,
            background="#e3e7ee",
            highlightthickness=0,
            width=300,
            height=200,
            cursor="fleur",
        )
        self.canvas.pack(fill="both", expand=True)
        controls_host = controls_parent if controls_parent is not None else self
        ttk.Label(controls_host, text="Framing", style="Section.TLabel").pack(
            anchor="w"
        )
        controls = ttk.Frame(controls_host)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Label(controls, text="Zoom").pack(side="left")
        self.slider = ttk.Scale(
            controls,
            from_=1,
            to=8,
            variable=self.zoom,
            command=self.changed,
            state="disabled",
        )
        self.slider.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(controls, textvariable=self.zoom_text, width=5).pack(side="left")
        ttk.Label(controls_host, text="Lighting", style="Section.TLabel").pack(
            anchor="w", pady=(10, 0)
        )
        brightness_controls = ttk.Frame(controls_host)
        brightness_controls.pack(fill="x", pady=(8, 0))
        ttk.Label(brightness_controls, text="Brightness").pack(side="left")
        self.brightness_slider = ttk.Scale(
            brightness_controls,
            from_=MIN_BRIGHTNESS,
            to=MAX_BRIGHTNESS,
            variable=self.brightness,
            command=self.changed,
            state="disabled",
        )
        self.brightness_slider.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(brightness_controls, textvariable=self.brightness_text, width=5).pack(
            side="right"
        )
        self.reset_button = ttk.Button(
            controls_host,
            text="Reset Adjustments",
            command=self.reset,
            state="disabled",
        )
        self.reset_button.pack(fill="x", pady=(8, 0))
        ttk.Label(
            controls_host,
            text="Drag the preview to position.\nBrightness: 100% is neutral.",
            font=("Segoe UI", 9),
            wraplength=225 if controls_parent is not None else 400,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        self.canvas.bind("<Configure>", self.changed)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.move_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda event: setattr(self, "drag", None))
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.changed()

    def set_image(self, cutout):
        """Replace the full-resolution cutout and reset framing and control availability."""
        self.cutout = cutout
        self.reset()
        state = "normal" if cutout is not None else "disabled"
        self.slider.configure(state=state)
        self.brightness_slider.configure(state=state)
        self.reset_button.configure(state=state)

    def reset(self):
        """Restore neutral brightness, initial zoom, centered position, and idle drag state."""
        self.zoom.set(1.0)
        self.brightness.set(1.0)
        self.offset = (0.0, 0.0)
        self.drag = None
        self.changed()

    def changed(self, *args):
        """Clamp panning, refresh the zoom label, and coalesce redraw requests."""
        self.zoom_text.set(f"{self.zoom.get():.0%}")
        self.brightness_text.set(f"{self.brightness.get():.0%}")
        if self.cutout is not None:
            maximum = max(self.cutout.size)
            limits = tuple(
                (1 + self.zoom.get() * dimension / maximum) / 2 - 0.02
                for dimension in self.cutout.size
            )
            self.offset = tuple(
                max(-limit, min(limit, value))
                for value, limit in zip(self.offset, limits)
            )
        if self.pending is None:
            self.pending = self.after(16, self.draw)

    def draw(self):
        """Render the square preview at canvas size using the export framing geometry."""
        self.pending = None
        colors = palette_for(self)
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        side = max(1, min(width, height) - 12)
        self.frame_side = side
        self.canvas.delete("all")
        if self.cutout is None:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="Your 2 × 2 portrait will appear here",
                fill=colors["muted"],
                width=max(1, width - 20),
                font=("Segoe UI", 10),
            )
            return
        self.display = ImageTk.PhotoImage(
            frame_portrait(
                self.cutout,
                self.zoom.get(),
                self.offset,
                (side, side),
                brightness=self.brightness.get(),
            ),
            master=self,
        )
        self.canvas.create_image(width / 2, height / 2, image=self.display)
        self.canvas.create_rectangle(
            (width - side) / 2,
            (height - side) / 2,
            (width + side) / 2,
            (height + side) / 2,
            outline=colors["border"],
        )

    def start_drag(self, event):
        """Remember the pointer position and starting crop offset for a drag."""
        if self.cutout is not None:
            self.drag = (event.x, event.y, self.offset)

    def move_drag(self, event):
        """Translate pointer movement into frame-relative crop offsets."""
        if self.drag is None:
            return
        x, y, origin = self.drag
        # Keep at least part of the source canvas within the crop frame.
        self.offset = tuple(
            start + delta / self.frame_side
            for start, delta in zip(origin, (event.x - x, event.y - y))
        )
        self.changed()

    def wheel(self, event):
        """Adjust zoom within its supported range and consume the mouse-wheel event."""
        if self.cutout is not None and event.delta:
            self.zoom.set(
                max(
                    1.0,
                    min(8.0, self.zoom.get() * (1.1 if event.delta > 0 else 1 / 1.1)),
                )
            )
            self.changed()
        return "break"

    def export(self):
        """Render the selected framing from source pixels at the fixed print dimensions."""
        return frame_portrait(
            self.cutout, self.zoom.get(), self.offset, brightness=self.brightness.get()
        )

    def destroy(self):
        """Cancel any scheduled redraw before destroying the crop widgets."""
        if self.pending is not None:
            self.after_cancel(self.pending)
        super().destroy()
