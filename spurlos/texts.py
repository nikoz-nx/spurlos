"""Texte für Anfragen, Erinnerungen, Folgeschreiben und Beschwerden.

Grundlage: die Musterschreiben von datenanfragen.de (CC0), die Musterbriefe
der Verbraucherzentralen und des LfDI Baden-Württemberg. Die Texte verweisen
bewusst auf die Artikel der DSGVO, damit die Firmen wissen, woran sie sind.
"""
from __future__ import annotations

from datetime import datetime


def fmt_date(value: str | None, lang: str = "de") -> str:
    if not value:
        return ""
    try:
        d = datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return str(value)
    if lang == "en":
        return d.strftime("%d %B %Y").lstrip("0")
    months = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
              "Oktober", "November", "Dezember"]
    return "%d. %s %d" % (d.day, months[d.month - 1], d.year)


def full_name(profile: dict) -> str:
    return (" ".join(x for x in (profile.get("first_name"), profile.get("last_name")) if x)).strip()


def addr_text(a: dict) -> str:
    """Adresse als eine Zeile: „Straße Nr, PLZ Ort“ (ältere Einträge haben nur „text“)."""
    if a.get("street") or a.get("city") or a.get("zip"):
        place = " ".join(x for x in ((a.get("zip") or "").strip(), (a.get("city") or "").strip()) if x)
        parts = [x for x in ((a.get("street") or "").strip(), place, (a.get("country") or "").strip()) if x]
        return ", ".join(parts)
    return (a.get("text") or "").strip()


def email_variants(addresses: list) -> list:
    """Gmail und Googlemail sind dasselbe Postfach – Firmen kennen aber nur die Schreibweise, die man angegeben hat."""
    out = []
    for a in addresses:
        a = a.strip()
        if not a or "@" not in a:
            continue
        local, domain = a.rsplit("@", 1)
        variants = [a]
        if domain.lower() == "gmail.com":
            variants.append(local + "@googlemail.com")
        elif domain.lower() == "googlemail.com":
            variants.append(local + "@gmail.com")
        for v in variants:
            if v.lower() not in [o.lower() for o in out]:
                out.append(v)
    return out


PREFIXES = {"49": "0", "41": "0", "43": "0"}


def phone_variants(number: str) -> str:
    """„+49 174 …“ und „0174 …“ – Firmen speichern Nummern in beiden Formen."""
    raw = (number or "").strip()
    digits = "".join(ch for ch in raw.replace("(0)", "") if ch.isdigit() or ch == "+")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("+"):
        for cc, trunk in PREFIXES.items():
            if digits.startswith("+" + cc) and len(digits) > len(cc) + 4:
                return "%s / %s%s" % (raw, trunk, digits[len(cc) + 1:])
        return raw
    if digits.startswith("0") and len(digits) > 5:
        return "%s / +49%s" % (raw, digits[1:])
    return raw


def company_text(c: dict) -> str:
    """Nur der Firmenname – einen Jobtitel brauchen die Firmen nicht."""
    return (c.get("name") or c.get("text") or "").strip()


def website_list(profile: dict) -> list:
    """Eigene Webseiten; ältere Profile hatten die Website noch in der Firmenzeile."""
    out = []
    items = [w.get("url", "") for w in profile.get("websites") or []]
    items += [c.get("website", "") for c in profile.get("companies") or []]
    for w in items:
        w = (w or "").strip()
        if w and w.lower() not in [o.lower() for o in out]:
            out.append(w)
    return out


