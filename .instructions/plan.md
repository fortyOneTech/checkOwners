# checkOwners: Execution Plan

*Internal only. Use alongside the Claude Code `plan` command to plan each step before executing.*

---

## Pre-flight

- Confirm `checkowners` PyPI name is available (HTTP 404 confirmed)
- Confirm `checkowners` GitHub organization/user namespace is available
- Create two public GitHub repos:
  - `checkowners`: Python CLI + PyPI package
  - `checkowners-action`: composite GitHub Action for GitHub Marketplace
- No domain purchase needed (OSS-only product)

---

## GitHub Repo Setup

### `checkowners` repo

- **Description:** `Infer CODEOWNERS from git history with confidence scoring, knowledge graphs, expertise decay detection, bus factor analysis, and team topology inference. CI-native.`
- **Topics:** `codeowners`, `git`, `github-actions`, `ownership`, `drift-detection`, `knowledge-graph`, `bus-factor`, `expertise-decay`, `cli`, `python`, `devtools`, `platform-engineering`, `code-review`
- **Visibility:** Public
- **License:** MIT
- **Default branch:** `main`

### `checkowners-action` repo

- **Description:** `GitHub Action for checkOwners: infer CODEOWNERS from git history, detect drift with confidence scoring, and calculate bus factor in CI.`
- **Topics:** `github-action`, `codeowners`, `ownership-inference`, `drift-detection`, `bus-factor`, `ci`, `devtools`
- **Visibility:** Public
- **License:** MIT
- **Default branch:** `main`

### README badges (both repos)

Include in README header: PyPI version, PyPI monthly downloads, GitHub stars, license, CI status, Python version.

---

## Claude Code Initialization

- **Primary session** (`checkowners` repo): handles all execution steps
  - `cd checkowners && claude` to open Claude Code
  - Run `/init` to auto-generate a base `CLAUDE.md` from the detected project structure
  - Replace the auto-generated `CLAUDE.md` with the prepared `checkOwners/CLAUDE.md` from this ideas repo
  - Place `checkOwners/PRODUCT.md` at the repo root as `PRODUCT.md`
  - Commit both files to `main` before starting any implementation step
- **Secondary session** (`checkowners-action` repo): opened during Step 5 only; simple repo; does not need its own `CLAUDE.md`

---

## Session Workflow

- Use Plan Mode (`Shift+Tab` twice) before every implementation step
- Follow the loop: Explore, Plan, Implement, Commit
- One focused task per Claude Code session
- Run `/compact` when context gets long
- Use `PRODUCT.md` to construct P.R.O.D.U.C.T. prompts

---

## Phase 1: MVP Execution Steps (Week 1)

- **Step 1: Project scaffold**
  - `hatch new checkowners` to generate the initial project structure
  - Write `pyproject.toml` with Typer, Rich, GitPython, PyGithub, PyYAML dependencies; optional extras: `[graph]` for networkx
  - Create the Typer CLI entry point in `checkowners/cli.py` with placeholder subcommands (`analyze`, `generate`, `print`, `validate`, `drift`, `notify`, `sync`, `graph`, `expertise`, `decay`, `topology`, `balance`, `onboard`, `bus-factor`)
  - Implement `config.py`: PyYAML loader for `.github/checkowners.yml` with defaults (lookback_days: 365, min_commits: 3, top_n_owners: 3, confidence_threshold: 0.3, scoring weights, decay threshold, bus factor thresholds)
  - Create `models.py` with `OwnershipMap`, `DriftResult`, `ConfidenceScore`, `ExpertiseRank`, `TeamCluster`, `BusFactor`, `Config` dataclasses
  - Set up pytest harness with `hatch run test` script and `tests/` directory structure

- **Step 2: Git analysis engine with confidence scoring**
  - Implement `analyze.py`: parse `git log` and `git blame` via GitPython and subprocess
  - Build the commit-to-path ownership map with confidence scoring:
    - Commit recency: exponential decay with configurable half-life (default 90 days)
    - Commit frequency: total commits in lookback window
    - Blame coverage: percentage of current lines attributed to contributor
    - Review activity: PR reviews on files in the path (when GitHub API available)
  - Confidence score = weighted average of all factors (configurable weights)
  - Apply default path exclusions from config
  - Implement `expertise.py`: per-path expertise ranking with confidence, recency, and commit count
  - Write `tests/test_analyze.py` and `tests/test_expertise.py` with mocked subprocess calls

