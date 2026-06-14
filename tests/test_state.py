"""Tests for checkowners.state module."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from checkowners.models import (
    BusFactor,
    ConfidenceScore,
    DecayWarning,
    OwnerEntry,
    OwnershipMap,
    PathOwnership,
    TeamCluster,
)
from checkowners.state import (
    SCHEMA_VERSION,
    _state_path,
    load_ownership,
    read_graph_cache,
    read_state,
    write_graph_cache,
    write_state,
)

_NOW = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path) -> None:
    with patch.dict("os.environ", {"CHECKOWNERS_STATE_DIR": str(tmp_path)}):
        yield


def _make_ownership() -> OwnershipMap:
    breakdown = ConfidenceScore(total=0.85, recency=0.9, frequency=0.7, blame=0.8, review=0.6)
    owner = OwnerEntry(
        handle="@alice",
        confidence=0.85,
        last_commit=_NOW,
        commits=12,
        score_breakdown=breakdown,
    )
    decay = DecayWarning(
        handle="@bob",
        path="src/auth.py",
        last_commit=_NOW,
        days_since_last_commit=200,
        historical_confidence=0.4,
    )
    po = PathOwnership(owners=(owner,), bus_factor=1, decay_warnings=(decay,))
    return OwnershipMap(paths={"src/auth.py": po}, last_analyzed=_NOW)


def test_state_path_honors_override(tmp_path: Path) -> None:
    expected = tmp_path / "state.json"
    assert _state_path() == expected


def test_read_state_missing_returns_none() -> None:
    assert read_state() is None


def test_read_state_invalid_json_returns_none() -> None:
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text("not json", encoding="utf-8")
    assert read_state() is None


def test_read_state_wrong_schema_returns_none() -> None:
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert read_state() is None


def test_read_state_non_dict_returns_none() -> None:
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert read_state() is None


def test_write_and_read_roundtrip() -> None:
    ownership = _make_ownership()
    topology = (
        TeamCluster(
            name="backend",
            members=("@alice", "@bob"),
            primary_paths=("src/api/",),
            declared=True,
        ),
    )
    bus_factor = (
        BusFactor(
            path="src/auth.py",
            bus_factor=1,
            contributors_above_threshold=("@alice",),
            recommended_backups=("@bob",),
        ),
    )
    target = write_state(
        ownership,
        topology=topology,
        bus_factor_summary=bus_factor,
        drift_detected=True,
    )
    assert target.exists()
    data = read_state()
    assert data is not None
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["drift_detected"] is True
    assert data["topology"]["clusters"][0]["name"] == "backend"
    assert data["bus_factor_summary"]["critical_paths"] == ["src/auth.py"]
    assert data["bus_factor_summary"]["repo_average"] == 1.0
    assert "src/auth.py" in data["inferred"]


def test_load_ownership_roundtrip() -> None:
    original = _make_ownership()
    write_state(original)
    loaded = load_ownership()
    assert loaded is not None
    assert set(loaded.paths) == set(original.paths)
    loaded_owner = loaded.paths["src/auth.py"].owners[0]
    assert loaded_owner.handle == "@alice"
    assert loaded_owner.confidence == pytest.approx(0.85)
    assert loaded_owner.commits == 12
    assert loaded_owner.last_commit == _NOW
    assert loaded_owner.score_breakdown is not None
    assert loaded_owner.score_breakdown.recency == pytest.approx(0.9)
    decay = loaded.paths["src/auth.py"].decay_warnings[0]
    assert decay.handle == "@bob"
    assert decay.days_since_last_commit == 200


def test_load_ownership_missing_returns_none() -> None:
    assert load_ownership() is None


def test_load_ownership_invalid_returns_none() -> None:
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "inferred": "not a dict"}),
        encoding="utf-8",
    )
    assert load_ownership() is None


def test_load_ownership_skips_malformed_path() -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "inferred": {
            "src/good.py": {
                "owners": [
                    {
                        "handle": "@alice",
                        "confidence": 0.5,
                        "last_commit": _NOW.isoformat(),
                        "commits": 3,
                    }
                ],
                "bus_factor": 1,
                "decay_warnings": [],
            },
            "src/bad.py": "garbage",
        },
        "last_analyzed": _NOW.isoformat(),
        "drift_detected": False,
    }
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_ownership()
    assert loaded is not None
    assert set(loaded.paths) == {"src/good.py"}


def test_write_state_creates_parent_dirs(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "dir"
    with patch.dict("os.environ", {"CHECKOWNERS_STATE_DIR": str(nested)}):
        write_state(_make_ownership())
    assert (nested / "state.json").exists()


def test_bus_factor_summary_empty() -> None:
    ownership = _make_ownership()
    target = write_state(ownership)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["bus_factor_summary"]["critical_paths"] == []
    assert data["bus_factor_summary"]["repo_average"] == 0.0


def test_graph_cache_roundtrip(tmp_path: Path) -> None:
    graph_data = {"nodes": [{"id": "contrib::a"}], "edges": []}
    target = write_graph_cache(tmp_path, _NOW, graph_data)
    assert target.exists()
    assert read_graph_cache(tmp_path, _NOW) == graph_data


def test_graph_cache_stale_timestamp_ignored(tmp_path: Path) -> None:
    write_graph_cache(tmp_path, _NOW, {"nodes": [], "edges": []})
    newer = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    assert read_graph_cache(tmp_path, newer) is None


def test_graph_cache_missing_returns_none(tmp_path: Path) -> None:
    assert read_graph_cache(tmp_path, _NOW) is None


def test_graph_cache_keyed_by_repo(tmp_path: Path) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    write_graph_cache(repo_a, _NOW, {"nodes": [{"id": "a"}], "edges": []})
    assert read_graph_cache(repo_b, _NOW) is None
    assert read_graph_cache(repo_a, _NOW) == {"nodes": [{"id": "a"}], "edges": []}
