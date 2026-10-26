"""Données de départ.

    python manage.py seed_demo           -> villes, catégories, formules, paramètres
    python manage.py seed_demo --demo    -> + prestataires de démonstration avec images générées
"""
import random
import textwrap
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.models import (
    Abonnement,
    Avis,
    Categorie,
    Demande,
    Offre,
    ParametresSite,
    Photo,
    Plan,
    Prestataire,
    Profil,
    Ville,
)

VILLES = ["Douala", "Yaoundé", "Bafoussam", "Bamenda", "Garoua", "Maroua", "Ngaoundéré", "Bertoua",
          "Kribi", "Limbé", "Buea", "Ebolowa", "Dschang"]

# slug, nom, emoji, icône Flet, couleur, description, champs
CATEGORIES = [
    ("restaurateur", "Restaurateur", "🍽️", "RESTAURANT", "#F57C00", "Plats et repas pour vos invités",
     [("Spécialités", "Ndolé, poulet DG, grillades"), ("Capacité / jour", "Ex : 100 plats")]),
    ("restauratrice", "Restauratrice", "🍲", "RESTAURANT_MENU", "#FFA726", "Cuisine maison et plats du jour",
     [("Spécialités", "Eru, koki, achu"), ("Menu du jour", "Ex : 2 500 FCFA")]),
    ("livraison", "Livraison", "🛵", "DELIVERY_DINING", "#E53935", "Société de livraison",
     [("Type de véhicule", "Moto, voiture, tricycle"), ("Zone de livraison", "Douala et environs")]),
    ("livreur", "Livreur", "🏍️", "TWO_WHEELER", "#EF5350", "Livreur indépendant",
     [("Permis", "A, B"), ("Disponibilité", "Jour, nuit")]),
    ("location-couverts", "Location de couverts", "🥂", "TABLE_RESTAURANT", "#00897B", "Assiettes, verres, chaises, tables",
     [("Matériel disponible", "Assiettes, verres, chaises, tables"), ("Quantité maximale", "Ex : 500 couverts")]),
    ("gateaux-patisserie", "Gâteaux et pâtisserie", "🎂", "CAKE", "#EC407A", "Gâteaux d'anniversaire et de mariage",
     [("Types de gâteaux", "Anniversaire, mariage"), ("Délai de commande", "Ex : 48 h")]),
    ("service-complementaire", "Service complémentaire", "🤝", "MISCELLANEOUS_SERVICES", "#3949AB", "Serveurs, sécurité, hôtesses",
     [("Service proposé", "Serveur, sécurité, hôtesse"), ("Tarif", "Par heure ou par jour")]),
    ("traiteur", "Traiteur", "🍱", "SOUP_KITCHEN", "#FFA000", "Buffets et cocktails",
     [("Spécialités", "Buffet, cocktail"), ("Invités maximum", "Ex : 500")]),
    ("dj", "DJ", "🎧", "MUSIC_NOTE", "#8E24AA", "Animation musicale",
     [("Matériel", "Platines, sono"), ("Style musical", "Afrobeat, makossa, bikutsi")]),
    ("decorateur", "Décorateur", "💐", "BRUSH", "#43A047", "Décoration de salles et d'événements",
     [("Thèmes", "Mariage, baptême"), ("Style de décoration", "Moderne, traditionnel")]),
    ("photographe", "Photographe", "📸", "CAMERA_ALT", "#1E88E5", "Photo et vidéo",
     [("Appareil", "Canon R6"), ("Livraison des photos", "Clé USB, Drive")]),
    ("salle", "Salle", "🏛️", "HOME_WORK", "#8D6E63", "Salles de fête et de réception",
     [("Capacité", "Ex : 200 places"), ("Adresse de la salle", "Quartier, repère")]),
]

PLANS = [
    ("essentiel", "Essentiel", 5000, 30, 6, 6, False, "Pour démarrer",
     "Profil visible par tous les clients\n6 photos dans la galerie\n6 offres avec photo\nDemandes de devis par WhatsApp"),
    ("pro", "Pro", 12000, 90, 20, 20, True, "Le plus choisi",
     "Tout Essentiel pendant 3 mois\n20 photos et 20 offres\nMise en avant sur la page d'accueil\nAccompagnement par l'équipe"),
    ("premium", "Premium", 40000, 365, 60, 60, True, "Pour les professionnels",
     "Tout Pro pendant 12 mois\n60 photos et 60 offres\nMise en avant toute l'année\nPriorité de validation"),
]

