"""Modèles de Fête & Services.

Règle de visibilité publique d'un prestataire :
    statut == "valide"  ET  abonnement actif en cours.
L'inscription des visiteurs est gratuite ; seuls les prestataires paient.
"""
import re
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Exists, FloatField, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .images import optimiser

# Limites tant qu'aucun abonnement n'est actif (le prestataire peut préparer sa vitrine)
LIMITE_PHOTOS_SANS_ABONNEMENT = 3
LIMITE_OFFRES_SANS_ABONNEMENT = 3


# ---------------------------------------------------------------- utilitaires
def _chemin(dossier, nom_fichier):
    extension = nom_fichier.rsplit(".", 1)[-1].lower() if "." in nom_fichier else "jpg"
    extension = re.sub(r"[^a-z0-9]", "", extension)[:5] or "jpg"
    return f"{dossier}/{uuid.uuid4().hex}.{extension}"


def chemin_logo(instance, nom):
    return _chemin("logos", nom)


def chemin_couverture(instance, nom):
    return _chemin("couvertures", nom)


def chemin_photo(instance, nom):
    return _chemin("galerie", nom)


def chemin_offre(instance, nom):
    return _chemin("offres", nom)


def normaliser_telephone(numero, indicatif="237"):
    """'677 12 34 56' -> '237677123456' (format wa.me)."""
    chiffres = re.sub(r"\D", "", numero or "")
    if chiffres.startswith("00"):
        chiffres = chiffres[2:]
    if len(chiffres) == 9:
        chiffres = indicatif + chiffres
    return chiffres


class ImageOptimiseeMixin:
    """Réduit chaque image téléversée (JPEG, 1600 px max) avant l'enregistrement."""

    champs_images = ()

    def save(self, *args, **kwargs):
        for nom in self.champs_images:
            fichier = getattr(self, nom, None)
            if fichier and not getattr(fichier, "_committed", True):
                try:
                    contenu = optimiser(fichier.file)
                    fichier.save(f"{uuid.uuid4().hex}.jpg", contenu, save=False)
                except Exception:  # image atypique : on garde l'original
                    try:
                        fichier.file.seek(0)
                    except Exception:
                        pass
        super().save(*args, **kwargs)


# ---------------------------------------------------------------- configuration
class ParametresSite(models.Model):
    """Réglages modifiables depuis l'administration (une seule ligne)."""

    nom_site = models.CharField("Nom du site", max_length=80, default="Fête & Services")
    slogan = models.CharField(
        max_length=160, blank=True, default="Les meilleurs prestataires pour vos événements"
    )
    email_contact = models.EmailField("E-mail de contact", blank=True)
    whatsapp_admin = models.CharField("WhatsApp de l'équipe", max_length=30, blank=True)
    raison_sociale = models.CharField("Raison sociale", max_length=160, blank=True)
    forme_juridique = models.CharField("Forme juridique", max_length=80, blank=True, help_text="Ex. SARL, entreprise individuelle")
    adresse_siege = models.CharField("Adresse du siège", max_length=250, blank=True)
    ville_siege = models.CharField("Ville du siège (tribunaux compétents)", max_length=80, default="Douala")
    rccm = models.CharField("N° RCCM", max_length=60, blank=True)
    niu = models.CharField("N° d'identifiant unique (NIU)", max_length=60, blank=True)
    directeur_publication = models.CharField("Directeur de la publication", max_length=120, blank=True)
    telephone_contact = models.CharField("Téléphone de contact", max_length=30, blank=True)
    hebergeur_nom = models.CharField("Hébergeur du site", max_length=120, blank=True)
    hebergeur_adresse = models.CharField("Adresse de l'hébergeur", max_length=250, blank=True)
    hebergeur_pays = models.CharField("Pays d'hébergement des données", max_length=80, blank=True)
    numero_mtn_momo = models.CharField("Numéro MTN MoMo", max_length=30, blank=True)
    numero_orange_money = models.CharField("Numéro Orange Money", max_length=30, blank=True)
    beneficiaire_paiement = models.CharField("Nom du bénéficiaire", max_length=120, blank=True)
    version_app_actuelle = models.CharField(
        "Dernière version de l'application mobile", max_length=20, default="1.1.0",
        help_text="Quand vous changez ce numéro, tous les utilisateurs reçoivent la notification « Mise à jour disponible ».",
    )
    lien_telechargement_app = models.URLField(
        "Lien de téléchargement de l'application", blank=True,
        help_text="Page ou fichier APK ouvert depuis la notification de mise à jour.",
    )
    instructions_paiement = models.TextField(
        "Instructions de paiement",
        default=(
            "Envoyez le montant de la formule choisie au numéro Mobile Money indiqué, "
            "puis saisissez la référence de la transaction. Votre abonnement est activé "
            "après vérification, en général sous 24 heures."
        ),
    )

    class Meta:
        verbose_name = "Paramètres du site"
        verbose_name_plural = "Paramètres du site"

    def __str__(self):
        return "Paramètres du site"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return None

    @classmethod
    def charger(cls):
        objet, _ = cls.objects.get_or_create(pk=1)
        return objet

    @property
    def editeur(self):
        return self.raison_sociale or self.nom_site

    @property
    def whatsapp_lien(self):
        numero = normaliser_telephone(self.whatsapp_admin)
        return f"https://wa.me/{numero}" if numero else ""


