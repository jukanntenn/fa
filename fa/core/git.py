from __future__ import annotations

import subprocess
from pathlib import Path


def is_git_repo(project_root: Path) -> bool:
    return (project_root / ".git").exists()


def parse_porcelain_line(line: str) -> str | None:
    raw = line[3:]
    if " -> " in raw:
        raw = raw.split(" -> ", 1)[1]
    value = raw.strip()
    return value or None


def changed_files(project_root: Path) -> list[Path]:
    if not is_git_repo(project_root):
        return []
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    files: set[Path] = set()
    for line in result.stdout.splitlines():
        path = parse_porcelain_line(line)
        if path:
            files.add(project_root / path)
    return sorted(files)
