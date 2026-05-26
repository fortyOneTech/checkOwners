"""Syntax-only CODEOWNERS validator. No inference, no git access."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_CODEOWNERS_PATH = ".github/CODEOWNERS"
_OWNER_PATTERN = re.compile(r"^(@[\w./-]+|[\w.+-]+@[\w.-]+)$")


@dataclass(frozen=True)
class ValidationError:
    line_number: int
    line: str
    message: str


def validate_codeowners(
    repo_root: Path,
    *,
    codeowners_path: Path | None = None,
) -> list[ValidationError]:
    """Validate CODEOWNERS syntax and return a list of errors."""
    target = codeowners_path or (repo_root / _DEFAULT_CODEOWNERS_PATH)
    if not target.exists():
        return [ValidationError(line_number=0, line="", message="CODEOWNERS file not found")]
    content = target.read_text(encoding="utf-8")
    return _validate_lines(content)


def _validate_lines(content: str) -> list[ValidationError]:
    """Validate each line of CODEOWNERS content."""
    errors: list[ValidationError] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line_errors = _validate_entry(line_number, line)
        errors.extend(line_errors)
    return errors


def _validate_entry(line_number: int, line: str) -> list[ValidationError]:
    """Validate a single CODEOWNERS entry line."""
    errors: list[ValidationError] = []
    parts = line.split()

    if len(parts) < 2:
        errors.append(
            ValidationError(
                line_number=line_number,
                line=line,
                message="Entry must have a path and at least one owner",
            )
        )
        return errors

    path = parts[0]
    if not path.startswith("/") and not path.startswith("*"):
        errors.append(
            ValidationError(
                line_number=line_number,
                line=line,
                message=f"Path must start with '/' or '*': {path}",
            )
        )

    for owner in parts[1:]:
        if not _OWNER_PATTERN.match(owner):
            errors.append(
                ValidationError(
                    line_number=line_number,
                    line=line,
                    message=f"Invalid owner format: {owner}",
                )
            )

    return errors