class Ville(models.Model):
    nom = models.CharField(max_length=80, unique=True)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "nom"]

    def __str__(self):
        return self.nom


class Categorie(models.Model):
    """Type de prestataire (Traiteur, DJ, Salle…) et champs spécifiques à renseigner."""

    slug = models.SlugField(unique=True)
    nom = models.CharField(max_length=60)
    emoji = models.CharField(max_length=8, default="🎉")
    icone_flet = models.CharField(
        "Icône Flet", max_length=60, default="STAR", help_text="Nom dans ft.Icons, ex. RESTAURANT"
    )
    couleur = models.CharField(max_length=7, default="#C23B66", help_text="Format #RRGGBB")
    description = models.CharField(max_length=160, blank=True)
    champs = models.JSONField(
        default=list,
        blank=True,
        help_text='Liste de {"label": "...", "placeholder": "..."} demandée à l\'inscription',
    )
    ordre = models.PositiveSmallIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordre", "nom"]

    def __str__(self):
        return self.nom


# ---------------------------------------------------------------- comptes
class Profil(models.Model):
    VISITEUR = "visiteur"
    PRESTATAIRE = "prestataire"
    ROLES = [(VISITEUR, "Visiteur"), (PRESTATAIRE, "Prestataire")]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profil")
    role = models.CharField(max_length=12, choices=ROLES, default=VISITEUR)
    telephone = models.CharField(max_length=30, blank=True)
    ville = models.ForeignKey(Ville, null=True, blank=True, on_delete=models.SET_NULL)
    cgu_acceptees_le = models.DateTimeField("CGU acceptées le", null=True, blank=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.role})"


