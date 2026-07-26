#!/usr/bin/env python3
"""Check a website's reachability and post a Discord alert when its status changes."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("uptime_monitor")

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_STATE_FILE = "state.json"
FAILURE_THRESHOLD = 2  # consecutive failed checks required before declaring "down"


@dataclass
class State:
    status: str = "unknown"  # "up", "down", or "unknown" (no successful check yet)
    consecutive_failures: int = 0


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def load_config() -> dict:
    target_url = os.environ.get("TARGET_URL", "https://www.uwrf.edu/").strip()
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    site_name = os.environ.get("SITE_NAME", "").strip() or urlparse(target_url).netloc or target_url
    state_file = os.environ.get("STATE_FILE", DEFAULT_STATE_FILE).strip()

    try:
        timeout = float(os.environ.get("TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError as exc:
        raise ConfigError(f"TIMEOUT_SECONDS must be a number, got {os.environ.get('TIMEOUT_SECONDS')!r}") from exc

    if not webhook_url:
        raise ConfigError(
            "DISCORD_WEBHOOK_URL environment variable is not set. "
            "Set it to your Discord webhook URL (do not hardcode it in source)."
        )
    if not target_url:
        raise ConfigError("TARGET_URL environment variable is empty.")

    return {
        "target_url": target_url,
        "webhook_url": webhook_url,
        "site_name": site_name,
        "state_file": Path(state_file),
        "timeout": timeout,
    }


def load_state(state_file: Path) -> State:
    if not state_file.exists():
        log.info("No existing state file at %s; starting fresh.", state_file)
        return State()

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return State(
            status=data.get("status", "unknown"),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
        )
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        log.warning("Could not read state file %s (%s); starting fresh.", state_file, exc)
        return State()


def save_state(state_file: Path, state: State) -> None:
    try:
        state_file.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
    except OSError as exc:
        log.error("Failed to write state file %s: %s", state_file, exc)


def check_site(url: str, timeout: float) -> bool:
    """Return True if the site is considered reachable (2xx response)."""
    try:
        response = requests.get(url, timeout=timeout)
        if 200 <= response.status_code < 300:
            log.info("Check OK: %s returned HTTP %s", url, response.status_code)
            return True
        log.warning("Check FAILED: %s returned HTTP %s", url, response.status_code)
        return False
    except requests.exceptions.Timeout:
        log.warning("Check FAILED: %s timed out after %ss", url, timeout)
        return False
    except requests.exceptions.ConnectionError as exc:
        log.warning("Check FAILED: could not connect to %s (%s)", url, exc)
        return False
    except requests.exceptions.RequestException as exc:
        log.warning("Check FAILED: request error for %s (%s)", url, exc)
        return False


def send_discord_alert(webhook_url: str, site_name: str, target_url: str, went_up: bool) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if went_up:
        content = f":white_check_mark: **{site_name}** is back **UP** ({target_url})\n_{timestamp}_"
    else:
        content = f":x: **{site_name}** just went **DOWN** ({target_url})\n_{timestamp}_"

    try:
        response = requests.post(webhook_url, json={"content": content}, timeout=10)
        response.raise_for_status()
        log.info("Discord alert sent: %s", "UP" if went_up else "DOWN")
    except requests.exceptions.RequestException as exc:
        log.error("Failed to send Discord alert: %s", exc)


def run() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        return 2

    state = load_state(config["state_file"])
    is_up = check_site(config["target_url"], config["timeout"])

    if is_up:
        if state.status == "down":
            send_discord_alert(config["webhook_url"], config["site_name"], config["target_url"], went_up=True)
        state.status = "up"
        state.consecutive_failures = 0
    else:
        state.consecutive_failures += 1
        if state.consecutive_failures >= FAILURE_THRESHOLD and state.status != "down":
            send_discord_alert(config["webhook_url"], config["site_name"], config["target_url"], went_up=False)
            state.status = "down"
        elif state.consecutive_failures < FAILURE_THRESHOLD:
            log.info(
                "Failure %d/%d for %s; waiting for confirmation before alerting.",
                state.consecutive_failures,
                FAILURE_THRESHOLD,
                config["target_url"],
            )

    save_state(config["state_file"], state)
    return 0


if __name__ == "__main__":
    sys.exit(run())
