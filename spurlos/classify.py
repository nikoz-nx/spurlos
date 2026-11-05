"""Antworten einordnen: Regeln auf Deutsch und Englisch, optional mit KI."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CATEGORIES = {
    "no_data": {"label": "Keine Daten gespeichert", "done": True},
    "deleted": {"label": "Daten gelöscht", "done": True},
    "objection": {"label": "Widerspruch bestätigt", "done": True},
    "access": {"label": "Auskunft erteilt", "done": False},
    "id_request": {"label": "Ausweis verlangt", "done": False},
    "clarify": {"label": "Rückfrage", "done": False},
    "webform": {"label": "Verweis auf Webformular", "done": False},
    "confirm": {"label": "Bestätigungslink", "done": False},
    "refused": {"label": "Abgelehnt", "done": False},
    "unknown": {"label": "Unklar", "done": False},
}

# Reihenfolge = Priorität bei mehreren Treffern (siehe decide()).
RULES = {
    "id_request": [
        r"\b(personal)?ausweis(kopie|dokument)?\b", r"identit[äa]ts?nachweis", r"identit[äa]t\s+(zu\s+)?(best[äa]tigen|verifizieren|nachweisen|pr[üu]fen)",
        r"verify\s+your\s+identity", r"identity\s+verification", r"proof\s+of\s+(your\s+)?identity",
        r"(government|state)[- ]issued\s+(photo\s+)?id", r"copy\s+of\s+(your|a)\s+(valid\s+)?(id|passport|driver)",
        r"reisepass", r"passport",
    ],
    "clarify": [
        r"r[üu]ckfrage", r"(bitte|k[öo]nnten\s+sie|k[öo]nnen\s+sie)\b[^.?!]{0,80}\b(pr[äa]zisieren|mitteilen|angeben|kl[äa]ren|erl[äa]utern)",
        r"could\s+you\s+(please\s+)?(clarify|confirm|specify|provide|let\s+us\s+know)",
        r"please\s+(clarify|specify|confirm\s+which)", r"which\s+of\s+the\s+(listed|following|provided)",
        r"need\s+(some\s+)?(more|additional|further)\s+information",
    ],
    "confirm": [
        r"(klicken|tippen)\s+sie\s+(bitte\s+)?(auf\s+)?(den|diesen|folgenden|untenstehenden)\s+(link|button|schaltfl[äa]che)",
        r"best[äa]tigen\s+sie\s+[^.]{0,60}(link|klick)", r"best[äa]tigungslink",
        r"click\s+(on\s+)?(the|this)\s+(link|button)\s+(below\s+)?to\s+(confirm|verify|complete|proceed)",
        r"(confirm|verify)\s+your\s+(email(\s+address)?|request)\s+(by|via)\s+clicking",
        r"please\s+(confirm|verify)\s+your\s+(email(\s+address)?|request)",
        r"verification\s+link", r"confirmation\s+link",
    ],
    "webform": [
        r"(web)?formular", r"privacy\s+(center|centre|portal|request\s+form)", r"web\s?form",
        r"submit\s+(your|a)\s+request\s+(via|through|using|on)", r"(request|opt[- ]out)\s+form",
        r"\bportal\b",
    ],
    "refused": [
        r"(lehnen|weisen)\s+[^.]{0,60}\bab\b", r"nicht\s+nachkommen", r"kein(en)?\s+anspruch", r"abgelehnt",
        r"(cannot|can\s*not|unable\s+to|will\s+not)\s+(comply|process|fulfil|fulfill|honou?r)",
        r"(request|it)\s+(is|has\s+been)\s+(denied|declined|rejected)",
    ],
    "deleted": [
        r"(haben|wurden|wurde|sind)\s+[^.]{0,80}gel[öo]scht", r"l[öo]schung\s+[^.]{0,60}(durchgef[üu]hrt|vorgenommen|best[äa]tig|veranlasst|erfolgt)",
        r"we\s+have\s+(now\s+)?(deleted|removed|erased|purged)", r"(has|have|was|were)\s+been\s+(permanently\s+)?(deleted|removed|erased|purged)",
        r"deletion\s+(request\s+)?(is|has\s+been|was)\s+(complete|completed|processed|confirmed)",
        r"(deleted|removed|erased)\s+(all|any|your)\s+(records|data|information|personal)",
    ],
    "no_data": [
        r"keine\s+(personenbezogenen\s+)?daten\s+[^.]{0,60}(gespeichert|vorliegen|verarbeit|vorhanden|gefunden)",
        r"(liegen|sind)\s+(uns\s+|bei\s+uns\s+)?keine\s+[^.]{0,40}daten", r"nicht\s+in\s+unserem?\s+(datenbestand|datenbank|system)",
        r"we\s+(do\s+not|don't|did\s+not|didn't)\s+(hold|have|store|process|maintain|possess|find)\s+any",
        r"no\s+(personal\s+)?(data|records|information|results)\s+(was\s+|were\s+)?(found|held|stored|associated|located)",
        r"(could|were)\s+not\s+(able\s+to\s+)?(find|locate|identify)\s+(any\s+)?(records|data|information|personal)",
        r"not\s+(present|found)\s+in\s+our\s+(database|records|systems)",
    ],
    "objection": [
        r"widerspruch\s+[^.]{0,60}(vermerkt|eingetragen|umgesetzt|ber[üu]cksichtigt|aufgenommen)",
        r"werbe(sperr|sperre|widerspruch)", r"sperr(liste|datei|vermerk)",
        r"suppression\s+list", r"(opted|been\s+opted)\s+out", r"do[- ]not[- ](mail|contact|sell)\s+list",
        r"objection\s+[^.]{0,40}(recorded|processed|noted|implemented)",
    ],
    "access": [
        r"(erteilen|geben)\s+wir\s+ihnen\s+[^.]{0,30}auskunft", r"\bauskunft\b[^.]{0,80}(anbei|beigef[üu]gt|anlage|wie\s+folgt|erteilt)",
        r"folgende\s+(daten|angaben)\s+[^.]{0,40}gespeichert", r"kopie\s+(ihrer|der)\s+(personenbezogenen\s+)?daten",
        r"(attached|enclosed|below)\s+[^.]{0,60}(copy|data|information|report)", r"here\s+is\s+(a\s+copy|the\s+data|your\s+data)",
        r"(access|subject\s+access)\s+request\s+[^.]{0,40}(attached|completed|fulfilled)",
        r"we\s+(hold|have|store|process)\s+the\s+following",
    ],
}

COMPILED = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in RULES.items()}

AUTO_SUBJECT = re.compile(
    r"(automatische\s+antwort|abwesenheit|out\s+of\s+(the\s+)?office|auto(matic)?[- ]?reply|autoreply|"
    r"eingangsbest[äa]tigung|we\s+have\s+received\s+your|ticket\s*#?\s*\d+|request\s+received|"
    r"wir\s+haben\s+ihre\s+(anfrage|nachricht)\s+erhalten)", re.IGNORECASE)
AUTO_BODY = re.compile(
    r"(wir\s+haben\s+ihre\s+(anfrage|nachricht|e-?mail)\s+(erhalten|bekommen)|"
    r"we\s+(have\s+)?received\s+your\s+(request|message|email)|this\s+is\s+an\s+automat(ic|ed)\s+(reply|response|message)|"
    r"dies\s+ist\s+eine\s+automatische)", re.IGNORECASE)
BOUNCE_FROM = re.compile(r"(mailer-daemon|postmaster|mail\s*delivery)", re.IGNORECASE)
BOUNCE_SUBJECT = re.compile(r"(undeliver|delivery\s+status|nicht\s+zustellbar|unzustellbar|returned\s+mail|"
                            r"delivery\s+failure|failure\s+notice|mail\s+delivery\s+failed)", re.IGNORECASE)


NOT_FAILED_SUBJECT = re.compile(r"(delay|verz[öo]ger|warning|warnung|success|relayed|delivered|zugestellt\b(?!.*nicht)|"
                                r"gelesen|read\s*:|read\s+receipt|lesebest[äa]tigung)", re.IGNORECASE)
FAILED_BODY = re.compile(r"(\b5\.\d\.\d+\b|\b55\d\b|user\s+unknown|no\s+such\s+user|does\s+not\s+exist|"
                         r"could\s+not\s+be\s+delivered|permanent(ly)?\s+(error|fail)|nicht\s+zugestellt\s+werden|"
                         r"unbekannt|existiert\s+nicht|address\s+rejected|mailbox\s+unavailable)", re.IGNORECASE)


def is_notice(msg: dict) -> bool:
    """Technische Meldung des Mailsystems (Lesebestätigung, Zustellbericht, Verzögerung)."""
    return bool(msg.get("report_type") or msg.get("is_report")
                or BOUNCE_FROM.search((msg.get("from_addr") or "") + " " + (msg.get("from_name") or "")))


def is_bounce(msg: dict) -> bool:
    """Nur echte, endgültige Unzustellbarkeit – keine Lesebestätigung, keine Verzögerungsmeldung."""
    if (msg.get("report_type") or "").lower() == "disposition-notification":
        return False
    actions = msg.get("dsn_actions") or []
    if actions:
        return any(a.startswith("failed") for a in actions)
    sender_hit = BOUNCE_FROM.search((msg.get("from_addr") or "") + " " + (msg.get("from_name") or ""))
    subject = msg.get("subject") or ""
    subject_hit = BOUNCE_SUBJECT.search(subject)
    if not (sender_hit or subject_hit or msg.get("is_report")):
        return False
    if NOT_FAILED_SUBJECT.search(subject) and not subject_hit:
        return False
    body = (msg.get("body") or "")[:6000]
    if re.search(r"(delay|verz[öo]gert|will\s+(retry|try\s+again)|wird\s+weiter\s+versucht)", subject + " " + body[:800],
                 re.IGNORECASE) and not FAILED_BODY.search(body):
        return False
    return bool(subject_hit or FAILED_BODY.search(body))


def is_auto_reply(msg: dict) -> bool:
    headers = msg.get("headers") or {}
    auto = headers.get("auto-submitted", "").strip().lower()
    if auto and auto != "no":
        return True
    if "x-autoreply" in headers or "x-autorespond" in headers:
        return True
    if headers.get("precedence", "").strip().lower() in ("auto_reply", "auto-reply"):
        return True
    subject_hit = AUTO_SUBJECT.search(msg.get("subject", "") or "")
    body = (msg.get("body") or "")[:1500]
    body_hit = AUTO_BODY.search(body)
    if not (subject_hit or body_hit):
        return False
    # Eine echte Antwort mit Inhalt ist keine bloße Eingangsbestätigung.
    substantive = any(match_rules(body).get(k) for k in ("no_data", "deleted", "access", "id_request", "refused"))
    return not substantive


# Ab hier beginnt in einer Antwort meist der zitierte Teil (unsere eigene Anfrage).
QUOTE_START = re.compile(
    r"(?im)^(\s*>|\s*-{2,}\s*(original|urspr[üu]ngliche|forwarded|weitergeleitete)\b|"
    r"\s*am\s.{4,140}\s(schrieb|hat\s+geschrieben)|\s*on\s.{4,160}\swrote:|"
    r"\s*(von|from)\s*:\s.+\n\s*(gesendet|sent|datum|date)\s*:)")
# Eindeutige Sätze aus unseren eigenen Briefen – kommen sie vor, ist der Rest ein Zitat.
OWN_TEXT = re.compile(
    r"(ich\s+wende\s+mich\s+mit\s+drei\s+anliegen|i\s+am\s+contacting\s+you\s+with\s+three\s+requests|"
    r"ich\s+bitte\s+(hiermit\s+|sie\s+)?um\s+auskunft\s+nach\s+art|i\s+am\s+requesting\s+access\s+to\s+my\s+personal|"
    r"damit\s+sie\s+mich\s+zuordnen\s+k[öo]nnen|to\s+identify\s+me,\s+please\s+use|"
    r"habe\s+ich\s+ihnen\s+eine\s+anfrage\s+nach|i\s+sent\s+you\s+a\s+request\s+under|"
    r"wie\s+in\s+meiner\s+anfrage\s+angek[üu]ndigt|as\s+announced\s+in\s+my\s+request|"
    r"sie\s+bitten\s+mich\s+um\s+eine\s+kopie\s+meines\s+ausweises|you\s+asked\s+me\s+for\s+a\s+copy\s+of\s+an\s+identity|"
    r"bitte\s+pr[üu]fen\s+sie\s+alle\s+angaben\s+aus\s+meiner|please\s+check\s+all\s+details\s+from\s+my\s+request)",
    re.IGNORECASE)
# Verneinung oder Zukunft kurz vor einem Treffer: „noch nicht gelöscht“, „once it has been deleted“
NOT_YET = re.compile(r"(\b(nicht|kein|keine|once|will\s+be|werden|wird|sobald|nachdem|after|if|falls|wenn|"
                     r"not|never|unless|until)\b|n't\b)\W*(\w+\W+){0,4}$", re.IGNORECASE)


INNER_NOT = re.compile(r"\b(nicht|not|kein|keine|never|noch)\b", re.IGNORECASE)


def own_part(body: str) -> str:
    """Nur der Teil der Antwort, den die Firma selbst geschrieben hat (ohne Zitat unserer Anfrage)."""
    text = body or ""
    cut = len(text)
    m = QUOTE_START.search(text)
    if m:
        cut = min(cut, m.start())
    m = OWN_TEXT.search(text)
    if m:
        cut = min(cut, m.start())
    return text[:cut]


def match_rules(text: str) -> dict:
    hits = {}
    for cat, patterns in COMPILED.items():
        for pattern in patterns:
            for m in pattern.finditer(text or ""):
                if cat in ("deleted", "objection", "access") and (
                        NOT_YET.search(text[max(0, m.start() - 60):m.start()]) or INNER_NOT.search(m.group(0))):
                    continue
                hits.setdefault(cat, []).append(m.group(0))
                break
    return hits


def decide(hits: dict, has_attachment: bool = False) -> tuple:
    """Gibt (Kategorie, Sicherheit 0..1, Regeltext) zurück."""
    def first(cat):
        return hits[cat][0] if hits.get(cat) else ""

    if hits.get("id_request"):
        return "id_request", 0.85, first("id_request")
    if hits.get("confirm"):
        return "confirm", 0.8, first("confirm")
    if hits.get("clarify") and not hits.get("deleted"):
        # „Wir haben nichts gefunden. Bitte nennen Sie uns …“ ist eine Rückfrage, keine Erledigung.
        return "clarify", 0.6, first("clarify")
    if hits.get("refused") and not (hits.get("deleted") or hits.get("no_data")):
        return "refused", 0.6, first("refused")
    if hits.get("access") or (has_attachment and not (hits.get("deleted") or hits.get("no_data"))):
        if hits.get("deleted"):
            return "deleted", 0.65, first("deleted")
        return "access", 0.8 if hits.get("access") else 0.5, first("access") or "Anhang mit Auskunft"
    if hits.get("deleted"):
        return "deleted", 0.7, first("deleted")
    if hits.get("no_data"):
        return "no_data", 0.7, first("no_data")
    if hits.get("objection"):
        return "objection", 0.6, first("objection")
    if hits.get("webform"):
        return "webform", 0.5, first("webform")
    return "unknown", 0.2, ""


OUR_SUBJECT = re.compile(r"(datenschutz-(anfrage|begehren)|gdpr\s+request|subject\s+access\s+request|selbstauskunft|"
                         r"auskunftsbegehren|erinnerung|reminder|l[öo]schung\s+meiner\s+daten|erasure\s+of\s+my\s+data|"
                         r"identit[äa]tsnachweis|identifizierung|identity\s+verification|r[üu]ckfrage|your\s+question)", re.IGNORECASE)


def classify_rules(msg: dict) -> dict:
    subject = msg.get("subject") or ""
    if OUR_SUBJECT.search(subject):
        subject = ""            # „AW: Löschung meiner Daten“ ist unser eigener Betreff, keine Aussage der Firma
    text = subject + "\n" + own_part(msg.get("body") or "")
    hits = match_rules(text)
    category, confidence, matched = decide(hits, bool(msg.get("attachments")))
    return {
        "category": category,
        "confidence": confidence,
        "match": matched,
        "rule": ('Formulierung „%s“ gefunden' % matched.strip()) if matched else "Keine bekannte Formulierung gefunden",
    }


# ----------------------------------------------------------------------------- KI

PROMPT = """You sort replies that data brokers send to a GDPR request (access, objection to direct marketing, erasure).
Pick exactly one category:
- no_data: they hold no data about the person
- deleted: they confirm the data was deleted
- objection: they confirm the objection / suppression, nothing else
- access: they provide the requested information or a copy of the data (deletion still pending)
- id_request: they ask for an ID document or identity verification
- clarify: they ask a question or need more details
- webform: they ask the person to use a web form or portal instead
- confirm: they ask the person to click a link to confirm the request or email address
- refused: they refuse the request
- unknown: none of the above
Answer only with JSON like {"category": "...", "note": "<one short sentence in German explaining why>"}.

