"""Bark 通知 — 向后兼容的 re-export"""
from app.services.notifications.bark import BarkNotifier

__all__ = ['BarkNotifier']
