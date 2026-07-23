"""Arrondi du prix de vente affiché/facturé (PVTTC), utile en zone FCFA où les
pièces disponibles ne permettent pas de payer n'importe quel montant (ex: 185
FCFA n'existe pas en pièces/billets, on arrondit à 175 ou 200). Ce module ne
gère que le réglage global : l'arrondi est-il actif, dans quel sens, et à quel
palier (multiple le plus proche) — voir models/produit.py pour son application
au calcul du prix de vente.
"""
import math

from models.setting import Setting

DEFAULT_PALIER = 25


def is_active():
    return Setting.get_value('arrondi_prix_active', 'false') == 'true'


def get_sens():
    """'superieur' ou 'inferieur' — sens de l'arrondi quand actif."""
    sens = Setting.get_value('arrondi_prix_sens', 'superieur')
    return sens if sens in ('superieur', 'inferieur') else 'superieur'


def get_palier():
    """Palier d'arrondi (ex: 25 => arrondi au multiple de 25 le plus proche selon
    le sens choisi). Valeur par défaut adaptée aux pièces/billets FCFA courants."""
    try:
        palier = float(Setting.get_value('arrondi_prix_palier', str(DEFAULT_PALIER)) or DEFAULT_PALIER)
    except (TypeError, ValueError):
        palier = DEFAULT_PALIER
    return palier if palier > 0 else DEFAULT_PALIER


def round_price(value):
    """Arrondit `value` au palier configuré, dans le sens configuré, si le
    réglage est actif. Renvoie `value` inchangé sinon (ou si `value` est None)."""
    if value is None or not is_active():
        return value
    palier = get_palier()
    if get_sens() == 'inferieur':
        return math.floor(value / palier) * palier
    return math.ceil(value / palier) * palier
