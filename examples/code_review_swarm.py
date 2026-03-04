#!/usr/bin/env python3
"""
Code Review Swarm Example

This example shows how to use Nexus Swarm to coordinate multiple
terminals for parallel code review. Open 4 terminals and run:

Terminal 1 (Leader):
    python code_review_swarm.py --leader --files src/

Terminal 2-4 (Workers):
    python code_review_swarm.py --join ABC123

The leader distributes files across workers, each reviews in parallel,
and results are aggregated at the end.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# In production, install with: pip install nexus-sdk
sys.path.insert(0, str(Path(__file__).parent.parent / "sdk-python"))

from nexus_sdk import NexusAsync


async def run_leader(nexus: NexusAsync, files_dir: str):
    """Leader: Create swarm, distribute files, aggregate results."""

    print("Creating swarm...")
    swarm = await nexus.swarm.create(
        name="Code Review Swarm",
        config={"max_members": 10, "task_timeout": 600},
    )

    join_code = swarm["join_code"]
    swarm_id = swarm["id"]

    print(f"\n{'='*50}")
    print(f"SWARM CREATED!")
    print(f"Join code: {join_code}")
    print(f"Share this code with workers to join")
    print(f"{'='*50}\n")

    # Wait for workers to join
    print("Waiting for workers to join (press Enter when ready to start)...")
    await asyncio.get_event_loop().run_in_executor(None, input)

    # Get current status
    status = await nexus.swarm.get(swarm_id)
    member_count = len([m for m in status.get("members", []) if m["status"] != "disconnected"])
    print(f"Swarm has {member_count} active members")

    # Find all files to review
    files = []
    for root, dirs, filenames in os.walk(files_dir):
        for filename in filenames:
            if filename.endswith((".py", ".js", ".ts", ".go", ".rs")):
                files.append(os.path.join(root, filename))

    print(f"Found {len(files)} files to review")

    # Submit tasks for each file
    tasks = []
    for filepath in files:
        task = await nexus.swarm.submit_task(
            swarm_id=swarm_id,
            title=f"Review {os.path.basename(filepath)}",
            description=f"Review the file at {filepath} for issues, improvements, and best practices",
            task_type="code_review",
            priority=5,
            input_data={"filepath": filepath},
            required_capabilities=["code_review"],
        )
        tasks.append(task)
        print(f"  Submitted: {os.path.basename(filepath)}")

    print(f"\nSubmitted {len(tasks)} review tasks")
    print("Workers are now processing...\n")

    # Poll for completion
    while True:
        await asyncio.sleep(5)
        status = await nexus.swarm.get(swarm_id)
        task_list = await nexus.swarm.list_tasks(swarm_id)

        completed = sum(1 for t in task_list if t["status"] == "completed")
        failed = sum(1 for t in task_list if t["status"] == "failed")
        pending = sum(1 for t in task_list if t["status"] in ["pending", "assigned", "in_progress"])

        print(f"Progress: {completed}/{len(tasks)} completed, {failed} failed, {pending} pending")

        if pending == 0:
            break

    # Get results
    print("\n" + "="*50)
    print("REVIEW COMPLETE - RESULTS")
    print("="*50 + "\n")

    results = await nexus.swarm.get_results(swarm_id)

    issues_found = 0
    for result in results:
        output = result.get("output_data", {})
        issues = output.get("issues", [])
        issues_found += len(issues)

        if issues:
            print(f"\n{result.get('title', 'Unknown file')}:")
            for issue in issues:
                print(f"  - {issue}")

    print(f"\n\nTotal issues found: {issues_found}")
    print("Review complete!")

    # Cleanup
    await nexus.swarm.disband(swarm_id)


async def run_worker(nexus: NexusAsync, join_code: str):
    """Worker: Join swarm, claim and complete tasks."""

    print(f"Joining swarm with code: {join_code}")

    membership = await nexus.swarm.join(
        join_code=join_code,
        capabilities=["code_review", "analysis"],
    )

    print(f"Joined swarm as worker!")
    print(f"Member ID: {membership['id']}")

    # Report vitals
    await nexus.vitals.update(
        is_online=True,
        is_busy=False,
        current_load=0.0,
        capabilities_status={"code_review": "available"},
    )

    tasks_completed = 0

    while True:
        # Claim next task
        task = await nexus.swarm.claim_task()

        if not task:
            print("No tasks available, waiting...")
            await asyncio.sleep(2)
            continue

        print(f"\nClaimed task: {task['title']}")

        # Update vitals
        await nexus.vitals.update(is_busy=True, current_tasks=1)

        # Simulate code review
        filepath = task.get("input_data", {}).get("filepath", "unknown")
        print(f"  Reviewing {filepath}...")

        # In a real agent, you would actually analyze the file
        # For this example, we simulate finding some issues
        issues = []

        try:
            with open(filepath, "r") as f:
                content = f.read()
                lines = content.split("\n")

                for i, line in enumerate(lines, 1):
                    # Simple heuristic checks
                    if "TODO" in line:
                        issues.append(f"Line {i}: TODO comment found")
                    if "FIXME" in line:
                        issues.append(f"Line {i}: FIXME comment found")
                    if len(line) > 120:
                        issues.append(f"Line {i}: Line exceeds 120 characters")
                    if "password" in line.lower() and "=" in line:
                        issues.append(f"Line {i}: Possible hardcoded password")
        except Exception as e:
            issues.append(f"Error reading file: {e}")

        # Complete the task
        await nexus.swarm.complete_task(
            task_id=task["id"],
            output_data={
                "filepath": filepath,
                "issues": issues,
                "lines_reviewed": len(lines) if "lines" in dir() else 0,
            },
        )

        tasks_completed += 1
        print(f"  Completed! Found {len(issues)} issues")

        # Update vitals
        await nexus.vitals.update(is_busy=False, current_tasks=0)

        # Record learning feedback
        await nexus.learning.record_feedback(
            action_type="code_review",
            feedback_type="success",
            action_description=f"Reviewed {filepath}",
            output_data={"issues_found": len(issues)},
        )


async def main():
    parser = argparse.ArgumentParser(description="Code Review Swarm")
    parser.add_argument("--leader", action="store_true", help="Run as swarm leader")
    parser.add_argument("--join", type=str, help="Join code for existing swarm")
    parser.add_argument("--files", type=str, default=".", help="Directory to review (leader only)")
    parser.add_argument("--api-key", type=str, help="Nexus API key")
    parser.add_argument("--url", type=str, default="http://localhost:8000/api/v1", help="Nexus API URL")

    args = parser.parse_args()

    if not args.leader and not args.join:
        parser.error("Must specify either --leader or --join CODE")

    api_key = args.api_key or os.environ.get("NEXUS_API_KEY")
    if not api_key:
        # Register new agent for demo
        print("No API key provided, registering new agent...")
        nexus = await NexusAsync.register(
            slug=f"review-agent-{os.getpid()}",
            name="Code Review Agent",
            description="Agent that reviews code for issues",
            base_url=args.url,
        )
    else:
        nexus = NexusAsync(api_key=api_key, base_url=args.url)

    try:
        if args.leader:
            await run_leader(nexus, args.files)
        else:
            await run_worker(nexus, args.join)
    finally:
        await nexus.close()


if __name__ == "__main__":
    asyncio.run(main())
