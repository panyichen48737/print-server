"""Base class for all pages: eliminates repetitive scroll-area boilerplate."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


class PageBase(QWidget):
    """Base page with pre-configured scroll area, standard margins, and title support.

    Subclasses override ``_build_content(layout)`` instead of re-creating
    the scroll + container + margins pattern.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName('dashboardScroll')

        self._container = QWidget()
        self._content = QVBoxLayout(self._container)
        self._content.setContentsMargins(28, 28, 32, 28)
        self._content.setSpacing(12)

        self._build_content(self._content)
        self._content.addStretch()

        scroll.setWidget(self._container)
        main_layout.addWidget(scroll, 1)

    def set_page_title(self, text: str) -> QLabel:
        """Set or replace the page title label and return it."""
        lbl = QLabel(text)
        lbl.setObjectName('pageTitle')
        # Insert at position 0 if it doesn't exist yet
        item = self._content.itemAt(0)
        if item and item.widget() and item.widget().objectName() == 'pageTitle':
            item.widget().setText(text)
            return item.widget()
        self._content.insertWidget(0, lbl)
        return lbl

    def _build_content(self, layout: QVBoxLayout) -> None:
        """Override in subclasses to populate the page content area."""
