"""Génération du rapport Markdown et de l'export CSV à partir de data/analyse.json."""

from __future__ import annotations

import csv
from pathlib import Path

from .categories import CATEGORIES
from .config import Config
from .stockage import lire_json

NOMS_SOURCES = {
    "google_play": "Google Play",
    "app_store": "App Store",
    "hackernews": "Hacker News",
    "reddit": "Reddit",
    "g2": "G2",
    "capterra": "Capterra",
    "trustpilot": "Trustpilot",
    "trustradius": "TrustRadius",
}
COUVERTURE = {
    "couvert": "✅ couvert",
    "partiel": "🟡 partiel",
    "non_couvert": "❌ non couvert",
    "inconnu": "❔ inconnu",
}
EFFORT = {"S": "faible (jours)", "M": "moyen (semaines)", "L": "élevé (mois)"}
THEMES_DETAILLES_MAX = 15


def nom_source(source: str) -> str:
    return NOMS_SOURCES.get(source, source)


def _cellule(texte) -> str:
    return str(texte).replace("|", "\\|").replace("\n", " ")


def _concurrents(theme: dict) -> str:
    return ", ".join(f"{nom} ({n})" for nom, n in theme["concurrents"].items())


def _etoiles(note) -> str:
    return f" · {note:g}★" if isinstance(note, (int, float)) else ""


def _citation(exemple: dict) -> str:
    texte = exemple["citation"].replace("\n", " ")
    origine = f"{exemple['concurrent']}, {nom_source(exemple['source'])}{_etoiles(exemple.get('note'))}"
    if exemple.get("url"):
        origine = f"[{origine}]({exemple['url']})"
    return f"> « {texte} »  \n> — {origine}"


def generer_markdown(analyse: dict) -> str:
    themes = analyse["themes"]
    avec_ia = analyse["methode"] == "claude"
    l: list[str] = []
    date = analyse["date"][:10]
    l.append(f"# Ce que les clients reprochent à tes concurrents — {date}")
    l.append("")
    methode = f"Claude (`{analyse['modele']}`)" if avec_ia else "mots-clés, sans IA"
    l.append(f"Produit : **{analyse['produit']}** · Méthode d'analyse : {methode}")
    l.append("")

    # ---------------------------------------------------------------- En bref
    nb_concurrents = len({c["concurrent"] for c in analyse["collecte"]})
    nb_sources = len({c["source"] for c in analyse["collecte"]})
    l.append("## En bref")
    l.append("")
    l.append(
        f"- **{analyse['nb_avis_total']}** avis collectés sur **{nb_concurrents}** concurrent(s) et "
        f"**{nb_sources}** source(s)."
    )
    l.append(
        f"- **{analyse['nb_avis_analyses']}** avis analysés (note ≤ {analyse['note_max']}/5 ou sans note), "
        f"**{analyse['nb_problemes']}** problèmes extraits, regroupés en **{len(themes)}** thèmes."
    )
    if analyse.get("synthese"):
        l.append("")
        l.append(analyse["synthese"].strip())
    l.append("")

    if not themes:
        l.append("Aucun problème trouvé dans les avis analysés.")
        l.append("")
        return "\n".join(l)

    # ---------------------------------------------------------------- Tableau principal
    l.append("## Les problèmes les plus importants")
    l.append("")
    l.append(
        "Classés par **priorité** = mentions × gravité moyenne × bonus si plusieurs concurrents sont touchés "
        "× bonus si des clients sont partis à cause du problème."
    )
    l.append("")
    entete = "| # | Problème | Mentions | Concurrents touchés | Gravité /3 | Départs | Priorité |"
    separateur = "|---|---|---:|---|---:|---:|---:|"
    if avec_ia:
        entete += " Ton produit |"
        separateur += "---|"
    l.append(entete)
    l.append(separateur)
    for rang, t in enumerate(themes, start=1):
        ligne = (
            f"| {rang} | {_cellule(t['titre'])} | {t['mentions']} | {_cellule(_concurrents(t))} | "
            f"{t['gravite_moyenne']:.1f} | {t['departs']} | {t['priorite']:g} |"
        )
        if avec_ia:
            reco = t.get("recommandation") or {}
            ligne += f" {COUVERTURE.get(reco.get('couverture'), '–')} |"
        l.append(ligne)
    l.append("")

    # ---------------------------------------------------------------- Quick wins
    quick_wins = [t for t in themes if (t.get("recommandation") or {}).get("quick_win")]
    if quick_wins:
        l.append("## Gains rapides (quick wins)")
        l.append("")
        for t in quick_wins:
            reco = t["recommandation"]
            l.append(
                f"- **{t['titre']}** ({t['mentions']} mentions, effort {EFFORT.get(reco.get('effort'), '?')}) : "
                f"{reco.get('recommandation', '')}"
            )
        l.append("")

    # ---------------------------------------------------------------- Détail
    l.append("## Détail par problème")
    l.append("")
    for rang, t in enumerate(themes[:THEMES_DETAILLES_MAX], start=1):
        l.append(f"### {rang}. {t['titre']}")
        l.append("")
        infos = [
            CATEGORIES.get(t.get("categorie"), t.get("categorie") or ""),
            f"{t['mentions']} mentions",
            f"dont {t['mentions_recentes']} sur les 6 derniers mois",
            f"gravité {t['gravite_moyenne']:.1f}/3",
            f"{t['departs']} départ(s)",
            "sources : " + ", ".join(f"{nom_source(s)} ({n})" for s, n in t["sources"].items()),
        ]
        l.append("*" + " · ".join(i for i in infos if i) + "*")
        l.append("")
        l.append(f"**Concurrents touchés :** {_concurrents(t)}")
        l.append("")
        if t.get("description"):
            l.append(t["description"])
            l.append("")
        # En mode mots-clés, la formulation est simplement le nom de la catégorie : rien à ajouter.
        if avec_ia and len(t.get("formulations") or []) > 1:
            l.append("**Formulations fréquentes :** " + " ; ".join(t["formulations"]))
            l.append("")
        if t["exemples"]:
            l.append("**Ce que disent les utilisateurs :**")
            l.append("")
            for exemple in t["exemples"][:3]:
                l.append(_citation(exemple))
                l.append("")
        reco = t.get("recommandation")
        if reco:
            l.append(
                f"**Ton produit :** {COUVERTURE.get(reco.get('couverture'), '–')} — {reco.get('justification', '')}"
            )
            l.append("")
            l.append(
                f"**Recommandation :** {reco.get('recommandation', '')} "
                f"*(effort {EFFORT.get(reco.get('effort'), '?')})*"
            )
            l.append("")
            if reco.get("argument_marketing"):
                l.append(f"**Argument marketing :** {reco['argument_marketing']}")
                l.append("")
    if len(themes) > THEMES_DETAILLES_MAX:
        l.append(f"*{len(themes) - THEMES_DETAILLES_MAX} autres thèmes figurent dans le tableau et dans themes.csv.*")
        l.append("")

    # ---------------------------------------------------------------- Par concurrent
    l.append("## Points faibles de chaque concurrent")
    l.append("")
    concurrents = sorted({c for t in themes for c in t["concurrents"]})
    for concurrent in concurrents:
        classement = sorted(
            ((t["concurrents"].get(concurrent, 0), t["titre"]) for t in themes if t["concurrents"].get(concurrent)),
            reverse=True,
        )
        l.append(f"### {concurrent}")
        l.append("")
        for n, titre in classement[:5]:
            l.append(f"1. {titre} — {n} mention(s)")
        l.append("")

    # ---------------------------------------------------------------- Données et méthode
    l.append("## Données collectées")
    l.append("")
    l.append("| Concurrent | Source | Avis collectés | Avis analysés |")
    l.append("|---|---|---:|---:|")
    for c in analyse["collecte"]:
        l.append(f"| {_cellule(c['concurrent'])} | {nom_source(c['source'])} | {c['collectes']} | {c['analyses']} |")
    l.append("")
    l.append("## Méthode et limites")
    l.append("")
    l.append(
        f"- Seuls les avis notés {analyse['note_max']}/5 ou moins, et les commentaires sans note (Reddit, Hacker News), "
        "sont analysés : ce sont eux qui décrivent les problèmes."
    )
    if avec_ia:
        l.append(
            "- Claude extrait chaque problème d'un avis avec une citation exacte, puis regroupe les problèmes "
            "semblables en thèmes. La couverture par ton produit est déduite de la description et des "
            "fonctionnalités indiquées dans la config : vérifie-la toi-même."
        )
    else:
        l.append(
            "- Analyse par mots-clés : rapide et gratuite, mais grossière (faux positifs, pas de regroupement "
            "fin). Relance sans `--sans-ia` pour une analyse par Claude."
        )
    l.append(
        "- Les avis publics ne sont pas un échantillon représentatif : ils surreprésentent les clients "
        "mécontents et les utilisateurs les plus actifs. Confirme les pistes en parlant à de vrais prospects."
    )
    l.append("")
    return "\n".join(l)


