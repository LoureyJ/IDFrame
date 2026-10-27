# PySide6 Editor and P3M Training Implementation Plan

**Execution:** Source prepared as v1.1.16; model candidate trained/evaluated but rejected for activation. [Evidence and limits](2026-10-27-pyside6-validation.md). No installer or live OTA publication.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate IDFrame's editing application to responsive PySide6, add mask cleanup, and train/evaluate a separate MODNet candidate using P3M-10k without collecting client photos.

**Architecture:** Keep portrait.py's model and export contract independent of Qt. A Qt main window coordinates bounded background jobs, cached previews, and a separate editor backed by a framework-independent alpha document. Training data and checkpoints remain local and excluded from Git; promote a model only after held-out evaluation and visual review.

**Tech Stack:** Python 3.12, PySide6 Qt Widgets, Pillow, NumPy, ONNX Runtime, CPU PyTorch, existing PyInstaller/Inno deployment.

**Spec:** ../specs/2026-10-27-pyside6-editor-design.md (approved by user); P3M-10k training separately authorized on 2026-10-27.

## Global Constraints

- White RGB PNG, 1200x1200, 600 DPI; immutable original photo and safe naming.
- Preserve models, Auto/Protect person/Fine hair, clipboard, crop, brightness, theme preferences, changelog, visible version, icons, LAN trust and rollback.
- No client-photo submissions. No installer build, live OTA publication, or GitHub release without explicit request.
- Keep old release/installers and active ONNX model until replacements pass validation.
- Prepare one new client version only after final distributable changes; maintain its changelog; push validated source, excluding data/secrets/builds.
- Training is a candidate experiment, not an accuracy claim. Record data origin, split, hashes, hyperparameters, checkpoint, losses, validation metrics, and hardware.

## Review Focus

- Closing/replacing a document while a worker is active must not crash or apply stale pixels (Task 2).
- Resize/theme actions on a large photo must not repeatedly resample the full source or grow queued jobs (Task 2).
- Erasing after zoom/pan must affect the matching source pixels and preserve unrelated partial alpha (Task 1).
- Cancel/X and reprocessing must have predictable edit ownership; saved output must match applied edits (Task 3).
- An old frozen runtime cannot import Qt until its dependency payload arrives; preserve safe upgrade/offline paths (Task 4).

### Task 1: Alpha editing document and history

**Files:** Create mask_document.py; create tests/test_mask_document.py.

**Interfaces:** MaskDocument(cutout: PIL.Image, history_limit_bytes=67108864); image() -> PIL.Image; begin_stroke(); erase_segment(start, end, diameter); end_stroke(); undo(); redo(); can_undo/can_redo. Coordinates and diameter are source pixels. History stores changed-region before/after alpha patches; one operation per stroke.

- [x] Add failing tests for continuous erase, zero-length click, bounds clipping, antialiased brush edge, original RGB/alpha immutability, exact undo/redo, redo invalidation, and bounded history.
- [x] Run `.venv\Scripts\python.exe -m unittest discover -s tests -p test_mask_document.py`; confirm missing-module failure.
- [x] Implement the document and per-stroke patch history; retain original RGBA copy, edit alpha only, validate finite positive inputs and safe bounds.
- [x] Run the focused tests; all pass. Commit the independently testable document.

### Task 2: Qt main window, jobs, themes, and cached framing

**Files:** Modify app.py; create qt_jobs.py, qt_theme.py, qt_preview.py, qt_dialogs.py; modify requirements.txt; create tests/test_qt_app.py, tests/test_qt_preview.py.

**Interfaces:** PortraitApp(QMainWindow); run() -> int application entry point; PhotoJob signals deliver result/error with document generation; PreviewWidget.set_image(cutout), export() -> PIL.Image; framing state zoom/offset/brightness remains equivalent to frame_portrait. qt_theme loads/saves existing JSON preferences without importing Tk styling. Dialog helpers replace Tk naming/changelog/clipboard surfaces.

- [x] Pin a compatible PySide6 distribution after checking Python/Windows support and licenses; install development dependency in the app venv. Record version and supported client platform.
- [x] Write failing Qt integration tests for open/set source, clipboard paste, removal/busy recovery, theme persistence with retained crop state, safe naming, stale job rejection, safe close, and responsive layout.
- [x] Run the selected tests; confirm expected missing Qt integration failures.
- [x] Implement Qt Widgets layout matching the accepted design. Keep existing main UI as Git history, not as a second active UI. Separate preview painting from model operations; QPixmap/widget operations only on GUI thread.
- [x] Use source thumbnails/cached display data for painting, bounded background render jobs, latest-request generation rejection, and no full-source resampling per resize. Process AI on a dedicated serialized worker. Avoid blocking waits in GUI callbacks.
- [x] Provide full-resolution final export in a worker, preserving exclusive save behavior, naming prompt, source overwrite prevention, and white background. Respect image orientation and clipboard formats.
- [x] Run Qt tests with offscreen platform for correctness, then visible Windows profiling for repeated resize/theme/crop behavior. Record timings/job counts. Commit only after focused checks pass.

### Task 3: Separate cleanup editor and integration

**Files:** Create qt_editor.py, tests/test_qt_editor.py; modify app.py and qt_preview.py.

**Interfaces:** CleanupEditor(cutout, theme, parent) wraps an independent MaskDocument; accepted image returned on Apply; Cancel/X returns no changes. View transform supplies source coordinates to mask_document.

