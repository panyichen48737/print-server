"""Theme engine: QPalette + QSS management with light/dark mode."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Porcelain palette — warm white, bronze accents, shadow-driven depth
TOKENS_LIGHT = {
    'surface': '#FAFAF8',
    'surface_alt': '#F5F0EB',
    'primary': '#8B7355',
    'primary_hover': '#6D5940',
    'primary_container': '#E8DFD4',
    'error': '#C53A3A',
    'error_container': '#FBF0F0',
    'on_surface': '#1C1917',
    'on_surface_variant': '#8A8178',
    'outline': '#E5DDD5',
    'outline_strong': '#D0C8BE',
    'success': '#6B8F6B',
    'success_container': '#EEF5EE',
    'warning': '#B8956A',
    'warning_container': '#F9F3EB',
    'nav_bg': '#F5F0EB',
    'nav_selected_bg': '#EDE6DD',
    'nav_selected_text': '#8B7355',
    'card_bg': '#FFFFFF',
    'input_bg': '#FFFFFF',
    'switch_off': '#D0C8BE',
    'switch_knob': '#FFFFFF',
    'monospace': "Consolas, 'Cascadia Code', 'Courier New', monospace",
}

TOKENS_DARK = {
    'surface': '#1C1C1A',
    'surface_alt': '#262522',
    'primary': '#B8956A',
    'primary_hover': '#C9A67E',
    'primary_container': '#2E2A24',
    'error': '#E86060',
    'error_container': '#2E1818',
    'on_surface': '#E8E5E0',
    'on_surface_variant': '#9A928A',
    'outline': '#353330',
    'outline_strong': '#4A4742',
    'success': '#7DBD7D',
    'success_container': '#1A241A',
    'warning': '#C9A67E',
    'warning_container': '#2A241A',
    'nav_bg': '#1C1C1A',
    'nav_selected_bg': '#2E2A24',
    'nav_selected_text': '#B8956A',
    'card_bg': '#262522',
    'input_bg': '#262522',
    'switch_off': '#4A4742',
    'switch_knob': '#E8E5E0',
    'monospace': "Consolas, 'Cascadia Code', 'Courier New', monospace",
}


class ThemeEngine:
    _instance: ThemeEngine | None = None

    def __init__(self):
        self._mode: str = 'light'
        self._tokens: dict[str, str] = dict(TOKENS_LIGHT)

    @classmethod
    def instance(cls) -> ThemeEngine:
        if cls._instance is None:
            cls._instance = ThemeEngine()
        return cls._instance

    @property
    def tokens(self) -> dict[str, str]:
        return dict(self._tokens)

    @property
    def mode(self) -> str:
        return self._mode

    def apply(self, mode: str, qapp: QApplication) -> None:
        self._mode = mode
        self._tokens = dict(TOKENS_LIGHT if mode == 'light' else TOKENS_DARK)
        qapp.setPalette(self._palette())
        if getattr(sys, 'frozen', False):
            res_dir = Path(sys.executable).parent / 'gui' / 'resources'
        else:
            res_dir = Path(__file__).parent / 'resources'
        # Load base.qss first, then theme-specific color overrides
        qss_parts = []
        base_path = res_dir / 'base.qss'
        if base_path.exists():
            qss_parts.append(base_path.read_text(encoding='utf-8'))
        theme_path = res_dir / f'{mode}.qss'
        if theme_path.exists():
            qss_parts.append(theme_path.read_text(encoding='utf-8'))
        qapp.setStyleSheet('\n'.join(qss_parts))

    def _palette(self) -> QPalette:
        p = QPalette()
        t = self._tokens
        p.setColor(QPalette.ColorRole.Window, QColor(t['surface']))
        p.setColor(QPalette.ColorRole.WindowText, QColor(t['on_surface']))
        p.setColor(QPalette.ColorRole.Base, QColor(t['input_bg']))
        p.setColor(QPalette.ColorRole.Text, QColor(t['on_surface']))
        p.setColor(QPalette.ColorRole.Button, QColor(t['surface_alt']))
        p.setColor(QPalette.ColorRole.ButtonText, QColor(t['on_surface']))
        p.setColor(QPalette.ColorRole.Highlight, QColor(t['primary']))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor(t['on_surface']))
        p.setColor(QPalette.ColorRole.Link, QColor(t['primary']))
        return p

    def apply_widget(self, widget, qss: str) -> None:
        widget.setStyleSheet(qss.format(**self._tokens))
