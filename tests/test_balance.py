"""Tests for checkowners.balance module."""

from __future__ import annotations

from datetime import UTC, datetime

from checkowners.balance import _qualified_pairs, analyze_balance
from checkowners.models import (
    AnalysisConfig,
    Config,
    GithubConfig,
    OwnerEntry,
    OwnershipMap,
    PathOwnership,
)

_NOW = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)


def _entry(handle: str, confidence: float, commits: int = 5) -> OwnerEntry:
    return OwnerEntry(handle=handle, confidence=confidence, last_commit=_NOW, commits=commits)


def _ownership(raw: dict[str, tuple[OwnerEntry, ...]]) -> OwnershipMap:
    return OwnershipMap(
        paths={
            p: PathOwnership(owners=owners, bus_factor=len(owners))
            for p, owners in raw.items()
        },
        last_analyzed=_NOW,
    )


def _config(confidence_threshold: float = 0.0) -> Config:
    return Config(
        analysis=AnalysisConfig(confidence_threshold=confidence_threshold),
        github=GithubConfig(api_enabled=False),
    )


def test_analyze_balance_empty_returns_empty() -> None:
    ownership = OwnershipMap(paths={}, last_analyzed=_NOW)
    report = analyze_balance(ownership, _config())
    assert report.loads == ()
    assert report.average == 0.0
    assert report.overloaded == ()
    assert report.suggestions == ()


def test_analyze_balance_authorship_fallback() -> None:
    ownership = _ownership(
        {
            "src/api.py": (_entry("@alice", 0.9, commits=20), _entry("@bob", 0.8, commits=5)),
            "src/db.py": (_entry("@alice", 0.85, commits=30), _entry("@carol", 0.7, commits=5)),
        }
    )
    report = analyze_balance(ownership, _config())
    handles = {load.handle: load.reviews for load in report.loads}
    assert handles["@alice"] == 50
    assert handles["@bob"] == 5
    assert handles["@carol"] == 5
    assert report.source == "git_authorship"


def test_analyze_balance_detects_overloaded_reviewer() -> None:
    ownership = _ownership(
        {
            "src/api.py": (
                _entry("@alice", 0.9, commits=80),
                _entry("@bob", 0.8, commits=10),
                _entry("@carol", 0.7, commits=10),
            ),
        }
    )
    report = analyze_balance(ownership, _config())
    overloaded_handles = {load.handle for load in report.overloaded}
    assert "@alice" in overloaded_handles
    assert "@bob" not in overloaded_handles


def test_analyze_balance_external_review_counts() -> None:
    ownership = _ownership(
        {
            "src/api.py": (
                _entry("@alice", 0.9, commits=1),
                _entry("@bob", 0.8, commits=1),
            ),
        }
    )
    report = analyze_balance(
        ownership,
        _config(),
        review_counts={"@alice": 50, "@bob": 5},
    )
    assert report.source == "external"
    handles = {load.handle: load.reviews for load in report.loads}
    assert handles == {"@alice": 50, "@bob": 5}


def test_analyze_balance_suggests_routing_to_qualified_co_owner() -> None:
    ownership = _ownership(
        {
            "src/api.py": (
                _entry("@alice", 0.9, commits=100),
                _entry("@bob", 0.7, commits=10),
                _entry("@carol", 0.6, commits=10),
            ),
        }
    )
    report = analyze_balance(ownership, _config())
    overloaded = {load.handle for load in report.overloaded}
    assert "@alice" in overloaded
    candidates = {s.candidate for s in report.suggestions if s.overloaded == "@alice"}
    assert candidates == {"@bob", "@carol"}


def test_analyze_balance_filters_low_confidence_candidates() -> None:
    ownership = _ownership(
        {
            "src/api.py": (
                _entry("@alice", 0.9, commits=100),
                _entry("@bob", 0.1, commits=10),
            ),
        }
    )
    report = analyze_balance(ownership, _config(confidence_threshold=0.5))
    assert report.suggestions == ()


def test_qualified_pairs_orders_by_confidence() -> None:
    ownership = _ownership(
        {
            "src/api.py": (
                _entry("@alice", 0.9),
                _entry("@bob", 0.7),
                _entry("@carol", 0.85),
            ),
        }
    )
    pairs = _qualified_pairs(ownership, 0.5)
    alice_neighbors = [handle for handle, _ in pairs["@alice"]]
    assert alice_neighbors == ["@carol", "@bob"]
