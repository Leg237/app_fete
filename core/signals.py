"""Notifications automatiques : une offre publiée, un prestataire mis à jour, un profil validé,
un abonnement activé, une demande de devis reçue, une nouvelle version de l'application…

Les anciens prix/valeurs sont mémorisés avant l'enregistrement (pre_save) pour ne notifier
que les vrais changements. Les mises à jour d'un même prestataire sont espacées (anti-spam).
"""
from datetime import timedelta

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from . import notifications as notif
from .models import Abonnement, Avis, Demande, Notification, Offre, Pack, ParametresSite, Photo, Prestataire

CHAMPS_PROFIL = ("nom", "description", "telephone", "whatsapp", "ville_id", "adresse", "logo", "couverture", "details")
CHAMPS_OFFRE = ("titre", "description", "prix", "unite_prix", "image", "actif")
ESPACEMENT_PROFIL = timedelta(hours=12)
ESPACEMENT_OFFRE = timedelta(hours=6)


# ---------------------------------------------------------------- utilitaires
def _valeur(objet, champ):
    valeur = getattr(objet, champ, None)
    return getattr(valeur, "name", valeur) if hasattr(valeur, "name") else valeur


def _memoriser(sender, instance, champs):
    instance._ancien = None
    if instance.pk:
        ancien = sender.objects.filter(pk=instance.pk).first()
        if ancien is not None:
            instance._ancien = {c: _valeur(ancien, c) for c in champs}


def _modifie(instance, champs):
    ancien = getattr(instance, "_ancien", None)
    return ancien is not None and any(ancien.get(c) != _valeur(instance, c) for c in champs)


def _prix(offre):
    if not offre.prix:
        return "Sur devis"
    texte = f"{offre.prix:,}".replace(",", " ") + " FCFA"
    return f"{texte} {offre.unite_prix}".strip()


# ---------------------------------------------------------------- prestataires
@receiver(pre_save, sender=Prestataire)
def prestataire_avant(sender, instance, **kwargs):
    _memoriser(sender, instance, CHAMPS_PROFIL + ("statut",))


@receiver(post_save, sender=Prestataire)
def prestataire_apres(sender, instance, created, **kwargs):
    if created or notif.est_silencieux():
        return
    ancien = getattr(instance, "_ancien", None) or {}
    if ancien.get("statut") not in (None, instance.statut):
        if instance.statut == Prestataire.VALIDE:
            notif.prive(instance.user, Notification.ESPACE, "Votre profil est validé",
                        "Choisissez une formule d'abonnement pour apparaître auprès des clients.",
                        route="/espace/abonnement", reference=f"valide-{instance.pk}-{instance.mis_a_jour:%Y%m%d%H%M}")
            notif.annoncer_nouveau_prestataire(instance)
        elif instance.statut == Prestataire.REFUSE:
            notif.prive(instance.user, Notification.ESPACE, "Votre profil a été refusé",
                        instance.motif_refus or "Ouvrez votre espace pour voir le motif et corriger votre profil.",
                        route="/espace/profil", reference=f"refuse-{instance.pk}-{instance.mis_a_jour:%Y%m%d%H%M}")
        elif instance.statut == Prestataire.SUSPENDU:
            notif.prive(instance.user, Notification.ESPACE, "Votre profil est suspendu",
                        "Contactez l'équipe Fête & Services pour en savoir plus.",
                        route="/espace", reference=f"suspendu-{instance.pk}-{instance.mis_a_jour:%Y%m%d%H%M}")
    elif _modifie(instance, CHAMPS_PROFIL) and instance.est_visible:
        notif.diffuser(Notification.PRESTATAIRE, f"{instance.nom} a mis à jour son profil",
                       f"{instance.categorie.nom} à {instance.ville.nom} : découvrez les nouveautés.",
                       route=f"/prestataire/{instance.slug}", reference=f"profil-{instance.pk}",
                       auteur=instance.user, delai=ESPACEMENT_PROFIL)


# ---------------------------------------------------------------- offres et photos
@receiver(pre_save, sender=Offre)
def offre_avant(sender, instance, **kwargs):
    _memoriser(sender, instance, CHAMPS_OFFRE)


@receiver(post_save, sender=Offre)
def offre_apres(sender, instance, created, **kwargs):
    if notif.est_silencieux() or not instance.actif:
        return
    presta = instance.prestataire
    if not presta.est_visible:
        return
    route = f"/prestataire/{presta.slug}"
    if created:
        notif.diffuser(Notification.OFFRE, f"Nouvelle offre chez {presta.nom}",
                       f"{instance.titre} · {_prix(instance)}", route=route,
                       reference=f"offre-{instance.pk}", auteur=presta.user)
    elif _modifie(instance, CHAMPS_OFFRE):
        ancien = instance._ancien
        if ancien.get("prix") != instance.prix:
            titre, message = f"Nouveau prix chez {presta.nom}", f"{instance.titre} · {_prix(instance)}"
        else:
            titre, message = f"Offre mise à jour chez {presta.nom}", instance.titre
        notif.diffuser(Notification.OFFRE, titre, message, route=route,
                       reference=f"offre-maj-{instance.pk}", auteur=presta.user, delai=ESPACEMENT_OFFRE)


