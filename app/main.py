# import os
# from fastapi import FastAPI, File, UploadFile, Form, HTTPException
# from urllib.parse import quote_plus
# from langchain_community.chat_message_histories import SQLChatMessageHistory
# from pydantic import BaseModel
# from dotenv import load_dotenv

# # RAG Servisindən lazım olan bütün funksiyaları import edirik
# from app.rag.rag_service import (
#     process_and_index_file,
#     search_knowledge_base,
#     search_standards_base,
#     create_llm_client
# )

# load_dotenv()


# from sqlalchemy import create_engine

# DB_USER = "rag_user"
# DB_PASS = "raguser123"
# DB_HOST = "127.0.0.1"
# DB_PORT = "5432"
# DB_NAME = "rag_history_db"

# DB_URL = os.getenv("DB_URL")
# OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
# OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX")

# engine = create_engine(DB_URL)

# try:
#     connection = engine.connect()
#     print("Bağlantı uğurla quruldu!")
#     connection.close()
# except Exception as e:
#     print(f"Bağlantı qurularkən xəta baş verdi: {e}")


# print(f"DEBUG URL: {DB_URL}")

# app = FastAPI()


# def get_history_manager(session_id: str) -> SQLChatMessageHistory:
#     global DB_URL
#     return SQLChatMessageHistory(
#         session_id=session_id,
#         connection=DB_URL  # <--- Düzgün URL ötürülür
#     )

# def format_history_for_prompt(history_manager: SQLChatMessageHistory, limit: int = 3) -> str:
#     """
#     PostgreSQL bazasından son 'limit' sayda mesajı oxuyur və prompt üçün formatlayır.
#     """
#     messages = history_manager.messages[-limit:]

#     formatted_history = "--- KEÇMİŞ ÇAT MƏLUMATI ---\n"
#     if not messages:
#         return ""

#     for message in messages:
#         # Rolu və məzmunu formatla
#         formatted_history += f"[{message.type.upper()}]: {message.content}\n"

#     return formatted_history + "-------------------------\n\n"


# # --- Pydantic Modelləri ---
# class ChatRequest(BaseModel):
#     session_id: str
#     message: str


# class ChatResponse(BaseModel):
#     session_id: str
#     ai_response: str


# # --- Kök (root) yolu ---
# @app.get("/")
# async def read_root():
#     return {"message": "RAG FastAPI Service is running."}


# # --- Sənəd Yükləmə Endpointi ---
# @app.post("/upload-document")
# async def upload_document(
#         file: UploadFile = File(...),
#         session_id: str = Form(...)  # Faylı istifadəçi ilə əlaqələndirmək üçün
# ):
#     """
#     Sənədi qəbul edir, emal edir və OpenSearch vektor bazasına indeksləyir.
#     """
#     if file.content_type != "application/pdf":
#         raise HTTPException(
#             status_code=400,
#             detail="Yalnız PDF sənədləri qəbul edilir."
#         )

#     success = process_and_index_file(file, session_id)

#     if success:
#         return {
#             "message": f"Fayl '{file.filename}' uğurla emal edildi və {session_id} sessiyası üçün indeksləndi.",
#             "session_id": session_id
#         }
#     else:
#         raise HTTPException(
#             status_code=500,
#             detail="Sənədin emalı zamanı daxili xəta baş verdi. OpenSearch əlaqəsini və API açarını yoxlayın."
#         )


# # --- Chat Endpointi (POSTGRESQL İLƏ) ---
# @app.post("/chat", response_model=ChatResponse)
# async def chat_with_rag(request: ChatRequest):
#     """
#     Multi-Source RAG, Çat Keçmişi və İxtisaslaşmış Audit Promtları ilə cavab verir.
#     """
#     try:
#         # 1. RETRIEVER LOGIC: Hər iki bazadan konteksti çıxar
#         user_context_list = search_knowledge_base(request.message, request.session_id)
#         standards_context_list = search_standards_base(request.message)

#         if not user_context_list and not standards_context_list:
#             ai_response = f"Sessiya '{request.session_id}' üçün OpenSearch-də relevant kontekst tapılmadı."
#             return ChatResponse(session_id=request.session_id, ai_response=ai_response)

#         user_context = "\n---\n".join(
#             user_context_list) if user_context_list else "İstifadəçi sənədində relevant məlumat tapılmadı."
#         standards_context = "\n---\n".join(
#             standards_context_list) if standards_context_list else "Standartlar bazasında relevant məlumat tapılmadı."

#         # 2. SESSION MANAGEMENT: History Manager yaradılır
#         history_manager = get_history_manager(request.session_id)

