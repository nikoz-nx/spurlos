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

CERTS = "Python"


def use_mac_certificates() -> str:
    """Zertifikate für verschlüsselte Verbindungen (Mailserver, Firmenliste, Cloud-KI).

    In der fertigen App findet Python die Zertifikate des Macs nicht von selbst.
    truststore nutzt die Zertifikatsverwaltung von macOS, certifi ist die Notlösung.
    Gilt für alle Verbindungen des Programms, nicht nur für E-Mail.
    """
    try:
        import truststore
        truststore.inject_into_ssl()
        return "macOS"
    except Exception:  # noqa: BLE001
        pass
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        return "certifi"
    except Exception:  # noqa: BLE001
        return "Python"


def keep_awake():
    """Verhindert, dass macOS die App im Hintergrund drosselt (App Nap).

    Sonst könnten Etappen verspätet rausgehen, sobald das Fenster verdeckt oder
    minimiert ist. Der Mac darf trotzdem normal in den Ruhezustand gehen.
    Gibt das Aktivitäts-Objekt zurück; es muss am Leben bleiben.
    """
    try:
        from Foundation import NSProcessInfo
        # NSActivityUserInitiatedAllowingIdleSystemSleep
        options = 0x00FFFFFF & ~0x00100000
        return NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            options, "Spurlos verschickt Anfragen und ruft das Postfach ab")
    except Exception:  # noqa: BLE001
        return None


def _check_tls() -> str:
    """Prüft eine verschlüsselte Verbindung (nur beim automatischen Bauen, braucht Internet)."""
    import socket
    import ssl
    ctx = ssl.create_default_context()
    with socket.create_connection(("imap.gmx.net", 993), timeout=15) as raw:
        with ctx.wrap_socket(raw, server_hostname="imap.gmx.net") as tls:
            return tls.version() or "TLS"


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
    from . import db, server

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
        tls = _check_tls() if os.environ.get("SPURLOS_SELFTEST_NET") == "1" else "nicht geprüft"
        print("Selbsttest OK: Spurlos %s, %d Firmen, Zertifikate: %s, Verbindung: %s"
              % (__version__, count, CERTS, tls))
        return 0
    finally:
        run.stop()


def setup_logging():
    """Protokoll in eine Datei: Aus dem Finder gestartet hat die App kein Terminal."""
    import faulthandler
    import logging
    from logging.handlers import RotatingFileHandler
    from . import config

    path = config.data_dir() / "spurlos.log"
    handler = RotatingFileHandler(str(path), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    try:
        crash = open(str(config.data_dir() / "spurlos-crash.log"), "a")
        faulthandler.enable(crash)
    except OSError:
        pass
    logging.getLogger("spurlos").info("Spurlos %s startet", __version__)
    return path


def show_error(title: str, text: str) -> None:
    """Fehlerdialog, damit ein Startproblem nicht stumm bleibt."""
    try:
        from AppKit import NSAlert, NSApplication
        NSApplication.sharedApplication()
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(text)
        alert.addButtonWithTitle_("OK")
        alert.runModal()
    except Exception:  # noqa: BLE001
        import subprocess
        try:
            subprocess.run(["osascript", "-e", "on run argv", "-e",
                            'display dialog (item 2 of argv) with title (item 1 of argv) buttons {"OK"} with icon stop',
                            "-e", "end run", title, text], timeout=60, capture_output=True)
        except Exception:  # noqa: BLE001
            print(title, text, file=sys.stderr)


class Api:
    """Kleine Brücke für die Oberfläche (window.pywebview.api)."""

    def __init__(self, url: str):
        self.url = url
        self.window = None

    def restart(self):
        """Oberfläche neu laden, mit Zugangs-Link – falls das Cookie mal weg ist."""
        if self.window:
            self.window.load_url(self.url)
        return True

    def open_url(self, url: str):
        import subprocess
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            subprocess.Popen(["open", url])
        return True

    def open_log(self):
        import subprocess
        from . import config
        subprocess.Popen(["open", "-R", str(config.data_dir() / "spurlos.log")])
        return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="Spurlos")
    parser.add_argument("--selftest", action="store_true", help="Programm prüfen und beenden")
    args, _unknown = parser.parse_known_args(argv)   # macOS hängt manchmal eigene Argumente an
    global CERTS
    CERTS = use_mac_certificates()
    if args.selftest:
        return selftest()
    try:
        return _run()
    except Exception as exc:  # noqa: BLE001
        import logging
        import traceback
        logging.getLogger("spurlos").error("Start fehlgeschlagen:\n%s", traceback.format_exc())
        show_error("Spurlos konnte nicht starten",
                   "%s\n\nDas Protokoll liegt unter Library › Application Support › Spurlos › spurlos.log."
                   % str(exc)[:300])
        return 1


def _run() -> int:
    setup_logging()
    import webview  # erst hier: wird für den Selbsttest nicht gebraucht

    from . import engine, server

    lock = server.acquire_lock()
    run = None
    if lock is None:
        # Läuft schon (z. B. die Terminal-Fassung): dessen Oberfläche im Fenster zeigen.
        info = server.existing_instance()
        if not info:
            show_error("Spurlos läuft schon",
                       "Ein anderes Spurlos scheint zu laufen, antwortet aber nicht. Beende es "
                       "(z. B. das Terminal-Fenster) und starte Spurlos danach noch einmal.")
            return 1
        url = server.url_for(info)
    else:
        run = server.start(8765)
        url = run.url

    _activity = keep_awake()  # noqa: F841 – Referenz halten, solange die App läuft
    api = Api(url)
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # Links zu Webformularen im Browser öffnen
    webview.settings["ALLOW_DOWNLOADS"] = True                    # Sicherungen und Beschwerde-Texte speichern
    window = webview.create_window("Spurlos", url, width=1280, height=860, min_size=(960, 640),
                                   text_select=True, zoomable=True, js_api=api, localization=GERMAN)
    api.window = window

    def closing():
        # Läuft bei Fensterschließen UND bei ⌘Q / Abmelden, bevor macOS den Prozess beendet:
        # laufende Mail zu Ende schicken, dann aufräumen. Kein Rückfrage-Dialog, der das Abmelden blockiert.
        engine.STOP.set()
        if run:
            got = engine._RUN_LOCK.acquire(timeout=25)
            try:
                run.stop()
            finally:
                if got:
                    engine._RUN_LOCK.release()
        if lock:
            lock.close()

    window.events.closing += closing
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
