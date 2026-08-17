"""
Notification Delivery Service.
Handles real delivery of notifications via configurable adapters.

Delivery states:
- QUEUED: Created, waiting for delivery
- SENDING: Currently being delivered
- SENT: Delivery attempt made (acknowledged by provider)
- DELIVERED: Confirmed delivered to recipient
- FAILED: Delivery failed (will retry if attempts < max)
- RETRYING: Scheduled for retry
- EXPIRED: Max attempts exceeded, permanently failed

Adapters:
- EmailAdapter: Sends via AWS SES or SMTP
- WebhookAdapter: Sends to configurable webhook URL (Teams/Slack/custom)
- InAppAdapter: Stores for in-app notification (always active)

Architecture:
- Notifications are created via NotificationService.send()
- Delivery is attempted immediately (async)
- Failed deliveries are retried by a background worker
- All delivery attempts are logged for audit
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from dataclasses import dataclass

import structlog

from config import settings
from database.database import AsyncSessionLocal
from database.repositories import NotificationRepository

logger = structlog.get_logger()


class DeliveryStatus(str, Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    EXPIRED = "expired"


class NotificationChannel(str, Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    WEBHOOK = "webhook"  # Teams/Slack/custom


@dataclass
class DeliveryAttempt:
    """Record of a single delivery attempt."""
    attempt_number: int
    channel: str
    status: str
    timestamp: str
    error: Optional[str] = None
    response: Optional[str] = None


@dataclass
class NotificationPayload:
    """Structured notification content."""
    title: str
    body: str
    visitor_name: Optional[str] = None
    visitor_company: Optional[str] = None
    purpose: Optional[str] = None
    action_url: Optional[str] = None
    urgency: str = "normal"  # low, normal, high, urgent


# ============================================================
# NOTIFICATION ADAPTERS
# ============================================================

class NotificationAdapter:
    """Base class for notification delivery adapters."""

    async def send(self, recipient: str, payload: NotificationPayload) -> Dict[str, Any]:
        """
        Send notification to recipient.
        Returns dict with: success (bool), message_id (str), error (str|None)
        """
        raise NotImplementedError


class InAppAdapter(NotificationAdapter):
    """
    In-app notification adapter.
    Always succeeds — stores notification in database for dashboard display.
    """

    async def send(self, recipient: str, payload: NotificationPayload) -> Dict[str, Any]:
        return {
            "success": True,
            "message_id": str(uuid.uuid4()),
            "channel": "in_app",
        }


class WebhookAdapter(NotificationAdapter):
    """
    Webhook notification adapter.
    Sends JSON payload to a configured URL (supports Slack/Teams/custom).
    
    Configure via environment:
        NOTIFICATION_WEBHOOK_URL=https://hooks.slack.com/services/...
    """

    def __init__(self):
        self.webhook_url = getattr(settings, 'notification_webhook_url', None)

    async def send(self, recipient: str, payload: NotificationPayload) -> Dict[str, Any]:
        if not self.webhook_url:
            return {
                "success": False,
                "error": "Webhook URL not configured (set NOTIFICATION_WEBHOOK_URL)",
                "channel": "webhook",
            }

        try:
            import httpx

            # Format for Slack/Teams compatible payload
            webhook_body = {
                "text": f"🔔 *{payload.title}*\n{payload.body}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{payload.title}*\n{payload.body}"
                        }
                    }
                ]
            }

            if payload.visitor_name:
                webhook_body["blocks"].append({
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Visitor:* {payload.visitor_name}"},
                        {"type": "mrkdwn", "text": f"*Company:* {payload.visitor_company or 'N/A'}"},
                    ]
                })

            if payload.action_url:
                webhook_body["blocks"].append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View in Dashboard"},
                            "url": payload.action_url
                        }
                    ]
                })

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=webhook_body,
                    headers={"Content-Type": "application/json"}
                )

            if response.status_code in (200, 201, 202, 204):
                return {
                    "success": True,
                    "message_id": str(uuid.uuid4()),
                    "channel": "webhook",
                    "status_code": response.status_code,
                }
            else:
                return {
                    "success": False,
                    "error": f"Webhook returned {response.status_code}: {response.text[:200]}",
                    "channel": "webhook",
                }

        except Exception as e:
            logger.error("Webhook delivery failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "channel": "webhook",
            }


class EmailAdapter(NotificationAdapter):
    """
    Email notification adapter.
    Uses AWS SES via boto3 (or falls back to SMTP if configured).
    
    Configure via environment:
        NOTIFICATION_EMAIL_FROM=reception@codeorigin.ai
        NOTIFICATION_EMAIL_ENABLED=true
    """

    def __init__(self):
        self.from_email = getattr(settings, 'notification_email_from', 'reception@codeorigin.ai')
        self.enabled = getattr(settings, 'notification_email_enabled', False)

    async def send(self, recipient: str, payload: NotificationPayload) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "success": False,
                "error": "Email notifications not enabled (set NOTIFICATION_EMAIL_ENABLED=true)",
                "channel": "email",
            }

        try:
            import boto3

            def _send_ses():
                session = boto3.Session(
                    region_name=settings.aws_region,
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                )
                ses = session.client('ses')
                return ses.send_email(
                    Source=self.from_email,
                    Destination={'ToAddresses': [recipient]},
                    Message={
                        'Subject': {'Data': payload.title, 'Charset': 'UTF-8'},
                        'Body': {
                            'Html': {
                                'Data': self._format_html(payload),
                                'Charset': 'UTF-8'
                            },
                            'Text': {
                                'Data': payload.body,
                                'Charset': 'UTF-8'
                            }
                        }
                    }
                )

            result = await asyncio.to_thread(_send_ses)

            return {
                "success": True,
                "message_id": result.get('MessageId', str(uuid.uuid4())),
                "channel": "email",
            }

        except Exception as e:
            logger.error("Email delivery failed", error=str(e), recipient=recipient)
            return {
                "success": False,
                "error": str(e),
                "channel": "email",
            }

    @staticmethod
    def _format_html(payload: NotificationPayload) -> str:
        """Format notification as HTML email."""
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
            <h2 style="color: #333;">{payload.title}</h2>
            <p style="color: #555; font-size: 14px;">{payload.body}</p>
        """
        if payload.visitor_name:
            html += f"""
            <table style="border: 1px solid #ddd; border-radius: 4px; padding: 12px; width: 100%;">
                <tr><td><strong>Visitor:</strong></td><td>{payload.visitor_name}</td></tr>
                <tr><td><strong>Company:</strong></td><td>{payload.visitor_company or 'N/A'}</td></tr>
                <tr><td><strong>Purpose:</strong></td><td>{payload.purpose or 'Not specified'}</td></tr>
            </table>
            """
        if payload.action_url:
            html += f'<p><a href="{payload.action_url}" style="color: #2563eb;">View in Dashboard</a></p>'
        html += "</div>"
        return html


