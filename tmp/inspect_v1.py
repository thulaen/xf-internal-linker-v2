import sqlite3
from pathlib import Path

db_path = r"C:\Users\goldm\OneDrive\Documents\GitHub\xf-internal-linker\data\linker.db"

def inspect():
    if not Path(db_path).exists():
        print(f"Error: {db_path} does not exist.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check counts
        cursor.execute("SELECT COUNT(*) as count FROM content_items")
        content_count = cursor.fetchone()["count"]
        print(f"Content items: {content_count}")

        cursor.execute("SELECT COUNT(*) as count FROM sentences")
        sentence_count = cursor.fetchone()["count"]
        print(f"Sentences: {sentence_count}")

        # Check settings
        cursor.execute("SELECT value FROM settings WHERE key = 'embedding_model'")
        row = cursor.fetchone()
        model = row["value"] if row else "unknown"
        print(f"Embedding model: {model}")

        # Check sync artifacts table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_artifacts'")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM sync_artifacts")
            rows = cursor.fetchall()
            print("\nSync Artifacts:")
            for r in rows:
                print(dict(r))

    except Exception as e:
        print(f"Error inspecting DB: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect()
