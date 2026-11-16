"""Calcul des statistiques par thème : fréquence, gravité, concurrents touchés, priorité."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..modeles import Avis, Probleme, lire_date

JOURS_RECENTS = 180


def priorite(mentions: int, gravite_moyenne: float, nb_concurrents: int, departs: int) -> float:
    """Plus un problème est fréquent, grave, partagé par plusieurs concurrents et cause de départs,
    plus il représente une opportunité de différenciation."""
    if mentions == 0:
        return 0.0
    bonus_concurrents = 1 + 0.5 * max(0, nb_concurrents - 1)
    bonus_departs = 1 + departs / mentions
    return round(mentions * gravite_moyenne * bonus_concurrents * bonus_departs, 1)


def choisir_exemples(problemes: list[Probleme], avis_par_id: dict[str, Avis], nombre: int = 5) -> list[dict]:
    """Les citations les plus graves, en alternant les concurrents pour varier les exemples."""
    tries = sorted(problemes, key=lambda p: (-p.gravite, -int(p.depart), -len(p.citation or "")))
    par_concurrent: dict[str, list[Probleme]] = defaultdict(list)
    for p in tries:
        avis = avis_par_id.get(p.avis_id)
        if avis and p.citation:
            par_concurrent[avis.concurrent].append(p)
    exemples: list[dict] = []
    vues: set[str] = set()
    while len(exemples) < nombre and any(par_concurrent.values()):
        for concurrent in list(par_concurrent):
            if not par_concurrent[concurrent] or len(exemples) >= nombre:
                continue
            p = par_concurrent[concurrent].pop(0)
            if p.citation.lower() in vues:
                continue
            vues.add(p.citation.lower())
            avis = avis_par_id[p.avis_id]
            exemples.append(
                {
                    "citation": p.citation,
                    "concurrent": avis.concurrent,
                    "source": avis.source,
                    "note": avis.note,
                    "date": avis.date,
                    "url": avis.url,
                    "gravite": p.gravite,
                }
            )
    return exemples


def statistiques(
    themes: list[dict],
    problemes: list[Probleme],
    theme_de: Callable[[Probleme], str],
    avis_par_id: dict[str, Avis],
    maintenant: datetime | None = None,
) -> list[dict]:
    maintenant = maintenant or datetime.now(timezone.utc)
    seuil_recent = maintenant - timedelta(days=JOURS_RECENTS)
    par_theme: dict[str, list[Probleme]] = defaultdict(list)
    for p in problemes:
        if p.avis_id in avis_par_id:
            par_theme[theme_de(p)].append(p)

    resultat = []
    for theme in themes:
        liste = par_theme.get(theme["id"], [])
        if not liste:
            continue
        # Une mention = un avis, même si l'avis évoque le thème plusieurs fois (on garde le plus grave).
        par_avis: dict[str, Probleme] = {}
        for p in liste:
            actuel = par_avis.get(p.avis_id)
            if actuel is None or (p.gravite, p.depart) > (actuel.gravite, actuel.depart):
                par_avis[p.avis_id] = p
        mentions = len(par_avis)
        concurrents = Counter(avis_par_id[i].concurrent for i in par_avis)
        sources = Counter(avis_par_id[i].source for i in par_avis)
        gravite_moyenne = round(sum(p.gravite for p in par_avis.values()) / mentions, 2)
        departs = sum(1 for p in par_avis.values() if p.depart)
        recentes = 0
        for i in par_avis:
            date = lire_date(avis_par_id[i].date)
            if date and date >= seuil_recent:
                recentes += 1
        resultat.append(
            {
                **theme,
                "mentions": mentions,
                "concurrents": dict(concurrents.most_common()),
                "sources": dict(sources.most_common()),
                "gravite_moyenne": gravite_moyenne,
                "departs": departs,
                "mentions_recentes": recentes,
                "priorite": priorite(mentions, gravite_moyenne, len(concurrents), departs),
                "formulations": [f for f, _ in Counter(p.probleme for p in liste).most_common(5)],
                "exemples": choisir_exemples(list(par_avis.values()), avis_par_id),
            }
        )
    resultat.sort(key=lambda s: (s["priorite"], s["mentions"]), reverse=True)
    return resultat
