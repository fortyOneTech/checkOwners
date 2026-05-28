"""Webhook notification on drift events."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from checkowners.models import Config, DriftEntry, DriftResult, Severity

_SEVERITY_ORDER: tuple[Severity, ...] = ("low", "medium", "high", "critical")


def send_notification(result: DriftResult, config: Config) -> bool:
    """POST drift result to the configured webhook URL.

    Returns True if the payload was sent, False if skipped because no webhook
    URL is configured or the computed severity is below severity_threshold.
    """
    if not config.notifications.webhook_url:
        return False
    severity = compute_severity(result)
    if not _meets_threshold(severity, config.notifications.severity_threshold):
        return False
    payload = _build_payload(result, severity, config)
    _post_webhook(config.notifications.webhook_url, payload)
    return True


def compute_severity(result: DriftResult) -> Severity:
    """Map the max confidence delta + bus factor signals to a severity level."""
    if _has_critical_signal(result):
        return "critical"
    delta = result.max_confidence_delta
    if delta >= 0.7:
        return "high"
    if delta >= 0.3:
        return "medium"
    return "low"


def _has_critical_signal(result: DriftResult) -> bool:
    for entries in (result.stale, result.missing, result.changed):
        for entry in entries:
            if entry.bus_factor is not None and entry.bus_factor <= 1:
                return True
            if entry.decay:
                return True
    return False


def _meets_threshold(severity: Severity, threshold: Severity) -> bool:
    return _SEVERITY_ORDER.index(severity) >= _SEVERITY_ORDER.index(threshold)


def _build_payload(
    result: DriftResult,
    severity: Severity,
    config: Config,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "drift_detected": result.drift_detected,
        "severity": severity,
        "max_confidence_delta": result.max_confidence_delta,
        "stale": [_entry_payload(e) for e in result.stale],
        "missing": [_entry_payload(e) for e in result.missing],
        "changed": [_entry_payload(e) for e in result.changed],
    }
    if config.notifications.include_unchanged:
        payload["include_unchanged"] = True
    return payload


def _entry_payload(entry: DriftEntry) -> dict[str, Any]:
    body: dict[str, Any] = {
        "path": entry.path,
        "confidence_delta": entry.confidence_delta,
        "reason": entry.reason,
    }
    if entry.bus_factor is not None:
        body["bus_factor"] = entry.bus_factor
    if entry.decay:
        body["decay"] = entry.decay
    return body


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
