from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Ifade, User
from ai import generate_ifade_with_ai
import datetime
import json # For handling JSON data if needed directly

ifade_bp = Blueprint('ifade', __name__, url_prefix='/ifade')

IFADE_TYPES = {
    'genel_ifade': {'name': 'Genel İfade Oluştur', 'icon': 'fas fa-file-alt', 'description': 'Genel bir ifade oluşturabilirsiniz.'},
    'musteki_ifadesi': {'name': 'Müşteki İfadesi Hazırlama', 'icon': 'fas fa-gavel', 'description': 'Şikayetçi olduğunuz bir olayla ilgili müşteki ifadesi hazırlayın.'},
    'magdur_ifadesi': {'name': 'Mağdur İfadesi Hazırlama', 'icon': 'fas fa-user-injured', 'description': 'Mağduru olduğunuz bir suçla ilgili mağdur ifadesi hazırlayın.'},
    'tanik_ifadesi': {'name': 'Tanık İfadesi Hazırlama', 'icon': 'fas fa-eye', 'description': 'Tanıklık edeceğiniz bir olayla ilgili tanık ifadesi hazırlayın.'},
    'supheli_ifadesi': {'name': 'Şüpheli İfadesi Hazırlama', 'icon': 'fas fa-user-secret', 'description': 'Hakkınızdaki bir iddia ile ilgili şüpheli sıfatıyla ifade hazırlayın.'},
}

@ifade_bp.route('/')
@login_required
def ifade_hub():
    """
    Displays the hub page for selecting a type of statement to create.
    """
    user_ifadeler = Ifade.query.filter_by(user_id=current_user.id, is_deleted=False).order_by(Ifade.created_at.desc()).all()
    return render_template('ifade/ifade_hub.html', title="İfade Hazırlama Merkezi", ifade_types=IFADE_TYPES, user_ifadeler=user_ifadeler)

