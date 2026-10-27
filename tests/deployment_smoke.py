r"""Manual end-to-end check of the built installer and frozen startup updater.

Run: .venv\Scripts\python tests/deployment_smoke.py
Creates a temporary installation and desktop shortcut, then uninstalls it.
An existing application desktop shortcut is preserved and restored.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import runpy
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deployment.common import digest
from deployment.publisher import publish
from deployment.server import handler_for
from deployment.versioning import increment_patch, version_tuple


def main():
    """Exercise a temporary installed client and verify signed incremental updates end to end."""
    installers = [
        path
        for prefix in ("PortraitStudio", "IDFrame")
        for path in (ROOT / "dist" / "installer").glob(f"{prefix}-Setup-*.exe")
    ]
    installer = max(
        installers, key=lambda path: version_tuple(path.stem.split("-Setup-", 1)[1])
    )
    version = installer.stem.split("-Setup-", 1)[1]
    built_exports = runpy.run_path(
        str(ROOT / "dist" / "client" / "payload" / "portrait.py")
    )
    work = Path(
        tempfile.mkdtemp(prefix="deployment-smoke-", dir=ROOT / "build")
    ).resolve()
    installed = work / "installed"
    desktop = subprocess.check_output(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "[Environment]::GetFolderPath('Desktop')",
        ],
        text=True,
    ).strip()
    shortcut = Path(desktop) / (
        "IDFrame.lnk"
        if installer.name.startswith("IDFrame-")
        else "Portrait Studio.lnk"
    )
    previous_shortcut = shortcut.read_bytes() if shortcut.exists() else None
    server = None
    thread = None
    report = {}
    registry_key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{4F996310-BECE-42C1-B5A5-359D8AE081C4}_is1"
    registry_backup = work / "previous-install.reg"
    if (
        subprocess.run(
            ["reg", "query", registry_key],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    ):
        subprocess.run(
            ["reg", "export", registry_key, str(registry_backup), "/y"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    try:
        repository = work / "repository"
        repository.mkdir()
        (repository / "blobs").mkdir()
        built_repository = ROOT / "build" / "installer-repository"
        for blob in (built_repository / "blobs").iterdir():
            if blob.is_file() and len(blob.name) == 64:
                os.link(blob, repository / "blobs" / blob.name)
        shutil.copy2(built_repository / "manifest.json", repository)
        requests = []
        parent = handler_for(repository)

        class Handler(parent):
            def do_GET(self):
                """Record a test HTTP request before delegating to the real update handler."""
                requests.append(self.path)
                super().do_GET()

            def log_message(self, *args):
                """Suppress HTTP request logging so test output shows only test results."""
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        # Install the original version first, then exercise an in-place upgrade.
        original = ROOT / "dist" / "installer" / "PortraitStudio-Setup-1.0.0.exe"
        subprocess.run(
            [
                str(original),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={installed}",
                "/GROUP=Portrait Studio Deployment Test",
                "/HOSTURL=http://127.0.0.1:9",
            ],
            check=True,
            timeout=90,
        )
        subprocess.run(
            [
                str(installer),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={installed}",
                "/GROUP=Portrait Studio Deployment Test",
                f"/LOG={work / 'install.log'}",
            ],
            check=True,
            timeout=90,
        )
        config = json.loads((installed / "client.json").read_text(encoding="utf-8-sig"))
        assert config["host_url"] == "http://192.168.83.169:8766", config
        assert (installed / "payload" / "photo_clipboard.py").is_file()
        assert (installed / "payload" / "assets" / "portrait-studio.ico").is_file()
        report["version_1_upgrade_and_corrected_host"] = "passed"
        (installed / "client.json").write_text(json.dumps({"host_url": url}))
        assert shortcut.is_file(), "Desktop shortcut missing"
        environment = os.environ.copy()
        environment["PORTRAIT_TEST_SHORTCUT"] = str(shortcut)
        target = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:PORTRAIT_TEST_SHORTCUT); $s.TargetPath",
            ],
            env=environment,
            text=True,
        ).strip()
        assert (
            Path(target).resolve() == installed / "PortraitStudio.exe"
        ), "Shortcut points to the wrong executable"
        report["installer_and_desktop_shortcut"] = "passed"

        def run_client(name):
            """Launch the isolated client smoke check and validate its export and update report."""
            output = work / (name + ".png")
            subprocess.run(
                [str(installed / "PortraitStudio.exe"), "--smoke-test", str(output)],
                check=True,
                timeout=60,
            )
            result = json.loads(output.with_suffix(".json").read_text())
            result.update(json.loads(output.with_suffix(".update.json").read_text()))
            assert (
                result["size"] == list(built_exports["OUTPUT_SIZE"])
                and result["mode"] == "RGB"
            )
            assert (
                result["corner"] == [255, 255, 255]
                and abs(result["dpi"][0] - built_exports["OUTPUT_DPI"][0]) < 0.01
            )
            return result

        report["initial_launch"] = run_client("initial")
        assert requests == ["/manifest.json"], requests
        requests.clear()
        model = installed / "payload" / "models" / "u2net_human_seg.onnx"
        model_timestamp = model.stat().st_mtime_ns
        source = work / "source"
        shutil.copytree(ROOT / "dist" / "client" / "payload", source)
        application = source / "app.py"
        application_source = application.read_text(encoding="utf-8")
        title_setter = (
            "self.setWindowTitle("
            if "self.setWindowTitle(" in application_source
            else "root.title("
        )
        assert title_setter in application_source
        application.write_text(
            application_source.replace(
                title_setter, title_setter + '"IDFrame LAN Updated " + ', 1
            ),
            encoding="utf-8",
        )
        publish(
            source,
            repository,
            ROOT / ".host" / "signing-key.pem",
            increment_patch(version),
        )
        report["updated_launch"] = run_client("updated")
        assert (
            "LAN Updated" in report["updated_launch"]["title"]
        ), "Updated source was not executed"
        assert "Updated to" in report["updated_launch"]["status"]
        assert requests == ["/manifest.json", "/blobs/" + digest(application)], requests
        assert (
            model.stat().st_mtime_ns == model_timestamp
        ), "Unchanged model was touched"
        report["only_changed_app_file_downloaded"] = "passed"
        server.shutdown()
        server.server_close()
        thread.join()
        server = None
        thread = None
        report["offline_launch"] = run_client("offline")
        assert "using installed version" in report["offline_launch"]["status"]
        report["passed"] = True
        print(json.dumps(report, indent=2))
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join()
        uninstallers = list(installed.glob("unins*.exe"))
        if uninstallers:
            subprocess.run(
                [
                    str(uninstallers[0]),
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                ],
                check=True,
                timeout=60,
            )
        if previous_shortcut is not None:
            shortcut.write_bytes(previous_shortcut)
        if registry_backup.exists():
            subprocess.run(
                ["reg", "import", str(registry_backup)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        (ROOT / "build" / "deployment-smoke-report.json").write_text(
            json.dumps(report, indent=2)
        )
        if work.parent != (ROOT / "build").resolve() or not work.name.startswith(
            "deployment-smoke-"
        ):
            raise ValueError("Unexpected smoke-test cleanup target")
        shutil.rmtree(work)


if __name__ == "__main__":
    main()
