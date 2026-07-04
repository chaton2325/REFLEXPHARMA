from datetime import datetime
from functools import cached_property

from extensions import db


class Vente(db.Model):
    __tablename__ = 'ventes'

    id = db.Column(db.Integer, primary_key=True)
    numero_vente = db.Column(db.String(80), nullable=False, unique=True, index=True)
    statut = db.Column(db.String(30), nullable=False, default='validee')
    mode_paiement = db.Column(db.String(50), nullable=False, default='especes')
    note = db.Column(db.Text)

    client_id = db.Column(db.Integer, nullable=True)
    client_matricule = db.Column(db.String(50))
    client_nom = db.Column(db.String(120))
    client_prenom = db.Column(db.String(120))
    client_email = db.Column(db.String(150))
    groupe_client_id = db.Column(db.Integer, nullable=True)
    groupe_client_nom = db.Column(db.String(120))
    groupe_absorption_pourcentage = db.Column(db.Float, nullable=False, default=0.0)

    total_ht = db.Column(db.Float, nullable=False, default=0.0)
    total_tva = db.Column(db.Float, nullable=False, default=0.0)
    total_ttc = db.Column(db.Float, nullable=False, default=0.0)
    montant_recu = db.Column(db.Float, nullable=False, default=0.0)
    montant_hors_solde = db.Column(db.Float, nullable=False, default=0.0)
    montant_solde_client = db.Column(db.Float, nullable=False, default=0.0)
    montant_solde_groupe = db.Column(db.Float, nullable=False, default=0.0)
    monnaie_rendue = db.Column(db.Float, nullable=False, default=0.0)
    solde_client_avant = db.Column(db.Float, nullable=False, default=0.0)
    solde_client_apres = db.Column(db.Float, nullable=False, default=0.0)
    solde_groupe_avant = db.Column(db.Float, nullable=False, default=0.0)
    solde_groupe_apres = db.Column(db.Float, nullable=False, default=0.0)

    auteur_id = db.Column(db.Integer, nullable=True)
    auteur_nom = db.Column(db.String(100))
    auteur_prenom = db.Column(db.String(100))
    auteur_email = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @cached_property
    def lignes(self):
        return VenteLigne.query.filter_by(numero_vente=self.numero_vente).order_by(VenteLigne.id.asc()).all()

    @property
    def client_label(self):
        label = f'{self.client_prenom or ""} {self.client_nom or ""}'.strip()
        return label or 'Client comptoir'

    @cached_property
    def total_tva_reelle(self):
        """TVA effective (hors marge/coefficient), calculee ligne par ligne."""
        return sum(ligne.tva_reelle for ligne in self.lignes)

    @cached_property
    def total_benefice(self):
        """Marge liee au coefficient produit, distincte de la TVA."""
        return sum(ligne.benefice for ligne in self.lignes)

    def __repr__(self):
        return f'<Vente {self.numero_vente}>'


class VenteLigne(db.Model):
    __tablename__ = 'vente_lignes'

    id = db.Column(db.Integer, primary_key=True)
    vente_id = db.Column(db.Integer, nullable=True)
    numero_vente = db.Column(db.String(80), nullable=False, index=True)
    produit_id = db.Column(db.Integer, nullable=True)
    produit_code = db.Column(db.String(50))
    produit_nom = db.Column(db.String(200), nullable=False)
    produit_fournisseur = db.Column(db.String(120))
    produit_groupe_fournisseur = db.Column(db.String(120))
    produit_rayon = db.Column(db.String(120))
    produit_famille = db.Column(db.String(120))
    produit_section = db.Column(db.String(120))
    produit_conditionnement = db.Column(db.Integer)
    produit_codes_suivi = db.Column(db.Text)
    produit_dates_peremption = db.Column(db.Text)
    stock_unite_avant = db.Column(db.Float, nullable=False, default=0.0)
    stock_sous_unite_avant = db.Column(db.Float, nullable=False, default=0.0)
    stock_sous_sous_unite_avant = db.Column(db.Float, nullable=False, default=0.0)
    unite = db.Column(db.String(30), nullable=False, default='unite')
    quantite = db.Column(db.Float, nullable=False, default=1.0)
    prix_unitaire_ht = db.Column(db.Float, nullable=False, default=0.0)
    prix_unitaire_ttc = db.Column(db.Float, nullable=False, default=0.0)
    tva_pourcentage = db.Column(db.Float, nullable=False, default=0.0)
    total_ht = db.Column(db.Float, nullable=False, default=0.0)
    total_tva = db.Column(db.Float, nullable=False, default=0.0)
    total_ttc = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def tva_reelle(self):
        """Montant de TVA effective (basee sur le taux applique a la vente), hors marge."""
        return self.total_ht * (self.tva_pourcentage / 100)

    @property
    def benefice(self):
        """Marge (coefficient) residuelle : ce que total_tva stocke en trop de la TVA reelle."""
        return max(self.total_ttc - self.total_ht - self.tva_reelle, 0)

    @property
    def coefficient_applique(self):
        """Coefficient tel qu'applique au moment de la vente, deduit du benefice constate."""
        if not self.total_ht:
            return 1.0
        return (self.total_ht + self.benefice) / self.total_ht

    def __repr__(self):
        return f'<VenteLigne {self.produit_nom} x {self.quantite}>'
