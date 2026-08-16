#!/usr/bin/env python3
"""Shared config + path resolution for the YouTube Checker scripts.

Config precedence: environment variable > config/config.json > built-in default.
Nothing here talks to the network.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "config.json"
EXAMPLE_PATH = ROOT / "config" / "config.example.json"
CACHE_DIR = ROOT / "data" / "cache"

DEFAULTS: dict[str, Any] = {
    "channel": {"id": "", "handle": ""},
    "competitor_channel_ids": [],
    "median": {
        "lookback_uploads": 30,
        "exclude_younger_than_days": 30,
        "min_duration_seconds": 90,
        "cache_days": 7,
    },
    "saturation": {
        "mode_a_window_days": 7,
        "mode_a_closed_at_channels": 3,
        "mode_b_window_days": 90,
        "mode_b_relevant_views": 20000,
        "big_channel_subscribers": 100000,
        "big_channel_window_days": 30,
    },
    "execution": {"available_hours_per_video": 8, "paid_tools": []},
    "notion": {"backlog_database": "Idea Backlog - Youtube", "write_back": False},
    "prediction_log": {"path": "data/predictions.csv"},
}

API_KEY_VARS = ("YOUTUBE_API_KEY", "YT_API_KEY", "YOUTUBE_DATA_API_KEY")


class ConfigError(RuntimeError):
    pass


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict:
    """Return the merged config. Missing config.json is not an error."""
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"config/config.json is not valid JSON: {exc}") from exc
        cfg = _merge(cfg, user)

    # Environment overrides for the values most likely to differ per machine.
    if os.environ.get("YT_CHANNEL_ID"):
        cfg["channel"]["id"] = os.environ["YT_CHANNEL_ID"]
    if os.environ.get("YT_CHANNEL_HANDLE"):
        cfg["channel"]["handle"] = os.environ["YT_CHANNEL_HANDLE"]
    if os.environ.get("COMPETITOR_CHANNEL_IDS"):
        cfg["competitor_channel_ids"] = [
            c.strip() for c in os.environ["COMPETITOR_CHANNEL_IDS"].split(",") if c.strip()
        ]
    return cfg


def api_key() -> str:
    for var in API_KEY_VARS:
        value = os.environ.get(var)
        if value:
            return value.strip()
    raise ConfigError(
        "No YouTube Data API key found. Set one of: "
        + ", ".join(API_KEY_VARS)
        + "\n(Reuse the key from the Viral Content System, or create one at "
        "https://console.cloud.google.com/apis/credentials with YouTube Data API v3 enabled.)"
    )


def own_channel_ref(cfg: dict | None = None) -> str:
    cfg = cfg or load()
    ref = cfg["channel"].get("id") or cfg["channel"].get("handle")
    if not ref:
        raise ConfigError(
            "No channel configured. Set channel.id or channel.handle in config/config.json "
            "(copy config/config.example.json), or export YT_CHANNEL_ID / YT_CHANNEL_HANDLE."
        )
    return ref


def prediction_log_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load()
    return ROOT / cfg["prediction_log"]["path"]


if __name__ == "__main__":
    import sys

    print(json.dumps(load(), indent=2))
    try:
        key = api_key()
        print(f"\napi key: found ({len(key)} chars)", file=sys.stderr)
    except ConfigError as exc:
        print(f"\napi key: MISSING\n{exc}", file=sys.stderr)
