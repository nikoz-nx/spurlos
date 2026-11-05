"""Postfach: Versand per SMTP, Abruf per IMAP, Anbieter-Vorlagen."""
from __future__ import annotations

import email
import email.policy
import email.utils
import imaplib
import re
import smtplib
import socket
import ssl
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, make_msgid, parsedate_to_datetime
from html.parser import HTMLParser

# Name, mit dem sich Spurlos beim Mailserver meldet. Ohne Angabe fragt Python den Mac
# nach seinem Netzwerknamen: Das löst auf dem Mac die Frage nach „Geräten in lokalen
# Netzwerken“ aus und schickt den Gerätenamen (oft mit dem Vornamen) an den Mailserver.
HELO_NAME = "[127.0.0.1]"   # gültige Form nach RFC 5321, verrät nichts über den Mac
TIMEOUT = 30          # Lesen/Schreiben
CONNECT_TIMEOUT = 10  # je Adresse: Macs probieren IPv6 zuerst, auch wenn es nicht funktioniert


def _connect(host: str, port: int) -> socket.socket:
    """Wie socket.create_connection, aber mit kurzem Timeout pro Adresse (IPv6 ohne Route)."""
    last = None
    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise MailUnreachable("Der Server %s wurde nicht gefunden – besteht eine Internetverbindung? (%s)" % (host, exc)) from exc
    # IPv4 zuerst: funktioniert praktisch immer; IPv6 danach
    infos.sort(key=lambda i: 0 if i[0] == socket.AF_INET else 1)
    for family, kind, proto, _name, addr in infos:
        sock = None
        try:
            sock = socket.socket(family, kind, proto)
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect(addr)
            sock.settimeout(TIMEOUT)
            return sock
        except OSError as exc:
            last = exc
            if sock is not None:
                sock.close()
    raise MailUnreachable("Der Server %s ist nicht erreichbar (%s)." % (host, last))


class _SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return _connect(host, port)


class _SMTP_SSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        return self.context.wrap_socket(_connect(host, port), server_hostname=self._host)


class _IMAP4_SSL(imaplib.IMAP4_SSL):
    def _create_socket(self, timeout):
        return self.ssl_context.wrap_socket(_connect(self.host, self.port), server_hostname=self.host)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

PROVIDERS = {
    "domain": {
        "label": "Eigene Domain", "imap_host": "", "imap_port": 993,
        "smtp_host": "", "smtp_port": 587, "smtp_security": "starttls", "save_sent": True,
    },
    "gmx": {
        "label": "GMX", "imap_host": "imap.gmx.net", "imap_port": 993,
        "smtp_host": "mail.gmx.net", "smtp_port": 587, "smtp_security": "starttls", "save_sent": True,
    },
    "webde": {
        "label": "WEB.DE", "imap_host": "imap.web.de", "imap_port": 993,
        "smtp_host": "smtp.web.de", "smtp_port": 587, "smtp_security": "starttls", "save_sent": True,
    },
    "icloud": {
        "label": "iCloud Mail", "imap_host": "imap.mail.me.com", "imap_port": 993,
        "smtp_host": "smtp.mail.me.com", "smtp_port": 587, "smtp_security": "starttls", "save_sent": True,
    },
    "gmail": {
        "label": "Gmail", "imap_host": "imap.gmail.com", "imap_port": 993,
        "smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_security": "starttls", "save_sent": False,
    },
}

DOMAIN_TO_PROVIDER = {
    "gmx.de": "gmx", "gmx.net": "gmx", "gmx.at": "gmx", "gmx.ch": "gmx",
    "web.de": "webde", "icloud.com": "icloud", "me.com": "icloud", "mac.com": "icloud",
    "gmail.com": "gmail", "googlemail.com": "gmail",
}


class MailError(Exception):
    pass


class MailUnreachable(MailError):
    """Kein Netz oder Server nicht erreichbar – vorübergehend, kein Passwort-Problem."""
    """Fehler mit verständlicher Meldung für die Oberfläche."""


