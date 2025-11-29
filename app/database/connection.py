# app/database/connection.py
import os
import psycopg2
from dotenv import load_dotenv

# .env faylını yükləyir
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

def get_db_connection():
    """
    PostgreSQL verilənlər bazası ilə əlaqə yaradır.
    """
    try:
        conn = psycopg2.connect(
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST, # Docker Compose-da xidmətin adı (db)
            port=DB_PORT,
            database=DB_NAME
        )
        return conn
    except psycopg2.Error as e:
        print(f"PostgreSQL ilə əlaqə xətası: {e}")
        return None