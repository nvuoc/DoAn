"""Convenient Root CLI Entrypoint for ParrotGo / Vanuoc Conversation Core v3.0."""
from __future__ import annotations

import sys
from typing import Optional
import typer
from rich.console import Console

from src.conversation.adapters.cli.shell import app, CLISession
from tests.harness.runner import run_scenario
import json
from pathlib import Path

cli_app = typer.Typer(help="Vanuoc Conversation Core v3.0 - Command Line Interface")
console = Console()


@cli_app.command("repl")
def start_repl(
    db: str = typer.Option(":memory:", "--db", "-d", help="SQLite database path or :memory:"),
    auto_book: bool = typer.Option(True, "--auto-book/--no-auto-book", help="Allow text-only booking confirmation"),
) -> None:
    """Launch the interactive REPL conversation shell."""
    from src.conversation.adapters.cli.shell import repl
    repl(db=db, auto_book=auto_book)


@cli_app.command("send")
def send_message(
    message: str = typer.Argument(..., help="User message to send to the assistant"),
    db: str = typer.Option(":memory:", "--db", "-d", help="SQLite database path or :memory:"),
    auto_book: bool = typer.Option(True, "--auto-book/--no-auto-book", help="Allow text-only booking confirmation"),
) -> None:
    """Send a single message turn and inspect the response and state."""
    session = CLISession(db_path=db, auto_book=auto_book)
    console.print(f"[bold blue]User >[/bold blue] {message}")
    session.execute_user_input(message)
    session.display_state()


@cli_app.command("scenario")
def execute_scenario(
    scenario_id: str = typer.Argument(..., help="Scenario ID (e.g. SC_CONFIRM_THEN_EDIT or list)"),
) -> None:
    """Run an automated scenario from examples/scenarios.jsonl."""
    scenarios_file = Path(__file__).parent / "examples" / "scenarios.jsonl"
    lines = scenarios_file.read_text(encoding="utf-8").strip().splitlines()
    scenarios = [json.loads(l) for l in lines if l.strip()]

    if scenario_id.lower() in ("list", "all"):
        console.print("[bold cyan]Available Scenarios:[/bold cyan]")
        for s in scenarios:
            console.print(f" - [bold yellow]{s['scenario_id']}[/bold yellow]: {s['title']}")
        return

    target = next((s for s in scenarios if s["scenario_id"] == scenario_id), None)
    if not target:
        console.print(f"[bold red]Scenario '{scenario_id}' not found.[/bold red] Use 'python cli.py scenario list' to see all IDs.")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Running Scenario:[/bold cyan] {target['scenario_id']} - {target['title']}")
    res = run_scenario(target)
    if res.passed:
        console.print(f"[bold green]PASSED[/bold green] (Verified {len(target.get('oracle', {}).get('assertions', []))} oracle assertions)")
    else:
        console.print(f"[bold red]FAILED[/bold red]:")
        for f in res.failed_assertions:
            console.print(f"  - {f}")


@cli_app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    db: str = typer.Option(":memory:", "--db", "-d", help="SQLite database path or :memory:"),
    auto_book: bool = typer.Option(True, "--auto-book/--no-auto-book", help="Allow text-only booking confirmation"),
) -> None:
    """Default entrypoint: launches interactive REPL when invoked with no subcommand."""
    if ctx.invoked_subcommand is None:
        from src.conversation.adapters.cli.shell import repl
        repl(db=db, auto_book=auto_book)


if __name__ == "__main__":
    cli_app()
