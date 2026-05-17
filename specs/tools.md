# Tool Integration

## Supported AI Tools

| Tool     | Command Template                                                                              |
| -------- | --------------------------------------------------------------------------------------------- |
| kilo     | `kilo run --auto "<prompt>" --print-logs --log-level DEBUG`                                   |
| claude   | `claude -p --dangerously-skip-permissions --output-format stream-json --verbose "<prompt>"`   |
| ccr      | `ccr code -p --dangerously-skip-permissions --output-format stream-json --verbose "<prompt>"` |
| opencode | `opencode run "<prompt>" --print-logs --log-level DEBUG`                                      |
| codex    | `codex exec --full-auto "<prompt>"`                                                           |
