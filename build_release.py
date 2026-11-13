"""Build a client installer or publish an incremental application release."""

import argparse
import importlib.metadata
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from deployment.common import atomic_write, canonical, digest
from deployment.branding import generate_windows_icon
from deployment.publisher import publish, signing_key
from deployment.updater import validate_url
from deployment.versioning import prepare_version
from deployment.host_network import sync_host_address

ROOT = Path(__file__).resolve().parent
HOST = ROOT / ".host"
BUILD = ROOT / "build"
CLIENT = ROOT / "dist" / "client"


def run(args):
    """Run a build command from the project directory and stop on failure."""
    environment = runtime_build_environment() if "PyInstaller" in args else None
    subprocess.run([str(a) for a in args], cwd=ROOT, env=environment, check=True)


def runtime_build_environment():
    """Prevent unrelated PATH/Qt/Python libraries from contaminating frozen binaries."""
    environment = os.environ.copy()
    windows = Path(environment.get("SystemRoot", r"C:\Windows"))
    environment["PATH"] = os.pathsep.join(
        str(path)
        for path in (
            Path(sys.executable).parent,
            Path(sys.base_prefix),
            Path(sys.base_prefix) / "DLLs",
            windows / "System32",
            windows,
        )
    )
    for name in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    return environment


def remove_build_dir(path):
    """Remove only an explicitly allowed generated build directory."""
    path = Path(path).resolve()
    # Only remove named generated directories inside this workspace.
    if path not in {
        (BUILD / "runtime-dist").resolve(),
        (BUILD / "hotspot-identity").resolve(),
        (CLIENT / "payload").resolve(),
        (CLIENT / "identity-assets").resolve(),
    }:
        raise ValueError("Unexpected build cleanup target")
    if path.exists():
        shutil.rmtree(path)


