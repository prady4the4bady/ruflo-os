"""Ruflo CLI — Interact with the Ruflo Control Plane from the terminal."""

import json
import typer
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Ruflo OS AI Assistant CLI")
console = Console()

CONTROL_PLANE_URL = "http://localhost:9000/api/v1"

@app.command()
def do(goal: str, require_approval: bool = True):
    """Ask Ruflo to perform a task."""
    with console.status(f"[bold blue]Submitting task to Ruflo...[/bold blue]"):
        try:
            resp = httpx.post(
                f"{CONTROL_PLANE_URL}/tasks",
                json={"goal": goal, "requires_approval": require_approval},
                timeout=10.0
            )
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("task_id")
        except Exception as e:
            console.print(f"[bold red]Error connecting to Control Plane:[/bold red] {e}")
            raise typer.Exit(1)

    console.print(Panel(
        f"Task Submitted successfully!\n[bold]Task ID:[/bold] {task_id}\n\n"
        f"Run [cyan]ruflo status {task_id}[/cyan] to monitor progress.",
        title="Ruflo Task", border_style="green"
    ))


@app.command()
def status(task_id: str):
    """Check the status of a specific task."""
    try:
        resp = httpx.get(f"{CONTROL_PLANE_URL}/tasks/{task_id}", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        console.print(f"[bold red]Failed to fetch task status:[/bold red] {e}")
        raise typer.Exit(1)
        
    state = data.get("state", "UNKNOWN")
    color = "green" if state == "completed" else "yellow" if state == "running" else "red"
    
    table = Table(title=f"Task Status: {task_id}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style=color)
    
    table.add_row("Goal", data.get("goal", ""))
    table.add_row("State", state)
    
    console.print(table)


@app.command()
def approve(task_id: str, action_id: str):
    """Approve a pending action."""
    try:
        resp = httpx.post(
            f"{CONTROL_PLANE_URL}/tasks/{task_id}/approve",
            json={"action_id": action_id, "approved": True},
            timeout=5.0
        )
        resp.raise_for_status()
        console.print(f"[bold green]Action {action_id} approved![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to approve action:[/bold red] {e}")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
