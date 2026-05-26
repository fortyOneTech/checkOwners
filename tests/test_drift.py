"""Tests for checkowners.drift module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from checkowners.drift import (
    _compare,
    _normalize_inferred,
    _parse_codeowners,
    _write_github_output,
    detect_drift,
)
from checkowners.models import Config, DriftConfig, DriftResult, OwnershipMap

_NOW = datetime.now(UTC)


def _make_ownership(owners: dict[str, tuple[str, ...]]) -> OwnershipMap:
    return OwnershipMap(owners=owners, last_analyzed=_NOW)


def _write_codeowners(tmp_path: Path, content: str) -> None:
    github_dir = tmp_path / ".github"
    github_dir.mkdir(exist_ok=True)
    (github_dir / "CODEOWNERS").write_text(content, encoding="utf-8")


def test_detect_drift_no_codeowners(tmp_path: Path) -> None:
    ownership = _make_ownership({"/src/main.py": ("alice@example.com",)})
    config = Config(drift=DriftConfig(mode="commit"))
    result = detect_drift(tmp_path, ownership, config)
    assert result.drift_detected is True
    assert "/src/main.py" in result.missing


def test_detect_drift_no_drift(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py alice@example.com\n")
    ownership = _make_ownership({"src/main.py": ("alice@example.com",)})
    config = Config(drift=DriftConfig(mode="both"))
    result = detect_drift(tmp_path, ownership, config)
    assert result.drift_detected is False
    assert result.stale == ()
    assert result.missing == ()
    assert result.changed == ()


def test_detect_drift_stale_entry(tmp_path: Path) -> None:
    _write_codeowners(
        tmp_path,
        "/src/main.py alice@example.com\n/src/old.py bob@example.com\n",
    )
    ownership = _make_ownership({"src/main.py": ("alice@example.com",)})
    config = Config(drift=DriftConfig(mode="repo"))
    result = detect_drift(tmp_path, ownership, config)
    assert "/src/old.py" in result.stale
    assert result.drift_detected is True


def test_detect_drift_missing_entry(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py alice@example.com\n")
    ownership = _make_ownership(
        {
            "src/main.py": ("alice@example.com",),
            "src/new.py": ("carol@example.com",),
        }
    )
    config = Config(drift=DriftConfig(mode="commit"))
    result = detect_drift(tmp_path, ownership, config)
    assert "/src/new.py" in result.missing
    assert result.drift_detected is True


def test_detect_drift_changed_entry_repo_mode(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py alice@example.com\n")
    ownership = _make_ownership({"src/main.py": ("bob@example.com",)})
    config = Config(drift=DriftConfig(mode="repo"))
    result = detect_drift(tmp_path, ownership, config)
    assert "/src/main.py" in result.changed
    assert result.drift_detected is True


def test_detect_drift_changed_entry_commit_mode(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py alice@example.com\n")
    ownership = _make_ownership({"src/main.py": ("bob@example.com",)})
    config = Config(drift=DriftConfig(mode="commit"))
    result = detect_drift(tmp_path, ownership, config)
    assert "/src/main.py" in result.changed


def test_detect_drift_both_mode(tmp_path: Path) -> None:
    _write_codeowners(
        tmp_path,
        "/src/main.py alice@example.com\n/src/old.py bob@example.com\n",
    )
    ownership = _make_ownership(
        {
            "src/main.py": ("carol@example.com",),
            "src/new.py": ("dave@example.com",),
        }
    )
    config = Config(drift=DriftConfig(mode="both"))
    result = detect_drift(tmp_path, ownership, config)
    assert "/src/old.py" in result.stale
    assert "/src/new.py" in result.missing
    assert "/src/main.py" in result.changed
    assert result.drift_detected is True


def test_parse_codeowners_skips_comments(tmp_path: Path) -> None:
    content = "# header comment\n\n/src/main.py alice@example.com\n# another comment\n"
    _write_codeowners(tmp_path, content)
    result = _parse_codeowners(tmp_path)
    assert result == {"/src/main.py": ("alice@example.com",)}


def test_parse_codeowners_multiple_owners(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/api.py alice@example.com bob@example.com\n")
    result = _parse_codeowners(tmp_path)
    assert result["/src/api.py"] == ("alice@example.com", "bob@example.com")


def test_parse_codeowners_missing_file(tmp_path: Path) -> None:
    result = _parse_codeowners(tmp_path)
    assert result == {}


def test_normalize_inferred_adds_slash() -> None:
    ownership = _make_ownership(
        {
            "src/main.py": ("alice@example.com",),
            "/already/slashed.py": ("bob@example.com",),
        }
    )
    result = _normalize_inferred(ownership)
    assert "/src/main.py" in result
    assert "/already/slashed.py" in result


def test_compare_empty_both() -> None:
    result = _compare({}, {}, "both")
    assert result == DriftResult(
        stale=(),
        missing=(),
        changed=(),
        drift_detected=False,
    )


def test_compare_changed_deduped() -> None:
    current = {"/f.py": ("alice",)}
    inferred = {"/f.py": ("bob",)}
    result = _compare(current, inferred, "both")
    assert result.changed == ("/f.py",)


def test_write_github_output(tmp_path: Path) -> None:
    output_file = tmp_path / "github_output.txt"
    output_file.write_text("", encoding="utf-8")
    result = DriftResult(
        stale=("/old.py",),
        missing=("/new.py",),
        changed=(),
        drift_detected=True,
    )
    with patch.dict("os.environ", {"GITHUB_OUTPUT": str(output_file)}):
        _write_github_output(result)
    content = output_file.read_text(encoding="utf-8")
    assert "checkowners_drift=" in content
    assert '"drift_detected": true' in content


def test_write_github_output_skipped_outside_actions() -> None:
    result = DriftResult(stale=(), missing=(), changed=(), drift_detected=False)
    with patch.dict("os.environ", {}, clear=True):
        _write_github_output(result)


def test_detect_drift_results_sorted(tmp_path: Path) -> None:
    _write_codeowners(
        tmp_path,
        "/z.py alice\n/a.py bob\n",
    )
    ownership = _make_ownership({})
    config = Config(drift=DriftConfig(mode="repo"))
    result = detect_drift(tmp_path, ownership, config)
    assert result.stale == ("/a.py", "/z.py")
