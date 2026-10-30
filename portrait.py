"""Local portrait segmentation and fixed-format, white-background export."""

from pathlib import Path
import math
import os
import tempfile

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from photo_sizes import PHOTO_SIZES, DPI

ROOT = Path(__file__).resolve().parent
LEGACY_MODEL_PATH = ROOT / "models" / "u2net_human_seg.onnx"
HAIR_MODEL_PATH = ROOT / "models" / "portrait_hair.onnx"
MODEL_PATH = LEGACY_MODEL_PATH if LEGACY_MODEL_PATH.is_file() else HAIR_MODEL_PATH
OUTPUT_MM = PHOTO_SIZES["2x2"].mm
OUTPUT_DPI = DPI
OUTPUT_SIZE = PHOTO_SIZES["2x2"].pixels

# Keep model-specific dimensions and normalization next to the export contract.
SEGMENTATION_SIZE = (320, 320)
MATTING_MAX_SIDE = 768
MODEL_ALIGNMENT = 32
MIN_MODEL_SIDE = 64
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
MIN_BRIGHTNESS = 0.25
MAX_BRIGHTNESS = 2.0


def load_photo(path):
    """Apply EXIF orientation and composite source transparency onto white RGB pixels."""
    with Image.open(path) as source:
        photo = ImageOps.exif_transpose(source).convert("RGBA")
        # Composite transparent source files before inference.
        white = Image.new("RGBA", photo.size, "white")
        return Image.alpha_composite(white, photo).convert("RGB")


class PortraitRemover:
    """Load one local model lazily and apply its alpha mask to the original RGB pixels."""

    def __init__(self, model_path=None, *, model_type=None, mode="protected"):
        """Select an available local model and defer loading its inference session."""
        if mode not in {"protected", "fine_hair"}:
            raise ValueError("Unsupported portrait removal mode")
        self.mode = mode
        if model_path is None:
            preferred, fallback = (
                (HAIR_MODEL_PATH, LEGACY_MODEL_PATH)
                if mode == "fine_hair"
                else (LEGACY_MODEL_PATH, HAIR_MODEL_PATH)
            )
            model_path = preferred if preferred.is_file() else fallback
        self.model_path = Path(model_path)
        self.model_type = model_type or (
            "matting"
            if self.model_path.name == HAIR_MODEL_PATH.name
            else "segmentation"
        )
        if self.model_type not in {"matting", "segmentation"}:
            raise ValueError("Unsupported portrait model type")
        self._session = None

    def remove(self, photo):
        """Return a full-resolution RGBA cutout using the selected local model."""
        session = self._get_session()
        rgb = photo.convert("RGB")
        tensor = self._prepare_tensor(rgb)
        prediction = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        alpha = self._prediction_to_alpha(prediction, rgb.size)
        result = rgb.convert("RGBA")
        result.putalpha(alpha)
        return result

    def _get_session(self):
        """Create the CPU inference session once and reuse it for subsequent photos."""
        if self._session is None:
            if not self.model_path.is_file():
                raise FileNotFoundError(
                    "Portrait model is missing. Run setup.bat once while connected "
                    "to the internet, then use the app offline."
                )
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = min(4, os.cpu_count() or 1)
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        return self._session

    def _prepare_tensor(self, rgb):
        """Resize and normalize RGB pixels for this model's expected NCHW input."""
        if self.model_type == "matting":
            # Preserve aspect ratio and much more hair detail than the old 320px square.
            scale = MATTING_MAX_SIDE / max(rgb.size)
            size = tuple(
                max(
                    MIN_MODEL_SIDE,
                    round(side * scale / MODEL_ALIGNMENT) * MODEL_ALIGNMENT,
                )
                for side in rgb.size
            )
            pixels = (
                np.asarray(rgb.resize(size, Image.Resampling.LANCZOS), dtype=np.float32)
                / 127.5
                - 1
            )
        else:
            pixels = np.asarray(
                rgb.resize(SEGMENTATION_SIZE, Image.Resampling.LANCZOS),
                dtype=np.float32,
            )
            pixels /= max(float(pixels.max()), 1e-6)
            pixels = (pixels - IMAGENET_MEAN) / IMAGENET_STD
        return pixels.transpose(2, 0, 1)[None].astype(np.float32)

    def _prediction_to_alpha(self, prediction, source_size):
        """Validate model output and resize continuous opacity to the source dimensions."""
        if np.ndim(prediction) != 4 or prediction.shape[0:2] != (1, 1):
            raise ValueError("The model returned an invalid alpha shape")
        mask = np.asarray(prediction[0, 0], dtype=np.float32)
        if not np.isfinite(mask).all():
            raise ValueError("The model returned an invalid mask. Try another photo.")
        low, high = float(mask.min()), float(mask.max())
        if high - low < 1e-6:
            raise ValueError("No clear person detected. Try a well-lit portrait photo.")
        if self.model_type == "segmentation":
            mask = (mask - low) / (high - low)
        # A matting model predicts real opacity. Stretching its range or binarizing
        # would destroy the partial transparency between curls and fine strands.
        mask = np.clip(mask, 0, 1)
        return Image.fromarray((mask * 255).astype(np.uint8)).resize(
            source_size, Image.Resampling.LANCZOS
        )


