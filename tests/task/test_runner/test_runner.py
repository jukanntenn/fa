import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fa.task import runner, storage
from fa.task.runner import _append_once


def test_append_once_adds_new_id():
    output = []
    appended = set()
    _append_once(output, appended, 5)
    assert output == [5]
    assert appended == {5}


def test_append_once_skips_duplicate():
    output = [5]
    appended = {5}
    _append_once(output, appended, 5)
    assert output == [5]
    assert appended == {5}


def test_append_once_preserves_order():
    output = []
    appended = set()
    _append_once(output, appended, 1)
    _append_once(output, appended, 2)
    _append_once(output, appended, 1)
    _append_once(output, appended, 3)
    assert output == [1, 2, 3]


def _create_approved_task(tmp_path: Path):
    with patch.object(storage, "find_project_root", return_value=tmp_path):
        task = storage.create_task("single")
        (task.path / "spec.md").write_text("spec", encoding="utf-8")
        (task.path / "plan.md").write_text("plan", encoding="utf-8")
        task.transition_to("approved")
        storage.save_task(task)
        return task


def test_run_tasks_passes_open_viewer_only_to_first_interactive_task() -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            first = storage.create_task("first")
            second = storage.create_task("second")
            for task in (first, second):
                (task.path / "spec.md").write_text("spec", encoding="utf-8")
                (task.path / "plan.md").write_text("plan", encoding="utf-8")
                task.transition_to("approved")
                storage.save_task(task)

            with (
                patch("fa.task.runner.build_task_prompt", return_value="prompt"),
                patch(
                    "fa.task.runner._run_task_interactive", return_value=False
                ) as run_interactive,
            ):
                result = runner.run_tasks(
                    logger=logging.getLogger("test"),
                    ids=[first.id, second.id],
                    force=False,
                    tool="claude",
                    rounds=1,
                    glm_plan=False,
                    attempt_mode=False,
                    open_viewer=True,
                )

    assert result == 0
    assert run_interactive.call_count == 2
    assert run_interactive.call_args_list[0].kwargs["open_viewer"]
    assert not run_interactive.call_args_list[1].kwargs["open_viewer"]


def test_run_tasks_uses_interactive_viewer_for_codex() -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("single")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")
            task.transition_to("approved")
            storage.save_task(task)

            with (
                patch("fa.task.runner.build_task_prompt", return_value="prompt"),
                patch(
                    "fa.task.runner._run_task_interactive", return_value=False
                ) as run_interactive,
            ):
                result = runner.run_tasks(
                    logger=logging.getLogger("test"),
                    ids=[task.id],
                    force=False,
                    tool="codex",
                    rounds=1,
                    glm_plan=False,
                    attempt_mode=False,
                    open_viewer=True,
                )

    assert result == 0
    run_interactive.assert_called_once()
    assert run_interactive.call_args.kwargs["tool"] == "codex"
    assert run_interactive.call_args.kwargs["open_viewer"]


def test_should_run_round_returns_true_when_glm_plan_false():
    from fa.task.runner import _should_run_round

    logger = MagicMock()
    result = _should_run_round(1, 1, 3, False, logger)
    assert result is True


def test_should_run_round_returns_true_when_quota_check_passes():
    from fa.task.runner import _should_run_round

    with patch("fa.task.runner.check_glm_quota_and_wait", return_value=True):
        logger = MagicMock()
        result = _should_run_round(1, 1, 3, True, logger)
        assert result is True


def test_should_run_round_returns_false_when_quota_check_fails():
    from fa.task.runner import _should_run_round

    with patch("fa.task.runner.check_glm_quota_and_wait", return_value=False):
        logger = MagicMock()
        result = _should_run_round(1, 1, 3, True, logger)
        assert result is False
        logger.error.assert_called_once()


def test_task_log_dir_returns_path_within_logs_dir(tmp_path: Path) -> None:
    from fa.task.runner import _task_log_dir

    task = _create_approved_task(tmp_path)
    with patch.object(storage, "find_project_root", return_value=tmp_path):
        result = _task_log_dir(task)

    assert "logs" in result.parts
    assert result.exists()
    assert result.is_dir()


def test_save_prompt_creates_normal_round_filename(tmp_path: Path) -> None:
    from fa.task.runner import _save_prompt

    result = _save_prompt(
        tmp_path, round_index=1, attempt=1, is_attempt_run=False, prompt="# Test"
    )

    assert result.name == "round-1-prompt.md"
    assert result.read_text(encoding="utf-8") == "# Test"


