from __future__ import annotations

import json
import logging
import re
import signal
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from fa.core.config import AGENT_LOGS_DIR_NAME, LOGS_DIR_NAME
from fa.core.quota import check_glm_quota, wait_for_quota_reset
from fa.core.subprocess import run_tool
from fa.task.storage import fa_dir


def extract_task_id(output: str) -> int | None:
    try:
        data = json.loads(output)
        if isinstance(data, dict) and "task_id" in data:
            return int(data["task_id"])
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    code_block_match = re.search(r"```json\s*(.*?)\s*```", output, re.DOTALL)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1))
            if isinstance(data, dict) and "task_id" in data:
                return int(data["task_id"])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    for obj in _find_json_objects(output):
        try:
            data = json.loads(obj)
            if isinstance(data, dict) and "task_id" in data:
                return int(data["task_id"])
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    return None


def _find_json_objects(text: str) -> list[str]:
    results: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            depth = 1
            j = i + 1
            while j < len(text) and depth > 0:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            if depth == 0:
                results.append(text[i:j])
            i = j
        else:
            i += 1
    return results


class CircuitBreakerAction(Enum):
    PROCEED = "proceed"
    WAIT = "wait"
    STOP = "stop"


@dataclass
class CircuitBreaker:
    max_iterations: int = 100
    quota_threshold: float = 90.0
    quota_buffer_seconds: int = 1800
    _iteration: int = field(default=0, init=False)

    def check(
        self, logger: logging.Logger
    ) -> tuple[CircuitBreakerAction, float | None]:
        self._iteration += 1
        if self._iteration > self.max_iterations:
            return (CircuitBreakerAction.STOP, None)
        result = check_glm_quota(logger, threshold=int(self.quota_threshold))
        if result.proceed:
            return (CircuitBreakerAction.PROCEED, None)
        if result.wait_until_ts is not None:
            return (
                CircuitBreakerAction.WAIT,
                result.wait_until_ts + self.quota_buffer_seconds,
            )
        return (CircuitBreakerAction.PROCEED, None)


_stop_event = threading.Event()


def _handle_signal(signum: int, frame: object) -> None:
    _stop_event.set()


def run_nudge_loop(
    *,
    logger: logging.Logger,
    tool: str,
    gestate_tool: str,
    prompt: str,
    max_iterations: int,
    quota_threshold: float,
    quota_buffer_seconds: int,
    gestate_max_rounds: int,
    gestate_run_rounds: int,
    gestate_run: bool,
    model: str | None = None,
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    profile: str | None = None,
) -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    breaker = CircuitBreaker(max_iterations, quota_threshold, quota_buffer_seconds)
    while not _stop_event.is_set():
        action, wait_until = breaker.check(logger)
        if action == CircuitBreakerAction.STOP:
            logger.info("Circuit breaker: max iterations (%d) reached", max_iterations)
            return 0
        if action == CircuitBreakerAction.WAIT and wait_until is not None:
            wait_for_quota_reset(int(wait_until), logger)
        if _stop_event.is_set():
            break
        log_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / "nudge"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"nudge-{breaker._iteration}-{timestamp}.log"
        code = run_tool(
            tool,
            prompt,
            log_path,
            logger,
            model=model,
            extra_args=extra_args,
            extra_env=extra_env,
        )
        if code != 0:
            logger.warning(
                "Nudge iteration %d: tool exited with code %d", breaker._iteration, code
            )
            continue
        output = log_path.read_text(encoding="utf-8")
        task_id = extract_task_id(output)
        if task_id is None:
            logger.warning(
                "Nudge iteration %d: no task_id found in output", breaker._iteration
            )
            continue
        from fa.gestate.commands import gestate

        try:
            gestate(
                arg=str(task_id),
                tool=gestate_tool,
                max_rounds=gestate_max_rounds,
                run=gestate_run,
                run_tool=gestate_tool,
                run_rounds=gestate_run_rounds,
                profile=profile,
            )
        except SystemExit as exc:
            if exc.code not in (None, 0):
                logger.error(
                    "Nudge iteration %d: gestate for task %d failed (exit %s)",
                    breaker._iteration,
                    task_id,
                    exc.code,
                )
                continue
        logger.info(
            "Nudge iteration %d: gestate for task %d completed",
            breaker._iteration,
            task_id,
        )
    logger.info("Nudge loop stopped by signal")
    return 0