def choose_removal_mode(protected, fine_hair):
    """Conservative mask-integrity heuristic, not a learned quality score.

    Prefer hair detail unless a credible person silhouette exposes missing solid
    interior regions or strong background spill. Return a whole candidate, never
    blend masks: blending produced patches on the client originals.
    """
    if protected.size != fine_hair.size:
        raise ValueError("Removal candidates have different dimensions")
    scale = 256 / max(protected.size)
    size = tuple(max(1, round(value * scale)) for value in protected.size)
    silhouette = protected.getchannel("A").resize(size, Image.Resampling.BICUBIC)
    detail = (
        np.asarray(
            fine_hair.getchannel("A").resize(size, Image.Resampling.BICUBIC),
            dtype=np.float32,
        )
        / 255
    )
    person = np.asarray(silhouette, dtype=np.float32) / 255
    radius = max(1, round(min(size) * 0.075))
    core = np.asarray(silhouette.filter(ImageFilter.MinFilter(2 * radius + 1))) > 245
    radius = max(1, round(min(size) * 0.02))
    support = np.asarray(silhouette.filter(ImageFilter.MaxFilter(2 * radius + 1))) > 13
    metrics = {
        "core_fraction": float(core.mean()),
        "missing_core": float((detail[core] < 0.5).mean()) if core.any() else 0.0,
        "core_deficit": (
            float(np.maximum(0, person[core] - detail[core] - 0.15).mean())
            if core.any()
            else 0.0
        ),
        "background_spill": float(
            ((detail > 0.8) & ~support).sum() / max(1, (person > 0.5).sum())
        ),
    }
    # Tiny coarse detections are common in camouflaged/historical portraits.
    # They are insufficient evidence to reject a larger, valid hair-model result.
    reliable = metrics["core_fraction"] >= 0.08
    damaged = metrics["missing_core"] > 0.015 or metrics["core_deficit"] > 0.015
    spill = metrics["background_spill"] > 0.02
    mode = "protected" if reliable and (damaged or spill) else "fine_hair"
    return mode, metrics


class AutomaticPortraitRemover:
    """Choose one complete local-model result using mask integrity diagnostics."""

    def __init__(self, protected=None, fine_hair=None):
        # The GUI shares these instances with manual modes, reusing loaded sessions.
        """Share manual-mode models and initialize automatic-selection diagnostics."""
        self.protected = (
            protected if protected is not None else PortraitRemover(mode="protected")
        )
        self.fine_hair = (
            fine_hair if fine_hair is not None else PortraitRemover(mode="fine_hair")
        )
        self.last_mode = None
        self.last_diagnostics = {}

    def remove(self, photo):
        """Compare whole model candidates, falling back to the usable result on failure."""
        self.last_mode = None
        self.last_diagnostics = {}
        if self.protected.model_path.resolve() == self.fine_hair.model_path.resolve():
            result = self.protected.remove(photo)
            self.last_mode = (
                "fine_hair" if self.protected.model_type == "matting" else "protected"
            )
            self.last_diagnostics = {"reason": "one_available_model"}
            return result
        protected = fine_hair = None
        errors = []
        for model, name in [
            (self.protected, "protected"),
            (self.fine_hair, "fine_hair"),
        ]:
            try:
                candidate = model.remove(photo)
            except (FileNotFoundError, ValueError, RuntimeError) as error:
                errors.append(error)
                continue
            if name == "protected":
                protected = candidate
            else:
                fine_hair = candidate
        if protected is None and fine_hair is None:
            raise errors[0]
        if protected is None or fine_hair is None:
            self.last_mode = "fine_hair" if protected is None else "protected"
            self.last_diagnostics = {"reason": "other_model_inconclusive"}
        else:
            self.last_mode, self.last_diagnostics = choose_removal_mode(
                protected, fine_hair
            )
        return protected if self.last_mode == "protected" else fine_hair


