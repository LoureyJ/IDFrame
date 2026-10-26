# IDFrame combined light and dark interface

## Intent and selected approach

Combine Clean Light's side-by-side photo comparison with Dark Studio's grouped
editing controls. Use one layout with selectable Light and Dark themes, rather
than separate editing workflows. This is a focused interface update to the
existing desktop application.

The alternatives shown were Clean Light, Dark Studio, and Guided Workspace. The
user selected a combination of the first two, with Dark Studio available as the
dark appearance. The guided workflow is not part of this update.

## Shared layout

- Header: camera logo, IDFrame name and installed version, Light/Dark selector,
  and Changelog.
- Photo actions: Open Photo and Paste, retaining Ctrl+V.
- Workspace: Original and 2×2 Preview cards beside each other, with the output
  preview receiving slightly more space when the window allows it.
- Right editing panel: removal mode and Remove Background action, then clearly
  separated Framing and Lighting sections for Zoom, Brightness, and Reset.
- A prominent Save 2×2 Photo button at the bottom of the editing panel.
- Footer: export dimensions, processing progress, and current status.

Keep the workspace resizable. Compact spacing at smaller supported window sizes
must keep controls and the save action reachable without hiding the preview.

## Appearance and interaction

Light uses white cards, a soft gray workspace, navy text, and blue primary
actions. Dark uses charcoal surfaces, readable light text, and teal primary
actions. Both use consistent spacing, clear section headings, subtle borders,
and comfortable button and slider sizes.

Proposed defaults: start in Light mode on first use and remember the user's
selection per Windows user outside the updated application payload. Switching
appearance applies immediately without resetting the photo, selected mode, crop,
brightness, or processing progress. A missing or unreadable preference falls back
to Light without preventing startup.

Apply the palette to application-owned auxiliary windows, including Changelog
and the person-name prompt. Native Windows file dialogs retain the operating
system appearance. The separate launcher update window is outside this focused
editing-workspace redesign.

## Behavior and compatibility

Retain the existing Python/Tkinter stack and current packaged dependencies.
Build the visual refresh using reusable palette and widget styles, with small
helpers for ordinary Tk widgets such as the preview labels and canvas. Exact
rounded-corner rendering in the generated concepts is visual guidance, not a
requirement to introduce another GUI framework.

Keep all existing image processing, manual background-removal action, automatic
mode selection, clipboard input, zoom, drag positioning, brightness, safe naming,
and client updates. Theme selection changes interface colors only: saved photos
always have a solid white background at 1200×1200 pixels and 600 DPI.

No installer rebuild or OTA publication is included. After implementation and
verification, prepare the next client version, add changelog notes, and commit
and push the completed update to GitHub under the project rules.

## Verification

Check both themes for readable enabled and disabled controls, visible progress,
and usable layout at the default and minimum supported window sizes. Confirm
theme changes retain the current image and editing state, persisted selection
survives reopening, and invalid preferences do not prevent startup. Run relevant
UI/export regressions and exercise both themes in the existing frozen runtime.

## Approval status

Awaiting approval of this combined layout and the proposed theme defaults before
implementation.
