from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fa.task import prompt
from fa.task.model import Task


class TaskPromptTests(unittest.TestCase):
    def test_infer_memory_sequence_returns_one_without_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            task = Task.new(1, "demo", None, Path(temp_dir))

            self.assertEqual(prompt.infer_memory_sequence(task), 1)

    def test_infer_memory_sequence_counts_existing_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir)
            task_path.joinpath("memory-1.md").write_text("a", encoding="utf-8")
            task_path.joinpath("memory-2.md").write_text("b", encoding="utf-8")
            task = Task.new(1, "demo", None, task_path)

            self.assertEqual(prompt.infer_memory_sequence(task), 3)

    def test_infer_attempt_returns_one_without_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            task = Task.new(1, "demo", None, Path(temp_dir))

            self.assertEqual(prompt.infer_attempt(task), 1)

    def test_infer_attempt_counts_existing_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir)
            task_path.joinpath("feedback-1.md").write_text("a", encoding="utf-8")
            task_path.joinpath("feedback-2.md").write_text("b", encoding="utf-8")
            task = Task.new(1, "demo", None, task_path)

            self.assertEqual(prompt.infer_attempt(task), 3)

    def test_task_template_prefers_override_template(self) -> None:
        with TemporaryDirectory() as temp_dir:
            override_dir = Path(temp_dir) / ".fa" / "templates"
            override_dir.mkdir(parents=True)
            template_name = "task_prompt.j2"
            override_dir.joinpath(template_name).write_text(
                "override", encoding="utf-8"
            )
            with patch.object(prompt, "fa_dir", return_value=Path(temp_dir) / ".fa"):
                env, selected = prompt.task_template()

                self.assertEqual(selected, template_name)
                self.assertEqual(env.get_template(template_name).render(), "override")


if __name__ == "__main__":
    unittest.main()
