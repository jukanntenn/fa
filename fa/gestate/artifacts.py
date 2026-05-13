from __future__ import annotations

import difflib
from pathlib import Path

import typer

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
