"""Tests for checkowners.analyze module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from checkowners.analyze import (
    _count_ownership,
    _filter_excluded,
    _filter_nonexistent,
    _is_excluded,
    _parse_log_output,
    _select_top_owners,
    analyze_ownership,
)
from checkowners.models import AnalysisConfig, Config


def _make_git_log_output(commits: list[tuple[str, list[str]]]) -> str:
    """Build a fake git log stdout string from (author, files) pairs."""
    chunks: list[str] = []
    for author, files in commits:
        chunk = f"COMMIT_START\n{author}\n\n" + "\n".join(files)
        chunks.append(chunk)
    return "\n".join(chunks) + "\n"


def _mock_run(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


_MOCK_GIT = "checkowners.analyze.subprocess.run"
_MOCK_EXIST = "checkowners.analyze._filter_nonexistent"


def _passthrough(
    counts: dict[str, dict[str, int]],
    _root: Path,
) -> dict[str, dict[str, int]]:
    return counts


def test_analyze_basic() -> None:
    commits = [
        ("alice@example.com", ["src/main.py", "src/utils.py"]),
        ("bob@example.com", ["src/main.py"]),
        ("alice@example.com", ["src/main.py", "src/utils.py"]),
        ("alice@example.com", ["src/main.py"]),
    ]
    stdout = _make_git_log_output(commits)
    config = Config(analysis=AnalysisConfig(min_commits=1, top_n_owners=2))

    with (
        patch(_MOCK_GIT, return_value=_mock_run(stdout)),
        patch(_MOCK_EXIST, side_effect=_passthrough),
    ):
        result = analyze_ownership(Path("/fake"), config)

    assert "src/main.py" in result.owners
    assert result.owners["src/main.py"][0] == "alice@example.com"
    assert "bob@example.com" in result.owners["src/main.py"]
    assert "src/utils.py" in result.owners
    assert result.owners["src/utils.py"] == ("alice@example.com",)
    assert result.last_analyzed is not None


def test_analyze_lookback_days() -> None:
    config = Config(analysis=AnalysisConfig(lookback_days=90, min_commits=1))

    with (
        patch(_MOCK_GIT, return_value=_mock_run("")) as mock,
        patch(_MOCK_EXIST, side_effect=_passthrough),
    ):
        analyze_ownership(Path("/fake"), config)

    args = mock.call_args[0][0]
    assert "--since=90 days ago" in args


def test_analyze_min_commits_filter() -> None:
    commits = [
        ("alice@example.com", ["src/main.py"]),
        ("alice@example.com", ["src/main.py"]),
        ("alice@example.com", ["src/main.py"]),
        ("bob@example.com", ["src/main.py"]),
    ]
    stdout = _make_git_log_output(commits)
    config = Config(analysis=AnalysisConfig(min_commits=2, top_n_owners=5))

    with (
        patch(_MOCK_GIT, return_value=_mock_run(stdout)),
        patch(_MOCK_EXIST, side_effect=_passthrough),
    ):
        result = analyze_ownership(Path("/fake"), config)

    assert result.owners["src/main.py"] == ("alice@example.com",)


def test_analyze_top_n_owners() -> None:
    commits = (
        [("alice@example.com", ["f.py"])] * 10
        + [("bob@example.com", ["f.py"])] * 7
        + [("carol@example.com", ["f.py"])] * 3
    )
    stdout = _make_git_log_output(commits)
    config = Config(analysis=AnalysisConfig(min_commits=1, top_n_owners=2))

    with (
        patch(_MOCK_GIT, return_value=_mock_run(stdout)),
        patch(_MOCK_EXIST, side_effect=_passthrough),
    ):
        result = analyze_ownership(Path("/fake"), config)

    assert result.owners["f.py"] == ("alice@example.com", "bob@example.com")


def test_analyze_path_exclusions() -> None:
    commits = [
        ("alice@example.com", ["src/main.py", "yarn.lock", "dist/bundle.js", "vendor/lib/u.go"]),
        ("alice@example.com", ["src/main.py", "yarn.lock", "dist/bundle.js", "vendor/lib/u.go"]),
        ("alice@example.com", ["src/main.py", "yarn.lock", "dist/bundle.js", "vendor/lib/u.go"]),
    ]
    stdout = _make_git_log_output(commits)
    config = Config(analysis=AnalysisConfig(min_commits=1))

    with (
        patch(_MOCK_GIT, return_value=_mock_run(stdout)),
        patch(_MOCK_EXIST, side_effect=_passthrough),
    ):
        result = analyze_ownership(Path("/fake"), config)

    assert "src/main.py" in result.owners
    assert "yarn.lock" not in result.owners
    assert "dist/bundle.js" not in result.owners
    assert "vendor/lib/u.go" not in result.owners


def test_analyze_empty_repo() -> None:
    config = Config(analysis=AnalysisConfig(min_commits=1))

    with patch(_MOCK_GIT, return_value=_mock_run("")), patch(_MOCK_EXIST, side_effect=_passthrough):
        result = analyze_ownership(Path("/fake"), config)

    assert result.owners == {}


def test_analyze_single_author() -> None:
    commits = [("alice@example.com", ["a.py", "b.py", "c.py"])] * 5
    stdout = _make_git_log_output(commits)
    config = Config(analysis=AnalysisConfig(min_commits=1, top_n_owners=2))

    with (
        patch(_MOCK_GIT, return_value=_mock_run(stdout)),
        patch(_MOCK_EXIST, side_effect=_passthrough),
    ):
        result = analyze_ownership(Path("/fake"), config)

    for path in ("a.py", "b.py", "c.py"):
        assert result.owners[path] == ("alice@example.com",)


def test_is_excluded_patterns() -> None:
    assert _is_excluded("yarn.lock", ("*.lock",))
    assert _is_excluded("package-lock.json", ("*.lock",)) is False
    assert _is_excluded("dist/bundle.js", ("dist/**",))
    assert _is_excluded("dist/sub/file.js", ("dist/**",))
    assert _is_excluded("vendor/a/b.go", ("vendor/**",))
    assert _is_excluded("src/main.py", ("*.lock", "dist/**", "vendor/**")) is False


def test_select_top_owners_tiebreaking() -> None:
    counts = {"f.py": {"bob@example.com": 5, "alice@example.com": 5}}
    result = _select_top_owners(counts, min_commits=1, top_n=2)
    assert result["f.py"] == ("alice@example.com", "bob@example.com")


def test_count_ownership() -> None:
    history = [
        ("alice@example.com", ("a.py", "b.py")),
        ("bob@example.com", ("a.py",)),
        ("alice@example.com", ("a.py",)),
    ]
    counts = _count_ownership(history)
    assert counts["a.py"]["alice@example.com"] == 2
    assert counts["a.py"]["bob@example.com"] == 1
    assert counts["b.py"]["alice@example.com"] == 1


def test_filter_excluded() -> None:
    counts = {
        "src/main.py": {"alice": 3},
        "yarn.lock": {"alice": 5},
        "dist/out.js": {"bob": 2},
    }
    patterns = ("*.lock", "dist/**")
    filtered = _filter_excluded(counts, patterns)
    assert "src/main.py" in filtered
    assert "yarn.lock" not in filtered
    assert "dist/out.js" not in filtered


def test_get_commit_history_subprocess_error() -> None:
    with (
        patch(
            "checkowners.analyze.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ),
        pytest.raises(subprocess.CalledProcessError),
    ):
        from checkowners.analyze import _get_commit_history

        _get_commit_history(Path("/fake"), 180)


def test_parse_log_output_empty() -> None:
    assert _parse_log_output("") == []
    assert _parse_log_output("  \n  ") == []


def test_filter_nonexistent(tmp_path: Path) -> None:
    (tmp_path / "exists.py").write_text("x", encoding="utf-8")
    counts = {
        "exists.py": {"alice": 3},
        "deleted.py": {"bob": 5},
    }
    result = _filter_nonexistent(counts, tmp_path)
    assert "exists.py" in result
    assert "deleted.py" not in result


def test_select_top_owners_all_below_threshold() -> None:
    counts = {"f.py": {"alice": 1, "bob": 2}}
    result = _select_top_owners(counts, min_commits=5, top_n=2)
    assert "f.py" not in result
