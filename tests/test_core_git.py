from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.core import git


class IsGitRepoTests(unittest.TestCase):
    def test_returns_true_when_git_dir_exists(self) -> None:
        with TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / ".git").mkdir()
            self.assertTrue(git.is_git_repo(Path(temp_dir)))

    def test_returns_false_when_no_git_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            self.assertFalse(git.is_git_repo(Path(temp_dir)))


class ChangedFilesTests(unittest.TestCase):
    def test_returns_empty_for_non_git_repo(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(subprocess, "run") as mock_run:
                result = git.changed_files(Path(temp_dir))

            self.assertEqual(result, [])
            mock_run.assert_not_called()

    def test_unstaged_tracked_change(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 0, stdout=" M file.txt\n")

            with patch.object(subprocess, "run", side_effect=fake_run):
                result = git.changed_files(root)

            self.assertEqual(result, [root / "file.txt"])

    def test_staged_change(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 0, stdout="M  staged.txt\n")

            with patch.object(subprocess, "run", side_effect=fake_run):
                result = git.changed_files(root)

            self.assertEqual(result, [root / "staged.txt"])

    def test_untracked_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 0, stdout="?? new.txt\n")

            with patch.object(subprocess, "run", side_effect=fake_run):
                result = git.changed_files(root)

            self.assertEqual(result, [root / "new.txt"])

    def test_deduplicates_staged_and_modified(self) -> None:
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
            self.assertEqual(paths.count(str(root / "file.txt")), 1)
            self.assertIn(str(root / "other.txt"), paths)

    def test_staged_rename_returns_new_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="R  old_name.txt -> new_name.txt\n"
                )

            with patch.object(subprocess, "run", side_effect=fake_run):
                result = git.changed_files(root)

            self.assertEqual(result, [root / "new_name.txt"])

    def test_ignores_blank_lines(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 0, stdout="\n\n  \n")

            with patch.object(subprocess, "run", side_effect=fake_run):
                result = git.changed_files(root)

            self.assertEqual(result, [])

    def test_returns_sorted_absolute_paths(self) -> None:
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
                self.assertTrue(path.is_absolute())
            names = [p.name for p in result]
            self.assertEqual(names, sorted(names))


class ParsePorcelainLineTests(unittest.TestCase):
    def test_unstaged_modified(self) -> None:
        self.assertEqual(git.parse_porcelain_line(" M file.txt"), "file.txt")

    def test_staged_modified(self) -> None:
        self.assertEqual(git.parse_porcelain_line("M  staged.txt"), "staged.txt")

    def test_untracked(self) -> None:
        self.assertEqual(git.parse_porcelain_line("?? new.txt"), "new.txt")

    def test_staged_rename(self) -> None:
        self.assertEqual(git.parse_porcelain_line("R  old.txt -> new.txt"), "new.txt")

    def test_copied_file(self) -> None:
        self.assertEqual(
            git.parse_porcelain_line("C  orig.txt -> copy.txt"), "copy.txt"
        )

    def test_deleted(self) -> None:
        self.assertEqual(git.parse_porcelain_line(" D gone.txt"), "gone.txt")

    def test_blank_line(self) -> None:
        self.assertIsNone(git.parse_porcelain_line(""))

    def test_whitespace_only(self) -> None:
        self.assertIsNone(git.parse_porcelain_line("   "))

    def test_empty_path(self) -> None:
        self.assertIsNone(git.parse_porcelain_line("M  "))

    def test_path_with_spaces(self) -> None:
        self.assertEqual(
            git.parse_porcelain_line("?? path with spaces.txt"), "path with spaces.txt"
        )


if __name__ == "__main__":
    unittest.main()
