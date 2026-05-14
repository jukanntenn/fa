#!/usr/bin/env python3
"""Stop hook for Codex that enforces file size budgets via entrix."""

import json
import subprocess
import sys


def main():
    try:
        hook_data = json.load(sys.stdin)

        if hook_data.get("stop_hook_active"):
            sys.exit(0)

        try:
            result = subprocess.run(
                [
                    "entrix",
                    "hook",
                    "file-length",
                    "--config",
                    "tools/entrix/file_budgets.json",
                    "--strict-limit",
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            sys.exit(0)

        if result.returncode != 1:
            sys.exit(0)

        files = []
        for line in result.stdout.splitlines():
            if line.startswith("current file length"):
                parts = line.split(": ", 1)
                if len(parts) == 2:
                    files.append(parts[1].split(" | ")[0].strip())

        if not files:
            sys.exit(0)

        file_list = " ".join(files)
        reason = (
            "File budget violations detected. The following files exceed their line budget:\n\n"
            + "\n".join(f"  - {f}" for f in files)
            + f"\n\nRun this command to get analysis:\n"
            f"  entrix analyze long-file --files {file_list} --strict-limit\n\n"
            "Review the analysis output, then refactor each file to bring it under the line budget. "
            "After refactoring, re-run to confirm:\n"
            "  entrix hook file-length --config tools/entrix/file_budgets.json --strict-limit\n\n"
            "Guidelines:\n"
            "- Refactor by logical organization: modularity, high cohesion, low coupling. "
            "Do NOT mechanically split files at arbitrary line boundaries.\n"
            "- If you are absolutely certain a file should be exempt from the budget, "
            "add it to the \"overrides\" array in tools/entrix/file_budgets.json with "
            "\"path\" and \"max_lines\" fields."
        )

        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
