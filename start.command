#!/bin/bash
# Double-clique ce fichier pour lancer le pipeline.
cd "$(dirname "$0")" || exit 1
export IGNOBEL_PAUSE=1
if command -v python3 >/dev/null 2>&1; then
  python3 scripts/start.py
else
  echo "Python 3 n'est pas installe."
  echo "Telecharge-le ici : https://www.python.org/downloads/"
  echo "Puis double-clique de nouveau ce fichier."
  read -r -p "Appuie sur Entree pour fermer..."
fi
