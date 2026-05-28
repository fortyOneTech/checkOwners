"""Bus factor analysis per path with backup-reviewer recommendations."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from checkowners.models import BusFactor, BusFactorConfig, Config, OwnershipMap

Tier = Literal["critical", "warning", "ok"]


@dataclass(frozen=True)
class BusFactorReport:
    entries: tuple[BusFactor, ...]
    repo_average: float

    @property
    def critical_paths(self) -> tuple[str, ...]:
        return tuple(e.path for e in self.entries if self.tier_for(e.bus_factor) == "critical")


    def tier_for(self, bus_factor: int) -> Tier:
        # Method preserved for explicit per-entry tier lookups by callers.
        return _classify(
            bus_factor,
            critical_threshold=_DEFAULT_CONFIG.critical_threshold,
            warn_threshold=_DEFAULT_CONFIG.warn_threshold,
        )


_DEFAULT_CONFIG = BusFactorConfig()


def compute_bus_factor(
    ownership: OwnershipMap,
    config: Config,
    *,
    target: str | None = None,
) -> BusFactorReport:
    """Compute bus factor entries for every path matching `target` (or all paths)."""
    threshold = config.analysis.confidence_threshold
    entries: list[BusFactor] = []
    for path, po in ownership.paths.items():
        if target is not None and not _matches(path, target):
            continue
        qualified = tuple(
            o.handle for o in po.owners if o.confidence >= threshold
        )
        backups = _recommend_backups(ownership, path, qualified, threshold)
        entries.append(
            BusFactor(
                path=path,
                bus_factor=po.bus_factor,
                contributors_above_threshold=qualified,
                recommended_backups=backups,
            )
        )
    entries.sort(key=lambda e: (e.bus_factor, e.path))
    repo_average = (
        round(sum(e.bus_factor for e in entries) / len(entries), 2) if entries else 0.0
    )
    return BusFactorReport(entries=tuple(entries), repo_average=repo_average)


def classify(bus_factor: int, config: BusFactorConfig) -> Tier:
    """Map a bus factor value to a severity tier."""
    return _classify(
        bus_factor,
        critical_threshold=config.critical_threshold,
        warn_threshold=config.warn_threshold,
    )


def _classify(
    bus_factor: int,
    *,
    critical_threshold: int,
    warn_threshold: int,
) -> Tier:
    if bus_factor <= critical_threshold:
        return "critical"
    if bus_factor <= warn_threshold:
        return "warning"
    return "ok"


def _matches(path: str, target: str) -> bool:
    """Match concrete paths, directory prefixes, and segment-aware globs."""
    normalized_path = path.lstrip("/")
    normalized_target = target.lstrip("/")
    if normalized_target == normalized_path:
        return True
    if normalized_target.endswith("/"):
        return normalized_path.startswith(normalized_target)
    if _is_glob(normalized_target):
        if PurePosixPath(normalized_path).match(normalized_target):
            return True
        no_slash = "/" not in normalized_target
        return no_slash and fnmatch.fnmatch(normalized_path, normalized_target)
    return normalized_path.startswith(normalized_target + "/")


def _is_glob(value: str) -> bool:
    return any(ch in value for ch in ("*", "?", "["))


def _recommend_backups(
    ownership: OwnershipMap,
    path: str,
    qualified: tuple[str, ...],
    threshold: float,
) -> tuple[str, ...]:
    """Suggest contributors who could build up backup expertise."""
    qualified_set = set(qualified)
    candidates: dict[str, float] = {}
    for other_path, po in ownership.paths.items():
        if other_path == path:
            continue
        if _common_prefix_depth(path, other_path) < 1:
            continue
        for owner in po.owners:
            if owner.handle in qualified_set:
                continue
            if owner.confidence < threshold:
                continue
            current = candidates.get(owner.handle, 0.0)
            if owner.confidence > current:
                candidates[owner.handle] = owner.confidence
    ordered = sorted(candidates.items(), key=lambda kv: (-kv[1], kv[0]))
    return tuple(handle for handle, _ in ordered[:3])


def _common_prefix_depth(a: str, b: str) -> int:
    a_parts = a.lstrip("/").split("/")[:-1]
    b_parts = b.lstrip("/").split("/")[:-1]
    common = 0
    for x, y in zip(a_parts, b_parts, strict=False):
        if x != y:
            break
        common += 1
    return common
