# BEN2 and InSPyReNet evaluation: 28 October 2026

The user approved benchmarking the models referenced by a supplied ComfyUI
workflow against IDFrame's current engines. The complete per-photo processing
target is ideally below one second and at most five seconds on the tested host.
This is evaluation only: no training, client integration or weight activation.

The supplied `RBG.json` loads one image and routes it independently to two
duplicate RMBG-1.4 nodes, one BEN2 node and one InSPyReNet node. It does not merge
models or contain weights. This evaluation tests BEN2 and InSPyReNet locally,
not the full ComfyUI wrapper. RMBG-1.4 is outside the approved benchmark scope.

## Pinned models

- **BEN2:** author's public base ONNX from
  [PramaLLC/BEN2](https://huggingface.co/PramaLLC/BEN2), revision
  `e48a20765fb421d19dcdb0bf3cc61e802ca5ec8f`, 222,932,053 bytes. SHA-256
  `22cea62108ff53b7ccc20f7a008bf30494228d84b1687f29ecbe76936a998101`
  matches the repository's published LFS hash. This is the public base model,
  not the provider's separately advertised enhanced commercial model.
- **InSPyReNet:** unmodified architecture from
  [transparent-background](https://github.com/plemeri/transparent-background),
  commit `6860e05c4c57db8e29127aa78323b77c31b1188b`. Official base and fast
  checkpoints come from release 1.2.12; each is 367,520,613 bytes. Both match
  the author-provided MD5 checksums in the pinned configuration. Locally
  calculated SHA-256 hashes are recorded below; no upstream SHA-256 was supplied.
- **Current MODNet:** active `portrait_hair.onnx`, SHA-256
  `17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.
- **Current U2Net:** the installed `u2net_human_seg.onnx` used by Protect mode.
  Its fingerprint is recorded in the local benchmark report.

InSPyReNet base SHA-256:
`0a6fe2a73ab0532d6d0b8d82849a9760a226df719e3063d09b4149ece6f80fcd`.
InSPyReNet fast SHA-256:
`e61ed7e85763dd83a796e1d650ea78604fff524121750858c54a6b560ac58c82`.
The BEN2 and transparent-background repositories identify their licenses as MIT.

## Processing and measurements

MODNet, U2Net, BEN2 and InSPyReNet fast use the same 41 local photos: 22 office
examples and 19 earlier hair, camouflage and low-quality challenges. InSPyReNet
base is limited to a three-photo latency/quality screen because its 1024px CPU
processing exceeded the five-second ceiling. The three main shirt-pattern,
detached-decoration and blurry-head failures are first. Source byte hashes are
checked before and after processing. These photos have been examined in earlier
experiments; there are no independent complete local alpha mattes. Existing
coarse annotations on 22 office photos provide limited foreground/background
interior measurements, not overall accuracy or precise hair-edge accuracy.

BEN2 follows the author's pinned `onnx_run.py`: bilinear 1024-square RGB input
divided by 255, model inference, bilinear alpha resize and min-max normalization.
The official sample incorrectly passes width/height as the interpolation size;
this harness preserves native height/width without that intermediate distortion.
The graph takes float32 input and emits float16 alpha; postprocessing uses
float32 for interpolation/normalization. No extra hard mask threshold is added.

InSPyReNet uses the author's strict-loaded checkpoints and static resize modes:
1024-square for base and 384-square for fast, bilinear RGB resizing and ImageNet
normalization. The unmodified model supplies sigmoid/min-max alpha, which is
resized bilinearly to the native source size with `align_corners=True`, following
the wrapper. Optional GUI/download modules are not imported. Optional PyMatting
foreground recoloring is excluded so every engine preserves original RGB.

The existing MODNet and U2Net use actual IDFrame preprocessing, mask handling
and source-resolution output. Auto mode is not measured here: the table compares
individual engines. Every result passes through actual `frame_portrait` and
atomic `save_portrait`, producing white RGB PNG at 1200-by-1200 / 600 DPI.

Measurements include source decode, preprocessing, inference, native alpha
resize, framing and saving. Each engine runs alone in a separate process with
four CPU threads. ONNX engines use CPU Execution Provider, full graph
optimization, one inter-op thread and disabled CPU memory arena. InSPyReNet is
PyTorch CPU eager inference. Model loading is reported separately from first-use
and warm processing. Native HEIC decoding and UI scheduling are excluded: the
three HEIC sources use previously verified upright RGB conversions. Filesystem
caches, background applications and thermal state are not controlled, so this
single sequential run is not a universal hardware speed guarantee. The host is
Windows 11 on an Intel Core i9-13900H with 14 cores and 20 logical processors;
the benchmark uses the host training Python environment with ONNX Runtime 1.31.0
and PyTorch 2.14.1+cpu. Larger model loading
and lower available system memory can also affect the user-visible first call.

The application environment is unchanged. Additional evaluation packages live
only under ignored `.tools/engine-bench`; models, sources and outputs are under
ignored `build/engine-benchmark-2026-10-28/`. The local harness is
`build/benchmark_background_engines.py`; `provenance.json` records source URLs,
revisions, sizes and hashes. Reports preserve per-image timings, source hashes,
native alpha masks, export checks and coarse interior metrics.

## Completed timing results

All four full runs completed on the same 41 photos, without runtime exceptions
or export-format failures. The base screen completed on three photos. Times
below are warm complete operations, including PNG saving; lower is better.

| Engine | Photos | Median seconds | p95 seconds | Maximum seconds | Over 5 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Current MODNet | 41 | 1.100 | 1.846 | 2.653 | 0 |
| Current U2Net | 41 | 1.070 | 1.769 | 2.732 | 0 |
| BEN2 base | 41 | 19.162 | 26.527 | 27.059 | 41 |
| InSPyReNet fast | 41 | 3.776 | 5.036 | 5.715 | 3 |
| InSPyReNet base, limited screen | 3 | 20.858 | — | 24.297 | 3 |

The three-photo base screen is not directly comparable to the 41-photo averages;
it establishes that this configuration already misses the CPU speed limit on
the main failures. It was not extended to the rest of the dataset. Current
MODNet was under one second on 18/41 photos and U2Net on 11/41; none of the new
engines achieved a subsecond warm operation in this run.

| Engine | Model setup/loading seconds | First processing/export seconds, excluding loading |
| --- | ---: | ---: |
| Current MODNet | 0.188 | 1.761 |
| Current U2Net | 0.597 | 1.391 |
| BEN2 base | 2.730 | 16.464 |
| InSPyReNet fast | 5.943 | 3.409 |
| InSPyReNet base | 5.105 | 20.940 |

Setup includes local model construction and fingerprinting. A lazy-loaded first
operation would also incur that cost. These measured baselines differ from the
earlier distillation report: this run uses the training environment, bounded
ONNX session configuration and a later host/thermal state. The active weights
are unchanged; the different timings are not evidence of an application change.

## Quality findings

These are equal-weight means over the same 22 annotated office photos. Lower
foreground deficit means more known foreground is retained; lower background
opacity means less known background remains. Neither is overall alpha accuracy.

| Engine | Coarse foreground deficit | Coarse background opacity |
| --- | ---: | ---: |
| Current MODNet | 0.00537824 | 0.02004417 |
| Current U2Net | 0.01320873 | 0.06368449 |
| BEN2 base | 0.01531474 | 0.00973319 |
| InSPyReNet fast | 0.02287213 | 0.00671872 |

The base screen is omitted from this table because only two of its three photos
have these annotations; its smaller mean must not be compared to the 22-photo
means. Full local alpha and hair-edge ground truth are still unavailable.

All 11 comparison pages were visually reviewed, with original, active MODNet,
current U2Net, BEN2, InSPyReNet base (where screened) and InSPyReNet fast columns.

**BEN2 gains:** the detached decoration and wall-logo fragments are removed in
the main office examples. It preserves substantially more of the blurry head
and hair, removes the plant fragment behind a neck, and gives a more complete
old low-quality head/hat outline. Ordinary office portraits often look similar.

**BEN2 failures:** large clothing/body regions disappear in camouflage cases
25–28. Nameplate content is retained wholly or partly, and the held phone
remains. Some dark-background and fine-hair examples retain fringes or lose
fine detail. Cleaner background does not establish the user's person-first or
human-body-only object policy.

**InSPyReNet fast gains:** it removes detached office decorations and some logo
fragments, with a much lower average known-background opacity. Several normal
portraits look usable and it is substantially faster than BEN2 in this setup.

**InSPyReNet fast failures:** severe camouflage clothing/body loss, a large
missing facial region in case 30, extensive portrait loss in case 39, and a
washed-out shirt in case 36. The blurry-hair example keeps more silhouette but
has a conspicuous translucent background/halo. Some nameplate, watermark and
held-object content remains. These failures reject default integration even
before the three warm operations over five seconds are considered.

The unexpected face/body losses were checked against the author's actual
`static_resize`, `tonumpy`, `normalize` and `totensor` classes extracted from the
pinned source. On cases 30 and 39, input differences were below 4.8e-7 and stored
alpha versus direct reference-model output mean differences were below 6.6e-8.
The visible losses reproduce the reference processing, rather than coming from
a height/width or normalization error in the adapter.

**InSPyReNet base screen:** the three examples have cleaner decorations and more
complete hair than active MODNet on the blurry failure, but processing takes
17.47–24.30 seconds. No claim about its camouflage behavior or overall 41-photo
quality is supported by this limited screen.

## Decision and verification

**Keep the current production models.** None of these evaluated new
configurations meets both strict person retention and the requested 1–5 second
complete CPU-operation target. BEN2 is useful as a quality reference on ordinary
office failures but is too slow and still loses camouflaged bodies. InSPyReNet
fast is closer to the speed target but has unacceptable person-removal failures.

GPU execution, quantized variants, BEN2 float32 conversion, InSPyReNet TorchScript
and ONNX conversion were not tested. Their speed/quality effects are unknown;
these results are not a rejection of every possible optimized deployment.

All 167 warm exports passed RGB / 1200px / 600 DPI verification, and their
native alpha masks passed L-mode/source-dimension checks. All five cold exports
passed the same output contract during measurement.
Source hashes match across the four full runs and the base subset. The 22
original office files remain unchanged, and the three native HEIC conversions
still match upright source RGB. Both active model fingerprints were checked
again; U2Net SHA-256 is
`01eb6a29a5c4d8edb30b56adad9bb3a2a0535338e480724a213e0acfd2d1c73c`.
No photographs, private masks or weights are included in Git.

Local evidence is under `build/engine-benchmark-2026-10-28/`: `summary.json`,
per-engine reports/masks/exports, `COMPARISON.md`, 11 comparison pages,
`main-three-comparison.jpg`, and `inspyre-reference-verification.json`.
No application/deployment code changed. Client version remains 1.1.18, with no
prepare-only version increment, model activation, OTA publication, installer
rebuild or GitHub release.
