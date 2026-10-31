"""API JSON (v1) consommée par l'application Flet.

Authentification : en-tête  Authorization: Token <clé>
Les images sont renvoyées en URL absolue.
"""
import json
import logging
import re
import secrets
from datetime import timedelta
from functools import wraps

from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import URLValidator
from django.core.paginator import Paginator
from django.db.models import F, Max, Q
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
    Campagne,
    Categorie,
    CodeReinitialisation,
    Demande,
    Notification,
    Offre,
    Pack,
    ParametresSite,
    Photo,
    Plan,
    Prestataire,
    Profil,
    Ville,
)
from .auth_backends import trouver_utilisateur
from .promos import format_fin, remise
from .notifications import diffuser, purger_anciennes, rappels_abonnement
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


def api(methodes=("GET",), auth=False, prestataire=False, admin=False):
    def decorateur(vue):
        @csrf_exempt
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if request.method not in methodes:
                return JsonResponse({"detail": "Méthode non autorisée."}, status=405)
            if auth or prestataire or admin:
                user = utilisateur_depuis_token(request)
                if user is None:
                    return JsonResponse({"detail": "Connexion requise."}, status=401)
                request.user = user
                if admin and not (user.is_staff or user.is_superuser):
                    return JsonResponse({"detail": "Réservé à l'administrateur."}, status=403)
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
            "max_photos": p.max_photos, "max_offres": p.max_offres, "max_packs": p.max_packs, "mis_en_avant": p.mis_en_avant,
            "description": p.description, "avantages": p.avantages_liste}


def s_offre(request, o):
    data = {"id": o.id, "titre": o.titre, "description": o.description, "prix": o.prix,
            "unite_prix": o.unite_prix, "image": url_abs(request, o.image), "actif": o.actif,
            "accepte_promo": o.accepte_promo}
    data.update(remise(request, o, o.prestataire))
    return data


def s_pack(request, pk):
    inclus = list(pk.offres.all())
    valeur = pk.valeur_separee
    data = {"id": pk.id, "titre": pk.titre, "description": pk.description, "prix": pk.prix,
            "image": url_abs(request, pk.image), "actif": pk.actif, "accepte_promo": pk.accepte_promo,
            "inclus": [{"id": o.id, "titre": o.titre} for o in inclus], "inclus_ids": [o.id for o in inclus],
            "valeur_separee": valeur, "economie": max(0, valeur - pk.prix) if valeur else None}
    data.update(remise(request, pk, pk.prestataire))
    return data


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


def s_notification(n):
    return {"id": n.id, "type": n.type, "titre": n.titre, "message": n.message, "route": n.route,
            "reference": n.reference, "date": timezone.localtime(n.cree_le).strftime("%d/%m/%Y %H:%M"),
            "prive": n.destinataire_id is not None}


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
            "packs": [s_pack(request, k) for k in p.packs.filter(actif=True).prefetch_related("offres")],
            "photos": [s_photo(request, ph) for ph in p.photos.all()],
            "avis": [s_avis(a) for a in p.avis.select_related("auteur")[:20]],
        })
    return data


def s_utilisateur(user):
    profil = getattr(user, "profil", None)
    return {"id": user.id, "username": user.username, "nom": user.first_name, "email": user.email,
            "telephone": profil.telephone if profil else "",
            "role": "prestataire" if hasattr(user, "prestataire") else "visiteur",
            "admin": bool(user.is_staff or user.is_superuser),
            "mdp_provisoire": bool(profil.mdp_provisoire) if profil else False}


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
        "limites": {"photos": p.limites()[0], "offres": p.limites()[1], "packs": p.limite_packs()},
        "compteurs": {"offres": p.offres.count(), "packs": p.packs.count(), "photos": p.photos.count(),
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
        "app": {"version": site.version_app_actuelle, "lien": site.lien_telechargement_app},
        "serveur": {"url": site.url_serveur},
    })


