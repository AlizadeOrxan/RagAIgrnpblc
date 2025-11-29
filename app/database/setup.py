# app/database/setup.py
from app.database.connection import get_db_connection


def create_tables():
    """
    Chat tarixçəsi üçün chat_history cədvəlini yaradır.
    """
    conn = get_db_connection()
    if conn is None:
        print("Cədvəllər yaradıla bilmədi: DB əlaqəsi yoxdur.")
        return

    cursor = conn.cursor()

    # Chat History Cədvəli üçün SQL sorğusu
    create_chat_history_table = """
    CREATE TABLE IF NOT EXISTS chat_history (
        id SERIAL PRIMARY KEY,
        session_id VARCHAR(255) NOT NULL,
        user_message TEXT NOT NULL,
        ai_response TEXT NOT NULL,
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    try:
        cursor.execute(create_chat_history_table)
        conn.commit()
        print("✅ chat_history cədvəli uğurla yaradıldı və ya mövcuddur.")
    except Exception as e:
        print(f"Cədvəl yaratma xətası: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    create_tables()