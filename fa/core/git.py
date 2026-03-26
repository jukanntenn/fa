from __future__ import annotations

import subprocess
from pathlib import Path


def is_git_repo(project_root: Path) -> bool:
    return (project_root / ".git").exists()


def changed_files(project_root: Path) -> list[Path]:
    if not is_git_repo(project_root):
        return []
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    files: set[Path] = set()
    for cmd in commands:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            value = line.strip()
            if value:
                files.add(project_root / value)
    return sorted(files)
