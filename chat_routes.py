import uuid
import datetime # Moved import to the top
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_required
from models import db, PDFDocument, ChatMessage, User, ChatSession # Added ChatSession
from forms import ChatMessageForm
from ai import ask_question_on_pdf, generate_chat_title_with_groq # Added Groq title generation

chat_bp = Blueprint('chat', __name__, url_prefix='/chat', template_folder='templates')

@chat_bp.before_request
@login_required # Ensures all routes in this blueprint require login
def require_login():
    pass

@chat_bp.route('/pdf/<int:pdf_id>', methods=['GET', 'POST'])
def chat_with_pdf(pdf_id):
    pdf = PDFDocument.query.filter_by(id=pdf_id, user_id=current_user.id, is_deleted=False).first_or_404()
    if not pdf.processed: # This check remains valid for non-deleted, but unprocessed PDFs
        flash(f"'{pdf.original_filename}' henüz işlenmedi. Lütfen daha sonra tekrar deneyin.", "warning")
        return redirect(url_for('dashboard.index'))

    form = ChatMessageForm()
    
    # session_uuid is the unique identifier for the chat session instance
    session_uuid = request.args.get('session_uuid')
    chat_session = None

    if session_uuid:
        chat_session = ChatSession.query.filter_by(
            session_uuid=session_uuid,
            user_id=current_user.id,
            pdf_document_id=pdf.id,
            is_deleted=False
        ).first()
    
    if not chat_session and not session_uuid and request.method == 'GET':
        # If no session_uuid is provided on GET, try to find the latest one or create a new one
        latest_session = ChatSession.query.filter_by(
            user_id=current_user.id,
            pdf_document_id=pdf.id,
            is_deleted=False
        ).order_by(ChatSession.updated_at.desc()).first()
        if latest_session:
            return redirect(url_for('chat.chat_with_pdf', pdf_id=pdf.id, session_uuid=latest_session.session_uuid))
        else:
            # No existing sessions, generate a new UUID for a potential new session
            # This new session will be created upon the first POST message
            new_session_uuid = str(uuid.uuid4())
            return redirect(url_for('chat.chat_with_pdf', pdf_id=pdf.id, session_uuid=new_session_uuid))


    if form.validate_on_submit() and request.method == 'POST':
        user_message_content = form.message.data
        
        if not session_uuid: # Should not happen if redirected correctly
            flash("Sohbet oturumu bulunamadı.", "danger")
            return redirect(url_for('dashboard.index'))

        # Find or create ChatSession
        if not chat_session:
            # This is the first message for this session_uuid
            session_title = generate_chat_title_with_groq(user_message_content)
            chat_session = ChatSession(
                session_uuid=session_uuid,
                user_id=current_user.id,
                pdf_document_id=pdf.id,
                title=session_title
            )
            db.session.add(chat_session)
            # We need to commit here to get chat_session.id for ChatMessage
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                flash(f"Sohbet oturumu oluşturulurken hata: {e}", "danger")
                return redirect(url_for('chat.chat_with_pdf', pdf_id=pdf.id, session_uuid=session_uuid))
        
        # Save user's message
        user_chat_message = ChatMessage(
            chat_session_id=chat_session.id,
            user_id=current_user.id,
            pdf_document_id=pdf.id, # Denormalized for easier direct queries if needed
            sender_type='user',
            message_content=user_message_content
        )
        db.session.add(user_chat_message)
        
        # Prepare chat history for the chain
        # Fetch previous messages for this session to pass to the chain
        previous_messages = ChatMessage.query.filter_by(
            chat_session_id=chat_session.id,
            is_deleted=False
        ).order_by(ChatMessage.timestamp.asc()).all()

        chat_history_for_chain = []
        # Group messages by user and AI to form (user_q, ai_a) tuples
        # This assumes user messages are always followed by AI messages.
        # A more robust way might be needed if this assumption doesn't hold.
        temp_user_msg = None
        for msg in previous_messages:
            if msg.sender_type == 'user':
                temp_user_msg = msg.message_content
            elif msg.sender_type == 'ai' and temp_user_msg:
                chat_history_for_chain.append((temp_user_msg, msg.message_content))
                temp_user_msg = None # Reset for the next pair

        # Call the updated ask_question_on_pdf function
        ai_response_content, _ = ask_question_on_pdf(
            current_user.id, 
            pdf.id, 
            user_message_content,
            chat_history=chat_history_for_chain # Pass the formatted history
        )
        
        ai_chat_message = ChatMessage(
            chat_session_id=chat_session.id,
            user_id=current_user.id, # Or a system user ID
            pdf_document_id=pdf.id,
            sender_type='ai',
            message_content=ai_response_content
        )
        db.session.add(ai_chat_message)
        
        # Update session's updated_at timestamp
        chat_session.updated_at = datetime.datetime.utcnow()
        db.session.commit()
        
        return redirect(url_for('chat.chat_with_pdf', pdf_id=pdf.id, session_uuid=chat_session.session_uuid))

    chat_history = []
    if chat_session:
        chat_history = ChatMessage.query.filter_by(
            chat_session_id=chat_session.id,
            is_deleted=False
        ).order_by(ChatMessage.timestamp.asc()).all()

    all_chat_sessions = ChatSession.query.filter_by(
        user_id=current_user.id,
        pdf_document_id=pdf.id,
        is_deleted=False
    ).order_by(ChatSession.updated_at.desc()).all()

    return render_template('chat_interface.html',
                           title=f"Sohbet: {pdf.original_filename}",
                           pdf=pdf,
                           form=form,
                           chat_history=chat_history,
                           current_chat_session=chat_session, # Pass the whole session object
                           all_chat_sessions=all_chat_sessions)


@chat_bp.route('/pdf/<int:pdf_id>/history', methods=['GET'])
@login_required
def get_chat_history_api(pdf_id):
    """API endpoint to fetch chat history for a specific session_uuid."""
    pdf = PDFDocument.query.filter_by(id=pdf_id, user_id=current_user.id, is_deleted=False).first_or_404()
    session_uuid = request.args.get('session_uuid')
    if not session_uuid:
        return jsonify({"error": "Session UUID is required"}), 400

    chat_session = ChatSession.query.filter_by(session_uuid=session_uuid, user_id=current_user.id, pdf_document_id=pdf.id, is_deleted=False).first()
    if not chat_session:
        return jsonify({"error": "Chat session not found"}), 404
        
    chat_history = ChatMessage.query.filter_by(
        chat_session_id=chat_session.id,
        is_deleted=False 
    ).order_by(ChatMessage.timestamp.asc()).all()

    history_data = [{
        "sender_type": msg.sender_type,
        "message_content": msg.message_content,
        "timestamp": msg.timestamp.isoformat()
    } for msg in chat_history]
    
    return jsonify(history_data)

# Route to start a new chat session (clears old one or generates new ID)
@chat_bp.route('/pdf/<int:pdf_id>/new_session')
@login_required
def new_chat_session(pdf_id):
    pdf = PDFDocument.query.filter_by(id=pdf_id, user_id=current_user.id, is_deleted=False).first_or_404()
    new_session_uuid = str(uuid.uuid4())
    # The actual ChatSession record will be created on the first message of this new_session_uuid
    flash("Yeni bir sohbet oturumu başlatıldı. İlk mesajınızla birlikte kaydedilecektir.", "info")
    return redirect(url_for('chat.chat_with_pdf', pdf_id=pdf.id, session_uuid=new_session_uuid))
