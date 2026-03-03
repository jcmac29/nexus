"""Email service for sending and receiving emails."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
import uuid as uuid_module

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.email.models import (
    Email, EmailThread, EmailAccount, EmailTemplate,
    EmailStatus, EmailDirection, EmailPriority, EmailProvider
)


class EmailService:
    """Service for email operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._providers = {}

    def configure_sendgrid(self, api_key: str):
        """Configure SendGrid for email."""
        import sendgrid
        self._providers["sendgrid"] = sendgrid.SendGridAPIClient(api_key=api_key)

    def configure_ses(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        """Configure AWS SES for email."""
        import boto3
        self._providers["ses"] = boto3.client(
            "ses",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region,
        )

    async def send_email(
        self,
        from_address: str,
        to_addresses: list[str],
        subject: str,
        body_text: str | None = None,
        body_html: str | None = None,
        cc_addresses: list[str] | None = None,
        bcc_addresses: list[str] | None = None,
        reply_to: str | None = None,
        attachments: list[dict] | None = None,
        sender_id: UUID | None = None,
        sender_type: str = "agent",
        priority: EmailPriority = EmailPriority.NORMAL,
        account_id: UUID | None = None,
        thread_id: UUID | None = None,
        in_reply_to: str | None = None,
    ) -> Email:
        """Send an email message."""
        # Find or create thread
        thread = None
        if thread_id:
            result = await self.db.execute(
                select(EmailThread).where(EmailThread.id == thread_id)
            )
            thread = result.scalar_one_or_none()
        elif in_reply_to:
            # Find thread by in_reply_to message
            result = await self.db.execute(
                select(Email).where(Email.message_id == in_reply_to)
            )
            original = result.scalar_one_or_none()
            if original and original.thread_id:
                thread_id = original.thread_id
                result = await self.db.execute(
                    select(EmailThread).where(EmailThread.id == thread_id)
                )
                thread = result.scalar_one_or_none()

        # Create email record
        email = Email(
            message_id=f"<{uuid_module.uuid4()}@nexus.local>",
            account_id=account_id,
            thread_id=thread.id if thread else None,
            direction=EmailDirection.OUTBOUND,
            status=EmailStatus.QUEUED,
            priority=priority,
            from_address=from_address,
            to_addresses=[{"email": addr} for addr in to_addresses],
            cc_addresses=[{"email": addr} for addr in (cc_addresses or [])],
            bcc_addresses=[{"email": addr} for addr in (bcc_addresses or [])],
            reply_to=reply_to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments or [],
            sender_id=sender_id,
            sender_type=sender_type,
            in_reply_to=in_reply_to,
        )
        self.db.add(email)
        await self.db.flush()

        # Send via provider
        account = None
        if account_id:
            result = await self.db.execute(
                select(EmailAccount).where(EmailAccount.id == account_id)
            )
            account = result.scalar_one_or_none()

        provider = account.provider if account else EmailProvider.SENDGRID

        if provider == EmailProvider.SENDGRID and "sendgrid" in self._providers:
            try:
                from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType

                message = Mail(
                    from_email=from_address,
                    to_emails=to_addresses,
                    subject=subject,
                    plain_text_content=body_text,
                    html_content=body_html,
                )

                if cc_addresses:
                    for cc in cc_addresses:
                        message.add_cc(cc)

                response = self._providers["sendgrid"].send(message)
                email.provider_message_id = response.headers.get("X-Message-Id")
                email.status = EmailStatus.SENT
                email.sent_at = datetime.utcnow()
            except Exception as e:
                email.status = EmailStatus.FAILED
                email.bounce_reason = str(e)

        elif provider == EmailProvider.SES and "ses" in self._providers:
            try:
                response = self._providers["ses"].send_email(
                    Source=from_address,
                    Destination={
                        "ToAddresses": to_addresses,
                        "CcAddresses": cc_addresses or [],
                        "BccAddresses": bcc_addresses or [],
                    },
                    Message={
                        "Subject": {"Data": subject},
                        "Body": {
                            "Text": {"Data": body_text or ""},
                            "Html": {"Data": body_html or ""},
                        },
                    },
                )
                email.provider_message_id = response["MessageId"]
                email.status = EmailStatus.SENT
                email.sent_at = datetime.utcnow()
            except Exception as e:
                email.status = EmailStatus.FAILED
                email.bounce_reason = str(e)

        # Update thread
        if thread:
            thread.message_count += 1
            thread.last_message_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(email)
        return email

    async def receive_email(
        self,
        from_address: str,
        to_addresses: list[str],
        subject: str,
        body_text: str | None = None,
        body_html: str | None = None,
        message_id: str | None = None,
        in_reply_to: str | None = None,
        headers: dict | None = None,
        attachments: list[dict] | None = None,
    ) -> Email:
        """Process a received email."""
        # Find matching account
        result = await self.db.execute(
            select(EmailAccount).where(
                EmailAccount.email_address.in_(to_addresses)
            )
        )
        account = result.scalars().first()

        # Find or create thread
        thread = None
        if in_reply_to:
            result = await self.db.execute(
                select(Email).where(Email.message_id == in_reply_to)
            )
            original = result.scalar_one_or_none()
            if original and original.thread_id:
                result = await self.db.execute(
                    select(EmailThread).where(EmailThread.id == original.thread_id)
                )
                thread = result.scalar_one_or_none()

        if not thread and account:
            thread = EmailThread(
                subject=subject,
                participants=[from_address] + to_addresses,
                owner_id=account.owner_id,
                account_id=account.id,
            )
            self.db.add(thread)
            await self.db.flush()

        # Create email record
        email = Email(
            message_id=message_id,
            account_id=account.id if account else None,
            thread_id=thread.id if thread else None,
            direction=EmailDirection.INBOUND,
            status=EmailStatus.DELIVERED,
            from_address=from_address,
            to_addresses=[{"email": addr} for addr in to_addresses],
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            headers=headers or {},
            attachments=attachments or [],
            in_reply_to=in_reply_to,
            received_at=datetime.utcnow(),
        )
        self.db.add(email)

        if thread:
            thread.message_count += 1
            thread.unread_count += 1
            thread.last_message_at = datetime.utcnow()

            # Auto-reply if enabled
            if account and account.auto_reply_enabled and account.ai_agent_id:
                await self._generate_auto_reply(account, email)

        await self.db.commit()
        await self.db.refresh(email)
        return email

    async def _generate_auto_reply(self, account: EmailAccount, incoming_email: Email):
        """Generate an AI auto-reply."""
        # Would integrate with LLM to generate response
        reply_text = "Thank you for your email. I will respond shortly."

        await self.send_email(
            from_address=account.email_address,
            to_addresses=[incoming_email.from_address],
            subject=f"Re: {incoming_email.subject}",
            body_text=reply_text,
            sender_id=account.ai_agent_id,
            sender_type="ai_agent",
            account_id=account.id,
            in_reply_to=incoming_email.message_id,
        )

    async def list_threads(
        self,
        owner_id: UUID,
        account_id: UUID | None = None,
        is_archived: bool = False,
        limit: int = 50,
    ) -> list[EmailThread]:
        """List email threads."""
        query = select(EmailThread).where(
            and_(
                EmailThread.owner_id == owner_id,
                EmailThread.is_archived == is_archived,
            )
        )
        if account_id:
            query = query.where(EmailThread.account_id == account_id)

        query = query.order_by(EmailThread.last_message_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_thread_emails(
        self,
        thread_id: UUID,
        limit: int = 100,
    ) -> list[Email]:
        """Get emails from a thread."""
        result = await self.db.execute(
            select(Email)
            .where(Email.thread_id == thread_id)
            .order_by(Email.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_as_read(self, email_id: UUID):
        """Mark an email as read."""
        result = await self.db.execute(
            select(Email).where(Email.id == email_id)
        )
        email = result.scalar_one_or_none()
        if email and not email.is_read:
            email.is_read = True
            if email.thread_id:
                result = await self.db.execute(
                    select(EmailThread).where(EmailThread.id == email.thread_id)
                )
                thread = result.scalar_one_or_none()
                if thread and thread.unread_count > 0:
                    thread.unread_count -= 1
            await self.db.commit()

    async def render_template(
        self,
        template_id: UUID,
        variables: dict,
    ) -> dict:
        """Render an email template with variables."""
        result = await self.db.execute(
            select(EmailTemplate).where(EmailTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError("Template not found")

        def render(text: str | None, vars: dict) -> str | None:
            if not text:
                return None
            for key, value in vars.items():
                text = text.replace(f"{{{{{key}}}}}", str(value))
            return text

        return {
            "subject": render(template.subject_template, variables),
            "body_text": render(template.body_text_template, variables),
            "body_html": render(template.body_html_template, variables),
        }
