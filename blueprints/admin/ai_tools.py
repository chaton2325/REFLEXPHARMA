"""Outils (function-calling) que l'assistante IA de ReflexPharma peut appeler pour
repondre avec de vraies donnees de la pharmacie (ventes, chiffre d'affaires, stock,
clients, employes) plutot que des reponses generiques.

Chaque fonction `tool_*` retourne un dict JSON-serialisable. `call_ai_tool()` est le
point d'entree unique utilise par la vue Flask : il capture toute exception pour ne
jamais faire planter la conversation, et renvoie {'error': ...} a la place.
"""

import os
import re
import unicodedata
import uuid
from datetime import datetime, date, timedelta
from xml.sax.saxutils import escape as xml_escape

from flask import url_for
from sqlalchemy import func, or_

from extensions import db
from models.vente import Vente, VenteLigne
from models.stock import Stock
from models.stock_exit_log import StockExitLog
from models.produit import Produit
from models.fournisseur import Fournisseur
from models.groupe_fournisseur import GroupeFournisseur
from models.client import Client
from models.groupe_client import GroupeClient
from models.inventaire import Inventaire, InventaireLigne
from models.user import User
from models.poste import Poste
from utils.permissions import FEATURES


# ---------------------------------------------------------------------------
# Resolution des periodes (evite de faire faire des calculs de dates au LLM)
# ---------------------------------------------------------------------------

PERIODES_VALIDES = [
    'aujourd_hui', 'hier', 'cette_semaine', 'semaine_derniere',
    'ce_mois', 'mois_dernier', 'cette_annee', 'personnalise'
]

_PERIODE_DESC = (
    "Periode a analyser. Valeurs possibles : aujourd_hui, hier, cette_semaine, "
    "semaine_derniere, ce_mois, mois_dernier, cette_annee, ou 'personnalise' "
    "(fournir alors aussi date_debut et date_fin au format AAAA-MM-JJ)."
)

_MODULE_DESC = (
    "Cle du module/fonctionnalite dont on veut verifier les acces. Valeurs possibles : "
    + ', '.join(f"{cle} ({nom})" for cle, nom in FEATURES.items())
)


def _resolve_periode(periode, date_debut=None, date_fin=None):
    today = date.today()
    periode = (periode or 'aujourd_hui').strip()

    if periode == 'personnalise':
        if not date_debut or not date_fin:
            raise ValueError("date_debut et date_fin (format AAAA-MM-JJ) sont requis pour periode='personnalise'.")
        try:
            start = datetime.strptime(date_debut, '%Y-%m-%d').date()
            end = datetime.strptime(date_fin, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError("Format de date invalide, utilisez AAAA-MM-JJ.")
        label = f"du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')}"
    elif periode == 'aujourd_hui':
        start = end = today
        label = "aujourd'hui"
    elif periode == 'hier':
        start = end = today - timedelta(days=1)
        label = "hier"
    elif periode == 'cette_semaine':
        start = today - timedelta(days=today.weekday())
        end = today
        label = "cette semaine"
    elif periode == 'semaine_derniere':
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        label = "la semaine dernière"
    elif periode == 'ce_mois':
        start = today.replace(day=1)
        end = today
        label = "ce mois-ci"
    elif periode == 'mois_dernier':
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        label = "le mois dernier"
    elif periode == 'cette_annee':
        start = today.replace(month=1, day=1)
        end = today
        label = "cette année"
    else:
        raise ValueError(f"Periode inconnue: {periode}. Valeurs valides: {', '.join(PERIODES_VALIDES)}")

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())
    return start_dt, end_dt, label


def _round2(value):
    return round(float(value or 0), 2)


_CONDITIONNEMENT_LABELS = {
    1: 'Cond 1 — unité seule',
    2: 'Cond 2 — unité + sous-unité',
    3: 'Cond 3 — unité + sous-unité + sous-sous-unité',
}


def _conditionnement_label(n):
    """'Conditionnement' = structure d'emballage du produit (combien de niveaux :
    unite / sous-unite / sous-sous-unite), PAS la quantite en stock."""
    return _CONDITIONNEMENT_LABELS.get(n, f'Cond {n}' if n is not None else 'Non précisé')


# ---------------------------------------------------------------------------
# Ventes / chiffre d'affaires
# ---------------------------------------------------------------------------

def tool_chiffre_affaires_periode(periode='aujourd_hui', date_debut=None, date_fin=None):
    start_dt, end_dt, label = _resolve_periode(periode, date_debut, date_fin)
    count, ttc, ht = db.session.query(
        func.count(Vente.id),
        func.coalesce(func.sum(Vente.total_ttc), 0.0),
        func.coalesce(func.sum(Vente.total_ht), 0.0),
    ).filter(
        Vente.created_at >= start_dt,
        Vente.created_at <= end_dt,
        Vente.statut != 'annulee'
    ).one()
    count = int(count or 0)
    ttc = float(ttc or 0)
    return {
        'periode': label,
        'nombre_ventes': count,
        'chiffre_affaires_ttc': _round2(ttc),
        'chiffre_affaires_ht': _round2(ht),
        'panier_moyen_ttc': _round2(ttc / count) if count else 0.0,
    }


def tool_comparer_ca_mois_precedent():
    curr = tool_chiffre_affaires_periode('ce_mois')
    prev = tool_chiffre_affaires_periode('mois_dernier')
    variation_montant = curr['chiffre_affaires_ttc'] - prev['chiffre_affaires_ttc']
    variation_pourcentage = (
        _round2(variation_montant / prev['chiffre_affaires_ttc'] * 100)
        if prev['chiffre_affaires_ttc'] else None
    )
    return {
        'ce_mois': curr,
        'mois_dernier': prev,
        'variation_montant_ttc': _round2(variation_montant),
        'variation_pourcentage': variation_pourcentage,
        'tendance': 'hausse' if variation_montant > 0 else ('baisse' if variation_montant < 0 else 'stable'),
    }


def tool_prevision_chiffre_affaires(horizon_jours=7):
    horizon_jours = max(1, min(int(horizon_jours or 7), 60))
    jours_historique = 30
    today = date.today()
    start = today - timedelta(days=jours_historique - 1)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())

    rows = db.session.query(
        func.date(Vente.created_at),
        func.coalesce(func.sum(Vente.total_ttc), 0.0)
    ).filter(
        Vente.created_at >= start_dt,
        Vente.created_at <= end_dt,
        Vente.statut != 'annulee'
    ).group_by(func.date(Vente.created_at)).all()

    daily_totals = {}
    for day_val, total in rows:
        day_key = datetime.strptime(day_val, '%Y-%m-%d').date() if isinstance(day_val, str) else day_val
        daily_totals[day_key] = float(total or 0)

    series = []
    curr = start
    while curr <= today:
        series.append(daily_totals.get(curr, 0.0))
        curr += timedelta(days=1)

    n = len(series)
    if n < 4:
        return {'erreur': "Pas assez d'historique de ventes (minimum 4 jours) pour calculer une prevision fiable."}

    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(series) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den else 0.0
    intercept = mean_y - slope * mean_x

    target_date = today + timedelta(days=horizon_jours)
    predicted_last_day = max(slope * (n - 1 + horizon_jours) + intercept, 0.0)
    predicted_cumulative = sum(
        max(slope * (n - 1 + i) + intercept, 0.0) for i in range(1, horizon_jours + 1)
    )

    return {
        'methode': "regression lineaire (moindres carres) sur le chiffre d'affaires quotidien des 30 derniers jours",
        'jours_historique_utilises': n,
        'tendance': 'croissante' if slope > 0 else ('decroissante' if slope < 0 else 'stable'),
        'variation_quotidienne_moyenne_ttc': _round2(slope),
        'date_cible': target_date.strftime('%Y-%m-%d'),
        'ca_ttc_estime_ce_jour_la': _round2(predicted_last_day),
        'ca_ttc_estime_cumule_sur_la_periode': _round2(predicted_cumulative),
    }