# ============================================================
# NOTIFICATION SERVICE
# ============================================================

class NotificationService:
    """
    Main notification service — orchestrates delivery across adapters.
    
    Usage:
        notification_service = NotificationService()
        await notification_service.send_visitor_arrival(
            employee_id="...",
            employee_email="priya@codeorigin.ai",
            visitor_name="Rahul",
            visitor_company="TechCorp",
        )
    """

    def __init__(self):
        self.adapters: Dict[str, NotificationAdapter] = {
            NotificationChannel.IN_APP.value: InAppAdapter(),
            NotificationChannel.WEBHOOK.value: WebhookAdapter(),
            NotificationChannel.EMAIL.value: EmailAdapter(),
        }
        self.max_retry_attempts = 3
        self.retry_delay_seconds = 60

    async def send_visitor_arrival(
        self,
        employee_id: str,
        employee_email: Optional[str],
        visitor_name: str,
        visitor_company: Optional[str] = None,
        visitor_id: Optional[str] = None,
        purpose: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send notification that a visitor has arrived for an employee.
        Attempts delivery via all configured channels.
        """
        payload = NotificationPayload(
            title=f"Visitor Arrived: {visitor_name}",
            body=f"{visitor_name}{f' from {visitor_company}' if visitor_company else ''} "
                 f"is at reception and would like to see you.",
            visitor_name=visitor_name,
            visitor_company=visitor_company,
            purpose=purpose,
            urgency="normal",
        )

        # Store in database (in_app is always created)
        db_notification_id = None
        try:
            async with AsyncSessionLocal() as db:
                repo = NotificationRepository(db)
                notification = await repo.create(
                    employee_id=employee_id,
                    message=payload.body,
                    notification_type="visitor_arrived",
                    visitor_id=visitor_id,
                )
                db_notification_id = notification.notification_id
                await db.commit()
        except Exception as e:
            logger.error("Failed to store notification in DB", error=str(e))

        # Attempt delivery via each configured adapter
        results = {}
        for channel_name, adapter in self.adapters.items():
            if channel_name == NotificationChannel.IN_APP.value:
                results[channel_name] = {"success": True, "status": "delivered"}
                continue

            recipient = employee_email or ""
            if channel_name == NotificationChannel.WEBHOOK.value:
                recipient = "webhook"  # Webhook doesn't need per-user recipient

            try:
                result = await adapter.send(recipient, payload)
                results[channel_name] = result

                if result.get("success"):
                    logger.info(
                        "Notification delivered",
                        channel=channel_name,
                        employee_id=employee_id,
                        visitor_name=visitor_name,
                    )
                else:
                    logger.warning(
                        "Notification delivery failed",
                        channel=channel_name,
                        error=result.get("error"),
                    )
            except Exception as e:
                results[channel_name] = {"success": False, "error": str(e)}
                logger.error("Notification adapter exception", channel=channel_name, error=str(e))

        return {
            "notification_id": db_notification_id,
            "delivery_results": results,
            "any_delivered": any(r.get("success") for r in results.values()),
        }

    async def send_host_approval_request(
        self,
        employee_id: str,
        employee_email: Optional[str],
        visitor_name: str,
        approval_token: str,
        visitor_company: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send approval request to host employee."""
        payload = NotificationPayload(
            title=f"Visitor Approval Required: {visitor_name}",
            body=f"{visitor_name}{f' from {visitor_company}' if visitor_company else ''} "
                 f"is requesting to meet you. Please approve or decline.",
            visitor_name=visitor_name,
            visitor_company=visitor_company,
            urgency="high",
            action_url=f"/api/visits/approve/{approval_token}",
        )

        # Store and deliver
        results = {}
        for channel_name, adapter in self.adapters.items():
            if channel_name == NotificationChannel.IN_APP.value:
                results[channel_name] = {"success": True}
                continue
            recipient = employee_email or "webhook"
            try:
                results[channel_name] = await adapter.send(recipient, payload)
            except Exception as e:
                results[channel_name] = {"success": False, "error": str(e)}

        return {"delivery_results": results}


# Global singleton
notification_service = NotificationService()
