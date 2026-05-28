"""Drift detection between inferred ownership and current CODEOWNERS."""

from __future__ import annotations

import json
import os
from pathlib import Path

from checkowners.models import (
    Config,
    DriftEntry,
    DriftMode,
    DriftResult,
    OwnerEntry,
    OwnershipMap,
    PathOwnership,
)

_DEFAULT_CODEOWNERS_PATH = ".github/CODEOWNERS"


def detect_drift(
    repo_root: Path,
    ownership: OwnershipMap,
    config: Config,
    *,
    codeowners_path: Path | None = None,
) -> DriftResult:
    """Compare inferred ownership against current CODEOWNERS."""
    target = codeowners_path or (repo_root / _DEFAULT_CODEOWNERS_PATH)
    current = _parse_codeowners(target)
    inferred = _normalize_inferred(ownership)
    result = _compare(current, inferred, config.drift.mode, config.drift.min_confidence_delta)
    _write_github_output(result)
    return result


def _parse_codeowners(codeowners_path: Path) -> dict[str, tuple[str, ...]]:
    """Parse existing CODEOWNERS file into path -> owner handles mapping."""
    if not codeowners_path.exists():
        return {}
    entries: dict[str, tuple[str, ...]] = {}
    for raw_line in codeowners_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            path = parts[0]
            owners = tuple(parts[1:])
            entries[path] = owners
    return entries


def _normalize_inferred(ownership: OwnershipMap) -> dict[str, PathOwnership]:
    """Normalize inferred ownership paths to match CODEOWNERS leading-slash format."""
    normalized: dict[str, PathOwnership] = {}
    for path, path_ownership in ownership.paths.items():
        key = path if path.startswith("/") else f"/{path}"
        normalized[key] = path_ownership
    return normalized


def _compare(
    current: dict[str, tuple[str, ...]],
    inferred: dict[str, PathOwnership],
    mode: DriftMode,
    min_delta: float,
) -> DriftResult:
    """Compare current CODEOWNERS against inferred PathOwnerships."""
    stale: list[DriftEntry] = []
    missing: list[DriftEntry] = []
    changed_seen: dict[str, DriftEntry] = {}

    if mode in ("repo", "both"):
        for path in sorted(current):
            if path not in inferred:
                stale.append(
                    DriftEntry(
                        path=path,
                        confidence_delta=1.0,
                        reason="path not in inferred ownership",
                    )
                )
            else:
                entry = _maybe_changed(path, current[path], inferred[path], min_delta)
                if entry is not None:
                    changed_seen[path] = entry

    if mode in ("commit", "both"):
        for path in sorted(inferred):
            if path not in current:
                missing.append(
                    DriftEntry(
                        path=path,
                        confidence_delta=_top_confidence(inferred[path].owners),
                        reason="path missing from CODEOWNERS",
                        bus_factor=inferred[path].bus_factor,
                        decay=bool(inferred[path].decay_warnings),
                    )
                )
            else:
                entry = _maybe_changed(path, current[path], inferred[path], min_delta)
                if entry is not None:
                    changed_seen.setdefault(path, entry)

    changed = tuple(changed_seen[path] for path in sorted(changed_seen))
    stale_sorted = _sort_by_delta(stale)
    missing_sorted = _sort_by_delta(missing)
    return DriftResult(
        stale=stale_sorted,
        missing=missing_sorted,
        changed=changed,
        drift_detected=bool(stale_sorted or missing_sorted or changed),
    )


def _maybe_changed(
    path: str,
    current_owners: tuple[str, ...],
    inferred: PathOwnership,
    min_delta: float,
) -> DriftEntry | None:
    inferred_handles = tuple(o.handle for o in inferred.owners)
    if set(current_owners) == set(inferred_handles):
        return None
    delta = _confidence_delta(current_owners, inferred.owners)
    if delta < min_delta:
        return None
    return DriftEntry(
        path=path,
        confidence_delta=delta,
        reason="owner set or ranking changed",
        bus_factor=inferred.bus_factor,
        decay=bool(inferred.decay_warnings),
    )


def _confidence_delta(
    current_owners: tuple[str, ...],
    inferred_owners: tuple[OwnerEntry, ...],
) -> float:
    """Aggregate per-owner confidence delta between current and inferred sets."""
    inferred_map = {o.handle: o.confidence for o in inferred_owners}
    inferred_set = set(inferred_map)
    current_set = set(current_owners)
    added = inferred_set - current_set
    removed = current_set - inferred_set
    delta_added = sum(inferred_map[h] for h in added)
    delta_removed = float(len(removed))
    if not added and not removed:
        return 0.0
    total = delta_added + delta_removed
    return min(1.0, total)


def _top_confidence(owners: tuple[OwnerEntry, ...]) -> float:
    if not owners:
        return 0.0
    return max(o.confidence for o in owners)


def _sort_by_delta(entries: list[DriftEntry]) -> tuple[DriftEntry, ...]:
    entries.sort(key=lambda e: (-abs(e.confidence_delta), e.path))
    return tuple(entries)


def _write_github_output(result: DriftResult) -> None:
    """Write drift result to GITHUB_OUTPUT if running in Actions."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    payload = json.dumps(
        {
            "drift_detected": result.drift_detected,
            "max_confidence_delta": result.max_confidence_delta,
            "stale": [_entry_payload(e) for e in result.stale],
            "missing": [_entry_payload(e) for e in result.missing],
            "changed": [_entry_payload(e) for e in result.changed],
        }
    )
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"checkowners_drift={payload}\n")


def _entry_payload(entry: DriftEntry) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": entry.path,
        "confidence_delta": entry.confidence_delta,
        "reason": entry.reason,
    }
    if entry.bus_factor is not None:
        payload["bus_factor"] = entry.bus_factor
    if entry.decay:
        payload["decay"] = entry.decay
    return payload
