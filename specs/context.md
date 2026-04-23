# Dynamic Context Injection

## Goal

Construct task prompts with appropriate context based on three axes:

- Task type (standalone, parent, or subtask)
- Execution mode (fresh run vs. attempt run)
- Available artifacts (memory files, feedback files)

## Design Principles

1. **Contextual relevance**: Inject only relevant context; provide paths for on-demand reading
2. **Clear separation**: Distinct sections for different context types
3. **Minimal prompt bloat**: Use counts/paths instead of full content where appropriate
4. **Template-driven**: All prompt structure controlled via Jinja2 template (`fa/templates/task_prompt.j2`)

## Run Modes

### Fresh Run (default)

Triggered when `--attempt` is **not** provided.

- `memory_sequence` = count(memory-\*.md) + 1
- No attempt concept displayed to agent
- Context: task metadata + task.md path + prior rounds' memory files
- Instruction: re-evaluate entire scope, build on what is correct, do not simply apply incremental patches

### Attempt Run (--attempt flag)

Triggered when `--attempt` **is** provided.

- `attempt` = count(feedback-\*.md) + 1
- Displays "Attempt: N" to agent
- Prerequisite: feedback files must exist
- Context: task metadata + task.md path + all memory files + feedback files
- Instruction: resume from current state, do not repeat completed work

## Context Sources

### Task Metadata (all tasks)

Fields injected: `id`, `slug`, `depends_on`, `related_to`, `status`.

### Task Description File

Path to `task.md` is always provided. The AI agent reads the file to understand full requirements.

### Parent Context (subtasks only)

For tasks with `parent_id != null`:

| Context               | Injection Method                      |
| --------------------- | ------------------------------------- |
| Parent metadata       | Full metadata fields                  |
| Parent task.md path   | Explicit path for AI to read          |
| Parent memory files   | Count only; paths available on demand |
| Parent feedback files | Count only; paths available on demand |

Rationale: parent context provides background without overwhelming the prompt.

### Memory Files

| Mode        | Injection                                                |
| ----------- | -------------------------------------------------------- |
| Fresh run   | List all existing memory file paths from previous rounds |
| Attempt run | List all memory file paths                               |

### Feedback Files (attempt run only)

Feedback is split into two categories:

- **History**: `feedback-1.md` through `feedback-{N-2}.md` (if N > 2)
- **Latest**: `feedback-{N-1}.md` (the most recent feedback triggering this attempt)

Fresh runs do not inject feedback files.

## Prompt Section Hierarchy

The template renders sections conditionally:

```
1. Execution Guidelines (always)
2. Parent Context (subtasks only)
3. Task Information (always)
4. Run Mode Instructions
   - Fresh Run Instructions (when is_attempt_run=False)
   - Attempt Context with memory/feedback (when is_attempt_run=True)
5. Output Instructions (always)
```

## Prompt Rebuilding

The prompt is rebuilt at the start of each round (not cached). This ensures:

- Memory file list grows as prior rounds create new `memory-{N}.md` files
- Task metadata is re-read from disk each round
- Quota checks happen per-round before prompt rendering
