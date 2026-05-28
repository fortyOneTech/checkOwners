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
from checkowners.balance import BalanceReport, analyze_balance
from checkowners.busfactor import BusFactorReport, classify, compute_bus_factor
from checkowners.config import find_codeowners_path, load_config
from checkowners.decay import DecayReport, detect_decay
from checkowners.drift import detect_drift
from checkowners.expertise import rank_expertise
from checkowners.generate import generate_codeowners
from checkowners.github import get_github_token, map_owners
from checkowners.graph import GraphExtraMissingError, build_graph, to_dot, to_text
from checkowners.models import (
    Config,
    DriftEntry,
    DriftResult,
    ExpertiseRank,
    OwnerEntry,
    OwnershipMap,
    PathOwnership,
)
from checkowners.notify import compute_severity, send_notification
from checkowners.onboard import OnboardingPath, generate_onboarding_path
from checkowners.state import load_ownership, write_state
from checkowners.topology import (
    TopologyReport,
    declared_teams_from_github,
    infer_topology,
)
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


def _load_or_analyze(config: Config, repo_root: Path) -> OwnershipMap:
    """Use cached state when available; otherwise re-analyze."""
    cached = load_ownership()
    if cached is not None:
        return cached
    return _run_analyze(config, repo_root)


def _expertise_rank_payload(rank: ExpertiseRank) -> dict[str, Any]:
    return {
        "handle": rank.handle,
        "confidence": round(rank.confidence, 4),
        "commits": rank.commits,
        "last_commit": rank.last_commit.isoformat() if rank.last_commit else None,
    }


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


def _decay_report_payload(report: DecayReport) -> dict[str, Any]:
    return {
        "handle": report.warning.handle,
        "path": report.warning.path,
        "days_since_last_commit": report.warning.days_since_last_commit,
        "last_commit": report.warning.last_commit.isoformat(),
        "historical_confidence": round(report.warning.historical_confidence, 4),
        "recommended_transfer": report.recommended_transfer,
        "departed": report.departed,
    }


@app.command()
def graph(
    export: Annotated[
        str | None,
        typer.Option(
            "--export",
            help="Export the graph in the given format (currently 'dot').",
            case_sensitive=False,
        ),
    ] = None,
) -> None:
    """Render the contributor-file knowledge graph in the terminal."""
    config = load_config()
    ownership = _load_or_analyze(config, Path.cwd())
    try:
        graph_obj = build_graph(ownership)
    except GraphExtraMissingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    if export is None:
        typer.echo(to_text(graph_obj))
        return
    fmt = export.strip().lower()
    if fmt == "dot":
        typer.echo(to_dot(graph_obj))
        return
    console.print(f"[red]Unsupported export format: {export!r}; supported: dot[/red]")
    raise typer.Exit(code=1)


@app.command()
def decay(json_output: JsonOption = False) -> None:
    """Detect contributors whose expertise on a path has gone stale."""
    config = load_config()
    ownership = _load_or_analyze(config, Path.cwd())
    reports = detect_decay(ownership, config)
    if json_output:
        typer.echo(
            json.dumps(
                {"reports": [_decay_report_payload(r) for r in reports]},
                indent=2,
            )
        )
        return
    if not reports:
        console.print("[green]No decaying expertise detected.[/green]")
        return
    table = Table(title="Expertise Decay")
    table.add_column("Path", style="cyan")
    table.add_column("Handle")
    table.add_column("Days", justify="right")
    table.add_column("Historical Δ", justify="right")
    table.add_column("Status")
    table.add_column("Recommended transfer")
    for report in reports:
        status = "[red]departed[/red]" if report.departed else "[yellow]dormant[/yellow]"
        target = report.recommended_transfer or "[dim]triage[/dim]"
        table.add_row(
            report.warning.path,
            report.warning.handle,
            str(report.warning.days_since_last_commit),
            f"{report.warning.historical_confidence:.2f}",
            status,
            target,
        )
    console.print(table)


