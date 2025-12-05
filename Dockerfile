# ------------------------------------------------------------------
FROM python:3.11-slim

# İşlək qovluq
WORKDIR /app

# Asılılıqların quraşdırılması
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bütün tətbiq kodunun köçürülməsi
COPY . .

# Application Serverin başlanğıcı
#CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# ------------------------------------------------------------------

#CMD ["gunicorn", "app.main:app","--workers", "4","--worker-class", "uvicorn.workers.UvicornWorker","--bind", "0.0.0.0:8000","--timeout", "120"]

#CMD ["sh", "-c", "gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 120"]

#CMD ["sh", "-c", "gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 120"]

CMD ["sh", "-c", "gunicorn app.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 300"]