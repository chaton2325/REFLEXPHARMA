from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from . import admin
from models.user import User
from models.poste import Poste
from models.permission import Permission
from models.fournisseur import Fournisseur
from models.groupe_fournisseur import GroupeFournisseur
from extensions import db
from functools import wraps
from datetime import datetime
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

# ... (delete_user et toggle_user_active restent identiques)
@admin.route('/users/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('gestion_employes')
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
        return redirect(url_for('admin.list_users'))
    db.session.delete(user)
    db.session.commit()
    flash('Utilisateur supprimé.', 'success')
    return redirect(url_for('admin.list_users'))

@admin.route('/users/toggle/<int:id>')
@login_required
@permission_required('gestion_employes')
def toggle_user_active(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas désactiver votre propre compte.", "danger")
        return redirect(url_for('admin.list_users'))
    user.is_active = not user.is_active
    db.session.commit()
    status = "activé" if user.is_active else "désactivé"
    flash(f'Utilisateur {status}.', 'success')
    return redirect(url_for('admin.list_users'))

@admin.route('/users/bulk-delete', methods=['POST'])
@login_required
@permission_required('gestion_employes')
def bulk_delete_users():
    ids = request.form.getlist('ids[]')
    if not ids:
        flash("Aucun utilisateur sélectionné.", "warning")
        return redirect(url_for('admin.list_users'))
    
    deleted_count = 0
    for user_id in ids:
        if int(user_id) == current_user.id:
            continue
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            deleted_count += 1
            
    db.session.commit()
    flash(f'{deleted_count} utilisateur(s) supprimé(s).', 'success')
    return redirect(url_for('admin.list_users'))

# --- GESTION DES FOURNISSEURS ---
@admin.route('/fournisseurs')
@login_required
@permission_required('gestion_fournisseurs')
def list_fournisseurs():
    fournisseurs = Fournisseur.query.all()
    groupes = GroupeFournisseur.query.all()
    return render_template('admin/fournisseurs/list.html', fournisseurs=fournisseurs, groupes=groupes)

# ... (les autres routes fournisseurs)

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
