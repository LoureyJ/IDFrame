# BiRefNet-portrait local evaluation: 28 October 2026

The user requested a test of BiRefNet-portrait after repeated MODNet fine-tuning
and a U2Net/PyMatting prototype failed the person-first quality requirement.
This experiment evaluates the author's existing portrait model; no training,
model merging or application integration is performed.

## Model and processing

The model is `BiRefNet-portrait-epoch_150.onnx` from the author's
[official v1 release](https://github.com/ZhengPeng7/BiRefNet/releases/tag/v1),
asset ID 186740865, last updated 18 August 2024. Download length was checked
against the release API: 972,666,916 bytes. Local SHA-256:
`1ba1c8ff5a7bbfadc8d8d13fb11d7be793f91f23d9d466549e37a854f6668f99`.
The upstream asset did not supply a digest, so this is a locally computed
fingerprint, not verification against an independently published checksum.
The repository and portrait model card identify the license as MIT.

The [author's ONNX notebook](https://github.com/ZhengPeng7/BiRefNet/blob/main/tutorials/BiRefNet_pth2onnx.ipynb)
specifies square 1024-by-1024 RGB bilinear resize, float32 pixels divided by 255,
ImageNet means `[0.485, 0.456, 0.406]`, standard deviations
`[0.229, 0.224, 0.225]`, and sigmoid applied to the last ONNX output.
The downloaded graph exposes one float input and one 1024-by-1024 output.
The harness uses those settings, quantizes opacity to 8 bits and resizes it
bicubically to the original image dimensions. It retains original RGB and
does not apply the optional foreground recoloring/refinement routine.

The comparison baseline is the active MODNet weights, SHA-256
`17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.
This compares engines directly rather than the application's Auto selection
heuristic. Both ONNX sessions use four intra-op threads, one inter-op thread,
CPU execution, disabled CPU memory arena and full graph optimization.
An initial basic-optimization pilot is retained separately; its timings are
not pooled with the optimized run.

The planned local set contains 41 photos: 22 recent office portraits and
19 earlier hair, camouflage and low-quality challenges. The same three
known shirt/decoration/hair failures are processed first. Comparison images
retain original, active-model, and BiRefNet results in that order. Every
completed example is also exported as white RGB PNG, 1200-by-1200 at 600 DPI.

There are no precise independent alpha masks for the local photos. Existing
coarse foreground/background regions allow limited interior measurements;
they are not complete silhouette or hair-boundary accuracy. Some public photos
could overlap the author's training data. The model card lists P3M training
data including the non-private test split, so that split must not be presented
as unseen evaluation for this model.

Local harness: `build/compare_birefnet_portrait.py`. Download source, size and
fingerprint: `build/birefnet-portrait-2026-10-28/provenance.json`. Optimized-run
evidence is under `build/birefnet-portrait-2026-10-28/optimized/`; the initial
basic-optimization pilot is in its parent folder. All photos, masks, model
weights and comparison outputs remain outside Git.

## Completed results

All 41 unique comparisons completed without inference failures. All 41 white
RGB 1200-by-1200 / 600 DPI exports passed verification, as did input-file hashes.
All 11 comparison pages were visually inspected. Original source hashes and the
active model hash were checked again after processing.

| Measurement | Active MODNet | BiRefNet-portrait |
| --- | ---: | ---: |
| ONNX file size, decimal MB | 25.97 | 972.67 |
| Median CPU processing time, seconds | 0.812 | 29.125 |
| Observed processing range, seconds | 0.30–2.41 | 20.41–48.17 |
| Coarse office foreground deficit | 0.00537824 | 0.00549306 |
| Coarse office background opacity | 0.02004417 | 0.01832160 |

The optimized BiRefNet session loaded in 6.97 seconds, excluded from per-photo
times. Timings cover preprocessing, inference and mask-to-source resizing;
file loading, saving and comparison rendering are excluded. Later samples were
slower than early samples. Cause was not isolated, so these observations are
not a controlled cross-machine performance benchmark. The initial three-image
basic-optimization pilot took 30.64–39.08 seconds per BiRefNet result; it is not
included in the table. Optional foreground recoloring was not tested.

Coarse scores average the same regions over the 22 recent office portraits.
Background opacity decreased about 8.6%, while missing-foreground deficit
increased about 2.1%. These are relative changes in small, weakly labelled
interiors, not overall accuracy percentages. They cannot measure all hair,
silhouette or unwanted-object errors.

### Visible improvements

- Examples 1 and 2 preserve the shirt pattern/person while removing the detached
  wall-decoration fragments retained by active MODNet.
- Example 3 preserves substantially more head/hair in the blurry portrait.
- Example 9 removes an additional wall-logo fragment above the person.
- Example 32 removes a plant fragment behind the neck.
- Examples 36 and 39 produce substantially more complete head/hat boundaries
  and less retained surrounding background in very low-quality photos.
- Several camouflage examples separate the person from a matching pattern much
  better, while ordinary office portraits often look similar.

### Remaining failures and tradeoffs

- Example 24 retains mainly the head and erases most of the heavily camouflaged
  body. Example 29 also loses large body/shoulder regions. These fail the
  person-first requirement despite cleaner backgrounds.
- Nameplates remain attached in some ID-photo crops. A held object remains in
  example 36. This model does not implement a universal "human body only" policy.
- Some hair/shoulder outlines differ, and the coarse foreground-retention mean
  is slightly worse than the accepted model. No claim of uniformly better
  person retention is supported.
- Median CPU processing is about 36 times the active model in this configuration,
  and the weight file is about 37 times larger. GPU, quantization, alternate
  BiRefNet variants, arena settings and other performance optimizations were not
  tested; their effects must not be assumed from this run.

**Decision: retain as a promising quality candidate, without replacing active
weights.** It fixes several concrete failures that the earlier training runs
did not fix, but it still fails strict person preservation on extreme camouflage
and carries a substantial measured CPU cost. A production choice needs those
tradeoffs reviewed rather than a claim that every parameter is now correct.
No app or deployment code changed, client version remains 1.1.18, and no
installer, OTA channel or GitHub release was published.

The private `optimized/COMPARISON.md` indexes all 11 comparison pages. Machine-
readable timings, weak-region results and provenance are in `optimized/report.json`.