- **Step 3: CODEOWNERS generator**
  - Implement `generate.py`: normalize paths, select top-N owners by confidence, write `.github/CODEOWNERS`
  - Prepend machine-generated header
  - Confidence-weighted ordering: highest-confidence owner listed first per path
  - Optional confidence comments: `# @alice (0.92) @bob (0.71)` as inline annotations
  - Support `include_unowned: true/false` for human triage paths
  - Write `tests/test_generate.py`

- **Step 4: Drift detection with confidence delta**
  - Implement `drift.py`: compare `OwnershipMap` from `analyze.py` against current `.github/CODEOWNERS`
  - Detect stale entries, missing entries, and changed paths with confidence delta
  - Priority-ranked drift reports: highest confidence-delta entries first
  - Support all three state machine modes (`commit`, `repo`, `both`)
  - Output JSON diff via `--json` flag; write `GITHUB_OUTPUT` when running in Actions
  - Write `tests/test_drift.py`

- **Step 5a: GitHub Actions integration (before PyPI publish)**
  - Implement the `GITHUB_OUTPUT` writer in `drift.py`
  - Write `action.yml` composite action
  - Add example `.github/workflows/checkowners-example.yml`
  - Open secondary session for `checkowners-action` repo
  - Local smoke-test with `act`

- **Step 5b: GitHub Actions end-to-end test (after PyPI publish)**
  - Restore `pip install checkowners` in `action.yml`
  - Create `v1` release tag on `checkowners-action`; submit to Marketplace

- **Step 6: Notifications + validate + print**
  - Implement `notify.py`: HTTP POST to `webhook_url` on drift events with severity based on confidence delta
  - Implement `validate.py`: syntax-only CODEOWNERS parser; exits non-zero on invalid syntax
  - Implement `checkowners print` command with confidence scores
  - Write `tests/test_validate.py`

- **Step 7: Packaging, README, and smoke-test**
  - Write full `README.md` with badges, install instructions, CLI reference, config reference
  - Include comparison table vs. git-codeowners, codeowners-validator, GitHub native CODEOWNERS
  - Highlight unique features: confidence scoring, knowledge graph, bus factor, expertise decay
  - Run `hatch run test` and confirm 85%+ coverage
  - Run `hatch build` and smoke-test
  - Dogfood: run `checkowners analyze` and `checkowners drift` against the checkowners repo itself

---

## Phase 2: Knowledge Intelligence Execution Steps (Weeks 2-4)

- **Step 8: Expertise decay detection (Week 2)**
  - Implement `decay.py`: flag contributors whose expertise is decaying
  - Configurable decay threshold (default 180 days since last commit)
  - Distinguish "dormant expert" vs. "departed owner"
  - Produce decay reports with recommended ownership transfers
  - `checkowners decay`: Rich table showing decaying expertise with actionable recommendations
  - Write `tests/test_decay.py` with time-manipulated commit histories

- **Step 9: Knowledge graph + bus factor (Week 3)**
  - Implement `graph.py`: build contributor-file-team relationship graph using networkx
  - `checkowners graph`: Rich TUI knowledge graph visualization
  - `checkowners graph --export dot`: DOT format export for Graphviz
  - Implement `busfactor.py`: calculate bus factor per path
  - Paths with bus_factor=1 flagged as critical risk
  - Aggregate bus factor across entire repo
  - Knowledge-sharing recommendations: suggest reviewers to build backup expertise
  - `checkowners bus-factor <path>`, `checkowners bus-factor --all`
  - Write `tests/test_graph.py` and `tests/test_busfactor.py`

