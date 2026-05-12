from __future__ import annotations

import contextlib
import difflib
import logging
import select
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import cast

import typer
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from fa.core.config import (
    AGENT_LOGS_DIR_NAME,
    LOGS_DIR_NAME,
    TOOL_COMMANDS,
)
from fa.core.logview import _STREAM_JSON_TOOLS, TaskViewer, ViewerController
from fa.task.model import Task
from fa.task.runner import build_execution_plan, run_tasks
from fa.task.storage import (
    all_tasks,
    fa_dir,
    find_children,
    find_task,
    relative_path,
    save_task,
)

ArtifactSnapshot = dict[str, str]


def _artifact_files(task_path: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ("spec.md", "plan.md"):
        files.extend(
            file_path for file_path in task_path.rglob(pattern) if file_path.is_file()
        )
    return sorted(files, key=lambda path: path.relative_to(task_path).as_posix())


def _capture_artifact_snapshot(task_path: Path) -> ArtifactSnapshot:
    snapshot: ArtifactSnapshot = {}
    for file_path in _artifact_files(task_path):
        relative = file_path.relative_to(task_path).as_posix()
        snapshot[relative] = file_path.read_text(encoding="utf-8")
    return snapshot


def _format_artifact_diff(before: ArtifactSnapshot, after: ArtifactSnapshot) -> str:
    chunks: list[str] = []
    for relative in sorted(set(before) | set(after)):
        old_text = before.get(relative)
        new_text = after.get(relative)
        if old_text == new_text:
            continue
        old_lines = [] if old_text is None else old_text.splitlines(keepends=True)
        new_lines = [] if new_text is None else new_text.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"before/{relative}",
                tofile=f"after/{relative}",
                lineterm="\n",
            )
        )
        diff_lines = [
            line if line.endswith("\n") else f"{line}\n" for line in diff_lines
        ]
        if diff_lines:
            chunks.extend(diff_lines)
        else:
            chunks.extend([f"--- before/{relative}\n", f"+++ after/{relative}\n"])
    return "".join(chunks)


def _print_round_artifact_diff(
    round_num: int,
    before: ArtifactSnapshot,
    after: ArtifactSnapshot,
) -> None:
    diff = _format_artifact_diff(before, after)
    if diff:
        typer.echo(f"\nRound {round_num} artifact diff:\n{diff}")
    else:
        typer.echo(f"Round {round_num}: no artifact changes")


def _is_task_id(value: str) -> bool:
    try:
        task_id = int(value.strip())
    except ValueError:
        return False
    return find_task(task_id) is not None


def _read_stdin() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.key_binding import KeyBindings

        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            buf = event.app.current_buffer
            if buf.text.strip() and buf.document.current_line.strip() == "":
                buf.validate_and_handle()
            else:
                buf.newline(copy_margin=False)

        typer.echo("  (Press Enter on blank line to submit)")
        text = pt_prompt(
            "Enter intent brief or task ID:\n> ",
            multiline=True,
            key_bindings=kb,
        )
        return text.strip()
    except ImportError:
        typer.echo(
            "Warning: prompt_toolkit not installed, single-line input only.",
            err=True,
        )
        typer.echo("Enter intent brief or task ID: ", nl=False)
        line = sys.stdin.readline()
        return line.strip() if line else ""
    except EOFError:
        return ""


def _build_tool_cmd(tool: str, prompt: str) -> list[str]:
    if tool not in TOOL_COMMANDS:
        raise ValueError(
            f"unknown tool '{tool}'. Available: {', '.join(TOOL_COMMANDS.keys())}"
        )
    template = TOOL_COMMANDS[tool]
    return [part.format(prompt=prompt) for part in template]


def _tool_accepts_prompt_stdin(tool: str) -> bool:
    return tool in {"claude", "ccr"}


def _build_tool_cmd_for_prompt(tool: str, prompt: str) -> tuple[list[str], str | None]:
    if not _tool_accepts_prompt_stdin(tool):
        return _build_tool_cmd(tool, prompt), None
    cmd = _build_tool_cmd(tool, "")
    return [part for part in cmd if part != ""], prompt


