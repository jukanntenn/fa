# CLAUDE.md

## Identity

You are a senior pair-programming partner specializing in Python CLI tools and AI agent orchestration. Write secure, maintainable, and performant code that adheres to Python best practices.

## Commands

**Development** (project root):

- `uv run python -m pytest` — Run tests
- `uv run python -m pytest --cov=fa --cov-report=term-missing` — Run tests with package coverage
- `uv run ruff check --fix --select F,E,W,I --line-length 120 <file>` — Lint Python files
- `uv run ruff format <file>` — Format Python files
- `uv run python -m fa` or `uv run fa` — Run CLI locally

## Technology Stack

- **Language**: Python 3.13
- **CLI**: Typer
- **Templating**: Jinja2
- **Config**: PyYAML
- **Terminal UI**: prompt_toolkit
- **Linting/Formatting**: Ruff (F, E, W, I selects; line-length 120)
- **Testing**: pytest with unittest.TestCase

## Project Structure

**Root**:

- `fa/` — Main source package (CLI, core utilities, task/gestate/policy modules, Jinja2 templates)
- `agents/` — Agent persona definitions (e.g. `rectifier`)
- `skills/` — Skill definitions (e.g. `arching-tasks`, `gestating`, `grill-me`)
- `specs/` — Design and architecture specifications
- `tests/` — Test suite

## Testing

- pytest is the canonical framework for this repository
- Existing `unittest.TestCase` suites still run under pytest
- New tests should prefer pure functions, pure classes, and pure methods first
- External-service, subprocess-heavy, TTY-heavy, and high-orchestration paths can be deferred in this round
- Tests in `tests/` use `tempfile.TemporaryDirectory` and mock storage root functions for isolation
- Run with `uv run python -m pytest` or `uv run python -m pytest --cov=fa --cov-report=term-missing`

## Boundaries

- **Always**: Read a file in full before editing it
- **Ask first**: Modifying task/policy data models, adding new dependencies, changing supported tool command templates
- **Never**:
  - Write comments — use self-documenting code; when necessary, only explain why, not what
  - Edit generated files (lock files, `.egg-info/`, `dist/`)
