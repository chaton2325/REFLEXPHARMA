from extensions import db
from datetime import datetime

class Produit(db.Model):
    __tablename__ = 'produits'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    code_produit = db.Column(db.String(50), unique=True, nullable=False)
    
    # Relations
    fournisseur_id = db.Column(db.Integer, db.ForeignKey('fournisseurs.id'), nullable=False)
    rayon_id = db.Column(db.Integer, db.ForeignKey('rayons.id'))
    famille_id = db.Column(db.Integer, db.ForeignKey('familles.id'))
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'))
    
    # Conditionnement: 1, 2 ou 3
    conditionnement = db.Column(db.Integer, default=1)
    
    # Prix
    prix_unite = db.Column(db.Float, default=0.0)
    prix_sous_unite = db.Column(db.Float, nullable=True) # Utilise si conditionnement >= 2
    prix_sous_sous_unite = db.Column(db.Float, nullable=True) # Utilise si conditionnement == 3
    
    # Parametres financiers (peuvent surcharger ceux du fournisseur)
    coefficient = db.Column(db.Float, nullable=True)
    tva = db.Column(db.Float, nullable=True)

    # Stock de securite (seuil d'alerte, exprime en unites)
    stock_securite = db.Column(db.Integer, default=0)

    # Points de fidelite par unite achetee. NULL = pas de regle sur ce produit
    # (voir points_fidelite_effectif pour le repli vers famille/rayon/section).
    points_fidelite = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def effectif_coefficient(self):
        if self.coefficient is not None:
            return self.coefficient
        return self.fournisseur.effectif_coefficient if self.fournisseur else 1.0

    @property
    def effectif_tva(self):
        if self.tva is not None:
            return self.tva
        return self.fournisseur.effectif_tva if self.fournisseur else 20.0

    @property
    def points_fidelite_effectif(self):
        """Points de fidelite par unite achetee, avec repli produit > famille >
        rayon > section (la premiere valeur non NULL rencontree l'emporte, sans
        cumul), sinon 0 si aucun niveau n'a de regle definie."""
        if self.points_fidelite is not None:
            return self.points_fidelite
        if self.famille and self.famille.points_fidelite is not None:
            return self.famille.points_fidelite
        if self.rayon and self.rayon.points_fidelite is not None:
            return self.rayon.points_fidelite
        if self.section and self.section.points_fidelite is not None:
            return self.section.points_fidelite
        return 0

    # ------------------------------------------------------------------
    # Logique de prix : prix_unite / prix_sous_unite / prix_sous_sous_unite
    # stockent le PRIX D'ACHAT (PA). Tout le reste (prix de vente HT, TVA,
    # bénéfice, prix de vente TTC) est dérivé du coefficient et du taux de
    # TVA effectifs, jamais stocké :
    #   PVHT = PA x coefficient
    #   Bénéfice = PVHT - PA (= PA x (coefficient - 1))
    #   TVA = PVHT x (taux / 100)  — calculée sur le PVHT, pas sur le PA
    #   PVTTC = PVHT + TVA
    # ------------------------------------------------------------------

    def _prix_vente_ht(self, prix_achat):
        if prix_achat is None:
            return None
        return prix_achat * (self.effectif_coefficient or 1.0)

    def _benefice(self, prix_achat):
        prix_vente_ht = self._prix_vente_ht(prix_achat)
        if prix_vente_ht is None:
            return None
        return prix_vente_ht - prix_achat

    def _montant_tva(self, prix_achat):
        prix_vente_ht = self._prix_vente_ht(prix_achat)
        if prix_vente_ht is None:
            return None
        return prix_vente_ht * ((self.effectif_tva or 0.0) / 100)

    def _calculate_ttc(self, prix_achat):
        prix_vente_ht = self._prix_vente_ht(prix_achat)
        if prix_vente_ht is None:
            return None
        return prix_vente_ht + self._montant_tva(prix_achat)

    @property
    def prix_vente_unite_ht(self):
        return self._prix_vente_ht(self.prix_unite)

    @property
    def prix_vente_sous_unite_ht(self):
        return self._prix_vente_ht(self.prix_sous_unite)

    @property
    def prix_vente_sous_sous_unite_ht(self):
        return self._prix_vente_ht(self.prix_sous_sous_unite)

    @property
    def benefice_unite(self):
        return self._benefice(self.prix_unite)

    @property
    def benefice_sous_unite(self):
        return self._benefice(self.prix_sous_unite)

    @property
    def benefice_sous_sous_unite(self):
        return self._benefice(self.prix_sous_sous_unite)

    @property
    def montant_tva_unite(self):
        return self._montant_tva(self.prix_unite)

    @property
    def montant_tva_sous_unite(self):
        return self._montant_tva(self.prix_sous_unite)

    @property
    def montant_tva_sous_sous_unite(self):
        return self._montant_tva(self.prix_sous_sous_unite)

    @property
    def prix_unite_ttc(self):
        return self._calculate_ttc(self.prix_unite)

    @property
    def prix_sous_unite_ttc(self):
        return self._calculate_ttc(self.prix_sous_unite)

    @property
    def prix_sous_sous_unite_ttc(self):
        return self._calculate_ttc(self.prix_sous_sous_unite)

    def __repr__(self):
        return f'<Produit {self.nom} ({self.code_produit})>'
