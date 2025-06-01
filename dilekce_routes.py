from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Dilekce 
from ai import generate_dilekce_with_ai # Import the AI function
import datetime

# The template_folder should be relative to the blueprint's location,
# or an absolute path, or relative to the app's template_folder if specified.
# For simplicity, if 'templates/dilekce' is directly under the main 'templates' folder:
dilekce_bp = Blueprint('dilekce', __name__, url_prefix='/dilekce', template_folder='templates/dilekce')

@dilekce_bp.route('/') # This will be the main page for dilekce, perhaps listing them
@login_required
def dilekce_hub():
    # This can list existing dilekceler or redirect to the creation form
    user_dilekceler = Dilekce.query.filter_by(user_id=current_user.id, is_deleted=False).order_by(Dilekce.created_at.desc()).all()
    # For now, let's make it redirect to the creation form, or you can create a separate hub page.
    # return render_template('dilekce_hub.html', title="Dilekçe Merkezi", dilekceler=user_dilekceler)
    # For now, let's assume this is the page that shows the form to select dilekce type
    return redirect(url_for('dilekce.create_dilekce_form'))


@dilekce_bp.route('/create', methods=['GET'])
@login_required
def create_dilekce_form():
    # This route will display the initial form with the dropdown to select dilekce type
    return render_template('dilekce_create.html', title="Yeni Dilekçe Oluştur")

@dilekce_bp.route('/create', methods=['POST'])
@login_required
def create_dilekce_handler():
    # This route will handle the form submission from dilekce_create.html
    dilekce_type = request.form.get('dilekce_type')
    # Extract other dynamic form fields based on dilekce_type
    # For now, we'll just get the type and prepare for AI generation
    
    if not dilekce_type:
        flash('Lütfen bir dilekçe türü seçin.', 'warning')
        return redirect(url_for('dilekce.create_dilekce_form'))

    # Placeholder for gathering all form inputs
    input_data = {key: value for key, value in request.form.items() if key not in ['csrf_token', 'dilekce_type']}
    # dilekce_type_selected is already available as 'dilekce_type' variable
    
    # Optional: Add a field for custom prompt if you plan to use it
    custom_prompt = request.form.get('custom_prompt', "") # Assuming a textarea with name="custom_prompt" might be added later

    # Call AI to generate content
    try:
        html_content, text_content = generate_dilekce_with_ai(
            dilekce_type_name=dilekce_type, 
            form_inputs_dict=input_data, 
            custom_prompt_text=custom_prompt
        )
    except Exception as e:
        flash(f"Dilekçe içeriği oluşturulurken bir hata oluştu: {str(e)}", "danger")
        return redirect(url_for('dilekce.create_dilekce_form'))

    new_dilekce = Dilekce(
        user_id=current_user.id,
        dilekce_type=dilekce_type,
        title=f"{dilekce_type.replace('_', ' ').title()} Taslağı", # Auto-generate title
        input_data=input_data, # Save all submitted form data
        generated_content_html=html_content,
        generated_content_text=text_content,
        created_at=datetime.datetime.utcnow()
    )
    db.session.add(new_dilekce)
    db.session.commit()
    
    flash(f'{dilekce_type.replace("_", " ").title()} için taslak oluşturuldu!', 'success')
    return redirect(url_for('dilekce.view_dilekce', dilekce_id=new_dilekce.id))


@dilekce_bp.route('/<int:dilekce_id>')
@login_required
def view_dilekce(dilekce_id):
    dilekce = Dilekce.query.filter_by(id=dilekce_id, user_id=current_user.id, is_deleted=False).first_or_404()
    return render_template('view_dilekce.html', title=dilekce.title if dilekce else "Dilekçe Detayı", dilekce=dilekce)


