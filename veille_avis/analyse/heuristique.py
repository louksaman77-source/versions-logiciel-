"""Analyse sans IA, par mots-clés : gratuite et hors ligne, mais beaucoup moins fine que Claude.

Chaque avis est découpé en phrases ; une phrase qui contient un mot-clé d'une catégorie devient
un problème de cette catégorie (une seule citation par catégorie et par avis).
"""

from __future__ import annotations

import re

from ..categories import CATEGORIES, MOTIF_DEPART, MOTIFS, normaliser
from ..modeles import Avis, Probleme

LONGUEUR_CITATION = 300


def phrases(texte: str) -> list[str]:
    morceaux = re.split(r"(?<=[.!?…])\s+|\n+", texte)
    return [m.strip() for m in morceaux if m and m.strip()]


def _couper(texte: str) -> str:
    return texte if len(texte) <= LONGUEUR_CITATION else texte[: LONGUEUR_CITATION - 1].rstrip() + "…"


def gravite(avis: Avis, depart: bool) -> int:
    if depart or (avis.note is not None and avis.note <= 1):
        return 3
    if avis.note is None or avis.note <= 2:
        return 2
    return 1


def extraire(avis: Avis) -> list[Probleme]:
    # Le corps de l'avis d'abord : le titre (« Lent », « Support »...) ne sert de citation qu'en dernier recours.
    liste_phrases = phrases(avis.texte) + ([avis.titre.strip()] if avis.titre and avis.titre.strip() else [])
    depart = MOTIF_DEPART.search(normaliser(avis.texte_complet())) is not None
    niveau = gravite(avis, depart)
    problemes: list[Probleme] = []
    for categorie, motif in MOTIFS.items():
        phrase = next((p for p in liste_phrases if motif.search(normaliser(p))), None)
        if phrase:
            problemes.append(
                Probleme(
                    avis_id=avis.id,
                    probleme=CATEGORIES[categorie],
                    categorie=categorie,
                    citation=_couper(phrase),
                    gravite=niveau,
                    depart=depart,
                )
            )
    # Avis très négatif sans mot-clé reconnu : on le garde dans « Autre » pour ne rien perdre.
    if not problemes and avis.note is not None and avis.note <= 2 and liste_phrases:
        problemes.append(
            Probleme(
                avis_id=avis.id,
                probleme=CATEGORIES["autre"],
                categorie="autre",
                citation=_couper(liste_phrases[0]),
                gravite=niveau,
                depart=depart,
            )
        )
    return problemes


def themes() -> list[dict]:
    """En mode mots-clés, chaque catégorie est un thème."""
    return [
        {"id": cle, "titre": titre, "description": "", "categorie": cle} for cle, titre in CATEGORIES.items()
    ]
