import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count
from django.http import Http404, HttpResponseRedirect, HttpResponseServerError
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST

from .forms import (
    AbonnementForm,
    AvisForm,
    ConnexionForm,
    DemandeForm,
    InscriptionPrestataireForm,
    InscriptionVisiteurForm,
    MotDePasseOubliForm,
    NouveauMotDePasseForm,
    OffreForm,
    PhotoForm,
    PrestataireProfilForm,
)
from .models import Abonnement, Categorie, Demande, Offre, Photo, Plan, Prestataire, Ville
from .services import rechercher


logger = logging.getLogger(__name__)


def prestataire_requis(vue):
    def enveloppe(request, *args, **kwargs):
        if not hasattr(request.user, "prestataire"):
            messages.info(request, "Cet espace est réservé aux prestataires.")
            return redirect("compte")
        request.presta = request.user.prestataire
        return vue(request, *args, **kwargs)

    enveloppe.__name__ = vue.__name__
    return login_required(enveloppe)


# ================================================================ pages publiques
def accueil(request):
    base = Prestataire.objects.visibles().avec_note().select_related("categorie", "ville")
    vedettes = list(base.en_avant().order_by("-cree_le")[:6])
    if len(vedettes) < 3:
        vedettes = list(base.order_by("-cree_le")[:6])
    contexte = {
        "categories": Categorie.objects.filter(actif=True),
        "vedettes": vedettes,
        "arches": [p for p in vedettes if p.image_principale][:3],
        "nb_prestataires": Prestataire.objects.visibles().count(),
        "plan_min": Plan.objects.filter(actif=True).order_by("prix_fcfa").first(),
        "villes": Ville.objects.all(),
    }
    return render(request, "accueil.html", contexte)


def liste_prestataires(request):
    qs = rechercher(request.GET)
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "prestataires.html",
        {
            "page": page,
            "categories": Categorie.objects.filter(actif=True),
            "villes": Ville.objects.all(),
            "q": request.GET.get("q", ""),
            "categorie_active": request.GET.get("categorie", ""),
            "ville_active": request.GET.get("ville", ""),
            "querystring": params.urlencode(),
        },
    )


def detail_prestataire(request, slug):
    p = get_object_or_404(Prestataire.objects.select_related("categorie", "ville", "user"), slug=slug)
    proprietaire = request.user.is_authenticated and p.user_id == request.user.id
    if not (p.est_visible or proprietaire or request.user.is_staff):
        raise Http404
    stats = p.avis.aggregate(m=Avg("note"), n=Count("id"))
    mon_avis = p.avis.filter(auteur=request.user).first() if request.user.is_authenticated else None
    initial = {}
    if request.user.is_authenticated:
        profil = getattr(request.user, "profil", None)
        initial = {
            "nom_contact": request.user.get_full_name(),
            "telephone": profil.telephone if profil else "",
        }
    return render(
        request,
        "prestataire.html",
        {
            "p": p,
            "proprietaire": proprietaire,
            "en_ligne": p.est_visible,
            "offres": p.offres.filter(actif=True),
            "photos": p.photos.all(),
            "details": [(k, v) for k, v in (p.details or {}).items() if v],
            "avis_liste": p.avis.select_related("auteur")[:10],
            "note_moyenne": stats["m"],
            "nb_avis": stats["n"],
            "mon_avis": mon_avis,
            "form_demande": DemandeForm(initial=initial),
            "form_avis": AvisForm(instance=mon_avis),
        },
    )


def _connexion_requise(request, p):
    return redirect(f"{reverse('connexion')}?next={p.get_absolute_url()}")


@require_POST
def envoyer_demande(request, slug):
    p = get_object_or_404(Prestataire, slug=slug)
    if not request.user.is_authenticated:
        return _connexion_requise(request, p)
    if not p.est_visible or p.user_id == request.user.id:
        raise Http404
    form = DemandeForm(request.POST)
    if form.is_valid():
        demande = form.save(commit=False)
        demande.prestataire, demande.auteur = p, request.user
        demande.save()
        messages.success(request, f"Votre demande a été envoyée à {p.nom}. Le prestataire vous répondra sur WhatsApp.")
    else:
        messages.error(request, "La demande n'a pas été envoyée : vérifiez les champs obligatoires.")
    return redirect(p.get_absolute_url() + "#contact")


@require_POST
def laisser_avis(request, slug):
    p = get_object_or_404(Prestataire, slug=slug)
    if not request.user.is_authenticated:
        return _connexion_requise(request, p)
    if p.user_id == request.user.id:
        raise Http404
    existant = p.avis.filter(auteur=request.user).first()
    form = AvisForm(request.POST, instance=existant)
    if form.is_valid():
        avis = form.save(commit=False)
        avis.prestataire, avis.auteur = p, request.user
        avis.save()
        messages.success(request, "Merci, votre avis est publié.")
    else:
        messages.error(request, "Choisissez une note de 1 à 5.")
    return redirect(p.get_absolute_url() + "#avis")


