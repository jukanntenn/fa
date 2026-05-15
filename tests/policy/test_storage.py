from __future__ import annotations

import json

import pytest

from fa.policy import storage
from fa.policy.model import Policy


def test_policies_dir_returns_policies_subdirectory(storage_root):
    result = storage.policies_dir()
    assert result.name == "policies"
    assert result.parent == storage.fa_dir()


def test_list_policy_files_returns_sorted_list(storage_root):
    (storage.policies_dir() / "bbb-policy.yml").write_text(
        "name: BBB\n", encoding="utf-8"
    )
    (storage.policies_dir() / "aaa-policy.yml").write_text(
        "name: AAA\n", encoding="utf-8"
    )
    (storage.policies_dir() / "ccc-policy.yml").write_text(
        "name: CCC\n", encoding="utf-8"
    )
    result = storage.list_policy_files()
    assert len(result) == 3
    assert [p.stem for p in result] == ["aaa-policy", "bbb-policy", "ccc-policy"]


def test_policy_file_returns_correct_path(storage_root):
    result = storage.policy_file("test-policy")
    assert result.name == "test-policy.yml"
    assert result.parent == storage.policies_dir()


def test_load_policy_raises_file_not_found_for_missing_policy(storage_root):
    with pytest.raises(FileNotFoundError, match="policy missing-policy not found"):
        storage.load_policy("missing-policy")


def test_load_policy_loads_valid_policy(storage_root):
    policy_path = storage.policy_file("test-policy")
    policy_path.write_text(
        "name: Test Policy\ndescription: A test policy\n", encoding="utf-8"
    )
    policy = storage.load_policy("test-policy")
    assert isinstance(policy, Policy)
    assert policy.name == "Test Policy"


def test_load_policy_uses_fallback_id_when_id_not_in_yaml(storage_root):
    policy_path = storage.policy_file("my-custom-policy")
    policy_path.write_text("name: Custom Policy\n", encoding="utf-8")
    policy = storage.load_policy("my-custom-policy")
    assert policy.id == "my-custom-policy"
    assert policy.name == "Custom Policy"


def test_load_policy_raises_value_error_for_non_dict_yaml(storage_root):
    policy_path = storage.policy_file("invalid-policy")
    policy_path.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="policy yaml must be an object"):
        storage.load_policy("invalid-policy")


def test_write_report_creates_parent_directories_and_writes_content(tmp_path):
    report_path = tmp_path / "subdir" / "report.txt"
    storage.write_report(report_path, "test content")
    assert report_path.read_text(encoding="utf-8") == "test content"


def test_as_json_returns_pretty_printed_json():
    result = storage.as_json({"key": "value", "number": 42})
    data = json.loads(result)
    assert data == {"key": "value", "number": 42}


def test_load_policy_with_context_renders_template(storage_root):
    policy_path = storage.policy_file("context-policy")
    policy_path.write_text(
        "name: Context Policy\nobjective: Test {{ date }}\n", encoding="utf-8"
    )
    policy = storage.load_policy("context-policy", context={"date": "2026-05-15"})
    assert policy.name == "Context Policy"
    assert "2026-05-15" in policy.objective


def test_from_dict_creates_policy_with_all_fields():
    data = {
        "id": "test-id",
        "name": "Test Policy",
        "description": "A test",
        "objective": "Test objective",
        "specs": ["spec1.md"],
        "scopes": {"required": ["src"], "exclude": ["*.test.py"]},
        "report": {"path": "report.md", "template": "template.md"},
        "agent": "custom-agent",
    }
    policy = Policy.from_dict(data, "fallback")
    assert policy.id == "test-id"
    assert policy.name == "Test Policy"
    assert policy.description == "A test"
    assert policy.objective == "Test objective"
    assert policy.specs == ["spec1.md"]
    assert policy.scopes.required == ["src"]
    assert policy.scopes.exclude == ["*.test.py"]
    assert policy.report.path == "report.md"
    assert policy.agent == "custom-agent"


def test_from_dict_uses_fallback_id():
    data = {"name": "Test Policy"}
    policy = Policy.from_dict(data, "my-fallback")
    assert policy.id == "my-fallback"


def test_from_dict_handles_missing_optional_fields():
    data = {"id": "test-id", "name": "Test Policy"}
    policy = Policy.from_dict(data, "fallback")
    assert policy.description == ""
    assert policy.objective == ""
    assert policy.specs == []
    assert policy.scopes.required == []
    assert policy.scopes.exclude == []


def test_from_dict_default_agent_is_rectifier():
    data = {"name": "Test Policy"}
    policy = Policy.from_dict(data, "fallback")
    assert policy.agent == "rectifier"
