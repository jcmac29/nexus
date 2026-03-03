"""Main CLI entry point."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from nexus_cli.config import load_config, save_config, clear_config, NexusConfig
from nexus_cli.client import NexusClient, NexusAPIError

console = Console()


def get_client() -> NexusClient:
    """Get configured Nexus client."""
    return NexusClient()


def handle_error(e: Exception):
    """Handle and display errors."""
    if isinstance(e, NexusAPIError):
        console.print(f"[red]Error ({e.status_code}):[/red] {e.detail}")
    else:
        console.print(f"[red]Error:[/red] {str(e)}")
    sys.exit(1)


@click.group()
@click.version_option()
def cli():
    """Nexus CLI - AI Agent Platform Command Line Interface"""
    pass


# --- Config Commands ---

@cli.group()
def config():
    """Manage CLI configuration."""
    pass


@config.command("set")
@click.option("--api-url", help="Nexus API URL")
@click.option("--api-key", help="Your API key")
def config_set(api_url: str | None, api_key: str | None):
    """Set configuration values."""
    current = load_config()

    if api_url:
        current.api_url = api_url
    if api_key:
        current.api_key = api_key

    save_config(current)
    console.print("[green]Configuration saved.[/green]")


@config.command("show")
def config_show():
    """Show current configuration."""
    current = load_config()

    table = Table(title="Nexus Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("API URL", current.api_url)
    table.add_row("API Key", f"{current.api_key[:20]}..." if current.api_key else "[dim]Not set[/dim]")
    table.add_row("Agent ID", current.agent_id or "[dim]Not set[/dim]")
    table.add_row("Agent Slug", current.agent_slug or "[dim]Not set[/dim]")

    console.print(table)


@config.command("clear")
def config_clear():
    """Clear saved configuration."""
    clear_config()
    console.print("[yellow]Configuration cleared.[/yellow]")


# --- Agent Commands ---

@cli.command()
@click.argument("name")
@click.argument("slug")
@click.option("--description", "-d", help="Agent description")
def register(name: str, slug: str, description: str | None):
    """Register a new agent."""
    try:
        client = NexusClient()
        result = client.register(name, slug, description)

        # Save to config
        current = load_config()
        current.api_key = result["api_key"]
        current.agent_id = result["agent"]["id"]
        current.agent_slug = result["agent"]["slug"]
        save_config(current)

        console.print(Panel.fit(
            f"[green]Agent registered successfully![/green]\n\n"
            f"[bold]Name:[/bold] {result['agent']['name']}\n"
            f"[bold]Slug:[/bold] {result['agent']['slug']}\n"
            f"[bold]ID:[/bold] {result['agent']['id']}\n\n"
            f"[bold yellow]API Key (save this!):[/bold yellow]\n"
            f"[cyan]{result['api_key']}[/cyan]",
            title="Registration Complete"
        ))

    except Exception as e:
        handle_error(e)


@cli.command()
def whoami():
    """Show current agent info."""
    try:
        client = get_client()
        result = client.whoami()

        console.print(Panel.fit(
            f"[bold]Name:[/bold] {result['name']}\n"
            f"[bold]Slug:[/bold] {result['slug']}\n"
            f"[bold]ID:[/bold] {result['id']}\n"
            f"[bold]Status:[/bold] {result['status']}\n"
            f"[bold]Description:[/bold] {result.get('description') or '[dim]None[/dim]'}",
            title="Current Agent"
        ))

    except Exception as e:
        handle_error(e)


# --- Discovery Commands ---

@cli.command()
@click.argument("query", required=False)
@click.option("--tags", "-t", help="Filter by tags (comma-separated)")
@click.option("--limit", "-l", default=20, help="Max results")
def search(query: str | None, tags: str | None, limit: int):
    """Search for capabilities."""
    try:
        client = get_client()
        tag_list = tags.split(",") if tags else None
        results = client.search(query=query, tags=tag_list, limit=limit)

        if not results:
            console.print("[yellow]No capabilities found.[/yellow]")
            return

        table = Table(title=f"Found {len(results)} Capabilities")
        table.add_column("Capability", style="cyan")
        table.add_column("Agent")
        table.add_column("Description")
        table.add_column("Tags")

        for cap in results:
            table.add_row(
                cap["name"],
                cap.get("agent_slug", "N/A"),
                (cap.get("description") or "")[:50],
                ", ".join(cap.get("tags") or []),
            )

        console.print(table)

    except Exception as e:
        handle_error(e)


@cli.command("capability")
@click.argument("name")
@click.argument("description")
@click.option("--tags", "-t", help="Tags (comma-separated)")
def register_capability(name: str, description: str, tags: str | None):
    """Register a capability."""
    try:
        client = get_client()
        tag_list = tags.split(",") if tags else None
        result = client.register_capability(
            name=name,
            description=description,
            tags=tag_list,
        )

        console.print(f"[green]Capability '{result['name']}' registered.[/green]")

    except Exception as e:
        handle_error(e)


@cli.command("capabilities")
def list_capabilities():
    """List my capabilities."""
    try:
        client = get_client()
        results = client.list_capabilities()

        if not results:
            console.print("[yellow]No capabilities registered.[/yellow]")
            return

        table = Table(title="My Capabilities")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Tags")
        table.add_column("Invocations", justify="right")

        for cap in results:
            table.add_row(
                cap["name"],
                (cap.get("description") or "")[:40],
                ", ".join(cap.get("tags") or []),
                str(cap.get("invocation_count", 0)),
            )

        console.print(table)

    except Exception as e:
        handle_error(e)


# --- Invocation Commands ---

@cli.command()
@click.argument("agent_slug")
@click.argument("capability")
@click.option("--input", "-i", "input_json", help="Input JSON data")
@click.option("--timeout", "-t", default=30, help="Timeout in seconds")
def invoke(agent_slug: str, capability: str, input_json: str | None, timeout: int):
    """Invoke a capability on another agent."""
    try:
        client = get_client()
        input_data = json.loads(input_json) if input_json else None

        console.print(f"Invoking [cyan]{capability}[/cyan] on [cyan]{agent_slug}[/cyan]...")

        result = client.invoke(
            agent_slug=agent_slug,
            capability=capability,
            input_data=input_data,
            timeout=timeout,
        )

        console.print(f"\n[bold]Invocation ID:[/bold] {result['id']}")
        console.print(f"[bold]Status:[/bold] {result['status']}")

        if result.get("output"):
            console.print("\n[bold]Output:[/bold]")
            rprint(result["output"])

        if result.get("error"):
            console.print(f"\n[red]Error:[/red] {result['error']}")

    except Exception as e:
        handle_error(e)


@cli.command()
def pending():
    """List pending invocations to handle."""
    try:
        client = get_client()
        results = client.pending()

        if not results:
            console.print("[dim]No pending invocations.[/dim]")
            return

        table = Table(title=f"{len(results)} Pending Invocations")
        table.add_column("ID", style="cyan")
        table.add_column("Capability")
        table.add_column("From")
        table.add_column("Created")

        for inv in results:
            table.add_row(
                inv["id"][:8],
                inv["capability"],
                inv.get("caller_agent_id", "Unknown")[:8],
                inv.get("created_at", "")[:19],
            )

        console.print(table)

    except Exception as e:
        handle_error(e)


@cli.command()
@click.argument("invocation_id")
@click.option("--output", "-o", help="Output JSON data")
@click.option("--error", "-e", help="Error message")
def complete(invocation_id: str, output: str | None, error: str | None):
    """Complete a pending invocation."""
    try:
        client = get_client()
        output_data = json.loads(output) if output else None

        result = client.complete(
            invocation_id=invocation_id,
            output=output_data,
            error=error,
        )

        console.print(f"[green]Invocation {invocation_id[:8]} completed.[/green]")

    except Exception as e:
        handle_error(e)


# --- Messaging Commands ---

@cli.command()
@click.argument("to_agent")
@click.argument("content")
@click.option("--subject", "-s", help="Message subject")
def send(to_agent: str, content: str, subject: str | None):
    """Send a message to another agent."""
    try:
        client = get_client()
        result = client.send_message(
            to_agent_slug=to_agent,
            content=content,
            subject=subject,
        )

        console.print(f"[green]Message sent to {to_agent}.[/green]")

    except Exception as e:
        handle_error(e)


@cli.command()
@click.option("--unread", is_flag=True, help="Show only unread messages")
def inbox(unread: bool):
    """View inbox messages."""
    try:
        client = get_client()
        results = client.inbox(unread_only=unread)

        if not results:
            console.print("[dim]No messages.[/dim]")
            return

        table = Table(title="Inbox")
        table.add_column("From", style="cyan")
        table.add_column("Subject")
        table.add_column("Preview")
        table.add_column("Date")
        table.add_column("Read")

        for msg in results:
            table.add_row(
                msg.get("from_agent_slug", "Unknown"),
                msg.get("subject") or "[dim]No subject[/dim]",
                (msg.get("content") or "")[:30],
                msg.get("created_at", "")[:10],
                "[green]Yes[/green]" if msg.get("read_at") else "[yellow]No[/yellow]",
            )

        console.print(table)

    except Exception as e:
        handle_error(e)


# --- Health Commands ---

@cli.command()
def heartbeat():
    """Send a heartbeat signal."""
    try:
        client = get_client()
        result = client.heartbeat()
        console.print(f"[green]Heartbeat sent.[/green] Status: {result.get('health_status', 'ok')}")

    except Exception as e:
        handle_error(e)


@cli.command()
def health():
    """Check health status."""
    try:
        client = get_client()
        result = client.health_status()

        status_color = {
            "healthy": "green",
            "degraded": "yellow",
            "unhealthy": "red",
            "unknown": "dim",
        }.get(result.get("status", "unknown"), "white")

        console.print(Panel.fit(
            f"[bold]Status:[/bold] [{status_color}]{result.get('status', 'unknown')}[/{status_color}]\n"
            f"[bold]Success Rate:[/bold] {result.get('success_rate', 0):.1f}%\n"
            f"[bold]Avg Response:[/bold] {result.get('avg_response_time_ms', 0):.0f}ms\n"
            f"[bold]Consecutive Failures:[/bold] {result.get('consecutive_failures', 0)}",
            title="Health Status"
        ))

    except Exception as e:
        handle_error(e)


if __name__ == "__main__":
    cli()
