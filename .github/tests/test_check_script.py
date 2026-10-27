import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.check import ROOT, validate_file


class CheckerTests(unittest.TestCase):
    def test_rejects_outside_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "story.md"
            outside.write_text("x")
            with self.assertRaises(ValueError):
                validate_file(str(outside), "/missing", None)

    def test_backend_failure_is_propagated(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = Path(tmp)
            (backend / "scripts").mkdir()
            (backend / "scripts/prepare_reflection.py").touch()
            target = ROOT / "reflections" / "FatherBrownAndThenThereWereNone.md"
            with patch("scripts.check.subprocess.run", side_effect=__import__("subprocess").CalledProcessError(7, ["fake"])) as run:
                with self.assertRaises(__import__("subprocess").CalledProcessError):
                    validate_file(str(target), str(backend), "python")
                self.assertEqual(1, run.call_count)
                argv = run.call_args.args[0]
                self.assertIn(str(target.resolve()), argv)
                self.assertIn("--out-dir", argv)
