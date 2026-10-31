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

Adresse du serveur : écrite dans `flet_app/config.py` (`URL_SERVEUR`) avant `flet build` ; les utilisateurs ne la saisissent jamais. Seul l'administrateur peut la changer ensuite, depuis l'application (voir section 6 quater). `FETE_API_URL` la remplace pour les tests sur PC.
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
vérification 5 / 15 / 30 / 60 min, « Vérifier maintenant », notification de test), autorisations et arrière-plan,
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

**Autorisations** (extension `flet-permission-handler==0.1.0`, déclarée dans `pyproject.toml` : sans elle le build affiche « Unknown control: permission_handler ») : au premier lancement sur Android/iOS, l'application explique pourquoi elle les demande (notifications, rester actif en
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

## 6 quater. Comptes, administrateur, récupération de mot de passe et adresse du serveur

**Mise à jour du serveur** : nouveaux champs et modèle `CodeReinitialisation`. Lancez
`python manage.py makemigrations core && python manage.py migrate`.

**Connexion** : nom d'utilisateur + mot de passe (majuscules ignorées). À l'inscription, l'application demande un nom d'utilisateur (3 à 30
caractères : lettres, chiffres, `.` `_` `-`) en plus de l'e-mail, qui sert à récupérer le mot de passe. Les comptes existants gardent leur
e-mail comme nom d'utilisateur et se connectent comme avant. Le site web accepte aussi nom d'utilisateur ou e-mail (`core/auth_backends.py`).
Au bout de 15 échecs depuis une même adresse IP, les connexions sont bloquées 10 minutes.

**Administrateur dans l'application** : tout compte « équipe » (`is_staff`) voit **Administration** dans l'onglet Compte et après sa
connexion. Créez-le avec `python manage.py createsuperuser`, puis connectez-vous dans l'application avec ce nom d'utilisateur. Écrans :
tableau de bord, prestataires (valider, refuser avec motif, suspendre, réactiver), abonnements (activer ou rejeter un paiement),
utilisateurs (mot de passe provisoire), annonce envoyée à tous, adresse du serveur. Les routes `/api/v1/admin/...` refusent tout compte
non administrateur (403), même si quelqu'un contourne l'application.

**Récupération du mot de passe** : « Mot de passe oublié ? » envoie un code à 6 chiffres par e-mail (valable 15 minutes, 5 essais, un code
par minute et par compte). Le serveur répond de la même façon que le compte existe ou non. Le nouveau mot de passe déconnecte les appareils
déjà connectés. L'envoi d'e-mails doit être configuré (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, voir
`settings.py`) ; sans cela, en mode `DEBUG`, le code s'affiche dans la console du serveur. Pour un utilisateur sans accès à son e-mail,
l'administrateur génère un **mot de passe provisoire** (Administration > Utilisateurs) : l'utilisateur doit en choisir un nouveau dès sa
connexion. Chacun peut aussi changer son mot de passe dans Paramètres.

