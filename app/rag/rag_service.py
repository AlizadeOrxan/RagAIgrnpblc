import os
from dotenv import load_dotenv
from fastapi import UploadFile
from tempfile import NamedTemporaryFile
from typing import List
from opensearchpy import OpenSearch # Pipeline yaratmaq üçün əlavə edildi

from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import OpenSearchVectorSearch 

load_dotenv()

# ---- Konfiqurasiya ----
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = None  

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


## 🚀 YENİLƏNMİŞ HİSSƏ: OpenSearch Klientləri və Pipeline Məntiqi

def get_opensearch_client(index_name: str):
    """OpenSearch vektor bazası bağlantısını verir."""
    
    # Düzgün Environment Variable-ları funksiya daxilində oxuyuruq
    HOST_V = os.getenv("OPENSEARCH_HOSTS")
    PORT_STR_V = os.getenv("OPENSEARCH_PORT")
    USER_V = os.getenv("OPENSEARCH_USER")
    PASSWORD_V = os.getenv("OPENSEARCH_PASSWORD")
    
    # Bütün dəyərlər mövcud olub-olmadığını yoxlayırıq
    if not (HOST_V and PORT_STR_V and PORT_STR_V.isdigit() and USER_V and PASSWORD_V):
        print("WARNING: OpenSearch Env Variables incomplete for Vector Search. Check App Platform settings.")
        return None

    try:
        embeddings = create_embeddings_client(GEMINI_API_KEY)
        PORT_V = int(PORT_STR_V)
        opensearch_url = f"https://{HOST_V}:{PORT_V}"
        
        # <<< Dəyişiklik 1: Pipeline arqumenti burada təyin edilir
        index_args = {}
        if index_name == STANDARDS_INDEX_NAME:
            index_args = {"pipeline": "pdf_date_fixer"}
        # >>>

        return OpenSearchVectorSearch(
            index_name=index_name,
            embedding_function=embeddings,
            opensearch_url=opensearch_url,
            http_auth=(USER_V, PASSWORD_V),  
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
            index_kwargs=index_args # <<< Pipeline arqumenti ötürülür
        )
    except Exception as e:
        print(f"OpenSearch bağlantı xətası ({index_name}): {e}")
        return None


def create_pipeline_if_not_exists():
    """OpenSearch daxilində PDF metadata xətasını düzəldən pipeline-ı yaradır."""
    
    HOST_V = os.getenv("OPENSEARCH_HOSTS")
    PORT_STR_V = os.getenv("OPENSEARCH_PORT")
    USER_V = os.getenv("OPENSEARCH_USER")
    PASSWORD_V = os.getenv("OPENSEARCH_PASSWORD")
    
    if not (HOST_V and PORT_STR_V and PORT_STR_V.isdigit() and USER_V and PASSWORD_V):
        print("WARNING: OpenSearch Env Variables incomplete for Pipeline creation.")
        return False
        
    try:
        # Təmiz opensearchpy klientini yaradırıq
        client = OpenSearch(
            hosts=[{'host': HOST_V, 'port': int(PORT_STR_V)}],
            http_auth=(USER_V, PASSWORD_V),
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False
        )

        pipeline_name = "pdf_date_fixer"
        
        # Pipeline-ın mövcudluğunu yoxlamaq
        if client.ingest.get_pipeline(id=pipeline_name, ignore=[404]):
            print(f"INFO: Pipeline '{pipeline_name}' already exists.")
            return True
            
        print(f"INFO: Creating Pipeline '{pipeline_name}' via Python client...")
        
        # Pipeline-ı yaratmaq
        client.ingest.put_pipeline(
            id=pipeline_name,
            body={
                "description" : "PDF metadata.moddate field cleaner for D:YYYYMMDDhhmmss format",
                "processors" : [
                    {"grok": {"field": "metadata.moddate", "patterns": ["D:%{NOTSPACE:metadata.moddate_cleaned}"], "if": "ctx.metadata.moddate != null && ctx.metadata.moddate.startsWith(\"D:\")"}},
                    {"date": {"field": "metadata.moddate_cleaned", "target_field": "metadata.moddate", "formats": ["yyyyMMddHHmmss"], "timezone": "UTC"}},
                    {"remove": {"field": "metadata.moddate_cleaned", "if": "ctx.metadata.moddate_cleaned != null"}}
                ]
            }
        )
        print(f"SUCCESS: Pipeline '{pipeline_name}' created.")
        return True

    except Exception as e:
        print(f"ERROR: Failed to create or check pipeline: {e}")
        return False

# --- STANDARTLARIN AVTOMATİK İNDEKSLƏNMƏSİ FUNKSİYASI ---
def index_standards_from_directory(directory_path: str):
    """
    Verilmiş qovluqdan PDF sənədlərini oxuyur və onları esg_standards indeksinə yükləyir.
    """
    vector_store = get_opensearch_client(STANDARDS_INDEX_NAME)
    if not vector_store:
        print("ERROR: Could not get OpenSearch client for standards indexing. Aborting.")
        return

    # İndeksin artıq mövcud olub-olmadığını yoxla (təkrar yüklənmənin qarşısını almaq üçün)
    try:
        if vector_store.client.indices.exists(index=STANDARDS_INDEX_NAME):
            print(f"INFO: Standards index '{STANDARDS_INDEX_NAME}' already exists. Skipping bulk indexing.")
            return
    except Exception as e:
        print(f"WARNING: Could not check index existence: {e}. Attempting to index.")
    
    # Faylları tap və indekslə
    if not os.path.exists(directory_path):
        print(f"WARNING: Standards directory not found at {directory_path}. Skipping indexing.")
        return

    pdf_files = [f for f in os.listdir(directory_path) if f.endswith(('.pdf', '.PDF'))]  
    if not pdf_files:
        print("INFO: No PDF standards files found to index.")
        return

    print(f"INFO: Starting indexing of {len(pdf_files)} standards files...")
    
    total_chunks = 0
    for filename in pdf_files:
        file_path = os.path.join(directory_path, filename)
        
        try:
            loader = PyPDFLoader(file_path)
            docs = loader.load()

            splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
            chunks = splitter.split_documents(docs)

            for doc in chunks:
                doc.metadata["standard_name"] = filename.replace('.pdf', '').replace('.PDF', '')
                doc.metadata["source_file"] = filename

            vector_store.add_documents(chunks)
            total_chunks += len(chunks)
            print(f"Indexed {len(chunks)} chunks from {filename}")
            
        except Exception as e:
            print(f"ERROR: Failed to index file {filename}: {e}")

    print(f"SUCCESS: Standards indexing finished. Total chunks indexed: {total_chunks}")


# --- FAYL EMALI VƏ İNDEKSLƏNMƏ (Dəyişməz qalır) ---

def process_and_index_file(file: UploadFile, session_id: str) -> bool:
    """PDF sənədini emal edib İSTİFADƏÇİ bazasına indeksləyir"""
    temp_path = None
    try:
        vector_store = get_opensearch_client(INDEX_NAME)
        if not vector_store:
            return False

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
    vector_store = get_opensearch_client(STANDARDS_INDEX_NAME)
    if not vector_store:
        return []

    docs = vector_store.similarity_search(
        query=query,
        k=4
    )

    context_list = []
    for d in docs:
        standard_name = d.metadata.get("standard_name", "Naməlum Standart")
        context_list.append(f"[{standard_name}]: {d.page_content}")

    return context_list