@app.command(name="bus-factor")
def bus_factor(
    path: Annotated[
        str | None,
        typer.Argument(help="Path (or glob) to limit the report to."),
    ] = None,
    all_paths: Annotated[
        bool,
        typer.Option("--all", help="Report every path in the repo."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Calculate the bus factor for each path."""
    if path is None and not all_paths:
        console.print("[yellow]Specify a path or pass --all to report every path.[/yellow]")
        raise typer.Exit(code=1)
    config = load_config()
    ownership = _load_or_analyze(config, Path.cwd())
    target = path if path else None
    report = compute_bus_factor(ownership, config, target=target)
    if json_output:
        data = _bus_factor_payload(report, config)
        typer.echo(json.dumps(data, indent=2))
        return
    if not report.entries:
        console.print("[yellow]No paths matched.[/yellow]")
        return
    table = Table(title="Bus Factor")
    table.add_column("Path", style="cyan")
    table.add_column("BF", justify="right")
    table.add_column("Tier")
    table.add_column("Owners")
    table.add_column("Recommended backups")
    for entry in report.entries:
        tier = classify(entry.bus_factor, config.bus_factor)
        owners = ", ".join(entry.contributors_above_threshold) or "-"
        backups = ", ".join(entry.recommended_backups) or "-"
        tier_str = {
            "critical": "[red]CRITICAL[/red]",
            "warning": "[yellow]WARN[/yellow]",
            "ok": "[green]OK[/green]",
        }[tier]
        table.add_row(entry.path, str(entry.bus_factor), tier_str, owners, backups)
    console.print(table)
    console.print(f"[dim]repo average bus factor: {report.repo_average:.2f}[/dim]")


def _bus_factor_payload(report: BusFactorReport, config: Config) -> dict[str, Any]:
    return {
        "repo_average": report.repo_average,
        "entries": [
            {
                "path": entry.path,
                "bus_factor": entry.bus_factor,
                "tier": classify(entry.bus_factor, config.bus_factor),
                "contributors_above_threshold": list(entry.contributors_above_threshold),
                "recommended_backups": list(entry.recommended_backups),
            }
            for entry in report.entries
        ],
        "critical_paths": list(report.critical_paths),
    }


def _topology_payload(report: TopologyReport) -> dict[str, Any]:
    return {
        "clusters": [
            {
                "name": cluster.name,
                "members": list(cluster.members),
                "primary_paths": list(cluster.primary_paths),
                "declared": cluster.declared,
            }
            for cluster in report.clusters
        ],
        "mismatches": list(report.mismatches),
    }


def _balance_payload(report: BalanceReport) -> dict[str, Any]:
    return {
        "source": report.source,
        "average": report.average,
        "loads": [{"handle": load.handle, "reviews": load.reviews} for load in report.loads],
        "overloaded": [
            {"handle": load.handle, "reviews": load.reviews} for load in report.overloaded
        ],
        "suggestions": [
            {
                "overloaded": suggestion.overloaded,
                "candidate": suggestion.candidate,
                "confidence": round(suggestion.confidence, 4),
                "proposed_shift": suggestion.proposed_shift,
            }
            for suggestion in report.suggestions
        ],
    }


@app.command()
def balance(json_output: JsonOption = False) -> None:
    """Analyze PR review load distribution and suggest rebalancing."""
    config = load_config()
    ownership = _load_or_analyze(config, Path.cwd())
    report = analyze_balance(ownership, config)
    if json_output:
        typer.echo(json.dumps(_balance_payload(report), indent=2))
        return
    if not report.loads:
        console.print("[yellow]No review load data available.[/yellow]")
        return
    console.print(f"[dim]source: {report.source}; average reviews: {report.average:.1f}[/dim]")
    table = Table(title="Review Load")
    table.add_column("Handle", style="cyan")
    table.add_column("Reviews", justify="right")
    table.add_column("Status")
    overloaded_handles = {load.handle for load in report.overloaded}
    for load in report.loads:
        status = (
            "[red]overloaded[/red]" if load.handle in overloaded_handles else "[green]ok[/green]"
        )
        table.add_row(load.handle, str(load.reviews), status)
    console.print(table)
    if report.suggestions:
        console.print()
        console.print("[bold]Rebalance suggestions:[/bold]")
        for suggestion in report.suggestions:
            console.print(
                f"  - shift ~{suggestion.proposed_shift} reviews from {suggestion.overloaded}"
                f" to {suggestion.candidate} (confidence {suggestion.confidence:.2f})"
            )


@app.command()
def topology(json_output: JsonOption = False) -> None:
    """Infer team topology from commit co-occurrence patterns."""
    config = load_config()
    ownership = _load_or_analyze(config, Path.cwd())
    declared = declared_teams_from_github(config)
    report = infer_topology(ownership, config, declared_teams=declared)
    if json_output:
        typer.echo(json.dumps(_topology_payload(report), indent=2))
        return
    if not report.clusters:
        console.print("[yellow]No clusters inferred.[/yellow]")
        return
    table = Table(title="Inferred Team Topology")
    table.add_column("Cluster", style="cyan")
    table.add_column("Members")
    table.add_column("Primary paths")
    table.add_column("Source")
    for cluster in report.clusters:
        source = "[green]declared[/green]" if cluster.declared else "[yellow]inferred[/yellow]"
        table.add_row(
            cluster.name,
            ", ".join(cluster.members),
            ", ".join(cluster.primary_paths) or "-",
            source,
        )
    console.print(table)
    if report.mismatches:
        console.print()
        console.print("[bold]Mismatches:[/bold]")
        for line in report.mismatches:
            console.print(f"  - {line}")


def _onboarding_payload(report: OnboardingPath) -> dict[str, Any]:
    return {
        "target": report.target,
        "steps": [
            {
                "order": step.order,
                "path": step.path,
                "reviewer": step.reviewer,
                "complexity": step.complexity,
                "description": step.description,
            }
            for step in report.steps
        ],
    }


@app.command()
def onboard(
    path: Annotated[str, typer.Argument(help="Path or directory to onboard into.")],
    json_output: JsonOption = False,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", help="Emit a Markdown checklist."),
    ] = False,
) -> None:
    """Generate a structured onboarding path for a codebase area."""
    config = load_config()
    ownership = _load_or_analyze(config, Path.cwd())
    report = generate_onboarding_path(ownership, config, target=path)
    if json_output:
        typer.echo(json.dumps(_onboarding_payload(report), indent=2))
        return
    if markdown:
        typer.echo(report.to_markdown())
        return
    if not report.steps:
        console.print(f"[yellow]No onboarding path could be built for {path!r}.[/yellow]")
        return
    table = Table(title=f"Onboarding path: {path}")
    table.add_column("#", justify="right")
    table.add_column("Path", style="cyan")
    table.add_column("Reviewer")
    table.add_column("Complexity")
    table.add_column("Why")
    for step in report.steps:
        table.add_row(
            str(step.order),
            step.path,
            step.reviewer,
            step.complexity,
            step.description,
        )
    console.print(table)


@app.command()
def expertise(
    path: Annotated[str, typer.Argument(help="Path or glob to rank expertise for.")],
    json_output: JsonOption = False,
) -> None:
    """Show expertise ranking for a specific path."""
    config = load_config()
    ownership = _load_or_analyze(config, Path.cwd())
    ranking = rank_expertise(ownership, path)
    if json_output:
        data = {
            "path": path,
            "ranking": [_expertise_rank_payload(r) for r in ranking],
        }
        typer.echo(json.dumps(data, indent=2))
        return
    if not ranking:
        console.print(f"[yellow]No experts found for {path!r}.[/yellow]")
        return
    table = Table(title=f"Expertise: {path}")
    table.add_column("#", justify="right")
    table.add_column("Handle", style="cyan")
    table.add_column("Confidence", justify="right")
    table.add_column("Commits", justify="right")
    table.add_column("Last commit", justify="right")
    for idx, rank in enumerate(ranking, start=1):
        table.add_row(
            str(idx),
            f"[{_confidence_style(rank.confidence)}]{rank.handle}[/]",
            f"{rank.confidence:.2f}",
            str(rank.commits),
            _format_last_commit(rank.last_commit),
        )
    console.print(table)


def main() -> None:
    """Entry point for the checkowners CLI."""
    app()
