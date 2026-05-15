from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fa.policy.model import Policy, PolicyReport, PolicyScopes
from fa.policy.runner import (
    _expand_entry,
    _iter_files,
    _policy_prompt,
    _save_prompt,
    scoped_files,
)


@pytest.fixture
def mock_project_root(tmp_path: Path):
    with patch("fa.policy.runner.project_root", return_value=tmp_path):
        yield tmp_path


def test_iter_files_returns_file_when_base_is_file(mock_project_root: Path):
    test_file = mock_project_root / "test.txt"
    test_file.write_text("content")
    result = _iter_files(test_file)
    assert result == [test_file]


def test_iter_files_returns_files_in_directory_recursively(mock_project_root: Path):
    subdir = mock_project_root / "subdir"
    subdir.mkdir()
    file1 = subdir / "file1.txt"
    file1.write_text("content1")
    file2 = mock_project_root / "file2.txt"
    file2.write_text("content2")
    result = _iter_files(mock_project_root)
    assert set(result) == {file1, file2}


def test_iter_files_returns_empty_list_for_nonexistent_path(mock_project_root: Path):
    nonexistent = mock_project_root / "nonexistent"
    result = _iter_files(nonexistent)
    assert result == []


def test_expand_entry_resolves_regular_path(mock_project_root: Path):
    test_file = mock_project_root / "src" / "main.py"
    test_file.parent.mkdir()
    test_file.write_text("content")
    with patch("fa.policy.runner._iter_files") as mock_iter:
        mock_iter.return_value = [test_file]
        result = _expand_entry("src/main.py")
        mock_iter.assert_called_once()
        assert result == [test_file]


def test_expand_entry_handles_git_prefix_when_not_git_repo(mock_project_root: Path):
    test_file = mock_project_root / "src" / "main.py"
    test_file.parent.mkdir()
    test_file.write_text("content")
    with patch("fa.policy.runner.is_git_repo", return_value=False):
        with patch("fa.policy.runner._iter_files") as mock_iter:
            mock_iter.return_value = [test_file]
            result = _expand_entry("git:src/main.py")
            mock_iter.assert_called_once()
            assert result == [test_file]


def test_expand_entry_handles_git_prefix_when_git_repo(mock_project_root: Path):
    test_file = mock_project_root / "src" / "main.py"
    test_file.parent.mkdir()
    changed = {test_file}
    with patch("fa.policy.runner.is_git_repo", return_value=True):
        with patch("fa.policy.runner.changed_files", return_value=changed):
            result = _expand_entry("git:src/main.py")
            assert result == [test_file]


def test_expand_entry_git_prefix_with_directory(mock_project_root: Path):
    src_dir = mock_project_root / "src"
    src_dir.mkdir()
    file1 = src_dir / "main.py"
    file1.write_text("content1")
    file2 = src_dir / "util.py"
    file2.write_text("content2")
    changed = {file1, file2}
    with patch("fa.policy.runner.is_git_repo", return_value=True):
        with patch("fa.policy.runner.changed_files", return_value=changed):
            result = _expand_entry("git:src")
            assert set(result) == {file1, file2}


def test_scoped_files_returns_relative_paths(mock_project_root: Path):
    test_file = mock_project_root / "src" / "main.py"
    test_file.parent.mkdir()
    test_file.write_text("content")
    policy = Policy(
        id="test",
        name="Test",
        description="",
        objective="",
        specs=[],
        scopes=PolicyScopes(required=["src"], exclude=[]),
        report=PolicyReport(path="", template=""),
    )
    with patch("fa.policy.runner._expand_entry", return_value=[test_file]):
        result = scoped_files(policy)
        assert result == ["src/main.py"]


def test_scoped_files_excludes_matching_patterns(mock_project_root: Path):
    file1 = mock_project_root / "src" / "main.py"
    file1.parent.mkdir()
    file1.write_text("content")
    file2 = mock_project_root / "src" / "main_test.py"
    file2.write_text("content")
    policy = Policy(
        id="test",
        name="Test",
        description="",
        objective="",
        specs=[],
        scopes=PolicyScopes(required=["src"], exclude=["*_test.py"]),
        report=PolicyReport(path="", template=""),
    )
    with patch("fa.policy.runner._expand_entry", return_value=[file1, file2]):
        result = scoped_files(policy)
        assert result == ["src/main.py"]
        assert "src/main_test.py" not in result


def test_scoped_files_combines_multiple_entries(mock_project_root: Path):
    file1 = mock_project_root / "src" / "main.py"
    file1.parent.mkdir()
    file1.write_text("content")
    file2 = mock_project_root / "lib" / "util.py"
    file2.parent.mkdir()
    file2.write_text("content")
    policy = Policy(
        id="test",
        name="Test",
        description="",
        objective="",
        specs=[],
        scopes=PolicyScopes(required=["src", "lib"], exclude=[]),
        report=PolicyReport(path="", template=""),
    )
    with patch("fa.policy.runner._expand_entry", side_effect=[[file1], [file2]]):
        result = scoped_files(policy)
        assert "src/main.py" in result
        assert "lib/util.py" in result


def test_policy_prompt_generates_correct_format():
    policy = Policy(
        id="test",
        name="Test Policy",
        description="A test",
        objective="Verify something",
        specs=["specs/test.md"],
        scopes=PolicyScopes(required=[], exclude=[]),
        report=PolicyReport(path="", template=""),
    )
    result = _policy_prompt(policy, ["src/main.py", "src/util.py"], "reports/test.md")
    assert "# Policy: Test Policy" in result
    assert "## Objective" in result
    assert "Verify something" in result
    assert "## Specs" in result
    assert "- specs/test.md" in result
    assert "## Scope Files" in result
    assert "- src/main.py" in result
    assert "- src/util.py" in result
    assert "reports/test.md" in result


def test_policy_prompt_handles_empty_specs():
    policy = Policy(
        id="test",
        name="Test",
        description="",
        objective="Check stuff",
        specs=[],
        scopes=PolicyScopes(required=[], exclude=[]),
        report=PolicyReport(path="", template=""),
    )
    result = _policy_prompt(policy, [], "reports/out.md")
    assert "## Specs" in result
    assert "- " not in result.split("## Specs")[1].split("\n\n")[0]


def test_save_prompt_writes_file_and_returns_path(tmp_path):
    prompt_content = "# Test prompt\nSome content"
    result = _save_prompt(tmp_path, 1, prompt_content)
    assert result == tmp_path / "round-1-prompt.md"
    assert result.read_text() == prompt_content


def test_save_prompt_creates_subdirectories(tmp_path):
    subdir = tmp_path / "logs" / "round-2"
    subdir.mkdir(parents=True)
    prompt_content = "# Test"
    result = _save_prompt(subdir, 1, prompt_content)
    assert result == subdir / "round-1-prompt.md"
    assert result.read_text() == "# Test"
