"""SMS service for text messaging."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.sms.models import SMSMessage, SMSConversation, SMSStatus, SMSDirection


class SMSService:
    """Service for SMS operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._providers = {}

    def configure_twilio(self, account_sid: str, auth_token: str):
        """Configure Twilio for SMS."""
        from twilio.rest import Client
        self._providers["twilio"] = Client(account_sid, auth_token)

    async def send_sms(
        self,
        from_number: str,
        to_number: str,
        body: str,
        sender_id: UUID | None = None,
        sender_type: str = "agent",
        media_urls: list[str] | None = None,
    ) -> SMSMessage:
        """Send an SMS message."""
        # Find or create conversation
        conversation = await self._get_or_create_conversation(from_number, to_number, sender_id)

        message = SMSMessage(
            conversation_id=conversation.id if conversation else None,
            direction=SMSDirection.OUTBOUND,
            from_number=from_number,
            to_number=to_number,
            body=body,
            sender_id=sender_id,
            sender_type=sender_type,
            media_urls=media_urls or [],
            num_media=len(media_urls) if media_urls else 0,
        )
        self.db.add(message)
        await self.db.flush()

        # Send via provider
        client = self._providers.get("twilio")
        if client:
            try:
                params = {
                    "to": to_number,
                    "from_": from_number,
                    "body": body,
                }
                if media_urls:
                    params["media_url"] = media_urls

                result = client.messages.create(**params)
                message.message_sid = result.sid
                message.status = SMSStatus.SENT
                message.sent_at = datetime.utcnow()
            except Exception as e:
                message.status = SMSStatus.FAILED
                message.error_message = str(e)

        # Update conversation
        if conversation:
            conversation.message_count += 1
            conversation.last_message_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def receive_sms(
        self,
        from_number: str,
        to_number: str,
        body: str,
        message_sid: str | None = None,
        media_urls: list[str] | None = None,
    ) -> SMSMessage:
        """Process a received SMS message."""
        # Find conversation with this number pair
        result = await self.db.execute(
            select(SMSConversation).where(
                and_(
                    SMSConversation.nexus_number == to_number,
                    SMSConversation.external_number == from_number,
                )
            )
        )
        conversation = result.scalar_one_or_none()

        message = SMSMessage(
            message_sid=message_sid,
            conversation_id=conversation.id if conversation else None,
            direction=SMSDirection.INBOUND,
            from_number=from_number,
            to_number=to_number,
            body=body,
            status=SMSStatus.RECEIVED,
            media_urls=media_urls or [],
            num_media=len(media_urls) if media_urls else 0,
        )
        self.db.add(message)

        if conversation:
            conversation.message_count += 1
            conversation.last_message_at = datetime.utcnow()

            # Auto-reply if enabled
            if conversation.auto_reply_enabled and conversation.ai_agent_id:
                await self._generate_auto_reply(conversation, message)

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def _generate_auto_reply(
        self,
        conversation: SMSConversation,
        incoming_message: SMSMessage,
    ):
        """Generate an AI auto-reply."""
        # Would integrate with LLM to generate response
        # For now, placeholder
        reply_text = f"Thanks for your message. An agent will respond shortly."

        await self.send_sms(
            from_number=conversation.nexus_number,
            to_number=conversation.external_number,
            body=reply_text,
            sender_id=conversation.ai_agent_id,
            sender_type="ai_agent",
        )

    async def _get_or_create_conversation(
        self,
        nexus_number: str,
        external_number: str,
        owner_id: UUID | None,
    ) -> SMSConversation | None:
        """Get or create an SMS conversation."""
        if not owner_id:
            return None

        result = await self.db.execute(
            select(SMSConversation).where(
                and_(
                    SMSConversation.nexus_number == nexus_number,
                    SMSConversation.external_number == external_number,
                )
            )
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            conversation = SMSConversation(
                nexus_number=nexus_number,
                external_number=external_number,
                owner_id=owner_id,
            )
            self.db.add(conversation)
            await self.db.flush()

        return conversation

    async def list_conversations(
        self,
        owner_id: UUID,
        limit: int = 50,
    ) -> list[SMSConversation]:
        """List SMS conversations."""
        result = await self.db.execute(
            select(SMSConversation)
            .where(SMSConversation.owner_id == owner_id)
            .order_by(SMSConversation.last_message_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_messages(
        self,
        conversation_id: UUID,
        limit: int = 100,
    ) -> list[SMSMessage]:
        """Get messages from a conversation."""
        result = await self.db.execute(
            select(SMSMessage)
            .where(SMSMessage.conversation_id == conversation_id)
            .order_by(SMSMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))
