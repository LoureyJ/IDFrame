"""Generate the native Windows icon from IDFrame's PNG brand artwork."""

from pathlib import Path

from PIL import Image

ICON_SIZES = ((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256))


def generate_windows_icon(png_path: Path, ico_path: Path):
    """Write a transparent multi-resolution ICO derived from the canonical PNG."""
    png_path, ico_path = Path(png_path), Path(ico_path)
    if not png_path.is_file():
        raise FileNotFoundError(f"IDFrame PNG logo is missing: {png_path}")
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ico_path.with_name(ico_path.stem + ".tmp.ico")
    try:
        with Image.open(png_path) as source:
            image = source.convert("RGBA")
            if image.width != image.height:
                raise ValueError("IDFrame's Windows icon source must be a square PNG.")
            image.save(temporary, format="ICO", sizes=list(ICON_SIZES))
        temporary.replace(ico_path)
    finally:
        temporary.unlink(missing_ok=True)
