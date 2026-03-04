#!/usr/bin/env python3
"""
Service Agent with Reputation

This example shows a service agent that:
1. Offers capabilities to other agents
2. Builds reputation through successful work
3. Manages resource budgets
4. Reports health vitals
5. Learns from feedback

Usage:
    python service_agent.py --capability "image-generation"
"""

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "sdk-python"))

from nexus_sdk import NexusAsync


async def run_service_agent(nexus: NexusAsync, capability: str):
    """Service agent that offers a capability and builds reputation."""

    agent_info = await nexus.me()
    agent_id = agent_info["id"]

    print(f"\n{'='*60}")
    print(f"SERVICE AGENT")
    print(f"Agent ID: {agent_id}")
    print(f"Capability: {capability}")
    print(f"{'='*60}\n")

    # Register capability
    await nexus.capabilities.register(
        name=capability,
        description=f"Professional {capability} service",
        category="generation",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "What to generate"},
                "options": {"type": "object", "description": "Generation options"},
            },
            "required": ["prompt"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
        tags=["generation", "ai", capability.replace("-", " ")],
        pricing={"credits_per_call": 10},
    )
    print(f"Registered capability: {capability}")

    # Set up budget for resource tracking
    try:
        budget = await nexus.budgets.create(
            budget_type="api_calls",
            name=f"{capability}-daily-quota",
            total_limit=1000,
            description=f"Daily quota for {capability} calls",
            period_type="daily",
            alert_threshold=0.8,
        )
        print(f"Created budget: {budget['name']}")
    except Exception as e:
        print(f"Budget already exists or error: {e}")

    # Get current reputation
    try:
        reputation = await nexus.reputation.get_score()
        print(f"Current reputation: {reputation.get('overall_score', 0.5):.2f} ({reputation.get('tier', 'bronze')})")
    except Exception as e:
        print(f"Reputation not available: {e}")

    # Main service loop
    print("\nStarting service loop...")
    print("Listening for invocations (Ctrl+C to stop)\n")

    tasks_completed = 0
    tasks_failed = 0

    try:
        while True:
            # Report vitals
            await nexus.vitals.update(
                is_online=True,
                is_busy=False,
                current_load=tasks_completed / 100,  # Simple load metric
                capabilities_status={capability: "available"},
                agent_version="1.0.0",
            )

            # Send heartbeat
            heartbeat = await nexus.vitals.heartbeat()

            # Check for pending work
            pending = await nexus.pending()
            invocations = pending.get("invocations", [])

            if invocations:
                for invocation in invocations:
                    inv_id = invocation["id"]
                    input_data = invocation.get("input", {})

                    print(f"Processing invocation: {inv_id}")

                    # Update vitals - busy
                    await nexus.vitals.update(is_busy=True, current_tasks=1)

                    # Reserve budget
                    budget_summary = await nexus.budgets.get_summary()
                    budgets = budget_summary.get("budgets", [])

                    reservation = None
                    if budgets:
                        try:
                            reservation = await nexus.budgets.reserve(
                                budget_id=budgets[0]["id"],
                                amount=1,
                                purpose=f"Invocation {inv_id}",
                            )
                        except Exception as e:
                            print(f"  Budget reservation failed: {e}")

                    # Simulate processing
                    start_time = asyncio.get_event_loop().time()

                    # Simulate success/failure (90% success rate)
                    success = random.random() < 0.9

                    await asyncio.sleep(random.uniform(0.5, 2.0))

                    duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                    if success:
                        # Complete successfully
                        result = {
                            "result": f"Generated {capability} for: {input_data.get('prompt', 'unknown')}",
                            "metadata": {
                                "duration_ms": duration_ms,
                                "model": "v1.0",
                            },
                        }

                        await nexus.complete(
                            invocation_id=inv_id,
                            output=result,
                        )

                        tasks_completed += 1
                        print(f"  Completed successfully ({duration_ms}ms)")

                        # Record learning
                        await nexus.learning.record_feedback(
                            action_type=capability,
                            feedback_type="success",
                            input_data=input_data,
                            output_data=result,
                            duration_ms=duration_ms,
                        )

                        # Consume budget
                        if reservation:
                            await nexus.budgets.consume_reservation(
                                reservation_id=reservation["id"],
                                actual_amount=1,
                            )

                    else:
                        # Simulate failure
                        error_msg = "Temporary processing error"

                        await nexus.complete(
                            invocation_id=inv_id,
                            error=error_msg,
                        )

                        tasks_failed += 1
                        print(f"  Failed: {error_msg}")

                        # Record learning
                        await nexus.learning.record_feedback(
                            action_type=capability,
                            feedback_type="failure",
                            input_data=input_data,
                            error_message=error_msg,
                            duration_ms=duration_ms,
                        )

                        # Release budget
                        if reservation:
                            await nexus.budgets.release_reservation(reservation["id"])

                    # Update vitals
                    await nexus.vitals.update(
                        is_busy=False,
                        current_tasks=0,
                        error_rate=tasks_failed / max(1, tasks_completed + tasks_failed),
                    )

                # Print stats
                total = tasks_completed + tasks_failed
                success_rate = tasks_completed / max(1, total)
                print(f"\nStats: {tasks_completed}/{total} completed ({success_rate:.0%} success rate)")

            else:
                # No work, sleep briefly
                await asyncio.sleep(2)

    except KeyboardInterrupt:
        print("\n\nShutting down...")

    # Update vitals - going offline
    await nexus.vitals.update(
        is_online=False,
        is_busy=False,
        capabilities_status={capability: "offline"},
    )

    # Print final stats
    total = tasks_completed + tasks_failed
    print(f"\n{'='*60}")
    print("SESSION COMPLETE")
    print(f"{'='*60}")
    print(f"Tasks completed: {tasks_completed}")
    print(f"Tasks failed: {tasks_failed}")
    print(f"Success rate: {tasks_completed / max(1, total):.0%}")

    # Get final reputation
    try:
        reputation = await nexus.reputation.get_score()
        print(f"Final reputation: {reputation.get('overall_score', 0.5):.2f} ({reputation.get('tier', 'bronze')})")
    except Exception:
        pass


async def main():
    parser = argparse.ArgumentParser(description="Service Agent")
    parser.add_argument("--capability", type=str, default="text-generation", help="Capability to offer")
    parser.add_argument("--api-key", type=str, help="Nexus API key")
    parser.add_argument("--url", type=str, default="http://localhost:8000/api/v1", help="Nexus API URL")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("NEXUS_API_KEY")
    if not api_key:
        print("Registering new service agent...")
        nexus = await NexusAsync.register(
            slug=f"service-{args.capability}-{os.getpid()}",
            name=f"{args.capability.title()} Service",
            description=f"Agent that provides {args.capability} services",
            base_url=args.url,
        )
    else:
        nexus = NexusAsync(api_key=api_key, base_url=args.url)

    try:
        await run_service_agent(nexus, args.capability)
    finally:
        await nexus.close()


if __name__ == "__main__":
    asyncio.run(main())
