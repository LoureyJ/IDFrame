# Light and Dark IDFrame UI Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this approved design inline, task by task. Steps use checkbox syntax for tracking.

**Goal:** Combine the two approved mockups into one workspace with remembered Light/Dark appearance.

**Architecture:** A dependency-free theme module owns palettes, preferences, ttk styles, and ordinary Tk widget colors. The existing controller retains image and worker state while its layout becomes a header, two preview cards, right inspector, and footer. Crop controls can live outside their preview without changing rendering.

**Tech Stack:** Python 3.12, Tkinter/ttk, Pillow; existing runtime and models.

**Spec:** `docs/superpowers/specs/2026-10-26-light-dark-ui-design.md`

## Global Constraints

- Theme affects interface colors only; exports remain white RGB, 1200×1200, 600 DPI.
- Preserve current actions, worker behavior, clipboard, cropping, brightness, naming, and OTA compatibility.
- Keep preferences outside the updated payload; Light is the first-use and error fallback.
- Add a purpose docstring to each maintained function.
- Prepare the next client version once after final code changes; do not build installers or publish OTA.
- Commit and push completed work as previously authorized.

## Review Focus

- Corrupt or inaccessible preferences must not prevent startup or theme changes.
- Theme changes during processing must not enable photo actions or discard a result.
- Dark mode must style plain Tk widgets and existing auxiliary windows as well as ttk widgets.
- Minimum-size layout must keep the save action reachable and both previews visible.
- Preview/export image bytes and native file dialogs must not be recolored by the theme.

## Task 1: Theme foundation

**Files:** Create `ui_theme.py`, `tests/test_ui_theme.py`.

**Interfaces:** `load_theme(path=None) -> str`, `save_theme(name, path=None) -> bool`, `apply_theme(root, name) -> None`; themes are `Light` and `Dark`.

- [ ] Write tests for missing/corrupt/non-object settings, persistence, write failures, and real Tk palette changes.
- [ ] Run the new tests and observe missing-feature failures.
- [ ] Implement palette/style configuration, safe per-user preference writes, and recursive plain-widget styling.
- [ ] Run the new tests until green.

## Task 2: Combined workspace and auxiliary windows

**Files:** Modify `app.py`, `portrait_crop.py`, `changelog.py`, `photo_naming.py`; extend `tests/test_ui_theme.py`.

**Interfaces:** `PortraitApp(root, *, preferences_path=None)` for isolated preference storage; `change_theme(event=None)` switches appearance without rebuilding widgets. `CropPreview(parent, controls_parent=None)` retains its existing API and optionally places controls in the inspector.

- [ ] Write failing tests for persisted theme, retained crop/brightness/photo state, busy controls, styled changelog/name prompt, and usable default/minimum geometry.
- [ ] Build the shared header, photo actions, preview cards, inspector, and footer, preserving callback and widget attribute names.
- [ ] Wire immediate theme selection and preference persistence. Apply theme colors to auxiliary windows and crop redraw decorations.
- [ ] Run UI tests and the full application regression suite.

## Task 3: Delivery proof

**Files:** Update `assets/changelog.json`, README/deployment notes, this plan, and the generated client version.

- [ ] Check both themes in the existing frozen runtime, including saved white-background output and preference reload.
- [ ] Run Black, Ruff, function-documentation checks, and relevant tests. Review the complete diff against the design.
- [ ] Run `build_release.py --prepare-only` once after changes, confirming published OTA and installer hashes do not change.
- [ ] Commit and push the completed update; report verification and pending OTA publication.

## Execution record

Design approved by the user. Execute inline under the existing authorization to implement and push updates.
Ruling: retain the existing checkout and host/model/runtime bindings while editing on a feature branch; an additional checkout would need private host provisioning unrelated to the approved UI update.
Ruling: native Windows file dialogs and the separate update launcher retain their own appearance as specified.

Task 1: complete. Missing/corrupt/unwritable preference cases and persisted choices are covered.
Task 2: complete. The user's visual correction requires visible radio choices and rounded controls; native ttk image elements use the existing Pillow runtime. The default layout shows all adjustments; the minimum layout scrolls overflow while keeping Save and status available. Keyboard focus reveals hidden controls and has visible focus styling.
Review: an independent reviewer identified footer clipping, stale Tcl dropdown colors, inherited light state colors, invisible keyboard focus, and hidden focused controls. These were addressed with layout, palette, and focus tests. A reported intermittent Tcl teardown warning was not reproduced in three fresh subprocess UI-suite runs, all of which exited 0; no speculative lifecycle change was made.
Task 3: delivery verification complete. The full suite passed 79 tests; Black, Ruff, and function documentation checks passed. Existing frozen-runtime checks passed for both themes, radio selection, preference reload, preserved editing state, and white 1200×1200/600-DPI export. Client v1.1.15 was prepared once after the final code changes. Published OTA and installer hashes remained unchanged. Commit and push are the final delivery step; publication remains excluded.
