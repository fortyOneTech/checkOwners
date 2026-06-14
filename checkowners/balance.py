"""PR review load analysis with rebalancing recommendations.

When github.api_enabled and a token are configured the analyzer reads
review counts straight from the GitHub PR review API. Otherwise it falls
back to commit-author frequency from the ownership map, which is a
strictly weaker but always-available signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from checkowners.models import Config, OwnershipMap

if TYPE_CHECKING:
    from github import Github


_MAX_INCREASE_FRACTION: float = 0.30
_OVERLOAD_FACTOR: float = 2.0


@dataclass(frozen=True)
class ReviewLoad:
    handle: str
    reviews: int


@dataclass(frozen=True)
class RebalanceSuggestion:
    overloaded: str
    candidate: str
    confidence: float
    proposed_shift: int


@dataclass(frozen=True)
class BalanceReport:
    loads: tuple[ReviewLoad, ...]
    average: float
    overloaded: tuple[ReviewLoad, ...]
    suggestions: tuple[RebalanceSuggestion, ...]
    source: str  # "github_api" or "git_authorship"


def analyze_balance(
    ownership: OwnershipMap,
    config: Config,
    *,
    review_counts: dict[str, int] | None = None,
) -> BalanceReport:
    """Compute review load distribution and rebalancing suggestions."""
    if review_counts is None:
        counts, source = _gather_counts(ownership, config)
    else:
        counts, source = dict(review_counts), "external"
    if not counts:
        return BalanceReport(
            loads=(),
            average=0.0,
            overloaded=(),
            suggestions=(),
            source=source,
        )
    loads = tuple(
        ReviewLoad(handle=handle, reviews=count)
        for handle, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    average = round(sum(load.reviews for load in loads) / len(loads), 2)
    overloaded = tuple(
        load for load in loads if load.reviews >= _OVERLOAD_FACTOR * average and average > 0
    )
    suggestions = _suggest(ownership, loads, overloaded, config.analysis.confidence_threshold)
    return BalanceReport(
        loads=loads,
        average=average,
        overloaded=overloaded,
        suggestions=suggestions,
        source=source,
    )


def _gather_counts(
    ownership: OwnershipMap,
    config: Config,
) -> tuple[dict[str, int], str]:
    if config.github.api_enabled and config.github.org:
        counts = _gather_from_github(config)
        if counts:
            return counts, "github_api"
    return _gather_from_authorship(ownership), "git_authorship"


def _gather_from_authorship(ownership: OwnershipMap) -> dict[str, int]:
    counts: dict[str, int] = {}
    for po in ownership.paths.values():
        for owner in po.owners:
            counts[owner.handle] = counts.get(owner.handle, 0) + owner.commits
    return counts


def _gather_from_github(config: Config) -> dict[str, int]:
    try:
        from checkowners.github import (  # noqa: PLC0415
            get_github_client,
            get_github_token,
        )
    except ImportError:
        return {}
    token = get_github_token(config.github.token)
    if not token:
        return {}
    client = get_github_client(token)
    if client is None:
        return {}
    return _fetch_review_counts(client, config.github.org)


def _fetch_review_counts(client: Github, org: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        github_org = client.get_organization(org)
        for repo in github_org.get_repos():
            for pull in repo.get_pulls(state="closed"):
                for review in pull.get_reviews():
                    handle = f"@{review.user.login}" if review.user else None
                    if handle:
                        counts[handle] = counts.get(handle, 0) + 1
    except Exception:  # noqa: BLE001
        return {}
    return counts


def _suggest(
    ownership: OwnershipMap,
    loads: tuple[ReviewLoad, ...],
    overloaded: tuple[ReviewLoad, ...],
    confidence_threshold: float,
) -> tuple[RebalanceSuggestion, ...]:
    load_map = {load.handle: load.reviews for load in loads}
    suggestions: list[RebalanceSuggestion] = []
    qualified_pairs = _qualified_pairs(ownership, confidence_threshold)
    for overloaded_load in overloaded:
        for candidate, candidate_confidence in qualified_pairs.get(
            overloaded_load.handle, []
        ):
            if candidate == overloaded_load.handle:
                continue
            candidate_load = load_map.get(candidate, 0)
            allowed_increase = max(1, int(candidate_load * _MAX_INCREASE_FRACTION) or 1)
            proposed = min(allowed_increase, max(1, overloaded_load.reviews // 4))
            suggestions.append(
                RebalanceSuggestion(
                    overloaded=overloaded_load.handle,
                    candidate=candidate,
                    confidence=candidate_confidence,
                    proposed_shift=proposed,
                )
            )
    suggestions.sort(key=lambda s: (-s.confidence, s.overloaded, s.candidate))
    return tuple(suggestions)


def _qualified_pairs(
    ownership: OwnershipMap,
    confidence_threshold: float,
) -> dict[str, list[tuple[str, float]]]:
    """For each handle, neighbors who co-own paths above the confidence threshold."""
    pairs: dict[str, dict[str, float]] = {}
    for po in ownership.paths.values():
        qualified = [
            (o.handle, o.confidence)
            for o in po.owners
            if o.confidence >= confidence_threshold
        ]
        for handle_a, _ in qualified:
            pairs.setdefault(handle_a, {})
            for handle_b, confidence_b in qualified:
                if handle_a == handle_b:
                    continue
                current = pairs[handle_a].get(handle_b, 0.0)
                if confidence_b > current:
                    pairs[handle_a][handle_b] = confidence_b
    return {
        handle: sorted(neighbors.items(), key=lambda kv: -kv[1])
        for handle, neighbors in pairs.items()
    }
