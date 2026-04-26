from flask import render_template, redirect, request, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from . import auth
from models.user import User
from extensions import db

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            flash('Veuillez vérifier vos identifiants de connexion.', 'danger')
            return redirect(url_for('auth.login'))
            
        if not user.is_active:
            flash('Votre compte est désactivé. Veuillez contacter un administrateur.', 'warning')
            return redirect(url_for('auth.login'))
            
        login_user(user, remember=remember)
        return redirect(url_for('admin.dashboard'))
        
    return render_template('auth/login.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(old_password):
            flash('L\'ancien mot de passe est incorrect.', 'danger')
            return redirect(url_for('auth.change_password'))

        if new_password != confirm_password:
            flash('Le nouveau mot de passe et la confirmation ne correspondent pas.', 'danger')
            return redirect(url_for('auth.change_password'))

        if not new_password:
            flash('Le nouveau mot de passe ne peut pas être vide.', 'danger')
            return redirect(url_for('auth.change_password'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('Votre mot de passe a été mis à jour avec succès.', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('auth/change_password.html')
