"""Tests for checkowners.notify module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from checkowners.models import Config, DriftResult, NotificationsConfig
from checkowners.notify import _build_payload, send_notification


def _make_drift(*, drift_detected: bool = True) -> DriftResult:
    return DriftResult(
        stale=("/old.py",) if drift_detected else (),
        missing=("/new.py",) if drift_detected else (),
        changed=(),
        drift_detected=drift_detected,
    )


def test_send_notification_skips_empty_url() -> None:
    result = _make_drift()
    config = Config(notifications=NotificationsConfig(webhook_url=""))
    assert send_notification(result, config) is False


def test_send_notification_posts_webhook() -> None:
    result = _make_drift()
    config = Config(
        notifications=NotificationsConfig(webhook_url="https://hooks.example.com/drift"),
    )
    with patch("checkowners.notify.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        sent = send_notification(result, config)
    assert sent is True
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://hooks.example.com/drift"
    assert req.get_header("Content-type") == "application/json"


def test_build_payload_basic() -> None:
    result = _make_drift()
    config = Config()
    payload = _build_payload(result, config)
    assert payload["drift_detected"] is True
    assert payload["stale"] == ["/old.py"]
    assert payload["missing"] == ["/new.py"]
    assert payload["changed"] == []
    assert "include_unchanged" not in payload


def test_build_payload_include_unchanged() -> None:
    result = _make_drift()
    config = Config(notifications=NotificationsConfig(include_unchanged=True))
    payload = _build_payload(result, config)
    assert payload["include_unchanged"] is True


def test_send_notification_no_drift() -> None:
    result = _make_drift(drift_detected=False)
    config = Config(
        notifications=NotificationsConfig(webhook_url="https://hooks.example.com/drift"),
    )
    with patch("checkowners.notify.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        sent = send_notification(result, config)
    assert sent is True