#         # Keçmişi formatlayıb prompta əlavə etmək üçün oxuyur
#         chat_history = format_history_for_prompt(history_manager, limit=3)  # Son 3 mesaj oxunur

#         # 3. İXTİSASLAŞMIŞ PROMPTLARIN SEÇİLMƏSİ

#         if "çatışmazlıq" in request.message.lower() or "tapılmadı" in request.message.lower() or "gap" in request.message.lower():
#             # Tələb: Specialized Prompt - Gap Detection
#             system_prompt = (
#                 "Sən yüksək səviyyəli ESG Auditörsən. Sənin əsas tapşırığın **Standartlar (Kontekst 2)** tərəfindən tələb olunan hər bir elementi **Şirkət Məlumatı (Kontekst 1)** ilə müqayisə etməkdir. "
#                 "Cavabında, Kontekst 2-də tələb olunan, lakin Kontekst 1-də **tapılmayan (çatışmayan)** məlumat nöqtələrinin **dəqiq siyahısını** ver. Nəticəni bir **Markdown Cədvəli** formatında təqdim et."
#             )

#         elif "dəqiqliyi" in request.message.lower() or "formatı" in request.message.lower() or "rəqəmsal" in request.message.lower() or "quote" in request.message.lower():
#             # Tələb: Specialized Prompt - Line-by-Line Analysis
#             system_prompt = (
#                 "Sən SASB/ISSB standartları üzrə Dəqiqlik Analitiksən. Sənin vəzifən istifadəçinin sualı əsasında Kontekst 1-dən **dəqiq sətiri çıxarmaq** (Quote the exact line) və Kontekst 2-də tələb olunan **spesifik numerik (rəqəmsal) və ya formatlama** tələblərinə uyğun olub-olmadığını yoxlamaqdır. "
#                 "Cavabını bir **Markdown Cədvəlində**, təhlil etdiyin **dəqiq sətiri qeyd edərək** təqdim et. Cədvəl [Tələb Olunan Standart], [Şirkət Mətnindən Dəqiq Sitat], [Uyğunluq Statusu] sütunlarından ibarət olsun."
#             )

#         else:
#             # Day 3-dən Ümumi Müqayisə Promptu
#             system_prompt = (
#                 "Sən Keyfiyyət Təminatı üzrə Ekspert Auditörsən. Sənin məqsədin verilmiş kontekstləri müqayisə etməkdir. Keçmiş məlumatları nəzərə alaraq, Azərbaycan dilində ətraflı cavab ver."
#             )

#         # 4. Promptun Hazırlanması
#         user_prompt = (
#                 chat_history +  # <<< KEÇMİŞ ÇAT MƏLUMATINI ƏLAVƏ EDIRIK
#                 f"Cari Sual: {request.message}\n\n"
#                 f"KONTEKST 1 (Şirkət Məlumatı / İstifadəçi Faylı):\n{user_context}\n\n"
#                 f"KONTEKST 2 (Standartlar Bazası / ESG Standartları):\n{standards_context}\n\n"
#         )

#         # 5. Modelə Göndərmə və Cavab Alma
#         llm = create_llm_client(os.getenv("GEMINI_API_KEY"))
#         response = llm.invoke(input=user_prompt, system=system_prompt)
#         final_response = response.content

#         # 6. SESSION MANAGEMENT: Çat Keçmişini PostgreSQL-ə yaziriq
#         history_manager.add_user_message(request.message)
#         history_manager.add_ai_message(final_response)

#         return ChatResponse(
#             session_id=request.session_id,
#             ai_response=final_response
#         )

#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"RAG prosesi zamanı daxili xəta: {e}"
#         ) elaveler olunub test olunacaq 

# import os
# from fastapi import FastAPI, File, UploadFile, Form, HTTPException
# from urllib.parse import quote_plus
# from langchain_community.chat_message_histories import SQLChatMessageHistory
# from pydantic import BaseModel
# from dotenv import load_dotenv

# # RAG Servisindən lazım olan bütün funksiyaları import edirik
# from app.rag.rag_service import (
#     process_and_index_file,
#     search_knowledge_base,
#     search_standards_base,
#     create_llm_client,
#     # YENİ: İndeksləmə funksiyasını import edirik
#     index_standards_from_directory 
# )

# load_dotenv()


# from sqlalchemy import create_engine

# # PostgreSQL Bağlantısı üçün Environment Variable-lardan istifadə edilməsi tövsiyə olunur
# DB_URL = os.getenv("DB_URL")
# OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
# OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX")

