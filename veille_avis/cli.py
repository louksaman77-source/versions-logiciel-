"""Ligne de commande : python -m veille_avis <commande>."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import ErreurConfig, charger_config, charger_env


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m veille_avis",
        description="Analyse les avis de tes concurrents pour trouver quoi ajouter ou ajuster dans ton SaaS.",
    )
    parser.add_argument("--config", default="config.yaml", help="fichier de configuration (défaut : config.yaml)")
    commandes = parser.add_subparsers(dest="commande", required=True, metavar="commande")

    collecter = commandes.add_parser("collecter", help="récupère les avis de chaque source configurée")
    collecter.add_argument("--concurrent", help="ne collecter que ce concurrent")

    def options_analyse(p: argparse.ArgumentParser) -> None:
        p.add_argument("--sans-ia", action="store_true", help="analyse gratuite par mots-clés, sans Claude")
        p.add_argument("--oui", "-y", action="store_true", help="ne pas demander de confirmation avant de payer")
        p.add_argument("--limite", type=int, help="n'analyser que N nouveaux avis (pour tester à petit prix)")

    options_analyse(commandes.add_parser("analyser", help="extrait les problèmes et les regroupe en thèmes"))
    commandes.add_parser("rapport", help="génère rapports/rapport.md et rapports/themes.csv")
    tout = commandes.add_parser("tout", help="collecter + analyser + rapport")
    tout.add_argument("--concurrent", help="ne collecter que ce concurrent")
    options_analyse(tout)
    return parser


def _collecter(cfg, concurrent: str | None) -> None:
    from .collecteurs import collecter_tout

    total, nouveaux = collecter_tout(cfg, concurrent)
    print(f"\n{nouveaux} nouveaux avis · {total} avis en base ({cfg.fichier_avis})")


def _analyser(cfg, args) -> bool:
    from .analyse import AnalyseAnnulee, lancer

    try:
        lancer(cfg, sans_ia=args.sans_ia, oui=args.oui, limite=args.limite)
    except AnalyseAnnulee:
        print("Analyse annulée.")
        return False
    return True


def _rapport(cfg) -> None:
    from .rapport import generer

    chemin_md, chemin_csv = generer(cfg)
    print(f"\nRapport : {chemin_md}\nTableau : {chemin_csv}")


def _executer(args) -> int:
    chemin_config = Path(args.config)
    charger_env(Path.cwd() / ".env")
    charger_env(chemin_config.resolve().parent / ".env")
    cfg = charger_config(chemin_config)

    if args.commande in ("collecter", "tout"):
        _collecter(cfg, args.concurrent)
    if args.commande in ("analyser", "tout"):
        if not _analyser(cfg, args):
            return 1
    if args.commande in ("rapport", "analyser", "tout"):
        _rapport(cfg)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _executer(args)
    except ErreurConfig as erreur:
        print(f"Erreur de configuration : {erreur}")
        return 2
    except KeyboardInterrupt:
        print("\nInterrompu. Les avis déjà analysés sont conservés : relance la commande pour reprendre.")
        return 130
    except Exception as erreur:
        message = _message_api(erreur)
        if message is None:
            raise
        print(f"Erreur : {message}")
        return 1


def _message_api(erreur: Exception) -> str | None:
    """Traduit les erreurs courantes en messages compréhensibles ; None = erreur inattendue."""
    if isinstance(erreur, TypeError) and "authentication method" in str(erreur):
        # Le SDK Anthropic lève cette erreur quand aucune clé n'est trouvée.
        return (
            "aucune clé API Anthropic trouvée. Ajoute ANTHROPIC_API_KEY=... dans ton fichier .env "
            "(clé à créer sur https://console.anthropic.com), ou ajoute --sans-ia pour tester gratuitement."
        )
    if isinstance(erreur, (RuntimeError, ValueError, FileNotFoundError)) and not _est_erreur_anthropic(erreur):
        return str(erreur)
    try:
        import anthropic
    except ImportError:
        return None
    if isinstance(erreur, anthropic.AuthenticationError):
        return "clé API Anthropic refusée. Vérifie ANTHROPIC_API_KEY dans ton fichier .env."
    if isinstance(erreur, anthropic.PermissionDeniedError):
        return "ta clé API n'a pas accès à ce modèle. Change « analyse.modele » dans la config."
    if isinstance(erreur, anthropic.NotFoundError):
        return "modèle introuvable. Vérifie « analyse.modele » dans la config."
    if isinstance(erreur, anthropic.RateLimitError):
        return "limite de requêtes atteinte. Patiente un peu puis relance : le travail déjà fait est conservé."
    if isinstance(erreur, anthropic.APIConnectionError):
        return "impossible de joindre l'API Anthropic. Vérifie ta connexion internet."
    if isinstance(erreur, anthropic.APIStatusError):
        return f"l'API Anthropic a répondu {erreur.status_code} : {erreur.message}"
    if isinstance(erreur, anthropic.AnthropicError):
        return (
            f"{erreur}\nAs-tu bien mis ta clé dans .env (ANTHROPIC_API_KEY=...) ? "
            "Pour tester sans clé, ajoute --sans-ia."
        )
    return None


def _est_erreur_anthropic(erreur: Exception) -> bool:
    return type(erreur).__module__.startswith("anthropic")
