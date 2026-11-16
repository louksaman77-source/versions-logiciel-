"""Avis App Store, via le flux RSS public d'Apple (500 avis les plus récents au maximum)."""

from __future__ import annotations

import requests

from ..config import Concurrent, Config
from ..modeles import Avis

URL = "https://itunes.apple.com/{pays}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
PAGES_MAX = 10  # limite imposée par Apple


def collecter(concurrent: Concurrent, cfg: Config, session=None) -> list[Avis]:
    session = session or requests.Session()
    app_id = concurrent.app_store
    pays = concurrent.pays or cfg.pays
    resultat: list[Avis] = []
    for page in range(1, PAGES_MAX + 1):
        reponse = session.get(URL.format(pays=pays, page=page, app_id=app_id), timeout=30)
        if reponse.status_code in (400, 404):
            break
        reponse.raise_for_status()
        entrees = lire_flux(reponse.json())
        if not entrees:
            break
        for entree in entrees:
            avis = convertir(entree, concurrent.nom, app_id, pays)
            # Même règle que Google Play : on garde les avis de 1 à note_max étoiles.
            if avis and avis.note is not None and avis.note <= cfg.note_max:
                resultat.append(avis)
        if len(resultat) >= cfg.max_avis_par_source:
            break
    return resultat[: cfg.max_avis_par_source]


def lire_flux(donnees: dict) -> list[dict]:
    entrees = (donnees.get("feed") or {}).get("entry") or []
    if isinstance(entrees, dict):  # une seule entrée → Apple renvoie un objet, pas une liste
        entrees = [entrees]
    return [e for e in entrees if isinstance(e, dict) and "im:rating" in e]


def _label(entree: dict, cle: str) -> str:
    valeur = entree.get(cle) or {}
    return str(valeur.get("label", "")).strip() if isinstance(valeur, dict) else ""


def convertir(entree: dict, nom_concurrent: str, app_id: str, pays: str) -> Avis | None:
    texte = _label(entree, "content")
    id_natif = _label(entree, "id")
    if not texte or not id_natif:
        return None
    try:
        note = float(_label(entree, "im:rating"))
    except ValueError:
        note = None
    return Avis(
        id=Avis.construire_id("app_store", nom_concurrent, id_natif),
        concurrent=nom_concurrent,
        source="app_store",
        texte=texte,
        titre=_label(entree, "title"),
        note=note,
        date=_label(entree, "updated") or None,
        url=f"https://apps.apple.com/{pays}/app/id{app_id}?see-all=reviews",
    )
