"""
Genere une autorite de certification (CA) locale + un certificat serveur signe
par cette CA, pour faire tourner ReflexPharma en HTTPS reellement fiable sur le
reseau local (necessaire pour l'acces camera depuis un telephone).

Pourquoi une CA et pas un simple certificat auto-signe ?
Un certificat auto-signe force a cliquer "continuer quand meme" a chaque fois,
et sur la plupart des navigateurs mobiles (Safari iOS notamment), cela ne suffit
PAS a activer l'acces camera : le navigateur continue de considerer la page
comme non securisee pour les API sensibles. En installant une seule fois la CA
comme "digne de confiance" sur le telephone, tous les certificats qu'elle signe
sont ensuite reconnus comme pleinement valides, sans aucun avertissement.

Usage :
    python certs/generate_cert.py [ip_supplementaire ...]

Fichiers generes dans ce dossier :
    reflexpharma-ca.crt   -> A INSTALLER sur chaque telephone/PC (une seule fois)
    reflexpharma-ca.key   -> cle privee de la CA, ne jamais partager
    reflexpharma-dev.crt  -> certificat du serveur (presente par Flask)
    reflexpharma-dev.key  -> cle privee du serveur

Si vous relancez ce script, la CA existante est reutilisee (pour ne pas avoir a
la reinstaller sur les telephones) et seul le certificat serveur est renouvele/
mis a jour avec les IP detectees. Supprimez reflexpharma-ca.* pour repartir de
zero (il faudra alors reinstaller la CA sur chaque appareil).
"""

import ipaddress
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_DIR = Path(__file__).parent
CA_CERT_PATH = CERT_DIR / 'reflexpharma-ca.crt'
CA_KEY_PATH = CERT_DIR / 'reflexpharma-ca.key'
SERVER_CERT_PATH = CERT_DIR / 'reflexpharma-dev.crt'
SERVER_KEY_PATH = CERT_DIR / 'reflexpharma-dev.key'


def detect_local_ips():
    ips = {'127.0.0.1'}
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            ips.add(ip)
    except socket.error:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def load_or_create_ca():
    if CA_CERT_PATH.exists() and CA_KEY_PATH.exists():
        print('Autorite de certification existante reutilisee :', CA_CERT_PATH)
        ca_key = serialization.load_pem_private_key(CA_KEY_PATH.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(CA_CERT_PATH.read_bytes())
        return ca_key, ca_cert

    print('Creation d\'une nouvelle autorite de certification locale...')
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'ReflexPharma Local'),
        x509.NameAttribute(NameOID.COMMON_NAME, 'ReflexPharma Local CA'),
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                key_encipherment=False, content_commitment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    CA_KEY_PATH.write_bytes(ca_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    CA_CERT_PATH.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    print('CA ecrite :', CA_CERT_PATH)
    return ca_key, ca_cert


def issue_server_cert(ca_key, ca_cert, all_ips):
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'ReflexPharma Local Server'),
    ])

    san_entries = [x509.DNSName('localhost')]
    for ip in all_ips:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            san_entries.append(x509.DNSName(ip))

    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=397))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=True, key_cert_sign=False,
                crl_sign=False, content_commitment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    SERVER_KEY_PATH.write_bytes(server_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    SERVER_CERT_PATH.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    print('Certificat serveur ecrit :', SERVER_CERT_PATH)
    print('Valide pour :', ', '.join(str(e) for e in san_entries))


def main():
    extra_ips = sys.argv[1:]
    all_ips = sorted(set(detect_local_ips()) | set(extra_ips))
    print('IP detectees :', ', '.join(all_ips))
    print()

    ca_key, ca_cert = load_or_create_ca()
    issue_server_cert(ca_key, ca_cert, all_ips)

    print()
    print('=' * 70)
    print('ETAPE SUIVANTE (une seule fois par telephone/ordinateur) :')
    print('Installez', CA_CERT_PATH.name, 'comme autorite de confiance.')
    print('Voir certs/README.md pour les instructions Android / iPhone / Windows.')
    print('=' * 70)


if __name__ == '__main__':
    main()