# ---------------------------------------------------------------------------
# Employes
# ---------------------------------------------------------------------------

def tool_employe_du_mois(periode='ce_mois'):
    if periode not in ('ce_mois', 'mois_dernier'):
        periode = 'ce_mois'
    start_dt, end_dt, label = _resolve_periode(periode)

    rows = db.session.query(
        Vente.auteur_id, Vente.auteur_nom, Vente.auteur_prenom,
        func.count(Vente.id), func.coalesce(func.sum(Vente.total_ttc), 0.0)
    ).filter(
        Vente.created_at >= start_dt,
        Vente.created_at <= end_dt,
        Vente.statut != 'annulee'
    ).group_by(Vente.auteur_id, Vente.auteur_nom, Vente.auteur_prenom).order_by(
        func.sum(Vente.total_ttc).desc()
    ).limit(5).all()

    classement = [
        {
            'employe': (f'{prenom or ""} {nom or ""}'.strip() or 'Employé inconnu'),
            'nombre_ventes': int(count or 0),
            'chiffre_affaires_ttc': _round2(ttc),
        }
        for _, nom, prenom, count, ttc in rows
    ]

    return {
        'periode': label,
        'classement': classement,
        'employe_du_mois': classement[0]['employe'] if classement else None,
    }


# ---------------------------------------------------------------------------
# Produits / stock
# ---------------------------------------------------------------------------

def tool_nombre_produits():
    total = db.session.query(func.count(Produit.id)).scalar() or 0
    return {'nombre_produits_catalogue': int(total)}


def tool_liste_produits(recherche=None, limite=50):
    """Liste le CATALOGUE de produits (fiche produit : nom, code, fournisseur, rayon,
    famille). Ne contient aucune quantite en stock — pour ca, voir stock_produit /
    produits_stock_faible, qui portent sur une notion differente (le stock physique)."""
    limite = max(1, min(int(limite or 50), 200))
    query = Produit.query
    recherche = (recherche or '').strip()
    if recherche:
        query = query.filter(
            or_(
                Produit.nom.ilike(f'%{recherche}%'),
                Produit.code_produit.ilike(f'%{recherche}%')
            )
        )

    total = query.count()
    produits = query.order_by(Produit.nom.asc()).limit(limite).all()

    return {
        'nombre_total_correspondant': total,
        'produits': [
            {
                'produit': p.nom,
                'code_produit': p.code_produit,
                'fournisseur': p.fournisseur.nom if p.fournisseur else None,
                'rayon': p.rayon.nom if p.rayon else None,
                'famille': p.famille.nom if p.famille else None,
                'conditionnement': p.conditionnement,
                'conditionnement_label': _conditionnement_label(p.conditionnement),
            }
            for p in produits
        ],
    }


def tool_liste_fournisseurs(recherche=None, limite=50):
    """Liste les fournisseurs avec leur coefficient et taux de TVA effectifs (propres au
    fournisseur, ou herites de son groupe fournisseur si non personnalises)."""
    limite = max(1, min(int(limite or 50), 200))
    query = Fournisseur.query
    recherche = (recherche or '').strip()
    if recherche:
        query = query.filter(
            or_(
                Fournisseur.nom.ilike(f'%{recherche}%'),
                Fournisseur.prefixe.ilike(f'%{recherche}%')
            )
        )

    total = query.count()
    fournisseurs = query.order_by(Fournisseur.nom.asc()).limit(limite).all()

    return {
        'nombre_total_correspondant': total,
        'fournisseurs': [
            {
                'fournisseur': f.nom,
                'prefixe': f.prefixe,
                'groupe_fournisseur': f.groupe.nom if f.groupe else None,
                'coefficient': _round2(f.effectif_coefficient),
                'coefficient_personnalise': f.coefficient is not None,
                'tva_pourcentage': _round2(f.effectif_tva),
                'tva_personnalisee': f.tva is not None,
                'contact': f.contact,
            }
            for f in fournisseurs
        ],
    }


def tool_liste_groupes_fournisseurs(recherche=None):
    """Liste les groupes fournisseurs avec leur coefficient et TVA par defaut (herites par
    les fournisseurs du groupe qui n'ont pas de valeur personnalisee)."""
    query = GroupeFournisseur.query
    recherche = (recherche or '').strip()
    if recherche:
        query = query.filter(GroupeFournisseur.nom.ilike(f'%{recherche}%'))

    groupes = query.order_by(GroupeFournisseur.nom.asc()).all()
    return {
        'nombre_groupes': len(groupes),
        'groupes': [
            {
                'groupe_fournisseur': g.nom,
                'coefficient_par_defaut': _round2(g.coefficient_defaut),
                'tva_par_defaut_pourcentage': _round2(g.tva_defaut),
                'nombre_fournisseurs': len(g.fournisseurs),
            }
            for g in groupes
        ],
    }


def tool_stock_produit(nom_produit):
    nom_produit = (nom_produit or '').strip()
    if not nom_produit:
        raise ValueError("Le parametre nom_produit est requis.")

    produits = Produit.query.filter(
        or_(
            Produit.nom.ilike(f'%{nom_produit}%'),
            Produit.code_produit.ilike(f'%{nom_produit}%')
        )
    ).limit(5).all()

    if not produits:
        return {'trouve': False, 'message': f"Aucun produit ne correspond a '{nom_produit}'."}

    resultats = []
    for p in produits:
        u, su, ssu, nb_lots, prochaine_peremption = db.session.query(
            func.coalesce(func.sum(Stock.quantite_unites), 0),
            func.coalesce(func.sum(Stock.quantite_sous_unites), 0),
            func.coalesce(func.sum(Stock.quantite_sous_sous_unites), 0),
            func.count(Stock.id),
            func.min(Stock.date_peremption),
        ).filter(Stock.produit_id == p.id).one()
        resultats.append({
            'produit': p.nom,
            'code_produit': p.code_produit,
            'conditionnement': p.conditionnement,
            'conditionnement_label': _conditionnement_label(p.conditionnement),
            'quantite_unites': int(u or 0),
            'quantite_sous_unites': int(su or 0),
            'quantite_sous_sous_unites': int(ssu or 0),
            'nombre_lots': int(nb_lots or 0),
            'prochaine_peremption': prochaine_peremption.strftime('%Y-%m-%d') if prochaine_peremption else None,
        })

    return {'trouve': True, 'resultats': resultats}


