"""Service for agent-to-agent messaging and invocations."""

from datetime import datetime, timezone
from uuid import UUID
from typing import Any

import httpx
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.messaging.models import Message, MessageStatus, Invocation, InvocationStatus
from nexus.identity.models import Agent
from nexus.discovery.models import Capability


class MessagingService:
    """Service for messaging between agents."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Messages ---

    async def send_message(
        self,
        from_agent_id: UUID,
        to_agent_id: UUID,
        content: dict[str, Any],
        subject: str | None = None,
        reply_to_id: UUID | None = None,
    ) -> Message:
        """Send a message from one agent to another."""
        # Verify target agent exists
        target = await self.db.execute(
            select(Agent).where(Agent.id == to_agent_id)
        )
        if not target.scalar_one_or_none():
            raise ValueError(f"Target agent {to_agent_id} not found")

        message = Message(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            subject=subject,
            content=content,
            reply_to_id=reply_to_id,
            status=MessageStatus.PENDING,
        )
        self.db.add(message)
        await self.db.flush()

        # Try to deliver via webhook if configured
        await self._try_deliver_message(message)

        return message

    async def get_messages(
        self,
        agent_id: UUID,
        inbox: bool = True,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        """Get messages for an agent."""
        if inbox:
            query = select(Message).where(Message.to_agent_id == agent_id)
        else:
            query = select(Message).where(Message.from_agent_id == agent_id)

        if unread_only:
            query = query.where(Message.status != MessageStatus.READ)

        # Count total
        count_query = select(Message.id).where(
            Message.to_agent_id == agent_id if inbox else Message.from_agent_id == agent_id
        )
        if unread_only:
            count_query = count_query.where(Message.status != MessageStatus.READ)
        count_result = await self.db.execute(count_query)
        total = len(count_result.all())

        # Get messages
        query = query.order_by(Message.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        messages = list(result.scalars().all())

        return messages, total

    async def mark_message_read(self, message_id: UUID, agent_id: UUID) -> Message | None:
        """Mark a message as read."""
        result = await self.db.execute(
            select(Message).where(
                Message.id == message_id,
                Message.to_agent_id == agent_id,
            )
        )
        message = result.scalar_one_or_none()
        if message:
            message.status = MessageStatus.READ
            message.read_at = datetime.now(timezone.utc)
        return message

    async def _try_deliver_message(self, message: Message) -> bool:
        """Try to deliver message via webhook."""
        # Get target agent's webhook URL
        result = await self.db.execute(
            select(Agent).where(Agent.id == message.to_agent_id)
        )
        agent = result.scalar_one_or_none()

        if not agent or not agent.metadata_.get("webhook_url"):
            return False

        webhook_url = agent.metadata_["webhook_url"]

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    webhook_url,
                    json={
                        "event": "message",
                        "data": {
                            "id": str(message.id),
                            "from_agent_id": str(message.from_agent_id),
                            "subject": message.subject,
                            "content": message.content,
                            "created_at": message.created_at.isoformat(),
                        }
                    }
                )
                if response.status_code < 300:
                    message.status = MessageStatus.DELIVERED
                    return True
        except Exception:
            pass

        return False

    # --- Invocations ---

    async def invoke_capability(
        self,
        caller_agent_id: UUID,
        target_agent_id: UUID,
        capability_name: str,
        input_data: dict[str, Any],
        timeout_seconds: int = 30,
        async_mode: bool = False,
    ) -> Invocation:
        """Invoke a capability on another agent."""
        # Find the capability
        result = await self.db.execute(
            select(Capability).where(
                Capability.agent_id == target_agent_id,
                Capability.name == capability_name,
                Capability.status == "active",
            )
        )
        capability = result.scalar_one_or_none()
        if not capability:
            raise ValueError(f"Capability '{capability_name}' not found on agent {target_agent_id}")

        # Create invocation
        invocation = Invocation(
            caller_agent_id=caller_agent_id,
            target_agent_id=target_agent_id,
            capability_id=capability.id,
            input_data=input_data,
            timeout_seconds=timeout_seconds,
            status=InvocationStatus.PENDING,
        )
        self.db.add(invocation)
        await self.db.flush()

        # If capability has an endpoint_url, call it directly
        if capability.endpoint_url and not async_mode:
            await self._execute_invocation(invocation, capability)
        elif not async_mode:
            # Try webhook delivery
            await self._try_webhook_invocation(invocation, capability)

        return invocation

    async def invoke_by_capability_id(
        self,
        caller_agent_id: UUID,
        capability_id: UUID,
        input_data: dict[str, Any],
        timeout_seconds: int = 30,
        async_mode: bool = False,
    ) -> Invocation:
        """Invoke a capability by its ID."""
        result = await self.db.execute(
            select(Capability).where(
                Capability.id == capability_id,
                Capability.status == "active",
            )
        )
        capability = result.scalar_one_or_none()
        if not capability:
            raise ValueError(f"Capability {capability_id} not found")

        return await self.invoke_capability(
            caller_agent_id=caller_agent_id,
            target_agent_id=capability.agent_id,
            capability_name=capability.name,
            input_data=input_data,
            timeout_seconds=timeout_seconds,
            async_mode=async_mode,
        )

    async def _execute_invocation(self, invocation: Invocation, capability: Capability) -> None:
        """Execute an invocation by calling the capability endpoint."""
        if not capability.endpoint_url:
            return

        invocation.status = InvocationStatus.PROCESSING
        invocation.started_at = datetime.now(timezone.utc)
        await self.db.flush()

        try:
            async with httpx.AsyncClient(timeout=invocation.timeout_seconds) as client:
                response = await client.post(
                    capability.endpoint_url,
                    json={
                        "invocation_id": str(invocation.id),
                        "caller_agent_id": str(invocation.caller_agent_id),
                        "capability": capability.name,
                        "input": invocation.input_data,
                    }
                )

                if response.status_code < 300:
                    invocation.output_data = response.json()
                    invocation.status = InvocationStatus.COMPLETED
                else:
                    invocation.error_message = f"HTTP {response.status_code}: {response.text}"
                    invocation.status = InvocationStatus.FAILED

        except httpx.TimeoutException:
            invocation.status = InvocationStatus.TIMEOUT
            invocation.error_message = "Request timed out"
        except Exception as e:
            invocation.status = InvocationStatus.FAILED
            invocation.error_message = str(e)

        invocation.completed_at = datetime.now(timezone.utc)

    async def _try_webhook_invocation(self, invocation: Invocation, capability: Capability) -> None:
        """Try to deliver invocation via agent webhook."""
        result = await self.db.execute(
            select(Agent).where(Agent.id == invocation.target_agent_id)
        )
        agent = result.scalar_one_or_none()

        if not agent or not agent.metadata_.get("webhook_url"):
            return

        webhook_url = agent.metadata_["webhook_url"]
        invocation.status = InvocationStatus.PROCESSING
        invocation.started_at = datetime.now(timezone.utc)
        await self.db.flush()

        try:
            async with httpx.AsyncClient(timeout=invocation.timeout_seconds) as client:
                response = await client.post(
                    webhook_url,
                    json={
                        "event": "invocation",
                        "data": {
                            "invocation_id": str(invocation.id),
                            "caller_agent_id": str(invocation.caller_agent_id),
                            "capability": capability.name,
                            "input": invocation.input_data,
                        }
                    }
                )

                if response.status_code < 300:
                    result_data = response.json()
                    if "output" in result_data:
                        invocation.output_data = result_data["output"]
                        invocation.status = InvocationStatus.COMPLETED
                    elif "error" in result_data:
                        invocation.error_message = result_data["error"]
                        invocation.status = InvocationStatus.FAILED
                    # Otherwise leave as PROCESSING for async completion
                else:
                    invocation.error_message = f"Webhook returned {response.status_code}"
                    invocation.status = InvocationStatus.FAILED

        except httpx.TimeoutException:
            invocation.status = InvocationStatus.TIMEOUT
            invocation.error_message = "Webhook request timed out"
        except Exception as e:
            invocation.status = InvocationStatus.FAILED
            invocation.error_message = str(e)

        if invocation.status in [InvocationStatus.COMPLETED, InvocationStatus.FAILED, InvocationStatus.TIMEOUT]:
            invocation.completed_at = datetime.now(timezone.utc)

    async def get_invocation(self, invocation_id: UUID) -> Invocation | None:
        """Get an invocation by ID."""
        result = await self.db.execute(
            select(Invocation).where(Invocation.id == invocation_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_invocations(self, agent_id: UUID) -> list[Invocation]:
        """Get pending invocations for an agent to process."""
        result = await self.db.execute(
            select(Invocation).where(
                Invocation.target_agent_id == agent_id,
                Invocation.status == InvocationStatus.PENDING,
            ).order_by(Invocation.created_at)
        )
        return list(result.scalars().all())

    async def complete_invocation(
        self,
        invocation_id: UUID,
        agent_id: UUID,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Invocation | None:
        """Complete an invocation with a result."""
        result = await self.db.execute(
            select(Invocation).where(
                Invocation.id == invocation_id,
                Invocation.target_agent_id == agent_id,
            )
        )
        invocation = result.scalar_one_or_none()

        if not invocation:
            return None

        if error:
            invocation.status = InvocationStatus.FAILED
            invocation.error_message = error
        else:
            invocation.status = InvocationStatus.COMPLETED
            invocation.output_data = output or {}

        invocation.completed_at = datetime.now(timezone.utc)
        return invocation

    async def get_invocations(
        self,
        agent_id: UUID,
        as_caller: bool = True,
        status: InvocationStatus | None = None,
        limit: int = 50,
    ) -> list[Invocation]:
        """Get invocations for an agent."""
        if as_caller:
            query = select(Invocation).where(Invocation.caller_agent_id == agent_id)
        else:
            query = select(Invocation).where(Invocation.target_agent_id == agent_id)

        if status:
            query = query.where(Invocation.status == status)

        query = query.order_by(Invocation.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # --- Webhook Configuration ---

    async def set_webhook(
        self,
        agent_id: UUID,
        endpoint_url: str,
        events: list[str] | None = None,
    ) -> None:
        """Set webhook configuration for an agent."""
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        metadata = dict(agent.metadata_)
        metadata["webhook_url"] = endpoint_url
        metadata["webhook_events"] = events or ["invocation", "message"]
        agent.metadata_ = metadata

    async def get_webhook(self, agent_id: UUID) -> dict[str, Any] | None:
        """Get webhook configuration for an agent."""
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return None

        webhook_url = agent.metadata_.get("webhook_url")
        if not webhook_url:
            return None

        return {
            "endpoint_url": webhook_url,
            "events": agent.metadata_.get("webhook_events", ["invocation", "message"]),
            "active": True,
        }

    async def remove_webhook(self, agent_id: UUID) -> None:
        """Remove webhook configuration for an agent."""
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent:
            metadata = dict(agent.metadata_)
            metadata.pop("webhook_url", None)
            metadata.pop("webhook_events", None)
            agent.metadata_ = metadata
