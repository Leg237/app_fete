"""API JSON (v1) consommée par l'application Flet.

Authentification : en-tête  Authorization: Token <clé>
Les images sont renvoyées en URL absolue.
"""
import json
import logging
from functools import wraps

from django.contrib.auth import authenticate
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .forms import (
    AbonnementForm,
    AvisForm,
    DemandeForm,
    InscriptionPrestataireForm,
    InscriptionVisiteurForm,
    MotDePasseOubliForm,
    OffreForm,
    PhotoForm,
    PrestataireProfilForm,
)
from .models import (
    ApiToken,
    Abonnement,
    Categorie,
    Demande,
    Offre,
    ParametresSite,
    Photo,
    Plan,
    Prestataire,
    Ville,
)
from .services import rechercher


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- infrastructure
def _erreurs(form):
    return {champ: [str(e) for e in liste] for champ, liste in form.errors.items()}


def _reponse_erreur(form, statut=400):
    return JsonResponse({"detail": "Données invalides.", "erreurs": _erreurs(form)}, status=statut)


def donnees(request):
    if (request.content_type or "").startswith("application/json"):
        try:
            return json.loads(request.body or b"{}")
        except ValueError:
            return {}
    return request.POST


def utilisateur_depuis_token(request):
    entete = request.META.get("HTTP_AUTHORIZATION", "")
    if not entete.startswith("Token "):
        return None
    jeton = ApiToken.objects.select_related("user").filter(cle=entete[6:].strip()).first()
    return jeton.user if jeton and jeton.user.is_active else None


def api(methodes=("GET",), auth=False, prestataire=False):
    def decorateur(vue):
        @csrf_exempt
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if request.method not in methodes:
                return JsonResponse({"detail": "Méthode non autorisée."}, status=405)
            if auth or prestataire:
                user = utilisateur_depuis_token(request)
                if user is None:
                    return JsonResponse({"detail": "Connexion requise."}, status=401)
                request.user = user
                if prestataire:
                    if not hasattr(user, "prestataire"):
                        return JsonResponse({"detail": "Réservé aux prestataires."}, status=403)
                    request.presta = user.prestataire
            try:
                return vue(request, *args, **kwargs)
            except Http404:
                return JsonResponse({"detail": "Introuvable."}, status=404)

        return enveloppe

    return decorateur


# ---------------------------------------------------------------- sérialisation
def url_abs(request, fichier):
    return request.build_absolute_uri(fichier.url) if fichier else None


def date_fr(valeur):
    return timezone.localtime(valeur).strftime("%d/%m/%Y") if valeur else None


def s_categorie(c):
    return {"id": c.id, "slug": c.slug, "nom": c.nom, "emoji": c.emoji, "icone": c.icone_flet,
            "couleur": c.couleur, "description": c.description, "champs": c.champs or []}


def s_plan(p):
    return {"id": p.id, "nom": p.nom, "prix": p.prix_fcfa, "duree_jours": p.duree_jours,
            "max_photos": p.max_photos, "max_offres": p.max_offres, "mis_en_avant": p.mis_en_avant,
            "description": p.description, "avantages": p.avantages_liste}


def s_offre(request, o):
    return {"id": o.id, "titre": o.titre, "description": o.description, "prix": o.prix,
            "unite_prix": o.unite_prix, "image": url_abs(request, o.image), "actif": o.actif}


def s_photo(request, ph):
    return {"id": ph.id, "image": url_abs(request, ph.image), "legende": ph.legende}


def s_avis(a):
    return {"id": a.id, "auteur": a.auteur.first_name or "Client", "note": a.note,
            "commentaire": a.commentaire, "date": date_fr(a.cree_le)}


def s_demande(d, cote_prestataire=False):
    return {"id": d.id, "prestataire": d.prestataire.nom, "slug": d.prestataire.slug,
            "type_fete": d.type_fete, "date_evenement": d.date_evenement.strftime("%d/%m/%Y") if d.date_evenement else None,
            "budget": d.budget, "message": d.message, "statut": d.statut,
            "statut_libelle": d.get_statut_display(), "date": date_fr(d.cree_le),
            "nom_contact": d.nom_contact, "telephone": d.telephone}


