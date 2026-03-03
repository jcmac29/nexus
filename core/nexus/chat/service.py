"""Chat service for external chat platform integrations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.chat.models import (
    ChatConnection, ChatChannel, ChatMessage, ChatCommand,
    ChatPlatform, ChatConnectionStatus
)


class ChatService:
    """Service for chat platform operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._clients = {}

    def configure_slack(self, bot_token: str, app_token: str | None = None):
        """Configure Slack client."""
        from slack_sdk.web.async_client import AsyncWebClient
        self._clients["slack"] = AsyncWebClient(token=bot_token)

    def configure_discord(self, bot_token: str):
        """Configure Discord client."""
        self._clients["discord"] = {"token": bot_token}

    def configure_telegram(self, bot_token: str):
        """Configure Telegram client."""
        self._clients["telegram"] = {"token": bot_token}

    async def create_connection(
        self,
        owner_id: UUID,
        platform: ChatPlatform,
        access_token: str | None = None,
        bot_token: str | None = None,
        webhook_url: str | None = None,
        workspace_id: str | None = None,
        workspace_name: str | None = None,
        ai_agent_id: UUID | None = None,
        auto_reply_enabled: bool = False,
        system_prompt: str | None = None,
    ) -> ChatConnection:
        """Create a connection to a chat platform."""
        connection = ChatConnection(
            owner_id=owner_id,
            platform=platform,
            status=ChatConnectionStatus.PENDING,
            access_token=access_token,
            bot_token=bot_token,
            webhook_url=webhook_url,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            ai_agent_id=ai_agent_id,
            auto_reply_enabled=auto_reply_enabled,
            system_prompt=system_prompt,
        )
        self.db.add(connection)
        await self.db.commit()
        await self.db.refresh(connection)

        # Verify connection
        if await self._verify_connection(connection):
            connection.status = ChatConnectionStatus.CONNECTED
            await self.db.commit()

        return connection

    async def _verify_connection(self, connection: ChatConnection) -> bool:
        """Verify connection to platform."""
        try:
            if connection.platform == ChatPlatform.SLACK:
                if "slack" in self._clients:
                    response = await self._clients["slack"].auth_test()
                    if response["ok"]:
                        connection.bot_user_id = response.get("user_id")
                        return True
            elif connection.platform == ChatPlatform.DISCORD:
                # Discord verification would go here
                return True
            elif connection.platform == ChatPlatform.TELEGRAM:
                # Telegram verification
                return True
        except Exception as e:
            connection.error_message = str(e)
            connection.status = ChatConnectionStatus.ERROR
        return False

    async def sync_channels(self, connection_id: UUID) -> list[ChatChannel]:
        """Sync channels from the platform."""
        result = await self.db.execute(
            select(ChatConnection).where(ChatConnection.id == connection_id)
        )
        connection = result.scalar_one_or_none()
        if not connection:
            raise ValueError("Connection not found")

        channels = []

        if connection.platform == ChatPlatform.SLACK and "slack" in self._clients:
            response = await self._clients["slack"].conversations_list(
                types="public_channel,private_channel"
            )
            for ch in response.get("channels", []):
                channel = await self._upsert_channel(
                    connection_id=connection_id,
                    channel_id=ch["id"],
                    channel_name=ch.get("name"),
                    channel_type="private" if ch.get("is_private") else "public",
                    topic=ch.get("topic", {}).get("value"),
                    member_count=ch.get("num_members", 0),
                    is_member=ch.get("is_member", False),
                )
                channels.append(channel)

        connection.last_sync_at = datetime.utcnow()
        await self.db.commit()
        return channels

    async def _upsert_channel(
        self,
        connection_id: UUID,
        channel_id: str,
        channel_name: str | None = None,
        channel_type: str | None = None,
        topic: str | None = None,
        member_count: int = 0,
        is_member: bool = False,
    ) -> ChatChannel:
        """Create or update a channel."""
        result = await self.db.execute(
            select(ChatChannel).where(
                and_(
                    ChatChannel.connection_id == connection_id,
                    ChatChannel.channel_id == channel_id,
                )
            )
        )
        channel = result.scalar_one_or_none()

        if channel:
            channel.channel_name = channel_name
            channel.channel_type = channel_type
            channel.topic = topic
            channel.member_count = member_count
            channel.is_member = is_member
        else:
            channel = ChatChannel(
                connection_id=connection_id,
                channel_id=channel_id,
                channel_name=channel_name,
                channel_type=channel_type,
                topic=topic,
                member_count=member_count,
                is_member=is_member,
            )
            self.db.add(channel)

        await self.db.flush()
        return channel

    async def send_message(
        self,
        channel_id: UUID,
        content: str,
        thread_id: str | None = None,
        attachments: list[dict] | None = None,
    ) -> dict:
        """Send a message to a channel."""
        result = await self.db.execute(
            select(ChatChannel).where(ChatChannel.id == channel_id)
        )
        channel = result.scalar_one_or_none()
        if not channel:
            raise ValueError("Channel not found")

        result = await self.db.execute(
            select(ChatConnection).where(ChatConnection.id == channel.connection_id)
        )
        connection = result.scalar_one_or_none()
        if not connection:
            raise ValueError("Connection not found")

        response = {}

        if connection.platform == ChatPlatform.SLACK and "slack" in self._clients:
            params = {
                "channel": channel.channel_id,
                "text": content,
            }
            if thread_id:
                params["thread_ts"] = thread_id
            if attachments:
                params["attachments"] = attachments

            result = await self._clients["slack"].chat_postMessage(**params)
            response = {
                "message_id": result.get("ts"),
                "channel_id": result.get("channel"),
            }

        elif connection.platform == ChatPlatform.DISCORD and "discord" in self._clients:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://discord.com/api/v10/channels/{channel.channel_id}/messages",
                    headers={"Authorization": f"Bot {self._clients['discord']['token']}"},
                    json={"content": content},
                )
                data = resp.json()
                response = {"message_id": data.get("id")}

        elif connection.platform == ChatPlatform.TELEGRAM and "telegram" in self._clients:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self._clients['telegram']['token']}/sendMessage",
                    json={
                        "chat_id": channel.channel_id,
                        "text": content,
                        "reply_to_message_id": thread_id,
                    },
                )
                data = resp.json()
                if data.get("ok"):
                    response = {"message_id": str(data["result"]["message_id"])}

        return response

    async def process_incoming_message(
        self,
        connection_id: UUID,
        channel_id: str,
        message_id: str,
        sender_id: str,
        content: str,
        sender_name: str | None = None,
        thread_id: str | None = None,
        is_bot: bool = False,
        attachments: list[dict] | None = None,
        mentions: list[str] | None = None,
        platform_timestamp: datetime | None = None,
    ) -> ChatMessage:
        """Process an incoming message from a platform."""
        # Find or create channel
        result = await self.db.execute(
            select(ChatChannel).where(
                and_(
                    ChatChannel.connection_id == connection_id,
                    ChatChannel.channel_id == channel_id,
                )
            )
        )
        channel = result.scalar_one_or_none()
        if not channel:
            channel = await self._upsert_channel(connection_id, channel_id)

        # Check for duplicate
        result = await self.db.execute(
            select(ChatMessage).where(
                and_(
                    ChatMessage.channel_id == channel.id,
                    ChatMessage.message_id == message_id,
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        message = ChatMessage(
            channel_id=channel.id,
            message_id=message_id,
            thread_id=thread_id,
            sender_id=sender_id,
            sender_name=sender_name,
            is_bot=is_bot,
            content=content,
            attachments=attachments or [],
            mentions=mentions or [],
            platform_timestamp=platform_timestamp,
        )
        self.db.add(message)

        channel.last_message_at = datetime.utcnow()

        # Auto-reply if enabled and not from a bot
        if not is_bot and channel.auto_reply_enabled:
            # Check if mention-only mode
            result = await self.db.execute(
                select(ChatConnection).where(ChatConnection.id == connection_id)
            )
            connection = result.scalar_one_or_none()

            should_reply = True
            if channel.mention_only and connection:
                # Check if bot was mentioned
                should_reply = connection.bot_user_id in (mentions or [])

            if should_reply and connection and connection.ai_agent_id:
                await self._generate_auto_reply(connection, channel, message)

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def _generate_auto_reply(
        self,
        connection: ChatConnection,
        channel: ChatChannel,
        message: ChatMessage,
    ):
        """Generate an AI auto-reply."""
        # Would integrate with LLM to generate response
        reply_text = "Thanks for your message! I'll get back to you shortly."

        response = await self.send_message(
            channel_id=channel.id,
            content=reply_text,
            thread_id=message.thread_id or message.message_id,
        )

        message.ai_processed = True

    async def list_connections(
        self,
        owner_id: UUID,
        platform: ChatPlatform | None = None,
    ) -> list[ChatConnection]:
        """List chat connections."""
        query = select(ChatConnection).where(ChatConnection.owner_id == owner_id)
        if platform:
            query = query.where(ChatConnection.platform == platform)
        query = query.order_by(ChatConnection.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_channels(
        self,
        connection_id: UUID,
        synced_only: bool = False,
    ) -> list[ChatChannel]:
        """List channels for a connection."""
        query = select(ChatChannel).where(ChatChannel.connection_id == connection_id)
        if synced_only:
            query = query.where(ChatChannel.is_synced == True)
        query = query.order_by(ChatChannel.channel_name.asc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_messages(
        self,
        channel_id: UUID,
        limit: int = 100,
    ) -> list[ChatMessage]:
        """Get messages from a channel."""
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.channel_id == channel_id)
            .order_by(ChatMessage.received_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def create_command(
        self,
        connection_id: UUID,
        name: str,
        description: str | None = None,
        handler_type: str = "agent",
        handler_id: UUID | None = None,
        options: list[dict] | None = None,
    ) -> ChatCommand:
        """Create a slash command."""
        command = ChatCommand(
            connection_id=connection_id,
            name=name,
            description=description,
            handler_type=handler_type,
            handler_id=handler_id,
            options=options or [],
        )
        self.db.add(command)
        await self.db.commit()
        await self.db.refresh(command)
        return command