def test_save_prompt_creates_attempt_filename(tmp_path: Path) -> None:
    from fa.task.runner import _save_prompt

    result = _save_prompt(
        tmp_path, round_index=2, attempt=3, is_attempt_run=True, prompt="# Attempt"
    )

    assert result.name == "round-2-attempt-3-prompt.md"
    assert result.read_text(encoding="utf-8") == "# Attempt"


def test_save_prompt_creates_parent_directories(tmp_path: Path) -> None:
    from fa.task.runner import _save_prompt

    subdir = tmp_path / "subdir" / "nested"
    result = _save_prompt(
        subdir, round_index=1, attempt=1, is_attempt_run=False, prompt="# Nested"
    )

    assert result.parent.exists()
    assert result.read_text(encoding="utf-8") == "# Nested"


def test_prompt_run_context_fresh_mode(tmp_path: Path) -> None:
    from fa.task.runner import _prompt_run_context

    task = _create_approved_task(tmp_path)
    result = _prompt_run_context(task, attempt_mode=False)

    assert result.mode == "fresh"
    assert result.attempt == 1
    assert result.feedback_count == 0


def test_prompt_run_context_attempt_mode(tmp_path: Path) -> None:
    from fa.task.runner import _prompt_run_context

    with patch.object(storage, "find_project_root", return_value=tmp_path):
        task = storage.create_task("test-task")
        (task.path / "spec.md").write_text("spec", encoding="utf-8")
        (task.path / "plan.md").write_text("plan", encoding="utf-8")
        task.transition_to("approved")
        (task.path / "feedback-1.md").write_text("feedback", encoding="utf-8")
        storage.save_task(task)

        result = _prompt_run_context(task, attempt_mode=True)

    assert result.mode == "attempt"
    assert result.attempt == 2
    assert result.feedback_count == 1


def test_run_task_batch_returns_false_when_all_rounds_succeed(tmp_path: Path) -> None:
    from fa.task.runner import _run_task_batch

    task = _create_approved_task(tmp_path)

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    with patch(
        "fa.task.runner._should_run_round", return_value=True
    ) as mock_should_run:
        with patch(
            "fa.task.runner._prepare_round",
            return_value=("prompt", tmp_path / "round.md"),
        ):
            with patch("fa.task.runner.run_tool", return_value=0) as mock_run_tool:
                result = _run_task_batch(
                    task=task,
                    parent=None,
                    tool="codex",
                    rounds=3,
                    logger=logging.getLogger("test"),
                    extra_env=None,
                    attempt_mode=False,
                    glm_plan=False,
                    log_dir=log_dir,
                )

    assert result is False
    assert mock_should_run.call_count == 3
    assert mock_run_tool.call_count == 3


def test_run_task_batch_returns_true_when_round_fails(tmp_path: Path) -> None:
    from fa.task.runner import _run_task_batch

    task = _create_approved_task(tmp_path)

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    with patch("fa.task.runner._should_run_round", return_value=True):
        with patch(
            "fa.task.runner._prepare_round",
            return_value=("prompt", tmp_path / "round.md"),
        ):
            with patch("fa.task.runner.run_tool", return_value=1) as mock_run_tool:
                result = _run_task_batch(
                    task=task,
                    parent=None,
                    tool="codex",
                    rounds=3,
                    logger=logging.getLogger("test"),
                    extra_env=None,
                    attempt_mode=False,
                    glm_plan=False,
                    log_dir=log_dir,
                )

    assert result is True
    assert mock_run_tool.call_count == 1


def test_run_task_batch_stops_early_when_should_not_run_round(tmp_path: Path) -> None:
    from fa.task.runner import _run_task_batch

    task = _create_approved_task(tmp_path)

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    with patch(
        "fa.task.runner._should_run_round", return_value=False
    ) as mock_should_run:
        with patch("fa.task.runner._prepare_round") as mock_prepare:
            with patch("fa.task.runner.run_tool") as mock_run_tool:
                result = _run_task_batch(
                    task=task,
                    parent=None,
                    tool="codex",
                    rounds=3,
                    logger=logging.getLogger("test"),
                    extra_env=None,
                    attempt_mode=False,
                    glm_plan=True,
                    log_dir=log_dir,
                )

    assert result is True
    assert mock_should_run.call_count == 1
    assert mock_prepare.call_count == 0
    assert mock_run_tool.call_count == 0


