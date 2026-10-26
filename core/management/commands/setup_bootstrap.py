"""Télécharge la version officielle de Bootstrap dans static/vendor/ (une seule fois, internet requis)."""
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

VERSION = "5.3.3"
FICHIERS = {
    "css/bootstrap.min.css": f"https://cdn.jsdelivr.net/npm/bootstrap@{VERSION}/dist/css/bootstrap.min.css",
    "js/bootstrap.bundle.min.js": f"https://cdn.jsdelivr.net/npm/bootstrap@{VERSION}/dist/js/bootstrap.bundle.min.js",
}


class Command(BaseCommand):
    help = "Installe Bootstrap officiel en local (static/vendor/bootstrap)."

    def handle(self, *args, **options):
        base = settings.BASE_DIR / "static" / "vendor" / "bootstrap"
        for chemin, url in FICHIERS.items():
            cible = base / chemin
            cible.parent.mkdir(parents=True, exist_ok=True)
            try:
                with urllib.request.urlopen(url, timeout=30) as reponse:
                    cible.write_bytes(reponse.read())
            except Exception as erreur:
                raise CommandError(f"Téléchargement impossible ({url}) : {erreur}")
            self.stdout.write(self.style.SUCCESS(f"OK  {cible.relative_to(settings.BASE_DIR)}"))
        self.stdout.write(f"Bootstrap {VERSION} installé en local.")
