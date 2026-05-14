from __future__ import annotations

import os
from pathlib import Path

from fa.core import project


def test_returns_ancestor_containing_fa_dir(tmp_path: Path) -> None:
    root = tmp_path
    (root / ".fa").mkdir()
    child = root / "sub" / "deep"
    child.mkdir(parents=True)

    assert project.find_project_root(child) == root


def test_returns_ancestor_containing_git_dir(tmp_path: Path) -> None:
    root = tmp_path
    (root / ".git").mkdir()
    child = root / "src"
    child.mkdir()

    assert project.find_project_root(child) == root


def test_fa_takes_precedence_over_git_when_closer(tmp_path: Path) -> None:
    root = tmp_path
    (root / ".git").mkdir()
    inner = root / "inner"
    inner.mkdir()
    (inner / ".fa").mkdir()
    child = inner / "work"
    child.mkdir()

    assert project.find_project_root(child) == inner


def test_returns_closest_ancestor_with_marker(tmp_path: Path) -> None:
    root = tmp_path
    (root / ".fa").mkdir()
    mid = root / "mid"
    mid.mkdir()
    (mid / ".fa").mkdir()
    leaf = mid / "leaf"
    leaf.mkdir()

    assert project.find_project_root(leaf) == mid


def test_defaults_to_cwd_when_start_is_none(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    (root / ".fa").mkdir()
    original = os.getcwd()
    try:
        os.chdir(root)
        assert project.find_project_root() == root
    finally:
        os.chdir(original)


def test_creates_expected_subdirectories(tmp_path: Path) -> None:
    root = tmp_path
    fa_dir = project.ensure_fa_structure(root)

    assert (fa_dir / "tasks" / "archive").is_dir()
    assert (fa_dir / "logs" / "agents").is_dir()
    assert (fa_dir / "policies").is_dir()
    assert (fa_dir / "templates").is_dir()


def test_returns_fa_dir_path(tmp_path: Path) -> None:
    root = tmp_path
    fa_dir = project.ensure_fa_structure(root)

    assert fa_dir == root / ".fa"


def test_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path
    project.ensure_fa_structure(root)
    fa_dir = project.ensure_fa_structure(root)

    assert fa_dir.is_dir()
