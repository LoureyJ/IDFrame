"""Shared print presets for preview, naming and 600-DPI export."""

from dataclasses import dataclass

DPI = (600, 600)


@dataclass(frozen=True)
class PhotoSize:
    """Describe one physical print format and its portable filename suffix."""

    label: str
    short_label: str
    mm: tuple[float, float]
    suffix: str

    @property
    def pixels(self):
        """Round physical dimensions to the nearest whole pixel at export resolution."""
        return tuple(round(mm / 25.4 * dpi) for mm, dpi in zip(self.mm, DPI))

    @property
    def description(self):
        """Explain the selected print dimensions and exact encoded pixel dimensions."""
        width, height = self.pixels
        return f"{self.label} · {width} × {height} pixels · 600 DPI · White PNG"


PHOTO_SIZES = {
    "2x2": PhotoSize("2 × 2 inches", "2×2", (50.8, 50.8), "2x2"),
    "1x1": PhotoSize("1 × 1 inch", "1×1", (25.4, 25.4), "1x1"),
    "passport": PhotoSize(
        "Philippine passport · 35 × 45 mm", "Passport", (35.0, 45.0), "Passport_35x45mm"
    ),
}
