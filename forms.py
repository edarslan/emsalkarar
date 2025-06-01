from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from models import User # Import User model to check for existing emails

class RegistrationForm(FlaskForm):
    full_name = StringField('Ad Soyad', validators=[DataRequired(), Length(min=2, max=100, message="Ad soyad 2 ile 100 karakter arasında olmalıdır.")])
    email = StringField('E-posta Adresi', validators=[DataRequired(), Email(message="Geçerli bir e-posta adresi giriniz.")])
    password = PasswordField('Şifre', validators=[DataRequired(), Length(min=6, message="Şifre en az 6 karakter olmalıdır.")])
    confirm_password = PasswordField('Şifre Tekrar', validators=[DataRequired(), EqualTo('password', message='Şifreler eşleşmelidir.')])
    submit = SubmitField('Kayıt Ol')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Bu e-posta adresi zaten kayıtlı. Lütfen farklı bir e-posta deneyin veya giriş yapın.')

class LoginForm(FlaskForm):
    email = StringField('E-posta Adresi', validators=[DataRequired(), Email(message="Geçerli bir e-posta adresi giriniz.")])
    password = PasswordField('Şifre', validators=[DataRequired()])
    remember = BooleanField('Beni Hatırla')
    submit = SubmitField('Giriş Yap')

# Todo: Word ve Txt destekleri eklenebilir.
class PDFUploadForm(FlaskForm):
    pdf_file = FileField('PDF Dosyası Yükle', validators=[
        FileRequired(message="Lütfen bir dosya seçin."),
        FileAllowed(['pdf'], message='Sadece PDF dosyaları yüklenebilir!')
    ])
    submit = SubmitField('Yükle')

class ChatMessageForm(FlaskForm):
    message = TextAreaField('Mesajınız', validators=[DataRequired(), Length(min=1, max=2000)])
    submit = SubmitField('Gönder')

class RequestPasswordResetForm(FlaskForm):
    email = StringField('E-posta Adresi',
                        validators=[DataRequired(), Email()])
    submit = SubmitField('Şifre Sıfırlama İsteği Gönder')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is None:
            raise ValidationError('Bu e-posta adresi ile kayıtlı bir hesap bulunamadı.')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Yeni Şifre', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Yeni Şifre Tekrar',
                                     validators=[DataRequired(), EqualTo('password', message='Şifreler eşleşmelidir.')])
    submit = SubmitField('Şifreyi Güncelle')
