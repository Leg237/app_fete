from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from .models import Abonnement, Avis, Demande, Offre, ParametresSite, Photo, Prestataire, Profil, Ville

TAILLE_MAX_IMAGE = 8 * 1024 * 1024  # 8 Mo (réduite ensuite à ~300 Ko)


def verifier_image(fichier):
    if isinstance(fichier, UploadedFile) and fichier.size > TAILLE_MAX_IMAGE:
        raise ValidationError("Image trop lourde (8 Mo maximum).")
    return fichier


class StyleMixin:
    """Ajoute les classes Bootstrap à tous les champs."""

    def styliser(self):
        for champ in self.fields.values():
            widget = champ.widget
            if isinstance(widget, forms.RadioSelect):
                continue
            if isinstance(widget, forms.CheckboxInput):
                classe = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                classe = "form-select"
            else:
                classe = "form-control"
            classes = widget.attrs.get("class", "").split()
            if classe not in classes:
                classes.append(classe)
            widget.attrs["class"] = " ".join(classes)


def ajouter_champs_details(form, categorie, valeurs=None):
    """Ajoute les champs spécifiques à la catégorie (detail_0, detail_1…)."""
    valeurs = valeurs or {}
    for i, champ in enumerate(categorie.champs or []):
        label = champ.get("label", f"Détail {i + 1}")
        form.fields[f"detail_{i}"] = forms.CharField(
            label=label,
            required=False,
            initial=valeurs.get(label, ""),
            widget=forms.TextInput(attrs={"placeholder": champ.get("placeholder", "")}),
        )


def extraire_details(form, categorie):
    return {
        champ.get("label", f"Détail {i + 1}"): (form.cleaned_data.get(f"detail_{i}") or "").strip()
        for i, champ in enumerate(categorie.champs or [])
    }


# ---------------------------------------------------------------- comptes
class ConnexionForm(AuthenticationForm):
    username = forms.CharField(label="Adresse e-mail", widget=forms.EmailInput(attrs={"autofocus": True}))
    password = forms.CharField(label="Mot de passe", strip=False, widget=forms.PasswordInput)

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            champ.widget.attrs["class"] = "form-control"


class InscriptionVisiteurForm(StyleMixin, forms.Form):
    nom_complet = forms.CharField(label="Nom complet", max_length=120)
    email = forms.EmailField(label="Adresse e-mail")
    telephone = forms.CharField(label="Téléphone WhatsApp", max_length=30)
    ville = forms.ModelChoiceField(queryset=Ville.objects.all(), label="Ville", empty_label="Choisir une ville")
    mot_de_passe = forms.CharField(label="Mot de passe", widget=forms.PasswordInput, strip=False)
    mot_de_passe2 = forms.CharField(label="Confirmer le mot de passe", widget=forms.PasswordInput, strip=False)
    accepte_cgu = forms.BooleanField(
        label="J'accepte les conditions d'utilisation et la politique de confidentialité",
        error_messages={"required": "Vous devez accepter les conditions pour créer un compte."},
    )

    role = Profil.VISITEUR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.styliser()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise ValidationError("Un compte existe déjà avec cette adresse. Connectez-vous.")
        return email

    def clean(self):
        donnees = super().clean()
        mdp, mdp2 = donnees.get("mot_de_passe"), donnees.get("mot_de_passe2")
        if mdp:
            try:
                password_validation.validate_password(mdp)
            except ValidationError as erreur:
                self.add_error("mot_de_passe", erreur)
            if mdp2 and mdp != mdp2:
                self.add_error("mot_de_passe2", "Les deux mots de passe ne correspondent pas.")
        return donnees

    @transaction.atomic
    def creer_utilisateur(self):
        d = self.cleaned_data
        user = User.objects.create_user(
            username=d["email"], email=d["email"], password=d["mot_de_passe"], first_name=d["nom_complet"][:150]
        )
        Profil.objects.create(user=user, role=self.role, telephone=d["telephone"], ville=d["ville"], cgu_acceptees_le=timezone.now())
        return user

    def save(self):
        return self.creer_utilisateur()


