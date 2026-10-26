"""Logique partagée entre le site web et l'API de l'application Flet."""
from django.db.models import Q

from .models import Prestataire


def rechercher(params):
    """Recherche publique : q, categorie (slug), ville (id). Renvoie un queryset."""
    q = (params.get("q") or "").strip()
    categorie = (params.get("categorie") or "").strip()
    ville = str(params.get("ville") or "").strip()

    qs = Prestataire.objects.visibles().avec_note().select_related("categorie", "ville")
    if q:
        qs = qs.filter(
            Q(nom__icontains=q)
            | Q(description__icontains=q)
            | Q(categorie__nom__icontains=q)
            | Q(offres__titre__icontains=q)
        ).distinct()
    if categorie:
        qs = qs.filter(categorie__slug=categorie)
    if ville.isdigit():
        qs = qs.filter(ville_id=int(ville))
    return qs.order_by("-cree_le")
