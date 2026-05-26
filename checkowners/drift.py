"""Drift detection between inferred ownership and current CODEOWNERS."""

from __future__ import annotations

import json
import os
from pathlib import Path

from checkowners.models import Config, DriftResult, OwnershipMap

_CODEOWNERS_PATH = ".github/CODEOWNERS"


def detect_drift(
    repo_root: Path,
    ownership: OwnershipMap,
    config: Config,
) -> DriftResult:
    """Compare inferred ownership against current CODEOWNERS."""
    current = _parse_codeowners(repo_root)
    inferred = _normalize_inferred(ownership)
    result = _compare(current, inferred, config.drift.mode)
    _write_github_output(result)
    return result


def _parse_codeowners(repo_root: Path) -> dict[str, tuple[str, ...]]:
    """Parse existing CODEOWNERS file into path → owners mapping."""
    codeowners_path = repo_root / _CODEOWNERS_PATH
    if not codeowners_path.exists():
        return {}
    entries: dict[str, tuple[str, ...]] = {}
    for line in codeowners_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            path = parts[0]
            owners = tuple(parts[1:])
            entries[path] = owners
    return entries


def _normalize_inferred(ownership: OwnershipMap) -> dict[str, tuple[str, ...]]:
    """Normalize inferred ownership paths to match CODEOWNERS format."""
    normalized: dict[str, tuple[str, ...]] = {}
    for path, owners in ownership.owners.items():
        key = path if path.startswith("/") else f"/{path}"
        normalized[key] = owners
    return normalized


def _compare(
    current: dict[str, tuple[str, ...]],
    inferred: dict[str, tuple[str, ...]],
    mode: str,
) -> DriftResult:
    """Compare current CODEOWNERS against inferred ownership."""
    stale: list[str] = []
    missing: list[str] = []
    changed: list[str] = []

    if mode in ("repo", "both"):
        for path in sorted(current):
            if path not in inferred:
                stale.append(path)
            elif current[path] != inferred[path]:
                changed.append(path)

    if mode in ("commit", "both"):
        for path in sorted(inferred):
            if path not in current:
                missing.append(path)
            elif mode == "commit" and current[path] != inferred[path]:
                changed.append(path)

    changed_deduped = sorted(set(changed))

    return DriftResult(
        stale=tuple(stale),
        missing=tuple(missing),
        changed=tuple(changed_deduped),
        drift_detected=bool(stale or missing or changed_deduped),
    )


def _write_github_output(result: DriftResult) -> None:
    """Write drift result to GITHUB_OUTPUT if running in Actions."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    data = json.dumps({
        "stale": list(result.stale),
        "missing": list(result.missing),
        "changed": list(result.changed),
        "drift_detected": result.drift_detected,
    })
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"checkowners_drift={data}\n")
