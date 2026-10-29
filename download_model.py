"""One-time online setup. The desktop application never downloads anything."""

import hashlib
from urllib.request import urlopen

from portrait import LEGACY_MODEL_PATH as MODEL_PATH

URL = (
    "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx"
)
EXPECTED_MD5 = "c09ddc2e0104f800e3e1bb4652583d1f"


def checksum(path):
    """Return the model file's MD5 digest for comparison with the upstream checksum."""
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    """Download the base model once, verify its checksum, and install it atomically."""
    download_alignment_model()
    if MODEL_PATH.exists() and checksum(MODEL_PATH) == EXPECTED_MD5:
        print("Portrait model is ready. You can now use the app offline.")
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MODEL_PATH.with_suffix(".download")
    print(
        "Downloading portrait model (about 176 MB). This is only needed once.",
        flush=True,
    )
    try:
        with urlopen(URL, timeout=60) as response, temporary.open("wb") as output:
            size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            last_progress = -1
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                downloaded += len(chunk)
                progress = (
                    int(downloaded * 100 / size)
                    if size
                    else downloaded // (1024 * 1024)
                )
                if progress // 10 != last_progress:
                    print(f"Downloaded: {progress}{'%' if size else ' MB'}", flush=True)
                    last_progress = progress // 10
        if checksum(temporary) != EXPECTED_MD5:
            raise RuntimeError("Model checksum mismatch. Run setup again to retry.")
        temporary.replace(MODEL_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    print("Setup complete. Run launch.bat. Internet is no longer required.")


def download_alignment_model():
    """Install the small optional face detector during host setup, never at runtime."""
    from alignment import MODEL_PATH, MODEL_URL, MODEL_SHA256

    if MODEL_PATH.is_file():
        with MODEL_PATH.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() == MODEL_SHA256:
                return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MODEL_PATH.with_suffix(".download")
    print("Downloading offline alignment model (about 233 KB).", flush=True)
    try:
        with urlopen(MODEL_URL, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        with temporary.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != MODEL_SHA256:
                raise RuntimeError(
                    "Alignment model checksum mismatch. Run setup again."
                )
        temporary.replace(MODEL_PATH)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
