# Agent d'impression ReflexPharma

Petit programme Windows qui tourne en arrière-plan sur un poste de caisse et
reçoit les tickets de vente depuis la page web ReflexPharma pour les imprimer
directement, sans jamais afficher la boîte de dialogue d'impression du
navigateur. Il faut l'installer **sur chaque poste de caisse** qui doit
imprimer automatiquement.

## Installation (une fois par poste)

1. Installer Python 3 si ce n'est pas déjà fait (https://python.org).
2. Ouvrir une invite de commande dans ce dossier (`print_agent`) et lancer :
   ```
   pip install -r requirements.txt
   ```
3. Lancer l'agent :
   ```
   python agent.py
   ```
   Une petite fenêtre s'ouvre indiquant que l'agent est actif. Ne la fermez
   pas — c'est elle qui permet l'impression automatique.
4. Aller dans ReflexPharma > **Paramètres App > Impression automatique**,
   choisir l'imprimante à utiliser pour les tickets de vente dans la liste,
   puis cliquer sur "Imprimer un ticket de test" pour vérifier.

## Démarrage automatique avec Windows

Pour ne pas avoir à relancer l'agent manuellement chaque matin :

1. Appuyez sur `Win + R`, tapez `shell:startup`, validez.
2. Créez un raccourci vers `agent.py` (ou vers l'exécutable, voir
   ci-dessous) dans ce dossier qui s'ouvre.
3. L'agent démarrera automatiquement à chaque ouverture de session Windows.

## Empaqueter en .exe (optionnel, évite d'installer Python sur le poste de caisse)

```
pip install pyinstaller
pyinstaller --onefile --noconsole --name ReflexPrintAgent agent.py
```

L'exécutable est généré dans `dist/ReflexPrintAgent.exe`. C'est lui qu'on
place dans le dossier de démarrage de Windows (`shell:startup`).

## Détails techniques

- Par défaut, l'agent écoute sur `0.0.0.0:38417` : il répond à la fois sur
  `127.0.0.1` (ce poste) ET sur l'IP réseau local de la machine, pour qu'un
  agent centralisé (ex: imprimante à étiquettes branchée sur un seul poste)
  reste joignable depuis les autres postes du réseau local. Sur une machine
  sans carte réseau active, `127.0.0.1` répond toujours de la même façon.
  Pour revenir à un agent strictement local (comme avant), ajoutez
  `"host": "127.0.0.1"` dans `print_agent_config.json`, ou définissez la
  variable d'environnement `REFLEXPHARMA_PRINT_AGENT_HOST=127.0.0.1` avant de
  lancer l'agent.
- L'adresse à utiliser depuis un autre poste s'affiche dans la fenêtre de
  l'agent, et est aussi renvoyée par `GET /health` (`host`, `port`, `lan_ip`).
- La configuration (imprimante choisie, hôte d'écoute) est stockée dans
  `%APPDATA%\ReflexPharma\print_agent_config.json`.
- Impression en mode `RAW`, avec deux formats possibles selon l'imprimante :
  - **ESC/POS** (ticket mis en forme : centrage, gras, coupe papier) pour les
    vraies imprimantes thermiques de tickets.
  - **Texte simple** (aucune commande, alignement par espaces) pour les
    imprimantes configurées sous Windows avec le driver **"Générique / Texte
    seulement"** (*Generic / Text Only*) — ce driver n'interprète pas les
    commandes ESC/POS, qui s'impriment alors comme des caractères parasites
    au lieu d'être exécutées : ticket illisible, sans aucune mise en forme.
  - Le format est **détecté automatiquement** à partir du nom du driver
    Windows de l'imprimante sélectionnée (déclenché si son nom contient
    "Generic"/"Générique" ou "Text Only"/"Texte seulement"). Un menu dans
    ReflexPharma > Paramètres App > Impression automatique permet de forcer
    l'un ou l'autre si la détection se trompe.
- Si votre page ReflexPharma n'est pas servie depuis `localhost`, définissez
  la variable d'environnement `REFLEXPHARMA_ORIGIN` avant de lancer l'agent
  (ex: `set REFLEXPHARMA_ORIGIN=http://192.168.1.10:5000`) pour restreindre
  les origines autorisées à parler à l'agent.
- **Accès via un tunnel HTTPS public (ngrok, etc.)** : Chrome bloque par
  défaut ("Private Network Access") les requêtes d'une page servie sur une
  origine publique en HTTPS vers `127.0.0.1` — l'agent renvoie l'en-tête
  `Access-Control-Allow-Private-Network: true` pour l'autoriser explicitement.
  Symptôme si un agent plus ancien (sans cet en-tête) est utilisé derrière
  ngrok : l'impression automatique semble ignorée et un ticket sans aucune
  mise en forme sort de l'imprimante, avec le titre de la page, son URL et
  la pagination ajoutés par le navigateur (le code s'est rabattu sur
  `window.print()`, faute de pouvoir joindre l'agent) — mettez à jour l'agent
  (ou relancez `agent.py`) si c'est le cas.
