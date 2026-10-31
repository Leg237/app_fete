"""Codes promo : les réductions n'apparaissent que pour les clients qui présentent un code valide.

L'application envoie ses codes dans l'en-tête  X-Codes-Promo: CODE1,CODE2  ; le serveur ne retient que
les campagnes en cours (code exact, dates, active). Une offre ou un pack n'est réduit que si son
prestataire a accepté les promotions (`accepte_promo`) et si la catégorie correspond.
"""
from django.utils import timezone

from .models import Campagne


def codes_de_la_requete(request):
    brut = request.META.get("HTTP_X_CODES_PROMO", "")
    return [c.strip().upper() for c in brut.split(",") if c.strip()][:10]


def campagnes_actives(request):
    if not hasattr(request, "_campagnes_promo"):
        codes = codes_de_la_requete(request)
        request._campagnes_promo = list(Campagne.valides(codes)) if codes else []
    return request._campagnes_promo


def format_fin(campagne):
    return timezone.localtime(campagne.fin).strftime("%d/%m/%Y %H:%M")


def remise(request, objet, prestataire):
    """{'prix_promo', 'promo'} pour une offre ou un pack, ou {} s'il n'y a aucune réduction applicable."""
    if not objet.prix or not objet.accepte_promo:
        return {}
    meilleure = None
    for c in campagnes_actives(request):
        if c.categorie_id and c.categorie_id != prestataire.categorie_id:
            continue
        if meilleure is None or c.pourcentage > meilleure.pourcentage:
            meilleure = c
    if meilleure is None:
        return {}
    return {
        "prix_promo": round(objet.prix * (100 - meilleure.pourcentage) / 100),
        "promo": {"nom": meilleure.nom, "pourcentage": meilleure.pourcentage, "fin": format_fin(meilleure)},
    }