@receiver(post_save, sender=Pack)
def pack_apres(sender, instance, created, **kwargs):
    if not created or notif.est_silencieux() or not instance.actif:
        return
    presta = instance.prestataire
    if presta.est_visible:
        notif.diffuser(Notification.OFFRE, f"Nouveau pack chez {presta.nom}", f"{instance.titre} · {instance.prix:,} FCFA".replace(",", " "),
                       route=f"/prestataire/{presta.slug}", reference=f"pack-{instance.pk}", auteur=presta.user)


@receiver(post_save, sender=Photo)
def photo_apres(sender, instance, created, **kwargs):
    if not created or notif.est_silencieux():
        return
    presta = instance.prestataire
    if presta.est_visible:
        notif.diffuser(Notification.PRESTATAIRE, f"Nouvelles photos chez {presta.nom}",
                       "Découvrez ses dernières réalisations.", route=f"/prestataire/{presta.slug}",
                       reference=f"photos-{presta.pk}", auteur=presta.user, delai=ESPACEMENT_PROFIL)


# ---------------------------------------------------------------- abonnements
@receiver(pre_save, sender=Abonnement)
def abonnement_avant(sender, instance, **kwargs):
    _memoriser(sender, instance, ("statut",))


@receiver(post_save, sender=Abonnement)
def abonnement_apres(sender, instance, created, **kwargs):
    if notif.est_silencieux():
        return
    ancien = (getattr(instance, "_ancien", None) or {}).get("statut")
    presta = instance.prestataire
    if instance.statut == Abonnement.ACTIF and ancien != Abonnement.ACTIF:
        fin = instance.fin.strftime("%d/%m/%Y") if instance.fin else ""
        notif.prive(presta.user, Notification.ESPACE, "Abonnement activé",
                    f"Formule {instance.plan.nom} active" + (f" jusqu'au {fin}." if fin else "."),
                    route="/espace/abonnement", reference=f"abo-actif-{instance.pk}")
        notif.annoncer_nouveau_prestataire(presta)
    elif instance.statut == Abonnement.REJETE and ancien != Abonnement.REJETE:
        notif.prive(presta.user, Notification.ESPACE, "Paiement non confirmé",
                    "Vérifiez la référence de la transaction ou contactez l'équipe.",
                    route="/espace/abonnement", reference=f"abo-rejete-{instance.pk}")


# ---------------------------------------------------------------- demandes et avis
@receiver(pre_save, sender=Demande)
def demande_avant(sender, instance, **kwargs):
    _memoriser(sender, instance, ("statut",))


@receiver(post_save, sender=Demande)
def demande_apres(sender, instance, created, **kwargs):
    if notif.est_silencieux():
        return
    if created:
        quand = f" le {instance.date_evenement:%d/%m/%Y}" if instance.date_evenement else ""
        notif.prive(instance.prestataire.user, Notification.ESPACE, "Nouvelle demande de devis",
                    f"{instance.nom_contact} : {instance.type_fete}{quand}.", route="/espace/demandes",
                    reference=f"demande-{instance.pk}")
    elif instance.statut == Demande.TRAITEE and (getattr(instance, "_ancien", None) or {}).get("statut") not in (None, Demande.TRAITEE):
        notif.prive(instance.auteur, Notification.ESPACE, "Votre demande a été traitée",
                    f"{instance.prestataire.nom} a traité votre demande de devis.", route="/compte",
                    reference=f"demande-traitee-{instance.pk}")


@receiver(post_save, sender=Avis)
def avis_apres(sender, instance, created, **kwargs):
    if not created or notif.est_silencieux():
        return
    presta = instance.prestataire
    etoiles = "★" * instance.note + "☆" * (5 - instance.note)
    notif.prive(presta.user, Notification.ESPACE, "Nouvel avis client",
                f"{etoiles} de {instance.auteur.first_name or 'un client'}", route="/espace",
                reference=f"avis-{instance.pk}")


# ---------------------------------------------------------------- application mobile
@receiver(pre_save, sender=ParametresSite)
def parametres_avant(sender, instance, **kwargs):
    instance.pk = 1
    _memoriser(sender, instance, ("version_app_actuelle",))


@receiver(post_save, sender=ParametresSite)
def parametres_apres(sender, instance, created, **kwargs):
    version = (instance.version_app_actuelle or "").strip()
    if version and _modifie(instance, ("version_app_actuelle",)):
        notif.diffuser(Notification.APPLICATION, "Mise à jour disponible",
                       f"La version {version} de Fête & Services est disponible.",
                       reference=version)
