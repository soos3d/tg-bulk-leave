# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Trove classifiers now advertise Python 3.14, which CI has tested since
  0.1.0 but the 0.1.0 metadata omitted.

## [0.1.0] - 2026-07-27

First packaged release, [published to PyPI](https://pypi.org/project/tg-bulk-leave/0.1.0/).
Previously a personal single-file script.

### Added

- Installable package `tg-bulk-leave` with a console entry point
  (`src/` layout, hatchling build; install with `uv tool install`, `pipx`,
  or `pip`). `python -m tg_bulk_leave` also works.
- Keywords and the protected list moved out of the source into a TOML config
  file (`config.toml` in the platform config directory, see
  `config.example.toml`), plus repeatable `--keyword`/`--protected` flags and
  `--config PATH`. `--keyword` replaces the config's keywords for that run;
  `--protected` only ever adds protection.
- Actionable first-run errors: a missing config with no `--keyword` explains
  exactly what to create and where; a typoed config key is rejected instead of
  silently matching nothing.
- MIT license.
- Project infrastructure for a public release: GitHub Actions CI (pytest on
  Python 3.11–3.14, `ruff check`, and a build smoke test of the wheel's entry
  point), a tag-triggered release workflow publishing to PyPI via Trusted
  Publishing, `SECURITY.md` documenting the session-file threat model, and
  `CONTRIBUTING.md` recording the safety invariants a change must not break.
- Dependencies locked in `uv.lock`; the dev toolchain moved from
  `requirements.txt` into a PEP 735 `dev` dependency group (`uv sync --dev`).

### Unchanged (deliberately)

- Dry run is still the default; `--execute` still requires typing `LEAVE`.
- Session storage location (`~/.config/tg_cleanup/`, `TG_SESSION` override)
  and its owner-only permission handling.
- Rate-limit pacing (2.5–5.0s between leaves), the FloodWait abort cap, CSV
  escaping, and per-iteration log flushing. These safety floors are not
  configurable, by design.

[Unreleased]: https://github.com/soos3d/tg-bulk-leave/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/soos3d/tg-bulk-leave/releases/tag/v0.1.0
