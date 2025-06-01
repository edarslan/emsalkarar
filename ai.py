import os
import hashlib
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA, ConversationalRetrievalChain
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from groq import Groq
from config import Config
from models import db, PDFDocument
import re # For basic HTML to text conversion

# Initialize OpenAI embeddings
try:
    embeddings = OpenAIEmbeddings(openai_api_key=Config.OPENAI_API_KEY, model="text-embedding-3-small")
except Exception as e:
    print(f"Error initializing OpenAIEmbeddings: {e}")
    embeddings = None

# Initialize ChatOpenAI model
try:
    llm = ChatOpenAI(openai_api_key=Config.OPENAI_API_KEY, model_name="gpt-4.1-nano", temperature=0.7)
except Exception as e:
    print(f"Error initializing ChatOpenAI: {e}")
    llm = None

def get_pdf_hash(file_stream):
    """Calculates SHA256 hash of a file stream."""
    sha256_hash = hashlib.sha256()
    file_stream.seek(0)
    for byte_block in iter(lambda: file_stream.read(4096), b""):
        sha256_hash.update(byte_block)
    file_stream.seek(0)
    return sha256_hash.hexdigest()

def process_and_store_pdf(pdf_file_path, user_id, original_filename, file_hash):
    """
    Processes a PDF file, extracts text, splits it, creates embeddings,
    and stores them in ChromaDB. Updates the PDFDocument record.
    """
    if not embeddings:
        print("Embeddings model not initialized. Cannot process PDF.")
        return False, "Embeddings model not initialized."

    try:
        loader = PyPDFLoader(pdf_file_path)
        raw_documents = loader.load()

        if not raw_documents:
            print(f"No documents could be loaded from {original_filename}.")
            return False, "PDF'den belge yüklenemedi."

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=400)
        all_split_texts = []
        page_block_size = 100

        print(f"Processing PDF '{original_filename}' in blocks of {page_block_size} pages.")
        for i in range(0, len(raw_documents), page_block_size):
            page_block = raw_documents[i:i + page_block_size]
            texts_from_block = text_splitter.split_documents(page_block)
            all_split_texts.extend(texts_from_block)

        if not all_split_texts:
            print(f"No text could be extracted and split from {original_filename} after processing all blocks.")
            return False, "PDF'den metin çıkarılamadı (blok işleme sonrası)."

        pdf_doc_record = PDFDocument.query.filter_by(user_id=user_id, file_hash=file_hash).first()
        if not pdf_doc_record:
            return False, "İlgili PDF kaydı bulunamadı."

        collection_name = f"user_{user_id}_pdf_{pdf_doc_record.id}"

        if not os.path.exists(Config.CHROMA_DB_PATH):
            os.makedirs(Config.CHROMA_DB_PATH)

        vector_store = Chroma.from_documents(
            documents=all_split_texts,
            embedding=embeddings,
            persist_directory=Config.CHROMA_DB_PATH,
            collection_name=collection_name
        )
        vector_store.persist()

        pdf_doc_record.processed = True
        pdf_doc_record.vector_db_collection_name = collection_name
        db.session.commit()

        return True, f"PDF '{original_filename}' başarıyla işlendi ve vektör veritabanına kaydedildi."
    except Exception as e:
        db.session.rollback()
        print(f"Error processing PDF {original_filename}: {e}")
        return False, f"PDF işlenirken bir hata oluştu: {e}"

def get_qa_chain(user_id, pdf_document_id):
    if not embeddings or not llm:
        return None
    pdf_doc = PDFDocument.query.filter_by(id=pdf_document_id, user_id=user_id).first()
    if not pdf_doc or not pdf_doc.processed or not pdf_doc.vector_db_collection_name:
        return None
    try:
        vector_store = Chroma(
            persist_directory=Config.CHROMA_DB_PATH,
            embedding_function=embeddings,
            collection_name=pdf_doc.vector_db_collection_name
        )
        retriever = vector_store.as_retriever(search_kwargs={"k": 3})
        from langchain.prompts import PromptTemplate
        prompt_template = """Aşağıdaki bağlamı kullanarak son kullanıcı sorusuna cevap ver. Eğer cevabı bilmiyorsan, bilmediğini söyle, cevap uydurmaya çalışma. Cevabını mümkün olduğunca kısa ve öz tut.

                **Bağlam**:
                {context}

                **Soru**: {question}

                Yardımcı Cevap:"""
        QA_PROMPT = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
        qa_chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=retriever,
            return_source_documents=True,
            combine_docs_chain_kwargs={"prompt": QA_PROMPT},
            verbose=False
        )
        return qa_chain
    except Exception as e:
        print(f"Error creating QA chain for PDF {pdf_document_id}: {e}")
        return None

