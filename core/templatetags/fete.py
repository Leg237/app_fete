from django import template

register = template.Library()


@register.filter
def fcfa(valeur):
    """5000 -> '5 000 FCFA' ; vide -> 'Sur devis'."""
    if valeur in (None, ""):
        return "Sur devis"
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return valeur
    return f"{nombre:,}".replace(",", "\u202f") + " FCFA"


@register.filter
def etoiles(note):
    try:
        n = int(round(float(note or 0)))
    except (TypeError, ValueError):
        n = 0
    n = max(0, min(5, n))
    return "★" * n + "☆" * (5 - n)
