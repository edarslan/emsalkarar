import os
import datetime # Added datetime import
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from langchain_community.vectorstores import Chroma # Added Chroma import
from models import db, PDFDocument, User
from forms import PDFUploadForm
from ai import process_and_store_pdf, get_pdf_hash # AI logic for processing

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard', template_folder='templates')

@dashboard_bp.before_request
@login_required # Ensures all routes in this blueprint require login
def require_login():
    pass

@dashboard_bp.route('/')
@dashboard_bp.route('/index')
def index():
    user_pdfs = PDFDocument.query.filter_by(user_id=current_user.id, is_deleted=False).order_by(PDFDocument.upload_date.desc()).all()
    return render_template('dashboard.html', title='Kullanıcı Paneli', user_pdfs=user_pdfs)

@dashboard_bp.route('/upload_pdf', methods=['GET', 'POST'])
def upload_pdf():
    form = PDFUploadForm()
    if form.validate_on_submit():
        pdf_file = form.pdf_file.data
        original_filename = secure_filename(pdf_file.filename)
        
        # Calculate file hash to check for duplicates for this user
        file_hash = get_pdf_hash(pdf_file.stream) # Pass the file stream

        # Check for existing, non-deleted PDF
        existing_pdf = PDFDocument.query.filter_by(user_id=current_user.id, file_hash=file_hash, is_deleted=False).first()
        if existing_pdf:
            flash(f"'{original_filename}' adlı dosyayı daha önce zaten yüklediniz.", 'warning')
            return redirect(url_for('dashboard.index'))
        
        # If a soft-deleted record exists, we might allow re-upload or restore.
        # For now, let's assume a new upload creates a new record or updates the existing soft-deleted one.
        # To keep it simple, we'll just create a new one if no active one exists.

        # Ensure user-specific upload folder exists
        user_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(current_user.id))
        if not os.path.exists(user_upload_folder):
            os.makedirs(user_upload_folder)
        
        # Save the file with a unique name (e.g., using hash or a UUID) to avoid conflicts
        # For simplicity, using original_filename prefixed with hash for now, but a UUID is better for true uniqueness
        # filename_on_server = f"{file_hash[:10]}_{original_filename}" # Example
        # A safer approach for filename_on_server:
        _, f_ext = os.path.splitext(original_filename)
        filename_on_server = f"{file_hash}{f_ext}" # Use the full hash as filename + extension

        filepath = os.path.join(user_upload_folder, filename_on_server)
        
        try:
            pdf_file.save(filepath)

            # Create PDFDocument record
            new_pdf = PDFDocument(
                user_id=current_user.id,
                filename=filename_on_server, # Name on the server
                original_filename=original_filename, # User's original name
                file_hash=file_hash,
                filepath=filepath,
                processed=False # Will be set to True after AI processing
            )
            db.session.add(new_pdf)
            db.session.commit()
            
            # Asynchronously process the PDF (e.g., using Celery or a background thread)
            # For now, processing synchronously for simplicity.
            # In a production app, this should be a background task.
            # Make sure Flask app context is available if process_and_store_pdf uses it implicitly
            # For synchronous processing, ensure the app context is pushed if needed by extensions
            # with current_app.app_context():
            success, message = process_and_store_pdf(filepath, current_user.id, original_filename, file_hash)
            
            if success:
                flash(f"'{original_filename}' başarıyla yüklendi ve işlenmeye alındı. {message}", 'success')
            else:
                # If processing fails, we might want to remove the file and DB record, or mark it as failed
                flash(f"'{original_filename}' yüklendi ancak işlenirken bir sorun oluştu: {message}", 'danger')
                # Consider cleanup: os.remove(filepath), db.session.delete(new_pdf), db.session.commit()
                
            return redirect(url_for('dashboard.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Dosya yüklenirken bir hata oluştu: {e}", 'danger')
            if os.path.exists(filepath): # Clean up saved file if error during DB commit
                os.remove(filepath)
            return redirect(url_for('dashboard.upload_pdf'))
            
    return render_template('upload_pdf.html', title='PDF Yükle', form=form)

@dashboard_bp.route('/delete_pdf/<int:pdf_id>', methods=['POST'])
@login_required
def delete_pdf(pdf_id):
    pdf_to_delete = PDFDocument.query.filter_by(id=pdf_id, user_id=current_user.id, is_deleted=False).first_or_404()
    # if pdf_to_delete.user_id != current_user.id: # Already checked by query filter
    #     flash('Bu işlemi yapmaya yetkiniz yok.', 'danger')
    #     return redirect(url_for('dashboard.index'))
    
    try:
        # Hard delete from ChromaDB (Item 5)
        collection_name = pdf_to_delete.vector_db_collection_name
        if collection_name and pdf_to_delete.processed: # Only if processed and has a collection
            try:
                # Need to import Chroma and embeddings from ai.py or pass them
                from ai import embeddings as ai_embeddings # Assuming embeddings is accessible
                if ai_embeddings: # Ensure embeddings were initialized
                    chroma_client = Chroma(
                        persist_directory=current_app.config['CHROMA_DB_PATH'],
                        embedding_function=ai_embeddings
                    )
                    # Check if collection exists before trying to delete
                    # This part of Chroma's API can be tricky; often get_collection then delete_collection
                    # For simplicity, we'll try to delete. If it fails, log it.
                    # A more robust way is to list collections and check.
                    try:
                        chroma_client.delete_collection(name=collection_name)
                        print(f"ChromaDB collection '{collection_name}' deleted successfully.")
                    except Exception as chroma_exc: # Catch specific ChromaDB exceptions if known
                        print(f"Could not delete ChromaDB collection '{collection_name}': {chroma_exc}. It might not exist or an error occurred.")
                        # flash(f"Vektör veritabanı koleksiyonu '{collection_name}' silinirken hata oluştu veya bulunamadı.", "warning")

                else:
                    print("Embeddings model not available for ChromaDB deletion.")
                    # flash("Embeddings modeli yüklenemediği için vektör veritabanı silinemedi.", "warning")

            except ImportError:
                 print("Could not import 'embeddings' from 'ai' module for ChromaDB deletion.")
            except Exception as e:
                print(f"Error during ChromaDB collection deletion for '{collection_name}': {e}")
                flash(f"Vektör veritabanından '{collection_name}' silinirken bir hata oluştu: {e}", "warning")

        # Hard delete the actual file (Item 5)
        if os.path.exists(pdf_to_delete.filepath):
            os.remove(pdf_to_delete.filepath)
            print(f"File '{pdf_to_delete.filepath}' deleted from server.")
            
        # Soft delete the metadata record (Item 6)
        pdf_to_delete.is_deleted = True
        pdf_to_delete.deleted_at = datetime.datetime.utcnow()
        # Optionally clear some fields if they are no longer relevant or to save space,
        # but filepath might be useful for audit. vector_db_collection_name is good to keep for audit too.
        # pdf_to_delete.filepath = None # Or some indicator
        # pdf_to_delete.processed = False # If it's considered no longer processed
        
        db.session.commit()
        flash(f"'{pdf_to_delete.original_filename}' başarıyla silindi.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Dosya silinirken bir hata oluştu: {e}", 'danger')
        
    return redirect(url_for('dashboard.index'))

# Placeholder for viewing a specific PDF's details or chat interface
@dashboard_bp.route('/pdf/<int:pdf_id>')
@login_required
def view_pdf(pdf_id):
    pdf = PDFDocument.query.filter_by(id=pdf_id, user_id=current_user.id, is_deleted=False).first_or_404()
    # This route will eventually lead to the chat interface for this PDF
    # For now, it could show PDF details or a placeholder
    # return render_template('view_pdf_details.html', pdf=pdf)
    return redirect(url_for('chat.chat_with_pdf', pdf_id=pdf.id))
