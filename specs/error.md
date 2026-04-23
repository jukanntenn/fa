# Error Handling

1. **Task not found**: Print error, exit code 1
2. **Policy not found**: Print error, exit code 1
3. **Tool execution failure**: Log error, mark task pending, continue to next task
4. **Template not found**: Log error, skip task
5. **Git operations in non-git directory**: Treat all files as in-scope
