"""Posts et commentaires Reddit qui citent un concurrent, via l'API officielle (bibliothèque PRAW).

Nécessite REDDIT_CLIENT_ID et REDDIT_CLIENT_SECRET (voir le README).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from ..config import Concurrent, Config
from ..modeles import Avis
from .hackernews import mentionne

COMMENTAIRES_MAX_PAR_POST = 200


def collecter(concurrent: Concurrent, cfg: Config) -> list[Avis]:
    id_client = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not id_client or not secret:
        raise RuntimeError(
            "identifiants Reddit manquants : renseigne REDDIT_CLIENT_ID et REDDIT_CLIENT_SECRET dans .env (voir README)"
        )
    import praw

    reddit = praw.Reddit(
        client_id=id_client,
        client_secret=secret,
        user_agent=os.environ.get("REDDIT_USER_AGENT") or "veille-avis/0.1 (analyse d'avis)",
    )
    reddit.read_only = True
    return collecter_depuis(reddit, concurrent, cfg)


def _date(horodatage) -> str | None:
    if horodatage is None:
        return None
    return datetime.fromtimestamp(float(horodatage), tz=timezone.utc).isoformat()


def collecter_depuis(reddit, concurrent: Concurrent, cfg: Config) -> list[Avis]:
    reglages = concurrent.reddit or {}
    requete = reglages.get("requete") or f'"{concurrent.nom}"'
    mot_cle = reglages.get("mot_cle") or concurrent.nom
    subreddits = reglages.get("subreddits") or ["all"]
    max_posts = int(reglages.get("max_posts") or 50)

    resultat: list[Avis] = []
    for post in reddit.subreddit("+".join(subreddits)).search(requete, sort="new", limit=max_posts):
        corps = (post.selftext or "").strip()
        resultat.append(
            Avis(
                id=Avis.construire_id("reddit", concurrent.nom, f"t3_{post.id}"),
                concurrent=concurrent.nom,
                source="reddit",
                titre=post.title or "",
                texte=corps or (post.title or ""),
                date=_date(getattr(post, "created_utc", None)),
                url=f"https://www.reddit.com{post.permalink}",
            )
        )
        post.comments.replace_more(limit=0)
        for commentaire in post.comments.list()[:COMMENTAIRES_MAX_PAR_POST]:
            corps = (getattr(commentaire, "body", "") or "").strip()
            if corps and mentionne(corps, mot_cle):
                resultat.append(
                    Avis(
                        id=Avis.construire_id("reddit", concurrent.nom, f"t1_{commentaire.id}"),
                        concurrent=concurrent.nom,
                        source="reddit",
                        titre=f"Discussion : {post.title}" if post.title else "",
                        texte=corps,
                        date=_date(getattr(commentaire, "created_utc", None)),
                        url=f"https://www.reddit.com{commentaire.permalink}",
                    )
                )
        if len(resultat) >= cfg.max_avis_par_source:
            break
    return resultat[: cfg.max_avis_par_source]
