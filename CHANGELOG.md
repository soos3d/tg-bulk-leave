# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-27

First packaged release. Previously a personal single-file script.

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

### Unchanged (deliberately)

- Dry run is still the default; `--execute` still requires typing `LEAVE`.
- Session storage location (`~/.config/tg_cleanup/`, `TG_SESSION` override)
  and its owner-only permission handling.
- Rate-limit pacing (2.5–5.0s between leaves), the FloodWait abort cap, CSV
  escaping, and per-iteration log flushing. These safety floors are not
  configurable, by design.
