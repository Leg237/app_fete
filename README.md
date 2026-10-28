# Fête & Services — plateforme web (Django + Bootstrap local) et application Flet 0.28.3

Les clients s'inscrivent **gratuitement**. Les prestataires paient un **abonnement** (Mobile Money) et gèrent chacun **leur espace** : profil, logo et couverture, offres avec photo et prix, galerie, demandes de devis. Les images apparaissent sur le site et dans l'application, car les deux lisent les mêmes données.

## 1. Démarrer le site

```bash
python -m venv venv && source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations core                 # première fois uniquement
python manage.py migrate
python manage.py seed_demo --demo                    # villes, catégories, formules + prestataires d'exemple
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

- Site : http://127.0.0.1:8000 — Administration : http://127.0.0.1:8000/admin
- `seed_demo` sans `--demo` crée seulement les données de base. Avec `--demo`, des comptes `<catégorie>@demo.cm` et `client@demo.cm` (mot de passe `demo1234`) sont créés, avec des images générées. À ne pas utiliser en production.
- Dans **Admin > Paramètres du site**, renseignez vos numéros MTN MoMo / Orange Money et le nom du bénéficiaire : ils s'affichent sur la page de paiement.

## 2. Bootstrap en local

`static/vendor/bootstrap/` contient Bootstrap 5.3.2 (CSS + JS), sans CDN. Le CSS fourni est une compilation aux couleurs « Cerulean » ; `static/css/theme.css` applique l'identité de la marque par-dessus. Pour installer la version officielle non thémée :

```bash
python manage.py setup_bootstrap     # internet requis, une seule fois
```

## 3. Flux métier

1. Un prestataire s'inscrit (choix de la catégorie, champs adaptés au métier) et arrive sur son espace.
2. Il prépare sa vitrine et choisit une formule, envoie le montant en Mobile Money, saisit la référence.
3. L'équipe, dans l'admin : **Prestataires > Valider** et **Abonnements > Confirmer le paiement et activer**.
4. Le prestataire est visible **si profil validé ET abonnement actif**. À l'expiration il disparaît automatiquement. Un renouvellement démarre à la fin de l'abonnement en cours.
5. Les visiteurs (compte gratuit) envoient des demandes de devis et laissent des avis. Sans compte, ils peuvent parcourir et écrire sur WhatsApp.

Les formules (prix, durée, nombre de photos/offres, mise en avant) se modifient dans **Admin > Formules**. Les catégories et leurs champs spécifiques dans **Admin > Catégories**.

## 4. Application Flet (dossier `flet_app/`)

```bash
cd flet_app
pip install -r requirements.txt
flet run main.py            # bureau
flet build apk              # Android
```

Adresse du serveur : modifiable dans l'app (**Paramètres > Serveur**) ou via `FETE_API_URL`.
Émulateur Android : `http://10.0.2.2:8000` — téléphone réel : l'IP du PC (`http://192.168.x.x:8000`) ou votre domaine HTTPS.
Android bloque le HTTP en clair sur les versions récentes : utilisez HTTPS en production.

## 5. API (préfixe `/api/v1/`, en-tête `Authorization: Token <clé>`)

`meta/` · `notifications/?apres=<id>` · `prestataires/?q=&categorie=&ville=&page=` · `prestataires/<slug>/` · `prestataires/<slug>/demande/` · `prestataires/<slug>/avis/` · `auth/inscription/` · `auth/connexion/` · `auth/deconnexion/` · `me/` · `me/demandes/` · `espace/` · `espace/profil/` · `espace/offres/` · `espace/offres/<id>/` · `espace/photos/` · `espace/photos/<id>/` · `espace/abonnement/` · `espace/demandes/` · `espace/demandes/<id>/statut/`

## 6. Pages d'erreur, pages légales, mot de passe oublié

**Pages d'erreur** (400, 403, 403 session expirée, 404, 500) au design de la plateforme. La 500 est autonome : elle s'affiche même si la base de données est en panne. En développement (`DEBUG=1`), prévisualisez-les sur `/apercu-erreur/404/`, `/403/`, `/400/`, `/500/` et `/csrf/`. En production (`DEBUG=0`) elles s'affichent automatiquement.

**Pages légales** : `/cgu/`, `/confidentialite/`, `/mentions-legales/`, `/cookies/`, liées dans le pied de page, à l'inscription (case « J'accepte… » obligatoire, date d'acceptation enregistrée) et dans l'application. Un bandeau d'information sur les cookies s'affiche une fois (le site n'utilise que `sessionid` et `csrftoken`). Complétez **Admin > Paramètres du site > Informations légales** (raison sociale, adresse, RCCM, NIU, hébergeur et pays d'hébergement) : ces champs alimentent automatiquement les pages. Ce sont des modèles rédigés selon la loi camerounaise n° 2024/017 sur la protection des données ; faites-les relire par un juriste avant la mise en ligne, notamment les règles sur l'hébergement hors du Cameroun et les formalités auprès de l'Autorité de protection des données.

**Mot de passe oublié** : `/mot-de-passe-oublie/` envoie un lien valable 24 h (page « vérifiez votre e-mail », page de nouveau mot de passe, page de confirmation, lien expiré géré). La réponse est identique que l'adresse existe ou non, avec une demande par minute et par adresse. L'application propose le même service (« Mot de passe oublié ? » sur l'écran de connexion) : elle demande l'e-mail à l'API, l'utilisateur ouvre le lien reçu dans son navigateur.

E-mails : en développement ils s'affichent dans la console du serveur. En production, définissez `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` et `DEFAULT_FROM_EMAIL` (par exemple un compte SMTP Gmail avec mot de passe d'application, Brevo ou Mailjet). Sans SMTP, la page affiche un message d'erreur clair au lieu de planter.

