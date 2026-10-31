"""Connexion par nom d'utilisateur (ou, pour les anciens comptes, par adresse e-mail)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


def trouver_utilisateur(identifiant):
    """Retrouve un compte par nom d'utilisateur (sans tenir compte des majuscules), sinon par e-mail unique."""
    User = get_user_model()
    identifiant = (identifiant or "").strip()
    if not identifiant:
        return None
    user = User.objects.filter(username__iexact=identifiant).first()
    if user is None:
        correspondants = list(User.objects.filter(email__iexact=identifiant)[:2])
        user = correspondants[0] if len(correspondants) == 1 else None
    return user


class ConnexionParIdentifiant(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = trouver_utilisateur(username)
        if user is None:
            get_user_model()().set_password(password or "")  # même durée que pour un compte existant
            return None
        if password and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
