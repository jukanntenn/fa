# CLI

## Overview

`fa` is a task orchestration tool that automates running AI coding agents on defined tasks. It manages task lifecycle, dependencies, multi-attempt workflows, and policy-based verification.

## Design Principles

- CLI is a thin facade over domain modules; no business logic in command handlers
- Subcommands map directly to domain modules (`task`, `policy`)
- Subcommand structure is stable; individual arguments may change frequently
- Confirmation prompts protect destructive and long-running operations

## Subcommands

### fa init

Initialize `.fa/` directory structure in the project root.

### fa task

Task lifecycle management. Subcommands:

| Subcommand | Purpose                                                     |
| ---------- | ----------------------------------------------------------- |
| `create`   | Create a new task (standalone or as subtask via `--parent`) |
| `list`     | List tasks with optional status filter                      |
| `info`     | Show task metadata and details                              |
| `done`     | Mark tasks as completed (supports ID ranges)                |
| `rm`       | Delete tasks (with confirmation, supports ID ranges)        |
| `archive`  | Archive completed tasks (organized by year-month)           |
| `run`      | Execute pending tasks via AI tool                           |

### fa policy

Policy verification. Subcommands:

| Subcommand | Purpose                           |
| ---------- | --------------------------------- |
| `list`     | List available policy definitions |
| `run`      | Execute specified policies        |
| `run-all`  | Execute all defined policies      |
