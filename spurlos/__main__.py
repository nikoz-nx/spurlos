"""Startet Spurlos: lokaler Server, Hintergrund-Abläufe und Browserfenster."""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import socket
import sys
import time
import urllib.request
import webbrowser

from werkzeug.serving import make_server

from . import __version__, app as appmod, brokers, config, db, engine


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _instance_file():
    return config.data_dir() / "instance.json"


def _existing_instance():
    path = _instance_file()
    if not path.exists():
        return None
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        urllib.request.urlopen("http://127.0.0.1:%d/static/app.css" % info["port"], timeout=2)
        return info
    except Exception:  # noqa: BLE001
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="spurlos", description="Spurlos – deine Daten zurückholen")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    parser.add_argument("--no-scheduler", action="store_true", help="Keine automatischen Abläufe (für Tests)")
    args = parser.parse_args(argv)

    # Nur ein Spurlos gleichzeitig: sonst ginge jede Mail doppelt raus.
    config.data_dir().mkdir(parents=True, exist_ok=True)
    lock_file = open(str(config.data_dir() / "spurlos.lock"), "a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Spurlos läuft bereits.")
        for _ in range(30):              # die andere Instanz startet evtl. gerade noch
            running = _existing_instance()
            if running:
                if not args.no_browser:
                    webbrowser.open("http://127.0.0.1:%d/?t=%s" % (running["port"], running["token"]))
                    print("Ich öffne das Fenster.")
                return 0
            time.sleep(1)
        return 0

    db.init()
    brokers.load_seed()

    port = args.port
    while not _port_free(port) and port < args.port + 20:
        port += 1
    appmod.PORT["value"] = port
    application = appmod.create_app()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    server = make_server("127.0.0.1", port, application, threaded=True)

    path = _instance_file()
    path.write_text(json.dumps({"port": port, "token": appmod.TOKEN, "pid": os.getpid()}), encoding="utf-8")
    os.chmod(path, 0o600)

    scheduler = None
    if not args.no_scheduler:
        scheduler = engine.Scheduler()
        scheduler.start()

    url = "http://127.0.0.1:%d/?t=%s" % (port, appmod.TOKEN)
    print("Spurlos %s läuft." % __version__)
    print("Fenster: %s" % url)
    print("Lass dieses Fenster offen, solange Spurlos arbeiten soll. Beenden mit Ctrl+C.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSpurlos wird beendet.")
    finally:
        if scheduler:
            scheduler.stop_event.set()
        try:
            path.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
