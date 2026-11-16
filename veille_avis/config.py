"""Chargement et validation du fichier de configuration YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

EFFORTS = ("low", "medium", "high", "xhigh", "max")


class ErreurConfig(Exception):
    pass


@dataclass
class SourceFichier:
    """Un export CSV / JSON / JSONL (G2, Capterra, Trustpilot, sondage...)."""

    chemin: Path
    source: str = "import"
    colonnes: dict = field(default_factory=dict)  # ex. {"texte": ["cons"], "note": "rating"}
    echelle_note: float = 5.0


@dataclass
class Concurrent:
    nom: str
    google_play: str | None = None  # identifiant de l'app (après ?id= dans l'URL Play Store)
    app_store: str | None = None  # identifiant numérique (après /id dans l'URL App Store)
    hackernews: str | None = None  # mot-clé recherché dans les commentaires Hacker News
    reddit: dict | None = None  # {"requete": ..., "subreddits": [...], "mot_cle": ..., "max_posts": 50}
    fichiers: list[SourceFichier] = field(default_factory=list)
    pays: str | None = None  # remplace collecte.pays pour ce concurrent
    langue: str | None = None  # remplace collecte.langue pour ce concurrent


@dataclass
class Config:
    produit_nom: str
    produit_description: str
    fonctionnalites: list[str]
    concurrents: list[Concurrent]
    dossier_donnees: Path
    dossier_rapports: Path
    pays: str = "fr"
    langue: str = "fr"
    max_avis_par_source: int = 200
    modele: str = "claude-opus-5-5"
    note_max: int = 3
    taille_lot: int = 25
    effort_extraction: str = "low"
    effort_synthese: str = "high"
    max_themes: int = 25

    @property
    def fichier_avis(self) -> Path:
        return self.dossier_donnees / "avis.jsonl"

    @property
    def fichier_analyse(self) -> Path:
        return self.dossier_donnees / "analyse.json"

    def fichier_extractions(self, methode: str) -> Path:
        return self.dossier_donnees / f"extractions_{methode}.jsonl"


def _texte(valeur, nom: str, defaut: str | None = None) -> str | None:
    if valeur is None:
        return defaut
    if not isinstance(valeur, (str, int)):
        raise ErreurConfig(f"« {nom} » doit être un texte.")
    return str(valeur).strip() or defaut


def _entier(valeur, nom: str, defaut: int, minimum: int = 1) -> int:
    if valeur is None:
        return defaut
    try:
        n = int(valeur)
    except (TypeError, ValueError):
        raise ErreurConfig(f"« {nom} » doit être un nombre entier.") from None
    if n < minimum:
        raise ErreurConfig(f"« {nom} » doit valoir au moins {minimum}.")
    return n


def _effort(valeur, nom: str, defaut: str) -> str:
    e = _texte(valeur, nom, defaut)
    if e not in EFFORTS:
        raise ErreurConfig(f"« {nom} » doit être l'une de ces valeurs : {', '.join(EFFORTS)}.")
    return e


def _fichiers(brut, base: Path, nom_concurrent: str) -> list[SourceFichier]:
    if brut is None:
        return []
    if not isinstance(brut, list):
        raise ErreurConfig(f"« fichiers » de {nom_concurrent} doit être une liste.")
    resultat = []
    for element in brut:
        if isinstance(element, str):
            element = {"chemin": element}
        if not isinstance(element, dict) or not element.get("chemin"):
            raise ErreurConfig(f"Chaque fichier de {nom_concurrent} doit avoir un « chemin ».")
        chemin = Path(element["chemin"])
        if not chemin.is_absolute():
            chemin = base / chemin
        colonnes = element.get("colonnes") or {}
        if not isinstance(colonnes, dict):
            raise ErreurConfig(f"« colonnes » ({chemin.name}) doit être un dictionnaire.")
        try:
            echelle = float(element.get("echelle_note", 5))
        except (TypeError, ValueError):
            raise ErreurConfig(f"« echelle_note » ({chemin.name}) doit être un nombre.") from None
        resultat.append(
            SourceFichier(
                chemin=chemin,
                source=_texte(element.get("source"), "source", "import"),
                colonnes=colonnes,
                echelle_note=echelle,
            )
        )
    return resultat


def charger_config(chemin: str | Path) -> Config:
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurConfig(
            f"Fichier de configuration introuvable : {chemin}\n"
            "Copie config.example.yaml en config.yaml puis remplis-le."
        )
    try:
        brut = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ErreurConfig(f"Le fichier {chemin} n'est pas un YAML valide : {e}") from None
    if not isinstance(brut, dict):
        raise ErreurConfig(f"Le fichier {chemin} doit contenir des sections (mon_produit, concurrents...).")

    base = chemin.resolve().parent
    produit = brut.get("mon_produit") or {}
    collecte = brut.get("collecte") or {}
    analyse = brut.get("analyse") or {}
    dossiers = brut.get("dossiers") or {}

    fonctionnalites = produit.get("fonctionnalites") or []
    if not isinstance(fonctionnalites, list):
        raise ErreurConfig("« mon_produit.fonctionnalites » doit être une liste.")

    concurrents = []
    for i, c in enumerate(brut.get("concurrents") or [], start=1):
        if not isinstance(c, dict) or not c.get("nom"):
            raise ErreurConfig(f"Le concurrent n°{i} doit avoir un « nom ».")
        nom = str(c["nom"]).strip()
        reddit = c.get("reddit")
        if isinstance(reddit, str):
            reddit = {"requete": reddit}
        if reddit is not None and not isinstance(reddit, dict):
            raise ErreurConfig(f"« reddit » de {nom} doit être un texte ou un dictionnaire.")
        concurrents.append(
            Concurrent(
                nom=nom,
                google_play=_texte(c.get("google_play"), "google_play"),
                app_store=_texte(c.get("app_store"), "app_store"),
                hackernews=_texte(c.get("hackernews"), "hackernews"),
                reddit=reddit,
                fichiers=_fichiers(c.get("fichiers"), base, nom),
                pays=_texte(c.get("pays"), "pays"),
                langue=_texte(c.get("langue"), "langue"),
            )
        )
    if not concurrents:
        raise ErreurConfig("Ajoute au moins un concurrent dans la section « concurrents ».")

    def dossier(cle: str, defaut: str) -> Path:
        p = Path(dossiers.get(cle) or defaut)
        return p if p.is_absolute() else base / p

    return Config(
        produit_nom=_texte(produit.get("nom"), "mon_produit.nom", "Mon produit"),
        produit_description=_texte(produit.get("description"), "mon_produit.description", ""),
        fonctionnalites=[str(f).strip() for f in fonctionnalites if str(f).strip()],
        concurrents=concurrents,
        dossier_donnees=dossier("donnees", "data"),
        dossier_rapports=dossier("rapports", "rapports"),
        pays=_texte(collecte.get("pays"), "collecte.pays", "fr"),
        langue=_texte(collecte.get("langue"), "collecte.langue", "fr"),
        max_avis_par_source=_entier(collecte.get("max_avis_par_source"), "collecte.max_avis_par_source", 200),
        modele=_texte(analyse.get("modele"), "analyse.modele", "claude-opus-5-5"),
        note_max=min(5, _entier(analyse.get("note_max"), "analyse.note_max", 3)),
        taille_lot=_entier(analyse.get("taille_lot"), "analyse.taille_lot", 25),
        effort_extraction=_effort(analyse.get("effort_extraction"), "analyse.effort_extraction", "low"),
        effort_synthese=_effort(analyse.get("effort_synthese"), "analyse.effort_synthese", "high"),
        max_themes=_entier(analyse.get("max_themes"), "analyse.max_themes", 25, minimum=3),
    )


def charger_env(chemin: str | Path = ".env") -> None:
    """Charge un fichier .env simple (CLE=valeur) sans écraser les variables déjà définies."""
    chemin = Path(chemin)
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        cle = cle.strip().removeprefix("export ").strip()
        valeur = valeur.strip().strip('"').strip("'")
        if cle and valeur and cle not in os.environ:
            os.environ[cle] = valeur
