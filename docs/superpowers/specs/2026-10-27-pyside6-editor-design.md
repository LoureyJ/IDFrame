# IDFrame PySide6 migration and portrait cleanup editor

Status: approved on 2026-10-27; implemented and prepared as v1.1.16. See the validation record for evidence and remaining native walkthrough limits.

## Intent and agreed scope

Replace the main Tkinter application with PySide6 (Qt 6), selected by the user,
while retaining offline AI removal and the existing photo export contract. The
user reports frozen frames during repeated actions, live resizing, maximize /
restore, and appearance switching. Provide a separate Edit window for erasing
remaining background artifacts, brush size adjustment, Undo, and Redo.

Keep the accepted IDFrame light/dark visual direction: camera branding, rounded
controls, original and result previews, visible removal-mode radio buttons, and
right-side controls with a prominent Save action. This is a framework migration,
not a new visual design.

Client-photo collection is excluded from this implementation. Automatic training
submissions require a disclosed opt-in and a separately agreed submission design.
The user has requested undisclosed collection; that request cannot be implemented.
No photos will be transmitted by this migration or editor.

## Approaches and selection

1. Optimize Tkinter: least deployment change; retain native Windows/Tk interaction
   limitations and existing redraw architecture. Originally recommended before the
   user chose a framework migration.
2. PySide6 with Qt Widgets: user-selected approach. Native desktop layout and input,
   cached image painting, worker-to-GUI signals, and no web engine. Adds Qt runtime
   libraries to the deployable payload.
3. PyQt6: same underlying Qt generation, different bindings. User explicitly chose
   PySide6 instead.

For editing, a separate window was selected over inline editing to avoid competing
with the existing main-preview drag-to-position gesture.

## Evidence and limits of diagnosis

The existing original-preview Configure handler resamples the full original photo
on every event, on the GUI thread. A synthetic 4000x6000 RGB image took a median
80.6 ms and maximum 103.1 ms for each show_image call in this environment (12 runs).
That is incompatible with fluid repeated resizing. This measured bottleneck must
be removed, not merely ported to Qt.

The existing theme callback measured median 14.7 ms and maximum 29.95 ms (12 runs,
withdrawn window). This does not reproduce the user's prolonged theme freeze or
native interactive resize behavior; visible-window repeated-action profiling is
still required. Framework choice alone is not a performance guarantee.

## Architecture

- Keep portrait.py as the framework-independent AI/compositing/export layer.
- Qt QApplication and a QMainWindow replace Tk in the application entry point.
  Use Qt widgets/dialogs for main-window photo input, clipboard, naming prompt,
  changelog, errors, progress, and settings interactions.
- Separate the Qt main window, preview/editor widgets, image document/history,
  theme support, and background jobs into purpose-specific modules. The builder
  chooses names and exact file boundaries; avoid mixing pixel mutation with UI.
- Preserve root-level module assembly, or explicitly extend packaging if modules
  become a package. Do not leave required files out of the frozen payload.
- Retain existing ONNX model choices, Auto selection, lazy sessions, and CPU
  inference. Serialize inference jobs so shared sessions/state cannot race.
- Workers handle expensive photo loading, inference, preview preparation, and
  export/file writes. GUI objects and pixmap presentation stay on the GUI thread.
  Carry document/request generations with results and discard superseded jobs.
- Keep bounded cached display images. Resize paints transform cached image data;
  it must not resample the full original on each event. Combine rapid adjustment
  requests and process the latest state without building an unbounded job queue.
- Theme changes update palette/style resources without rebuilding widgets, rerunning
  inference, or resetting the current document. Reuse cached light/dark resources.
- Workers never directly access widgets. Close waits or defers safely for active
  jobs; never forcibly terminates a thread or lets a stale callback touch a closed
  window.

## Main window behavior

- Start near the existing 1240x780 size, bounded by the screen's available geometry.
  Support minimize, maximize, restore, and live resize; use Qt layout stretch and
  scrolling for small available heights rather than hiding actions.
- Keep all current features: Open, clipboard paste/Ctrl+V, Auto/Protect person/Fine
  hair, progress/errors, changelog, version, icons, theme persistence, framing zoom
  1x-8x, pan, neutral brightness at 100%, and Reset Adjustments.
- Preserve preferences.json location and Light/Dark values. Theme and layout
  changes preserve the source, cutout, crop position, zoom, brightness, and edits.
- Source files remain untouched. Safe PersonName_2x2.png naming and numbered collision
  handling remain. Export is white RGB PNG, 1200x1200, 600 DPI.
- Edit is enabled after a successful removal result and disabled during replacement
  inference. One editor per document. Opening a different photo or rerunning removal
  clears its old edit history through the normal document replacement path.

## Separate Edit window

- A resizable, theme-matched Qt dialog/window with a large portrait workspace and
  controls for Eraser size, Undo, Redo, Fit, Apply, and Cancel. The main window is
  blocked from document-changing actions while this editor is open.
