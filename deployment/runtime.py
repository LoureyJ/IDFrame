"""Frozen Python runtime; application source files remain independently updatable."""
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    # Source modules are updated independently; avoid stale timestamp-based caches.
    sys.dont_write_bytecode = True
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        import tkinter as tk
        import onnxruntime
        from PIL import Image, ImageDraw
        from portrait import PortraitRemover, save_portrait
        from app import PortraitApp
        image = Image.new("RGB", (240, 320), "#6484a8")
        draw = ImageDraw.Draw(image)
        draw.ellipse((75, 25, 165, 145), fill="#dda888")
        draw.ellipse((35, 155, 205, 410), fill="#27313e")
        output = Path(sys.argv[2])
        save_portrait(PortraitRemover().remove(image), output)
        window = tk.Tk()
        window.withdraw()
        app = PortraitApp(window)
        title = window.title()
        window.update()
        app.close()
        with Image.open(output) as saved:
            report = {"size": saved.size, "mode": saved.mode, "dpi": saved.info["dpi"], "corner": saved.getpixel((0, 0)), "runtime": onnxruntime.__version__, "title": title}
        output.with_suffix(".json").write_text(json.dumps(report))
        return
    runpy.run_path(str(root / "app.py"), run_name="__main__")


if __name__ == "__main__":
    main()
