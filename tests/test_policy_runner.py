from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fa.policy.runner import run_policies_by_ids, run_policy


def test_run_policies_by_ids_returns_zero_when_all_succeed():
    with patch("fa.policy.runner.run_policy", return_value=0):
        result = run_policies_by_ids(
            logger=MagicMock(),
            policy_ids=["policy1", "policy2"],
            tool="codex",
            rounds=1,
        )
    assert result == 0


def test_run_policies_by_ids_returns_one_when_any_fails():
    with patch("fa.policy.runner.run_policy", return_value=1):
        result = run_policies_by_ids(
            logger=MagicMock(),
            policy_ids=["policy1", "policy2"],
            tool="codex",
            rounds=1,
        )
    assert result == 1


def test_run_policies_by_ids_handles_missing_policy():
    with patch("fa.policy.runner.run_policy", side_effect=FileNotFoundError):
        logger = MagicMock()
        result = run_policies_by_ids(
            logger=logger,
            policy_ids=["nonexistent"],
            tool="codex",
            rounds=1,
        )
    assert result == 1
    logger.error.assert_called()


def test_run_policy_returns_zero_on_success():
    with TemporaryDirectory() as tempdir:
        with patch("fa.policy.runner.run_tool", return_value=0):
            with patch("fa.policy.runner.load_policy") as mock_load:
                mock_policy = MagicMock()
                mock_policy.id = "test"
                mock_policy.name = "Test Policy"
                mock_policy.objective = "Test objective"
                mock_policy.specs = []
                mock_policy.scopes.required = []
                mock_policy.scopes.exclude = []
                mock_policy.report.path = "report.md"
                mock_policy.agent = None
                mock_load.return_value = mock_policy

                with patch("fa.policy.runner.fa_dir", return_value=Path(tempdir)):
                    result = run_policy(
                        logger=MagicMock(),
                        policy_id="test",
                        tool="codex",
                        rounds=1,
                    )
        assert result == 0


def test_run_policy_returns_one_when_tool_fails():
    with TemporaryDirectory() as tempdir:
        with patch("fa.policy.runner.run_tool", return_value=1):
            with patch("fa.policy.runner.load_policy") as mock_load:
                mock_policy = MagicMock()
                mock_policy.id = "test"
                mock_policy.name = "Test Policy"
                mock_policy.objective = "Test objective"
                mock_policy.specs = []
                mock_policy.scopes.required = []
                mock_policy.scopes.exclude = []
                mock_policy.report.path = "report.md"
                mock_policy.agent = None
                mock_load.return_value = mock_policy

                with patch("fa.policy.runner.fa_dir", return_value=Path(tempdir)):
                    result = run_policy(
                        logger=MagicMock(),
                        policy_id="test",
                        tool="codex",
                        rounds=1,
                    )
        assert result == 1


def test_run_policy_continues_through_all_rounds():
    with TemporaryDirectory() as tempdir:
        with patch("fa.policy.runner.run_tool", return_value=0) as mock_run:
            with patch("fa.policy.runner.load_policy") as mock_load:
                mock_policy = MagicMock()
                mock_policy.id = "test"
                mock_policy.name = "Test Policy"
                mock_policy.objective = "Test objective"
                mock_policy.specs = []
                mock_policy.scopes.required = []
                mock_policy.scopes.exclude = []
                mock_policy.report.path = "report.md"
                mock_policy.agent = None
                mock_load.return_value = mock_policy

                with patch("fa.policy.runner.fa_dir", return_value=Path(tempdir)):
                    result = run_policy(
                        logger=MagicMock(),
                        policy_id="test",
                        tool="codex",
                        rounds=3,
                    )
        assert result == 0
        assert mock_run.call_count == 3


def test_run_policy_returns_one_when_glm_quota_fails():
    with TemporaryDirectory() as tempdir:
        with patch("fa.policy.runner.check_glm_quota_and_wait", return_value=False):
            with patch("fa.policy.runner.load_policy") as mock_load:
                mock_policy = MagicMock()
                mock_policy.id = "test"
                mock_load.return_value = mock_policy

                with patch("fa.policy.runner.fa_dir", return_value=Path(tempdir)):
                    result = run_policy(
                        logger=MagicMock(),
                        policy_id="test",
                        tool="codex",
                        rounds=3,
                        glm_plan=True,
                    )
        assert result == 1
