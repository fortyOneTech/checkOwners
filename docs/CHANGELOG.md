# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `docs/` directory housing detailed reference: `USAGE.md`, `FAQ.md`, `CONTRIBUTING.md`, this `CHANGELOG.md`, and the project `CODEOWNERS` (moved from `.github/CODEOWNERS`).
- Mermaid pipeline diagram in the README showing the flow from git history through `analyze`, the persisted state, and the seven downstream commands.

### Changed
- README slimmed to intro, install, quick start, command table, and links to the new `docs/`.
- All Markdown across the repo follows a tightened style: no em dashes, no typographic `--` separators, multi-entry bullets only.

### Fixed
- CI smoke job: `pip install "dist/checkowners-"*"-py3-none-any.whl[graph]"` failed because bash treated `[graph]` as a glob character class and never expanded the wildcard. The wheel path is now resolved via `ls` before installation.

## [0.3.0] - 2026-05-28

### Added
- Confidence scoring on every path-owner pair. Score is a weighted blend of four signals: commit recency (exponential decay), commit frequency, blame coverage, and PR review activity (last one only when `github.api_enabled`).
- Bus factor calculation per path with backup-reviewer suggestions, plus `checkowners bus-factor [<path>] [--all]`.
- Expertise decay detection that distinguishes dormant from departed owners, recommends transfer targets, and exposes them through `checkowners decay`.
- Knowledge graph builder backed by an optional `networkx` extra: `pip install "checkowners[graph]"`. Render in the terminal or export to DOT via `checkowners graph [--export dot]`.
- Per-path expertise ranking via `checkowners expertise <path>`.
- Team topology inference from commit co-occurrence, with reconciliation against declared GitHub teams when `api_enabled`. Exposed as `checkowners topology`.
- PR review load balancer that detects overloaded reviewers and suggests redistribution. Exposed as `checkowners balance`.
- Onboarding path generator that walks the knowledge graph from broad-ownership files to deep-expertise files and emits a Markdown checklist via `checkowners onboard <path>`.
- Persistent state cache at `~/.checkowners/state.json` (schema v2), with `CHECKOWNERS_STATE_DIR` override for CI and tests.
- Composite GitHub Action (`action.yml`) exposing `checkowners_drift`, `bus_factor_summary`, and `decay_summary` outputs; example workflow at `.github/workflows/checkowners-example.yml`.
- Drift severity tiers (`low` / `medium` / `high` / `critical`) computed from the max confidence delta plus bus-factor and decay signals; `notifications.severity_threshold` gates webhook delivery.
- Config sections `scoring`, `decay`, `bus_factor` and new fields on existing sections (`confidence_threshold`, `min_confidence_delta`, `include_confidence`, `severity_threshold`, `github.api_enabled`).

### Changed
- `analysis.lookback_days` default lifted from 180 to 365.
- `analysis.top_n_owners` default lifted from 2 to 3.
- `paths.exclude` default now includes `node_modules/**`.
- `OwnershipMap` reshaped to carry `PathOwnership` entries (confidence-scored owners, bus factor, decay warnings).
- `DriftResult` now carries `DriftEntry` tuples with per-entry confidence delta and reason.
- `notify` payload includes severity, max delta, and per-entry bus factor / decay flags.

### Fixed
- `validate` strips inline confidence comments so `output.include_confidence: true` does not fail the validator. Caught while dogfooding.

### Security
- `github.token` is now refused inside `.github/checkowners.yml`. `load_config` raises a clear error if the field is present, since that file gets pushed to GitHub. The only supported way to provide a token is the `GITHUB_TOKEN` environment variable.

## [0.2.0] - 2026-05-26

### Added
- GitHub `@handle` mapping: commit emails are looked up against the GitHub user-search API and rewritten to `@username` when a match is found.
- Team and subteam resolution: owner sets whose handles are a subset of an org team collapse to `@org/team-slug`, with the most deeply-nested matching team winning.
- CODEOWNERS path auto-detection across `.github/CODEOWNERS`, root `CODEOWNERS`, and `docs/CODEOWNERS` in priority order.

## [0.1.1] - 2026-05-26

### Fixed
- Deleted files are no longer carried into the generated CODEOWNERS; `analyze` filters out paths that no longer exist on disk.

### Changed
- Repo now dogfoods its own generated CODEOWNERS.

## [0.1.0] - 2026-05-26

### Added
- Initial CLI: `analyze`, `generate`, `print`, `validate`, `drift`, `notify`, `sync`.
- Drift detection with three modes (`commit`, `repo`, `both`) and GITHUB_OUTPUT integration.
- Webhook notifications on drift events.
- Syntax-only CODEOWNERS validator.
- Packaging via hatch; published to PyPI under `checkowners`.
- CI workflow running tests and lint across Python 3.11, 3.12, 3.13.

[Unreleased]: https://github.com/smusali/checkowners/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/smusali/checkowners/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/smusali/checkowners/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/smusali/checkowners/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/smusali/checkowners/releases/tag/v0.1.0