def id_block(profile: dict, lang: str = "de") -> str:
    de = lang != "en"
    lines = []
    name = full_name(profile)
    if name:
        lines.append(("Name: " if de else "Name: ") + name)
    former = [n for n in profile.get("former_names") or [] if n]
    if former:
        lines.append(("Frühere Namen: " if de else "Former names: ") + ", ".join(former))
    addresses = [a for a in profile.get("addresses") or [] if addr_text(a)]
    current = [addr_text(a) for a in addresses if a.get("current")]
    old = [addr_text(a) for a in addresses if not a.get("current")]
    if current:
        lines.append(("Anschrift: " if de else "Postal address: ") + "; ".join(current))
    if old:
        lines.append(("Frühere Anschriften: " if de else "Previous addresses: ") + "; ".join(old))
    emails = email_variants([e.get("address", "") for e in profile.get("emails") or []])
    if emails:
        lines.append(("E-Mail-Adressen: " if de else "Email addresses: ") + ", ".join(emails))
    phones = [phone_variants(p["number"]) for p in profile.get("phones") or [] if p.get("number")]
    if phones:
        lines.append(("Telefonnummern: " if de else "Phone numbers: ") + ", ".join(phones))
    companies = [company_text(c) for c in profile.get("companies") or [] if company_text(c)]
    if companies:
        lines.append(("Eigene Firmen: " if de else "Own businesses: ") + ", ".join(companies))
    sites = website_list(profile)
    if sites:
        lines.append(("Eigene Webseiten: " if de else "Own websites: ") + ", ".join(sites))
    return "\n".join(lines)


# ----------------------------------------------------------------------------- Erstanfrage

REQUEST_DE = """Guten Tag,

ich wende mich mit drei Anliegen nach der Datenschutz-Grundverordnung (DSGVO) an Sie.

1. Auskunft (Art. 15 DSGVO)
Bitte bestätigen Sie mir, ob Sie personenbezogene Daten zu meiner Person verarbeiten. Falls ja, stellen Sie mir bitte eine Kopie dieser Daten zur Verfügung und teilen Sie mir mit:
– die Verarbeitungszwecke,
– die Kategorien der verarbeiteten Daten,
– die Empfänger oder Kategorien von Empfängern, denen Sie die Daten offengelegt haben oder noch offenlegen werden,
– die geplante Speicherdauer oder die Kriterien dafür,
– alle verfügbaren Informationen über die Herkunft der Daten, soweit Sie diese nicht bei mir erhoben haben.

2. Widerspruch gegen Direktwerbung (Art. 21 Abs. 2 DSGVO)
Ich widerspreche der Verarbeitung meiner personenbezogenen Daten für Zwecke der Direktwerbung. Das gilt auch für Profiling, soweit es mit Direktwerbung in Verbindung steht, und für die Weitergabe, Vermietung oder den Verkauf meiner Daten an Dritte zu Werbezwecken. Eine etwa erteilte Einwilligung widerrufe ich hiermit.

3. Löschung (Art. 17 DSGVO)
Bitte löschen Sie nach Erteilung der Auskunft alle zu meiner Person gespeicherten Daten. Soweit Sie Daten aufbewahren müssen, damit mein Widerspruch dauerhaft beachtet wird (Sperrvermerk), beschränken Sie die Verarbeitung bitte auf diesen Zweck. Falls Sie meine Daten an Empfänger weitergegeben haben, teilen Sie diesen die Löschung bitte mit (Art. 19 DSGVO).

Meine Anfrage umfasst ausdrücklich auch alle weiteren Angebote und Unternehmen, für die Sie Verantwortlicher im Sinne des Art. 4 Nr. 7 DSGVO sind.

Damit Sie mich zuordnen können, nenne ich Ihnen folgende Angaben. Bitte verwenden Sie diese ausschließlich zur Bearbeitung dieser Anfrage.
{id_block}

Bitte beantworten Sie meine Anfrage unverzüglich, spätestens aber innerhalb eines Monats nach Eingang (Art. 12 Abs. 3 DSGVO). Die Auskunft ist kostenlos (Art. 15 Abs. 3 DSGVO). Bitte geben Sie in Ihrer Antwort das Aktenzeichen {ref} an.

Sollten Sie meine Anfrage nicht fristgerecht beantworten, werde ich Beschwerde bei der zuständigen Datenschutzaufsichtsbehörde einreichen.

Vielen Dank im Voraus.

Mit freundlichen Grüßen
{name}"""

