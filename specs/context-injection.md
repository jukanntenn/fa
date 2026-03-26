# Dynamic Context Injection Mechanism for Task Prompts

## 1. Overview

### 1.1 Goal

Design and implement a dynamic context injection mechanism that constructs task prompts with the appropriate context based on:
- Task type (standalone, parent, or subtask)
- Execution mode (fresh run vs. attempt run)
- Available artifacts (memory files, feedback files)

### 1.2 Design Principles

1. **Contextual relevance**: Inject only relevant context; provide paths for on-demand reading
2. **Clear separation**: Distinct sections for different context types
3. **Minimal prompt bloat**: Use counts/paths instead of full content where appropriate
4. **Template-driven**: All prompt structure controlled via Jinja2 template

### 1.3 Run Mode Mechanism

The system supports two execution modes, controlled exclusively by the `--attempt` CLI flag:

#### Fresh Run (default)

- Triggered when `--attempt` flag is **NOT** provided
- `is_attempt_run` = `False`
- `memory_index` = 1 (internal index for memory output)
- Prompt: Does NOT display "Attempt" information (fresh run has no attempt concept)
- Context: Task metadata + task.md path only
- Instruction: "Re-evaluate the entire task scope and requirements. Build upon what is correct while addressing any gaps or issues."
- Memory output: `memory-1.md`

#### Attempt Run

- Triggered when `--attempt` flag **IS** provided
- `is_attempt_run` = `True`
- `attempt` = `count(feedback-*.md) + 1`
- Prompt: Displays "Attempt: N" in Task Information
- Prerequisite: Feedback files must exist (attempt run implies previous feedback)
- Context: Task metadata + task.md path + memory files + feedback files
- Instruction: "Resume from the current state instead of restarting from scratch. Do not repeat already-completed investigation or validation."
- Memory output: `memory-{attempt}.md`

#### Mode Determination Logic

```
is_attempt_run = (--attempt CLI flag is set)
attempt = count(feedback-*.md) + 1 if is_attempt_run else 1
```

**Important**:
- Fresh run has no "attempt" concept - the `attempt` variable is purely an internal index for memory output file naming
- Only attempt run displays the attempt number to the AI agent

---

## 2. Context Sources

### 2.1 Task Metadata

All tasks inject the following metadata fields:

| Field | Source | Description |
|-------|--------|-------------|
| `id` | `task.json` | Global sequential task ID |
| `slug` | `task.json` | URL-friendly identifier |
| `depends_on` | `task.json` | List of dependency task IDs |
| `related_to` | `task.json` | List of related task IDs |
| `status` | `task.json` | Current task status |

### 2.2 Task Description File

- Path to `task.md` is always provided
- AI agent reads the file to understand the full task requirements

### 2.3 Parent Task Context (Subtasks Only)

For tasks with `parent_id != null`:

| Context | Injection Method |
|---------|-----------------|
| Parent metadata | Full metadata (id, slug, depends_on, related_to) |
| Parent task.md path | Explicit path for AI to read |
| Parent memory files | Count only; paths available for on-demand reading |
| Parent feedback files | Count only; paths available for on-demand reading |

**Rationale**: Parent context provides background without overwhelming the prompt. AI reads parent files only when necessary.

### 2.4 Memory Files

| Mode | Injection |
|------|-----------|
| Fresh run (is_attempt_run=False) | None (no memory files exist) |
| Attempt run (is_attempt_run=True) | List all `memory-{1..N}.md` paths where N < attempt |

### 2.5 Feedback Files

| Mode | Injection |
|------|-----------|
| Fresh run (is_attempt_run=False) | None |
| Attempt run (is_attempt_run=True) | Separate into "History" and "Latest Feedback" |

Feedback structure for attempt N:
- **History**: `feedback-1.md` through `feedback-{N-2}.md` (if N > 2)
- **Latest**: `feedback-{N-1}.md` (the most recent feedback triggering this attempt)

---

## 3. Template Structure

### 3.1 Section Hierarchy

The prompt template is organized into the following sections, rendered conditionally:

```
1. Execution Guidelines (always)
2. Parent Context (subtasks only)
3. Task Information (always)
4. Run Mode Instructions (conditional)
   4a. Fresh Run Instructions (is_attempt_run=False)
   4b. Attempt Context (is_attempt_run=True)
5. Output Instructions (always)
```

### 3.2 Complete Template

