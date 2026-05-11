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
| `status`       | string         | `draft` \| `approved` \| `running` \| `failed` \| `completed` |
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

## State Machine

### States

| State      | Description                                    |
| ---------- | ---------------------------------------------- |
| `draft`    | Created, awaiting gestate review               |
| `approved` | Gestate review passed, ready for execution     |
| `running`  | Currently executing                            |
| `failed`   | Execution failed, eligible for retry           |
| `completed`| Execution succeeded or manually completed      |

### Valid Transitions

```
draft     → approved       (gestate review passes)
approved  → running        (fa task run starts execution)
approved  → completed      (fa task done, manual completion)
running   → completed      (all rounds succeed)
running   → failed         (any round fails)
failed    → running        (fa task run retries)
failed    → completed      (fa task done, manual completion)
```

`completed` is a terminal state. To re-execute a completed task, use `--force` which resets it to `approved` first.

`draft` tasks cannot be executed or marked as done — they must go through `fa gestate` first. `--force` bypasses this requirement.

### Lifecycle Example

```
fa gestate "implement auth"  → draft → (review rounds) → approved
fa task run                  → approved → running → failed (round failed)
fa task run --ids 5          → failed → running → completed (all rounds succeed)
fa task archive 5            → archived
```

## Execution Principles

### Task Run

1. Build candidate list:
   - If `--ids` provided: parse comma-separated IDs and ranges (e.g., `--ids 1,3,5-8`)
   - If `--ids` not provided: auto-select all tasks with status `approved` or `failed`
   - If `--attempt` is active: ignore task status (like `--force`) but skip tasks with no feedback files
   - If `--force` is active: reset task to `approved` then run (requires `--ids`)
2. Build execution plan — group subtasks; only leaf tasks (subtasks or standalone tasks) are executed, parent tasks are excluded when children are in the selected set
3. User confirms the plan before execution begins
4. For each task, run N rounds via the configured AI tool
5. Prompt is rebuilt each round to reflect new memory files from prior rounds
6. GLM quota is checked per-round (if enabled)
7. On failure: task status becomes `failed`, execution continues to next task

### Parent Task Execution Rule

When executing subtasks (whether all or a subset via `--ids`):

- Parent tasks are **excluded** from execution when any of their children are in the selected set
- Only leaf tasks (subtasks or standalone tasks without selected children) are executed
- A parent task with no children in the selected set is treated as a standalone task and executed normally
- Siblings outside the selected range are skipped

### Attempt Inference

| Feedback Files Present                  | Attempt |
| --------------------------------------- | ------- |
| None                                    | 1       |
| `feedback-1.md`                         | 2       |
| `feedback-1.md`, `feedback-2.md`        | 3       |
| `feedback-1.md` through `feedback-N.md` | N + 1   |

### Subtask Discovery

A task has subtasks if its directory contains subdirectories matching pattern `{id}-{mm-dd}-{slug}` with valid `task.json`.
