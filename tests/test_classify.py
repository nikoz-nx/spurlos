import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spurlos import classify  # noqa: E402

CASES = [
    ("UpLead", "Re: GDPR request [DA-015]", "Hello, we searched our systems for the email addresses you listed. We do not hold any personal data about you. No further action is needed.", [], "no_data"),
    ("Lighthouse", "Re: request [DA-016]", "Dear Sir or Madam, as requested we have deleted all records linked to your email addresses and added them to our suppression list.", [], "deleted"),
    ("M1", "Re: [DA-017]", "Thank you for your request. Before we can proceed, could you please clarify which of the listed addresses you would like us to check?", [], "clarify"),
    ("Apollo", "Your request", "To process your request we need to verify your identity. Please send a copy of your government-issued ID.", [], "id_request"),
    ("DPD", "AW: Datenschutz-Anfrage [DA-001]", "Sehr geehrter Herr Mustermann, auf Ihre Anfrage erteilen wir Ihnen Auskunft über die zu Ihrer Person gespeicherten Daten. Ihren Widerspruch gegen die Nutzung für Werbung haben wir vermerkt.", ["auskunft.pdf"], "access"),
    ("AZ", "AW: Ihre Anfrage", "Zu Ihrer Person sind bei uns keine personenbezogenen Daten gespeichert.", [], "no_data"),
    ("Schober", "AW: Anfrage", "Ihren Widerspruch haben wir in unsere Werbesperrdatei aufgenommen.", [], "objection"),
    ("X", "AW", "Ihre Daten wurden vollständig gelöscht.", [], "deleted"),
    ("Y", "Re", "Please submit your request via our privacy portal at https://example.com/privacy.", [], "webform"),
    ("Z", "Re", "We are unable to comply with your request.", [], "refused"),
    # Aus der Prüfung: Zitate, eigener Betreff, Verneinung, Zukunft
    ("Zitat", "AW: Datenschutz-Anfrage: Auskunft, Widerspruch und Löschung [DA-003]",
     "Vielen Dank, wir prüfen Ihr Anliegen und melden uns.\n\nAm 04.11.2026 um 12:00 schrieb Max Mustermann:\n"
     "> 3. Löschung\n> Bitte löschen Sie ... damit mein Widerspruch dauerhaft beachtet wird (Sperrvermerk).", [], "unknown"),
    ("Eigener Betreff", "AW: Löschung meiner Daten [DA-002]", "Hiermit bestätigen wir den Eingang Ihrer Nachricht.", [], "unknown"),
    ("Zukunft", "Re: GDPR request [DA-020]", "Once your data has been deleted we will inform you.", [], "unknown"),
    ("Verneinung", "AW", "Wir haben Ihre Daten nicht gelöscht, da wir zur Aufbewahrung verpflichtet sind.", [], "unknown"),
    ("Nichts gefunden, Rückfrage", "Re", "We did not find any records. Could you please provide your postal address?", [], "clarify"),
    ("Bestätigungslink", "Confirm your request", "Please click the link below to confirm your request: https://example.com/c/123", [], "confirm"),
    ("Note", "Re", "Please note: we have deleted all data associated with your email.", [], "deleted"),
]

ok = True
for name, subject, body, att, expected in CASES:
    msg = {"subject": subject, "body": body, "attachments": att}
    r = classify.classify_rules(msg)
    status = "OK " if r["category"] == expected else "FAIL"
    if r["category"] != expected:
        ok = False
    print(status, name, "->", r["category"], r["confidence"], "|", r["rule"])

auto = {"subject": "Automatische Antwort: Ihre Anfrage", "body": "Wir haben Ihre Anfrage erhalten und melden uns.",
        "headers": {"auto-submitted": "auto-replied"}}
print("auto header:", classify.is_auto_reply(auto))
auto2 = {"subject": "We have received your request [#12345]", "body": "This is an automated response.", "headers": {}}
print("auto subject:", classify.is_auto_reply(auto2))
real = {"subject": "Re: request received", "body": "We do not hold any personal data about you.", "headers": {}}
print("real reply not auto:", not classify.is_auto_reply(real))
bounce = {"from_addr": "mailer-daemon@example.com", "subject": "Undelivered Mail Returned to Sender"}
print("bounce:", classify.is_bounce(bounce))
receipt = {"from_addr": "privacy@example.com", "subject": "Gelesen: Datenschutz-Anfrage", "is_report": True,
           "report_type": "disposition-notification"}
delay = {"from_addr": "mailer-daemon@example.com", "subject": "Delivery Status Notification (Delay)", "is_report": True,
         "report_type": "delivery-status", "dsn_actions": ["delayed"]}
hard = {"from_addr": "mailer-daemon@example.com", "subject": "Undelivered Mail Returned to Sender",
        "body": "550 5.1.1 <x@example.com>: Recipient address rejected: User unknown"}
bounce_ok = (not classify.is_bounce(receipt)) and (not classify.is_bounce(delay)) and classify.is_bounce(hard)
print("bounce rules:", bounce_ok)
ok = ok and bounce_ok
print("ALL OK" if ok else "SOME FAILED")
