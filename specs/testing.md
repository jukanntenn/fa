# Testing Guidelines

> Testing standards and best practices for this project.

## Overview

This project uses **pytest** for unit testing. Tests are organized to mirror the source code structure, making it easy to locate tests for specific modules.

## File Organization

Tests MUST mirror the source code structure:

| Source                     | Test                       |
| -------------------------- | -------------------------- |
| `src/feeber/ai/`           | `tests/ai/`                |
| `src/feeber/config.py`     | `tests/config/`            |
| `src/feeber/db/`           | `tests/db/`                |
| `src/feeber/utils/`        | `tests/utils/`             |
| `src/feeber/utils/text.py` | `tests/utils/test_text.py` |

When tests for a single module grow too large, create a subdirectory mirroring the source module. For example, `src/feeber/config.py` tests grew into multiple files and were split into `tests/config/`:

**Before (flat files):**

```
tests/
├── test_config.py                # Core config tests
├── test_config_analysis.py       # Analysis config tests
├── test_config_markpost.py       # Markpost config tests
├── test_config_miniflux.py       # Miniflux config tests
├── test_config_notification.py   # Notification config tests
├── test_config_report.py         # Report config tests
├── test_config_validation.py     # Config validation tests
```

**After (subdirectory):**

```
tests/config/
├── __init__.py                   # Empty init for pytest discovery
├── test_config.py                # Core config tests
├── test_config_analysis.py       # Analysis config tests
├── test_config_markpost.py       # Markpost config tests
├── test_config_miniflux.py       # Miniflux config tests
├── test_config_notification.py   # Notification config tests
├── test_config_report.py         # Report config tests
└── test_config_validation.py     # Config validation tests
```

**Pattern:** When tests for a module grow beyond a single file, create a `tests/<module>/` subdirectory with an empty `__init__.py`. Split test files by logical concern, not arbitrary line counts.

## Naming Conventions

| Element        | Convention                   | Example                                    |
| -------------- | ---------------------------- | ------------------------------------------ |
| Test files     | `test_<module_name>.py`      | `test_models.py`, `test_text.py`           |
| Test functions | `test_<function>_<scenario>` | `test_filter_new_entries_filters_per_feed` |
| Fixture names  | `<entity>_fixture`           | `config_file`, `test_db`                   |

## Commands

Pytest is pre-installed in the environment. Run `pytest` directly to execute all tests. If errors persist after multiple attempts, stop immediately and report the issue. 🚫 Do NOT attempt to install pytest yourself.

```bash
# Run all tests
uv run pytest -v

# Run specific test file
uv run pytest tests/config/test_config.py -v

# Run specific test function
uv run pytest tests/config/test_config.py::test_miniflux_defaults -v

# Run tests matching pattern
uv run pytest -k "filter_new_entries" -v
```

## Best Practices

### Test Cases Organization

**Principles:**

- Do NOT use classes for test organization, always use functions
- Do NOT use unittest framework
- Use comment blocks to group related tests
- One test function tests one case
- Use `pytest.mark.parametrize` for table-driven tests

**Example:**

```python
from feeber.utils.text import extract_json

# ─── extract_json ──────────────────────────────────────────────
def test_extract_json_plain_json():
    ...

def test_extract_json_wrapped_text():
    ...

# ─── truncate ──────────────────────────────────────────────
@pytest.mark.parametrize("input, expected", [
    ("input-1", "expected-1"),
    ("input-2", "expected-2"),
])
def test_truncate(input, expected):
    result = truncate(input)
    assert result == expected
```

### Use Fixtures

**Principles:**

- Config MUST be constructed, NOT mocked
- Database MUST NOT be mocked, use fixtures instead
- Leverage pytest built-in fixtures such as `tmp_path`, `monkeypatch`, etc.
- Extract repeatedly constructed objects into fixtures. Place globally shared fixtures in `tests/conftest.py`, module-specific fixtures in the corresponding module's `conftest.py`. Pytest will auto-discover them
- Use `monkeypatch` to manage environment variables with `monkeypatch.delenv` and `monkeypatch.setenv`
- Clean environment variables before each test

**Available Fixtures:**

- `config_file`: Factory fixture for creating config files
- `default_config`: Config object with all default values
- `config`: Config object without None values, empty strings, zeros, or other empty values
- `custom_config`: Config object with all default values overridden
- `test_db`: In-memory database for testing, leaves no traces, no cleanup required

### Mocking External Services

**Components NOT to Mock:**

| Component         | Rule        | Alternative                         |
| ----------------- | ----------- | ----------------------------------- |
| Config            | DO NOT mock | Construct real config with fixtures |
| Database          | DO NOT mock | Use in-memory SQLite                |
| Utility functions | DO NOT mock | Test directly                       |
| Internal logic    | DO NOT mock | Test implementation directly        |

**Components That CAN Be Mocked:**

| Component         | When to Mock | Example                             |
| ----------------- | ------------ | ----------------------------------- |
| External APIs     | Always       | `requests.post`, HTTP clients       |
| External services | Always       | Miniflux API, Markpost API          |
| Filesystem        | When needed  | `Path.write_text`, file operations  |
| Time              | When needed  | `datetime.now`, time-sensitive code |

External services currently used by the system: Markpost, Miniflux

### Document tests

Add docstrings for tests with non-obvious behavior:

```python
def test_checkpoint_get_last_successful():
    """
    Test that get_last_successful skips failure and partial status checkpoints,
    returning only the most recent success checkpoint.
    """
    # Create failure checkpoint
    MinifluxCheckpoint.create_checkpoint(
        feed_offsets={},
        last_entry_id=50,
        status="failure",
    )

    # Create success checkpoint
    MinifluxCheckpoint.create_checkpoint(
        feed_offsets={1: 100},
        last_entry_id=100,
        status="success",
    )

    ...
```

## Common Pitfalls

1. **Using unittest framework** - Always use pytest, not unittest.TestCase
2. **Mocking config** - Construct real config using fixtures
3. **Mocking database** - Use in-memory SQLite, not mocks
4. **Testing multiple cases in one function** - One test per case, or use parametrize
5. **Unclear test names** - Use descriptive names like `test_filter_new_entries_filters_per_feed`
6. **Not cleaning up state** - Use fixtures with cleanup in yield statements
7. **Hardcoding test data** - Use fixtures for reusable test data

## Type Hints

```python
from pathlib import Path
from feeber.config import Config

# Fixture return types should be specified
@pytest.fixture
def config_file(tmp_path: Path) -> callable:
    def _create_config_file(toml_content: str, filename: str | None = None) -> str:
        ...
    return _create_config_file

# Test function parameters should use type hints
def test_config_load_valid_file(config_file: callable) -> None:
    ...
```