def test_prepare_round_returns_prompt_and_log_path(tmp_path: Path) -> None:
    from fa.task.runner import _prepare_round, _prompt_run_context

    task = _create_approved_task(tmp_path)

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    ctx = _prompt_run_context(task, attempt_mode=False)

    with patch("fa.task.runner.build_task_prompt", return_value="test prompt"):
        with patch("fa.task.runner._save_prompt"):
            prompt, log_path = _prepare_round(
                task=task,
                parent=None,
                attempt_mode=False,
                ctx=ctx,
                log_dir=log_dir,
                round_index=2,
                rounds=3,
                tool="codex",
                logger=logging.getLogger("test"),
            )

    assert prompt == "test prompt"
    assert log_path == log_dir / "round-2-codex.log"


def test_prepare_round_calls_save_prompt(tmp_path: Path) -> None:
    from fa.task.runner import _prepare_round, _prompt_run_context

    task = _create_approved_task(tmp_path)

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    ctx = _prompt_run_context(task, attempt_mode=False)

    with patch("fa.task.runner.build_task_prompt", return_value="test prompt"):
        with patch("fa.task.runner._save_prompt") as mock_save:
            _prepare_round(
                task=task,
                parent=None,
                attempt_mode=False,
                ctx=ctx,
                log_dir=log_dir,
                round_index=1,
                rounds=5,
                tool="claude",
                logger=logging.getLogger("test"),
            )

    mock_save.assert_called_once_with(log_dir, 1, ctx.attempt, False, "test prompt")


def test_run_tasks_force_resets_non_approved_failed_status(tmp_path: Path) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("test-task")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")
            task.status = "pending"
            task.completed_at = "2026-01-01T00:00:00"
            storage.save_task(task)

            with patch("fa.task.runner.build_task_prompt", return_value="prompt"):
                with patch("fa.task.runner._run_task_interactive", return_value=False):
                    result = runner.run_tasks(
                        logger=logging.getLogger("test"),
                        ids=[task.id],
                        force=True,
                        tool="claude",
                        rounds=1,
                        glm_plan=False,
                        attempt_mode=False,
                        open_viewer=False,
                    )

            assert result == 0


def test_run_tasks_missing_task_returns_failure(tmp_path: Path) -> None:
    with patch.object(storage, "find_project_root", return_value=tmp_path):
        result = runner.run_tasks(
            logger=logging.getLogger("test"),
            ids=[99999],
            force=False,
            tool="claude",
            rounds=1,
            glm_plan=False,
            attempt_mode=False,
        )
    assert result == 1


def test_run_tasks_template_not_found_returns_failure(tmp_path: Path) -> None:
    with patch.object(storage, "find_project_root", return_value=tmp_path):
        task = storage.create_task("no-template")
        (task.path / "spec.md").write_text("spec", encoding="utf-8")
        task.transition_to("approved")
        storage.save_task(task)

        with patch(
            "fa.task.runner.build_task_prompt",
            side_effect=FileNotFoundError("missing template"),
        ):
            result = runner.run_tasks(
                logger=logging.getLogger("test"),
                ids=[task.id],
                force=False,
                tool="claude",
                rounds=1,
                glm_plan=False,
                attempt_mode=False,
            )
    assert result == 1


def test_run_tasks_batch_failure_marks_task_failed(tmp_path: Path) -> None:
    with TemporaryDirectory() as tempdir:
        with patch.object(storage, "find_project_root", return_value=Path(tempdir)):
            task = storage.create_task("batch-fail")
            (task.path / "spec.md").write_text("spec", encoding="utf-8")
            (task.path / "plan.md").write_text("plan", encoding="utf-8")
            task.transition_to("approved")
            storage.save_task(task)

            with (
                patch("fa.task.runner.build_task_prompt", return_value="prompt"),
                patch("fa.task.runner._run_task_batch", return_value=True),
            ):
                result = runner.run_tasks(
                    logger=logging.getLogger("test"),
                    ids=[task.id],
                    force=False,
                    tool="generic-tool",
                    rounds=1,
                    glm_plan=False,
                    attempt_mode=False,
                )

            assert result == 1
            updated = storage.find_task(task.id)
            assert updated is not None
            assert updated.status == "failed"
