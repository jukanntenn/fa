# Nudge Command

Automated iterative workflow: run an AI tool, extract a `task_id` from its output, then call `fa gestate` on it. Repeats until stopped.

## Usage

```bash
fa nudge                          # defaults: claude, 100 iterations, /nudging prompt
fa nudge --profile my-profile     # use a profile for tool/model config
fa nudge --max-iterations 50      # stop after 50 iterations
fa nudge --no-gestate-run         # only run the tool, skip gestate
```

## Options

| Option                             | Default         | Description                                |
| ---------------------------------- | --------------- | ------------------------------------------ |
| `--tool`                           | `claude`        | Tool for the nudging phase                 |
| `--gestate-tool`                   | `claude`        | Tool for the gestate phase                 |
| `--max-iterations`                 | `100`           | Max iterations before auto-stop            |
| `--quota-threshold`                | `90`            | GLM quota % that triggers a wait           |
| `--quota-buffer`                   | `1800`          | Seconds to wait after quota reset          |
| `--prompt`                         | `/nudging`      | Prompt sent to the tool each iteration     |
| `--gestate-max-rounds`             | `10`            | Max gestate convergence rounds             |
| `--gestate-run-rounds`             | `1`             | Execution rounds per task                  |
| `--gestate-run / --no-gestate-run` | `--gestate-run` | Whether to run tasks after gestation       |
| `--profile`                        | —               | Profile name (see [profiles](profiles.md)) |

## How It Works

1. Sends `--prompt` to `--tool`, captures output
2. Extracts a `task_id` from the output (supports raw JSON, fenced code blocks, nested objects)
3. If found, runs `fa gestate` on that task
4. Repeats until max iterations or Ctrl+C

Logs are written to `.fa/logs/agents/nudge/`.