**Adresse du serveur** : elle est intégrée à l'application (`flet_app/config.py`, `URL_SERVEUR`, à remplir avant `flet build`) : personne
n'a à la saisir. Quand l'administrateur la change (Administration > Adresse du serveur, ou *Admin Django > Paramètres du site > Application
mobile*), le serveur l'annonce aux téléphones au démarrage et à chaque vérification de notifications ; chaque téléphone teste la nouvelle
adresse et l'adopte seulement si elle répond comme Fête & Services. Limites à connaître :
- un téléphone ne peut apprendre la nouvelle adresse que tant que l'ancienne répond : gardez-la en service jusqu'à ce que les téléphones
  aient suivi (ouvrir l'application suffit, quelques minutes) ;
- la nouvelle adresse doit servir les mêmes données (même base de données) ;
- si l'adresse mémorisée ne répond plus au démarrage, l'application retombe sur l'adresse de `config.py` : mettez-y un nom de domaine
  stable en HTTPS plutôt qu'une IP qui change.
Sur Android, utilisez de préférence HTTPS : le trafic HTTP non chiffré peut être bloqué par le système.

## 6 quinquies. Modifier ses offres, packs et campagnes de promotion par code

**Mise à jour du serveur** : nouveaux modèles (`Pack`, `Campagne`) et champs (`Offre.accepte_promo`, `Plan.max_packs`).
Lancez `python manage.py makemigrations core && python manage.py migrate`.

**Modifier une offre dans l'application** : Mon espace > Mes offres. Un appui sur une offre (ou sur le crayon) ouvre le formulaire prérempli :
titre, prix, unité, description, photo (la photo actuelle est conservée si on n'en choisit pas une autre), visibilité et participation aux promotions.
Une offre masquée affiche l'étiquette « Masquée ».

**Packs** : Mon espace > Mes packs. Un pack regroupe au moins 2 offres du prestataire à un prix unique (ex. « Pack Mariage » : DJ + décoration + traiteur).
Les clients voient sur la fiche du prestataire les services inclus, le prix du pack et, quand toutes les offres ont un prix, l'économie réalisée.
Le nombre de packs dépend de la formule (`Plan.max_packs`, 3 par défaut ; 1 sans abonnement) et se règle dans l'admin Django. Un nouveau pack visible
déclenche une notification « Nouveau pack chez … ».

**Campagnes de promotion par code** (administrateur) : Administration > Campagnes de promotion. En un clic : nom, réduction (1 à 90 %), durée
(1 à 90 jours), catégorie (ou toutes), code (généré automatiquement si on le laisse vide), annonce facultative aux utilisateurs. La campagne démarre
immédiatement et se termine toute seule à la date de fin ; elle peut être arrêtée avant. L'écran liste les campagnes, leur code, leurs dates et le nombre de
saisies du code.
- Le code n'est **jamais** publié dans l'annonce sauf si vous cochez « Inclure le code dans l'annonce » : sinon l'annonce invite à le demander à l'équipe.
- Côté clients : Code promo (icône étiquette de l'accueil, ou onglet Compte) > saisir le code. Le serveur le vérifie (existant, en cours, non arrêté) ; l'application
  le mémorise jusqu'à la fin de la campagne puis l'oublie. Pendant ce temps, les offres et packs participants affichent le prix réduit, l'ancien prix barré et « -X % ».
  Sans code valide, le serveur ne renvoie aucune réduction : un client ne peut pas voir le prix réduit en le « devinant ».
- **Consentement des prestataires** : une offre ou un pack n'est réduit que si son prestataire a activé « Participer aux campagnes de promotion » (désactivé par défaut).
  L'écran de lancement indique combien d'offres et de packs sont concernés ; s'il n'y en a aucun, demandez aux prestataires d'activer l'option. La réduction est calculée
  sur le prix affiché, arrondie au FCFA ; les offres « sur devis » ne sont pas concernées. Si deux codes sont actifs, le client obtient la meilleure réduction.
- Essais de codes limités à 30 par heure et par adresse IP.
Le site web n'affiche pas encore les packs ni les prix promotionnels : ils sont gérés et affichés dans l'application (les packs et campagnes sont aussi visibles dans l'admin Django).

## 7. Mise en production (PythonAnywhere, Render…)

Variables : `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY=...`, `DJANGO_ALLOWED_HOSTS=monsite.com`, `DJANGO_CSRF_ORIGINS=https://monsite.com`. Puis `python manage.py collectstatic`. Servez `/static/` (dossier `staticfiles`) et `/media/` (dossier `media`) par votre hébergeur : Django ne sert `/media/` que si `DEBUG=1`. Les images sont réduites à 1600 px (JPEG) à l'envoi.

## Choses à savoir

- Les migrations ne sont pas incluses : `makemigrations core` les génère à votre première installation. Si vous aviez déjà généré des migrations avant la mise à jour légale, relancez `python manage.py makemigrations core && python manage.py migrate` pour ajouter les nouveaux champs.
- Les catégories reprennent celles de `dash.py` (dont Restaurateur/Restauratrice et Livraison/Livreur) ; fusionnez-les dans l'admin si vous préférez.
- Les villes d'exemple sont camerounaises (Douala, Yaoundé…) ; modifiables dans l'admin.