```jinja2
# Execution Guidelines

This is an unattended orchestration session. Never ask a human to perform follow-up actions. Operate autonomously end-to-end
unless blocked by missing requirements, secrets, or permissions. If blocked, record the blocker in the memory file.

Based on the task requirements, load necessary specification files on demand and strictly follow specifications during development.

Specification index: {{ specs_dir }}/index.md
{% if parent %}

# Parent Task

- ID: {{ parent.id }}
- Slug: {{ parent.slug }}
{% if parent.depends_on %}- Depends on: {{ parent.depends_on|join(', ') }}
{% endif %}{% if parent.related_to %}- Related to: {{ parent.related_to|join(', ') }}
{% endif %}- Task file: {{ parent_file }}
- Memory files: {{ parent_memory_count }} file(s) available
- Feedback files: {{ parent_feedback_count }} file(s) available
{% endif %}

# Task Information

- ID: {{ task.id }}
- Slug: {{ task.slug }}
{% if task.depends_on %}- Depends on: {{ task.depends_on|join(', ') }}
{% endif %}{% if task.related_to %}- Related to: {{ task.related_to|join(', ') }}
{% endif %}{% if is_attempt_run %}- Attempt: {{ attempt }}
{% endif %}- Task file: {{ task_file }}
{% if not is_attempt_run %}

## Fresh Run Instructions

This is a fresh run. Re-evaluate the entire task scope and requirements. Build upon what is correct while addressing any gaps
or issues. Do not simply apply incremental patches.
{% else %}

## Attempt Context

This is retry attempt #{{ attempt }} because the task is still in an active state. Resume from the current state instead of
restarting from scratch. Do not repeat already-completed investigation or validation.

### Previous Memory Files

Read previous work summaries:
{% for memory_file in memory_files %}
- {{ memory_file }}
{% endfor %}

### Feedback History
{% if history_feedback_files %}
{% for feedback_file in history_feedback_files %}
- {{ feedback_file }}
{% endfor %}
{% else %}
(None - this is your first retry)
{% endif %}

### Latest Feedback

The most recent feedback that triggered this attempt:
- {{ latest_feedback_file }}

This attempt is because there is feedback indicating the task was not completed as expected. Pay extra attention to quality and
ensure complete delivery that satisfies user expectations.
{% endif %}

# Output Instructions

After completion, write your work summary to: {{ memory_output_path }}
```

---

## 4. Template Variables

### 4.1 Variable Definitions

| Variable | Type | Description |
|----------|------|-------------|
| `task` | dict | Current task metadata from `task.json` |
| `parent` | dict \| null | Parent task metadata (null for standalone tasks) |
| `task_file` | string | Relative path to current task's `task.md` |
| `parent_file` | string \| null | Relative path to parent's `task.md` (null if no parent) |
| `attempt` | int | Internal index for memory output; only displayed when `is_attempt_run=True` |
| `is_attempt_run` | bool | True if `--attempt` flag is set (attempt run), False otherwise (fresh run) |
| `memory_files` | list[string] | List of relative paths to memory files (empty for fresh run) |
| `history_feedback_files` | list[string] | List of feedback files excluding latest (empty for first retry) |
| `latest_feedback_file` | string \| null | Path to most recent feedback file (null for fresh run) |
| `parent_memory_count` | int | Count of parent's memory files (0 if no parent) |
| `parent_feedback_count` | int | Count of parent's feedback files (0 if no parent) |
| `memory_output_path` | string | Relative path for AI to write memory output |
| `specs_dir` | string | Relative path to specs directory |

### 4.2 Variable Computation Logic

```
is_attempt_run = value of --attempt CLI flag (True if set, False otherwise)

attempt = count(feedback-*.md in task directory) + 1 if is_attempt_run else 1

memory_files = [
  memory-1.md, memory-2.md, ..., memory-{attempt-1}.md
] if is_attempt_run else []

all_feedback_files = [
  feedback-1.md, feedback-2.md, ..., feedback-{attempt-1}.md
] if is_attempt_run else []

history_feedback_files = all_feedback_files[:-1] if len(all_feedback_files) > 1 else []

latest_feedback_file = all_feedback_files[-1] if all_feedback_files else null

parent_memory_count = count(memory-*.md in parent directory) if parent else 0

parent_feedback_count = count(feedback-*.md in parent directory) if parent else 0
```

---

## 5. Implementation Changes

### 5.1 Files to Modify

| File | Changes |
|------|---------|
| `fa/templates/task_prompt.j2` | Replace with new template structure |
| `fa/task/prompt.py` | Update `build_task_prompt()` to compute new variables |