REQUEST_EN = """Dear Sir or Madam,

I am contacting you with three requests under the EU General Data Protection Regulation (GDPR). I live in the European Union, so the GDPR applies to your processing of my personal data (Article 3 GDPR).

1. Access (Article 15 GDPR)
Please confirm whether you process personal data concerning me. If so, please provide me with a copy of this data and tell me:
– the purposes of the processing,
– the categories of personal data concerned,
– the recipients or categories of recipients to whom the data has been or will be disclosed,
– the period for which the data will be stored, or the criteria used to determine it,
– all available information about the source of the data, where it was not collected from me.

2. Objection to direct marketing (Article 21(2) GDPR)
I object to the processing of my personal data for direct marketing purposes. This includes profiling related to direct marketing and any sale, rental or disclosure of my data to third parties for marketing purposes. I withdraw any consent I may have given.

3. Erasure (Article 17 GDPR)
After providing the information above, please erase all personal data concerning me. Where you need to keep minimal data so that my objection is respected permanently (suppression list), please restrict its processing to that purpose. If you have disclosed my data to recipients, please inform them of the erasure (Article 19 GDPR).
{us_note}
My request explicitly includes all other services and companies for which you are the controller as defined in Article 4(7) GDPR.

To identify me, please use the following information. Please use it only to process this request.
{id_block}

Please respond without undue delay and in any event within one month of receipt (Article 12(3) GDPR). Providing this information is free of charge (Article 15(3) GDPR). Please quote the reference {ref} in your reply.

If I do not receive a reply within this period, I will lodge a complaint with the competent data protection supervisory authority.

Thank you in advance.

Yours faithfully,
{name}"""

US_NOTE = """
If you are also subject to the California Consumer Privacy Act or similar US state privacy laws, please treat this message as a request to know, a request to delete and a request to opt out of the sale and sharing of my personal information as well.
"""

ACCESS_DE = """Guten Tag,

ich bitte hiermit um Auskunft nach Art. 15 DSGVO. Bitte bestätigen Sie mir, ob Sie personenbezogene Daten zu meiner Person verarbeiten.

Falls ja, stellen Sie mir bitte eine Kopie aller zu meiner Person gespeicherten Daten zur Verfügung, einschließlich gespeicherter Wahrscheinlichkeits- oder Scorewerte, und teilen Sie mir mit:
– die Verarbeitungszwecke,
– die Kategorien der verarbeiteten Daten,
– die Empfänger oder Kategorien von Empfängern, denen Sie die Daten offengelegt haben oder noch offenlegen werden, insbesondere in den letzten zwölf Monaten,
– die geplante Speicherdauer oder die Kriterien dafür,
– alle verfügbaren Informationen über die Herkunft der Daten,
– falls zutreffend, das Bestehen einer automatisierten Entscheidungsfindung einschließlich Profiling und aussagekräftige Informationen über die dabei verwendete Logik.

Damit Sie mich zuordnen können, nenne ich Ihnen folgende Angaben. Bitte verwenden Sie diese ausschließlich zur Bearbeitung dieser Anfrage.
{id_block}

Die Auskunft ist unverzüglich, spätestens innerhalb eines Monats nach Eingang zu erteilen (Art. 12 Abs. 3 DSGVO) und kostenlos (Art. 15 Abs. 3 DSGVO). Bitte geben Sie in Ihrer Antwort das Aktenzeichen {ref} an.

Sollten Sie meine Anfrage nicht fristgerecht beantworten, werde ich Beschwerde bei der zuständigen Datenschutzaufsichtsbehörde einreichen.

Mit freundlichen Grüßen
{name}"""

ACCESS_EN = """Dear Sir or Madam,

I am requesting access to my personal data under Article 15 of the EU General Data Protection Regulation (GDPR). Please confirm whether you process personal data concerning me.

If so, please provide me with a copy of all personal data concerning me, including any scores or probability values, and tell me:
– the purposes of the processing,
– the categories of personal data concerned,
– the recipients or categories of recipients to whom the data has been or will be disclosed,
– the period for which the data will be stored, or the criteria used to determine it,
– all available information about the source of the data,
– where applicable, the existence of automated decision-making including profiling, and meaningful information about the logic involved.

To identify me, please use the following information. Please use it only to process this request.
{id_block}

Please respond without undue delay and in any event within one month of receipt (Article 12(3) GDPR). Access is free of charge (Article 15(3) GDPR). Please quote the reference {ref} in your reply.

If I do not receive a reply within this period, I will lodge a complaint with the competent data protection supervisory authority.

Yours faithfully,
{name}"""

# ----------------------------------------------------------------------------- Folgeschreiben

