from datetime import datetime
from extensions import db


class Commande(db.Model):
    """Commande passée auprès d'un fournisseur défini dans l'application.

    Les informations fournisseur/produits sont snapshotées pour que
    l'historique reste lisible même si le fournisseur ou les produits
    sont modifiés ou supprimés plus tard.
    """
    __tablename__ = 'commandes'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(40), unique=True, nullable=False, index=True)
    statut = db.Column(db.String(30), nullable=False, default='en_cours')  # 'en_cours', 'livree', 'annulee'

    fournisseur_id = db.Column(db.Integer, db.ForeignKey('fournisseurs.id', ondelete='SET NULL'), nullable=True)
    fournisseur = db.relationship('Fournisseur')
    fournisseur_nom = db.Column(db.String(100), nullable=False)

    note = db.Column(db.Text, nullable=True)

    # Numéro de la commande d'origine si celle-ci est une relance de manquants
    relance_de_numero = db.Column(db.String(40), nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    created_by_nom = db.Column(db.String(200), nullable=True)

    livree_at = db.Column(db.DateTime, nullable=True)
    livree_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    livree_by = db.relationship('User', foreign_keys=[livree_by_id])
    livree_by_nom = db.Column(db.String(200), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @property
    def total_commande(self):
        return sum(l.quantite_commandee or 0 for l in self.lignes)

    @property
    def total_livre(self):
        return sum(l.quantite_livree or 0 for l in self.lignes)

    @property
    def montant_commande_ht(self):
        return sum(l.montant_commande_ht for l in self.lignes)

    @property
    def montant_livre_ht(self):
        return sum(l.montant_livre_ht for l in self.lignes)

    @property
    def nb_lignes_ecart(self):
        return sum(1 for l in self.lignes if l.a_ecart)

    @property
    def a_ecart(self):
        return self.nb_lignes_ecart > 0

    @property
    def lignes_manquantes(self):
        """Lignes livrées en quantité inférieure au commandé."""
        return [l for l in self.lignes if l.ecart is not None and l.ecart < 0]

    @property
    def total_manquant(self):
        return sum(-l.ecart for l in self.lignes_manquantes)

    def __repr__(self):
        return f'<Commande {self.numero} ({self.statut})>'


class CommandeLigne(db.Model):
    __tablename__ = 'commande_lignes'

    id = db.Column(db.Integer, primary_key=True)
    commande_id = db.Column(db.Integer, db.ForeignKey('commandes.id', ondelete='CASCADE'), nullable=False)
    commande = db.relationship('Commande', backref=db.backref('lignes', lazy=True, cascade='all, delete-orphan'))

    produit_id = db.Column(db.Integer, db.ForeignKey('produits.id', ondelete='SET NULL'), nullable=True)
    produit = db.relationship('Produit')
    produit_nom = db.Column(db.String(200), nullable=False)
    produit_code = db.Column(db.String(50), nullable=True)

    # Prix unitaire HT au moment de la commande (pour estimer les montants)
    prix_unite_ht = db.Column(db.Float, default=0.0)
    # Stock (en unités) au moment où la commande a été passée
    stock_unites_au_moment = db.Column(db.Integer, default=0)

    # Quantités en unités
    quantite_commandee = db.Column(db.Integer, nullable=False, default=0)
    quantite_livree = db.Column(db.Integer, nullable=True)  # None tant que non livrée

    created_at = db.Column(db.DateTime, default=datetime.now)

    @property
    def ecart(self):
        if self.quantite_livree is None:
            return None
        return self.quantite_livree - (self.quantite_commandee or 0)

    @property
    def a_ecart(self):
        e = self.ecart
        return e is not None and e != 0

    @property
    def montant_commande_ht(self):
        return (self.quantite_commandee or 0) * (self.prix_unite_ht or 0)

    @property
    def montant_livre_ht(self):
        return (self.quantite_livree or 0) * (self.prix_unite_ht or 0)

    @property
    def quantite_cible_stock(self):
        """Quantite de reference pour le suivi de mise en stock : livree si deja
        renseignee, sinon commandee."""
        return self.quantite_livree if self.quantite_livree is not None else (self.quantite_commandee or 0)

    @property
    def quantite_mise_en_stock(self):
        """Unites deja entrees en stock a partir de cette ligne (via l'entree en
        stock rapide depuis le module Commandes)."""
        return sum((s.quantite_unites or 0) for s in self.stocks_lies)

    @property
    def quantite_restante_a_stocker(self):
        return max(self.quantite_cible_stock - self.quantite_mise_en_stock, 0)

    @property
    def entierement_mise_en_stock(self):
        return self.quantite_cible_stock > 0 and self.quantite_restante_a_stocker == 0

    def __repr__(self):
        return f'<CommandeLigne {self.produit_nom} (C: {self.quantite_commandee}, L: {self.quantite_livree})>'
