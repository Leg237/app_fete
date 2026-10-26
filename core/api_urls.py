from django.urls import path

from . import api

urlpatterns = [
    path("meta/", api.meta),
    path("prestataires/", api.prestataires),
    path("prestataires/<slug:slug>/", api.prestataire_detail),
    path("prestataires/<slug:slug>/demande/", api.demande),
    path("prestataires/<slug:slug>/avis/", api.avis),
    path("auth/inscription/", api.inscription),
    path("auth/connexion/", api.connexion),
    path("auth/deconnexion/", api.deconnexion),
    path("auth/mot-de-passe-oublie/", api.mdp_oublie),
    path("me/", api.moi),
    path("me/demandes/", api.mes_demandes),
    path("espace/", api.espace),
    path("espace/profil/", api.espace_profil),
    path("espace/offres/", api.espace_offres),
    path("espace/offres/<int:pk>/", api.espace_offre),
    path("espace/photos/", api.espace_photos),
    path("espace/photos/<int:pk>/", api.espace_photo),
    path("espace/abonnement/", api.espace_abonnement),
    path("espace/demandes/", api.espace_demandes),
    path("espace/demandes/<int:pk>/statut/", api.espace_demande_statut),
]
