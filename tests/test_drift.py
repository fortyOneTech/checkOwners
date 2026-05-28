"""Tests for checkowners.drift module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from checkowners.drift import (
    _compare,
    _confidence_delta,
    _normalize_inferred,
    _parse_codeowners,
    _write_github_output,
    detect_drift,
)
from checkowners.models import (
    Config,
    DecayWarning,
    DriftConfig,
    DriftEntry,
    DriftResult,
    OwnerEntry,
    OwnershipMap,
    PathOwnership,
)

_NOW = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)


def _entry(handle: str, confidence: float = 0.8) -> OwnerEntry:
    return OwnerEntry(handle=handle, confidence=confidence, last_commit=_NOW, commits=5)


def _make_ownership(raw: dict[str, tuple[OwnerEntry, ...]]) -> OwnershipMap:
    return OwnershipMap(
        paths={p: PathOwnership(owners=owners, bus_factor=len(owners)) for p, owners in raw.items()},
        last_analyzed=_NOW,
    )


def _write_codeowners(tmp_path: Path, content: str) -> None:
    github_dir = tmp_path / ".github"
    github_dir.mkdir(exist_ok=True)
    (github_dir / "CODEOWNERS").write_text(content, encoding="utf-8")


def _zero_delta_config(mode: str = "both") -> Config:
    return Config(drift=DriftConfig(mode=mode, min_confidence_delta=0.0))


def test_detect_drift_no_codeowners(tmp_path: Path) -> None:
    ownership = _make_ownership({"/src/main.py": (_entry("alice@example.com"),)})
    result = detect_drift(tmp_path, ownership, _zero_delta_config("commit"))
    assert result.drift_detected is True
    paths = [e.path for e in result.missing]
    assert "/src/main.py" in paths


def test_detect_drift_no_drift(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py alice@example.com\n")
    ownership = _make_ownership({"src/main.py": (_entry("alice@example.com"),)})
    result = detect_drift(tmp_path, ownership, _zero_delta_config("both"))
    assert result.drift_detected is False
    assert result.stale == ()
    assert result.missing == ()
    assert result.changed == ()


def test_detect_drift_stale_entry(tmp_path: Path) -> None:
    _write_codeowners(
        tmp_path,
        "/src/main.py alice@example.com\n/src/old.py bob@example.com\n",
    )
    ownership = _make_ownership({"src/main.py": (_entry("alice@example.com"),)})
    result = detect_drift(tmp_path, ownership, _zero_delta_config("repo"))
    paths = [e.path for e in result.stale]
    assert "/src/old.py" in paths
    assert result.drift_detected is True


def test_detect_drift_missing_entry_records_bus_factor_and_decay(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py alice@example.com\n")
    decay = DecayWarning(
        handle="carol@example.com",
        path="src/new.py",
        last_commit=_NOW,
        days_since_last_commit=300,
        historical_confidence=0.4,
    )
    ownership = OwnershipMap(
        paths={
            "src/main.py": PathOwnership(owners=(_entry("alice@example.com"),), bus_factor=1),
            "src/new.py": PathOwnership(
                owners=(_entry("carol@example.com", 0.65),),
                bus_factor=1,
                decay_warnings=(decay,),
            ),
        },
        last_analyzed=_NOW,
    )
    result = detect_drift(tmp_path, ownership, _zero_delta_config("commit"))
    missing = {e.path: e for e in result.missing}
    assert "/src/new.py" in missing
    assert missing["/src/new.py"].bus_factor == 1
    assert missing["/src/new.py"].decay is True


def test_detect_drift_changed_entry_records_delta(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py alice@example.com\n")
    ownership = _make_ownership({"src/main.py": (_entry("bob@example.com", 0.9),)})
    result = detect_drift(tmp_path, ownership, _zero_delta_config("repo"))
    assert len(result.changed) == 1
    assert result.changed[0].path == "/src/main.py"
    assert result.changed[0].confidence_delta > 0


def test_detect_drift_min_confidence_delta_suppresses_small_changes(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/main.py alice@example.com\n")
    ownership = _make_ownership(
        {
            "src/main.py": (
                _entry("alice@example.com", 0.9),
                _entry("carol@example.com", 0.05),
            )
        }
    )
    config = Config(drift=DriftConfig(mode="both", min_confidence_delta=0.5))
    result = detect_drift(tmp_path, ownership, config)
    assert result.changed == ()


def test_detect_drift_both_mode(tmp_path: Path) -> None:
    _write_codeowners(
        tmp_path,
        "/src/main.py alice@example.com\n/src/old.py bob@example.com\n",
    )
    ownership = _make_ownership(
        {
            "src/main.py": (_entry("carol@example.com", 0.9),),
            "src/new.py": (_entry("dave@example.com", 0.9),),
        }
    )
    result = detect_drift(tmp_path, ownership, _zero_delta_config("both"))
    assert {e.path for e in result.stale} == {"/src/old.py"}
    assert {e.path for e in result.missing} == {"/src/new.py"}
    assert {e.path for e in result.changed} == {"/src/main.py"}
    assert result.drift_detected is True


def test_parse_codeowners_strips_inline_comments(tmp_path: Path) -> None:
    content = (
        "# header\n"
        "/src/main.py alice@example.com  # alice(0.92)\n"
        "# trailing\n"
    )
    _write_codeowners(tmp_path, content)
    assert _parse_codeowners(tmp_path / ".github" / "CODEOWNERS") == {
        "/src/main.py": ("alice@example.com",),
    }


def test_parse_codeowners_multiple_owners(tmp_path: Path) -> None:
    _write_codeowners(tmp_path, "/src/api.py alice@example.com bob@example.com\n")
    result = _parse_codeowners(tmp_path / ".github" / "CODEOWNERS")
    assert result["/src/api.py"] == ("alice@example.com", "bob@example.com")


def test_parse_codeowners_missing_file(tmp_path: Path) -> None:
    result = _parse_codeowners(tmp_path / ".github" / "CODEOWNERS")
    assert result == {}


def test_detect_drift_with_custom_codeowners_path(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "CODEOWNERS").write_text("/src/main.py alice@example.com\n", encoding="utf-8")
    ownership = _make_ownership({"src/main.py": (_entry("alice@example.com"),)})
    result = detect_drift(
        tmp_path, ownership, _zero_delta_config("both"), codeowners_path=docs_dir / "CODEOWNERS"
    )
    assert result.drift_detected is False


def test_normalize_inferred_adds_slash() -> None:
    ownership = _make_ownership(
        {
            "src/main.py": (_entry("alice@example.com"),),
            "/already/slashed.py": (_entry("bob@example.com"),),
        }
    )
    result = _normalize_inferred(ownership)
    assert "/src/main.py" in result
    assert "/already/slashed.py" in result


def test_compare_empty_both() -> None:
    result = _compare({}, {}, "both", 0.0)
    assert result == DriftResult(stale=(), missing=(), changed=(), drift_detected=False)


def test_compare_changed_deduped_across_modes() -> None:
    current = {"/f.py": ("alice@example.com",)}
    inferred = {
        "/f.py": PathOwnership(owners=(_entry("bob@example.com", 0.9),), bus_factor=1),
    }
    result = _compare(current, inferred, "both", 0.0)
    paths = [e.path for e in result.changed]
    assert paths == ["/f.py"]


def test_confidence_delta_added_and_removed() -> None:
    inferred = (_entry("alice@example.com", 0.8), _entry("eve@example.com", 0.6))
    delta = _confidence_delta(("alice@example.com", "bob@example.com"), inferred)
    assert delta > 0


def test_confidence_delta_identical_returns_zero() -> None:
    inferred = (_entry("alice@example.com", 0.8),)
    assert _confidence_delta(("alice@example.com",), inferred) == 0.0


def test_drift_results_sorted_by_delta(tmp_path: Path) -> None:
    _write_codeowners(
        tmp_path,
        "/keep.py alice@example.com\n/z_old.py bob@example.com\n/a_old.py carol@example.com\n",
    )
    ownership = _make_ownership({"keep.py": (_entry("alice@example.com"),)})
    result = detect_drift(tmp_path, ownership, _zero_delta_config("repo"))
    assert all(e.confidence_delta == 1.0 for e in result.stale)
    assert [e.path for e in result.stale] == ["/a_old.py", "/z_old.py"]


def test_write_github_output(tmp_path: Path) -> None:
    output_file = tmp_path / "github_output.txt"
    output_file.write_text("", encoding="utf-8")
    result = DriftResult(
        stale=(DriftEntry(path="/old.py", confidence_delta=1.0, reason="stale"),),
        missing=(DriftEntry(path="/new.py", confidence_delta=0.7, reason="missing"),),
        changed=(),
        drift_detected=True,
    )
    with patch.dict("os.environ", {"GITHUB_OUTPUT": str(output_file)}):
        _write_github_output(result)
    content = output_file.read_text(encoding="utf-8")
    assert "checkowners_drift=" in content
    assert '"drift_detected": true' in content
    assert '"max_confidence_delta": 1.0' in content


def test_write_github_output_skipped_outside_actions() -> None:
    result = DriftResult(stale=(), missing=(), changed=(), drift_detected=False)
    with patch.dict("os.environ", {}, clear=True):
        _write_github_output(result)
