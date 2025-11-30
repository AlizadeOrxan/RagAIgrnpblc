import os
from dotenv import load_dotenv
from fastapi import UploadFile
from tempfile import NamedTemporaryFile
from typing import List
from opensearchpy import OpenSearch

from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import OpenSearchVectorSearch

load_dotenv()

# ---- Konfiqurasiya ----
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# OS_HOST = os.getenv("OS_HOST", "localhost")
# OS_PORT = int(os.getenv("OS_PORT", 9200))
# OS_USER = os.getenv("OS_USER", "admin")
# OS_PASS = os.getenv("OS_PASS", "StrongP@ss123")

HOST = os.getenv("OPENSEARCH_HOSTS")
PORT = int(os.getenv("OPENSEARCH_PORT"))
USER = os.getenv("OPENSEARCH_USER")
PASSWORD = os.getenv("OPENSEARCH_PASSWORD")

# 2. OpenSearch klientini yaratmaq (Ayrı-ayrı dəyərlərlə)
client = OpenSearch(
    hosts=[{'host': HOST, 'port': PORT}],
    http_auth=(USER, PASSWORD),
    use_ssl=True,
    # verify_certs-i False etmək bəzən App Platformda SSL xətalarını aradan qaldırır.
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False
)

# İki fərqli indeksin adı
INDEX_NAME = "rag_knowledge_base"  # İstifadəçi faylları
STANDARDS_INDEX_NAME = "esg_standards"  # Sizin standart fayllarınız


# --- KLİENT YARATMA FUNKSİYALARI ---

def create_embeddings_client(api_key: str):
    """Embeddings obyektini yaradır."""
    if not api_key:
        raise ValueError("GEMINI_API_KEY mühit dəyişəni tapılmadı! Zəhmət olmasa terminalda export edin.")

    os.environ['GEMINI_API_KEY'] = api_key
    os.environ['GOOGLE_API_KEY'] = api_key

    return GoogleGenerativeAIEmbeddings(
        model="text-embedding-004",
        api_key=api_key
    )


def create_llm_client(api_key: str):
    """LLM obyektini yaradır. Gemini modeli istifadə olunur."""
    if not api_key:
        raise ValueError("GEMINI_API_KEY mühit dəyişəni tapılmadı.")

    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        api_key=api_key,
        temperature=0.0
    )


# --- OPENSEARCH KLİENTİNİN YARADILMASI ---

def get_opensearch_client(index_name: str):
    """OpenSearch vektor bazası bağlantısını verir (həm istifadəçi, həm də standartlar üçün istifadə edilə bilər)."""
    try:
        embeddings = create_embeddings_client(GEMINI_API_KEY)

        host = "localhost" if OS_HOST in ["opensearch", "db"] else OS_HOST

        return OpenSearchVectorSearch(
            index_name=index_name,
            embedding_function=embeddings,
            opensearch_url=f"https://{host}:{OS_PORT}",
            http_auth=(OS_USER, OS_PASS),
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False
        )
    except Exception as e:
        print(f"OpenSearch bağlantı xətası ({index_name}): {e}")
        return None


# --- FAYL EMALI VƏ İNDEKSLƏNMƏ (Dəyişməz qalır) ---

def process_and_index_file(file: UploadFile, session_id: str) -> bool:
    """PDF sənədini emal edib İSTİFADƏÇİ bazasına indeksləyir"""
    temp_path = None
    try:
        # get_opensearch_client-i çağırarkən INDEX_NAME-i ötürürük
        vector_store = get_opensearch_client(INDEX_NAME)
        if not vector_store:
            return False

        # ... (qalan kod dəyişməz qalır: temp fayl, loader, splitter, add_documents) ...

        with NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
            tmp.write(file.file.read())
            temp_path = tmp.name

        loader = PyPDFLoader(temp_path)
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200
        )
        chunks = splitter.split_documents(docs)

        for doc in chunks:
            doc.metadata["session_id"] = session_id
            doc.metadata["source_file"] = file.filename

        vector_store.add_documents(chunks)
        return True

    except Exception as e:
        print("PDF emalı xətası:", e)
        return False

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# --- Çoxlu Bazadan Axtarış Funksiyaları (MULTI-SOURCE RAG) ---

def search_knowledge_base(query: str, session_id: str) -> List[str]:
    """İstifadəçi sessiyası üzrə kontekst qaytarır."""
    vector_store = get_opensearch_client(INDEX_NAME)
    if not vector_store:
        return []

    opensearch_filter = {
        "term": {
            "metadata.session_id": session_id
        }
    }

    docs = vector_store.similarity_search(
        query=query,
        k=4,
        filter=opensearch_filter
    )

    return [d.page_content for d in docs]


def search_standards_base(query: str) -> List[str]:
    """Standartlar indeksində kontekst qaytarır (filtrsüz)."""
    vector_store = get_opensearch_client(STANDARDS_INDEX_NAME)  # STANDARTLAR İNDEXİNİ istifadə edirik
    if not vector_store:
        return []

    docs = vector_store.similarity_search(
        query=query,
        k=4  # Standartlardan da 4 relevant chunk çıxarırıq
    )

    # Standartın adını da cavaba daxil etmək faydalı olar (opsional)
    context_list = []
    for d in docs:
        standard_name = d.metadata.get("standard_name", "Naməlum Standart")
        context_list.append(f"[{standard_name}]: {d.page_content}")

    return context_list