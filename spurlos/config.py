"""Pfade und feste Werte."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Spurlos"
PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
SEED_DIR = PACKAGE_DIR / "data"


def data_dir() -> Path:
    """Ordner für Datenbank, Sicherungen und Laufzeitdateien."""
    env = os.environ.get("SPURLOS_HOME")
    if env:
        path = Path(env)
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "spurlos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "spurlos.sqlite3"