## 6 bis. Paramètres, notifications, arrière-plan, icône et écran de démarrage (application)

**Mise à jour du serveur** : de nouveaux champs et un nouveau modèle (`Notification`) ont été ajoutés. Lancez
`python manage.py makemigrations core && python manage.py migrate`, puis redémarrez.

**Écran Paramètres** (icône engrenage de l'accueil, ou onglet Compte) : compte, notifications (interrupteur général, par type, fréquence de
vérification 5 / 15 / 30 / 60 min, « Vérifier maintenant », notification de test), autorisations et arrière-plan, adresse du serveur,
effacement des données de l'appareil, version et recherche de mise à jour, liens légaux.

**Notifications créées automatiquement par le serveur** (`core/signals.py`) :

| Événement | Qui est notifié |
|---|---|
| Nouvelle offre, changement de prix ou d'offre d'un prestataire visible | tous (type « offre ») |
| Nouveau prestataire visible, mise à jour de profil, nouvelles photos | tous (type « prestataire ») |
| Demande de devis reçue, nouvel avis, profil validé / refusé / suspendu, abonnement activé / rejeté / bientôt expiré / expiré | la personne concernée (type « espace ») |
| Demande de devis marquée « traitée » | le client |
| Nouveau numéro dans **Admin > Paramètres du site > Application mobile** | tous (« Mise à jour disponible », avec le lien de téléchargement) |
| **Admin > Notifications > Ajouter** (annonce, promotion) | tous, ou une seule personne |

Les mises à jour d'un même prestataire sont espacées (6 h pour une offre, 12 h pour le profil et les photos) pour éviter le spam, et l'auteur
d'un changement ne reçoit pas sa propre notification. Pour créer des données sans notifier : `with core.notifications.silencieux(): ...`
(c'est ce que fait `seed_demo`).

**Autorisations** : au premier lancement sur Android/iOS, l'application explique pourquoi elle les demande (notifications, rester actif en
arrière-plan), puis le système affiche ses propres fenêtres. Tout se gère ensuite dans Paramètres > Autorisations. Les permissions Android sont
déclarées dans `flet_app/pyproject.toml` (`[tool.flet.android.permission]`).

**Arrière-plan : ce qui est fait et ses limites.** Flet 0.28.3 ne fournit ni service Android au premier plan ni notifications locales.
L'application vérifie donc le serveur toutes les N minutes tant que son processus est vivant (écran allumé ou en arrière-plan), et
dès que vous revenez dans l'application. Les nouveautés arrivent dans le **centre de notifications** (cloche de l'accueil, badge) et dans une
bannière ; en arrière-plan, une notification système est émise si l'appareil le permet (`flet_app/notifs.py` : Android via `pyjnius` s'il est
présent dans le build, bureau via `plyer`/`notify-send`/`osascript`). Paramètres > Notifications indique si les alertes système sont disponibles
et le bouton « Envoyer une notification test » permet de le vérifier sur le téléphone. Android peut suspendre l'application après un long
moment ; l'autorisation « Rester actif en arrière-plan » réduit ce risque sans l'éliminer. Pour être alerté application fermée de façon
fiable, il faut des notifications push (Firebase Cloud Messaging), qui demandent une extension Flutter personnalisée.

**Icône et écran de démarrage** : le dossier `flet_app/assets/` contient `icon.png` (icône de l'application), `splash.png` (logo de l'écran
de démarrage natif, fond `#2A1840` défini dans `pyproject.toml`) et `logo.png` (logo de l'écran de chargement). Au lancement, l'application affiche
le logo avec un indicateur de chargement tant que les données ne sont pas prêtes, puis ouvre l'accueil. `flet build` prend `icon.png` et `splash.png`
automatiquement. Pour changer le logo, remplacez ces trois fichiers (mêmes noms) ou modifiez puis relancez `python outils/generer_assets.py`
(Pillow requis). La version de l'application est dans `flet_app/pyproject.toml` **et** `flet_app/reglages.py` (`VERSION`) : gardez-les identiques.

## 7. Mise en production (PythonAnywhere, Render…)

Variables : `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY=...`, `DJANGO_ALLOWED_HOSTS=monsite.com`, `DJANGO_CSRF_ORIGINS=https://monsite.com`. Puis `python manage.py collectstatic`. Servez `/static/` (dossier `staticfiles`) et `/media/` (dossier `media`) par votre hébergeur : Django ne sert `/media/` que si `DEBUG=1`. Les images sont réduites à 1600 px (JPEG) à l'envoi.

## Choses à savoir

- Les migrations ne sont pas incluses : `makemigrations core` les génère à votre première installation. Si vous aviez déjà généré des migrations avant la mise à jour légale, relancez `python manage.py makemigrations core && python manage.py migrate` pour ajouter les nouveaux champs.
- Les catégories reprennent celles de `dash.py` (dont Restaurateur/Restauratrice et Livraison/Livreur) ; fusionnez-les dans l'admin si vous préférez.
- Les villes d'exemple sont camerounaises (Douala, Yaoundé…) ; modifiables dans l'admin.
