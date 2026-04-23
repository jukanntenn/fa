# Task

## Data Model

### Task (task.json)

```json
{
  "id": 5,
  "slug": "implement-auth",
  "parent_id": null,
  "status": "pending",
  "depends_on": [3, 4],
  "related_to": [7],
  "created_at": "2026-03-25T10:30:00",
  "completed_at": null
}
```

| Field          | Type           | Description                                                |
| -------------- | -------------- | ---------------------------------------------------------- |
| `id`           | int            | Global sequential task ID                                  |
| `slug`         | string         | URL-friendly identifier (alphanumeric + hyphens)           |
| `parent_id`    | int \| null    | Parent task ID for subtasks, null for standalone/parent    |
| `status`       | string         | `pending` \| `running` \| `completed`                      |
| `depends_on`   | int[]          | Task IDs for dependency graph (informational, no blocking) |
| `related_to`   | int[]          | Task IDs for related tasks (informational only)            |
| `created_at`   | string         | ISO 8601 timestamp                                         |
| `completed_at` | string \| null | ISO 8601 timestamp when completed                          |

### Task Directory Naming

Format: `{id}-{mm-dd}-{slug}`

Examples: `1-03-25-setup-project`, `2-03-25-add-authentication`, `15-04-01-refactor-api`

### Memory Files

After each round of task execution, the AI agent creates a `memory-N.md` file. The sequence number increments each round. When `--rounds 3` is used, a fresh run produces `memory-1.md`, `memory-2.md`, and `memory-3.md`. Memory files record the AI's work and decisions for future reference.

### Feedback Files

`feedback-N.md` files are human-provided feedback placed in the task directory between runs. They drive attempt-mode execution (see [context.md](context.md)).

## Execution Principles

### Task Run

1. Scan pending tasks, optionally filtered by ID range
2. Build execution plan — group subtasks with their parent; parent always executes after subtasks
3. User confirms the plan before execution begins
4. For each task, run N rounds via the configured AI tool
5. Prompt is rebuilt each round to reflect new memory files from prior rounds
6. GLM quota is checked per-round (if enabled)
7. On failure: task resets to `pending`, execution continues to next task

### Parent Task Execution Rule

When executing subtasks (whether all or a subset via ID range):

- The parent task **always executes after** all its subtasks complete
- Only the specified subtasks run; siblings outside the range are skipped

### Attempt Inference

| Feedback Files Present                  | Attempt |
| --------------------------------------- | ------- |
| None                                    | 1       |
| `feedback-1.md`                         | 2       |
| `feedback-1.md`, `feedback-2.md`        | 3       |
| `feedback-1.md` through `feedback-N.md` | N + 1   |

### Subtask Discovery

A task has subtasks if its directory contains subdirectories matching pattern `{id}-{mm-dd}-{slug}` with valid `task.json`.
