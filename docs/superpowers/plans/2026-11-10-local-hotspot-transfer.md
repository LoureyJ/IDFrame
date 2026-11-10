# Local hotspot photo transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically start an isolated temporary PC hotspot, transition from Wi-Fi QR to upload QR after a phone connects, and preserve the current EXE plus OTA deployment path.

**Architecture:** The EXE installer registers a signed sparse identity package against the existing install directory with the `wiFiControl` capability. The PySide6 runtime controls Windows tethering through PyWinRT on a worker thread, while the existing local HTTP upload server handles the second QR stage.

**Tech Stack:** Python 3.12, PySide6, PyWinRT, Windows tethering WinRT API, Inno Setup, sparse MSIX.

**Spec:** `docs/superpowers/specs/2026-11-10-local-hotspot-transfer-design.md`

## Global Constraints

- Preserve current install path and signed file-level OTA updater.
- Temporary hotspot uses WPA2, 2.4 GHz, and per-session random credentials.
- Never alter persistent hotspot credentials or stop a hotspot session IDFrame did not start.
- Do not publish OTA. Prepare the client version and changelog after code changes.
- Keep private signing keys outside Git and build artifacts except the signed identity package and its public certificate.
- Do not rebuild the installer unless requested; the user approved updating the installer package for this feature.

## Review Focus

- Missing package identity or untrusted signature: installer must fail clearly and not launch as if the feature works.
- Unsupported Windows/tethering/radio: present actionable error; retain existing app operation.
- Phone connects before receiver binds: show upload QR only after the receiver URL is ready.
- Cancel, upload, or failure: stop IDFrame-owned tethering and close receiver sockets.
- Repeated transfers: generate fresh credentials/token, and do not stop or replace a previously active user hotspot.

## Files

- `deployment/hotspot/`: sparse package manifest and package-logo assets.
- `deployment/installer.iss`: include identity package and public cert; register at post-install; unregister on uninstall.
- `build_release.py`: sign and stage the sparse package using private host material; never add private cert/password to client payload.
- `requirements.txt`, `build_release.py`: PyWinRT namespace/runtime dependencies and PyInstaller collection.
- `windows_hotspot.py`: start/monitor/stop one tethering session from a worker thread and report credentials/client count/errors.
- `qt_phone_transfer.py`: show first-stage Wi-Fi QR, wait for a connected phone, then show the upload QR and clean up on exit.
- `assets/changelog.json`: user-facing notes for the prepared version.
- `DEPLOYMENT.md`: one-time reinstallation requirement and later OTA workflow.

## Tasks

### 1. Verify package identity/build prerequisites

- [ ] Confirm Python 3.12 wheels exist for the required WinRT namespaces.
- [ ] Locate MakeAppx/SignTool from a standard Windows SDK installation or the ignored `.tools/windows-sdk-buildtools` cache; keep certificate creation under `.host/` and untracked.
- [ ] Define stable package name, publisher, app IDs, and install-root external location; confirm both launcher and runtime process can resolve the sparse package identity.

### 2. Add sparse identity package to the EXE installer

- [ ] Add the manifest with external content enabled and `wiFiControl` declared.
- [ ] Build and sign the sparse MSIX with MakeAppx/SignTool during installer preparation; include its public certificate only.
- [ ] Register the package after files are installed, before IDFrame can be launched; retain existing client configuration and install path.
- [ ] Unregister the package on uninstall without removing unrelated trust entries.

### 3. Add the Windows hotspot controller

- [ ] Add pinned WinRT dependencies and freeze-time collection.
- [ ] Implement one session using the current network profile, temporary random SSID/password, WPA2, and 2.4 GHz.
- [ ] Start asynchronously off the GUI thread, report actual tethering result, monitor `ClientCount`, expose hotspot IPv4, and stop only the session this instance started.
- [ ] Return readable errors for missing package identity/capability, missing profile, unsupported adapter/API, or Windows-rejected tethering.

### 4. Implement the two-stage phone flow

- [ ] Start tethering, discover hotspot IP, and bind `PhoneTransfer` before showing the join QR.
- [ ] Render a Wi-Fi QR with visible SSID/password. Poll connected-client count without blocking Qt.
- [ ] On the first connection and when upload URL is ready, replace the QR with the existing one-use photo URL QR.
- [ ] Cancel/expiry/error/success tears down the receiver and owned hotspot; preserve automatic remove-background and source-clearing behavior.

### 5. Prepare, build, and verify deliverables

- [ ] Compile/import changed modules and inspect installer/package manifest outputs without running tests.
- [ ] Run `.venv\Scripts\python.exe build_release.py --prepare-only` once after changes complete; verify app version and changelog.
- [ ] Build the new EXE installer only (no OTA publication), verify it contains the signed sparse package and registration script.
- [ ] Commit and push only task files to `https://github.com/LoureyJ/IDFrame`; preserve unrelated working-tree edits.
- [ ] Report that clients need one reinstall; future app code stays OTA-updatable.
