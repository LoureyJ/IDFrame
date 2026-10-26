"""Publish immutable, content-addressed files and one atomically replaced manifest."""

import base64
from pathlib import Path
import shutil
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from deployment.common import (
    atomic_write,
    canonical,
    digest,
    safe_path,
    verify_manifest,
)


def signing_key(key_path):
    """Load or create the host-only Ed25519 key and return its public key as hex."""
    key_path = Path(key_path)
    if key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        key = Ed25519PrivateKey.generate()
        atomic_write(
            key_path,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        .hex()
    )
    return key, public


def publish(payload_dir, repository, key_path, version):
    """Store immutable file blobs and atomically publish a signed, monotonic release manifest."""
    payload_dir, repository = Path(payload_dir), Path(repository)
    key, public = signing_key(key_path)
    repository.mkdir(parents=True, exist_ok=True)
    blobs = repository / "blobs"
    blobs.mkdir(exist_ok=True)
    files = {}
    changed = 0
    for source in sorted(payload_dir.rglob("*")):
        if not source.is_file():
            continue
        name = source.relative_to(payload_dir).as_posix()
        safe_path(payload_dir, name)
        sha = digest(source)
        files[name] = {"sha256": sha, "size": source.stat().st_size}
        blob = blobs / sha
        if not blob.exists():
            temporary = blob.with_suffix(".tmp")
            shutil.copyfile(source, temporary)
            if digest(temporary) != sha:
                raise RuntimeError("Build file changed during publication")
            temporary.replace(blob)
            changed += 1
    manifest_path = repository / "manifest.json"
    previous = None
    if manifest_path.exists():
        previous = verify_manifest(manifest_path.read_bytes(), public)["payload"]
    if previous and previous["files"] == files and previous["version"] == version:
        return manifest_path.read_bytes(), public, 0
    payload = {
        "schema": 1,
        "generation": max(
            time.time_ns(), previous["generation"] + 1 if previous else 1
        ),
        "version": version,
        "files": files,
    }
    envelope = {
        "payload": payload,
        "signature": base64.b64encode(key.sign(canonical(payload))).decode("ascii"),
    }
    raw = canonical(envelope)
    verify_manifest(raw, public)
    atomic_write(manifest_path, raw)
    return raw, public, changed