@api()
def notifications(request):
    """Fil de notifications (public + privées si jeton).

    ?apres=<id>   : seulement les nouveautés (ordre croissant) — utilisé par l'application en tâche de fond
    sans `apres`  : les dernières, pour initialiser le centre de notifications
    `dernier_id`  : plus grand identifiant visible, sert de point de départ au premier appel.
    """
    user = utilisateur_depuis_token(request)
    if user is not None:
        if hasattr(user, "prestataire"):
            rappels_abonnement(user.prestataire)
        qs = Notification.objects.filter(Q(destinataire__isnull=True) | Q(destinataire=user)).exclude(auteur=user)
    else:
        qs = Notification.objects.filter(destinataire__isnull=True)
    try:
        limite = max(1, min(50, int(request.GET.get("limite", 30))))
    except ValueError:
        limite = 30
    apres = (request.GET.get("apres") or "").strip()
    if apres.isdigit():
        elements = list(qs.filter(id__gt=int(apres)).order_by("id")[:limite])
    else:
        elements = list(qs.order_by("-id")[:limite])[::-1]
        if Notification.objects.count() > 2000:  # ménage occasionnel des vieilles notifications
            purger_anciennes()
    return JsonResponse({
        "dernier_id": qs.aggregate(m=Max("id"))["m"] or 0,
        "serveur": ParametresSite.charger().url_serveur,
        "resultats": [s_notification(n) for n in elements],
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
    if not str(d.get("nom_utilisateur") or "").strip():
        return JsonResponse({"detail": "Données invalides.", "erreurs": {"nom_utilisateur": ["Choisissez un nom d'utilisateur."]}}, status=400)
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
    identifiant = str(d.get("nom_utilisateur") or d.get("email") or "").strip()
    cle = f"connexion:{request.META.get('REMOTE_ADDR', '')}"
    if (cache.get(cle) or 0) >= 15:
        return JsonResponse({"detail": "Trop de tentatives. Réessayez dans quelques minutes."}, status=429)
    user = authenticate(request, username=identifiant, password=d.get("mot_de_passe") or "")
    if user is None:
        cache.set(cle, (cache.get(cle) or 0) + 1, 600)
        return JsonResponse({"detail": "Nom d'utilisateur ou mot de passe incorrect."}, status=400)
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


def _limite(cle, maximum, duree):
    """Compteur anti-abus : vrai tant que le nombre d'appels reste sous `maximum` pendant `duree` secondes."""
    n = (cache.get(cle) or 0) + 1
    cache.set(cle, n, duree)
    return n <= maximum


@api(("POST",))
def mdp_code(request):
    """Envoie par e-mail un code à 6 chiffres (15 min). Réponse identique que le compte existe ou non."""
    identifiant = str(donnees(request).get("identifiant") or "").strip()
    if not identifiant:
        return JsonResponse({"detail": "Saisissez votre nom d'utilisateur ou votre e-mail.", "erreurs": {"identifiant": ["Champ obligatoire."]}}, status=400)
    reponse = JsonResponse({"ok": True, "detail": "Si ce compte existe et a une adresse e-mail, un code à 6 chiffres vient d'être envoyé (valable 15 minutes)."})
    if not _limite(f"mdp-code-ip:{request.META.get('REMOTE_ADDR', '')}", 10, 3600):
        return JsonResponse({"detail": "Trop de demandes. Réessayez plus tard."}, status=429)
    user = trouver_utilisateur(identifiant)
    if user is None or not user.email or not user.is_active:
        return reponse
    if not _limite(f"mdp-code:{user.pk}", 1, 60):  # un code par minute et par compte
        return reponse
    code = f"{secrets.randbelow(10 ** 6):06d}"
    CodeReinitialisation.objects.filter(user=user, utilise=False).update(utilise=True)
    CodeReinitialisation.objects.create(user=user, code_hash=make_password(code), expire_le=timezone.now() + timedelta(minutes=15))
    nom_site = ParametresSite.charger().nom_site
    try:
        send_mail(
            f"{nom_site} : code de réinitialisation",
            f"Bonjour {user.first_name or user.username},\n\nVotre code de réinitialisation est : {code}\n"
            f"Il est valable 15 minutes. Si vous n'avez rien demandé, ignorez ce message : votre mot de passe reste inchangé.\n\n{nom_site}",
            None, [user.email],
        )
    except Exception:
        logger.exception("Échec de l'envoi du code de réinitialisation")
        return JsonResponse({"detail": "L'e-mail n'a pas pu être envoyé pour le moment. Réessayez plus tard ou contactez l'administrateur."}, status=503)
    return reponse


@api(("POST",))
def mdp_reinitialiser(request):
    d = donnees(request)
    echec = JsonResponse({"detail": "Code invalide ou expiré. Demandez un nouveau code."}, status=400)
    if not _limite(f"mdp-reinit-ip:{request.META.get('REMOTE_ADDR', '')}", 30, 3600):
        return JsonResponse({"detail": "Trop de tentatives. Réessayez plus tard."}, status=429)
    user = trouver_utilisateur(str(d.get("identifiant") or ""))
    code = str(d.get("code") or "").strip()
    nouveau = d.get("nouveau_mot_de_passe") or ""
    if user is None or not code:
        return echec
    enreg = CodeReinitialisation.objects.filter(user=user, utilise=False, expire_le__gt=timezone.now()).first()
    if enreg is None:
        return echec
    if not check_password(code, enreg.code_hash):
        enreg.tentatives += 1
        if enreg.tentatives >= 5:
            enreg.utilise = True
        enreg.save(update_fields=["tentatives", "utilise"])
        return echec
    try:
        password_validation.validate_password(nouveau, user)
    except ValidationError as erreur:
        return JsonResponse({"detail": "Données invalides.", "erreurs": {"nouveau_mot_de_passe": list(erreur.messages)}}, status=400)
    user.set_password(nouveau)
    user.save()
    enreg.utilise = True
    enreg.save(update_fields=["utilise"])
    Profil.objects.filter(user=user).update(mdp_provisoire=False)
    ApiToken.objects.filter(user=user).delete()  # déconnecte les appareils déjà connectés
    return JsonResponse({"ok": True, "detail": "Mot de passe modifié. Vous pouvez vous connecter."})


@api(("POST",), auth=True)
def mdp_changer(request):
    d = donnees(request)
    user = request.user
    if not user.check_password(d.get("ancien") or ""):
        return JsonResponse({"detail": "Données invalides.", "erreurs": {"ancien": ["Mot de passe actuel incorrect."]}}, status=400)
    try:
        password_validation.validate_password(d.get("nouveau") or "", user)
    except ValidationError as erreur:
        return JsonResponse({"detail": "Données invalides.", "erreurs": {"nouveau": list(erreur.messages)}}, status=400)
    user.set_password(d["nouveau"])
    user.save()
    Profil.objects.filter(user=user).update(mdp_provisoire=False)
    return JsonResponse({"ok": True, "detail": "Mot de passe modifié."})


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


def _ids(valeur):
    """Liste d'identifiants depuis une liste JSON, « 1,2,3 » ou un champ de formulaire répété."""
    if hasattr(valeur, "getlist"):
        valeur = valeur.getlist("offres")
    if isinstance(valeur, str):
        valeur = valeur.split(",")
    ids = []
    for v in valeur or []:
        for morceau in str(v).split(","):
            if morceau.strip().isdigit():
                ids.append(int(morceau))
    return ids


def _vrai(valeur, defaut=True):
    if valeur is None or valeur == "":
        return defaut
    return str(valeur).strip().lower() in ("1", "on", "true", "oui", "vrai")


def _enregistrer_pack(request, p, instance=None):
    """Valide les données d'un pack (titre, prix, au moins 2 offres du prestataire) puis l'enregistre."""
    brut = donnees(request)
    d = brut.dict() if hasattr(brut, "dict") else dict(brut)
    erreurs = {}
    titre = str(d.get("titre") or "").strip()[:120]
    if not titre:
        erreurs["titre"] = ["Saisissez un titre."]
    try:
        prix = int(str(d.get("prix") or "").replace(" ", ""))
        if prix <= 0:
            raise ValueError
    except ValueError:
        prix = 0
        erreurs["prix"] = ["Saisissez le prix du pack en FCFA."]
    ids = _ids(brut.getlist("offres") if hasattr(brut, "getlist") else d.get("offres"))
    offres = list(p.offres.filter(pk__in=ids))
    if len(offres) < 2:
        erreurs["offres"] = ["Choisissez au moins 2 de vos offres à regrouper."]
    image = request.FILES.get("image")
    if image is not None:
        if image.size > 8 * 1024 * 1024:
            erreurs["image"] = ["Image trop lourde (8 Mo maximum)."]
        else:
            try:
                from PIL import Image
                Image.open(image).verify()
                image.seek(0)
            except Exception:
                erreurs["image"] = ["Fichier image invalide."]
    if erreurs:
        return None, JsonResponse({"detail": "Données invalides.", "erreurs": erreurs}, status=400)
    pack = instance or Pack(prestataire=p)
    pack.titre, pack.prix = titre, prix
    pack.description = str(d.get("description") or "").strip()
    pack.actif = _vrai(d.get("actif"), True)
    pack.accepte_promo = _vrai(d.get("accepte_promo"), False)
    if image is not None:
        pack.image = image
    pack.save()
    pack.offres.set(offres)
    return pack, None


@api(("GET", "POST"), prestataire=True)
def espace_packs(request):
    p = request.presta
    if request.method == "POST":
        if p.packs.count() >= p.limite_packs():
            return JsonResponse({"detail": "Limite de packs atteinte pour votre formule."}, status=403)
        pack, erreur = _enregistrer_pack(request, p)
        return erreur or JsonResponse(s_pack(request, pack), status=201)
    return JsonResponse({"resultats": [s_pack(request, k) for k in p.packs.prefetch_related("offres")]})


@api(("POST", "DELETE"), prestataire=True)
def espace_pack(request, pk):
    pack = get_object_or_404(Pack, pk=pk, prestataire=request.presta)
    if request.method == "DELETE":
        pack.delete()
        return JsonResponse({"ok": True})
    pack, erreur = _enregistrer_pack(request, request.presta, instance=pack)
    return erreur or JsonResponse(s_pack(request, pack))


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


# ---------------------------------------------------------------- administration (comptes is_staff)
def _s_presta_admin(p):
    return {"id": p.id, "nom": p.nom, "categorie": p.categorie.nom, "ville": p.ville.nom, "statut": p.statut,
            "statut_libelle": p.get_statut_display(), "motif_refus": p.motif_refus, "visible": p.est_visible,
            "utilisateur": p.user.username, "email": p.user.email, "telephone": p.telephone}


def _s_abo_admin(a):
    return {"id": a.id, "prestataire": a.prestataire.nom, "plan": a.plan.nom, "statut": a.statut,
            "statut_libelle": a.get_statut_display(), "methode": a.get_methode_display(), "telephone": a.telephone_paiement,
            "reference": a.reference_paiement, "montant": a.montant, "date": date_fr(a.cree_le)}


@api(admin=True)
def admin_tableau(request):
    site = ParametresSite.charger()
    return JsonResponse({
        "prestataires": {s: Prestataire.objects.filter(statut=s).count() for s, _ in Prestataire.STATUTS},
        "abonnements_attente": Abonnement.objects.filter(statut=Abonnement.ATTENTE).count(),
        "utilisateurs": User.objects.count(),
        "demandes": Demande.objects.count(),
        "campagnes_en_cours": sum(1 for c in Campagne.objects.filter(active=True, fin__gte=timezone.now()) if c.statut == "en_cours"),
        "version_app": site.version_app_actuelle,
        "serveur": site.url_serveur,
    })


@api(admin=True)
def admin_prestataires(request):
    qs = Prestataire.objects.select_related("categorie", "ville", "user")
    statut = request.GET.get("statut") or ""
    if statut in dict(Prestataire.STATUTS):
        qs = qs.filter(statut=statut)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(user__username__icontains=q) | Q(user__email__icontains=q))
    return JsonResponse({"resultats": [_s_presta_admin(p) for p in qs.order_by("-id")[:50]]})


@api(("POST",), admin=True)
def admin_prestataire_statut(request, pk):
    p = get_object_or_404(Prestataire.objects.select_related("categorie", "ville", "user"), pk=pk)
    d = donnees(request)
    statut = d.get("statut")
    if statut not in (Prestataire.VALIDE, Prestataire.REFUSE, Prestataire.SUSPENDU):
        return JsonResponse({"detail": "Statut invalide."}, status=400)
    p.statut = statut
    p.motif_refus = str(d.get("motif") or "").strip()[:200] if statut == Prestataire.REFUSE else ""
    p.save()  # save() et non update() : déclenche la notification au prestataire
    logger.info("Admin %s : prestataire %s -> %s", request.user.pk, p.pk, statut)
    return JsonResponse(_s_presta_admin(p))


@api(admin=True)
def admin_abonnements(request):
    qs = Abonnement.objects.select_related("prestataire", "plan")
    statut = request.GET.get("statut") or Abonnement.ATTENTE
    if statut in dict(Abonnement.STATUTS):
        qs = qs.filter(statut=statut)
    return JsonResponse({"resultats": [_s_abo_admin(a) for a in qs.order_by("-cree_le")[:50]]})


@api(("POST",), admin=True)
def admin_abonnement_decision(request, pk):
    abo = get_object_or_404(Abonnement.objects.select_related("prestataire", "plan"), pk=pk)
    decision = donnees(request).get("decision")
    if abo.statut != Abonnement.ATTENTE:
        return JsonResponse({"detail": "Cet abonnement a déjà été traité."}, status=400)
    if decision == "activer":
        abo.activer()
    elif decision == "rejeter":
        abo.statut, abo.valide_le = Abonnement.REJETE, timezone.now()
        abo.save()
    else:
        return JsonResponse({"detail": "Décision invalide."}, status=400)
    logger.info("Admin %s : abonnement %s -> %s", request.user.pk, abo.pk, decision)
    return JsonResponse(_s_abo_admin(abo))


@api(admin=True)
def admin_utilisateurs(request):
    q = (request.GET.get("q") or "").strip()
    qs = User.objects.all()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q))
    return JsonResponse({"resultats": [
        {"id": u.id, "username": u.username, "nom": u.first_name, "email": u.email, "admin": bool(u.is_staff or u.is_superuser),
         "role": "prestataire" if hasattr(u, "prestataire") else "visiteur"}
        for u in qs.order_by("-id")[:25]]})


