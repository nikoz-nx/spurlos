#!/bin/bash
# Richtet Spurlos ein: eigene Python-Umgebung im Programmordner, danach Flask und keyring.
# Nichts wird systemweit installiert. Löschen = Ordner in den Papierkorb.
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
VENV="$HERE/.venv"
QUIET=0
[ "$1" = "--quiet" ] && QUIET=1

say() { echo "$@"; }
fail() {
  echo
  echo "Fehler: $1"
  if [ "$QUIET" = "0" ]; then
    echo
    read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen. " _
  fi
  exit 1
}

# 1. Python finden (mindestens 3.9)
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 /usr/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PY="$(command -v "$candidate")"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  say "Für Spurlos braucht dein Mac Python 3."
  say "Gleich öffnet sich ein Fenster von Apple, das die „Befehlszeilenentwicklerwerkzeuge“ installiert."
  say "Klick dort auf „Installieren“ und starte Spurlos danach noch einmal."
  xcode-select --install >/dev/null 2>&1
  fail "Python 3 fehlt noch."
fi

say "Python gefunden: $("$PY" --version 2>&1)"

# 2. Eigene Umgebung im Programmordner
if [ ! -x "$VENV/bin/python3" ]; then
  say "Lege die Umgebung an …"
  "$PY" -m venv "$VENV" || fail "Die Python-Umgebung konnte nicht angelegt werden."
fi

# 3. Pakete installieren
say "Installiere Flask und keyring …"
"$VENV/bin/python3" -m pip install --disable-pip-version-check -q --upgrade pip >/dev/null 2>&1
"$VENV/bin/python3" -m pip install --disable-pip-version-check -q -r "$HERE/requirements.txt" \
  || fail "Die Pakete konnten nicht installiert werden. Bist du mit dem Internet verbunden?"

# 4. Optional: Apple Intelligence (nur macOS 26 oder neuer mit Apple-Chip)
MAJOR="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
ARCH="$(uname -m)"
if [ "${MAJOR:-0}" -ge 26 ] 2>/dev/null && [ "$ARCH" = "arm64" ]; then
  if xcrun --find swiftc >/dev/null 2>&1; then
    say "Richte die Anbindung an Apple Intelligence ein (optional) …"
    if xcrun swiftc -O -parse-as-library "$HERE/spurlos/helpers/spurlos_fm.swift" -o "$VENV/bin/spurlos-fm" >/dev/null 2>&1; then
      say "Apple Intelligence: Anbindung eingerichtet."
    else
      say "Apple Intelligence: konnte nicht eingerichtet werden. Spurlos funktioniert trotzdem."
    fi
  fi
fi

"$VENV/bin/python3" -c "import flask, keyring" >/dev/null 2>&1 || fail "Die Installation ist unvollständig."
say "Fertig. Starte Spurlos jetzt mit einem Doppelklick auf „Spurlos.command“."
if [ "$QUIET" = "0" ]; then
  echo
  read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen. " _
fi
exit 0
