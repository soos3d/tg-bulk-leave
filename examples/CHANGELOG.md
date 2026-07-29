# Changelog

## [2.1.0] - 2026-07-20

### Added

- feat: streaming mode — process video chunks as they arrive instead of buffering the full file
- feat(cli): new `--watch` flag re-runs the pipeline when the input changes

### Changed

- perf: transcoding is now 3.2x faster on multi-core machines thanks to parallel segment encoding
- refactor: split the encoder into composable stages

### Fixed

- fix: resolved a race condition that dropped the final frame on short clips ([#142](https://github.com/example/example/issues/142))
- fix: `--output` paths with spaces no longer crash the muxer

## [2.0.0] - 2026-05-02

### Breaking

- feat!: the config file format moved from JSON to TOML — run `migrate-config` to convert

### Added

- feat: hardware-accelerated decoding on Apple Silicon
