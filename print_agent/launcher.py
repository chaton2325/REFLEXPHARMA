"""
Utilitaire pour lancer automatiquement l'agent d'impression local
(print_agent/agent.py) en meme temps que le serveur Flask.

Utilise par app.py et run.py. Ne fait rien sur un OS autre que Windows, et
n'interrompt jamais le demarrage du serveur si quelque chose echoue
(pywin32 absent, port deja pris par un agent existant, etc.) : un simple
message est affiche dans la console.
"""

import os
import socket
import subprocess
import sys

AGENT_PORT = 38417
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_PATH = os.path.join(AGENT_DIR, 'agent.py')


def _is_agent_already_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', AGENT_PORT)) == 0


def start_print_agent():
    if sys.platform != 'win32':
        return

    try:
        if _is_agent_already_running():
            return

        if not os.path.exists(AGENT_PATH):
            print("Agent d'impression introuvable (print_agent/agent.py), demarrage automatique ignore.")
            return

        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        subprocess.Popen(
            [sys.executable, AGENT_PATH],
            cwd=AGENT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        print("Agent d'impression ReflexPharma demarre automatiquement (http://127.0.0.1:%d)." % AGENT_PORT)
    except Exception as e:
        print("Impossible de demarrer automatiquement l'agent d'impression : %s" % e)
