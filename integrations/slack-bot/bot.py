"""
Nexus Slack Bot - AI-powered team assistant
Connects Slack to Nexus for shared context and AI capabilities.

Install:
    pip install slack-bolt aiohttp

Run:
    export SLACK_BOT_TOKEN=xoxb-your-token
    export SLACK_APP_TOKEN=xapp-your-token
    export NEXUS_URL=http://localhost:8000
    export NEXUS_API_KEY=your-nexus-key
    python bot.py
"""

import os
import asyncio
import aiohttp
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

# Configuration
NEXUS_URL = os.environ.get("NEXUS_URL", "http://localhost:8000")
NEXUS_API_KEY = os.environ.get("NEXUS_API_KEY", "")

app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))


class NexusClient:
    def __init__(self):
        self.base_url = NEXUS_URL
        self.headers = {
            "Authorization": f"Bearer {NEXUS_API_KEY}",
            "Content-Type": "application/json"
        }

    async def store_memory(self, key: str, value: dict, text: str, tags: list):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/memory",
                headers=self.headers,
                json={
                    "key": key,
                    "value": value,
                    "text_content": text,
                    "tags": tags,
                    "scope": "shared"
                }
            ) as resp:
                return await resp.json()

    async def search_memory(self, query: str, limit: int = 5):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/memory/search",
                headers=self.headers,
                json={"query": query, "limit": limit, "include_shared": True}
            ) as resp:
                return await resp.json()

    async def discover_agents(self, capability: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/discover/capabilities/{capability}",
                headers=self.headers
            ) as resp:
                data = await resp.json()
                return data.get("agents", [])

    async def invoke(self, agent_id: str, capability: str, input_data: dict):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/invoke/{agent_id}/{capability}",
                headers=self.headers,
                json={"input": input_data}
            ) as resp:
                return await resp.json()


nexus = NexusClient()


# Store important messages
@app.event("message")
async def handle_message(event, say):
    # Skip bot messages and thread replies
    if event.get("bot_id") or event.get("thread_ts"):
        return

    text = event.get("text", "")
    user = event.get("user", "unknown")
    channel = event.get("channel", "unknown")

    # Store messages that seem important (mentions, questions, decisions)
    if any(indicator in text.lower() for indicator in ["decided", "important", "remember", "fyi", "update:", "announcement"]):
        await nexus.store_memory(
            key=f"slack:{channel}:{event.get('ts', '')}",
            value={
                "user": user,
                "channel": channel,
                "text": text,
                "timestamp": event.get("ts")
            },
            text=f"Slack message from {user}: {text}",
            tags=["slack", "message", channel]
        )


# Search command
@app.command("/nexus-search")
async def search_command(ack, respond, command):
    await ack()

    query = command.get("text", "")
    if not query:
        await respond("Usage: /nexus-search <query>")
        return

    results = await nexus.search_memory(query)

    if not results.get("results"):
        await respond(f"No results found for: {query}")
        return

    blocks = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*Search results for:* {query}"}
    }]

    for r in results["results"][:5]:
        memory = r["memory"]
        score = r["score"]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{memory['key']}* (score: {score:.2f})\n>{', '.join(memory.get('tags', []))}"
            }
        })

    await respond({"blocks": blocks})


# Ask AI command
@app.command("/nexus-ask")
async def ask_command(ack, respond, command):
    await ack()

    question = command.get("text", "")
    if not question:
        await respond("Usage: /nexus-ask <question>")
        return

    await respond(f"Thinking about: {question}...")

    # Get context
    context = await nexus.search_memory(question, limit=3)
    context_text = "\n".join([
        f"- {r['memory']['key']}: {r['memory'].get('value', {})}"
        for r in context.get("results", [])
    ])

    # Find AI agent
    agents = await nexus.discover_agents("code-assist")
    if not agents:
        await respond("No AI agents available. Register an agent with 'code-assist' capability.")
        return

    # Invoke
    result = await nexus.invoke(
        agents[0]["id"],
        "code-assist",
        {"question": question, "context": context_text}
    )

    await respond(f"AI request submitted: `{result.get('invocation_id')}`\nCheck back for the response.")


# Remember command
@app.command("/nexus-remember")
async def remember_command(ack, respond, command):
    await ack()

    text = command.get("text", "")
    if not text:
        await respond("Usage: /nexus-remember <something to remember>")
        return

    user = command.get("user_id", "unknown")
    channel = command.get("channel_id", "unknown")

    result = await nexus.store_memory(
        key=f"slack:note:{channel}:{int(asyncio.get_event_loop().time())}",
        value={"note": text, "user": user, "channel": channel},
        text=f"Note from Slack: {text}",
        tags=["slack", "note", channel]
    )

    await respond(f"Remembered: {result.get('key', 'unknown')}")


# Team activity command
@app.command("/nexus-activity")
async def activity_command(ack, respond, command):
    await ack()

    results = await nexus.search_memory("recent updates changes activity", limit=10)

    if not results.get("results"):
        await respond("No recent activity found.")
        return

    blocks = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Recent Team Activity*"}
    }]

    for r in results["results"][:10]:
        memory = r["memory"]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"• *{memory['key']}*\n  _{', '.join(memory.get('tags', []))}_"
            }
        })

    await respond({"blocks": blocks})


# App mention - respond to @nexus mentions
@app.event("app_mention")
async def handle_mention(event, say):
    text = event.get("text", "")
    user = event.get("user", "")

    # Remove the bot mention from the text
    question = text.split(">", 1)[-1].strip() if ">" in text else text

    if not question:
        await say("How can I help? Ask me anything or use `/nexus-search` to search the knowledge base.")
        return

    # Search for context
    context = await nexus.search_memory(question, limit=3)

    if context.get("results"):
        response = f"<@{user}> Here's what I found:\n\n"
        for r in context["results"][:3]:
            response += f"• *{r['memory']['key']}* (relevance: {r['score']:.0%})\n"
        await say(response)
    else:
        # Try to get AI help
        agents = await nexus.discover_agents("code-assist")
        if agents:
            result = await nexus.invoke(agents[0]["id"], "code-assist", {"question": question})
            await say(f"<@{user}> I've asked an AI agent to help. Request ID: `{result.get('invocation_id')}`")
        else:
            await say(f"<@{user}> I couldn't find anything relevant. Try being more specific or add information with `/nexus-remember`.")


async def main():
    handler = AsyncSocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
