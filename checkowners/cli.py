"""checkOwners CLI entry point."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from checkowners.analyze import analyze_ownership
from checkowners.config import load_config
from checkowners.drift import detect_drift
from checkowners.generate import generate_codeowners

app = typer.Typer(
    name="checkowners",
    help="Infer and maintain CODEOWNERS from git history.",
    rich_markup_mode="rich",
)

console = Console()

JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Output as JSON."),
]


def _not_implemented(command: str, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps({"command": command, "status": "not implemented"}))
    else:
        console.print(f"[yellow]{command}[/yellow] is not yet implemented.")
    raise typer.Exit(code=0)


@app.command()
def analyze(json_output: JsonOption = False) -> None:
    """Analyze git history to infer file ownership."""
    config = load_config()
    repo_root = Path.cwd()
    try:
        ownership = analyze_ownership(repo_root, config)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Git command failed:[/red] {exc}")
        raise typer.Exit(code=1) from None
    if json_output:
        data = {
            "inferred": {path: list(owners) for path, owners in ownership.owners.items()},
            "last_analyzed": ownership.last_analyzed.isoformat(),
        }
        typer.echo(json.dumps(data, indent=2))
    else:
        if not ownership.owners:
            console.print("[yellow]No ownership data inferred.[/yellow]")
            return
        from rich.table import Table

        table = Table(title="Inferred Ownership")
        table.add_column("Path", style="cyan")
        table.add_column("Owners", style="green")
        for path in sorted(ownership.owners):
            owners = ", ".join(ownership.owners[path])
            table.add_row(path, owners)
        console.print(table)


@app.command()
def generate(json_output: JsonOption = False) -> None:
    """Generate a CODEOWNERS file from inferred ownership."""
    config = load_config()
    repo_root = Path.cwd()
    try:
        ownership = analyze_ownership(repo_root, config)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Git command failed:[/red] {exc}")
        raise typer.Exit(code=1) from None
    content = generate_codeowners(repo_root, ownership, config)
    if json_output:
        data = {"path": ".github/CODEOWNERS", "content": content}
        typer.echo(json.dumps(data, indent=2))
    else:
        console.print("[green]Generated .github/CODEOWNERS[/green]")


@app.command(name="print")
def print_cmd(json_output: JsonOption = False) -> None:
    """Print inferred ownership to stdout."""
    _not_implemented("print", json_output=json_output)


@app.command()
def validate(json_output: JsonOption = False) -> None:
    """Validate CODEOWNERS file syntax."""
    _not_implemented("validate", json_output=json_output)


@app.command()
def drift(json_output: JsonOption = False) -> None:
    """Detect drift between inferred and current CODEOWNERS."""
    config = load_config()
    repo_root = Path.cwd()
    try:
        ownership = analyze_ownership(repo_root, config)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Git command failed:[/red] {exc}")
        raise typer.Exit(code=1) from None
    result = detect_drift(repo_root, ownership, config)
    if json_output:
        data = {
            "stale": list(result.stale),
            "missing": list(result.missing),
            "changed": list(result.changed),
            "drift_detected": result.drift_detected,
        }
        typer.echo(json.dumps(data, indent=2))
    else:
        if not result.drift_detected:
            console.print("[green]No drift detected.[/green]")
            return
        from rich.table import Table

        table = Table(title="CODEOWNERS Drift")
        table.add_column("Category", style="bold")
        table.add_column("Paths")
        if result.stale:
            table.add_row("[red]Stale[/red]", ", ".join(result.stale))
        if result.missing:
            table.add_row("[yellow]Missing[/yellow]", ", ".join(result.missing))
        if result.changed:
            table.add_row("[cyan]Changed[/cyan]", ", ".join(result.changed))
        console.print(table)


@app.command()
def notify(json_output: JsonOption = False) -> None:
    """Send webhook notification on drift events."""
    _not_implemented("notify", json_output=json_output)


@app.command()
def sync(json_output: JsonOption = False) -> None:
    """Sync CODEOWNERS with inferred ownership."""
    _not_implemented("sync", json_output=json_output)


def main() -> None:
    """Entry point for the checkowners CLI."""
    app()
