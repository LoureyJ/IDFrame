"""Allocate one client version per distinct application/deployment code snapshot."""

import importlib.metadata
import json
from pathlib import Path
import re

from deployment.common import atomic_write, canonical, digest


def version_tuple(version):
    """Validate a numeric version and pad it for consistent comparisons."""
    if not isinstance(version, str) or not re.fullmatch(
        r"\d+\.\d+\.\d+(?:\.\d+)?", version
    ):
        raise ValueError("Use a numeric version such as 1.1.1")
    parts = tuple(int(part) for part in version.split("."))
    return parts + (0,) * (4 - len(parts))


def increment_patch(version):
    """Increment the final numeric version component without changing the prefix."""
    version_tuple(version)
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def source_fingerprint(root):
    """Hash distributable inputs and package versions while excluding the generated version file."""
    root = Path(root)
    sources = [
        path
        for path in root.glob("*.py")
        if path.name not in {"app_version.py", "download_model.py"}
    ]
    sources.extend(root.glob("*.bat"))
    sources.extend(root.glob("*.ps1"))
    sources.extend((root / "deployment").glob("*.py"))
    sources.extend((root / "deployment").glob("*.iss"))
    sources.extend(path for path in (root / "assets").rglob("*") if path.is_file())
    sources.extend(path for path in (root / "models").glob("*.onnx") if path.is_file())
    sources.extend(
        path
        for path in (root / "requirements.txt", root / "requirements-build.txt")
        if path.is_file()
    )
    snapshot = {
        path.relative_to(root).as_posix(): digest(path) for path in sorted(set(sources))
    }
    packages = sorted(
        (distribution.metadata["Name"], distribution.version)
        for distribution in importlib.metadata.distributions()
    )
    import hashlib

    return hashlib.sha256(
        canonical({"files": snapshot, "packages": packages})
    ).hexdigest()


def prepare_version(root, fingerprint=None):
    """Idempotent for unchanged code; a new snapshot increments the patch once."""
    root = Path(root)
    settings_path = root / "host_settings.json"
    settings = json.loads(settings_path.read_text())
    requested = settings["version"]
    version_tuple(requested)
    state_path = root / ".host" / "version-state.json"
    previous = json.loads(state_path.read_bytes()) if state_path.exists() else None
    fingerprint = fingerprint or source_fingerprint(root)
    baseline = previous["version"] if previous else None
    if baseline is None:
        releases = []
        for manifest in (
            root / ".host" / "repository" / "manifest.json",
            root / "build" / "installer-repository" / "manifest.json",
        ):
            if manifest.exists():
                candidate = json.loads(manifest.read_bytes())["payload"]["version"]
                version_tuple(candidate)
                releases.append(candidate)
        if releases:
            baseline = max(releases, key=version_tuple)
    if baseline and version_tuple(requested) < version_tuple(baseline):
        raise ValueError(
            f"Version cannot move backwards from {baseline} to {requested}"
        )
    version = requested
    if (
        baseline
        and requested == baseline
        and (previous is None or previous["fingerprint"] != fingerprint)
    ):
        version = increment_patch(baseline)
    state = {"version": version, "fingerprint": fingerprint}
    if settings["version"] != version:
        settings["version"] = version
        atomic_write(settings_path, (json.dumps(settings, indent=2) + "\n").encode())
    client_version = (
        '"""Client version, maintained by the release tools."""\n'
        f'VERSION = "{version}"\n'
    ).encode()
    client_path = root / "app_version.py"
    if not client_path.exists() or client_path.read_bytes() != client_version:
        atomic_write(client_path, client_version)
    # Save the snapshot last, so an interrupted write can be safely retried.
    if previous != state:
        atomic_write(state_path, canonical(state))
    return version
