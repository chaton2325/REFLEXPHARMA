# HTTPS local pour ReflexPharma

ReflexPharma a besoin d'HTTPS pour que la caméra fonctionne (scan QR) sur les
téléphones connectés au réseau local. Comme il n'y a pas de nom de domaine
public, on utilise une **autorité de certification (CA) locale** : une fois
installée comme "digne de confiance" sur chaque appareil, tout se passe
ensuite normalement, sans aucun avertissement "connexion non sécurisée".

## 1. Générer les certificats (sur le PC serveur, une seule fois)

```
pip install cryptography
python certs/generate_cert.py
```

Cela crée 4 fichiers dans `certs/` :
- `reflexpharma-ca.crt` — **à installer sur chaque téléphone/PC** (fichier public, pas secret)
- `reflexpharma-ca.key` — clé privée de la CA, **ne la partagez jamais**
- `reflexpharma-dev.crt` / `reflexpharma-dev.key` — certificat du serveur (utilisé automatiquement par `app.py`/`run.py`)

Relancez `app.py` ou `run.py` : la console doit maintenant afficher
`Running on https://...` (au lieu de `http://`).

## 2. Installer la CA sur chaque téléphone (une seule fois par appareil)

**Le plus simple** : depuis le navigateur du téléphone (connecté au même
réseau que le serveur), ouvrez :

```
http://<IP-du-serveur>:5000/ca-cert
```

(en `http://`, pas besoin d'HTTPS pour ce téléchargement) — le fichier
`reflexpharma-ca.crt` se télécharge directement, et Android proposera même
souvent de l'installer automatiquement.

Sinon, transférez `certs/reflexpharma-ca.crt` par email, messagerie ou clé
USB.

### Android
1. Copiez `reflexpharma-ca.crt` sur le téléphone (téléchargement, USB, etc.).
2. **Réglages → Sécurité → Chiffrement et identifiants → Installer un certificat → Certificat CA** (le chemin exact varie selon la marque : Samsung, Xiaomi, etc. — cherchez "Installer un certificat" dans les réglages).
3. Sélectionnez le fichier `reflexpharma-ca.crt`. Android affichera un avertissement générique ("le réseau peut être surveillé") — c'est normal pour toute CA installée manuellement, ignorez-le.
4. Le réseau/l'app peut demander de définir un code PIN/schéma sur le téléphone si aucun n'est configuré (obligatoire pour stocker un certificat).

### iPhone / iPad (2 étapes obligatoires, souvent oubliée à la 2e)
1. Envoyez-vous `reflexpharma-ca.crt` par email ou AirDrop, puis ouvrez-le : iOS propose d'installer un **profil**. **Réglages → Profil téléchargé → Installer**.
2. **Étape indispensable et différente** : **Réglages → Général → Informations → Réglages de confiance des certificats** → activez la confiance totale pour "ReflexPharma Local CA".
   Sans cette 2e étape, iOS installe le profil mais ne fait toujours pas confiance au certificat, et la caméra continuera d'être bloquée.

### Windows (PC serveur ou autre PC qui accède à l'app)
Ouvrir une invite de commande **en administrateur** :
```
certutil -addstore -f "ROOT" certs\reflexpharma-ca.crt
```
Ou double-cliquez sur `reflexpharma-ca.crt` → Installer le certificat →
Ordinateur local → "Placer tous les certificats dans le magasin suivant" →
**Autorités de certification racines de confiance**.

## 3. Vérifier

Depuis le téléphone (une fois la CA installée), ouvrez
`https://<IP-du-serveur>:5000` — le cadenas doit s'afficher **sans aucun
avertissement**. Testez ensuite le bouton de scan QR dans une vente : la
caméra doit démarrer sans le message "Erreur d'accès aux caméras".

## Si l'IP du serveur change

Relancez simplement `python certs/generate_cert.py` (la CA existante est
réutilisée automatiquement, pas besoin de la réinstaller sur les téléphones)
puis redémarrez `app.py`/`run.py`.

## Renouvellement

Le certificat serveur est valide 397 jours (limite imposée par les
navigateurs). La CA elle-même est valide 10 ans. Relancer
`generate_cert.py` avant expiration régénère uniquement le certificat
serveur, sans toucher à la CA déjà installée sur les téléphones.
