from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import datetime
from pathlib import Path


def _load_settings() -> dict | None:
    path = Path.home() / ".claude" / "settings.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


THRESHOLD = 70


def check_glm_quota(logger: logging.Logger) -> bool:
    settings = _load_settings()
    token = (settings or {}).get("env", {}).get("ANTHROPIC_AUTH_TOKEN")
    if not token:
        logger.debug("GLM quota: no token found, skipping check")
        return True
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/monitor/usage/quota/limit"
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.load(response)
    except Exception as exc:
        logger.warning("GLM quota: check failed (%s) - proceeding", exc)
        return True
    for item in data.get("data", {}).get("limits", []):
        if item.get("type") != "TOKENS_LIMIT":
            continue
        percentage = float(item.get("percentage", 0))
        if percentage < THRESHOLD:
            logger.debug(
                "GLM quota: %.0f%% (threshold: %d%%) - proceeding",
                percentage,
                THRESHOLD,
            )
            return True
        next_reset = item.get("nextResetTime")
        if not next_reset:
            logger.warning(
                "GLM quota: %.0f%% (threshold: %d%%) - no reset time, cannot wait",
                percentage,
                THRESHOLD,
            )
            return False
        wait_until_ts = int(next_reset / 1000) + 1800
        wait_until_dt = datetime.fromtimestamp(wait_until_ts)
        logger.warning(
            "GLM quota: %.0f%% (threshold: %d%%) - waiting until %s (+30min buffer)",
            percentage,
            THRESHOLD,
            wait_until_dt.strftime("%Y-%m-%d %H:%M:%S"),
        )
        while time.time() < wait_until_ts:
            time.sleep(10)
        logger.debug("GLM quota: wait complete - proceeding")
        return True
    logger.debug("GLM quota: no TOKENS_LIMIT entry found - proceeding")
    return True
