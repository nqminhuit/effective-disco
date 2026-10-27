# Effective Disco

A public authoring and build repository for audiobook reflections, chapter videos, and OmniVoice text. This is a fresh snapshot, not a history rewrite, from `nqminhuit/friendly-broccoli` at `ccdaab345e0b9d959877f088bd7d6252386b2691`.

## Layout and authoring

- `reflections/`: narration, image prompts, and reflection rules.
- `chapters/`: chapter scripts and chapter rules.
- `.pi/skills/`: Pi authoring workflows; `.pi/prompts/`: short task templates.
- `.github/workflows/`: content build workflows and read-only checks.
- `text/omnivoice.txt`: OmniVoice source text.

Use Pi 1.4.0 with a fresh session for each piece. Pi is expected to be available as `pi`; no repository-specific model or provider is selected. From the repository root, use `/reflection <task>`, `/chapter <task>`, or `/review <paths>`. `/skill:write-reflection` and `/skill:prepare-chapter` are also available. Create scratch space with `mkdir -p .scratch`; keep downloaded sources and intermediates there. Review finished files separately and pass only relevant files to each review.

A prompt is not a sandbox. For a fresh read-only review use Pi's explicit tool selection and disable extensions/MCP, for example:

```sh
pi --no-extensions --no-mcp --tools read,grep,find,ls
```

## Checks

Use an isolated environment (Python 3.13 in CI; local Python 3.10+):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python scripts/check.py
```

Tests use unittest and pinned PyYAML. Optional content-preparer validation uses the canonical scripts in an existing `sec10v` checkout; it does not install dependencies, access the network, run TTS, or upload artifacts:

```sh
python scripts/check.py --file reflections/name.md --sec10v-dir ../sec10v --sec10v-python ../sec10v/.venv/bin/python
```

The backend directory can instead be set via `SEC10V_DIR`; its interpreter via `SEC10V_PYTHON`. Validation only checks what the preparer checks. It does not prove missing eligible spoken names, story accuracy, complete prompt coverage, or equality with a chapter baseline; the skills require those separate reviews.

## Workflow activation and cutover

Automatic content builds are gated off unless repository variable `CONTENT_BUILDS_ENABLED` is exactly `true`. Manual workflow dispatch remains available. Do not enable the variable until the old repository's automatic push workflows have been disabled and credentials provisioned. A cutover requires these secret names (never put values in this repo): `SEC10V_ACCESS_TOKEN`, `HF_TOKEN`, `REFLECTION_IMAGE_BUCKET`, optional `REFLECTION_IMAGE_PREFIX`, `CHAPTER_IMAGE_BUCKET`, optional `CHAPTER_IMAGE_PREFIX`, `BUCKET_S3_ENDPOINT`, `BUCKET_S3_URI`, `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`. `GITHUB_TOKEN` is automatic and the coordinator needs `actions:write`. Encrypted source-repository secrets cannot be exported/read with `gh`; securely provision replacements. Ensure `SEC10V_ACCESS_TOKEN` still has read access to `nqminhuit/sec10v`. No `OPENCODE_API_KEY` or `GEMINI_API_KEY` is needed.

Recommended order: import/merge with push gate off; provision secrets; perform only an explicitly authorized smoke build; disable/remove old-repository push workflows before setting this repo's variable to `true`; verify no duplicate builds/uploads; then clean up the source repository. The backend `nqminhuit/sec10v` remains separate and is not modified here. Some backend CLI defaults still point at friendly-broccoli: examples and operational commands must pass destination `--owner`/`--repo` explicitly. Existing artifacts and caches do not transfer. Old successful uploads are not globally deduplicated; inspect pending failed-upload bundles and the existing channel before replaying historical content because renamed workflows/settings may change fallback identity. Images remain in existing buckets without path changes. Cutover is not complete.

The OmniVoice push workflow also triggers for source text changes on any branch; commits touching `text/omnivoice.txt` must include `[skip ci]` unless a run was explicitly intended. This migration itself must use `[skip ci]`.
