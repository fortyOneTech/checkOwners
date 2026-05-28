# FAQ

Common questions about configuring and operating checkowners. For the full configuration reference see [docs/USAGE.md](USAGE.md).

## Ownership identity

### Will the generated CODEOWNERS show GitHub usernames or commit email addresses?

GitHub usernames whenever they can be resolved. `github.resolve_handles` (on by default) takes the commit email of each inferred owner and looks it up via the GitHub user-search API; a successful match becomes `@username`. When the lookup misses (private email, no GitHub account, API unavailable) the entry falls back to the raw email so the output stays usable.

```yaml
github:
  resolve_handles: true  # default
```

### Does it handle GitHub teams and subteams?

Yes. When `github.org` is set and a token is available, `checkowners generate` collects every team in the org (including nested subteams), and any owner set whose handles are a subset of a team's membership is collapsed to that team. The most deeply-nested matching team wins ties, so subteams are preferred over their parents.

```yaml
github:
  org: my-org
  resolve_teams: true    # default; emits @my-org/platform/backend etc.
```

Disable `resolve_teams` if you want raw `@username` entries even when a team would match.

## GitHub API access

### Does checkowners require a GitHub token?

No. The core inference is pure git and runs offline. A token is only needed for three optional features:

| Feature | Config gate | Why a token is needed |
|---------|-------------|-----------------------|
| Email to `@username` resolution | `github.resolve_handles` | GitHub user-search API |
| Team / subteam resolution | `github.resolve_teams` + `github.org` | List org teams + members |
| Review-load + topology reconciliation | `github.api_enabled` | PR review API + team membership |

Without a token you still get confidence-scored ownership, drift detection, bus factor, expertise decay, and onboarding paths; they just operate on email handles and skip the review-activity signal in the confidence score.

### What environment variable holds the token?

`GITHUB_TOKEN` (not `GITHUB_API_KEY`). This is the **only** supported way to provide a token. `github.token` is intentionally **not** accepted in `checkowners.yml` because that file gets committed to git and storing a secret there would publish it to GitHub. `load_config` refuses to load a config that contains `github.token` so a misconfigured repo fails fast instead of silently leaking.

```bash
export GITHUB_TOKEN=ghp_...
checkowners generate
```

In GitHub Actions, `${{ secrets.GITHUB_TOKEN }}` is automatically available; see the composite action documented in [docs/USAGE.md](USAGE.md#github-actions).

### What token scopes are needed?

- Email to username: public `read:user` is sufficient.
- Team resolution: `read:org` so org teams and their members are visible.
- Review-load analysis: `repo` (or fine-grained PR `read` for the org).

A fine-grained PAT scoped to the target org with the minimums above is the recommended setup.

## File locations

### Can the CODEOWNERS file live in the repo root instead of `.github/`?

Yes. `checkowners` auto-detects the file at any of the three locations GitHub itself supports, in priority order:

1. `.github/CODEOWNERS`
2. `CODEOWNERS` (repo root)
3. `docs/CODEOWNERS`

The first one that exists wins for `analyze`, `drift`, `validate`, and `sync`. If none exists, `generate` creates `.github/CODEOWNERS` by default; pass `--codeowners-path` or move the file manually if you want a different layout.

### Where does the config file live?

`.github/checkowners.yml`. There's no auto-detection for the config; it has to live there.

### Where is the state cache?

`~/.checkowners/state.json` (schema v2). Downstream commands (`drift`, `bus-factor`, `decay`, `topology`, `balance`, `onboard`) read it so they don't re-run `git log`. Override the directory with `CHECKOWNERS_STATE_DIR` for CI or tests.

## Inference behavior

### How is confidence computed?

A weighted sum of four signals, each in `[0.0, 1.0]`:

- **Recency**: `exp(-ln 2 × days_since_last_commit / half_life)`. Default half-life is 90 days.
- **Frequency**: contributor's commits on the path divided by the path's max contributor.
- **Blame coverage**: fraction of current lines `git blame --line-porcelain` attributes to the contributor.
- **Review activity**: PR reviews on the path divided by total reviews; `0.0` unless `github.api_enabled` is true.

Weights are configurable under `scoring`. The final score is clamped to `[0.0, 1.0]`; owners below `analysis.confidence_threshold` are dropped from the generated CODEOWNERS.

### Can I tune the inference for a high-turnover team?

Yes. Common tunings:

```yaml
scoring:
  recency_half_life_days: 45   # decay expertise faster
  recency_weight: 0.5          # weigh "what did you touch last month" higher

decay:
  threshold_days: 90           # flag dormant owners after 3 months

analysis:
  confidence_threshold: 0.4    # stricter cutoff
```

### Why are some paths missing from `checkowners analyze`?

Three filters can drop a path: it matches a `paths.exclude` pattern, it no longer exists on disk (deleted files are filtered automatically so CODEOWNERS doesn't pin removed paths), or no contributor reaches `analysis.min_commits` within the lookback window.

## Drift, severity, and CI

### What does drift "severity" mean in CI?

`notify.compute_severity` maps the max confidence delta plus bus-factor / decay flags to a tier:

| Severity | Trigger |
|----------|---------|
| `critical` | Any drift entry has `bus_factor <= 1` or is `decay = true` |
| `high` | `max_confidence_delta >= 0.7` |
| `medium` | `max_confidence_delta >= 0.3` |
| `low` | otherwise |

`notifications.severity_threshold` decides when a webhook fires, and `--json` always includes the severity field so CI workflows can branch on it.

### How do I fail a PR only on critical drift?

The example workflow in `.github/workflows/checkowners-example.yml` does this with `fromJson(steps.checkowners.outputs.checkowners_drift).severity == 'critical'`. The composite action also accepts `fail_on_drift: "false"` if you want to comment without blocking.

## Troubleshooting

### `networkx` is not installed but I want `checkowners graph`.

Install the extra: `pip install "checkowners[graph]"`. The error message points to this too.

### `checkowners drift` complains about lines with `# alice(0.92)`.

You're on an older version that predates the inline-comment fix. Upgrade to v0.3.0+ or strip the annotations by setting `output.include_confidence: false` and regenerating.

### The bus factor report says `repo_average: 1.0`. Is that right?

For a solo-maintainer repo, yes. Bus factor is the number of selected owners with confidence above `analysis.confidence_threshold`; a single committer caps out at 1 per path. Invite a co-owner and let them rack up commits to move the needle.
