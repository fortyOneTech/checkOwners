"""Per-path expertise ranking from a confidence-scored ownership map."""

from __future__ import annotations

import fnmatch
from datetime import datetime

from checkowners.models import ExpertiseRank, OwnershipMap


def rank_expertise(
    ownership: OwnershipMap,
    target: str,
) -> tuple[ExpertiseRank, ...]:
    """Rank contributors who have expertise in `target`.

    `target` may be a concrete path or a fnmatch-style glob. Multiple
    PathOwnerships matching the target are merged: a contributor's
    rank is the max confidence across the matched paths, with commits
    summed and last_commit set to the most recent.
    """
    aggregated: dict[str, ExpertiseRank] = {}
    for path, po in ownership.paths.items():
        if not _matches(path, target):
            continue
        for owner in po.owners:
            existing = aggregated.get(owner.handle)
            if existing is None:
                aggregated[owner.handle] = ExpertiseRank(
                    handle=owner.handle,
                    confidence=owner.confidence,
                    commits=owner.commits,
                    last_commit=owner.last_commit,
                )
                continue
            new_confidence = max(existing.confidence, owner.confidence)
            new_commits = existing.commits + owner.commits
            new_last = _max_dt(existing.last_commit, owner.last_commit)
            aggregated[owner.handle] = ExpertiseRank(
                handle=owner.handle,
                confidence=new_confidence,
                commits=new_commits,
                last_commit=new_last,
            )
    ranked = sorted(aggregated.values(), key=lambda r: (-r.confidence, -r.commits, r.handle))
    return tuple(ranked)


def _matches(path: str, target: str) -> bool:
    """Match a path against a target path or glob."""
    normalized_target = target.lstrip("/")
    normalized_path = path.lstrip("/")
    if normalized_target == normalized_path:
        return True
    if fnmatch.fnmatch(normalized_path, normalized_target):
        return True
    if not normalized_target.endswith("/") and not _is_glob(normalized_target):
        target_with_slash = normalized_target + "/"
        if normalized_path == normalized_target or normalized_path.startswith(target_with_slash):
            return True
    if normalized_target.endswith("/"):
        return normalized_path.startswith(normalized_target)
    return False


def _is_glob(value: str) -> bool:
    return any(ch in value for ch in ("*", "?", "["))


def _max_dt(a: datetime | None, b: datetime | None) -> datetime | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b
