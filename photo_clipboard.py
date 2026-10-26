"""Read copied Windows images or image files using the existing Pillow runtime."""
import io
import struct
import sys
from pathlib import Path

from PIL import Image, ImageOps

from portrait import load_photo


def _read_windows_clipboard():
    if sys.platform != "win32":
        raise OSError("Pasting photos is currently supported on Windows.")
    # This reader is already present in version 1's bundled Pillow native library.
    # No additional package or rebuilt runtime is required.
    return Image.core.grabclipboard_win32()


def load_clipboard_photo():
    """Return (RGB photo, original file path or None); never change the clipboard."""
    fmt, data = _read_windows_clipboard()
    if fmt == "file" and isinstance(data, bytes):
        # Windows CF_HDROP header: filename-list offset and Unicode flag.
        if len(data) < 20:
            raise ValueError("The copied file list is invalid. Copy the photo again.")
        offset, = struct.unpack_from("<I", data)
        unicode_names, = struct.unpack_from("<I", data, 16)
        if not 20 <= offset < len(data):
            raise ValueError("The copied file list is invalid. Copy the photo again.")
        names = data[offset:].decode("utf-16le" if unicode_names else "mbcs").split("\0")
        for name in names:
            if not name:
                break
            try:
                path = Path(name)
                return load_photo(path), path
            except (OSError, ValueError):
                continue
        raise ValueError("No supported photo found in the copied files. Copy a JPG, PNG, WebP, BMP, or TIFF photo.")
    if fmt in ("png", "DIB") and isinstance(data, bytes):
        with Image.open(io.BytesIO(data)) as source:
            rgba = ImageOps.exif_transpose(source).convert("RGBA")
            white = Image.new("RGBA", rgba.size, "white")
            return Image.alpha_composite(white, rgba).convert("RGB"), None
    raise ValueError("No photo found on the clipboard. Copy an image or a photo file, then paste it here.")