# nom, catégorie, ville, téléphone, formule, statut, offres [(titre, prix, unité)]
DEMO = [
    ("Mama Thieb", "restaurateur", "Douala", "677 12 34 56", "pro", "valide",
     [("Ndolé aux crevettes", 3500, "la portion"), ("Poulet DG", 4000, "la portion"), ("Plateau buffet 20 personnes", 65000, "le plateau")]),
    ("Location Fatou", "location-couverts", "Yaoundé", "699 98 76 54", "premium", "valide",
     [("Assiettes en porcelaine, lot de 100", 15000, "par jour"), ("Verres à pied, lot de 100", 10000, "par jour"),
      ("Chaises Chiavari dorées", 500, "la chaise"), ("Tables rondes, 10 personnes", 3000, "la table")]),
    ("Rapide Livraison", "livreur", "Douala", "670 11 22 33", None, "attente", []),
    ("Sweet Cake Douala", "gateaux-patisserie", "Douala", "676 55 44 33", "pro", "valide",
     [("Gâteau d'anniversaire, 20 parts", 25000, ""), ("Pièce montée de mariage", None, ""), ("Cupcakes", 6000, "la douzaine")]),
    ("DJ Kamer Vibes", "dj", "Bafoussam", "655 40 20 10", "essentiel", "valide",
     [("Soirée complète, sono incluse", 150000, "la soirée"), ("Animation de baptême", 80000, "")]),
    ("Salle Les Jardins", "salle", "Yaoundé", "699 10 20 30", "premium", "valide",
     [("Salle de réception, 300 places", 350000, "la journée"), ("Terrasse extérieure", 120000, "la journée")]),
    ("Studio Éclat", "photographe", "Douala", "677 90 80 70", "pro", "valide",
     [("Reportage de mariage", 200000, ""), ("Séance de couple", 50000, "")]),
]


