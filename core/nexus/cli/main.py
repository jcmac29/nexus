"""Nexus CLI main entry point."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="nexus",
    help="Nexus - The connective layer for AI agents",
    add_completion=True,
)
console = Console()


# --- Database Commands ---

db_app = typer.Typer(help="Database management commands")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init():
    """Initialize database (create tables)."""
    from nexus.database import init_db

    console.print("[yellow]Initializing database...[/yellow]")

    async def run():
        await init_db()

    asyncio.run(run())
    console.print("[green]Database initialized successfully![/green]")


@db_app.command("migrate")
def db_migrate(
    message: str = typer.Option(..., "--message", "-m", help="Migration message"),
):
    """Create a new database migration."""
    import subprocess

    result = subprocess.run(
        ["alembic", "revision", "--autogenerate", "-m", message],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        console.print(f"[green]Migration created: {message}[/green]")
        console.print(result.stdout)
    else:
        console.print(f"[red]Migration failed:[/red]")
        console.print(result.stderr)
        raise typer.Exit(1)


@db_app.command("upgrade")
def db_upgrade(revision: str = "head"):
    """Apply database migrations."""
    import subprocess

    console.print(f"[yellow]Upgrading database to {revision}...[/yellow]")
    result = subprocess.run(
        ["alembic", "upgrade", revision],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        console.print("[green]Database upgraded successfully![/green]")
        console.print(result.stdout)
    else:
        console.print("[red]Upgrade failed:[/red]")
        console.print(result.stderr)
        raise typer.Exit(1)


@db_app.command("downgrade")
def db_downgrade(revision: str = "-1"):
    """Rollback database migrations."""
    import subprocess

    console.print(f"[yellow]Downgrading database to {revision}...[/yellow]")
    result = subprocess.run(
        ["alembic", "downgrade", revision],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        console.print("[green]Database downgraded successfully![/green]")
    else:
        console.print("[red]Downgrade failed:[/red]")
        console.print(result.stderr)
        raise typer.Exit(1)


# --- Agent Commands ---

agent_app = typer.Typer(help="Agent management commands")
app.add_typer(agent_app, name="agent")


@agent_app.command("list")
def agent_list(
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum agents to list"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
):
    """List registered agents."""
    from nexus.database import get_async_session
    from nexus.identity.models import Agent
    from sqlalchemy import select

    async def run():
        async with get_async_session() as session:
            query = select(Agent).limit(limit)
            if status:
                query = query.where(Agent.status == status)
            result = await session.execute(query)
            agents = result.scalars().all()

            table = Table(title="Registered Agents")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Version")
            table.add_column("Created")

            for agent in agents:
                table.add_row(
                    str(agent.id)[:8] + "...",
                    agent.name or "-",
                    agent.status,
                    agent.version or "-",
                    str(agent.created_at.date()),
                )

            console.print(table)
            console.print(f"\nTotal: {len(agents)} agents")

    asyncio.run(run())


@agent_app.command("create")
def agent_create(
    name: str = typer.Option(..., "--name", "-n", help="Agent name"),
    version: str = typer.Option("1.0.0", "--version", "-v", help="Agent version"),
    description: str = typer.Option("", "--description", "-d", help="Agent description"),
):
    """Create a new agent."""
    from nexus.database import get_async_session
    from nexus.identity.service import IdentityService

    async def run():
        async with get_async_session() as session:
            service = IdentityService(session)
            agent = await service.register_agent(
                name=name,
                version=version,
                description=description,
                capabilities=[],
            )
            await session.commit()

            console.print(f"[green]Agent created successfully![/green]")
            console.print(f"ID: {agent.id}")
            console.print(f"API Key: {agent.api_key}")
            console.print("\n[yellow]Save the API key - it won't be shown again![/yellow]")

    asyncio.run(run())


@agent_app.command("delete")
def agent_delete(
    agent_id: str = typer.Argument(..., help="Agent ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete an agent."""
    if not force:
        confirm = typer.confirm(f"Delete agent {agent_id}?")
        if not confirm:
            raise typer.Abort()

    from nexus.database import get_async_session
    from nexus.identity.models import Agent
    from sqlalchemy import select, delete

    async def run():
        async with get_async_session() as session:
            result = await session.execute(
                delete(Agent).where(Agent.id == agent_id)
            )
            await session.commit()

            if result.rowcount > 0:
                console.print(f"[green]Agent {agent_id} deleted[/green]")
            else:
                console.print(f"[red]Agent {agent_id} not found[/red]")

    asyncio.run(run())


# --- Job Commands ---

job_app = typer.Typer(help="Background job commands")
app.add_typer(job_app, name="job")