def format_portrait(cutout, size=OUTPUT_SIZE):
    """Fit the original framing into a selected white print size without stretching."""
    rgba = cutout.convert("RGBA")
    if rgba.getchannel("A").getbbox() is None:
        raise ValueError("No person detected. Try another portrait photo.")
    scaled = ImageOps.contain(rgba, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, "white")
    canvas.alpha_composite(
        scaled,
        ((size[0] - scaled.width) // 2, (size[1] - scaled.height) // 2),
    )
    return canvas.convert("RGB")


def frame_portrait(
    cutout,
    zoom=1.0,
    offset=(0.0, 0.0),
    size=OUTPUT_SIZE,
    *,
    brightness=1.0,
    rotation=0.0,
):
    """Render a movable square crop from source pixels, without allocating a huge zoomed image.

    Offset is measured as a fraction of the output frame, positive right/down.
    The same geometry is used for the interactive preview and full-resolution save.
    Brightness changes portrait RGB only; opacity and the white background are preserved.
    Rotation is clockwise in degrees, applied once with crop scaling at export.
    """
    if not (
        math.isfinite(zoom)
        and 1 <= zoom <= 8
        and all(math.isfinite(value) for value in offset)
    ):
        raise ValueError("Invalid crop framing")
    if (
        not math.isfinite(brightness)
        or not MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS
    ):
        raise ValueError("Invalid portrait brightness")
    if not math.isfinite(rotation) or not -180 <= rotation <= 180:
        raise ValueError("Invalid portrait rotation")
    rgba = cutout.convert("RGBA")
    if rgba.getchannel("A").getbbox() is None:
        raise ValueError("No person detected. Try another portrait photo.")
    scale = min(size[0] / rgba.width, size[1] / rgba.height) * zoom
    inverse = 1 / scale
    angle = math.radians(rotation)
    cosine, sine = math.cos(angle) * inverse, math.sin(angle) * inverse
    center_x = size[0] / 2 + offset[0] * size[0]
    center_y = size[1] / 2 + offset[1] * size[1]
    transform = (
        cosine,
        sine,
        rgba.width / 2 - center_x * cosine - center_y * sine,
        -sine,
        cosine,
        rgba.height / 2 + center_x * sine - center_y * cosine,
    )
    framed = rgba.transform(
        size,
        Image.Transform.AFFINE,
        transform,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )
    if brightness != 1.0:
        # Adjust before compositing so darkening never turns the white backdrop grey.
        # A lookup table uses the existing bundled Pillow core, so older runtimes
        # can receive this feature through OTA without new packaged dependencies.
        levels = [min(255, int(value * brightness)) for value in range(256)]
        adjusted = framed.convert("RGB").point(levels * 3)
        adjusted.putalpha(framed.getchannel("A"))
        framed = adjusted
    canvas = Image.new("RGBA", size, "white")
    return Image.alpha_composite(canvas, framed).convert("RGB")


def save_portrait(image, path, *, overwrite=True, size=OUTPUT_SIZE):
    """Enforce the export contract even if called outside the desktop UI."""
    result = format_portrait(image, size)
    path = Path(path)
    # An interrupted save never damages an existing output file.
    handle, temporary = tempfile.mkstemp(suffix=".png", dir=path.parent)
    os.close(handle)
    try:
        result.save(temporary, format="PNG", dpi=OUTPUT_DPI)
        if overwrite:
            os.replace(temporary, path)
        elif os.name == "nt":
            # Windows rename fails if the destination already exists.
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