def s_abonnement(a):
    return {"id": a.id, "plan": a.plan.nom, "statut": a.statut, "statut_libelle": a.get_statut_display(),
            "methode": a.get_methode_display(), "montant": a.montant, "reference": a.reference_paiement,
            "debut": date_fr(a.debut), "fin": date_fr(a.fin), "jours_restants": a.jours_restants}


def s_prestataire(request, p, detail=False):
    data = {
        "id": p.id, "slug": p.slug, "nom": p.nom, "categorie": s_categorie(p.categorie),
        "ville": p.ville.nom, "logo": url_abs(request, p.logo), "couverture": url_abs(request, p.couverture),
        "note": round(p.note, 1) if p.note else None, "nb_avis": p.nombre_avis,
        "description_courte": (p.description or "")[:120],
    }
    if detail:
        data.update({
            "description": p.description, "telephone": p.telephone, "whatsapp": p.whatsapp_numero,
            "adresse": p.adresse,
            "details": [{"label": k, "valeur": v} for k, v in (p.details or {}).items() if v],
            "offres": [s_offre(request, o) for o in p.offres.filter(actif=True)],
            "photos": [s_photo(request, ph) for ph in p.photos.all()],
            "avis": [s_avis(a) for a in p.avis.select_related("auteur")[:20]],
        })
    return data


def s_utilisateur(user):
    profil = getattr(user, "profil", None)
    return {"id": user.id, "nom": user.first_name, "email": user.email,
            "telephone": profil.telephone if profil else "",
            "role": "prestataire" if hasattr(user, "prestataire") else "visiteur"}


def s_espace(request, p):
    abo = p.abonnement_en_cours()
    attente = p.abonnements.filter(statut=Abonnement.ATTENTE).first()
    data = s_prestataire(request, p, detail=True)
    data["offres"] = [s_offre(request, o) for o in p.offres.all()]
    data.update({
        "statut": p.statut, "statut_libelle": p.get_statut_display(), "motif_refus": p.motif_refus,
        "visible": p.est_visible, "ville_id": p.ville_id,
        "abonnement": s_abonnement(abo) if abo else None,
        "abonnement_attente": s_abonnement(attente) if attente else None,
        "limites": {"photos": p.limites()[0], "offres": p.limites()[1]},
        "compteurs": {"offres": p.offres.count(), "photos": p.photos.count(),
                      "demandes_nouvelles": p.demandes.filter(statut=Demande.NOUVELLE).count()},
    })
    return data


def session(request, user):
    reponse = {"token": ApiToken.pour(user).cle, "user": s_utilisateur(user), "prestataire": None}
    if hasattr(user, "prestataire"):
        reponse["prestataire"] = s_espace(request, user.prestataire)
    return reponse


# ---------------------------------------------------------------- public
@api()
def meta(request):
    site = ParametresSite.charger()
    return JsonResponse({
        "site": {"nom": site.nom_site, "slogan": site.slogan, "whatsapp": site.whatsapp_admin,
                 "mtn": site.numero_mtn_momo, "orange": site.numero_orange_money,
                 "beneficiaire": site.beneficiaire_paiement, "instructions": site.instructions_paiement},
        "categories": [s_categorie(c) for c in Categorie.objects.filter(actif=True)],
        "villes": [{"id": v.id, "nom": v.nom} for v in Ville.objects.all()],
        "plans": [s_plan(p) for p in Plan.objects.filter(actif=True)],
    })


@api()
def prestataires(request):
    qs = rechercher(request.GET)
    if request.GET.get("en_avant"):
        avant = qs.en_avant()
        qs = avant if avant.exists() else qs
    try:
        limite = max(1, min(50, int(request.GET.get("limite", 12))))
    except ValueError:
        limite = 12
    page = Paginator(qs, limite).get_page(request.GET.get("page"))
    return JsonResponse({
        "resultats": [s_prestataire(request, p) for p in page.object_list],
        "page": page.number, "pages": page.paginator.num_pages, "total": page.paginator.count,
    })