# # Engine yaradılması (App Platform-da DB_URL-in düzgün olmasını fərz edirik)
# try:
#     engine = create_engine(DB_URL)
#     connection = engine.connect()
#     print("PostgreSQL bağlantısı uğurla yoxlandı.")
#     connection.close()
# except Exception as e:
#     # Bu hissə hələ də "Connection refused" xətası verə bilər, 
#     # əgər DB_URL hələ də 'localhost' istifadə edirsə.
#     print(f"Bağlantı qurularkən xəta baş verdi: {e}")


# print(f"DEBUG URL: {DB_URL}")

# app = FastAPI()

# # --- TƏTBİQİN BAŞLANĞIC DÜZƏLİŞİ (STARTUP EVENT) ---
# @app.on_event("startup")
# async def startup_event():
    
#     # 1. Başlanğıc yolu təyin edilir (App Platform üçün)
#     # BASE_DIR - main.py-in olduğu qovluq (məsələn, /app)
#     BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
#     # 2. Sizin göstərdiyiniz 'standards_data' qovluğuna nisbi yol təyin edilir
#     # Fərz edilir: /app/standards_data
#     # '..' App qovluğundan bir səviyyə yuxarıya (layihə kökünə) qalxır
#     STANDARDS_DIR = os.path.join(BASE_DIR, "..", "standards_data") 
    
#     # 3. İndeksləmə funksiyasını çağırırıq
#     print(f"INFO: Searching for standards in: {STANDARDS_DIR}")
#     index_standards_from_directory(STANDARDS_DIR)
    
#     # ... (Digər mövcud startup kodları buraya gəlir) ...


# def get_history_manager(session_id: str) -> SQLChatMessageHistory:
#     global DB_URL
#     return SQLChatMessageHistory(
#         session_id=session_id,
#         connection=DB_URL  # <--- Düzgün URL ötürülür
#     )

# def format_history_for_prompt(history_manager: SQLChatMessageHistory, limit: int = 3) -> str:
#     """
#     PostgreSQL bazasından son 'limit' sayda mesajı oxuyur və prompt üçün formatlayır.
#     """
#     messages = history_manager.messages[-limit:]

#     formatted_history = "--- KEÇMİŞ ÇAT MƏLUMATI ---\n"
#     if not messages:
#         return ""

#     for message in messages:
#         # Rolu və məzmunu formatla
#         formatted_history += f"[{message.type.upper()}]: {message.content}\n"

#     return formatted_history + "-------------------------\n\n"


# # --- Pydantic Modelləri ---
# class ChatRequest(BaseModel):
#     session_id: str
#     message: str


# class ChatResponse(BaseModel):
#     session_id: str
#     ai_response: str


# # --- Kök (root) yolu ---
# @app.get("/")
# async def read_root():
#     return {"message": "RAG FastAPI Service is running."}


# # --- Sənəd Yükləmə Endpointi ---
# @app.post("/upload-document")
# async def upload_document(
#         file: UploadFile = File(...),
#         session_id: str = Form(...)  # Faylı istifadəçi ilə əlaqələndirmək üçün
# ):
#     """
#     Sənədi qəbul edir, emal edir və OpenSearch vektor bazasına indeksləyir.
#     """
#     if file.content_type != "application/pdf":
#         raise HTTPException(
#             status_code=400,
#             detail="Yalnız PDF sənədləri qəbul edilir."
#         )

#     success = process_and_index_file(file, session_id)

#     if success:
#         return {
#             "message": f"Fayl '{file.filename}' uğurla emal edildi və {session_id} sessiyası üçün indeksləndi.",
#             "session_id": session_id
#         }
#     else:
#         raise HTTPException(
#             status_code=500,
#             detail="Sənədin emalı zamanı daxili xəta baş verdi. OpenSearch əlaqəsini və API açarını yoxlayın."
#         )


# # --- Chat Endpointi (POSTGRESQL İLƏ) ---
# @app.post("/chat", response_model=ChatResponse)
# async def chat_with_rag(request: ChatRequest):
#     """
#     Multi-Source RAG, Çat Keçmişi və İxtisaslaşmış Audit Promtları ilə cavab verir.
#     """
#     try:
#         # 1. RETRIEVER LOGIC: Hər iki bazadan konteksti çıxar
#         user_context_list = search_knowledge_base(request.message, request.session_id)
#         # esg_standards indeksi artıq startup zamanı yaradılacaq
#         standards_context_list = search_standards_base(request.message) 

#         if not user_context_list and not standards_context_list:
#             ai_response = f"Sessiya '{request.session_id}' üçün OpenSearch-də relevant kontekst tapılmadı."
#             return ChatResponse(session_id=request.session_id, ai_response=ai_response)

