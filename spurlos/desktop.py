"""Spurlos als Mac-Programm mit eigenem Fenster.

Startet denselben lokalen Server wie die Terminal-Fassung und zeigt die
Oberfläche in einem Programmfenster (pywebview, WKWebView) statt im Browser.
Solange das Fenster offen ist, verschickt Spurlos Anfragen und ruft das
Postfach ab.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import os
import sys
import tempfile
import urllib.request

from . import __version__


GERMAN = {
    "global.quitConfirmation": "Spurlos beenden? Solange Spurlos geschlossen ist, verschickt es keine Anfragen "
                               "und ruft das Postfach nicht ab. Beim nächsten Start macht es weiter.",
    "global.ok": "OK",
    "global.quit": "Beenden",
    "global.cancel": "Abbrechen",
    "global.saveFile": "Datei sichern",
    "cocoa.menu.about": "Über Spurlos",
    "cocoa.menu.services": "Dienste",
    "cocoa.menu.view": "Darstellung",
    "cocoa.menu.edit": "Bearbeiten",
    "cocoa.menu.hide": "Spurlos ausblenden",
    "cocoa.menu.hideOthers": "Andere ausblenden",
    "cocoa.menu.showAll": "Alle einblenden",
    "cocoa.menu.quit": "Spurlos beenden",
    "cocoa.menu.fullscreen": "Vollbildmodus",
    "cocoa.menu.cut": "Ausschneiden",
    "cocoa.menu.copy": "Kopieren",
    "cocoa.menu.paste": "Einsetzen",
    "cocoa.menu.selectAll": "Alles auswählen",
}


def selftest() -> int:
    """Prüft das fertig gebaute Programm, ohne ein Fenster zu öffnen.

    Wird beim automatischen Bauen aufgerufen: startet den Server mit einem
    leeren Testordner und lädt Oberfläche, Firmenliste und Startseite.
    """
    os.environ["SPURLOS_HOME"] = tempfile.mkdtemp(prefix="spurlos-selftest-")
    os.environ["SPURLOS_FILE_SECRETS"] = "1"
    from . import brokers, db, server

    run = server.start(18765, with_scheduler=False)
    try:
        base = "http://127.0.0.1:%d" % run.port
        # Mit Cookie-Speicher, wie das Programmfenster: der Start-Link setzt das Zugangs-Cookie.
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        for path in ("/static/app.css", "/static/app.js", "/?t=" + run.url.split("?t=")[1]):
            with opener.open(base + path, timeout=10) as resp:
                if resp.status != 200 or not resp.read():
                    raise RuntimeError("leer: " + path)
        count = db.query_one("SELECT COUNT(*) AS n FROM brokers")["n"]
        if count < 100:
            raise RuntimeError("Firmenliste zu kurz: %d" % count)
        print("Selbsttest OK: Spurlos %s, %d Firmen, %s" % (__version__, count, brokers.__name__))
        return 0
    finally:
        run.stop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="Spurlos")
    parser.add_argument("--selftest", action="store_true", help="Programm prüfen und beenden")
    args, _unknown = parser.parse_known_args(argv)   # macOS hängt manchmal eigene Argumente an
    if args.selftest:
        return selftest()

    import webview  # erst hier: wird für den Selbsttest nicht gebraucht

    from . import server

    lock = server.acquire_lock()
    run = None
    if lock is None:
        # Läuft schon (z. B. die Terminal-Fassung): dessen Oberfläche im Fenster zeigen.
        info = server.existing_instance()
        if not info:
            return 0
        url = server.url_for(info)
    else:
        run = server.start(8765)
        url = run.url

    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # Links zu Webformularen im Browser öffnen
    webview.settings["ALLOW_DOWNLOADS"] = True                    # Sicherungen und Beschwerde-Texte speichern
    webview.create_window("Spurlos", url, width=1280, height=860, min_size=(960, 640), text_select=True,
                          confirm_close=True, localization=GERMAN)
    try:
        webview.start()
    finally:
        if run:
            run.stop()
        if lock:
            lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