REMINDER_DE = """Guten Tag,

am {sent_date} habe ich Ihnen eine Anfrage nach der DSGVO geschickt (Aktenzeichen {ref}). Leider habe ich bisher keine Antwort von Ihnen erhalten. Die Frist von einem Monat nach Art. 12 Abs. 3 DSGVO ist damit abgelaufen.

Bitte beantworten Sie meine Anfrage innerhalb von zwei Wochen nach Erhalt dieser Erinnerung. Andernfalls werde ich Beschwerde bei der zuständigen Datenschutzaufsichtsbehörde einreichen.

Meine ursprüngliche Anfrage finden Sie unten.

Mit freundlichen Grüßen
{name}

----- Ursprüngliche Anfrage vom {sent_date} -----
{original}"""

REMINDER_EN = """Dear Sir or Madam,

On {sent_date} I sent you a request under the GDPR (reference {ref}). I have not received a reply so far. The one-month deadline under Article 12(3) GDPR has therefore expired.

Please answer my request within two weeks of receiving this reminder. Otherwise I will lodge a complaint with the competent data protection supervisory authority.

You will find my original request below.

Yours faithfully,
{name}

----- Original request of {sent_date} -----
{original}"""

ERASURE_DE = """Guten Tag,

vielen Dank für Ihre Auskunft zu meiner Anfrage vom {sent_date} (Aktenzeichen {ref}).

Wie in meiner Anfrage angekündigt, bitte ich Sie jetzt, alle zu meiner Person gespeicherten Daten zu löschen (Art. 17 DSGVO). Behalten Sie nur den Sperrvermerk, der nötig ist, damit mein Widerspruch gegen Werbung weiter beachtet wird.

Falls Sie meine Daten an andere weitergegeben haben, informieren Sie diese bitte ebenfalls über die Löschung (Art. 19 DSGVO).

Bitte bestätigen Sie mir die Löschung bis zum {due_date} und geben Sie dabei das Aktenzeichen {ref} an.

Mit freundlichen Grüßen
{name}"""

ERASURE_EN = """Dear Sir or Madam,

Thank you for your reply to my request of {sent_date} (reference {ref}).

As announced in my request, I now ask you to erase all personal data concerning me (Article 17 GDPR). Please keep only the minimal suppression entry needed to keep respecting my objection to direct marketing.

If you have disclosed my data to other recipients, please inform them of the erasure as well (Article 19 GDPR).

Please confirm the erasure by {due_date} and quote the reference {ref}.

Yours faithfully,
{name}"""

ID_REPLY_DE = """Guten Tag,

vielen Dank für Ihre Nachricht zu meiner Anfrage vom {sent_date} (Aktenzeichen {ref}). Sie bitten mich um eine Kopie meines Ausweises.

Nach Art. 12 Abs. 6 DSGVO dürfen Sie zusätzliche Informationen zur Bestätigung meiner Identität nur anfordern, wenn begründete Zweifel an meiner Identität bestehen. Solche Zweifel haben Sie nicht dargelegt. Die Angaben in meiner Anfrage (Name, Anschriften, E-Mail-Adressen, Telefonnummern) reichen aus, um mich in Ihrem Datenbestand zuzuordnen. Gern bestätige ich Ihnen eine der genannten E-Mail-Adressen, indem ich Ihnen von dort schreibe.

Bitte bearbeiten Sie meine Anfrage deshalb ohne Ausweiskopie. Falls Sie konkrete Zweifel haben, erläutern Sie mir diese bitte.

Mit freundlichen Grüßen
{name}"""

ID_REPLY_EN = """Dear Sir or Madam,

Thank you for your message regarding my request of {sent_date} (reference {ref}). You asked me for a copy of an identity document.

Under Article 12(6) GDPR you may only request additional information to confirm my identity where you have reasonable doubts about it. You have not explained any such doubts. The details in my request (name, postal addresses, email addresses, phone numbers) are sufficient to identify me in your records. I am happy to confirm one of the listed email addresses by writing to you from it.

Please therefore process my request without a copy of an identity document. If you have specific doubts, please explain them to me.

Yours faithfully,
{name}"""

