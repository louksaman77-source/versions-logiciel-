"""Collecte des avis de chaque concurrent, source par source."""

from __future__ import annotations

from typing import Callable

from ..config import Concurrent, Config
from ..modeles import Avis, slug
from ..stockage import fusionner_avis
from . import app_store, fichiers, google_play, hackernews, reddit

SOURCES: list[tuple[str, Callable[[Concurrent], bool], Callable[[Concurrent, Config], list[Avis]]]] = [
    ("Google Play", lambda c: bool(c.google_play), google_play.collecter),
    ("App Store", lambda c: bool(c.app_store), app_store.collecter),
    ("Hacker News", lambda c: bool(c.hackernews), hackernews.collecter),
    ("Reddit", lambda c: c.reddit is not None, reddit.collecter),
    ("Fichiers importés", lambda c: bool(c.fichiers), fichiers.collecter),
]


def collecter_tout(cfg: Config, seulement: str | None = None) -> tuple[int, int]:
    """Collecte toutes les sources configurées et les ajoute à data/avis.jsonl.

    Une source en échec n'arrête pas les autres. Renvoie (total en base, nouveaux avis).
    """
    concurrents = cfg.concurrents
    if seulement:
        concurrents = [c for c in concurrents if slug(c.nom) == slug(seulement)]
        if not concurrents:
            noms = ", ".join(c.nom for c in cfg.concurrents)
            raise ValueError(f"concurrent « {seulement} » absent de la config (disponibles : {noms})")

    collectes: list[Avis] = []
    for concurrent in concurrents:
        print(f"\n▶ {concurrent.nom}")
        sources = [(nom, fn) for nom, active, fn in SOURCES if active(concurrent)]
        if not sources:
            print("  ⚠ aucune source configurée pour ce concurrent")
        for nom, fonction in sources:
            try:
                avis = fonction(concurrent, cfg)
            except Exception as erreur:  # une source cassée ne doit pas bloquer les autres
                print(f"  ✗ {nom} : {erreur}")
                continue
            collectes.extend(avis)
            print(f"  ✓ {nom} : {len(avis)} avis")
            if not avis:
                print("    ⚠ aucun avis récupéré : vérifie l'identifiant, le pays/la langue ou ta connexion")

    total, nouveaux = fusionner_avis(cfg.fichier_avis, collectes)
    return total, nouveaux