def tool_produits_stock_faible(seuil=10, limite=15):
    seuil = max(0, int(seuil or 10))
    limite = max(1, min(int(limite or 15), 50))

    total_expr = (
        func.coalesce(func.sum(Stock.quantite_unites), 0)
        + func.coalesce(func.sum(Stock.quantite_sous_unites), 0)
        + func.coalesce(func.sum(Stock.quantite_sous_sous_unites), 0)
    )

    rows = db.session.query(
        Produit.nom, Produit.code_produit, total_expr.label('total')
    ).outerjoin(Stock, Stock.produit_id == Produit.id).group_by(
        Produit.id, Produit.nom, Produit.code_produit
    ).having(total_expr <= seuil).order_by(total_expr.asc()).limit(limite).all()

    return {
        'seuil': seuil,
        'nombre_produits_concernes': len(rows),
        'produits': [
            {'produit': nom, 'code_produit': code, 'quantite_totale': int(total or 0)}
            for nom, code, total in rows
        ],
    }


def tool_produits_peremption_proche(nb_jours=30, limite=15):
    nb_jours = max(1, min(int(nb_jours or 30), 365))
    limite = max(1, min(int(limite or 15), 50))
    today = date.today()
    limite_date = today + timedelta(days=nb_jours)

    rows = db.session.query(Stock, Produit.nom, Produit.code_produit).join(
        Produit, Stock.produit_id == Produit.id
    ).filter(
        Stock.date_peremption >= today,
        Stock.date_peremption <= limite_date
    ).order_by(Stock.date_peremption.asc()).limit(limite).all()

    return {
        'horizon_jours': nb_jours,
        'nombre_lots_concernes': len(rows),
        'lots': [
            {
                'produit': nom,
                'code_produit': code,
                'date_peremption': stock.date_peremption.strftime('%Y-%m-%d'),
                'quantite_totale': stock.quantite_totale,
                'code_suivi': stock.code_suivi,
            }
            for stock, nom, code in rows
        ],
    }


def tool_top_produits_vendus(periode='ce_mois', critere='chiffre_affaires', limite=5, date_debut=None, date_fin=None):
    start_dt, end_dt, label = _resolve_periode(periode, date_debut, date_fin)
    limite = max(1, min(int(limite or 5), 20))

    query = db.session.query(
        VenteLigne.produit_nom,
        func.coalesce(func.sum(VenteLigne.quantite), 0.0),
        func.coalesce(func.sum(VenteLigne.total_ttc), 0.0)
    ).filter(
        VenteLigne.created_at >= start_dt,
        VenteLigne.created_at <= end_dt
    ).group_by(VenteLigne.produit_nom)

    if critere == 'quantite':
        query = query.order_by(func.sum(VenteLigne.quantite).desc())
    else:
        critere = 'chiffre_affaires'
        query = query.order_by(func.sum(VenteLigne.total_ttc).desc())

    rows = query.limit(limite).all()

    return {
        'periode': label,
        'critere': critere,
        'classement': [
            {'produit': nom, 'quantite_vendue': _round2(qte), 'chiffre_affaires_ttc': _round2(ttc)}
            for nom, qte, ttc in rows
        ],
    }


# ---------------------------------------------------------------------------
# Sorties de stock (ventes, pertes, corrections, transferts...)
# ---------------------------------------------------------------------------

def _quantite_sortie(row):
    return (
        (row.quantite_unites_sortie or 0)
        + (row.quantite_sous_unites_sortie or 0)
        + (row.quantite_sous_sous_unites_sortie or 0)
    )


def tool_sorties_stock_periode(periode='aujourd_hui', date_debut=None, date_fin=None):
    start_dt, end_dt, label = _resolve_periode(periode, date_debut, date_fin)

    count, total_ht, total_ttc, u, su, ssu = db.session.query(
        func.count(StockExitLog.id),
        func.coalesce(func.sum(StockExitLog.total_sortie_ht), 0.0),
        func.coalesce(func.sum(StockExitLog.total_sortie_ttc), 0.0),
        func.coalesce(func.sum(StockExitLog.quantite_unites_sortie), 0),
        func.coalesce(func.sum(StockExitLog.quantite_sous_unites_sortie), 0),
        func.coalesce(func.sum(StockExitLog.quantite_sous_sous_unites_sortie), 0),
    ).filter(
        StockExitLog.created_at >= start_dt,
        StockExitLog.created_at <= end_dt
    ).one()

    raisons = db.session.query(
        StockExitLog.reason_nom,
        func.count(StockExitLog.id),
        func.coalesce(func.sum(StockExitLog.total_sortie_ttc), 0.0)
    ).filter(
        StockExitLog.created_at >= start_dt,
        StockExitLog.created_at <= end_dt
    ).group_by(StockExitLog.reason_nom).order_by(func.sum(StockExitLog.total_sortie_ttc).desc()).all()

    return {
        'periode': label,
        'nombre_sorties': int(count or 0),
        'quantite_totale_sortie': int((u or 0) + (su or 0) + (ssu or 0)),
        'valeur_totale_ht': _round2(total_ht),
        'valeur_totale_ttc': _round2(total_ttc),
        'repartition_par_raison': [
            {'raison': raison or 'Non précisée', 'nombre': int(n), 'valeur_ttc': _round2(v)}
            for raison, n, v in raisons
        ],
    }


def tool_dernieres_sorties_stock(periode='aujourd_hui', date_debut=None, date_fin=None, limite=10):
    limite = max(1, min(int(limite or 10), 50))
    start_dt, end_dt, label = _resolve_periode(periode, date_debut, date_fin)

    rows = StockExitLog.query.filter(
        StockExitLog.created_at >= start_dt,
        StockExitLog.created_at <= end_dt
    ).order_by(StockExitLog.created_at.desc()).limit(limite).all()

    return {
        'periode': label,
        'nombre': len(rows),
        'sorties': [
            {
                'produit': r.produit_nom,
                'quantite': _quantite_sortie(r),
                'raison': r.reason_nom,
                'effectue_par': f'{r.user_prenom} {r.user_nom}'.strip(),
                'valeur_ttc': _round2(r.total_sortie_ttc),
                'date_heure': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else None,
            }
            for r in rows
        ],
    }


def tool_sorties_stock_produit(nom_produit, periode='ce_mois', date_debut=None, date_fin=None):
    nom_produit = (nom_produit or '').strip()
    if not nom_produit:
        raise ValueError("Le parametre nom_produit est requis.")
    start_dt, end_dt, label = _resolve_periode(periode, date_debut, date_fin)

    rows = db.session.query(
        StockExitLog.produit_nom,
        func.count(StockExitLog.id),
        func.coalesce(func.sum(StockExitLog.quantite_unites_sortie), 0),
        func.coalesce(func.sum(StockExitLog.quantite_sous_unites_sortie), 0),
        func.coalesce(func.sum(StockExitLog.quantite_sous_sous_unites_sortie), 0),
        func.coalesce(func.sum(StockExitLog.total_sortie_ttc), 0.0),
    ).filter(
        StockExitLog.created_at >= start_dt,
        StockExitLog.created_at <= end_dt,
        StockExitLog.produit_nom.ilike(f'%{nom_produit}%')
    ).group_by(StockExitLog.produit_nom).all()

    if not rows:
        return {'trouve': False, 'message': f"Aucune sortie de stock pour '{nom_produit}' sur cette periode ({label})."}

    return {
        'trouve': True,
        'periode': label,
        'resultats': [
            {
                'produit': nom,
                'nombre_sorties': int(n),
                'quantite_totale': int((u or 0) + (su or 0) + (ssu or 0)),
                'valeur_ttc': _round2(v),
            }
            for nom, n, u, su, ssu, v in rows
        ],
    }


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

