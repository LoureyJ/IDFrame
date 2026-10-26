# Host and client deployment

## Files to use

| File | Use |
| --- | --- |
| `dist/installer/PortraitStudio-Setup-1.1.0.exe` | Current built installer baseline; newer prepared changes arrive when you publish OTA. |
| `start_host.bat` | Start your host's background OTA server. |
| `stop_host.bat` | Stop this project's background OTA server. |
| `update.bat` | Run on the host after editing application code. |
| `build_installer.bat` | Build a fresh installer for new clients. |
| `host_settings.json` | Host IP, port, and displayed application version. |
| `allow_host_firewall.bat` | Run as Administrator once on the host to allow LAN connections. |

The current host URL is **http://192.168.83.169:8766**. Port 8765 is used by
Scanning COR on this PC and must remain separate.
Reserve this IP for your PC in the router/DHCP settings. Host and clients must be
able to reach each other over the LAN; internet is not required during use.
When `auto_detect_ip` is enabled, the host detects its active LAN IPv4 on startup
and before preparing a release, then checks for changes every three seconds while
running. Its settings and this PC's registered installed client follow that LAN IP.
The registration lives in `.host/host-client.json` and is never shipped to clients.
Remote PCs must still use a reachable current host address; they are not rewritten
to their own IPs. A DHCP reservation remains useful for keeping their address stable.
The firewall helper permits the configured port from the local subnet across local
addresses, so a newly created rule does not become stale after an IP change.
The host server is a separate read-only Python process. `start_host.bat` runs it
in the background; closing the batch window leaves it running. `update.bat` also
starts it after publication and detects port conflicts. Run `start_host.bat` again
after rebooting the host PC. Clients retain their installed version when the host
is stopped. Publishing does not require restarting a running host server.

## First deployment

1. On the host, open `host_settings.json` and confirm the IP and port.
2. Give clients **PortraitStudio-Setup-1.1.0.exe**. It includes paste support,
   600 DPI export, the custom icon, and the correct default host address.
   Existing version 1 clients can run it over their current installation; it
   replaces the old configuration without needing any separate client scripts.
   Building a future installer requires Python 3.12, dependencies in
   `requirements-build.txt`, and the Inno Setup compiler. A compiler is currently
   installed in `.tools/inno`; it is a build tool, not part of the client install.
3. Right-click `allow_host_firewall.bat` and select **Run as administrator**.
   Its inbound TCP rule permits the configured host IP/port from the local subnet.
   This rule works with both Public and Private Windows network profiles.
4. Double-click `start_host.bat`. From another LAN computer,
   open `http://192.168.83.169:8766/health` to confirm connectivity.
5. Copy the installer EXE to each client and run it. The installer asks for the host
   URL and creates an **IDFrame** shortcut on that user's desktop and Start menu.
6. Clients open that shortcut. They do not need Python, pip, or internet access.

Building an installer stages a signed release separately and does not publish to
the live OTA channel. Run `update.bat` yourself when ready to publish the matching
release to the host. Until then, the new installer runs its bundled application.

Installation is per Windows user under `%LOCALAPPDATA%\Programs\Portrait Studio`.
The legacy directory name is retained for update compatibility. From v1.1.12,
the application displays IDFrame and renames its owned shortcuts when the new
name is unused. Future installer builds use IDFrame branding. Existing installer
files are preserved. GitHub source releases do not publish the LAN OTA repository.
It does not require administrator privileges; updates can write to that same folder.
The bundled model is included, so the initial installation works offline too.
The installer is for 64-bit Windows 10/11. It is not Authenticode-signed; signing
Windows installers for your organization requires your own code-signing certificate.

## Publishing code changes

1. Edit `app.py`, `portrait.py`, other application Python modules in the project
   root, or files in `assets/`.
2. Versions increment automatically for changed code, assets, models, or dependencies:
   `1.1.1` → `1.1.2` → `1.1.3`. Repeated builds of unchanged code reuse the version.
   You may set an explicit higher version in `host_settings.json` for a major/minor release.
3. Double-click `update.bat` on the host. Wait for **Update published**.
4. Clients receive the update the next time they open the desktop shortcut.
   An app that is already running continues its current session.

The application title and heading display the installed client version. The generated
`app_version.py` file is updated and delivered with each release. For local code changes,
`build_release.py --prepare-only` reserves the new version without building an installer
or touching the live OTA manifest. Current source prepares v1.1.11 with person-based automatic filenames, automatic host IP synchronization, automatic selection between Protect person / Fine hair modes, zoomable 2 × 2 crop framing, the versioned changelog, camo/low-quality
adapted matting model, centered update dialog, and the 2 × 2 inch,
1200 × 1200 pixel export at 600 DPI; the preserved v1.1 installer has the earlier 208 × 208 export.