CLARIFY_DE = """Guten Tag,

vielen Dank für Ihre Rückfrage zu meiner Anfrage vom {sent_date} (Aktenzeichen {ref}).

Bitte prüfen Sie alle Angaben aus meiner Anfrage, also sämtliche genannten Namen, Anschriften, E-Mail-Adressen und Telefonnummern. Hier noch einmal zusammengefasst:
{id_block}

Meine Anfrage umfasst Auskunft (Art. 15 DSGVO), Widerspruch gegen Direktwerbung (Art. 21 Abs. 2 DSGVO) und Löschung (Art. 17 DSGVO).

Mit freundlichen Grüßen
{name}"""

CLARIFY_EN = """Dear Sir or Madam,

Thank you for your question regarding my request of {sent_date} (reference {ref}).

Please check all details from my request, that is every name, postal address, email address and phone number listed. Here they are again:
{id_block}

My request covers access (Article 15 GDPR), objection to direct marketing (Article 21(2) GDPR) and erasure (Article 17 GDPR).

Yours faithfully,
{name}"""

COMPLAINT_DE = """Guten Tag,

hiermit reiche ich Beschwerde nach Art. 77 DSGVO ein.

Am {sent_date} habe ich mich mit einer Anfrage nach Art. 15, 17 und 21 DSGVO an folgenden Verantwortlichen gewandt:
{broker_name}
{broker_contact}

{history}

Daher wende ich mich nun an Sie. Ich bitte Sie, den Vorgang zu prüfen und den Verantwortlichen zur Erfüllung meiner Anfrage zu bewegen. Kopien meiner Anfrage und der Erinnerung füge ich bei.

Sie erreichen mich unter {contact}.

Mit freundlichen Grüßen
{name}
{address}"""


# ----------------------------------------------------------------------------- Schweiz (DSG)
# Für Firmen mit Sitz in der Schweiz. Grundlage: revidiertes Datenschutzgesetz (DSG, SR 235.1)
# und Datenschutzverordnung (DSV, SR 235.11), in Kraft seit 1. September 2023.

REQUEST_CH = """Guten Tag

ich wende mich mit drei Anliegen nach dem Datenschutzgesetz (DSG) an Sie.

1. Auskunft (Art. 25 DSG)
Bitte teilen Sie mir mit, ob Sie Personendaten über mich bearbeiten. Falls ja, teilen Sie mir bitte mit:
– die bearbeiteten Personendaten als solche,
– den Bearbeitungszweck,
– die Aufbewahrungsdauer oder die Kriterien dafür,
– die verfügbaren Angaben über die Herkunft der Daten, soweit Sie sie nicht bei mir beschafft haben,
– die Empfängerinnen und Empfänger oder die Kategorien von Empfängern, denen Sie Personendaten bekanntgegeben haben,
– gegebenenfalls das Vorliegen einer automatisierten Einzelentscheidung und die Logik, auf der sie beruht.

2. Widerspruch gegen Werbung
Ich widerspreche ausdrücklich jeder Bearbeitung meiner Personendaten für Werbung und Marketing sowie jeder Bekanntgabe, Vermietung oder jedem Verkauf meiner Daten an Dritte (Art. 30 Abs. 2 Bst. b DSG). Eine allenfalls erteilte Einwilligung widerrufe ich.

3. Löschung
Bitte löschen Sie nach Erteilung der Auskunft alle Personendaten über mich (Art. 6 Abs. 4 und Art. 32 Abs. 2 Bst. c DSG). Bewahren Sie nur auf, was nötig ist, damit mein Widerspruch dauerhaft beachtet wird (Sperrvermerk).

Soweit die Datenschutz-Grundverordnung (DSGVO) auf Ihre Bearbeitung anwendbar ist, stütze ich mich zusätzlich auf Art. 15, 17 und 21 DSGVO.

Damit Sie mich zuordnen können, nenne ich Ihnen folgende Angaben. Bitte verwenden Sie diese ausschliesslich zur Bearbeitung dieser Anfrage.
{id_block}

Bitte beantworten Sie meine Anfrage innert 30 Tagen (Art. 18 DSV). Die Auskunft ist kostenlos (Art. 25 Abs. 6 DSG). Bitte geben Sie in Ihrer Antwort das Aktenzeichen {ref} an.

Sollten Sie nicht fristgerecht antworten, werde ich die Angelegenheit dem Eidgenössischen Datenschutz- und Öffentlichkeitsbeauftragten (EDÖB) melden und behalte mir weitere Schritte vor.

Freundliche Grüsse
{name}"""

