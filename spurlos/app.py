"""Lokaler Webserver für die Oberfläche (nur 127.0.0.1)."""
from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime

from flask import Flask, abort, jsonify, make_response, redirect, request, send_from_directory

from . import __version__, brokers, classify, config, db, engine, mail, secrets_store, texts

TOKEN = secrets.token_urlsafe(24)
PORT = {"value": 8765}


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    # ------------------------------------------------------------------ Schutz
    @app.before_request
    def guard():
        host = (request.host or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            abort(403)
        if request.path.startswith("/api/"):
            if request.cookies.get("spurlos") != TOKEN or request.headers.get("X-Spurlos") != "1":
                abort(403)

    @app.after_request
    def headers(resp):
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; frame-ancestors 'none'")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ------------------------------------------------------------------ Seiten
    @app.route("/")
    def index():
        token = request.args.get("t")
        if token:
            if not secrets.compare_digest(token, TOKEN):
                abort(403)
            resp = make_response(redirect("/"))
            resp.set_cookie("spurlos", TOKEN, httponly=True, samesite="Strict")
            return resp
        if request.cookies.get("spurlos") != TOKEN:
            return ("Bitte starte Spurlos über das Programm. Der Link öffnet sich dann automatisch.", 403)
        return send_from_directory(config.WEB_DIR, "index.html")

    @app.route("/static/<path:name>")
    def static_files(name):
        return send_from_directory(config.WEB_DIR, name)

    # ------------------------------------------------------------------ Hilfen
    def body() -> dict:
        return request.get_json(silent=True) or {}

    def ok(**data):
        data.setdefault("ok", True)
        return jsonify(data)

    def fail(message: str, code: int = 400):
        return jsonify({"ok": False, "error": message}), code

    @app.errorhandler(mail.MailError)
    def mail_error(exc):
        return fail(str(exc))

    @app.errorhandler(ValueError)
    def value_error(exc):
        return fail(str(exc))

    @app.errorhandler(Exception)
    def any_error(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        app.logger.exception("Fehler bei %s", request.path)
        return fail("Interner Fehler: %s" % str(exc)[:200], 500)

    # ------------------------------------------------------------------ Grundzustand
    @app.get("/api/bootstrap")
    def bootstrap():
        # Nicht den Schlüsselbund lesen: Auf dem Mac kann das eine Rückfrage auslösen,
        # und solange die offen ist, hinge der Start. Ein Merker in der Datenbank reicht.
        mb = db.get("mailbox")
        mb["has_password"] = bool(mb.get("password_saved", mb.get("verified")))
        ai = db.get("ai")
        ai["has_key"] = bool(ai.get("key_saved", ai.get("provider") == "cloud"))
        return ok(
            version=__version__,
            setup_done=db.get("setup_done"), setup_step=db.get("setup_step"), started=db.get("started"),
            profile=db.get("profile"), state=db.get("state"), countries=db.get("countries"), groups=db.get("groups"),
            mailbox=mb, sending=db.get("sending"), ai=ai,
            providers={k: v["label"] for k, v in mail.PROVIDERS.items()},
            all_countries=brokers.COUNTRIES, group_meta=brokers.GROUPS, group_order=brokers.GROUP_ORDER,
            states=sorted(brokers.authorities().keys()), secret_storage=secrets_store.storage_name(),
            data_dir=str(config.data_dir()), templates=texts.TEMPLATE_LIST,
            categories={k: v["label"] for k, v in classify.CATEGORIES.items()},
        )

    @app.post("/api/profile")
    def save_profile():
        data = body()
        if "profile" in data:
            db.put("profile", data["profile"])
        if "state" in data:
            db.put("state", data["state"])
        if "countries" in data:
            db.put("countries", [c for c in data["countries"] if c in brokers.COUNTRIES] or ["de"])
        if db.get("started"):
            engine.run_locked(engine.build_requests)
        return ok()

    @app.post("/api/groups")
    def save_groups():
        groups = db.get("groups")
        groups.update({k: bool(v) for k, v in (body().get("groups") or {}).items() if k in brokers.GROUPS})
        db.put("groups", groups)
        if db.get("started"):
            engine.run_locked(engine.build_requests)
        return ok(groups=groups)

    @app.post("/api/setup")
    def setup_state():
        data = body()
        if "step" in data:
            db.put("setup_step", int(data["step"]))
        if "done" in data:
            db.put("setup_done", bool(data["done"]))
        return ok()

    # ------------------------------------------------------------------ Postfach
    @app.post("/api/mailbox/detect")
    def detect():
        data = body()
        provider = data.get("provider") or "domain"
        address = (data.get("address") or "").strip()
        if provider != "domain":
            result = mail.provider_defaults(provider)
        else:
            result = mail.autodetect(address) or mail.provider_defaults("domain")
        return ok(servers=result)

    def _merge_mailbox(data: dict) -> dict:
        cfg = db.get("mailbox")
        for key in ("provider", "address", "display_name", "username", "imap_host", "imap_port", "smtp_host",
                    "smtp_port", "smtp_security", "save_sent", "sent_folder"):
            if key in (data.get("mailbox") or {}):
                cfg[key] = data["mailbox"][key]
        cfg["imap_port"] = int(cfg.get("imap_port") or 993)
        cfg["smtp_port"] = int(cfg.get("smtp_port") or 587)
        if not cfg.get("username"):
            cfg["username"] = cfg.get("address")
        if cfg.get("provider") == "gmail":
            cfg["save_sent"] = False
        return cfg

    @app.post("/api/mailbox/test")
    def test_mailbox():
        data = body()
        cfg = _merge_mailbox(data)
        password = data.get("password") or secrets_store.get_secret("mailbox") or ""
        steps = []
        try:
            imap = mail.connect_imap(cfg, password)
            folder = mail.find_sent_folder(imap)
            imap.logout()
            steps.append({"name": "Posteingang (IMAP)", "ok": True, "detail": "Anmeldung erfolgreich"})
        except mail.MailError as exc:
            steps.append({"name": "Posteingang (IMAP)", "ok": False, "detail": str(exc)})
            return ok(passed=False, steps=steps)
        try:
            smtp = mail.connect_smtp(cfg, password)
            smtp.quit()
            steps.append({"name": "Postausgang (SMTP)", "ok": True, "detail": "Anmeldung erfolgreich"})
        except mail.MailError as exc:
            steps.append({"name": "Postausgang (SMTP)", "ok": False, "detail": str(exc)})
            return ok(passed=False, steps=steps)
        if data.get("send_test"):
            try:
                stamp = datetime.now().strftime("%H:%M:%S")
                mail.send(cfg, password, cfg["address"], "Spurlos Testmail %s" % stamp,
                          "Diese Testmail hat Spurlos an sich selbst geschickt. Du kannst sie löschen.")
                steps.append({"name": "Testmail an dich selbst", "ok": True, "detail": "Verschickt um %s" % stamp})
            except mail.MailError as exc:
                steps.append({"name": "Testmail an dich selbst", "ok": False, "detail": str(exc)})
                return ok(passed=False, steps=steps)
        steps.append({"name": "Gesendet-Ordner", "ok": True,
                      "detail": ("Kopien landen in %s" % folder.strip('"')) if folder and cfg.get("save_sent")
                      else "Der Anbieter legt Kopien selbst ab" if not cfg.get("save_sent") else "Kein Gesendet-Ordner gefunden"})
        return ok(passed=True, steps=steps)

    @app.post("/api/mailbox/save")
    def save_mailbox():
        data = body()
        cfg = _merge_mailbox(data)
        if data.get("password"):
            secrets_store.set_secret("mailbox", data["password"])
            cfg["password_saved"] = True
        cfg["verified"] = bool(data.get("verified", cfg.get("verified")))
        db.put("mailbox", cfg)
        return ok()

    # ------------------------------------------------------------------ Einstellungen
    @app.post("/api/settings/sending")
    def save_sending():
        data = body()
        cfg = db.get("sending")
        for key in ("per_day", "reminder_days", "complaint_days", "poll_minutes"):
            if key in data:
                cfg[key] = max(1, int(data[key]))
        for key in ("auto_remind", "notifications", "first_batch_now"):
            if key in data:
                cfg[key] = bool(data[key])
        if "send_time" in data and len(str(data["send_time"])) == 5:
            cfg["send_time"] = str(data["send_time"])
        db.put("sending", cfg)
        if db.get("started"):
            engine.run_locked(engine.plan_batches, False)
        return ok(sending=cfg)

    @app.post("/api/settings/ai")
    def save_ai():
        data = body()
        cfg = db.get("ai")
        for key in ("provider", "ollama_model", "ollama_url", "cloud_vendor", "cloud_model"):
            if key in data:
                cfg[key] = data[key]
        if data.get("api_key"):
            secrets_store.set_secret("ai_cloud", data["api_key"])
            cfg["key_saved"] = True
        db.put("ai", cfg)
        return ok(ai=cfg)

    @app.get("/api/ai/status")
    def ai_status():
        apple_ok, apple_text = classify.apple_status()
        cfg = db.get("ai")
        try:
            models = classify.ollama_models(cfg.get("ollama_url") or "http://127.0.0.1:11434")
            ollama = {"ok": True, "models": models}
        except Exception:  # noqa: BLE001
            ollama = {"ok": False, "models": []}
        return ok(apple={"ok": apple_ok, "text": apple_text}, ollama=ollama,
                  cloud={"has_key": bool(secrets_store.get_secret("ai_cloud"))})

    @app.post("/api/ai/test")
    def ai_test():
        sample = {"subject": "Re: GDPR request [DA-999]",
                  "body": "Hello, we searched our systems for the email addresses you listed. We do not hold any "
                          "personal data about you. No further action is needed.", "attachments": []}
        cfg = db.get("ai")
        started = datetime.now()
        result = classify.classify(sample, cfg, secrets_store.get_secret("ai_cloud"))
        seconds = (datetime.now() - started).total_seconds()
        return ok(category=classify.CATEGORIES[result["category"]]["label"], ai=result.get("ai_category"),
                  note=result.get("ai_note"), seconds=round(seconds, 1))

    # ------------------------------------------------------------------ Firmen
    @app.get("/api/brokers")
    def list_brokers():
        groups = db.get("groups")
        countries = set(db.get("countries") or ["de"])
        reqs = {r["broker_id"]: r for r in db.query("SELECT broker_id, ref, status, label, outcome FROM requests")}
        out = []
        for b in db.query("SELECT * FROM brokers ORDER BY name COLLATE NOCASE"):
            r = reqs.get(b["id"])
            out.append({
                "id": b["id"], "name": b["name"], "category": b["category"], "grp": b["grp"], "origin": b["origin"],
                "email": b["email"], "webform": b["webform"], "webform_only": bool(b["webform_only"]),
                "lang": b["lang"], "website": b["website"], "what": b["what"], "source_url": b["source_url"],
                "countries": b["countries"], "is_new": bool(b["is_new"]), "active": bool(b["active"]),
                "confirmed": bool(b["confirmed"]), "contact": brokers.contact_kind(b),
                "relevant": brokers.is_relevant(b, countries), "selected": brokers.selected(b, groups, countries),
                "request": {"ref": r["ref"], "status": r["status"], **_status_view(r)} if r else None,
            })
        return ok(brokers=out, update=db.get("broker_update_info"), last_update=db.get("last_broker_update"))

    @app.post("/api/brokers")
    def save_broker():
        data = body()
        name = (data.get("name") or "").strip()
        if not name:
            return fail("Bitte einen Namen angeben.")
        bid = data.get("id") or ("own-" + brokers.slugify(name))
        existing = db.query_one("SELECT * FROM brokers WHERE id = ?", (bid,)) or {}
        entry = dict(existing)
        entry.update({
            "id": bid, "name": name, "email": (data.get("email") or "").strip() or None,
            "webform": (data.get("webform") or "").strip() or None, "webform_only": bool(data.get("webform_only")),
            "lang": data.get("lang") or existing.get("lang") or "de", "grp": data.get("grp") or existing.get("grp") or "consumer",
            "category": data.get("category") or existing.get("category") or "Eigene Ergänzung",
            "origin": existing.get("origin") or "eigene", "countries": existing.get("countries") or "all",
            "transport": "email", "notes": data.get("notes") or existing.get("notes"),
        })
        brokers.upsert(entry)
        if existing:
            db.execute("UPDATE brokers SET user_edited = 1 WHERE id = ?", (bid,))   # Schalter bleibt, wie er war
        else:
            db.execute("UPDATE brokers SET user_edited = 1, active = 1 WHERE id = ?", (bid,))
        req = db.query_one("SELECT * FROM requests WHERE broker_id = ?", (bid,))
        if req and req["status"] in ("no_contact", "letter", "webform"):
            kind = brokers.contact_kind(db.query_one("SELECT * FROM brokers WHERE id = ?", (bid,)))
            new_status = {"email": "planned", "webform": "webform"}.get(kind, req["status"])
            db.execute("UPDATE requests SET status = ?, channel = ? WHERE id = ?", (new_status, kind, req["id"]))
        if db.get("started"):
            engine.run_locked(engine.build_requests)
        return ok(id=bid)

    @app.post("/api/brokers/<bid>/active")
    def broker_active(bid):
        db.execute("UPDATE brokers SET active = ?, is_new = 0 WHERE id = ?", (1 if body().get("active") else 0, bid))
        if db.get("started"):
            engine.run_locked(engine.build_requests)
        return ok()

    @app.post("/api/brokers/seen")
    def brokers_seen():
        db.execute("UPDATE brokers SET is_new = 0")
        return ok()

    @app.post("/api/brokers/update")
    def brokers_update():
        info = brokers.update_all()
        if db.get("started"):
            engine.run_locked(engine.build_requests)
        return ok(info=info)

    # ------------------------------------------------------------------ Start und Abläufe
    @app.post("/api/start")
    def start():
        if not engine.profile_ok():
            return fail("Bitte zuerst Name und mindestens eine Adresse oder E-Mail-Adresse eintragen.")
        if not engine.mailbox_ready()[0]:
            return fail("Bitte zuerst das Postfach einrichten.")
        created = engine.run_locked(engine.build_requests)
        db.put("started", True)
        db.put("setup_done", True)
        threading.Thread(target=lambda: engine.run_locked(engine.send_due), daemon=True).start()
        return ok(created=created)

    @app.post("/api/poll")
    def poll_now():
        result = engine.run_locked(engine.poll)
        engine.run_locked(engine.check_deadlines)
        return ok(**result) if result.get("ok") else fail(result.get("error") or "Abruf fehlgeschlagen")

    @app.post("/api/send")
    def send_now():
        result = engine.run_locked(engine.send_due, True)
        return ok(**result)

    # ------------------------------------------------------------------ Übersicht
    def _status_view(r: dict) -> dict:
        grp, label = engine.STATUS.get(r["status"], ("todo", r["status"]))
        if r["status"] == "done":
            label = engine.OUTCOME_LABEL.get(r.get("outcome") or "", "Erledigt")
        elif r.get("label"):
            label = r["label"]
        return {"group": grp, "label": label}

    @app.get("/api/overview")
    def overview():
        rows = db.query("SELECT r.*, b.name AS broker_name FROM requests r JOIN brokers b ON b.id = r.broker_id")
        counts = {"done": 0, "wait": 0, "todo": 0, "overdue": 0, "planned": 0, "missing": 0}
        for r in rows:
            counts[_status_view(r)["group"]] = counts.get(_status_view(r)["group"], 0) + 1
        total = len(rows)
        sent = sum(1 for r in rows if r["sent_at"])
        outcomes = {}
        for r in rows:
            if r["status"] == "done":
                outcomes[r["outcome"] or "manual"] = outcomes.get(r["outcome"] or "manual", 0) + 1
        replies = db.query_one("SELECT COUNT(DISTINCT request_id) AS n FROM messages WHERE direction = 'in' AND kind = 'reply'")["n"]
        inbox = db.query_one("SELECT COUNT(*) AS n FROM messages WHERE direction = 'in' AND kind IN ('reply', 'unassigned') "
                             "AND reviewed = 0")["n"]
        todos = []
        if inbox:
            names = [r["broker_name"] for r in db.query(
                "SELECT DISTINCT b.name AS broker_name FROM messages m JOIN requests r ON r.id = m.request_id "
                "JOIN brokers b ON b.id = r.broker_id WHERE m.direction = 'in' AND m.kind = 'reply' AND m.reviewed = 0 LIMIT 5")]
            todos.append({"n": inbox, "title": "Antworten prüfen", "sub": ", ".join(names), "href": "#/eingang", "cta": "Prüfen"})
        for status, title, cta in (("webform", "Webformulare ausfüllen", "Ansehen"),
                                   ("failed", "Zustellung fehlgeschlagen", "Ansehen"),
                                   ("complaint", "Beschwerde vorbereiten", "Ansehen")):
            items = [r for r in rows if r["status"] == status]
            if items:
                todos.append({"n": len(items), "title": title, "sub": ", ".join(i["broker_name"] for i in items[:4]),
                              "href": "#/anfragen?f=todo", "cta": cta})
        missing = [r for r in rows if r["status"] in ("no_contact", "letter")]
        if missing:
            todos.append({"n": len(missing), "title": "Kontakt fehlt", "sub": ", ".join(i["broker_name"] for i in missing[:4]),
                          "href": "#/anfragen?f=missing", "cta": "Ergänzen"})
        plan = []
        nxt = db.query_one("SELECT planned_for, COUNT(*) AS n FROM requests WHERE status = 'planned' AND planned_for IS NOT NULL "
                           "GROUP BY substr(planned_for, 1, 10) ORDER BY planned_for LIMIT 1")
        if nxt and nxt["n"]:
            plan.append({"when": nxt["planned_for"], "title": "%d Anfragen senden" % nxt["n"],
                         "sub": "%d weitere danach" % max(0, counts["planned"] - nxt["n"])})
        sending = db.get("sending")
        plan.append({"when": "alle %d Min." % int(sending.get("poll_minutes") or 15), "title": "Postfach abrufen und Antworten zuordnen",
                     "sub": "Zuletzt: %s" % (db.get("last_poll") or "noch nie")})
        due = db.query_one("SELECT r.due_at, b.name FROM requests r JOIN brokers b ON b.id = r.broker_id "
                           "WHERE r.status IN ('sent', 'ack', 'followup') AND r.due_at IS NOT NULL ORDER BY r.due_at LIMIT 1")
        if due:
            plan.append({"when": due["due_at"], "title": "Nächste Frist: %s" % due["name"],
                         "sub": "Ohne Antwort geht automatisch eine Erinnerung raus" if sending.get("auto_remind") else "Dann bekommst du einen Hinweis"})
        plan.append({"when": "wöchentlich", "title": "Händlerliste auf neue Firmen prüfen",
                     "sub": "Zuletzt: %s" % (db.get("last_broker_update") or "noch nie")})
        activity = db.query("SELECT e.at, e.kind, e.text, r.ref, r.status, r.label, r.outcome, b.name FROM events e "
                            "LEFT JOIN requests r ON r.id = e.request_id LEFT JOIN brokers b ON b.id = r.broker_id "
                            "WHERE e.kind != 'created' ORDER BY e.at DESC, e.id DESC LIMIT 8")
        for a in activity:
            a.update(_status_view({"status": a["status"] or "planned", "label": a["label"], "outcome": a["outcome"]}))
        mb = db.get("mailbox")
        return ok(counts=counts, total=total, sent=sent, replies=replies, outcomes=outcomes, todos=todos, plan=plan,
                  activity=activity, inbox=inbox, started=db.get("started"),
                  mailbox={"address": mb.get("address"), "ok": not db.get("last_poll_error"),
                           "error": db.get("last_poll_error"), "send_error": db.get("last_send_error"),
                           "last_poll": db.get("last_poll")},
                  ai=db.get("ai").get("provider"))

    # ------------------------------------------------------------------ Anfragen
    @app.get("/api/requests")
    def list_requests():
        rows = db.query("SELECT r.*, b.name AS broker_name, b.category, b.grp, b.lang, b.countries, b.email, b.webform "
                        "FROM requests r JOIN brokers b ON b.id = r.broker_id ORDER BY r.id")
        for r in rows:
            r.update(_status_view(r))
        return ok(requests=rows)

    @app.get("/api/requests/<ref>")
    def request_detail(ref):
        r = db.query_one("SELECT * FROM requests WHERE ref = ?", (ref,))
        if not r:
            abort(404)
        r.update(_status_view(r))
        b = db.query_one("SELECT * FROM brokers WHERE id = ?", (r["broker_id"],))
        events = db.query("SELECT at, kind, text FROM events WHERE request_id = ? ORDER BY at, id", (r["id"],))
        messages = db.query("SELECT id, direction, kind, subject, date, from_addr, to_addr, category, reviewed FROM messages "
                            "WHERE request_id = ? ORDER BY id", (r["id"],))
        return ok(request=r, broker=b, events=events, messages=messages)

    @app.get("/api/requests/<ref>/preview")
    def request_preview(ref):
        r = db.query_one("SELECT * FROM requests WHERE ref = ?", (ref,))
        if not r:
            abort(404)
        sent = db.query_one("SELECT subject, body, to_addr FROM messages WHERE request_id = ? AND direction = 'out' "
                            "AND kind = 'request' ORDER BY id LIMIT 1", (r["id"],))
        if sent:
            return ok(subject=sent["subject"], body=sent["body"], to=sent["to_addr"], sent=True)
        b = db.query_one("SELECT * FROM brokers WHERE id = ?", (r["broker_id"],))
        subject, text = engine.render_request(r, b)
        return ok(subject=subject, body=text, to=b.get("email") or b.get("webform") or "", sent=False)

    @app.get("/api/messages/<int:mid>")
    def message_detail(mid):
        m = db.query_one("SELECT * FROM messages WHERE id = ?", (mid,))
        if not m:
            abort(404)
        return ok(message=m)

    @app.post("/api/requests/<ref>/action")
    def request_action(ref):
        data = body()
        engine.run_locked(engine.action, ref, data.get("action") or "", data.get("data") or {})
        return ok()

    @app.get("/api/requests/<ref>/complaint")
    def request_complaint(ref):
        return ok(**engine.complaint(ref))

    @app.get("/api/sample")
    def sample():
        """Vorschau einer Anfrage vor dem Start."""
        lang = request.args.get("lang") or "de"
        kind = request.args.get("kind") or "request"
        profile = db.get("profile")
        ctx = {"ref": "DA-001", "name": texts.full_name(profile) or "Max Mustermann",
               "id_block": texts.id_block(profile, lang) or "Name: …", "sent_date": texts.fmt_date(db.now(), lang),
               "due_date": texts.fmt_date(db.now(), lang), "original": "(ursprüngliche Anfrage)"}
        if kind in ("request", "access"):
            subject, text = texts.request_text(lang, ctx, access_only=kind == "access")
        elif kind == "complaint":
            subject, text = texts.complaint_text(dict(ctx, broker_name="Beispiel GmbH", broker_contact="datenschutz@beispiel.de",
                                                      history="", contact=db.get("mailbox").get("address") or "", address=""),
                                                 swiss=lang == "ch")
        else:
            subject, text = texts.followup_text(kind, lang, ctx)
        return ok(subject=subject, body=text)

    # ------------------------------------------------------------------ Eingang
    @app.get("/api/inbox")
    def inbox():
        rows = db.query("SELECT m.id, m.subject, m.date, m.from_addr, m.reply_to, m.folder, m.link, m.body, m.attachments, "
                        "m.category, m.confidence, m.rule, m.match_text, m.ai_category, m.ai_note, r.ref, r.status, "
                        "b.name AS broker_name, b.grp, b.lang "
                        "FROM messages m JOIN requests r ON r.id = m.request_id JOIN brokers b ON b.id = r.broker_id "
                        "WHERE m.direction = 'in' AND m.kind = 'reply' AND m.reviewed = 0 ORDER BY m.date DESC")
        for r in rows:
            r["category_label"] = classify.CATEGORIES.get(r["category"], {}).get("label", "Unklar")
            r["ai_label"] = classify.CATEGORIES.get(r["ai_category"], {}).get("label") if r["ai_category"] else None
        unassigned = db.query("SELECT id, subject, date, from_addr, reply_to, folder, link, body, attachments, category "
                              "FROM messages WHERE kind = 'unassigned' AND reviewed = 0 ORDER BY date DESC")
        for u in unassigned:
            u["category_label"] = classify.CATEGORIES.get(u["category"], {}).get("label", "Unklar")
        targets = db.query("SELECT r.ref, b.name FROM requests r JOIN brokers b ON b.id = r.broker_id "
                           "WHERE r.sent_at IS NOT NULL AND r.status != 'done' ORDER BY b.name COLLATE NOCASE")
        return ok(items=rows, unassigned=unassigned, targets=targets)

    @app.post("/api/inbox/<int:mid>/assign")
    def inbox_assign(mid):
        result = engine.run_locked(engine.assign_message, mid, body().get("ref") or None)
        return ok(**result)

    @app.post("/api/inbox/<int:mid>/confirm")
    def inbox_confirm(mid):
        category = body().get("category")
        if category not in classify.CATEGORIES:
            return fail("Bitte eine Einordnung wählen.")
        result = engine.run_locked(engine.confirm_reply, mid, category)
        return ok(**result)

    # ------------------------------------------------------------------ Daten
    @app.get("/api/export")
    def export():
        data = {"exported_at": db.now(), "version": __version__,
                "settings": {k: db.get(k) for k in ("profile", "state", "countries", "groups", "mailbox", "sending", "ai")},
                "brokers": db.query("SELECT * FROM brokers WHERE user_edited = 1 OR origin = 'eigene'"),
                "requests": db.query("SELECT * FROM requests"), "messages": db.query("SELECT * FROM messages"),
                "events": db.query("SELECT * FROM events")}
        resp = make_response(json.dumps(data, ensure_ascii=False, indent=1))
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
        resp.headers["Content-Disposition"] = "attachment; filename=spurlos-sicherung-%s.json" % datetime.now().strftime("%Y-%m-%d")
        return resp

    @app.post("/api/reset")
    def reset():
        if body().get("confirm") != "LÖSCHEN":
            return fail("Bitte zur Bestätigung LÖSCHEN eintippen.")

        def wipe():
            next_ref = db.get("next_ref")      # Aktenzeichen nicht neu vergeben: alte Antworten dürfen nicht passen
            for table in ("events", "messages", "requests", "brokers", "settings"):
                db.execute("DELETE FROM %s" % table)
            db.put("next_ref", next_ref)
            secrets_store.delete_secret("mailbox")
            secrets_store.delete_secret("ai_cloud")
            brokers.load_seed()
        engine.run_locked(wipe)
        return ok()

    return app
