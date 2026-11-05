# Spurlos

Spurlos schreibt Datenhändler für dich an und verlangt Auskunft, Widerspruch gegen Werbung und Löschung deiner Daten. Es verschickt die Anfragen in Etappen aus einem eigenen Postfach, erkennt die Antworten, achtet auf die Fristen und erinnert Firmen, die nicht antworten. Bleibt eine Firma stumm, bereitet es einen Beschwerde-Text für die Datenschutzbehörde vor.

Die Liste umfasst rund 200 geprüfte Firmen aus Deutschland, Österreich, der Schweiz, der EU, Großbritannien und den USA. Welche davon angeschrieben werden, richtet sich nach den Ländern, die du angibst. Firmen in der Schweiz bekommen Briefe nach dem Schweizer Datenschutzgesetz.

Spurlos läuft nur auf deinem Mac. Es gibt keinen Server und kein Benutzerkonto.

## Was du brauchst

- Einen Mac mit macOS 12 oder neuer
- Ein eigenes E-Mail-Postfach nur für Spurlos, zum Beispiel bei deinem Webhoster, GMX, WEB.DE, iCloud oder Gmail
- Beim ersten Start eine Internetverbindung (Spurlos lädt zwei kleine Programmteile nach)

## Installieren

1. Die ZIP-Datei doppelklicken. Den Ordner „Spurlos“ an einen festen Ort legen, zum Beispiel in „Dokumente“. Später nicht mehr verschieben.
2. Im Ordner **Spurlos.command** doppelklicken.
3. macOS sagt beim ersten Mal, dass es die Datei nicht prüfen kann. Das liegt daran, dass Spurlos nicht über den App Store kommt.
   - Klick auf „Fertig“ (nicht „In den Papierkorb“).
   - Öffne **Systemeinstellungen › Datenschutz & Sicherheit**, scroll nach unten und klick bei „Spurlos.command“ auf **Dennoch öffnen**.
   - Danach noch einmal Spurlos.command doppelklicken.
4. Falls dein Mac nach den „Befehlszeilenentwicklerwerkzeugen“ fragt: auf „Installieren“ klicken, warten, dann Spurlos.command noch einmal öffnen. Das braucht Spurlos für Python.
5. Beim ersten Start richtet sich Spurlos ein (etwa eine Minute). Danach öffnet sich dein Browser mit der Einrichtung.

## Benutzen

- Das Terminal-Fenster muss offen bleiben, solange Spurlos arbeiten soll. Nur dann verschickt es Etappen und ruft das Postfach ab.
- Was liegen bleibt, holt Spurlos beim nächsten Start nach. Du kannst den Mac also normal ausschalten.
- Zum Beenden das Terminal-Fenster schließen.
- Wenn du Spurlos öffnest, während es schon läuft, öffnet sich nur das Browserfenster neu.

## Deine Daten

- Alles liegt in `~/Library/Application Support/Spurlos`.
- Das Passwort deines Postfachs und ein KI-Schlüssel liegen im Schlüsselbund deines Macs.
- Unter **Einstellungen › Daten & Sicherung** kannst du eine Sicherung exportieren oder alles löschen.

## KI (optional)

Spurlos erkennt Antworten auch ohne KI. Wenn du willst, hilft eine KI bei ungewöhnlichen Antworten:

- **Apple Intelligence**: läuft auf deinem Mac, kostenlos. Braucht macOS 26 und einen Mac mit Apple-Chip. Das Installationsprogramm richtet die Anbindung dann selbst ein.
- **Ollama**: ein freies Modell auf deinem Mac, kostenlos, braucht viel Speicher. Gibt es auf ollama.com.
- **Cloud-KI** (Claude oder ChatGPT): braucht einen API-Schlüssel und kostet pro Nutzung. Der Text der Antworten geht dann an den Anbieter.

Egal welche Einstellung: Spurlos verschickt nichts, bevor du einen Vorschlag bestätigt hast.

## Entfernen

1. In Spurlos unter **Einstellungen › Daten & Sicherung** auf „Alle Daten löschen“.
2. Den Ordner „Spurlos“ in den Papierkorb legen.

## Hinweise

Spurlos hilft dir, deine Rechte nach der Datenschutz-Grundverordnung und dem Schweizer Datenschutzgesetz wahrzunehmen. Es ersetzt keine Rechtsberatung.

Die Firmenliste stammt aus der offenen Datenbank von datenanfragen.de (CC0), der öffentlichen Liste von Incogni, dem Datenhändler-Register des US-Bundesstaats Kalifornien und eigener Recherche. Die Kontaktadressen wurden im November 2026 auf den Datenschutzseiten der Firmen geprüft. Kontaktdaten können sich ändern. Wenn eine Mail nicht zugestellt wird, zeigt Spurlos das an, und du kannst die Adresse in der Händlerliste korrigieren.

Schrift: IBM Plex (SIL Open Font License).
