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

- L'agent écoute uniquement sur `127.0.0.1:38417` (pas accessible depuis le
  réseau, seulement depuis ce même ordinateur).
- La configuration (imprimante choisie) est stockée dans
  `%APPDATA%\ReflexPharma\print_agent_config.json`.
- Impression en mode `RAW` (commandes ESC/POS) — pensé pour une imprimante
  thermique de tickets, mais fonctionne avec toute imprimante Windows
  configurée en mode RAW/texte brut.
- Si votre page ReflexPharma n'est pas servie depuis `localhost`, définissez
  la variable d'environnement `REFLEXPHARMA_ORIGIN` avant de lancer l'agent
  (ex: `set REFLEXPHARMA_ORIGIN=http://192.168.1.10:5000`) pour restreindre
  les origines autorisées à parler à l'agent.
