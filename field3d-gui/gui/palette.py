"""
Colour palette — shared CSS strings and OpenGL RGBA tuples.
All Qt widgets reference these constants so restyling is one-place.
"""

# ── Qt / CSS strings ─────────────────────────────────────────────────────────
BG        = "#070D16"
PANEL     = "#0D1B2A"
CARD      = "#112234"
BORDER    = "#1C3A52"
BORDER2   = "#254B68"
TEXT      = "#C8E4F0"
DIM       = "#5A7E96"
ACCENT    = "#1A9FE0"
ACTIVE    = "#43C759"
ALERT_COL = "#EF5350"
WARN      = "#FF9800"
ROVER_COL = "#69F0AE"
SENSOR_COL= "#40C4FF"
INTRUDER  = "#FF5252"

# tooltip / hover
HOVER     = "#1A3A55"

# ── OpenGL background (normalised RGBA) ───────────────────────────────────────
GL_BG     = (0.028, 0.051, 0.087, 1.0)

# ── Entity colours for the 3D view (RGBA float32) ────────────────────────────
GL_ROVER    = (0.41, 0.94, 0.50, 1.0)
GL_SENSOR   = (0.25, 0.77, 1.00, 1.0)
GL_SENSOR_ALERT = (1.0, 0.30, 0.25, 1.0)
GL_INTRUDER = (1.00, 0.22, 0.18, 1.0)

# ── top-bar chip ─────────────────────────────────────────────────────────────
CHIP_KEY   = DIM
CHIP_VAL   = TEXT

# ── stylesheet fragments ─────────────────────────────────────────────────────
BASE_SS = f"""
    QWidget    {{ background: {BG}; color: {TEXT}; font-family: 'Liberation Mono', monospace; font-size: 12px; }}
    QFrame     {{ background: {PANEL}; border: 1px solid {BORDER}; }}
    QLabel     {{ background: transparent; }}
    QScrollBar:vertical   {{ background: {PANEL}; width: 7px; }}
    QScrollBar::handle:vertical {{ background: {BORDER2}; border-radius: 3px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QPlainTextEdit {{ background: {BG}; color: {TEXT}; border: none; font-size: 11px; }}
    QTreeWidget   {{ background: {BG}; color: {TEXT}; border: none; font-size: 11px;
                     alternate-background-color: {CARD}; }}
    QTreeWidget::item:selected {{ background: {ACCENT}; color: #FFFFFF; }}
    QHeaderView::section {{ background: {PANEL}; color: {DIM}; border: none;
                            border-bottom: 1px solid {BORDER}; padding: 3px 6px; font-size: 10px; }}
    QPushButton {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};
                   padding: 4px 10px; border-radius: 3px; }}
    QPushButton:hover {{ background: {HOVER}; border-color: {ACCENT}; }}
    QPushButton:checked {{ background: {ACCENT}; color: #FFFFFF; border-color: #64C8F0; }}
"""
