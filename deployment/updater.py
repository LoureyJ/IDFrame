"""Verified, file-level client updates with crash recovery and rollback."""
import base64
import json
from pathlib import Path
import shutil
import time
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from deployment.common import MAX_MANIFEST, atomic_write, canonical, digest, safe_path, verify_manifest


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Use a host address such as http://192.168.83.169:8765")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("Invalid host port")
    return url.rstrip("/")


def transaction_dir(root):
    root = Path(root).resolve()
    transaction = root / ".update-transaction"
    if transaction.is_symlink() or transaction.resolve() != transaction:
        raise ValueError("Unsafe update staging folder")
    return transaction


def clean_transaction(root):
    transaction = transaction_dir(root)
    if transaction.exists():
        # Resolved exact child of the installation root was checked above.
        shutil.rmtree(transaction)


def recover(root):
    """Undo an interrupted installation before ever starting the application."""
    root = Path(root).resolve()
    transaction = transaction_dir(root)
    journal_path = transaction / "journal.json"
    if not journal_path.exists():
        clean_transaction(root)
        return
    journal = json.loads(journal_path.read_bytes())
    if journal.get("committed"):
        clean_transaction(root)
        return
    for operation in reversed(journal["operations"]):
        name = operation["name"]
        target = safe_path(root / "payload", name)
        backup = safe_path(transaction / "backup", name)
        if backup.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            backup.replace(target)
        elif not operation["existed"]:
            target.unlink(missing_ok=True)
    state = root / "installed-manifest.json"
    if journal["previous"] is None:
        state.unlink(missing_ok=True)
    else:
        atomic_write(state, base64.b64decode(journal["previous"]))
    clean_transaction(root)


def apply_update(root, base_url, public_key, progress=lambda text: None, timeout=3, download_timeout=30, budget=180, transfer_progress=None):
    root = Path(root).resolve()
    recover(root)
    base_url = validate_url(base_url)
    # Ignore system proxies for local-network updates.
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + budget
    with opener.open(base_url + "/manifest.json", timeout=timeout) as response:
        raw = response.read(MAX_MANIFEST + 1)
    remote = verify_manifest(raw, public_key)["payload"]
    state = root / "installed-manifest.json"
    previous_raw = state.read_bytes() if state.exists() else None
    previous = verify_manifest(previous_raw, public_key)["payload"] if previous_raw else None
    if previous:
        if remote["generation"] < previous["generation"]:
            raise ValueError("Host offered an older release; update rejected")
        if remote["generation"] == previous["generation"] and remote != previous:
            raise ValueError("Conflicting release generation")
    files = remote["files"]
    progress("Checking installed files…")
    changed = []
    for name, entry in files.items():
        target = safe_path(root / "payload", name)
        if not target.is_file() or target.stat().st_size != entry["size"] or digest(target) != entry["sha256"]:
            changed.append(name)
    current_names = {name.casefold() for name in files}
    removed = sorted(name for name in (previous["files"] if previous else ())
                     if name.casefold() not in current_names)
    if not changed and not removed:
        if raw != previous_raw:
            atomic_write(state, raw)
        return f"Up to date · v{remote['version']}"
    transaction = transaction_dir(root)
    transaction.mkdir()
    try:
        completed = 0
        total = sum(files[name]["size"] for name in changed)
        if transfer_progress:
            transfer_progress(0, total)
        for index, name in enumerate(changed, 1):
            progress(f"Downloading update {index} of {len(changed)}")
            entry = files[name]
            destination = safe_path(transaction / "files", name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Update exceeded its time limit")
            with opener.open(base_url + "/blobs/" + entry["sha256"], timeout=min(download_timeout, remaining)) as response, destination.open("wb") as output:
                count = 0
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > entry["size"] or time.monotonic() > deadline:
                        raise ValueError("Update file exceeded its size or time limit")
                    output.write(chunk)
                    if transfer_progress:
                        transfer_progress(completed + count, total)
            if count != entry["size"] or digest(destination) != entry["sha256"]:
                raise ValueError(f"Update file failed verification: {name}")
            completed += count
        operations = [{"name": name, "existed": safe_path(root / "payload", name).exists()}
                      for name in changed + removed]
        journal = {"operations": operations, "previous": base64.b64encode(previous_raw).decode() if previous_raw else None,
                   "committed": False}
        atomic_write(transaction / "journal.json", canonical(journal))
        progress("Installing verified update…")
        for operation in operations:
            name = operation["name"]
            target = safe_path(root / "payload", name)
            if operation["existed"]:
                backup = safe_path(transaction / "backup", name)
                backup.parent.mkdir(parents=True, exist_ok=True)
                target.replace(backup)
            staged = safe_path(transaction / "files", name)
            if staged.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                staged.replace(target)
        atomic_write(state, raw)
        journal["committed"] = True
        atomic_write(transaction / "journal.json", canonical(journal))
    except Exception:
        recover(root)
        raise
    clean_transaction(root)
    return f"Updated to v{remote['version']} · {len(changed)} changed files"
