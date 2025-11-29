# 💡 RAG FastAPI Xidməti (Gemini + OpenSearch)

Bu layihə, **Google Gemini Embeddings** vasitəsilə sənədlərin yüklənməsi, indekslənməsi və **DigitalOcean Managed OpenSearch** verilənlər bazası üzərində sual-cavab (Retrieval-Augmented Generation - RAG) funksiyasını təmin edən FastAPI əsaslı API-dir.

## 🛠️ 1. Texnologiyalar və Servislər

* **Application Server:** Python, FastAPI, Uvicorn
* **Vektor Verilənlər Bazası:** DigitalOcean Managed OpenSearch
* **Chat Tarixçəsi DB:** PostgreSQL (Docker Konteynerində)
* **Deployment Mühiti:** DigitalOcean Droplet üzərində Docker Compose

---

## ⚙️ 2. Deployment Konfiqurasiyası

Bütün qoşulma məlumatları layihənin kökündəki **`.env`** faylında saxlanılır.

### 2.1. `.env` Faylının Məzmunu

Aşağıdakı dəyərlər sizin real məlumatlarınızla yenilənməlidir:

```ini

# Google Gemini API Açarı
GEMINI_API_KEY="AIzaSyXXXXXXXXXXXXXXXXXX" 

# PostgreSQL (Lokal Docker Konteneyrinə qoşulma)
DB_URL="postgresql+psycopg2://rag_user:raguser123@db:5432/rag_history_db" 

# OpenSearch
OPENSEARCH_HOST="https://doadmin:<parol>@<host_unvani>:25060" 
OPENSEARCH_INDEX="rag_knowledge_base"
STANDARDS_INDEX_NAME="esg_standards"
# ----------------------------------------------------

2.2. Əsas Deployment Əmri
Layihənin bütün komponentlərini Droplet-də işə salmaq üçün yeganə komut:


docker compose up -d

🚀 3. Application Serverin İşə Salınması (Yekun Addımlar)
Siz artıq bütün konfiqurasiya fayllarını (o cümlədən yeni Dockerfile və README.md) hazırlamısınız. İndi Application Serveri işə salırıq:

Addım A: Köçürmə və Qoşulma
Lokal Terminalınızda, bütün faylları köçürün:


scp -r ~/rag-fastapi-service root@167.71.129.151:/root/
Droplet-ə SSH ilə qoşulun:


ssh root@167.71.129.151
cd /root/rag-fastapi-service

Addım B: Serveri İşə Salma
Application Serveri (FastAPI) və PostgreSQL-i İşə Salın:


docker compose up -d

Addım C: İşlək Vəziyyətin Yoxlanılması
Logları İzləyin (Qoşulma xətası varmı?):


docker compose logs -f rag-fastapi-service

Brauzerlə Yoxlayın: 
Tətbiqinizin interfeysinə daxil olun. 
Ünvan: http://167.71.129.151:8000/docs

📋 4. API Endpointləri
Tətbiq işə salındıqdan sonra, bütün funksiyalar bu endpointlər vasitəsilə təmin edilir:

/upload-document (POST): Yeni PDF sənədi yükləyir və OpenSearch DB-də indeksləyir.

/chat (POST): İstifadəçinin sualını qəbul edir, konteksti OpenSearch-dən çıxarır və Gemini ilə cavab yaradır.

/history (GET): PostgreSQL DB-də saxlanılan bütün chat tarixçəsini qaytarır.

/reset (POST): Bütün PostgreSQL chat tarixçəsini sıfırlayır.