def tool_top_clients(periode='ce_mois', limite=5, date_debut=None, date_fin=None):
    start_dt, end_dt, label = _resolve_periode(periode, date_debut, date_fin)
    limite = max(1, min(int(limite or 5), 20))

    rows = db.session.query(
        Vente.client_nom, Vente.client_prenom,
        func.count(Vente.id), func.coalesce(func.sum(Vente.total_ttc), 0.0)
    ).filter(
        Vente.created_at >= start_dt,
        Vente.created_at <= end_dt,
        Vente.statut != 'annulee',
        Vente.client_id.isnot(None)
    ).group_by(Vente.client_id, Vente.client_nom, Vente.client_prenom).order_by(
        func.sum(Vente.total_ttc).desc()
    ).limit(limite).all()

    return {
        'periode': label,
        'classement': [
            {
                'client': (f'{prenom or ""} {nom or ""}'.strip() or 'Client inconnu'),
                'nombre_achats': int(count or 0),
                'chiffre_affaires_ttc': _round2(ttc),
            }
            for nom, prenom, count, ttc in rows
        ],
    }


def tool_solde_client(recherche):
    recherche = (recherche or '').strip()
    if not recherche:
        raise ValueError("Le parametre 'recherche' (nom, prenom, matricule ou email) est requis.")

    clients = Client.query.filter(
        or_(
            Client.nom.ilike(f'%{recherche}%'),
            Client.prenom.ilike(f'%{recherche}%'),
            Client.matricule.ilike(f'%{recherche}%'),
            Client.email.ilike(f'%{recherche}%')
        )
    ).limit(5).all()

    if not clients:
        return {'trouve': False, 'message': f"Aucun client ne correspond a '{recherche}'."}

    return {
        'trouve': True,
        'resultats': [
            {'client': c.nom_complet, 'matricule': c.matricule, 'solde': _round2(c.solde)}
            for c in clients
        ],
    }


def tool_nombre_clients():
    total = db.session.query(func.count(Client.id)).scalar() or 0
    return {'nombre_clients': int(total)}


def tool_liste_clients(recherche=None, limite=50):
    limite = max(1, min(int(limite or 50), 200))
    query = Client.query
    recherche = (recherche or '').strip()
    if recherche:
        query = query.filter(
            or_(
                Client.nom.ilike(f'%{recherche}%'),
                Client.prenom.ilike(f'%{recherche}%'),
                Client.matricule.ilike(f'%{recherche}%'),
                Client.email.ilike(f'%{recherche}%')
            )
        )

    total = query.count()
    clients = query.order_by(Client.nom.asc()).limit(limite).all()
    return {
        'nombre_total_correspondant': total,
        'clients': [
            {
                'client': c.nom_complet,
                'matricule': c.matricule,
                'groupe': c.groupe.nom if c.groupe else None,
                'solde': _round2(c.solde),
            }
            for c in clients
        ],
    }


def tool_nombre_groupes_clients():
    total = db.session.query(func.count(GroupeClient.id)).scalar() or 0
    return {'nombre_groupes_clients': int(total)}


def tool_liste_groupes_clients():
    rows = db.session.query(
        GroupeClient.nom, GroupeClient.solde, GroupeClient.pourcentage_absorption,
        func.count(Client.id)
    ).outerjoin(Client, Client.groupe_id == GroupeClient.id).group_by(
        GroupeClient.id, GroupeClient.nom, GroupeClient.solde, GroupeClient.pourcentage_absorption
    ).order_by(GroupeClient.nom.asc()).all()

    return {
        'nombre_groupes': len(rows),
        'groupes': [
            {
                'groupe': nom,
                'solde': _round2(solde),
                'pourcentage_absorption': _round2(pct),
                'nombre_clients': int(count),
            }
            for nom, solde, pct, count in rows
        ],
    }


def tool_solde_groupe_client(recherche):
    recherche = (recherche or '').strip()
    if not recherche:
        raise ValueError("Le parametre 'recherche' (nom du groupe) est requis.")

    groupes = GroupeClient.query.filter(GroupeClient.nom.ilike(f'%{recherche}%')).limit(5).all()
    if not groupes:
        return {'trouve': False, 'message': f"Aucun groupe client ne correspond a '{recherche}'."}

    return {
        'trouve': True,
        'resultats': [
            {
                'groupe': g.nom,
                'solde': _round2(g.solde),
                'pourcentage_absorption': _round2(g.pourcentage_absorption),
                'nombre_clients': len(g.clients),
            }
            for g in groupes
        ],
    }


def tool_clients_par_groupe(nom_groupe):
    nom_groupe = (nom_groupe or '').strip()
    if not nom_groupe:
        raise ValueError("Le parametre 'nom_groupe' est requis.")

    groupe = GroupeClient.query.filter(GroupeClient.nom.ilike(f'%{nom_groupe}%')).first()
    if not groupe:
        return {'trouve': False, 'message': f"Aucun groupe client ne correspond a '{nom_groupe}'."}

    clients = Client.query.filter_by(groupe_id=groupe.id).order_by(Client.nom.asc()).all()
    return {
        'trouve': True,
        'groupe': groupe.nom,
        'nombre_clients': len(clients),
        'clients': [
            {'client': c.nom_complet, 'matricule': c.matricule, 'solde': _round2(c.solde)}
            for c in clients
        ],
    }


def tool_clients_sans_groupe(limite=15):
    limite = max(1, min(int(limite or 15), 50))
    total = db.session.query(func.count(Client.id)).filter(Client.groupe_id.is_(None)).scalar() or 0
    clients = Client.query.filter(Client.groupe_id.is_(None)).order_by(Client.nom.asc()).limit(limite).all()
    return {
        'nombre_total_sans_groupe': int(total),
        'apercu': [{'client': c.nom_complet, 'matricule': c.matricule} for c in clients],
    }


def tool_top_clients_solde(limite=10):
    limite = max(1, min(int(limite or 10), 50))
    clients = Client.query.order_by(Client.solde.desc()).limit(limite).all()
    return {
        'classement': [
            {'client': c.nom_complet, 'matricule': c.matricule, 'solde': _round2(c.solde)}
            for c in clients
        ],
    }


def tool_solde_total_clients_et_groupes():
    total_clients = db.session.query(func.coalesce(func.sum(Client.solde), 0.0)).scalar() or 0
    total_groupes = db.session.query(func.coalesce(func.sum(GroupeClient.solde), 0.0)).scalar() or 0
    return {
        'solde_total_clients': _round2(total_clients),
        'solde_total_groupes_clients': _round2(total_groupes),
        'solde_total_general': _round2(total_clients + total_groupes),
    }


# ---------------------------------------------------------------------------
# Inventaires
# ---------------------------------------------------------------------------

def _inventaire_personne_label(user):
    return f'{user.prenom} {user.nom}'.strip() if user else None