#         user_context = "\n---\n".join(
#             user_context_list) if user_context_list else "İstifadəçi sənədində relevant məlumat tapılmadı."
#         standards_context = "\n---\n".join(
#             standards_context_list) if standards_context_list else "Standartlar bazasında relevant məlumat tapılmadı."

#         # 2. SESSION MANAGEMENT: History Manager yaradılır
#         history_manager = get_history_manager(request.session_id)

#         # Keçmişi formatlayıb prompta əlavə etmək üçün oxuyur
#         chat_history = format_history_for_prompt(history_manager, limit=3)  # Son 3 mesaj oxunur

#         # 3. İXTİSASLAŞMIŞ PROMPTLARIN SEÇİLMƏSİ

#         if "çatışmazlıq" in request.message.lower() or "tapılmadı" in request.message.lower() or "gap" in request.message.lower():
#             # Tələb: Specialized Prompt - Gap Detection
#             system_prompt = (
#                 "Sən yüksək səviyyəli ESG Auditörsən. Sənin əsas tapşırığın **Standartlar (Kontekst 2)** tərəfindən tələb olunan hər bir elementi **Şirkət Məlumatı (Kontekst 1)** ilə müqayisə etməkdir. "
#                 "Cavabında, Kontekst 2-də tələb olunan, lakin Kontekst 1-də **tapılmayan (çatışmayan)** məlumat nöqtələrinin **dəqiq siyahısını** ver. Nəticəni bir **Markdown Cədvəli** formatında təqdim et."
#             )

#         elif "dəqiqliyi" in request.message.lower() or "formatı" in request.message.lower() or "rəqəmsal" in request.message.lower() or "quote" in request.message.lower():
#             # Tələb: Specialized Prompt - Line-by-Line Analysis
#             system_prompt = (
#                 "Sən SASB/ISSB standartları üzrə Dəqiqlik Analitiksən. Sənin vəzifən istifadəçinin sualı əsasında Kontekst 1-dən **dəqiq sətiri çıxarmaq** (Quote the exact line) və Kontekst 2-də tələb olunan **spesifik numerik (rəqəmsal) və ya formatlama** tələblərinə uyğun olub-olmadığını yoxlamaqdır. "
#                 "Cavabını bir **Markdown Cədvəlində**, təhlil etdiyin **dəqiq sətiri qeyd edərək** təqdim et. Cədvəl [Tələb Olunan Standart], [Şirkət Mətnindən Dəqiq Sitat], [Uyğunluq Statusu] sütunlarından ibarət olsun."
#             )

#         else:
#             # Day 3-dən Ümumi Müqayisə Promptu
#             system_prompt = (
#                 "Sən Keyfiyyət Təminatı üzrə Ekspert Auditörsən. Sənin məqsədin verilmiş kontekstləri müqayisə etməkdir. Keçmiş məlumatları nəzərə alaraq, Azərbaycan dilində ətraflı cavab ver."
#             )

#         # 4. Promptun Hazırlanması
#         user_prompt = (
#                 chat_history +  # <<< KEÇMİŞ ÇAT MƏLUMATINI ƏLAVƏ EDIRIK
#                 f"Cari Sual: {request.message}\n\n"
#                 f"KONTEKST 1 (Şirkət Məlumatı / İstifadəçi Faylı):\n{user_context}\n\n"
#                 f"KONTEKST 2 (Standartlar Bazası / ESG Standartları):\n{standards_context}\n\n"
#         )

#         # 5. Modelə Göndərmə və Cavab Alma
#         llm = create_llm_client(os.getenv("GEMINI_API_KEY"))
#         response = llm.invoke(input=user_prompt, system=system_prompt)
#         final_response = response.content

#         # 6. SESSION MANAGEMENT: Çat Keçmişini PostgreSQL-ə yaziriq
#         history_manager.add_user_message(request.message)
#         history_manager.add_ai_message(final_response)

#         return ChatResponse(
#             session_id=request.session_id,
#             ai_response=final_response
#         )

#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"RAG prosesi zamanı daxili xəta: {e}"
#         ) bu kodda deyishiklik olacaq ashagi hissede indexlenmeye gore 


#

# import os
# from fastapi import FastAPI, File, UploadFile, Form, HTTPException
# from urllib.parse import quote_plus
# from langchain_community.chat_message_histories import SQLChatMessageHistory
# from pydantic import BaseModel
# from dotenv import load_dotenv

# # RAG Servisindən lazım olan bütün funksiyaları import edirik
# from app.rag.rag_service import (
#     process_and_index_file,
#     search_knowledge_base,
#     search_standards_base,
#     create_llm_client,
#     index_standards_from_directory,
#     create_pipeline_if_not_exists # <<< YENİ ƏLAVƏ OLUNUB
# )

