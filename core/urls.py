from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("prestataires/", views.liste_prestataires, name="prestataires"),
    path("prestataires/<slug:slug>/", views.detail_prestataire, name="prestataire"),
    path("prestataires/<slug:slug>/demande/", views.envoyer_demande, name="demande"),
    path("prestataires/<slug:slug>/avis/", views.laisser_avis, name="avis"),
    path("tarifs/", views.tarifs, name="tarifs"),
    # comptes
    path("inscription/", views.inscription, name="inscription"),
    path("inscription/client/", views.inscription_visiteur, name="inscription_visiteur"),
    path("inscription/prestataire/<slug:categorie>/", views.inscription_prestataire, name="inscription_prestataire"),
    path("connexion/", views.VueConnexion.as_view(), name="connexion"),
    path("deconnexion/", LogoutView.as_view(), name="deconnexion"),
    path("redirection/", views.redirection, name="redirection"),
    # mot de passe oublié
    path("mot-de-passe-oublie/", views.VueMdpOublie.as_view(), name="mdp_oublie"),
    path("mot-de-passe-oublie/envoye/", auth_views.PasswordResetDoneView.as_view(template_name="auth/mdp_oublie_envoye.html"), name="mdp_oublie_envoye"),
    path("mot-de-passe/reinitialiser/<uidb64>/<token>/", views.VueMdpConfirmer.as_view(), name="mdp_confirmer"),
    path("mot-de-passe/reinitialise/", auth_views.PasswordResetCompleteView.as_view(template_name="auth/mdp_reinitialise.html"), name="mdp_reinitialise"),
    # pages légales
    path("cgu/", TemplateView.as_view(template_name="legal/cgu.html"), name="cgu"),
    path("confidentialite/", TemplateView.as_view(template_name="legal/confidentialite.html"), name="confidentialite"),
    path("mentions-legales/", TemplateView.as_view(template_name="legal/mentions.html"), name="mentions_legales"),
    path("cookies/", TemplateView.as_view(template_name="legal/cookies.html"), name="cookies"),
    path("mon-compte/", views.compte, name="compte"),
    # espace prestataire
    path("espace/", views.espace, name="espace"),
    path("espace/profil/", views.espace_profil, name="espace_profil"),
    path("espace/offres/", views.espace_offres, name="espace_offres"),
    path("espace/offres/nouvelle/", views.espace_offre_form, name="espace_offre_ajout"),
    path("espace/offres/<int:pk>/", views.espace_offre_form, name="espace_offre_modif"),
    path("espace/offres/<int:pk>/supprimer/", views.espace_offre_suppr, name="espace_offre_suppr"),
    path("espace/galerie/", views.espace_galerie, name="espace_galerie"),
    path("espace/galerie/<int:pk>/supprimer/", views.espace_photo_suppr, name="espace_photo_suppr"),
    path("espace/abonnement/", views.espace_abonnement, name="espace_abonnement"),
    path("espace/abonnement/<int:plan_id>/", views.espace_souscrire, name="espace_souscrire"),
    path("espace/demandes/", views.espace_demandes, name="espace_demandes"),
    path("espace/demandes/<int:pk>/statut/", views.espace_demande_statut, name="espace_demande_statut"),
]

if settings.DEBUG:  # aperçu des pages d'erreur sans passer en production
    urlpatterns += [path("apercu-erreur/<slug:code>/", views.apercu_erreur, name="apercu_erreur")]
