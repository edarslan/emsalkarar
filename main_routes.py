from flask import Blueprint, render_template, request, flash, redirect, url_for
import datetime

main_bp = Blueprint('main', __name__, template_folder='templates')

@main_bp.context_processor
def inject_now():
    return {'now': datetime.datetime.utcnow()}

@main_bp.route('/')
@main_bp.route('/index')
def index():
    return render_template('index.html', title='Ana Sayfa')

@main_bp.route('/about')
def about():
    return render_template('about.html', title='Hakkımızda')

@main_bp.route('/cases') # This might be expanded or moved if case details become complex
def cases():
    # Add logic to fetch cases if needed, or this could be a static page
    # For now, it refers to the existing template.
    # If dynamic case listing is needed, this will interact with models.
    query = request.args.get('query') # Example: for search functionality
    # Dummy cases data for now if you want to pass something to the template
    # sample_cases = [
    #     {'title': 'Örnek Dava 1', 'summary': 'Bu bir örnek dava özetidir.'},
    #     {'title': 'Örnek Dava 2', 'summary': 'Bu başka bir örnek dava özetidir.'}
    # ]
    # return render_template('cases.html', title='Emsal Kararlar', cases=sample_cases, query=query)
    return render_template('cases.html', title='Emsal Kararlar', query=query)


@main_bp.route('/faq')
def faq():
    return render_template('faq.html', title='S.S.S.')

@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # Process contact form data (e.g., send email, save to DB)
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        
        # Basic validation (can be enhanced with WTForms if this form becomes complex)
        if not name or not email or not subject or not message:
            flash('Lütfen tüm alanları doldurun.', 'danger')
            return render_template('contact.html', title='İletişim', form_data=request.form)

        # Placeholder for sending email or saving message
        print(f"Contact Form Submission: Name: {name}, Email: {email}, Subject: {subject}, Message: {message}")
        
        flash('Mesajınız başarıyla gönderildi! En kısa sürede sizinle iletişime geçeceğiz.', 'success')
        return redirect(url_for('main.contact')) # Redirect to clear the form
        
    return render_template('contact.html', title='İletişim')
