"""A compact scrollable settings area that keeps the save action outside the scroll."""

import tkinter as tk
from tkinter import ttk


class InspectorBody(ttk.Frame):
    """Scroll editing controls only when a smaller window cannot display them all."""

    def __init__(self, parent):
        """Create a themed canvas-backed control column and an overflow-only scrollbar."""
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, width=260, height=100, highlightthickness=0)
        self.canvas.theme_surface = "card"
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.body = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._sync_scroll)
        self.canvas.bind("<Configure>", self._resize_body)
        self._wheel_binding = self.winfo_toplevel().bind(
            "<MouseWheel>", self._wheel, add="+"
        )
        self._focus_binding = self.winfo_toplevel().bind(
            "<FocusIn>", self._reveal_focus, add="+"
        )

    def _resize_body(self, event):
        """Fit the inspector contents to the current visible width before checking overflow."""
        self.canvas.itemconfigure(self.window_id, width=event.width)
        self._sync_scroll()

    def _sync_scroll(self, event=None):
        """Show a scrollbar only when the editing controls exceed the visible height."""
        bounds = self.canvas.bbox("all")
        self.canvas.configure(scrollregion=bounds)
        if bounds and bounds[3] > self.canvas.winfo_height():
            self.scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.scrollbar.grid_remove()
            self.canvas.yview_moveto(0)

    def _wheel(self, event):
        """Scroll only while the pointer is inside this inspector's control subtree."""
        if str(event.widget).startswith(str(self)) and self.canvas.yview() != (
            0.0,
            1.0,
        ):
            self.canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"

    def _reveal_focus(self, event):
        """Keep a tab-focused editing control visible inside an overflowing inspector."""
        if not str(event.widget).startswith(str(self.body)):
            return
        offset = self.canvas.canvasy(0)
        top = event.widget.winfo_rooty() - self.canvas.winfo_rooty() + offset
        bottom = top + event.widget.winfo_height()
        height = self.canvas.winfo_height()
        total = max(1, self.body.winfo_height())
        if top < offset:
            self.canvas.yview_moveto(max(0, top - 8) / total)
        elif bottom > offset + height:
            self.canvas.yview_moveto(max(0, bottom + 8 - height) / total)

    def destroy(self):
        """Remove this inspector's wheel callback before destroying its widgets."""
        self.winfo_toplevel().unbind("<MouseWheel>", self._wheel_binding)
        self.winfo_toplevel().unbind("<FocusIn>", self._focus_binding)
        super().destroy()
