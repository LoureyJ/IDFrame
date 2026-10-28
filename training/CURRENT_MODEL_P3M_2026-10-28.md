# Fine-tuning the accepted MODNet with P3M: 28 October 2026

This experiment continues the accepted IDFrame portrait model, rather than
initializing from P3M-Net or from the earlier rejected P3M-trained checkpoint.
The starting checkpoint is the accepted local curl/camo/low-quality adaptation,
SHA-256 `12ac97b675eb0397d20276df169c79c190da131c3389933abc23d469a367b567`.
Its ONNX counterpart is the active client model, SHA-256
`17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.
The architecture remains MODNet throughout.

## Controlled training pass

The run uses the already cached P3M-10K image/alpha dataset, mirror revision
`a239de9297bd56e372cf3c9c82f7085d59e71219`. Every pinned shard's size and
SHA-256 were verified before use. The existing eight dataset/loss/cache/resume
tests passed before training. The original dataset release agreement remains
with the local dataset.

A deterministic sample from the 9,421-row official training split provides
256 supervised training pairs and 64 disjoint selection-validation pairs.
This is one pass over a bounded subset, not a full P3M-10K epoch. No official
test images enter fitting or checkpoint selection. Seed 73 controls sampling,
order, paired flips and input blur/brightness/JPEG degradation. Training uses
384px maximum-side geometry, frozen normalization, Adam at 0.000001, gradient
norm clipping at 1, and the existing semantic/detail/matte/composition loss.

To reduce forgetting, the accepted model is a frozen teacher. Every two public
steps are followed by one teacher-replay step drawn cyclically from 41 local
portraits (22 recent and 19 earlier). Local semantic/detail/matte MSE weights
are 5, 1 and 10. These replay targets are predictions, not ground-truth local
masks. On public training pairs, a 0.5-weight matte consistency term applies
only where the accepted teacher already agrees with the alpha label within
0.02. Other pixels remain free to learn corrections from the real masks.

The 64 held-out pairs are evaluated before training and after 128 and 256
public steps. Checkpoints retain model/optimizer state, RNG, cursor and metadata
every 64 public steps. Local experimental driver:
`build/finetune_current_p3m.py`; final run directory:
`build/current-p3m-2026-10-28-run3/`. Earlier setup attempts were abandoned after
a replay tensor-cache issue; neither supplied weights to this final run.

Photos, annotations, cached data and model checkpoints remain local and are
excluded from Git. Training does not itself publish OTA or rebuild installers.

## Results and decision

The final run completed 256 supervised steps and 128 local replay steps,
384 optimizer updates total. Its state keys and shapes exactly match the
accepted model; 388 state tensors changed. Final ONNX SHA-256:
`cde70097ba617ac03ab1746350ab58612228063ad1e41d6a4d1f0ee174ad3a73`.

On the 64 disjoint selection images at 384px, alpha MAE decreased from
0.01438412 to 0.01222741 and boundary MAE from 0.07942646 to 0.06403653.
Interior foreground deficit increased from 0.00835607 to 0.00856812.
The 128-step checkpoint also improved alpha/boundary errors, but its
foreground deficit was similarly above baseline.

The exported final model then processed the first 50 images from each official
500-image test split using actual client preprocessing and output-alpha
conversion at up to 768px. No official test images entered training. All
100 requested images succeeded. This is a diagnostic subset, not a complete
1,000-image benchmark. Baseline comparisons use exactly matching cached rows,
with model and dataset identities checked.

| Metric, equal-weight mean over 100 images | Accepted model | Fine-tuned model |
| --- | ---: | ---: |
| Alpha MAE | 0.01681876 | 0.01452682 |
| Alpha MSE | 0.01170916 | 0.01033423 |
| Custom 7-pixel boundary MAE | 0.10756810 | 0.08314285 |
| Interior foreground deficit | 0.00677976 | 0.00688169 |

Public subset alpha error is about 14% lower and boundary error about 23% lower.
These are relative error reductions, not accuracy percentages or official
leaderboard results. Foreground retention is slightly worse on this subset.

Actual client inference and white RGB 1200-by-1200 / 600 DPI exports passed
on all 41 local portraits. Numerical PyTorch/ONNX parity passed on three client
input shapes at absolute tolerance 0.0001 and relative tolerance 0.001; maximum
mean difference was 0.0000001035. All 22 original photo hashes remained
unchanged after training.

On the 22 new photos' weak training regions, foreground deficit increased from
0.00537824 to 0.00596955 and background opacity from 0.02004417 to 0.02275404.
Mean alpha drift on the 19 earlier replay photos was 0.00804039. These are
coarse training-region measurements, not independent local accuracy scores.
Contact sheets covering 12 new photos and six earlier low-quality challenges
were visually inspected. Some older low-quality hair improved, but office
background fragments persisted or enlarged and a new clothing hole appeared.

**Decision: retain the fine-tuned weights locally, without activating them.**
This run demonstrates that the existing model can learn from P3M masks, but
the public improvements do not resolve the office-photo regressions. Correct
local alpha masks remain necessary for reliable local supervision and
validation. No app/deployment code or active model was changed; client version
remains 1.1.18. No OTA, GitHub release or installer was published.

Private machine-readable evidence is in the run's `report.json`, `selection.json`
and `official-evaluation/evaluation.json`. Local export/comparison evidence is
under `build/new-photos-review/review-current-p3m-2026-10-28/`.