Reply to classify:
"""


def _parse_ai(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    cat = str(data.get("category", "")).strip()
    if cat not in CATEGORIES:
        return None
    return {"category": cat, "note": str(data.get("note", ""))[:300]}


def _excerpt(msg: dict, limit: int = 6000) -> str:
    text = "Subject: %s\n\n%s" % (msg.get("subject", ""), msg.get("body", ""))
    if msg.get("attachments"):
        text += "\n\nAttachments: " + ", ".join(msg["attachments"])
    return text[:limit]


def _fm_helper():
    """Pfad zum kompilierten Hilfsprogramm, sonst None.

    Terminal-Fassung: liegt neben Python in .venv/bin (legt das Installationsprogramm an).
    Mac-App: liegt in Spurlos.app/Contents/MacOS neben dem Programm.
    """
    if sys.platform == "darwin":
        import platform
        try:
            major = int((platform.mac_ver()[0] or "0").split(".")[0])
        except ValueError:
            major = 0
        if major < 26 or platform.machine() != "arm64":
            return None   # Hilfsprogramm würde auf älteren Macs nur abstürzen (fehlendes Framework)
    for folder in (Path(sys.executable).parent, Path(getattr(sys, "_MEIPASS", "") or sys.executable).parent):
        path = folder / "spurlos-fm"
        if path.exists() and os.access(str(path), os.X_OK):
            return str(path)
    return None


def apple_status() -> tuple:
    helper = _fm_helper()
    if helper:
        try:
            out = subprocess.run([helper, "--check"], capture_output=True, text=True, timeout=20)
        except Exception as exc:  # noqa: BLE001
            return False, "Nicht verfügbar: %s" % exc
        if out.returncode == 0:
            return True, "Verfügbar"
        reason = (out.stderr or "").strip().replace("unavailable: ", "")
        return False, _apple_reason(reason)
    try:
        import apple_fm_sdk as fm  # type: ignore
    except Exception:  # noqa: BLE001
        return False, ("Die Anbindung fehlt. Sie braucht macOS 26 und einen Mac mit Apple-Chip; "
                       "das Installationsprogramm richtet sie dann automatisch ein.")
    try:
        ok, reason = fm.SystemLanguageModel().is_available()
        return bool(ok), ("Verfügbar" if ok else _apple_reason(str(reason)))
    except Exception as exc:  # noqa: BLE001
        return False, "Nicht verfügbar: %s" % exc


def _apple_reason(reason: str) -> str:
    low = reason.lower()
    if "notenabled" in low.replace(" ", "") or "not enabled" in low:
        return "Apple Intelligence ist ausgeschaltet. Einschalten unter Systemeinstellungen › Apple Intelligence & Siri."
    if "noteligible" in low.replace(" ", "") or "not eligible" in low:
        return "Dieser Mac unterstützt Apple Intelligence nicht."
    if "notready" in low.replace(" ", "") or "not ready" in low:
        return "Das Modell wird noch geladen. Bitte später noch einmal versuchen."
    return "Nicht verfügbar: %s" % (reason or "unbekannter Grund")


def _ask_apple(prompt: str) -> str:
    helper = _fm_helper()
    if helper:
        out = subprocess.run([helper], input=prompt, capture_output=True, text=True, timeout=45)
        if out.returncode != 0:
            raise RuntimeError(_apple_reason((out.stderr or "").strip().replace("unavailable: ", "")))
        return out.stdout
    try:
        import apple_fm_sdk as fm  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Apple Intelligence ist auf diesem Mac nicht ansprechbar.") from exc

    async def run():
        model = fm.SystemLanguageModel()
        ok, reason = model.is_available()
        if not ok:
            raise RuntimeError(_apple_reason(str(reason)))
        session = fm.LanguageModelSession()
        return str(await session.respond(prompt))

    return asyncio.run(run())


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 45) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=dict({"Content-Type": "application/json"}, **headers), method="POST")
    local = urllib.parse.urlparse(url).hostname in ("127.0.0.1", "localhost", "::1")
    opener = _LOCAL_OPENER if local else urllib.request.build_opener()
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Ollama läuft auf diesem Mac: nie über den System-Proxy
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ollama_models(base_url: str) -> list:
    req = urllib.request.Request(base_url.rstrip("/") + "/api/tags")
    with _LOCAL_OPENER.open(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [m.get("name") for m in data.get("models", []) if m.get("name")]


def _ask_ollama(prompt: str, cfg: dict) -> str:
    base = (cfg.get("ollama_url") or "http://127.0.0.1:11434").rstrip("/")
    model = cfg.get("ollama_model")
    if not model:
        models = ollama_models(base)
        if not models:
            raise RuntimeError("In Ollama ist noch kein Modell installiert.")
        model = models[0]
    data = _post_json(base + "/api/generate", {"model": model, "prompt": prompt, "stream": False, "format": "json"}, {}, 45)
    return data.get("response", "")


def _ask_cloud(prompt: str, cfg: dict, api_key: str) -> str:
    if not api_key:
        raise RuntimeError("Es ist noch kein API-Schlüssel eingetragen.")
    vendor = cfg.get("cloud_vendor") or "anthropic"
    model = cfg.get("cloud_model")
    if vendor == "openai":
        data = _post_json("https://api.openai.com/v1/chat/completions",
                          {"model": model or "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}],
                           "temperature": 0},
                          {"Authorization": "Bearer " + api_key})
        return data["choices"][0]["message"]["content"]
    data = _post_json("https://api.anthropic.com/v1/messages",
                      {"model": model or "claude-haiku-5-5", "max_tokens": 300,
                       "messages": [{"role": "user", "content": prompt}]},
                      {"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    return "".join(block.get("text", "") for block in data.get("content", []))


def classify_ai(msg: dict, cfg: dict, api_key: str | None = None) -> dict | None:
    provider = cfg.get("provider") or "none"
    if provider == "none":
        return None
    prompt = PROMPT + _excerpt(msg, 3000 if provider == "apple" else 8000)
    if provider == "apple":
        raw = _ask_apple(prompt)
    elif provider == "ollama":
        raw = _ask_ollama(prompt, cfg)
    elif provider == "cloud":
        raw = _ask_cloud(prompt, cfg, api_key or "")
    else:
        return None
    return _parse_ai(raw)


def classify(msg: dict, ai_cfg: dict | None = None, api_key: str | None = None) -> dict:
    result = classify_rules(msg)
    result["ai_category"] = None
    result["ai_note"] = None
    if ai_cfg and (ai_cfg.get("provider") or "none") != "none":
        try:
            ai = classify_ai(msg, ai_cfg, api_key)
        except Exception as exc:  # noqa: BLE001
            ai = None
            result["ai_note"] = "KI nicht erreichbar: %s" % str(exc)[:160]
        if ai:
            result["ai_category"] = ai["category"]
            result["ai_note"] = ai["note"]
            if ai["category"] == result["category"]:
                result["confidence"] = max(result["confidence"], 0.92)
            elif result["category"] == "unknown" or result["confidence"] < 0.6:
                result["category"] = ai["category"]
                result["confidence"] = 0.65
            else:
                result["confidence"] = min(result["confidence"], 0.5)
    return result
