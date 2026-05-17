# Profiles

TOML-based configuration that overrides tool selection per command phase. Use high-tier models for planning and lower-tier models for execution.

## Quick Start

1. Create `.fa/profiles/<name>.toml`:

```toml
[phases.nudge]
tool = "claude"
model = "sonnet"

[phases.gestate-create]
tool = "claude"
model = "opus"

[phases.gestate-run]
tool = "codex"

[phases.task-run]
tool = "codex"
model = "o3"
```

2. Use it:

```bash
fa nudge --profile my-profile
fa gestate 123 --profile my-profile
fa task run --profile my-profile
fa policy run --profile my-profile
fa policy run-all --profile my-profile
```

## Manage Profiles

```bash
fa profile list          # list all profiles
fa profile show <name>   # display profile contents
```

## Per-Phase Settings

| Field        | Type                | Description                              |
| ------------ | ------------------- | ---------------------------------------- |
| `tool`       | string              | Tool name (claude, codex, etc.)          |
| `model`      | string              | Passed as `--model` to the tool          |
| `agent`      | string              | Agent name override                      |
| `extra_args` | list[string]        | Extra CLI arguments for the tool         |
| `env`        | map[string, string] | Environment variables for the subprocess |

## Behavior

- Without `--profile`, everything works as before — CLI flags like `--tool` apply normally.
- With `--profile`, the profile takes precedence over `--tool` flags.
- If a phase is missing from the profile, CLI defaults are used.
