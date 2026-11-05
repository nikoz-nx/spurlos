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


def setup_notifications():
    """Mitteilungen als „Spurlos“ statt über den Script Editor. Nur in der fertigen App möglich."""
    if not getattr(sys, "frozen", False):
        return
    try:
        from UserNotifications import (UNUserNotificationCenter, UNMutableNotificationContent,
                                       UNNotificationRequest, UNAuthorizationOptionAlert, UNAuthorizationOptionSound)
        import uuid
        center = UNUserNotificationCenter.currentNotificationCenter()
        center.requestAuthorizationWithOptions_completionHandler_(
            UNAuthorizationOptionAlert | UNAuthorizationOptionSound, lambda granted, error: None)

        def notifier(text: str) -> bool:
            content = UNMutableNotificationContent.alloc().init()
            content.setTitle_("Spurlos")
            content.setBody_(text)
            req = UNNotificationRequest.requestWithIdentifier_content_trigger_(str(uuid.uuid4()), content, None)
            center.addNotificationRequest_withCompletionHandler_(req, lambda error: None)
            return True

        from . import engine
        engine.NOTIFIER = notifier
    except Exception:  # noqa: BLE001
        pass   # dann weiter über osascript


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

    def save_backup(self, text: str, filename: str):
        """Sichern-Dialog des Macs; schreibt die Datei und meldet den Pfad zurück (oder None)."""
        import webview
        from pathlib import Path
        if not self.window or not isinstance(text, str):
            return None
        downloads = str(Path.home() / "Downloads")
        result = self.window.create_file_dialog(webview.SAVE_DIALOG, directory=downloads, save_filename=str(filename))
        if not result:
            return None
        path = result[0] if isinstance(result, (list, tuple)) else result
        Path(path).write_text(text, encoding="utf-8")
        return str(path)


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

    from . import config, engine, server

    state = {"run": None, "lock": None}
    api = Api("")
    _activity = keep_awake()  # noqa: F841 – Referenz halten, solange die App läuft
    setup_notifications()
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # Links zu Webformularen im Browser öffnen
    webview.settings["ALLOW_DOWNLOADS"] = True                    # Beschwerde-Texte speichern

    geo = _load_window_geometry(config)
    window = webview.create_window("Spurlos", html=LOADING_HTML, width=geo["w"], height=geo["h"], x=geo.get("x"), y=geo.get("y"),
                                   min_size=(960, 640), text_select=True, zoomable=True, js_api=api, localization=GERMAN)
    api.window = window

    def start_server():
        # Läuft, sobald das Fenster steht: Datenbank öffnen, Server starten, Oberfläche laden.
        try:
            lock = server.acquire_lock()
            if lock is None:
                info = server.existing_instance()
                if not info:
                    window.load_html(_error_html("Spurlos läuft schon",
                                                 "Ein anderes Spurlos scheint zu laufen, antwortet aber nicht. "
                                                 "Beende es (z. B. das Terminal-Fenster) und starte Spurlos danach noch einmal."))
                    return
                url = server.url_for(info)
            else:
                state["lock"] = lock
                state["run"] = server.start(8765)
                url = state["run"].url
            api.url = url
            window.load_url(url)
        except Exception as exc:  # noqa: BLE001
            import logging
            import traceback
            logging.getLogger("spurlos").error("Start fehlgeschlagen:\n%s", traceback.format_exc())
            window.load_html(_error_html("Spurlos konnte nicht starten", str(exc)[:300] +
                                         " – Das Protokoll liegt unter Library › Application Support › Spurlos › spurlos.log."))

    def shutdown():
        # Bei ⌘Q, „Beenden“ im Menü oder Abmelden, bevor macOS den Prozess beendet:
        # laufende Mail zu Ende schicken, dann aufräumen. Kein Rückfrage-Dialog, der das Abmelden blockiert.
        engine.STOP.set()
        run = state["run"]
        if run:
            _save_window_geometry(config, window)
            got = engine._RUN_LOCK.acquire(timeout=25)
            try:
                run.stop()
            finally:
                if got:
                    engine._RUN_LOCK.release()
        if state["lock"]:
            state["lock"].close()

    def closing():
        # Rotes Schließen-Feld: Fenster nur ausblenden, Spurlos arbeitet im Hintergrund weiter
        # (Versand, Postfach, Erinnerungen). Ein Klick aufs Dock-Symbol holt das Fenster zurück.
        if state["quit"] or not state["run"]:
            shutdown()
            return None
        _save_window_geometry(config, window)
        state["hidden"] = True
        window.minimize()   # ins Dock, nicht weg: ein Klick aufs Symbol holt es zurück
        _first_hide_hint(engine)
        return False

    state["quit"] = False
    state["hidden"] = False
    _hook_quit(state)
    _hook_reopen(window, state)
    _show_on_activate(window, state)
    window.events.closing += closing
    webview.start(func=start_server)
    return 0