@api(("POST",), admin=True)
def admin_utilisateur_mdp(request, pk):
    """Génère un mot de passe provisoire (pour un utilisateur sans accès à son e-mail)."""
    cible = get_object_or_404(User, pk=pk)
    if (cible.is_staff or cible.is_superuser) and not request.user.is_superuser:
        return JsonResponse({"detail": "Seul un super-administrateur peut modifier ce compte."}, status=403)
    provisoire = "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(8))
    cible.set_password(provisoire)
    cible.save()
    profil, _ = Profil.objects.get_or_create(user=cible)
    profil.mdp_provisoire = True
    profil.save(update_fields=["mdp_provisoire"])
    ApiToken.objects.filter(user=cible).delete()
    logger.info("Admin %s : mot de passe provisoire pour l'utilisateur %s", request.user.pk, cible.pk)
    return JsonResponse({"username": cible.username, "mot_de_passe_provisoire": provisoire})


@api(("POST",), admin=True)
def admin_annonce(request):
    d = donnees(request)
    titre = str(d.get("titre") or "").strip()
    if not titre:
        return JsonResponse({"detail": "Données invalides.", "erreurs": {"titre": ["Saisissez un titre."]}}, status=400)
    route = str(d.get("route") or "").strip()
    n = diffuser(Notification.ANNONCE, titre, str(d.get("message") or ""), route=route if route.startswith("/") else "")
    return JsonResponse({"ok": True, "id": n.id if n else None})


