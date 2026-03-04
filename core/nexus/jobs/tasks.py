"""Common background tasks for Nexus."""

from nexus.jobs.service import task


@task(name="nexus.send_email", queue="emails", max_retries=3)
async def send_email(
    to: str,
    subject: str,
    body: str,
    html: str | None = None,
    from_addr: str | None = None,
):
    """Send an email in the background."""
    # This would integrate with the email service
    print(f"Sending email to {to}: {subject}")
    return {"sent": True, "to": to}


@task(name="nexus.send_notification", queue="notifications", max_retries=3)
async def send_notification(
    recipient_id: str,
    title: str,
    body: str,
    channel: str = "push",
):
    """Send a notification in the background."""
    print(f"Sending {channel} notification to {recipient_id}: {title}")
    return {"sent": True}


@task(name="nexus.process_webhook", queue="webhooks", max_retries=5)
async def process_webhook(
    webhook_id: str,
    url: str,
    payload: dict,
    headers: dict | None = None,
):
    """Process a webhook delivery."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers=headers or {},
            timeout=30.0,
        )
        return {
            "status_code": response.status_code,
            "success": response.status_code < 400,
        }


@task(name="nexus.process_payout", queue="billing", max_retries=3)
async def process_payout(seller_account_id: str):
    """Process a marketplace payout."""
    print(f"Processing payout for seller {seller_account_id}")
    return {"processed": True}


@task(name="nexus.generate_report", queue="reports", max_retries=2, timeout=600)
async def generate_report(
    report_type: str,
    owner_id: str,
    parameters: dict,
):
    """Generate a report in the background."""
    print(f"Generating {report_type} report for {owner_id}")
    # Simulate report generation
    import asyncio
    await asyncio.sleep(5)
    return {"report_id": "report-123", "type": report_type}


@task(name="nexus.cleanup_expired", queue="maintenance")
async def cleanup_expired_data():
    """Clean up expired data (sessions, tokens, etc.)."""
    print("Running cleanup of expired data")
    return {"cleaned": True}


@task(name="nexus.sync_device_telemetry", queue="devices", max_retries=2)
async def sync_device_telemetry(device_id: str):
    """Sync device telemetry to external systems."""
    print(f"Syncing telemetry for device {device_id}")
    return {"synced": True}


@task(name="nexus.process_recording", queue="media", timeout=1800)
async def process_recording(recording_id: str, actions: list[str]):
    """Process a call/video recording (transcription, etc.)."""
    print(f"Processing recording {recording_id}: {actions}")
    return {"processed": True, "actions": actions}


@task(name="nexus.index_document", queue="search")
async def index_document(document_id: str, content: str):
    """Index a document for search."""
    print(f"Indexing document {document_id}")
    return {"indexed": True}


@task(name="nexus.generate_embeddings", queue="ai", timeout=120)
async def generate_embeddings(content: str, model: str = "text-embedding-3-small"):
    """Generate vector embeddings for content."""
    print(f"Generating embeddings with {model}")
    # This would call OpenAI or another embedding service
    return {"dimensions": 1536}


# --- Analytics Aggregation Tasks ---


@task(name="nexus.aggregate_hourly_metrics", queue="analytics", max_retries=3)
async def aggregate_hourly_metrics():
    """
    Aggregate metrics from Redis to PostgreSQL hourly tables.

    Runs every hour to roll up real-time counters.
    """
    from nexus.database import get_db
    from nexus.analytics.collector import MetricsCollector

    async for session in get_db():
        collector = MetricsCollector(session)
        result = await collector.flush_to_database()
        return result


@task(name="nexus.aggregate_daily_metrics", queue="analytics", max_retries=3)
async def aggregate_daily_metrics():
    """
    Aggregate hourly metrics into daily summaries.

    Runs daily to compute daily aggregates and percentiles.
    """
    from nexus.database import get_db
    from nexus.analytics.tasks import roll_up_daily_metrics

    async for session in get_db():
        result = await roll_up_daily_metrics(session)
        return result


@task(name="nexus.calculate_storage_usage", queue="analytics", max_retries=2)
async def calculate_storage_usage():
    """
    Calculate storage usage for all agents.

    Runs daily to update storage_usage table.
    """
    from nexus.database import get_db
    from nexus.analytics.tasks import calculate_storage_snapshots

    async for session in get_db():
        result = await calculate_storage_snapshots(session)
        return result


@task(name="nexus.retry_failed_webhooks", queue="webhooks", max_retries=1)
async def retry_failed_webhooks():
    """
    Retry webhooks that are due for retry.

    Runs every minute to process webhook retry queue.
    """
    from nexus.database import get_db
    from nexus.webhooks.service import WebhookService

    async for session in get_db():
        service = WebhookService(session)
        result = await service.process_retry_queue()
        return result


@task(name="nexus.cleanup_old_metrics", queue="maintenance", max_retries=1)
async def cleanup_old_metrics(retention_days: int = 90):
    """
    Clean up old metrics data beyond retention period.

    Runs weekly to purge old analytics data.
    """
    from nexus.database import get_db
    from nexus.analytics.tasks import cleanup_old_data

    async for session in get_db():
        result = await cleanup_old_data(session, retention_days)
        return result


@task(name="nexus.cleanup_delivery_logs", queue="maintenance", max_retries=1)
async def cleanup_delivery_logs(retention_days: int = 30):
    """
    Clean up old webhook delivery logs.

    Runs weekly to purge old delivery logs.
    """
    from nexus.database import get_db
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from nexus.webhooks.models import WebhookDeliveryLog

    async for session in get_db():
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        result = await session.execute(
            delete(WebhookDeliveryLog).where(WebhookDeliveryLog.created_at < cutoff)
        )
        await session.commit()
        return {"deleted": result.rowcount}


@task(name="nexus.refresh_tenant_limits", queue="tenants", max_retries=2)
async def refresh_tenant_limits():
    """
    Refresh cached tenant limits.

    Runs hourly to update limit calculations.
    """
    from nexus.database import get_db
    from nexus.tenants.limits import LimitsService

    async for session in get_db():
        service = LimitsService(session)
        result = await service.refresh_all_limits()
        return result
