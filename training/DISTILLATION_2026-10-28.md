# Fast MODNet distillation: 28 October 2026

The user approved teaching the accepted MODNet from reviewed BiRefNet portrait
masks, with an ideal subsecond client operation and an acceptable 1–5 seconds.
The teacher runs only on the host during data preparation. Student architecture,
client preprocessing and offline operation are preserved.

## Inputs and method

The starting accepted checkpoint has SHA-256
`12ac97b675eb0397d20276df169c79c190da131c3389933abc23d469a367b567`.
Its exported active ONNX has SHA-256
`17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.
The cached teacher is the official portrait model described in the
[BiRefNet evaluation](BIREFNET_PORTRAIT_2026-10-28.md), SHA-256
`1ba1c8ff5a7bbfadc8d8d13fb11d7be793f91f23d9d466549e37a854f6668f99`.

Visually reviewed teacher masks provide 26 local training pairs. Fifteen other
photos remain outside fitting, including the main three failures, all camouflage
examples, uncertain hair, nameplates/watermarks and a held-object case. Exact
image-byte hashes and paths cannot cross those partitions. Subject-disjointness
is not verified, and these local photos have been examined in earlier experiments.
Three reviewed teacher masks from the held-out group provide checkpoint-selection
agreement measurements; they are not independent ground-truth alpha mattes.

Existing coarse human-annotated foreground/background interiors override teacher
opacity only in those regions. Unknown/hair regions retain fractional teacher
alpha. These are corrected pseudo-labels, not complete manually annotated mattes.
Known teacher body-loss cases are excluded from training.

Public supervision uses 128 actual alpha pairs from the official P3M training
split, plus 64 separate training-split selection rows. The official test splits
are not used for student fitting. The pinned mirror revision is
`a239de9297bd56e372cf3c9c82f7085d59e71219`; all shard hashes are verified.
This bounded run is not a full 9,421-image P3M epoch.

MODNet retains 6,487,075 parameters. The backbone is frozen; 4,263,203 decoder
parameters remain trainable. Normalization running statistics are frozen using
the vendor's `freeze_norm()` method; decoder normalization affine weights and
biases can adapt. Local pairs use the client's 768px aspect-preserving geometry;
public training and selection use 512px. Paired flips preserve masks; mild input
brightness/degradation leaves alpha unchanged. Adam uses a learning rate of
0.000002, betas 0.9/0.99, seed 91 and gradient clipping at 1. Four epochs mix
128 public pairs and two repetitions of 26 local pairs: 720 optimizer updates.

The objective retains the existing semantic/detail/matte/composition losses and
adds stable matte-logit supervision. Foreground opacity receives weight 3,
fractional edges weight 4 and background weight 1. Teacher targets are detached;
confidently wrong student logits still receive finite correcting gradients.

## Reproduction and local evidence

`distillation.py` implements target corrections, soft loss and split checks;
`train_distillation.py` verifies a privately reviewed manifest and trains the
existing model. The manifest contains `photo_root`, active/teacher model hashes,
and `rows` with `index`, `sample`, `source_sha256`, `role` (`train` or `holdout`),
`teacher_mask`, `teacher_mask_sha256`, and, for training, `target` and
`target_sha256`. Source/mask hashes are checked before fitting. A reviewed
manifest is required; the trainer does not automatically accept teacher failures.

```powershell
.training-venv\Scripts\python.exe training/train_distillation.py `
  --manifest build/modnet-distillation-2026-10-28/manifest.json `
  --checkpoint build/camo-lowqual-review/guided-adaptation/epoch-6.pt `
  --output build/modnet-distillation-2026-10-28/run --epochs 4
```

The trainer saves epoch checkpoints and an atomic resume checkpoint with model,
optimizer, cursor, RNG and run configuration. Use the same command with `--resume`
after interruption. It exports a diagnostic final ONNX without copying it into
the application. Private masks, photos, weights and review outputs remain under
ignored local build directories.

## Quality results

All 720 updates and four epoch checkpoints completed. The frozen backbone was
verified bit-identical to its starting state. Lower values are better below;
these 64 selection images are from the public training split at 512px, not the
official test set or a full-resolution benchmark.

| Checkpoint | Alpha MAE | Boundary MAE | Solid-foreground deficit | Local teacher agreement MAE, 3 photos |
| --- | ---: | ---: | ---: | ---: |
| Active starting weights | 0.0129873 | 0.0869847 | 0.00622335 | 0.0890620 |
| Epoch 1 | 0.0115155 | 0.0692954 | 0.00655807 | 0.0937526 |
| Epoch 2 | 0.0112237 | 0.0657975 | 0.00671377 | 0.0946880 |
| Epoch 3 | 0.0110826 | 0.0645375 | 0.00669463 | 0.0937926 |
| Epoch 4 | 0.0110540 | 0.0637259 | 0.00720033 | 0.0927453 |

