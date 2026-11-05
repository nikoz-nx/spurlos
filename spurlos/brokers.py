"""Firmenliste: Grundbestand, Auswahl nach Ländern und Gruppen, Aktualisierung."""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
import zipfile
from datetime import date
from html.parser import HTMLParser

from . import config, db

GROUPS = {
    "consumer": {"label": "Adresshändler", "sub": "Verkaufen und vermieten Privatadressen für Werbung."},
    "b2b": {"label": "Firmen- und Kontaktdatenbanken", "sub": "Verkaufen Kontaktdaten von Berufstätigen an Vertriebsteams."},
    "adtech": {"label": "Werbe- und Tracking-Daten", "sub": "Verknüpfen E-Mail-Adressen, Cookies und Geräte für Werbung."},
    "people": {"label": "Personensuche und Recruiting", "sub": "Profile von Personen für Suche, Recruiting oder Identitätsprüfung."},
    "credit": {"label": "Auskunfteien", "sub": "Bonitätsdaten. Hier fragt Spurlos nur nach Auskunft, ohne Löschung."},
    "us": {"label": "USA: registrierte Datenhändler", "sub": "Aus dem offiziellen Datenhändler-Register von Kalifornien."},
}
GROUP_ORDER = ["consumer", "b2b", "people", "adtech", "credit", "us"]

COUNTRIES = {
    "de": "Deutschland", "at": "Österreich", "ch": "Schweiz", "gb": "Großbritannien", "us": "USA",
    "fr": "Frankreich", "it": "Italien", "es": "Spanien", "nl": "Niederlande", "be": "Belgien",
    "se": "Schweden", "dk": "Dänemark", "pl": "Polen", "cz": "Tschechien", "pt": "Portugal", "ie": "Irland",
}
EU = {"de", "at", "fr", "it", "es", "nl", "be", "se", "dk", "pl", "cz", "pt", "ie", "fi", "gr", "hr", "hu",
      "lu", "ro", "sk", "si", "bg", "ee", "lv", "lt", "mt", "cy"}

USER_AGENT = "Spurlos/0.1 (+lokales Datenschutz-Werkzeug)"


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower())
    return s.strip("-")[:60] or "firma"


def domain_of(value: str | None) -> str:
    if not value:
        return ""
    v = value.lower().strip()
    if "@" in v:
        v = v.split("@", 1)[1]
    v = re.sub(r"^https?://", "", v).split("/")[0].split(":")[0]
    parts = [p for p in v.split(".") if p]
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ----------------------------------------------------------------------------- Grundbestand

FIELDS = ["name", "category", "origin", "region", "lang", "email", "webform", "webform_only", "address",
          "website", "needs_id", "transport", "source_url", "notes", "grp", "countries", "what", "confirmed"]


def _row(entry: dict) -> dict:
    row = {k: entry.get(k) for k in FIELDS}
    row["webform_only"] = 1 if entry.get("webform_only") else 0
    row["needs_id"] = 1 if entry.get("needs_id") else 0
    row["confirmed"] = 1 if entry.get("confirmed") else 0
    if isinstance(row.get("countries"), (list, tuple)):
        row["countries"] = ",".join(row["countries"])
    row["lang"] = row.get("lang") or "en"
    row["grp"] = row.get("grp") if row.get("grp") in GROUPS else "consumer"
    return row


def upsert(entry: dict, is_new: bool = False) -> str:
    """Fügt eine Firma ein oder aktualisiert sie, außer der Nutzer hat sie selbst bearbeitet."""
    bid = entry["id"]
    existing = db.query_one("SELECT id, user_edited FROM brokers WHERE id = ?", (bid,))
    row = _row(entry)
    if existing is None:
        cols = ["id"] + FIELDS + ["is_new", "active", "added_at"]
        values = [bid] + [row[k] for k in FIELDS] + [1 if is_new else 0, 1, db.now()]
        db.execute("INSERT INTO brokers(%s) VALUES (%s)" % (",".join(cols), ",".join("?" * len(cols))), values)
        return "added"
    if existing["user_edited"]:
        return "kept"
    sets = ", ".join("%s = ?" % k for k in FIELDS)
    db.execute("UPDATE brokers SET %s WHERE id = ?" % sets, [row[k] for k in FIELDS] + [bid])
    return "updated"


