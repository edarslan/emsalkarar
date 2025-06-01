from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash # Only for initial admin or testing
from models import db, User
from forms import LoginForm, RegistrationForm 
#from forms import RequestPasswordResetForm, ResetPasswordForm
# from utils import send_password_reset_email # Implement later if needed

auth_bp = Blueprint('auth', __name__, template_folder='templates')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index')) # Assuming 'main.index' will be the main blueprint's index
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            user = User(full_name=form.full_name.data, email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Hesabınız başarıyla oluşturuldu! Şimdi giriş yapabilirsiniz.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Kayıt sırasında bir hata oluştu: {e}', 'danger')
    return render_template('register.html', title='Kayıt Ol', form=form)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index')) # Redirect to dashboard blueprint's index
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash('Başarıyla giriş yaptınız!', 'success')
            # Redirect to dashboard or the originally requested page
            return redirect(next_page) if next_page else redirect(url_for('dashboard.index'))
        else:
            flash('Giriş başarısız. Lütfen e-posta ve şifrenizi kontrol edin.', 'danger')
    return render_template('login.html', title='Giriş Yap', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Başarıyla çıkış yaptınız.', 'info')
    return redirect(url_for('main.index')) # Redirect to main page after logout

# Password Reset Routes (Implement later if needed)
# @auth_bp.route('/reset_password_request', methods=['GET', 'POST'])
# def reset_password_request():
#     if current_user.is_authenticated:
#         return redirect(url_for('main.index'))
#     form = RequestPasswordResetForm()
#     if form.validate_on_submit():
#         user = User.query.filter_by(email=form.email.data).first()
#         if user:
#             send_password_reset_email(user) # You'll need to implement this function
#         flash('Şifre sıfırlama talimatları e-posta adresinize gönderildi.', 'info')
#         return redirect(url_for('auth.login'))
#     return render_template('request_reset_password.html', title='Şifre Sıfırlama İsteği', form=form)

# @auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
# def reset_password(token):
#     if current_user.is_authenticated:
#         return redirect(url_for('main.index'))
#     user = User.verify_reset_password_token(token) # You'll need to implement this method in User model
#     if not user:
#         flash('Geçersiz veya süresi dolmuş bir token.', 'warning')
#         return redirect(url_for('auth.reset_password_request'))
#     form = ResetPasswordForm()
#     if form.validate_on_submit():
#         user.set_password(form.password.data)
#         db.session.commit()
#         flash('Şifreniz başarıyla güncellendi.', 'success')
#         return redirect(url_for('auth.login'))
#     return render_template('reset_password.html', title='Şifreyi Sıfırla', form=form)

# Helper to create a default admin user (optional, for development)
# def create_admin_user(app_instance):
#     with app_instance.app_context():
#         admin_email = "admin@example.com"
#         if not User.query.filter_by(email=admin_email).first():
#             admin = User(full_name="Admin User", email=admin_email)
#             admin.set_password("adminpassword") # Change this!
#             db.session.add(admin)
#             db.session.commit()
#             print(f"Admin user {admin_email} created.")
