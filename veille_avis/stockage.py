"""Lecture et écriture des fichiers de données (JSON Lines et JSON)."""

from __future__ import annotations

import json
from pathlib import Path

from .modeles import Avis


def lire_jsonl(chemin: Path) -> list[dict]:
    if not chemin.exists():
        return []
    lignes = []
    with chemin.open(encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne:
                lignes.append(json.loads(ligne))
    return lignes


def ecrire_jsonl(chemin: Path, lignes: list[dict]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(chemin.suffix + ".tmp")
    with temporaire.open("w", encoding="utf-8") as f:
        for ligne in lignes:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    temporaire.replace(chemin)


def ajouter_jsonl(chemin: Path, lignes: list[dict]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("a", encoding="utf-8") as f:
        for ligne in lignes:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def lire_json(chemin: Path) -> dict | None:
    if not chemin.exists():
        return None
    return json.loads(chemin.read_text(encoding="utf-8"))


def ecrire_json(chemin: Path, donnees: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")


def lire_avis(chemin: Path) -> list[Avis]:
    return [Avis.from_dict(d) for d in lire_jsonl(chemin)]


def fusionner_avis(chemin: Path, nouveaux: list[Avis]) -> tuple[int, int]:
    """Ajoute les nouveaux avis au fichier sans doublon. Renvoie (total, nombre d'avis nouveaux)."""
    existants = {a.id: a for a in lire_avis(chemin)}
    ajoutes = 0
    for avis in nouveaux:
        if avis.id not in existants:
            ajoutes += 1
        existants[avis.id] = avis  # la version la plus récente remplace l'ancienne
    ecrire_jsonl(chemin, [a.to_dict() for a in existants.values()])
    return len(existants), ajoutes