def load_seed() -> int:
    path = config.SEED_DIR / "brokers_seed.json"
    if not path.exists():
        return 0
    entries = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        upsert(entry)
    return len(entries)


def authorities() -> dict:
    path = config.SEED_DIR / "authorities.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# ----------------------------------------------------------------------------- Auswahl

def _countries(b: dict) -> set:
    return {c.strip() for c in (b.get("countries") or "").split(",") if c.strip()}


def is_relevant(b: dict, user_countries: set | None = None) -> bool:
    user = set(user_countries if user_countries is not None else db.get("countries") or ["de"])
    bc = _countries(b)
    if not bc or "all" in bc:
        return True
    if "eu" in bc and user & EU:
        return True
    return bool(bc & user)


def selected(b: dict, groups: dict | None = None, user_countries: set | None = None) -> bool:
    groups = groups if groups is not None else db.get("groups") or {}
    grp = b.get("grp") or "consumer"
    if not b.get("active"):
        return False
    if not groups.get(grp, grp != "credit"):
        return False
    return is_relevant(b, user_countries)


# Bundesland am Firmensitz, für die zuständige Datenschutzbehörde (Firmen in Deutschland).
CITY_STATE = {
    "frankfurt am main": "Hessen", "wiesbaden": "Hessen", "mücke": "Hessen", "sulzbach/ts": "Hessen",
    "sulzbach (taunus)": "Hessen", "grävenwiesbach": "Hessen", "idstein": "Hessen", "heppenheim": "Hessen",
    "darmstadt": "Hessen", "kassel": "Hessen", "offenbach am main": "Hessen", "eschborn": "Hessen",
    "münchen": "Bayern", "grünwald": "Bayern", "nürnberg": "Bayern", "augsburg": "Bayern", "unterföhring": "Bayern",
    "stuttgart": "Baden-Württemberg", "leinfelden-echterdingen": "Baden-Württemberg", "bruchsal": "Baden-Württemberg",
    "karlsruhe": "Baden-Württemberg", "baden-baden": "Baden-Württemberg", "pforzheim": "Baden-Württemberg",
    "großbottwar": "Baden-Württemberg", "mannheim": "Baden-Württemberg", "heidelberg": "Baden-Württemberg",
    "freiburg im breisgau": "Baden-Württemberg", "ulm": "Baden-Württemberg",
    "herdecke": "Nordrhein-Westfalen", "gütersloh": "Nordrhein-Westfalen", "troisdorf": "Nordrhein-Westfalen",
    "düsseldorf": "Nordrhein-Westfalen", "frechen": "Nordrhein-Westfalen", "köln": "Nordrhein-Westfalen",
    "bonn": "Nordrhein-Westfalen", "bochum": "Nordrhein-Westfalen", "ratingen": "Nordrhein-Westfalen",
    "neuss": "Nordrhein-Westfalen", "dortmund": "Nordrhein-Westfalen", "essen": "Nordrhein-Westfalen",
    "münster": "Nordrhein-Westfalen", "bielefeld": "Nordrhein-Westfalen", "duisburg": "Nordrhein-Westfalen",
    "hamburg": "Hamburg", "bremen": "Bremen", "berlin": "Berlin", "bellheim": "Rheinland-Pfalz",
    "mainz": "Rheinland-Pfalz", "hannover": "Niedersachsen", "leipzig": "Sachsen", "dresden": "Sachsen",
    "potsdam": "Brandenburg", "kiel": "Schleswig-Holstein", "saarbrücken": "Saarland", "erfurt": "Thüringen",
    "magdeburg": "Sachsen-Anhalt", "rostock": "Mecklenburg-Vorpommern", "schwerin": "Mecklenburg-Vorpommern",
}
_PLZ_CITY = re.compile(r"\b(\d{5})\s+([^\n|,]+)")


EDOEB = {
    "name": "Eidgenössischer Datenschutz- und Öffentlichkeitsbeauftragter (EDÖB)",
    "address": "Feldeggweg 1\n3003 Bern\nSchweiz", "email": None,
    "webform": "https://www.edoeb.admin.ch/en/report-form-data-subjects",
    "web": "https://www.edoeb.admin.ch", "phone": "+41 58 462 43 95", "form_preferred": True,
}


def is_swiss(b: dict) -> bool:
    a = (b.get("address") or "").lower()
    return b.get("lang") == "ch" or "schweiz" in a or "switzerland" in a or "suisse" in a