ACCESS_CH = """Guten Tag

ich bitte Sie um Auskunft nach Art. 25 DSG. Bitte teilen Sie mir mit, ob Sie Personendaten über mich bearbeiten.

Falls ja, teilen Sie mir bitte mit:
– die bearbeiteten Personendaten als solche, einschliesslich allfälliger Bonitäts- oder Scorewerte,
– den Bearbeitungszweck,
– die Aufbewahrungsdauer oder die Kriterien dafür,
– die verfügbaren Angaben über die Herkunft der Daten,
– die Empfängerinnen und Empfänger oder die Kategorien von Empfängern, denen Sie Personendaten bekanntgegeben haben,
– gegebenenfalls das Vorliegen einer automatisierten Einzelentscheidung und die Logik, auf der sie beruht.

Damit Sie mich zuordnen können, nenne ich Ihnen folgende Angaben. Bitte verwenden Sie diese ausschliesslich zur Bearbeitung dieser Anfrage.
{id_block}

Die Auskunft ist innert 30 Tagen zu erteilen (Art. 18 DSV) und kostenlos (Art. 25 Abs. 6 DSG). Bitte geben Sie in Ihrer Antwort das Aktenzeichen {ref} an.

Freundliche Grüsse
{name}"""

REMINDER_CH = """Guten Tag

am {sent_date} habe ich Ihnen eine Anfrage nach dem Datenschutzgesetz geschickt (Aktenzeichen {ref}). Leider habe ich bisher keine Antwort erhalten. Die Frist von 30 Tagen nach Art. 18 DSV ist damit abgelaufen.

Bitte beantworten Sie meine Anfrage innert 14 Tagen nach Erhalt dieser Erinnerung. Andernfalls werde ich die Angelegenheit dem Eidgenössischen Datenschutz- und Öffentlichkeitsbeauftragten (EDÖB) melden und behalte mir rechtliche Schritte vor.

Meine ursprüngliche Anfrage finden Sie unten.

Freundliche Grüsse
{name}

----- Ursprüngliche Anfrage vom {sent_date} -----
{original}"""

ERASURE_CH = """Guten Tag

vielen Dank für Ihre Auskunft zu meiner Anfrage vom {sent_date} (Aktenzeichen {ref}).

Wie in meiner Anfrage angekündigt, bitte ich Sie jetzt, alle Personendaten über mich zu löschen (Art. 6 Abs. 4 und Art. 32 Abs. 2 Bst. c DSG). Behalten Sie nur den Sperrvermerk, der nötig ist, damit mein Widerspruch gegen Werbung weiter beachtet wird. Falls Sie meine Daten an Dritte bekanntgegeben haben, informieren Sie diese bitte ebenfalls.

Bitte bestätigen Sie mir die Löschung bis zum {due_date} und geben Sie dabei das Aktenzeichen {ref} an.

Freundliche Grüsse
{name}"""

ID_REPLY_CH = """Guten Tag

vielen Dank für Ihre Nachricht zu meiner Anfrage vom {sent_date} (Aktenzeichen {ref}). Sie bitten mich um eine Kopie meines Ausweises.

Nach Art. 16 Abs. 5 DSV treffen Sie angemessene Massnahmen, um mich zu identifizieren. Bitte prüfen Sie dafür zuerst die Angaben aus meiner Anfrage (Name, Anschriften, E-Mail-Adressen, Telefonnummern). Gern bestätige ich Ihnen eine der genannten E-Mail-Adressen, indem ich Ihnen von dort schreibe.

Falls das nicht genügt, teilen Sie mir bitte mit, warum. Ich sende Ihnen dann eine Ausweiskopie, auf der ich alle Angaben schwärze, die Sie für die Identifizierung nicht brauchen.

Freundliche Grüsse
{name}"""