def ask_question_on_pdf(user_id, pdf_document_id, question, chat_history=None):
    if chat_history is None: chat_history = []
    qa_chain = get_qa_chain(user_id, pdf_document_id)
    if not qa_chain:
        return "Üzgünüm, bu belge için soru cevaplama sistemi şu anda kullanılamıyor.", chat_history
    try:
        result = qa_chain.invoke({"question": question, "chat_history": chat_history})
        answer = result.get("answer", "Cevap alınırken bir sorun oluştu.")
        updated_chat_history = chat_history + [(question, answer)]
        return answer, updated_chat_history
    except Exception as e:
        print(f"Error during Conversational QA chain invocation: {e}")
        return f"Soruya cevap verilirken bir hata oluştu: {e}", chat_history

def generate_chat_title_with_groq(first_message_content):
    if not Config.GROQ_API_KEY:
        return "Sohbet Başlığı"
    try:
        client = Groq(api_key=Config.GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates a very short, concise title (3-7 words) for a given user query or statement. The title should capture the main topic of the query. Respond only with the title itself, nothing else."},
                {"role": "user", "content": f"Generate a short title for this query: \"{first_message_content}\""}
            ],
            model="llama3-8b-8192", temperature=0.3, max_tokens=20, top_p=1, stream=False
        )
        title = chat_completion.choices[0].message.content.strip()
        if title.startswith('"') and title.endswith('"'): title = title[1:-1]
        if title.startswith("'") and title.endswith("'"): title = title[1:-1]
        return title if title else "Sohbet Başlığı"
    except Exception as e:
        print(f"Error generating chat title with Groq: {e}")
        return "Sohbet Başlığı"