def tarifs(request):
    return render(request, "tarifs.html", {"plans": Plan.objects.filter(actif=True)})


# ================================================================ comptes
def inscription(request):
    return render(request, "auth/inscription.html", {"categories": Categorie.objects.filter(actif=True)})


def inscription_visiteur(request):
    form = InscriptionVisiteurForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Bienvenue ! Votre compte est créé, c'est gratuit.")
        return redirect("prestataires")
    return render(request, "auth/formulaire.html", {"form": form, "titre": "Créer mon compte client", "bouton": "Créer mon compte gratuit", "sous_titre": "Gratuit. Demandez des devis et laissez des avis."})


def inscription_prestataire(request, categorie):
    cat = get_object_or_404(Categorie, slug=categorie, actif=True)
    form = InscriptionPrestataireForm(request.POST or None, categorie=cat)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Votre espace est créé. Choisissez une formule pour être visible par les clients.")
        return redirect("espace_abonnement")
    return render(
        request,
        "auth/formulaire.html",
        {"form": form, "titre": f"Inscription {cat.nom}", "bouton": "Créer mon espace prestataire", "sous_titre": "Votre profil sera vérifié par notre équipe, puis publié avec votre abonnement.", "categorie": cat},
    )


class VueConnexion(auth_views.LoginView):
    template_name = "auth/connexion.html"
    authentication_form = ConnexionForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse("redirection")


@login_required
def redirection(request):
    return redirect("espace" if hasattr(request.user, "prestataire") else "compte")


@login_required
def compte(request):
    if hasattr(request.user, "prestataire"):
        return redirect("espace")
    return render(
        request,
        "compte.html",
        {
            "demandes": request.user.demandes_envoyees.select_related("prestataire"),
            "avis": request.user.avis_donnes.select_related("prestataire"),
        },
    )


# ================================================================ espace prestataire
@prestataire_requis
def espace(request):
    p = request.presta
    return render(
        request,
        "espace/tableau.html",
        {
            "p": p,
            "onglet": "tableau",
            "abo": p.abonnement_en_cours(),
            "abo_attente": p.abonnements.filter(statut=Abonnement.ATTENTE).first(),
            "nb_offres": p.offres.count(),
            "nb_photos": p.photos.count(),
            "nb_nouvelles": p.demandes.filter(statut=Demande.NOUVELLE).count(),
            "dernieres": p.demandes.all()[:5],
            "limites": p.limites(),
        },
    )


@prestataire_requis
def espace_profil(request):
    p = request.presta
    form = PrestataireProfilForm(request.POST or None, request.FILES or None, instance=p)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil enregistré.")
        return redirect("espace_profil")
    return render(request, "espace/profil.html", {"p": p, "form": form, "onglet": "profil"})


@prestataire_requis
def espace_offres(request):
    p = request.presta
    return render(
        request,
        "espace/offres.html",
        {"p": p, "offres": p.offres.all(), "onglet": "offres", "limite": p.limites()[1]},
    )


@prestataire_requis
def espace_offre_form(request, pk=None):
    p = request.presta
    offre = get_object_or_404(Offre, pk=pk, prestataire=p) if pk else None
    if offre is None and p.offres.count() >= p.limites()[1]:
        messages.warning(request, "Vous avez atteint la limite d'offres de votre formule. Passez à une formule supérieure.")
        return redirect("espace_offres")
    form = OffreForm(request.POST or None, request.FILES or None, instance=offre)
    if request.method == "POST" and form.is_valid():
        nouvelle = form.save(commit=False)
        nouvelle.prestataire = p
        nouvelle.save()
        messages.success(request, "Offre enregistrée.")
        return redirect("espace_offres")
    return render(
        request,
        "espace/formulaire.html",
        {"p": p, "form": form, "onglet": "offres", "titre": "Modifier l'offre" if offre else "Nouvelle offre", "retour": "espace_offres", "multipart": True},
    )


@require_POST
@prestataire_requis
def espace_offre_suppr(request, pk):
    get_object_or_404(Offre, pk=pk, prestataire=request.presta).delete()
    messages.success(request, "Offre supprimée.")
    return redirect("espace_offres")


