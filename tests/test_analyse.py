import pytest

from conftest import FauxClient, FauxMessage, repondeur_standard, type_de_requete
from veille_avis.analyse import heuristique, lancer
from veille_avis.analyse.agregation import priorite
from veille_avis.analyse.claude import AnalyseurClaude, estimer_cout
from veille_avis.modeles import Avis
from veille_avis.stockage import fusionner_avis, lire_json, lire_jsonl


def _avis(i, texte, note=1.0, concurrent="OutilAlpha", titre=""):
    return Avis(id=f"test:{i}", concurrent=concurrent, source="capterra", texte=texte, note=note, titre=titre,
                date="2026-10-01")


def _base(cfg):
    avis = [
        _avis(1, "Le support ne répond jamais, je résilie mon abonnement."),
        _avis(2, "Aucun export comptable possible, très pénible.", note=2.0, concurrent="OutilBeta"),
        _avis(3, "Support aux abonnés absents et pas d'export non plus.", note=2.0),
        _avis(4, "Excellent produit, rien à dire de plus.", note=5.0),  # trop bien noté : ignoré
        _avis(5, "Interface agréable et équipe sympa.", note=None),  # sans plainte
    ]
    fusionner_avis(cfg.fichier_avis, avis)
    return avis


# ---------------------------------------------------------------- mots-clés


def test_heuristique_trouve_categories_et_depart():
    problemes = heuristique.extraire(_avis(1, "Trop cher. Le support ne répond pas, je résilie.", titre="Bof"))
    categories = {p.categorie for p in problemes}
    assert {"prix", "support"} <= categories
    assert all(p.depart for p in problemes)
    assert all(p.gravite == 3 for p in problemes)


def test_heuristique_prefere_le_corps_au_titre():
    problemes = heuristique.extraire(_avis(1, "Chaque page met dix secondes à s'afficher, c'est lent.", titre="Lent"))
    assert problemes[0].citation.startswith("Chaque page")


def test_heuristique_pas_de_faux_positif_sur_cherche():
    assert not [p for p in heuristique.extraire(_avis(1, "Je cherche encore mes marques.", note=3.0))
                if p.categorie == "prix"]


def test_lancer_sans_ia_produit_une_analyse(cfg):
    _base(cfg)
    resultat = lancer(cfg, sans_ia=True)
    assert resultat["methode"] == "heuristique"
    assert resultat["nb_avis_analyses"] == 4  # l'avis 5 étoiles est exclu
    titres = [t["titre"] for t in resultat["themes"]]
    assert "Support client" in titres
    assert lire_json(cfg.fichier_analyse)["themes"]


# ---------------------------------------------------------------- Claude (faux client)


def test_lancer_avec_claude_de_bout_en_bout(cfg):
    _base(cfg)
    client = FauxClient(repondeur_standard)
    resultat = lancer(cfg, oui=True, client=client)

    themes = {t["titre"]: t for t in resultat["themes"]}
    assert themes["Support injoignable"]["mentions"] == 2
    assert themes["Support injoignable"]["departs"] == 1
    assert themes["Export comptable absent"]["concurrents"] == {"OutilBeta": 1, "OutilAlpha": 1}
    assert themes["Support injoignable"]["recommandation"]["quick_win"] is True
    assert resultat["synthese"] == "Commence par le support."
    assert resultat["consommation"]["tokens_entree"] > 0

    # Chaque requête utilise le modèle configuré, l'effort demandé et le repli automatique.
    for params in client.appels:
        assert params["model"] == "claude-opus-5-5"
        assert params["fallbacks"] == "default"
        assert params["betas"] == ["server-side-fallback-2026-07-01"]
        assert "thinking" not in params
    efforts = {type_de_requete(p): p["output_config"]["effort"] for p in client.appels}
    assert efforts == {"resultats": "low", "themes": "high", "classement": "low", "synthese": "high"}


def test_les_avis_deja_analyses_ne_sont_pas_repayes(cfg):
    _base(cfg)
    lancer(cfg, oui=True, client=FauxClient(repondeur_standard))
    client = FauxClient(repondeur_standard)
    lancer(cfg, oui=True, client=client)
    assert "resultats" not in [type_de_requete(p) for p in client.appels]


def test_lot_tronque_est_redecoupe(cfg):
    avis = [_avis(i, f"Le support ne répond pas (cas {i}).") for i in range(6)]

    def repondeur(params):
        if type_de_requete(params) == "resultats" and params["messages"][0]["content"].count('"id"') > 2:
            return FauxMessage({}, stop_reason="max_tokens")
        return repondeur_standard(params)

    analyseur = AnalyseurClaude(cfg, FauxClient(repondeur))
    resultat = analyseur.extraire_lot(avis)
    assert set(resultat) == {a.id for a in avis}
    assert all(len(p) == 1 for p in resultat.values())


def test_avis_refuse_est_ignore_sans_bloquer(cfg):
    analyseur = AnalyseurClaude(cfg, FauxClient(lambda p: FauxMessage({}, stop_reason="refusal")))
    assert analyseur.extraire_lot([_avis(1, "texte quelconque assez long")]) == {"test:1": []}


def test_pas_de_repli_pour_un_modele_qui_ne_le_permet_pas(cfg):
    cfg.modele = "claude-haiku-5-5"
    client = FauxClient(repondeur_standard)
    AnalyseurClaude(cfg, client).extraire_lot([_avis(1, "Le support est nul.")])
    assert "fallbacks" not in client.appels[0] and "betas" not in client.appels[0]


def test_extraction_enregistree_au_fil_de_l_eau(cfg, tmp_path):
    analyseur = AnalyseurClaude(cfg, FauxClient(repondeur_standard))
    cache = tmp_path / "cache.jsonl"
    analyseur.extraire_tout([_avis(i, "Pas d'export du tout.") for i in range(25)], cache)
    lignes = lire_jsonl(cache)
    assert len(lignes) == 25
    assert lignes[0]["modele"] == "claude-opus-5-5"


# ---------------------------------------------------------------- calculs


def test_priorite_favorise_les_problemes_partages_et_les_departs():
    assert priorite(10, 2.0, 1, 0) == 20.0
    assert priorite(10, 2.0, 3, 0) == 40.0
    assert priorite(10, 2.0, 1, 5) == 30.0
    assert priorite(0, 2.0, 1, 0) == 0.0


def test_estimation_du_cout():
    estimation = estimer_cout([_avis(i, "x" * 350) for i in range(50)], "claude-opus-5-5", 25)
    assert estimation["lots"] == 2
    assert 0 < estimation["cout_usd"] < 5
    assert estimer_cout([], "modele-inconnu", 25)["cout_usd"] is None


@pytest.mark.parametrize("note,attendu", [(1.0, 3), (2.0, 2), (3.0, 1), (None, 2)])
def test_gravite_heuristique(note, attendu):
    assert heuristique.gravite(_avis(1, "x", note=note), depart=False) == attendu