@api(("GET", "POST"), admin=True)
def admin_serveur(request):
    site = ParametresSite.charger()
    if request.method == "POST":
        url = str(donnees(request).get("url") or "").strip().rstrip("/")
        if url:
            try:
                URLValidator(schemes=["http", "https"])(url)
            except ValidationError:
                return JsonResponse({"detail": "Données invalides.", "erreurs": {"url": ["Adresse invalide (exemple : https://monsite.com)."]}}, status=400)
        site.url_serveur = url
        site.save()
        logger.info("Admin %s : adresse officielle du serveur -> %s", request.user.pk, url or "(vide)")
    return JsonResponse({"url": site.url_serveur})


# ---------------------------------------------------------------- codes promo
@api(("POST",))
def promo_valider(request):
    """Vérifie un code promo saisi par l'utilisateur ; l'application le mémorise tant que la campagne dure."""
    if not _limite(f"promo-ip:{request.META.get('REMOTE_ADDR', '')}", 30, 3600):
        return JsonResponse({"detail": "Trop d'essais. Réessayez plus tard."}, status=429)
    code = str(donnees(request).get("code") or "").strip().upper()
    c = Campagne.valides([code]).select_related("categorie").first() if code else None
    if c is None:
        return JsonResponse({"detail": "Code promo invalide ou expiré."}, status=400)
    Campagne.objects.filter(pk=c.pk).update(saisies=F("saisies") + 1)
    return JsonResponse(_s_campagne_publique(c))