The update launcher shows a centered **Checking Updates** dialog with the camera logo
and a progress bar underneath. Checking uses an animated bar; downloads report byte
progress. Launcher and child processes use Windows GUI mode without a console.

Existing clients first receive `payload/PortraitLauncher.exe` as a normal signed OTA
file. When they close that updated app, a hidden helper verifies the candidate against
their signed installed manifest, waits for the previous session lock, and atomically
replaces `PortraitStudio.exe`. The centered dialog appears on the **next opening**.
The first opening that downloads this change still uses the previous launcher's dialog.
No new installer is needed for that migration. If replacement is temporarily blocked,
the existing launcher is retained and the next session close retries it.

`update.bat` syntax-checks root application modules and publishes a new signed file
manifest. It reuses the built runtime unless the runtime entry point or installed
dependency versions changed. Each client compares SHA-256 hashes of its actual
files against the host manifest. It downloads and replaces only changed or missing
files. Unchanged files retain their contents and timestamps. In particular, normal
source changes do not transfer the approximately 176 MB AI model again.

New files are added. Files removed from the previous managed release are removed
from the client; files the updater does not manage are preserved. `client.json`,
logs, and saved portraits are outside the published payload and are retained.

For third-party dependency changes, install the new dependencies into `.venv`
first, then run `update.bat`. The runtime rebuilds automatically when installed
package versions change. Files in the rebuilt runtime are still compared individually;
only files with changed hashes are transferred. A changed executable or archive is
transferred as a whole file, rather than as a byte-level patch.

The small launcher/updater itself is the stable installation component. Changes to
`deployment/launcher.py`, `deployment/updater.py`, the update protocol, signing trust,
or installer settings require rebuilding and distributing the installer. Application
source, model, assets, and the application runtime use LAN updates.

## Client startup and recovery

Startup checks the configured host with a 3-second connection timeout. Downloads
have a 30-second socket timeout and a 3-minute update budget. When the host cannot
be reached or an update cannot be verified, the installed app opens. Photos are
processed locally and are never sent to the host.

Clients verify the release signature using the host's public key embedded in the
launcher, then verify downloaded file sizes and hashes. Files are fully staged
before installation. A journal and backups restore the prior release if replacement
fails or the client closes unexpectedly. If recovery itself fails, the launcher
stops and asks for a reinstall instead of running a partial release. One launcher
instance runs per installation, and it holds the lock until the app closes.

Client logs: `%LOCALAPPDATA%\Programs\Portrait Studio\update.log`.
The client log rotates at 1 MB. Background host access logs are in `.host/server.log`.

## Changing the host address

Stop the background host with `stop_host.bat`, edit `host_settings.json`, then run
`start_host.bat`. If the IP/port changed, rerun the host firewall script.
Clients can run the current installer to receive the corrected default address.
For a custom host address, enter it in the installer or edit `client.json`:

```json
{"host_url":"http://192.168.83.169:8766"}
```

The installer also accepts `/HOSTURL=http://192.168.83.169:8766` for unattended
deployment. Example:

```powershell
.\PortraitStudio-Setup-1.1.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /HOSTURL=http://192.168.83.169:8766
```

## Host backup

Keep a private backup of **`.host/signing-key.pem`**, plus the project and
`host_settings.json`. Keep the key on the host; never give it to clients. The
installer includes the public key only. If you move the host to a different PC,
restore the same key before publishing, then update client addresses if needed.
Losing the key requires installing a new trusted launcher on every client.

The server serves only `.host/repository/manifest.json`, content-addressed blobs,
and `/health`. It exposes no write/publish endpoint or filesystem directory listing.
Old blobs are retained so a publication cannot break an update already downloading.
Repository disk usage therefore grows with distinct published file contents.

## Verification

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

Tests cover file-level updates, unchanged-file timestamps, signature rejection,
corrupt downloads, rollback, crash recovery, managed file deletions, retained client
data, replay rejection, path validation, and model/export behavior. A local test
server checks actual HTTP requests to ensure unchanged files are not downloaded.
LAN reachability from another physical PC must still be checked in your environment.

The built installer was also tested by `tests/deployment_smoke.py`: it installed
into a temporary client folder, created the desktop shortcut, ran the frozen app,
received exactly one changed `app.py` over HTTP, retained the model timestamp,
and produced the expected image after the host went offline. It then uninstalled
the test client. Results are recorded in `build/deployment-smoke-report.json`.