### 5.2 `fa/task/prompt.py` Changes

```python
def build_task_prompt(task: Task, parent: Task | None, is_attempt_run: bool) -> str:
    attempt = infer_attempt(task, is_attempt_run)
    
    # Memory files for current task
    memory_files = [
        relative_path(task.path / f"memory-{index}.md") 
        for index in range(1, attempt)
    ]
    
    # Feedback files for current task
    feedback_files = [
        relative_path(task.path / f"feedback-{index}.md") 
        for index in range(1, attempt)
    ]
    
    # Split feedback into history and latest
    history_feedback_files = feedback_files[:-1] if len(feedback_files) > 1 else []
    latest_feedback_file = feedback_files[-1] if feedback_files else None
    
    # Parent context counts
    if parent:
        parent_memory_files = sorted(parent.path.glob("memory-*.md"))
        parent_feedback_files = sorted(parent.path.glob("feedback-*.md"))
        parent_memory_count = len(parent_memory_files)
        parent_feedback_count = len(parent_feedback_files)
    else:
        parent_memory_count = 0
        parent_feedback_count = 0
    
    memory_output_path = relative_path(task.path / f"memory-{attempt}.md")
    
    env, template_name = task_template()
    try:
        template = env.get_template(template_name)
    except TemplateNotFound as exc:
        raise FileNotFoundError("template not found") from exc
    
    return template.render(
        task=task.to_dict(),
        parent=parent.to_dict() if parent else None,
        task_file=relative_path(task.path / TASK_FILE_NAME),
        parent_file=relative_path(parent.path / TASK_FILE_NAME) if parent else None,
        attempt=attempt,
        is_attempt_run=is_attempt_run,
        memory_files=memory_files,
        history_feedback_files=history_feedback_files,
        latest_feedback_file=latest_feedback_file,
        parent_memory_count=parent_memory_count,
        parent_feedback_count=parent_feedback_count,
        memory_output_path=memory_output_path,
        specs_dir=str(project_root() / "specs"),
    )
```

---

## 6. Edge Cases

### 6.1 Attempt Run Without Feedback Files (Invalid)

Using `--attempt` flag without feedback files is invalid:
- Attempt run implies feedback exists
- User should add feedback files before running attempt mode
- System does not prevent this, but the prompt will show empty feedback sections

### 6.2 Parent Task with No Memory/Feedback

If parent task exists but has no memory or feedback files:
- Counts are 0
- Template shows "0 file(s) available"

### 6.3 Missing Spec Index

If `specs/index.md` does not exist:
- Path is still provided in template
- AI agent handles missing file gracefully

### 6.4 First Retry Attempt

When `attempt = 2`:
- `memory_files` = [`memory-1.md`]
- `history_feedback_files` = []
- `latest_feedback_file` = `feedback-1.md`
- Template shows "None - this is your first retry" for history section

---

## 7. Example Outputs

### 7.1 Fresh Run - Standalone Task

```
# Execution Guidelines

This is an unattended orchestration session. Never ask a human to perform follow-up actions. Operate autonomously end-to-end
unless blocked by missing requirements, secrets, or permissions. If blocked, record the blocker in the memory file.

Based on the task requirements, load necessary specification files on demand and strictly follow specifications during development.

Specification index: specs/index.md

# Task Information

- ID: 5
- Slug: implement-auth
- Depends on: 3, 4
- Related to: 7
- Task file: .fa/tasks/5-03-25-implement-auth/task.md

## Fresh Run Instructions

This is a fresh run. Re-evaluate the entire task scope and requirements. Build upon what is correct while addressing any gaps
or issues. Do not simply apply incremental patches.

# Output Instructions

After completion, write your work summary to: .fa/tasks/5-03-25-implement-auth/memory-1.md
```

### 7.2 Fresh Run - Subtask

```
# Execution Guidelines

This is an unattended orchestration session. Never ask a human to perform follow-up actions. Operate autonomously end-to-end
unless blocked by missing requirements, secrets, or permissions. If blocked, record the blocker in the memory file.

Based on the task requirements, load necessary specification files on demand and strictly follow specifications during development.

Specification index: specs/index.md

# Parent Task

- ID: 2
- Slug: user-management-system
- Task file: .fa/tasks/2-03-25-user-management-system/task.md
- Memory files: 2 file(s) available
- Feedback files: 1 file(s) available

# Task Information

- ID: 3
- Slug: setup-database
- Task file: .fa/tasks/2-03-25-user-management-system/3-03-25-setup-database/task.md

## Fresh Run Instructions

This is a fresh run. Re-evaluate the entire task scope and requirements. Build upon what is correct while addressing any gaps
or issues. Do not simply apply incremental patches.

# Output Instructions

After completion, write your work summary to: .fa/tasks/2-03-25-user-management-system/3-03-25-setup-database/memory-1.md
```

