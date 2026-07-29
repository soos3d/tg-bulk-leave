---
name: rw-release-video
description: "Turn a repo's release notes or CHANGELOG section into a short product-update video using the Runway API (gen4_image keyframes animated with gen4.5, stitched with ffmpeg). Use when the user wants a release video, changelog video, or product-update clip for a version tag."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(release2reel *), Bash(pip install *), Bash(ffmpeg -version), Bash(command -v ffmpeg)
---

# Release Video

Generate a 15–30 second product-update video from a changelog or GitHub release body via the `release2reel` CLI.

## Usage

```
release2reel <changelog-or-release-body> --tag <vX.Y.Z> [flags]
```

## Preflight

1. `command -v ffmpeg` — required for assembly. If missing, tell the user to install it (`apt install ffmpeg` / `brew install ffmpeg`).
2. `pip install git+https://github.com/soos3d/release2reel.git` if the CLI is not installed.
3. `RUNWAYML_API_SECRET` must be set for real generation. If it is not set, offer `--dry-run` (shot list + cost, spends nothing) or `--mock` (full pipeline, placeholder clips) instead — never ask the user to paste a key into chat.
4. `ANTHROPIC_API_KEY` is optional; when absent, always pass `--no-llm`.

## Security Notes

- Never echo API keys. The CLI reads them from the environment.
- Real runs spend Runway credits (~195 credits ≈ $1.95 per default video). **Always run `--dry-run` first and show the user the cost estimate before a real run.**
- Generated media comes from a generative model — have the user review the output before publishing it.

## Parameters

| Flag | Default | Notes |
|---|---|---|
| `--tag` | (required) | Selects the changelog section; names the outputs |
| `--scenes` | 3 | Max highlights → scenes |
| `--seconds` | 5 | Per-scene clip length (2–10) |
| `--out` | `out/` | Output directory |
| `--style-ref` | — | Brand image URL for consistent palette |
| `--no-llm` | off | Deterministic templates; required when no Anthropic key |
| `--dry-run` | off | Print shot list + cost, spend nothing |
| `--mock` | off | Placeholder clips, zero API calls |

## Examples

```bash
# Cost preview before anything else
release2reel CHANGELOG.md --tag v2.1.0 --dry-run

# Cheapest real iteration while tuning prompts (29 credits)
release2reel CHANGELOG.md --tag v2.1.0 --scenes 1 --seconds 2

# Full video with brand palette
release2reel CHANGELOG.md --tag v2.1.0 --style-ref https://example.com/brand.png

# From a GitHub release body on stdin
gh release view v2.1.0 --json body -q .body | release2reel - --tag v2.1.0
```

## Output

`out/<tag>.mp4` (720p, ≤30s) and `out/<tag>.gif` (README-embeddable). Report both paths to the user when done.

## Common Failures

| Symptom | Fix |
|---|---|
| `RUNWAYML_API_SECRET is not set` | Export the key, or use `--mock` / `--dry-run` |
| `no highlights found for <tag>` | The tag doesn't match a changelog heading — check `--tag` against the file |
| `ffmpeg not found` | Install ffmpeg |
| A scene warning + partial video | Normal graceful degradation: a failed generation was retried once, then skipped |
| `TaskFailedError` on every scene | Check credit balance and key validity at dev.runwayml.com |
