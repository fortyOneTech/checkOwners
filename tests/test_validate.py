"""Tests for checkowners.validate module."""

from __future__ import annotations

from pathlib import Path

from checkowners.validate import validate_codeowners


def _write_codeowners(tmp_path: Path, content: str) -> None:
    github_dir = tmp_path / ".github"
    github_dir.mkdir(exist_ok=True)
    (github_dir / "CODEOWNERS").write_text(content, encoding="utf-8")


def test_validate_valid_file(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "# Header\n\n/src/main.py @alice\n/docs/ @bob\n")
    errors = validate_codeowners(tmp_path)
    assert errors == []


def test_validate_missing_file(tmp_path: Path) -> None:
    errors = validate_codeowners(tmp_path)
    assert len(errors) == 1
    assert "not found" in errors[0].message


def test_validate_missing_owner(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py\n")
    errors = validate_codeowners(tmp_path)
    assert len(errors) == 1
    assert "at least one owner" in errors[0].message


def test_validate_invalid_path(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "src/main.py @alice\n")
    errors = validate_codeowners(tmp_path)
    assert len(errors) == 1
    assert "must start with" in errors[0].message


def test_validate_invalid_owner(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py not-an-owner!\n")
    errors = validate_codeowners(tmp_path)
    assert len(errors) == 1
    assert "Invalid owner" in errors[0].message


def test_validate_skips_comments_and_blanks(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "# comment\n\n  # indented comment\n")
    errors = validate_codeowners(tmp_path)
    assert errors == []


def test_validate_multiple_owners(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/ @alice @org/team bob@example.com\n")
    errors = validate_codeowners(tmp_path)
    assert errors == []


def test_validate_wildcard_path(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "*.py @alice\n")
    errors = validate_codeowners(tmp_path)
    assert errors == []


def test_validate_multiple_errors(tmp_path: Path) -> None:
    content = "/valid.py @alice\nsrc/bad.py @bob\n/also.py\n"
    _write_codeowners(tmp_path, content)
    errors = validate_codeowners(tmp_path)
    assert len(errors) == 2


def test_validate_line_numbers(tmp_path: Path) -> None:
    content = "# header\n\n/ok.py @alice\nsrc/bad.py @bob\n"
    _write_codeowners(tmp_path, content)
    errors = validate_codeowners(tmp_path)
    assert len(errors) == 1
    assert errors[0].line_number == 4


def test_validate_email_owner(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/ alice@example.com\n")
    errors = validate_codeowners(tmp_path)
    assert errors == []


def test_validate_org_team_owner(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/ @org/team-name\n")
    errors = validate_codeowners(tmp_path)
    assert errors == []
