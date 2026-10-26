# Working on IDFrame

## Code map

| File or folder | Purpose |
| --- | --- |
| `app.py` | Tk interface, photo state, worker coordination, and save actions. |
| `portrait.py` | CPU model sessions, model preprocessing, automatic selection, and white-background export. |
| `portrait_crop.py` | Interactive crop preview using the same geometry as saved photos. |
| `photo_clipboard.py`, `photo_naming.py` | Clipboard input and safe person-based filenames. |
| `changelog.py`, `windows_branding.py` | Offline release notes and installed Windows shortcuts. |
| `deployment/` | Signed LAN manifests, verified updates, recovery, host management, and client startup. |
| `build_release.py` | Runtime caching, payload assembly, version preparation, and explicit publication. |
| `training/` | Optional model adaptation, checkpoint export, and visual review tools. |
| `tests/` | Isolated image, UI, update, host, and versioning regression checks. |

## Readability conventions

Give every project-owned function a purpose docstring, including nested callbacks
and test helpers. Explain invariants and non-obvious decisions with nearby comments.
Keep UI changes on the Tk thread; inference and downloads run in workers. Preserve
public callback names and deployment filenames used by existing installed clients.

Use Black for consistent formatting and Ruff for syntax and unused-name checks.
Third-party source under `training/vendor/` retains its upstream formatting and
license. Generated versions, trust keys, installers, and private training data are
not formatting targets.

Install development dependencies in a separate environment if you want to avoid
changing the package inventory used by release fingerprints:

```powershell
py -3.12 -m venv .dev-venv
.dev-venv\Scripts\python -m pip install -r requirements-dev.txt
.dev-venv\Scripts\python -m black --check .
.dev-venv\Scripts\python -m ruff check .
.venv\Scripts\python scripts/check_documentation.py
.venv\Scripts\python -m unittest discover -s tests -v
.training-venv\Scripts\python training/test_dataset.py
```

Model weights are needed for real inference checks. The training checks also need
the optional training dependencies. Production and development environments are
separate; the client never needs PyTorch or formatting tools.

## Completing an update

Add user-facing notes for the next client version in `assets/changelog.json`.
When code and verification are complete, run
`.venv\Scripts\python.exe build_release.py --prepare-only` once. This prepares
the visible version without publishing OTA or building an installer. Unchanged
code keeps its existing version. Commit and push completed updates to GitHub.
The host decides separately when to publish the LAN update or request an installer.
