"""Non-destructive alpha-mask edits with bounded, stroke-level undo history."""

import math

from PIL import Image, ImageChops, ImageDraw


class MaskDocument:
    """Keep portrait colors immutable while editing opacity in source coordinates."""

    def __init__(self, cutout, history_limit_bytes=64 * 1024 * 1024):
        """Copy the source and establish a bounded history of changed alpha regions."""
        self._source = cutout.convert("RGBA").copy()
        self._alpha = self._source.getchannel("A")
        self._before = None
        self._undo = []
        self._redo = []
        self.history_limit_bytes = max(0, int(history_limit_bytes))

    @property
    def can_undo(self):
        """Report whether a completed stroke remains in undo history."""
        return bool(self._undo)

    @property
    def can_redo(self):
        """Report whether an undone stroke can be reapplied."""
        return bool(self._redo)

    @property
    def history_bytes(self):
        """Count retained before/after alpha bytes across both history directions."""
        return sum(
            before.width * before.height * 2
            for _, before, _ in self._undo + self._redo
        )

    def image(self):
        """Return an independent full-resolution cutout with the current alpha."""
        result = self._source.copy()
        result.putalpha(self._alpha)
        return result

    def begin_stroke(self):
        """Snapshot only alpha once, allowing many pointer samples to form one step."""
        if self._before is None:
            self._before = self._alpha.copy()

    def erase_segment(self, start, end, diameter):
        """Erase a clipped antialiased capsule between two source-space positions."""
        values = (*start, *end, diameter)
        if not all(math.isfinite(value) for value in values) or diameter <= 0:
            raise ValueError("Brush coordinates must be finite and size positive")
        radius = diameter / 2
        width, height = self._alpha.size
        bounds = (
            max(0, math.floor(min(start[0], end[0]) - radius - 2)),
            max(0, math.floor(min(start[1], end[1]) - radius - 2)),
            min(width, math.ceil(max(start[0], end[0]) + radius + 3)),
            min(height, math.ceil(max(start[1], end[1]) + radius + 3)),
        )
        left, top, right, bottom = bounds
        if right <= left or bottom <= top:
            return
        self.begin_stroke()
        scale = 4
        brush = Image.new("L", ((right - left) * scale, (bottom - top) * scale))
        draw = ImageDraw.Draw(brush)
        points = [((x - left) * scale, (y - top) * scale) for x, y in (start, end)]
        draw.line(points, fill=255, width=max(1, round(diameter * scale)))
        radius *= scale
        for x, y in points:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
        # Area averaging smooths edges without Lanczos ringing inside the brush.
        brush = brush.resize((right - left, bottom - top), Image.Resampling.BOX)
        patch = ImageChops.multiply(
            self._alpha.crop(bounds), ImageChops.invert(brush)
        )
        self._alpha.paste(patch, (left, top))

    def end_stroke(self):
        """Retain only the changed rectangle and evict oldest steps over the budget."""
        if self._before is None:
            return
        bounds = ImageChops.difference(self._before, self._alpha).getbbox()
        if bounds is not None:
            self._undo.append(
                (bounds, self._before.crop(bounds), self._alpha.crop(bounds))
            )
            self._redo.clear()
            while self._undo and self.history_bytes > self.history_limit_bytes:
                self._undo.pop(0)
        self._before = None

    def undo(self):
        """Restore exact pre-stroke alpha without changing portrait RGB pixels."""
        self.end_stroke()
        if self._undo:
            entry = self._undo.pop()
            self._alpha.paste(entry[1], entry[0][:2])
            self._redo.append(entry)

    def redo(self):
        """Reapply exact post-stroke alpha from the most recent undone operation."""
        self.end_stroke()
        if self._redo:
            entry = self._redo.pop()
            self._alpha.paste(entry[2], entry[0][:2])
            self._undo.append(entry)
