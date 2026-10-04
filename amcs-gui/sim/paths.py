"""
Where AMCS reads and writes files — source checkout vs. packaged app.

Running from the repo (`./run.sh`) everything stays next to the code, as
before.  A packaged app (PyInstaller, e.g. AMCS.app on macOS) cannot write
into its own bundle and is started without a shell environment, so it uses
the platform's per-user folders instead:

                 macOS                                   Linux
  resources      bundle (sys._MEIPASS)                   bundle
  scenarios      ~/Library/Application Support/AMCS/…    ~/.local/share/amcs/scenarios
  cache          ~/Library/Caches/AMCS                   ~/.cache/amcs
  logs           ~/Library/Logs/AMCS                     ~/.local/share/amcs/logs
  config.env     ~/Library/Application Support/AMCS/     ~/.local/share/amcs/

config.env holds KEY=VALUE lines (ARTEMIDES_TOKEN=…, ARTEMIDES_URL=…) that
are applied to the environment at start-up unless already set — the way to
give a Finder-launched app its artemides token.
"""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path

_REPO_DIR = Path(__file__).resolve().parent.parent
_APP = "AMCS"


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Read-only files shipped with the app (QML, seed scenarios)."""
    return Path(getattr(sys, "_MEIPASS", _REPO_DIR))


def user_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / _APP
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "amcs"


def cache_dir() -> Path:
    if os.environ.get("AMCS_CACHE"):
        return Path(os.environ["AMCS_CACHE"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / _APP
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "amcs"


def log_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / _APP
    return user_data_dir() / "logs"


def config_file() -> Path:
    return user_data_dir() / "config.env"


def scenario_dir() -> Path:
    """Saved scenarios: next to the code from a checkout, per-user when packaged."""
    if os.environ.get("AMCS_SCENARIO_DIR"):
        return Path(os.environ["AMCS_SCENARIO_DIR"])
    if not frozen():
        return _REPO_DIR / "scenarios"
    target = user_data_dir() / "scenarios"
    if not target.exists():
        # First start of the packaged app: seed with the scenarios shipped in the bundle
        target.mkdir(parents=True, exist_ok=True)
        seed = resource_dir() / "scenarios"
        if seed.is_dir():
            for f in seed.iterdir():
                if f.is_file():
                    shutil.copy2(f, target / f.name)
    return target


_CONFIG_TEMPLATE = """\
# AMCS settings — KEY=VALUE, applied at start-up unless already set in the environment.
# artemides-trax link (default: the scenario's deployment, guest routing):
# ARTEMIDES_URL=https://vojsrb.artemides-trax.com
# ARTEMIDES_TOKEN=paste-token-from-account.php
# ARTEMIDES_TELEMETRY=0
# ARTEMIDES_PUBLISH_THREATS=0
"""


def load_config_env() -> Path:
    """Apply config.env to os.environ (existing variables win); create a template if missing."""
    path = config_file()
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_CONFIG_TEMPLATE, encoding="utf-8")
        except OSError:
            return path
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return path
