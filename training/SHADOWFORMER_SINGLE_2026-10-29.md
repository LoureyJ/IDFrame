# ShadowFormer single-photo test: 29 October 2026

The user requested testing ShadowFormer on only the source photo shown in a
comparison screenshot. This completed experiment uses the original local
547-by-365 photo, not the collage. No other source photographs are processed.
It does not train or change IDFrame's production model.

## Model and inputs

Author repository: [GuoLanqing/ShadowFormer](https://github.com/GuoLanqing/ShadowFormer),
commit `f72158109ff3f09b4ee67d343cdc7c7b83c5ce6d`. The author's linked ISTD+
checkpoint is `ISTD_plus_model_latest.pth`, 137,241,888 bytes, downloaded from
Drive file ID `10pBsJenoWGriZ9kjWOcE4l4Kzg-F1TFd`. Its locally calculated SHA-256
is `2748060149908df37cc65f0695ef61d64cd25847aba0c35af36823f9b780f5b2`.
Length matches the download server's Content-Length. No independently published
checksum was found. The repository includes an MIT license.

The checkpoint loads with `weights_only=True` and a strict state-dictionary
match after removing the standard DataParallel `module.` prefix. The pinned
architecture uses embedding dimension 32, linear token projection, LEFF and a
10px attention window, consistent with checkpoint bias-table dimensions and the
author's test settings. CPU evaluation uses four PyTorch threads. Only unused
CLI/metrics imports (`utils`, `scipy.misc`) are omitted when loading the model;
no architecture or forward-operation code is changed. An isolated `einops`
installation is added to ignored `.tools/engine-bench`; the app runtime is unchanged.

ShadowFormer is an RGB restoration model requiring a shadow mask. Two inputs
are therefore tested on this same photo:

1. **Automatic:** cached SDDNet shadow probability thresholded at 0.5. This
   includes natural portrait shading and some non-shadow/portrait edges.
2. **Assisted:** a hand-reviewed polygon covering only the visible background
   cast shadow beside the head. This is manual guidance, not automatic detection
   and not a ground-truth full shadow mask. Its overlay was visually inspected.

RGB and mask tensors are in [0,1]. Reflect padding extends the original
547-by-365 image to 560-by-400, multiples of `8 * window_size`, following the
author's test implementation. Predictions are clamped to [0,1] and unpadded to
native dimensions. No source resizing, tiling or inference-time augmentation
is used. The automatic condition runs twice for first-call/warm diagnostics;
the assisted condition runs once. A final refinement expands the manual polygon
by seven pixels, then clips it to x>=357 and y<217 to keep it on the background.
This makes four calls on one photo, not four independent test images.

Each restored image is then passed to the accepted MODNet to obtain a new alpha
mask. That mask is applied to the **original RGB**, so the final white-background
cutout retains the source's facial/clothing colours rather than adopting the
restoration model's relighting. The fixed white RGB 1200px / 600 DPI export
contract remains in use.

## Observed results

| Condition | ShadowFormer forward seconds | MODNet + PNG export seconds | Sum of those measured stages |
| --- | ---: | ---: | ---: |
| Automatic, first call | 4.807 | 0.586 | 5.393 |
| Automatic, warm | 5.418 | 0.435 | 5.853 |
| Assisted background-only mask | 4.727 | 0.555 | 5.281 |
| Assisted, expanded background mask | 5.313 | 0.912 | 6.224 |

Model setup/loading took 0.346 seconds separately. These sums exclude shadow
detection, input decoding/padding, intermediate output conversion and diagnostic
image saving; they are **not full end-to-end pipeline timings**. They already
exceed five seconds, so the complete automatic workflow would also fail the
requested limit in this tested configuration. One photo and a few calls cannot
establish a general CPU latency distribution.

Mean MODNet alpha inside the manually selected background-shadow region changes
from 0.965760 on the original image to 0.618405 after automatic-mask restoration,
or 0.229761 after assisted-mask restoration. This is a diagnostic opacity
measurement in one selected region, not shadow-removal accuracy or proof of
generalization. There is no shadow-free ground-truth image, so no PSNR/SSIM or
restoration-accuracy claim is made. The expanded-mask check is retained separately
in `refinement-report.json` and does not replace the original measurements.

The native restored images, mask overlays and nine-panel comparison were visually
inspected. The automatic mask causes unwanted relighting/background patches,
and its subsequent cutout retains substantial shadow fragments. The assisted
mask produces a substantially cleaner outline while preserving the portrait's
source RGB in the final cutout, but a thin residual edge remains. It does not
fully match the clean BEN2 result and is not an automatic fix.
Expanding the background mask did not reliably improve the cutout: a larger dark
remnant reappeared beside the neck, and the measured stages rose to 6.224 seconds.
This final check demonstrates sensitivity to the supplied mask rather than a
robust cleanup rule. No further parameter search is launched.

## Decision and deliverables

**Single-photo test complete; no production integration.** ShadowFormer can
help this example when supplied a careful background-only shadow mask, but the
automatic mask still needs reliable person/hair exclusion. The tested CPU stages
also miss the 1–5 second target. No further training, model searches or batch
testing are performed as part of this request.

Local evidence under `build/shadowformer-one-photo/`:

- `comparison.jpg`: original, current cutout, automatic guidance/restoration,
  assisted guidance/restoration, and the expanded-mask cutout.
- `auto-mask-overlay.png` and `assisted-mask-overlay.png`: the exact guidance.
- `auto-warm-relit.png` and `assisted-relit.png`: native RGB restoration outputs.
- `auto-warm-original-rgb-2x2.png` and `assisted-original-rgb-2x2.png`: white
  exports using original RGB and the new MODNet alpha.
- `report.json`, `provenance.json`, pinned source and checkpoint.
- `refinement-report.json` and `assisted-wide-*`: final manual-mask check.

The source file hash is unchanged, every result has native 547-by-365 geometry,
and the white exports pass RGB / 1200-by-1200 / 600 DPI checks. Active MODNet and
U2Net hashes remain unchanged. Images, masks, checkpoints and local builds are
not committed to Git. Client version stays 1.1.18. No app/deployment code,
installer, OTA channel or GitHub release is changed.