def _s_campagne_publique(c):
    return {"code": c.code, "nom": c.nom, "pourcentage": c.pourcentage, "fin": format_fin(c), "fin_iso": c.fin.isoformat(),
            "categorie": c.categorie.nom if c.categorie else ""}


def _s_campagne_admin(c):
    data = _s_campagne_publique(c)
    data.update({"id": c.id, "statut": c.statut, "debut": timezone.localtime(c.debut).strftime("%d/%m/%Y %H:%M"), "saisies": c.saisies})
    return data


def _participants(categorie=None):
    """Nombre d'offres et de packs visibles dont le prestataire accepte les promotions."""
    offres = Offre.objects.filter(actif=True, accepte_promo=True, prestataire__statut=Prestataire.VALIDE)
    packs = Pack.objects.filter(actif=True, accepte_promo=True, prestataire__statut=Prestataire.VALIDE)
    if categorie is not None:
        offres, packs = offres.filter(prestataire__categorie=categorie), packs.filter(prestataire__categorie=categorie)
    return {"offres": offres.count(), "packs": packs.count()}


@api(("GET", "POST"), admin=True)
def admin_campagnes(request):
    if request.method == "GET":
        return JsonResponse({"resultats": [_s_campagne_admin(c) for c in Campagne.objects.select_related("categorie")[:50]],
                             "participants": _participants()})
    d = donnees(request)
    erreurs = {}
    nom = str(d.get("nom") or "").strip()[:120]
    if not nom:
        erreurs["nom"] = ["Donnez un nom à la campagne."]
    try:
        pourcentage = int(d.get("pourcentage"))
        if not 1 <= pourcentage <= 90:
            raise ValueError
    except (TypeError, ValueError):
        pourcentage = 0
        erreurs["pourcentage"] = ["La réduction doit être comprise entre 1 et 90 %."]
    try:
        duree = int(d.get("duree_jours"))
        if not 1 <= duree <= 365:
            raise ValueError
    except (TypeError, ValueError):
        duree = 0
        erreurs["duree_jours"] = ["La durée doit être comprise entre 1 et 365 jours."]
    categorie = None
    if d.get("categorie"):
        categorie = Categorie.objects.filter(slug=d.get("categorie")).first()
        if categorie is None:
            erreurs["categorie"] = ["Catégorie inconnue."]
    code = str(d.get("code") or "").strip().upper()
    if code:
        if not re.fullmatch(r"[A-Z0-9]{4,20}", code):
            erreurs["code"] = ["4 à 20 caractères : lettres sans accent et chiffres."]
        elif Campagne.objects.filter(code=code).exists():
            erreurs["code"] = ["Ce code existe déjà. Choisissez-en un autre."]
    if erreurs:
        return JsonResponse({"detail": "Données invalides.", "erreurs": erreurs}, status=400)
    while not code or Campagne.objects.filter(code=code).exists():  # code généré : 8 caractères sans ambiguïté (pas de 0/O, 1/I)
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    maintenant = timezone.now()
    c = Campagne.objects.create(nom=nom, code=code, pourcentage=pourcentage, categorie=categorie, debut=maintenant,
                                fin=maintenant + timedelta(days=duree), cree_par=request.user)
    if _vrai(d.get("annoncer"), False):
        message = (f"Utilisez le code {c.code} dans l'application (rubrique Code promo)." if _vrai(d.get("publier_code"), False)
                   else "Demandez votre code promo à l'équipe Fête & Services.")
        diffuser(Notification.ANNONCE, f"Promotion : -{pourcentage} % jusqu'au {timezone.localtime(c.fin):%d/%m}", message, route="/promo")
    logger.info("Admin %s : campagne %s lancée (%s, -%s %%)", request.user.pk, c.pk, c.code, pourcentage)
    reponse = _s_campagne_admin(c)
    reponse["participants"] = _participants(categorie)
    return JsonResponse(reponse, status=201)


@api(("POST",), admin=True)
def admin_campagne_arreter(request, pk):
    c = get_object_or_404(Campagne, pk=pk)
    c.active = False
    c.save(update_fields=["active"])
    logger.info("Admin %s : campagne %s arrêtée", request.user.pk, c.pk)
    return JsonResponse(_s_campagne_admin(c))
