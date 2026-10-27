"""Keep unrelated machine-native libraries out of frozen client dependency discovery."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from build_release import runtime_build_environment


class RuntimeBuildTests(unittest.TestCase):
    """Verify an explicit, reproducible native-library search path for packaging."""

    def test_build_path_excludes_unrelated_native_tools(self):
        """Poppler ICU and other PATH libraries cannot shadow Windows Qt dependencies."""
        with patch.dict(
            os.environ,
            {
                "PATH": "C:/unrelated/poppler/bin",
                "QT_PLUGIN_PATH": "C:/unrelated/qt",
                "PYTHONPATH": "C:/unrelated/python",
                "IDFRAME_TEST_VALUE": "preserved",
            },
        ):
            environment = runtime_build_environment()
        self.assertNotIn("poppler", environment["PATH"])
        self.assertIn(str(Path(sys.executable).parent), environment["PATH"])
        self.assertIn("System32", environment["PATH"])
        self.assertNotIn("QT_PLUGIN_PATH", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertEqual(environment["IDFRAME_TEST_VALUE"], "preserved")
