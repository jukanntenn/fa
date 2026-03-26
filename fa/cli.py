from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from fa.core.config import LOGS_DIR_NAME
from fa.core.logging import configure_logging
from fa.core.project import ensure_fa_structure, find_project_root
from fa.policy.commands import policy_app
from fa.task.commands import task_app

app = typer.Typer(help="Harness Engineering Tool")
app.add_typer(task_app, name="task")
app.add_typer(policy_app, name="policy")


@dataclass
class AppState:
    project_root: Path
    logger: object


root = find_project_root()
fa_dir = ensure_fa_structure(root)
app_state = AppState(
    project_root=root,
    logger=configure_logging(fa_dir / LOGS_DIR_NAME),
)


@app.command("init")
def init() -> None:
    ensure_fa_structure(app_state.project_root)
    typer.echo(f"Initialized {app_state.project_root / '.fa'}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
