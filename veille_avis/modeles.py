"""Structures de données partagées par tout le pipeline."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone


def sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c))


def slug(texte: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", sans_accents(texte).lower()).strip("-")
    return s or "x"


def empreinte(texte: str) -> str:
    return hashlib.sha1(texte.encode("utf-8")).hexdigest()[:16]


def lire_date(valeur: str | None) -> datetime | None:
    """Lit une date ISO (ou qui commence par AAAA-MM-JJ). Renvoie None si illisible."""
    if not valeur:
        return None
    texte = str(valeur).strip()
    for candidat in (texte, texte.replace("Z", "+00:00"), texte[:19], texte[:10]):
        try:
            d = datetime.fromisoformat(candidat)
        except ValueError:
            continue
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


@dataclass
class Avis:
    """Un avis ou commentaire public, quelle que soit sa source."""

    id: str
    concurrent: str
    source: str
    texte: str
    note: float | None = None  # ramenée sur 5 ; None quand la source n'a pas de note (Reddit, HN)
    titre: str = ""
    date: str | None = None  # ISO 8601
    url: str | None = None

    @staticmethod
    def construire_id(source: str, concurrent: str, id_natif: str) -> str:
        return f"{source}:{slug(concurrent)}:{id_natif}"

    def texte_complet(self) -> str:
        if self.titre and self.titre.strip() and self.titre.strip() not in self.texte:
            return f"{self.titre.strip()}\n{self.texte}"
        return self.texte

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Avis":
        noms = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in noms})


@dataclass
class Probleme:
    """Un problème précis extrait d'un avis."""

    avis_id: str
    probleme: str  # formulation courte et générique, en français
    categorie: str  # clé de veille_avis.categories.CATEGORIES
    citation: str  # extrait exact de l'avis
    gravite: int  # 1 = gêne mineure, 2 = frustration, 3 = bloquant / pousse à partir
    depart: bool  # l'auteur dit avoir quitté le produit ou chercher une alternative

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Probleme":
        noms = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in noms})


def normaliser_probleme(texte: str) -> str:
    """Clé de regroupement des formulations identiques."""
    return re.sub(r"\s+", " ", texte.strip().lower().rstrip("."))