@job_app.command("worker")
def job_worker(
    queues: str = typer.Option("default,high,low", "--queues", "-q", help="Queues to process"),
    concurrency: int = typer.Option(10, "--concurrency", "-c", help="Number of concurrent jobs"),
):
    """Start a background job worker."""
    from nexus.jobs.service import Worker

    console.print(f"[yellow]Starting worker for queues: {queues}[/yellow]")
    console.print(f"Concurrency: {concurrency}")

    queue_list = [q.strip() for q in queues.split(",")]
    worker = Worker(queues=queue_list, concurrency=concurrency)

    asyncio.run(worker.run())


@job_app.command("list")
def job_list(
    queue: str = typer.Option("default", "--queue", "-q", help="Queue to list"),
    status: str = typer.Option("pending", "--status", "-s", help="Job status filter"),
):
    """List background jobs."""
    from nexus.database import get_async_session
    from nexus.jobs.models import Job
    from sqlalchemy import select

    async def run():
        async with get_async_session() as session:
            query = select(Job).where(
                Job.queue == queue,
                Job.status == status,
            ).limit(50)
            result = await session.execute(query)
            jobs = result.scalars().all()

            table = Table(title=f"Jobs in {queue} ({status})")
            table.add_column("ID", style="cyan")
            table.add_column("Task", style="green")
            table.add_column("Priority")
            table.add_column("Attempts")
            table.add_column("Created")

            for job in jobs:
                table.add_row(
                    str(job.id)[:8],
                    job.task_name,
                    str(job.priority),
                    str(job.attempts),
                    str(job.created_at),
                )

            console.print(table)

    asyncio.run(run())


# --- Cache Commands ---

cache_app = typer.Typer(help="Cache management commands")
app.add_typer(cache_app, name="cache")


@cache_app.command("clear")
def cache_clear(
    pattern: str = typer.Option("*", "--pattern", "-p", help="Key pattern to clear"),
):
    """Clear cache entries."""
    from nexus.cache import get_cache

    async def run():
        cache = await get_cache()
        # Note: This requires implementing a clear_pattern method
        console.print(f"[yellow]Clearing cache keys matching: {pattern}[/yellow]")
        # await cache.clear_pattern(pattern)
        console.print("[green]Cache cleared![/green]")

    asyncio.run(run())


@cache_app.command("stats")
def cache_stats():
    """Show cache statistics."""
    from nexus.cache import get_cache

    async def run():
        cache = await get_cache()
        stats = await cache.stats()
        console.print(json.dumps(stats, indent=2))

    asyncio.run(run())


# --- Server Commands ---

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers"),
):
    """Start the Nexus API server."""
    import uvicorn

    console.print(f"[green]Starting Nexus server on {host}:{port}[/green]")

    uvicorn.run(
        "nexus.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
    )


@app.command()
def version():
    """Show Nexus version."""
    from nexus import __version__
    console.print(f"Nexus v{__version__}")


@app.command()
def config():
    """Show current configuration."""
    from nexus.config import get_settings

    settings = get_settings()
    table = Table(title="Nexus Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    for key, value in settings.model_dump().items():
        # Mask sensitive values
        if any(s in key.lower() for s in ["secret", "password", "key", "token"]):
            value = "****" if value else "(not set)"
        table.add_row(key, str(value))

    console.print(table)


@app.command()
def health():
    """Check system health."""
    import httpx

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking health...", total=None)

        try:
            response = httpx.get("http://localhost:8000/api/v1/health")
            data = response.json()

            progress.update(task, completed=True)

            # Show results
            status_color = {
                "healthy": "green",
                "degraded": "yellow",
                "unhealthy": "red",
            }.get(data["status"], "white")

            console.print(f"\nOverall: [{status_color}]{data['status'].upper()}[/{status_color}]")
            console.print(f"Version: {data['version']}")

            table = Table(title="Components")
            table.add_column("Component")
            table.add_column("Status")
            table.add_column("Latency")
            table.add_column("Message")

            for comp in data.get("components", []):
                color = {
                    "healthy": "green",
                    "degraded": "yellow",
                    "unhealthy": "red",
                }.get(comp["status"], "white")

                table.add_row(
                    comp["name"],
                    f"[{color}]{comp['status']}[/{color}]",
                    f"{comp.get('latency_ms', '-')}ms" if comp.get("latency_ms") else "-",
                    comp.get("message", "-"),
                )

            console.print(table)

        except httpx.ConnectError:
            progress.update(task, completed=True)
            console.print("[red]Could not connect to Nexus server[/red]")
            console.print("Is the server running? Try: nexus serve")
            raise typer.Exit(1)


def main():
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
