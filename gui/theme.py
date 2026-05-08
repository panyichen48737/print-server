"""Theme engine: QPalette + QSS management with light/dark mode."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


TOKENS_LIGHT = {
    "surface": "#FFFFFF",
    "primary": "#4F46E5",
    "primary_container": "#EEF2FF",
    "error": "#DC2626",
    "on_surface": "#1F2937",
    "on_surface_variant": "#6B7280",
    "outline": "#D1D5DB",
    "success": "#16A34A",
}

TOKENS_DARK = {
    "surface": "#1E1E2E",
    "primary": "#818CF8",
    "primary_container": "#312E81",
    "error": "#F87171",
    "on_surface": "#E2E8F0",
    "on_surface_variant": "#94A3B8",
    "outline": "#4B5563",
    "success": "#4ADE80",
}


class ThemeEngine:
    _instance: ThemeEngine | None = None

    def __init__(self):
        self._mode: str = "light"
        self._tokens: dict[str, str] = dict(TOKENS_LIGHT)

    @classmethod
    def instance(cls) -> ThemeEngine:
        if cls._instance is None:
            cls._instance = ThemeEngine()
        return cls._instance

    @property
    def tokens(self) -> dict[str, str]:
        return dict(self._tokens)

    def apply(self, mode: str, qapp: QApplication) -> None:
        self._mode = mode
        self._tokens = dict(TOKENS_LIGHT if mode == "light" else TOKENS_DARK)
        qapp.setPalette(self._palette())
        qss_path = Path(__file__).parent / "resources" / f"{mode}.qss"
        if qss_path.exists():
            with open(qss_path, encoding="utf-8") as f:
                qapp.setStyleSheet(f.read())

    def _palette(self) -> QPalette:
        p = QPalette()
        t = self._tokens
        p.setColor(QPalette.ColorRole.Window, QColor(t["surface"]))
        p.setColor(QPalette.ColorRole.WindowText, QColor(t["on_surface"]))
        p.setColor(QPalette.ColorRole.Base, QColor(t["surface"]))
        p.setColor(QPalette.ColorRole.Text, QColor(t["on_surface"]))
        p.setColor(QPalette.ColorRole.Button, QColor(t["primary"]))
        p.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
        p.setColor(QPalette.ColorRole.Highlight, QColor(t["primary"]))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        p.setColor(QPalette.ColorRole.Link, QColor(t["primary"]))
        return p

    def apply_widget(self, widget, qss: str) -> None:
        widget.setStyleSheet(qss.format(**self._tokens))