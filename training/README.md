# Local portrait adaptation

## Camo and low-quality challenge set

The second training round includes six images under `training photos/camo/`, six
under `training photos/low qual/` (including AVIF), and the original seven curl
examples for replay. Discovery is recursive. Relative paths and original extensions
are preserved in review filenames, so duplicate names in different folders cannot
overwrite each other.

A first SOC-only attempt was rejected after reviewing epoch 3: it reinforced
missing subjects and removed more of several faces. Its evidence is retained under
`build/camo-lowqual-review/adaptation/` and `rejected-soc.json`. It was never activated.

The guided run starts again from the accepted curl checkpoint, not the rejected
weights. `challenge_guidance.json` supplies assistant-created coarse foreground and
background interior circles on the 12 new photos. Green/red review overlays are in
`build/camo-lowqual-review/guidance.jpg`. These weak annotations are **not precise
alpha mattes**. Unknown pixels, including fine hair boundaries, are left unlabelled.
Balanced binary cross-entropy trains the semantic, detail, and matte branches on
known interiors; a small teacher anchor constrains unknown pixels. The original
seven examples replay the accepted model's continuous predictions against a fixed
teacher to reduce forgetting. The normalizers remain frozen and gradients clipped.

The run completed 10 epochs / 190 steps at learning rate 0.00002, seed 42.
Visual selection retained **epoch 6 (114 steps)** for the active model because it
keeps more of the blurred hair/hat and grid clothing than epoch 10. The final
checkpoint's lower training loss was not a reliable guide to those boundaries.
`guided-adaptation/selection.json` records the choice and model hash.

```powershell
.training-venv\Scripts\python training/adapt_modnet.py --checkpoint build/training-review/modnet-adaptation/epoch-10.pt --output build/camo-lowqual-review/guided-adaptation --guidance training/challenge_guidance.json --lr 0.00002 --epochs 10
.training-venv\Scripts\python training/export_checkpoint.py --checkpoint build/camo-lowqual-review/guided-adaptation/epoch-6.pt --output build/camo-lowqual-review/guided-adaptation/selected.onnx
.venv\Scripts\python training/review_adaptation.py --run build/camo-lowqual-review/guided-adaptation --model selected.onnx --epoch epoch-6
.training-venv\Scripts\python training/test_dataset.py
```

The review command uses the actual client ONNX inference, checks agreement with
PyTorch previews and verifies white RGB 1200px/600 DPI exports. Contact sheets compare
original / previous model / candidate model. Mean opacity and training losses are
diagnostics, not segmentation accuracy. All 19 photos are training examples; no
independent labelled test set is available. Camouflaged boundaries and missing
details in blurry source images can still require manual corrections.
Selected outputs and ONNX/PyTorch comparisons for all 19 photos are under
`build/camo-lowqual-review/client-review/`. Review shows more complete faces and
clothing in several challenge examples while the curl examples remain similar.
Substantial residue remains in some patterned backgrounds, and some hair/hat areas
remain incomplete. This model is not a complete solution to the camouflage set.

## Original curl adaptation

The initial `models/portrait_hair.onnx` was adapted locally from photographic
[MODNet](https://github.com/ZHKKKe/MODNet) using the seven images in `training photos/`.
The process used 10 epochs, 70 optimizer steps, Adam at 0.00001, seed 42, and four CPU
threads. The architecture is Apache-2.0; its license is included under
`assets/licenses/MODNet/` and with the vendored source.

These are original images without manually labelled foreground alpha mattes.
Training therefore uses **self-supervised sub-objective consistency (SOC-style)
adaptation**, following the method provided by the MODNet authors. It is not
supervised hair segmentation training. The CPU implementation uses frozen normalizers,
teacher edge consistency, clipped gradients, a binomial blur, and morphological
boundary masks. It keeps a pretrained teacher at the beginning of each epoch.

No photo is uploaded. CPU-only PyTorch/ONNX export dependencies are isolated in
`.training-venv`. Clients require only the existing ONNX Runtime, NumPy, and Pillow.
The client preserves continuous opacity rather than converting hair into a binary
mask, and uses an aspect-preserving 768px matting input rather than the previous
320px square segmentation input. `u2net_human_seg.onnx` remains the fallback when the
adapted model is absent.

## Results and limits

Review images and logs are in `build/training-review/`:

- `hair-comparison.png`: previous versus adapted output on the orange/red curl cases.
- `all-seven-review.jpg`: all seven originals with previous and adapted removals.
- `modnet-adaptation/training-report.json`: data hashes, parameters, and epoch losses.
- `adapted-inference.json`: actual CPU ONNX inference timings and alpha ranges.
- `modnet-adaptation/before/`: pretrained MODNet outputs, before local adaptation.
- `modnet-adaptation/epoch-3/`, `epoch-6/`, `epoch-10/`: training checkpoints' outputs.

The mean SOC objective was 0.08485 in epoch 1 and 0.03087 in epoch 10. These are
self-consistency losses, **not foreground accuracy scores**. All seven images were
adaptation examples; none is an independent labelled validation set. Visual review
shows substantially less orange/red background around curls compared with the old
U2Net model. The pretrained MODNet upgrade already provides most of that difference;
the additional adaptation is smaller. Difficult shadows, very similar clothing and
background colours, and very low-resolution source photos can still be imperfect.
True quantitative hair-edge validation or supervised fine-tuning requires manually
reviewed alpha mattes and a separate validation set.

## Reproduce

`training/vendor/MODNet/PROVENANCE.json` records the pinned architecture commit.
The initial photographic checkpoint in `training/checkpoints/` has SHA-256
`7c22235f0925deba15d4d63e53afcb654c47055bbcd98f56e393ab2584007ed8`, mirrored from
the original model at
`https://huggingface.co/DavG25/modnet-pretrained-models` revision
`903cc06311b3b12071edfa1b42b534e4a31c718a`.

```powershell
py -3.12 -m venv --system-site-packages .training-venv
.training-venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.training-venv\Scripts\python -m pip install -r training/requirements.txt
.training-venv\Scripts\python training/adapt_modnet.py --epochs 10 --root-only
```

Training outputs go to `build/training-review/modnet-adaptation`. The script does not
overwrite the active model, publish OTA updates, or rebuild installers. Visually
review exported results before copying an accepted model to `models/portrait_hair.onnx`.
Then prepare the client version with `build_release.py --prepare-only`.

The next user-triggered `update.bat` publication includes the new ONNX file and the
changed application code. Training images, checkpoint files, training dependencies,
and review outputs are not client payload files.
