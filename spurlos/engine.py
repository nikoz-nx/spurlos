"""Ablauf: Anfragen planen, verschicken, Antworten zuordnen, Fristen überwachen."""
from __future__ import annotations

import re
import os
import subprocess
import sys
import threading
import time
import calendar
from datetime import date, datetime, timedelta

from . import brokers, classify, db, mail, secrets_store, texts

STATUS = {
    "planned": ("planned", "Versand geplant"),
    "sent": ("wait", "Anfrage verschickt"),
    "ack": ("wait", "Eingang bestätigt"),
    "followup": ("wait", "Rückfrage beantwortet"),
    "review": ("todo", "Antwort prüfen"),
    "webform": ("todo", "Formular nötig"),
    "failed": ("todo", "Zustellung fehlgeschlagen"),
    "complaint": ("todo", "Beschwerde möglich"),
    "overdue": ("overdue", "Frist abgelaufen"),
    "reminded": ("overdue", "Erinnerung verschickt"),
    "done": ("done", "Abgeschlossen"),
    "no_contact": ("missing", "Kontakt fehlt"),
    "letter": ("missing", "Brief nötig"),
}
OUTCOME_LABEL = {"no_data": "Keine Daten", "deleted": "Daten gelöscht", "objection": "Widerspruch bestätigt",
                 "access_only": "Auskunft erhalten", "manual": "Von dir abgeschlossen", "webform": "Formular abgeschickt"}
# Erklärung je Plakette (erscheint beim Drüberfahren mit der Maus)
STATUS_HELP = {
    "Versand geplant": "Die Anfrage ist fertig und geht automatisch raus, einzeln über den Tag verteilt. Du musst nichts tun.",
    "Anfrage verschickt": "Die Anfrage ist raus. Die Firma hat einen Monat Zeit zu antworten. Kommt nichts, erinnert Spurlos von selbst.",
    "Eingang bestätigt": "Die Firma hat den Eingang bestätigt, die eigentliche Antwort fehlt noch. Spurlos wartet weiter.",
    "Rückfrage beantwortet": "Die Firma hatte eine Rückfrage, zum Beispiel nach einem Ausweis. Spurlos hat geantwortet und wartet wieder.",
    "Antwort prüfen": "Spurlos ist sich bei einer Antwort nicht sicher. Schau sie dir im Eingang kurz an und bestätige, was die Firma meint.",
    "Formular nötig": "Diese Firma nimmt Anfragen nur über ein Formular auf ihrer Website an. Den Text zum Einfügen findest du bei der Anfrage.",
    "Zustellung fehlgeschlagen": "Die E-Mail kam nicht an, die Adresse funktioniert nicht. Du kannst in der Händlerliste eine andere eintragen.",
    "Beschwerde möglich": "Die Firma hat trotz Erinnerung nicht geantwortet. Der Text für eine kostenlose Beschwerde bei der Datenschutzbehörde liegt bereit.",
    "Frist abgelaufen": "Die Firma hat nach einem Monat nicht geantwortet. Spurlos schickt automatisch eine Erinnerung.",
    "Erinnerung verschickt": "Die Firma hat eine Erinnerung bekommen und noch eine kurze Nachfrist.",
    "Abgeschlossen": "Die Firma hat geantwortet, der Fall ist zu Ende.",
    "Kontakt fehlt": "Für diese Firma ist keine Adresse bekannt. Du kannst eine in der Händlerliste nachtragen.",
    "Brief nötig": "Diese Firma nimmt Anfragen nur per Post an. Das Drucken kommt in einer späteren Version.",
    "Keine Daten": "Die Firma hatte nichts über dich gespeichert.",
    "Daten gelöscht": "Die Firma hat deine Daten gelöscht.",
    "Widerspruch bestätigt": "Die Firma nutzt deine Daten nicht mehr für Werbung.",
    "Auskunft erhalten": "Bei Auskunfteien: Du hast deine Auskunft bekommen. Gelöscht wird dort nichts.",
    "Von dir abgeschlossen": "Du hast die Anfrage selbst als abgeschlossen markiert, zum Beispiel nach einem Brief.",
    "Formular abgeschickt": "Du hast das Webformular der Firma ausgefüllt. Spurlos überwacht ab jetzt die Frist.",
    "Link bestätigt": "Du hast den Bestätigungslink der Firma angeklickt. Spurlos wartet auf die eigentliche Antwort.",
}

_RUN_LOCK = threading.Lock()