def tool_liste_inventaires(limite=10):
    """ReflexPharma ne planifie pas d'inventaires futurs : il n'existe qu'un inventaire
    'en_cours' au plus (le cas echeant) et l'historique des inventaires passes (valide/annule)."""
    limite = max(1, min(int(limite or 10), 50))
    inventaires = Inventaire.query.order_by(Inventaire.created_at.desc()).limit(limite).all()

    resultats = []
    for inv in inventaires:
        lignes = inv.lignes
        resultats.append({
            'titre': inv.titre,
            'statut': inv.statut,
            'cree_le': inv.created_at.strftime('%Y-%m-%d %H:%M') if inv.created_at else None,
            'cree_par': _inventaire_personne_label(inv.created_by),
            'valide_le': inv.validated_at.strftime('%Y-%m-%d %H:%M') if inv.validated_at else None,
            'valide_par': _inventaire_personne_label(inv.validated_by),
            'nombre_produits': len(lignes),
            'nombre_produits_comptes': sum(1 for l in lignes if l.is_scanned),
            'nombre_ecarts': sum(1 for l in lignes if l.a_decalage),
        })

    return {
        'nombre_inventaires': len(resultats),
        'inventaires': resultats,
    }


def tool_detail_inventaire(recherche=None):
    """Sans recherche : renvoie l'inventaire actuellement en cours s'il y en a un, sinon le
    plus recent (donc le 'dernier inventaire')."""
    recherche = (recherche or '').strip()
    if recherche:
        inv = Inventaire.query.filter(Inventaire.titre.ilike(f'%{recherche}%')).order_by(Inventaire.created_at.desc()).first()
    else:
        inv = Inventaire.query.filter_by(statut='en_cours').order_by(Inventaire.created_at.desc()).first()
        if not inv:
            inv = Inventaire.query.order_by(Inventaire.created_at.desc()).first()

    if not inv:
        return {'trouve': False, 'message': "Aucun inventaire trouve."}

    lignes = inv.lignes
    ecarts = [l for l in lignes if l.a_decalage]

    return {
        'trouve': True,
        'titre': inv.titre,
        'statut': inv.statut,
        'cree_le': inv.created_at.strftime('%Y-%m-%d %H:%M') if inv.created_at else None,
        'cree_par': _inventaire_personne_label(inv.created_by),
        'valide_le': inv.validated_at.strftime('%Y-%m-%d %H:%M') if inv.validated_at else None,
        'valide_par': _inventaire_personne_label(inv.validated_by),
        'nombre_produits_total': len(lignes),
        'nombre_produits_comptes': sum(1 for l in lignes if l.is_scanned),
        'nombre_ecarts': len(ecarts),
        'ecarts': [
            {
                'produit': l.produit.nom if l.produit else None,
                'code_suivi': l.code_suivi,
                'quantite_avant': l.total_avant,
                'quantite_apres': l.total_apres,
                'constate_par': _inventaire_personne_label(l.constate_by),
            }
            for l in ecarts[:30]
        ],
        'ecarts_tronques': len(ecarts) > 30,
    }


# ---------------------------------------------------------------------------
# Employes / equipe / permissions
# ---------------------------------------------------------------------------

def tool_nombre_employes():
    total = db.session.query(func.count(User.id)).scalar() or 0
    actifs = db.session.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    par_role = db.session.query(User.role, func.count(User.id)).group_by(User.role).all()
    return {
        'nombre_total_employes': int(total),
        'nombre_employes_actifs': int(actifs),
        'nombre_employes_inactifs': int(total) - int(actifs),
        'repartition_par_role': {role or 'non precise': int(count) for role, count in par_role},
    }


def _employe_ancienne_annees(u):
    if not u.date_prise_poste:
        return None
    jours = (date.today() - u.date_prise_poste).days
    return round(jours / 365.25, 1)


def tool_liste_employes(statut='actifs'):
    query = User.query
    if statut == 'actifs':
        query = query.filter(User.is_active.is_(True))
    elif statut == 'inactifs':
        query = query.filter(User.is_active.is_(False))
    # 'tous' -> pas de filtre

    users = query.order_by(User.nom.asc()).all()
    return {
        'statut_filtre': statut,
        'nombre': len(users),
        'employes': [
            {
                'employe': f'{u.prenom} {u.nom}'.strip(),
                'role': u.role,
                'poste': u.poste,
                'actif': bool(u.is_active),
                'anciennete_annees': _employe_ancienne_annees(u),
            }
            for u in users
        ],
    }


def tool_employes_par_poste():
    rows = db.session.query(User.poste, func.count(User.id)).filter(
        User.is_active.is_(True)
    ).group_by(User.poste).order_by(func.count(User.id).desc()).all()
    return {
        'repartition': [
            {'poste': poste or 'Sans poste attribué', 'nombre_employes': int(count)}
            for poste, count in rows
        ],
    }


def tool_postes_disponibles():
    postes = Poste.query.order_by(Poste.nom.asc()).all()
    return {
        'nombre_postes': len(postes),
        'postes': [{'poste': p.nom, 'description': p.description} for p in postes],
    }


def tool_acces_module(module):
    module = (module or '').strip()
    if module not in FEATURES:
        raise ValueError(
            f"Module inconnu: '{module}'. Modules valides: {', '.join(FEATURES.keys())}"
        )

    users = User.query.filter_by(is_active=True).order_by(User.nom.asc()).all()
    avec_acces, sans_acces = [], []
    for u in users:
        entry = {'employe': f'{u.prenom} {u.nom}'.strip(), 'role': u.role, 'poste': u.poste}
        (avec_acces if u.has_permission(module) else sans_acces).append(entry)

    return {
        'module': module,
        'module_label': FEATURES.get(module, module),
        'nombre_avec_acces': len(avec_acces),
        'employes_avec_acces': avec_acces,
        'nombre_sans_acces': len(sans_acces),
        'employes_sans_acces': sans_acces,
    }


def tool_modules_disponibles():
    """Liste les modules/fonctionnalites dont l'acces peut etre accorde ou restreint."""
    return {'modules': [{'cle': cle, 'nom': nom} for cle, nom in FEATURES.items()]}


# ---------------------------------------------------------------------------
# Generation de rapport PDF telechargeable depuis le chat
# ---------------------------------------------------------------------------

REPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'ai_reports'
)
REPORT_FILENAME_RE = re.compile(r'^[0-9a-f]{32}__[A-Za-z0-9_-]+\.pdf$')


