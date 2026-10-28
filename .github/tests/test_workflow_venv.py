"""Exercise cached-venv recovery without installing dependencies or contacting the network."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"
REQUIREMENTS = {
    "sec10v.yml": "requirements_no_cuda.txt",
    "omnivoice.yml": "requirements-omnivoice.txt",
}
FAKE_PYTHON = f"""#!{sys.executable}
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps({{'executable': sys.argv[0], 'args': args}}) + '\\n')
if args == ['-m', 'venv', '.venv']:
    target = Path('.venv/bin/python')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(Path(__file__).read_text())
    target.chmod(0o755)
elif args == ['-m', 'pip', '--version']:
    if Path('.venv/broken-pip').exists():
        sys.exit(1)
elif args[:3] == ['-m', 'pip', 'install']:
    if os.environ.get('FAIL_INSTALL') == 'true':
        sys.exit(19)
else:
    raise SystemExit('unexpected command: ' + repr(args))
"""


def run_install(script, cache_hit, state, fail_install=False):
    """Run the real workflow shell body using fake setup/venv interpreters."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        work = root / "sec10v"
        work.mkdir()
        bindir = root / "bin"
        bindir.mkdir()
        setup_python = bindir / "python"
        setup_python.write_text(FAKE_PYTHON)
        setup_python.chmod(0o755)
        if state != "missing":
            venv_bin = work / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            (work / ".venv" / "from-cache").touch()
            if state == "broken-link":
                # venvs can reference a setup-python toolcache patch removed from the image.
                (venv_bin / "python").symlink_to(root / "Python/3.13.16/x64/bin/python")
            else:
                (venv_bin / "python").write_text(FAKE_PYTHON)
                (venv_bin / "python").chmod(0o755)
                if state == "broken-pip":
                    (work / ".venv" / "broken-pip").touch()
        log = root / "commands.jsonl"
        log.touch()
        env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ.get("PATH", ""),
                   VENV_CACHE_HIT=cache_hit, COMMAND_LOG=str(log),
                   FAIL_INSTALL="true" if fail_install else "false")
        proc = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                              cwd=work, env=env, capture_output=True, text=True, timeout=30)
        commands = [json.loads(line) for line in log.read_text().splitlines()]
        marker_remains = (work / ".venv" / "from-cache").exists()
        interpreter_exists = (work / ".venv" / "bin" / "python").is_file()
        return proc, commands, marker_remains, interpreter_exists


class WorkflowVenvTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = {}
        for filename in REQUIREMENTS:
            doc = yaml.safe_load((WORKFLOWS / filename).read_text())
            cls.steps[filename] = doc["jobs"]["build-external"]["steps"]

    def test_cache_uses_exact_python_version_and_architecture(self):
        for filename, requirements in REQUIREMENTS.items():
            with self.subTest(workflow=filename):
                steps = self.steps[filename]
                setup = next(s for s in steps if s.get("id") == "python")
                cache = next(s for s in steps if s.get("id") == "cache-venv")
                install = next(s for s in steps if s.get("name") == "Install Python dependencies")
                activate = next(s for s in steps if s.get("name") == "Activate Python venv")
                self.assertTrue(setup["uses"].startswith("actions/setup-python@"))
                key = cache["with"]["key"]
                for want in ("${{ runner.os }}", "${{ runner.arch }}", "venv-v2",
                             "${{ steps.python.outputs.python-version }}",
                             "hashFiles('sec10v/" + requirements + "')"):
                    self.assertIn(want, key)
                self.assertNotIn("restore-keys", cache["with"])
                self.assertEqual("sec10v/.venv", cache["with"]["path"])
                self.assertNotIn("if", install, "validation must run even on a cache hit")
                self.assertEqual("sec10v", install["working-directory"])
                self.assertEqual("${{ steps.cache-venv.outputs.cache-hit }}",
                                 install["env"]["VENV_CACHE_HIT"])
                self.assertLess(steps.index(setup), steps.index(cache))
                self.assertLess(steps.index(cache), steps.index(install))
                self.assertLess(steps.index(install), steps.index(activate))
                if filename == "sec10v.yml":
                    weights = next(s for s in steps if s.get("name") == "Ensure Chatterbox weights are local")
                    self.assertLess(steps.index(activate), steps.index(weights))

    def test_restored_venv_is_validated_and_rebuilt_when_needed(self):
        cases = (("false", "missing", True), ("", "missing", True),
                 ("true", "healthy", False), ("true", "missing", True),
                 ("true", "broken-link", True), ("true", "broken-pip", True),
                 ("false", "healthy", True))
        for filename, requirements in REQUIREMENTS.items():
            script = next(s["run"] for s in self.steps[filename]
                          if s.get("name") == "Install Python dependencies")
            for cache_hit, state, rebuild in cases:
                with self.subTest(workflow=filename, cache_hit=cache_hit, state=state):
                    proc, commands, marker, interpreter = run_install(script, cache_hit, state)
                    self.assertEqual(0, proc.returncode, proc.stderr)
                    self.assertTrue(interpreter)
                    args = [command["args"] for command in commands]
                    if rebuild:
                        self.assertIn(["-m", "venv", ".venv"], args)
                        self.assertFalse(marker, "rebuild must remove the stale environment first")
                        installs = [command for command in commands
                                    if command["args"][:3] == ["-m", "pip", "install"]]
                        self.assertEqual(3, len(installs))
                        self.assertTrue(all(c["executable"] == ".venv/bin/python" for c in installs))
                        self.assertEqual(["-m", "pip", "install", "--upgrade", "pip"], installs[0]["args"])
                        self.assertEqual(["-m", "pip", "install", "torch", "torchaudio", "--index-url",
                                          "https://download.pytorch.org/whl/cpu"], installs[1]["args"])
                        self.assertEqual(["-m", "pip", "install", "-r", requirements], installs[2]["args"])
                    else:
                        self.assertEqual([["-m", "pip", "--version"]], args)
                        self.assertTrue(marker, "a healthy cache should not be reinstalled")

    def test_install_failures_still_fail_the_step(self):
        for filename in REQUIREMENTS:
            with self.subTest(workflow=filename):
                script = next(s["run"] for s in self.steps[filename]
                              if s.get("name") == "Install Python dependencies")
                proc, commands, _, _ = run_install(script, "true", "broken-link", fail_install=True)
                self.assertEqual(19, proc.returncode)
                self.assertEqual(["-m", "pip", "install", "--upgrade", "pip"], commands[-1]["args"])


if __name__ == "__main__":
    unittest.main()