- **Step 10: Team topology + review load balancer (Week 4)**
  - Implement `topology.py`: commit co-occurrence clustering to infer team boundaries
  - Compare inferred teams against declared GitHub teams (when API available)
  - Detect cross-team coupling: paths with multi-team contributions
  - `checkowners topology`: Rich table showing inferred teams and their primary paths
  - Implement `balance.py`: PR review load analysis
  - Detect overloaded reviewers (super-reviewer bottleneck)
  - Suggest rebalancing: route reviews to qualified but underutilized contributors
  - `checkowners balance`: Rich table showing review load distribution
  - Write `tests/test_topology.py` and `tests/test_balance.py`

---

## Phase 3: Ecosystem Execution Steps (Months 2-6)

- **Month 2: Onboarding path generator + enhanced CI**
  - Implement `onboard.py`: generate learning paths from ownership graph
  - Paths go from broadly-owned files (easy) to deep-expertise files (complex)
  - Include recommended reviewers and estimated complexity per step
  - Export as Markdown checklist for onboarding docs
  - `checkowners onboard src/payments/`: Rich learning path output
  - Enhanced CI: PR comment integration showing drift summary + bus factor alerts
  - Branch protection integration: fail PR if bus_factor=1 paths are modified without backup reviewer

- **Month 3: GitLab + Bitbucket support**
  - Extend CODEOWNERS format support: GitLab CODEOWNERS syntax, Bitbucket reviewer mapping
  - Abstract git operations to support both GitHub and GitLab APIs
  - CI integration for GitLab CI (.gitlab-ci.yml) and Bitbucket Pipelines
  - Platform-agnostic core with provider-specific adapters

- **Month 4: Historical trend analysis**
  - Ownership confidence trends over time: how has expertise evolved?
  - Expertise growth/decay charts: visualize knowledge transfer patterns
  - Team stability metrics: how often do ownership assignments change?
  - `checkowners trends --period 6m`: Rich charts showing ownership evolution

- **Month 5: IDE extensions**
  - VS Code extension: ownership overlay in editor (who owns this file? confidence score, bus factor)
  - IntelliJ plugin: inline ownership annotations
  - Neovim integration via lua plugin
  - Git blame integration: enhanced blame showing confidence-weighted ownership

- **Month 6: Enterprise features**
  - Multi-repo ownership aggregation: org-wide bus factor dashboard
  - Cross-repo expertise mapping: find experts across the entire org
  - Automated ownership transfer workflows: when expertise decay is detected
  - API for downstream tools (AI code reviewers, PR assignment bots)

---

## Community Building Strategy

### Launch (Week 1-2)
- Hacker News "Show HN" post: "checkOwners: CODEOWNERS inference with confidence scoring, bus factor, and expertise decay detection"
- r/github, r/devops, r/programming subreddits
- Dev.to article: "Why your CODEOWNERS file is lying to you (and how to fix it)"
- GitHub Marketplace listing for the Action

### Growth (Month 1-3)
- Write comparison blog posts: "checkOwners vs. manual CODEOWNERS maintenance"
- Blog post: "How we reduced our review bottleneck by 40% with checkOwners"
- Submit to Awesome lists: awesome-github, awesome-devops, awesome-cli-apps
- Engage with platform engineering communities (Platform Engineering Slack, Team Topologies community)
- Present at DevOpsDays and Platform Engineering meetups

### Sustain (Month 3-6)
- Monthly release cadence with community-requested features
- Contributors guide with "good first issue" labels
- Platform bounties: $50-100 for GitLab/Bitbucket provider implementations
- Partnership outreach: GitHub (co-listed in CODEOWNERS docs), platform engineering tool vendors

---

## Metrics-Driven Iteration

| Metric | Target (Month 1) | Target (Month 3) | Target (Month 6) | Measurement |
|--------|------------------|-------------------|-------------------|-------------|
| PyPI downloads/month | 1,000 | 3,000 | 5,000 | `pypistats overall checkowners` |
| GitHub stars | 100 | 500 | 2,000 | GitHub Insights |
| Active contributors | 3 | 10 | 20 | GitHub contributor graph |
| Marketplace installs | 50 | 100 | 200 | Marketplace analytics |
| Issue response time | <24h | <12h | <8h | GitHub Issues SLA |
| Test coverage | 85% | 90% | 92% | `hatch run test` |
| Platforms supported | 1 (GitHub) | 2 (+ GitLab) | 3 (+ Bitbucket) | Provider count |
| Bus factor alerts accuracy | 90% | 95% | 97% | User feedback |

