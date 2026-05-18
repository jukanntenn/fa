from pathlib import Path

from fa.task.commands import _dedupe_archive_roots
from fa.task.model import Task


def _make_task(task_id: int, path: str) -> Task:
    return Task(
        id=task_id,
        slug=f"t-{task_id}",
        parent_id=None,
        status="completed",
        depends_on=[],
        related_to=[],
        created_at="2025-01-01T00:00:00",
        completed_at=None,
        path=Path(path),
    )


class TestDedupeArchiveRoots:
    def test_empty_list(self):
        assert _dedupe_archive_roots([]) == []

    def test_single_task(self):
        task = _make_task(1, "/archive/alpha")
        assert _dedupe_archive_roots([task]) == [task]

    def test_sibling_tasks(self):
        a = _make_task(1, "/archive/alpha")
        b = _make_task(2, "/archive/bravo")
        assert _dedupe_archive_roots([a, b]) == [a, b]

    def test_parent_and_child(self):
        parent = _make_task(1, "/archive/alpha")
        child = _make_task(2, "/archive/alpha/sub")
        result = _dedupe_archive_roots([parent, child])
        assert result == [parent]

    def test_unrelated_branches(self):
        a = _make_task(1, "/archive/alpha")
        b = _make_task(2, "/other/bravo")
        assert _dedupe_archive_roots([a, b]) == [a, b]

    def test_id_ordering(self):
        b = _make_task(2, "/archive/bravo")
        a = _make_task(1, "/archive/alpha")
        assert _dedupe_archive_roots([b, a]) == [a, b]