def is_german(b: dict) -> bool:
    a = (b.get("address") or "").lower()
    return "deutschland" in a or "germany" in a


def company_state(b: dict):
    """Bundesland am Firmensitz, wenn es sich aus der Adresse sicher ablesen lässt, sonst None."""
    if not is_german(b):
        return None
    for m in _PLZ_CITY.finditer(b.get("address") or ""):
        city = m.group(2).strip().lower()
        if city in CITY_STATE:
            return CITY_STATE[city]
    return None


def contact_kind(b: dict) -> str:
    if b.get("email") and not b.get("webform_only"):
        return "email"
    if b.get("webform"):
        return "webform"
    if b.get("address") and (b.get("transport") == "letter"):
        return "letter"
    return "none"


# ----------------------------------------------------------------------------- Aktualisierung

DA_ZIP = "https://codeload.github.com/datenanfragen/data/zip/refs/heads/master"
INCOGNI_URL = "https://blog.incogni.com/data-brokers-incogni-covers/"
CA_CSV = "https://cppa.ca.gov/data_broker_registry/registry{year}.csv"


def _excluded() -> dict:
    path = config.SEED_DIR / "excluded.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"ids": [], "incogni_alias": {}}


def update_datenanfragen() -> dict:
    """Lädt die offene Firmendatenbank von datenanfragen.de (CC0).

    Neue Firmen kommen dazu. Bei bekannten Firmen werden nur fehlende Kontakte ergänzt: Die mitgelieferte
    Liste ist geprüft und hat Vorrang, ebenso alles, was der Nutzer selbst geändert hat.
    """
    raw = _get(DA_ZIP, timeout=90)
    stats = {"updated": 0, "added": 0}
    known = {r["id"] for r in db.query("SELECT id FROM brokers")}
    skip = set(_excluded().get("ids") or [])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            if "/companies/" not in name or not name.endswith(".json"):
                continue
            try:
                c = json.loads(zf.read(name).decode("utf-8"))
            except Exception:  # noqa: BLE001
                continue
            cats = c.get("categories") or []
            if not ("addresses" in cats or "credit agency" in cats):
                continue
            bid = "da-" + c.get("slug", "")
            if bid in skip:
                continue
            current = db.query_one("SELECT * FROM brokers WHERE id = ?", (bid,))
            entry = {
                "id": bid, "name": c.get("name"), "origin": "datenanfragen",
                "email": c.get("email"), "webform": c.get("webform"), "address": c.get("address"),
                "website": c.get("web"), "needs_id": c.get("needs-id-document"),
                "transport": c.get("suggested-transport-medium") or ("email" if c.get("email") else "letter"),
                "source_url": "https://www.datenanfragen.de/company/" + c.get("slug", ""),
                "countries": c.get("relevant-countries") or ["all"],
                "lang": ("ch" if set(c.get("relevant-countries") or []) == {"ch"} else
                         "de" if set(c.get("relevant-countries") or []) & {"de", "at", "ch"} else "en"),
            }
            if current:
                # Nur Lücken füllen: fehlt bei uns eine Kontaktadresse, übernehmen wir die von datenanfragen.de.
                if current.get("user_edited") or current.get("email") or current.get("webform"):
                    continue
                if not (entry["email"] or entry["webform"]) or current.get("transport") == "letter" and current.get("notes"):
                    continue
                for k in ("name", "grp", "category", "what", "region", "notes", "confirmed", "webform_only", "lang",
                          "countries", "address", "website", "source_url"):
                    entry[k] = current.get(k)
                if upsert(entry) == "updated":
                    stats["updated"] += 1
            else:
                entry.update({
                    "grp": "credit" if "credit agency" in cats else "consumer",
                    "category": "Auskunftei" if "credit agency" in cats else "Adress- und Datenhändler",
                    "region": "", "what": "", "confirmed": False,
                })
                upsert(entry, is_new=bid not in known)
                stats["added"] += 1
    return stats


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.in_cell, self.cell = True, []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None and self.in_cell:
            self.row.append(" ".join("".join(self.cell).split()))
            self.in_cell = False
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def parse_incogni(html: str) -> list:
    parser = _TableParser()
    parser.feed(html)
    result = []
    for row in parser.rows:
        if len(row) < 5 or row[0].lower() == "name":
            continue
        name, website, _sens, category, coverage = row[:5]
        result.append({"name": name, "website": website, "category": category, "coverage": coverage})
    return result


