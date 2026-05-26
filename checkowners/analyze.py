"""Git history analysis for ownership inference."""

from __future__ import annotations

import fnmatch
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from checkowners.models import Config, OwnershipMap

_COMMIT_SENTINEL = "COMMIT_START"


def analyze_ownership(repo_root: Path, config: Config) -> OwnershipMap:
    """Analyze git history and return an ownership map."""
    history = _get_commit_history(repo_root, config.analysis.lookback_days)
    counts = _count_ownership(history)
    filtered = _filter_excluded(counts, config.paths.exclude)
    selected = _select_top_owners(
        filtered, config.analysis.min_commits, config.analysis.top_n_owners
    )
    return OwnershipMap(owners=selected, last_analyzed=datetime.now(UTC))


def _get_commit_history(
    repo_root: Path, since_days: int
) -> list[tuple[str, tuple[str, ...]]]:
    """Run git log and parse (author, changed_files) pairs."""
    result = subprocess.run(
        [
            "git",
            "log",
            f"--format={_COMMIT_SENTINEL}%n%ae",
            "--name-only",
            f"--since={since_days} days ago",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=True,
    )
    return _parse_log_output(result.stdout)


def _parse_log_output(stdout: str) -> list[tuple[str, tuple[str, ...]]]:
    """Parse git log output into (author, files) pairs."""
    if not stdout.strip():
        return []
    chunks = stdout.split(_COMMIT_SENTINEL)
    commits: list[tuple[str, tuple[str, ...]]] = []
    for chunk in chunks:
        lines = [line for line in chunk.strip().splitlines() if line.strip()]
        if not lines:
            continue
        author = lines[0]
        files = tuple(line for line in lines[1:] if line)
        if files:
            commits.append((author, files))
    return commits


def _count_ownership(
    history: list[tuple[str, tuple[str, ...]]],
) -> dict[str, dict[str, int]]:
    """Count commits per author per file path."""
    counts: dict[str, dict[str, int]] = {}
    for author, files in history:
        for file_path in files:
            if file_path not in counts:
                counts[file_path] = {}
            counts[file_path][author] = counts[file_path].get(author, 0) + 1
    return counts


def _filter_excluded(
    counts: dict[str, dict[str, int]],
    exclude_patterns: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    """Remove paths matching exclusion patterns."""
    return {
        path: authors
        for path, authors in counts.items()
        if not _is_excluded(path, exclude_patterns)
    }


def _is_excluded(path: str, patterns: tuple[str, ...]) -> bool:
    """Check if a path matches any exclusion pattern."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _select_top_owners(
    counts: dict[str, dict[str, int]],
    min_commits: int,
    top_n: int,
) -> dict[str, tuple[str, ...]]:
    """Apply min_commits filter and select top-N owners per path."""
    result: dict[str, tuple[str, ...]] = {}
    for path, authors in counts.items():
        qualified = {
            author: count for author, count in authors.items() if count >= min_commits
        }
        if not qualified:
            continue
        sorted_owners = sorted(qualified.items(), key=lambda item: (-item[1], item[0]))
        result[path] = tuple(author for author, _ in sorted_owners[:top_n])
    return result
