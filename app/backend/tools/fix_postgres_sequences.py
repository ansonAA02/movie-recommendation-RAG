import os
import sys
import psycopg2

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is required.")
    sys.exit(1)

def fix_sequences():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()

        tables = ["users", "movies", "ratings", "genres", "movie_genres", "view_history", "favorites", "likes", "comments", "user_profiles"]
        
        for table in tables:
            try:
                # Get the max id
                cur.execute(f"SELECT MAX(id) FROM {table};")
                max_id = cur.fetchone()[0]
                
                if max_id is not None:
                    # Reset the sequence to max_id + 1
                    seq_name = f"{table}_id_seq"
                    cur.execute(f"SELECT setval('{seq_name}', {max_id + 1}, false);")
                    print(f"✅ Reset sequence {seq_name} to {max_id + 1}")
                else:
                    print(f"⚠️ Table {table} is empty, skipping sequence reset.")
            except Exception as e:
                print(f"⚠️ Failed to reset sequence for {table}: {e}")
                
        cur.close()
        conn.close()
        print("\n🎉 All sequences fixed successfully!")
        
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")

if __name__ == "__main__":
    fix_sequences()