# load_dotenv()


# from sqlalchemy import create_engine

# # PostgreSQL Bağlantısı üçün Environment Variable-lardan istifadə edilməsi tövsiyə olunur
# DB_URL = os.getenv("DB_URL")
# OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
# OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX")

# # Engine yaradılması (App Platform-da DB_URL-in düzgün olmasını fərz edirik)
# try:
#     engine = create_engine(DB_URL)
#     connection = engine.connect()
#     print("PostgreSQL bağlantısı uğurla yoxlandı.")
#     connection.close()
# except Exception as e:
#     # Bu hissə hələ də "Connection refused" xətası verə bilər, 
#     # əgər DB_URL hələ də 'localhost' istifadə edirsə.
#     print(f"Bağlantı qurularkən xəta baş verdi: {e}")


# print(f"DEBUG URL: {DB_URL}")

# app = FastAPI()

# # --- TƏTBİQİN BAŞLANĞIC DÜZƏLİŞİ (STARTUP EVENT) ---
# @app.on_event("startup")
# async def startup_event():
    
#     # 1. Pipeline-ı yaratmağa çalışırıq (İLK OLARAQ)
#     print("INFO: Checking/Creating OpenSearch Pipeline...")
#     create_pipeline_if_not_exists()
    
#     # 2. Başlanğıc yolu təyin edilir (App Platform üçün)
#     BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
#     # 3. Sizin göstərdiyiniz 'standards_data' qovluğuna nisbi yol təyin edilir
#     STANDARDS_DIR = os.path.join(BASE_DIR, "..", "standards_data") 
    
#     # 4. İndeksləmə funksiyasını çağırırıq
#     print(f"INFO: Searching for standards in: {STANDARDS_DIR}")
#     index_standards_from_directory(STANDARDS_DIR)
    
#     # ... (Digər mövcud startup kodları buraya gəlir) ...


# def get_history_manager(session_id: str) -> SQLChatMessageHistory:
#     global DB_URL
#     return SQLChatMessageHistory(
#         session_id=session_id,
#         connection=DB_URL  # <--- Düzgün URL ötürülür
#     )

# def format_history_for_prompt(history_manager: SQLChatMessageHistory, limit: int = 3) -> str:
#     """
#     PostgreSQL bazasından son 'limit' sayda mesajı oxuyur və prompt üçün formatlayır.
#     """
#     messages = history_manager.messages[-limit:]

#     formatted_history = "--- KEÇMİŞ ÇAT MƏLUMATI ---\n"
#     if not messages:
#         return ""

#     for message in messages:
#         # Rolu və məzmunu formatla
#         formatted_history += f"[{message.type.upper()}]: {message.content}\n"

#     return formatted_history + "-------------------------\n\n"


# # --- Pydantic Modelləri ---
# class ChatRequest(BaseModel):
#     session_id: str
#     message: str


# class ChatResponse(BaseModel):
#     session_id: str
#     ai_response: str


# # --- Kök (root) yolu ---
# @app.get("/")
# async def read_root():
#     return {"message": "RAG FastAPI Service is running."}


# # --- Sənəd Yükləmə Endpointi ---
# @app.post("/upload-document")
# async def upload_document(
#         file: UploadFile = File(...),
#         session_id: str = Form(...)  # Faylı istifadəçi ilə əlaqələndirmək üçün
# ):
#     """
#     Sənədi qəbul edir, emal edir və OpenSearch vektor bazasına indeksləyir.
#     """
#     if file.content_type != "application/pdf":
#         raise HTTPException(
#             status_code=400,
#             detail="Yalnız PDF sənədləri qəbul edilir."
#         )

#     success = process_and_index_file(file, session_id)

#     if success:
#         return {
#             "message": f"Fayl '{file.filename}' uğurla emal edildi və {session_id} sessiyası üçün indeksləndi.",
#             "session_id": session_id
#         }
#     else:
#         raise HTTPException(
#             status_code=500,
#             detail="Sənədin emalı zamanı daxili xəta baş verdi. OpenSearch əlaqəsini və API açarını yoxlayın."
#         )


# # --- Chat Endpointi (POSTGRESQL İLƏ) ---
# @app.post("/chat", response_model=ChatResponse)
# async def chat_with_rag(request: ChatRequest):
#     """
#     Multi-Source RAG, Çat Keçmişi və İxtisaslaşmış Audit Promtları ilə cavab verir.
#     """
#     try:
#         # 1. RETRIEVER LOGIC: Hər iki bazadan konteksti çıxar
#         user_context_list = search_knowledge_base(request.message, request.session_id)
#         # esg_standards indeksi artıq startup zamanı yaradılacaq
#         standards_context_list = search_standards_base(request.message) 

