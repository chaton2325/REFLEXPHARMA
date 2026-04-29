from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from . import admin
from models.user import User
from models.poste import Poste
from models.permission import Permission
from models.fournisseur import Fournisseur
from models.groupe_fournisseur import GroupeFournisseur
from models.rayon import Rayon
from models.famille import Famille
from models.section import Section
from models.produit import Produit
from models.stock import Stock
from models.stock_modification import StockModification
from models.stock_reason import StockReason
from models.stock_exit_log import StockExitLog
from extensions import db
from functools import wraps
from datetime import datetime
import secrets
from urllib.parse import quote
from utils.permissions import FEATURES

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'superadmin':
            flash("Accès refusé. Vous devez être superadmin.", "danger")
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(feature):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_permission(feature):
                flash(f"Accès refusé. Vous n'avez pas la permission : {feature}", "danger")
                return redirect(url_for('admin.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def generate_product_code(fournisseur):
    prefix = (fournisseur.prefixe or 'XXXX').upper()
    while True:
        suffix = ''.join(secrets.choice('0123456789') for _ in range(9))
        code = f'{prefix}-{suffix}'[:13]
        if not Produit.query.filter_by(code_produit=code).first():
            return code

def create_stock_modification(stock, produit, action, reason, old_values, new_values, old_qr_tire, new_qr_tire, reason_id=None):
    modification = StockModification(
        stock_id=None,
        produit=produit,
        user_id=current_user.id,
        action=action,
        reason=reason if not reason_id else None,
        reason_id=reason_id,
        numero_bl=stock.numero_bl,
        date_peremption=stock.date_peremption,
        code_suivi=stock.code_suivi,
        old_qr_tire=old_qr_tire,
        new_qr_tire=new_qr_tire,
        old_quantite_unites=old_values[0],
        old_quantite_sous_unites=old_values[1],
        old_quantite_sous_sous_unites=old_values[2],
        new_quantite_unites=new_values[0],
        new_quantite_sous_unites=new_values[1],
        new_quantite_sous_sous_unites=new_values[2]
    )
    db.session.add(modification)

def create_stock_exit_log(stock, reason, old_values, new_values, exit_values):
    fournisseur = stock.produit.fournisseur
    groupe_fournisseur = fournisseur.groupe if fournisseur else None
    stock_creation = (
        StockModification.query
        .filter_by(code_suivi=stock.code_suivi, action='create')
        .order_by(StockModification.created_at.asc())
        .first()
    )
    stocked_by = stock_creation.user if stock_creation and stock_creation.user else None
    prix_unite_ht = float(stock.produit.prix_unite or 0)
    prix_sous_unite_ht = float(stock.produit.prix_sous_unite or 0)
    prix_sous_sous_unite_ht = float(stock.produit.prix_sous_sous_unite or 0)
    prix_unite_ttc = float(stock.produit.prix_unite_ttc or 0)
    prix_sous_unite_ttc = float(stock.produit.prix_sous_unite_ttc or 0)
    prix_sous_sous_unite_ttc = float(stock.produit.prix_sous_sous_unite_ttc or 0)
    total_sortie_ht = (
        exit_values[0] * prix_unite_ht
        + exit_values[1] * prix_sous_unite_ht
        + exit_values[2] * prix_sous_sous_unite_ht
    )
    total_sortie_ttc = (
        exit_values[0] * prix_unite_ttc
        + exit_values[1] * prix_sous_unite_ttc
        + exit_values[2] * prix_sous_sous_unite_ttc
    )

    log = StockExitLog(
        produit_nom=stock.produit.nom,
        produit_code=stock.produit.code_produit,
        fournisseur_nom=fournisseur.nom if fournisseur else None,
        groupe_fournisseur_nom=groupe_fournisseur.nom if groupe_fournisseur else None,
        numero_bl=stock.numero_bl,
        date_peremption=stock.date_peremption,
        code_suivi=stock.code_suivi,
        mise_en_stock_at=stock_creation.created_at if stock_creation else stock.created_at,
        mise_en_stock_user_nom=stocked_by.nom if stocked_by else None,
        mise_en_stock_user_prenom=stocked_by.prenom if stocked_by else None,
        mise_en_stock_user_email=stocked_by.email if stocked_by else None,
        user_nom=current_user.nom,
        user_prenom=current_user.prenom,
        user_email=current_user.email,
        reason_nom=reason.nom,
        quantite_unites_sortie=exit_values[0],
        quantite_sous_unites_sortie=exit_values[1],
        quantite_sous_sous_unites_sortie=exit_values[2],
        prix_unite_ht=prix_unite_ht,
        prix_sous_unite_ht=prix_sous_unite_ht,
        prix_sous_sous_unite_ht=prix_sous_sous_unite_ht,
        prix_unite_ttc=prix_unite_ttc,
        prix_sous_unite_ttc=prix_sous_unite_ttc,
        prix_sous_sous_unite_ttc=prix_sous_sous_unite_ttc,
        tva_pourcentage=float(stock.produit.effectif_tva or 0),
        total_sortie_ht=total_sortie_ht,
        total_sortie_ttc=total_sortie_ttc,
        old_quantite_unites=old_values[0],
        old_quantite_sous_unites=old_values[1],
        old_quantite_sous_sous_unites=old_values[2],
        new_quantite_unites=new_values[0],
        new_quantite_sous_unites=new_values[1],
        new_quantite_sous_sous_unites=new_values[2]
    )
    db.session.add(log)

# --- GESTION DES RAISONS DE STOCK ---
@admin.route('/stock/reasons')
@login_required
@permission_required('gestion_raisons_stock')
def list_stock_reasons():
    reasons = StockReason.query.all()
    return render_template('admin/stock/reasons.html', reasons=reasons)

@admin.route('/stock/reasons/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_raisons_stock')
def create_stock_reason():
    if request.method == 'POST':
        new_reason = StockReason(
            nom=request.form.get('nom'),
            type=request.form.get('type'),
            description=request.form.get('description')
        )
        db.session.add(new_reason)
        db.session.commit()
        flash('Raison de stock ajoutée avec succès.', 'success')
        return redirect(url_for('admin.list_stock_reasons'))
    return render_template('admin/stock/reason_form.html', title="Ajouter une raison de stock")

@admin.route('/stock/reasons/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_raisons_stock')
def edit_stock_reason(id):
    reason = StockReason.query.get_or_404(id)
    if request.method == 'POST':
        reason.nom = request.form.get('nom')
        reason.type = request.form.get('type')
        reason.description = request.form.get('description')
        db.session.commit()
        flash('Raison de stock mise à jour avec succès.', 'success')
        return redirect(url_for('admin.list_stock_reasons'))
    return render_template('admin/stock/reason_form.html', reason=reason, title="Modifier la raison de stock")

@admin.route('/stock/reasons/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_raisons_stock')
def delete_stock_reason(id):
    reason = StockReason.query.get_or_404(id)
    db.session.delete(reason)
    db.session.commit()
    flash('Raison de stock supprimée.', 'success')
    return redirect(url_for('admin.list_stock_reasons'))

def build_qr_svg_data_uri(value, size=96):
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderSVG

    widget = qr.QrCodeWidget(value)
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(widget)
    svg = renderSVG.drawToString(drawing)
    return f"data:image/svg+xml;utf8,{quote(svg)}"

def build_stock_qr_items(stocks, requested_counts=None):
    requested_counts = requested_counts or {}
    return [
        {
            'stock': stock,
            'qr_count': max(requested_counts.get(stock.id, stock.quantite_unites), 0),
            'qr_image': build_qr_svg_data_uri(stock.code_suivi)
        }
        for stock in stocks
    ]

def get_requested_qr_counts(stock_ids):
    counts = {}
    for stock_id in stock_ids:
        raw_count = request.form.get(f'qr_count_{stock_id}')
        if raw_count is None:
            continue
        try:
            counts[stock_id] = max(int(raw_count), 0)
        except ValueError:
            counts[stock_id] = 0
    return counts

def get_selected_stock_ids():
    return [int(stock_id) for stock_id in request.form.getlist('stock_ids') if stock_id.isdigit()]

def get_stocks_in_requested_order(stock_ids):
    stocks = Stock.query.filter(Stock.id.in_(stock_ids)).all()
    stock_by_id = {stock.id: stock for stock in stocks}
    return [stock_by_id[stock_id] for stock_id in stock_ids if stock_id in stock_by_id]

def get_qr_print_info_map(stocks):
    codes = [stock.code_suivi for stock in stocks]
    if not codes:
        return {}

    modifications = (
        StockModification.query
        .filter(StockModification.action == 'qr_print', StockModification.code_suivi.in_(codes))
        .order_by(StockModification.created_at.desc())
        .all()
    )
    info_by_code = {}
    for modification in modifications:
        if modification.code_suivi not in info_by_code:
            info_by_code[modification.code_suivi] = modification
    return info_by_code

def build_stock_qr_report_rows(stocks):
    qr_print_info = get_qr_print_info_map(stocks)
    rows = []
    for stock in stocks:
        print_info = qr_print_info.get(stock.code_suivi)
        user_label = '-'
        if print_info and print_info.user:
            user_label = f'{print_info.user.nom} {print_info.user.prenom}'

        rows.append({
            'produit': stock.produit.nom,
            'code_suivi': stock.code_suivi,
            'numero_bl': stock.numero_bl,
            'date_peremption': stock.date_peremption.strftime('%d/%m/%Y') if stock.date_peremption else '-',
            'unites': stock.quantite_unites,
            'sous_unites': stock.quantite_sous_unites,
            'sous_sous_unites': stock.quantite_sous_sous_unites,
            'qr_tire': 'Oui' if stock.qr_tire else 'Non',
            'date_tirage': print_info.created_at.strftime('%d/%m/%Y %H:%M') if print_info and print_info.created_at else '-',
            'tire_par': user_label
        })
    return rows

# --- DASHBOARD ---
@admin.route('/dashboard')
@login_required
def dashboard():
    return render_template('admin/dashboard.html')

# --- GESTION DES POSTES (METIERS) ---
@admin.route('/postes')
@login_required
@permission_required('gestion_postes')
def list_postes():
    postes = Poste.query.all()
    return render_template('admin/postes/list.html', postes=postes)

@admin.route('/postes/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_postes')
def create_poste():
    if request.method == 'POST':
        nom = request.form.get('nom')
        if Poste.query.filter_by(nom=nom).first():
            flash('Ce poste existe déjà.', 'danger')
            return redirect(url_for('admin.create_poste'))
        
        new_poste = Poste(nom=nom, description=request.form.get('description'))
        db.session.add(new_poste)
        db.session.commit()
        flash('Poste ajouté avec succès.', 'success')
        return redirect(url_for('admin.list_postes'))
    return render_template('admin/postes/form.html', title="Ajouter un Poste")

@admin.route('/postes/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_postes')
def edit_poste(id):
    poste = Poste.query.get_or_404(id)
    if request.method == 'POST':
        poste.nom = request.form.get('nom')
        poste.description = request.form.get('description')
        
        # Gestion des permissions du poste (uniquement par superadmin)
        if current_user.role == 'superadmin':
            for feature in FEATURES:
                is_allowed = True if request.form.get(f'perm_{feature}') else False
                perm = Permission.query.filter_by(feature=feature, poste_id=poste.id).first()
                if perm:
                    perm.is_allowed = is_allowed
                else:
                    new_perm = Permission(feature=feature, poste_id=poste.id, is_allowed=is_allowed)
                    db.session.add(new_perm)
        
        db.session.commit()
        flash('Poste mis à jour avec succès.', 'success')
        return redirect(url_for('admin.list_postes'))
    
    poste_perms = {p.feature: p.is_allowed for p in Permission.query.filter_by(poste_id=id).all()}
    return render_template('admin/postes/form.html', poste=poste, title="Modifier le Poste", features=FEATURES, poste_perms=poste_perms)

@admin.route('/postes/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_postes')
def delete_poste(id):
    poste = Poste.query.get_or_404(id)
    db.session.delete(poste)
    db.session.commit()
    flash('Poste supprimé.', 'success')
    return redirect(url_for('admin.list_postes'))

@admin.route('/postes/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_postes')
def bulk_delete_postes():
    ids = request.form.getlist('ids[]')
    if not ids:
        flash("Aucun poste sélectionné.", "warning")
        return redirect(url_for('admin.list_postes'))
    
    deleted_count = 0
    for p_id in ids:
        p = Poste.query.get(p_id)
        if p:
            db.session.delete(p)
            deleted_count += 1
            
    db.session.commit()
    flash(f'{deleted_count} poste(s) supprimé(s).', 'success')
    return redirect(url_for('admin.list_postes'))

# --- GESTION DES UTILISATEURS ---
@admin.route('/users')
@login_required
@permission_required('gestion_employes')
def list_users():
    users = User.query.all()
    return render_template('admin/users/list.html', users=users)

@admin.route('/users/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_employes')
def create_user():
    postes = Poste.query.all()
    if request.method == 'POST':
        email = request.form.get('email')
        if User.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'danger')
            return redirect(url_for('admin.create_user'))
            
        date_prise_poste_str = request.form.get('date_prise_poste')
        date_prise_poste = datetime.strptime(date_prise_poste_str, '%Y-%m-%d').date() if date_prise_poste_str else None
        salaire_mensuel = request.form.get('salaire_mensuel')
        salaire_mensuel = float(salaire_mensuel) if salaire_mensuel else None

        new_user = User(
            nom=request.form.get('nom'),
            prenom=request.form.get('prenom'),
            email=email,
            telephone=request.form.get('telephone'),
            adresse=request.form.get('adresse'),
            role=request.form.get('role'),
            poste=request.form.get('poste'),
            date_prise_poste=date_prise_poste,
            salaire_mensuel=salaire_mensuel,
            is_active=True if request.form.get('is_active') else False
        )
        new_user.set_password(request.form.get('password'))
        
        db.session.add(new_user)
        db.session.commit()
        flash('Utilisateur créé avec succès.', 'success')
        return redirect(url_for('admin.list_users'))
    return render_template('admin/users/form.html', title="Créer un utilisateur", postes=postes)

@admin.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_employes')
def edit_user(id):
    user = User.query.get_or_404(id)
    postes = Poste.query.all()
    if request.method == 'POST':
        user.nom = request.form.get('nom')
        user.prenom = request.form.get('prenom')
        user.email = request.form.get('email')
        user.telephone = request.form.get('telephone')
        user.adresse = request.form.get('adresse')
        user.role = request.form.get('role')
        user.poste = request.form.get('poste')
        user.is_active = True if request.form.get('is_active') else False
        
        date_prise_poste_str = request.form.get('date_prise_poste')
        user.date_prise_poste = datetime.strptime(date_prise_poste_str, '%Y-%m-%d').date() if date_prise_poste_str else None
        salaire_mensuel = request.form.get('salaire_mensuel')
        user.salaire_mensuel = float(salaire_mensuel) if salaire_mensuel else None
        
        password = request.form.get('password')
        if password:
            user.set_password(password)
            
        # Gestion des permissions (uniquement par superadmin)
        if current_user.role == 'superadmin':
            for feature in FEATURES:
                is_allowed = True if request.form.get(f'perm_{feature}') else False
                perm = Permission.query.filter_by(feature=feature, user_id=user.id).first()
                if perm:
                    perm.is_allowed = is_allowed
                else:
                    new_perm = Permission(feature=feature, user_id=user.id, is_allowed=is_allowed)
                    db.session.add(new_perm)

        db.session.commit()
        flash('Utilisateur mis à jour avec succès.', 'success')
        return redirect(url_for('admin.list_users'))
    
    # Récupérer les permissions actuelles de l'utilisateur
    user_perms = {p.feature: p.is_allowed for p in Permission.query.filter_by(user_id=id).all()}
    return render_template('admin/users/form.html', user=user, title="Modifier l'utilisateur", postes=postes, features=FEATURES, user_perms=user_perms)

@admin.route('/users/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_employes')
def bulk_delete_users():
    ids = request.form.getlist('ids[]')
    if not ids:
        flash("Aucun utilisateur sélectionné.", "warning")
        return redirect(url_for('admin.list_users'))
    
    deleted_count = 0
    for u_id in ids:
        u = User.query.get(u_id)
        if u and u.id != current_user.id:
            db.session.delete(u)
            deleted_count += 1
            
    db.session.commit()
    flash(f'{deleted_count} utilisateur(s) supprimé(s).', 'success')
    return redirect(url_for('admin.list_users'))

@admin.route('/users/toggle-active/<int:id>')
@login_required
@permission_required('gestion_employes')
def toggle_user_active(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas modifier le statut de votre propre compte.", "warning")
        return redirect(url_for('admin.list_users'))

    user.is_active = not user.is_active
    db.session.commit()
    flash(
        'Utilisateur activ? avec succ?s.' if user.is_active else 'Utilisateur d?sactiv? avec succ?s.',
        'success'
    )
    return redirect(url_for('admin.list_users'))

@admin.route('/users/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_employes')
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "warning")
        return redirect(url_for('admin.list_users'))

    db.session.delete(user)
    db.session.commit()
    flash('Utilisateur supprim?.', 'success')
    return redirect(url_for('admin.list_users'))

# --- GESTION DES FOURNISSEURS ---
@admin.route('/fournisseurs')
@login_required
@permission_required('gestion_fournisseurs')
def list_fournisseurs():
    fournisseurs = Fournisseur.query.all()
    groupes = GroupeFournisseur.query.all()
    return render_template('admin/fournisseurs/list.html', fournisseurs=fournisseurs, groupes=groupes)

@admin.route('/fournisseurs/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_fournisseurs')
def bulk_delete_fournisseurs():
    ids = request.form.getlist('ids[]')
    if not ids:
        flash("Aucun fournisseur sélectionné.", "warning")
        return redirect(url_for('admin.list_fournisseurs'))
    
    deleted_count = 0
    for f_id in ids:
        f = Fournisseur.query.get(f_id)
        if f:
            db.session.delete(f)
            deleted_count += 1
            
    db.session.commit()
    flash(f'{deleted_count} fournisseur(s) supprimé(s).', 'success')
    return redirect(url_for('admin.list_fournisseurs'))

@admin.route('/fournisseurs/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_fournisseurs')
def create_fournisseur():
    groupes = GroupeFournisseur.query.all()
    if request.method == 'POST':
        nom = request.form.get('nom')
        prefixe_propose = request.form.get('prefixe').upper()
        
        import re
        base_prefix = re.sub(r'[0-9]+$', '', prefixe_propose)
        if not base_prefix: base_prefix = prefixe_propose
        
        prefixe = prefixe_propose
        counter = 1
        match = re.search(r'([0-9]+)$', prefixe_propose)
        if match:
            counter = int(match.group(1))
            base_prefix = prefixe_propose[:match.start()]

        while Fournisseur.query.filter_by(prefixe=prefixe).first():
            prefixe = f"{base_prefix}{counter}"
            counter += 1
        
        coeff = request.form.get('coefficient')
        tva = request.form.get('tva')
        groupe_id = request.form.get('groupe_id')

        new_fournisseur = Fournisseur(
            nom=nom,
            site_web=request.form.get('site_web'),
            contact=request.form.get('contact'),
            prefixe=prefixe,
            coefficient=float(coeff) if coeff else None,
            tva=float(tva) if tva else None,
            groupe_id=int(groupe_id) if groupe_id else None
        )
        db.session.add(new_fournisseur)
        db.session.commit()
        flash(f'Fournisseur ajouté avec succès. Préfixe utilisé : {prefixe}', 'success')
        return redirect(url_for('admin.list_fournisseurs'))
    return render_template('admin/fournisseurs/form.html', title="Ajouter un Fournisseur", groupes=groupes)

@admin.route('/fournisseurs/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_fournisseurs')
def edit_fournisseur(id):
    fournisseur = Fournisseur.query.get_or_404(id)
    groupes = GroupeFournisseur.query.all()
    if request.method == 'POST':
        prefixe = request.form.get('prefixe')
        existing = Fournisseur.query.filter_by(prefixe=prefixe).first()
        if existing and existing.id != id:
            flash('Ce préfixe est déjà utilisé.', 'danger')
            return redirect(url_for('admin.edit_fournisseur', id=id))
            
        fournisseur.nom = request.form.get('nom')
        fournisseur.site_web = request.form.get('site_web')
        fournisseur.contact = request.form.get('contact')
        fournisseur.prefixe = prefixe
        
        coeff = request.form.get('coefficient')
        fournisseur.coefficient = float(coeff) if coeff else None
        tva = request.form.get('tva')
        fournisseur.tva = float(tva) if tva else None
        groupe_id = request.form.get('groupe_id')
        fournisseur.groupe_id = int(groupe_id) if groupe_id else None
        
        db.session.commit()
        flash('Fournisseur mis à jour avec succès.', 'success')
        return redirect(url_for('admin.list_fournisseurs'))
    return render_template('admin/fournisseurs/form.html', fournisseur=fournisseur, title="Modifier le Fournisseur", groupes=groupes)

@admin.route('/fournisseurs/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_fournisseurs')
def delete_fournisseur(id):
    fournisseur = Fournisseur.query.get_or_404(id)
    db.session.delete(fournisseur)
    db.session.commit()
    flash('Fournisseur supprimé.', 'success')
    return redirect(url_for('admin.list_fournisseurs'))

# --- GESTION DES GROUPES DE FOURNISSEURS ---
@admin.route('/fournisseurs/groupes')
@login_required
@permission_required('gestion_groupes_fournisseurs')
def list_groupes_fournisseurs():
    groupes = GroupeFournisseur.query.all()
    return render_template('admin/fournisseurs/groupes_list.html', groupes=groupes)

@admin.route('/fournisseurs/groupes/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_groupes_fournisseurs')
def create_groupe_fournisseur():
    if request.method == 'POST':
        nom = request.form.get('nom')
        if GroupeFournisseur.query.filter_by(nom=nom).first():
            flash('Ce groupe existe déjà.', 'danger')
            return redirect(url_for('admin.create_groupe_fournisseur'))
            
        coeff = request.form.get('coefficient_defaut')
        tva = request.form.get('tva_defaut')
        
        new_groupe = GroupeFournisseur(
            nom=nom,
            coefficient_defaut=float(coeff) if coeff else 1.0,
            tva_defaut=float(tva) if tva else 20.0
        )
        db.session.add(new_groupe)
        db.session.commit()
        flash('Groupe de fournisseurs créé avec succès.', 'success')
        return redirect(url_for('admin.list_groupes_fournisseurs'))
    return render_template('admin/fournisseurs/groupe_form.html', title="Créer un Groupe")

@admin.route('/fournisseurs/groupes/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_groupes_fournisseurs')
def edit_groupe_fournisseur(id):
    groupe = GroupeFournisseur.query.get_or_404(id)
    if request.method == 'POST':
        groupe.nom = request.form.get('nom')
        coeff = request.form.get('coefficient_defaut')
        groupe.coefficient_defaut = float(coeff) if coeff else 1.0
        tva = request.form.get('tva_defaut')
        groupe.tva_defaut = float(tva) if tva else 20.0
        
        db.session.commit()
        flash('Groupe mis à jour avec succès.', 'success')
        return redirect(url_for('admin.list_groupes_fournisseurs'))
    return render_template('admin/fournisseurs/groupe_form.html', groupe=groupe, title="Modifier le Groupe")

@admin.route('/fournisseurs/groupes/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_groupes_fournisseurs')
def delete_groupe_fournisseur(id):
    groupe = GroupeFournisseur.query.get_or_404(id)
    # Optionnel: gérer les fournisseurs orphelins si nécessaire
    db.session.delete(groupe)
    db.session.commit()
    flash('Groupe supprimé.', 'success')
    return redirect(url_for('admin.list_groupes_fournisseurs'))

@admin.route('/fournisseurs/groupes/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_groupes_fournisseurs')
def bulk_delete_groupes_fournisseurs():
    ids = request.form.getlist('ids[]')
    if not ids:
        flash("Aucun groupe sélectionné.", "warning")
        return redirect(url_for('admin.list_groupes_fournisseurs'))
    
    deleted_count = 0
    for g_id in ids:
        g = GroupeFournisseur.query.get(g_id)
        if g:
            db.session.delete(g)
            deleted_count += 1
            
    db.session.commit()
    flash(f'{deleted_count} groupe(s) supprimé(s).', 'success')
    return redirect(url_for('admin.list_groupes_fournisseurs'))

# --- GESTION DES RAYONS ---
@admin.route('/rayons')
@login_required
@permission_required('gestion_rayons')
def list_rayons():
    rayons = Rayon.query.all()
    return render_template('admin/rayons/list.html', rayons=rayons)

@admin.route('/rayons/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_rayons')
def create_rayon():
    if request.method == 'POST':
        nom = request.form.get('nom')
        if Rayon.query.filter_by(nom=nom).first():
            flash('Ce rayon existe déjà.', 'danger')
            return redirect(url_for('admin.create_rayon'))
        new_rayon = Rayon(nom=nom, description=request.form.get('description'))
        db.session.add(new_rayon)
        db.session.commit()
        flash('Rayon ajouté avec succès.', 'success')
        return redirect(url_for('admin.list_rayons'))
    return render_template('admin/rayons/form.html', title='Ajouter un Rayon')

@admin.route('/rayons/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_rayons')
def edit_rayon(id):
    rayon = Rayon.query.get_or_404(id)
    if request.method == 'POST':
        rayon.nom = request.form.get('nom')
        rayon.description = request.form.get('description')
        db.session.commit()
        flash('Rayon mis à jour.', 'success')
        return redirect(url_for('admin.list_rayons'))
    return render_template('admin/rayons/form.html', rayon=rayon, title='Modifier le Rayon')

@admin.route('/rayons/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_rayons')
def bulk_delete_rayons():
    ids = request.form.getlist('ids[]')
    deleted_count = 0
    for r_id in ids:
        r = Rayon.query.get(r_id)
        if r:
            db.session.delete(r)
            deleted_count += 1
    db.session.commit()
    flash(f'{deleted_count} rayon(s) supprimé(s).', 'success')
    return redirect(url_for('admin.list_rayons'))

@admin.route('/rayons/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_rayons')
def delete_rayon(id):
    item = Rayon.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash('Rayon supprimé.', 'success')
    return redirect(url_for('admin.list_rayons'))

# --- GESTION DES FAMILLES ---
@admin.route('/familles')
@login_required
@permission_required('gestion_familles')
def list_familles():
    familles = Famille.query.all()
    return render_template('admin/familles/list.html', familles=familles)

@admin.route('/familles/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_familles')
def create_famille():
    if request.method == 'POST':
        nom = request.form.get('nom')
        if Famille.query.filter_by(nom=nom).first():
            flash('Cette famille existe déjà.', 'danger')
            return redirect(url_for('admin.create_famille'))
        new_famille = Famille(nom=nom, description=request.form.get('description'))
        db.session.add(new_famille)
        db.session.commit()
        flash('Famille ajoutée.', 'success')
        return redirect(url_for('admin.list_familles'))
    return render_template('admin/familles/form.html', title='Ajouter une Famille')

@admin.route('/familles/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_familles')
def edit_famille(id):
    famille = Famille.query.get_or_404(id)
    if request.method == 'POST':
        famille.nom = request.form.get('nom')
        famille.description = request.form.get('description')
        db.session.commit()
        flash('Famille mise à jour.', 'success')
        return redirect(url_for('admin.list_familles'))
    return render_template('admin/familles/form.html', famille=famille, title='Modifier la Famille')

@admin.route('/familles/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_familles')
def bulk_delete_familles():
    ids = request.form.getlist('ids[]')
    deleted_count = 0
    for f_id in ids:
        f = Famille.query.get(f_id)
        if f:
            db.session.delete(f)
            deleted_count += 1
    db.session.commit()
    flash(f'{deleted_count} famille(s) supprimée(s).', 'success')
    return redirect(url_for('admin.list_familles'))

@admin.route('/familles/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_familles')
def delete_famille(id):
    item = Famille.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash('Famille supprimée.', 'success')
    return redirect(url_for('admin.list_familles'))

# --- GESTION DES SECTIONS ---
@admin.route('/sections')
@login_required
@permission_required('gestion_sections')
def list_sections():
    sections = Section.query.all()
    return render_template('admin/sections/list.html', sections=sections)

@admin.route('/sections/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_sections')
def create_section():
    if request.method == 'POST':
        nom = request.form.get('nom')
        if Section.query.filter_by(nom=nom).first():
            flash('Cette section existe déjà.', 'danger')
            return redirect(url_for('admin.create_section'))
        new_section = Section(nom=nom, description=request.form.get('description'))
        db.session.add(new_section)
        db.session.commit()
        flash('Section ajoutée.', 'success')
        return redirect(url_for('admin.list_sections'))
    return render_template('admin/sections/form.html', title='Ajouter une Section')

@admin.route('/sections/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_sections')
def edit_section(id):
    section = Section.query.get_or_404(id)
    if request.method == 'POST':
        section.nom = request.form.get('nom')
        section.description = request.form.get('description')
        db.session.commit()
        flash('Section mise à jour.', 'success')
        return redirect(url_for('admin.list_sections'))
    return render_template('admin/sections/form.html', section=section, title='Modifier la Section')

@admin.route('/sections/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_sections')
def bulk_delete_sections():
    ids = request.form.getlist('ids[]')
    deleted_count = 0
    for s_id in ids:
        s = Section.query.get(s_id)
        if s:
            db.session.delete(s)
            deleted_count += 1
    db.session.commit()
    flash(f'{deleted_count} section(s) supprimée(s).', 'success')
    return redirect(url_for('admin.list_sections'))

@admin.route('/sections/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_sections')
def delete_section(id):
    item = Section.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash('Section supprimée.', 'success')
    return redirect(url_for('admin.list_sections'))

# --- GESTION DES PRODUITS ---
@admin.route('/produits')
@login_required
@permission_required('gestion_produits')
def list_produits():
    produits = Produit.query.all()
    fournisseurs_list = Fournisseur.query.all()
    rayons_list = Rayon.query.all()
    familles_list = Famille.query.all()
    return render_template('admin/produits/list.html', produits=produits, 
                           fournisseurs_list=fournisseurs_list, 
                           rayons_list=rayons_list, 
                           familles_list=familles_list)

@admin.route('/produits/create', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_produits')
def create_produit():
    fournisseurs = Fournisseur.query.all()
    rayons = Rayon.query.all()
    familles = Famille.query.all()
    sections = Section.query.all()
    
    if request.method == 'POST':
        f_id = int(request.form.get('fournisseur_id'))
        fournisseur = Fournisseur.query.get_or_404(f_id)
        
        new_produit = Produit(
            nom=request.form.get('nom'),
            code_produit=generate_product_code(fournisseur),
            fournisseur_id=f_id,
            rayon_id=int(request.form.get('rayon_id')) if request.form.get('rayon_id') else None,
            famille_id=int(request.form.get('famille_id')) if request.form.get('famille_id') else None,
            section_id=int(request.form.get('section_id')) if request.form.get('section_id') else None,
            conditionnement=int(request.form.get('conditionnement')),
            prix_unite=float(request.form.get('prix_unite') or 0),
            prix_sous_unite=float(request.form.get('prix_sous_unite') or 0),
            prix_sous_sous_unite=float(request.form.get('prix_sous_sous_unite') or 0),
            coefficient=float(request.form.get('coefficient')) if request.form.get('coefficient') else None,
            tva=float(request.form.get('tva')) if request.form.get('tva') else None
        )
        db.session.add(new_produit)
        db.session.commit()
        
        flash(f'Produit créé avec le code : {new_produit.code_produit}', 'success')
        return redirect(url_for('admin.list_produits'))
        
    return render_template('admin/produits/form.html', title='Ajouter un Produit', 
                           fournisseurs=fournisseurs, rayons=rayons, familles=familles, sections=sections)

@admin.route('/produits/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_produits')
def edit_produit(id):
    produit = Produit.query.get_or_404(id)
    fournisseurs = Fournisseur.query.all()
    rayons = Rayon.query.all()
    familles = Famille.query.all()
    sections = Section.query.all()
    
    if request.method == 'POST':
        produit.nom = request.form.get('nom')
        produit.rayon_id = int(request.form.get('rayon_id')) if request.form.get('rayon_id') else None
        produit.famille_id = int(request.form.get('famille_id')) if request.form.get('famille_id') else None
        produit.section_id = int(request.form.get('section_id')) if request.form.get('section_id') else None
        produit.conditionnement = int(request.form.get('conditionnement'))
        produit.prix_unite = float(request.form.get('prix_unite') or 0)
        produit.prix_sous_unite = float(request.form.get('prix_sous_unite') or 0)
        produit.prix_sous_sous_unite = float(request.form.get('prix_sous_sous_unite') or 0)
        produit.coefficient = float(request.form.get('coefficient')) if request.form.get('coefficient') else None
        produit.tva = float(request.form.get('tva')) if request.form.get('tva') else None
        
        db.session.commit()
        flash('Produit mis à jour.', 'success')
        return redirect(url_for('admin.list_produits'))
        
    return render_template('admin/produits/form.html', produit=produit, title='Modifier le Produit',
                           fournisseurs=fournisseurs, rayons=rayons, familles=familles, sections=sections)

@admin.route('/produits/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_produits')
def bulk_delete_produits():
    ids = request.form.getlist('ids[]')
    deleted_count = 0
    for p_id in ids:
        p = Produit.query.get(p_id)
        if p:
            db.session.delete(p)
            deleted_count += 1
    db.session.commit()
    flash(f'{deleted_count} produit(s) supprimé(s).', 'success')
    return redirect(url_for('admin.list_produits'))

@admin.route('/produits/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_produits')
def delete_produit(id):
    produit = Produit.query.get_or_404(id)
    db.session.delete(produit)
    db.session.commit()
    flash('Produit supprimé du catalogue.', 'success')
    return redirect(url_for('admin.list_produits'))

# --- GESTION DU STOCK ---
@admin.route('/stock', methods=['GET', 'POST'])
@login_required
@permission_required('gestion_stock')
def manage_stock():
    produits = Produit.query.order_by(Produit.nom.asc()).all()
    reasons = StockReason.query.filter_by(type='ajout').all()

    if request.method == 'POST':
        produit_id = int(request.form.get('produit_id'))
        produit = Produit.query.get_or_404(produit_id)
        reason_id = request.form.get('reason_id')
        reason_text = (request.form.get('reason') or '').strip()
        numero_bl_raw = (request.form.get('numero_bl') or '').strip()
        date_peremption_str = (request.form.get('date_peremption') or '').strip()
        
        if not reason_id and not reason_text:
            flash('Veuillez préciser la raison de cette entrée en stock.', 'warning')
            return redirect(url_for('admin.manage_stock'))
        if not numero_bl_raw:
            flash('Veuillez préciser le numéro du BL.', 'warning')
            return redirect(url_for('admin.manage_stock'))
        if not date_peremption_str:
            flash('Veuillez préciser la date de péremption.', 'warning')
            return redirect(url_for('admin.manage_stock'))

        try:
            date_peremption = datetime.strptime(date_peremption_str, '%Y-%m-%d').date()
        except ValueError:
            flash('La date de péremption est invalide.', 'danger')
            return redirect(url_for('admin.manage_stock'))

        numero_bl = Stock.normalize_bl(numero_bl_raw)

        quantite_unites = int(request.form.get('quantite_unites') or 0)
        quantite_sous_unites = int(request.form.get('quantite_sous_unites') or 0)
        quantite_sous_sous_unites = int(request.form.get('quantite_sous_sous_unites') or 0)
        code_suivi = Stock.build_tracking_code(produit.code_produit, numero_bl, date_peremption)

        stock = Stock.query.filter_by(
            produit_id=produit_id,
            numero_bl=numero_bl,
            date_peremption=date_peremption
        ).first()
        if stock is None:
            stock = Stock(
                produit_id=produit_id,
                numero_bl=numero_bl,
                date_peremption=date_peremption,
                code_suivi=code_suivi,
                quantite_unites=quantite_unites,
                quantite_sous_unites=quantite_sous_unites,
                quantite_sous_sous_unites=quantite_sous_sous_unites
            )
            db.session.add(stock)
            db.session.flush()
            create_stock_modification(
                stock=stock,
                produit=produit,
                action='create',
                reason=reason_text,
                reason_id=reason_id,
                old_values=(0, 0, 0),
                new_values=(quantite_unites, quantite_sous_unites, quantite_sous_sous_unites),
                old_qr_tire=False,
                new_qr_tire=stock.qr_tire
            )
            message = f'Stock initial ajouté pour {produit.nom}.'
        else:
            old_values = (stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites)
            stock.quantite_unites += quantite_unites
            stock.quantite_sous_unites += quantite_sous_unites
            stock.quantite_sous_sous_unites += quantite_sous_sous_unites
            create_stock_modification(
                stock=stock,
                produit=produit,
                action='adjust',
                reason=reason_text,
                reason_id=reason_id,
                old_values=old_values,
                new_values=(stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites),
                old_qr_tire=stock.qr_tire,
                new_qr_tire=stock.qr_tire
            )
            message = f'Stock mis à jour pour {produit.nom} ({stock.code_suivi}).'

        db.session.commit()
        flash(message, 'success')
        return redirect(url_for('admin.manage_stock'))

    stocks = Stock.query.join(Produit).order_by(Produit.nom.asc(), Stock.date_peremption.asc()).all()
    return render_template('admin/stock/list.html', produits=produits, stocks=stocks, reasons=reasons)

@admin.route('/stock/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_stock')
def edit_stock(id):
    stock = Stock.query.get_or_404(id)
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        flash('Veuillez préciser la raison de la modification du stock.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    old_values = (stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites)
    old_qr_tire = stock.qr_tire
    stock.quantite_unites = int(request.form.get('quantite_unites') or 0)
    stock.quantite_sous_unites = int(request.form.get('quantite_sous_unites') or 0)
    stock.quantite_sous_sous_unites = int(request.form.get('quantite_sous_sous_unites') or 0)
    stock.qr_tire = True if request.form.get('qr_tire') else False
    create_stock_modification(
        stock=stock,
        produit=stock.produit,
        action='edit',
        reason=reason,
        old_values=old_values,
        new_values=(stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites),
        old_qr_tire=old_qr_tire,
        new_qr_tire=stock.qr_tire
    )
    db.session.commit()
    flash(f'Stock mis à jour pour {stock.produit.nom} ({stock.code_suivi}).', 'success')
    return redirect(url_for('admin.manage_stock'))

@admin.route('/stock/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_stock')
def delete_stock(id):
    stock = Stock.query.get_or_404(id)
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        flash('Veuillez préciser la raison de la suppression du stock.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    produit_nom = stock.produit.nom
    code_suivi = stock.code_suivi
    old_values = (stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites)
    create_stock_modification(
        stock=stock,
        produit=stock.produit,
        action='delete',
        reason=reason,
        old_values=old_values,
        new_values=(0, 0, 0),
        old_qr_tire=stock.qr_tire,
        new_qr_tire=stock.qr_tire
    )
    db.session.delete(stock)
    db.session.commit()
    flash(f'Stock supprimé pour {produit_nom} ({code_suivi}).', 'success')
    return redirect(url_for('admin.manage_stock'))

@admin.route('/stock/exit', methods=['GET', 'POST'])
@login_required
@permission_required('effectuer_sortie_stock')
def stock_exit():
    reasons = StockReason.query.filter_by(type='sortie').all()
    if request.method == 'POST':
        stock_id = request.form.get('stock_id')
        stock = Stock.query.get_or_404(stock_id)
        reason_id = request.form.get('reason_id')
        reason = StockReason.query.filter_by(id=reason_id, type='sortie').first() if reason_id else None

        if reason is None:
            flash("Veuillez preciser une raison de sortie valide.", "warning")
            return redirect(url_for('admin.stock_exit', stock_id=stock.id))
        
        q_u = int(request.form.get('quantite_unites') or 0)
        q_su = int(request.form.get('quantite_sous_unites') or 0)
        q_ssu = int(request.form.get('quantite_sous_sous_unites') or 0)

        if q_u < 0 or q_su < 0 or q_ssu < 0:
            flash("Les quantites de sortie ne peuvent pas etre negatives.", "danger")
            return redirect(url_for('admin.stock_exit', stock_id=stock.id))

        if q_u == 0 and q_su == 0 and q_ssu == 0:
            flash("Veuillez preciser au moins une quantite a sortir.", "warning")
            return redirect(url_for('admin.stock_exit', stock_id=stock.id))

        if q_u > stock.quantite_unites or q_su > stock.quantite_sous_unites or q_ssu > stock.quantite_sous_sous_unites:
            flash("La quantité de sortie dépasse le stock disponible pour ce lot.", "danger")
            return redirect(url_for('admin.manage_stock'))

        old_values = (stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites)
        stock.quantite_unites -= q_u
        stock.quantite_sous_unites -= q_su
        stock.quantite_sous_sous_unites -= q_ssu

        create_stock_modification(
            stock=stock,
            produit=stock.produit,
            action='sortie',
            reason=None,
            reason_id=reason_id,
            old_values=old_values,
            new_values=(stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites),
            old_qr_tire=stock.qr_tire,
            new_qr_tire=stock.qr_tire
        )
        create_stock_exit_log(
            stock=stock,
            reason=reason,
            old_values=old_values,
            new_values=(stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites),
            exit_values=(q_u, q_su, q_ssu)
        )
        db.session.commit()
        flash(f'Sortie de stock effectuée pour {stock.produit.nom}.', 'success')
        return redirect(url_for('admin.manage_stock'))
    
    # Si GET, on peut passer un stock_id pour pré-remplir
    stock_id = request.args.get('stock_id')
    stock = Stock.query.get(stock_id) if stock_id else None
    stocks = Stock.query.join(Produit).order_by(Produit.nom.asc()).all()
    return render_template('admin/stock/exit_form.html', stock=stock, stocks=stocks, reasons=reasons)

@admin.route('/stock/<int:id>/qr-preview')
@login_required
@permission_required('gestion_stock')
def preview_stock_qr_codes(id):
    stock = Stock.query.get_or_404(id)
    if stock.qr_tire:
        flash('Les QR codes de ce lot sont déjà marqués comme tirés.', 'info')
        return redirect(url_for('admin.manage_stock'))

    qr_items = build_stock_qr_items([stock])
    return render_template(
        'admin/stock/qr_preview.html',
        qr_items=qr_items,
        total_qr_count=sum(item['qr_count'] for item in qr_items),
        selected_ids=[stock.id]
    )

@admin.route('/stock/qr-preview', methods=['POST'])
@login_required
@permission_required('gestion_stock')
def preview_selected_stock_qr_codes():
    selected_ids = get_selected_stock_ids()
    if not selected_ids:
        flash('Veuillez selectionner au moins une ligne de stock pour tirer les QR codes.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    stocks = get_stocks_in_requested_order(selected_ids)
    if not stocks:
        flash('Aucune ligne de stock valide selectionnee.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    qr_items = build_stock_qr_items(stocks, get_requested_qr_counts(selected_ids))
    return render_template(
        'admin/stock/qr_preview.html',
        qr_items=qr_items,
        total_qr_count=sum(item['qr_count'] for item in qr_items),
        selected_ids=[stock.id for stock in stocks]
    )

@admin.route('/stock/<int:id>/mark-qr-printed', methods=['POST'])
@login_required
@permission_required('gestion_stock')
def mark_stock_qr_printed(id):
    stock = Stock.query.get_or_404(id)
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        flash('Veuillez préciser la raison du tirage des QR codes.', 'warning')
        return redirect(url_for('admin.preview_stock_qr_codes', id=id))

    old_values = (stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites)
    old_qr_tire = stock.qr_tire
    stock.qr_tire = True
    create_stock_modification(
        stock=stock,
        produit=stock.produit,
        action='qr_print',
        reason=reason,
        old_values=old_values,
        new_values=old_values,
        old_qr_tire=old_qr_tire,
        new_qr_tire=stock.qr_tire
    )
    db.session.commit()
    flash(f'QR codes marqués comme tirés pour {stock.produit.nom} ({stock.code_suivi}).', 'success')
    return redirect(url_for('admin.manage_stock'))

@admin.route('/stock/mark-qr-printed', methods=['POST'])
@login_required
@permission_required('gestion_stock')
def mark_selected_stock_qr_printed():
    selected_ids = get_selected_stock_ids()
    reason = (request.form.get('reason') or '').strip()

    if not selected_ids:
        flash('Veuillez selectionner au moins une ligne de stock.', 'warning')
        return redirect(url_for('admin.manage_stock'))
    if not reason:
        flash('Veuillez preciser la raison du tirage des QR codes.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    stocks = get_stocks_in_requested_order(selected_ids)
    updated_count = 0
    for stock in stocks:
        old_values = (stock.quantite_unites, stock.quantite_sous_unites, stock.quantite_sous_sous_unites)
        old_qr_tire = stock.qr_tire
        stock.qr_tire = True
        create_stock_modification(
            stock=stock,
            produit=stock.produit,
            action='qr_print',
            reason=reason,
            old_values=old_values,
            new_values=old_values,
            old_qr_tire=old_qr_tire,
            new_qr_tire=stock.qr_tire
        )
        updated_count += 1

    db.session.commit()
    flash(f'QR codes marques comme tires pour {updated_count} lot(s).', 'success')
    return redirect(url_for('admin.manage_stock'))

@admin.route('/stock/export/qr/excel', methods=['POST'])
@login_required
@permission_required('gestion_stock')
def export_selected_stock_qr_excel():
    selected_ids = get_selected_stock_ids()
    stocks = get_stocks_in_requested_order(selected_ids)
    if not stocks:
        flash('Veuillez selectionner au moins une ligne de stock a exporter.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    import pandas as pd
    import io
    from flask import send_file
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

    generated_at = datetime.now()
    rows = build_stock_qr_report_rows(stocks)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            'produit': 'Produit',
            'code_suivi': 'Code suivi',
            'numero_bl': 'BL',
            'date_peremption': 'Peremption',
            'unites': 'Unites',
            'sous_unites': 'Sous-unites',
            'sous_sous_unites': 'Sous-sous-unites',
            'qr_tire': 'QR tire',
            'date_tirage': 'Date tirage QR',
            'tire_par': 'Tire par'
        })
        df.to_excel(writer, index=False, sheet_name='Stock QR', startrow=4)
        worksheet = writer.sheets['Stock QR']
        worksheet['A1'] = 'Rapport Stock QR - ReflexPharma'
        worksheet['A2'] = f'Genere le : {generated_at.strftime("%d/%m/%Y %H:%M")}'
        worksheet['A3'] = f'Genere par : {current_user.nom} {current_user.prenom}'
        worksheet['A4'] = f'Lignes exportees : {len(rows)}'

        title_font = Font(bold=True, size=14, color='1F2937')
        meta_font = Font(size=10, color='374151')
        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='1F2937', end_color='1F2937', fill_type='solid')
        thin_border = Border(bottom=Side(style='thin', color='D1D5DB'))

        worksheet['A1'].font = title_font
        for row_number in range(2, 5):
            worksheet[f'A{row_number}'].font = meta_font

        for cell in worksheet[5]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for row in worksheet.iter_rows(min_row=6, max_row=worksheet.max_row):
            for cell in row:
                cell.border = thin_border
                cell.alignment = Alignment(vertical='top', wrap_text=True)

        widths = [24, 34, 16, 14, 10, 12, 16, 10, 18, 22]
        for index, width in enumerate(widths, start=1):
            worksheet.column_dimensions[chr(64 + index)].width = width
        worksheet.freeze_panes = 'A6'

    output.seek(0)
    filename = f'stock_qr_{generated_at.strftime("%Y%m%d_%H%M")}.xlsx'
    return send_file(output, download_name=filename, as_attachment=True)

@admin.route('/stock/export/qr/pdf', methods=['POST'])
@login_required
@permission_required('gestion_stock')
def export_selected_stock_qr_pdf():
    selected_ids = get_selected_stock_ids()
    stocks = get_stocks_in_requested_order(selected_ids)
    if not stocks:
        flash('Veuillez selectionner au moins une ligne de stock a exporter.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    import io
    from flask import send_file
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    generated_at = datetime.now()
    rows = build_stock_qr_report_rows(stocks)
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        topMargin=12,
        bottomMargin=12,
        leftMargin=12,
        rightMargin=12
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('StockQrTitle', parent=styles['Title'], fontSize=12, leading=14, spaceAfter=4)
    meta_style = ParagraphStyle('StockQrMeta', parent=styles['Normal'], fontSize=7, leading=9, textColor=colors.HexColor('#374151'))
    cell_style = ParagraphStyle('StockQrCell', parent=styles['Normal'], fontSize=6, leading=7)
    header_style = ParagraphStyle('StockQrHeader', parent=cell_style, alignment=TA_CENTER, textColor=colors.white)

    elements = [
        Paragraph('Rapport Stock QR - ReflexPharma', title_style),
        Paragraph(
            f'Genere le : {generated_at.strftime("%d/%m/%Y %H:%M")} | Genere par : {current_user.nom} {current_user.prenom} | Lignes : {len(rows)}',
            meta_style
        ),
        Spacer(1, 6)
    ]

    data = [[
        Paragraph('Produit', header_style),
        Paragraph('Code suivi', header_style),
        Paragraph('BL', header_style),
        Paragraph('Peremp.', header_style),
        Paragraph('U', header_style),
        Paragraph('S/U', header_style),
        Paragraph('SS/U', header_style),
        Paragraph('QR', header_style),
        Paragraph('Date tirage', header_style),
        Paragraph('Tire par', header_style)
    ]]
    for row in rows:
        data.append([
            Paragraph(str(row['produit']), cell_style),
            Paragraph(str(row['code_suivi']), cell_style),
            Paragraph(str(row['numero_bl']), cell_style),
            row['date_peremption'],
            row['unites'],
            row['sous_unites'],
            row['sous_sous_unites'],
            row['qr_tire'],
            row['date_tirage'],
            Paragraph(str(row['tire_par']), cell_style)
        ])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[95, 155, 70, 52, 28, 32, 36, 30, 75, 85]
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 6),
        ('LEADING', (0, 0), (-1, -1), 7),
        ('ALIGN', (3, 1), (8, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(table)
    doc.build(elements)
    output.seek(0)
    filename = f'stock_qr_{generated_at.strftime("%Y%m%d_%H%M")}.pdf'
    return send_file(output, download_name=filename, as_attachment=True)

@admin.route('/stock/modifications')
@login_required
@permission_required('gestion_modifications_stock')
def list_stock_modifications():
    modifications = StockModification.query.order_by(StockModification.created_at.desc()).all()
    return render_template('admin/stock/modifications.html', modifications=modifications)

@admin.route('/stock/exits')
@login_required
@permission_required('gestion_modifications_stock')
def list_stock_exit_logs():
    exits = StockExitLog.query.order_by(StockExitLog.created_at.desc()).all()
    exit_prices = {item.id: get_exit_log_prices(item) for item in exits}
    exit_suppliers = {item.id: get_exit_log_supplier_info(item) for item in exits}
    return render_template(
        'admin/stock/exit_logs.html',
        exits=exits,
        exit_prices=exit_prices,
        exit_suppliers=exit_suppliers
    )

def parse_date_arg(name):
    value = (request.args.get(name) or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None

def parse_float_arg(name):
    value = (request.args.get(name) or '').strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None

def get_stock_exit_stats_filters():
    return {
        'date_from': request.args.get('date_from', '').strip(),
        'date_to': request.args.get('date_to', '').strip(),
        'produit': request.args.get('produit', '').strip(),
        'fournisseur': request.args.get('fournisseur', '').strip(),
        'groupe': request.args.get('groupe', '').strip(),
        'sorti_par': request.args.get('sorti_par', '').strip(),
        'mis_en_stock_par': request.args.get('mis_en_stock_par', '').strip(),
        'raison': request.args.get('raison', '').strip(),
        'tva': request.args.get('tva', '').strip(),
        'min_ttc': request.args.get('min_ttc', '').strip(),
        'max_ttc': request.args.get('max_ttc', '').strip()
    }

def get_stock_exit_stats_options(exits):
    def sorted_values(values):
        return sorted(value for value in values if value)

    return {
        'produits': sorted_values({f'{item.produit_nom} ({item.produit_code})' for item in exits}),
        'fournisseurs': sorted_values({item.fournisseur_nom or '-' for item in exits}),
        'groupes': sorted_values({item.groupe_fournisseur_nom or '-' for item in exits}),
        'sorti_par': sorted_values({f'{item.user_prenom} {item.user_nom}'.strip() for item in exits}),
        'mis_en_stock_par': sorted_values({f'{item.mise_en_stock_user_prenom or ""} {item.mise_en_stock_user_nom or ""}'.strip() or '-' for item in exits}),
        'raisons': sorted_values({item.reason_nom or '-' for item in exits}),
        'tvas': sorted_values({f'{get_exit_log_prices(item)["tva_pourcentage"]:.2f}' for item in exits})
    }

def get_filtered_stock_exit_logs(filters=None):
    filters = filters or get_stock_exit_stats_filters()
    exits = StockExitLog.query.order_by(StockExitLog.created_at.asc()).all()
    date_from = parse_date_arg('date_from')
    date_to = parse_date_arg('date_to')
    min_ttc = parse_float_arg('min_ttc')
    max_ttc = parse_float_arg('max_ttc')

    def item_value(item, key):
        if key == 'produit':
            return f'{item.produit_nom} ({item.produit_code})'
        if key == 'fournisseur':
            return item.fournisseur_nom or '-'
        if key == 'groupe':
            return item.groupe_fournisseur_nom or '-'
        if key == 'sorti_par':
            return f'{item.user_prenom} {item.user_nom}'.strip()
        if key == 'mis_en_stock_par':
            return f'{item.mise_en_stock_user_prenom or ""} {item.mise_en_stock_user_nom or ""}'.strip() or '-'
        if key == 'raison':
            return item.reason_nom or '-'
        if key == 'tva':
            return f'{get_exit_log_prices(item)["tva_pourcentage"]:.2f}'
        return ''

    filtered = []
    for item in exits:
        item_date = item.created_at.date() if item.created_at else None
        if date_from and item_date and item_date < date_from:
            continue
        if date_to and item_date and item_date > date_to:
            continue
        if min_ttc is not None and get_exit_log_prices(item)['total_ttc'] < min_ttc:
            continue
        if max_ttc is not None and get_exit_log_prices(item)['total_ttc'] > max_ttc:
            continue
        if any(filters[key] and item_value(item, key) != filters[key] for key in ['produit', 'fournisseur', 'groupe', 'sorti_par', 'mis_en_stock_par', 'raison', 'tva']):
            continue
        filtered.append(item)
    return filtered

def build_stock_exit_stats(exits=None):
    from collections import defaultdict

    exits = exits if exits is not None else StockExitLog.query.order_by(StockExitLog.created_at.asc()).all()
    now = datetime.now()
    today = now.date()

    totals = {
        'count': len(exits),
        'total_ht': 0.0,
        'total_ttc': 0.0,
        'total_taxes': 0.0,
        'today_count': 0,
        'today_ttc': 0.0,
        'today_taxes': 0.0,
        'last_7_count': 0,
        'last_7_ttc': 0.0,
        'last_7_taxes': 0.0,
        'last_30_count': 0,
        'last_30_ttc': 0.0,
        'last_30_taxes': 0.0,
        'expired_count': 0,
        'expired_ttc': 0.0,
        'expired_taxes': 0.0,
        'quantity_total': 0,
        'avg_ttc': 0.0,
        'avg_taxes': 0.0,
        'avg_stock_age_days': 0.0
    }

    daily = defaultdict(lambda: {'count': 0, 'ht': 0.0, 'taxes': 0.0, 'ttc': 0.0})
    monthly = defaultdict(lambda: {'count': 0, 'ht': 0.0, 'taxes': 0.0, 'ttc': 0.0})
    by_product = defaultdict(lambda: {'count': 0, 'ttc': 0.0, 'quantity': 0})
    by_supplier = defaultdict(lambda: {'count': 0, 'ttc': 0.0, 'quantity': 0})
    by_supplier_group = defaultdict(lambda: {'count': 0, 'ttc': 0.0, 'quantity': 0})
    by_exit_user = defaultdict(lambda: {'count': 0, 'ttc': 0.0, 'quantity': 0})
    by_stock_user = defaultdict(lambda: {'count': 0, 'ttc': 0.0, 'quantity': 0})
    by_reason = defaultdict(lambda: {'count': 0, 'ttc': 0.0, 'quantity': 0})
    by_tva = defaultdict(lambda: {'count': 0, 'ttc': 0.0, 'taxes': 0.0})
    by_weekday = defaultdict(lambda: {'count': 0, 'ht': 0.0, 'taxes': 0.0, 'ttc': 0.0})
    by_hour = defaultdict(lambda: {'count': 0, 'ht': 0.0, 'taxes': 0.0, 'ttc': 0.0})
    stock_age_days = []

    for item in exits:
        prices = get_exit_log_prices(item)
        total_ht = prices['total_ht']
        total_ttc = prices['total_ttc']
        total_taxes = max(total_ttc - total_ht, 0)
        quantity = (
            item.quantite_unites_sortie
            + item.quantite_sous_unites_sortie
            + item.quantite_sous_sous_unites_sortie
        )
        created_at = item.created_at or now
        created_date = created_at.date()

        totals['total_ht'] += total_ht
        totals['total_ttc'] += total_ttc
        totals['total_taxes'] += total_taxes
        totals['quantity_total'] += quantity

        if created_date == today:
            totals['today_count'] += 1
            totals['today_ttc'] += total_ttc
            totals['today_taxes'] += total_taxes
        if (today - created_date).days <= 6:
            totals['last_7_count'] += 1
            totals['last_7_ttc'] += total_ttc
            totals['last_7_taxes'] += total_taxes
        if (today - created_date).days <= 29:
            totals['last_30_count'] += 1
            totals['last_30_ttc'] += total_ttc
            totals['last_30_taxes'] += total_taxes
        if item.date_peremption and item.date_peremption < created_date:
            totals['expired_count'] += 1
            totals['expired_ttc'] += total_ttc
            totals['expired_taxes'] += total_taxes
        if item.mise_en_stock_at:
            stock_age_days.append(max((created_at - item.mise_en_stock_at).days, 0))

        day_key = created_at.strftime('%Y-%m-%d')
        month_key = created_at.strftime('%Y-%m')
        daily[day_key]['count'] += 1
        daily[day_key]['ht'] += total_ht
        daily[day_key]['taxes'] += total_taxes
        daily[day_key]['ttc'] += total_ttc
        monthly[month_key]['count'] += 1
        monthly[month_key]['ht'] += total_ht
        monthly[month_key]['taxes'] += total_taxes
        monthly[month_key]['ttc'] += total_ttc

        product_key = f'{item.produit_nom} ({item.produit_code})'
        supplier_key = item.fournisseur_nom or '-'
        supplier_group_key = item.groupe_fournisseur_nom or '-'
        exit_user_key = f'{item.user_prenom} {item.user_nom}'.strip() or '-'
        stock_user_key = f'{item.mise_en_stock_user_prenom or ""} {item.mise_en_stock_user_nom or ""}'.strip() or '-'
        reason_key = item.reason_nom or '-'
        tva_key = f'{prices["tva_pourcentage"]:.2f}%'
        weekday_key = created_at.strftime('%A')
        hour_key = created_at.strftime('%H:00')

        for bucket, key in [
            (by_product, product_key),
            (by_supplier, supplier_key),
            (by_supplier_group, supplier_group_key),
            (by_exit_user, exit_user_key),
            (by_stock_user, stock_user_key),
            (by_reason, reason_key),
        ]:
            bucket[key]['count'] += 1
            bucket[key]['ttc'] += total_ttc
            bucket[key]['quantity'] += quantity

        by_tva[tva_key]['count'] += 1
        by_tva[tva_key]['ttc'] += total_ttc
        by_tva[tva_key]['taxes'] += total_taxes
        by_weekday[weekday_key]['count'] += 1
        by_weekday[weekday_key]['ht'] += total_ht
        by_weekday[weekday_key]['taxes'] += total_taxes
        by_weekday[weekday_key]['ttc'] += total_ttc
        by_hour[hour_key]['count'] += 1
        by_hour[hour_key]['ht'] += total_ht
        by_hour[hour_key]['taxes'] += total_taxes
        by_hour[hour_key]['ttc'] += total_ttc

    totals['avg_ttc'] = totals['total_ttc'] / totals['count'] if totals['count'] else 0
    totals['avg_taxes'] = totals['total_taxes'] / totals['count'] if totals['count'] else 0
    totals['avg_stock_age_days'] = sum(stock_age_days) / len(stock_age_days) if stock_age_days else 0

    def top_rows(bucket, limit=10):
        return [
            {
                'label': label,
                'count': values['count'],
                'quantity': values.get('quantity', 0),
                'ttc': round(values['ttc'], 2),
                'taxes': round(values.get('taxes', 0), 2)
            }
            for label, values in sorted(bucket.items(), key=lambda item: item[1]['ttc'], reverse=True)[:limit]
        ]

    def series_rows(bucket):
        labels = sorted(bucket.keys())
        return {
            'labels': labels,
            'count': [bucket[label]['count'] for label in labels],
            'ht': [round(bucket[label].get('ht', 0), 2) for label in labels],
            'taxes': [round(bucket[label].get('taxes', 0), 2) for label in labels],
            'ttc': [round(bucket[label]['ttc'], 2) for label in labels]
        }

    return {
        'totals': {key: round(value, 2) if isinstance(value, float) else value for key, value in totals.items()},
        'daily': series_rows(daily),
        'monthly': series_rows(monthly),
        'hourly': series_rows(by_hour),
        'weekday': series_rows(by_weekday),
        'top_products': top_rows(by_product),
        'top_suppliers': top_rows(by_supplier),
        'top_supplier_groups': top_rows(by_supplier_group),
        'top_exit_users': top_rows(by_exit_user),
        'top_stock_users': top_rows(by_stock_user),
        'top_reasons': top_rows(by_reason),
        'tva': top_rows(by_tva, limit=20)
    }

@admin.route('/stock/exits/stats')
@login_required
@permission_required('stats_sorties_stock')
def stock_exit_stats():
    filters = get_stock_exit_stats_filters()
    all_exits = StockExitLog.query.order_by(StockExitLog.created_at.asc()).all()
    exits = get_filtered_stock_exit_logs(filters)
    stats = build_stock_exit_stats(exits)
    options = get_stock_exit_stats_options(all_exits)
    return render_template('admin/stock/exit_stats.html', stats=stats, filters=filters, options=options)

@admin.route('/stock/exits/stats/export/excel')
@login_required
@permission_required('stats_sorties_stock')
def export_stock_exit_stats_excel():
    import io
    import pandas as pd
    from flask import send_file
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference

    filters = get_stock_exit_stats_filters()
    exits = get_filtered_stock_exit_logs(filters)
    stats = build_stock_exit_stats(exits)
    rows = build_stock_exit_log_rows(exits)
    generated_at = datetime.now()
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        summary_rows = [
            {'Indicateur': 'Sorties totales', 'Valeur': stats['totals']['count']},
            {'Indicateur': 'Quantite totale', 'Valeur': stats['totals']['quantity_total']},
            {'Indicateur': 'Total HT', 'Valeur': stats['totals']['total_ht']},
            {'Indicateur': 'Taxes perdues', 'Valeur': stats['totals']['total_taxes']},
            {'Indicateur': 'Perte / valeur TTC', 'Valeur': stats['totals']['total_ttc']},
            {'Indicateur': 'Sortie moyenne TTC', 'Valeur': stats['totals']['avg_ttc']},
            {'Indicateur': 'Taxes moyennes par sortie', 'Valeur': stats['totals']['avg_taxes']},
            {'Indicateur': 'Age moyen stock avant sortie', 'Valeur': stats['totals']['avg_stock_age_days']},
            {'Indicateur': 'Produits perimes sortis', 'Valeur': stats['totals']['expired_count']},
            {'Indicateur': 'Taxes perdues produits perimes', 'Valeur': stats['totals']['expired_taxes']},
            {'Indicateur': 'Perte TTC produits perimes', 'Valeur': stats['totals']['expired_ttc']}
        ]
        pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name='Synthese', startrow=5)
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name='Details')
        for sheet_name in ['Top produits', 'Top fournisseurs', 'Top raisons', 'Par utilisateur']:
            data = {
                'Top produits': stats['top_products'],
                'Top fournisseurs': stats['top_suppliers'],
                'Top raisons': stats['top_reasons'],
                'Par utilisateur': stats['top_exit_users']
            }[sheet_name]
            pd.DataFrame(data).to_excel(writer, index=False, sheet_name=sheet_name)

        chart_sheet = writer.book.create_sheet('Courbes')
        chart_sheet['A1'] = 'Evolution quotidienne'
        chart_sheet.append(['Date', 'Sorties', 'HT', 'Taxes', 'TTC'])
        for label, count, ht, taxes, ttc in zip(stats['daily']['labels'], stats['daily']['count'], stats['daily']['ht'], stats['daily']['taxes'], stats['daily']['ttc']):
            chart_sheet.append([label, count, ht, taxes, ttc])

        monthly_start = chart_sheet.max_row + 3
        chart_sheet.cell(monthly_start, 1, 'Evolution mensuelle')
        chart_sheet.cell(monthly_start + 1, 1, 'Mois')
        chart_sheet.cell(monthly_start + 1, 2, 'Sorties')
        chart_sheet.cell(monthly_start + 1, 3, 'HT')
        chart_sheet.cell(monthly_start + 1, 4, 'Taxes')
        chart_sheet.cell(monthly_start + 1, 5, 'TTC')
        for offset, (label, count, ht, taxes, ttc) in enumerate(zip(stats['monthly']['labels'], stats['monthly']['count'], stats['monthly']['ht'], stats['monthly']['taxes'], stats['monthly']['ttc']), start=monthly_start + 2):
            chart_sheet.cell(offset, 1, label)
            chart_sheet.cell(offset, 2, count)
            chart_sheet.cell(offset, 3, ht)
            chart_sheet.cell(offset, 4, taxes)
            chart_sheet.cell(offset, 5, ttc)

        products_start = chart_sheet.max_row + 3
        chart_sheet.cell(products_start, 1, 'Top produits')
        chart_sheet.cell(products_start + 1, 1, 'Produit')
        chart_sheet.cell(products_start + 1, 2, 'TTC')
        for offset, row in enumerate(stats['top_products'][:10], start=products_start + 2):
            chart_sheet.cell(offset, 1, row['label'])
            chart_sheet.cell(offset, 2, row['ttc'])

        reasons_start = chart_sheet.max_row + 3
        chart_sheet.cell(reasons_start, 1, 'Top raisons')
        chart_sheet.cell(reasons_start + 1, 1, 'Raison')
        chart_sheet.cell(reasons_start + 1, 2, 'TTC')
        for offset, row in enumerate(stats['top_reasons'][:10], start=reasons_start + 2):
            chart_sheet.cell(offset, 1, row['label'])
            chart_sheet.cell(offset, 2, row['ttc'])

        worksheet = writer.sheets['Synthese']
        worksheet['A1'] = 'Rapport statistiques sorties de stock - ReflexPharma'
        worksheet['A2'] = f'Date du tirage : {generated_at.strftime("%d/%m/%Y %H:%M")}'
        worksheet['A3'] = f'Tire par : {current_user.nom} {current_user.prenom}'
        active_filters = ', '.join(f'{key}={value}' for key, value in filters.items() if value) or 'Aucun filtre'
        worksheet['A4'] = f'Filtres : {active_filters}'
        worksheet['A5'] = f'Lignes analysees : {len(exits)}'

        header_fill = PatternFill(start_color='1F2937', end_color='1F2937', fill_type='solid')
        header_font = Font(bold=True, color='FFFFFF')
        thin_border = Border(bottom=Side(style='thin', color='D1D5DB'))
        for ws in writer.sheets.values():
            for row in ws.iter_rows():
                for cell in row:
                    cell.alignment = Alignment(vertical='top', wrap_text=True)
                    cell.border = thin_border
            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
            for col in range(1, min(ws.max_column, 12) + 1):
                ws.column_dimensions[chr(64 + col)].width = 22

        if stats['daily']['labels']:
            daily_chart = LineChart()
            daily_chart.title = 'Sorties quotidiennes'
            daily_chart.y_axis.title = 'HT / taxes / TTC / sorties'
            daily_chart.x_axis.title = 'Date'
            daily_chart.add_data(Reference(chart_sheet, min_col=2, max_col=5, min_row=2, max_row=2 + len(stats['daily']['labels'])), titles_from_data=True)
            daily_chart.set_categories(Reference(chart_sheet, min_col=1, min_row=3, max_row=2 + len(stats['daily']['labels'])))
            daily_chart.height = 9
            daily_chart.width = 22
            chart_sheet.add_chart(daily_chart, 'E2')

        if stats['monthly']['labels']:
            monthly_chart = BarChart()
            monthly_chart.title = 'Valeur mensuelle HT / taxes / TTC'
            monthly_chart.y_axis.title = 'Valeur'
            monthly_chart.x_axis.title = 'Mois'
            monthly_end = monthly_start + 1 + len(stats['monthly']['labels'])
            monthly_chart.add_data(Reference(chart_sheet, min_col=3, max_col=5, min_row=monthly_start + 1, max_row=monthly_end), titles_from_data=True)
            monthly_chart.set_categories(Reference(chart_sheet, min_col=1, min_row=monthly_start + 2, max_row=monthly_end))
            monthly_chart.height = 8
            monthly_chart.width = 18
            chart_sheet.add_chart(monthly_chart, 'E20')

        if stats['top_products']:
            product_chart = BarChart()
            product_chart.type = 'bar'
            product_chart.title = 'Top produits par perte TTC'
            product_end = products_start + 1 + min(len(stats['top_products']), 10)
            product_chart.add_data(Reference(chart_sheet, min_col=2, min_row=products_start + 1, max_row=product_end), titles_from_data=True)
            product_chart.set_categories(Reference(chart_sheet, min_col=1, min_row=products_start + 2, max_row=product_end))
            product_chart.height = 10
            product_chart.width = 22
            chart_sheet.add_chart(product_chart, 'E36')

        if stats['top_reasons']:
            reason_chart = PieChart()
            reason_chart.title = 'Repartition par raison'
            reason_end = reasons_start + 1 + min(len(stats['top_reasons']), 10)
            reason_chart.add_data(Reference(chart_sheet, min_col=2, min_row=reasons_start + 1, max_row=reason_end), titles_from_data=True)
            reason_chart.set_categories(Reference(chart_sheet, min_col=1, min_row=reasons_start + 2, max_row=reason_end))
            reason_chart.height = 9
            reason_chart.width = 14
            chart_sheet.add_chart(reason_chart, 'E56')

    output.seek(0)
    filename = f'stats_sorties_stock_{generated_at.strftime("%Y%m%d_%H%M")}.xlsx'
    return send_file(output, download_name=filename, as_attachment=True)

@admin.route('/stock/exits/stats/export/pdf')
@login_required
@permission_required('stats_sorties_stock')
def export_stock_exit_stats_pdf():
    import io
    from flask import send_file
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie

    filters = get_stock_exit_stats_filters()
    exits = get_filtered_stock_exit_logs(filters)
    stats = build_stock_exit_stats(exits)
    generated_at = datetime.now()
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, topMargin=18, bottomMargin=18, leftMargin=18, rightMargin=18)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('StatsTitle', parent=styles['Title'], fontSize=13, leading=15)
    meta_style = ParagraphStyle('StatsMeta', parent=styles['Normal'], fontSize=8, leading=10)
    elements = [
        Paragraph('Rapport statistiques sorties de stock - ReflexPharma', title_style),
        Paragraph(f'Date du tirage : {generated_at.strftime("%d/%m/%Y %H:%M")} | Tire par : {current_user.nom} {current_user.prenom}', meta_style),
        Paragraph('Filtres : ' + (', '.join(f'{key}={value}' for key, value in filters.items() if value) or 'Aucun filtre'), meta_style),
        Spacer(1, 8)
    ]

    summary = [
        ['Indicateur', 'Valeur'],
        ['Sorties totales', stats['totals']['count']],
        ['Quantite totale', stats['totals']['quantity_total']],
        ['Total HT', f"{stats['totals']['total_ht']:.2f}"],
        ['Taxes perdues', f"{stats['totals']['total_taxes']:.2f}"],
        ['Perte / valeur TTC', f"{stats['totals']['total_ttc']:.2f}"],
        ['Sortie moyenne TTC', f"{stats['totals']['avg_ttc']:.2f}"],
        ['Taxes moyennes par sortie', f"{stats['totals']['avg_taxes']:.2f}"],
        ['Age moyen avant sortie', f"{stats['totals']['avg_stock_age_days']:.1f} j"],
        ['Produits perimes sortis', stats['totals']['expired_count']],
        ['Taxes perdues produits perimes', f"{stats['totals']['expired_taxes']:.2f}"]
    ]
    elements.append(Table(summary, repeatRows=1, colWidths=[260, 240], style=[
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(Spacer(1, 10))

    def add_vertical_chart(title, labels, values, value_label='TTC', max_items=12):
        labels = labels[:max_items]
        values = values[:max_items]
        if not labels or not values:
            return
        drawing = Drawing(500, 185)
        drawing.add(String(0, 170, title, fontSize=10, fillColor=colors.HexColor('#1F2937')))
        chart = VerticalBarChart()
        chart.x = 35
        chart.y = 35
        chart.height = 115
        chart.width = 430
        chart.data = [values]
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.angle = 35
        chart.categoryAxis.labels.fontSize = 5
        chart.valueAxis.valueMin = 0
        chart.bars[0].fillColor = colors.HexColor('#DC3545')
        drawing.add(chart)
        drawing.add(String(35, 12, value_label, fontSize=7, fillColor=colors.HexColor('#6B7280')))
        elements.append(drawing)
        elements.append(Spacer(1, 8))

    def add_grouped_vertical_chart(title, labels, series, max_items=12):
        labels = labels[:max_items]
        if not labels or not series:
            return
        drawing = Drawing(500, 205)
        drawing.add(String(0, 190, title, fontSize=10, fillColor=colors.HexColor('#1F2937')))
        chart = VerticalBarChart()
        chart.x = 35
        chart.y = 42
        chart.height = 125
        chart.width = 430
        chart.data = [values[:max_items] for _, values, _ in series]
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.angle = 35
        chart.categoryAxis.labels.fontSize = 5
        chart.valueAxis.valueMin = 0
        for index, (_, _, color) in enumerate(series):
            chart.bars[index].fillColor = color
        drawing.add(chart)
        y = 18
        x = 35
        for label, _, color in series:
            drawing.add(String(x, y, label, fontSize=7, fillColor=color))
            x += 80
        elements.append(drawing)
        elements.append(Spacer(1, 8))

    def add_horizontal_chart(title, rows, max_items=8):
        rows = rows[:max_items]
        if not rows:
            return
        drawing = Drawing(500, 210)
        drawing.add(String(0, 195, title, fontSize=10, fillColor=colors.HexColor('#1F2937')))
        chart = HorizontalBarChart()
        chart.x = 125
        chart.y = 25
        chart.height = 155
        chart.width = 330
        chart.data = [[row['ttc'] for row in rows]]
        chart.categoryAxis.categoryNames = [row['label'][:28] for row in rows]
        chart.categoryAxis.labels.fontSize = 6
        chart.valueAxis.valueMin = 0
        chart.bars[0].fillColor = colors.HexColor('#198754')
        drawing.add(chart)
        elements.append(drawing)
        elements.append(Spacer(1, 8))

    def add_line_chart(title, labels, values, max_items=18):
        labels = labels[-max_items:]
        values = values[-max_items:]
        if not labels or not values:
            return
        drawing = Drawing(500, 185)
        drawing.add(String(0, 170, title, fontSize=10, fillColor=colors.HexColor('#1F2937')))
        chart = HorizontalLineChart()
        chart.x = 35
        chart.y = 35
        chart.height = 115
        chart.width = 430
        chart.data = [values]
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.angle = 35
        chart.categoryAxis.labels.fontSize = 5
        chart.valueAxis.valueMin = 0
        chart.lines[0].strokeColor = colors.HexColor('#DC3545')
        drawing.add(chart)
        elements.append(drawing)
        elements.append(Spacer(1, 8))

    def add_multi_line_chart(title, labels, series, max_items=18):
        labels = labels[-max_items:]
        if not labels or not series:
            return
        drawing = Drawing(500, 200)
        drawing.add(String(0, 185, title, fontSize=10, fillColor=colors.HexColor('#1F2937')))
        chart = HorizontalLineChart()
        chart.x = 35
        chart.y = 45
        chart.height = 115
        chart.width = 430
        chart.data = [values[-max_items:] for _, values, _ in series]
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.angle = 35
        chart.categoryAxis.labels.fontSize = 5
        chart.valueAxis.valueMin = 0
        for index, (_, _, color) in enumerate(series):
            chart.lines[index].strokeColor = color
        drawing.add(chart)
        x = 35
        for label, _, color in series:
            drawing.add(String(x, 18, label, fontSize=7, fillColor=color))
            x += 85
        elements.append(drawing)
        elements.append(Spacer(1, 8))

    def add_pie_chart(title, rows, max_items=6):
        rows = rows[:max_items]
        if not rows:
            return
        drawing = Drawing(500, 180)
        drawing.add(String(0, 165, title, fontSize=10, fillColor=colors.HexColor('#1F2937')))
        pie = Pie()
        pie.x = 20
        pie.y = 25
        pie.width = 130
        pie.height = 130
        pie.data = [row['ttc'] for row in rows]
        pie.labels = [row['label'][:18] for row in rows]
        drawing.add(pie)
        y = 135
        for row in rows:
            drawing.add(String(180, y, f"{row['label'][:40]}: {row['ttc']:.2f}", fontSize=7, fillColor=colors.HexColor('#374151')))
            y -= 16
        elements.append(drawing)
        elements.append(Spacer(1, 8))

    add_multi_line_chart(
        'Courbe quotidienne HT / taxes / TTC',
        stats['daily']['labels'],
        [
            ('HT', stats['daily']['ht'], colors.HexColor('#198754')),
            ('Taxes', stats['daily']['taxes'], colors.HexColor('#FFC107')),
            ('TTC', stats['daily']['ttc'], colors.HexColor('#DC3545'))
        ]
    )
    add_grouped_vertical_chart(
        'Valeur mensuelle HT / taxes / TTC',
        stats['monthly']['labels'],
        [
            ('HT', stats['monthly']['ht'], colors.HexColor('#198754')),
            ('Taxes', stats['monthly']['taxes'], colors.HexColor('#FFC107')),
            ('TTC', stats['monthly']['ttc'], colors.HexColor('#DC3545'))
        ]
    )
    add_horizontal_chart('Top produits par perte TTC', stats['top_products'])
    add_horizontal_chart('Top fournisseurs par perte TTC', stats['top_suppliers'])
    add_pie_chart('Repartition par raison', stats['top_reasons'])

    def add_top_table(title, rows):
        elements.append(Paragraph(title, styles['Heading3']))
        data = [['Libelle', 'Sorties', 'Qte', 'TTC']]
        data.extend([[row['label'], row['count'], row.get('quantity', 0), f"{row['ttc']:.2f}"] for row in rows[:8]])
        elements.append(Table(data, repeatRows=1, colWidths=[290, 60, 60, 90], style=[
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(Spacer(1, 8))

    add_top_table('Top produits', stats['top_products'])
    add_top_table('Top fournisseurs', stats['top_suppliers'])
    add_top_table('Top raisons', stats['top_reasons'])
    add_top_table('Top utilisateurs sortie', stats['top_exit_users'])

    doc.build(elements)
    output.seek(0)
    filename = f'stats_sorties_stock_{generated_at.strftime("%Y%m%d_%H%M")}.pdf'
    return send_file(output, download_name=filename, as_attachment=True)

def get_exit_log_prices(item):
    prix_unite_ht = float(item.prix_unite_ht or 0)
    prix_sous_unite_ht = float(item.prix_sous_unite_ht or 0)
    prix_sous_sous_unite_ht = float(item.prix_sous_sous_unite_ht or 0)
    prix_unite_ttc = float(item.prix_unite_ttc or 0)
    prix_sous_unite_ttc = float(item.prix_sous_unite_ttc or 0)
    prix_sous_sous_unite_ttc = float(item.prix_sous_sous_unite_ttc or 0)

    total_ht = float(item.total_sortie_ht or 0)
    total_ttc = float(item.total_sortie_ttc or 0)
    if not total_ht:
        total_ht = (
            item.quantite_unites_sortie * prix_unite_ht
            + item.quantite_sous_unites_sortie * prix_sous_unite_ht
            + item.quantite_sous_sous_unites_sortie * prix_sous_sous_unite_ht
        )
    if not total_ttc:
        total_ttc = (
            item.quantite_unites_sortie * prix_unite_ttc
            + item.quantite_sous_unites_sortie * prix_sous_unite_ttc
            + item.quantite_sous_sous_unites_sortie * prix_sous_sous_unite_ttc
        )

    return {
        'prix_unite_ht': prix_unite_ht,
        'prix_sous_unite_ht': prix_sous_unite_ht,
        'prix_sous_sous_unite_ht': prix_sous_sous_unite_ht,
        'prix_unite_ttc': prix_unite_ttc,
        'prix_sous_unite_ttc': prix_sous_unite_ttc,
        'prix_sous_sous_unite_ttc': prix_sous_sous_unite_ttc,
        'tva_pourcentage': float(item.tva_pourcentage or 0),
        'total_ht': total_ht,
        'total_ttc': total_ttc
    }

def get_exit_log_supplier_info(item):
    return {
        'fournisseur': item.fournisseur_nom or '-',
        'groupe_fournisseur': item.groupe_fournisseur_nom or '-'
    }

def build_stock_exit_log_rows(exits):
    rows = []
    for item in exits:
        prices = get_exit_log_prices(item)
        supplier = get_exit_log_supplier_info(item)
        rows.append({
            'date_sortie': item.created_at.strftime('%d/%m/%Y %H:%M') if item.created_at else '-',
            'produit': item.produit_nom,
            'code_produit': item.produit_code,
            'fournisseur': supplier['fournisseur'],
            'groupe_fournisseur': supplier['groupe_fournisseur'],
            'code_suivi': item.code_suivi,
            'numero_bl': item.numero_bl,
            'date_peremption': item.date_peremption.strftime('%d/%m/%Y') if item.date_peremption else '-',
            'date_mise_en_stock': item.mise_en_stock_at.strftime('%d/%m/%Y %H:%M') if item.mise_en_stock_at else '-',
            'mis_en_stock_par': (
                f'{item.mise_en_stock_user_prenom or ""} {item.mise_en_stock_user_nom or ""}'.strip()
                or '-'
            ),
            'mis_en_stock_email': item.mise_en_stock_user_email or '-',
            'sorti_par': f'{item.user_prenom} {item.user_nom}',
            'email': item.user_email,
            'raison': item.reason_nom,
            'sortie': f'U:{item.quantite_unites_sortie} S/U:{item.quantite_sous_unites_sortie} SS/U:{item.quantite_sous_sous_unites_sortie}',
            'prix_ht': f'U:{prices["prix_unite_ht"]:.2f} S/U:{prices["prix_sous_unite_ht"]:.2f} SS/U:{prices["prix_sous_sous_unite_ht"]:.2f}',
            'prix_ttc': f'U:{prices["prix_unite_ttc"]:.2f} S/U:{prices["prix_sous_unite_ttc"]:.2f} SS/U:{prices["prix_sous_sous_unite_ttc"]:.2f}',
            'tva': f'{prices["tva_pourcentage"]:.2f}',
            'total_ht': f'{prices["total_ht"]:.2f}',
            'total_ttc': f'{prices["total_ttc"]:.2f}',
            'avant': f'U:{item.old_quantite_unites} S/U:{item.old_quantite_sous_unites} SS/U:{item.old_quantite_sous_sous_unites}',
            'apres': f'U:{item.new_quantite_unites} S/U:{item.new_quantite_sous_unites} SS/U:{item.new_quantite_sous_sous_unites}'
        })
    return rows

def get_stock_exit_logs_for_export():
    exits = StockExitLog.query.order_by(StockExitLog.created_at.desc()).all()
    query = (request.args.get('q') or '').strip().lower()
    sort_field = request.args.get('sort') or 'date'
    sort_direction = request.args.get('direction') or 'desc'

    if query:
        exits = [
            item for item in exits
            if query in ' '.join([
                item.created_at.strftime('%d/%m/%Y %H:%M') if item.created_at else '',
                item.produit_nom or '',
                item.produit_code or '',
                get_exit_log_supplier_info(item)['fournisseur'],
                get_exit_log_supplier_info(item)['groupe_fournisseur'],
                item.code_suivi or '',
                item.numero_bl or '',
                item.date_peremption.strftime('%d/%m/%Y') if item.date_peremption else '',
                item.mise_en_stock_at.strftime('%d/%m/%Y %H:%M') if item.mise_en_stock_at else '',
                item.mise_en_stock_user_prenom or '',
                item.mise_en_stock_user_nom or '',
                item.mise_en_stock_user_email or '',
                item.user_prenom or '',
                item.user_nom or '',
                item.user_email or '',
                item.reason_nom or '',
                f'{get_exit_log_prices(item)["tva_pourcentage"]:.2f}',
                f'{get_exit_log_prices(item)["total_ht"]:.2f}',
                f'{get_exit_log_prices(item)["total_ttc"]:.2f}'
            ]).lower()
        ]

    sort_getters = {
        'date': lambda item: item.created_at or datetime.min,
        'produit': lambda item: (item.produit_nom or '').lower(),
        'fournisseur': lambda item: get_exit_log_supplier_info(item)['fournisseur'].lower(),
        'groupe': lambda item: get_exit_log_supplier_info(item)['groupe_fournisseur'].lower(),
        'code': lambda item: (item.code_suivi or '').lower(),
        'bl': lambda item: (item.numero_bl or '').lower(),
        'peremption': lambda item: item.date_peremption or datetime.min.date(),
        'mise_stock': lambda item: item.mise_en_stock_at or datetime.min,
        'mis_par': lambda item: f'{item.mise_en_stock_user_prenom or ""} {item.mise_en_stock_user_nom or ""} {item.mise_en_stock_user_email or ""}'.lower(),
        'auteur': lambda item: f'{item.user_prenom or ""} {item.user_nom or ""} {item.user_email or ""}'.lower(),
        'raison': lambda item: (item.reason_nom or '').lower(),
        'perte': lambda item: get_exit_log_prices(item)['total_ttc']
    }
    exits.sort(key=sort_getters.get(sort_field, sort_getters['date']), reverse=sort_direction != 'asc')
    return exits

@admin.route('/stock/exits/export/excel')
@login_required
@permission_required('gestion_modifications_stock')
def export_stock_exit_logs_excel():
    import io
    import pandas as pd
    from flask import send_file
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

    exits = get_stock_exit_logs_for_export()
    rows = build_stock_exit_log_rows(exits)
    generated_at = datetime.now()
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            'date_sortie': 'Date sortie',
            'produit': 'Produit',
            'code_produit': 'Code produit',
            'fournisseur': 'Fournisseur',
            'groupe_fournisseur': 'Groupe fournisseur',
            'code_suivi': 'Code suivi',
            'numero_bl': 'BL',
            'date_peremption': 'Peremption',
            'date_mise_en_stock': 'Date mise en stock',
            'mis_en_stock_par': 'Mis en stock par',
            'mis_en_stock_email': 'Email mise en stock',
            'sorti_par': 'Sorti par',
            'email': 'Email auteur',
            'raison': 'Raison',
            'sortie': 'Quantite sortie',
            'prix_ht': 'Prix unitaires HT',
            'prix_ttc': 'Prix unitaires TTC',
            'tva': 'TVA %',
            'total_ht': 'Total sortie HT',
            'total_ttc': 'Perte / valeur TTC',
            'avant': 'Avant',
            'apres': 'Apres'
        })
        df.to_excel(writer, index=False, sheet_name='Sorties stock', startrow=4)
        worksheet = writer.sheets['Sorties stock']
        worksheet['A1'] = 'Historique des sorties de stock - ReflexPharma'
        worksheet['A2'] = f'Date du tirage : {generated_at.strftime("%d/%m/%Y %H:%M")}'
        worksheet['A3'] = f'Tire par : {current_user.nom} {current_user.prenom}'
        worksheet['A4'] = f'Lignes exportees : {len(rows)}'

        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='1F2937', end_color='1F2937', fill_type='solid')
        meta_font = Font(size=10, color='374151')
        thin_border = Border(bottom=Side(style='thin', color='D1D5DB'))

        worksheet['A1'].font = Font(bold=True, size=14, color='1F2937')
        for row_number in range(2, 5):
            worksheet[f'A{row_number}'].font = meta_font
        for cell in worksheet[5]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        for row in worksheet.iter_rows(min_row=6, max_row=worksheet.max_row):
            for cell in row:
                cell.border = thin_border
                cell.alignment = Alignment(vertical='top', wrap_text=True)

        widths = [17, 24, 15, 22, 22, 34, 14, 13, 17, 20, 26, 20, 26, 20, 21, 24, 24, 10, 16, 18, 21, 21]
        for index, width in enumerate(widths, start=1):
            worksheet.column_dimensions[chr(64 + index)].width = width
        worksheet.freeze_panes = 'A6'

    output.seek(0)
    filename = f'sorties_stock_{generated_at.strftime("%Y%m%d_%H%M")}.xlsx'
    return send_file(output, download_name=filename, as_attachment=True)

@admin.route('/stock/exits/export/pdf')
@login_required
@permission_required('gestion_modifications_stock')
def export_stock_exit_logs_pdf():
    import io
    from flask import send_file
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    exits = get_stock_exit_logs_for_export()
    rows = build_stock_exit_log_rows(exits)
    generated_at = datetime.now()
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), topMargin=10, bottomMargin=10, leftMargin=10, rightMargin=10)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ExitLogTitle', parent=styles['Title'], fontSize=11, leading=13, spaceAfter=3)
    meta_style = ParagraphStyle('ExitLogMeta', parent=styles['Normal'], fontSize=7, leading=8, textColor=colors.HexColor('#374151'))
    cell_style = ParagraphStyle('ExitLogCell', parent=styles['Normal'], fontSize=5.5, leading=6.4)
    header_style = ParagraphStyle('ExitLogHeader', parent=cell_style, alignment=TA_CENTER, textColor=colors.white)

    elements = [
        Paragraph('Historique des sorties de stock - ReflexPharma', title_style),
        Paragraph(
            f'Date du tirage : {generated_at.strftime("%d/%m/%Y %H:%M")} | Tire par : {current_user.nom} {current_user.prenom} | Lignes : {len(rows)}',
            meta_style
        ),
        Spacer(1, 4)
    ]

    data = [[
        Paragraph('Date', header_style),
        Paragraph('Produit', header_style),
        Paragraph('Fourn.', header_style),
        Paragraph('Groupe', header_style),
        Paragraph('Code suivi', header_style),
        Paragraph('BL', header_style),
        Paragraph('Peremp.', header_style),
        Paragraph('Mise stock', header_style),
        Paragraph('Mis par', header_style),
        Paragraph('Auteur', header_style),
        Paragraph('Raison', header_style),
        Paragraph('Sortie', header_style),
        Paragraph('TVA', header_style),
        Paragraph('Prix TTC', header_style),
        Paragraph('Perte TTC', header_style),
        Paragraph('Avant', header_style),
        Paragraph('Apres', header_style)
    ]]
    for row in rows:
        produit = escape(str(row['produit']))
        code_produit = escape(str(row['code_produit']))
        data.append([
            row['date_sortie'],
            Paragraph(f"{produit}<br/>{code_produit}", cell_style),
            Paragraph(escape(str(row['fournisseur'])), cell_style),
            Paragraph(escape(str(row['groupe_fournisseur'])), cell_style),
            Paragraph(escape(str(row['code_suivi'])), cell_style),
            Paragraph(escape(str(row['numero_bl'])), cell_style),
            row['date_peremption'],
            row['date_mise_en_stock'],
            Paragraph(escape(str(row['mis_en_stock_par'])), cell_style),
            Paragraph(escape(str(row['sorti_par'])), cell_style),
            Paragraph(escape(str(row['raison'])), cell_style),
            row['sortie'],
            f"{row['tva']}%",
            row['prix_ttc'],
            row['total_ttc'],
            row['avant'],
            row['apres']
        ])

    table = Table(data, repeatRows=1, colWidths=[42, 68, 54, 50, 76, 36, 32, 47, 47, 48, 48, 45, 43, 58, 39, 42, 42])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 5.5),
        ('LEADING', (0, 0), (-1, -1), 6.4),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (3, 1), (4, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.4),
        ('LEFTPADDING', (0, 0), (-1, -1), 1.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1.5),
    ]))
    elements.append(table)
    doc.build(elements)
    output.seek(0)
    filename = f'sorties_stock_{generated_at.strftime("%Y%m%d_%H%M")}.pdf'
    return send_file(output, download_name=filename, as_attachment=True)

# --- VUES FILTRÉES PRODUITS ---
@admin.route('/produits/rayon/<int:id>')
@login_required
@permission_required('gestion_produits')
def list_produits_by_rayon(id):
    rayon = Rayon.query.get_or_404(id)
    produits = Produit.query.filter_by(rayon_id=id).all()
    return render_template('admin/produits/list.html', produits=produits, title=f'Produits - Rayon : {rayon.nom}')

@admin.route('/produits/famille/<int:id>')
@login_required
@permission_required('gestion_produits')
def list_produits_by_famille(id):
    famille = Famille.query.get_or_404(id)
    produits = Produit.query.filter_by(famille_id=id).all()
    return render_template('admin/produits/list.html', produits=produits, title=f'Produits - Famille : {famille.nom}')

@admin.route('/produits/section/<int:id>')
@login_required
@permission_required('gestion_produits')
def list_produits_by_section(id):
    section = Section.query.get_or_404(id)
    produits = Produit.query.filter_by(section_id=id).all()
    return render_template('admin/produits/list.html', produits=produits, title=f'Produits - Section : {section.nom}')

import pandas as pd
from flask import send_file
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

@admin.route('/produits/export/excel')
@login_required
@permission_required('gestion_produits')
def export_produits_excel():
    produits = Produit.query.all()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    data = [{
        'Code': p.code_produit,
        'Nom': p.nom,
        'Fournisseur': p.fournisseur.nom if p.fournisseur else '',
        'Rayon': p.rayon.nom if p.rayon else '',
        'Famille': p.famille.nom if p.famille else '',
        'Conditionnement': p.conditionnement,
        'Prix Unité': p.prix_unite
    } for p in produits]
    
    df = pd.DataFrame(data)
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Produits', startrow=2)
        workbook = writer.book
        worksheet = writer.sheets['Produits']
        
        # Add metadata
        worksheet['A1'] = f"Rapport généré le : {timestamp}"
        worksheet['A2'] = f"Tiré par : {current_user.nom} {current_user.prenom}"
        
        # Style
        from openpyxl.styles import Font, PatternFill, Alignment
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        
        for cell in worksheet[3]: # Header row is now 3
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
            
    output.seek(0)
    return send_file(output, download_name=f'produits_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx', as_attachment=True)

@admin.route('/produits/export/pdf')
@login_required
@permission_required('gestion_produits')
def export_produits_pdf():
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    
    produits = Produit.query.all()
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, topMargin=20, bottomMargin=20, leftMargin=20, rightMargin=20)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph(f'Catalogue Produits - ReflexPharma', styles['Title']))
    elements.append(Paragraph(f'Tiré par : {current_user.nom} {current_user.prenom} | Date : {datetime.now().strftime("%d/%m/%Y %H:%M")}', styles['Normal']))
    elements.append(Spacer(1, 12))
    
    data = [['Code', 'Nom', 'Fournisseur', 'Prix']]
    for p in produits:
        data.append([p.code_produit, p.nom, p.fournisseur.nom if p.fournisseur else '-', f'{p.prix_unite} €'])
        
    table = Table(data, repeatRows=1, colWidths=[100, 200, 150, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    elements.append(table)
    doc.build(elements)
    output.seek(0)
    return send_file(output, download_name=f'produits_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf', as_attachment=True)