def update_incogni() -> dict:
    html = _get(INCOGNI_URL).decode("utf-8", "replace")
    entries = [e for e in parse_incogni(html) if "EU" in e["coverage"].upper()]
    known_names = {slugify(r["name"]) for r in db.query("SELECT name FROM brokers")}
    known_domains = {domain_of(r["website"]) for r in db.query("SELECT website FROM brokers") if r["website"]}
    added = []
    ex = _excluded()
    skip = set(ex.get("ids") or [])
    alias = ex.get("incogni_alias") or {}
    for e in entries:
        if slugify(e["name"]) in known_names or (e["website"] and domain_of(e["website"]) in known_domains):
            continue
        if slugify(e["name"]) in alias:
            continue
        bid = "inc-" + slugify(e["name"])
        if bid in skip:
            continue
        if db.query_one("SELECT id FROM brokers WHERE id = ?", (bid,)):
            continue
        upsert({"id": bid, "name": e["name"], "category": e["category"], "origin": "incogni", "region": "EU",
                "lang": "en", "website": e["website"], "grp": "adtech" if "market" in e["category"].lower() else "people",
                "countries": ["eu"], "what": "", "transport": "email", "source_url": INCOGNI_URL}, is_new=True)
        added.append(e["name"])
    return {"checked": len(entries), "added": added}


def parse_ca_registry(text: str) -> list:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]

    def col(*needles, avoid=()):
        for i, h in enumerate(header):
            if all(n in h for n in needles) and not any(a in h for a in avoid):
                return i
        return None

    i_name = col("data broker name")
    i_email = col("email")
    i_web = col("primary website", avoid=("ccpa", "rights", "how"))
    i_rights = col("ccpa")
    out = []
    for r in rows[1:]:
        def get(i):
            return r[i].strip() if i is not None and i < len(r) else ""
        name = get(i_name)
        if not name:
            continue
        email = get(i_email)
        if email and "@" not in email:
            email = ""
        out.append({"name": name, "email": email, "website": get(i_web), "rights": get(i_rights)})
    return out


def update_ca_registry() -> dict:
    text = None
    for year in (date.today().year, date.today().year - 1):
        try:
            text = _get(CA_CSV.format(year=year), timeout=60).decode("utf-8", "replace")
            if text.count("\n") > 10:
                break
        except Exception:  # noqa: BLE001
            text = None
    if not text:
        raise RuntimeError("Das kalifornische Register ist gerade nicht erreichbar.")
    entries = parse_ca_registry(text)
    known_domains = {domain_of(r["email"]) for r in db.query("SELECT email FROM brokers WHERE email IS NOT NULL")}
    added = updated = 0
    for e in entries:
        bid = "ca-" + slugify(e["name"])
        exists = db.query_one("SELECT id FROM brokers WHERE id = ?", (bid,))
        if not exists and e["email"] and domain_of(e["email"]) in known_domains:
            continue  # schon über eine andere Quelle in der Liste
        res = upsert({"id": bid, "name": e["name"], "category": "Registrierter Datenhändler (USA)", "origin": "kalifornien",
                      "region": "US", "lang": "en", "email": e["email"] or None, "webform": e["rights"] or None,
                      "website": e["website"], "grp": "us", "countries": ["us"], "transport": "email",
                      "what": "", "confirmed": bool(e["email"]),
                      "source_url": "https://cppa.ca.gov/data_broker_registry/"}, is_new=not exists)
        if res == "added":
            added += 1
        elif res == "updated":
            updated += 1
    return {"entries": len(entries), "added": added, "updated": updated}


def update_all() -> dict:
    info = {"at": db.now(), "errors": []}
    for name, fn in (("datenanfragen", update_datenanfragen), ("incogni", update_incogni)):
        try:
            info[name] = fn()
        except Exception as exc:  # noqa: BLE001
            info["errors"].append("%s: %s" % (name, str(exc)[:160]))
    if "us" in (db.get("countries") or []):
        try:
            info["kalifornien"] = update_ca_registry()
        except Exception as exc:  # noqa: BLE001
            info["errors"].append("kalifornien: %s" % str(exc)[:160])
    db.put("last_broker_update", info["at"])
    db.put("broker_update_info", info)
    return info
