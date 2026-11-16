"""Étape d'analyse : extraction des problèmes, regroupement en thèmes, statistiques, recommandations."""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone

from ..config import Config
from ..modeles import Avis, Probleme, normaliser_probleme
from ..stockage import ajouter_jsonl, ecrire_json, lire_avis, lire_jsonl
from . import agregation, heuristique

LONGUEUR_MIN = 15  # en dessous, un avis (« nul », « bof ») n'apprend rien


class AnalyseAnnulee(Exception):
    pass


def avis_a_analyser(avis: list[Avis], cfg: Config) -> list[Avis]:
    return [
        a for a in avis if len(a.texte.strip()) >= LONGUEUR_MIN and (a.note is None or a.note <= cfg.note_max)
    ]


def _confirmer(question: str) -> bool:
    if not sys.stdin.isatty():
        return True
    reponse = input(f"{question} [o/N] ").strip().lower()
    return reponse in ("o", "oui", "y", "yes")


def _bilan_collecte(tous: list[Avis], candidats: list[Avis], analyses: set[str]) -> list[dict]:
    collectes = Counter((a.concurrent, a.source) for a in tous)
    retenus = Counter((a.concurrent, a.source) for a in candidats if a.id in analyses)
    return [
        {"concurrent": c, "source": s, "collectes": n, "analyses": retenus.get((c, s), 0)}
        for (c, s), n in sorted(collectes.items())
    ]


def lancer(cfg: Config, sans_ia: bool = False, oui: bool = False, limite: int | None = None, client=None) -> dict:
    tous = lire_avis(cfg.fichier_avis)
    if not tous:
        raise RuntimeError("aucun avis en base : lance d'abord la commande « collecter ».")
    avis_par_id = {a.id: a for a in tous}
    candidats = avis_a_analyser(tous, cfg)
    methode = "heuristique" if sans_ia else "claude"
    fichier_cache = cfg.fichier_extractions(methode)
    deja = {d["avis_id"] for d in lire_jsonl(fichier_cache)}
    a_faire = [a for a in candidats if a.id not in deja]
    if limite is not None:
        a_faire = a_faire[:limite]

    deja_retenus = sum(1 for a in candidats if a.id in deja)
    print(
        f"{len(tous)} avis en base · {len(candidats)} retenus (note ≤ {cfg.note_max} ou sans note) · "
        f"{deja_retenus} déjà analysés · {len(a_faire)} à analyser"
    )

    analyseur = None
    if sans_ia:
        print("Analyse par mots-clés (sans IA)…")
        ajouter_jsonl(
            fichier_cache,
            [{"avis_id": a.id, "problemes": [p.to_dict() for p in heuristique.extraire(a)]} for a in a_faire],
        )
    else:
        from .claude import AnalyseurClaude, estimer_cout

        analyseur = AnalyseurClaude(cfg, client)
        if a_faire:
            estimation = estimer_cout(a_faire, cfg.modele, cfg.taille_lot)
            cout = f"≈ {estimation['cout_usd']:.2f} $" if estimation["cout_usd"] is not None else "inconnu pour ce modèle"
            print(
                f"Analyse avec {cfg.modele} : {estimation['avis']} avis en {estimation['lots']} lot(s) · "
                f"coût estimé {cout} (ordre de grandeur, à vérifier dans ta console Anthropic)"
            )
            if not oui and not _confirmer("Lancer l'analyse ?"):
                raise AnalyseAnnulee()
            analyseur.extraire_tout(a_faire, fichier_cache)

    # Toutes les extractions disponibles pour les avis retenus (celles d'avant + celles d'aujourd'hui)
    extractions = {d["avis_id"]: d for d in lire_jsonl(fichier_cache)}
    ids_candidats = {a.id for a in candidats}
    analyses = {i for i in extractions if i in ids_candidats}
    problemes = [Probleme.from_dict(p) for i in analyses for p in extractions[i]["problemes"]]
    print(f"{len(problemes)} problèmes extraits de {len(analyses)} avis.")

    synthese = ""
    recommandations: dict[str, dict] = {}
    if sans_ia:
        themes = heuristique.themes()
        stats = agregation.statistiques(themes, problemes, lambda p: p.categorie, avis_par_id)
    else:
        print("Regroupement des problèmes en thèmes…")
        themes, classement = analyseur.construire_themes(problemes)
        stats = agregation.statistiques(
            themes, problemes, lambda p: classement.get(normaliser_probleme(p.probleme), "AUTRE"), avis_par_id
        )
        if stats:
            print("Rédaction des recommandations…")
            from .claude import ReponseInutilisable

            try:
                reponse = analyseur.recommander(stats)
                synthese = reponse.get("synthese", "")
                recommandations = {r["theme_id"]: r for r in reponse.get("recommandations") or []}
            except ReponseInutilisable as erreur:
                print(f"  ⚠ recommandations indisponibles ({erreur}) ; le rapport sera produit sans elles.")

    for s in stats:
        if s["id"] in recommandations:
            s["recommandation"] = recommandations[s["id"]]

    resultat = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methode": methode,
        "modele": cfg.modele if not sans_ia else None,
        "produit": cfg.produit_nom,
        "note_max": cfg.note_max,
        "nb_avis_total": len(tous),
        "nb_avis_analyses": len(analyses),
        "nb_problemes": len(problemes),
        "collecte": _bilan_collecte(tous, candidats, analyses),
        "synthese": synthese,
        "themes": stats,
    }
    if analyseur is not None:
        resultat["consommation"] = {
            "tokens_entree": analyseur.tokens_entree,
            "tokens_sortie": analyseur.tokens_sortie,
            "cout_usd": analyseur.cout_reel(),
        }
        cout = analyseur.cout_reel()
        print(
            f"Consommation de cette exécution : {analyseur.tokens_entree:,} tokens en entrée, "
            f"{analyseur.tokens_sortie:,} en sortie".replace(",", " ")
            + (f" (≈ {cout:.2f} $)" if cout is not None else "")
        )
    ecrire_json(cfg.fichier_analyse, resultat)
    return resultat
