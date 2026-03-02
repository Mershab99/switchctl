#!/usr/bin/env python3
"""switchctl CLI - Manage Aruba S2500 switches from the command line."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.config_loader import load_config
from app.core.commands import generate_commands
from app.core.diff import diff_config
from app.drivers import get_driver

app = typer.Typer(name="switchctl", help="Aruba S2500 Switch Manager")
console = Console()

DEFAULT_CONFIG = "config/switch.yaml"


@app.command()
def status(
    mock: bool = typer.Option(False, "--mock", help="Use mock driver"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--file", "-f", help="Path to switch YAML config file"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show current switch status."""
    cfg = load_config(config)
    driver = get_driver(cfg.credentials, mock=mock)

    with driver:
        sw_status = driver.get_status()

    if output_json:
        console.print_json(sw_status.model_dump_json())
        return

    # Switch info table
    info_table = Table(title=f"Switch: {sw_status.hostname}", show_header=False)
    info_table.add_column("Property", style="cyan")
    info_table.add_column("Value")
    info_table.add_row("Model", sw_status.model)
    info_table.add_row("Version", sw_status.version)
    info_table.add_row("Uptime", sw_status.uptime)
    info_table.add_row("Serial", sw_status.serial)

    # Port summary
    ports_up = sum(1 for p in sw_status.ports.values() if p.oper_status == "up")
    ports_down = sum(
        1 for p in sw_status.ports.values()
        if p.oper_status == "down" and p.admin_status == "up"
    )
    ports_disabled = sum(1 for p in sw_status.ports.values() if p.admin_status == "down")
    poe_active = sum(1 for p in sw_status.ports.values() if p.poe_status == "delivering")

    info_table.add_row("Ports Up", f"[green]{ports_up}[/green]")
    info_table.add_row("Ports Down", f"[yellow]{ports_down}[/yellow]")
    info_table.add_row("Ports Disabled", f"[red]{ports_disabled}[/red]")
    info_table.add_row("PoE Active", f"[blue]{poe_active}[/blue]")
    info_table.add_row("VLANs", str(len(sw_status.vlans)))
    console.print(info_table)

    # Port detail table
    port_table = Table(title="Port Status")
    port_table.add_column("Port", style="cyan", width=6)
    port_table.add_column("Admin", width=8)
    port_table.add_column("Oper", width=8)
    port_table.add_column("Speed", width=8)
    port_table.add_column("Duplex", width=8)
    port_table.add_column("VLAN", width=8)
    port_table.add_column("PoE", width=12)
    port_table.add_column("Description")

    for port_id in sorted(sw_status.ports.keys(), key=lambda x: int(x)):
        p = sw_status.ports[port_id]
        admin_style = "green" if p.admin_status == "up" else "red"
        oper_style = "green" if p.oper_status == "up" else "dim"
        poe_str = p.poe_status
        if p.poe_status == "delivering":
            poe_str = f"[blue]{p.poe_power_mw / 1000:.1f}W[/blue]"
        elif p.poe_status == "disabled":
            poe_str = "[dim]off[/dim]"

        port_table.add_row(
            port_id,
            f"[{admin_style}]{p.admin_status}[/{admin_style}]",
            f"[{oper_style}]{p.oper_status}[/{oper_style}]",
            p.speed,
            p.duplex,
            p.vlan or "-",
            poe_str,
            p.description or "",
        )

    console.print(port_table)


@app.command()
def diff(
    mock: bool = typer.Option(False, "--mock", help="Use mock driver"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--file", "-f", help="Path to switch YAML config file"),
):
    """Show planned changes (desired vs current state)."""
    cfg = load_config(config)
    driver = get_driver(cfg.credentials, mock=mock)

    with driver:
        sw_status = driver.get_status()

    diffs = diff_config(cfg, sw_status)

    if not diffs:
        console.print("[green]No changes needed. Switch matches desired config.[/green]")
        return

    table = Table(title=f"Planned Changes ({len(diffs)} diffs)")
    table.add_column("Type", style="cyan", width=8)
    table.add_column("ID", width=8)
    table.add_column("Action", width=10)
    table.add_column("Field", width=16)
    table.add_column("Current", width=20)
    table.add_column("Desired", width=20)

    for d in diffs:
        action_style = {"create": "green", "update": "yellow", "delete": "red"}.get(
            d.action, "white"
        )
        table.add_row(
            d.resource_type,
            d.resource_id,
            f"[{action_style}]{d.action}[/{action_style}]",
            d.field,
            str(d.current_value) if d.current_value is not None else "-",
            str(d.desired_value) if d.desired_value is not None else "-",
        )

    console.print(table)

    # Show commands
    all_commands = generate_commands(diffs)
    if all_commands:
        console.print("\n[bold]Commands to execute:[/bold]")
        for cmd in all_commands:
            console.print(f"  [dim]{cmd}[/dim]")


@app.command()
def apply(
    mock: bool = typer.Option(False, "--mock", help="Use mock driver"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--file", "-f", help="Path to switch YAML config file"),
    save: bool = typer.Option(False, "--save", help="Save config after apply (write memory)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Apply configuration changes to the switch."""
    cfg = load_config(config)
    driver = get_driver(cfg.credentials, mock=mock)

    with driver:
        sw_status = driver.get_status()
        diffs = diff_config(cfg, sw_status)

        if not diffs:
            console.print("[green]No changes needed.[/green]")
            return

        console.print(f"[yellow]{len(diffs)} change(s) to apply.[/yellow]")
        all_commands = generate_commands(diffs)

        for cmd in all_commands:
            console.print(f"  {cmd}")

        if not yes:
            confirm = typer.confirm("\nApply these changes?")
            if not confirm:
                console.print("[red]Aborted.[/red]")
                raise typer.Exit(1)

        console.print("\n[bold]Applying...[/bold]")
        output = driver.send_commands(all_commands)
        console.print(output)

        if save:
            console.print("[bold]Saving config...[/bold]")
            driver.save_config()
            console.print("[green]Config saved.[/green]")

    console.print("[green]Done.[/green]")


@app.command()
def backup(
    mock: bool = typer.Option(False, "--mock", help="Use mock driver"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--file", "-f", help="Path to switch YAML config file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Backup running configuration from the switch."""
    cfg = load_config(config)
    driver = get_driver(cfg.credentials, mock=mock)

    with driver:
        running_config = driver.get_running_config()

    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = Path(f"backup_{cfg.name}_{timestamp}.txt")

    output.write_text(running_config)
    console.print(f"[green]Backup saved to {output}[/green]")


if __name__ == "__main__":
    app()
