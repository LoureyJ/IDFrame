# IDFrame v1.1.16 validation record

The PySide6 workspace and separate cleanup editor are implemented. Client v1.1.16
was prepared with `build_release.py --prepare-only`. No installer was rebuilt and
the live LAN OTA repository was not published. Existing installed models remain
unchanged. Source delivery and training results are recorded below.

## Application and distribution

- 103 application/deployment tests passed after the final runtime changes.
- Eight public-data training/evaluation fixture tests passed, including continuous
  alpha, paired geometry, split isolation, loss gradients, exact optimizer/RNG
  checkpoint restoration, failed-inference reporting and cache ownership.
- Black, Ruff and function-purpose documentation checks passed. Documentation
  covers 59 maintained Python files.
- A clean PyInstaller runtime started with Qt, constructed the cleanup editor,
  erased and undid a stroke, and exported white RGB 1200×1200 PNG at 599.9988 DPI.
  Its title displayed IDFrame v1.1.16.
- An isolated copy of the v1.1.15 frozen launcher downloaded the complete signed
  Qt payload, started it, retained the model file's timestamp, downloaded no blobs
  on the next launch, and reopened with its test server offline. The test changed
  153 files. It used a loopback-only temporary repository, not the live OTA host.
- The first frozen build exposed an incompatible Poppler ICU DLL discovered on
  the build machine's PATH. Packaging now isolates its native search path and
  cleans PyInstaller analysis before rebuilding. The corrected payload passed
  without renaming or removing DLLs after the build.

On a synthetic 4000×6000 photo, 50 offscreen Qt resize operations measured median
9.91 ms / maximum 18.20 ms; 50 appearance changes measured median 29.26 ms / maximum
55.26 ms. These operations caused **zero additional image preparations**. This
measures Qt event handling/painting on this host, not continuous native drag FPS.
Windows Light/Dark, maximize/restore, erase, keyboard Undo/Redo and Cancel were
visually checked. Desktop interaction ended after the user's physical Escape;
a complete native walkthrough and continuous border-drag measurement remain
unverified. Automated geometry tests cover small/scaled logical desktops and
verify actual Save/Apply button bounds.

## Public training experiment

The public P3M mirror was pinned to revision
`a239de9297bd56e372cf3c9c82f7085d59e71219`. All 13 shards were hash-verified;
the local audit found 9,421 train, 500 P and 500 NP rows and no byte-identical
image overlap between splits. Source data, photographs, checkpoints and candidate
weights remain outside Git.

One complete epoch used 9,021 training pairs and 400 fixed selection-validation
pairs, with continuous ground-truth alpha labels. It started from the original
photographic MODNet checkpoint, not the previously adapted local model. Training
used Intel Core i9-13900H CPU, two threads, PyTorch 2.14.1+cpu, seed 42, maximum
side 384, Adam learning rate 0.00001 and frozen normalization layers. No client
submission or collection service was added.

Selection validation (400 pairs at training geometry):

| Model | Alpha MAE | Alpha MSE | Boundary MAE | Interior opacity deficit |
| --- | ---: | ---: | ---: | ---: |
| Original photographic checkpoint | 0.015148 | 0.011006 | 0.064300 | 0.020354 |
| One-epoch P3M candidate | 0.008648 | 0.006166 | 0.043904 | 0.009343 |

The candidate ONNX SHA-256 is
`fbe89b866983f89d201aafd63c5941898ca55d5aa49594f5c121a61766060309`.
PyTorch/ONNX comparisons at actual client input geometries (768×640, 512×768,
768×768) passed `atol=0.0001, rtol=0.001`. Maximum absolute alpha differences
were 0.000007391, 0.000002146 and 0.000018388 respectively.

The official test comparison uses actual client preprocessing and opacity
conversion, metrics at maximum side 768, and equal-weight per-image means. Its
7-pixel boundary metric is custom; these are not official leaderboard scores.

| Test split | Model | Images | Alpha MAE | Alpha MSE | Boundary MAE | Interior deficit |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| P3M_500_P | current | 500 | 0.026449 | 0.020889 | 0.121170 | 0.013780 |
| P3M_500_P | candidate | 500 | 0.013426 | 0.010015 | 0.070930 | 0.011854 |
| P3M_500_NP | current | 500 | 0.018477 | 0.012755 | 0.101571 | 0.008247 |
| P3M_500_NP | candidate | 500 | 0.010745 | 0.007023 | 0.060928 | 0.009177 |

Both runs completed all 1,000 images with zero inference failures. Lower errors on
these public test images do not override the subject-loss regressions below.
The NP split's interior opacity deficit worsened from 0.008247 to 0.009177,
despite lower overall alpha MAE and boundary error.

Visual review covered six public test portraits and the existing 19 local
challenge photos. Public curls and several ordinary portraits look cleaner, but
the candidate removes substantial face/body regions in several low-quality
examples and loses clothing in camouflage examples. **Do not activate this
candidate.** The deployed fine-hair model is retained with SHA-256
`17567979483c1e9e7dd6809e84917e169a76ea052633b0b5285168e33e2917ae`.
The existing Auto/Protect person/Fine hair behavior therefore remains intact.

## Review decisions and remaining limits

The single fresh whole-change review found no critical defects. Two important
findings were reproduced with failing tests and fixed: screen bounds overriding
fixed minimum window sizes, and unowned/mismatched evaluation caches. Their
regressions and the full application suite passed after correction.

Decisions during execution:

1. Used a feature branch in the existing checkout because separate-worktree
   consent was not received. Preserved pre-existing line-ending-only changes;
   the cost is shared-checkout interference risk during concurrent user edits.
2. Used a Windows-native ignored progress ledger because the skill's Bash-only
   bookkeeping helpers could not run here. Committed this validation record for
   durable evidence; automated helper bookkeeping was unavailable.
3. Treated the interrupted native walkthrough as limited evidence and made no
   continuous drag FPS claim. Desktop-specific issues may remain unmeasured.
4. Retained the current model despite the candidate's selection improvement,
   because visual review found lost subject regions. This forgoes the candidate's
   improvements on some public portraits.

One minor review finding is deferred: opening the editor and beginning/ending a
stroke still copy or scan full alpha on the GUI thread. A reviewer measured
15.6–20.3 ms first samples and 45.4–64.7 ms stroke completion at 24 megapixels;
construction took 176.1 ms. Brush painting and history payloads use changed
regions, but this bookkeeping can still cause brief pauses on large images.

Detailed local evidence is under ignored `build/qt-validation/`,
`build/p3m-review/full/`, `build/p3m-review/evaluation-current/`,
`build/p3m-review/evaluation-candidate/` and `build/p3m-review/visuals/`.