CLARIFY_CH = """Guten Tag

vielen Dank für Ihre Rückfrage zu meiner Anfrage vom {sent_date} (Aktenzeichen {ref}).

Bitte prüfen Sie alle Angaben aus meiner Anfrage, also sämtliche genannten Namen, Anschriften, E-Mail-Adressen und Telefonnummern. Hier noch einmal zusammengefasst:
{id_block}

Meine Anfrage umfasst Auskunft (Art. 25 DSG), Widerspruch gegen Werbung (Art. 30 Abs. 2 Bst. b DSG) und Löschung (Art. 32 Abs. 2 Bst. c DSG).

Freundliche Grüsse
{name}"""

COMPLAINT_CH = """Guten Tag

ich melde Ihnen eine mögliche Verletzung des Datenschutzgesetzes (Art. 49 DSG).

Am {sent_date} habe ich mich mit einem Auskunfts-, Widerspruchs- und Löschungsbegehren nach Art. 25, 30 und 32 DSG an folgende Firma gewandt:
{broker_name}
{broker_contact}

{history}

Die Frist von 30 Tagen (Art. 18 DSV) ist abgelaufen, auch eine Erinnerung blieb ohne Erfolg. Ich bitte Sie, den Vorgang zu prüfen. Kopien meiner Anfrage und der Erinnerung kann ich Ihnen gern zusenden.

Sie erreichen mich unter {contact}.

Freundliche Grüsse
{name}
{address}"""

REMINDER_FOLLOWUP_DE = """Guten Tag,

zu meiner Anfrage vom {sent_date} (Aktenzeichen {ref}) habe ich Ihnen am {last_date} noch einmal geschrieben. Auf dieses Schreiben habe ich bisher keine Antwort erhalten, die Frist von einem Monat ist abgelaufen.

Bitte beantworten Sie mein Schreiben innerhalb von zwei Wochen nach Erhalt dieser Erinnerung. Andernfalls werde ich Beschwerde bei der zuständigen Datenschutzaufsichtsbehörde einreichen.

Mein letztes Schreiben finden Sie unten.

Mit freundlichen Grüßen
{name}

----- Mein Schreiben vom {last_date} -----
{last_body}"""

REMINDER_FOLLOWUP_EN = """Dear Sir or Madam,

Regarding my request of {sent_date} (reference {ref}), I wrote to you again on {last_date}. I have not received a reply to that message, and the one-month deadline has expired.

Please answer within two weeks of receiving this reminder. Otherwise I will lodge a complaint with the competent data protection supervisory authority.

You will find my last message below.

Yours faithfully,
{name}

----- My message of {last_date} -----
{last_body}"""

REMINDER_FOLLOWUP_CH = """Guten Tag

zu meinem Begehren vom {sent_date} (Aktenzeichen {ref}) habe ich Ihnen am {last_date} noch einmal geschrieben. Darauf habe ich bisher keine Antwort erhalten, die Frist von 30 Tagen ist abgelaufen.

Bitte beantworten Sie mein Schreiben innert 14 Tagen nach Erhalt dieser Erinnerung. Andernfalls werde ich die Angelegenheit dem Eidgenössischen Datenschutz- und Öffentlichkeitsbeauftragten (EDÖB) melden und behalte mir rechtliche Schritte vor.

Mein letztes Schreiben finden Sie unten.

Freundliche Grüsse
{name}

----- Mein Schreiben vom {last_date} -----
{last_body}"""


def _ctx(ctx: dict) -> dict:
    out = dict(ctx)
    out.setdefault("us_note", "")
    out.setdefault("last_date", out.get("sent_date", ""))
    out.setdefault("last_body", "")
    return out


def request_text(lang: str, ctx: dict, access_only: bool = False, us: bool = False) -> tuple:
    ctx = _ctx(ctx)
    if lang == "ch":
        if access_only:
            return ("Auskunftsbegehren nach Art. 25 DSG [%s]" % ctx["ref"], ACCESS_CH.format(**ctx))
        return ("Datenschutz-Begehren: Auskunft, Widerspruch und Löschung [%s]" % ctx["ref"], REQUEST_CH.format(**ctx))
    if lang == "en":
        if access_only:
            return ("Subject access request under Article 15 GDPR [%s]" % ctx["ref"], ACCESS_EN.format(**ctx))
        ctx["us_note"] = US_NOTE if us else ""
        return ("GDPR request: access, objection and erasure [%s]" % ctx["ref"], REQUEST_EN.format(**ctx))
    if access_only:
        return ("Selbstauskunft nach Art. 15 DSGVO [%s]" % ctx["ref"], ACCESS_DE.format(**ctx))
    return ("Datenschutz-Anfrage: Auskunft, Widerspruch und Löschung [%s]" % ctx["ref"], REQUEST_DE.format(**ctx))


