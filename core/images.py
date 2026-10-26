"""Optimisation des images envoyées (poids réduit pour le mobile)."""
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps


def optimiser(fichier, max_cote=1600, qualite=85):
    """Retourne un ContentFile JPEG redimensionné, orientation EXIF corrigée."""
    image = Image.open(fichier)
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.thumbnail((max_cote, max_cote))
    tampon = BytesIO()
    image.save(tampon, "JPEG", quality=qualite, optimize=True)
    return ContentFile(tampon.getvalue())
