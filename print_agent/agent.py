"""
Agent d'impression local ReflexPharma.

Tourne en arriere-plan sur un poste de caisse Windows. Recoit les tickets de
vente depuis la page web ReflexPharma (appel HTTP local, meme reseau que
le navigateur) et les envoie directement a l'imprimante configuree, via le
spouleur Windows, sans jamais afficher de boite de dialogue.

Prerequis : pywin32   ->  pip install -r requirements.txt
Lancer    : python agent.py

Voir README.md pour la configuration au demarrage de Windows et
l'empaquetage en .exe avec PyInstaller.
"""

import json
import os
import sys
import threading
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import win32print
except ImportError:
    print("ERREUR: le module 'pywin32' est requis. Installez-le avec : pip install pywin32")
    sys.exit(1)

PORT = 38417
CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'ReflexPharma')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'print_agent_config.json')
ALLOWED_ORIGIN = os.environ.get('REFLEXPHARMA_ORIGIN', '*')
LINE_WIDTH = 32

ESC = b'\x1B'
GS = b'\x1D'


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_default_printer():
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def get_selected_printer():
    config = load_config()
    return config.get('printer') or get_default_printer()


def list_printers():
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    printers = win32print.EnumPrinters(flags)
    names = sorted(p[2] for p in printers)
    return names, get_default_printer()


def strip_accents(text):
    normalized = unicodedata.normalize('NFD', text)
    return ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')


def encode_line(text):
    return strip_accents(text).encode('cp437', errors='replace')


class ReceiptBuilder:
    """Construit une sequence de commandes ESC/POS pour imprimante thermique."""

    def __init__(self):
        self.data = bytearray()
        self.data += ESC + b'\x40'  # Init imprimante

    def align(self, pos):
        mapping = {'left': 0, 'center': 1, 'right': 2}
        self.data += ESC + b'\x61' + bytes([mapping.get(pos, 0)])
        return self

    def bold(self, on):
        self.data += ESC + b'\x45' + bytes([1 if on else 0])
        return self

    def double(self, on):
        self.data += GS + b'\x21' + bytes([0x11 if on else 0x00])
        return self

    def line(self, text=''):
        self.data += encode_line(text) + b'\n'
        return self

    def feed(self, n=1):
        self.data += b'\n' * n
        return self

    def hr(self, char='-'):
        self.line(char * LINE_WIDTH)
        return self

    def row(self, left, right):
        left, right = str(left), str(right)
        space = max(1, LINE_WIDTH - len(left) - len(right))
        self.line(left + ' ' * space + right)
        return self

    def cut(self):
        self.data += GS + b'\x56' + b'\x01'  # Coupe partielle
        return self

    def build(self):
        return bytes(self.data)


def build_receipt_bytes(receipt):
    b = ReceiptBuilder()
    b.align('center').double(True).bold(True).line(receipt.get('pharmacyName') or 'ReflexPharma')
    b.double(False).bold(False)
    b.line('Pharmacie - Parapharmacie')
    b.line('Vente No: ' + str(receipt.get('numero') or ''))
    b.feed(1)
    b.align('left')
    b.row('Date: ' + str(receipt.get('date') or ''), 'Heure: ' + str(receipt.get('heure') or ''))
    b.line('Vendeur: ' + str(receipt.get('vendeur') or ''))
    if receipt.get('client'):
        b.line('Client: ' + str(receipt['client']))
    if receipt.get('points'):
        b.line('Points fidelite gagnes: ' + str(receipt['points']))
    if receipt.get('pointsTotaux'):
        b.line('Total points fidelite client: ' + str(receipt['pointsTotaux']))
    b.hr('-')
    for ligne in receipt.get('lignes') or []:
        b.line(ligne.get('nom', ''))
        b.row('  ' + str(ligne.get('qte', '')) + ' x ' + str(ligne.get('pu', '')), ligne.get('total', ''))
    b.hr('-')
    if receipt.get('codePromo'):
        b.row(
            'Code promo ' + str(receipt['codePromo']) + ' (-' + str(receipt.get('codePromoPourcentage', '')) + '%)',
            '-' + str(receipt.get('codePromoMontant', ''))
        )
    b.bold(True).row('NET A PAYER (TTC)', receipt.get('totalTtc', '')).bold(False)
    b.hr('.')
    b.row('Paiement:', receipt.get('modePaiement', ''))
    b.row('Recu:', receipt.get('montantRecu', ''))
    b.row('Rendu:', receipt.get('monnaieRendue', ''))
    b.feed(1)
    if receipt.get('watermark'):
        b.align('center').line('*** ' + str(receipt['watermark']) + ' ***')
    b.align('center')
    b.line('Merci de votre confiance !')
    b.line('Logiciel ReflexPharma')
    b.feed(3)
    b.cut()
    return b.build()


