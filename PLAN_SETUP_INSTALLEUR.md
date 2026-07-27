# Setup Windows + mise à jour en un clic pour REFLEXPHARMA

## Contexte

REFLEXPHARMA n'est pas encore en production. Aujourd'hui, faire tourner l'app sur
un poste de pharmacie veut dire : installer Python à la main, installer PostgreSQL
à la main, cloner le dépôt, `pip install -r requirements.txt`, écrire `.env` à la
main, lancer `python run.py`. Aucun installeur, aucun exécutable, aucune notion de
version n'existe dans le dépôt (vérifié : aucun `.spec`, `.iss`, `.nsi`, script de
build, ou `__version__`).

Objectif : un `setup.exe` unique que le personnel d'une pharmacie double-clique,
qui installe PostgreSQL 17, crée la base et le fichier `.env`, installe l'appli, et
la démarre — et un bouton "Mettre à jour" dans l'appli déjà installée qui télécharge
et applique la nouvelle version en un clic, sans repasser par tout ce processus.

Déjà en place, à ne PAS reconstruire :
- **Premiers identifiants admin** : `services/bootstrap.py::ensure_bootstrap_admin_user`,
  appelé automatiquement à chaque démarrage une fois une licence activée — génère un
  mot de passe, l'écrit dans `instance/first_admin_credentials.json`, l'affiche sur
  l'écran de connexion tant qu'il n'a jamais servi. Rien à faire ici.
- **Écran d'activation de licence** : `blueprints/license/views.py::activate` — déjà
  fonctionnel, ne nécessite aucun Postgres avant la toute première activation (utilise
  `license_cache.db`, un SQLite séparé). Le setup n'a donc PAS besoin de gérer
  l'activation — juste préparer Postgres et `.env` pour que l'appli, une fois lancée,
  puisse gérer la suite elle-même.
- **Auto-heal du schéma DB** : `app.py::ensure_database_schema` (`db.create_all()` +
  `ALTER TABLE ADD COLUMN IF NOT EXISTS`) — s'exécute déjà à chaque démarrage une fois
  la licence connue. Le setup n'a donc qu'à créer une base Postgres VIDE ; l'appli se
  charge de la remplir au premier lancement.
- **Agent d'impression tickets** (`print_agent/`) : déjà empaqueté en `.exe` via
  PyInstaller (voir son README), déjà lancé automatiquement par `app.py`/`run.py` au
  démarrage (`print_agent/launcher.py`). Aucun changement demandé ici — reste tel quel.

Décisions déjà tranchées avec l'utilisateur :
- Empaquetage app → **PyInstaller** (déjà précédent dans ce dépôt pour print_agent).
- Installeur Windows → **Inno Setup**.
- PostgreSQL 17 → l'utilisateur fournit lui-même l'installeur officiel (`.exe`) à
  embarquer — pas de téléchargement à l'installation.
- Mises à jour hébergées par **ReflexPharma Admin** (déjà le serveur central contacté
  pour la licence, `LICENSE_ADMIN_API_BASE_URL`).
- UX de mise à jour : **un seul bouton**, pas d'assistant à plusieurs écrans.
- Agent d'étiquettes (nouveau, séparé des tickets) : **un agent central par pharmacie**,
  doit être joignable depuis tout le réseau local (pas seulement sa propre machine) ;
  repli sur un localhost configurable si la machine n'a pas de carte réseau active.
  L'impression des tickets et le reste ne changent pas (navigateur, comme aujourd'hui).

## État d'avancement

- **Phase E (partiel, déjà fait)** : `print_agent/agent.py` écoute maintenant sur
  `0.0.0.0` par défaut (configurable via `print_agent_config.json` ou
  `REFLEXPHARMA_PRINT_AGENT_HOST`), `GET /health` renvoie `host`/`port`/`lan_ip`, la
  fenêtre tkinter affiche les adresses joignables. Reste à faire pour Phase E :
  l'endpoint `/print-label` (conversion QR → ESC/POS) et le bouton dans
  `qr_preview.html`.
- **Phases A, B, C, D** : pas commencées.

## Phase A — Numéro de version (REFLEXPHARMA)

- Nouveau `version.py` à la racine : `APP_VERSION = "1.0.0"`, source unique de vérité.
- `services/license_service.py` appelle déjà `license_client.activate()`/`verify()`
  qui acceptent un paramètre `app_version` — mais ne le renseignent jamais aujourd'hui
  (vérifié par grep : aucune occurrence côté REFLEXPHARMA). Renseigner ce paramètre
  avec `version.APP_VERSION` dans les deux appels, pour que ReflexPharma Admin sache
  enfin quelle version tourne sur chaque poste (déjà stocké côté serveur dans
  `Activation.app_version`, `ReflexPharma-admin/models/activation.py`).
