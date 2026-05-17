from __future__ import annotations

import logging
from unittest.mock import patch

from fa.core.quota import QuotaResult
from fa.nudge.runner import CircuitBreaker, CircuitBreakerAction, extract_task_id


def test_extract_task_id_from_valid_json():
    assert extract_task_id('{"task_id": 42}') == 42


def test_extract_task_id_from_code_block():
    text = 'Some output\n```json\n{"task_id": 7}\n```\nMore text'
    assert extract_task_id(text) == 7


def test_extract_task_id_from_embedded_json():
    text = 'Here is the result: {"task_id": 99, "status": "ok"} done'
    assert extract_task_id(text) == 99


def test_extract_task_id_returns_none_for_empty():
    assert extract_task_id("") is None


def test_extract_task_id_returns_none_for_no_task_id():
    assert extract_task_id('{"foo": "bar"}') is None


def test_extract_task_id_handles_nested_braces():
    text = '{"outer": {"inner": "val"}, "task_id": 3}'
    assert extract_task_id(text) == 3


def test_extract_task_id_finds_code_block_when_direct_parse_fails():
    text = 'Result:\n```json\n{"task_id": 9}\n```\nDone'
    assert extract_task_id(text) == 9


def test_extract_task_id_handles_string_task_id():
    assert extract_task_id('{"task_id": "15"}') == 15


def test_circuit_breaker_proceeds_below_max():
    logger = logging.getLogger("test")
    with patch("fa.nudge.runner.check_glm_quota", return_value=QuotaResult(True, None)):
        breaker = CircuitBreaker(
            max_iterations=5, quota_threshold=90.0, quota_buffer_seconds=1800
        )
        for _ in range(5):
            action, wait_until = breaker.check(logger)
            assert action == CircuitBreakerAction.PROCEED
            assert wait_until is None


def test_circuit_breaker_stops_at_max():
    logger = logging.getLogger("test")
    with patch("fa.nudge.runner.check_glm_quota", return_value=QuotaResult(True, None)):
        breaker = CircuitBreaker(
            max_iterations=3, quota_threshold=90.0, quota_buffer_seconds=1800
        )
        for _ in range(3):
            breaker.check(logger)
        action, _ = breaker.check(logger)
        assert action == CircuitBreakerAction.STOP


def test_circuit_breaker_waits_on_quota_exceeded():
    logger = logging.getLogger("test")
    wait_until_ts = 1700000000.0
    with patch(
        "fa.nudge.runner.check_glm_quota",
        return_value=QuotaResult(False, int(wait_until_ts)),
    ):
        breaker = CircuitBreaker(
            max_iterations=10, quota_threshold=90.0, quota_buffer_seconds=1800
        )
        action, wait_until = breaker.check(logger)
        assert action == CircuitBreakerAction.WAIT
        assert wait_until == wait_until_ts + 1800


def test_circuit_breaker_proceeds_on_quota_api_failure():
    logger = logging.getLogger("test")
    with patch(
        "fa.nudge.runner.check_glm_quota", return_value=QuotaResult(False, None)
    ):
        breaker = CircuitBreaker(
            max_iterations=10, quota_threshold=90.0, quota_buffer_seconds=1800
        )
        action, wait_until = breaker.check(logger)
        assert action == CircuitBreakerAction.PROCEED
        assert wait_until is None