#         if not user_context_list and not standards_context_list:
#             ai_response = f"Sessiya '{request.session_id}' üçün OpenSearch-də relevant kontekst tapılmadı."
#             return ChatResponse(session_id=request.session_id, ai_response=ai_response)

#         user_context = "\n---\n".join(
#             user_context_list) if user_context_list else "İstifadəçi sənədində relevant məlumat tapılmadı."
#         standards_context = "\n---\n".join(
#             standards_context_list) if standards_context_list else "Standartlar bazasında relevant məlumat tapılmadı."

#         # 2. SESSION MANAGEMENT: History Manager yaradılır
#         history_manager = get_history_manager(request.session_id)

#         # Keçmişi formatlayıb prompta əlavə etmək üçün oxuyur
#         chat_history = format_history_for_prompt(history_manager, limit=3)  # Son 3 mesaj oxunur

#         # 3. İXTİSASLAŞMIŞ PROMPTLARIN SEÇİLMƏSİ

#         if "çatışmazlıq" in request.message.lower() or "tapılmadı" in request.message.lower() or "gap" in request.message.lower():
#             # Tələb: Specialized Prompt - Gap Detection
#             system_prompt = (
#                 "Sən yüksək səviyyəli ESG Auditörsən. Sənin əsas tapşırığın **Standartlar (Kontekst 2)** tərəfindən tələb olunan hər bir elementi **Şirkət Məlumatı (Kontekst 1)** ilə müqayisə etməkdir. "
#                 "Cavabında, Kontekst 2-də tələb olunan, lakin Kontekst 1-də **tapılmayan (çatışmayan)** məlumat nöqtələrinin **dəqiq siyahısını** ver. Nəticəni bir **Markdown Cədvəli** formatında təqdim et."
#             )

#         elif "dəqiqliyi" in request.message.lower() or "formatı" in request.message.lower() or "rəqəmsal" in request.message.lower() or "quote" in request.message.lower():
#             # Tələb: Specialized Prompt - Line-by-Line Analysis
#             system_prompt = (
#                 "Sən SASB/ISSB standartları üzrə Dəqiqlik Analitiksən. Sənin vəzifən istifadəçinin sualı əsasında Kontekst 1-dən **dəqiq sətiri çıxarmaq** (Quote the exact line) və Kontekst 2-də tələb olunan **spesifik numerik (rəqəmsal) və ya formatlama** tələblərinə uyğun olub-olmadığını yoxlamaqdır. "
#                 "Cavabını bir **Markdown Cədvəlində**, təhlil etdiyin **dəqiq sətiri qeyd edərək** təqdim et. Cədvəl [Tələb Olunan Standart], [Şirkət Mətnindən Dəqiq Sitat], [Uyğunluq Statusu] sütunlarından ibarət olsun."
#             )

#         else:
#             # Day 3-dən Ümumi Müqayisə Promptu
#             system_prompt = (
#                 "Sən Keyfiyyət Təminatı üzrə Ekspert Auditörsən. Sənin məqsədin verilmiş kontekstləri müqayisə etməkdir. Keçmiş məlumatları nəzərə alaraq, Azərbaycan dilində ətraflı cavab ver."
#             )

#         # 4. Promptun Hazırlanması
#         user_prompt = (
#             chat_history +  # <<< KEÇMİŞ ÇAT MƏLUMATINI ƏLAVƏ EDIRIK
#             f"Cari Sual: {request.message}\n\n"
#             f"KONTEKST 1 (Şirkət Məlumatı / İstifadəçi Faylı):\n{user_context}\n\n"
#             f"KONTEKST 2 (Standartlar Bazası / ESG Standartları):\n{standards_context}\n\n"
#         )

#         # 5. Modelə Göndərmə və Cavab Alma
#         llm = create_llm_client(os.getenv("GEMINI_API_KEY"))
#         response = llm.invoke(input=user_prompt, system=system_prompt)
#         final_response = response.content

#         # 6. SESSION MANAGEMENT: Çat Keçmişini PostgreSQL-ə yaziriq
#         history_manager.add_user_message(request.message)
#         history_manager.add_ai_message(final_response)

#         return ChatResponse(
#             session_id=request.session_id,
#             ai_response=final_response
#         )

#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"RAG prosesi zamanı daxili xəta: {e}"
#         ) chat modeli ashagida teyin olunur

import os
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from urllib.parse import quote_plus
from langchain_community.chat_message_histories import SQLChatMessageHistory
from pydantic import BaseModel
from typing import List, Dict # List və Dict importları əlavə edildi
from dotenv import load_dotenv

