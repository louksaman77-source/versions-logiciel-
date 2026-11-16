"""Catégories de problèmes, partagées par l'analyse Claude et l'analyse par mots-clés.

Dans les listes de mots-clés, un « * » final veut dire « commence par » (ex. « rembours* »
trouve « remboursement »). Sans « * », le mot doit apparaître en entier. Les accents et les
majuscules sont ignorés.
"""

from __future__ import annotations

import re

from .modeles import sans_accents

CATEGORIES: dict[str, str] = {
    "prix": "Prix, facturation & résiliation",
    "support": "Support client",
    "bugs": "Bugs & fiabilité",
    "performance": "Lenteur & performance",
    "ergonomie": "Ergonomie & prise en main",
    "fonctionnalites": "Fonctionnalité manquante ou limitée",
    "integrations": "Intégrations, import & export",
    "donnees": "Données, sécurité & confidentialité",
    "mobile": "Application mobile",
    "autre": "Autre",
}

MOTS_CLES: dict[str, list[str]] = {
    "prix": [
        "prix", "cher", "chere", "chers", "tarif*", "abonnement*", "payant*", "facturation", "rembours*",
        "resiliation", "desabonn*", "hors de prix", "trop couteux", "augmentation",
        "price*", "pricing", "expensive", "overpriced", "subscription*", "charged", "refund*",
        "billing", "billed", "cancellation", "cost*", "fee", "fees", "paywall",
    ],
    "support": [
        "support", "service client", "sav", "assistance", "ticket*", "joindre", "injoignable",
        "aucune reponse", "pas de reponse", "personne ne repond", "ne repond",
        "customer service", "customer support", "no response", "no reply", "never responded",
        "help desk", "helpdesk", "unresponsive",
    ],
    "bugs": [
        "bug*", "bogue*", "beug*", "plant*", "crash*", "erreur*", "panne*", "ne fonctionne pas",
        "ne marche pas", "marche pas", "fonctionne plus", "marche plus", "fige", "bloque", "bloquee",
        "buggy", "broken", "doesn't work", "does not work", "not working", "stopped working",
        "glitch*", "error*", "freez*",
    ],
    "performance": [
        "lent", "lente", "lents", "lentes", "lenteur*", "rame", "ramer", "temps de chargement", "chargement",
        "slow*", "lag*", "loading", "takes forever", "performance*",
    ],
    "ergonomie": [
        "complique*", "complexe*", "intuiti*", "ergonom*", "interface", "confus*", "pas clair",
        "difficile", "prise en main", "on s'y perd", "usine a gaz",
        "confusing", "complicated", "hard to use", "difficult", "clunky", "unintuitive",
        "learning curve", "ui", "ux", "user interface",
    ],
    "fonctionnalites": [
        "il manque", "manque*", "pas possible", "impossible de", "j'aimerais", "ne permet pas",
        "aucune option", "pas d'option", "fonctionnalite*", "limite*",
        "missing", "lack*", "i wish", "wish it", "no way to", "can't", "cannot", "feature*",
        "doesn't support", "does not support", "limited",
    ],
    "integrations": [
        "integration*", "synchro*", "sync*", "import*", "export*", "api", "connecteur*", "zapier",
        "csv", "excel", "connect*", "plugin*",
    ],
    "donnees": [
        "donnees", "perdu", "perte", "securite", "confidentialite", "rgpd", "pirate*", "fuite*",
        "data", "lost", "security", "privacy", "gdpr", "hacked", "breach*", "leak*",
    ],
    "mobile": [
        "application mobile", "appli", "android", "iphone", "ipad", "ios", "smartphone",
        "mobile app", "mobile",
    ],
}

# Signes que l'auteur a quitté le produit ou s'apprête à le faire
MOTS_DEPART = [
    "je change", "j'ai change", "je quitte", "j'ai quitte", "desinstall*", "resilie*", "je resilie",
    "je suis passe a", "nous sommes passes a", "on est passe a", "je suis parti*",
    "je cherche une alternative", "a fuir", "je pars",
    "switched", "switching", "uninstall*", "cancelled", "canceled", "moving to", "moved to",
    "leaving", "looking for an alternative", "looking for alternatives", "migrated to",
]


def _motif(mots: list[str]) -> re.Pattern:
    morceaux = []
    for mot in mots:
        mot = sans_accents(mot.lower())
        if mot.endswith("*"):
            morceaux.append(re.escape(mot[:-1]) + r"[a-z0-9']*")
        else:
            morceaux.append(re.escape(mot) + r"(?![a-z0-9])")
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(morceaux) + ")")


MOTIFS: dict[str, re.Pattern] = {cat: _motif(mots) for cat, mots in MOTS_CLES.items()}
MOTIF_DEPART: re.Pattern = _motif(MOTS_DEPART)


def normaliser(texte: str) -> str:
    return sans_accents(texte.lower()).replace("’", "'")