Epoch 1 was selected for further review because it retained the most solid
foreground among the trained candidates. Even this checkpoint increased public
foreground deficit by 5.4%, although alpha MAE improved by 11.3% and boundary MAE
by 20.3%. All four checkpoints worsened agreement on the three held-out teacher
masks. Teacher agreement is a diagnostic, not accuracy against human labels.

Actual client inference reviewed all 41 local photos. On the 22 office photos,
existing coarse-region foreground deficit increased from 0.00537824 to 0.00618834
(15.1% worse); background opacity decreased from 0.02004417 to 0.01964864
(2.0% better). These limited coarse interiors include training examples and do
not measure complete hair/silhouette accuracy. Mean alpha drift on the 19 older
challenge photos was 0.00972797; drift is not an accuracy measurement.

All eight contact sheets were visually inspected. The detached decoration,
nameplates and held phone remained. The patterned shirt developed a larger
missing area, and the difficult low-quality hair still had conspicuous missing
regions. Some small background remnants were reduced. Camouflage remained
unreliable. The candidate did not reproduce the teacher's large improvements on
the main failures.

ONNX/PyTorch parity passed on three actual client geometries with a maximum
per-image mean alpha difference of 8.9e-8 before 8-bit quantization. All 41 white
RGB 1200-by-1200 / 600 DPI PNG exports passed. Original source-file hashes were
unchanged; direct HEIC loading matched all three staged upright RGB conversions.

The selected diagnostic ONNX is stored locally as `selected-epoch-1.onnx`.
Its SHA-256 is
`d5652c7747d1ecd15791ce7d5ceb55a56032ea21d4b82e662e6d534bb6258b2e`.
The final epoch ONNX SHA-256 is
`efcb8e19afc833a444f0a644aaa0a6eee8c41a97602d908e65e9e69250aaf365`.
Neither candidate is activated: the person-first quality gate failed.

## Complete client latency

The application Python environment measured sequential CPU operations on this
Windows 11 host with an Intel Core i9-13900H (14 cores, 20 logical processors).
The pipeline includes `load_photo`, actual `remove`, default `frame_portrait`
and atomic `save_portrait`; it excludes user interaction and UI scheduling.
It uses the application's normal CPU sessions (up to four intra-op threads),
with no concurrent training or quality inference. Auto runs both existing
engines and performs the existing whole-mask selection.

Each model/mode processed one cold example and then all 41 photos warm. Cold
means a new inference session on the first main portrait, not a machine reboot;
filesystem data may be cached. The staged upright RGB versions of HEIC sources
were used, so native HEIC decoder time is excluded. All timed exports were
verified as white RGB 1200-by-1200 / 600 DPI PNG.

| Model / mode | Cold seconds | Warm median | Warm p95 | Warm maximum | Warm photos under 1 second |
| --- | ---: | ---: | ---: | ---: | ---: |
| Active / Fine Hair | 1.103 | 0.614 | 1.012 | 1.561 | 38/41 |
| Active / Auto | 2.075 | 1.352 | 1.880 | 2.351 | 7/41 |
| Candidate / Fine Hair | 1.088 | 0.829 | 1.297 | 1.812 | 27/41 |
| Candidate / Auto | 2.719 | 1.761 | 2.346 | 3.876 | 0/41 |

All observed operations fit within five seconds on this host. The student meets
the requested latency target here, with a subsecond Fine Hair median, but does
not achieve BiRefNet-like quality. This single sequential pass is not a
controlled speedup study: machine load, thermal state and PNG compressibility
can affect differences. These timings are not guarantees for other clients,
larger sources, native HEIC decoding or UI/queue latency.

## Verification and decision

All 103 application tests and 25 host training tests passed. The six new tests cover soft target
corrections, detachment, saturated-logit gradients, geometry, empty manifests
and byte-level split separation. Formatting, Ruff and function-purpose
documentation checks passed. Independent code review found ambiguous
normalizer-freezing documentation; the spec/plan now explicitly distinguish
frozen running statistics from trainable decoder affine parameters. All 363
normalization running-state buffers were verified unchanged after training.
All 41 source/mask identities and the active model hash were verified again.

The candidate is retained as a diagnostic experiment. Active weights and client
version 1.1.18 remain unchanged because the person-retention quality gate failed.
No application/deployment payload changed, so no prepare-only version increment,
OTA publication, release publication or installer rebuild was performed.
This small reviewed-data experiment cannot establish that distillation itself
cannot work; it shows that this bounded decoder fine-tune is insufficient.
Further training needs precise corrected local alpha labels and broader,
representative supervision before another deployment decision.

Local evidence: `build/modnet-distillation-2026-10-28/` contains the private
manifest, reviewed targets, completed run and client benchmark. The eight
comparison pages and quality/export report are under
`build/new-photos-review/review-distillation-2026-10-28/`. None are included in Git.
