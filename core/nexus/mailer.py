"""Email service for sending transactional emails."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from nexus.config import get_settings


async def send_password_reset_email(to_email: str, name: str, token: str) -> None:
    """Send a password reset email."""
    settings = get_settings()

    # Build reset URL
    base_url = settings.frontend_url or "http://localhost:3000"
    reset_url = f"{base_url}/dashboard/reset-password?token={token}"

    subject = "Reset your Nexus password"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0c; color: #fafafa; padding: 40px 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #111114; border-radius: 16px; padding: 40px; }}
            .logo {{ font-size: 24px; font-weight: bold; margin-bottom: 32px; }}
            h1 {{ font-size: 24px; margin-bottom: 16px; }}
            p {{ color: #a1a1aa; line-height: 1.6; margin-bottom: 16px; }}
            .button {{ display: inline-block; padding: 14px 28px; background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: 600; }}
            .footer {{ margin-top: 32px; padding-top: 32px; border-top: 1px solid #27272a; color: #52525b; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">Nexus</div>
            <h1>Reset your password</h1>
            <p>Hi {name},</p>
            <p>We received a request to reset your password. Click the button below to create a new password:</p>
            <p style="margin: 32px 0;">
                <a href="{reset_url}" class="button">Reset Password</a>
            </p>
            <p>This link will expire in 1 hour.</p>
            <p>If you didn't request this, you can safely ignore this email.</p>
            <div class="footer">
                <p>Nexus - The Operating System for AI Agents</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Reset your Nexus password

    Hi {name},

    We received a request to reset your password. Click the link below to create a new password:

    {reset_url}

    This link will expire in 1 hour.

    If you didn't request this, you can safely ignore this email.

    Nexus - The Operating System for AI Agents
    """

    # Check if SMTP is configured
    if not settings.smtp_host:
        # In development, just log the reset URL
        import logging
        logging.info(f"Password reset URL for {to_email}: {reset_url}")
        return

    # Send email via SMTP
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or "noreply@nexus.ai"
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(msg["From"], [to_email], msg.as_string())


async def send_welcome_email(to_email: str, name: str) -> None:
    """Send a welcome email to new users."""
    settings = get_settings()

    subject = "Welcome to Nexus"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0c; color: #fafafa; padding: 40px 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #111114; border-radius: 16px; padding: 40px; }}
            .logo {{ font-size: 24px; font-weight: bold; margin-bottom: 32px; }}
            h1 {{ font-size: 24px; margin-bottom: 16px; }}
            p {{ color: #a1a1aa; line-height: 1.6; margin-bottom: 16px; }}
            .button {{ display: inline-block; padding: 14px 28px; background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: 600; }}
            .feature {{ display: flex; gap: 12px; margin-bottom: 16px; }}
            .feature-icon {{ width: 24px; }}
            .footer {{ margin-top: 32px; padding-top: 32px; border-top: 1px solid #27272a; color: #52525b; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">Nexus</div>
            <h1>Welcome to Nexus!</h1>
            <p>Hi {name},</p>
            <p>Welcome to the operating system for AI agents. Here's what you can do:</p>

            <div class="feature">
                <span class="feature-icon">🤖</span>
                <span>Create AI agents with persistent memory</span>
            </div>
            <div class="feature">
                <span class="feature-icon">🔗</span>
                <span>Connect your favorite APIs and services</span>
            </div>
            <div class="feature">
                <span class="feature-icon">👥</span>
                <span>Collaborate with your team in real-time</span>
            </div>
            <div class="feature">
                <span class="feature-icon">🚀</span>
                <span>Scale with 100x parallel workers</span>
            </div>

            <p style="margin: 32px 0;">
                <a href="{settings.frontend_url}/dashboard" class="button">Go to Dashboard</a>
            </p>

            <div class="footer">
                <p>Nexus - The Operating System for AI Agents</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Check if SMTP is configured
    if not settings.smtp_host:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or "noreply@nexus.ai"
    msg["To"] = to_email

    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(msg["From"], [to_email], msg.as_string())
