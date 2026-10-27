import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.check as check


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.backend = Path(self.tmp.name) / "backend"
        (self.backend / "scripts").mkdir(parents=True)
        (self.backend / "scripts/prepare_reflection.py").touch()
        (self.backend / "scripts/prepare_markdown_chapter.py").touch()
        self.patch_root = patch.object(check, "ROOT", self.root)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)

    def content(self, rel):
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("content")
        return target

    def test_both_preparers_nested_paths_and_invocation_details(self):
        for rel, script in (("reflections/nested/story.md", "prepare_reflection.py"),
                            ("chapters/nested/story.md", "prepare_markdown_chapter.py")):
            target = self.content(rel)
            with patch.object(check.subprocess, "run") as run:
                check.validate_file(str(target), str(self.backend), "python3")
            argv = run.call_args.args[0]
            self.assertEqual(str(self.backend / "scripts" / script), argv[1])
            self.assertEqual(str(target.resolve()), argv[3])
            self.assertEqual(self.backend.resolve(), run.call_args.kwargs["cwd"])
            self.assertIn(str(self.backend / "scripts"), run.call_args.kwargs["env"]["PYTHONPATH"])
            out_dir = Path(argv[-1])
            self.assertFalse(out_dir.exists())
        self.assertFalse((self.backend / "out").exists())

    def test_rejects_leaf_and_ancestor_symlinks_and_outside_paths(self):
        real = self.content("reflections/real.md")
        leaf = self.root / "reflections/alias.md"
        leaf.symlink_to(real)
        (self.root / "reflections/diralias").symlink_to(real.parent, target_is_directory=True)
        outside = self.content("chapters/outside.md")
        for path in (leaf, self.root / "reflections/diralias/real.md", Path(self.tmp.name) / "outside.md"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                check.validate_file(str(path), str(self.backend), None)
        outside.write_text("x")

    def test_rejects_docs_uppercase_and_bad_components(self):
        for rel in ("chapters/README.md", "chapters/nested/AGENTS.md", "reflections/story.MD", "chapters/a b.md"):
            path = self.content(rel)
            with self.subTest(rel=rel), self.assertRaises(ValueError):
                check.validate_file(str(path), str(self.backend), None)

    def test_backend_option_and_environment_fallback(self):
        target = self.content("reflections/a.md")
        with patch.dict(os.environ, {"SEC10V_DIR": ""}):
            with self.assertRaisesRegex(ValueError, "SEC10V_DIR"):
                check.validate_file(str(target), None, None)
        with patch.dict(os.environ, {"SEC10V_DIR": str(self.backend)}), patch.object(check.subprocess, "run") as run:
            check.validate_file(str(target), None, None)
            self.assertEqual(os.path.abspath(os.path.expanduser(check.sys.executable)), run.call_args.args[0][0])

    def test_venv_interpreter_symlink_is_preserved_for_explicit_and_default(self):
        target = self.content("reflections/a.md")
        venv = Path(self.tmp.name) / "venv"
        subprocess.run([check.sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
        interpreter = venv / "bin/python"
        if not interpreter.is_symlink():
            self.skipTest("venv interpreter is not a symlink on this platform")

        preparer = self.backend / "scripts/prepare_reflection.py"
        preparer.write_text(
            "import pathlib, sys\n"
            "assert sys.prefix != sys.base_prefix, (sys.prefix, sys.base_prefix)\n"
            "pathlib.Path(sys.argv[sys.argv.index('--out-dir') + 1], 'ran').write_text(sys.prefix)\n"
        )
        with patch.dict(os.environ, {"SEC10V_DIR": str(self.backend)}):
            check.validate_file(str(target), str(self.backend), str(interpreter))
            with patch.object(check.sys, "executable", str(interpreter)):
                check.validate_file(str(target), str(self.backend), None)

    def test_relative_interpreter_resolved_before_backend_cwd(self):
        target = self.content("reflections/a.md")
        with patch("scripts.check.os.getcwd", return_value="/invocation"), patch.object(check.subprocess, "run") as run:
            check.validate_file(str(target), str(self.backend), "./.venv/bin/python")
        self.assertEqual("/invocation/.venv/bin/python", run.call_args.args[0][0])

    def test_missing_interpreter_is_concise(self):
        self.content("reflections/a.md")
        with patch.object(check.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0), FileNotFoundError("python missing")]), \
             patch("sys.argv", ["check.py", "--file", "reflections/a.md", "--sec10v-dir", str(self.backend), "--sec10v-python", "missing"]), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(2, check.main())
        self.assertIn("check backend prerequisites and --sec10v-python", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_rejects_noncanonical_dotdot_path(self):
        self.content("reflections/story.md")
        (self.root / "reflections/nested").mkdir()
        with self.assertRaisesRegex(ValueError, "unsupported characters"):
            check.validate_file("reflections/nested/../story.md", str(self.backend), None)

    def test_failed_preparer_propagates(self):
        target = self.content("chapters/a.md")
        with patch.object(check.subprocess, "run", side_effect=subprocess.CalledProcessError(7, ["x"])):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                check.validate_file(str(target), str(self.backend), "python")
        self.assertEqual(7, raised.exception.returncode)

    def test_main_tests_failure_stops_before_preparer(self):
        with patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], 4)) as run, \
             patch("sys.argv", ["check.py", "--file", "reflections/a.md"]):
            self.assertEqual(4, check.main())
            run.assert_called_once()

    def test_main_catches_missing_interpreter_and_no_content_test_mode(self):
        with patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch("sys.argv", ["check.py"]):
            self.assertEqual(0, check.main())
        self.assertEqual(1, run.call_count)

    def test_main_propagates_preparer_failure(self):
        self.content("reflections/a.md")
        with patch.object(check.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0), subprocess.CalledProcessError(7, ["x"])]), \
             patch("sys.argv", ["check.py", "--file", "reflections/a.md", "--sec10v-dir", str(self.backend)]), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(7, check.main())

    def test_absolute_caller_target_from_other_cwd(self):
        target = self.content("reflections/nested/a.md")
        with patch("scripts.check.Path.cwd", return_value=Path("/elsewhere")), patch.object(check.subprocess, "run"):
            check.validate_file(str(target), str(self.backend), "python")


if __name__ == "__main__":
    unittest.main()
