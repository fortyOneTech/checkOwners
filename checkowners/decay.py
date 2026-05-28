"""Expertise decay detector.

Surfaces contributors whose expertise on a path is stale: they committed
heavily in the past but not within the configured threshold window.
"""

from __future__ import annotations

from dataclasses import dataclass

from checkowners.models import Config, DecayWarning, OwnershipMap, PathOwnership


@dataclass(frozen=True)
class DecayReport:
    warning: DecayWarning
    recommended_transfer: str | None
    departed: bool


def detect_decay(
    ownership: OwnershipMap,
    config: Config,
) -> tuple[DecayReport, ...]:
    """Walk the ownership map and report every decay warning with a recommendation."""
    if not config.decay.alert_on_decay:
        return ()
    reports: list[DecayReport] = []
    active_handles = _active_handles(ownership, config.analysis.confidence_threshold)
    for path, po in ownership.paths.items():
        for warning in po.decay_warnings:
            recommended = _recommend_transfer(
                ownership=ownership,
                path=path,
                decaying_handle=warning.handle,
                confidence_threshold=config.analysis.confidence_threshold,
            )
            departed = warning.handle not in active_handles
            reports.append(
                DecayReport(
                    warning=warning,
                    recommended_transfer=recommended,
                    departed=departed,
                )
            )
    reports.sort(key=lambda r: (-r.warning.days_since_last_commit, r.warning.path))
    return tuple(reports)


def _active_handles(
    ownership: OwnershipMap,
    confidence_threshold: float,
) -> frozenset[str]:
    """Handles that still appear as an owner anywhere with high enough confidence."""
    handles: set[str] = set()
    for po in ownership.paths.values():
        for owner in po.owners:
            if owner.confidence >= confidence_threshold and not _is_decaying(po, owner.handle):
                handles.add(owner.handle)
    return frozenset(handles)


def _is_decaying(po: PathOwnership, handle: str) -> bool:
    return any(w.handle == handle for w in po.decay_warnings)


def _recommend_transfer(
    ownership: OwnershipMap,
    path: str,
    decaying_handle: str,
    confidence_threshold: float,
) -> str | None:
    """Pick the highest-confidence active owner of `path` other than the decaying one."""
    po = ownership.paths.get(path)
    if po is None:
        return None
    decaying_handles = {w.handle for w in po.decay_warnings}
    candidates = [
        o
        for o in po.owners
        if o.handle != decaying_handle
        and o.handle not in decaying_handles
        and o.confidence >= confidence_threshold
    ]
    if candidates:
        return candidates[0].handle
    # Fallback: walk other paths and rank by adjacency depth, then confidence.
    cross_path_candidates: dict[str, tuple[int, float]] = {}
    for other_path, other_po in ownership.paths.items():
        if other_path == path:
            continue
        adjacency = _common_prefix_depth(path, other_path)
        if adjacency < 1:
            continue
        other_decaying = {w.handle for w in other_po.decay_warnings}
        for owner in other_po.owners:
            if owner.handle == decaying_handle:
                continue
            if owner.handle in other_decaying:
                continue
            if owner.confidence < confidence_threshold:
                continue
            current = cross_path_candidates.get(owner.handle)
            score = (adjacency, owner.confidence)
            if current is None or score > current:
                cross_path_candidates[owner.handle] = score
    if not cross_path_candidates:
        return None
    best = max(cross_path_candidates.items(), key=lambda kv: kv[1])
    return best[0]


def _common_prefix_depth(a: str, b: str) -> int:
    """Number of leading directory components shared between two paths."""
    a_parts = a.lstrip("/").split("/")[:-1]
    b_parts = b.lstrip("/").split("/")[:-1]
    common = 0
    for x, y in zip(a_parts, b_parts, strict=False):
        if x != y:
            break
        common += 1
    return common


def _path_is_adjacent(a: str, b: str) -> bool:
    """Adjacency heuristic: share at least one common directory component."""
    return _common_prefix_depth(a, b) >= 1