def send_raw_to_printer(printer_name, data):
    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, ('Ticket ReflexPharma', None, 'RAW'))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


class AgentHandler(BaseHTTPRequestHandler):
    def _set_cors(self):
        self.send_header('Access-Control-Allow-Origin', ALLOWED_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self._set_cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self._send_json(200, {'status': 'ok'})
        elif self.path == '/printers':
            try:
                names, default = list_printers()
                self._send_json(200, {'printers': names, 'default': default, 'selected': get_selected_printer()})
            except Exception as e:
                self._send_json(500, {'message': str(e)})
        elif self.path == '/config':
            self._send_json(200, {'printer': get_selected_printer()})
        else:
            self._send_json(404, {'message': 'Route inconnue.'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(length) if length else b'{}'
        try:
            payload = json.loads(raw or b'{}')
        except json.JSONDecodeError:
            self._send_json(400, {'message': 'JSON invalide.'})
            return

        if self.path == '/config':
            printer = payload.get('printer')
            if not printer:
                self._send_json(400, {'message': "Nom d'imprimante requis."})
                return
            config = load_config()
            config['printer'] = printer
            save_config(config)
            self._send_json(200, {'printer': printer})
        elif self.path == '/print':
            printer = get_selected_printer()
            if not printer:
                self._send_json(400, {'message': 'Aucune imprimante configuree sur ce poste.'})
                return
            try:
                data = build_receipt_bytes(payload)
                send_raw_to_printer(printer, data)
                self._send_json(200, {'success': True})
            except Exception as e:
                self._send_json(500, {'message': "Echec d'impression : " + str(e)})
        else:
            self._send_json(404, {'message': 'Route inconnue.'})

    def log_message(self, format, *args):
        pass  # Pas de bruit dans la console


def run_server():
    server = ThreadingHTTPServer(('127.0.0.1', PORT), AgentHandler)
    server.serve_forever()


def run_gui():
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("ReflexPharma - Agent d'impression")
    root.geometry('380x180')
    root.resizable(False, False)

    tk.Label(root, text="Agent d'impression ReflexPharma", font=('Segoe UI', 11, 'bold')).pack(pady=(16, 4))
    tk.Label(root, text='En ecoute sur http://127.0.0.1:%d' % PORT, font=('Segoe UI', 9)).pack()

    printer_var = tk.StringVar()

    def refresh_printer_label():
        selected = get_selected_printer() or 'Aucune imprimante configuree'
        printer_var.set('Imprimante active : ' + selected)
        root.after(3000, refresh_printer_label)

    tk.Label(root, textvariable=printer_var, font=('Segoe UI', 9, 'bold'), fg='#1e8e3e', wraplength=340).pack(pady=(12, 0))
    tk.Label(
        root,
        text="Ne fermez pas cette fenetre : l'impression automatique\ndes tickets de vente ne fonctionnera plus.",
        font=('Segoe UI', 8),
        fg='#7a8896',
        justify='center'
    ).pack(pady=(16, 0))

    def on_close():
        if messagebox.askyesno('Quitter', "Fermer l'agent d'impression ?\nL'impression automatique des tickets sera desactivee sur ce poste."):
            root.destroy()
            os._exit(0)

    root.protocol('WM_DELETE_WINDOW', on_close)
    refresh_printer_label()
    root.mainloop()


def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("Agent d'impression ReflexPharma demarre sur http://127.0.0.1:%d" % PORT)

    try:
        run_gui()
    except ImportError:
        # Tkinter absent (ex: certaines installations Python minimalistes) : on reste en console.
        print("Tkinter indisponible, l'agent tourne en mode console (Ctrl+C pour arreter).")
        server_thread.join()


if __name__ == '__main__':
    main()
