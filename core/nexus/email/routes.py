"""Email API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.email.service import EmailService
from nexus.email.models import EmailPriority

router = APIRouter(prefix="/email", tags=["email"])


class SendEmailRequest(BaseModel):
    from_address: str
    to_addresses: list[str]
    subject: str
    body_text: str | None = None
    body_html: str | None = None
    cc_addresses: list[str] | None = None
    bcc_addresses: list[str] | None = None
    reply_to: str | None = None
    attachments: list[dict] | None = None
    priority: str = "normal"
    account_id: str | None = None
    thread_id: str | None = None
    in_reply_to: str | None = None


class CreateAccountRequest(BaseModel):
    email_address: str
    display_name: str | None = None
    provider: str
    provider_config: dict | None = None
    auto_reply_enabled: bool = False
    ai_agent_id: str | None = None


class CreateTemplateRequest(BaseModel):
    name: str
    description: str | None = None
    subject_template: str | None = None
    body_text_template: str | None = None
    body_html_template: str | None = None
    variables: list[dict] | None = None
    category: str | None = None


@router.post("/send")
async def send_email(
    request: SendEmailRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Send an email message."""
    service = EmailService(db)

    priority_map = {
        "low": EmailPriority.LOW,
        "normal": EmailPriority.NORMAL,
        "high": EmailPriority.HIGH,
        "urgent": EmailPriority.URGENT,
    }

    email = await service.send_email(
        from_address=request.from_address,
        to_addresses=request.to_addresses,
        subject=request.subject,
        body_text=request.body_text,
        body_html=request.body_html,
        cc_addresses=request.cc_addresses,
        bcc_addresses=request.bcc_addresses,
        reply_to=request.reply_to,
        attachments=request.attachments,
        sender_id=agent.id,
        sender_type="agent",
        priority=priority_map.get(request.priority, EmailPriority.NORMAL),
        account_id=UUID(request.account_id) if request.account_id else None,
        thread_id=UUID(request.thread_id) if request.thread_id else None,
        in_reply_to=request.in_reply_to,
    )

    return {
        "id": str(email.id),
        "message_id": email.message_id,
        "status": email.status.value,
        "sent_at": email.sent_at.isoformat() if email.sent_at else None,
    }


@router.get("/threads")
async def list_threads(
    account_id: str | None = None,
    is_archived: bool = False,
    limit: int = Query(default=50, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List email threads."""
    service = EmailService(db)
    threads = await service.list_threads(
        owner_id=agent.id,
        account_id=UUID(account_id) if account_id else None,
        is_archived=is_archived,
        limit=limit,
    )

    return [
        {
            "id": str(t.id),
            "subject": t.subject,
            "participants": t.participants,
            "message_count": t.message_count,
            "unread_count": t.unread_count,
            "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
            "is_starred": t.is_starred,
            "labels": t.labels,
        }
        for t in threads
    ]


@router.get("/threads/{thread_id}/emails")
async def get_thread_emails(
    thread_id: str,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get emails from a thread."""
    service = EmailService(db)
    emails = await service.get_thread_emails(UUID(thread_id), limit)

    return [
        {
            "id": str(e.id),
            "message_id": e.message_id,
            "direction": e.direction.value,
            "status": e.status.value,
            "from_address": e.from_address,
            "to_addresses": e.to_addresses,
            "subject": e.subject,
            "body_text": e.body_text,
            "body_html": e.body_html,
            "attachments": e.attachments,
            "is_read": e.is_read,
            "created_at": e.created_at.isoformat(),
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
        }
        for e in emails
    ]


@router.post("/emails/{email_id}/read")
async def mark_email_read(
    email_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Mark an email as read."""
    service = EmailService(db)
    await service.mark_as_read(UUID(email_id))
    return {"status": "read"}


@router.post("/accounts")
async def create_account(
    request: CreateAccountRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create an email account."""
    from nexus.email.models import EmailAccount, EmailProvider

    provider_map = {
        "sendgrid": EmailProvider.SENDGRID,
        "mailgun": EmailProvider.MAILGUN,
        "ses": EmailProvider.SES,
        "postmark": EmailProvider.POSTMARK,
        "smtp": EmailProvider.SMTP,
        "resend": EmailProvider.RESEND,
    }

    account = EmailAccount(
        email_address=request.email_address,
        display_name=request.display_name,
        provider=provider_map.get(request.provider, EmailProvider.SMTP),
        provider_config=request.provider_config or {},
        owner_id=agent.id,
        auto_reply_enabled=request.auto_reply_enabled,
        ai_agent_id=UUID(request.ai_agent_id) if request.ai_agent_id else None,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return {
        "id": str(account.id),
        "email_address": account.email_address,
        "provider": account.provider.value,
    }


@router.post("/templates")
async def create_template(
    request: CreateTemplateRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create an email template."""
    from nexus.email.models import EmailTemplate

    template = EmailTemplate(
        name=request.name,
        description=request.description,
        owner_id=agent.id,
        subject_template=request.subject_template,
        body_text_template=request.body_text_template,
        body_html_template=request.body_html_template,
        variables=request.variables or [],
        category=request.category,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return {
        "id": str(template.id),
        "name": template.name,
    }


@router.post("/templates/{template_id}/render")
async def render_template(
    template_id: str,
    variables: dict,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Render an email template."""
    service = EmailService(db)
    rendered = await service.render_template(UUID(template_id), variables)
    return rendered


@router.post("/webhook/inbound")
async def inbound_webhook(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Handle inbound email webhook (SendGrid, Mailgun, etc.)."""
    service = EmailService(db)

    # Parse webhook data (format varies by provider)
    email = await service.receive_email(
        from_address=data.get("from", ""),
        to_addresses=data.get("to", "").split(",") if isinstance(data.get("to"), str) else data.get("to", []),
        subject=data.get("subject", ""),
        body_text=data.get("text", data.get("body-plain")),
        body_html=data.get("html", data.get("body-html")),
        message_id=data.get("Message-Id", data.get("message-id")),
        in_reply_to=data.get("In-Reply-To", data.get("in-reply-to")),
        headers=data.get("headers", {}),
        attachments=data.get("attachments", []),
    )

    return {"status": "received", "email_id": str(email.id)}
