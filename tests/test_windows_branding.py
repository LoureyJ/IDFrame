import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from windows_branding import APP_ID, repair_shortcut_icons, sync_installed_shortcuts


@unittest.skipUnless(os.name == "nt", "Windows shortcut integration")
class WindowsBrandingTests(unittest.TestCase):
    def test_shortcuts_receive_camera_icon_and_taskbar_identity(self):
        # Test shell-link files in a temporary directory, never the real desktop.
        """Verify that shortcuts receive camera icon and taskbar identity."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            launcher = root / "PortraitStudio.exe"
            launcher.write_bytes(b"test")
            (root / "payload").mkdir()
            runtime = root / "payload" / "PortraitRuntime.exe"
            runtime.write_bytes(b"test")
            other = root / "other.exe"
            other.write_bytes(b"other")
            shortcuts = [
                root / "Portrait Studio.lnk",
                root / "Taskbar.lnk",
                root / "Unrelated.lnk",
            ]
            environment = os.environ.copy()
            environment["PORTRAIT_TEST_LINKS"] = json.dumps(
                [
                    {"path": str(path), "target": str(target)}
                    for path, target in zip(shortcuts, [launcher, runtime, other])
                ]
            )
            setup = "$s=New-Object -ComObject WScript.Shell; foreach($i in ($env:PORTRAIT_TEST_LINKS | ConvertFrom-Json)) { $l=$s.CreateShortcut($i.path); $l.TargetPath=$i.target; $l.Save() }"
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", setup],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            before = shortcuts[2].read_bytes()
            count = repair_shortcut_icons(
                root, Path(__file__).resolve().parents[1] / "assets", shortcuts
            )
            self.assertEqual(count, 2)
            self.assertEqual(shortcuts[2].read_bytes(), before)
            self.assertFalse(shortcuts[0].exists())
            shortcuts[0] = root / "IDFrame.lnk"
            self.assertTrue(shortcuts[0].exists())
            environment["PORTRAIT_TEST_LINKS"] = json.dumps(
                [{"path": str(path)} for path in shortcuts]
            )
            inspect = r"""
$s=New-Object -ComObject WScript.Shell
$shell=New-Object -ComObject Shell.Application
$out=@()
foreach($i in ($env:PORTRAIT_TEST_LINKS | ConvertFrom-Json)) {
  $l=$s.CreateShortcut($i.path)
  $item=$shell.Namespace([IO.Path]::GetDirectoryName($i.path)).ParseName([IO.Path]::GetFileName($i.path))
  $out+=@{target=$l.TargetPath;icon=$l.IconLocation;identity=$item.ExtendedProperty('System.AppUserModel.ID')}
}
$out | ConvertTo-Json -Compress
"""
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", inspect],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            values = json.loads(result.stdout)
            for value in values[:2]:
                self.assertEqual(Path(value["target"]), launcher)
                self.assertIn(".branding", value["icon"])
                self.assertEqual(value["identity"], APP_ID)

    def test_source_session_never_changes_installed_shortcuts(self):
        """Verify that source session never changes installed shortcuts."""
        with patch("windows_branding.repair_shortcut_icons") as repair:
            sync_installed_shortcuts(Path("assets"))
            repair.assert_not_called()


if __name__ == "__main__":
    unittest.main()
