#!/usr/bin/env python3
"""
Research Agent with Context Handoff

This example shows how an AI research agent can:
1. Work on a research goal with milestones
2. Store findings in memory
3. Hand off context to another agent when expertise is needed
4. Track learning from research outcomes

Usage:
    python research_agent.py --topic "quantum computing applications"
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "sdk-python"))

from nexus_sdk import NexusAsync


async def run_research_agent(nexus: NexusAsync, topic: str):
    """Research agent that works on a topic and can hand off to specialists."""

    print(f"\n{'='*60}")
    print(f"RESEARCH AGENT")
    print(f"Topic: {topic}")
    print(f"{'='*60}\n")

    # Create a research goal
    goal = await nexus.goals.create(
        title=f"Research: {topic}",
        description=f"Conduct comprehensive research on {topic}",
        success_criteria="Produce a summary with key findings and recommendations",
        goal_type="research",
        tags=["research", "knowledge"],
        priority="high",
    )
    print(f"Created goal: {goal['id']}")

    # Add milestones
    milestones = [
        ("Literature Review", "Review existing knowledge and sources", 0.3),
        ("Analysis", "Analyze key findings and patterns", 0.3),
        ("Synthesis", "Synthesize findings into coherent summary", 0.4),
    ]

    for title, desc, weight in milestones:
        await nexus.goals.add_milestone(
            goal_id=goal["id"],
            title=title,
            description=desc,
            weight=weight,
        )
    print(f"Added {len(milestones)} milestones")

    # Start the goal
    await nexus.goals.start(goal["id"])

    # Reserve budget for the research
    try:
        budget_summary = await nexus.budgets.get_summary()
        if budget_summary.get("budgets"):
            budget = budget_summary["budgets"][0]
            reservation = await nexus.budgets.reserve(
                budget_id=budget["id"],
                amount=1000,
                purpose=f"Research on {topic}",
                goal_id=goal["id"],
            )
            print(f"Reserved budget: {reservation['amount']} units")
    except Exception as e:
        print(f"Budget reservation skipped: {e}")

    # Phase 1: Literature Review
    print("\n--- Phase 1: Literature Review ---")

    # Store findings in memory
    findings = [
        {
            "source": "Academic Paper 1",
            "key_point": f"Recent advances in {topic} show promising results",
            "relevance": "high",
        },
        {
            "source": "Industry Report",
            "key_point": f"Market adoption of {topic} growing at 25% annually",
            "relevance": "medium",
        },
        {
            "source": "Expert Interview",
            "key_point": f"Key challenges in {topic} include scalability and cost",
            "relevance": "high",
        },
    ]

    for i, finding in enumerate(findings):
        await nexus.memory.store(
            key=f"research-{topic}-finding-{i}",
            content=finding,
            metadata={"goal_id": goal["id"], "phase": "literature_review"},
            tags=["research", "finding", topic.replace(" ", "-")],
        )
        print(f"  Stored finding: {finding['source']}")

    # Record learning
    await nexus.learning.record_feedback(
        action_type="literature_review",
        feedback_type="success",
        action_description=f"Reviewed 3 sources on {topic}",
        output_data={"sources_reviewed": 3, "findings": len(findings)},
    )

    # Update progress
    await nexus.goals.update_progress(
        goal_id=goal["id"],
        progress_percent=30,
        progress_notes="Literature review complete, found 3 key sources",
    )

    # Phase 2: Need specialist help - Context Handoff
    print("\n--- Phase 2: Specialist Consultation ---")

    # Find a specialist agent
    specialists = await nexus.vitals.find_healthy(
        capability="domain_expert",
        max_load=0.7,
        limit=5,
    )

    if specialists:
        specialist = specialists[0]
        print(f"Found specialist: {specialist['agent_id']}")

        # Pack current context for handoff
        context_package = await nexus.context.pack(
            name=f"Research Context: {topic}",
            summary=f"Research in progress on {topic}, need domain expertise",
            goals={"current_goal": goal["id"], "phase": "analysis"},
            memories={"findings": findings},
            conversation_history=[
                {"role": "system", "content": f"Researching {topic}"},
                {"role": "assistant", "content": "Completed literature review with 3 key findings"},
            ],
            reasoning_trace=[
                "Started with broad literature search",
                "Identified 3 key sources",
                "Need domain expertise for deeper analysis",
            ],
            constraints={"deadline": "2 hours", "budget": "1000 units"},
            tags=["research", "handoff"],
            expires_in_hours=24,
        )
        print(f"Packed context: {context_package['id']}")

        # Transfer context to specialist
        transfer = await nexus.context.transfer(
            package_id=context_package["id"],
            receiver_id=specialist["agent_id"],
            purpose="Need domain expertise for research analysis",
            message="Please help analyze these findings with your domain expertise",
            related_goal_id=goal["id"],
        )
        print(f"Transferred context to specialist: {transfer['id']}")

        # Also delegate part of the goal
        delegation = await nexus.goals.delegate(
            goal_id=goal["id"],
            delegate_id=specialist["agent_id"],
            title=f"Expert analysis of {topic}",
            description="Provide domain expert analysis of the research findings",
            scope={"phase": "analysis", "findings": findings},
        )
        print(f"Delegated analysis: {delegation['id']}")

        # Add blocker while waiting
        blocker = await nexus.goals.add_blocker(
            goal_id=goal["id"],
            title="Waiting for specialist input",
            blocker_type="dependency",
            description="Need specialist analysis before synthesis",
            blocking_agent_id=specialist["agent_id"],
        )
        print(f"Added blocker: {blocker['id']}")

    else:
        print("No specialists available, continuing independently")

        # Update progress anyway
        await nexus.goals.update_progress(
            goal_id=goal["id"],
            progress_percent=60,
            progress_notes="Analysis complete (self-conducted)",
        )

    # Phase 3: Synthesis (simulated)
    print("\n--- Phase 3: Synthesis ---")

    # Retrieve our stored findings
    stored_findings = await nexus.memory.search(
        query=topic,
        tags=["research", "finding"],
        limit=10,
    )
    print(f"Retrieved {len(stored_findings)} stored findings")

    # Generate summary
    summary = {
        "topic": topic,
        "key_findings": [f["key_point"] for f in findings],
        "recommendations": [
            f"Invest in {topic} research and development",
            f"Address scalability challenges in {topic}",
            f"Monitor market trends in {topic}",
        ],
        "confidence": 0.85,
    }

    # Store final summary
    await nexus.memory.store(
        key=f"research-{topic}-summary",
        content=summary,
        metadata={"goal_id": goal["id"], "phase": "synthesis"},
        tags=["research", "summary", topic.replace(" ", "-")],
    )

    # Complete the goal
    await nexus.goals.complete(
        goal_id=goal["id"],
        outcome="Research completed successfully",
        outcome_data=summary,
    )
    print("Goal completed!")

    # Record final learning
    await nexus.learning.record_feedback(
        action_type="research",
        feedback_type="success",
        action_description=f"Completed research on {topic}",
        output_data={
            "findings_count": len(findings),
            "recommendations_count": len(summary["recommendations"]),
            "confidence": summary["confidence"],
        },
        confidence_score=summary["confidence"],
    )

    # Update vitals
    await nexus.vitals.update(
        is_online=True,
        is_busy=False,
        capabilities_status={"research": "available", "analysis": "available"},
    )

    print(f"\n{'='*60}")
    print("RESEARCH COMPLETE")
    print(f"{'='*60}")
    print(f"\nSummary stored with key: research-{topic}-summary")
    print(f"Goal ID: {goal['id']}")


async def main():
    parser = argparse.ArgumentParser(description="Research Agent")
    parser.add_argument("--topic", type=str, required=True, help="Research topic")
    parser.add_argument("--api-key", type=str, help="Nexus API key")
    parser.add_argument("--url", type=str, default="http://localhost:8000/api/v1", help="Nexus API URL")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("NEXUS_API_KEY")
    if not api_key:
        print("Registering new research agent...")
        nexus = await NexusAsync.register(
            slug=f"research-agent-{os.getpid()}",
            name="Research Agent",
            description="Agent that conducts research on topics",
            base_url=args.url,
        )
    else:
        nexus = NexusAsync(api_key=api_key, base_url=args.url)

    try:
        await run_research_agent(nexus, args.topic)
    finally:
        await nexus.close()


if __name__ == "__main__":
    asyncio.run(main())
