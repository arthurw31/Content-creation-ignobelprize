#!/usr/bin/env python3
"""Lanceur tout-en-un : installe, verifie, teste, produit.

Ce script est fait pour etre lance par double-clic (start.command sur Mac,
start.bat sur Windows). Il ne suppose aucune connaissance du terminal.

Il enchaine :
    1. verification de Python
    2. creation d'un environnement isole et installation des dependances
    3. installation de FFmpeg (via imageio-ffmpeg, aucun telechargement manuel)
    4. saisie masquee de la cle OpenRouter, enregistree dans .env
    5. le probe : verifie la cle et liste les modeles accessibles
    6. proposition de lancer un rendu

Les messages sont en francais parce que c'est un outil, pas du code de
bibliotheque. Le reste du depot reste en anglais.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
ENV_FILE = ROOT / ".env"
REPORT = ROOT / "probe-resultat.txt"

DEPS = ["Pillow>=10.0", "imageio-ffmpeg>=0.5"]


# Les couleurs ANSI ne sont pas garanties dans cmd.exe. On les desactive sur
# Windows plutot que de risquer un affichage rempli de codes illisibles.
COLOUR = os.name != "nt" and sys.stdout.isatty()


def _paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOUR else text


def title(text: str) -> None:
    print("\n" + _paint("1", text))


def ok(text: str) -> None:
    print(f"  {_paint('32', 'ok')}  {text}")


def warn(text: str) -> None:
    print(f"  {_paint('33', '!')}   {text}")


def fail(text: str) -> None:
    print(f"  {_paint('31', 'X')}   {text}")


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def check_python() -> None:
    title("1. Python")
    if sys.version_info < (3, 10):
        fail(f"Python {sys.version_info.major}.{sys.version_info.minor} est trop ancien.")
        print("\n     Installe Python 3.10 ou plus recent : https://www.python.org/downloads/")
        print("     Puis relance ce script.")
        raise SystemExit(1)
    ok(f"Python {sys.version_info.major}.{sys.version_info.minor}")


def build_venv() -> Path:
    title("2. Environnement et dependances")
    if not venv_python().exists():
        print("     creation de l'environnement isole (une seule fois)...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    python = venv_python()
    print("     installation des dependances...")
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--upgrade", *DEPS],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail("l'installation a echoue")
        print(result.stderr[-1500:])
        raise SystemExit(1)
    ok("dependances installees")
    return python


def check_ffmpeg(python: Path) -> None:
    title("3. FFmpeg")
    probe = (
        "import imageio_ffmpeg, sys; "
        "sys.stdout.write(imageio_ffmpeg.get_ffmpeg_exe())"
    )
    result = subprocess.run([str(python), "-c", probe],
                            capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        fail("FFmpeg introuvable")
        print(result.stderr[-800:])
        raise SystemExit(1)
    path = result.stdout.strip()
    ok(f"FFmpeg pret\n      {path}")


def read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def get_key() -> str:
    title("4. Cle OpenRouter")
    existing = read_env().get("OPENROUTER_API_KEY", "")
    if existing:
        ok(f"cle deja enregistree (...{existing[-6:]})")
        answer = input("     en utiliser une autre ? [o/N] ").strip().lower()
        if answer not in {"o", "oui", "y", "yes"}:
            return existing

    print("\n     Colle ta cle OpenRouter (elle ne s'affichera pas).")
    print("     Elle est enregistree dans le fichier .env, qui n'est jamais")
    print("     envoye sur GitHub.\n")

    import getpass
    key = getpass.getpass("     cle : ").strip()
    if not key.startswith("sk-or-"):
        warn("cette cle ne ressemble pas a une cle OpenRouter (attendu sk-or-...)")
        if input("     continuer quand meme ? [o/N] ").strip().lower() not in {"o", "oui"}:
            raise SystemExit(1)

    ENV_FILE.write_text(f"OPENROUTER_API_KEY={key}\n", encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass
    ok("cle enregistree dans .env")
    return key


def run_probe(python: Path, key: str) -> bool:
    title("5. Test de la cle (gratuit, ne genere rien)")
    env = {**os.environ, "OPENROUTER_API_KEY": key, "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [str(python), "-m", "pipeline.aiclip.openrouter", "--probe"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    print(output)
    REPORT.write_text(output, encoding="utf-8")
    print(f"\n     Resultat enregistre dans : {REPORT.name}")
    print("     Copie-colle son contenu a Claude s'il y a une erreur.")
    return result.returncode == 0


def offer_render(python: Path, key: str) -> None:
    title("6. Produire une video")
    print("     a) apercu du plan et du cout, sans rien depenser")
    print("     b) generer la video pour de vrai")
    print("     c) quitter")
    choice = input("\n     ton choix [a/b/c] ").strip().lower()

    env = {**os.environ, "OPENROUTER_API_KEY": key, "PYTHONPATH": str(ROOT)}
    if choice == "a":
        subprocess.run([str(python), "scripts/make_ai_video.py",
                        "--prize", "polyester-rats", "--dry-run"],
                       cwd=ROOT, env=env)
    elif choice == "b":
        budget = input("     budget maximum en dollars [8] ").strip() or "8"
        subprocess.run([str(python), "scripts/make_ai_video.py",
                        "--prize", "polyester-rats", "--budget", budget],
                       cwd=ROOT, env=env)
        print(f"\n     La video est dans le dossier : {ROOT / 'out'}")


def main() -> int:
    print("\n" + _paint("1", "Pipeline video Ig Nobel"))
    print("Rien n'est depense sans que tu le demandes explicitement.")

    check_python()
    python = build_venv()
    check_ffmpeg(python)
    key = get_key()

    if not run_probe(python, key):
        fail("\nLe test a echoue. Envoie le contenu de probe-resultat.txt a Claude.")
        return 1

    offer_render(python, key)
    print("\nTermine.\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrompu")
        raise SystemExit(130)
    finally:
        if os.name == "nt" or os.environ.get("IGNOBEL_PAUSE"):
            input("\nAppuie sur Entree pour fermer...")
