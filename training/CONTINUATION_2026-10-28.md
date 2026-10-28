# Existing-model continuation: 28 October 2026

The user requested continued training of the existing portrait model on the
22 new local photos. This run starts directly from the accepted checkpoint
`build/camo-lowqual-review/guided-adaptation/epoch-6.pt`, SHA-256
`12ac97b675eb0397d20276df169c79c190da131c3389933abc23d469a367b567`.
Its baseline ONNX export is byte-identical to the active client model,
SHA-256 `17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.
The architecture and model family remain MODNet. No P3M weights or public
training images are used in this continuation.

The training set consists of 22 new photos with the previously reviewed coarse
foreground/background labels and 19 earlier photos replayed against the fixed
accepted teacher. Unknown regions, including fine boundaries, have no reference
alpha mattes. Originals are not edited. The direct HEIC loader was checked
against the staged upright RGB copies before training; all three matched, and
all 22 original source hashes were unchanged.

The run uses the existing `training/adapt_modnet.py` trainer, Adam with a lower
learning rate of 0.0000005, seed 42, frozen normalization layers, and a 512px
maximum training side. Local outputs are retained under ignored
`build/new-photos-review/continuation-2026-10-28/`.

## Completed results

Three epochs completed, 123 optimizer steps. Mean training losses were
0.172013, 0.169709 and 0.163311. These are training objectives, not accuracy.
The trained checkpoint has exactly the same state keys and tensor shapes as the
accepted checkpoint; 388 state tensors changed. The exported ONNX SHA-256 is
`d55a72571f8a2a4e0c29c43595e2bbfe7640fcca2b6ad6005b1f9e21ca151526`.

Actual client ONNX inference and white RGB 1200-by-1200, 600 DPI PNG exports
passed for all 41 photos. PyTorch/ONNX numerical parity passed on three inputs
at absolute tolerance 0.0001 and relative tolerance 0.001; maximum mean alpha
difference was 0.0000003123. Four training-input regression tests passed.

On the 22 new photos' coarse training labels, foreground deficit decreased from
0.00537824 to 0.00529978 and background opacity decreased from 0.02004417 to
0.02001324. Mean output-alpha drift on the 19 earlier photos was 0.00170797.
These small changes do not prove improved generalization or hair boundaries.
All 41 photos are training examples; no independently labelled evaluation was
performed in this continuation. No public data was used for training or evaluation.

Visual inspection of contact sheets covering all 22 new photos and six earlier
low-quality challenges found largely similar outputs. Existing shadow fragments,
detached background objects and difficult low-quality hair failures remain.
Therefore the result is retained as a trained checkpoint rather than promoted
as a demonstrated quality improvement. The active client model remains unchanged,
as does client version 1.1.18. All 22 original hashes were checked again after
training and remained unchanged.

Local evidence: `training-report.json` and `selection.json` in the continuation
directory, plus actual-client comparisons and `review.json` under
`build/new-photos-review/review-continuation-2026-10-28/`.

Training checkpoints and ONNX exports are local continuations of the accepted
model, not a switch to a different pretrained model. Saving an experimental
checkpoint does not install it in the application. Images, annotations and model
weights remain outside Git. This run does not publish OTA or rebuild installers.
