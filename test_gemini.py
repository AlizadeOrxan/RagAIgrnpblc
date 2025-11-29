# test_gemini.py

import os
# google.genai paketinin quraşdırıldığını fərz edirik (pip install google-genai)
from google.genai import Client
from google.genai.errors import APIError
from dotenv import load_dotenv

# .env faylını yüklə
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

print("--- Gemini API Testi Başlayır ---")

if not API_KEY:
    print("❌ XƏTA: GEMINI_API_KEY .env faylında tapılmadı.")
else:
    try:
        # Client obyektini düzgün import (Client) və düzgün dəyişən (API_KEY) ilə yaratmaq
        client = Client(api_key=API_KEY)

        print("✅ Client uğurla yaradıldı.")

        # Test sorğusu
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="FastAPI ilə inteqrasiya üçün qısa bir salam mesajı yaz."
        )

        print("\n✅ Gemini Cavabı Uğurlu!")
        print("Modelin Cavabı:")
        print("--------------------")
        print(response.text.strip())
        print("--------------------")

    except APIError as e:
        print(f"\n❌ API XƏTASI: Gemini API cavab vermədi. Açarı yoxlayın. Xəta: {e}")
    except Exception as e:
        print(f"\n❌ Gözlənilməz Xəta: {e}")