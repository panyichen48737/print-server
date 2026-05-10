"""钉钉通知 — 向后兼容的 re-export"""

from app.services.notifications.dingtalk import DingTalk

__all__ = ['DingTalk']
