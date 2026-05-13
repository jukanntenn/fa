#!/usr/bin/env python3
import json
import re
import subprocess
import sys


def extract_file_paths(tool_input):
    command = tool_input.get("command", "")
    if not command:
        return []
    return [
        m.group(1)
        for m in re.finditer(
            r"^\*\*\* (?:Update|Add) File: (.+)$", command, re.MULTILINE
        )
    ]


def main():
    try:
        hook_data = json.load(sys.stdin)
        file_paths = extract_file_paths(hook_data.get("tool_input", {}))
        python_files = [p for p in file_paths if p.endswith((".py", ".pyi"))]

        if not python_files:
            sys.exit(0)

        try:
            subprocess.run(
                ["ruff", "format"] + python_files,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            pass

        sys.exit(0)

    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