def _parse(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(sep=" ")


NOTIFIER = None   # setzt die Mac-App: Mitteilungszentrum statt osascript


def notify(text: str) -> None:
    if not (db.get("sending") or {}).get("notifications", True):
        return
    if sys.platform != "darwin":
        return
    if NOTIFIER:
        try:
            if NOTIFIER(text[:180]):
                return
        except Exception:  # noqa: BLE001
            pass
    # Text als Argument übergeben, nicht ins Skript einsetzen: Firmennamen sind Fremddaten.
    # LANG setzen, sonst kommen Umlaute aus einer per Finder gestarteten App kaputt an.
    env = dict(os.environ, LANG="de_DE.UTF-8", LC_ALL="de_DE.UTF-8")
    script = ["-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "Spurlos"', "-e", "end run"]
    try:
        subprocess.run(["osascript"] + script + [text[:180]], env=env, timeout=10, capture_output=True)
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------------- Hilfen

def mailbox_ready() -> tuple:
    cfg = db.get("mailbox")
    pw = secrets_store.get_secret("mailbox")
    if not cfg.get("address") or not pw or not cfg.get("smtp_host"):
        return None, None
    return cfg, pw


def profile_ok() -> bool:
    p = db.get("profile")
    return bool(texts.full_name(p) and (p.get("emails") or p.get("addresses")))


def lang_of(broker: dict) -> str:
    """Schweizer Firmen bekommen Briefe nach Schweizer Recht, egal was in der Liste steht."""
    if brokers.is_swiss(broker):
        return "ch"
    return broker.get("lang") or "en"


def _add_months(d: datetime, months: int) -> datetime:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def due_from(start: datetime, broker: dict) -> datetime:
    """Frist für eine Antwort. DSGVO: ein Monat (gleicher Tag im Folgemonat, Tagesende). Schweiz: 30 Tage."""
    days = int((db.get("sending") or {}).get("reminder_days") or 30)
    if lang_of(broker) == "ch" or days != 30:
        end = start + timedelta(days=days)
    else:
        end = _add_months(start, 1)
    return end.replace(hour=23, minute=59, second=59, microsecond=0)


def request_ctx(req: dict, broker: dict, kind: str = "") -> dict:
    profile = db.get("profile")
    lang = lang_of(broker)
    first = db.query_one("SELECT body, date FROM messages WHERE request_id = ? AND direction = 'out' AND kind = 'request' "
                         "ORDER BY id LIMIT 1", (req["id"],)) if req.get("id") else None
    sent_at = req.get("sent_at") or db.now()
    due = due_from(datetime.now(), broker)
    last_out = db.query_one("SELECT body, date FROM messages WHERE request_id = ? AND direction = 'out' "
                            "AND kind = 'followup' ORDER BY id DESC LIMIT 1", (req["id"],)) if req.get("id") else None
    return {
        "ref": req["ref"],
        "name": texts.full_name(profile),
        "id_block": texts.id_block(profile, lang),
        "sent_date": texts.fmt_date(sent_at, lang),
        "due_date": texts.fmt_date(_iso(due), lang),
        "original": (first or {}).get("body", ""),
        "last_date": texts.fmt_date((last_out or {}).get("date") or sent_at, lang),
        "last_body": (last_out or {}).get("body", ""),
    }


def render_request(req: dict, broker: dict) -> tuple:
    lang = lang_of(broker)
    ctx = request_ctx(req, broker)
    return texts.request_text(lang, ctx, access_only=broker.get("grp") == "credit", us=broker.get("grp") == "us")


def _broker(broker_id: str) -> dict:
    return db.query_one("SELECT * FROM brokers WHERE id = ?", (broker_id,)) or {}


def _req(ref: str) -> dict:
    req = db.query_one("SELECT * FROM requests WHERE ref = ?", (ref,))
    if not req:
        raise ValueError("Anfrage %s nicht gefunden" % ref)
    return req


def _set(req_id: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join("%s = ?" % k for k in fields)
    db.execute("UPDATE requests SET %s WHERE id = ?" % sets, list(fields.values()) + [req_id])


# ----------------------------------------------------------------------------- Planung

def build_requests() -> dict:
    """Legt für alle ausgewählten Firmen ohne Anfrage eine Anfrage an."""
    groups = db.get("groups")
    countries = set(db.get("countries") or ["de"])
    created = {"email": 0, "webform": 0, "letter": 0, "none": 0}
    existing = {r["broker_id"] for r in db.query("SELECT broker_id FROM requests")}
    rows = db.query("SELECT * FROM brokers WHERE active = 1")
    for b in rows:
        if b["id"] in existing or not brokers.selected(b, groups, countries):
            continue
        kind = brokers.contact_kind(b)
        status = {"email": "planned", "webform": "webform", "letter": "letter", "none": "no_contact"}[kind]
        ref = db.next_ref()
        rid = db.execute("INSERT INTO requests(ref, broker_id, status, channel, created_at) VALUES (?, ?, ?, ?, ?)",
                         (ref, b["id"], status, kind, db.now()))
        db.event(rid, "created", "Anfrage angelegt")
        created[kind] += 1
    # Abgewählte Firmen: noch nicht verschickte Anfragen entfernen.
    for r in db.query("SELECT r.id, r.status, b.* FROM requests r JOIN brokers b ON b.id = r.broker_id "
                      "WHERE r.status IN ('planned', 'no_contact', 'webform', 'letter')"):
        if not brokers.selected(r, groups, countries):
            db.execute("DELETE FROM events WHERE request_id = ?", (r["id"],))
            db.execute("DELETE FROM requests WHERE id = ?", (r["id"],))
    plan_batches()
    return created


# Versandplan: Spurlos entscheidet selbst, wie viele Mails pro Tag vertretbar sind.
# Ein neues Postfach fängt klein an und steigert sich; die Mails gehen einzeln raus,
# mit Abstand, verteilt über den Tag – so wirkt es wie normales Schreiben, nicht wie Werbung.
RAMP = [15, 25, 35]      # Tag 1, 2, 3 …
DAILY_MAX = 40           # … danach
SEND_FROM, SEND_UNTIL = 8, 20   # Uhrzeiten, zwischen denen verschickt wird


def _send_days_so_far() -> int:
    """An wie vielen früheren Tagen schon Anfragen rausgingen (für die Steigerung)."""
    today = date.today().isoformat()
    row = db.query_one("SELECT COUNT(DISTINCT substr(date, 1, 10)) AS n FROM messages "
                       "WHERE direction = 'out' AND kind = 'request' AND substr(date, 1, 10) < ?", (today,))
    return int(row["n"]) if row else 0


def daily_cap(day_index: int) -> int:
    return RAMP[day_index] if day_index < len(RAMP) else DAILY_MAX


def _day_slots(day_start: datetime, n: int, not_before: datetime | None = None) -> list:
    """n Zeitpunkte, gleichmäßig zwischen 8 und 20 Uhr (bzw. ab jetzt) verteilt."""
    begin = day_start.replace(hour=SEND_FROM, minute=0, second=0, microsecond=0)
    end = day_start.replace(hour=SEND_UNTIL, minute=0, second=0, microsecond=0)
    if not_before and not_before > begin:
        begin = not_before
    if n <= 0 or begin >= end:
        return []
    step = (end - begin) / n
    return [begin + step * i + timedelta(seconds=(i * 37) % 60) for i in range(n)]


def plan_batches(first_now: bool | None = None) -> None:   # first_now bleibt für alte Aufrufer
    rows = db.query("SELECT r.id, b.grp, b.origin FROM requests r JOIN brokers b ON b.id = r.broker_id "
                    "WHERE r.status = 'planned' ORDER BY r.id")
    order = {g: i for i, g in enumerate(brokers.GROUP_ORDER)}
    origin_rank = {"datenanfragen": 0, "recherche": 1, "incogni": 2, "eigene": 0, "kalifornien": 3}
    rows.sort(key=lambda r: (order.get(r["grp"] or "consumer", 9), origin_rank.get(r["origin"], 5), r["id"]))
    for row, slot in zip(rows, _plan_slots(len(rows))):
        _set(row["id"], planned_for=_iso(slot))


def _plan_slots(n: int) -> list:
    now = datetime.now()
    day_index = _send_days_so_far()
    slots = []
    # Heute: was heute noch frei ist, ab jetzt (erste Mail sofort)
    today_left = max(0, daily_cap(day_index) - sent_count_today())
    if now.hour < SEND_UNTIL and today_left:
        take = min(today_left, n)
        slots.extend(_day_slots(now, take, not_before=now))
        if slots:
            slots[0] = now
        if sent_count_today() or slots:
            day_index += 1
    day = 1
    while len(slots) < n:
        cap = daily_cap(day_index)
        slots.extend(_day_slots(now + timedelta(days=day), min(cap, n - len(slots))))
        day_index += 1
        day += 1
    return slots[:n]


def estimate_days(n: int | None = None) -> int:
    """In wie vielen Tagen alle (geplanten) Anfragen voraussichtlich verschickt sind."""
    if n is None:
        n = db.query_one("SELECT COUNT(*) AS c FROM requests WHERE status = 'planned'")["c"]
    if n <= 0:
        return 0
    last = _plan_slots(n)[-1]
    return (last.date() - date.today()).days + 1


def sent_count_today() -> int:
    today = date.today().isoformat()
    row = db.query_one("SELECT COUNT(*) AS n FROM messages WHERE direction = 'out' AND kind = 'request' "
                       "AND substr(date, 1, 10) = ?", (today,))
    return int(row["n"]) if row else 0


# ----------------------------------------------------------------------------- Versand

def send_request(ref: str) -> None:
    cfg, pw = mailbox_ready()
    if not cfg:
        raise mail.MailError("Das Postfach ist noch nicht eingerichtet.")
    req = _req(ref)
    b = _broker(req["broker_id"])
    if req["status"] not in ("planned", "failed"):
        raise mail.MailError("Die Anfrage an %s ist schon verschickt." % b.get("name"))
    if not b.get("active"):
        raise mail.MailError("%s ist in der Händlerliste ausgeschaltet." % b.get("name"))
    if not b.get("email"):
        raise mail.MailError("Für %s ist keine E-Mail-Adresse hinterlegt." % b.get("name"))
    subject, body = render_request(req, b)
    msg_id = mail.new_message_id(cfg)
    _set(req["id"], last_message_id=msg_id)   # vorab merken: falls die Verbindung mittendrin abreißt
    note = None
    try:
        mail.send(cfg, pw, b["email"], subject, body, message_id=msg_id)
    except mail.MailError as exc:
        if not getattr(exc, "maybe_sent", False):
            raise
        # Mail war schon beim Server, nur die Bestätigung kam nicht an. Lieber als verschickt
        # werten als doppelt senden – bleibt eine Antwort aus, erinnert Spurlos ohnehin.
        note = "Verbindung brach beim Versand ab; die Anfrage gilt als verschickt."
    now = datetime.now()
    _set(req["id"], status="sent", label=None, sent_at=_iso(now), due_at=_iso(due_from(now, b)),
         reminder_sent_at=None, reminder_due_at=None, last_message_id=msg_id, planned_for=None)
    db.execute("INSERT INTO messages(request_id, direction, kind, message_id, from_addr, to_addr, subject, date, body, created_at) "
               "VALUES (?, 'out', 'request', ?, ?, ?, ?, ?, ?, ?)",
               (req["id"], msg_id, cfg["address"], b["email"], subject, _iso(now), body, db.now()))
    db.event(req["id"], "sent", "Anfrage per E-Mail gesendet an %s" % b["email"] + (" – " + note if note else ""))


def send_followup(ref: str, kind: str, body_override: str | None = None) -> None:
    cfg, pw = mailbox_ready()
    if not cfg:
        raise mail.MailError("Das Postfach ist noch nicht eingerichtet.")
    req = _req(ref)
    b = _broker(req["broker_id"])
    lang = lang_of(b)
    text_kind = kind
    if kind == "reminder" and _waiting_status(req) == "followup":
        text_kind = "reminder_followup"     # die Firma hat schon geantwortet, offen ist unser letztes Schreiben
    subject, body = texts.followup_text(text_kind, lang, request_ctx(req, b))
    if body_override:
        body = body_override
    last_in = db.query_one("SELECT from_addr, reply_to, message_id FROM messages WHERE request_id = ? AND direction = 'in' "
                           "AND kind = 'reply' ORDER BY id DESC LIMIT 1", (req["id"],))
    to = None
    if last_in and kind != "reminder":
        to = last_in.get("reply_to") or (None if NOREPLY.search(last_in.get("from_addr") or "") else last_in.get("from_addr"))
    to = to or b.get("email")
    if not to:
        raise mail.MailError("Für %s ist keine E-Mail-Adresse hinterlegt." % b.get("name"))
    in_reply = (last_in or {}).get("message_id") or req.get("last_message_id")
    msg_id = mail.send(cfg, pw, to, subject, body, in_reply_to=in_reply)
    now = datetime.now()
    db.execute("INSERT INTO messages(request_id, direction, kind, message_id, from_addr, to_addr, subject, date, body, created_at) "
               "VALUES (?, 'out', ?, ?, ?, ?, ?, ?, ?, ?)",
               (req["id"], kind if kind == "reminder" else "followup", msg_id, cfg["address"], to, subject, _iso(now), body, db.now()))
    sending = db.get("sending")
    if kind == "reminder":
        _set(req["id"], status="reminded", reminder_sent_at=_iso(now),
             reminder_due_at=_iso(now + timedelta(days=int(sending.get("complaint_days") or 14))), last_message_id=msg_id)
        db.event(req["id"], "reminder", "Erinnerung gesendet")
    else:
        labels = {"erasure": "Löschung angefordert", "id_reply": "Antwort zum Ausweis gesendet",
                  "clarify": "Rückfrage beantwortet"}
        _set(req["id"], status="followup", label=labels.get(kind, "Antwort gesendet"), due_at=_iso(due_from(now, b)),
             reminder_sent_at=None, reminder_due_at=None, last_message_id=msg_id)
        db.event(req["id"], "followup", labels.get(kind, "Antwort gesendet"))


def send_due(force: bool = False) -> dict:
    """Verschickt fällige Anfragen der heutigen Etappe."""
    cfg, pw = mailbox_ready()
    if not cfg or not db.get("started"):
        return {"sent": 0}
    pause = _parse(db.get("send_pause_until"))
    if pause and pause > datetime.now() and not force:
        return {"sent": 0, "paused": True}
    quota = daily_cap(_send_days_so_far()) - sent_count_today()
    if quota <= 0:
        return {"sent": 0}
    now_s = db.now()
    if force:
        # „Jetzt senden“: was heute noch vertretbar ist, sofort statt verteilt.
        rows = db.query("SELECT ref FROM requests WHERE status = 'planned' ORDER BY planned_for IS NULL, planned_for, id "
                        "LIMIT ?", (quota,))
    else:
        rows = db.query("SELECT ref FROM requests WHERE status = 'planned' AND planned_for IS NOT NULL AND planned_for <= ? "
                        "ORDER BY planned_for, id LIMIT ?", (now_s, quota))
    sent, errors = 0, []
    for r in rows:
        if STOP.is_set():
            break   # Programm wird beendet: keine neue Mail mehr anfangen
        try:
            send_request(r["ref"])
            sent += 1
            time.sleep(2)
        except mail.MailError as exc:
            errors.append("%s: %s" % (r["ref"], exc))
            text = str(exc)
            if isinstance(exc, mail.MailUnreachable):
                # Kein Netz (z. B. gerade aus dem Ruhezustand aufgewacht): kurz warten, nicht hochzählen.
                db.put("send_pause_until", _iso(datetime.now() + timedelta(minutes=3)))
                break
            if "Anmeldung" in text or "erreichbar" in text:
                # Server oder Passwort: nicht jede Minute neu probieren, sonst sperrt der Anbieter das Konto.
                fails = int(db.get("send_failures") or 0) + 1
                db.put("send_failures", fails)
                db.put("send_pause_until", _iso(datetime.now() + timedelta(minutes=min(240, 15 * 2 ** (fails - 1)))))
                break
            req = db.query_one("SELECT id FROM requests WHERE ref = ?", (r["ref"],))
            if req and ("Empfängeradresse" in text or "keine E-Mail-Adresse" in text):
                _set(req["id"], status="failed", label=None)
                db.event(req["id"], "error", text)
            elif req and ("ausgeschaltet" in text or "schon verschickt" in text):
                pass
            elif req:
                # Unbekannter Fehler: diese Anfrage auf morgen schieben statt sie jede Minute neu zu versuchen.
                _set(req["id"], planned_for=_iso(datetime.now() + timedelta(days=1)))
                db.event(req["id"], "error", "Versand fehlgeschlagen, neuer Versuch morgen: %s" % text)
    if sent:
        db.put("send_failures", 0)
        db.put("send_pause_until", None)
    db.put("last_send_error", errors[-1] if errors else None)
    if force and sent:
        plan_batches(False)
    if sent:
        notify("%d Anfragen verschickt" % sent)
    return {"sent": sent, "errors": errors}


# ----------------------------------------------------------------------------- Eingang

REF_RE = re.compile(r"\bDA-\d{3,5}\b")
NOREPLY = re.compile(r"(no-?reply|do-?not-?reply|noreply|mailer|notification|bounce)", re.IGNORECASE)
LINK_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def _first_link(msg: dict) -> str | None:
    body = classify.own_part(msg.get("body") or "")
    links = [u.rstrip(".,;:") for u in LINK_RE.findall(body)]
    for u in links:
        if re.search(r"(confirm|verify|verif|bestaetig|bestätig|token|activate|validate)", u, re.IGNORECASE):
            return u
    return links[0] if links else None


def _extra_fields(message_id: int, msg: dict) -> None:
    db.execute("UPDATE messages SET reply_to = ?, received = ?, folder = ?, link = ? WHERE id = ?",
               (msg.get("reply_to") or None, msg.get("received"), msg.get("folder"), _first_link(msg), message_id))


def match_request(msg: dict) -> dict | None:
    ids = re.findall(r"<[^>]+>", "%s %s" % (msg.get("in_reply_to", ""), msg.get("references", "")))
    if ids:
        marks = ",".join("?" * len(ids))
        row = db.query_one("SELECT request_id FROM messages WHERE direction = 'out' AND message_id IN (%s) "
                           "AND request_id IS NOT NULL ORDER BY id DESC LIMIT 1" % marks, ids)
        if row:
            return db.query_one("SELECT * FROM requests WHERE id = ?", (row["request_id"],))
    for ref in REF_RE.findall("%s\n%s" % (msg.get("subject", ""), (msg.get("body") or "")[:8000])):
        req = db.query_one("SELECT * FROM requests WHERE ref = ?", (ref,))
        if req and req.get("sent_at") and _after_sent(req, msg):
            return req
    # Nur noch über den Absender: genaue Adresse vor Domain, und nur Anfragen, die wirklich verschickt wurden.
    addrs = {a for a in ((msg.get("from_addr") or "").lower(), (msg.get("reply_to") or "").lower()) if a}
    sent = db.query("SELECT r.*, b.email AS b_email, b.website AS b_website FROM requests r JOIN brokers b ON b.id = r.broker_id "
                    "WHERE r.sent_at IS NOT NULL")
    exact = [r for r in sent if (r.get("b_email") or "").lower() in addrs and _after_sent(r, msg)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    doms = {brokers.domain_of(a) for a in addrs} - {None, ""}
    by_dom = [r for r in sent if doms & {brokers.domain_of(r.get("b_email")), brokers.domain_of(r.get("b_website"))}
              and _after_sent(r, msg)]
    return by_dom[0] if len(by_dom) == 1 else None


def _after_sent(req: dict, msg: dict) -> bool:
    """Eine Antwort kann nicht älter sein als die Anfrage (schützt vor Verwechslungen nach einem Neustart)."""
    sent = _parse(req.get("sent_at"))
    got = _parse(msg.get("received") or msg.get("date"))
    if not sent or not got:
        return True
    return got >= sent - timedelta(minutes=30)


def _bounce_target(msg: dict) -> dict | None:
    body = msg.get("body") or ""
    req = match_request(msg)
    if req:
        return req
    for b in db.query("SELECT id, email FROM brokers WHERE email IS NOT NULL"):
        if b["email"] and b["email"].lower() in body.lower():
            req = db.query_one("SELECT * FROM requests WHERE broker_id = ? AND sent_at IS NOT NULL", (b["id"],))
            if req:
                return req
    return None


def process_incoming(msg: dict) -> str | None:
    if db.query_one("SELECT id FROM messages WHERE direction = 'in' AND message_id = ? AND message_id != ''",
                    (msg.get("message_id", ""),)):
        return None
    own = ((db.get("mailbox") or {}).get("address") or "").lower()
    if own and (msg.get("from_addr") or "").lower() == own:
        return None                      # eigene Testmail oder Kopie
    bounce = classify.is_bounce(msg)
    notice = not bounce and classify.is_notice(msg)
    req = _bounce_target(msg) if bounce else match_request(msg)
    if not req:
        if bounce or notice or classify.is_auto_reply(msg):
            return None
        # Nicht zuordenbar: nicht wegwerfen, sondern im Eingang zum Zuordnen anzeigen.
        result = classify.classify_rules(msg)
        db.execute("INSERT INTO messages(request_id, direction, kind, message_id, in_reply_to, from_addr, reply_to, to_addr, "
                   "subject, date, received, folder, body, attachments, imap_uid, created_at, category, confidence, rule, "
                   "match_text, link, reviewed) VALUES (NULL, 'in', 'unassigned', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                   (msg.get("message_id"), msg.get("in_reply_to"), msg.get("from_addr"), msg.get("reply_to"), msg.get("to"),
                    msg.get("subject"), msg.get("date"), msg.get("received"), msg.get("folder"), msg.get("body"),
                    ", ".join(msg.get("attachments") or []), msg.get("uid"), db.now(), result["category"],
                    result["confidence"], result["rule"], result.get("match"), _first_link(msg)))
        notify("Antwort, die Spurlos nicht zuordnen kann")
        return "unassigned"
    b = _broker(req["broker_id"])
    base = (req["id"], msg.get("message_id"), msg.get("in_reply_to"), msg.get("from_addr"), msg.get("to"),
            msg.get("subject"), msg.get("date"), msg.get("body"), ", ".join(msg.get("attachments") or []),
            msg.get("uid"), db.now())
    cols = ("request_id, direction, kind, message_id, in_reply_to, from_addr, to_addr, subject, date, body, "
            "attachments, imap_uid, created_at, category, confidence, rule, match_text, ai_category, ai_note, reviewed")
    if bounce:
        db.execute("INSERT INTO messages(%s) VALUES (?, 'in', 'bounce', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, 1)" % cols, base)
        _set(req["id"], status="failed", label=None)
        db.event(req["id"], "bounce", "Zustellung fehlgeschlagen. Bitte die Adresse von %s prüfen." % b.get("name"))
        return "bounce"
    if notice:
        # Lesebestätigung oder Zustellbericht: nur im Verlauf vermerken, Status bleibt.
        db.execute("INSERT INTO messages(%s) VALUES (?, 'in', 'auto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, 1)" % cols, base)
        return "auto"
    if classify.is_auto_reply(msg):
        db.execute("INSERT INTO messages(%s) VALUES (?, 'in', 'auto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, 1)" % cols, base)
        if req["status"] == "sent":
            _set(req["id"], status="ack")
        db.event(req["id"], "ack", "Eingangsbestätigung (automatisch)")
        return "auto"
    ai_cfg = db.get("ai")
    api_key = secrets_store.get_secret("ai_cloud") if ai_cfg.get("provider") == "cloud" else None
    result = classify.classify(msg, ai_cfg, api_key)
    mid = db.execute("INSERT INTO messages(%s) VALUES (?, 'in', 'reply', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)" % cols,
                     base + (result["category"], result["confidence"], result["rule"], result.get("match"),
                             result.get("ai_category"), result.get("ai_note")))
    _extra_fields(mid, msg)
    label = classify.CATEGORIES[result["category"]]["label"]
    _set(req["id"], status="review",
         label=label if result["category"] in ("id_request", "clarify", "webform", "refused", "confirm") else "Prüfen")
    db.event(req["id"], "reply", "Antwort erhalten: %s" % label)
    notify("Neue Antwort von %s" % b.get("name"))
    return "reply"


def poll() -> dict:
    cfg, pw = mailbox_ready()
    if not cfg:
        err = secrets_store.LAST_ERROR["text"] or "Postfach nicht eingerichtet"
        if db.get("mailbox").get("password_saved"):
            db.put("last_poll_error", err)
        return {"ok": False, "error": err}
    first = db.query_one("SELECT MIN(date) AS d FROM messages WHERE direction = 'out'")
    since = None
    if first and first["d"]:
        d = _parse(first["d"])
        since = (d - timedelta(days=1)).date() if d else None
    if since is None:
        since = date.today() - timedelta(days=2)
    try:
        messages, state = mail.fetch_new(cfg, pw, db.get("imap_state"), since)
    except mail.MailError as exc:
        db.put("last_poll_error", str(exc))
        return {"ok": False, "error": str(exc), "unreachable": isinstance(exc, mail.MailUnreachable)}
    except Exception as exc:  # noqa: BLE001
        db.put("last_poll_error", "Abruf fehlgeschlagen: %s" % exc)
        return {"ok": False, "error": "Abruf fehlgeschlagen: %s" % exc}
    counts = {"reply": 0, "auto": 0, "bounce": 0, "unassigned": 0}
    for m in messages:
        kind = process_incoming(m)
        if kind:
            counts[kind] += 1
    db.put("imap_state", state)
    db.put("last_poll", db.now())
    db.put("last_poll_error", None)
    return {"ok": True, "fetched": len(messages), **counts}


# ----------------------------------------------------------------------------- Fristen

def check_deadlines() -> dict:
    """Abgelaufene Fristen: erinnern (wenn möglich), danach Beschwerde vorbereiten. Nie zweimal erinnern."""
    now = datetime.now()
    now_s = _iso(now)
    sending = db.get("sending")
    complaint_days = int(sending.get("complaint_days") or 14)
    reminded = 0
    pause = _parse(db.get("send_pause_until"))
    can_send = bool(mailbox_ready()[0]) and not (pause and pause > now)
    rows = db.query("SELECT r.* FROM requests r JOIN brokers b ON b.id = r.broker_id WHERE b.active = 1 AND "
                    "r.status IN ('sent', 'ack', 'followup') AND r.due_at IS NOT NULL AND r.due_at < ?", (now_s,))
    for r in rows:
        # Erst als überfällig markieren und den nächsten Schritt festlegen, dann (einmal) erinnern.
        _set(r["id"], status="overdue", reminder_due_at=_iso(now + timedelta(days=complaint_days)))
        db.event(r["id"], "overdue", "Frist abgelaufen")
    # Erinnerung für überfällige Anfragen, die noch keine bekommen haben (auch erneuter Versuch nach Fehler).
    if sending.get("auto_remind", True) and can_send:
        for r in db.query("SELECT r.*, b.email AS b_email FROM requests r JOIN brokers b ON b.id = r.broker_id "
                          "WHERE b.active = 1 AND r.status = 'overdue' AND r.reminder_sent_at IS NULL"):
            has_reply_addr = db.query_one("SELECT id FROM messages WHERE request_id = ? AND direction = 'in' AND kind = 'reply'",
                                          (r["id"],))
            if not (r.get("b_email") or has_reply_addr):
                continue                  # Webformular-Firma ohne Mailadresse: nur Hinweis, später Beschwerde
            try:
                send_followup(r["ref"], "reminder")
                reminded += 1
            except mail.MailError as exc:
                db.event(r["id"], "error", "Erinnerung konnte nicht gesendet werden: %s" % exc)
                if "Anmeldung" in str(exc) or "erreichbar" in str(exc):
                    break
    for r in db.query("SELECT * FROM requests WHERE status IN ('reminded', 'overdue') AND reminder_due_at IS NOT NULL "
                      "AND reminder_due_at < ?", (now_s,)):
        _set(r["id"], status="complaint")
        db.event(r["id"], "complaint", "Keine Antwort nach Fristablauf. Beschwerde-Text ist vorbereitet.")
    if reminded:
        notify("%d Erinnerungen verschickt" % reminded)
    return {"reminded": reminded}


# ----------------------------------------------------------------------------- Aktionen

def _waiting_status(req: dict) -> str:
    out = db.query_one("SELECT id FROM messages WHERE request_id = ? AND direction = 'out' AND kind = 'followup'", (req["id"],))
    return "followup" if out else "sent"


def confirm_reply(message_id: int, category: str) -> dict:
    msg = db.query_one("SELECT * FROM messages WHERE id = ?", (message_id,))
    if not msg or not msg.get("request_id"):
        raise ValueError("Nachricht nicht gefunden")
    req = db.query_one("SELECT * FROM requests WHERE id = ?", (msg["request_id"],))
    b = _broker(req["broker_id"])
    label = classify.CATEGORIES.get(category, {}).get("label", category)

    def mark():
        db.execute("UPDATE messages SET reviewed = 1, category = ? WHERE id = ?", (category, message_id))
        db.event(req["id"], "confirmed", "Von dir eingeordnet: %s" % label)

    # Erst handeln, dann als erledigt markieren: schlägt der Versand fehl, bleibt die Antwort im Eingang.
    if category in ("no_data", "deleted", "objection"):
        _set(req["id"], status="done", outcome=category, label=None, closed_at=db.now())
        mark()
        return {"next": "done"}
    if category == "access":
        if b.get("grp") == "credit":
            _set(req["id"], status="done", outcome="access_only", label=None, closed_at=db.now())
            mark()
            return {"next": "done"}
        send_followup(req["ref"], "erasure")
        mark()
        return {"next": "erasure_sent"}
    if category == "id_request":
        send_followup(req["ref"], "id_reply")
        mark()
        return {"next": "id_reply_sent"}
    if category == "clarify":
        send_followup(req["ref"], "clarify")
        mark()
        return {"next": "clarify_sent"}
    if category == "webform":
        _set(req["id"], status="webform", label=None)
        mark()
        return {"next": "webform"}
    if category == "refused":
        _set(req["id"], status="complaint", label=None)
        mark()
        return {"next": "complaint"}
    if category == "confirm":
        _set(req["id"], status=_waiting_status(req), label="Link bestätigt")
        mark()
        db.event(req["id"], "confirm", "Bestätigungslink geöffnet, Frist läuft weiter")
        return {"next": "confirmed"}
    # Unklar / nichts zu tun: weiter warten, die Frist läuft weiter.
    _set(req["id"], status=_waiting_status(req), label=None)
    mark()
    return {"next": "waiting"}


def assign_message(message_id: int, ref: str | None) -> dict:
    """Eine nicht zugeordnete Antwort einer Anfrage zuordnen (oder mit ref=None ignorieren)."""
    msg = db.query_one("SELECT * FROM messages WHERE id = ? AND kind = 'unassigned'", (message_id,))
    if not msg:
        raise ValueError("Nachricht nicht gefunden")
    if not ref:
        db.execute("UPDATE messages SET reviewed = 1, kind = 'ignored' WHERE id = ?", (message_id,))
        return {"next": "ignored"}
    req = _req(ref)
    data = dict(msg)
    data["attachments"] = [a for a in (msg.get("attachments") or "").split(", ") if a]
    ai_cfg = db.get("ai")
    api_key = secrets_store.get_secret("ai_cloud") if ai_cfg.get("provider") == "cloud" else None
    result = classify.classify(data, ai_cfg, api_key)
    db.execute("UPDATE messages SET request_id = ?, kind = 'reply', category = ?, confidence = ?, rule = ?, match_text = ?, "
               "ai_category = ?, ai_note = ?, reviewed = 0 WHERE id = ?",
               (req["id"], result["category"], result["confidence"], result["rule"], result.get("match"),
                result.get("ai_category"), result.get("ai_note"), message_id))
    label = classify.CATEGORIES[result["category"]]["label"]
    _set(req["id"], status="review",
         label=label if result["category"] in ("id_request", "clarify", "webform", "refused", "confirm") else "Prüfen")
    db.event(req["id"], "reply", "Antwort zugeordnet: %s" % label)
    return {"next": "assigned"}


def action(ref: str, name: str, data: dict | None = None) -> dict:
    data = data or {}
    req = _req(ref)
    if name == "send_now":
        send_request(ref)
    elif name == "remind":
        send_followup(ref, "reminder")
    elif name in ("erasure", "id_reply", "clarify"):
        send_followup(ref, name, data.get("body"))
    elif name == "done":
        _set(req["id"], status="done", outcome=data.get("outcome") or "manual", label=None, closed_at=db.now())
        db.event(req["id"], "done", "Von dir als abgeschlossen markiert")
    elif name == "webform_sent":
        now = datetime.now()
        _set(req["id"], status="sent", label="Formular abgeschickt", sent_at=_iso(now),
             due_at=_iso(now + timedelta(days=int(db.get("sending").get("reminder_days") or 30))))
        db.event(req["id"], "sent", "Anfrage über das Webformular abgeschickt")
    elif name == "reopen":
        now = datetime.now()
        if req.get("sent_at"):
            _set(req["id"], status=_waiting_status(req), outcome=None, closed_at=None, label=None,
                 due_at=_iso(due_from(now, _broker(req["broker_id"]))), reminder_sent_at=None, reminder_due_at=None)
        else:
            _set(req["id"], status="planned", outcome=None, closed_at=None, label=None)
        db.event(req["id"], "reopen", "Wieder geöffnet")
        if not req.get("sent_at"):
            plan_batches(first_now=False)
    elif name == "skip":
        if req["status"] in ("planned", "no_contact", "webform", "letter"):
            db.execute("UPDATE brokers SET active = 0 WHERE id = ?", (req["broker_id"],))
            db.execute("DELETE FROM events WHERE request_id = ?", (req["id"],))
            db.execute("DELETE FROM requests WHERE id = ?", (req["id"],))
    else:
        raise ValueError("Unbekannte Aktion")
    return {"ok": True}


def complaint(ref: str) -> dict:
    req = _req(ref)
    b = _broker(req["broker_id"])
    profile = db.get("profile")
    state = db.get("state") or ""
    all_auth = brokers.authorities()
    firm_state = brokers.company_state(b)
    swiss = brokers.is_swiss(b)
    if swiss:
        auth = brokers.EDOEB
        auth_note = ("Die Firma sitzt in der Schweiz. Zuständig ist der EDÖB. Er nimmt Meldungen über sein Online-Formular an, "
                     "wenn die Firma nicht innert eines Monats geantwortet hat. Er prüft den Fall, setzt deinen Anspruch "
                     "aber nicht für dich durch. Dafür bleibt eine Klage vor dem Zivilgericht, bei der für Datenschutz-Fälle "
                     "keine Gerichtskosten anfallen.")
    elif firm_state and firm_state in all_auth:
        auth = all_auth[firm_state]
        auth_note = ("Zuständig ist die Behörde in %s, wo die Firma ihren Sitz hat." % firm_state)
    else:
        auth = all_auth.get(state)
        if brokers.is_german(b):
            auth_note = ("Zuständig ist die Behörde im Bundesland, in dem die Firma ihren Sitz hat. "
                         "Du kannst die Beschwerde auch bei deiner eigenen Behörde einreichen.")
        elif (b.get("countries") or "") and set(str(b.get("countries")).split(",")) <= {"us"}:
            auth_note = "Die Firma sitzt außerhalb der EU. Deine Behörde prüft, was sie tun kann."
        else:
            auth_note = ("Die Firma sitzt nicht in Deutschland. Deine Behörde nimmt die Beschwerde an "
                         "und stimmt sich mit der Behörde im Land der Firma ab.")
    events = db.query("SELECT at, text FROM events WHERE request_id = ? ORDER BY at, id", (req["id"],))
    lines = []
    for e in events:
        if e["text"] in ("Anfrage angelegt",):
            continue
        lines.append("%s: %s" % (texts.fmt_date(e["at"]), e["text"]))
    current = [texts.addr_text(a) for a in profile.get("addresses") or [] if a.get("current") and texts.addr_text(a)]
    contact = (db.get("mailbox") or {}).get("address") or ""
    ctx = {
        "sent_date": texts.fmt_date(req.get("sent_at")),
        "broker_name": b.get("name", ""),
        "broker_contact": "\n".join(x for x in ((b.get("address") or "").replace("\n", ", "), b.get("email") or "") if x),
        "history": "Bisheriger Verlauf:\n" + "\n".join(lines) if lines else "",
        "contact": contact,
        "name": texts.full_name(profile),
        "address": current[0] if current else "",
    }
    subject, body = texts.complaint_text(ctx, swiss=swiss)
    return {"subject": subject, "body": body, "authority": auth, "state": state, "authority_note": auth_note}


# ----------------------------------------------------------------------------- Hintergrund

STOP = threading.Event()   # wird beim Beenden gesetzt: laufende Etappe nach der aktuellen Mail abbrechen


class Scheduler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="spurlos-scheduler")
        self.stop_event = STOP
        self.last_poll = 0.0
        self.last_deadline = 0.0
        self.poll_failures = 0
        self._updating = False
        STOP.clear()

    def run(self):
        time.sleep(5)
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                db.put("last_send_error", "Hintergrund: %s" % str(exc)[:200])
            self.stop_event.wait(60)

    def tick(self):
        if not db.get("setup_done") or not db.get("started"):
            return
        with _RUN_LOCK:
            sending = db.get("sending")
            now = time.time()
            wait = int(sending.get("poll_minutes") or 15) * 60
            if self.poll_failures:
                wait = min(4 * 3600, wait * 2 ** self.poll_failures)   # bei Fehlern seltener versuchen
            if now - self.last_poll >= wait:
                _busy("Postfach abrufen und Antworten einordnen")
                result = poll()
                _busy(None)
                if result.get("ok"):
                    self.poll_failures = 0
                elif result.get("unreachable"):
                    self.last_poll = now - wait + 180   # kein Netz: in 3 Minuten noch einmal
                else:
                    self.poll_failures += 1
                    self.last_poll = now
                if result.get("ok"):
                    self.last_poll = now
            _busy("Anfragen verschicken")
            send_due()
            _busy(None)
            if now - self.last_deadline >= 3600:
                check_deadlines()
                self.last_deadline = now
        last = _parse(db.get("last_broker_update"))
        if (last is None or datetime.now() - last > timedelta(days=7)) and not self._updating:
            # Download der Firmenlisten (bis zu 90 s) läuft im eigenen Thread, damit die Oberfläche nicht hängt.
            self._updating = True
            threading.Thread(target=self._update_brokers, name="spurlos-brokers", daemon=True).start()

    def _update_brokers(self):
        try:
            info = brokers.update_all()
            if info.get("incogni", {}).get("added"):
                notify("Neue Firmen auf der Händlerliste")
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._updating = False


BUSY = {"what": None, "since": None}   # was die Hintergrund-Abläufe gerade tun (für die Oberfläche)


class Busy(Exception):
    pass


def run_locked(fn, *args, **kwargs):
    """Aus der Oberfläche: kurz warten; läuft gerade ein langer Abruf, lieber sofort Bescheid sagen."""
    if not _RUN_LOCK.acquire(timeout=8):
        raise Busy("Spurlos ist gerade beschäftigt (%s). Bitte gleich noch einmal versuchen." % (BUSY["what"] or "Postfach abrufen"))
    try:
        return fn(*args, **kwargs)
    finally:
        _RUN_LOCK.release()


def _busy(what):
    BUSY["what"] = what
    BUSY["since"] = db.now() if what else None
