import os
from dotenv import load_dotenv
from fastapi import UploadFile
from tempfile import NamedTemporaryFile
from typing import List
from typing import Optional
from opensearchpy import OpenSearch
import shutil  # Fayl kopyalama

from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import UnstructuredExcelLoader  # <<< EXCEL LOADER
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import OpenSearchVectorSearch

# ... (digər importlar)

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
        # 1. Embeddings Klientini Yaradırıq
        embeddings = create_embeddings_client(GEMINI_API_KEY)

        PORT_V = int(PORT_STR_V)
        opensearch_url = f"https://{HOST_V}:{PORT_V}"

        # OpenSearch Klient parametrləri
        client_kwargs = {
            # Bağlantı timeout-unu 30 saniyəyə qaldırırıq
            "timeout": 30,
            "max_retries": 3,
            "retry_on_timeout": True,
        }

        # 2. OpenSearch Klientini Yaradıb Bağlantını Yoxlayırıq (Ping)
        # Ping uğursuz olsa belə, bu, Langchain obyektini yaratmağa mane olmamalıdır.
        # Əgər Ping bu qısa müddətdə dərhal xəta verirsə, bu Kod 128-in səbəbidir.
        raw_client = OpenSearch(
            hosts=[{'host': HOST_V, 'port': PORT_V}],
            http_auth=(USER_V, PASSWORD_V),
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
            **client_kwargs
        )

        # XƏTA MƏNBƏYİ: Ping atılması hələ də prosesi dayandırır.
        # Təhlükəsizlik üçün: Ping-i try/except ilə bükürük, amma əsas obyekti qaytarırıq.
        try:
            # Ping cəhdi - Loglarda xəta görmək üçün
            if not raw_client.ping():
                print(f"ERROR: OpenSearch hostu {HOST_V}:{PORT_V} əlçatmazdır (Ping uğursuz).")
        except Exception as ping_e:
            # Əgər Ping zamanı birbaşa Connection Refused gəlirsə, onu çap edirik.
            print(f"ERROR: OpenSearch Ping zamanı kritik xəta: {ping_e}")

        index_args = {}
        if index_name == STANDARDS_INDEX_NAME:
            index_args = {"pipeline": "pdf_date_fixer"}

        return OpenSearchVectorSearch(
            index_name=index_name,
            embedding_function=embeddings,
            opensearch_url=opensearch_url,
            http_auth=(USER_V, PASSWORD_V),
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
            index_kwargs=index_args,
            client_kwargs=client_kwargs
        )
    except Exception as e:
        # Bütün xətaları (OpenSearch və ya Embeddings Client) burada tuturuq.
        print(f"KRİTİK BAĞLANTI XƏTASI ({index_name}): {e}. Tətbiq dayana bilər.")
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
        client = OpenSearch(
            hosts=[{'host': HOST_V, 'port': int(PORT_STR_V)}],
            http_auth=(USER_V, PASSWORD_V),
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False
        )

        pipeline_name = "pdf_date_fixer"

        if client.ingest.get_pipeline(id=pipeline_name, ignore=[404]):
            print(f"INFO: Pipeline '{pipeline_name}' already exists.")
            return True

        print(f"INFO: Creating Pipeline '{pipeline_name}' via Python client...")

        client.ingest.put_pipeline(
            id=pipeline_name,
            body={
                "description": "PDF metadata.moddate field cleaner for D:YYYYMMDDhhmmss format",
                "processors": [
                    {"grok": {"field": "metadata.moddate", "patterns": ["D:%{NOTSPACE:metadata.moddate_cleaned}"],
                              "if": "ctx.metadata.moddate != null && ctx.metadata.moddate.startsWith(\"D:\")"}},
                    {"date": {"field": "metadata.moddate_cleaned", "target_field": "metadata.moddate",
                              "formats": ["yyyyMMddHHmmss"], "timezone": "UTC"}},
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

    try:
        if vector_store.client.indices.exists(index=STANDARDS_INDEX_NAME):
            print(f"INFO: Standards index '{STANDARDS_INDEX_NAME}' already exists. Skipping bulk indexing.")
            return
    except Exception as e:
        print(f"WARNING: Could not check index existence: {e}. Attempting to index.")

    if not os.path.exists(directory_path):
        print(f"WARNING: Standards directory not found at {directory_path}. Skipping indexing.")
        return

    # SADECE PDF DEYİL, EXCEL'İ DƏ YOXLAYIRIQ (Ancaq standartların PDF olduğu fərz edilir, bu hissəni PDF saxlayıram)
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



def process_and_index_file(uploaded_file: UploadFile, session_id: str) -> bool:
    """PDF/EXCEL sənədini emal edib İSTİFADƏÇİ bazasına indeksləyir"""
    temp_path = None
    try:
        vector_store = get_opensearch_client(INDEX_NAME)
        if not vector_store:
            return False

        # Faylı temp qovluğuna yazırıq
        temp_filepath = f"/tmp/{uploaded_file.filename}"
        with open(temp_filepath, "wb") as f:
            # Faylın məzmununu temp fayla kopyalayırıq
            shutil.copyfileobj(uploaded_file.file, f)
            temp_path = temp_filepath

        file_extension = os.path.splitext(uploaded_file.filename)[1].lower()

        # --- LOADER SEÇİMİ ---
        if file_extension == '.pdf':
            print("INFO: Loading file with PyMuPDFLoader...")
            loader = PyPDFLoader(temp_path)
        elif file_extension in ['.xlsx', '.xls']:  # <<< EXCEL DƏSTƏYİ
            print("INFO: Loading file with UnstructuredExcelLoader...")
            # Problem 1 (Format Xətası) ehtimalını azaltmaq üçün 'mode="elements"' çıxarılır
            loader = UnstructuredExcelLoader(temp_path)
        else:
            print(f"ERROR: process_and_index_file received unsupported file type: {file_extension}")
            return False

        # 1. Faylı yükləyirik
        docs = loader.load()

        # 2. <<< Problem 2 Həlli: Məzmunun Təmizlənməsi (Sanitizasiya) >>>
        for doc in docs:
            if doc.page_content:
                # Ulduzları ('*') boşluqla əvəz edirik (Markdown formatını aradan qaldırır)
                doc.page_content = doc.page_content.replace('*', ' ')
                # Birdən çox olan boşluqları tək boşluğa çeviririk (əlavə təmizlik)
                doc.page_content = ' '.join(doc.page_content.split())
        # -------------------------------------------------------------

        # 3. Məzmunu parçalara ayırırıq
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200
        )
        chunks = splitter.split_documents(docs)

        # 4. Metadata əlavə edirk
        for doc in chunks:
            doc.metadata["session_id"] = session_id  # Problem 3 üçün əsas
            doc.metadata["source_file"] = uploaded_file.filename

        # 5. OpenSearch-ə indeksləyirik
        vector_store.add_documents(chunks)

        print(f"SUCCESS: {len(chunks)} parça {session_id} sessiyası üçün indeksləndi.")
        return True

    except Exception as e:
        print("Fayl emalı xətası:", e)
        return False

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

#- --- -- - - - Excell fayl yukleme
async def extract_excel_context_for_comparison(uploaded_file: UploadFile) -> Optional[str]:
    """
    Yüklənən Excel faylını oxuyur, parçalayır və OpenSearch-ə indeksləmədən
    yalnız bir sorğuluq kontekst (str) kimi qaytarır.
    """
    temp_path = None
    try:
        # 1. Faylı temp qovluğuna yazırıq
        # Fayl adının unikal olması üçün random hissə əlavə olunur
        temp_filepath = f"/tmp/excel_{os.urandom(8).hex()}_{uploaded_file.filename}"

        # Fayl məzmununu yaddaşda oxuyuruq
        file_content = await uploaded_file.read()

        with open(temp_filepath, "wb") as f:
            f.write(file_content)
            temp_path = temp_filepath

        file_extension = os.path.splitext(uploaded_file.filename)[1].lower()

        # Yalnız Excel fayllarını emal et
        if file_extension not in ['.xlsx', '.xls']:
            print(f"ERROR: Fayl tipi dəstəklənmir: {file_extension}")
            return None

        # 2. Faylı yükləyirik
        loader = UnstructuredExcelLoader(temp_path)
        docs = loader.load()

        # 3. Məzmunu təmizləyirik (Markdown, * simvolları və artıq boşluqlar)
        for doc in docs:
            if doc.page_content:
                doc.page_content = doc.page_content.replace('*', ' ')
                doc.page_content = ' '.join(doc.page_content.split())

        # 4. Məzmunu parçalara ayırırıq
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200
        )
        chunks = splitter.split_documents(docs)

        # 5. Kontekst üçün ilk bir neçə parçanı birləşdiririk
        # Bu kontekst sorğu zamanı Prompta daxil ediləcək.
        context_texts = [chunk.page_content for chunk in chunks[:5]]  # İlk 5 chunk

        return "\n\n--- YÜKLƏNƏN EXCEL MƏLUMATI ---\n\n" + "\n\n".join(context_texts)

    except Exception as e:
        print(f"Excel faylından kontekst çıxarılması xətası: {e}")
        print(f"KRİTİK HATA: Excel faylından kontekst çıxarılması zamanı gözlənilməz xəta: {e}")
        # Hətta tam traceback-i çap edin
        import traceback
        traceback.print_exc()
        return None

    finally:
        # 6. Müvəqqəti faylı silirik
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as cleanup_e:
                print(f"WARNING: Temp faylın silinməsi uğursuz oldu: {cleanup_e}")


# --- Çoxlu Bazadan Axtarış Funksiyaları (MULTI-SOURCE RAG) ---
# ... (Bu hissə dəyişməz qalır) ...

def search_knowledge_base(query: str, session_id: str) -> List[str]:
    # ...
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
    # ...
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