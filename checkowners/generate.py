"""CODEOWNERS file generator from inferred ownership."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from checkowners.models import Config, OwnershipMap

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
    owned_paths = _collect_owned_paths(ownership)
    unowned_paths = _collect_unowned_paths(ownership)

    team_resolve: Callable[[tuple[str, ...]], str | None] | None = None
    if config.github.resolve_teams and token and org:
        from checkowners.github import create_team_resolver

        team_resolve = create_team_resolver(token, org)

    for path, owners in owned_paths:
        if team_resolve is not None:
            team = team_resolve(owners)
            if team is not None:
                lines.append(f"{path} {team}")
                continue
        lines.append(f"{path} {' '.join(owners)}")

    if config.output.include_unowned and unowned_paths:
        lines.append("")
        lines.append("# Unowned paths (needs triage)")
        for path in unowned_paths:
            lines.append(f"# {path}")

    lines.append("")
    return "\n".join(lines)


def _collect_owned_paths(
    ownership: OwnershipMap,
) -> list[tuple[str, tuple[str, ...]]]:
    """Return owned paths sorted alphabetically with their owners."""
    return sorted(
        ((_normalize_path(path), owners) for path, owners in ownership.owners.items() if owners),
        key=lambda item: item[0],
    )


def _collect_unowned_paths(ownership: OwnershipMap) -> list[str]:
    """Return paths with no inferred owners, sorted alphabetically."""
    return sorted(_normalize_path(path) for path, owners in ownership.owners.items() if not owners)


def _normalize_path(path: str) -> str:
    """Normalize a file path for CODEOWNERS format."""
    if not path.startswith("/"):
        return f"/{path}"
    return path


def _write_codeowners(codeowners_path: Path, content: str) -> None:
    """Write CODEOWNERS content to the given path."""
    codeowners_path.parent.mkdir(parents=True, exist_ok=True)
    codeowners_path.write_text(content, encoding="utf-8")
