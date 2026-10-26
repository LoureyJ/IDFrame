# IDFrame

Previously named Portrait Studio. IDFrame creates white-background 2 × 2 inch
portraits at 1200 × 1200 pixels and 600 DPI, entirely on your computer.

## GitHub source and releases

Source and release notes are maintained at https://github.com/LoureyJ/IDFrame.
Completed code updates are committed and pushed there. GitHub source releases
are separate from LAN OTA: clients continue to use their configured LAN host,
and the host chooses when to publish with `update.bat`.

Personal training photos, host settings, signing keys, generated installers, and
model weights are excluded. On a new host, copy `host_settings.example.json` to
`host_settings.json`, then set the host address and version before building.
`setup.bat` downloads the base person model. The locally adapted fine-hair model
is not included in the source repository; without it, Auto uses the available
person model. See `training/README.md` for adaptation details. Private training
photos and their guidance annotations are not distributed.

Existing clients retain their installation directory, executable filenames,
protocol headers, and internal Windows identity for OTA compatibility. The app
and its installed shortcuts display IDFrame. Existing installers are preserved;
a GitHub source release does not rebuild an installer.

A local Python desktop background remover for portrait photos. Every exported PNG
has a **solid white background**, measures **1200 × 1200 pixels**, and stores **600 DPI**
print-resolution metadata for a **2 × 2 inch photo**.
Photos initially fit proportionally in the square. After removing the background,
use the Zoom slider or mouse wheel and drag the crop preview to enlarge and position
the person. Reset restores the full photo framing. Saving uses the selected crop
and the full-resolution cutout; the original photo is preserved.

## Client installers and LAN updates

See [DEPLOYMENT.md](DEPLOYMENT.md) for the Windows installer, desktop shortcut,
host server, and automatic file-level LAN updates. Clients do not need Python.
On the host, use `build_installer.bat`, `start_host.bat`, and `update.bat`.

## Windows quick start

1. Install Python 3.12 with the Python launcher and Tkinter (included in the standard Windows installer).
2. Double-click `setup.bat`. This one-time step requires internet to install dependencies
   and download the approximately 176 MB portrait model.
3. Double-click `launch.bat`.
4. Choose **Open photo**, **Remove background**, adjust the 2 × 2 crop if needed, then **Save PNG**.

You can also choose **Paste photo** or press **Ctrl+V** after copying an image
or a photo file in Windows. Pasted photos use the same white, 2 × 2 inch,
600 DPI export. The pending client version is **1.1.11**, displayed in the title
and app heading. The preserved version 1.1 installer contains the earlier
208 × 208 export; clients receive the new dimensions when you publish this update.

Choose **Changelog** beside the application heading to browse offline release notes
by version. Your installed version is selected automatically. Release notes travel
with OTA updates in `assets/changelog.json`.

When saving, enter the person's name. The app suggests a filename such as
`Juan_Dela_Cruz_2x2.png`, then lets you choose the save location. Existing files
are retained; repeat saves use `_002`, `_003`, and so on. A new photo clears the
previous person's name. Cancelling either dialog leaves the current portrait open.

The replacement camera logo is prepared in `assets/` for your next OTA publication.
It is intentionally excluded from the already built version 1.1 installer, which
retains the earlier portrait-frame icon.
The pending update also refreshes this installation's desktop, Start menu, and
existing taskbar shortcuts on first startup with the new logo. Windows taskbar
grouping retains the existing internal Windows identity for update compatibility.

The current OTA address is **http://192.168.83.169:8766**.
With `auto_detect_ip` enabled in `host_settings.json`, starting the
host or preparing a release detects the active LAN IPv4 address. The running host
checks every three seconds and synchronizes its settings and its own registered
installed app to that LAN IP. It does not switch that app to localhost. The private
`.host/host-client.json` binding identifies this PC's installed `client.json` and is
never distributed to clients. Remote client URLs do not automatically change when
the host moves to a different network.

Port 8765 belongs to
Scanning COR. Existing clients can run the new installer over version 1 to correct
their address and receive its bundled features. `update.bat` publishes application changes
and starts the background host; `stop_host.bat` stops it.

Setup has already been run if `.venv` and `models/u2net_human_seg.onnx` are present.
After setup, you can disconnect from the internet. Photo processing loads the local
ONNX model directly, without uploads, accounts, or API keys. The installed client
checks only its configured LAN update host at startup and uses its installed version
when the host is unavailable. For clients, distribute the installer described in
DEPLOYMENT.md; virtual environments themselves are not portable.

## Manual setup

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python download_model.py
.venv\Scripts\python app.py
```

Both models run on the CPU. **Auto** is the default: it compares the U2Net person
silhouette against the locally adapted MODNet matte. It prefers **Fine hair** unless
a sufficiently solid silhouette indicates missing person interiors or strong
background spill. Small, inconclusive silhouette detections are not trusted to
reject a larger matte. The selected mode appears in the status line.

Auto returns one complete candidate, without blending or reconstructing pixels.
It takes longer because it runs both models, sharing their cached sessions with
manual modes. You can still choose **Protect person** or **Fine hair** yourself.
Changing mode after processing recomputes the cutout and resets crop framing.
Auto is a mask-consistency heuristic, not a trained quality classifier; it can
choose poorly on unseen photos. If one detection fails or only one model is
available, Auto uses the available result. Neither mode guarantees perfect edges.
See [training/README.md](training/README.md) for the
curl and camo/low-quality training rounds, comparisons, and limitations. JPEG, PNG, WebP, BMP, and TIFF inputs are supported.
Processing runs in a worker so the window stays responsive. Fine hair, busy
backgrounds, and low-contrast photos can still produce imperfect edges. Use a clear,
well-lit portrait for best results. HEIC inputs must first be converted to JPEG/PNG.

At 600 DPI, 1200 × 1200 pixels prints at 2 × 2 inches (50.8 × 50.8 mm).
PNG stores resolution in pixels per meter, so inspectors may display 599.999 DPI
due to rounding.

## Client versions

Each distinct code/assets/model/dependency snapshot automatically increments the
patch version: `1.1.1` → `1.1.2` → `1.1.3`. Running the release tools again with
unchanged code keeps the current version. The client title and heading show it;
`app_version.py` travels through OTA along with the changed files.

Prepare a local version without building or publishing:

```powershell
.venv\Scripts\python build_release.py --prepare-only
```

`update.bat` and `build_installer.bat` also prepare the version automatically.
An explicit higher version in `host_settings.json` is respected; downgrades are rejected.

## Verification

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

Deployment tests additionally require `requirements-build.txt` on the host.

The suite checks white-background export, exact dimensions, DPI, proportional
fitting, EXIF orientation, and missing-model behavior. When the model is installed,
it also runs a real inference smoke test with Python network sockets blocked.
The synthetic smoke-test image checks execution, not segmentation quality.

Model: [U²-Net human segmentation](https://github.com/xuebinqin/U-2-Net),
with weights and normalization documented by
[rembg](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/u2net_human_seg.py).
The downloader checks the upstream model checksum before accepting the file.
