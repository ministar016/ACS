"""
Generate the map symbols (symbols/*.svg) — NATO joint military symbology
(APP-6 / MIL-STD-2525C) rendered by milsymbol (MIT, www.spatialillusions.com).

milsymbol runs inside Qt's own JavaScript engine, so no Node.js is needed:

    cd amcs-gui && .venv/bin/python packaging/make_symbols.py

The SVGs are committed; the app only reads them.  Re-run after changing
SYMBOLS.  Frame shape / fill give the identity (friend blue rectangle /
circle, hostile red diamond, neutral green square, unknown yellow
quatrefoil), the icon the platform type.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_LOGGING_RULES", "qt.qml.usedbeforedeclared=false")
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtQml import QJSEngine

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "symbols"
MILSYMBOL = "https://cdn.jsdelivr.net/npm/milsymbol@2.2.0/dist/milsymbol.js"

# name → 2525C SIDC (15 characters)
SYMBOLS = {
    # air tracks / platforms
    "air_hostile_uav":   "SHAPMFQ--------",   # hostile military UAV
    "air_hostile_helo":  "SHAPMHA--------",   # hostile attack helicopter
    "air_suspect_uav":   "SSAPMFQ--------",   # suspect UAV
    "air_neutral_uav":   "SNAPMFQ--------",   # neutral UAV
    "air_unknown":       "SUAP-----------",   # unknown air track
    "air_friend_uav":    "SFAPMFQ--------",   # own interceptor drone
    # ground tracks / platforms
    "gnd_hostile_truck": "SHGPEVUT-------",   # hostile utility truck
    "gnd_suspect_truck": "SSGPEVUT-------",
    "gnd_unknown":       "SUGPE----------",   # unknown ground equipment
    "gnd_friend_ugv":    "SFGPEVUR-------",   # own UGV (jammer / charges)
    # sites
    "site_pvo_sam":      "SFGPUCDM-------",   # air defence missile unit
    "site_pvo_gun":      "SFGPUCDG-------",   # air defence gun(-missile) unit
    "site_ssm":          "SFGPEWMS-------",   # surface-to-surface missile launcher (ALAS)
    "site_radar":        "SFGPESR--------",   # ground radar
    "site_sensor":       "SFGPESE--------",   # emplaced sensor (acoustic / seismic)
    "site_base":         "SFGPI-----H----",   # installation / HQ
}
SIZE = 60          # px for the base frame; the map scales it down


def _engine() -> QJSEngine:
    cache = Path(os.environ.get("TMPDIR", "/tmp")) / "milsymbol-2.2.0.js"
    if not cache.exists():
        with urllib.request.urlopen(MILSYMBOL, timeout=60) as resp:
            cache.write_bytes(resp.read())
    e = QJSEngine()
    r = e.evaluate("var module = {exports: {}}; var exports = module.exports; var window = this; var self = this;\n"
                   + cache.read_text(encoding="utf-8"))
    if r.isError():
        raise RuntimeError(r.toString())
    e.evaluate("var ms = module.exports.Symbol ? module.exports : this.ms;")
    return e


def main() -> int:
    app = QCoreApplication(sys.argv)
    e = _engine()
    OUT.mkdir(exist_ok=True)
    meta = {}
    for name, sidc in SYMBOLS.items():
        r = e.evaluate(f"var s = new ms.Symbol('{sidc}', {{size: {SIZE}, outlineWidth: 3, outlineColor: 'rgb(0,0,0)'}});"
                       "JSON.stringify([s.asSVG(), s.isValid(), s.getAnchor(), s.getSize()])")
        svg, ok, anchor, size = json.loads(r.toString())
        if not ok:
            raise SystemExit(f"invalid SIDC {sidc} for {name}")
        (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
        meta[name] = {"sidc": sidc, "w": size["width"], "h": size["height"],
                      "ax": anchor["x"], "ay": anchor["y"]}
    (OUT / "symbols.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{len(meta)} symbols → {OUT}")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
