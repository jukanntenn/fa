# Policy

## Data Model

### Policy (YAML)

```yaml
id: testing
name: Test Compliance Check
description: Ensure test code complies with specifications
objective: |
  Ensure test code complies with specifications
specs:
  - "./specs/testing-guidelines.md"
  - "./specs/quality-guidelines.md"
scopes:
  required:
    - "git:./tests/"
    - "./src/"
  exclude:
    - "./tests/fixtures/"
    - "*.snap"
report:
  path: ".fa/reports/{{ policy.id }}/{{ date }}_{{ time }}/round-{{ round }}.md"
  template: |
    # Policy Report: {{ policy.name }}
    ...
agent: rectifier
```

| Field             | Type     | Description                                                               |
| ----------------- | -------- | ------------------------------------------------------------------------- |
| `id`              | string   | Unique identifier (defaults to filename stem)                             |
| `name`            | string   | Human-readable name                                                       |
| `description`     | string   | Brief description                                                         |
| `objective`       | string   | Detailed objective for the AI agent                                       |
| `specs`           | string[] | Specification file paths (relative to project root)                       |
| `scopes.required` | string[] | Required file scopes (`git:` prefix for git-aware filtering)              |
| `scopes.exclude`  | string[] | File patterns to exclude from scopes                                      |
| `report.path`     | string   | Report output path (Jinja2; variables: `policy`, `date`, `time`, `round`) |
| `report.template` | string   | Report template (Jinja2)                                                  |
| `agent`           | string   | Agent persona for the AI tool (default: `"rectifier"`)                    |

### Git-aware Scoping

Paths prefixed with `git:` are filtered to only include files that are staged, modified in working directory, or untracked. In non-git directories, `git:` entries fall back to listing all matching files.

## Execution

Each policy executes for N rounds. Each round:

1. Re-load policy YAML with fresh Jinja2 context (`date`, `time`, `round`)
2. Expand `git:` scoped paths and apply exclude patterns
3. Build prompt from policy definition + scoped file paths + report path
4. Execute via AI tool using the policy's `agent` persona
5. AI agent writes the report to the specified path

### Failure Handling

- Round failure (non-zero exit code) stops further rounds for that policy
- Policy not found: logged as error, skipped
- Quota exceeded (`--glm-plan`): remaining rounds skipped

### Agent Integration

Each policy declares an `agent` persona (default: `"rectifier"`). The agent argument is passed to the AI tool via the tool-specific flag defined in configuration.
