"""Notification adapters for email and generic IM/webhook delivery."""

from __future__ import annotations

import smtplib
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from typing import Protocol

import requests

from astock_agent_system.config import NotificationSettings, Settings, load_settings


@dataclass(slots=True)
class NotificationResult:
    channel: str
    status: str
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class NotificationChannel(Protocol):
    name: str

    def send(self, title: str, body: str) -> NotificationResult:
        ...


class EmailNotifier:
    name = "email"

    def __init__(self, settings: NotificationSettings) -> None:
        self.settings = settings

    def send(self, title: str, body: str) -> NotificationResult:
        required = [self.settings.smtp_host, self.settings.email_from, self.settings.email_to]
        if not all(required):
            return NotificationResult(self.name, "skipped", "SMTP_HOST, EMAIL_FROM or EMAIL_TO is not configured")

        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.settings.email_from
        message["To"] = self.settings.email_to
        message.set_content(body)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
                smtp.starttls()
                if self.settings.smtp_username or self.settings.smtp_password:
                    smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(message)
        except Exception as exc:  # pragma: no cover - external service guard
            return NotificationResult(self.name, "error", str(exc))
        return NotificationResult(self.name, "ok")


class WebhookNotifier:
    name = "webhook"

    def __init__(self, settings: NotificationSettings) -> None:
        self.settings = settings

    def send(self, title: str, body: str) -> NotificationResult:
        if not self.settings.webhook_url:
            return NotificationResult(self.name, "skipped", "NOTIFY_WEBHOOK_URL is not configured")
        payload = _webhook_payload(self.settings.webhook_url, title, body)
        try:
            response = requests.post(self.settings.webhook_url, json=payload, timeout=20)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - external service guard
            return NotificationResult(self.name, "error", str(exc))
        return NotificationResult(self.name, "ok")


class Notifier:
    """Fan-out notifier that safely skips unconfigured channels."""

    def __init__(self, channels: list[NotificationChannel] | None = None) -> None:
        self.channels = channels or []

    def send(self, title: str, body: str) -> list[NotificationResult]:
        if not self.channels:
            return [NotificationResult("notifier", "skipped", "no notification channels configured")]
        return [channel.send(title, body) for channel in self.channels]


def build_notifier(settings: Settings | NotificationSettings | None = None) -> Notifier:
    if settings is None:
        notification = load_settings().notification
    elif isinstance(settings, NotificationSettings):
        notification = settings
    else:
        notification = settings.notification

    channels: list[NotificationChannel] = []
    requested = {item.lower() for item in notification.channels}
    if notification.smtp_host or "email" in requested:
        channels.append(EmailNotifier(notification))
    if notification.webhook_url or "webhook" in requested or "im" in requested:
        channels.append(WebhookNotifier(notification))
    return Notifier(channels)


def _webhook_payload(url: str, title: str, body: str) -> dict[str, object]:
    text = f"{title}\n\n{body}"
    lowered = url.lower()
    if "dingtalk" in lowered or "qyapi.weixin.qq.com" in lowered or "weixin" in lowered:
        return {"msgtype": "text", "text": {"content": text}}
    return {"title": title, "body": body, "text": text}
