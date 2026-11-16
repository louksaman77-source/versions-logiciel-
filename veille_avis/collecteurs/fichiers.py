"""Import d'avis depuis des fichiers CSV, JSON ou JSONL.

Pour les sites sans API publique (G2, Capterra, Trustpilot, TrustRadius...), exporte les avis
avec l'outil de ton choix (Apify, export manuel, sondage...) puis déclare le fichier dans la config.
Les colonnes courantes sont reconnues automatiquement ; sinon, indique-les dans « colonnes ».
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from ..config import Concurrent, Config, SourceFichier
from ..modeles import Avis, empreinte

CANDIDATS: dict[str, list[str]] = {
    "texte": [
        "texte", "text", "review_text", "reviewtext", "review_body", "reviewbody", "review", "content",
        "body", "comment", "commentaire", "avis", "cons", "dislikes", "what_do_you_dislike",
        "negatives", "inconvenients", "message",
    ],
    "titre": ["titre", "title", "headline", "review_title", "reviewtitle", "summary"],
    "note": ["note", "rating", "score", "stars", "etoiles", "overall_rating", "rating_value", "ratingvalue"],
    "date": [
        "date", "review_date", "date_published", "datepublished", "published_at", "published",
        "publishedat", "created_at", "createdat", "submitted_at", "updated", "at",
    ],
    "url": ["url", "review_url", "reviewurl", "link", "lien", "permalink"],
    "id": ["id", "review_id", "reviewid", "uuid"],
}


def _cle(nom: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", nom.strip().lower()).strip("_")


def aplatir(objet: dict, prefixe: str = "") -> dict:
    """{"rating": {"value": 4}} → {"rating_value": 4} (pour les exports JSON imbriqués)."""
    resultat = {}
    for cle, valeur in objet.items():
        nom = _cle(f"{prefixe}_{cle}" if prefixe else str(cle))
        if isinstance(valeur, dict):
            resultat.update(aplatir(valeur, nom))
        else:
            resultat[nom] = valeur
    return resultat


def lire_lignes(chemin: Path) -> list[dict]:
    suffixe = chemin.suffix.lower()
    if suffixe == ".csv":
        texte = chemin.read_text(encoding="utf-8-sig")
        try:
            dialecte = csv.Sniffer().sniff(texte[:5000], delimiters=",;\t")
        except csv.Error:
            dialecte = csv.excel
        return [dict(ligne) for ligne in csv.DictReader(io.StringIO(texte, newline=""), dialect=dialecte)]
    if suffixe == ".jsonl":
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]
    if suffixe == ".json":
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        if isinstance(donnees, dict):
            # Formats du type {"reviews": [...]} ou {"data": [...]}
            listes = [v for v in donnees.values() if isinstance(v, list)]
            donnees = listes[0] if listes else [donnees]
        return [d for d in donnees if isinstance(d, dict)]
    raise ValueError(f"format non pris en charge : {chemin.name} (utilise .csv, .json ou .jsonl)")


def lire_note(valeur, echelle: float) -> float | None:
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, (int, float)):
        nombre = float(valeur)
    else:
        trouve = re.search(r"\d+(?:[.,]\d+)?", str(valeur))
        if not trouve:
            return None
        nombre = float(trouve.group().replace(",", "."))
    if echelle and echelle != 5:
        nombre = nombre * 5 / echelle
    return round(nombre, 2)


def _colonnes(source: SourceFichier, cles_presentes: set[str]) -> dict[str, list[str]]:
    choix: dict[str, list[str]] = {}
    for champ, candidats in CANDIDATS.items():
        impose = source.colonnes.get(champ)
        if impose:
            choix[champ] = [_cle(c) for c in (impose if isinstance(impose, list) else [impose])]
        else:
            trouve = next((c for c in candidats if c in cles_presentes), None)
            choix[champ] = [trouve] if trouve else []
    return choix


def importer(source: SourceFichier, nom_concurrent: str) -> list[Avis]:
    if not source.chemin.exists():
        raise FileNotFoundError(f"fichier introuvable : {source.chemin}")
    lignes = [aplatir(l) for l in lire_lignes(source.chemin)]
    if not lignes:
        return []
    cles = set().union(*(l.keys() for l in lignes))
    colonnes = _colonnes(source, cles)
    if not colonnes["texte"]:
        raise ValueError(
            f"{source.chemin.name} : impossible de trouver la colonne du texte des avis. "
            f"Colonnes disponibles : {', '.join(sorted(cles))}. Indique-la dans « colonnes: texte: ... »."
        )

    def valeur(ligne: dict, champ: str):
        for colonne in colonnes[champ]:
            v = ligne.get(colonne)
            if v not in (None, ""):
                return v
        return None

    resultat = []
    for ligne in lignes:
        morceaux = [str(ligne.get(c)).strip() for c in colonnes["texte"] if ligne.get(c) not in (None, "")]
        texte = "\n".join(m for m in morceaux if m)
        if not texte:
            continue
        id_natif = valeur(ligne, "id")
        id_natif = str(id_natif) if id_natif is not None else empreinte(texte)
        date = valeur(ligne, "date")
        url = valeur(ligne, "url")
        resultat.append(
            Avis(
                id=Avis.construire_id(source.source, nom_concurrent, id_natif),
                concurrent=nom_concurrent,
                source=source.source,
                texte=texte,
                titre=str(valeur(ligne, "titre") or "").strip(),
                note=lire_note(valeur(ligne, "note"), source.echelle_note),
                date=str(date) if date is not None else None,
                url=str(url) if url is not None else None,
            )
        )
    return resultat


def collecter(concurrent: Concurrent, cfg: Config) -> list[Avis]:
    resultat = []
    for source in concurrent.fichiers:
        resultat.extend(importer(source, concurrent.nom))
    return resultat