def image_demo(titre, couleur, taille=(1200, 800)):
    """Image de démonstration (dégradé + cercles + titre) générée avec Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = taille
    base = tuple(int(couleur[i:i + 2], 16) for i in (1, 3, 5))
    sombre = tuple(int(c * 0.42) for c in base)
    img = Image.new("RGB", taille, sombre)
    trace = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        trace.line([(0, y), (w, y)], fill=tuple(int(base[i] * (1 - t) + sombre[i] * t) for i in range(3)))
    hasard = random.Random(titre)
    calque = Image.new("RGBA", taille, (0, 0, 0, 0))
    cercle = ImageDraw.Draw(calque)
    for _ in range(7):
        r, x, y = hasard.randint(70, 280), hasard.randint(0, w), hasard.randint(0, h)
        cercle.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, hasard.randint(16, 42)))
    img = Image.alpha_composite(img.convert("RGBA"), calque).convert("RGB")
    dessin = ImageDraw.Draw(img)
    try:
        police = ImageFont.load_default(size=h // 11)
    except TypeError:
        police = ImageFont.load_default()
    texte = "\n".join(textwrap.wrap(titre, width=20))
    boite = dessin.multiline_textbbox((0, 0), texte, font=police, align="center", spacing=10)
    x = (w - (boite[2] - boite[0])) / 2
    y = (h - (boite[3] - boite[1])) / 2
    dessin.multiline_text((x, y), texte, font=police, fill="white", align="center", spacing=10)
    tampon = BytesIO()
    img.save(tampon, "JPEG", quality=84)
    return ContentFile(tampon.getvalue(), name="demo.jpg")


class Command(BaseCommand):
    help = "Crée les données de base (et des prestataires de démonstration avec --demo)."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Ajoute des prestataires de démonstration")

    def handle(self, *args, **options):
        ParametresSite.charger()
        for i, nom in enumerate(VILLES):
            Ville.objects.get_or_create(nom=nom, defaults={"ordre": i})
        for i, (slug, nom, emoji, icone, couleur, desc, champs) in enumerate(CATEGORIES):
            Categorie.objects.update_or_create(
                slug=slug,
                defaults={"nom": nom, "emoji": emoji, "icone_flet": icone, "couleur": couleur,
                          "description": desc, "ordre": i,
                          "champs": [{"label": a, "placeholder": b} for a, b in champs]},
            )
        for i, (slug, nom, prix, duree, photos, offres, avant, desc, avantages) in enumerate(PLANS):
            Plan.objects.update_or_create(
                slug=slug,
                defaults={"nom": nom, "prix_fcfa": prix, "duree_jours": duree, "max_photos": photos,
                          "max_offres": offres, "mis_en_avant": avant, "description": desc,
                          "avantages": avantages, "ordre": i},
            )
        self.stdout.write(self.style.SUCCESS("Villes, catégories et formules prêtes."))
        self.stdout.write("Pensez à renseigner vos numéros MTN MoMo / Orange Money dans Admin > Paramètres du site.")
        if options["demo"]:
            self.demo()

    def demo(self):
        client, cree = User.objects.get_or_create(username="client@demo.cm", defaults={"email": "client@demo.cm", "first_name": "Aïcha Demo"})
        if cree:
            client.set_password("demo1234")
            client.save()
            Profil.objects.create(user=client, role=Profil.VISITEUR, telephone="690 00 00 00", ville=Ville.objects.get(nom="Douala"))

        for nom, cat_slug, ville, tel, plan_slug, statut, offres in DEMO:
            categorie = Categorie.objects.get(slug=cat_slug)
            email = f"{cat_slug}@demo.cm"
            if User.objects.filter(username=email).exists():
                continue
            user = User.objects.create_user(username=email, email=email, password="demo1234", first_name=nom)
            Profil.objects.create(user=user, role=Profil.PRESTATAIRE, telephone=tel, ville=Ville.objects.get(nom=ville))
            p = Prestataire.objects.create(
                user=user, categorie=categorie, nom=nom, telephone=tel, ville=Ville.objects.get(nom=ville),
                statut=statut, adresse=f"Centre-ville, {ville}",
                description=f"{nom} vous accompagne pour vos mariages, baptêmes et anniversaires à {ville}. "
                            "Service soigné, tarifs clairs et réponse rapide sur WhatsApp.",
                details={c["label"]: c["placeholder"].replace("Ex : ", "") for c in categorie.champs},
            )
            p.logo.save("logo.jpg", image_demo(nom[:2].upper(), categorie.couleur, (400, 400)), save=False)
            p.couverture.save("couv.jpg", image_demo(nom, categorie.couleur), save=False)
            p.save()
            for titre, prix, unite in offres:
                offre = Offre(prestataire=p, titre=titre, prix=prix, unite_prix=unite,
                              description=f"{titre}. Contactez-nous pour la disponibilité à votre date.")
                offre.image.save("offre.jpg", image_demo(titre, categorie.couleur, (900, 700)), save=False)
                offre.save()
            for i in range(3):
                photo = Photo(prestataire=p, legende=f"Réalisation {i + 1}")
                photo.image.save("photo.jpg", image_demo(f"{nom} {i + 1}", categorie.couleur, (1000, 750)), save=False)
                photo.save()
            if plan_slug:
                abo = Abonnement.objects.create(
                    prestataire=p, plan=Plan.objects.get(slug=plan_slug), montant=Plan.objects.get(slug=plan_slug).prix_fcfa,
                    methode=Abonnement.MTN, telephone_paiement=tel, reference_paiement="DEMO-" + email[:6],
                )
                abo.activer()
                Avis.objects.create(prestataire=p, auteur=client, note=random.choice([4, 5, 5]), commentaire="Très bon service, je recommande.")
                Demande.objects.create(prestataire=p, auteur=client, nom_contact="Aïcha Demo", telephone="690 00 00 00",
                                       type_fete="Mariage", budget="500 000 FCFA", message="Bonjour, êtes-vous disponible en décembre ?")
        self.stdout.write(self.style.SUCCESS("Démo créée. Comptes : <slug-catégorie>@demo.cm et client@demo.cm, mot de passe demo1234."))
