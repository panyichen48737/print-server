"""Design tokens for light/dark themes."""
from dataclasses import dataclass

import flet as ft


@dataclass
class ThemeTokens:
    surface: str
    primary: str
    primary_container: str
    error: str
    on_surface: str
    on_surface_variant: str
    outline: str
    success: str


LIGHT = ThemeTokens(
    surface="#FFFFFF",
    primary="#4F46E5",
    primary_container="#EEF2FF",
    error="#DC2626",
    on_surface="#1F2937",
    on_surface_variant="#6B7280",
    outline="#D1D5DB",
    success="#16A34A",
)

DARK = ThemeTokens(
    surface="#1E1E2E",
    primary="#818CF8",
    primary_container="#312E81",
    error="#F87171",
    on_surface="#E2E8F0",
    on_surface_variant="#94A3B8",
    outline="#4B5563",
    success="#4ADE80",
)


def build_theme(mode: ft.ThemeMode) -> ft.Theme:
    tokens = DARK if mode == ft.ThemeMode.DARK else LIGHT
    return ft.Theme(
        font_family="Microsoft YaHei",
        color_scheme=ft.ColorScheme(
            primary=tokens.primary,
            primary_container=tokens.primary_container,
            error=tokens.error,
            surface=tokens.surface,
            on_surface=tokens.on_surface,
            on_surface_variant=tokens.on_surface_variant,
            outline=tokens.outline,
        ),
    )


# Module-level dark mode flag, set by app.py main()
_IS_DARK: bool = False
