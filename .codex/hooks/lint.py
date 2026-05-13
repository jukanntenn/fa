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
            print("Ruff check: No Python files in patch, skipping.")
            sys.exit(0)

        try:
            check_result = subprocess.run(
                [
                    "ruff",
                    "check",
                    "--fix",
                    "--select",
                    "F,E,W,I",
                    "--line-length",
                    "120",
                ]
                + python_files,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            print("Ruff not found. Please install ruff.", file=sys.stderr)
            sys.exit(0)

        if check_result.returncode == 0:
            if check_result.stdout:
                print(check_result.stdout, end="")
            if check_result.stderr:
                print(check_result.stderr, file=sys.stderr, end="")
            sys.exit(0)
        elif check_result.returncode == 1:
            if check_result.stdout:
                print(check_result.stdout, file=sys.stderr, end="")
            if check_result.stderr:
                print(check_result.stderr, file=sys.stderr, end="")
            sys.exit(2)
        else:
            if check_result.stdout:
                print(check_result.stdout, end="")
            if check_result.stderr:
                print(check_result.stderr, file=sys.stderr, end="")
            sys.exit(0)

    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