def html_to_text(html_content):
    """Basic HTML to text conversion."""
    if not html_content:
        return ""
    text = html_content
    text = re.sub(r'<style[^>]*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE) # Remove style blocks
    text = re.sub(r'<script[^>]*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE) # Remove script blocks
    text = re.sub(r'<h1>(.*?)</h1>', r'\1\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<h2>(.*?)</h2>', r'\1\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<h3>(.*?)</h3>', r'\1\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>\s*<p>', '\n\n', text, flags=re.IGNORECASE) # Handle paragraph spacing
    text = re.sub(r'<p>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li>', '\n- ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text) # Remove all other tags, replace with space
    text = re.sub(r'\n\s*\n', '\n\n', text) # Consolidate multiple newlines
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&', '&')
    text = text.replace('<', '<')
    text = text.replace('>', '>')
    text = text.replace('"', '"')
    text = text.replace('&#39;', "'")
    return text.strip()

def generate_contract_with_ai(contract_type_name, form_inputs_dict, custom_prompt_text):
    """
    Generates contract content using an LLM based on type, inputs, and custom prompts.
    Returns HTML and plain text versions.
    """
    if not llm:
        print("LLM not initialized. Cannot generate contract.")
        error_html = "<p>Yapay zeka modeli başlatılamadığı için sözleşme oluşturulamadı. Lütfen sistem yöneticisine başvurun.</p>"
        return error_html, "Yapay zeka modeli başlatılamadığı için sözleşme oluşturulamadı."

    print(f"AI: Generating contract for '{contract_type_name}'")
    print(f"Form Inputs: {form_inputs_dict}")
    if custom_prompt_text:
        print(f"Custom Prompt: {custom_prompt_text}")

    system_prompt = (
        "Sen Türk hukukuna göre sözleşme taslakları hazırlayan uzman bir yapay zeka asistanısın. "
        "Görevin, sağlanan bilgilere dayanarak kapsamlı ve yasalara uygun bir sözleşme metni oluşturmaktır. "
        "Sözleşme metnini HTML formatında, iyi yapılandırılmış ve okunabilir bir şekilde sunmalısın. "
        "HTML içeriği başlıklar (örn: <h1>, <h2>), paragraflar (<p>), listeler (<ul>, <ol>, <li>) ve "
        "metin biçimlendirmesi (<strong>, <em>) gibi temel HTML etiketlerini kullanmalıdır. "
        "Sözleşmenin sonuna, bunun yapay zeka tarafından oluşturulmuş bir taslak olduğu ve bir hukuk uzmanı "
        "tarafından incelenmesi gerektiğine dair bir feragatname eklemeyi unutma."
    )

    formatted_inputs = "\n".join([f"- {key.replace('_', ' ').title()}: {value}" for key, value in form_inputs_dict.items()])

    user_prompt_content = (
        f"Lütfen aşağıdaki bilgilere dayanarak bir '{contract_type_name}' sözleşmesi taslağı oluşturun:\n\n"
        f"**Sözleşme Türü:** {contract_type_name}\n\n"
        f"**Sağlanan Bilgiler:**\n{formatted_inputs}\n\n"
    )

    if custom_prompt_text:
        user_prompt_content += f"**Ek Notlar / Özel İstekler:**\n{custom_prompt_text}\n\n"

    user_prompt_content += (
        "Lütfen sözleşmeyi Türkçe olarak, HTML formatında oluşturun. "
        "Genel Türk hukuk kurallarına ve belirtilen sözleşme türü için yaygın maddelere (tarafların tam unvan ve adresleri, sözleşmenin konusu, "
        "temel hak ve yükümlülükler, bedel (varsa), süre, fesih şartları, tebligat adresleri, yetkili mahkeme ve uygulanacak hukuk gibi) uyun. "
        "Taraflar için imza alanları ekleyin. "
        "Son olarak, sözleşmenin altına şu feragatnameyi ekleyin: "
        "'İşbu sözleşme taslağı yapay zeka tarafından oluşturulmuştur ve yalnızca bir örnek teşkil eder. "
        "Hukuki geçerliliği ve özel durumunuza uygunluğu için mutlaka bir hukuk danışmanına başvurunuz. "
        "Oluşturulan metin üzerinde değişiklik yapabilir ve ihtiyaçlarınıza göre uyarlayabilirsiniz.'"
    )
    
    print(f"--- AI Prompt for Contract Generation ---")
    print(f"System: {system_prompt}")
    print(f"User: {user_prompt_content}")
    print(f"--- End AI Prompt ---")

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt_content)
        ]
        response = llm.invoke(messages)
        html_content = response.content

        # Basic check if LLM returned something that looks like HTML
        if not ("<html" in html_content.lower() or "<body" in html_content.lower() or "<p>" in html_content.lower() or "<h1>" in html_content.lower()):
            # If not, wrap it in basic HTML structure
            print("AI response doesn't look like full HTML, wrapping it.")
            wrapped_html = f"<h1>{contract_type_name}</h1>\n{html_content}"
            # Ensure the disclaimer is present
            disclaimer = ("<hr><p><em>İşbu sözleşme taslağı yapay zeka tarafından oluşturulmuştur ve yalnızca bir örnek teşkil eder. "
                          "Hukuki geçerliliği ve özel durumunuza uygunluğu için mutlaka bir hukuk danışmanına başvurunuz. "
                          "Oluşturulan metin üzerinde değişiklik yapabilir ve ihtiyaçlarınıza göre uyarlayabilirsiniz.</em></p>")
            if "hukuk danışmanına başvurunuz" not in html_content:
                 wrapped_html += f"\n{disclaimer}"
            html_content = wrapped_html


        text_content = html_to_text(html_content)

        print(f"AI Generated HTML (first 300 chars): {html_content[:300]}")
        print(f"AI Generated Text (first 300 chars): {text_content[:300]}")

        return html_content, text_content

    except Exception as e:
        print(f"Error during LLM call for contract generation: {e}")
        error_html = (f"<h1>{contract_type_name} - Hata</h1>"
                      f"<p>Sözleşme oluşturulurken bir hata meydana geldi: {str(e)}</p>"
                      "<p>Lütfen daha sonra tekrar deneyin veya sistem yöneticisine başvurun.</p>")
        error_text = (f"{contract_type_name} - Hata\n\n"
                      f"Sözleşme oluşturulurken bir hata meydana geldi: {str(e)}\n"
                      "Lütfen daha sonra tekrar deneyin veya sistem yöneticisine başvurun.")
        return error_html, error_text

def generate_dilekce_with_ai(dilekce_type_name, form_inputs_dict, custom_prompt_text=""):
    """
    Generates dilekce content using an LLM based on type, inputs, and custom prompts.
    Returns HTML and plain text versions.
    """
    if not llm:
        print("LLM not initialized. Cannot generate dilekce.")
        error_html = "<p>Yapay zeka modeli başlatılamadığı için dilekçe oluşturulamadı. Lütfen sistem yöneticisine başvurun.</p>"
        return error_html, "Yapay zeka modeli başlatılamadığı için dilekçe oluşturulamadı."

    print(f"AI: Generating dilekce for '{dilekce_type_name}'")
    print(f"Form Inputs: {form_inputs_dict}")
    if custom_prompt_text:
        print(f"Custom Prompt: {custom_prompt_text}")

    system_prompt = (
        "Sen Türk hukukuna göre dilekçe taslakları hazırlayan uzman bir yapay zeka asistanısın. "
        "Görevin, sağlanan bilgilere dayanarak kapsamlı, yasalara uygun ve resmi bir dilekçe metni oluşturmaktır. "
        "Dilekçe metnini HTML formatında, iyi yapılandırılmış ve okunabilir bir şekilde sunmalısın. "
        "HTML içeriği başlıklar (örn: <h1>, <h2>), paragraflar (<p>), listeler (<ul>, <ol>, <li>) ve "
        "metin biçimlendirmesi (<strong>, <em>) gibi temel HTML etiketlerini kullanmalıdır. "
        "Dilekçenin sonuna, bunun yapay zeka tarafından oluşturulmuş bir taslak olduğu ve bir hukuk uzmanı "
        "tarafından incelenmesi gerektiğine dair bir feragatname eklemeyi unutma."
    )

    # Convert form_inputs_dict keys to more readable versions for the prompt
    formatted_inputs_list = []
    for key, value in form_inputs_dict.items():
        # Replace underscores with spaces and capitalize words
        readable_key = ' '.join(word.capitalize() for word in key.split('_'))
        formatted_inputs_list.append(f"- {readable_key}: {value}")
    formatted_inputs = "\n".join(formatted_inputs_list)
    
    # Dilekce type name for prompt
    readable_dilekce_type_name = ' '.join(word.capitalize() for word in dilekce_type_name.split('_'))


    user_prompt_content = (
        f"Lütfen aşağıdaki bilgilere dayanarak bir '{readable_dilekce_type_name}' dilekçesi taslağı oluşturun:\n\n"
        f"**Dilekçe Türü:** {readable_dilekce_type_name}\n\n"
        f"**Sağlanan Bilgiler:**\n{formatted_inputs}\n\n"
    )

    if custom_prompt_text:
        user_prompt_content += f"**Ek Notlar / Özel İstekler:**\n{custom_prompt_text}\n\n"

    user_prompt_content += (
        "Lütfen dilekçeyi Türkçe olarak, resmi bir dille ve HTML formatında oluşturun. "
        "Genel Türk hukuk kurallarına ve belirtilen dilekçe türü için yaygın formatlara uyun. "
        "Örneğin, ilgili makam (örn: .... MAHKEMESİNE, .... SAVCILIĞINA), davacı/şikayetçi, davalı/şüpheli bilgileri, "
        "konu, açıklamalar, hukuki sebepler, sonuç ve talep gibi bölümleri içermelidir. "
        "Gerekiyorsa tarih ve imza için alan bırakın. "
        "Son olarak, dilekçenin altına şu feragatnameyi ekleyin: "
        "'İşbu dilekçe taslağı yapay zeka tarafından oluşturulmuştur ve yalnızca bir örnek teşkil eder. "
        "Hukuki geçerliliği ve özel durumunuza uygunluğu için mutlaka bir hukuk danışmanına başvurunuz. "
        "Oluşturulan metin üzerinde değişiklik yapabilir ve ihtiyaçlarınıza göre uyarlayabilirsiniz.'"
    )
    
    print(f"--- AI Prompt for Dilekce Generation ---")
    print(f"System: {system_prompt}")
    print(f"User: {user_prompt_content}")
    print(f"--- End AI Prompt ---")

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt_content)
        ]
        response = llm.invoke(messages)
        html_content = response.content

        # Basic check if LLM returned something that looks like HTML
        if not ("<html" in html_content.lower() or "<body" in html_content.lower() or "<p>" in html_content.lower() or "<h1>" in html_content.lower()):
            print("AI response doesn't look like full HTML, wrapping it.")
            wrapped_html = f"<h1>{readable_dilekce_type_name}</h1>\n{html_content}"
            disclaimer = ("<hr><p><em>İşbu dilekçe taslağı yapay zeka tarafından oluşturulmuştur ve yalnızca bir örnek teşkil eder. "
                          "Hukuki geçerliliği ve özel durumunuza uygunluğu için mutlaka bir hukuk danışmanına başvurunuz. "
                          "Oluşturulan metin üzerinde değişiklik yapabilir ve ihtiyaçlarınıza göre uyarlayabilirsiniz.</em></p>")
            if "hukuk danışmanına başvurunuz" not in html_content:
                 wrapped_html += f"\n{disclaimer}"
            html_content = wrapped_html

        text_content = html_to_text(html_content)

        print(f"AI Generated HTML (first 300 chars): {html_content[:300]}")
        print(f"AI Generated Text (first 300 chars): {text_content[:300]}")

        return html_content, text_content

    except Exception as e:
        print(f"Error during LLM call for dilekce generation: {e}")
        error_html = (f"<h1>{readable_dilekce_type_name} - Hata</h1>"
                      f"<p>Dilekçe oluşturulurken bir hata meydana geldi: {str(e)}</p>"
                      "<p>Lütfen daha sonra tekrar deneyin veya sistem yöneticisine başvurun.</p>")
        error_text = (f"{readable_dilekce_type_name} - Hata\n\n"
                      f"Dilekçe oluşturulurken bir hata meydana geldi: {str(e)}\n"
                      "Lütfen daha sonra tekrar deneyin veya sistem yöneticisine başvurun.")
        return error_html, error_text

