"""
Generate the map icons (icons/<shape>_<colour>.svg) — plain top-down
silhouettes without a symbol frame, nose up (north), so the map can rotate
movers to their heading.  The NATO frames (symbols/*.svg) are shown in the
side lists instead.

    cd amcs-gui && .venv/bin/python packaging/make_icons.py
"""
from __future__ import annotations
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "icons"

COLOURS = {
    "hostile": "#E53935",
    "suspect": "#FFB300",
    "neutral": "#43A047",
    "unknown": "#CFD8DC",
    "friend":  "#29B6F6",
    "dead":    "#8D9399",
}
EDGE = "#0B1622"

# 64×64 viewBox, centred on (32, 32), nose toward y = 0.  {c} = fill colour.
SHAPES = {
    "quad": """
      <g stroke="{e}" stroke-width="2.2">
        <line x1="14" y1="14" x2="50" y2="50" stroke-width="7" stroke-linecap="round"/>
        <line x1="50" y1="14" x2="14" y2="50" stroke-width="7" stroke-linecap="round"/>
        <line x1="14" y1="14" x2="50" y2="50" stroke="{c}" stroke-width="3.6" stroke-linecap="round"/>
        <line x1="50" y1="14" x2="14" y2="50" stroke="{c}" stroke-width="3.6" stroke-linecap="round"/>
        <circle cx="14" cy="14" r="9" fill="{c}" fill-opacity="0.55"/>
        <circle cx="50" cy="14" r="9" fill="{c}" fill-opacity="0.55"/>
        <circle cx="14" cy="50" r="9" fill="{c}" fill-opacity="0.55"/>
        <circle cx="50" cy="50" r="9" fill="{c}" fill-opacity="0.55"/>
        <rect x="25" y="23" width="14" height="18" rx="4" fill="{c}"/>
        <path d="M28 23 L32 17 L36 23 Z" fill="{c}"/>
      </g>""",
    "wing": """
      <path d="M32 4 C35 4 36 9 36 14 L36 25 L61 33 L61 38 L36 34 L35 50 L44 55 L44 59 L32 57 L20 59 L20 55
               L29 50 L28 34 L3 38 L3 33 L28 25 L28 14 C28 9 29 4 32 4 Z"
            fill="{c}" stroke="{e}" stroke-width="2.2" stroke-linejoin="round"/>""",
    "helo": """
      <g stroke="{e}" stroke-width="2.2">
        <circle cx="32" cy="24" r="21" fill="{c}" fill-opacity="0.18"/>
        <rect x="30" y="34" width="4" height="24" fill="{c}"/>
        <rect x="24" y="54" width="16" height="4" fill="{c}"/>
        <ellipse cx="32" cy="25" rx="8" ry="14" fill="{c}"/>
        <line x1="12" y1="5" x2="52" y2="45" stroke-width="2"/>
        <line x1="52" y1="5" x2="12" y2="45" stroke-width="2"/>
      </g>""",
    "truck": """
      <g stroke="{e}" stroke-width="2.2" stroke-linejoin="round">
        <rect x="18" y="22" width="28" height="36" rx="2" fill="{c}"/>
        <rect x="20" y="6" width="24" height="14" rx="3" fill="{c}"/>
        <rect x="23" y="8" width="18" height="5" fill="{e}" fill-opacity="0.55" stroke="none"/>
        <line x1="18" y1="34" x2="46" y2="34"/>
        <line x1="18" y1="46" x2="46" y2="46"/>
      </g>""",
    "ugv": """
      <g stroke="{e}" stroke-width="2.2" stroke-linejoin="round">
        <rect x="12" y="10" width="10" height="46" rx="3" fill="#37474F"/>
        <rect x="42" y="10" width="10" height="46" rx="3" fill="#37474F"/>
        <rect x="20" y="14" width="24" height="38" rx="3" fill="{c}"/>
        <rect x="25" y="12" width="14" height="6" fill="{c}"/>
        <circle cx="32" cy="38" r="4" fill="#FFFFFF"/>
        <path d="M24 14 L32 6 L40 14" fill="none" stroke="{c}" stroke-width="3"/>
      </g>""",
    "sam": """
      <g stroke="{e}" stroke-width="2.2" stroke-linejoin="round">
        <rect x="14" y="18" width="36" height="40" rx="3" fill="{c}"/>
        <rect x="20" y="4" width="5" height="26" rx="2" fill="#ECEFF1"/>
        <rect x="27" y="4" width="5" height="26" rx="2" fill="#ECEFF1"/>
        <rect x="34" y="4" width="5" height="26" rx="2" fill="#ECEFF1"/>
        <rect x="41" y="4" width="5" height="26" rx="2" fill="#ECEFF1" visibility="hidden"/>
        <circle cx="32" cy="44" r="7" fill="{e}" fill-opacity="0.35"/>
      </g>""",
    "spaag": """
      <g stroke="{e}" stroke-width="2.2" stroke-linejoin="round">
        <rect x="14" y="18" width="36" height="40" rx="3" fill="{c}"/>
        <circle cx="32" cy="38" r="11" fill="{c}"/>
        <rect x="30" y="2" width="4" height="28" fill="#263238"/>
        <rect x="16" y="22" width="5" height="16" rx="2" fill="#ECEFF1"/>
        <rect x="43" y="22" width="5" height="16" rx="2" fill="#ECEFF1"/>
      </g>""",
    "ssm": """
      <g stroke="{e}" stroke-width="2.2" stroke-linejoin="round">
        <rect x="18" y="20" width="28" height="38" rx="2" fill="{c}"/>
        <rect x="20" y="6" width="24" height="12" rx="3" fill="{c}"/>
        <rect x="21" y="25" width="22" height="28" fill="#ECEFF1"/>
        <line x1="28" y1="25" x2="28" y2="53"/>
        <line x1="36" y1="25" x2="36" y2="53"/>
      </g>""",
    "radar": """
      <g stroke="{e}" stroke-width="2.2" stroke-linejoin="round" fill="none">
        <path d="M14 30 A20 20 0 0 1 50 30 L32 44 Z" fill="{c}"/>
        <line x1="32" y1="44" x2="32" y2="58" stroke-width="4"/>
        <line x1="32" y1="44" x2="32" y2="58" stroke="{c}" stroke-width="2"/>
        <path d="M22 58 L42 58" stroke-width="4"/>
        <path d="M41 14 A14 14 0 0 1 52 8" stroke="{c}" stroke-width="2.5"/>
        <path d="M45 21 A20 20 0 0 1 58 13" stroke="{c}" stroke-width="2.5"/>
      </g>""",
    "acoustic": """
      <g stroke="{e}" stroke-width="2.2" fill="none">
        <circle cx="32" cy="32" r="9" fill="{c}"/>
        <path d="M18 18 A20 20 0 0 0 18 46" stroke="{c}" stroke-width="3"/>
        <path d="M46 18 A20 20 0 0 1 46 46" stroke="{c}" stroke-width="3"/>
        <path d="M10 10 A31 31 0 0 0 10 54" stroke="{c}" stroke-width="2.5" stroke-opacity="0.7"/>
        <path d="M54 10 A31 31 0 0 1 54 54" stroke="{c}" stroke-width="2.5" stroke-opacity="0.7"/>
      </g>""",
    "seismic": """
      <g stroke="{e}" stroke-width="2.2" stroke-linejoin="round">
        <rect x="16" y="16" width="32" height="32" rx="6" fill="{c}" transform="rotate(45 32 32)"/>
        <path d="M14 34 L22 34 L26 24 L32 44 L37 28 L41 34 L50 34" fill="none" stroke="{e}" stroke-width="3"/>
      </g>""",
    "base": """
      <g stroke="{e}" stroke-width="2.2" stroke-linejoin="round">
        <path d="M32 4 L39 23 L59 23 L43 35 L49 55 L32 43 L15 55 L21 35 L5 23 L25 23 Z" fill="{c}"/>
      </g>""",
}
# which colours each shape is generated in
VARIANTS = {
    "quad": COLOURS, "wing": COLOURS, "helo": COLOURS, "truck": COLOURS, "ugv": COLOURS,
    "sam": ("friend", "dead"), "spaag": ("friend", "dead"), "ssm": ("friend", "dead"),
    "radar": ("friend", "dead"), "acoustic": ("friend", "suspect"), "seismic": ("friend", "suspect"),
    "base": ("friend",),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    n = 0
    for shape, colours in VARIANTS.items():
        for key in colours:
            body = SHAPES[shape].format(c=COLOURS[key], e=EDGE)
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
                   f'{body}</svg>\n')
            (OUT / f"{shape}_{key}.svg").write_text(svg, encoding="utf-8")
            n += 1
    print(f"{n} icons → {OUT}")


if __name__ == "__main__":
    main()