# RAG Servisindən lazım olan bütün funksiyaları import edirik
from app.rag.rag_service import (
    process_and_index_file,
    search_knowledge_base,
    search_standards_base,
    create_llm_client,
    index_standards_from_directory,
    create_pipeline_if_not_exists 
)

load_dotenv()


from sqlalchemy import create_engine

# PostgreSQL Bağlantısı üçün Environment Variable-lardan istifadə edilməsi tövsiyə olunur
DB_URL = os.getenv("DB_URL")
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX")

# Engine yaradılması (App Platform-da DB_URL-in düzgün olmasını fərz edirik)
try:
    engine = create_engine(DB_URL)
    connection = engine.connect()
    print("PostgreSQL bağlantısı uğurla yoxlandı.")
    connection.close()
except Exception as e:
    # Bağlantı xətasının düzəldildiyi fərz edilir.
    print(f"Bağlantı qurularkən xəta baş verdi: {e}")


print(f"DEBUG URL: {DB_URL}")

app = FastAPI()

# --- TƏTBİQİN BAŞLANĞIC DÜZƏLİŞİ (STARTUP EVENT) ---
@app.on_event("startup")
async def startup_event():
    
    # 1. Pipeline-ı yaratmağa çalışırıq (İLK OLARAQ)
    print("INFO: Checking/Creating OpenSearch Pipeline...")
    create_pipeline_if_not_exists()
    
    # 2. Başlanğıc yolu təyin edilir (App Platform üçün)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # 3. Sizin göstərdiyiniz 'standards_data' qovluğuna nisbi yol təyin edilir
    STANDARDS_DIR = os.path.join(BASE_DIR, "..", "standards_data") 
    
    # 4. İndeksləmə funksiyasını çağırırıq
    print(f"INFO: Searching for standards in: {STANDARDS_DIR}")
    index_standards_from_directory(STANDARDS_DIR)


def get_history_manager(session_id: str) -> SQLChatMessageHistory:
    global DB_URL
    return SQLChatMessageHistory(
        session_id=session_id,
        connection=DB_URL  # <--- Düzgün URL ötürülür
    )

def format_history_for_prompt(history_manager: SQLChatMessageHistory, limit: int = 3) -> str:
    """
    PostgreSQL bazasından son 'limit' sayda mesajı oxuyur və prompt üçün formatlayır.
    """
    messages = history_manager.messages[-limit:]

    formatted_history = "--- KEÇMİŞ ÇAT MƏLUMATI ---\n"
    if not messages:
        return ""

    for message in messages:
        # Rolu və məzmunu formatla
        formatted_history += f"[{message.type.upper()}]: {message.content}\n"

    return formatted_history + "-------------------------\n\n"


# --- Pydantic Modelləri ---
class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    ai_response: str

# <<< YENİ Pydantic Modelİ BURADADIR
class HistoryResponse(BaseModel):
    session_id: str
    history: List[Dict[str, str]] 
# >>>


# --- Kök (root) yolu ---
@app.get("/")
async def read_root():
    return {"message": "RAG FastAPI Service is running."}


