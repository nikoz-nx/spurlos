"""Startet Spurlos im Terminal: lokaler Server, Hintergrund-Abläufe und Browserfenster."""
from __future__ import annotations

import argparse
import sys
import webbrowser

from . import __version__, server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="spurlos", description="Spurlos – deine Daten zurückholen")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    parser.add_argument("--no-scheduler", action="store_true", help="Keine automatischen Abläufe (für Tests)")
    args = parser.parse_args(argv)

    lock = server.acquire_lock()
    if lock is None:
        print("Spurlos läuft bereits.")
        running = server.existing_instance()
        if running and not args.no_browser:
            webbrowser.open(server.url_for(running))
            print("Ich öffne das Fenster.")
        return 0

    run = server.start(args.port, with_scheduler=not args.no_scheduler)
    print("Spurlos %s läuft." % __version__)
    print("Fenster: %s" % run.url)
    print("Lass dieses Fenster offen, solange Spurlos arbeiten soll. Beenden mit Ctrl+C.")
    if not args.no_browser:
        webbrowser.open(run.url)
    try:
        while run.thread.is_alive():
            run.thread.join(0.5)
    except KeyboardInterrupt:
        print("\nSpurlos wird beendet.")
    finally:
        run.stop()
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
