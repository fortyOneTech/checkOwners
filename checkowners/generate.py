"""CODEOWNERS file generator from inferred ownership."""

from __future__ import annotations

from pathlib import Path

from checkowners.models import Config, OwnershipMap

_CODEOWNERS_PATH = ".github/CODEOWNERS"


def generate_codeowners(
    repo_root: Path,
    ownership: OwnershipMap,
    config: Config,
) -> str:
    """Generate CODEOWNERS file content and write it to disk."""
    content = _build_codeowners_content(ownership, config)
    _write_codeowners(repo_root, content)
    return content


def _build_codeowners_content(ownership: OwnershipMap, config: Config) -> str:
    """Build the CODEOWNERS file content string."""
    lines: list[str] = [config.output.header, ""]
    owned_paths = _collect_owned_paths(ownership)
    unowned_paths = _collect_unowned_paths(ownership)

    for path, owners in owned_paths:
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


def _write_codeowners(repo_root: Path, content: str) -> None:
    """Write CODEOWNERS content to .github/CODEOWNERS."""
    codeowners_path = repo_root / _CODEOWNERS_PATH
    codeowners_path.parent.mkdir(parents=True, exist_ok=True)
    codeowners_path.write_text(content, encoding="utf-8")
