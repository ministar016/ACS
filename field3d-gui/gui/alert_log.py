"""
AlertLog — scrollable right-sidebar showing timestamped detection alerts.

New alerts from ScenarioSnapshot.alerts are appended with colour-coded
text (RED for contacts, YELLOW for warnings).  The log auto-scrolls to
the latest entry and keeps a maximum of MAX_LINES visible lines.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPlainTextEdit
from PyQt6.QtGui     import QTextCharFormat, QColor, QTextCursor
from PyQt6.QtCore    import Qt

from sim.scenario import ScenarioSnapshot
from .palette     import PANEL, BORDER, DIM, TEXT, ALERT_COL, WARN, ACTIVE, ACCENT

MAX_LINES = 120


class AlertLog(QWidget):
    """Narrow right panel (~260 px) with live alert feed."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(264)
        self.setStyleSheet(f"background: {PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QLabel("  ALERT LOG")
        hdr.setStyleSheet(
            f"background: #091420; color: {DIM}; padding: 6px 8px;"
            f" font-size: 10px; letter-spacing: 1px;"
            f" border-bottom: 1px solid {BORDER};"
        )
        layout.addWidget(hdr)

        # Text area
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(MAX_LINES)
        self._log.document().setMaximumBlockCount(MAX_LINES)
        self._log.setStyleSheet(
            f"QPlainTextEdit {{ background: #060D18; color: {TEXT};"
            f"  border: none; font-family: 'Liberation Mono', monospace;"
            f"  font-size: 11px; padding: 4px 6px; }}"
        )
        layout.addWidget(self._log)

        # Summary footer
        self._footer = QLabel("  0 total events")
        self._footer.setStyleSheet(
            f"background: #091420; color: {DIM}; padding: 4px 8px;"
            f" font-size: 10px; border-top: 1px solid {BORDER};"
        )
        layout.addWidget(self._footer)

        self._total = 0

    # ── public ────────────────────────────────────────────────────────────────

    def update_snapshot(self, snap: ScenarioSnapshot) -> None:
        if not snap.alerts:
            return
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        for msg in snap.alerts:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(
                ALERT_COL if "CONTACT" in msg else
                WARN      if "WARNING" in msg else TEXT
            ))
            cursor.insertText(msg + "\n", fmt)
            self._total += 1

        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()
        self._footer.setText(f"  {self._total} total events")
