# Tool Integration

## Supported AI Tools

| Tool     | Command Template                                                                              |
| -------- | --------------------------------------------------------------------------------------------- |
| kilo     | `kilo run --auto "<prompt>" --print-logs --log-level DEBUG`                                   |
| claude   | `claude -p --dangerously-skip-permissions --output-format stream-json --verbose "<prompt>"`   |
| ccr      | `ccr code -p --dangerously-skip-permissions --output-format stream-json --verbose "<prompt>"` |
| opencode | `opencode run "<prompt>" --print-logs --log-level DEBUG`                                      |
| codex    | `codex exec --full-auto "<prompt>"`                                                           |

## GLM Quota Management

When `--glm-plan` is enabled:

1. Check GLM token usage via API
2. If usage >= 70%, wait until reset time + 30 minutes
3. Proceed with execution