def _hook_quit(state: dict) -> None:
    """Unterscheiden, ob macOS die App beenden will (⌘Q, Menü, Abmelden) oder nur das Fenster zugeht.

    pywebview fragt in beiden Fällen dieselbe Funktion. Beim Beenden kommt der Aufruf aus
    applicationShouldTerminate_, beim Schließen-Feld aus windowShouldClose_."""
    try:
        from webview.platforms import cocoa
    except Exception:  # noqa: BLE001
        return
    original = cocoa.BrowserView.should_close

    def should_close(window):
        caller = sys._getframe(1).f_code.co_name
        state["quit"] = caller != "windowShouldClose_"
        return original(window)

    cocoa.BrowserView.should_close = staticmethod(should_close)


def _hook_reopen(window, state: dict) -> None:
    """Klick aufs Dock-Symbol: Fenster zurückholen, auch wenn Spurlos schon die aktive App ist."""
    try:
        import objc
        from webview.platforms import cocoa

        def applicationShouldHandleReopen_hasVisibleWindows_(self, app, has_visible):
            if not has_visible and not state.get("quit"):
                _bring_back(window, state)
            return True

        sig = objc._C_NSBOOL + b"@:@" + objc._C_NSBOOL
        objc.classAddMethods(cocoa.BrowserView.AppDelegate, [
            objc.selector(applicationShouldHandleReopen_hasVisibleWindows_,
                          selector=b"applicationShouldHandleReopen:hasVisibleWindows:", signature=sig)])
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("spurlos").warning("Dock-Reopen nicht verfügbar", exc_info=True)


def _bring_back(window, state: dict) -> None:
    state["hidden"] = False
    try:
        window.restore()
    except Exception:  # noqa: BLE001
        pass
    try:
        window.show()
    except Exception:  # noqa: BLE001
        pass


def _show_on_activate(window, state: dict) -> None:
    """Fenster wieder zeigen, wenn die App aktiv wird (Klick aufs Dock-Symbol, ⌘-Tab)."""
    try:
        import AppKit
        from Foundation import NSObject, NSNotificationCenter

        class Reopen(NSObject):
            def activated_(self, note):
                if state.get("hidden") and not state.get("quit"):
                    _bring_back(window, state)

        state["_reopen"] = Reopen.alloc().init()
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            state["_reopen"], "activated:", AppKit.NSApplicationDidBecomeActiveNotification, None)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("spurlos").warning("Dock-Klick zum Wiederöffnen nicht verfügbar", exc_info=True)


def _first_hide_hint(engine) -> None:
    """Einmalig erklären, dass Spurlos weiterläuft."""
    from . import db
    try:
        if db.get("hide_hint_shown"):
            return
        db.put("hide_hint_shown", True)
        engine.notify("Spurlos läuft im Hintergrund weiter. Klick aufs Dock-Symbol zeigt das Fenster, "
                      "Beenden geht über das Menü Spurlos.")
    except Exception:  # noqa: BLE001
        pass


LOADING_HTML = """<!doctype html><html lang="de"><meta charset="utf-8"><body style="margin:0;height:100vh;display:flex;align-items:center;
justify-content:center;font-family:-apple-system,system-ui;background:#F4F5F7;color:#5B6472"><div style="text-align:center">
<div style="width:28px;height:28px;border:3px solid #D5DAE2;border-top-color:#1F8A5B;border-radius:50%;margin:0 auto 14px;
animation:s .8s linear infinite"></div>Spurlos startet …</div><style>@keyframes s{to{transform:rotate(360deg)}}</style></body></html>"""


def _error_html(title: str, text: str) -> str:
    import html
    return ("<!doctype html><html lang=\"de\"><meta charset=\"utf-8\"><body style=\"margin:0;height:100vh;display:flex;align-items:center;"
            "justify-content:center;font-family:-apple-system,system-ui;background:#F4F5F7;color:#0E1116\">"
            "<div style=\"max-width:480px;padding:24px;text-align:center\"><h2 style=\"margin:0 0 8px\">%s</h2>"
            "<p style=\"color:#5B6472;line-height:1.5\">%s</p></div></body></html>" % (html.escape(title), html.escape(text)))


def _load_window_geometry(config) -> dict:
    import json
    geo = {"w": 1280, "h": 860}
    try:
        saved = json.loads((config.data_dir() / "window.json").read_text(encoding="utf-8"))
        if 960 <= int(saved.get("w", 0)) <= 6000 and 640 <= int(saved.get("h", 0)) <= 4000:
            geo.update({"w": int(saved["w"]), "h": int(saved["h"])})
            if isinstance(saved.get("x"), int) and isinstance(saved.get("y"), int):
                geo.update({"x": saved["x"], "y": saved["y"]})
    except Exception:  # noqa: BLE001
        pass
    return geo


def _save_window_geometry(config, window) -> None:
    import json
    try:
        (config.data_dir() / "window.json").write_text(json.dumps({
            "w": int(window.width), "h": int(window.height), "x": int(window.x), "y": int(window.y)}), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.exit(main())
