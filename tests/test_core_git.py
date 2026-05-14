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

    def test_deduplicates_across_commands(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()

            def fake_run(cmd, **kwargs):
                stdout = ""
                if "--cached" in cmd:
                    stdout = "README.md"
                elif "--others" in cmd:
                    stdout = "README.md\nnew.txt"
                else:
                    stdout = "README.md"
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout)

            with patch.object(subprocess, "run", side_effect=fake_run):
                result = git.changed_files(root)

            paths = [str(p) for p in result]
            self.assertEqual(len(paths), len(set(paths)))
            self.assertIn(str(root / "README.md"), paths)
            self.assertIn(str(root / "new.txt"), paths)

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
                if "--cached" in cmd:
                    stdout = "zebra.txt"
                elif "--others" in cmd:
                    stdout = "alpha.txt"
                else:
                    stdout = "mid.txt"
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout)

            with patch.object(subprocess, "run", side_effect=fake_run):
                result = git.changed_files(root)

            for path in result:
                self.assertTrue(path.is_absolute())
            names = [p.name for p in result]
            self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()