- [x] Write failing tests for inverse zoom/pan mapping, brush sizing/click-drag continuity, undo/redo buttons/shortcuts, Apply preserving crop/brightness, and Cancel/X preserving prior applied result.
- [x] Run editor tests and observe expected missing implementation failures.
- [x] Build resizable editor with white workspace, circular eraser cursor, wheel zoom, distinct pan gesture, brush size, Undo/Redo, Fit, Apply/Cancel. Apply ends any active stroke; one editor owns the current document.
- [x] Integrate Edit availability and document replacement. Reset Adjustments does not discard applied erasures. Reopening starts from applied alpha with fresh session history.
- [x] Run focused tests and verify saved export includes applied mask. Visually inspect alignment at several view scales. Commit.

### Task 4: Frozen runtime and backward-compatible distribution

**Files:** Modify build_release.py, deployment/runtime.py, deployment smoke/integration tests, requirements-build.txt only if needed; document deployment behavior.

**Interfaces:** Retain PortraitRuntime.exe, PortraitStudio.exe, payload layout and signed update protocol. Smoke test starts a Qt main window and reports correct version plus unchanged export contract.

- [x] Add a failing assertion/check for required Qt imports and platform plugin in frozen payload/startup; adapt main-window Tk tests to their Qt equivalents, retaining launcher tests.
- [x] Extend PyInstaller hidden imports/hooks/collections for external Qt source modules, ONNX/Pillow, and Qt Widgets platform dependencies. Include relevant license notices; exclude unused web/Qt modules when safe.
- [x] Build an isolated runtime (not an installer or live publication). Exercise Qt startup and local inference in an environment where global PySide6 is unavailable.
- [x] Test existing launcher installing a complete signed new payload through an isolated server; verify offline fallback, recovery and source version visibility. If incompatible, report need for a new installer and do not publish broken OTA.
- [x] Run focused deployment suite; commit tested runtime changes.

### Task 5: Public P3M data and supervised MODNet training

**Files:** Create training/p3m_dataset.py, training/train_p3m.py, training/test_p3m.py; modify training/requirements.txt, training/README.md and .gitignore for local data if needed. Store downloaded data under ignored build/datasets/p3m10k and candidates under build/p3m-review.

**Interfaces:** P3MDataset provides matched RGB tensors and continuous alpha tensors with synchronized transforms and explicit split. train_p3m CLI takes data/checkpoint/output, epochs, max side, seed, learning rate, device, and resume; resume retains optimizer, epoch, step and RNG state. Evaluator compares frozen baseline and candidate on untouched held-out examples at the same inference geometry.

- [x] Retrieve official release and agreement, preserving provenance. Official Google Drive currently returns a quota error; inspect a publicly available P3M mirror if necessary and record that origin explicitly. Verify checksums where published, pairing, alpha ranges, split counts, duplicates and available disk before extraction.
- [x] Add failing fixture tests for split isolation, image/matte pairing, continuous alpha (not thresholded), synchronized resize/flip, malformed data rejection, reproducible training, and checkpoint/resume metadata.
- [x] Implement dataset adapter for the acquired layout. Do not substitute SOC-only training on unlabeled images for supervised training on the provided mattes.
- [x] Fine-tune MODNet from an existing accepted checkpoint using supervised semantic/detail/matte losses with appropriate branch target geometry and alpha/composition objectives. Use bounded CPU threads; keep pretrained normalization handling explicit. Add controlled blur/JPEG/lighting augmentation with unchanged alpha alignment.
- [x] Run fixture tests, then a short smoke training run to measure seconds/step and numerical stability. Estimate full training duration and storage from actual measurements; state any practical constraints before an expensive full run.
- [x] Train on the training split only, using a held-out portion for model selection and untouched official evaluation sets for final reporting. Save resumable checkpoints and periodic reports. Never describe a subset or incomplete run as full-dataset training.
- [x] Compare baseline/candidate alpha MAE/MSE, foreground-interior loss and boundary errors; review paired images including existing difficult examples. Record failures and avoid unsupported accuracy claims.
- [x] Export best eligible candidate with existing ONNX contract; compare PyTorch/ONNX numerics and actual client output. Activate only if held-out evidence and visual review justify it; otherwise retain current model and report experiment outcome.

### Task 6: Final verification, version, and source delivery

**Files:** Update assets/changelog.json, app_version.py through preparation tool, README.md and plan/ledger evidence.

- [x] Run all applicable unit/integration tests, Black, Ruff, function-purpose checks and frozen runtime smoke. Request one fresh whole-change review and address important findings with regression tests.
- [ ] Perform visible Windows walkthrough: normal/maximized/small screens, repeated themes/resizes, open/paste, all removal modes, editor Apply/Cancel/Undo/Redo, framing/brightness, naming collisions and final export. **Partially verified; remaining native walkthrough deferred after physical Escape stopped desktop interaction. See validation record.**
- [x] Add user-facing changelog notes for the final prepared version; run `.venv\Scripts\python.exe build_release.py --prepare-only` once distributable changes are complete. Confirm rerunning unchanged code would retain version through the existing versioning tests.
- [x] Commit/push validated source and documentation; exclude dataset, photos, models/checkpoints, credentials and generated outputs. Leave installers/live OTA unchanged.
- [x] Report shipped source behavior, exact validation evidence, training dataset/run extent, model activation decision, deployment compatibility, and any required next action. Do not claim training or migration completion before the evidence exists.