def generate_ifade_with_ai(ifade_type_name, form_inputs_dict, custom_prompt_text=""):
    """
    Generates ifade (statement) content using an LLM based on type, inputs, and custom prompts.
    Returns HTML and plain text versions.
    """
    if not llm:
        print("LLM not initialized. Cannot generate ifade.")
        error_html = "<p>Yapay zeka modeli başlatılamadığı için ifade oluşturulamadı. Lütfen sistem yöneticisine başvurun.</p>"
        return error_html, "Yapay zeka modeli başlatılamadığı için ifade oluşturulamadı."

    print(f"AI: Generating ifade for '{ifade_type_name}'")
    print(f"Form Inputs: {form_inputs_dict}")
    if custom_prompt_text:
        print(f"Custom Prompt: {custom_prompt_text}")

    system_prompt = (
        "Sen Türk Ceza Muhakemesi Kanunu ve ilgili mevzuata göre ifade tutanakları hazırlayan uzman bir yapay zeka asistanısın. "
        "Görevin, sağlanan bilgilere dayanarak kapsamlı, yasalara uygun ve resmi bir ifade metni oluşturmaktır. "
        "İfade metnini HTML formatında, iyi yapılandırılmış ve okunabilir bir şekilde sunmalısın. "
        "HTML içeriği başlıklar (örn: <h1>, <h2>), paragraflar (<p>), ve metin biçimlendirmesi (<strong>, <em>) gibi temel HTML etiketlerini kullanmalıdır. "
        "İfade metninin sonuna, bunun yapay zeka tarafından oluşturulmuş bir taslak olduğu ve bir hukuk uzmanı "
        "tarafından incelenmesi ve resmiyet kazandırılması gerektiğine dair bir feragatname eklemeyi unutma."
    )

    # Convert form_inputs_dict keys to more readable versions for the prompt
    formatted_inputs_list = []
    for key, value in form_inputs_dict.items():
        readable_key = ' '.join(word.capitalize() for word in key.split('_'))
        formatted_inputs_list.append(f"- {readable_key}: {value}")
    formatted_inputs = "\n".join(formatted_inputs_list)
    
    # Ifade type name for prompt
    readable_ifade_type_name = ' '.join(word.capitalize() for word in ifade_type_name.split('_'))


    user_prompt_content = (
        f"Lütfen aşağıdaki bilgilere dayanarak bir '{readable_ifade_type_name}' ifade tutanağı taslağı oluşturun:\n\n"
        f"**İfade Türü:** {readable_ifade_type_name}\n\n"
        f"**Sağlanan Bilgiler (Olay Özeti, Tanık Bilgisi, Olay Yeri, Olay Tarihi vb.):**\n{formatted_inputs}\n\n"
    )

    if custom_prompt_text:
        user_prompt_content += f"**Ek Notlar / Özel İstekler:**\n{custom_prompt_text}\n\n"

    user_prompt_content += (
        "Lütfen ifade tutanağını Türkçe olarak, resmi bir dille ve HTML formatında oluşturun. "
        "Türk Ceza Muhakemesi Kanunu'ndaki ifade alma usullerine ve genel ilkelere uygun olmalıdır. "
        "İfade veren kişinin kimlik bilgileri, olayın anlatımı, sorular ve cevaplar (eğer varsa), ifadenin özgür iradeyle verildiğine dair beyan, "
        "tarih ve imza için alanlar gibi standart bölümleri içermelidir. "
        "Özellikle ifadenin türüne göre (şüpheli, mağdur, tanık vb.) dikkat edilmesi gereken yasal unsurları gözetin. "
        "Son olarak, ifadenin altına şu feragatnameyi ekleyin: "
        "'İşbu ifade taslağı yapay zeka tarafından oluşturulmuştur ve yalnızca bir örnek teşkil eder. "
        "Hukuki geçerliliği, doğruluğu ve özel durumunuza uygunluğu için mutlaka bir hukuk danışmanına başvurunuz ve resmi mercilerce usulüne uygun şekilde kayıt altına alınmasını sağlayınız. "
        "Oluşturulan metin üzerinde değişiklik yapabilir ve ihtiyaçlarınıza göre uyarlayabilirsiniz.'"
    )
    
    print(f"--- AI Prompt for Ifade Generation ---")
    print(f"System: {system_prompt}")
    print(f"User: {user_prompt_content}")
    print(f"--- End AI Prompt ---")

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt_content)
        ]
        response = llm.invoke(messages)
        html_content = response.content

        # Basic check if LLM returned something that looks like HTML
        if not ("<html" in html_content.lower() or "<body" in html_content.lower() or "<p>" in html_content.lower() or "<h1>" in html_content.lower()):
            print("AI response doesn't look like full HTML, wrapping it.")
            wrapped_html = f"<h1>{readable_ifade_type_name}</h1>\n{html_content}"
            disclaimer = ("<hr><p><em>İşbu ifade taslağı yapay zeka tarafından oluşturulmuştur ve yalnızca bir örnek teşkil eder. "
                          "Hukuki geçerliliği, doğruluğu ve özel durumunuza uygunluğu için mutlaka bir hukuk danışmanına başvurunuz ve resmi mercilerce usulüne uygun şekilde kayıt altına alınmasını sağlayınız. "
                          "Oluşturulan metin üzerinde değişiklik yapabilir ve ihtiyaçlarınıza göre uyarlayabilirsiniz.</em></p>")
            if "hukuk danışmanına başvurunuz" not in html_content and "resmi mercilerce" not in html_content:
                 wrapped_html += f"\n{disclaimer}"
            html_content = wrapped_html

        text_content = html_to_text(html_content)

        print(f"AI Generated HTML (first 300 chars): {html_content[:300]}")
        print(f"AI Generated Text (first 300 chars): {text_content[:300]}")

        return html_content, text_content

    except Exception as e:
        print(f"Error during LLM call for ifade generation: {e}")
        error_html = (f"<h1>{readable_ifade_type_name} - Hata</h1>"
                      f"<p>İfade oluşturulurken bir hata meydana geldi: {str(e)}</p>"
                      "<p>Lütfen daha sonra tekrar deneyin veya sistem yöneticisine başvurun.</p>")
        error_text = (f"{readable_ifade_type_name} - Hata\n\n"
                      f"İfade oluşturulurken bir hata meydana geldi: {str(e)}\n"
                      "Lütfen daha sonra tekrar deneyin veya sistem yöneticisine başvurun.")
        return error_html, error_text

if __name__ == '__main__':
    pass
