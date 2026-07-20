"""Envoi d'e-mails via le serveur SMTP configuré dans les paramètres de l'application.

La configuration est lue depuis la table `settings` (voir models/setting.py) à chaque
envoi, plutôt que figée au démarrage de l'app : elle peut être changée à chaud depuis
la page Paramètres, sans redémarrer le serveur.
"""
import smtplib
import ssl
from email.message import EmailMessage

from models.setting import Setting

SMTP_ENCRYPTIONS = ('starttls', 'ssl', 'none')


class SmtpConfigError(Exception):
    """La configuration SMTP est absente ou incomplète."""


class SmtpSendError(Exception):
    """La connexion ou l'envoi via le serveur SMTP a échoué."""


def get_smtp_config():
    return {
        'host': (Setting.get_value('smtp_host', '') or '').strip(),
        'port': Setting.get_value('smtp_port', '587') or '587',
        'encryption': Setting.get_value('smtp_encryption', 'starttls') or 'starttls',
        'username': (Setting.get_value('smtp_username', '') or '').strip(),
        'password': Setting.get_value('smtp_password', '') or '',
        'from_email': (Setting.get_value('smtp_from_email', '') or '').strip(),
        'from_name': (Setting.get_value('smtp_from_name', '') or '').strip(),
    }


def is_smtp_configured(config=None):
    config = config or get_smtp_config()
    return bool(config['host'] and config['from_email'])


def send_email(to, subject, body, html=None):
    """Envoie un e-mail texte (optionnellement avec une alternative HTML).

    Lève SmtpConfigError si la configuration est incomplète, ou SmtpSendError si la
    connexion/authentification/envoi échoue côté serveur SMTP.
    """
    config = get_smtp_config()
    if not is_smtp_configured(config):
        raise SmtpConfigError("Le serveur SMTP n'est pas configuré (hôte et adresse d'expédition requis).")

    try:
        port = int(config['port'])
    except (TypeError, ValueError):
        raise SmtpConfigError(f"Port SMTP invalide : {config['port']!r}.")

    encryption = config['encryption'] if config['encryption'] in SMTP_ENCRYPTIONS else 'starttls'

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = f"{config['from_name']} <{config['from_email']}>" if config['from_name'] else config['from_email']
    message['To'] = to
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype='html')

    try:
        if encryption == 'ssl':
            server = smtplib.SMTP_SSL(config['host'], port, timeout=10, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(config['host'], port, timeout=10)
        with server:
            if encryption == 'starttls':
                server.starttls(context=ssl.create_default_context())
            if config['username']:
                server.login(config['username'], config['password'])
            server.send_message(message)
    except SmtpConfigError:
        raise
    except Exception as exc:
        raise SmtpSendError(str(exc)) from exc
