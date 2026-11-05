"""Startet den lokalen Server und die Hintergrund-Abläufe.

Wird vom Terminal-Start (`python -m spurlos`) und von der Mac-App
(`spurlos.desktop`) gemeinsam genutzt.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import socket
import threading
import time
import urllib.request

from werkzeug.serving import make_server

from . import app as appmod, brokers, config, db, engine


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _instance_file():
    return config.data_dir() / "instance.json"


def acquire_lock():
    """Nur ein Spurlos gleichzeitig: sonst ginge jede Mail doppelt raus.

    Gibt die offene Sperrdatei zurück (muss offen bleiben) oder None, wenn
    schon ein anderes Spurlos läuft.
    """
    config.data_dir().mkdir(parents=True, exist_ok=True)
    lock_file = open(str(config.data_dir() / "spurlos.lock"), "a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        return None
    return lock_file


def existing_instance(wait_seconds: int = 30):
    """Adresse des schon laufenden Spurlos (wartet, falls es gerade startet)."""
    for _ in range(max(1, wait_seconds)):
        path = _instance_file()
        if path.exists():
            try:
                info = json.loads(path.read_text(encoding="utf-8"))
                # Ohne System-Proxy: Firmen-Macs leiten sonst auch 127.0.0.1 über den Proxy
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                opener.open("http://127.0.0.1:%d/static/app.css" % info["port"], timeout=2)
                return info
            except Exception:  # noqa: BLE001
                pass
        time.sleep(1)
    return None


def url_for(info: dict) -> str:
    return "http://127.0.0.1:%d/?t=%s" % (info["port"], info["token"])


class Running:
    """Ein laufender Server samt Hintergrund-Abläufen."""

    def __init__(self, server, thread, scheduler, port: int):
        self.server = server
        self.thread = thread
        self.scheduler = scheduler
        self.port = port
        self.url = url_for({"port": port, "token": appmod.TOKEN})

    def stop(self) -> None:
        if self.scheduler:
            self.scheduler.stop_event.set()
        try:
            self.server.shutdown()
        except Exception:  # noqa: BLE001
            pass
        try:
            _instance_file().unlink()
        except OSError:
            pass


def start(port: int = 8765, with_scheduler: bool = True) -> Running:
    """Datenbank öffnen, Server im Hintergrund starten, Abläufe anwerfen."""
    db.init()
    brokers.load_seed()

    first = port
    while not _port_free(port) and port < first + 20:
        port += 1
    appmod.PORT["value"] = port
    application = appmod.create_app()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    server = make_server("127.0.0.1", port, application, threaded=True)

    path = _instance_file()
    path.write_text(json.dumps({"port": port, "token": appmod.TOKEN, "pid": os.getpid()}), encoding="utf-8")
    os.chmod(path, 0o600)

    thread = threading.Thread(target=server.serve_forever, name="spurlos-server", daemon=True)
    thread.start()

    scheduler = None
    if with_scheduler:
        scheduler = engine.Scheduler()
        scheduler.start()
    return Running(server, thread, scheduler, port)
