"""Conversation service for managing dialogue threads."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nexus.conversations.models import (
    Conversation,
    ConversationMessage,
    ConversationParticipant,
    ConversationStatus,
    ParticipantType,
)


class ConversationService:
    """Service for managing conversations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(
        self,
        creator_id: UUID,
        creator_type: ParticipantType = ParticipantType.AGENT,
        title: str | None = None,
        description: str | None = None,
        context: dict | None = None,
        participant_ids: list[tuple[UUID, ParticipantType]] | None = None,
        team_id: UUID | None = None,
    ) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(
            title=title,
            description=description,
            context=context or {},
            creator_id=creator_id,
            creator_type=creator_type,
            team_id=team_id,
        )
        self.db.add(conversation)
        await self.db.flush()

        # Add creator as participant
        creator_participant = ConversationParticipant(
            conversation_id=conversation.id,
            participant_id=creator_id,
            participant_type=creator_type,
            role="owner",
        )
        self.db.add(creator_participant)

        # Add other participants
        if participant_ids:
            for pid, ptype in participant_ids:
                if pid != creator_id:
                    participant = ConversationParticipant(
                        conversation_id=conversation.id,
                        participant_id=pid,
                        participant_type=ptype,
                        role="participant",
                    )
                    self.db.add(participant)

        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def get_conversation(
        self,
        conversation_id: UUID,
        include_messages: bool = False,
    ) -> Conversation | None:
        """Get a conversation by ID."""
        query = select(Conversation).where(Conversation.id == conversation_id)

        if include_messages:
            query = query.options(
                selectinload(Conversation.messages),
                selectinload(Conversation.participants),
            )
        else:
            query = query.options(selectinload(Conversation.participants))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        participant_id: UUID,
        status: ConversationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations for a participant."""
        query = (
            select(Conversation)
            .join(ConversationParticipant)
            .where(
                and_(
                    ConversationParticipant.participant_id == participant_id,
                    ConversationParticipant.is_active == True,
                )
            )
            .options(selectinload(Conversation.participants))
            .order_by(Conversation.last_message_at.desc().nullslast())
            .offset(offset)
            .limit(limit)
        )

        if status:
            query = query.where(Conversation.status == status)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def add_participant(
        self,
        conversation_id: UUID,
        participant_id: UUID,
        participant_type: ParticipantType = ParticipantType.AGENT,
        role: str = "participant",
        display_name: str | None = None,
    ) -> ConversationParticipant:
        """Add a participant to a conversation."""
        participant = ConversationParticipant(
            conversation_id=conversation_id,
            participant_id=participant_id,
            participant_type=participant_type,
            role=role,
            display_name=display_name,
        )
        self.db.add(participant)
        await self.db.commit()
        return participant

    async def remove_participant(
        self,
        conversation_id: UUID,
        participant_id: UUID,
    ):
        """Remove a participant from a conversation (soft delete)."""
        query = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.participant_id == participant_id,
            )
        )
        result = await self.db.execute(query)
        participant = result.scalar_one_or_none()

        if participant:
            participant.is_active = False
            participant.left_at = datetime.utcnow()
            await self.db.commit()

    async def send_message(
        self,
        conversation_id: UUID,
        sender_id: UUID,
        content: str,
        sender_type: ParticipantType = ParticipantType.AGENT,
        sender_name: str | None = None,
        content_type: str = "text",
        reply_to_id: UUID | None = None,
        metadata: dict | None = None,
        tool_name: str | None = None,
        tool_input: dict | None = None,
        tool_output: dict | None = None,
    ) -> ConversationMessage:
        """Send a message to a conversation."""
        message = ConversationMessage(
            conversation_id=conversation_id,
            sender_id=sender_id,
            sender_type=sender_type,
            sender_name=sender_name,
            content=content,
            content_type=content_type,
            reply_to_id=reply_to_id,
            metadata=metadata or {},
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
        )
        self.db.add(message)

        # Update conversation
        conversation = await self.get_conversation(conversation_id)
        if conversation:
            conversation.message_count += 1
            conversation.last_message_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages(
        self,
        conversation_id: UUID,
        limit: int = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> list[ConversationMessage]:
        """Get messages from a conversation."""
        query = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )

        if before:
            query = query.where(ConversationMessage.created_at < before)
        if after:
            query = query.where(ConversationMessage.created_at > after)

        result = await self.db.execute(query)
        messages = list(result.scalars().all())
        return list(reversed(messages))  # Return in chronological order

    async def update_shared_state(
        self,
        conversation_id: UUID,
        state_update: dict,
    ) -> Conversation | None:
        """Update shared state of a conversation."""
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            return None

        # Merge state update
        current_state = conversation.shared_state or {}
        current_state.update(state_update)
        conversation.shared_state = current_state

        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def mark_read(
        self,
        conversation_id: UUID,
        participant_id: UUID,
    ):
        """Mark conversation as read for a participant."""
        query = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.participant_id == participant_id,
            )
        )
        result = await self.db.execute(query)
        participant = result.scalar_one_or_none()

        if participant:
            participant.last_read_at = datetime.utcnow()
            await self.db.commit()

    async def add_reaction(
        self,
        message_id: UUID,
        participant_id: UUID,
        emoji: str,
    ):
        """Add a reaction to a message."""
        query = select(ConversationMessage).where(ConversationMessage.id == message_id)
        result = await self.db.execute(query)
        message = result.scalar_one_or_none()

        if message:
            reactions = message.reactions or {}
            if emoji not in reactions:
                reactions[emoji] = []
            if str(participant_id) not in reactions[emoji]:
                reactions[emoji].append(str(participant_id))
            message.reactions = reactions
            await self.db.commit()

    async def edit_message(
        self,
        message_id: UUID,
        new_content: str,
    ) -> ConversationMessage | None:
        """Edit a message."""
        query = select(ConversationMessage).where(ConversationMessage.id == message_id)
        result = await self.db.execute(query)
        message = result.scalar_one_or_none()

        if message:
            message.content = new_content
            message.is_edited = True
            message.edited_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(message)

        return message

    async def close_conversation(
        self,
        conversation_id: UUID,
        summary: str | None = None,
    ):
        """Close/complete a conversation."""
        conversation = await self.get_conversation(conversation_id)
        if conversation:
            conversation.status = ConversationStatus.COMPLETED
            if summary:
                context = conversation.context or {}
                context["completion_summary"] = summary
                conversation.context = context
            await self.db.commit()