@api()
def prestataire_detail(request, slug):
    p = get_object_or_404(Prestataire.objects.avec_note().select_related("categorie", "ville"), slug=slug)
    if not p.est_visible:
        raise Http404
    return JsonResponse(s_prestataire(request, p, detail=True))


# ---------------------------------------------------------------- comptes
@api(("POST",))
def inscription(request):
    brut = donnees(request)
    d = brut.dict() if hasattr(brut, "dict") else dict(brut)
    d.setdefault("mot_de_passe2", d.get("mot_de_passe", ""))
    if d.get("role") == "prestataire":
        cat = Categorie.objects.filter(slug=d.get("categorie"), actif=True).first()
        if cat is None:
            return JsonResponse({"detail": "Catégorie inconnue.", "erreurs": {"categorie": ["Choisissez une catégorie."]}}, status=400)
        details = d.get("details") or {}
        for i, champ in enumerate(cat.champs or []):
            d[f"detail_{i}"] = details.get(champ.get("label"), "")
        form = InscriptionPrestataireForm(d, categorie=cat)
    else:
        form = InscriptionVisiteurForm(d)
    if not form.is_valid():
        return _reponse_erreur(form)
    user = form.save()
    return JsonResponse(session(request, user), status=201)


@api(("POST",))
def connexion(request):
    d = donnees(request)
    user = authenticate(request, username=(d.get("email") or "").strip().lower(), password=d.get("mot_de_passe") or "")
    if user is None:
        return JsonResponse({"detail": "Adresse e-mail ou mot de passe incorrect."}, status=400)
    return JsonResponse(session(request, user))


@api(("POST",))
def mdp_oublie(request):
    """Envoie le lien de réinitialisation par e-mail. Réponse identique que le compte existe ou non."""
    form = MotDePasseOubliForm(donnees(request))
    if not form.is_valid():
        return _reponse_erreur(form)
    try:
        form.envoyer(request)
    except Exception:
        logger.exception("Échec de l'envoi de l'e-mail de réinitialisation")
        return JsonResponse({"detail": "L'e-mail n'a pas pu être envoyé pour le moment. Réessayez plus tard."}, status=503)
    return JsonResponse({"ok": True, "detail": "Si un compte existe avec cette adresse, un e-mail vient d'être envoyé."})


@api(("POST",), auth=True)
def deconnexion(request):
    ApiToken.objects.filter(user=request.user).delete()
    return JsonResponse({"ok": True})


@api(auth=True)
def moi(request):
    return JsonResponse(session(request, request.user))


@api(auth=True)
def mes_demandes(request):
    qs = request.user.demandes_envoyees.select_related("prestataire")
    return JsonResponse({"resultats": [s_demande(d) for d in qs]})


@api(("POST",), auth=True)
def demande(request, slug):
    p = get_object_or_404(Prestataire, slug=slug)
    if not p.est_visible or p.user_id == request.user.id:
        raise Http404
    form = DemandeForm(donnees(request))
    if not form.is_valid():
        return _reponse_erreur(form)
    obj = form.save(commit=False)
    obj.prestataire, obj.auteur = p, request.user
    obj.save()
    return JsonResponse(s_demande(obj), status=201)


@api(("POST",), auth=True)
def avis(request, slug):
    p = get_object_or_404(Prestataire, slug=slug)
    if not p.est_visible or p.user_id == request.user.id:
        raise Http404
    form = AvisForm(donnees(request), instance=p.avis.filter(auteur=request.user).first())
    if not form.is_valid():
        return _reponse_erreur(form)
    obj = form.save(commit=False)
    obj.prestataire, obj.auteur = p, request.user
    obj.save()
    return JsonResponse(s_avis(obj), status=201)


