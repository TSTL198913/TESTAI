import os
import json
import smtplib
import requests
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class NotificationChannel(str, Enum):
    EMAIL = "email"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass
class Notification:
    notification_id: str
    channel: NotificationChannel
    recipient: str
    title: str
    message: str
    status: NotificationStatus = NotificationStatus.PENDING
    error_message: str = ""
    sent_at: Optional[datetime] = None


class EmailNotifier:
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.smtp_server = self.config.get("smtp_server", os.environ.get("SMTP_SERVER", "smtp.gmail.com"))
        self.smtp_port = int(self.config.get("smtp_port", os.environ.get("SMTP_PORT", "587")))
        self.smtp_username = self.config.get("smtp_username", os.environ.get("SMTP_USERNAME"))
        self.smtp_password = self.config.get("smtp_password", os.environ.get("SMTP_PASSWORD"))
        self.sender_email = self.config.get("sender_email", os.environ.get("SMTP_USERNAME"))
        self.enabled = bool(self.smtp_username and self.smtp_password)

    def send(self, to_email: str, subject: str, body: str) -> bool:
        if not self.enabled:
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.sender_email
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html", "utf-8"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                text = msg.as_string()
                server.sendmail(self.sender_email, to_email, text)

            return True
        except Exception as e:
            return False


class DingTalkNotifier:
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.webhook_url = self.config.get("webhook_url", os.environ.get("DINGTALK_WEBHOOK"))
        self.secret = self.config.get("secret", os.environ.get("DINGTALK_SECRET"))
        self.enabled = bool(self.webhook_url)

    def send(self, title: str, message: str) -> bool:
        if not self.enabled:
            return False

        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": message,
                },
                "at": {"isAtAll": False},
            }

            response = requests.post(self.webhook_url, json=payload)
            result = response.json()
            return result.get("errcode") == 0
        except Exception as e:
            return False


class FeishuNotifier:
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.webhook_url = self.config.get("webhook_url", os.environ.get("FEISHU_WEBHOOK"))
        self.enabled = bool(self.webhook_url)

    def send(self, title: str, message: str) -> bool:
        if not self.enabled:
            return False

        try:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {"tag": "lark_md", "content": message},
                        }
                    ],
                },
            }

            response = requests.post(self.webhook_url, json=payload)
            result = response.json()
            return result.get("code") == 0
        except Exception as e:
            return False


class NotificationManager:
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or os.environ.get(
            "NOTIFICATION_STORAGE_PATH", "data/notifications.json"
        )
        self.notifications: Dict[str, Notification] = {}
        self.email_notifier = EmailNotifier()
        self.dingtalk_notifier = DingTalkNotifier()
        self.feishu_notifier = FeishuNotifier()
        self._load_notifications()

    def _load_notifications(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for notif_id, notif_data in data.items():
                        self.notifications[notif_id] = Notification(
                            notification_id=notif_data["notification_id"],
                            channel=NotificationChannel(notif_data["channel"]),
                            recipient=notif_data["recipient"],
                            title=notif_data["title"],
                            message=notif_data["message"],
                            status=NotificationStatus(notif_data.get("status", "pending")),
                            error_message=notif_data.get("error_message", ""),
                            sent_at=datetime.fromisoformat(notif_data["sent_at"])
                            if notif_data.get("sent_at")
                            else None,
                        )
            except Exception:
                self.notifications = {}

    def _save_notifications(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        data = {}
        for notif_id, notif in self.notifications.items():
            data[notif_id] = {
                "notification_id": notif.notification_id,
                "channel": notif.channel.value,
                "recipient": notif.recipient,
                "title": notif.title,
                "message": notif.message,
                "status": notif.status.value,
                "error_message": notif.error_message,
                "sent_at": notif.sent_at.isoformat() if notif.sent_at else None,
            }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def send_notification(
        self,
        channel: NotificationChannel,
        recipient: str,
        title: str,
        message: str,
    ) -> Notification:
        notification_id = f"notif_{len(self.notifications) + 1:06d}"
        notification = Notification(
            notification_id=notification_id,
            channel=channel,
            recipient=recipient,
            title=title,
            message=message,
            status=NotificationStatus.PENDING,
        )

        success = False
        if channel == NotificationChannel.EMAIL:
            success = self.email_notifier.send(recipient, title, message)
        elif channel == NotificationChannel.DINGTALK:
            success = self.dingtalk_notifier.send(title, message)
        elif channel == NotificationChannel.FEISHU:
            success = self.feishu_notifier.send(title, message)

        if success:
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.now()
        else:
            notification.status = NotificationStatus.FAILED
            notification.error_message = f"Failed to send via {channel.value}"

        self.notifications[notification_id] = notification
        self._save_notifications()
        return notification

    def send_to_all_channels(
        self,
        title: str,
        message: str,
        email_recipients: list = None,
        dingtalk_enabled: bool = True,
        feishu_enabled: bool = True,
    ) -> Dict[str, Notification]:
        results = {}

        if email_recipients:
            for recipient in email_recipients:
                result = self.send_notification(
                    channel=NotificationChannel.EMAIL,
                    recipient=recipient,
                    title=title,
                    message=message,
                )
                results[f"email_{recipient}"] = result

        if dingtalk_enabled and self.dingtalk_notifier.enabled:
            result = self.send_notification(
                channel=NotificationChannel.DINGTALK,
                recipient="webhook",
                title=title,
                message=message,
            )
            results["dingtalk"] = result

        if feishu_enabled and self.feishu_notifier.enabled:
            result = self.send_notification(
                channel=NotificationChannel.FEISHU,
                recipient="webhook",
                title=title,
                message=message,
            )
            results["feishu"] = result

        return results

    def get_notification(self, notification_id: str) -> Optional[Notification]:
        return self.notifications.get(notification_id)

    def get_notifications(
        self,
        channel: Optional[NotificationChannel] = None,
        status: Optional[NotificationStatus] = None,
    ) -> list:
        filtered = []
        for notif in self.notifications.values():
            if channel and notif.channel != channel:
                continue
            if status and notif.status != status:
                continue
            filtered.append(notif)
        return sorted(filtered, key=lambda n: n.sent_at or datetime.min, reverse=True)

    def get_channel_status(self) -> Dict[str, bool]:
        return {
            "email": self.email_notifier.enabled,
            "dingtalk": self.dingtalk_notifier.enabled,
            "feishu": self.feishu_notifier.enabled,
        }

    def configure_email(self, config: Dict):
        self.email_notifier = EmailNotifier(config)

    def configure_dingtalk(self, config: Dict):
        self.dingtalk_notifier = DingTalkNotifier(config)

    def configure_feishu(self, config: Dict):
        self.feishu_notifier = FeishuNotifier(config)

    def generate_alert_message(self, alert) -> str:
        return f"""
**告警标题**: {alert.title}

**告警级别**: {alert.level.value.upper()}

**告警类型**: {alert.alert_type.value}

**告警时间**: {alert.timestamp.isoformat()}

**告警源**: {alert.source}

**详细信息**: {alert.message}

**详情**: {json.dumps(alert.details, indent=2, ensure_ascii=False)}
"""