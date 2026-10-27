# Local portrait training: 27 October 2026

The user supplied 22 photos under private `training photos/new photos`, including
three HEIC files. All files decoded successfully. EXIF orientation was applied to
local RGB copies; source hashes were checked again afterward and all 22 originals
were unchanged. The new direct HEIC loader produced byte-identical upright RGB
pixels to the three staged copies. No photos, annotations, checkpoints or candidate
weights are included in Git.

## Labels and safeguards

No reference alpha mattes were supplied. Coarse interior foreground/background
circles were placed and inspected; unlabelled pixels, including hair boundaries,
remained unknown. Initial trial annotations touching silhouettes were corrected or
removed before the final run. Those trial outputs were discarded. These labels
are weak supervision, not precise segmentation ground truth.

Training started from the existing accepted photographic/curl/challenge model,
not the rejected P3M candidate. Its ONNX SHA-256 is
`17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.
The checkpoint SHA-256 is
`12ac97b675eb0397d20276df169c79c190da131c3389933abc23d469a367b567`.
Nineteen earlier portraits were included as fixed-teacher replay.

## Full fine-tuning trial

The completed run used six epochs and 246 optimizer steps: 22 new images plus
19 replay images per epoch. Settings: Adam, learning rate 0.000005, seed 42,
four CPU threads, 512px maximum training side, frozen normalization layers,
supervised coarse interiors and teacher consistency elsewhere. Epochs 3 and 6
were exported and reviewed. Mean objective fell from 0.177664 to 0.030126;
this loss is not an accuracy score.

Both checkpoints passed actual ONNX inference, PyTorch/ONNX opacity comparisons
and white RGB 1200×1200 / 600 DPI export checks on all 41 local examples.
Checkpoint 6 reduced mean opacity in the coarse background regions from 0.020044
to 0.017664, while foreground deficit changed from 0.005378 to 0.005348. These
measurements use training annotations and cannot establish generalization.

For a separate diagnostic comparison, each model processed the same first 50
images from each official P3M test split, 100 images total, using actual client
preprocessing. There were no inference failures. Means below give each image
equal weight. Boundary error uses the project's custom 7-pixel band and is not an
official leaderboard metric. This is a subset comparison, not a full benchmark.

| Model | Alpha MAE | Boundary MAE | Interior deficit |
| --- | ---: | ---: | ---: |
| Accepted model | 0.016819 | 0.107568 | 0.006780 |
| Full fine-tune, epoch 3 | 0.019152 | 0.150743 | 0.008273 |
| Full fine-tune, epoch 6 | 0.020594 | 0.154096 | 0.007162 |

Both full fine-tuning checkpoints are rejected for activation: some local
background residue improved, but public alpha/boundary errors increased.

## Frozen-feature correction

A second experiment keeps the learned feature extractor and other weights fixed.
Only the final 1×1 output convolution's 17 parameters are fitted using stable
logits supervision on known interiors. Unknown edges/interiors, the 19 earlier
portraits and 64 public **training-split** photos use the accepted model as teacher.
No official test images enter fitting. Settings: Adam 0.001, 200 steps, seed 42,
teacher MSE weight 30 and parameter-drift weight 0.1. The private images use
client geometry up to 768px. Pixel features are sampled reproducibly.

The correction changed exactly the two final weight/bias tensors, 17 values
total; all other model state remained identical. Actual client tests passed
on 41 local images, with PyTorch/ONNX numerical parity checked at three
client input shapes. Public subset alpha MAE was 0.017137, boundary
MAE 0.111149, and interior deficit 0.007331.

On the new weak labels, foreground deficit was 0.005533
and background opacity 0.020033. Earlier-photo
output drift was 0.001362, smaller than full fine-tuning.
However, this produced no meaningful background improvement and slightly
worsened public alpha/boundary error and solid foreground retention.

**Selection: retain the current deployed model.** Both full fine-tuning
checkpoints and the output correction remain local experiment artifacts.
No installer, OTA channel or active model was changed. Client version stays
1.1.18 because the maintained code change concerns host-only training input.
Reliable further supervised improvement needs corrected alpha mattes, not
additional unlabelled photos alone. Twelve training tests and the source
formatting/lint/documentation checks passed; a fresh ingestion-code review
found no actionable findings.

## Reproduction and local evidence

`training/requirements.txt` includes host-only `pillow-heif==1.8.1`. Adaptation
discovers HEIC/HEIF as well as existing image types and registers the codec only
for those files. HEIC discovery and orientation in a fresh process have regression
coverage. The client application has no new dependency or photo format changes.

The completed full trial can be reproduced from the retained private staging and
annotation files with:

```powershell
.training-venv\Scripts\python training/adapt_modnet.py --photos build/new-photos-review/photos --checkpoint build/camo-lowqual-review/guided-adaptation/epoch-6.pt --output build/new-photos-review/reproduction --guidance build/new-photos-review/guidance.json --lr 0.000005 --epochs 6
```

Private evidence is under ignored `build/new-photos-review/`: input hashes,
staged copies, reviewed annotations, rejected trials, completed checkpoints,
bounded contact sheets, per-image comparisons and public subset reports.
The frozen-feature experiment's local driver is
`build/calibrate_new_photo_head.py`; it is an experimental host script rather
than a supported client feature. Trained candidates do not enter client updates
unless deliberately selected for `models/portrait_hair.onnx` and versioned.
