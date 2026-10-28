"""Création des notifications de l'application mobile.

diffuser(...) : notification pour tous les utilisateurs (nouvelle offre, mise à jour…)
prive(...)    : notification pour un seul utilisateur (demande de devis, abonnement…)

Les signaux (core/signals.py) appellent ces fonctions automatiquement. Pour créer des objets
sans notifier (import de données, démo), utilisez :  with silencieux(): ...
"""
import threading
from contextlib import contextmanager
from datetime import timedelta

from django.utils import timezone

from .models import Abonnement, Notification

_local = threading.local()


@contextmanager
def silencieux():
    avant = getattr(_local, "silence", False)
    _local.silence = True
    try:
        yield
    finally:
        _local.silence = avant


def est_silencieux():
    return getattr(_local, "silence", False)


def _couper(texte, longueur):
    texte = (texte or "").strip()
    return texte if len(texte) <= longueur else texte[: longueur - 1].rstrip() + "…"


def diffuser(type_, titre, message="", route="", reference="", auteur=None, delai=None):
    """Notification pour tous. Avec `reference`, évite les doublons (dans le `delai` si fourni)."""
    if est_silencieux():
        return None
    if reference:
        deja = Notification.objects.filter(type=type_, reference=reference, destinataire__isnull=True)
        if delai:
            deja = deja.filter(cree_le__gte=timezone.now() - delai)
        if deja.exists():
            return None
    return Notification.objects.create(
        type=type_, titre=_couper(titre, 120), message=_couper(message, 300), route=route,
        reference=reference, auteur=auteur,
    )


def prive(user, type_, titre, message="", route="", reference=""):
    """Notification pour un seul utilisateur. Avec `reference`, une seule fois."""
    if est_silencieux() or user is None:
        return None
    if reference and Notification.objects.filter(destinataire=user, type=type_, reference=reference).exists():
        return None
    return Notification.objects.create(
        destinataire=user, type=type_, titre=_couper(titre, 120), message=_couper(message, 300),
        route=route, reference=reference,
    )


def annoncer_nouveau_prestataire(presta):
    """Une seule annonce « Nouveau prestataire », quand il devient visible (validé + abonnement actif)."""
    if not presta.est_visible:
        return None
    return diffuser(
        Notification.PRESTATAIRE,
        f"Nouveau : {presta.nom}",
        f"{presta.categorie.nom} à {presta.ville.nom} vient de rejoindre Fête & Services.",
        route=f"/prestataire/{presta.slug}",
        reference=f"nouveau-{presta.pk}",
        auteur=presta.user,
    )


def rappels_abonnement(presta):
    """Rappels générés au moment où l'application interroge le serveur (aucune tâche planifiée requise)."""
    abo = presta.abonnement_en_cours()
    if abo:
        jours = abo.jours_restants
        if jours <= 3:
            quand = "dans moins de 24 h" if jours == 0 else ("demain" if jours == 1 else f"dans {jours} jours")
            prive(
                presta.user, Notification.ESPACE, "Votre abonnement se termine bientôt",
                f"Votre formule {abo.plan.nom} expire {quand}. Renouvelez-la pour rester visible.",
                route="/espace/abonnement", reference=f"expire-bientot-{abo.pk}",
            )
        return
    derniere = presta.abonnements.filter(statut=Abonnement.ACTIF, fin__lt=timezone.now()).order_by("-fin").first()
    if derniere:
        prive(
            presta.user, Notification.ESPACE, "Votre abonnement a expiré",
            "Votre page n'est plus visible des clients. Choisissez une formule pour la remettre en ligne.",
            route="/espace/abonnement", reference=f"expire-{derniere.pk}",
        )


def purger_anciennes(jours=60):
    Notification.objects.filter(cree_le__lt=timezone.now() - timedelta(days=jours)).delete()