# --------------------------------------------------------------------------- Serverdaten

def provider_defaults(provider: str) -> dict:
    return dict(PROVIDERS.get(provider) or PROVIDERS["domain"])


def autodetect(address: str) -> dict | None:
    """Sucht Serverdaten über die Thunderbird-Datenbank und Autoconfig der Domain."""
    if "@" not in address:
        return None
    domain = address.split("@", 1)[1].strip().lower()
    known = DOMAIN_TO_PROVIDER.get(domain)
    if known:
        result = provider_defaults(known)
        result["provider"] = known
        return result
    urls = [
        "https://autoconfig.thunderbird.net/v1.1/" + domain,
        "https://autoconfig.%s/mail/config-v1.1.xml?emailaddress=%s" % (domain, address),
        "https://%s/.well-known/autoconfig/mail/config-v1.1.xml" % domain,
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Spurlos"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                parsed = _parse_autoconfig(resp.read(), address)
            if parsed:
                parsed["source"] = url
                return parsed
        except Exception:  # noqa: BLE001
            continue
    return {
        "imap_host": "imap." + domain, "imap_port": 993,
        "smtp_host": "smtp." + domain, "smtp_port": 587, "smtp_security": "starttls",
        "guessed": True,
    }


def _parse_autoconfig(raw: bytes, address: str) -> dict | None:
    root = ET.fromstring(raw)
    imap = None
    smtp = None
    for server in root.iter("incomingServer"):
        if server.get("type") == "imap" and imap is None:
            imap = server
    for server in root.iter("outgoingServer"):
        if server.get("type") == "smtp" and smtp is None:
            smtp = server
    if imap is None or smtp is None:
        return None

    def text(node, tag):
        el = node.find(tag)
        return (el.text or "").strip() if el is not None else ""

    local, domain = address.split("@", 1)

    def fill(value):
        return (value.replace("%EMAILADDRESS%", address).replace("%EMAILLOCALPART%", local)
                .replace("%EMAILDOMAIN%", domain))

    smtp_socket = text(smtp, "socketType").upper()
    return {
        "imap_host": fill(text(imap, "hostname")),
        "imap_port": int(text(imap, "port") or 993),
        "smtp_host": fill(text(smtp, "hostname")),
        "smtp_port": int(text(smtp, "port") or 587),
        "smtp_security": "ssl" if smtp_socket == "SSL" else "starttls",
        "username": fill(text(imap, "username")) or address,
    }


# --------------------------------------------------------------------------- Verbindungen

def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


def _login_names(cfg: dict) -> list:
    names = []
    for value in (cfg.get("username"), cfg.get("address")):
        if value and value not in names:
            names.append(value)
    address = cfg.get("address") or ""
    if cfg.get("provider") == "icloud" and "@" in address:
        names.append(address.split("@", 1)[0])
    return names


def connect_imap(cfg: dict, password: str) -> imaplib.IMAP4_SSL:
    host = cfg.get("imap_host")
    if not host:
        raise MailError("Es fehlt der Posteingangsserver (IMAP).")
    try:
        imap = _IMAP4_SSL(host, int(cfg.get("imap_port") or 993), ssl_context=_ctx(), timeout=TIMEOUT)
    except MailUnreachable:
        raise
    except (socket.gaierror, OSError) as exc:
        raise MailUnreachable("Der Posteingangsserver %s ist nicht erreichbar (%s)." % (host, exc)) from exc
    last = None
    for name in _login_names(cfg):
        try:
            imap.login(name, password)
            return imap
        except imaplib.IMAP4.error as exc:
            last = exc
    try:
        imap.logout()
    except Exception:  # noqa: BLE001
        pass
    hint = ""
    if cfg.get("provider") in ("gmx", "webde"):
        hint = " Prüfe auch, ob der Zugriff über POP3 und IMAP in den Einstellungen erlaubt ist."
    if cfg.get("provider") in ("gmail", "icloud"):
        hint = " Bei diesem Anbieter brauchst du ein App-Passwort, nicht dein normales Passwort."
    raise MailError("Anmeldung am Posteingang fehlgeschlagen: %s.%s" % (_short(last), hint))


def connect_smtp(cfg: dict, password: str) -> smtplib.SMTP:
    host = cfg.get("smtp_host")
    if not host:
        raise MailError("Es fehlt der Postausgangsserver (SMTP).")
    port = int(cfg.get("smtp_port") or 587)
    try:
        if cfg.get("smtp_security") == "ssl" or port == 465:
            smtp = _SMTP_SSL(host, port, context=_ctx(), timeout=TIMEOUT, local_hostname=HELO_NAME)
        else:
            smtp = _SMTP(host, port, timeout=TIMEOUT, local_hostname=HELO_NAME)
            smtp.ehlo()
            smtp.starttls(context=_ctx())
            smtp.ehlo()
    except MailUnreachable:
        raise
    except (socket.gaierror, OSError) as exc:
        raise MailUnreachable("Der Postausgangsserver %s ist nicht erreichbar (%s)." % (host, exc)) from exc
    except smtplib.SMTPException as exc:
        raise MailError("Der Postausgangsserver %s ist nicht erreichbar (%s)." % (host, exc)) from exc
    last = None
    for name in _login_names(cfg):
        try:
            smtp.login(name, password)
            return smtp
        except smtplib.SMTPAuthenticationError as exc:
            last = exc
        except smtplib.SMTPException as exc:
            last = exc
            break
    try:
        smtp.quit()
    except Exception:  # noqa: BLE001
        pass
    raise MailError("Anmeldung am Postausgang fehlgeschlagen: %s." % _short(last))


def _short(exc) -> str:
    if exc is None:
        return "unbekannter Fehler"
    text = str(exc)
    if isinstance(exc, smtplib.SMTPResponseException):
        text = exc.smtp_error.decode("utf-8", "replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
    text = text.strip().strip("b'\"")
    return text[:180]


# --------------------------------------------------------------------------- Versand

def build_message(cfg: dict, to: str, subject: str, body: str, message_id: str | None = None,
                  in_reply_to: str | None = None, references: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    sender = cfg.get("address")
    msg["From"] = formataddr((cfg.get("display_name") or "", sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    domain = sender.split("@", 1)[1] if sender and "@" in sender else None
    msg["Message-ID"] = message_id or make_msgid(domain=domain)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.set_content(body)
    return msg


def send(cfg: dict, password: str, to: str, subject: str, body: str, in_reply_to: str | None = None,
         references: str | None = None) -> str:
    msg = build_message(cfg, to, subject, body, in_reply_to=in_reply_to, references=references)
    smtp = connect_smtp(cfg, password)
    try:
        refused = smtp.send_message(msg)
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError("Der Server hat die Empfängeradresse %s abgelehnt." % to) from exc
    except smtplib.SMTPException as exc:
        raise MailError("Versand fehlgeschlagen: %s" % _short(exc)) from exc
    except OSError as exc:
        # Verbindung mittendrin weg (z. B. Mac schläft ein): nicht gleich noch mal, sonst geht die Mail doppelt raus
        raise MailError("Versand abgebrochen, Verbindung verloren: %s" % _short(exc)) from exc
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001
            pass
    if refused:
        raise MailError("Der Server hat die Empfängeradresse %s abgelehnt." % to)
    if cfg.get("save_sent", True):
        try:
            imap = connect_imap(cfg, password)
            try:
                folder = find_sent_folder(imap, cfg.get("sent_folder"))
                if folder:
                    imap.append(folder, "(\\Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            finally:
                imap.logout()
        except Exception:  # noqa: BLE001
            pass  # Kopie im Gesendet-Ordner ist nett, aber kein Muss.
    return msg["Message-ID"]


_LIST_RE = re.compile(r'\((?P<flags>[^)]*)\)\s+(?P<delim>"[^"]*"|NIL)\s+(?P<name>.+)$')


def list_folders(imap: imaplib.IMAP4) -> list:
    status, data = imap.list()
    folders = []
    if status != "OK":
        return folders
    for raw in data:
        if raw is None:
            continue
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        m = _LIST_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1].replace('\\"', '"')
        folders.append((m.group("flags"), name))
    return folders


def _quote(name: str) -> str:
    return '"%s"' % name.replace("\\", "\\\\").replace('"', '\\"')


def find_sent_folder(imap: imaplib.IMAP4, preferred: str | None = None) -> str | None:
    folders = list_folders(imap)
    names = [n for _, n in folders]
    if preferred and preferred in names:
        return _quote(preferred)
    for flags, name in folders:
        if "\\Sent" in flags:
            return _quote(name)
    for candidate in ("Sent", "INBOX.Sent", "Gesendet", "INBOX.Gesendet", "Gesendete Objekte",
                      "Gesendete Elemente", "Sent Messages", "Sent Items"):
        if candidate in names:
            return _quote(candidate)
    return None


# --------------------------------------------------------------------------- Abruf

def _imap_date(d: date) -> str:
    return "%02d-%s-%d" % (d.day, MONTHS[d.month - 1], d.year)


def find_junk_folder(imap: imaplib.IMAP4):
    folders = list_folders(imap)
    for flags, name in folders:
        if "\\Junk" in flags:
            return name
    lower = {n.lower(): n for _, n in folders}
    for candidate in ("junk", "spam", "inbox.junk", "inbox.spam", "junk-e-mail", "junk e-mail", "[gmail]/spam",
                      "unerwünscht", "inbox.spamverdacht", "spamverdacht"):
        if candidate in lower:
            return lower[candidate]
    return None


MAX_PER_POLL = 200


def _fetch_folder(imap, folder: str, fstate: dict, since: date) -> tuple:
    """Neue Nachrichten eines Ordners, ohne sie als gelesen zu markieren. Gibt (Nachrichten, neuer Stand) zurück."""
    status, _ = imap.select(_quote(folder) if folder != "INBOX" else "INBOX", readonly=True)
    if status != "OK":
        return [], fstate
    uidvalidity = None
    resp = imap.response("UIDVALIDITY")
    if resp and resp[1] and resp[1][0]:
        uidvalidity = resp[1][0].decode() if isinstance(resp[1][0], bytes) else str(resp[1][0])
    last_uid = int(fstate.get("last_uid") or 0)
    if fstate.get("uidvalidity") and uidvalidity and fstate.get("uidvalidity") != uidvalidity:
        last_uid = 0
    status, data = imap.uid("SEARCH", None, "SINCE", _imap_date(since))
    uids = sorted(int(x) for x in (data[0].split() if data and data[0] else []))
    todo = [u for u in uids if u > last_uid][:MAX_PER_POLL]   # Rest beim nächsten Abruf
    messages = []
    done_uid = last_uid
    for uid in todo:
        status, parts = imap.uid("FETCH", str(uid), "(INTERNALDATE BODY.PEEK[])")
        raw, meta = None, b""
        for part in parts or []:
            if isinstance(part, tuple) and len(part) >= 2:
                meta, raw = part[0], part[1]
                break
        done_uid = uid
        if not raw:
            continue
        try:
            parsed = parse_message(raw)
        except Exception:  # noqa: BLE001  – eine kaputte Mail soll den Abruf nicht stoppen
            continue
        received = _internal_date(meta)
        if received:
            parsed["received"] = received
        parsed["uid"] = "%s:%s" % (folder, uid)
        parsed["folder"] = folder
        messages.append(parsed)
    return messages, {"uidvalidity": uidvalidity, "last_uid": done_uid}


def _internal_date(meta) -> str | None:
    try:
        tt = imaplib.Internaldate2tuple(meta if isinstance(meta, bytes) else str(meta).encode())
        if not tt:
            return None
        return datetime.fromtimestamp(time.mktime(tt)).replace(microsecond=0).isoformat(sep=" ")
    except Exception:  # noqa: BLE001
        return None


def fetch_new(cfg: dict, password: str, state: dict, since: date | None = None) -> tuple:
    """Holt neue Nachrichten aus Posteingang und Spam-Ordner, ohne sie als gelesen zu markieren."""
    state = dict(state or {})
    if "last_uid" in state or "uidvalidity" in state:      # alter Stand (nur Posteingang)
        state = {"INBOX": {"uidvalidity": state.get("uidvalidity"), "last_uid": state.get("last_uid")}}
    since = since or (date.today() - timedelta(days=60))
    imap = connect_imap(cfg, password)
    messages = []
    try:
        folders = ["INBOX"]
        try:
            junk = find_junk_folder(imap)
        except Exception:  # noqa: BLE001
            junk = None
        if junk and junk.upper() != "INBOX":
            folders.append(junk)
        for folder in folders:
            got, fstate = _fetch_folder(imap, folder, state.get(folder) or {}, since)
            messages.extend(got)
            state[folder] = fstate
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
    return messages, state


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table", "section", "blockquote"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.skip:
            self.skip -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        return re.sub(r"<[^>]+>", " ", html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _decode(value) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(str(value))))
    except Exception:  # noqa: BLE001
        return str(value)


def parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    body = ""
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is not None:
            content = part.get_content()
            body = html_to_text(content) if part.get_content_type() == "text/html" else content
    except Exception:  # noqa: BLE001
        body = ""
    attachments = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()
        if filename or "attachment" in disp:
            attachments.append(_decode(filename) or part.get_content_type())
    from_name, from_addr = "", ""
    froms = getaddresses([str(msg.get("From", ""))])
    if froms:
        from_name, from_addr = froms[0]
    try:
        when = parsedate_to_datetime(str(msg.get("Date"))).astimezone().replace(tzinfo=None)
        when_text = when.replace(microsecond=0).isoformat(sep=" ")
    except Exception:  # noqa: BLE001
        when_text = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    headers = {}
    for key in ("Auto-Submitted", "X-Autoreply", "X-Autorespond", "Precedence", "X-Auto-Response-Suppress",
                "X-Failed-Recipients", "Return-Path"):
        if msg.get(key) is not None:
            headers[key.lower()] = str(msg.get(key))
    content_type = msg.get_content_type()
    report_type, actions = "", []
    if content_type == "multipart/report":
        report_type = (msg.get_param("report-type") or "").lower()
        for part in msg.walk():
            if part.get_content_type() in ("message/delivery-status", "message/global-delivery-status"):
                try:
                    payload = part.get_payload()
                    text = "\n".join(str(p) for p in payload) if isinstance(payload, list) else str(payload)
                except Exception:  # noqa: BLE001
                    text = ""
                actions += [a.strip().lower() for a in re.findall(r"(?im)^\s*action\s*:\s*(\S+)", text)]
    reply_to = ""
    rts = getaddresses([str(msg.get("Reply-To", ""))]) if msg.get("Reply-To") else []
    if rts and rts[0][1]:
        reply_to = rts[0][1].lower()
    return {
        "message_id": str(msg.get("Message-ID", "")).strip(),
        "in_reply_to": str(msg.get("In-Reply-To", "") or "").strip(),
        "references": str(msg.get("References", "") or "").strip(),
        "from_addr": (from_addr or "").lower(),
        "from_name": _decode(from_name),
        "to": str(msg.get("To", "")),
        "subject": _decode(msg.get("Subject", "")),
        "date": when_text,
        "body": (body or "").strip()[:60000],
        "attachments": attachments,
        "headers": headers,
        "is_report": content_type == "multipart/report",
        "report_type": report_type,
        "dsn_actions": actions,
        "reply_to": reply_to,
    }
