import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from veille_avis.collecteurs import app_store, fichiers, google_play, hackernews, reddit
from veille_avis.config import Concurrent, SourceFichier


class FausseReponse:
    def __init__(self, donnees, status_code=200):
        self._donnees = donnees
        self.status_code = status_code

    def json(self):
        return self._donnees

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FausseSession:
    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []

    def get(self, url, params=None, timeout=None):
        self.appels.append((url, params))
        return self.reponses.pop(0) if self.reponses else FausseReponse({}, 404)


# ---------------------------------------------------------------- Google Play


def test_google_play_convertit_un_avis():
    brut = {"reviewId": "gp1", "content": " Trop lent ", "score": 2, "at": datetime(2026, 10, 1, 12, 0)}
    avis = google_play.convertir(brut, "OutilAlpha", "com.alpha")
    assert avis.id == "google_play:outilalpha:gp1"
    assert avis.texte == "Trop lent"
    assert avis.note == 2.0
    assert avis.date.startswith("2026-10-01")
    assert "com.alpha" in avis.url and "gp1" in avis.url


def test_google_play_ne_demande_que_les_notes_basses(cfg, monkeypatch):
    import google_play_scraper

    appels = []

    def faux_reviews(app_id, lang, country, sort, count, filter_score_with):
        appels.append(filter_score_with)
        return [{"reviewId": f"r{filter_score_with}", "content": "bug", "score": filter_score_with, "at": None}], None

    monkeypatch.setattr(google_play_scraper, "reviews", faux_reviews)
    avis = google_play.collecter(Concurrent(nom="A", google_play="com.a"), cfg)
    assert appels == [1, 2, 3]
    assert [a.note for a in avis] == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------- App Store


def _entree(id_, note, texte="Ça plante"):
    return {
        "id": {"label": id_},
        "title": {"label": "Titre"},
        "content": {"label": texte, "attributes": {"type": "text"}},
        "im:rating": {"label": str(note)},
        "updated": {"label": "2026-09-01T10:00:00-07:00"},
    }


def test_app_store_lit_le_flux_et_filtre_les_notes(cfg):
    page1 = {"feed": {"entry": [{"im:name": {"label": "Fiche de l'app"}}, _entree("1", 1), _entree("2", 5)]}}
    page2 = {"feed": {"entry": _entree("3", 3)}}  # une seule entrée → objet, pas liste
    page3 = {"feed": {}}
    session = FausseSession([FausseReponse(page1), FausseReponse(page2), FausseReponse(page3)])
    avis = app_store.collecter(Concurrent(nom="A", app_store="123"), cfg, session=session)
    assert [a.id for a in avis] == ["app_store:a:1", "app_store:a:3"]
    assert all(a.note <= cfg.note_max for a in avis)
    assert "/fr/rss/customerreviews/page=1/id=123/" in session.appels[0][0]


# ---------------------------------------------------------------- Hacker News


def test_hackernews_nettoie_et_filtre(cfg):
    page = {
        "nbPages": 1,
        "hits": [
            {"objectID": "11", "comment_text": "<p>We left Notion&#x27;s API</p>", "created_at": "2026-01-01T00:00:00Z",
             "story_title": "Ask HN"},
            {"objectID": "12", "comment_text": "Notional value is fine", "created_at": "2026-01-02T00:00:00Z"},
        ],
    }
    session = FausseSession([FausseReponse(page)])
    avis = hackernews.collecter(Concurrent(nom="Notion", hackernews="Notion"), cfg, session=session)
    assert len(avis) == 1
    assert avis[0].texte == "We left Notion's API"
    assert avis[0].url == "https://news.ycombinator.com/item?id=11"
    assert avis[0].titre == "Discussion : Ask HN"


# ---------------------------------------------------------------- Reddit


def test_reddit_garde_les_posts_et_les_commentaires_qui_citent_le_concurrent(cfg):
    commentaires = [
        SimpleNamespace(id="c1", body="OutilAlpha support is awful", permalink="/r/SaaS/c1", created_utc=1.7e9),
        SimpleNamespace(id="c2", body="unrelated", permalink="/r/SaaS/c2", created_utc=1.7e9),
    ]
    post = SimpleNamespace(
        id="p1", title="Alternatives to OutilAlpha?", selftext="Too expensive", permalink="/r/SaaS/p1",
        created_utc=1.7e9,
        comments=SimpleNamespace(replace_more=lambda limit: None, list=lambda: commentaires),
    )
    recherches = []

    class FauxSubreddit:
        def search(self, requete, sort, limit):
            recherches.append((requete, sort, limit))
            return [post]

    faux_reddit = SimpleNamespace(subreddit=lambda nom: FauxSubreddit())
    concurrent = Concurrent(nom="OutilAlpha", reddit={"subreddits": ["SaaS"]})
    avis = reddit.collecter_depuis(faux_reddit, concurrent, cfg)
    assert [a.id for a in avis] == ["reddit:outilalpha:t3_p1", "reddit:outilalpha:t1_c1"]
    assert recherches == [('"OutilAlpha"', "new", 50)]


def test_reddit_sans_identifiants_donne_un_message_clair(cfg, monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="REDDIT_CLIENT_ID"):
        reddit.collecter(Concurrent(nom="A", reddit={}), cfg)


# ---------------------------------------------------------------- Fichiers


def test_import_csv_detecte_les_colonnes(tmp_path):
    chemin = tmp_path / "g2.csv"
    chemin.write_text(
        'Review ID;Rating;Title;Review Text;Date\nx1;"4,5";Bien;"Ligne 1\nLigne 2";2026-01-01\nx2;2;;;2026-01-02\n',
        encoding="utf-8",
    )
    avis = fichiers.importer(SourceFichier(chemin=chemin, source="g2"), "OutilAlpha")
    assert len(avis) == 1  # la ligne sans texte est ignorée
    assert avis[0].id == "g2:outilalpha:x1"
    assert avis[0].texte == "Ligne 1\nLigne 2"
    assert avis[0].note == 4.5
    assert avis[0].titre == "Bien"


def test_import_json_imbrique_avec_echelle_sur_10(tmp_path):
    chemin = tmp_path / "export.json"
    chemin.write_text(json.dumps({"items": [{"rating": {"value": 4}, "pros": "Rapide", "cons": "Cher"}]}))
    source = SourceFichier(chemin=chemin, colonnes={"texte": ["cons", "pros"]}, echelle_note=10)
    avis = fichiers.importer(source, "OutilBeta")
    assert avis[0].texte == "Cher\nRapide"
    assert avis[0].note == 2.0


def test_import_sans_colonne_texte_explique_quoi_faire(tmp_path):
    chemin = tmp_path / "x.jsonl"
    chemin.write_text('{"foo": "bar"}\n')
    with pytest.raises(ValueError, match="colonnes"):
        fichiers.importer(SourceFichier(chemin=chemin), "A")