# --- Sənəd Yükləmə Endpointi ---
@app.post("/upload-document")
async def upload_document(
        file: UploadFile = File(...),
        session_id: str = Form(...)  # Faylı istifadəçi ilə əlaqələndirmək üçün
):
    """
    Sənədi qəbul edir, emal edir və OpenSearch vektor bazasına indeksləyir.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Yalnız PDF sənədləri qəbul edilir."
        )

    success = process_and_index_file(file, session_id)

    if success:
        return {
            "message": f"Fayl '{file.filename}' uğurla emal edildi və {session_id} sessiyası üçün indeksləndi.",
            "session_id": session_id
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Sənədin emalı zamanı daxili xəta baş verdi. OpenSearch əlaqəsini və API açarını yoxlayın."
        )


# --- ÇAT TARİXÇƏSİNİ GÖSTƏRƏN YENİ ENDPOINT BURADADIR ---
@app.get("/history/{session_id}", response_model=HistoryResponse)
async def get_chat_history(session_id: str):
    """
    Verilmiş session_id üçün bütün chat keçmişini bazadan oxuyur.
    """
    try:
        history_manager = get_history_manager(session_id)
        
        # LangChain mesaj obyektlərini JSON-a çevrilə bilən Python dict-lərə çeviririk
        messages_list = [
            {"type": msg.type, "content": msg.content} 
            for msg in history_manager.messages
        ]
        
        return HistoryResponse(
            session_id=session_id,
            history=messages_list
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Tarixin oxunması zamanı daxili xəta: {e}"
        )
# -----------------------------------------------------------------


# --- Chat Endpointi (POSTGRESQL İLƏ) ---
@app.post("/chat", response_model=ChatResponse)
async def chat_with_rag(request: ChatRequest):
    """
    Multi-Source RAG, Çat Keçmişi və İxtisaslaşmış Audit Promtları ilə cavab verir.
    """
    try:
        # 1. RETRIEVER LOGIC: Hər iki bazadan konteksti çıxar
        user_context_list = search_knowledge_base(request.message, request.session_id)
        standards_context_list = search_standards_base(request.message) 

        if not user_context_list and not standards_context_list:
            ai_response = f"Sessiya '{request.session_id}' üçün OpenSearch-də relevant kontekst tapılmadı."
            return ChatResponse(session_id=request.session_id, ai_response=ai_response)

        user_context = "\n---\n".join(
            user_context_list) if user_context_list else "İstifadəçi sənədində relevant məlumat tapılmadı."
        standards_context = "\n---\n".join(
            standards_context_list) if standards_context_list else "Standartlar bazasında relevant məlumat tapılmadı."

        # 2. SESSION MANAGEMENT: History Manager yaradılır
        history_manager = get_history_manager(request.session_id)

        # Keçmişi formatlayıb prompta əlavə etmək üçün oxuyur
        chat_history = format_history_for_prompt(history_manager, limit=3) 

        # 3. İXTİSASLAŞMIŞ PROMPTLARIN SEÇİLMƏSİ

        if "çatışmazlıq" in request.message.lower() or "tapılmadı" in request.message.lower() or "gap" in request.message.lower():
            # Tələb: Specialized Prompt - Gap Detection
            system_prompt = (
                "Sən yüksək səviyyəli ESG Auditörsən. Sənin əsas tapşırığın **Standartlar (Kontekst 2)** tərəfindən tələb olunan hər bir elementi **Şirkət Məlumatı (Kontekst 1)** ilə müqayisə etməkdir. "
                "Cavabında, Kontekst 2-də tələb olunan, lakin Kontekst 1-də **tapılmayan (çatışmayan)** məlumat nöqtələrinin **dəqiq siyahısını** ver. Nəticəni bir **Markdown Cədvəli** formatında təqdim et."
            )

        elif "dəqiqliyi" in request.message.lower() or "formatı" in request.message.lower() or "rəqəmsal" in request.message.lower() or "quote" in request.message.lower():
            # Tələb: Specialized Prompt - Line-by-Line Analysis
            system_prompt = (
                "Sən SASB/ISSB standartları üzrə Dəqiqlik Analitiksən. Sənin vəzifən istifadəçinin sualı əsasında Kontekst 1-dən **dəqiq sətiri çıxarmaq** (Quote the exact line) və Kontekst 2-də tələb olunan **spesifik numerik (rəqəmsal) və ya formatlama** tələblərinə uyğun olub-olmadığını yoxlamaqdır. "
                "Cavabını bir **Markdown Cədvəlində**, təhlil etdiyin **dəqiq sətiri qeyd edərək** təqdim et. Cədvəl [Tələb Olunan Standart], [Şirkət Mətnindən Dəqiq Sitat], [Uyğunluq Statusu] sütunlarından ibarət olsun."
            )

        else:
            # Day 3-dən Ümumi Müqayisə Promptu
            system_prompt = (
                "Sən Keyfiyyət Təminatı üzrə Ekspert Auditörsən. Sənin məqsədin verilmiş kontekstləri müqayisə etməkdir. Keçmiş məlumatları nəzərə alaraq, Azərbaycan dilində ətraflı cavab ver."
            )

        # 4. Promptun Hazırlanması
        user_prompt = (
            chat_history + 
            f"Cari Sual: {request.message}\n\n"
            f"KONTEKST 1 (Şirkət Məlumatı / İstifadəçi Faylı):\n{user_context}\n\n"
            f"KONTEKST 2 (Standartlar Bazası / ESG Standartları):\n{standards_context}\n\n"
        )

        # 5. Modelə Göndərmə və Cavab Alma
        llm = create_llm_client(os.getenv("GEMINI_API_KEY"))
        response = llm.invoke(input=user_prompt, system=system_prompt)
        final_response = response.content

        # 6. SESSION MANAGEMENT: Çat Keçmişini PostgreSQL-ə yaziriq
        history_manager.add_user_message(request.message)
        history_manager.add_ai_message(final_response)

        return ChatResponse(
            session_id=request.session_id,
            ai_response=final_response
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RAG prosesi zamanı daxili xəta: {e}"
        )
