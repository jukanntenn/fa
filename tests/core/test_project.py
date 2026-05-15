from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.core import project
from fa.core.project import ensure_fa_structure, find_project_root


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


# ─── find_project_root (extended) ──────────────────────────────
def test_find_project_root_prefers_nearest_fa_directory() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        nested = root / "workspace" / "feature"
        (root / ".fa").mkdir()
        nested.mkdir(parents=True)

        assert find_project_root(nested) == root


def test_find_project_root_returns_git_root_when_fa_missing() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        nested = root / "workspace" / "feature"
        (root / ".git").mkdir()
        nested.mkdir(parents=True)

        assert find_project_root(nested) == root


def test_find_project_root_returns_start_when_no_markers_exist() -> None:
    with TemporaryDirectory() as temp_dir:
        start = Path(temp_dir) / "workspace" / "feature"
        start.mkdir(parents=True)

        original_is_dir = Path.is_dir

        def marker_free_is_dir(path: Path) -> bool:
            if path.name in {".fa", ".git"}:
                return False
            return original_is_dir(path)

        with patch.object(Path, "is_dir", marker_free_is_dir):
            assert find_project_root(start) == start.resolve()


# ─── ensure_fa_structure (extended) ──────────────────────────────
def test_ensure_fa_structure_creates_expected_directories() -> None:
    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)

        fa_dir = ensure_fa_structure(project_root)

        assert fa_dir == project_root / ".fa"
        assert (fa_dir / "tasks" / "archive").is_dir()
        assert (fa_dir / "logs" / "agents").is_dir()
        assert (fa_dir / "policies").is_dir()
        assert (fa_dir / "templates").is_dir()
