from pathlib import Path
from unittest.mock import patch

from fa.task.model import Task
from fa.task.prompt import _next_sequence_number, _numbered_paths


def _make_task(path: Path) -> Task:
    return Task(
        id=1,
        slug="test",
        parent_id=None,
        status="draft",
        depends_on=[],
        related_to=[],
        created_at="2026-01-01T00:00:00",
        completed_at=None,
        path=path,
    )


class TestNextSequenceNumber:
    def test_empty_dir(self, tmp_path):
        task = _make_task(tmp_path)
        assert _next_sequence_number(task, "memory") == 1

    def test_one_file(self, tmp_path):
        (tmp_path / "memory-1.md").touch()
        task = _make_task(tmp_path)
        assert _next_sequence_number(task, "memory") == 2

    def test_multiple_files(self, tmp_path):
        (tmp_path / "memory-1.md").touch()
        (tmp_path / "memory-2.md").touch()
        task = _make_task(tmp_path)
        assert _next_sequence_number(task, "memory") == 3

    def test_ignores_wrong_prefix(self, tmp_path):
        (tmp_path / "feedback-1.md").touch()
        task = _make_task(tmp_path)
        assert _next_sequence_number(task, "memory") == 1

    def test_out_of_order(self, tmp_path):
        (tmp_path / "memory-3.md").touch()
        (tmp_path / "memory-1.md").touch()
        task = _make_task(tmp_path)
        assert _next_sequence_number(task, "memory") == 3


class TestNumberedPaths:
    @patch("fa.task.storage.project_root")
    def test_from_one(self, mock_root, tmp_path):
        mock_root.return_value = tmp_path
        result = _numbered_paths(tmp_path, "memory", 3)
        assert len(result) == 2
        assert result[0] == str(Path("memory-1.md"))
        assert result[1] == str(Path("memory-2.md"))

    @patch("fa.task.storage.project_root")
    def test_up_to_one(self, mock_root, tmp_path):
        mock_root.return_value = tmp_path
        result = _numbered_paths(tmp_path, "memory", 1)
        assert result == []

    @patch("fa.task.storage.project_root")
    def test_returns_relative_paths(self, mock_root, tmp_path):
        mock_root.return_value = tmp_path
        result = _numbered_paths(tmp_path, "memory", 3)
        for p in result:
            assert not Path(p).is_absolute()
