from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import typer
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from fa.core.config import (
    AGENT_LOGS_DIR_NAME,
    LOGS_DIR_NAME,
    TOOL_COMMANDS,
)
from fa.task.model import Task
from fa.task.storage import (
    all_tasks,
    fa_dir,
    find_children,
    find_task,
    relative_path,
    save_task,
)


def _compute_content_hash(task_path: Path) -> str:
    sha = hashlib.sha256()
    for pattern in ("spec.md", "plan.md"):
        for file_path in sorted(task_path.rglob(pattern)):
            sha.update(file_path.read_bytes())
    return sha.hexdigest()


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
                buf.newline(copy_margin=not buf.is_pasting)

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


def _find_new_parent_task(preexisting_ids: frozenset[int]) -> Task | None:
    tasks = all_tasks()
    new_tasks = [t for tid, t in tasks.items() if tid not in preexisting_ids]
    if not new_tasks:
        return None
    no_parent = [t for t in new_tasks if t.parent_id is None]
    if no_parent:
        return min(no_parent, key=lambda t: t.id)
    return min(new_tasks, key=lambda t: t.id)


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
) -> None:
    from fa.cli import app_state

    logger: logging.Logger = app_state.logger

    if arg is not None:
        input_text = arg.strip()
    else:
        input_text = _read_stdin()

    if not input_text:
        typer.echo("Error: empty input", err=True)
        raise typer.Exit(code=1)

    task: Task | None = None

    if _is_task_id(input_text):
        task = find_task(int(input_text.strip()))
        if task is None:
            typer.echo(f"Error: task {input_text} not found", err=True)
            raise typer.Exit(code=1)
    else:
        preexisting_ids = frozenset(all_tasks().keys())
        prompt = f"/gestating {input_text}"
        cmd = _build_tool_cmd(tool, prompt)
        gestate_log_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / "gestate"
        gestate_log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = gestate_log_dir / f"gestate-create-{timestamp}.log"
        logger.info("Creating task from intent brief using tool=%s", tool)
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                result = subprocess.run(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
        except OSError:
            typer.echo(f"Error: tool '{tool}' execution failed", err=True)
            raise typer.Exit(code=1)
        if result.returncode != 0:
            typer.echo(
                f"Error: tool '{tool}' exited with code {result.returncode}", err=True
            )
            raise typer.Exit(code=1)
        task = _find_new_parent_task(preexisting_ids)
        if task is None:
            typer.echo("Error: no new task created by gestating tool", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Created task {task.id}: {relative_path(task.path)}")

    issues = _validate_task(task)
    critical = False
    for issue in issues:
        typer.echo(f"Warning: {issue}", err=True)
        if "status" in issue or "missing" in issue:
            critical = True
    if critical:
        raise typer.Exit(code=1)

    log_dir = fa_dir() / LOGS_DIR_NAME / AGENT_LOGS_DIR_NAME / f"gestate-{task.id}"
    log_dir.mkdir(parents=True, exist_ok=True)

    for round_num in range(1, max_rounds + 1):
        old_hash = _compute_content_hash(task.path)
        prompt = _build_review_prompt(task, round_num, max_rounds)
        prompt_path = log_dir / f"round-{round_num}-prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        cmd = _build_tool_cmd(tool, prompt)
        log_path = log_dir / f"round-{round_num}-{tool}.log"
        logger.info(
            "Task [%d] gestate round %d/%d started | tool=%s",
            task.id,
            round_num,
            max_rounds,
            tool,
        )
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                result = subprocess.run(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
        except OSError:
            logger.warning("Tool '%s' execution failed in round %d", tool, round_num)
            continue
        if result.returncode != 0:
            logger.warning(
                "Tool '%s' exited with code %d in round %d",
                tool,
                result.returncode,
                round_num,
            )
        new_hash = _compute_content_hash(task.path)
        if old_hash == new_hash:
            typer.echo(f"Converged after {round_num} round(s)")
            break
    else:
        typer.echo(f"Max rounds ({max_rounds}) reached")

    task.status = "approved"
    save_task(task)

    children = find_children(task.id)
    approved_count = 0
    for child in children:
        if child.status == "draft":
            child.transition_to("approved")
            save_task(child)
            approved_count += 1
        elif child.status not in {"approved", "completed"}:
            typer.echo(
                f"Warning: subtask {child.id} is '{child.status}', skipped approval",
                err=True,
            )
    if children:
        typer.echo(f"{approved_count}/{len(children)} subtask(s) approved")

    typer.echo(f"Task {task.id} approved")
