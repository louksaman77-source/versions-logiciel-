import csv
import shutil

import pytest

from conftest import RACINE, FauxClient, repondeur_standard
from veille_avis.analyse import lancer
from veille_avis.cli import main
from veille_avis.config import ErreurConfig, charger_config
from veille_avis.modeles import Avis
from veille_avis.rapport import generer
from veille_avis.stockage import fusionner_avis


def test_rapport_avec_recommandations(cfg):
    fusionner_avis(
        cfg.fichier_avis,
        [
            Avis(id="a", concurrent="OutilAlpha", source="g2", texte="Le support | ne répond pas, je résilie.",
                 note=1.0, url="https://exemple.test/a"),
            Avis(id="b", concurrent="OutilBeta", source="google_play", texte="Pas d'export comptable.", note=2.0),
        ],
    )
    lancer(cfg, oui=True, client=FauxClient(repondeur_standard))
    chemin_md, chemin_csv = generer(cfg)
    texte = chemin_md.read_text(encoding="utf-8")
    for section in ("## En bref", "## Les problèmes les plus importants", "## Gains rapides",
                    "## Détail par problème", "## Points faibles de chaque concurrent", "## Méthode et limites"):
        assert section in texte
    assert "Commence par le support." in texte
    assert "❌ non couvert" in texte
    assert "[OutilAlpha, G2 · 1★](https://exemple.test/a)" in texte
    assert "Google Play" in texte

    with chemin_csv.open(encoding="utf-8-sig") as f:
        lignes = list(csv.reader(f, delimiter=";"))
    assert lignes[0][:3] == ["rang", "theme", "categorie"]
    assert len(lignes) == 3  # en-tête + 2 thèmes


def test_demo_complete_en_ligne_de_commande(tmp_path, capsys):
    dossier = tmp_path / "exemples"
    shutil.copytree(RACINE / "exemples", dossier, ignore=shutil.ignore_patterns("data", "rapports"))
    code = main(["--config", str(dossier / "config.demo.yaml"), "tout", "--sans-ia"])
    assert code == 0
    rapport = (dossier / "rapports" / "rapport.md").read_text(encoding="utf-8")
    assert "OutilAlpha" in rapport and "OutilBeta" in rapport
    assert "Support client" in rapport
    sortie = capsys.readouterr().out
    assert "20 nouveaux avis" in sortie


def test_config_exemple_est_valide():
    cfg = charger_config(RACINE / "config.example.yaml")
    assert cfg.concurrents[0].google_play == "com.exemple.app"
    assert cfg.concurrents[0].fichiers[0].source == "g2"
    assert cfg.modele == "claude-opus-5-5"


def test_config_absente_ou_invalide(tmp_path):
    with pytest.raises(ErreurConfig, match="config.example.yaml"):
        charger_config(tmp_path / "absent.yaml")
    mauvais = tmp_path / "c.yaml"
    mauvais.write_text("concurrents: []\n")
    with pytest.raises(ErreurConfig, match="au moins un concurrent"):
        charger_config(mauvais)
    mauvais.write_text("concurrents: [{nom: A}]\nanalyse: {effort_synthese: enorme}\n")
    with pytest.raises(ErreurConfig, match="effort_synthese"):
        charger_config(mauvais)


def test_cli_message_clair_si_rien_n_est_collecte(tmp_path, capsys):
    config = tmp_path / "c.yaml"
    config.write_text("concurrents: [{nom: A}]\n")
    assert main(["--config", str(config), "analyser", "--sans-ia"]) == 1
    assert "collecter" in capsys.readouterr().out
