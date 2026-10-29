# Automatic portrait alignment feasibility test — 29 October 2026

## Decision

Do not enable the tested YuNet eye-line approach automatically in IDFrame yet.
Detection is fast, but the landmark-derived rotation is insufficiently accurate.
The requested interaction remains automatic alignment after background removal,
without another button. This experiment does not implement that interaction.

## Method and provenance

Tested OpenCV Zoo's `face_detection_yunet_2023mar.onnx`, downloaded from the
[official model directory](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet).
The directory includes an MIT license. The file is 232,589 bytes, with locally
calculated SHA-256
`8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`.
This is a local identity check, not an independently published checksum.

Inference uses the existing application environment's ONNX Runtime 1.31.0 CPU
provider, two intra-operation threads and one inter-operation thread. Images are
contained within 384×384 pixels, placed at the top left of the fixed 640×640 BGR
input, and padded with zeros. Confidence threshold is 0.9; NMS IoU threshold is
0.3. Score, bounding-box and landmark decoding follow OpenCV's official
[`face_detect.cpp`](https://github.com/opencv/opencv/blob/4.x/modules/objdetect/src/face_detect.cpp).

For one independently checked tilted portrait, isolated OpenCV 4.12.0.88
FaceDetectorYN returned an eye angle of −3.0956°, versus −3.0966° from the ONNX
decoder. This supports that the observed under-correction is not simply a
different decoding implementation. It is not exhaustive decoder equivalence.
OpenCV was installed only beneath the ignored local experiment directory; the
application dependencies were not changed.

## Coverage

The local portrait folder contains 41 files. Pillow loaded 38; three HEIC files
were skipped because this test harness did not register a HEIC decoder. That is
a harness limitation, not a finding about IDFrame's existing photo loader.

Each readable file was tested as an original, at synthetic rotations −30°, −15°,
+15°, +30°, as an 80-pixel-maximum-side copy, and with Gaussian blur radius 2:
266 cases. Originals were bounded to 900 pixels before these transformations.
These are local convenience samples, not an independently annotated validation
dataset; files may depict similar subjects.

| Variant | Files | One detected face | No detected face |
|---|---:|---:|---:|
| Original | 38 | 31 | 7 |
| −30° | 38 | 27 | 11 |
| −15° | 38 | 29 | 9 |
| +15° | 38 | 30 | 8 |
| +30° | 38 | 19 | 19 |
| Low resolution | 38 | 30 | 8 |
| Blur | 38 | 30 | 8 |

Blank white pixels and seeded noise produced no faces. A composed two-person
image produced two faces, so a single-face-only application rule would skip it.
No production failure-handling logic was added or validated by these checks.

## Results

One detector pass, including bounded input preparation and decoding, took median
11.358 ms, 95th percentile 24.214 ms, maximum 30.344 ms. Session initialization
took 17.610 ms. File opening, background removal, UI work and export are excluded.

Relative rotation error compares each rotated image's estimated angle with its
original estimate minus the known injected rotation. Median absolute error was
12.156°, 95th percentile 26.605°, maximum 28.659°. This measures consistency with
known injected rotations; the original facial landmarks are not human-annotated
ground truth. It therefore cannot establish absolute eye-level accuracy.

Four independent corrected-image re-detections yielded residual estimated eye
angles of −1.69°, −5.61°, −1.71°, and −1.09°. Another attempted sample did not have
a single detectable face after the injected rotation. Re-detection uses the same
detector and can repeat its bias. Visual comparison also showed an obviously
tilted portrait remaining tilted despite a small reported angle.

A second experiment searched rotations −30°, −15°, 0°, +15°, +30°, then refined
the most confident candidate by ±5°. It tested 38 originals and their ±20° copies
(114 cases), bounded to 600 pixels before transformation. This is a different
experiment, not a direct timing comparison at identical image sizes.

- At least one single-face candidate was found for 94/114 cases.
- There were 61 comparable tilted cases with detectable baseline and candidate.
- Relative rotation error: median 5.645°, 95th percentile 14.336°, maximum 20.371°.
- Only 16/61 comparable cases were within 3° of the injected rotation.
- Search time: median 227.066 ms, 95th percentile 392.397 ms, maximum 462.277 ms.

Higher face-detection confidence is not a reliable indicator of a correct
straightening angle. The search is fast enough for further experiments but
does not meet a proposed 3° rotation-consistency target on this sample.

## Scope and next step

Do not add an automatic correction that might rotate an already acceptable
portrait incorrectly. A follow-up should evaluate a dedicated facial-landmark
estimator with independently checked eye locations before preview integration.
Use confidence/geometry checks to leave uncertain photos unchanged. Multiple-face
cases should also remain unchanged without adding a selection dialog by default.
Eye leveling does not reconstruct a front-facing pose from a turned head.

This was a detector/rotation feasibility test. Centering, crop/headroom quality,
UI responsiveness, preview/export equivalence and full-resolution resampling were
not implemented or tested. Production source, client version, dependencies,
background-removal weights, installers and the LAN OTA manifest remain unchanged.

Local-only scripts, downloaded detector, per-file measurements and visual
comparisons are under `build/alignment-probe/`. They are ignored by Git and
contain personal photos or filenames. No portrait data or generated comparison
images are included in this report's Git commit.
