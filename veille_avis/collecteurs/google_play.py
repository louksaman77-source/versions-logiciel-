"""Avis Google Play, via la bibliothèque open source google-play-scraper (JoMingyu)."""

from __future__ import annotations

from ..config import Concurrent, Config
from ..modeles import Avis


def collecter(concurrent: Concurrent, cfg: Config) -> list[Avis]:
    from google_play_scraper import Sort, reviews

    app_id = concurrent.google_play
    # On ne récupère que les avis de 1 à note_max étoiles : ce sont eux qui décrivent les problèmes.
    par_note = max(1, cfg.max_avis_par_source // cfg.note_max)
    bruts: list[dict] = []
    for note in range(1, cfg.note_max + 1):
        lot, _ = reviews(
            app_id,
            lang=concurrent.langue or cfg.langue,
            country=concurrent.pays or cfg.pays,
            sort=Sort.NEWEST,
            count=par_note,
            filter_score_with=note,
        )
        bruts.extend(lot)
    return [convertir(r, concurrent.nom, app_id) for r in bruts if (r.get("content") or "").strip()]


def convertir(brut: dict, nom_concurrent: str, app_id: str) -> Avis:
    date = brut.get("at")
    date_iso = date.isoformat() if hasattr(date, "isoformat") else (str(date) if date else None)
    note = brut.get("score")
    return Avis(
        id=Avis.construire_id("google_play", nom_concurrent, brut["reviewId"]),
        concurrent=nom_concurrent,
        source="google_play",
        texte=brut["content"].strip(),
        note=float(note) if note is not None else None,
        date=date_iso,
        url=f"https://play.google.com/store/apps/details?id={app_id}&reviewId={brut['reviewId']}",
    )
