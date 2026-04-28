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

def create_stock_modification(stock, produit, action, reason, old_values, new_values, old_qr_tire, new_qr_tire):
    modification = StockModification(
        stock_id=None,
        produit=produit,
        user_id=current_user.id,
        action=action,
        reason=reason,
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

    if request.method == 'POST':
        produit_id = int(request.form.get('produit_id'))
        produit = Produit.query.get_or_404(produit_id)
        reason = (request.form.get('reason') or '').strip()
        numero_bl_raw = (request.form.get('numero_bl') or '').strip()
        date_peremption_str = (request.form.get('date_peremption') or '').strip()

        if not reason:
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
                reason=reason,
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
                reason=reason,
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
    return render_template('admin/stock/list.html', produits=produits, stocks=stocks)

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
    selected_ids = [int(stock_id) for stock_id in request.form.getlist('stock_ids') if stock_id.isdigit()]
    if not selected_ids:
        flash('Veuillez selectionner au moins une ligne de stock pour tirer les QR codes.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    stocks = (
        Stock.query
        .join(Produit)
        .filter(Stock.id.in_(selected_ids))
        .order_by(Produit.nom.asc(), Stock.date_peremption.asc())
        .all()
    )
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
    selected_ids = [int(stock_id) for stock_id in request.form.getlist('stock_ids') if stock_id.isdigit()]
    reason = (request.form.get('reason') or '').strip()

    if not selected_ids:
        flash('Veuillez selectionner au moins une ligne de stock.', 'warning')
        return redirect(url_for('admin.manage_stock'))
    if not reason:
        flash('Veuillez preciser la raison du tirage des QR codes.', 'warning')
        return redirect(url_for('admin.manage_stock'))

    stocks = Stock.query.filter(Stock.id.in_(selected_ids)).all()
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

@admin.route('/stock/modifications')
@login_required
@permission_required('gestion_modifications_stock')
def list_stock_modifications():
    modifications = StockModification.query.order_by(StockModification.created_at.desc()).all()
    return render_template('admin/stock/modifications.html', modifications=modifications)

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
