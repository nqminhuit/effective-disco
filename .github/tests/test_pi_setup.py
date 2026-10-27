import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class PiSetupTests(unittest.TestCase):
    def test_snapshot_essentials_are_present(self):
        for path in ("text/omnivoice.txt", "reflections/AGENTS.md", "chapters/AGENTS.md",
                     ".github/scripts/select_chapter_files.py", ".github/workflows/sec10v.yml",
                     ".github/workflows/sec10v_chapter.yml", ".github/workflows/sec10v_reflection.yml",
                     ".github/workflows/sec10v_maya1.yml", ".github/workflows/sec10v_test_voices.yml",
                     ".github/workflows/omnivoice.yml"):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_skills_and_routes_exist(self):
        for path in (".pi/skills/write-reflection/SKILL.md", ".pi/skills/prepare-chapter/SKILL.md",
                     ".pi/skills/prepare-chapter/scripts/extract_chapter.py",
                     ".pi/prompts/reflection.md", ".pi/prompts/chapter.md", ".pi/prompts/review.md"):
            self.assertTrue((ROOT / path).is_file(), path)
        for key in ("$schema",):
            self.assertEqual("https://pi.dev/schemas/settings.schema.json", json.loads((ROOT / ".pi/settings.json").read_text())[key])

    def test_push_gates_do_not_block_manual_dispatch(self):
        for name, job in (("sec10v_reflection.yml", "files"), ("sec10v_chapter.yml", "files"), ("omnivoice.yml", "build-external")):
            text = (ROOT / ".github/workflows" / name).read_text()
            section = text.split(f"  {job}:\n", 1)[1].split("\n  ", 1)[0]
            self.assertIn("github.event_name != 'push' || vars.CONTENT_BUILDS_ENABLED == 'true'", section)
            self.assertIn("workflow_dispatch:", text)