def _cleanup_old_reports(max_age_hours=48):
    """Best-effort : supprime les rapports generes il y a plus de 48h pour ne pas accumuler de fichiers."""
    try:
        if not os.path.isdir(REPORTS_DIR):
            return
        cutoff = datetime.now().timestamp() - max_age_hours * 3600
        for fname in os.listdir(REPORTS_DIR):
            fpath = os.path.join(REPORTS_DIR, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
    except OSError:
        pass


def _build_pdf_report(filepath, titre, sections):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReportTitle', parent=styles['Title'], textColor=colors.HexColor('#2c3e50'), fontSize=18, spaceAfter=4)
    meta_style = ParagraphStyle('ReportMeta', parent=styles['Normal'], textColor=colors.HexColor('#7a8896'), fontSize=9, spaceAfter=16)
    section_style = ParagraphStyle('SectionTitle', parent=styles['Heading2'], textColor=colors.HexColor('#3498db'), fontSize=13, spaceBefore=14, spaceAfter=6)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=14)
    header_cell_style = ParagraphStyle('HeaderCell', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.white, fontName='Helvetica-Bold')
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=9, leading=11)

    doc = SimpleDocTemplate(filepath, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm)
    story = [
        Paragraph(xml_escape(titre), title_style),
        Paragraph(f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — ReflexPharma", meta_style),
    ]

    for section in sections or []:
        section_title = (section.get('titre_section') or '').strip()
        if section_title:
            story.append(Paragraph(xml_escape(section_title), section_style))

        texte = (section.get('texte') or '').strip()
        if texte:
            for line in texte.split('\n'):
                if line.strip():
                    story.append(Paragraph(xml_escape(line.strip()), body_style))
            story.append(Spacer(1, 6))

        tableau = section.get('tableau') or {}
        colonnes = tableau.get('colonnes') or []
        lignes = tableau.get('lignes') or []
        if colonnes and lignes:
            header = [Paragraph(xml_escape(str(c)), header_cell_style) for c in colonnes]
            body_rows = [
                [Paragraph(xml_escape(str(cell)) if cell is not None else '', cell_style) for cell in row]
                for row in lignes
            ]
            table = Table([header] + body_rows, hAlign='LEFT', repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafd')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e4ea')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(table)
            story.append(Spacer(1, 10))

    doc.build(story)


def tool_generer_rapport_pdf(titre, sections):
    titre = (titre or 'Rapport ReflexPharma').strip() or 'Rapport ReflexPharma'
    if not isinstance(sections, list) or not sections:
        raise ValueError(
            "Le parametre 'sections' est requis et doit contenir au moins une section "
            "(avec un titre_section et du texte et/ou un tableau)."
        )

    os.makedirs(REPORTS_DIR, exist_ok=True)
    _cleanup_old_reports()

    token = uuid.uuid4().hex
    ascii_titre = unicodedata.normalize('NFKD', titre).encode('ascii', 'ignore').decode('ascii')
    safe_titre = re.sub(r'[^A-Za-z0-9_-]+', '_', ascii_titre).strip('_') or 'rapport'
    filename = f'{token}__{safe_titre}.pdf'
    filepath = os.path.join(REPORTS_DIR, filename)

    _build_pdf_report(filepath, titre, sections)

    return {
        'pdf_genere': True,
        'titre': titre,
        'nom_fichier': f'{safe_titre}.pdf',
        'url_telechargement': url_for('admin.assistant_download_report', filename=filename),
    }


# ---------------------------------------------------------------------------
# Registre des outils + schemas JSON (format compatible Mistral/OpenAI tool-calling)
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    'chiffre_affaires_periode': tool_chiffre_affaires_periode,
    'comparer_ca_mois_precedent': tool_comparer_ca_mois_precedent,
    'prevision_chiffre_affaires': tool_prevision_chiffre_affaires,
    'employe_du_mois': tool_employe_du_mois,
    'nombre_produits': tool_nombre_produits,
    'liste_produits': tool_liste_produits,
    'liste_fournisseurs': tool_liste_fournisseurs,
    'liste_groupes_fournisseurs': tool_liste_groupes_fournisseurs,
    'stock_produit': tool_stock_produit,
    'produits_stock_faible': tool_produits_stock_faible,
    'produits_peremption_proche': tool_produits_peremption_proche,
    'top_produits_vendus': tool_top_produits_vendus,
    'sorties_stock_periode': tool_sorties_stock_periode,
    'dernieres_sorties_stock': tool_dernieres_sorties_stock,
    'sorties_stock_produit': tool_sorties_stock_produit,
    'top_clients': tool_top_clients,
    'solde_client': tool_solde_client,
    'nombre_clients': tool_nombre_clients,
    'liste_clients': tool_liste_clients,
    'nombre_groupes_clients': tool_nombre_groupes_clients,
    'liste_groupes_clients': tool_liste_groupes_clients,
    'solde_groupe_client': tool_solde_groupe_client,
    'clients_par_groupe': tool_clients_par_groupe,
    'clients_sans_groupe': tool_clients_sans_groupe,
    'top_clients_solde': tool_top_clients_solde,
    'solde_total_clients_et_groupes': tool_solde_total_clients_et_groupes,
    'liste_inventaires': tool_liste_inventaires,
    'detail_inventaire': tool_detail_inventaire,
    'nombre_employes': tool_nombre_employes,
    'liste_employes': tool_liste_employes,
    'employes_par_poste': tool_employes_par_poste,
    'postes_disponibles': tool_postes_disponibles,
    'acces_module': tool_acces_module,
    'modules_disponibles': tool_modules_disponibles,
    'generer_rapport_pdf': tool_generer_rapport_pdf,
}


def call_ai_tool(name, arguments):
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return {'error': f"Outil inconnu: {name}"}
    try:
        return fn(**(arguments or {}))
    except TypeError as exc:
        return {'error': f"Parametres invalides pour {name}: {exc}"}
    except ValueError as exc:
        return {'error': str(exc)}
    except Exception as exc:  # ne jamais faire planter la conversation
        return {'error': f"Erreur interne lors de l'appel a {name}: {exc}"}