### Iteration Triggers
- If confidence scoring has poor accuracy: collect user feedback; tune weight parameters; add A/B testing
- If bus factor is too alarming (false positives): add configurable thresholds and confidence bands
- If graph visualization is hard to read: switch to Textual TUI with zoom/pan; add export to SVG
- If GitLab/Bitbucket support is requested frequently: prioritize Month 3 platform expansion
- If Marketplace installs lag: improve action.yml UX; add more example workflows

---

## Dogfooding

After Step 3 (generator) is complete:
- Run `checkowners generate` inside the `checkowners` repo to produce `.github/CODEOWNERS`
- Commit the generated `CODEOWNERS` file to `main`

After Step 4 (drift detection) is complete:
- Make intentional ownership changes and verify drift detection catches them
- Verify confidence delta reporting ranks drift by severity

After Step 8 (expertise decay) is complete:
- Run `checkowners decay` against the checkowners repo
- Create test scenarios with simulated old commits and verify decay detection

After Step 9 (bus factor) is complete:
- Run `checkowners bus-factor --all` against the checkowners repo
- Verify single-contributor paths are flagged as critical

After both PyPI publish and `checkowners-action` `v1` release:
- Add `.github/workflows/checkowners.yml` to the checkowners repo
- Verify CI passes on the first push

---

## Commit Discipline

- Commit after every execution step's deliverable is complete and all tests pass
- Use conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`
- Tag `v0.1.0` after Step 7 (MVP); `v0.2.0` after Step 10 (Phase 2 complete)

---

## Publishing and Distribution

### Publish Order (Critical)

The dogfooding CI workflow references `checkowners/checkowners-action@v1`, which internally runs `pip install checkowners`. Correct sequence:

1. Complete Steps 1-6 and locally smoke-test with the local wheel (Step 5a)
2. Complete Step 7: full README, 85%+ coverage, `hatch build`, local smoke-test
3. `hatch publish` to push `checkowners` to PyPI; tag `v0.1.0`
4. Run Step 5b: restore `pip install checkowners`; create `v1` release tag on `checkowners-action`; submit to Marketplace
5. Only after both 3 and 4: commit `.github/workflows/checkowners.yml`
6. Verify CI passes on the first push

### PyPI

- `hatch build` to produce sdist and wheel in `dist/`
- `hatch publish` to push to PyPI
- Verify optional extras: `pip install checkowners[graph]`

### GitHub Action (Marketplace)

- Publish `checkowners-action` repo with `action.yml` at the root
- Submit to GitHub Marketplace: category `Code quality`
- Branding: `icon: shield`, `color: blue`
- Create versioned release tag (`v1`, `v1.0.0`)

### Announcement Channels (in order)

- Hacker News "Show HN" post with problem/solution framing
- r/github, r/devops, r/programming subreddits
- Dev.to article: "How I built checkOwners: CODEOWNERS inference with knowledge graphs and bus factor"
- GitHub Explore: topics ensure organic surfacing
- Platform Engineering community Slack

### Post-publish Monitoring

- PyPI download stats: `pypistats overall checkowners` weekly
- GitHub Marketplace installs
- Success targets (6 months): 5,000 PyPI downloads/month, 2,000+ GitHub stars, 200+ Marketplace installs, 20+ contributors
- Monitor competitor releases and GitHub CODEOWNERS feature updates

---

## Partnership Opportunities

| Partner | Value Proposition | Outreach Timing |
|---------|------------------|-----------------|
| **GitHub** | Co-listed in CODEOWNERS documentation; recommended tool | Month 2 |
| **GitLab** | CODEOWNERS format support; co-listed in GitLab docs | Month 3 |
| **Team Topologies** | Team topology inference aligns with their methodology | Month 3 |
| **Linear** | Integration for ownership-aware issue assignment | Month 4 |
| **VS Code team** | Extension marketplace listing | Month 5 |
| **Sourcegraph** | Code intelligence integration; knowledge graph overlay | Month 6 |
