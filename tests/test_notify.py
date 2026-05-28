"""Tests for checkowners.notify module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from checkowners.models import (
    Config,
    DriftEntry,
    DriftResult,
    NotificationsConfig,
)
from checkowners.notify import (
    _build_payload,
    compute_severity,
    send_notification,
)


def _drift_with(
    *,
    delta: float = 1.0,
    bus_factor: int | None = None,
    decay: bool = False,
    detected: bool = True,
) -> DriftResult:
    if not detected:
        return DriftResult(stale=(), missing=(), changed=(), drift_detected=False)
    entry = DriftEntry(
        path="/src/main.py",
        confidence_delta=delta,
        reason="test",
        bus_factor=bus_factor,
        decay=decay,
    )
    return DriftResult(stale=(entry,), missing=(), changed=(), drift_detected=True)


def test_send_notification_skips_empty_url() -> None:
    config = Config(notifications=NotificationsConfig(webhook_url=""))
    assert send_notification(_drift_with(), config) is False


def test_send_notification_posts_webhook() -> None:
    config = Config(
        notifications=NotificationsConfig(
            webhook_url="https://hooks.example.com/drift",
            severity_threshold="low",
        ),
    )
    with patch("checkowners.notify.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        sent = send_notification(_drift_with(delta=0.9), config)
    assert sent is True
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://hooks.example.com/drift"
    assert req.get_header("Content-type") == "application/json"


def test_send_notification_skipped_when_below_threshold() -> None:
    config = Config(
        notifications=NotificationsConfig(
            webhook_url="https://hooks.example.com/drift",
            severity_threshold="critical",
        ),
    )
    with patch("checkowners.notify.urllib.request.urlopen") as mock_urlopen:
        sent = send_notification(_drift_with(delta=0.2), config)
    assert sent is False
    mock_urlopen.assert_not_called()


def test_compute_severity_low_medium_high_critical() -> None:
    assert compute_severity(_drift_with(delta=0.1)) == "low"
    assert compute_severity(_drift_with(delta=0.4)) == "medium"
    assert compute_severity(_drift_with(delta=0.8)) == "high"
    assert compute_severity(_drift_with(delta=0.8, bus_factor=1)) == "critical"
    assert compute_severity(_drift_with(delta=0.1, decay=True)) == "critical"


def test_compute_severity_no_drift_is_low() -> None:
    assert compute_severity(_drift_with(detected=False)) == "low"


def test_build_payload_basic() -> None:
    result = _drift_with(delta=0.6, bus_factor=2)
    config = Config()
    payload = _build_payload(result, "medium", config)
    assert payload["drift_detected"] is True
    assert payload["severity"] == "medium"
    assert payload["max_confidence_delta"] == 0.6
    assert payload["stale"][0]["path"] == "/src/main.py"
    assert payload["stale"][0]["bus_factor"] == 2
    assert "include_unchanged" not in payload


def test_build_payload_include_unchanged() -> None:
    result = _drift_with(delta=0.6)
    config = Config(notifications=NotificationsConfig(include_unchanged=True))
    payload = _build_payload(result, "medium", config)
    assert payload["include_unchanged"] is True


def test_send_notification_critical_signal_overrides_low_delta() -> None:
    config = Config(
        notifications=NotificationsConfig(
            webhook_url="https://hooks.example.com/drift",
            severity_threshold="critical",
        ),
    )
    drift = _drift_with(delta=0.05, bus_factor=1)
    captured: list[bytes] = []

    def _capture(req, timeout):  # type: ignore[no-untyped-def]
        captured.append(req.data)
        return MagicMock()

    with patch("checkowners.notify.urllib.request.urlopen", side_effect=_capture):
        sent = send_notification(drift, config)
    assert sent is True
    body = json.loads(captured[0].decode("utf-8"))
    assert body["severity"] == "critical"
