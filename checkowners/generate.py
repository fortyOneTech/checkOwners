"""CODEOWNERS file generator from confidence-scored ownership."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from checkowners.models import Config, OwnerEntry, OwnershipMap, PathOwnership

_DEFAULT_CODEOWNERS_PATH = ".github/CODEOWNERS"


def generate_codeowners(
    repo_root: Path,
    ownership: OwnershipMap,
    config: Config,
    *,
    codeowners_path: Path | None = None,
    token: str = "",
    org: str = "",
) -> str:
    """Generate CODEOWNERS file content and write it to disk."""
    content = _build_codeowners_content(ownership, config, token=token, org=org)
    target = codeowners_path or (repo_root / _DEFAULT_CODEOWNERS_PATH)
    _write_codeowners(target, content)
    return content


def _build_codeowners_content(
    ownership: OwnershipMap,
    config: Config,
    *,
    token: str = "",
    org: str = "",
) -> str:
    """Build the CODEOWNERS file content string."""
    lines: list[str] = [config.output.header, ""]
    owned_paths = _collect_owned_paths(ownership, config.analysis.confidence_threshold)
    unowned_paths = _collect_unowned_paths(ownership)

    team_resolve: Callable[[tuple[str, ...]], str | None] | None = None
    if config.github.resolve_teams and token and org:
        from checkowners.github import create_team_resolver

        team_resolve = create_team_resolver(token, org)

    for path, owners in owned_paths:
        handles = tuple(o.handle for o in owners)
        if team_resolve is not None:
            team = team_resolve(handles)
            if team is not None:
                lines.append(_format_line(path, (team,), owners, config))
                continue
        lines.append(_format_line(path, handles, owners, config))

    if owned_paths and config.output.include_confidence:
        lines.append("")
        lines.append("# Confidence scores reflect each owner's expertise as of")
        lines.append(f"# {ownership.last_analyzed.isoformat(timespec='seconds')}.")

    if config.output.include_unowned and unowned_paths:
        lines.append("")
        lines.append("# Unowned paths (needs triage)")
        for path in unowned_paths:
            lines.append(f"# {path}")

    lines.append("")
    return "\n".join(lines)


def _format_line(
    path: str,
    written_handles: tuple[str, ...],
    owners: tuple[OwnerEntry, ...],
    config: Config,
) -> str:
    line = f"{path} {' '.join(written_handles)}"
    if not config.output.include_confidence:
        return line
    annotations = " ".join(f"{o.handle}({o.confidence:.2f})" for o in owners)
    return f"{line}  # {annotations}"


def _collect_owned_paths(
    ownership: OwnershipMap,
    confidence_threshold: float,
) -> list[tuple[str, tuple[OwnerEntry, ...]]]:
    """Return owned paths sorted alphabetically with their confidence-ordered owners."""
    rows: list[tuple[str, tuple[OwnerEntry, ...]]] = []
    for path, path_ownership in ownership.paths.items():
        filtered = tuple(
            o for o in path_ownership.owners if o.confidence >= confidence_threshold
        )
        if not filtered:
            continue
        rows.append((_normalize_path(path), filtered))
    rows.sort(key=lambda item: item[0])
    return rows


def _collect_unowned_paths(ownership: OwnershipMap) -> list[str]:
    """Paths present in the map with no inferred owners."""
    return sorted(
        _normalize_path(path)
        for path, po in ownership.paths.items()
        if not po.owners
    )


def _normalize_path(path: str) -> str:
    if not path.startswith("/"):
        return f"/{path}"
    return path


def _write_codeowners(codeowners_path: Path, content: str) -> None:
    codeowners_path.parent.mkdir(parents=True, exist_ok=True)
    codeowners_path.write_text(content, encoding="utf-8")


def _owners_for_path(po: PathOwnership) -> tuple[OwnerEntry, ...]:
    return po.owners
