"""Frozen Python runtime; application source files remain independently updatable."""

import json
from pathlib import Path
import runpy
import sys


def main():
    # Source modules are updated independently; avoid stale timestamp-based caches.
    """Launch independently updated source modules or run the frozen-runtime smoke check."""
    sys.dont_write_bytecode = True
    root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )
    sys.path.insert(0, str(root))
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QPointF
        import onnxruntime
        from PIL import Image, ImageDraw
        from portrait import PortraitRemover, save_portrait
        from app import PortraitApp
        from qt_editor import CleanupEditor

        image = Image.new("RGB", (240, 320), "#6484a8")
        draw = ImageDraw.Draw(image)
        draw.ellipse((75, 25, 165, 145), fill="#dda888")
        draw.ellipse((35, 155, 205, 410), fill="#27313e")
        output = Path(sys.argv[2])
        save_portrait(PortraitRemover().remove(image), output)
        application = QApplication.instance() or QApplication([])
        window = PortraitApp(sync_shortcuts=False)
        editor = CleanupEditor(Image.new("RGBA", (100, 100), "red"), window)
        editor.view.erase_at(QPointF(50, 50), QPointF(50, 50), source_coordinates=True)
        editor.view.finish_stroke()
        assert editor.edited_image().getpixel((50, 50))[3] == 0
        editor.view.undo()
        assert editor.edited_image().getpixel((50, 50))[3] == 255
        editor.reject()
        title = window.windowTitle()
        application.processEvents()
        window.close()
        with Image.open(output) as saved:
            report = {
                "size": saved.size,
                "mode": saved.mode,
                "dpi": saved.info["dpi"],
                "corner": saved.getpixel((0, 0)),
                "runtime": onnxruntime.__version__,
                "title": title,
                "ui": "PySide6",
                "editor": "passed",
            }
        output.with_suffix(".json").write_text(json.dumps(report))
        return
    runpy.run_path(str(root / "app.py"), run_name="__main__")


if __name__ == "__main__":
    main()
