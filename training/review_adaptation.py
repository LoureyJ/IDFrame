"""Compare an exported adaptation against its starting model using client inference.

Runs in the application .venv. Coverage is a diagnostic, not foreground accuracy.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portrait import PortraitRemover, load_photo, save_portrait


def white_preview(image, size):
    """Composite a cutout onto white and resize it for the comparison contact sheet."""
    rgba = image.convert("RGBA")
    canvas = Image.new("RGBA", rgba.size, "white")
    canvas.alpha_composite(rgba)
    return ImageOps.contain(canvas.convert("RGB"), size, Image.Resampling.LANCZOS)


def main():
    """Compare baseline and adapted client inference against saved PyTorch previews and export metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--epoch", default="epoch-10")
    parser.add_argument("--model", default="adapted.onnx")
    args = parser.parse_args()
    report = json.loads((args.run / "training-report.json").read_text())
    photos = [ROOT / "training photos" / entry["file"] for entry in report["photos"]]
    old = PortraitRemover(args.run / "baseline.onnx", model_type="matting")
    new = PortraitRemover(args.run / args.model, model_type="matting")
    destination = args.run.parent / "client-review"
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    groups = {}
    for photo in photos:
        relative = photo.relative_to(ROOT / "training photos")
        group = relative.parts[0] if len(relative.parts) > 1 else "curls"
        source = load_photo(photo)
        start = time.perf_counter()
        before, after = old.remove(source), new.remove(source)
        output = destination / relative.parent / (relative.name + ".png")
        output.parent.mkdir(parents=True, exist_ok=True)
        after.save(output)
        with Image.open(
            args.run / args.epoch / relative.parent / (relative.name + ".png")
        ) as torch_output:
            difference = (
                np.abs(
                    np.asarray(after.getchannel("A"), dtype=float)
                    - np.asarray(torch_output.getchannel("A"), dtype=float)
                )
                / 255
            )
        assert float(difference.mean()) < 1.1 / 255, (
            relative,
            float(difference.mean()),
        )
        exported = output.with_name(output.stem + "-2x2.png")
        save_portrait(after, exported)
        with Image.open(exported) as image:
            assert image.size == (1200, 1200) and image.mode == "RGB"
            assert all(abs(dpi - 600) < 0.1 for dpi in image.info["dpi"])
        record = {
            "photo": relative.as_posix(),
            "seconds_two_models": round(time.perf_counter() - start, 3),
            "onnx_vs_torch_alpha_mae": float(difference.mean()),
            "before_mean_alpha": float(np.asarray(before.getchannel("A")).mean() / 255),
            "after_mean_alpha": float(np.asarray(after.getchannel("A")).mean() / 255),
        }
        records.append(record)
        groups.setdefault(group, []).append((relative, source, before, after))
        print(json.dumps(record), flush=True)
    for group, rows in groups.items():
        sheet = Image.new("RGB", (1200, len(rows) * 290 + 36), "#dddddd")
        draw = ImageDraw.Draw(sheet)
        for col, label in enumerate(
            ["Original", "Before this training", "After this training"]
        ):
            draw.text((col * 400 + 12, 10), label, fill="black")
        for row, (relative, *images) in enumerate(rows):
            for col, image in enumerate(images):
                preview = white_preview(image, (390, 256))
                sheet.paste(
                    preview, (col * 400 + (400 - preview.width) // 2, row * 290 + 36)
                )
            draw.text((12, row * 290 + 295), str(relative)[:120], fill="black")
        sheet.save(destination / (group + "-comparison.jpg"))
    (destination / "validation.json").write_text(
        json.dumps(
            {
                "model_sha256": hashlib.sha256(
                    (args.run / args.model).read_bytes()
                ).hexdigest(),
                "note": "Training examples only; alpha coverage is not segmentation accuracy.",
                "results": records,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
