from django.contrib import admin, messages
from django.utils import timezone

from .models import (
    Abonnement,
    ApiToken,
    Avis,
    Campagne,
    Categorie,
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

admin.site.site_header = "Fête & Services — administration"
admin.site.site_title = "Fête & Services"
admin.site.index_title = "Gérer la plateforme"


@admin.register(ParametresSite)
class ParametresSiteAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Identité du site", {"fields": ("nom_site", "slogan", "email_contact", "telephone_contact", "whatsapp_admin")}),
        ("Informations légales (pages CGU, mentions légales, confidentialité)", {
            "description": "Ces informations sont affichées sur les pages légales. Complétez-les avant la mise en ligne.",
            "fields": ("raison_sociale", "forme_juridique", "adresse_siege", "ville_siege", "rccm", "niu", "directeur_publication",
                       "hebergeur_nom", "hebergeur_adresse", "hebergeur_pays")}),
        ("Application mobile", {
            "description": "Changer la version déclenche une notification « Mise à jour disponible » chez tous les utilisateurs.",
            "fields": ("url_serveur", "version_app_actuelle", "lien_telechargement_app")}),
        ("Paiement Mobile Money", {"fields": ("numero_mtn_momo", "numero_orange_money", "beneficiaire_paiement", "instructions_paiement")}),
    ]

    def has_add_permission(self, request):
        return not ParametresSite.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Ville)
class VilleAdmin(admin.ModelAdmin):
    list_display = ("nom", "ordre")
    list_editable = ("ordre",)


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("emoji", "nom", "slug", "couleur", "ordre", "actif")
    list_editable = ("ordre", "actif")
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("nom", "prix_fcfa", "duree_jours", "max_photos", "max_offres", "mis_en_avant", "actif", "ordre")
    list_editable = ("ordre", "actif")
    prepopulated_fields = {"slug": ("nom",)}


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0


class OffreInline(admin.TabularInline):
    model = Offre
    extra = 0


class AbonnementInline(admin.TabularInline):
    model = Abonnement
    extra = 0
    readonly_fields = ("cree_le",)


@admin.register(Prestataire)
class PrestataireAdmin(admin.ModelAdmin):
    list_display = ("nom", "categorie", "ville", "statut", "en_ligne", "cree_le")
    list_filter = ("statut", "categorie", "ville")
    search_fields = ("nom", "telephone", "user__email")
    inlines = [AbonnementInline, OffreInline, PhotoInline]
    actions = ["valider", "refuser", "suspendre"]

    @admin.display(boolean=True, description="En ligne")
    def en_ligne(self, obj):
        return obj.est_visible

    @admin.action(description="Valider les prestataires sélectionnés")
    def valider(self, request, queryset):
        n = 0
        for p in queryset:  # save() et non update() : déclenche la notification au prestataire
            p.statut, p.motif_refus = Prestataire.VALIDE, ""
            p.save()
            n += 1
        self.message_user(request, f"{n} prestataire(s) validé(s).", messages.SUCCESS)

    @admin.action(description="Refuser les prestataires sélectionnés")
    def refuser(self, request, queryset):
        n = 0
        for p in queryset:
            p.statut = Prestataire.REFUSE
            p.save()
            n += 1
        self.message_user(request, f"{n} prestataire(s) refusé(s). Précisez le motif dans la fiche.", messages.WARNING)

    @admin.action(description="Suspendre les prestataires sélectionnés")
    def suspendre(self, request, queryset):
        n = 0
        for p in queryset:
            p.statut = Prestataire.SUSPENDU
            p.save()
            n += 1
        self.message_user(request, f"{n} prestataire(s) suspendu(s).", messages.WARNING)


@admin.register(Abonnement)
class AbonnementAdmin(admin.ModelAdmin):
    list_display = ("prestataire", "plan", "montant", "methode", "reference_paiement", "statut", "fin", "cree_le")
    list_filter = ("statut", "methode", "plan")
    search_fields = ("prestataire__nom", "reference_paiement", "telephone_paiement")
    actions = ["activer", "rejeter"]

    @admin.action(description="Confirmer le paiement et activer l'abonnement")
    def activer(self, request, queryset):
        n = 0
        for abo in queryset.filter(statut=Abonnement.ATTENTE).select_related("plan", "prestataire"):
            abo.activer()
            n += 1
        self.message_user(request, f"{n} abonnement(s) activé(s).", messages.SUCCESS)

    @admin.action(description="Rejeter le paiement")
    def rejeter(self, request, queryset):
        n = 0
        for abo in queryset.filter(statut=Abonnement.ATTENTE):
            abo.statut, abo.valide_le = Abonnement.REJETE, timezone.now()
            abo.save()
            n += 1
        self.message_user(request, f"{n} paiement(s) rejeté(s).", messages.WARNING)


@admin.register(Avis)
class AvisAdmin(admin.ModelAdmin):
    list_display = ("prestataire", "auteur", "note", "cree_le")
    list_filter = ("note",)


@admin.register(Demande)
class DemandeAdmin(admin.ModelAdmin):
    list_display = ("prestataire", "type_fete", "nom_contact", "date_evenement", "statut", "cree_le")
    list_filter = ("statut",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Envoyez ici une annonce ou une promotion : elle arrive dans l'application de tous les utilisateurs."""

    list_display = ("titre", "type", "destinataire", "cree_le")
    list_filter = ("type",)
    search_fields = ("titre", "message")
    fields = ("type", "titre", "message", "route", "destinataire")


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ("titre", "prestataire", "prix", "actif", "accepte_promo")
    list_filter = ("actif", "accepte_promo")
    search_fields = ("titre", "prestataire__nom")
    filter_horizontal = ("offres",)


@admin.register(Campagne)
class CampagneAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "pourcentage", "categorie", "debut", "fin", "active", "saisies")
    list_filter = ("active", "categorie")
    search_fields = ("nom", "code")
    readonly_fields = ("saisies", "cree_le")


admin.site.register(Profil)
admin.site.register(ApiToken)