class ApiToken(models.Model):
    """Jeton d'authentification utilisé par l'application Flet."""

    cle = models.CharField(max_length=40, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tokens")
    cree_le = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.cle:
            self.cle = secrets.token_hex(20)
        super().save(*args, **kwargs)

    @classmethod
    def pour(cls, user):
        jeton = cls.objects.filter(user=user).first()
        return jeton or cls.objects.create(user=user)

    def __str__(self):
        return f"Jeton de {self.user}"


# ---------------------------------------------------------------- prestataires
class PrestataireQuerySet(models.QuerySet):
    def visibles(self):
        """Prestataires validés avec un abonnement en cours."""
        maintenant = timezone.now()
        en_cours = Abonnement.objects.filter(
            prestataire=OuterRef("pk"),
            statut=Abonnement.ACTIF,
            debut__lte=maintenant,
            fin__gte=maintenant,
        )
        return self.filter(statut=Prestataire.VALIDE).filter(Exists(en_cours))

    def en_avant(self):
        maintenant = timezone.now()
        premium = Abonnement.objects.filter(
            prestataire=OuterRef("pk"),
            statut=Abonnement.ACTIF,
            debut__lte=maintenant,
            fin__gte=maintenant,
            plan__mis_en_avant=True,
        )
        return self.filter(Exists(premium))

    def avec_note(self):
        moyenne = (
            Avis.objects.filter(prestataire=OuterRef("pk"))
            .values("prestataire")
            .annotate(m=Avg("note"))
            .values("m")
        )
        nombre = (
            Avis.objects.filter(prestataire=OuterRef("pk"))
            .values("prestataire")
            .annotate(c=Count("pk"))
            .values("c")
        )
        return self.annotate(
            note_moy=Subquery(moyenne, output_field=FloatField()),
            nb_avis_calc=Coalesce(Subquery(nombre, output_field=IntegerField()), 0),
        )


class Prestataire(ImageOptimiseeMixin, models.Model):
    EN_ATTENTE, VALIDE, REFUSE, SUSPENDU = "attente", "valide", "refuse", "suspendu"
    STATUTS = [
        (EN_ATTENTE, "En attente de validation"),
        (VALIDE, "Validé"),
        (REFUSE, "Refusé"),
        (SUSPENDU, "Suspendu"),
    ]
    champs_images = ("logo", "couverture")

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="prestataire")
    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="prestataires")
    nom = models.CharField("Nom de l'entreprise ou du prestataire", max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    telephone = models.CharField("Téléphone", max_length=30)
    whatsapp = models.CharField("WhatsApp", max_length=30, blank=True, help_text="Laissez vide pour utiliser le téléphone")
    ville = models.ForeignKey(Ville, on_delete=models.PROTECT, related_name="prestataires")
    adresse = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(upload_to=chemin_logo, blank=True)
    couverture = models.ImageField("Photo de couverture", upload_to=chemin_couverture, blank=True)
    details = models.JSONField(default=dict, blank=True)
    statut = models.CharField(max_length=10, choices=STATUTS, default=EN_ATTENTE)
    motif_refus = models.CharField(max_length=200, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    mis_a_jour = models.DateTimeField(auto_now=True)

    objects = PrestataireQuerySet.as_manager()

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nom)[:120] or "prestataire"
            slug, i = base, 2
            while Prestataire.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("prestataire", args=[self.slug])

    # --- contact
    @property
    def whatsapp_numero(self):
        return normaliser_telephone(self.whatsapp or self.telephone)

    @property
    def lien_whatsapp(self):
        numero = self.whatsapp_numero
        return f"https://wa.me/{numero}" if numero else ""

    # --- notes
    @property
    def note(self):
        if hasattr(self, "note_moy"):
            return self.note_moy
        return self.avis.aggregate(m=Avg("note"))["m"]

    @property
    def nombre_avis(self):
        if hasattr(self, "nb_avis_calc"):
            return self.nb_avis_calc
        return self.avis.count()

    # --- abonnement
    def abonnement_en_cours(self):
        maintenant = timezone.now()
        return (
            self.abonnements.filter(statut=Abonnement.ACTIF, debut__lte=maintenant, fin__gte=maintenant)
            .select_related("plan")
            .order_by("-fin")
            .first()
        )

    @property
    def est_visible(self):
        return self.statut == self.VALIDE and self.abonnement_en_cours() is not None

    def limites(self):
        """(photos max, offres max) selon la formule active."""
        abo = self.abonnement_en_cours()
        if abo:
            return abo.plan.max_photos, abo.plan.max_offres
        return LIMITE_PHOTOS_SANS_ABONNEMENT, LIMITE_OFFRES_SANS_ABONNEMENT

    @property
    def image_principale(self):
        if self.couverture:
            return self.couverture
        if self.logo:
            return self.logo
        photo = self.photos.first()
        return photo.image if photo else None


class Photo(ImageOptimiseeMixin, models.Model):
    """Galerie de réalisations du prestataire."""

    champs_images = ("image",)
    prestataire = models.ForeignKey(Prestataire, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=chemin_photo)
    legende = models.CharField(max_length=120, blank=True)
    ordre = models.PositiveSmallIntegerField(default=0)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordre", "-cree_le"]

    def __str__(self):
        return self.legende or f"Photo {self.pk}"


class Offre(ImageOptimiseeMixin, models.Model):
    """Produit ou service proposé (ex. « Verres à pied, lot de 100 »)."""

    champs_images = ("image",)
    prestataire = models.ForeignKey(Prestataire, on_delete=models.CASCADE, related_name="offres")
    titre = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    prix = models.PositiveIntegerField("Prix (FCFA)", null=True, blank=True, help_text="Laissez vide pour « Sur devis »")
    unite_prix = models.CharField("Unité", max_length=40, blank=True, help_text="ex. par jour, le lot, par invité")
    image = models.ImageField(upload_to=chemin_offre, blank=True)
    actif = models.BooleanField("Visible", default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return self.titre


# ---------------------------------------------------------------- abonnements
class Plan(models.Model):
    nom = models.CharField(max_length=60)
    slug = models.SlugField(unique=True)
    prix_fcfa = models.PositiveIntegerField("Prix (FCFA)")
    duree_jours = models.PositiveIntegerField("Durée (jours)", default=30)
    max_photos = models.PositiveIntegerField(default=6)
    max_offres = models.PositiveIntegerField(default=6)
    mis_en_avant = models.BooleanField("Mis en avant sur l'accueil", default=False)
    description = models.CharField(max_length=160, blank=True)
    avantages = models.TextField(blank=True, help_text="Un avantage par ligne")
    ordre = models.PositiveSmallIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordre", "prix_fcfa"]

    def __str__(self):
        return f"{self.nom} ({self.prix_fcfa} FCFA)"

    @property
    def avantages_liste(self):
        return [ligne.strip() for ligne in self.avantages.splitlines() if ligne.strip()]


class Abonnement(models.Model):
    ATTENTE, ACTIF, REJETE = "attente", "actif", "rejete"
    STATUTS = [(ATTENTE, "Paiement à vérifier"), (ACTIF, "Actif"), (REJETE, "Rejeté")]
    MTN, ORANGE = "mtn_momo", "orange_money"
    METHODES = [(MTN, "MTN MoMo"), (ORANGE, "Orange Money")]

    prestataire = models.ForeignKey(Prestataire, on_delete=models.CASCADE, related_name="abonnements")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    statut = models.CharField(max_length=8, choices=STATUTS, default=ATTENTE)
    methode = models.CharField("Moyen de paiement", max_length=14, choices=METHODES, default=MTN)
    telephone_paiement = models.CharField("Numéro utilisé pour payer", max_length=30)
    reference_paiement = models.CharField("Référence de la transaction", max_length=60)
    montant = models.PositiveIntegerField("Montant (FCFA)")
    debut = models.DateTimeField(null=True, blank=True)
    fin = models.DateTimeField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    valide_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.prestataire} — {self.plan.nom} ({self.get_statut_display()})"

    def activer(self):
        """Active l'abonnement ; un renouvellement démarre à la fin de l'abonnement en cours."""
        maintenant = timezone.now()
        derniere_fin = (
            self.prestataire.abonnements.filter(statut=self.ACTIF, fin__gte=maintenant)
            .exclude(pk=self.pk)
            .order_by("-fin")
            .values_list("fin", flat=True)
            .first()
        )
        self.debut = max(maintenant, derniere_fin) if derniere_fin else maintenant
        self.fin = self.debut + timedelta(days=self.plan.duree_jours)
        self.statut = self.ACTIF
        self.valide_le = maintenant
        self.save()

    @property
    def jours_restants(self):
        if not self.fin:
            return 0
        return max(0, (self.fin - timezone.now()).days)

    @property
    def en_cours(self):
        maintenant = timezone.now()
        return bool(self.statut == self.ACTIF and self.debut and self.fin and self.debut <= maintenant <= self.fin)


# ---------------------------------------------------------------- interactions
class Avis(models.Model):
    prestataire = models.ForeignKey(Prestataire, on_delete=models.CASCADE, related_name="avis")
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name="avis_donnes")
    note = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    commentaire = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]
        unique_together = [("prestataire", "auteur")]
        verbose_name_plural = "avis"

    def __str__(self):
        return f"{self.note}/5 — {self.prestataire}"