def compiler_path():
    """Locate the bundled or installed Inno Setup compiler for installer builds."""
    candidates = [ROOT / ".tools" / "inno" / "ISCC.exe"]
    for base in (
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if base:
            candidates.extend(Path(base).glob("Inno Setup*/ISCC.exe"))
            candidates.extend(Path(base).glob("Programs/Inno Setup*/ISCC.exe"))
    if shutil.which("ISCC.exe"):
        candidates.append(Path(shutil.which("ISCC.exe")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "Inno Setup compiler is missing. Install Inno Setup, then rerun build_installer.bat."
    )


def windows_sdk_tool_path(tool_name):
    """Locate a Windows SDK packaging tool in the bundled cache or standard SDK path."""
    tools = [
        ROOT / ".tools" / "windows-sdk-buildtools" / "bin" / "10.0.26100.0" / "x64" / tool_name,
    ]
    kits = os.environ.get("ProgramFiles(x86)")
    if kits:
        sdk_bin = Path(kits) / "Windows Kits" / "10" / "bin"
        if sdk_bin.is_dir():
            tools.extend(
                path
                for version in sorted(sdk_bin.iterdir(), reverse=True)
                for path in (version / "x64" / tool_name,)
            )
    tools.extend(
        Path(path) for path in [shutil.which(tool_name) or ""] if path
    )
    for tool in tools:
        if tool.is_file():
            return tool
    raise RuntimeError(
        f"{tool_name} is required to build the hotspot identity package. "
        "Install the Windows 10/11 SDK or Windows SDK BuildTools package."
    )


def hotspot_package_signing_material():
    """Create or reuse the private host signing key and public package certificate."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    from datetime import datetime, timedelta, timezone

    private_path = HOST / "hotspot-package-signing.pfx"
    public_path = HOST / "hotspot-package-signing.cer"
    if private_path.is_file() and public_path.is_file():
        return private_path, public_path
    if private_path.exists() or public_path.exists():
        raise RuntimeError(
            "Only one IDFrame hotspot signing certificate file exists. Restore both "
            "files from the host backup before building an installer."
        )

    HOST.mkdir(exist_ok=True)
    # MSIX package signing uses the Windows RSA Authenticode path.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "IDFrame Local Hotspot")]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    pfx = pkcs12.serialize_key_and_certificates(
        b"IDFrame Local Hotspot",
        key,
        certificate,
        None,
        serialization.NoEncryption(),
    )
    atomic_write(private_path, pfx)
    atomic_write(public_path, certificate.public_bytes(serialization.Encoding.DER))
    return private_path, public_path


def build_hotspot_identity(version):
    """Build the installer-only sparse identity MSIX and stage its public assets."""
    package_version = version if len(version.split(".")) == 4 else version + ".0"
    if any(int(part) > 65535 for part in package_version.split(".")):
        raise ValueError("The Windows identity package version fields must be <= 65535")
    private_cert, public_cert = hotspot_package_signing_material()
    source_manifest = ROOT / "deployment" / "hotspot" / "AppxManifest.xml"
    work = BUILD / "hotspot-identity"
    if work.exists():
        remove_build_dir(work)
    work.mkdir(parents=True)
    manifest = work / "AppxManifest.xml"
    raw = source_manifest.read_text(encoding="utf-8")
    manifest.write_text(
        raw.replace("__PACKAGE_VERSION__", package_version), encoding="utf-8"
    )
    # Package logos must be physically inside the sparse MSIX. The full-trust
    # runtime executable and its payload stay under the external install root.
    shutil.copytree(
        ROOT / "deployment" / "hotspot" / "Assets",
        work / "Assets",
    )
    package = CLIENT / "IDFrameHotspot.identity.msix"
    package.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            windows_sdk_tool_path("makeappx.exe"),
            "pack",
            "/o",
            "/d",
            work,
            "/nv",
            "/p",
            package,
        ]
    )
    run(
        [
            windows_sdk_tool_path("signtool.exe"),
            "sign",
            "/fd",
            "SHA256",
            "/f",
            private_cert,
            package,
        ]
    )
    assets = CLIENT / "identity-assets"
    if assets.exists():
        remove_build_dir(assets)
    shutil.copytree(ROOT / "deployment" / "hotspot" / "Assets", assets / "Assets")
    shutil.copy2(public_cert, assets / "IDFramePackage.cer")
    shutil.copy2(
        ROOT / "deployment" / "hotspot" / "register_package.ps1",
        CLIENT / "register_hotspot_package.ps1",
    )


def build_runtime(force=False):
    """Reuse or rebuild the frozen CPU runtime when its inputs change."""
    fingerprint = canonical(
        {
            "builder": digest(ROOT / "build_release.py"),
            "runtime": digest(ROOT / "deployment" / "runtime.py"),
            "logo": digest(ROOT / "assets" / "portrait-studio.png"),
            "icon": digest(ROOT / "assets" / "portrait-studio.ico"),
            "manifest": digest(ROOT / "deployment" / "hotspot" / "runtime.manifest"),
            "packages": sorted(
                (d.metadata["Name"], d.version)
                for d in importlib.metadata.distributions()
            ),
        }
    )
    stamp = BUILD / "runtime-fingerprint.json"
    runtime_dir = BUILD / "runtime-dist" / "PortraitRuntime"
    if (
        force
        or not stamp.exists()
        or stamp.read_bytes() != fingerprint
        or not runtime_dir.exists()
    ):
        remove_build_dir(BUILD / "runtime-dist")
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onedir",
                "--windowed",
                "--noupx",
                "--icon",
                ROOT / "assets" / "portrait-studio.ico",
                "--manifest",
                ROOT / "deployment" / "hotspot" / "runtime.manifest",
                "--name",
                "PortraitRuntime",
                "--distpath",
                BUILD / "runtime-dist",
                "--workpath",
                BUILD / "pyinstaller-runtime",
                "--specpath",
                BUILD,
                "--hidden-import",
                "numpy",
                "--hidden-import",
                "onnxruntime",
                "--hidden-import",
                "PIL.ImageTk",
                "--hidden-import",
                "PIL.ImageOps",
                "--hidden-import",
                "http.server",
                "--hidden-import",
                "qrcode.image.pil",
                "--hidden-import",
                "tkinter.filedialog",
                "--hidden-import",
                "tkinter.messagebox",
                "--hidden-import",
                "tkinter.ttk",
                "--hidden-import",
                "PySide6.QtCore",
                "--hidden-import",
                "PySide6.QtGui",
                "--hidden-import",
                "PySide6.QtWidgets",
                "--hidden-import",
                "PySide6.QtNetwork",
                "--hidden-import",
                "PySide6.QtMultimedia",
                "--hidden-import",
                "PySide6.QtMultimediaWidgets",
                "--hidden-import",
                "winrt.windows.networking.connectivity",
                "--hidden-import",
                "winrt.windows.networking.networkoperators",
                "--hidden-import",
                "winrt.windows.foundation",
                "--collect-all",
                "winrt",
                "--collect-binaries",
                "onnxruntime",
                "--collect-all",
                "pillow_heif",
                ROOT / "deployment" / "runtime.py",
            ]
        )
        atomic_write(stamp, fingerprint)
    return runtime_dir


def build_launcher():
    """Reuse or rebuild the windowed updater launcher when its inputs change."""
    sources = [
        ROOT / "deployment" / name
        for name in ("launcher.py", "updater.py", "common.py", "trust.py")
    ]
    sources += [
        ROOT / "windows_branding.py",
        ROOT / "launcher_refresh.py",
        ROOT / "assets/portrait-studio.png",
        ROOT / "assets/portrait-studio.ico",
    ]
    fingerprint = canonical(
        {
            "files": {p.relative_to(ROOT).as_posix(): digest(p) for p in sources},
            "packages": sorted(
                (d.metadata["Name"], d.version)
                for d in importlib.metadata.distributions()
            ),
        }
    )
    stamp = BUILD / "launcher-fingerprint.json"
    executable = BUILD / "launcher-dist" / "PortraitStudio.exe"
    if (
        not stamp.exists()
        or stamp.read_bytes() != fingerprint
        or not executable.is_file()
    ):
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onefile",
                "--windowed",
                "--noupx",
                "--icon",
                ROOT / "assets" / "portrait-studio.ico",
                "--name",
                "PortraitStudio",
                "--paths",
                ROOT,
                "--distpath",
                BUILD / "launcher-dist",
                "--workpath",
                BUILD / "pyinstaller-launcher",
                "--specpath",
                BUILD,
                ROOT / "deployment" / "launcher.py",
            ]
        )
        atomic_write(stamp, fingerprint)
    return executable


def assemble_payload(runtime, launcher):
    """Copy the runtime, editable modules, models, assets, and launcher candidate."""
    payload = CLIENT / "payload"
    remove_build_dir(payload)
    shutil.copytree(runtime, payload)
    # Source modules are independent files: ordinary code edits transfer only those files.
    for source in ROOT.glob("*.py"):
        if source.name not in {"build_release.py", "download_model.py"}:
            compile(source.read_bytes(), str(source), "exec")
            shutil.copy2(source, payload / source.name)
    shutil.copytree(
        ROOT / "models", payload / "models", ignore=shutil.ignore_patterns("*.download")
    )
    if (ROOT / "assets").is_dir():
        shutil.copytree(ROOT / "assets", payload / "assets")
    # Old clients receive a verified candidate through their existing updater.
    # The new application activates it safely after their current session ends.
    shutil.copy2(launcher, payload / "PortraitLauncher.exe")
    return payload


def main():
    """Validate settings, acquire the release lock, and prepare, stage, or publish as requested."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", action="store_true")
    parser.add_argument("--rebuild-runtime", action="store_true")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare the client version without building or publishing",
    )
    args = parser.parse_args()
    settings = sync_host_address(ROOT)
    version = settings["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", version):
        parser.error("Use a numeric version such as 1.0.1 in host_settings.json")
    if not isinstance(settings["port"], int) or not 1 <= settings["port"] <= 65535:
        parser.error("Host port must be between 1 and 65535")
    url = validate_url(f"http://{settings['host']}:{settings['port']}")
    if not (ROOT / "models" / "u2net_human_seg.onnx").exists():
        parser.error("Portrait model missing. Run setup.bat first.")
    if not all((ROOT / name).is_file() for name in ("app.py", "portrait.py")):
        parser.error("Required application modules app.py and portrait.py are missing")
    HOST.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    CLIENT.mkdir(parents=True, exist_ok=True)
    # Serialize publication, installer assembly and key creation.
    import msvcrt

    with (HOST / "publish.lock").open("a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            parser.error("Another release build is running")
        generate_windows_icon(
            ROOT / "assets" / "portrait-studio.png",
            ROOT / "assets" / "portrait-studio.ico",
        )
        version = prepare_version(ROOT)
        if args.prepare_only:
            print(
                f"Client v{version} prepared. No installer built and no OTA release published."
            )
            return
        _, public = signing_key(HOST / "signing-key.pem")
        atomic_write(
            ROOT / "deployment" / "trust.py", f'PUBLIC_KEY = "{public}"\n'.encode()
        )
        runtime = build_runtime(args.rebuild_runtime)
        launcher = build_launcher()
        if args.installer:
            build_hotspot_identity(version)
        payload = assemble_payload(runtime, launcher)
        # Building an installer must not publish to the live OTA channel.
        repository = (
            BUILD / "installer-repository" if args.installer else HOST / "repository"
        )
        raw, public, new_blobs = publish(
            payload, repository, HOST / "signing-key.pem", version
        )
        atomic_write(CLIENT / "installed-manifest.json", raw)
        atomic_write(CLIENT / "client.json", canonical({"host_url": url}))
        action = "Staged installer" if args.installer else "Published"
        print(
            f"{action} v{version}: {new_blobs} new or changed file contents. Host: {url}",
            flush=True,
        )
        if args.installer:
            shutil.copy2(launcher, CLIENT / "PortraitStudio.exe")
            run(
                [
                    compiler_path(),
                    f"/DClientDir={CLIENT}",
                    f"/DOutputDir={ROOT / 'dist' / 'installer'}",
                    f"/DAppVersion={version}",
                    f"/DHostURL={url}",
                    ROOT / "deployment" / "installer.iss",
                ]
            )
            print(f"Installer ready in {ROOT / 'dist' / 'installer'}", flush=True)
            print(
                "Live OTA release unchanged. Run update.bat when you want to publish this version.",
                flush=True,
            )
        else:
            print(
                "Clients receive this release the next time they open the desktop shortcut.",
                flush=True,
            )


if __name__ == "__main__":
    main()