- Afficher la version quelque part de discret dans l'UI (ex: bas de la sidebar ou
  page Paramètres) — petite modif de template.

## Phase B — Empaqueter REFLEXPHARMA en .exe (PyInstaller)

- `app.py` (pas `run.py`, qui duplique `app.py` sans rien y ajouter) est le point
  d'entrée canonique : `create_app()` + le bloc `if __name__ == '__main__':` déjà
  présent y fait tout (scheduler licence, bootstrap admin, print_agent, `app.run`).
- Nouveau `installer/reflexpharma.spec` (PyInstaller, mode **onedir** — un Flask avec
  autant de templates/assets s'accommode mal du onefile, qui réextrait tout à chaque
  lancement) bundlant `templates/`, `static/`, `certs/`. `migrations/`/Alembic ne sont
  pas nécessaires au runtime (le schéma est géré par `db.create_all()` + auto-heal) —
  à exclure du build.
- **Chemins à corriger pour un exécutable gelé** (`sys.frozen`) dans `config.py` et
  `app.py::create_app` :
  - `template_folder`/`static_folder` de Flask doivent pointer vers `sys._MEIPASS`
    quand `getattr(sys, 'frozen', False)` est vrai.
  - `instance/` (SQLite `license.db`, `db_override.json`, `first_admin_credentials.json`)
    et `.env` ne doivent PAS vivre sous `Program Files` (souvent non-inscriptible pour
    un utilisateur standard) — les faire pointer vers `%PROGRAMDATA%\ReflexPharma\`
    quand `sys.frozen`, en gardant le comportement actuel (dossier relatif) en dev.
- Remplacer la console par une petite fenêtre de statut tkinter (même pattern que
  `print_agent/agent.py::run_gui`, pour rester cohérent avec le codebase) : "ReflexPharma
  tourne sur http://localhost:5000", bouton "Ouvrir dans le navigateur", bouton
  "Quitter" — et ouverture automatique du navigateur par défaut ~1s après le démarrage
  du serveur (thread `webbrowser.open`).

## Phase C — Installeur Windows (Inno Setup)

- Nouveau `installer/ReflexPharma.iss`. `installer/vendor/` : dossier où l'utilisateur
  dépose l'installeur PostgreSQL 17 officiel fourni (référencé en `[Files]`).
- Étapes du script (section `[Code]` Pascal pour l'orchestration) :
  1. Copier le build PyInstaller (dossier onedir + l'exe `ReflexPrintAgent.exe` déjà
     documenté dans `print_agent/README.md`) vers `{app}`.
  2. Détecter si PostgreSQL 17 est déjà installé (idempotent, nécessaire pour que ce
     même script serve aussi de mise à jour) ; sinon lancer l'installeur PG17 fourni en
     mode silencieux (`--mode unattended --unattendedmodeui minimal --superpassword
     <généré> --servicename postgresql-x64-17 --serverport 5432`), avec un mot de passe
     superuser généré aléatoirement à l'installation (pas de valeur fixe).
  3. Créer la base `reflexdatabase` (vide) via `createdb.exe` (fourni avec PG17) et les
     identifiants générés à l'étape précédente.
  4. Écrire `.env` sous `%PROGRAMDATA%\ReflexPharma\` : `DATABASE_LOCAL_URL` (pointant
     vers la base tout juste créée), `SECRET_KEY` et `LICENSE_HMAC_SECRET_LOCAL`
     générés aléatoirement (jamais de valeur par défaut partagée — actuellement en dur
     dans `.env` de dev, à ne jamais réutiliser), `LICENSE_ADMIN_API_BASE_URL` pointant
     vers l'URL **de production** de ReflexPharma Admin (pas `localhost:5001`).
  5. Raccourcis Bureau + menu Démarrer vers l'exe principal.
  6. Lance l'appli à la fin de l'installation (`[Run] ... postinstall`).
  - En mode "mise à jour" (install déjà détectée via le registre Inno) : sauter les
    étapes 2-4 (Postgres et `.env` déjà en place, ne jamais les toucher), juste
    remplacer les fichiers de l'appli puis relancer — c'est ce même installeur que le
    bouton "Mettre à jour" invoquera en silencieux.

## Phase D — Mécanisme de mise à jour

**ReflexPharma Admin** (nouveau, minimal — pas de nouvelle table, cohérent avec
l'existant) :
- `instance/app_releases/` (gitignored, comme `support_uploads/`) : un `latest.json`
  (`{"version": "1.2.0", "url": "...", "notes": "...", "sha256": "..."}`) + les
  `.exe` d'installeur, déposés manuellement à chaque nouvelle version.
- Nouvelle route publique `GET /updates/latest` (renvoie le JSON) et
  `GET /updates/download/<version>` (`send_file`, même pattern que le téléchargement
  du certificat CA dans REFLEXPHARMA `app.py::download_ca_cert`).

**REFLEXPHARMA** (nouveau) :
- `services/update_service.py` : `check_for_update()` (compare `version.APP_VERSION`
  au manifeste distant), `download_update()`, `apply_update()`.
- Section "Mise à jour" dans Paramètres (superadmin uniquement) : version actuelle,
  bouton "Vérifier les mises à jour", puis "Mettre à jour maintenant" si une version
  plus récente existe.
- Flux d'application : télécharger l'installeur vers un dossier temporaire, vérifier
  le sha256, lancer l'installeur en détaché et silencieux
  (`/VERYSILENT /NORESTART /SUPPRESSMSGBOXES`, `subprocess.Popen(...,
  creationflags=DETACHED_PROCESS)`), puis arrêter proprement le process Flask actuel
  pour libérer les fichiers verrouillés — l'installeur relance l'appli tout seul à la
  fin (`[Run] postinstall`, déjà prévu Phase C).

## Phase E — Agent d'étiquettes réseau (print_agent)

- ✅ `print_agent/agent.py` écoute désormais sur `0.0.0.0` (sert simultanément
  127.0.0.1 ET l'IP réseau de la machine), configurable via `print_agent_config.json`
  (`host`) ou `REFLEXPHARMA_PRINT_AGENT_HOST`. `GET /health` expose `host`/`port`/
  `lan_ip`, la fenêtre tkinter affiche les adresses joignables.
- ⬜ Nouvel endpoint `POST /print-label` : reçoit le PNG du QR déjà généré côté serveur
  (même génération que `templates/admin/stock/qr_preview.html`) + les lignes de texte,
  le convertit en bitmap monochrome via Pillow (déjà une dépendance) et émet les
  commandes ESC/POS `GS v 0` (raster image) — nouvelle classe `LabelBuilder`, sur le
  même modèle que `ReceiptBuilder` existant, réutilise `send_raw_to_printer`.
- ⬜ `templates/admin/stock/qr_preview.html` : ajouter un bouton "Imprimer via l'agent
  réseau" (POST vers l'IP:port configuré) à côté du bouton `window.print()` existant
  (conservé tel quel, ne rien casser). L'IP:port de l'agent central se configure et se
  stocke via `Setting` (comme la devise, aucune nouvelle table).
- Aucune authentification sur ce nouvel endpoint (même posture que l'existant `/print`,
  réseau local de confiance) — à noter explicitement comme limite connue.

## Fichiers concernés (représentatif)

- `version.py` (nouveau), `config.py`, `app.py`, `services/license_service.py`
- `installer/reflexpharma.spec`, `installer/ReflexPharma.iss`, `installer/vendor/` (nouveaux)
- `services/update_service.py` (nouveau), `templates/admin/settings.html` (section MAJ)
- `print_agent/agent.py`, `print_agent/README.md`, `templates/admin/stock/qr_preview.html`
- Côté `ReflexPharma-admin` : nouveau petit blueprint/route `updates`, `instance/app_releases/`, `.gitignore`

## Vérification

- Build PyInstaller local : lancer l'exe gelé, confirmer qu'il trouve templates/static/
  certs et démarre (le point de rupture le plus probable est la résolution de chemin
  `sys._MEIPASS`).
- Script Inno Setup : test manuel sur une machine/VM Windows propre — installation
  silencieuse de PG17, `.env` généré correctement, écran d'activation atteint, premier
  compte admin créé (réutilise le flux déjà existant). Pas automatisable en pytest,
  nécessite un vrai environnement Windows.
- `services/update_service.py` : script de test disposable (même pattern que les
  scripts déjà utilisés dans ce projet) contre un client Flask de test de ReflexPharma
  Admin, vérifiant la forme du manifeste et la logique de comparaison de version.
- `print_agent` : test unitaire isolé de la conversion PNG → bytes ESC/POS (assert sur
  la structure des octets), test de `/print-label` avec `send_raw_to_printer` mocké —
  pas de test d'impression réelle possible sans matériel.

## Séquencement

Vu l'ampleur, à traiter phase par phase (comme le chantier accès distant précédent) :
A (version) → B (empaquetage, bloquant pour tout le reste) → C (installeur, une fois
le fichier PostgreSQL 17 fourni) → D (mise à jour) → E (agent étiquettes, indépendant,
peut être fait à tout moment — networking déjà fait, reste l'endpoint label).
