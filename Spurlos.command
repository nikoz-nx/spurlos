#!/bin/bash
# Startet Spurlos. Beim ersten Mal wird es vorher eingerichtet (dauert etwa eine Minute).
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
VENV="$HERE/.venv"

finish() {
  echo
  read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen. " _
}

need_install=0
if [ ! -x "$VENV/bin/python3" ]; then
  need_install=1
elif ! "$VENV/bin/python3" -c "import flask, keyring" >/dev/null 2>&1; then
  need_install=1
fi

if [ "$need_install" = "1" ]; then
  echo "Spurlos wird eingerichtet …"
  if ! /bin/bash "$HERE/Installieren.command" --quiet; then
    finish
    exit 1
  fi
fi

clear
echo "Spurlos"
echo "-------"
echo "Lass dieses Fenster offen, solange Spurlos arbeiten soll."
echo "Zum Beenden: dieses Fenster schließen oder Ctrl+C drücken."
echo
"$VENV/bin/python3" -m spurlos "$@"
status=$?
if [ $status -ne 0 ]; then
  echo
  echo "Spurlos wurde mit einem Fehler beendet (Code $status)."
  finish
fi
exit $status
