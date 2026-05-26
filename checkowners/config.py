"""Configuration loader for .github/checkowners.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from checkowners.models import (
    AnalysisConfig,
    Config,
    DriftConfig,
    NotificationsConfig,
    OutputConfig,
    PathsConfig,
)

CONFIG_FILENAME = ".github/checkowners.yml"


def load_config(repo_root: Path | None = None) -> Config:
    """Load configuration from .github/checkowners.yml, merging with defaults."""
    config_path = _resolve_config_path(repo_root)
    if not config_path.exists():
        return Config()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw is None:
        return Config()
    if not isinstance(raw, dict):
        msg = f"Invalid checkowners config: expected a YAML mapping, got {type(raw).__name__}"
        raise ValueError(msg)
    return _merge_config(raw)


def _resolve_config_path(repo_root: Path | None) -> Path:
    root = repo_root if repo_root is not None else Path.cwd()
    return root / CONFIG_FILENAME


def _merge_config(raw: dict[str, Any]) -> Config:
    kwargs: dict[str, Any] = {}
    if "analysis" in raw and isinstance(raw["analysis"], dict):
        kwargs["analysis"] = _build_analysis_config(raw["analysis"])
    if "paths" in raw and isinstance(raw["paths"], dict):
        kwargs["paths"] = _build_paths_config(raw["paths"])
    if "output" in raw and isinstance(raw["output"], dict):
        kwargs["output"] = _build_output_config(raw["output"])
    if "drift" in raw and isinstance(raw["drift"], dict):
        kwargs["drift"] = _build_drift_config(raw["drift"])
    if "notifications" in raw and isinstance(raw["notifications"], dict):
        kwargs["notifications"] = _build_notifications_config(raw["notifications"])
    return Config(**kwargs)


def _build_analysis_config(data: dict[str, Any]) -> AnalysisConfig:
    kwargs: dict[str, Any] = {}
    if "lookback_days" in data:
        kwargs["lookback_days"] = int(data["lookback_days"])
    if "min_commits" in data:
        kwargs["min_commits"] = int(data["min_commits"])
    if "top_n_owners" in data:
        kwargs["top_n_owners"] = int(data["top_n_owners"])
    return AnalysisConfig(**kwargs)


def _build_paths_config(data: dict[str, Any]) -> PathsConfig:
    kwargs: dict[str, Any] = {}
    if "exclude" in data and isinstance(data["exclude"], list):
        kwargs["exclude"] = tuple(str(item) for item in data["exclude"])
    return PathsConfig(**kwargs)


def _build_output_config(data: dict[str, Any]) -> OutputConfig:
    kwargs: dict[str, Any] = {}
    if "header" in data:
        kwargs["header"] = str(data["header"])
    if "include_unowned" in data:
        kwargs["include_unowned"] = bool(data["include_unowned"])
    return OutputConfig(**kwargs)


def _build_drift_config(data: dict[str, Any]) -> DriftConfig:
    kwargs: dict[str, Any] = {}
    if "mode" in data:
        kwargs["mode"] = str(data["mode"])
    if "compare_to" in data:
        kwargs["compare_to"] = str(data["compare_to"])
    return DriftConfig(**kwargs)


def _build_notifications_config(data: dict[str, Any]) -> NotificationsConfig:
    kwargs: dict[str, Any] = {}
    if "webhook_url" in data:
        kwargs["webhook_url"] = str(data["webhook_url"])
    if "include_unchanged" in data:
        kwargs["include_unchanged"] = bool(data["include_unchanged"])
    return NotificationsConfig(**kwargs)
