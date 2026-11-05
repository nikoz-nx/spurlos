"""Passwörter und API-Schlüssel im Schlüsselbund des Macs.

Auf dem Mac nutzt `keyring` den macOS-Schlüsselbund. Nur wenn kein
Schlüsselbund verfügbar ist (z. B. in Tests unter Linux), landen die Werte
in einer Datei mit Zugriff nur für den eigenen Benutzer.
"""
from __future__ import annotations

import json
import os
import sys

from . import config

SERVICE = "Spurlos"

try:  # pragma: no cover - abhängig von der Umgebung
    import keyring
    from keyring.errors import KeyringError
except Exception:  # noqa: BLE001
    keyring = None
    KeyringError = Exception

if keyring is not None and sys.platform == "darwin" and os.environ.get("SPURLOS_FILE_SECRETS") != "1":
    # In der fertigen Mac-App findet keyring seine Bausteine nicht immer von selbst.
    # Den Schlüsselbund fest einstellen, damit Passwörter nie in einer Datei landen.
    try:  # pragma: no cover - nur auf dem Mac
        from keyring.backends import macOS as _macos_backend
        keyring.set_keyring(_macos_backend.Keyring())
    except Exception:  # noqa: BLE001
        pass


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


# Einmal gelesene Werte bleiben im Speicher. Sonst fragt der Schlüsselbund jede Minute
# neu, wenn jemand bei der Rückfrage nur „Erlauben“ statt „Immer erlauben“ klickt.
_CACHE: dict = {}
# Letzter Fehler beim Zugriff auf den Schlüsselbund (None = alles gut). Zeigt die Oberfläche an.
LAST_ERROR = {"text": None}

KEYCHAIN_HINT = ("Spurlos darf nicht auf den Schlüsselbund zugreifen. Öffne die Schlüsselbundverwaltung, "
                 "such den Eintrag „Spurlos“ und erlaube Spurlos den Zugriff, oder trag das Passwort "
                 "in den Einstellungen neu ein.")


def set_secret(name: str, value: str) -> None:
    if _use_fallback():
        data = _read_fallback()
        data[name] = value
        _write_fallback(data)
        _CACHE[name] = value
        return
    try:
        keyring.set_password(SERVICE, name, value)
    except Exception as exc:  # noqa: BLE001  (KeyringLocked, PasswordSetError …)
        raise ValueError("Das Passwort konnte nicht im Schlüsselbund gespeichert werden (%s). "
                         "Entsperre den Schlüsselbund „Anmeldung“ und versuch es noch einmal." % str(exc)[:120])
    _CACHE[name] = value
    LAST_ERROR["text"] = None


def get_secret(name: str) -> str | None:
    if name in _CACHE:
        return _CACHE[name]
    if _use_fallback():
        value = _read_fallback().get(name)
    else:
        try:
            value = keyring.get_password(SERVICE, name)
            LAST_ERROR["text"] = None
        except Exception as exc:  # noqa: BLE001
            LAST_ERROR["text"] = KEYCHAIN_HINT + " (%s)" % str(exc)[:80]
            return None
    if value:
        _CACHE[name] = value
    return value


def delete_secret(name: str) -> None:
    _CACHE.pop(name, None)
    if _use_fallback():
        data = _read_fallback()
        data.pop(name, None)
        _write_fallback(data)
        return
    try:
        keyring.delete_password(SERVICE, name)
    except Exception:  # noqa: BLE001
        pass