# ---------------------------------------------------------------- espace prestataire
@api(prestataire=True)
def espace(request):
    return JsonResponse(s_espace(request, request.presta))


@api(("POST", "PUT"), prestataire=True)
def espace_profil(request):
    p = request.presta
    form = PrestataireProfilForm(donnees(request), request.FILES, instance=p)
    if not form.is_valid():
        return _reponse_erreur(form)
    form.save()
    p.refresh_from_db()
    return JsonResponse(s_espace(request, p))


@api(("GET", "POST"), prestataire=True)
def espace_offres(request):
    p = request.presta
    if request.method == "POST":
        if p.offres.count() >= p.limites()[1]:
            return JsonResponse({"detail": "Limite d'offres atteinte pour votre formule."}, status=403)
        form = OffreForm(donnees(request), request.FILES)
        if not form.is_valid():
            return _reponse_erreur(form)
        offre = form.save(commit=False)
        offre.prestataire = p
        offre.save()
        return JsonResponse(s_offre(request, offre), status=201)
    return JsonResponse({"resultats": [s_offre(request, o) for o in p.offres.all()]})


@api(("POST", "DELETE"), prestataire=True)
def espace_offre(request, pk):
    offre = get_object_or_404(Offre, pk=pk, prestataire=request.presta)
    if request.method == "DELETE":
        offre.delete()
        return JsonResponse({"ok": True})
    form = OffreForm(donnees(request), request.FILES, instance=offre)
    if not form.is_valid():
        return _reponse_erreur(form)
    form.save()
    return JsonResponse(s_offre(request, offre))


@api(("GET", "POST"), prestataire=True)
def espace_photos(request):
    p = request.presta
    if request.method == "POST":
        if p.photos.count() >= p.limites()[0]:
            return JsonResponse({"detail": "Limite de photos atteinte pour votre formule."}, status=403)
        form = PhotoForm(donnees(request), request.FILES)
        if not form.is_valid():
            return _reponse_erreur(form)
        photo = form.save(commit=False)
        photo.prestataire = p
        photo.save()
        return JsonResponse(s_photo(request, photo), status=201)
    return JsonResponse({"resultats": [s_photo(request, ph) for ph in p.photos.all()]})


@api(("DELETE",), prestataire=True)
def espace_photo(request, pk):
    get_object_or_404(Photo, pk=pk, prestataire=request.presta).delete()
    return JsonResponse({"ok": True})


@api(("GET", "POST"), prestataire=True)
def espace_abonnement(request):
    p = request.presta
    if request.method == "POST":
        d = donnees(request)
        plan = Plan.objects.filter(pk=d.get("plan_id") or 0, actif=True).first()
        if plan is None:
            return JsonResponse({"detail": "Formule inconnue."}, status=400)
        if p.abonnements.filter(statut=Abonnement.ATTENTE).exists():
            return JsonResponse({"detail": "Un paiement est déjà en cours de vérification."}, status=400)
        form = AbonnementForm(d)
        if not form.is_valid():
            return _reponse_erreur(form)
        abo = form.save(commit=False)
        abo.prestataire, abo.plan, abo.montant = p, plan, plan.prix_fcfa
        abo.save()
        return JsonResponse(s_abonnement(abo), status=201)
    return JsonResponse({"resultats": [s_abonnement(a) for a in p.abonnements.select_related("plan")]})


@api(prestataire=True)
def espace_demandes(request):
    return JsonResponse({"resultats": [s_demande(d, True) for d in request.presta.demandes.select_related("prestataire")]})


@api(("POST",), prestataire=True)
def espace_demande_statut(request, pk):
    obj = get_object_or_404(Demande, pk=pk, prestataire=request.presta)
    statut = donnees(request).get("statut")
    if statut not in (Demande.LUE, Demande.TRAITEE):
        return JsonResponse({"detail": "Statut invalide."}, status=400)
    obj.statut = statut
    obj.save(update_fields=["statut"])
    return JsonResponse(s_demande(obj, True))
