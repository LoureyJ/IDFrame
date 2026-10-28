"""Experimental host-only fusion of person, hair and shadow masks; not enabled in clients."""

import math
import numpy as np
from PIL import Image, ImageFilter


def fuse_shadow_masks(fine_hair, protected, shadow, *, strength=1.0, core_radius=0.05):
    """Preserve a conservative person core and attenuate shadows outside it.

    All three inputs are aligned L-mode masks. Shadow white means shadow, while
    white in the other masks means person. This is mask fusion, not weight merging.
    Protection is heuristic: an erroneous person mask can also protect a shadow.
    Validate real portraits before treating this experiment as a deployment rule.
    """
    if fine_hair.size != protected.size or fine_hair.size != shadow.size:
        raise ValueError("Model mask geometry differs")
    if min(protected.size) < 1:
        raise ValueError("Model masks must have positive dimensions")
    if any(mask.mode != "L" for mask in (fine_hair, protected, shadow)):
        raise ValueError("Aligned L-mode masks are required")
    if not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("Shadow strength must be between zero and one")
    if not math.isfinite(core_radius) or not 0 < core_radius <= 0.15:
        raise ValueError("Person core radius is invalid")
    scale = 256 / max(protected.size)
    size = tuple(max(1, round(side * scale)) for side in protected.size)
    silhouette = protected.resize(size, Image.Resampling.BICUBIC)
    radius = max(1, round(min(size) * core_radius))
    core = np.asarray(silhouette.filter(ImageFilter.MinFilter(radius * 2 + 1))) > 245
    guard = Image.fromarray(np.uint8(core) * 255).resize(
        protected.size, Image.Resampling.BILINEAR
    )
    guard = np.asarray(guard, dtype=np.float32) / 255
    matte = np.asarray(fine_hair, dtype=np.float32) / 255
    person = np.asarray(protected, dtype=np.float32) / 255
    probability = np.asarray(shadow, dtype=np.float32) / 255
    # Preserve extra fractional hair where the shadow detector is not confident.
    detail = (
        (matte > person + 0.1) & (matte < 0.98) & (person > 0.02) & (probability < 0.5)
    )
    guard = np.maximum(guard, detail.astype(np.float32))
    # Restore confidently protected interiors before suppressing external shadows.
    base = matte + (np.maximum(matte, person) - matte) * guard
    fused = base * (1 - strength * probability * (1 - guard))
    return Image.fromarray(np.uint8(np.rint(np.clip(fused, 0, 1) * 255)))
