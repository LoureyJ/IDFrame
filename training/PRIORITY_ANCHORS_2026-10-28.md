# Person, hair, and background priorities: 28 October 2026

The user requested another training run with three priorities: preserve the
person, avoid clipping hair, and erase non-person background objects. Clothing,
glasses and worn accessories are retained as part of the portrait. The model
architecture remains MODNet; training starts from the accepted client checkpoint
SHA-256 `12ac97b675eb0397d20276df169c79c190da131c3389933abc23d469a367b567`,
corresponding to active ONNX SHA-256
`17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.

## Objectives

`training/priority_loss.py` supplements the existing supervised public-mask loss:

- Missing solid foreground receives weight 8; excess opacity in known background
  receives weight 3. These are region-normalized penalties, not a guarantee that
  every person pixel always wins every competing objective.
- Fractional alpha transitions receive weight 3, with opacity-gradient matching
  weight 2 in each spatial direction. Hair is not forced into a binary mask.
  Alpha transition supervision covers all soft edges; it has no separate hair
  segmentation or body-part labels.
- Local foreground/background scribbles use binary cross-entropy weights 8 and 3.
  Unlabelled regions distill the accepted teacher at weight 6, with semantic/detail
  MSE weights 5 and 1. Explicit scribbles override the teacher on known interiors.

Local matte supervision uses pre-sigmoid logits captured from the existing fusion
convolution, with BCEWithLogitsLoss for stable gradients even when the model is
confidently wrong. This is a training-only hook, removed before ONNX export; it
does not alter the network architecture or client processing. Independent review
identified an initial probability-clamp gradient issue; a failing regression test
was added, the issue was corrected, and the partial first attempt was abandoned.
The final run restarts from the accepted checkpoint, not the abandoned weights.

Seven objective tests cover person-vs-background weighting, fractional hair,
correction direction, teacher overrides, empty-region crops, differing branch
sizes, and confidently wrong logits. All passed, along with the eight existing
P3M loading/loss/cache/resume tests. Independent code review found no remaining
actionable findings. Formatting, lint and purpose-docstring checks passed.

## Data and scope

The controlled run uses the same deterministic 256 P3M training pairs and 64
disjoint selection pairs as the preceding experiment. All pinned shard hashes
were verified. No official test rows enter fitting or checkpoint selection.
Each public step is now followed by one local correction/replay step, rather
than one local step per two public steps. The 41 local examples comprise 22 new
portraits and 19 earlier challenges. Reviewed additional coarse labels cover five
background interiors around detached decorations and two shirt interiors at a
previous clothing failure. Original photos and earlier annotation files remain
unchanged; new labels are stored in a separate ignored guidance file.

Settings: seed 73, 384px maximum side, Adam learning rate 0.000001, frozen
normalization layers, gradient norm clipping at 1. The existing paired input
augmentation is retained. Public training uses real soft alpha mattes; local
photos still lack precise ground-truth alpha masks. Neither teacher replay nor
coarse circles establishes independent local accuracy.

The dataset's alpha labels define foreground, not arbitrary semantic categories.
An object included in a public foreground matte will not automatically become
background merely because it is non-human. This run teaches removal where labels
mark an object as background; it cannot guarantee removal of every held object or
separation of touching objects without further object-specific labels.

Local driver: `build/train_priority_anchors.py`. Final run:
`build/priority-anchors-2026-10-28-stable/`. Coarse priority labels and all private
photos/checkpoints remain outside Git. Training does not publish OTA or rebuild
installers.

## Completed results

The corrected run completed 256 public supervised steps and 256 local steps:
512 optimizer updates. This is one pass over the 256 selected public pairs,
not a full 9,421-pair epoch. Both trained checkpoints were evaluated on the
64 held-out selection pairs. Person retention took priority over boundary error
when selecting between trained checkpoints: step 128 had foreground deficit
0.00863226, while step 256 had 0.00904257. Both were worse than the accepted
baseline, 0.00835607. Step 128 was therefore retained for diagnostic client
review, without implying it beat the accepted model.

The selected model has the same state keys and tensor shapes as the accepted
model, with 388 state tensors changed. Selected ONNX SHA-256:
`e27c7d44383c662d5bef506521d176d9d9937aa75fb7776565409cd8db79c5e7`.
The final step-256 ONNX SHA-256 is
`010b48d982bf152a67163478b676d51932679fed8ea0974d5b022c1806cdeadc`.

Actual client evaluation reused the diagnostic first 50 rows from each official
test split, 100 images total. All 100 succeeded. This is neither a complete
1,000-image benchmark nor a new untouched test set. Model/dataset identities and
exact row correspondence were verified against cached accepted-model results.

| Metric, equal-weight mean over 100 images | Accepted | Priority checkpoint |
| --- | ---: | ---: |
| Alpha MAE | 0.01681876 | 0.01576304 |
| Alpha MSE | 0.01170916 | 0.01100951 |
| Custom 7-pixel boundary MAE | 0.10756810 | 0.09607990 |
| Interior foreground deficit | 0.00677976 | 0.00714038 |

The public alpha/boundary errors are lower, but person retention is worse.
Actual client inference and white RGB 1200-by-1200 / 600 DPI exports passed for
all 41 local photos. PyTorch/ONNX numerical parity passed at three client
geometries; maximum mean alpha difference was 0.0000001022. Source photo hashes
were checked again after training; all 22 originals remained unchanged.

The original 22-photo weak-region comparison remains directly comparable to
earlier runs; added circles are measured separately:

| Local measurement, lower is better | Accepted | Previous P3M run | Priority checkpoint |
| --- | ---: | ---: | ---: |
| Coarse foreground deficit | 0.00537824 | 0.00596955 | 0.00561203 |
| Coarse background opacity | 0.02004417 | 0.02275404 | 0.02067255 |

Average office errors are smaller than the preceding P3M run, but still worse
than active weights. These are measurements on weak training labels, not
independent local accuracy. Mean opacity drift on the 19 earlier photos was
0.00557124. On newly annotated training regions, the detached-decoration opacity
increased from 0.546489 to 0.702308 and the shirt foreground deficit from
0.044371 to 0.268283. The second labeled background region stayed at zero opacity.
The explicit corrections therefore did not produce the intended result at client
inference geometry. The reason for this generalization failure was not established
by these measurements; adding loss weights is not proof of learning each priority.

Contact sheets covering six new portraits and six older low-quality challenges
were visually inspected. Clothing damage and detached background decoration
remain. **The person-first requirement is not met; do not activate these weights.**
All 19 host-training tests passed and independent review found no remaining
actionable code issue. Test success checks the training implementation, not
portrait quality. Active weights and client version 1.1.18 remain unchanged.
No installer, OTA or GitHub release was published.

Private evidence is retained in the run's `report.json`, `selection.json`,
`corrected-region-review.json`, `official-evaluation/`, and local comparison
folder `build/new-photos-review/review-priority-anchors-2026-10-28/`.
