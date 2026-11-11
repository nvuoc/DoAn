"""Interactive CLI REPL for ParrotGo / Vanuoc Conversation Core v3.0."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import time
from typing import Optional
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import typer

from src.conversation.contract import (
    TurnInput,
    TurnResult,
    TurnStatus,
    BookingStatus,
    SourceEnvelope,
    TrustedEnvelope,
    Actor,
    ActorType,
    AuthorizedScope,
    InputTiming,
    InputTimingOverlap,
    InputTimingBasis,
    Channel,
    compute_input_hash,
)
from src.conversation.errors import ConversationCoreException
from src.conversation.service import ConversationService
from src.conversation.storage.db import get_connection, init_schema

app = typer.Typer(help="Vanuoc Conversation Core v3.0 CLI Shell")
console = Console()


class CLISession:
    def __init__(self, db_path: str = ":memory:", auto_book: bool = True):
        self.conn = get_connection(db_path)
        init_schema(self.conn)
        self.service = ConversationService(self.conn)
        if auto_book:
            self.service.policy["allow_text_only_auto_booking"] = True
        self.session_id = f"sess-{uuid.uuid4().hex[:8]}"
        self.request_id = f"req-{uuid.uuid4().hex[:8]}"
        self.draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        self.show_profile = False
        self.latest_result: Optional[TurnResult] = None
        self.turn_counter = 0

    def new_request(self) -> None:
        self.request_id = f"req-{uuid.uuid4().hex[:8]}"
        self.draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        self.latest_result = None
        self.turn_counter = 0
        console.print(f"[bold green]Started new request:[/bold green] {self.request_id}")

    def display_state(self) -> None:
        agg = self.service.coordinator.repo.load_aggregate(self.request_id)
        draft = agg.draft
        table = Table(title=f"Conversation State - Request {self.request_id}")
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        table.add_row("Request ID", agg.request_id)
        table.add_row("State Version", str(agg.state_version))
        table.add_row("Owner Generation", str(agg.owner_generation))
        table.add_row("Draft Status", draft.status.value)
        table.add_row("Booking Revision", str(draft.booking_revision))
        table.add_row("Origin", draft.origin.label if draft.origin else "None")
        table.add_row("Destination", draft.destination.label if draft.destination else "None")
        table.add_row("Vehicle Type", draft.vehicle_type or "None")
        table.add_row("Passengers", str(draft.passengers) if draft.passengers else "None")

        offered = agg.conversation_state.offered_question
        table.add_row("Offered Question", f"{offered.kind} ({offered.question_id})" if offered else "None")

        console.print(table)

    def display_history(self) -> None:
        agg = self.service.coordinator.repo.load_aggregate(self.request_id)
        history = agg.conversation_state.recent_delivered_history
        if not history:
            console.print("[dim]No delivered history recorded yet.[/dim]")
            return

        table = Table(title="Recent Delivered History")
        table.add_column("Role", style="cyan")
        table.add_column("Text", style="green")
        for item in history:
            table.add_row(item.get("role", "unknown"), item.get("text", ""))
        console.print(table)

    def display_trace(self) -> None:
        if not self.latest_result:
            console.print("[dim]No turn executed yet.[/dim]")
            return

        res = self.latest_result
        table = Table(title="Latest Turn Execution Trace")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row("Turn ID", res.turn_id)
        table.add_row("Status", res.status.value)
        table.add_row("State Version", str(res.state_version))
        table.add_row("Prepare Time", f"{res.timings.prepare_ms:.2f} ms")
        table.add_row("Commit Time", f"{res.timings.commit_ms:.2f} ms")
        table.add_row("Total Time", f"{res.timings.total_ms:.2f} ms")
        table.add_row("Outcome Kind", res.business_outcome.kind.value)
        table.add_row("Dispatch Status", res.business_outcome.dispatch_status.value)

        console.print(table)

    def export_state(self, filepath: str) -> None:
        agg = self.service.coordinator.repo.load_aggregate(self.request_id)
        out = {
            "request_id": agg.request_id,
            "state_version": agg.state_version,
            "draft": agg.draft.model_dump(mode="json"),
            "conversation_state": agg.conversation_state.model_dump(mode="json"),
        }
        Path(filepath).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[bold green]Exported state to:[/bold green] {filepath}")

    def execute_user_input(self, text: str) -> None:
        self.turn_counter += 1
        turn_id = str(uuid.uuid4())
        input_id = f"inp-{self.turn_counter}-{uuid.uuid4().hex[:6]}"

        raw_hash_data = {
            "schema_version": "3.0",
            "kind": "user_turn",
            "session_id": self.session_id,
            "request_id": self.request_id,
            "draft_id": self.draft_id,
            "turn_id": turn_id,
            "input_id": input_id,
            "source": {
                "channel": "cli",
                "adapter_id": "cli-adapter-01",
                "source_segment_ids": [],
            },
            "text": text,
        }
        inp_hash = compute_input_hash(raw_hash_data)

        # Get current state
        req_row = self.conn.execute(
            "SELECT state_version, owner_generation FROM core_requests WHERE request_id = ?",
            (self.request_id,),
        ).fetchone()
        st_ver = req_row["state_version"] if req_row else 0
        gen = req_row["owner_generation"] if req_row else 1

        turn_input = TurnInput(
            schema_version="3.0",
            kind="user_turn",
            session_id=self.session_id,
            request_id=self.request_id,
            draft_id=self.draft_id,
            turn_id=turn_id,
            input_id=input_id,
            received_at="2026-10-19T10:00:00+07:00",
            source=SourceEnvelope(channel=Channel.CLI, adapter_id="cli-adapter-01"),
            text=text,
            trusted=TrustedEnvelope(
                owner_generation=gen,
                turn_epoch=0,
                state_version=st_ver,
                booking_revision=0,
                deadline_at="2026-10-19T10:00:15+07:00",
                timezone="Asia/Ho_Chi_Minh",
                input_hash=inp_hash,
                actor=Actor(
                    actor_id="cli-user",
                    actor_type=ActorType.CUSTOMER,
                    authorized_scopes=[AuthorizedScope.CONVERSATION_WRITE],
                ),
                input_timing=InputTiming(
                    overlap=InputTimingOverlap.NO_OVERLAP,
                    basis=InputTimingBasis.TEXT_ADAPTER,
                ),
            ),
        )

        try:
            res = self.service.execute_turn(turn_input)
            self.latest_result = res

            # Render response panel
            resp_text = res.response.final_text if res.response else "(No response text)"
            console.print(Panel(resp_text, title="Assistant", border_style="green"))

            # Text delivery: presenting text to CLI screen fulfills delivery eligibility for offered question
            if res.response and res.response.question:
                from src.conversation.contract import (
                    ControlEvent,
                    ControlEventKind,
                    TrustedControlEnvelope,
                    DeliveryEventType,
                )
                try:
                    self.service.execute_delivery(
                        ControlEvent(
                            schema_version="3.0",
                            kind=ControlEventKind.DELIVERY,
                            session_id=self.session_id,
                            request_id=self.request_id,
                            input_id=f"ctrl-cli-{self.turn_counter}",
                            occurred_at="2026-10-19T10:00:01+07:00",
                            trusted=TrustedControlEnvelope(
                                owner_generation=gen,
                                actor=Actor(
                                    actor_id="cli-adapter",
                                    actor_type=ActorType.SYSTEM,
                                    authorized_scopes=[AuthorizedScope.DELIVERY_WRITE],
                                ),
                                adapter_id="cli-adapter-01",
                            ),
                            payload={
                                "event_type": DeliveryEventType.TEXT_PRESENTED.value,
                                "response_id": res.response.response_id,
                                "segment_id": res.response.segments[0].segment_id if res.response.segments else "seg-0",
                                "mode": "text",
                                "reporter": "client_adapter",
                            },
                        )
                    )
                except Exception:
                    pass

            if self.show_profile and res.timings:
                console.print(
                    f"[dim cyan]Timing: prepare {res.timings.prepare_ms:.1f}ms | "
                    f"commit {res.timings.commit_ms:.1f}ms | "
                    f"total {res.timings.total_ms:.1f}ms[/dim cyan]"
                )

        except ConversationCoreException as ex:
            console.print(f"[bold red]Core Error [{ex.code}]:[/bold red] {ex.message}")
        except Exception as ex:
            console.print(f"[bold red]System Error:[/bold red] {ex}")


@app.command()
def repl(
    db: str = typer.Option(":memory:", "--db", "-d", help="SQLite database path or :memory:"),
    auto_book: bool = typer.Option(True, "--auto-book/--no-auto-book", help="Allow text-only booking confirmation"),
) -> None:
    """Launch the interactive Vanuoc CLI REPL."""
    console.print(
        Panel(
            "[bold cyan]ParrotGo / Vanuoc Conversation Core v3.0 REPL[/bold cyan]\n"
            "Type your message to talk, or use slash commands like [bold yellow]/help[/bold yellow], "
            "[bold yellow]/state[/bold yellow], [bold yellow]/policy[/bold yellow], [bold yellow]/new[/bold yellow], [bold yellow]/exit[/bold yellow].",
            border_style="cyan",
        )
    )

    session = CLISession(db_path=db, auto_book=auto_book)

    while True:
        try:
            user_input = console.input("\n[bold blue]User > [/bold blue]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/dim]")
            break

        if not user_input:
            continue

        if user_input in ("/exit", "/quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input == "/help":
            table = Table(title="Available Slash Commands")
            table.add_column("Command", style="yellow")
            table.add_column("Description", style="white")
            table.add_row("/help", "Show this help screen")
            table.add_row("/state", "Inspect current Draft & Aggregate state")
            table.add_row("/policy", "Toggle allow_text_only_auto_booking policy")
            table.add_row("/history", "Show recent delivered dialogue history")
            table.add_row("/trace", "Show execution timings & status of latest turn")
            table.add_row("/new", "Start a brand-new conversation request")
            table.add_row("/reset", "Reset draft slots on current request")
            table.add_row("/profile", "Toggle latency profiling display")
            table.add_row("/export <path>", "Export current state to JSON file")
            table.add_row("/exit, /quit", "Exit the shell")
            console.print(table)
            continue

        if user_input == "/policy":
            cur = session.service.policy.get("allow_text_only_auto_booking", False)
            session.service.policy["allow_text_only_auto_booking"] = not cur
            new_st = "enabled (auto-recording allowed)" if not cur else "disabled (requires verified locations)"
            console.print(f"[bold cyan]Policy allow_text_only_auto_booking:[/bold cyan] {new_st}")
            continue

        if user_input == "/state":
            session.display_state()
            continue

        if user_input == "/history":
            session.display_history()
            continue

        if user_input == "/trace":
            session.display_trace()
            continue

        if user_input == "/new":
            session.new_request()
            continue

        if user_input == "/reset":
            session.new_request()
            continue

        if user_input == "/profile":
            session.show_profile = not session.show_profile
            status = "enabled" if session.show_profile else "disabled"
            console.print(f"[bold cyan]Profiling {status}.[/bold cyan]")
            continue

        if user_input.startswith("/export "):
            path = user_input.split(" ", 1)[1].strip()
            session.export_state(path)
            continue

        # Normal dialogue turn
        session.execute_user_input(user_input)


if __name__ == "__main__":
    app()