@ifade_bp.route('/olustur/<ifade_type_key>', methods=['GET', 'POST'])
@login_required
def create_ifade(ifade_type_key):
    """
    Handles the creation of a new statement.
    GET: Displays the form for the statement.
    POST: Processes the form, generates content with AI, and saves the statement.
    """
    if ifade_type_key not in IFADE_TYPES:
        flash('Geçersiz ifade türü seçildi.', 'danger')
        return redirect(url_for('ifade.ifade_hub'))

    ifade_type_details = IFADE_TYPES[ifade_type_key]
    page_title = f"{ifade_type_details['name']}"

    if request.method == 'POST':
        form_data = request.form.to_dict()
        
        # Basic validation (can be expanded with Flask-WTF or more checks)
        olay_ozeti = form_data.get('olay_ozeti')
        olay_yeri = form_data.get('olay_yeri')
        olay_tarihi_str = form_data.get('olay_tarihi') # Assuming 'YYYY-MM-DD'

        if not all([olay_ozeti, olay_yeri, olay_tarihi_str]):
            flash('Lütfen tüm zorunlu alanları doldurun (* ile işaretli).', 'warning')
            return render_template('ifade/ifade_create.html', title=page_title, ifade_type_key=ifade_type_key, ifade_type_details=ifade_type_details, form_data=form_data, current_datetime=datetime.datetime.now())

        try:
            # Convert date string to datetime object if needed, or pass as string
            # For simplicity, we'll pass it as a string to AI and store as string in JSON
            pass
        except ValueError:
            flash('Geçersiz tarih formatı. Lütfen GG.AA.YYYY formatında girin.', 'warning')
            return render_template('ifade/ifade_create.html', title=page_title, ifade_type_key=ifade_type_key, ifade_type_details=ifade_type_details, form_data=form_data, current_datetime=datetime.datetime.now())

        custom_prompt = form_data.get('custom_prompt', '') # Optional custom prompt

        # Prepare inputs for AI
        ai_input_data = {
            'olay_ozeti': olay_ozeti,
            'tanik_bilgisi': form_data.get('tanik_bilgisi', ''),
            'olay_yeri': olay_yeri,
            'olay_tarihi': olay_tarihi_str,
            # Add any other common or type-specific fields here
        }
        
        # Add type-specific fields if any, for example:
        if ifade_type_key == 'musteki_ifadesi':
            ai_input_data['sikayet_edilen_kisi'] = form_data.get('sikayet_edilen_kisi', '')
        elif ifade_type_key == 'supheli_ifadesi':
            ai_input_data['itham_edilen_suc'] = form_data.get('itham_edilen_suc', '')


        generated_html, generated_text = generate_ifade_with_ai(
            ifade_type_name=ifade_type_details['name'],
            form_inputs_dict=ai_input_data,
            custom_prompt_text=custom_prompt
        )

        if "Yapay zeka modeli başlatılamadığı için" in generated_text or "bir hata meydana geldi" in generated_text:
            flash(f'İfade oluşturulurken bir hata oluştu: {generated_text}', 'danger')
        else:
            flash('İfade başarıyla oluşturuldu!', 'success')
        
        # Save the new ifade to the database
        new_ifade = Ifade(
            user_id=current_user.id,
            ifade_type=ifade_type_key,
            title=form_data.get('ifade_basligi') or f"{ifade_type_details['name']} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            input_data=ai_input_data, # Store the data sent to AI
            generated_content_html=generated_html,
            generated_content_text=generated_text,
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        db.session.add(new_ifade)
        db.session.commit()
        
        # Instead of redirecting, render the same page with the generated content
        # This allows the user to see, edit (if editor is integrated), and then explicitly save or download
        return render_template('ifade/ifade_create.html', 
                               title=page_title, 
                               ifade_type_key=ifade_type_key, 
                               ifade_type_details=ifade_type_details, 
                               form_data=form_data, # Keep form data for display/editing
                               generated_html_content=generated_html,
                               ifade_id=new_ifade.id,
                               current_datetime=datetime.datetime.now()) # Pass ifade_id for potential further actions

    # GET request: show the form
    return render_template('ifade/ifade_create.html', title=page_title, ifade_type_key=ifade_type_key, ifade_type_details=ifade_type_details, form_data={}, current_datetime=datetime.datetime.now())


@ifade_bp.route('/goruntule/<int:ifade_id>')
@login_required
def view_ifade(ifade_id):
    """
    Displays a previously created statement.
    """
    ifade = Ifade.query.get_or_404(ifade_id)
    if ifade.user_id != current_user.id:
        flash('Bu ifadeyi görüntüleme yetkiniz yok.', 'danger')
        return redirect(url_for('ifade.ifade_hub'))
    
    ifade_type_name = IFADE_TYPES.get(ifade.ifade_type, {}).get('name', ifade.ifade_type.replace('_', ' ').title())
    page_title = ifade.title or f"{ifade_type_name} Görüntüle"

    return render_template('ifade/view_ifade.html', title=page_title, ifade=ifade, ifade_type_name=ifade_type_name)

@ifade_bp.route('/guncelle/<int:ifade_id>', methods=['POST'])
@login_required
def update_ifade_content(ifade_id):
    """
    Updates the content of an existing ifade (e.g., after editing in a rich text editor).
    This is an example endpoint; actual implementation might vary based on editor.
    """
    ifade = Ifade.query.filter_by(id=ifade_id, user_id=current_user.id).first_or_404()
    
    data = request.get_json()
    new_html_content = data.get('html_content')

    if new_html_content is None:
        return jsonify({'status': 'error', 'message': 'İçerik bulunamadı.'}), 400

    # Potentially generate new text content from HTML if needed, or store as is
    # from ai import html_to_text # Ensure html_to_text is accessible
    # new_text_content = html_to_text(new_html_content)

    ifade.generated_content_html = new_html_content
    # ifade.generated_content_text = new_text_content # If you re-generate text
    ifade.updated_at = datetime.datetime.utcnow()
    
    try:
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'İfade başarıyla güncellendi.'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating ifade {ifade_id}: {e}")
        return jsonify({'status': 'error', 'message': f'Güncelleme sırasında bir hata oluştu: {str(e)}'}), 500


@ifade_bp.route('/sil/<int:ifade_id>', methods=['POST']) # Should be POST for deletion
@login_required
def delete_ifade(ifade_id):
    """
    Deletes (soft delete) a statement.
    """
    ifade_to_delete = Ifade.query.filter_by(id=ifade_id, user_id=current_user.id).first_or_404()
    
    ifade_to_delete.is_deleted = True
    ifade_to_delete.deleted_at = datetime.datetime.utcnow()
    db.session.commit()
    
    flash(f"'{ifade_to_delete.title or 'İsimsiz İfade'}' başarıyla silindi.", "success")
    return redirect(url_for('ifade.ifade_hub'))

# Add other routes as needed, e.g., for editing existing statements, listing all, etc.
