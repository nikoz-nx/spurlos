"""Passwörter und API-Schlüssel im Schlüsselbund des Macs.

Auf dem Mac nutzt `keyring` den macOS-Schlüsselbund. Nur wenn kein
Schlüsselbund verfügbar ist (z. B. in Tests unter Linux), landen die Werte
in einer Datei mit Zugriff nur für den eigenen Benutzer.
"""
from __future__ import annotations

import json
import os

from . import config

SERVICE = "Spurlos"

try:  # pragma: no cover - abhängig von der Umgebung
    import keyring
    from keyring.errors import KeyringError
except Exception:  # noqa: BLE001
    keyring = None
    KeyringError = Exception


def _fallback_path():
    return config.data_dir() / ".secrets.json"


def _use_fallback() -> bool:
    if os.environ.get("SPURLOS_FILE_SECRETS") == "1" or keyring is None:
        return True
    try:
        backend = keyring.get_keyring()
        name = type(backend).__name__.lower()
        return "fail" in name or "null" in name
    except Exception:  # noqa: BLE001
        return True


def _read_fallback() -> dict:
    path = _fallback_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _write_fallback(data: dict) -> None:
    path = _fallback_path()
    path.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(path, 0o600)


def storage_name() -> str:
    return "Datei (nur für Tests)" if _use_fallback() else "Schlüsselbund"


def set_secret(name: str, value: str) -> None:
    if _use_fallback():
        data = _read_fallback()
        data[name] = value
        _write_fallback(data)
        return
    keyring.set_password(SERVICE, name, value)


def get_secret(name: str) -> str | None:
    if _use_fallback():
        return _read_fallback().get(name)
    try:
        return keyring.get_password(SERVICE, name)
    except KeyringError:
        return None


def delete_secret(name: str) -> None:
    if _use_fallback():
        data = _read_fallback()
        data.pop(name, None)
        _write_fallback(data)
        return
    try:
        keyring.delete_password(SERVICE, name)
    except Exception:  # noqa: BLE001
        pass
