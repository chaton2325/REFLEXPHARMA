"""Programme de fidélité : activation et taux de conversion points -> devise.

Les règles d'attribution des points (points par unité achetée) vivent directement
sur Produit/Famille/Rayon/Section (voir Produit.points_fidelite_effectif) ; ce
module ne gère que le réglage global : le programme est-il actif, et combien vaut
un point en devise (taux de conversion unique pour toute la pharmacie).
"""
from models.setting import Setting


def is_active():
    return Setting.get_value('fidelite_active', 'false') == 'true'


def get_conversion_rate():
    """{'points': int, 'valeur': float} — ex: {'points': 100, 'valeur': 500}
    signifie 100 points = 500 [devise]. 'points' à 0 signifie taux non configuré."""
    try:
        points = int(Setting.get_value('fidelite_points_montant', '0') or 0)
    except (TypeError, ValueError):
        points = 0
    try:
        valeur = float(Setting.get_value('fidelite_points_valeur', '0') or 0)
    except (TypeError, ValueError):
        valeur = 0.0
    return {'points': max(points, 0), 'valeur': max(valeur, 0.0)}


def can_redeem():
    """True si le programme est actif ET qu'un taux de conversion valide est
    configuré — l'accumulation de points ne dépend, elle, que de is_active()."""
    rate = get_conversion_rate()
    return is_active() and rate['points'] > 0 and rate['valeur'] > 0


def points_to_value(points):
    """Équivalent en devise d'un nombre de points, selon le taux de conversion
    global. 0 si le taux n'est pas configuré (pas de division par zéro)."""
    rate = get_conversion_rate()
    if rate['points'] <= 0:
        return 0.0
    return max(points, 0) * rate['valeur'] / rate['points']
