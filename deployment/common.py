import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_MANIFEST = 4 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def safe_path(root, name):
    """Accept only portable relative file paths, including on Windows."""
    if not isinstance(name, str):
        raise ValueError("Update paths must be strings")
    parts = PurePosixPath(name).parts
    if (not name or "\\" in name or ":" in name
            or name.startswith("/") or not parts or "/".join(parts) != name
            or any(p in (".", "..") or p.endswith((".", " ")) for p in parts)
            or any(re.search(r'[<>"|?*\x00-\x1f]', p) for p in parts)
            or any(p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]} for p in parts)):
        raise ValueError(f"Unsafe update path: {name!r}")
    root = Path(root).resolve()
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError("Update path escapes installation folder")
    return target


def verify_manifest(raw, public_key):
    if len(raw) > MAX_MANIFEST:
        raise ValueError("Manifest is too large")
    envelope = json.loads(raw)
    payload = envelope["payload"]
    signature = base64.b64decode(envelope["signature"], validate=True)
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(signature, canonical(payload))
    if payload.get("schema") != 1 or type(payload.get("generation")) is not int or payload["generation"] < 1:
        raise ValueError("Unsupported update manifest")
    files = payload["files"]
    if not isinstance(files, dict) or len(files) > 20000 or not files:
        raise ValueError("Invalid file list")
    seen = set()
    for name, entry in files.items():
        safe_path(Path.cwd(), name)
        lowered = name.casefold()
        if lowered in seen or any(lowered.startswith(p + "/") or p.startswith(lowered + "/") for p in seen):
            raise ValueError("Conflicting update paths")
        seen.add(lowered)
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("Invalid file checksum")
        if type(entry["size"]) is not int or not 0 <= entry["size"] <= 1024**3:
            raise ValueError("Invalid file size")
    if sum(entry["size"] for entry in files.values()) > 4 * 1024**3:
        raise ValueError("Update is too large")
    return envelope
