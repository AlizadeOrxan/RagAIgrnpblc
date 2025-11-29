import os
from dotenv import load_dotenv
from glob import glob
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import OpenSearchVectorSearch

load_dotenv()

# --- Konfiqurasiya ---
STANDARDS_DIR = "./standards_data"
STANDARDS_INDEX_NAME = "esg_standards"

OS_HOST = os.getenv("OS_HOST", "opensearch")
OS_PORT = int(os.getenv("OS_PORT", 9200))
OS_USER = os.getenv("OS_USER", "admin")
OS_PASS = os.getenv("OS_PASS", "StrongP@ss123")

# API açarını faylın yuxarısında sadəcə oxuyuruq
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")



def create_embeddings_client(api_key: str):
    """Embeddings obyektini yaradır. Xəta vermənin qarşısını almaq üçün."""
    if not api_key:
        raise ValueError("GEMINI_API_KEY mühit dəyişəni tapılmadı! Zəhmət olmasa terminalda export edin.")

    # LangChain üçün mühiti təmin edirik
    os.environ['GEMINI_API_KEY'] = api_key
    os.environ['GOOGLE_API_KEY'] = api_key

    return GoogleGenerativeAIEmbeddings(
        model="text-embedding-004",
        api_key=api_key
    )


def get_opensearch_client_standards():
    """Standartlar indeksi üçün OpenSearch əlaqəsini qaytarır."""
    try:
        # Embeddings klientini burada yaradırıq (SpawnProcess xətasını həll edir)
        embeddings = create_embeddings_client(GEMINI_API_KEY)

        host = "localhost" if OS_HOST in ["opensearch", "db"] else OS_HOST
        return OpenSearchVectorSearch(
            index_name=STANDARDS_INDEX_NAME,
            embedding_function=embeddings,  # Funksiyadan gələn obyekti ötürürük
            opensearch_url=f"https://{host}:{OS_PORT}",
            http_auth=(OS_USER, OS_PASS),
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False
        )
    except ValueError as e:
        print(f"❌ XƏTA: {e}")
        return None
    except Exception as e:
        print(f"OpenSearch Standartlar əlaqəsi xətası: {e}")
        return None


def ingest_standards_documents():
    """STANDARDS_DIR qovluğundakı bütün PDF fayllarını OpenSearch-ə yükləyir."""

    if not os.path.exists(STANDARDS_DIR):
        print(
            f"❌ XƏTA: '{STANDARDS_DIR}' qovluğu tapılmadı. Zəhmət olmasa, qovluğu yaradın və faylları içinə yerləşdirin.")
        return

    pdf_files = glob(os.path.join(STANDARDS_DIR, "*.pdf"))
    if not pdf_files:
        print(f"⚠️ XƏBƏRDARLIQ: '{STANDARDS_DIR}' qovluğunda PDF faylları tapılmadı.")
        return

    vector_store = get_opensearch_client_standards()
    if vector_store is None:
        return

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=200
    )

    print(f"--- {len(pdf_files)} Standart Fayl İndekslənir ---")

    for file_path in pdf_files:
        try:
            print(f"İndekslənir: {os.path.basename(file_path)}")

            loader = PyPDFLoader(file_path)
            documents = loader.load()
            texts = text_splitter.split_documents(documents)

            for doc in texts:
                doc.metadata["source_type"] = "ESG_Standard"
                doc.metadata["standard_name"] = os.path.basename(file_path)

            vector_store.add_documents(texts)
            print(f"✅ Uğurla indeksləndi: {len(texts)} chunks.")

        except Exception as e:
            print(f"❌ {file_path} faylının emalı zamanı xəta: {e}")

    print("\n✅ Bütün Standart Faylların İndekslənməsi Bitdi.")


if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("❌ XƏTA: GEMINI_API_KEY DƏYƏRİ TAPILMADI. Zəhmət olmasa, .env faylını yoxlayın.")
    else:
        print("✅ GEMINI API KEY TAPILDI. İndeksləməyə başlanır...")
        ingest_standards_documents()