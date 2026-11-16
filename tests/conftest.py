import json
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from veille_avis.config import Concurrent, Config

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        produit_nom="MonSaaS",
        produit_description="Facturation pour indépendants.",
        fonctionnalites=["Relances automatiques"],
        concurrents=[Concurrent(nom="OutilAlpha"), Concurrent(nom="OutilBeta")],
        dossier_donnees=tmp_path / "data",
        dossier_rapports=tmp_path / "rapports",
        max_avis_par_source=50,
        taille_lot=10,
    )


class FauxMessage:
    def __init__(self, donnees, stop_reason="end_turn"):
        self.content = [SimpleNamespace(type="text", text=json.dumps(donnees, ensure_ascii=False))]
        self.stop_reason = stop_reason
        self.usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0)


class FauxClient:
    """Imite client.beta.messages.create / .stream ; `repondeur(params)` fabrique chaque réponse."""

    def __init__(self, repondeur):
        self.repondeur = repondeur
        self.appels: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create, stream=self._stream))

    def _create(self, **params):
        self.appels.append(params)
        return self.repondeur(params)

    @contextmanager
    def _stream(self, **params):
        self.appels.append(params)
        message = self.repondeur(params)
        yield SimpleNamespace(get_final_message=lambda: message)


def type_de_requete(params: dict) -> str:
    return next(iter(params["output_config"]["format"]["schema"]["properties"]))


def avis_envoyes(params: dict) -> list[dict]:
    contenu = params["messages"][0]["content"]
    partie = contenu[contenu.index("Avis à analyser") :]
    return json.loads(partie[partie.index("[") :])


def repondeur_standard(params: dict) -> FauxMessage:
    """Faux Claude : reconnaît « support » et « export » dans les avis."""
    genre = type_de_requete(params)
    contenu = params["messages"][0]["content"]
    if genre == "resultats":
        resultats = []
        for avis in avis_envoyes(params):
            texte = avis["texte"].lower()
            problemes = []
            if "support" in texte:
                problemes.append(
                    {"probleme": "Le support ne répond pas", "categorie": "support", "citation": avis["texte"][:60],
                     "gravite": 3, "depart": "résilie" in texte}
                )
            if "export" in texte:
                problemes.append(
                    {"probleme": "Pas d'export comptable", "categorie": "integrations", "citation": avis["texte"][:60],
                     "gravite": 2, "depart": False}
                )
            resultats.append({"id": avis["id"], "problemes": problemes})
        return FauxMessage({"resultats": resultats})
    if genre == "themes":
        return FauxMessage(
            {"themes": [
                {"titre": "Support injoignable", "description": "Les clients n'obtiennent pas d'aide.", "categorie": "support"},
                {"titre": "Export comptable absent", "description": "Pas d'export vers la compta.", "categorie": "integrations"},
            ]}
        )
    if genre == "classement":
        lignes = re.findall(r"^(\d+)\. (.+)$", contenu.split("Problèmes à classer :", 1)[1], flags=re.M)
        return FauxMessage(
            {"classement": [{"n": int(n), "theme": "T1" if "support" in t.lower() else "T2"} for n, t in lignes]}
        )
    if genre == "synthese":
        ids = params["output_config"]["format"]["schema"]["properties"]["recommandations"]["items"]["properties"][
            "theme_id"]["enum"]
        return FauxMessage(
            {"synthese": "Commence par le support.", "recommandations": [
                {"theme_id": i, "couverture": "non_couvert", "justification": "Absent de la liste.",
                 "recommandation": "Ajouter un chat.", "effort": "S", "quick_win": True,
                 "argument_marketing": "Un humain vous répond."} for i in ids
            ]}
        )
    raise AssertionError(f"requête inattendue : {genre}")
