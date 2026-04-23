# Logging

## Log Structure

```
.fa/logs/
├── fa.log                           # Tool internal logs (DEBUG level)
└── agents/                          # Agent execution logs
    └── {task-dir}/
        ├── round-1-prompt.md        # Rendered prompt for round 1
        ├── round-1-{tool}.log       # Agent raw output
        ├── round-2-prompt.md
        ├── round-2-{tool}.log
        └── ...
```

## Log Format

- Tool logs (fa.log): `{timestamp} [{level}] - {message}`
- Agent logs: raw output from AI tool execution
- Prompt files: full rendered prompt content in Markdown

## Log Levels

- Console: INFO level
- File (fa.log): DEBUG level

## Logging Conventions

### Event Categories and Levels

| Category            | Level   | Examples                                       |
| ------------------- | ------- | ---------------------------------------------- |
| Execution lifecycle | INFO    | Execution plan, task start/complete/fail       |
| Per-round progress  | INFO    | Round start, round complete with duration      |
| Diagnostic data     | DEBUG   | Prompt rendering stats, scope resolution       |
| Resource management | WARNING | GLM quota wait states                          |
| GLM quota OK        | DEBUG   | Quota check passed                             |
| Errors              | ERROR   | Task not found, policy not found, tool failure |

### Format Principles

- Include task/policy identifier: `Task [{id}]` or `Policy "{id}"`
- Use pipe-separated key=value pairs for structured context: `round 1/3 completed in 45s | exit_code=0`
- Include duration in seconds for completed operations
