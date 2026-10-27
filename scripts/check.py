#!/usr/bin/env python3
"""Run repository tests and, optionally, canonical sec10v content preparation."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def validate_file(target: str, backend_arg: str | None, python_arg: str | None) -> None:
    path = Path(target)
    if not path.is_absolute():
        path = ROOT / path
    if any(component.is_symlink() for component in (path, *path.parents) if component != path.anchor) or not path.is_file() or path.suffix != ".md":
        raise ValueError("content target must be a regular, non-symlink .md file")
    try:
        lexical_rel = path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("content target must be under this repository") from exc
    if any(part in {"", ".", ".."} or not part.isascii() or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for char in part) for part in lexical_rel.parts):
        raise ValueError("target path contains unsupported characters")
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("content target must be under this repository") from exc
    if len(rel.parts) < 2 or rel.parts[0] not in {"reflections", "chapters"} or rel.name in {"README.md", "AGENTS.md"}:
        raise ValueError("target must be a content Markdown file under reflections/ or chapters/")
    backend_value = backend_arg or os.environ.get("SEC10V_DIR")
    if not backend_value:
        raise ValueError("set --sec10v-dir or SEC10V_DIR to an existing sec10v checkout")
    backend = Path(backend_value).expanduser().resolve()
    script_name = "prepare_reflection.py" if rel.parts[0] == "reflections" else "prepare_markdown_chapter.py"
    script = backend / "scripts" / script_name
    if not script.is_file():
        raise ValueError(f"canonical preparer not found: {script}")
    interpreter = python_arg or os.environ.get("SEC10V_PYTHON") or sys.executable
    if "/" in interpreter or interpreter.startswith("~"):
        interpreter_path = Path(interpreter).expanduser()
        if not interpreter_path.is_absolute():
            interpreter_path = Path.cwd() / interpreter_path
        interpreter = str(interpreter_path.resolve())
    with tempfile.TemporaryDirectory(prefix="effective-disco-check-") as out_dir:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(backend / "scripts"), env.get("PYTHONPATH", "")]))
        subprocess.run([interpreter, str(script), "--script-file", str(resolved), "--out-dir", out_dir], cwd=backend, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="optionally run canonical content preparation after unit tests")
    parser.add_argument("--sec10v-dir")
    parser.add_argument("--sec10v-python")
    args = parser.parse_args()
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", ".github/tests", "-p", "test_*.py"], cwd=ROOT)
    if result.returncode:
        return result.returncode
    if args.file:
        try:
            validate_file(args.file, args.sec10v_dir, args.sec10v_python)
        except (ValueError, subprocess.CalledProcessError) as exc:
            print(f"content preparation failed: {exc}", file=sys.stderr)
            return getattr(exc, "returncode", 2) or 2
        except OSError as exc:
            print(f"cannot run content preparer ({exc}); check backend prerequisites and --sec10v-python", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
