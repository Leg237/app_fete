"""Génère les images de l'application Flet dans flet_app/assets/ :

    icon.png    1024x1024  icône de l'application (lue par `flet build`)
    splash.png  1152x1152  logo sur fond transparent (écran de démarrage natif ; couleur dans pyproject.toml)
    logo.png     512x512   logo transparent affiché par l'écran de chargement de l'application

Pour utiliser votre propre logo, remplacez simplement ces fichiers (mêmes noms) ou modifiez les
couleurs/lettres ci-dessous puis relancez :   python outils/generer_assets.py    (nécessite Pillow)
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AUB, AUB2, OR, CHAMP, ROSE = "#2A1840", "#3B2459", "#B8913A", "#E9D5A1", "#C23B66"
LETTRES = "F&S"
POLICES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
]
SORTIE = Path(__file__).resolve().parent.parent / "flet_app" / "assets"
SS = 2  # sur-échantillonnage pour des bords lisses


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def degrade(taille, c1, c2):
    """Dégradé diagonal c1 -> c2."""
    a, b = rgb(c1), rgb(c2)
    img = Image.new("RGB", (taille, taille))
    px = img.load()
    for y in range(taille):
        for x in range(taille):
            t = (x + y) / (2 * taille - 2)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return img


def police(taille):
    for chemin in POLICES:
        try:
            return ImageFont.truetype(chemin, taille)
        except OSError:
            continue
    return ImageFont.load_default()


def logo(n, fond):
    """Dessine le logo sur un carré de n pixels. fond=True : fond dégradé opaque (icône)."""
    N = n * SS
    img = degrade(N, AUB, AUB2).convert("RGBA") if fond else Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = N / 2
    R = N * 0.215  # rayon de l'anneau : tout reste dans le cercle central (zone sûre des icônes adaptatives)

    # confettis autour de l'anneau
    hasard = random.Random(7)
    couleurs = [ROSE, OR, CHAMP, "#FFFFFF", "#E26D93"]
    for i in range(34):
        angle = i / 34 * 2 * math.pi + hasard.uniform(-0.09, 0.09)
        dist = N * hasard.uniform(0.275, 0.320)
        x, y = c + math.cos(angle) * dist, c + math.sin(angle) * dist
        col = rgb(random.Random(i).choice(couleurs))
        t = N * hasard.uniform(0.007, 0.013)
        if i % 3 == 0:
            d.ellipse([x - t, y - t, x + t, y + t], fill=col)
        else:
            rot = hasard.uniform(0, math.pi)
            l1, l2 = t * 1.9, t * 0.8
            pts = [(x + math.cos(rot) * dx - math.sin(rot) * dy, y + math.sin(rot) * dx + math.cos(rot) * dy)
                   for dx, dy in ((-l1, -l2), (l1, -l2), (l1, l2), (-l1, l2))]
            d.polygon(pts, fill=col)

    # anneau doré (dégradé) + disque aubergine
    anneau = degrade(N, CHAMP, OR).convert("RGBA")
    masque = Image.new("L", (N, N), 0)
    ImageDraw.Draw(masque).ellipse([c - R, c - R, c + R, c + R], fill=255)
    img.paste(anneau, (0, 0), masque)
    ep = R * 0.085
    d.ellipse([c - R + ep, c - R + ep, c + R - ep, c + R - ep], fill=rgb(AUB))

    # lettres
    f = police(int(R * 0.64))
    boite = d.textbbox((0, 0), LETTRES, font=f)
    w, h = boite[2] - boite[0], boite[3] - boite[1]
    d.text((c - w / 2 - boite[0], c - h / 2 - boite[1] - R * 0.02), LETTRES, font=f, fill=rgb(CHAMP))

    # étincelle en haut à droite de l'anneau
    sx, sy, r = c + R * 0.78, c - R * 0.78, R * 0.20
    d.polygon([(sx, sy - r), (sx + r * .28, sy - r * .28), (sx + r, sy), (sx + r * .28, sy + r * .28),
               (sx, sy + r), (sx - r * .28, sy + r * .28), (sx - r, sy), (sx - r * .28, sy - r * .28)], fill=rgb("#FFFFFF"))
    return img.resize((n, n), Image.LANCZOS)


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    logo(1024, fond=True).convert("RGB").save(SORTIE / "icon.png")
    logo(1152, fond=False).save(SORTIE / "splash.png")
    logo(512, fond=False).save(SORTIE / "logo.png")
    print("Images écrites dans", SORTIE)


if __name__ == "__main__":
    main()