class Demande(models.Model):
    """Demande de devis envoyée par un visiteur à un prestataire."""

    NOUVELLE, LUE, TRAITEE = "nouvelle", "lue", "traitee"
    STATUTS = [(NOUVELLE, "Nouvelle"), (LUE, "Lue"), (TRAITEE, "Traitée")]

    prestataire = models.ForeignKey(Prestataire, on_delete=models.CASCADE, related_name="demandes")
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name="demandes_envoyees")
    nom_contact = models.CharField("Votre nom", max_length=120)
    telephone = models.CharField("Votre téléphone WhatsApp", max_length=30)
    type_fete = models.CharField("Type de fête", max_length=80, help_text="Mariage, baptême, anniversaire…")
    date_evenement = models.DateField("Date de l'événement", null=True, blank=True)
    budget = models.CharField("Budget", max_length=60, blank=True)
    message = models.TextField(blank=True)
    statut = models.CharField(max_length=8, choices=STATUTS, default=NOUVELLE)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.type_fete} → {self.prestataire}"

    @property
    def lien_whatsapp(self):
        numero = normaliser_telephone(self.telephone)
        return f"https://wa.me/{numero}" if numero else ""


# ---------------------------------------------------------------- notifications
class Notification(models.Model):
    """Notification affichée dans l'application mobile.

    destinataire vide  -> diffusée à tous les utilisateurs (nouvelles offres, mises à jour…)
    destinataire rempli -> privée (demande de devis reçue, abonnement activé…)
    """

    OFFRE, PRESTATAIRE, ESPACE, APPLICATION, ANNONCE = "offre", "prestataire", "espace", "application", "annonce"
    TYPES = [
        (OFFRE, "Nouvelle offre ou changement de prix"),
        (PRESTATAIRE, "Nouveau prestataire ou mise à jour d'un prestataire"),
        (ESPACE, "Activité personnelle (demande, avis, abonnement)"),
        (APPLICATION, "Mise à jour de l'application"),
        (ANNONCE, "Annonce ou promotion de l'équipe"),
    ]

    destinataire = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications",
        help_text="Laissez vide pour envoyer à tous les utilisateurs.",
    )
    auteur = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False,
        help_text="Celui qui a déclenché la notification : il ne la reçoit pas.",
    )
    type = models.CharField(max_length=12, choices=TYPES, default=ANNONCE)
    titre = models.CharField(max_length=120)
    message = models.CharField(max_length=300, blank=True)
    route = models.CharField(
        "Écran à ouvrir", max_length=160, blank=True,
        help_text="Ex. /prestataire/mon-traiteur ou /recherche. Vide = centre de notifications.",
    )
    reference = models.CharField(max_length=80, blank=True, db_index=True, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.titre
