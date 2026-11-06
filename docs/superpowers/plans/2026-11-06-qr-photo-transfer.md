# QR photo transfer implementation plan

> For implementation, use Superpowers `executing-plans` or `subagent-driven-development` and follow the checkboxes in order.

## Proposed design

Add **Receive from Phone** beside the photo input actions. It opens a dialog showing a QR code, a countdown, the address as a troubleshooting aid, and **Cancel**. The phone user scans the code, chooses an image using their browser’s photo picker, and taps **Send photo**. After a successful transfer, IDFrame closes the dialog and displays the photo in **Original**, ready for the usual background removal workflow.

Use a temporary receiver on the PC running IDFrame. This gives each workstation its own receiving session and keeps the transfer independent of the OTA host. A phone and PC on a trusted local network can transfer directly. A guest network that isolates devices or a Windows Firewall rule can prevent access. The dialog will explain this in plain language. The first version uses local HTTP, so it is intended for trusted networks. The QR token grants access to one upload and provides no transport encryption.

Use one upload per QR code and a five-minute expiry. Cancel, expiry, or a successful upload closes the listener. An invalid photo lets the user retry until expiry. The receiver keeps the bytes in memory, and the ordinary **Save Photo** action controls when IDFrame writes an output. The existing photo stays visible until a valid upload is accepted.

## Implementation

### 1. Receive and validate one photo

- [ ] Add `phone_transfer.py` with a session object that binds to the selected local IPv4 address and an OS-assigned TCP port. Reuse `deployment.host_network.detect_lan_ip()` as the initial address candidate. Handle a missing or unusable address with a readable startup error. Treat manual interface selection as a follow-up if Windows chooses the wrong interface during device testing.
- [ ] Generate a fresh random URL token with `secrets.token_urlsafe(32)`. Serve the upload page at `/receive/<token>` and accept a raw file body at `POST /receive/<token>`. Keep the HTML and JavaScript self-contained. The browser sends only the chosen image on an explicit tap.
- [ ] Require a valid bounded `Content-Length`. Cap uploads at 20 MiB and images at 32 megapixels before decoding. Support JPEG, PNG and WebP, as verified by Pillow. Reject corrupt data, unsupported formats and oversized images with a retry message. Apply the same EXIF orientation and white compositing as **Open Photo** through shared `portrait.py` logic.
- [ ] Reserve the upload slot under a lock before reading. Permit one in-flight upload, impose an upload deadline, and commit only after decoding and rechecking the token, cancellation and expiry. Release the slot on a failed upload. Close sockets and worker resources on success, cancellation, expiry, or app shutdown. Suppress request logs that would expose the token. The receiver serves only the upload page and its response.
- [ ] Add `tests/test_phone_transfer.py` with loopback cases for valid upload, corrupt or oversized input followed by retry, invalid token, duplicate and concurrent uploads, expiry, a stalled upload, and cancellation while decoding. Use synthetic images and confirm that only the valid winning upload reaches the callback.

### 2. Connect the phone and desktop screens

- [ ] Add `qt_phone_transfer.py` for the QR dialog, status messages and timer. Generate the QR locally with the Python `qrcode` package. Move startup and uploads off the Qt thread and deliver the decoded image through a Qt signal. Keep the phone’s success response available before stopping the listener.
- [ ] Wire **Receive from Phone** in `app.py`. Disable it during conflicting work. Accept a result only while the matching receive dialog is active, then call `set_photo(photo, None, "Photo received from phone")` on the Qt thread. Closing the dialog or the app cancels the receiver. Keep the current photo if setup fails or the user cancels.
- [ ] Extend `tests/test_qt_app.py` to verify successful handoff to **Original**, cancellation preserving the loaded photo, and a late signal from a closed session being ignored. Check that the new action fits the existing small-window layout.

### 3. Verify the client package and real phones

- [ ] Add the QR dependency to `requirements.txt` and ensure `build_release.py` includes it in the frozen runtime. Test the packaged runtime on Windows without the development environment. Verify that the changed runtime can travel through the existing OTA path.
- [ ] Scan and upload with Android Chrome and iPhone Safari on a trusted LAN. Check an iPhone photo selected from the library and a camera photo. If the picker supplies HEIC, show a clear format message and verify the JPEG path. Check blocked-network behavior, a second scan after success, and a cancelled session followed by a fresh QR code.
- [ ] Run the focused tests and the full suite. Add the changelog and run `.venv\Scripts\python.exe build_release.py --prepare-only`. Commit and push the validated code per `AGENTS.md`. OTA publication and installer builds follow the user’s separate instructions.
