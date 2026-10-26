from .models import Categorie, ParametresSite


def site(request):
    return {
        "site": ParametresSite.charger(),
        "categories_menu": Categorie.objects.filter(actif=True),
    }