class InscriptionPrestataireForm(InscriptionVisiteurForm):
    nom = forms.CharField(label="Nom de l'entreprise ou du prestataire", max_length=120)
    role = Profil.PRESTATAIRE

    field_order = ["nom", "nom_complet", "email", "telephone", "ville"]

    def __init__(self, *args, categorie, **kwargs):
        self.categorie = categorie
        super().__init__(*args, **kwargs)
        ajouter_champs_details(self, categorie)
        self.styliser()
        # place les mots de passe en dernier
        for nom in ("mot_de_passe", "mot_de_passe2", "accepte_cgu"):
            self.fields[nom] = self.fields.pop(nom)

    @transaction.atomic
    def save(self):
        user = self.creer_utilisateur()
        d = self.cleaned_data
        Prestataire.objects.create(
            user=user,
            categorie=self.categorie,
            nom=d["nom"],
            telephone=d["telephone"],
            ville=d["ville"],
            details=extraire_details(self, self.categorie),
        )
        return user


# ---------------------------------------------------------------- mot de passe oublié
class MotDePasseOubliForm(PasswordResetForm):
    email = forms.EmailField(
        label="Adresse e-mail",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True, "class": "form-control"}),
    )

    def envoyer(self, request):
        """Envoie le lien de réinitialisation. Une demande par minute et par adresse (anti-abus)."""
        email = self.cleaned_data["email"].strip().lower()
        cle = f"mdp-oublie:{email}"
        if cache.get(cle):
            return False
        cache.set(cle, 1, 60)
        self.save(
            request=request,
            use_https=request.is_secure(),
            subject_template_name="auth/email_reinitialisation_sujet.txt",
            email_template_name="auth/email_reinitialisation.txt",
            html_email_template_name="auth/email_reinitialisation.html",
            extra_email_context={"nom_site": ParametresSite.charger().nom_site},
        )
        return True


class NouveauMotDePasseForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password2"].label = "Confirmer le nouveau mot de passe"
        for champ in self.fields.values():
            champ.widget.attrs["class"] = "form-control"


# ---------------------------------------------------------------- espace prestataire
class PrestataireProfilForm(StyleMixin, forms.ModelForm):
    class Meta:
        model = Prestataire
        fields = ["nom", "description", "telephone", "whatsapp", "ville", "adresse", "logo", "couverture"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "logo": forms.FileInput(attrs={"accept": "image/*"}),
            "couverture": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ajouter_champs_details(self, self.instance.categorie, self.instance.details)
        self.styliser()

    def clean_logo(self):
        return verifier_image(self.cleaned_data.get("logo"))

    def clean_couverture(self):
        return verifier_image(self.cleaned_data.get("couverture"))

    def save(self, commit=True):
        self.instance.details = extraire_details(self, self.instance.categorie)
        return super().save(commit)


class OffreForm(StyleMixin, forms.ModelForm):
    class Meta:
        model = Offre
        fields = ["titre", "description", "prix", "unite_prix", "image", "actif"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "image": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.styliser()

    def clean_image(self):
        return verifier_image(self.cleaned_data.get("image"))


class PhotoForm(StyleMixin, forms.ModelForm):
    class Meta:
        model = Photo
        fields = ["image", "legende"]
        widgets = {"image": forms.FileInput(attrs={"accept": "image/*"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].required = True
        self.styliser()

    def clean_image(self):
        return verifier_image(self.cleaned_data.get("image"))


class AbonnementForm(StyleMixin, forms.ModelForm):
    class Meta:
        model = Abonnement
        fields = ["methode", "telephone_paiement", "reference_paiement"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.styliser()


# ---------------------------------------------------------------- visiteurs
class AvisForm(StyleMixin, forms.ModelForm):
    note = forms.TypedChoiceField(
        choices=[(5, "5"), (4, "4"), (3, "3"), (2, "2"), (1, "1")],
        coerce=int,
        label="Votre note",
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Avis
        fields = ["note", "commentaire"]
        widgets = {"commentaire": forms.Textarea(attrs={"rows": 3, "placeholder": "Racontez votre expérience"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.styliser()


class DemandeForm(StyleMixin, forms.ModelForm):
    class Meta:
        model = Demande
        fields = ["nom_contact", "telephone", "type_fete", "date_evenement", "budget", "message"]
        widgets = {
            "date_evenement": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "message": forms.Textarea(attrs={"rows": 3, "placeholder": "Nombre d'invités, lieu, précisions…"}),
            "type_fete": forms.TextInput(attrs={"placeholder": "Mariage, baptême, anniversaire…"}),
            "budget": forms.TextInput(attrs={"placeholder": "Ex : 500 000 FCFA"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.styliser()
