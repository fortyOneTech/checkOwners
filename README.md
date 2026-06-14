# checkowners

[![CI](https://github.com/smusali/checkowners/actions/workflows/ci.yml/badge.svg)](https://github.com/smusali/checkowners/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/checkowners.svg)](https://pypi.org/project/checkowners/)
[![PyPI downloads](https://img.shields.io/pypi/dm/checkowners.svg)](https://pypi.org/project/checkowners/)
[![Python versions](https://img.shields.io/pypi/pyversions/checkowners.svg)](https://pypi.org/project/checkowners/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Infer CODEOWNERS from git history with confidence scoring, a knowledge graph, expertise decay detection, bus factor analysis, team topology inference, review load balancing, and onboarding paths. Pure git, no LLMs. CI-native: structured JSON output, GITHUB_OUTPUT integration, composite GitHub Action.

> Ownership is not binary. checkOwners is the first CODEOWNERS tool that treats it as a confidence-scored spectrum and surfaces the second-order risks (bus factor, expertise decay, team topology) that come with it.

## How it works

`checkowners analyze` reads `git log` and `git blame` into a confidence-scored ownership map cached at `~/.checkowners/state.json`. From that map, `generate` writes a CODEOWNERS file and `drift` compares it against the committed one, while `bus-factor`, `decay`, `topology`, `balance`, `onboard`, and `trends` emit their own reports. In CI, the composite GitHub Action runs the same flow and writes structured `GITHUB_OUTPUT`. See [docs/USAGE.md](docs/USAGE.md) for the full pipeline and a diagram.

## Installation

```bash
pip install checkowners               # core CLI
pip install "checkowners[graph]"      # adds networkx-backed graph / topology / onboard
```

## Quick start

```bash
# Confidence-scored ownership inference
checkowners analyze

# Write CODEOWNERS with owners ranked by expertise confidence
checkowners generate

# Compare inferred vs current CODEOWNERS, ranked by confidence delta
checkowners drift

# Validate syntax (no git access)
checkowners validate
```

All commands accept `--json` and persist their results to `~/.checkowners/state.json` so downstream commands can reuse the analysis.

## Commands

| Command | What it does |
|---------|--------------|
| `checkowners analyze` | Infer ownership with confidence scores, bus factor, decay warnings |
| `checkowners generate` | Write CODEOWNERS, ordered by confidence; optional inline annotations |
| `checkowners print` | Print inferred ownership to stdout |
| `checkowners validate` | Validate existing CODEOWNERS syntax |
| `checkowners drift` | Compare inferred vs current; severity + max confidence delta |
| `checkowners notify` | POST drift to a webhook gated by `severity_threshold` |
| `checkowners sync` | Generate CODEOWNERS and commit the result |
| `checkowners expertise <path>` | Per-path expertise ranking |
| `checkowners decay` | Detect dormant owners; recommend transfers |
| `checkowners graph [--export dot]` | Render the contributor / file / team graph |
| `checkowners bus-factor [<path>] [--all]` | Per-path bus factor with backup-reviewer suggestions |
| `checkowners topology` | Infer team boundaries from commit co-occurrence |
| `checkowners balance` | Detect overloaded reviewers and propose rebalancing |
| `checkowners onboard <path>` | Generate a learning path from broad-ownership to deep-expertise files |
| `checkowners trends [--periods N] [--period-days D]` | Show how ownership confidence and bus factor have evolved over time |
| `checkowners github-action` | Run the full CI flow and write `GITHUB_OUTPUT`; used by the composite Action |

## Documentation

- [docs/USAGE.md](docs/USAGE.md): full configuration reference, confidence scoring formula, drift severity tiers, GitHub Actions integration, comparison table.
- [docs/FAQ.md](docs/FAQ.md): identity (usernames vs emails, teams + subteams), GitHub API access, file locations, tuning, troubleshooting.
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md): dev setup, commands, conventional commits, code conventions, PR workflow.
- [docs/CHANGELOG.md](docs/CHANGELOG.md): release history.

## License

MIT
