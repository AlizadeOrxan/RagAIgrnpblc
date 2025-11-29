import os
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from urllib.parse import quote_plus
from langchain_community.chat_message_histories import SQLChatMessageHistory
from pydantic import BaseModel
from dotenv import load_dotenv

# RAG Servisindən lazım olan bütün funksiyaları import edirik
from app.rag.rag_service import (
    process_and_index_file,
    search_knowledge_base,
    search_standards_base,
    create_llm_client
)

load_dotenv()


from sqlalchemy import create_engine

DB_USER = "rag_user"
DB_PASS = "raguser123"
DB_HOST = "127.0.0.1"
DB_PORT = "5432"
DB_NAME = "rag_history_db"

DB_URL = os.getenv("DB_URL")
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX")

engine = create_engine(DB_URL)

try:
    connection = engine.connect()
    print("Bağlantı uğurla quruldu!")
    connection.close()
except Exception as e:
    print(f"Bağlantı qurularkən xəta baş verdi: {e}")


print(f"DEBUG URL: {DB_URL}")

app = FastAPI()


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
        chat_history = format_history_for_prompt(history_manager, limit=3)  # Son 3 mesaj oxunur

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
                chat_history +  # <<< KEÇMİŞ ÇAT MƏLUMATINI ƏLAVƏ EDIRIK
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