### 7.3 Attempt Run - Second Attempt

```
# Execution Guidelines

This is an unattended orchestration session. Never ask a human to perform follow-up actions. Operate autonomously end-to-end
unless blocked by missing requirements, secrets, or permissions. If blocked, record the blocker in the memory file.

Based on the task requirements, load necessary specification files on demand and strictly follow specifications during development.

Specification index: specs/index.md

# Task Information

- ID: 5
- Slug: implement-auth
- Attempt: 2
- Task file: .fa/tasks/5-03-25-implement-auth/task.md

## Attempt Context

This is retry attempt #2 because the task is still in an active state. Resume from the current state instead of
restarting from scratch. Do not repeat already-completed investigation or validation.

### Previous Memory Files

Read previous work summaries:
- .fa/tasks/5-03-25-implement-auth/memory-1.md

### Feedback History

(None - this is your first retry)

### Latest Feedback

The most recent feedback that triggered this attempt:
- .fa/tasks/5-03-25-implement-auth/feedback-1.md

This attempt is because there is feedback indicating the task was not completed as expected. Pay extra attention to quality and
ensure complete delivery that satisfies user expectations.

# Output Instructions

After completion, write your work summary to: .fa/tasks/5-03-25-implement-auth/memory-2.md
```

### 7.4 Attempt Run - Third Attempt with History

```
# Execution Guidelines

This is an unattended orchestration session. Never ask a human to perform follow-up actions. Operate autonomously end-to-end
unless blocked by missing requirements, secrets, or permissions. If blocked, record the blocker in the memory file.

Based on the task requirements, load necessary specification files on demand and strictly follow specifications during development.

Specification index: specs/index.md

# Task Information

- ID: 5
- Slug: implement-auth
- Attempt: 3
- Task file: .fa/tasks/5-03-25-implement-auth/task.md

## Attempt Context

This is retry attempt #3 because the task is still in an active state. Resume from the current state instead of
restarting from scratch. Do not repeat already-completed investigation or validation.

### Previous Memory Files

Read previous work summaries:
- .fa/tasks/5-03-25-implement-auth/memory-1.md
- .fa/tasks/5-03-25-implement-auth/memory-2.md

### Feedback History

- .fa/tasks/5-03-25-implement-auth/feedback-1.md

### Latest Feedback

The most recent feedback that triggered this attempt:
- .fa/tasks/5-03-25-implement-auth/feedback-2.md

This attempt is because there is feedback indicating the task was not completed as expected. Pay extra attention to quality and
ensure complete delivery that satisfies user expectations.

# Output Instructions

After completion, write your work summary to: .fa/tasks/5-03-25-implement-auth/memory-3.md
```

---

## 8. Testing Checklist

## Attempt Context

This is retry attempt #3 because the task is still in an active state. 
Resume from the current state instead of restarting from scratch. 
Do not repeat already-completed investigation or validation.

### Previous Memory Files

Read previous work summaries:
- .fa/tasks/5-03-25-implement-auth/memory-1.md
- .fa/tasks/5-03-25-implement-auth/memory-2.md

### Feedback History

- .fa/tasks/5-03-25-implement-auth/feedback-1.md

### Latest Feedback

The most recent feedback that triggered this attempt:
- .fa/tasks/5-03-25-implement-auth/feedback-2.md

This attempt is because there is feedback indicating the task was not completed as expected. Pay extra attention to quality and
ensure complete delivery that satisfies user expectations.

# Output Instructions

After completion, write your work summary to: .fa/tasks/5-03-25-implement-auth/memory-3.md
```

---

## 8. Testing Checklist

- [ ] Fresh run for standalone task produces correct prompt
- [ ] Fresh run for subtask includes parent context
- [ ] Attempt run (first retry) shows correct feedback structure
- [ ] Attempt run (multiple retries) shows history and latest feedback
- [ ] Parent memory/feedback counts are accurate
- [ ] Memory output path is correctly inferred
- [ ] Template handles missing optional fields gracefully (depends_on, related_to)