- Show the full cutout on white without baking the main 2x2 crop into its pixels.
  Mouse wheel zoom and a distinct pan gesture allow precise cleanup. A round cursor
  indicates brush diameter; diameter is defined in original-image pixels, with the
  displayed circle following view scale. The builder chooses practical slider
  limits and initial zoom, clamped safely for the image dimensions.
- Store an editable alpha mask separately from immutable source RGB. An eraser
  stroke reduces opacity to zero with a smooth antialiased edge; it never paints
  white into the source. Interpolate pointer samples to prevent gaps during drags.
- Map strokes through the inverse view transform into original-image coordinates.
  Clamp to image bounds and retain partial alpha outside the affected brush area.
- One Undo step per completed stroke, not per pointer event. Undo restores exactly
  the previous alpha; Redo reapplies exactly the stroke. A new stroke after Undo
  clears Redo. Use changed-region patches with a documented memory budget; drop
  oldest undo entries if necessary rather than copying whole photos indefinitely.
- Apply commits the working alpha and refreshes the main preview while retaining
  existing crop/brightness. Cancel and closing via X discard this editor session's
  edits. Reopening begins from the latest applied mask with a fresh session history.
- Reset Adjustments resets crop/lighting only; it does not silently discard applied
  eraser corrections. Rerunning AI removal creates a new result instead.
- No restore brush in the first version: Undo restores eraser mistakes within the
  open editor. No model retraining occurs during editing.

## Deployment and compatibility

- Retain the stable launcher executable/path, desktop/taskbar identity, installation
  folder, client host configuration, trust keys, signing, rollback, and LAN checks.
- The stable updater dialog may remain Tkinter in this stage; it runs in its own
  launcher process and must work before the application runtime starts. The main
  application and its editing dialogs use Qt exclusively.
- Update frozen runtime collection to include required PySide6 modules, Qt DLLs,
  Windows platform plugin, and applicable license notices. Keep AI dependencies.
  Replace the Tk-specific application smoke test with Qt startup coverage.
- A source-only update cannot provide Qt to old clients. A rebuilt full runtime
  payload is required. Existing OTA assembly already includes runtime files, so a
  signed full-payload migration may work; it must be tested with the existing frozen
  launcher before claiming compatibility. A new installer is the alternative.
- Do not overwrite or remove the existing installers, live OTA repository, private
  configuration, photos, or model checkpoints. Keep current distribution usable
  while developing. Isolated frozen runtime tests are allowed; creating an installer
  or publishing OTA/GitHub releases requires the user's explicit request.
- After implementation and validation, add user-facing changelog notes and run
  build_release.py --prepare-only once. Let the tool assign the next version; do
  not promise a particular patch number before inspecting final state. Commit/push
  validated source as required by AGENTS.md, excluding private files and builds.
- Preserve the existing release as rollback material. Trial migration uses an
  isolated repository/install and never alters the host's live OTA manifest.

## Acceptance evidence

- Unit tests for source immutability, erase coordinate transforms, continuous
  strokes, patch-based undo/redo, redo invalidation, Apply/Cancel, and crop/export
  invariants including white corners and 600 DPI metadata.
- Qt integration checks for every existing main-window action, appearance
  persistence/state preservation, correct busy controls, stale-job rejection, and
  safe worker shutdown. Migrate Tk main-window tests to equivalent Qt checks;
  retain tests for the separate launcher and framework-independent processing.
- Repeated resize/maximize/restore and at least 50 theme/adjustment changes using
  representative large photos. Record callback timings, job/cache counts and memory
  stability; no inference on resize/theme and no continuously growing queue/history.
- Target normal GUI callbacks below one 16 ms frame budget where practical, and
  visibly responsive continuous resize/theme interactions on the development PC.
  Treat long stalls or growing memory as unresolved failures; do not claim a fixed
  frame rate on client hardware from automated geometry changes alone.
- Visually inspect Light/Dark, normal/maximized/small windows, brush alignment at
  multiple view scales, undo/redo, and main/export agreement on a real Windows UI.
- Frozen runtime launches with local models and no globally installed PySide6.
  Exercise an isolated old-client-to-new-full-payload upgrade, rejection/rollback
  behavior where relevant, and offline startup. Report whether old-client OTA is
  verified or requires a new installer; do not silently publish an incompatible OTA.

## Documentation references

- Qt Widgets image view and transformations:
  https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html
- Qt thread ownership and queued delivery:
  https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html
- Qt for Python deployment:
  https://doc.qt.io/qtforpython-6/deployment/index.html

## Builder discretion

Choose pinned compatible PySide6 dependencies, exact Qt layouts, cache sizes,
history memory limit, job implementation, and test fixtures. Prefer Qt Widgets and
existing Python image logic over QML, a web engine, custom GPU infrastructure, or
new services. Document choices that affect supported client Windows versions.