@contextlib.contextmanager
def _main_session_cbreak():
    if not sys.stdin.isatty():
        yield
        return
    original_tty = None
    try:
        import termios as termios_module
        import tty as tty_module

        original_tty = termios_module.tcgetattr(sys.stdin.fileno())
        tty_module.setcbreak(sys.stdin.fileno())
    except Exception:
        yield
        return
    try:
        yield
    finally:
        if original_tty is not None:
            termios_module.tcsetattr(
                sys.stdin.fileno(), termios_module.TCSADRAIN, original_tty
            )


def _read_main_session_key() -> str | None:
    if not sys.stdin.isatty():
        return None
    try:
        readable, _, _ = select.select([sys.stdin], [], [], 0.2)
        if not readable:
            return None
        return sys.stdin.read(1)
    except OSError:
        return None


def _run_tool_with_optional_viewer(
    *,
    tool: str,
    prompt: str,
    log_path: Path,
    logger: logging.Logger,
    viewer: TaskViewer | None,
    round_index: int,
    viewer_controller: ViewerController | None = None,
) -> int | None:
    cmd, prompt_stdin = _build_tool_cmd_for_prompt(tool, prompt)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if viewer is None or tool not in _STREAM_JSON_TOOLS:
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                result = subprocess.run(
                    cmd,
                    input=prompt_stdin,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
        except OSError:
            return None
        return int(result.returncode)

    return_code: int | None = None

    def _worker() -> None:
        nonlocal return_code
        started_at = time.monotonic()
        viewer.start_round(round_index, log_path)
        try:
            try:
                with log_path.open("w", encoding="utf-8") as log_file:
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE
                        if prompt_stdin is not None
                        else subprocess.DEVNULL,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    proc.communicate(input=prompt_stdin)
                    return_code = int(proc.returncode)
            except OSError:
                return_code = None
        finally:
            viewer.end_round(time.monotonic() - started_at)

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    if not sys.stdin.isatty():
        worker.join()
    else:
        assert viewer_controller is not None
        logger.info("Agent running. Press Ctrl+L to open the log viewer.")
        while worker.is_alive():
            if viewer_controller.is_open():
                time.sleep(0.2)
                continue
            with _main_session_cbreak():
                key = _read_main_session_key()
            if key == "\x0c":
                viewer_controller.open()
    worker.join()
    viewer._drain_current_log()
    return return_code


def _find_new_parent_task(preexisting_ids: frozenset[int]) -> Task | None:
    tasks = all_tasks()
    new_tasks = [t for tid, t in tasks.items() if tid not in preexisting_ids]
    if not new_tasks:
        return None
    no_parent = [t for t in new_tasks if t.parent_id is None]
    if no_parent:
        return min(no_parent, key=lambda t: t.id)
    return min(new_tasks, key=lambda t: t.id)


def _resolve_task_descendants(task: Task) -> list[Task]:
    descendants: list[Task] = []

    def visit(parent_id: int) -> None:
        for child in sorted(find_children(parent_id), key=lambda item: item.id):
            descendants.append(child)
            visit(child.id)

    visit(task.id)
    return descendants


def _approve_task_descendants(task: Task) -> tuple[int, int, bool]:
    descendants = _resolve_task_descendants(task)
    approved_count = 0
    approval_failed = False
    for child in descendants:
        if child.status == "draft":
            child.transition_to("approved")
            save_task(child)
            approved_count += 1
        elif child.status not in {"approved", "failed", "completed"}:
            typer.echo(
                f"Warning: subtask {child.id} is '{child.status}', skipped approval",
                err=True,
            )
            approval_failed = True
    return approved_count, len(descendants), approval_failed


def _resolve_to_leaves(task_ids: list[int]) -> list[int]:
    tasks = all_tasks()
    leaves: list[int] = []
    seen: set[int] = set()

    def visit(task_id: int) -> None:
        children = sorted(find_children(task_id), key=lambda item: item.id)
        if not children:
            if task_id not in seen:
                leaves.append(task_id)
                seen.add(task_id)
            return
        for child in children:
            visit(child.id)

    for task_id in task_ids:
        if task_id in tasks:
            visit(task_id)
    return leaves


def _resolve_execution_candidates(task: Task) -> list[int]:
    tasks = all_tasks()
    leaf_ids = _resolve_to_leaves([task.id])
    return sorted(
        task_id
        for task_id in leaf_ids
        if task_id in tasks and tasks[task_id].status in {"approved", "failed"}
    )


def _run_runnable_task_tree(
    task: Task,
    logger: logging.Logger,
    tool: str,
    rounds: int,
    glm_plan: bool,
    *,
    open_viewer: bool = False,
) -> int:
    tasks = all_tasks()
    candidates = _resolve_execution_candidates(task)
    if not candidates:
        logger.info("No runnable tasks to run after gestate.")
        typer.echo("No runnable tasks to run after gestate.")
        return 0
    plan = build_execution_plan(tasks, candidates)
    typer.echo(f"Running task(s) after gestate: {','.join(str(i) for i in plan)}")
    return run_tasks(
        logger=logger,
        ids=plan,
        force=False,
        tool=tool,
        rounds=rounds,
        glm_plan=glm_plan,
        attempt_mode=False,
        open_viewer=open_viewer,
    )


def _validate_task(task: Task) -> list[str]:
    issues: list[str] = []
    if task.status != "draft":
        issues.append(f"task {task.id} status is '{task.status}', expected 'draft'")
    all_t = all_tasks()
    has_children = any(t.parent_id == task.id for t in all_t.values())

    if has_children:
        if not (task.path / "spec.md").exists():
            issues.append(f"task {task.id} missing spec.md")
        for child in all_t.values():
            if child.parent_id == task.id and not (child.path / "plan.md").exists():
                issues.append(f"subtask {child.id} missing plan.md")
    elif task.parent_id is not None:
        if task.parent_id in all_t:
            if not (task.path / "plan.md").exists():
                issues.append(f"task {task.id} missing plan.md")
        else:
            if not (task.path / "spec.md").exists():
                issues.append(f"task {task.id} missing spec.md")
            if not (task.path / "plan.md").exists():
                issues.append(f"task {task.id} missing plan.md")
    else:
        if not (task.path / "spec.md").exists():
            issues.append(f"task {task.id} missing spec.md")
        if not (task.path / "plan.md").exists():
            issues.append(f"task {task.id} missing plan.md")
    return issues


def _build_review_prompt(task: Task, round_num: int, max_rounds: int) -> str:
    from fa.core.config import package_template_dir

    env = Environment(
        loader=FileSystemLoader(str(package_template_dir())),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("gestate_review.j2")
    spec_files = sorted(task.path.rglob("spec.md"))
    plan_files = sorted(task.path.rglob("plan.md"))
    return template.render(
        task=task.to_dict(),
        task_dir=relative_path(task.path),
        spec_files=[relative_path(p) for p in spec_files],
        plan_files=[relative_path(p) for p in plan_files],
        round=round_num,
        max_rounds=max_rounds,
    )


def gestate(
    arg: str | None = typer.Argument(None, help="Intent brief or task ID"),
    tool: str = typer.Option("claude", "--tool", help="AI tool to use"),
    max_rounds: int = typer.Option(10, "--max-rounds", help="Max convergence rounds"),
    run: bool = typer.Option(
        True, "--run/--no-run", help="Run runnable task(s) after gestation"
    ),
    run_tool: str = typer.Option(
        "claude", "--run-tool", help="AI tool to use for task execution"
    ),
    run_rounds: int = typer.Option(
        3, "--run-rounds", help="Execution rounds for each task"
    ),
    glm_plan: bool = typer.Option(
        False, "--glm-plan", help="Check GLM plan quota before execution rounds"
    ),
) -> None:
    from fa.cli import app_state

    logger = cast(logging.Logger, app_state.logger)

    if arg is not None:
        input_text = arg.strip()
    else:
        input_text = _read_stdin()

    if not input_text:
        typer.echo("Error: empty input", err=True)
        raise typer.Exit(code=1)

    create_phase_rounds = 0 if _is_task_id(input_text) else 1
    viewer = (
        TaskViewer(slug="gestate", total_rounds=max_rounds + create_phase_rounds)
        if tool in _STREAM_JSON_TOOLS
        else None
    )
    viewer_controller = ViewerController(viewer) if viewer is not None else None
    had_tool_failure = False
    task: Task | None = None

    if create_phase_rounds == 0:
        task = find_task(int(input_text.strip()))
        if task is None:
            typer.echo(f"Error: task {input_text} not found", err=True)
            raise typer.Exit(code=1)
    else:
        preexisting_ids = frozenset(all_tasks().keys())
        prompt = f"/gestating {input_text}"
        gestate_log_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / "gestate"
        gestate_log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = gestate_log_dir / f"gestate-create-{timestamp}.log"
        logger.info("Creating task from intent brief using tool=%s", tool)
        result_code = _run_tool_with_optional_viewer(
            tool=tool,
            prompt=prompt,
            log_path=log_path,
            logger=logger,
            viewer=viewer,
            round_index=1,
            viewer_controller=viewer_controller,
        )
        if result_code is None:
            typer.echo(f"Error: tool '{tool}' execution failed", err=True)
            if viewer is not None:
                viewer.mark_failed()
            raise typer.Exit(code=1)
        if result_code != 0:
            typer.echo(f"Error: tool '{tool}' exited with code {result_code}", err=True)
            if viewer is not None:
                viewer.mark_failed()
            raise typer.Exit(code=1)
        task = _find_new_parent_task(preexisting_ids)
        if task is None:
            typer.echo("Error: no new task created by gestating tool", err=True)
            if viewer is not None:
                viewer.mark_failed()
            raise typer.Exit(code=1)
        typer.echo(f"Created task {task.id}: {relative_path(task.path)}")

    assert task is not None
    issues = _validate_task(task)
    critical = False
    for issue in issues:
        typer.echo(f"Warning: {issue}", err=True)
        if "status" in issue or "missing" in issue:
            critical = True
    if critical:
        if viewer is not None:
            viewer.mark_failed()
        raise typer.Exit(code=1)

    log_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / f"gestate-{task.id}"
    log_dir.mkdir(parents=True, exist_ok=True)
    review_round_offset = create_phase_rounds

    for round_num in range(1, max_rounds + 1):
        before_snapshot = _capture_artifact_snapshot(task.path)
        prompt = _build_review_prompt(task, round_num, max_rounds)
        prompt_path = log_dir / f"round-{round_num}-prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        log_path = log_dir / f"round-{round_num}-{tool}.log"
        logger.info(
            "Task [%d] gestate round %d/%d started | tool=%s",
            task.id,
            round_num,
            max_rounds,
            tool,
        )
        result_code = _run_tool_with_optional_viewer(
            tool=tool,
            prompt=prompt,
            log_path=log_path,
            logger=logger,
            viewer=viewer,
            round_index=review_round_offset + round_num,
            viewer_controller=viewer_controller,
        )
        if result_code is None:
            had_tool_failure = True
            logger.warning("Tool '%s' execution failed in round %d", tool, round_num)
            after_snapshot = _capture_artifact_snapshot(task.path)
            _print_round_artifact_diff(round_num, before_snapshot, after_snapshot)
            if before_snapshot == after_snapshot:
                typer.echo(f"Converged after {round_num} round(s)")
                break
            continue
        if result_code != 0:
            had_tool_failure = True
            logger.warning(
                "Tool '%s' exited with code %d in round %d",
                tool,
                result_code,
                round_num,
            )
        after_snapshot = _capture_artifact_snapshot(task.path)
        _print_round_artifact_diff(round_num, before_snapshot, after_snapshot)
        if before_snapshot == after_snapshot:
            typer.echo(f"Converged after {round_num} round(s)")
            break
    else:
        typer.echo(f"Max rounds ({max_rounds}) reached")

    will_try_auto_run = run and not had_tool_failure
    if viewer is not None:
        if had_tool_failure:
            viewer.mark_failed()
        elif not will_try_auto_run:
            viewer.mark_done()

    task.status = "approved"
    save_task(task)

    approved_count, descendant_count, approval_failed = _approve_task_descendants(task)
    if descendant_count:
        typer.echo(f"{approved_count}/{descendant_count} subtask(s) approved")

    if approval_failed:
        if viewer is not None:
            viewer.mark_failed()
        raise typer.Exit(code=1)

    typer.echo(f"Task {task.id} approved")

    if run:
        if had_tool_failure:
            typer.echo(
                "Warning: gestate review had tool failures; skipping automatic task execution",
                err=True,
            )
        else:
            handoff_open_viewer = bool(
                viewer_controller is not None and viewer_controller.is_open()
            )
            should_close_viewer = handoff_open_viewer
            handoff_open_viewer = handoff_open_viewer and run_tool in _STREAM_JSON_TOOLS
            if should_close_viewer:
                viewer_controller.close()
                viewer_controller.wait_closed()
            exit_code = _run_runnable_task_tree(
                task,
                logger,
                run_tool,
                run_rounds,
                glm_plan,
                open_viewer=handoff_open_viewer,
            )
            if exit_code != 0:
                raise typer.Exit(code=exit_code)
