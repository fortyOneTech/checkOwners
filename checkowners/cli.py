"""checkOwners CLI entry point."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from checkowners.analyze import analyze_ownership
from checkowners.config import find_codeowners_path, load_config
from checkowners.drift import detect_drift
from checkowners.generate import generate_codeowners
from checkowners.github import get_github_token, map_owners
from checkowners.models import (
    Config,
    DriftEntry,
    DriftResult,
    OwnerEntry,
    OwnershipMap,
    PathOwnership,
)
from checkowners.notify import compute_severity, send_notification
from checkowners.state import write_state
from checkowners.validate import validate_codeowners

app = typer.Typer(
    name="checkowners",
    help="Infer and maintain CODEOWNERS from git history.",
    rich_markup_mode="rich",
)

console = Console()

JsonOption = Annotated[bool, typer.Option("--json", help="Output as JSON.")]


def _resolve_github_owners(ownership: OwnershipMap, config: Config) -> OwnershipMap:
    """Replace email handles with GitHub @handles when a token is available."""
    if not config.github.resolve_handles:
        return ownership
    token = config.github.token or get_github_token()
    if not token:
        return ownership
    handle_map = ownership.handles_only()
    mapped = map_owners(handle_map, token)
    new_paths: dict[str, PathOwnership] = {}
    for path, po in ownership.paths.items():
        mapped_handles = mapped.get(path, tuple(o.handle for o in po.owners))
        rewritten = tuple(
            OwnerEntry(
                handle=mapped_handles[idx] if idx < len(mapped_handles) else owner.handle,
                confidence=owner.confidence,
                last_commit=owner.last_commit,
                commits=owner.commits,
                score_breakdown=owner.score_breakdown,
            )
            for idx, owner in enumerate(po.owners)
        )
        new_paths[path] = PathOwnership(
            owners=rewritten,
            bus_factor=po.bus_factor,
            decay_warnings=po.decay_warnings,
        )
    return OwnershipMap(paths=new_paths, last_analyzed=ownership.last_analyzed)


def _confidence_style(confidence: float) -> str:
    if confidence >= 0.7:
        return "green"
    if confidence >= 0.4:
        return "yellow"
    return "red"


def _format_last_commit(value: datetime | None) -> str:
    return value.date().isoformat() if value else "-"


def _owner_payload(owner: OwnerEntry) -> dict[str, Any]:
    return {
        "handle": owner.handle,
        "confidence": round(owner.confidence, 4),
        "commits": owner.commits,
        "last_commit": owner.last_commit.isoformat() if owner.last_commit else None,
    }


def _path_payload(po: PathOwnership) -> dict[str, Any]:
    return {
        "owners": [_owner_payload(o) for o in po.owners],
        "bus_factor": po.bus_factor,
        "decay_warnings": [
            {
                "handle": w.handle,
                "days_since_last_commit": w.days_since_last_commit,
                "last_commit": w.last_commit.isoformat(),
                "historical_confidence": round(w.historical_confidence, 4),
            }
            for w in po.decay_warnings
        ],
    }


def _drift_entry_payload(entry: DriftEntry) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": entry.path,
        "confidence_delta": round(entry.confidence_delta, 4),
        "reason": entry.reason,
    }
    if entry.bus_factor is not None:
        payload["bus_factor"] = entry.bus_factor
    if entry.decay:
        payload["decay"] = entry.decay
    return payload


def _render_ownership_table(ownership: OwnershipMap) -> None:
    if not ownership.paths:
        console.print("[yellow]No ownership data inferred.[/yellow]")
        return
    table = Table(title="Inferred Ownership")
    table.add_column("Path", style="cyan")
    table.add_column("Owners (confidence)", style="white")
    table.add_column("Bus", justify="right")
    table.add_column("Decay", justify="right")
    for path in sorted(ownership.paths):
        po = ownership.paths[path]
        owners_str = ", ".join(
            f"[{_confidence_style(o.confidence)}]{o.handle} ({o.confidence:.2f})[/]"
            for o in po.owners
        )
        bus = str(po.bus_factor)
        if po.bus_factor <= 1:
            bus = f"[red]{bus}[/red]"
        decay = str(len(po.decay_warnings)) if po.decay_warnings else "-"
        table.add_row(path, owners_str, bus, decay)
    console.print(table)


def _run_analyze(config: Config, repo_root: Path) -> OwnershipMap:
    try:
        ownership = analyze_ownership(repo_root, config)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Git command failed:[/red] {exc}")
        raise typer.Exit(code=1) from None
    ownership = _resolve_github_owners(ownership, config)
    write_state(ownership)
    return ownership


@app.command()
def analyze(json_output: JsonOption = False) -> None:
    """Analyze git history to infer confidence-scored ownership."""
    config = load_config()
    ownership = _run_analyze(config, Path.cwd())
    if json_output:
        data = {
            "inferred": {path: _path_payload(po) for path, po in ownership.paths.items()},
            "last_analyzed": ownership.last_analyzed.isoformat(),
        }
        typer.echo(json.dumps(data, indent=2))
    else:
        _render_ownership_table(ownership)


@app.command()
def generate(json_output: JsonOption = False) -> None:
    """Generate a CODEOWNERS file from inferred ownership."""
    config = load_config()
    repo_root = Path.cwd()
    codeowners_path = find_codeowners_path(repo_root)
    ownership = _run_analyze(config, repo_root)
    token = config.github.token or get_github_token()
    content = generate_codeowners(
        repo_root,
        ownership,
        config,
        codeowners_path=codeowners_path,
        token=token,
        org=config.github.org,
    )
    rel_path = codeowners_path.relative_to(repo_root)
    if json_output:
        typer.echo(json.dumps({"path": str(rel_path), "content": content}, indent=2))
    else:
        console.print(f"[green]Generated {rel_path}[/green]")


@app.command(name="print")
def print_cmd(json_output: JsonOption = False) -> None:
    """Print inferred ownership to stdout."""
    config = load_config()
    ownership = _run_analyze(config, Path.cwd())
    if json_output:
        data = {path: _path_payload(po) for path, po in sorted(ownership.paths.items())}
        typer.echo(json.dumps(data, indent=2))
    else:
        for path in sorted(ownership.paths):
            owners = " ".join(
                f"{o.handle}({o.confidence:.2f})" for o in ownership.paths[path].owners
            )
            typer.echo(f"{path}\t{owners}")


@app.command()
def validate(json_output: JsonOption = False) -> None:
    """Validate CODEOWNERS file syntax."""
    repo_root = Path.cwd()
    codeowners_path = find_codeowners_path(repo_root)
    errors = validate_codeowners(repo_root, codeowners_path=codeowners_path)
    if json_output:
        data = {
            "valid": len(errors) == 0,
            "errors": [{"line": e.line_number, "message": e.message} for e in errors],
        }
        typer.echo(json.dumps(data, indent=2))
        return
    if not errors:
        console.print("[green]CODEOWNERS is valid.[/green]")
    else:
        for err in errors:
            console.print(f"[red]Line {err.line_number}:[/red] {err.message}")
        raise typer.Exit(code=1)


def _render_drift_table(result: DriftResult) -> None:
    table = Table(title="CODEOWNERS Drift")
    table.add_column("Category", style="bold")
    table.add_column("Path", style="cyan")
    table.add_column("Δ", justify="right")
    table.add_column("Reason")
    for entry in result.stale:
        table.add_row("[red]stale[/red]", entry.path, f"{entry.confidence_delta:.2f}", entry.reason)
    for entry in result.missing:
        bf_low = entry.bus_factor is not None and entry.bus_factor <= 1
        flag = " [red](bf=1)[/red]" if bf_low else ""
        decay = " [magenta](decay)[/magenta]" if entry.decay else ""
        table.add_row(
            "[yellow]missing[/yellow]",
            entry.path,
            f"{entry.confidence_delta:.2f}",
            entry.reason + flag + decay,
        )
    for entry in result.changed:
        table.add_row(
            "[cyan]changed[/cyan]",
            entry.path,
            f"{entry.confidence_delta:.2f}",
            entry.reason,
        )
    console.print(table)


@app.command()
def drift(json_output: JsonOption = False) -> None:
    """Detect drift between inferred and current CODEOWNERS."""
    config = load_config()
    repo_root = Path.cwd()
    codeowners_path = find_codeowners_path(repo_root)
    ownership = _run_analyze(config, repo_root)
    result = detect_drift(repo_root, ownership, config, codeowners_path=codeowners_path)
    severity = compute_severity(result)
    if json_output:
        data = {
            "stale": [_drift_entry_payload(e) for e in result.stale],
            "missing": [_drift_entry_payload(e) for e in result.missing],
            "changed": [_drift_entry_payload(e) for e in result.changed],
            "drift_detected": result.drift_detected,
            "severity": severity,
            "max_confidence_delta": round(result.max_confidence_delta, 4),
        }
        typer.echo(json.dumps(data, indent=2))
        return
    if not result.drift_detected:
        console.print("[green]No drift detected.[/green]")
        return
    console.print(
        f"[bold]severity:[/bold] [{_severity_style(severity)}]{severity.upper()}[/] "
        f"(Δmax={result.max_confidence_delta:.2f})"
    )
    _render_drift_table(result)


def _severity_style(severity: str) -> str:
    return {"critical": "red", "high": "red", "medium": "yellow", "low": "green"}[severity]


@app.command()
def notify(json_output: JsonOption = False) -> None:
    """Send webhook notification on drift events."""
    config = load_config()
    repo_root = Path.cwd()
    codeowners_path = find_codeowners_path(repo_root)
    ownership = _run_analyze(config, repo_root)
    result = detect_drift(repo_root, ownership, config, codeowners_path=codeowners_path)
    sent = send_notification(result, config)
    severity = compute_severity(result)
    if json_output:
        data = {
            "sent": sent,
            "drift_detected": result.drift_detected,
            "severity": severity,
        }
        typer.echo(json.dumps(data, indent=2))
        return
    if sent:
        console.print(f"[green]Notification sent ({severity}).[/green]")
    elif not config.notifications.webhook_url:
        console.print("[yellow]No webhook URL configured; skipped.[/yellow]")
    else:
        console.print(
            f"[yellow]Severity {severity} below threshold "
            f"{config.notifications.severity_threshold}; skipped.[/yellow]"
        )


@app.command()
def sync(json_output: JsonOption = False) -> None:
    """Sync CODEOWNERS with inferred ownership (generate + commit)."""
    config = load_config()
    repo_root = Path.cwd()
    codeowners_path = find_codeowners_path(repo_root)
    ownership = _run_analyze(config, repo_root)
    token = config.github.token or get_github_token()
    content = generate_codeowners(
        repo_root,
        ownership,
        config,
        codeowners_path=codeowners_path,
        token=token,
        org=config.github.org,
    )
    rel_path = codeowners_path.relative_to(repo_root)
    try:
        subprocess.run(
            ["git", "add", str(rel_path)],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "chore: sync CODEOWNERS via checkowners"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Git commit failed:[/red] {exc.stderr.strip()}")
        raise typer.Exit(code=1) from None
    if json_output:
        data = {"path": str(rel_path), "committed": True, "content": content}
        typer.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Generated and committed {rel_path}[/green]")


def main() -> None:
    """Entry point for the checkowners CLI."""
    app()