@prestataire_requis
def espace_galerie(request):
    p = request.presta
    limite = p.limites()[0]
    form = PhotoForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if p.photos.count() >= limite:
            messages.warning(request, "Vous avez atteint la limite de photos de votre formule.")
            return redirect("espace_galerie")
        if form.is_valid():
            photo = form.save(commit=False)
            photo.prestataire = p
            photo.save()
            messages.success(request, "Photo ajoutée à votre galerie.")
            return redirect("espace_galerie")
    return render(request, "espace/galerie.html", {"p": p, "form": form, "photos": p.photos.all(), "limite": limite, "onglet": "galerie"})


@require_POST
@prestataire_requis
def espace_photo_suppr(request, pk):
    get_object_or_404(Photo, pk=pk, prestataire=request.presta).delete()
    messages.success(request, "Photo supprimée.")
    return redirect("espace_galerie")


@prestataire_requis
def espace_abonnement(request):
    p = request.presta
    return render(
        request,
        "espace/abonnement.html",
        {
            "p": p,
            "onglet": "abonnement",
            "abo": p.abonnement_en_cours(),
            "abo_attente": p.abonnements.filter(statut=Abonnement.ATTENTE).first(),
            "plans": Plan.objects.filter(actif=True),
            "historique": p.abonnements.select_related("plan"),
        },
    )


@prestataire_requis
def espace_souscrire(request, plan_id):
    p = request.presta
    plan = get_object_or_404(Plan, pk=plan_id, actif=True)
    if p.abonnements.filter(statut=Abonnement.ATTENTE).exists():
        messages.info(request, "Un paiement est déjà en cours de vérification. Nous vous prévenons dès son activation.")
        return redirect("espace_abonnement")
    form = AbonnementForm(request.POST or None, initial={"telephone_paiement": p.telephone})
    if request.method == "POST" and form.is_valid():
        abo = form.save(commit=False)
        abo.prestataire, abo.plan, abo.montant = p, plan, plan.prix_fcfa
        abo.save()
        messages.success(request, "Paiement reçu. Nous le vérifions et activons votre abonnement, en général sous 24 heures.")
        return redirect("espace_abonnement")
    return render(request, "espace/souscrire.html", {"p": p, "plan": plan, "form": form, "onglet": "abonnement"})


@prestataire_requis
def espace_demandes(request):
    p = request.presta
    return render(request, "espace/demandes.html", {"p": p, "demandes": p.demandes.all(), "onglet": "demandes"})


@require_POST
@prestataire_requis
def espace_demande_statut(request, pk):
    demande = get_object_or_404(Demande, pk=pk, prestataire=request.presta)
    statut = request.POST.get("statut")
    if statut in (Demande.LUE, Demande.TRAITEE):
        demande.statut = statut
        demande.save(update_fields=["statut"])
    return redirect("espace_demandes")


# ================================================================ mot de passe oublié
class VueMdpOublie(auth_views.PasswordResetView):
    """Demande de lien par e-mail. La réponse est la même que l'adresse existe ou non."""

    template_name = "auth/mdp_oublie.html"
    form_class = MotDePasseOubliForm
    success_url = reverse_lazy("mdp_oublie_envoye")

    def form_valid(self, form):
        try:
            form.envoyer(self.request)
        except Exception:
            logger.exception("Échec de l'envoi de l'e-mail de réinitialisation")
            messages.error(self.request, "L'e-mail n'a pas pu être envoyé pour le moment. Réessayez dans quelques minutes ou contactez l'équipe.")
            return self.form_invalid(form)
        return HttpResponseRedirect(self.get_success_url())


class VueMdpConfirmer(auth_views.PasswordResetConfirmView):
    template_name = "auth/mdp_reinitialiser.html"
    form_class = NouveauMotDePasseForm
    success_url = reverse_lazy("mdp_reinitialise")


# ================================================================ pages d'erreur
def erreur_400(request, exception=None):
    return render(request, "400.html", status=400)


def erreur_403(request, exception=None):
    return render(request, "403.html", status=403)


def erreur_404(request, exception=None):
    return render(request, "404.html", status=404)


def erreur_500(request):
    # Gabarit autonome : aucune requête en base, il reste affichable même si la base est en panne.
    return HttpResponseServerError(render_to_string("500.html"))


def echec_csrf(request, reason=""):
    return render(request, "403_csrf.html", status=403)


def apercu_erreur(request, code):
    """Aperçu des pages d'erreur en développement (DEBUG=1) : /apercu-erreur/404/"""
    pages = {"400": ("400.html", 400), "403": ("403.html", 403), "404": ("404.html", 404), "csrf": ("403_csrf.html", 403)}
    if code == "500":
        return erreur_500(request)
    if code not in pages:
        raise Http404
    gabarit, statut = pages[code]
    return render(request, gabarit, status=statut)
