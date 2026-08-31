from flask import g
from extensions import db

# Sentinelle distincte de None : marque "reglage absent en base" dans le cache
# ci-dessous, pour ne jamais confondre avec une ligne existante dont la valeur
# est explicitement NULL (voir get_value).
_ABSENT = object()


class Setting(db.Model):
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.String(200))

    @staticmethod
    def get_value(key, default=None):
        """Lecture d'un reglage, mise en cache pour la duree de LA REQUETE EN
        COURS (flask.g). Sans ce cache, chaque lecture est une requete SQL a
        part entiere -- or utils/arrondi.py (is_active/get_sens/get_palier)
        relit ces memes reglages a CHAQUE niveau de prix de CHAQUE lot lors du
        calcul des stats de stock (/api/stock-stats boucle sur tout le
        stock) : plusieurs dizaines de requetes identiques par lot, donc des
        milliers sur un stock qui grossit, meme apres pagination de la liste
        elle-meme (la pagination ne change rien a ce calcul, qui reste
        volontairement global, voir stock_stats). Cache scope a la requete
        (pas au process) : reste correct sans aucune precaution particuliere
        si la valeur est modifiee entre deux requetes (prochaine requete =
        nouveau cache, relit la base), et sans risque de melanger des
        reglages entre deux requetes differentes."""
        cache = g.setdefault('_settings_cache', {})
        if key in cache:
            cached = cache[key]
            return default if cached is _ABSENT else cached
        setting = Setting.query.filter_by(key=key).first()
        if setting is None:
            cache[key] = _ABSENT
            return default
        cache[key] = setting.value
        return setting.value

    @staticmethod
    def set_value(key, value, description=None):
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = Setting(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()
        # Garde le cache de LA REQUETE EN COURS a jour : un set_value() suivi
        # d'un get_value() du meme reglage dans la meme requete doit voir la
        # nouvelle valeur immediatement, pas l'ancienne.
        g.setdefault('_settings_cache', {})[key] = value
        return setting

    def __repr__(self):
        return f'<Setting {self.key}={self.value}>'
