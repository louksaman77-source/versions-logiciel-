"""Commentaires Hacker News qui citent un concurrent, via l'API publique Algolia."""

from __future__ import annotations

import html
import re

import requests

from ..categories import normaliser
from ..config import Concurrent, Config
from ..modeles import Avis

URL = "https://hn.algolia.com/api/v1/search_by_date"


def collecter(concurrent: Concurrent, cfg: Config, session=None) -> list[Avis]:
    session = session or requests.Session()
    requete = concurrent.hackernews
    resultat: list[Avis] = []
    page = 0
    while len(resultat) < cfg.max_avis_par_source:
        reponse = session.get(
            URL,
            params={"query": requete, "tags": "comment", "hitsPerPage": 100, "page": page},
            timeout=30,
        )
        reponse.raise_for_status()
        donnees = reponse.json()
        resultats_page = donnees.get("hits") or []
        for brut in resultats_page:
            avis = convertir(brut, concurrent.nom)
            # Algolia tolère les fautes de frappe : on ne garde que les commentaires qui citent vraiment le nom.
            if avis and mentionne(avis.texte, requete):
                resultat.append(avis)
        page += 1
        if not resultats_page or page >= int(donnees.get("nbPages") or 0):
            break
    return resultat[: cfg.max_avis_par_source]


def nettoyer_html(texte: str) -> str:
    texte = re.sub(r"<p>", "\n\n", texte)
    texte = re.sub(r"<[^>]+>", "", texte)
    return html.unescape(texte).strip()


def mentionne(texte: str, terme: str) -> bool:
    terme = normaliser(terme.strip().strip('"'))
    return bool(terme) and re.search(r"(?<![a-z0-9])" + re.escape(terme) + r"(?![a-z0-9])", normaliser(texte)) is not None


def convertir(brut: dict, nom_concurrent: str) -> Avis | None:
    texte = nettoyer_html(brut.get("comment_text") or "")
    id_natif = str(brut.get("objectID") or "")
    if not texte or not id_natif:
        return None
    return Avis(
        id=Avis.construire_id("hackernews", nom_concurrent, id_natif),
        concurrent=nom_concurrent,
        source="hackernews",
        texte=texte,
        titre=f"Discussion : {brut['story_title']}" if brut.get("story_title") else "",
        date=brut.get("created_at"),
        url=f"https://news.ycombinator.com/item?id={id_natif}",
    )