def followup_text(kind: str, lang: str, ctx: dict) -> tuple:
    en = lang == "en"
    ctx = _ctx(ctx)
    ref = ctx["ref"]
    if kind == "reminder_followup":
        body = {"en": REMINDER_FOLLOWUP_EN, "ch": REMINDER_FOLLOWUP_CH}.get(lang, REMINDER_FOLLOWUP_DE)
        subject = ("Reminder: my message of %s [%s]" if en else "Erinnerung: mein Schreiben vom %s [%s]") % (ctx["last_date"], ref)
        return subject, body.format(**ctx)
    if lang == "ch":
        subjects = {"reminder": "Erinnerung: Datenschutz-Begehren vom %s [%s]" % (ctx["sent_date"], ref),
                    "erasure": "Löschung meiner Daten [%s]" % ref, "id_reply": "AW: Identifizierung [%s]" % ref,
                    "clarify": "AW: Ihre Rückfrage zu meinem Begehren [%s]" % ref}
        bodies = {"reminder": REMINDER_CH, "erasure": ERASURE_CH, "id_reply": ID_REPLY_CH, "clarify": CLARIFY_CH}
        if kind not in bodies:
            raise ValueError(kind)
        return subjects[kind], bodies[kind].format(**ctx)
    if kind == "reminder":
        return (("Reminder: GDPR request of %s [%s]" if en else "Erinnerung: Datenschutz-Anfrage vom %s [%s]")
                % (ctx["sent_date"], ref), (REMINDER_EN if en else REMINDER_DE).format(**ctx))
    if kind == "erasure":
        return (("Erasure of my data [%s]" if en else "Löschung meiner Daten [%s]") % ref,
                (ERASURE_EN if en else ERASURE_DE).format(**ctx))
    if kind == "id_reply":
        return (("Re: identity verification [%s]" if en else "AW: Identitätsnachweis [%s]") % ref,
                (ID_REPLY_EN if en else ID_REPLY_DE).format(**ctx))
    if kind == "clarify":
        return (("Re: your question about my request [%s]" if en else "AW: Ihre Rückfrage zu meiner Anfrage [%s]") % ref,
                (CLARIFY_EN if en else CLARIFY_DE).format(**ctx))
    raise ValueError(kind)


def complaint_text(ctx: dict, swiss: bool = False) -> tuple:
    if swiss:
        return ("Meldung nach Art. 49 DSG: %s" % ctx["broker_name"], COMPLAINT_CH.format(**ctx))
    return ("Beschwerde nach Art. 77 DSGVO gegen %s" % ctx["broker_name"], COMPLAINT_DE.format(**ctx))


TEMPLATE_LIST = [
    {"id": "request", "label": "Erstanfrage", "sub": "Auskunft, Widerspruch gegen Werbung, Löschung", "langs": "DE · CH · EN"},
    {"id": "access", "label": "Selbstauskunft", "sub": "Für Auskunfteien: nur Auskunft", "langs": "DE · CH · EN"},
    {"id": "reminder", "label": "Erinnerung", "sub": "Wenn die Frist abgelaufen ist", "langs": "DE · CH · EN"},
    {"id": "erasure", "label": "Löschung nach Auskunft", "sub": "Mit Sperrvermerk gegen erneute Aufnahme", "langs": "DE · CH · EN"},
    {"id": "id_reply", "label": "Antwort auf Ausweis-Forderung", "sub": "Nur bei echtem Grund für Zweifel", "langs": "DE · CH · EN"},
    {"id": "clarify", "label": "Antwort auf Rückfrage", "sub": "Bitte alle genannten Angaben prüfen", "langs": "DE · CH · EN"},
    {"id": "complaint", "label": "Beschwerde an die Datenschutzbehörde", "sub": "Wenn eine Firma gar nicht reagiert", "langs": "DE · CH"},
]
