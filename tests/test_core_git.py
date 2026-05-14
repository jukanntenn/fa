from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.core import git


def test_returns_true_when_git_dir_exists() -> None:
    with TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / ".git").mkdir()
        assert git.is_git_repo(Path(temp_dir))


def test_returns_false_when_no_git_dir() -> None:
    with TemporaryDirectory() as temp_dir:
        assert not git.is_git_repo(Path(temp_dir))


def test_changed_files_returns_empty_for_non_git_repo() -> None:
    with TemporaryDirectory() as temp_dir:
        with patch.object(subprocess, "run") as mock_run:
            result = git.changed_files(Path(temp_dir))

        assert result == []
        mock_run.assert_not_called()


def test_changed_files_unstaged_tracked_change() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / ".git").mkdir()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=" M file.txt\n")

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = git.changed_files(root)

        assert result == [root / "file.txt"]


def test_changed_files_staged_change() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / ".git").mkdir()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="M  staged.txt\n")

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = git.changed_files(root)

        assert result == [root / "staged.txt"]


def test_changed_files_untracked_file() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / ".git").mkdir()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="?? new.txt\n")

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = git.changed_files(root)

        assert result == [root / "new.txt"]


def test_changed_files_deduplicates_staged_and_modified() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / ".git").mkdir()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0, stdout="MM file.txt\n M other.txt\n"
            )

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = git.changed_files(root)

        paths = [str(p) for p in result]
        assert paths.count(str(root / "file.txt")) == 1
        assert str(root / "other.txt") in paths


def test_changed_files_staged_rename_returns_new_path() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / ".git").mkdir()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0, stdout="R  old_name.txt -> new_name.txt\n"
            )

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = git.changed_files(root)

        assert result == [root / "new_name.txt"]


def test_changed_files_ignores_blank_lines() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / ".git").mkdir()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="\n\n  \n")

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = git.changed_files(root)

        assert result == []


def test_changed_files_returns_sorted_absolute_paths() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / ".git").mkdir()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0, stdout="?? zebra.txt\n M mid.txt\nA  alpha.txt\n"
            )

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = git.changed_files(root)

        for path in result:
            assert path.is_absolute()
        names = [p.name for p in result]
        assert names == sorted(names)


def test_parse_porcelain_unstaged_modified() -> None:
    assert git.parse_porcelain_line(" M file.txt") == "file.txt"


def test_parse_porcelain_staged_modified() -> None:
    assert git.parse_porcelain_line("M  staged.txt") == "staged.txt"


def test_parse_porcelain_untracked() -> None:
    assert git.parse_porcelain_line("?? new.txt") == "new.txt"


def test_parse_porcelain_staged_rename() -> None:
    assert git.parse_porcelain_line("R  old.txt -> new.txt") == "new.txt"


def test_parse_porcelain_copied_file() -> None:
    assert git.parse_porcelain_line("C  orig.txt -> copy.txt") == "copy.txt"


def test_parse_porcelain_deleted() -> None:
    assert git.parse_porcelain_line(" D gone.txt") == "gone.txt"


def test_parse_porcelain_blank_line() -> None:
    assert git.parse_porcelain_line("") is None


def test_parse_porcelain_whitespace_only() -> None:
    assert git.parse_porcelain_line("   ") is None


def test_parse_porcelain_empty_path() -> None:
    assert git.parse_porcelain_line("M  ") is None


def test_parse_porcelain_path_with_spaces() -> None:
    assert git.parse_porcelain_line("?? path with spaces.txt") == "path with spaces.txt"
