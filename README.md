# Veille avis : ce que les clients reprochent à tes concurrents

Ce pipeline récupère les avis publics laissés sur les produits de tes concurrents, en extrait les problèmes avec Claude, les regroupe par thème et les classe par priorité. Il produit un rapport qui dit :

- quels problèmes reviennent le plus souvent, à quel point ils sont graves et chez quels concurrents ;
- si ton SaaS règle déjà chaque problème (d'après la description que tu en donnes) ;
- quoi ajouter ou ajuster en premier, en signalant les gains rapides ;
- un argument marketing par problème, tiré des mots des utilisateurs.

```
 collecter                         analyser                                   rapport
┌─────────────────┐   avis    ┌──────────────────────────────────┐   ┌──────────────────────────┐
│ Google Play     │──────────▶│ 1. Claude lit chaque avis et     │──▶│ rapports/rapport.md      │
│ App Store       │ data/     │    extrait les problèmes         │   │ rapports/themes.csv      │
│ Hacker News     │ avis.jsonl│ 2. regroupe en thèmes            │   │  (s'ouvre dans Excel)    │
│ Reddit          │           │ 3. calcule fréquence, gravité,   │   └──────────────────────────┘
│ CSV/JSON (G2,   │           │    départs, priorité             │
│ Capterra,       │           │ 4. compare avec ton produit et   │
│ Trustpilot...)  │           │    recommande                    │
└─────────────────┘           └──────────────────────────────────┘
```

## Essai en une minute, sans clé ni connexion

Le dossier `exemples/` contient deux concurrents **fictifs** et une vingtaine d'avis **fictifs**.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python -m veille_avis --config exemples/config.demo.yaml tout --sans-ia
```

Le rapport est créé dans `exemples/rapports/rapport.md`. L'option `--sans-ia` utilise une analyse par mots-clés, gratuite mais grossière. Le vrai travail se fait avec Claude.

## Installation

Il faut Python 3.10 ou plus récent.

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
```

1. Dans `.env`, mets ta clé API Anthropic (`ANTHROPIC_API_KEY=...`), à créer sur https://console.anthropic.com.
2. Dans `config.yaml`, décris ton produit et tes concurrents (voir plus bas).

## Configurer ton produit

```yaml
mon_produit:
  nom: "MonSaaS"
  description: >
    Logiciel de devis et factures pour indépendants, avec relances automatiques.
  fonctionnalites:
    - "Relances automatiques des impayés"
    - "Export FEC pour l'expert-comptable"
```

Plus la liste des fonctionnalités est précise, plus la colonne « Ton produit » du rapport est juste. C'est elle qui sépare les problèmes que tu règles déjà, et que tu peux mettre en avant, de ceux qu'il te reste à traiter.

## Configurer les sources

Chaque concurrent peut avoir une ou plusieurs sources. Toutes sont facultatives.

| Source | Ce qu'il faut | Remarques |
|---|---|---|
| **Google Play** | l'identifiant après `?id=` dans l'URL de la fiche | Seuls les avis de 1 à `note_max` étoiles sont récupérés. |
| **App Store** | le nombre après `/id` dans l'URL de la fiche | Flux public d'Apple, limité aux 500 avis les plus récents. |
| **Hacker News** | un mot-clé (le nom du concurrent) | Utile pour les SaaS B2B et tech. Aucune clé nécessaire. |
| **Reddit** | une application Reddit gratuite | Voir ci-dessous. |
| **Fichiers** (G2, Capterra, Trustpilot, TrustRadius, sondages...) | un export CSV, JSON ou JSONL | Voir ci-dessous. |

Les paramètres `pays` (`fr`, `be`, `ch`, `ca`, `us`...) et `langue` de la section `collecte` s'appliquent aux stores. Tu peux les remplacer concurrent par concurrent.

### Reddit

1. Va sur https://www.reddit.com/prefs/apps, clique sur « create another app… » et choisis le type **script**.
2. Copie l'identifiant (sous le nom de l'app) et le secret dans `.env` (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`).

Reddit encadre l'accès à son API et peut demander une validation pour certaines applications. Consulte ses conditions avant un usage régulier.

### G2, Capterra, Trustpilot et les autres sites d'avis

Ces sites n'ont pas d'API publique pour les avis, et leurs conditions d'utilisation limitent souvent l'extraction automatique. Le pipeline ne les aspire donc pas lui-même : il importe des fichiers que tu récupères comme tu le souhaites, par exemple avec un acteur Apify (« G2 reviews scraper », « Capterra reviews », « Trustpilot reviews »), par un export manuel ou à partir de tes propres sondages.

```yaml
    fichiers:
      - chemin: "imports/concurrent_a_g2.json"
        source: "g2"
```

Les colonnes courantes (`text`, `review`, `content`, `cons`, `rating`, `date`, `url`...) sont reconnues automatiquement, même dans un JSON imbriqué (`{"rating": {"value": 4}}` devient `rating_value`). Sinon, indique-les toi-même :

```yaml
        colonnes:
          texte: ["cons", "review_text"]   # plusieurs colonnes sont mises bout à bout
          note: "rating_value"
        echelle_note: 10                   # si les notes sont sur 10
```

## Lancer

```bash
python -m veille_avis collecter            # récupère les avis (relançable : pas de doublons)
python -m veille_avis analyser --limite 30 # essai à petit prix sur 30 avis
python -m veille_avis analyser             # analyse le reste et génère le rapport
python -m veille_avis rapport              # régénère seulement le rapport
python -m veille_avis tout                 # les trois étapes d'un coup
```

| Option | Effet |
|---|---|
| `--config fichier.yaml` | utiliser une autre config (défaut : `config.yaml`) |
| `--concurrent "Nom"` | ne collecter qu'un concurrent |
| `--sans-ia` | analyse par mots-clés, gratuite et hors ligne |
| `--limite N` | n'analyser que N nouveaux avis |
| `--oui` | ne pas demander de confirmation avant de lancer l'analyse payante |

## Combien ça coûte

Avant chaque analyse, une estimation s'affiche, puis le programme demande confirmation. À la fin, la consommation réelle est affichée.

- Un avis déjà analysé ne l'est jamais deux fois : les résultats sont gardés dans `data/extractions_claude.jsonl`. Relancer chaque semaine ne coûte que les nouveaux avis, plus le regroupement en thèmes et les recommandations.
- Le modèle par défaut est `claude-opus-5-5`. Pour réduire le coût, change `analyse.modele`, par exemple en `claude-sonnet-5-5`, ou baisse `effort_synthese`. La qualité du regroupement peut baisser.
- Le repli automatique de l'API est activé (`fallbacks: "default"`). Si un filtre de sécurité refuse une requête, ce qui est rare sur des avis clients, l'API la relance sur un autre modèle au lieu de perdre le lot.

## Lire le rapport

`rapports/rapport.md` contient :

1. **En bref** : volumes analysés et synthèse des opportunités les plus fortes.
2. **Les problèmes les plus importants** : un tableau classé par priorité.
3. **Gains rapides** : effort faible pour un problème fréquent ou grave.
4. **Détail par problème** : citations exactes avec lien vers l'avis, couverture par ton produit, recommandation, effort estimé et argument marketing.
5. **Points faibles de chaque concurrent** : utile pour des pages « Alternative à X » ou des fiches de comparaison commerciales.
6. **Données collectées** et **Méthode et limites**.

La **priorité** vaut : mentions × gravité moyenne × (1 + 0,5 par concurrent touché en plus du premier) × (1 + part des avis qui parlent de départ). Un problème fréquent, grave, présent chez plusieurs concurrents et qui fait partir des clients est une vraie opportunité de différenciation.

`rapports/themes.csv` contient le même tableau, à ouvrir dans Excel ou Google Sheets pour trier et filtrer.

## Bonnes pratiques

- **Vise 50 à 100 avis récents par concurrent au minimum**, en priorité ceux à 1 ou 2 étoiles.
- **Relis les citations** des premiers thèmes : ce sont les mots de tes futurs clients, réutilisables dans tes pages et tes publicités.
- **Les avis publics ne sont pas représentatifs** : ils surreprésentent les mécontents. Valide chaque piste en parlant à de vrais prospects avant de la développer.
- **Respecte les conditions d'utilisation** des sites dont tu importes les avis. Le pipeline ne conserve ni le nom ni le pseudo des auteurs.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Les tests n'appellent ni Internet ni l'API Claude : les sources et Claude sont simulés.

## Organisation du code

```
veille_avis/
├── cli.py               ligne de commande
├── config.py            lecture de config.yaml et .env
├── modeles.py           Avis, Probleme
├── categories.py        catégories de problèmes et mots-clés
├── stockage.py          fichiers JSONL / JSON
├── collecteurs/         google_play, app_store, hackernews, reddit, fichiers
├── analyse/
│   ├── claude.py        extraction, thèmes et recommandations avec Claude
│   ├── heuristique.py   analyse par mots-clés (--sans-ia)
│   └── agregation.py    statistiques et priorité
└── rapport.py           rapport Markdown et export CSV
```
