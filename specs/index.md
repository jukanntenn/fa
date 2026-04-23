# Specifications

Design specifications for the `fa` tool. These documents capture golden principles, patterns, high-level design, and domain knowledge — not implementation details. For argument flags, code-level APIs, and full templates, read the source code.

## Specification Files

| File                     | Domain                | When to Refer                                                                           |
| ------------------------ | --------------------- | --------------------------------------------------------------------------------------- |
| [layout.md](layout.md)   | Directory structure   | When creating or modifying `.fa/` paths, auto-initialization, or project root detection |
| [cli.md](cli.md)         | CLI subcommand design | When adding or removing subcommands, or changing the command structure                  |
| [task.md](task.md)       | Task domain model     | When changing task data model, execution rules, or parent/subtask relationships         |
| [policy.md](policy.md)   | Policy domain model   | When changing policy YAML schema, file scoping, or policy execution flow                |
| [context.md](context.md) | Context injection     | When changing how prompts are assembled, what context is injected, or run mode behavior |
| [tools.md](tools.md)     | AI tool integration   | When adding new AI tools or changing tool invocation commands                           |
| [logging.md](logging.md) | Logging conventions   | When adding new log events or changing logging format and levels                        |
| [error.md](error.md)     | Error handling        | When adding new error paths or changing error handling behavior                         |

## Principles

- Specifications describe **WHAT** and **WHY**, not **HOW**
- Each file must remain under 200 lines
- When the mechanism changes, update the specification to reflect the new design
- For implementation details, read the source code under `fa/`
