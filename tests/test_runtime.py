"""Check that the source runtime bootstraps the actual Qt application offline."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RuntimeTests(unittest.TestCase):
    """Exercise runtime startup and the existing export contract in a fresh process."""

    def test_source_runtime_smoke_starts_qt_and_exports_white_portrait(self):
        """The runtime smoke path must construct Qt rather than the retired Tk UI."""
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "portrait.png"
            environment = os.environ | {"QT_QPA_PLATFORM": "offscreen"}
            result = subprocess.run(
                [sys.executable, "deployment/runtime.py", "--smoke-test", str(output)],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.with_suffix(".json").read_text())
            self.assertEqual(report["ui"], "PySide6")
            self.assertEqual(report["editor"], "passed")
            self.assertEqual(report["size"], [1200, 1200])
            self.assertEqual(report["mode"], "RGB")
            self.assertEqual(report["corner"], [255, 255, 255])
            self.assertAlmostEqual(report["dpi"][0], 600, delta=1)