# Placeholder for fetching dynamic form fields based on dilekce_type
@dilekce_bp.route('/get-form-fields/<string:dilekce_type>')
@login_required
def get_form_fields(dilekce_type):
    # This would return HTML snippets for the form fields
    # For example, based on the images you provided:
    fields_html = ""
    if dilekce_type == "bilirkisi_raporu_itiraz":
        fields_html = """
        <div class="mb-3">
            <label for="itiraz_noktalari" class="form-label">Bilirkişi Raporundaki İtiraz Noktaları</label>
            <textarea class="form-control" id="itiraz_noktalari" name="itiraz_noktalari" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="ekler_bilirkişi" class="form-label">Ekler (Örn: İtiraza dayanak belgeler)</label>
            <textarea class="form-control" id="ekler_bilirkişi" name="ekler_bilirkişi" rows="2"></textarea>
        </div>
        """
    elif dilekce_type == "dava_dilekcesi":
        fields_html = """
        <div class="mb-3">
            <label for="dava_konusu_ozeti" class="form-label">Dava Konusu / Olay Özeti</label>
            <textarea class="form-control" id="dava_konusu_ozeti" name="dava_konusu_ozeti" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="davaci_bilgileri" class="form-label">Davacı Bilgileri (Ad, Soyad, TC, Adres)</label>
            <textarea class="form-control" id="davaci_bilgileri" name="davaci_bilgileri" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="davali_bilgileri" class="form-label">Davalı Bilgileri (Ad, Soyad/Unvan, Adres)</label>
            <textarea class="form-control" id="davali_bilgileri" name="davali_bilgileri" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="talep_ve_istekler" class="form-label">Talep (İstekleriniz / Talepleriniz)</label>
            <textarea class="form-control" id="talep_ve_istekler" name="talep_ve_istekler" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="olay_yeri_tarih" class="form-label">Olay Yeri ve Tarihi (Biliniyorsa)</label>
            <input type="text" class="form-control" id="olay_yeri_tarih" name="olay_yeri_tarih">
        </div>
        <div class="form-check mb-3">
            <input class="form-check-input" type="checkbox" value="true" id="kesif_talebi" name="kesif_talebi">
            <label class="form-check-label" for="kesif_talebi">Keşif Talebi</label>
        </div>
        <div class="form-check mb-3">
            <input class="form-check-input" type="checkbox" value="true" id="dava_degeri_belirsiz" name="dava_degeri_belirsiz">
            <label class="form-check-label" for="dava_degeri_belirsiz">Dava Değeri (Belirsiz Alacak)</label>
        </div>
         <div class="mb-3">
            <label for="ekler_dava" class="form-label">Ekler (Örn: Deliller, sözleşme, fatura)</label>
            <textarea class="form-control" id="ekler_dava" name="ekler_dava" rows="2"></textarea>
        </div>
        """
    elif dilekce_type == "tutanak":
        fields_html = """
        <div class="mb-3">
            <label for="tutanak_konusu" class="form-label">Tutanak Konusu (Örn: Toplantı, İnceleme Raporu)</label>
            <input type="text" class="form-control" id="tutanak_konusu" name="tutanak_konusu" required>
        </div>
        <div class="mb-3">
            <label for="taraflar_bilgileri" class="form-label">Tarafların Bilgileri (Örn: Katılımcılar, Gözlemciler)</label>
            <textarea class="form-control" id="taraflar_bilgileri" name="taraflar_bilgileri" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="tutanak_detaylari" class="form-label">Tutanağın Detayları (Olay, Görüşmeler, Kararlar vb.)</label>
            <textarea class="form-control" id="tutanak_detaylari" name="tutanak_detaylari" rows="4" required></textarea>
        </div>
        <div class="mb-3">
            <label for="tutanak_tarihi" class="form-label">Tutanak Tarihi</label>
            <input type="date" class="form-control" id="tutanak_tarihi" name="tutanak_tarihi" required>
        </div>
        <div class="mb-3">
            <label for="ekler_tutanak" class="form-label">Ek Belgeler (İsteğe Bağlı)</label>
            <textarea class="form-control" id="ekler_tutanak" name="ekler_tutanak" rows="2"></textarea>
        </div>
        """
    elif dilekce_type == "fesih_bildirimi":
        fields_html = """
        <div class="mb-3">
            <label for="fesih_sebebi" class="form-label">Fesih Sebebini Açıklayın</label>
            <textarea class="form-control" id="fesih_sebebi" name="fesih_sebebi" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="taraf_bilgileri_fesih" class="form-label">Taraf Bilgileri (Örn: İşveren ve Çalışan)</label>
            <textarea class="form-control" id="taraf_bilgileri_fesih" name="taraf_bilgileri_fesih" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="fesih_tarihi" class="form-label">Fesih Tarihi</label>
            <input type="date" class="form-control" id="fesih_tarihi" name="fesih_tarihi" required>
        </div>
        <div class="mb-3">
            <label for="ekler_fesih" class="form-label">Ek Belgeler (İsteğe Bağlı)</label>
            <textarea class="form-control" id="ekler_fesih" name="ekler_fesih" rows="2"></textarea>
        </div>
        """
    elif dilekce_type == "sikayet":
        fields_html = """
        <div class="mb-3">
            <label for="sikayet_eden_bilgileri" class="form-label">Şikayet Eden Bilgileri (Ad, Soyad, TC, Adres, Telefon)</label>
            <textarea class="form-control" id="sikayet_eden_bilgileri" name="sikayet_eden_bilgileri" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="sikayet_edilen_bilgileri" class="form-label">Şikayet Edilen Bilgileri (Ad, Soyad/Unvan, Adres)</label>
            <textarea class="form-control" id="sikayet_edilen_bilgileri" name="sikayet_edilen_bilgileri" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="sikayet_detayi" class="form-label">Şikayet Detayı (Olaylar, Tarihler, Yerler)</label>
            <textarea class="form-control" id="sikayet_detayi" name="sikayet_detayi" rows="4" required></textarea>
        </div>
        <div class="mb-3">
            <label for="ekler_sikayet" class="form-label">Ekler (Deliller, Belgeler)</label>
            <textarea class="form-control" id="ekler_sikayet" name="ekler_sikayet" rows="2"></textarea>
        </div>
        """
    elif dilekce_type == "itiraz_genel": # Based on the "İtiraz" screenshot with "Borçlu Bilgileri"
        fields_html = """
        <div class="mb-3">
            <label for="borclu_bilgileri" class="form-label">Borçlu Bilgileri (Ad, Soyad/Unvan, TC/VKN, Adres)</label>
            <textarea class="form-control" id="borclu_bilgileri" name="borclu_bilgileri" rows="3" required></textarea>
        </div>
        <div class="mb-3">
            <label for="itiraz_nedenleri" class="form-label">İtiraz Nedenleri</label>
            <textarea class="form-control" id="itiraz_nedenleri" name="itiraz_nedenleri" rows="4" required></textarea>
        </div>
        <div class="mb-3">
            <label for="ekler_itiraz_genel" class="form-label">Ekler (İtiraza Dayanak Belgeler)</label>
            <textarea class="form-control" id="ekler_itiraz_genel" name="ekler_itiraz_genel" rows="2"></textarea>
        </div>
        """
    else:
        fields_html = '<p class="text-warning">Bu dilekçe türü için özel alanlar henüz tanımlanmamış.</p>'
    
    return jsonify({'html': fields_html})

# Add other routes like edit, delete, export_pdf, export_word as needed
