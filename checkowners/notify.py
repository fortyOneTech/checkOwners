"""Webhook notification on drift events."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from checkowners.models import Config, DriftResult


def send_notification(result: DriftResult, config: Config) -> bool:
    """POST drift result to the configured webhook URL.

    Returns True if notification was sent, False if skipped.
    """
    if not config.notifications.webhook_url:
        return False
    payload = _build_payload(result, config)
    _post_webhook(config.notifications.webhook_url, payload)
    return True


def _build_payload(result: DriftResult, config: Config) -> dict[str, Any]:
    """Build the webhook JSON payload."""
    payload: dict[str, Any] = {
        "drift_detected": result.drift_detected,
        "stale": list(result.stale),
        "missing": list(result.missing),
        "changed": list(result.changed),
    }
    if config.notifications.include_unchanged:
        payload["include_unchanged"] = True
    return payload


def _post_webhook(url: str, payload: dict[str, Any]) -> None:
    """Send an HTTP POST with JSON payload to the given URL."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30)  # noqa: S310
