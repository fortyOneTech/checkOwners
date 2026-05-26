"""Tests for checkowners.cli module."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from checkowners.cli import app
from checkowners.models import DriftResult, OwnershipMap

runner = CliRunner()

_NOW = datetime.now(UTC)
_OWNERSHIP = OwnershipMap(
    owners={"src/main.py": ("alice@example.com", "bob@example.com")},
    last_analyzed=_NOW,
)
_EMPTY_OWNERSHIP = OwnershipMap(owners={}, last_analyzed=_NOW)
_DRIFT_DETECTED = DriftResult(
    stale=("/old.py",),
    missing=("/new.py",),
    changed=("/changed.py",),
    drift_detected=True,
)
_NO_DRIFT = DriftResult(stale=(), missing=(), changed=(), drift_detected=False)


# --- analyze ---


def test_analyze_json() -> None:
    with patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP):
        result = runner.invoke(app, ["analyze", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "src/main.py" in data["inferred"]


def test_analyze_table() -> None:
    with patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP):
        result = runner.invoke(app, ["analyze"])
    assert result.exit_code == 0
    assert "alice@example.com" in result.stdout


def test_analyze_empty() -> None:
    with patch("checkowners.cli.analyze_ownership", return_value=_EMPTY_OWNERSHIP):
        result = runner.invoke(app, ["analyze"])
    assert result.exit_code == 0
    assert "No ownership" in result.stdout


def test_analyze_git_error() -> None:
    with patch(
        "checkowners.cli.analyze_ownership",
        side_effect=subprocess.CalledProcessError(1, "git"),
    ):
        result = runner.invoke(app, ["analyze"])
    assert result.exit_code == 1


# --- generate ---


def test_generate_rich(tmp_path: Path) -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.generate_codeowners", return_value="content"),
    ):
        result = runner.invoke(app, ["generate"])
    assert result.exit_code == 0
    assert "Generated" in result.stdout


def test_generate_json() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.generate_codeowners", return_value="content"),
    ):
        result = runner.invoke(app, ["generate", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["path"] == ".github/CODEOWNERS"


# --- print ---


def test_print_json() -> None:
    with patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP):
        result = runner.invoke(app, ["print", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "src/main.py" in data


def test_print_plain() -> None:
    with patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP):
        result = runner.invoke(app, ["print"])
    assert result.exit_code == 0
    assert "src/main.py" in result.stdout
    assert "alice@example.com" in result.stdout


# --- validate ---


def test_validate_valid(tmp_path: Path) -> None:
    with patch("checkowners.cli.validate_codeowners", return_value=[]):
        result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0
    assert "valid" in result.stdout


def test_validate_errors() -> None:
    from checkowners.validate import ValidationError

    errors = [ValidationError(line_number=3, line="bad", message="bad line")]
    with patch("checkowners.cli.validate_codeowners", return_value=errors):
        result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "Line 3" in result.stdout


def test_validate_json_valid() -> None:
    with patch("checkowners.cli.validate_codeowners", return_value=[]):
        result = runner.invoke(app, ["validate", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["valid"] is True


def test_validate_json_errors() -> None:
    from checkowners.validate import ValidationError

    errors = [ValidationError(line_number=1, line="x", message="oops")]
    with patch("checkowners.cli.validate_codeowners", return_value=errors):
        result = runner.invoke(app, ["validate", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["valid"] is False
    assert len(data["errors"]) == 1


# --- drift ---


def test_drift_no_drift() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.detect_drift", return_value=_NO_DRIFT),
    ):
        result = runner.invoke(app, ["drift"])
    assert result.exit_code == 0
    assert "No drift" in result.stdout


def test_drift_detected() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.detect_drift", return_value=_DRIFT_DETECTED),
    ):
        result = runner.invoke(app, ["drift"])
    assert result.exit_code == 0
    assert "Stale" in result.stdout


def test_drift_json() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.detect_drift", return_value=_DRIFT_DETECTED),
    ):
        result = runner.invoke(app, ["drift", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["drift_detected"] is True


# --- notify ---


def test_notify_sent() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.detect_drift", return_value=_DRIFT_DETECTED),
        patch("checkowners.cli.send_notification", return_value=True),
    ):
        result = runner.invoke(app, ["notify"])
    assert result.exit_code == 0
    assert "sent" in result.stdout.lower()


def test_notify_skipped() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.detect_drift", return_value=_NO_DRIFT),
        patch("checkowners.cli.send_notification", return_value=False),
    ):
        result = runner.invoke(app, ["notify"])
    assert result.exit_code == 0
    assert "skipped" in result.stdout.lower()


def test_notify_json() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.detect_drift", return_value=_DRIFT_DETECTED),
        patch("checkowners.cli.send_notification", return_value=True),
    ):
        result = runner.invoke(app, ["notify", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["sent"] is True


# --- sync ---


def test_sync_rich() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.generate_codeowners", return_value="content"),
        patch("checkowners.cli.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "committed" in result.stdout.lower()


def test_sync_json() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.generate_codeowners", return_value="content"),
        patch("checkowners.cli.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(app, ["sync", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["committed"] is True


def test_sync_git_commit_error() -> None:
    with (
        patch("checkowners.cli.analyze_ownership", return_value=_OWNERSHIP),
        patch("checkowners.cli.generate_codeowners", return_value="content"),
        patch(
            "checkowners.cli.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git", stderr="nothing to commit"),
        ),
    ):
        result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1