AI_TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'chiffre_affaires_periode',
            'description': (
                "Donne le nombre de ventes, le chiffre d'affaires (HT et TTC) et le panier moyen "
                "sur une periode donnee (aujourd'hui, hier, cette semaine, ce mois, une periode "
                "personnalisee, etc.)."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'enum': PERIODES_VALIDES, 'description': _PERIODE_DESC},
                    'date_debut': {'type': 'string', 'description': "Date de debut AAAA-MM-JJ, uniquement si periode='personnalise'."},
                    'date_fin': {'type': 'string', 'description': "Date de fin AAAA-MM-JJ, uniquement si periode='personnalise'."},
                },
                'required': ['periode'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'comparer_ca_mois_precedent',
            'description': (
                "Compare le chiffre d'affaires du mois en cours avec celui du mois precedent et "
                "calcule la variation en montant et en pourcentage. A utiliser pour toute question "
                "du type 'comment se compare le CA / les ventes par rapport au mois dernier'."
            ),
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'prevision_chiffre_affaires',
            'description': (
                "Calcule une prevision du chiffre d'affaires futur par regression lineaire sur les "
                "30 derniers jours de ventes quotidiennes, et projette la tendance sur un horizon "
                "donne (en jours, defaut 7). A utiliser pour toute question sur les previsions, "
                "tendances ou projections de ventes futures."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'horizon_jours': {'type': 'integer', 'description': "Nombre de jours a projeter dans le futur (defaut 7, max 60)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'employe_du_mois',
            'description': (
                "Classe les employes par chiffre d'affaires genere sur le mois en cours ou le mois "
                "precedent, pour repondre a 'qui est l'employe du mois' ou identifier les meilleurs "
                "vendeurs."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'enum': ['ce_mois', 'mois_dernier'], 'description': "ce_mois (defaut) ou mois_dernier."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'nombre_produits',
            'description': "Donne le nombre total de produits references dans le catalogue de la pharmacie.",
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'liste_produits',
            'description': (
                "Liste les produits du CATALOGUE (fiche produit : nom, code, fournisseur, rayon, "
                "famille, conditionnement), avec une recherche optionnelle. A utiliser pour 'quels sont "
                "nos produits', 'liste des produits', pour retrouver le nom d'un ou plusieurs produits "
                "mentionnes precedemment (par exemple juste apres avoir demande le nombre de produits), "
                "ou pour une question sur le 'conditionnement' d'un produit — le conditionnement est la "
                "STRUCTURE D'EMBALLAGE (combien de niveaux : unite seule / unite+sous-unite / "
                "unite+sous-unite+sous-sous-unite), une notion totalement differente de la quantite "
                "actuellement en stock. Ne contient PAS de quantite en stock physique — pour ca, utilise "
                "stock_produit ou produits_stock_faible."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'recherche': {'type': 'string', 'description': "Filtre optionnel sur nom ou code produit (recherche partielle, texte uniquement — pas de prix/quantite). Laisser vide pour lister tout le catalogue et chercher toi-meme dans les resultats si le critere est une valeur numerique."},
                    'limite': {'type': 'integer', 'description': "Nombre maximum de produits a retourner (defaut 50, max 200)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'liste_fournisseurs',
            'description': (
                "Liste les fournisseurs avec leur coefficient et leur taux de TVA effectifs (leur "
                "propre valeur si personnalisee, sinon celle heritee de leur groupe fournisseur), "
                "ainsi que le groupe fournisseur auquel ils appartiennent. A utiliser pour toute "
                "question sur le coefficient ou la TVA 'par fournisseur'."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'recherche': {'type': 'string', 'description': "Filtre optionnel sur nom ou prefixe du fournisseur (recherche partielle, texte uniquement). Ne filtre PAS sur le coefficient ou la TVA (des valeurs numeriques) : pour trouver un fournisseur par son coefficient/TVA, laisse ce parametre vide pour tout recuperer, puis identifie toi-meme le bon fournisseur dans les resultats retournes."},
                    'limite': {'type': 'integer', 'description': "Nombre maximum de fournisseurs a retourner (defaut 50, max 200)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'liste_groupes_fournisseurs',
            'description': (
                "Liste les groupes fournisseurs avec leur coefficient par defaut et leur taux de TVA "
                "par defaut (valeurs heritees par les fournisseurs du groupe qui n'ont pas de valeur "
                "personnalisee), et le nombre de fournisseurs dans chaque groupe. A utiliser pour toute "
                "question sur le coefficient ou la TVA 'par groupe fournisseur'."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'recherche': {'type': 'string', 'description': "Filtre optionnel sur le nom du groupe (recherche partielle, texte uniquement). Ne filtre PAS sur le coefficient ou la TVA : pour trouver un groupe par ces valeurs, laisse ce parametre vide et identifie toi-meme le bon groupe dans les resultats."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'stock_produit',
            'description': (
                "Cherche un ou plusieurs produits par nom ou code produit (recherche partielle) et "
                "donne leur quantite en stock actuelle (tous lots confondus, avec le conditionnement du "
                "produit pour interpreter correctement les quantites unites/sous-unites/sous-sous-unites) "
                "ainsi que la prochaine date de peremption. A utiliser pour toute question 'quelle est la "
                "quantite en stock de tel produit' — mais PAS pour une simple question sur le "
                "conditionnement seul (utilise plutot liste_produits dans ce cas)."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'nom_produit': {'type': 'string', 'description': "Nom ou code du produit recherche (recherche partielle, insensible a la casse)."},
                },
                'required': ['nom_produit'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'produits_stock_faible',
            'description': (
                "Liste les produits dont le stock total est faible ou nul (rupture de stock), en "
                "dessous d'un seuil donne (defaut 10 unites). Utile pour detecter les produits a "
                "reapprovisionner d'urgence."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'seuil': {'type': 'integer', 'description': "Seuil en dessous duquel un produit est considere en stock faible (defaut 10). Utiliser 0 pour ne lister que les ruptures totales."},
                    'limite': {'type': 'integer', 'description': "Nombre maximum de produits a retourner (defaut 15)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'produits_peremption_proche',
            'description': (
                "Liste les lots de produits dont la date de peremption arrive dans les N prochains "
                "jours (defaut 30), tries par date de peremption la plus proche."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'nb_jours': {'type': 'integer', 'description': "Horizon en jours (defaut 30)."},
                    'limite': {'type': 'integer', 'description': "Nombre maximum de lots a retourner (defaut 15)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'top_produits_vendus',
            'description': "Classe les produits les plus vendus sur une periode, par chiffre d'affaires ou par quantite.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'enum': PERIODES_VALIDES, 'description': _PERIODE_DESC},
                    'date_debut': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                    'date_fin': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                    'critere': {'type': 'string', 'enum': ['chiffre_affaires', 'quantite'], 'description': "Trier par chiffre_affaires (defaut) ou par quantite vendue."},
                    'limite': {'type': 'integer', 'description': "Nombre de produits a retourner (defaut 5)."},
                },
                'required': ['periode'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'sorties_stock_periode',
            'description': (
                "Donne un resume des sorties de stock (ventes, pertes, casse, corrections, transferts...) "
                "sur une periode : nombre de sorties, quantite totale, valeur HT/TTC, et repartition par "
                "raison. A utiliser pour toute question du type 'sorties de stock du jour/de la semaine/du mois'."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'enum': PERIODES_VALIDES, 'description': _PERIODE_DESC},
                    'date_debut': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                    'date_fin': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                },
                'required': ['periode'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'dernieres_sorties_stock',
            'description': (
                "Liste le detail des sorties de stock sur une periode (produit, quantite, raison, qui l'a "
                "effectuee, valeur, date/heure), les plus recentes en premier. A utiliser quand on veut le "
                "detail ligne par ligne plutot qu'un simple total (ex: 'quelles sont les sorties de stock "
                "d'aujourd'hui', 'montre-moi les dernieres sorties')."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'enum': PERIODES_VALIDES, 'description': _PERIODE_DESC},
                    'date_debut': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                    'date_fin': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                    'limite': {'type': 'integer', 'description': "Nombre maximum de sorties a retourner (defaut 10, max 50)."},
                },
                'required': ['periode'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'sorties_stock_produit',
            'description': "Donne le total des sorties de stock (quantite et valeur) pour un produit specifique sur une periode.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'nom_produit': {'type': 'string', 'description': "Nom ou code du produit recherche (recherche partielle)."},
                    'periode': {'type': 'string', 'enum': PERIODES_VALIDES, 'description': _PERIODE_DESC},
                    'date_debut': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                    'date_fin': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                },
                'required': ['nom_produit', 'periode'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'top_clients',
            'description': "Classe les clients ayant depense le plus sur une periode donnee.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'enum': PERIODES_VALIDES, 'description': _PERIODE_DESC},
                    'date_debut': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                    'date_fin': {'type': 'string', 'description': "AAAA-MM-JJ, si periode='personnalise'."},
                    'limite': {'type': 'integer', 'description': "Nombre de clients a retourner (defaut 5)."},
                },
                'required': ['periode'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'solde_client',
            'description': "Cherche un client par nom, prenom, matricule ou email et donne son solde de compte actuel.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'recherche': {'type': 'string', 'description': "Nom, prenom, matricule ou email (recherche partielle)."},
                },
                'required': ['recherche'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'nombre_clients',
            'description': "Donne le nombre total de clients enregistres.",
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'liste_clients',
            'description': (
                "Liste les clients (nom, matricule, groupe, solde), avec une recherche optionnelle. "
                "A utiliser pour 'quels sont nos clients', 'liste des clients', ou pour retrouver le "
                "nom d'un ou plusieurs clients mentionnes precedemment dans la conversation (par "
                "exemple juste apres avoir demande le nombre de clients)."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'recherche': {'type': 'string', 'description': "Filtre optionnel sur nom, prenom, matricule ou email (recherche partielle, texte uniquement). Ne filtre PAS sur le solde (numerique) : pour trouver un client par son solde, laisse ce parametre vide et identifie toi-meme le bon client dans les resultats (ou utilise top_clients_solde)."},
                    'limite': {'type': 'integer', 'description': "Nombre maximum de clients a retourner (defaut 50, max 200)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'nombre_groupes_clients',
            'description': "Donne le nombre total de groupes clients enregistres (ex: mutuelles, entreprises partenaires...).",
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'liste_groupes_clients',
            'description': (
                "Liste tous les groupes clients avec leur solde, leur pourcentage d'absorption et le "
                "nombre de clients qui en font partie."
            ),
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'solde_groupe_client',
            'description': "Cherche un groupe client par nom (recherche partielle) et donne son solde et son pourcentage d'absorption.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'recherche': {'type': 'string', 'description': "Nom du groupe client recherche (recherche partielle)."},
                },
                'required': ['recherche'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'clients_par_groupe',
            'description': "Liste les clients membres d'un groupe client donne, avec leur solde individuel.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'nom_groupe': {'type': 'string', 'description': "Nom du groupe client (recherche partielle)."},
                },
                'required': ['nom_groupe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'clients_sans_groupe',
            'description': "Donne le nombre de clients qui ne sont rattaches a aucun groupe, et un apercu de leur liste.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'limite': {'type': 'integer', 'description': "Nombre de clients a lister dans l'apercu (defaut 15)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'top_clients_solde',
            'description': (
                "Classe les clients ayant le solde de compte (credit) le plus eleve, tous mouvements "
                "confondus (pas seulement leurs achats sur une periode)."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'limite': {'type': 'integer', 'description': "Nombre de clients a retourner (defaut 10)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'solde_total_clients_et_groupes',
            'description': "Donne la somme totale des soldes de tous les clients et de tous les groupes clients.",
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'liste_inventaires',
            'description': (
                "Liste l'historique des inventaires (titre, statut en_cours/valide/annule, date et "
                "auteur de creation, date et auteur de validation, nombre de produits et d'ecarts), du "
                "plus recent au plus ancien. A utiliser pour 'quand est le dernier inventaire', 'liste "
                "des inventaires', 'historique des inventaires'. IMPORTANT : ReflexPharma ne planifie "
                "aucun inventaire dans le futur — il n'existe que des inventaires deja crees (au plus un "
                "'en_cours' a la fois) et l'historique des inventaires passes. Si on te demande les "
                "inventaires 'a venir/futurs', explique qu'il n'y a pas de planification, et precise s'il "
                "y a un inventaire actuellement en_cours (donc pas encore termine)."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'limite': {'type': 'integer', 'description': "Nombre maximum d'inventaires a retourner (defaut 10, max 50)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'detail_inventaire',
            'description': (
                "Donne le detail d'un inventaire : statut, dates, qui l'a cree/valide, nombre de produits "
                "comptes, et la liste des ecarts constates (produit, quantite avant/apres, qui a compte). "
                "Sans parametre 'recherche', renvoie l'inventaire en cours s'il y en a un, sinon le plus "
                "recent (donc 'le dernier inventaire'). Pour generer un PDF de ce rapport (comme l'export "
                "manuel), appelle d'abord cet outil puis generer_rapport_pdf avec les donnees obtenues."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'recherche': {'type': 'string', 'description': "Titre de l'inventaire recherche (recherche partielle, texte uniquement). Laisser vide pour l'inventaire en cours / le plus recent."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'nombre_employes',
            'description': (
                "Donne le nombre total d'employes (actifs/inactifs) et leur repartition par role "
                "(superadmin, admin, employee). A utiliser pour 'combien d'employes avons-nous'."
            ),
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'liste_employes',
            'description': (
                "Liste les employes (nom, role, poste, anciennete en annees). A utiliser pour "
                "'qui travaille ici', 'liste des employes', 'qui a le plus d'anciennete', etc."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'statut': {'type': 'string', 'enum': ['actifs', 'inactifs', 'tous'], 'description': "Filtrer par statut du compte (defaut actifs)."},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'employes_par_poste',
            'description': "Donne le nombre d'employes actifs par poste/metier (ex: pharmacien, caissier...).",
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'postes_disponibles',
            'description': "Liste les postes/metiers configures dans la pharmacie (nom et description).",
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'acces_module',
            'description': (
                "Donne la liste des employes ayant (ou n'ayant pas) acces a un module/fonctionnalite "
                "donne du logiciel. A utiliser pour toute question du type 'qui a acces a tel module', "
                "'qui peut gerer les ventes/le stock/les clients', etc. Si tu ne connais pas la cle exacte "
                "du module, appelle d'abord l'outil modules_disponibles."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'module': {'type': 'string', 'description': _MODULE_DESC},
                },
                'required': ['module'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'modules_disponibles',
            'description': "Liste toutes les cles de modules/fonctionnalites existantes (utile avant d'appeler acces_module si le module demande n'est pas evident).",
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'generer_rapport_pdf',
            'description': (
                "Genere un rapport PDF telechargeable a partir de donnees deja obtenues via d'autres "
                "outils, et le rend disponible en telechargement dans le chat. N'utilise cet outil QUE "
                "si l'utilisateur demande explicitement un PDF, un rapport, un document ou une "
                "impression des resultats — jamais spontanement. Appelle d'abord le(s) outil(s) "
                "necessaires pour obtenir les donnees demandees, PUIS appelle cet outil avec un titre "
                "et le contenu structure (texte et/ou tableaux) a inclure dans le document."
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'titre': {'type': 'string', 'description': "Titre du rapport (ex: 'Ventes du jour - 13/07/2026', 'Sorties de stock - Juillet 2026')."},
                    'sections': {
                        'type': 'array',
                        'description': "Sections composant le rapport, dans l'ordre d'affichage.",
                        'items': {
                            'type': 'object',
                            'properties': {
                                'titre_section': {'type': 'string', 'description': "Titre de la section."},
                                'texte': {'type': 'string', 'description': "Texte libre de la section (optionnel), une phrase par ligne."},
                                'tableau': {
                                    'type': 'object',
                                    'description': "Tableau optionnel pour cette section.",
                                    'properties': {
                                        'colonnes': {'type': 'array', 'items': {'type': 'string'}, 'description': "Noms des colonnes."},
                                        'lignes': {
                                            'type': 'array',
                                            'items': {'type': 'array', 'items': {'type': 'string'}},
                                            'description': "Lignes du tableau, chaque ligne etant une liste de valeurs (une par colonne, converties en texte).",
                                        },
                                    },
                                },
                            },
                            'required': ['titre_section'],
                        },
                    },
                },
                'required': ['titre', 'sections'],
            },
        },
    },
]