def ecrire_csv(analyse: dict, chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    colonnes = [
        "rang", "theme", "categorie", "mentions", "mentions_6_mois", "gravite_moyenne", "departs", "priorite",
        "concurrents", "couverture", "recommandation", "effort", "quick_win", "argument_marketing",
        "citation_1", "citation_2", "citation_3",
    ]
    with chemin.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig : lisible directement par Excel
        ecrivain = csv.writer(f, delimiter=";")
        ecrivain.writerow(colonnes)
        for rang, t in enumerate(analyse["themes"], start=1):
            reco = t.get("recommandation") or {}
            citations = [e["citation"] for e in t["exemples"][:3]] + ["", "", ""]
            ecrivain.writerow(
                [
                    rang, t["titre"], CATEGORIES.get(t.get("categorie"), ""), t["mentions"], t["mentions_recentes"],
                    t["gravite_moyenne"], t["departs"], t["priorite"], _concurrents(t), reco.get("couverture", ""),
                    reco.get("recommandation", ""), reco.get("effort", ""),
                    {True: "oui", False: "non"}.get(reco.get("quick_win"), ""), reco.get("argument_marketing", ""),
                    *citations[:3],
                ]
            )


def generer(cfg: Config) -> tuple[Path, Path]:
    analyse = lire_json(cfg.fichier_analyse)
    if analyse is None:
        raise RuntimeError("aucune analyse disponible : lance d'abord la commande « analyser ».")
    cfg.dossier_rapports.mkdir(parents=True, exist_ok=True)
    chemin_md = cfg.dossier_rapports / "rapport.md"
    chemin_csv = cfg.dossier_rapports / "themes.csv"
    chemin_md.write_text(generer_markdown(analyse), encoding="utf-8")
    ecrire_csv(analyse, chemin_csv)
    return chemin_md, chemin_csv
