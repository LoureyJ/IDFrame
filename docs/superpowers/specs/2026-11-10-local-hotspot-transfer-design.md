# Local hotspot photo transfer design

## Intent

Let an office client send a photo to IDFrame without joining the office LAN or using Internet access. In Receive from Phone, IDFrame starts this PC's Wi-Fi hotspot, displays a Wi-Fi join QR, waits for a connected phone, then replaces it with a one-use upload QR. The received image continues through the existing automatic background-removal/save flow; the source photo is cleared from IDFrame after the processed result is saved.

## Goals and constraints

- Preserve the existing EXE installer, installation path, desktop shortcut, and signed file-level OTA updater.
- Add a sparse MSIX identity package declaring Windows `wiFiControl`, registered by the EXE installer against the existing installation folder.
- Use a temporary WPA2 2.4 GHz hotspot network name and password for each transfer, without overwriting the user's saved Mobile Hotspot settings.
- Internet access is not needed for the phone transfer. Windows still needs a usable connection profile and a Wi-Fi adapter capable of tethering; show a clear error if Windows or the adapter rejects startup.
- Start the phone upload receiver on the hotspot interface before showing the Wi-Fi QR. Transition to the upload QR only after Windows reports a connected client.
- Stop only the hotspot session IDFrame started, on cancel, upload completion, or failure. Never stop an existing user hotspot session owned by Windows.
- Do not publish an OTA release. The host controls publication.

## Approaches considered

1. Keep manual hotspot activation — no installer change, but does not satisfy automatic startup.
2. Replace the installer with a full MSIX — package identity is native, but abandons the existing EXE installer and file-level deployment model.
3. Add a sparse identity package to the existing EXE installer — gives the app the required capability while preserving its install path and OTA model. **Selected by the user.**

## Implementation outline

Add a small signed sparse package with package identity, an external-content declaration, and `wiFiControl`; register it from the installer at the install root. For the in-house self-signed package, request UAC elevation only to add its public certificate to the machine's `TrustedPeople` store, while keeping the app and sparse package registration per-user. Keep signing material private on the host and include only the public certificate needed for client trust. Add a Windows hotspot controller around WinRT tethering, executed off the Qt UI thread. Update the receive dialog to manage the two QR stages and clean up its owned hotspot session on every exit path. Keep the existing local HTTP token upload and photo processing behavior.

## Limitations

Clients must install the new installer once to register the identity package. Subsequent application changes can still arrive by OTA. Windows tethering capability, an available connection profile, radio/driver support, and local firewall behavior vary by PC; the dialog must report startup failures rather than claim the hotspot is active.
