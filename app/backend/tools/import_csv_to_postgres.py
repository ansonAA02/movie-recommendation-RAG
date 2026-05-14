import os
import sys
import csv
from datetime import datetime
from dotenv import load_dotenv

# 英文註解: Setup paths to import from backend modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

load_dotenv()

from database import Base, engine, SessionLocal
from sqlalchemy import text
from models import (
    User, Genre, Movie, Rating, Favorite, Like, ViewHistory, Comment, UserProfile, movie_genre_association
)

# 英文註解: Type conversion helpers
def to_int(v):
    return int(v) if v else None

def to_float(v):
    return float(v) if v else None

def to_bool(v):
    if not v: return False
    return v.lower() in ('1', 'true', 't', 'yes', 'y')

# 英文註解: Read CSV files safely
def read_csv(path):
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: (v if v is not None else "") for k, v in row.items()}

# 英文註解: Bulk insert mapped dictionaries for performance
def chunked_insert(db, model, data, chunk_size=200):
    chunk = []
    for row in data:
        chunk.append(row)
        if len(chunk) >= chunk_size:
            # 英文註解: Open a new transaction for each chunk to prevent long-running transaction drops
            try:
                db.bulk_insert_mappings(model, chunk)
                db.commit()
            except Exception as e:
                db.rollback()
                raise e
            chunk = []
            import time
            time.sleep(0.3) # 英文註解: longer pause to prevent connection drop
    if chunk:
        try:
            db.bulk_insert_mappings(model, chunk)
            db.commit()
        except Exception as e:
            db.rollback()
            raise e

def main():
    csv_dir = os.path.join(PROJECT_ROOT, "data", "DataCSV")
    if not os.path.isdir(csv_dir):
        print(f"Directory not found: {csv_dir}")
        return

    print("Creating tables if not exists...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 英文註解: Truncate existing tables to avoid duplicate key errors during import
        print("Truncating existing tables in Postgres...")
        tables = [
            "user_profiles", "comments", "likes", "favorites", "ratings", "view_history",
            "movie_genre", "movies", "genres", "users"
        ]
        for table in tables:
            try:
                db.execute(text(f'TRUNCATE TABLE "{table}" CASCADE;'))
            except Exception as e:
                db.rollback()
                print(f"Truncate failed for {table}, skipping. Error: {e}")
        db.commit()

        # 英文註解: Import Users
        path = os.path.join(csv_dir, "users.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = []
            for r in read_csv(path):
                data.append({
                    "id": to_int(r.get("id")),
                    "username": (r.get("username") or f"user_{r.get('id')}")[:50],
                    "email": (r.get("email") or f"user_{r.get('id')}@example.com")[:100],
                    "hashed_password": (r.get("hashed_password") or "")[:255],
                    "age": to_int(r.get("age")),
                    "gender": r.get("gender"),
                    "occupation": r.get("occupation")
                })
            chunked_insert(db, User, data)

        # 英文註解: Import Genres
        path = os.path.join(csv_dir, "genres.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = [{"id": to_int(r.get("id")), "name": (r.get("name") or "")[:50]} for r in read_csv(path)]
            chunked_insert(db, Genre, data)

        # 英文註解: Import Movies
        path = os.path.join(csv_dir, "movies.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = []
            for r in read_csv(path):
                imdb = r.get("imdb_id")
                data.append({
                    "id": to_int(r.get("id")),
                    "title": (r.get("title") or "Untitled")[:255],
                    "year": to_int(r.get("year")),
                    "imdb_id": (imdb[:20] if imdb else None),
                    "poster_url": (r.get("poster_url") or "")[:500],
                    "description": r.get("description"),
                    "director": (r.get("director") or "")[:255],
                    "cast": r.get("cast"),
                    "runtime": to_int(r.get("runtime")),
                    "language": (r.get("language") or "")[:100],
                    "country": (r.get("country") or "")[:100],
                    "average_rating": to_float(r.get("average_rating")) or 0.0,
                    "rating_count": to_int(r.get("rating_count")) or 0,
                    "view_count": to_int(r.get("view_count")) or 0,
                    "like_count": to_int(r.get("like_count")) or 0,
                    "favorite_count": to_int(r.get("favorite_count")) or 0,
                    "comment_count": to_int(r.get("comment_count")) or 0
                })
            chunked_insert(db, Movie, data)

        # 英文註解: Import Movie Genres (Association Table)
        path = os.path.join(csv_dir, "movie_genre.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = []
            for r in read_csv(path):
                mid = to_int(r.get("movie_id"))
                gid = to_int(r.get("genre_id"))
                if mid and gid:
                    data.append({"movie_id": mid, "genre_id": gid})
            
            chunk = []
            for row in data:
                chunk.append(row)
                if len(chunk) >= 200:
                    try:
                        db.execute(movie_genre_association.insert(), chunk)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        raise e
                    chunk = []
                    import time
                    time.sleep(0.3)
            if chunk:
                try:
                    db.execute(movie_genre_association.insert(), chunk)
                    db.commit()
                except Exception as e:
                    db.rollback()
                    raise e

        # 英文註解: Import Ratings
        path = os.path.join(csv_dir, "ratings.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = []
            for r in read_csv(path):
                data.append({
                    "id": to_int(r.get("id")),
                    "user_id": to_int(r.get("user_id")),
                    "movie_id": to_int(r.get("movie_id")),
                    "rating": to_float(r.get("rating"))
                })
            chunked_insert(db, Rating, data)

        # 英文註解: Import Favorites
        path = os.path.join(csv_dir, "favorites.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = [{"id": to_int(r.get("id")), "user_id": to_int(r.get("user_id")), "movie_id": to_int(r.get("movie_id"))} for r in read_csv(path)]
            chunked_insert(db, Favorite, data)

        # 英文註解: Import Likes
        path = os.path.join(csv_dir, "likes.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = [{"id": to_int(r.get("id")), "user_id": to_int(r.get("user_id")), "movie_id": to_int(r.get("movie_id"))} for r in read_csv(path)]
            chunked_insert(db, Like, data)
            
        # 英文註解: Import Comments
        path = os.path.join(csv_dir, "comments.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = []
            for r in read_csv(path):
                data.append({
                    "id": to_int(r.get("id")),
                    "user_id": to_int(r.get("user_id")),
                    "movie_id": to_int(r.get("movie_id")),
                    "content": r.get("content", ""),
                    "rating": to_float(r.get("rating"))
                })
            chunked_insert(db, Comment, data)

        # 英文註解: Import ViewHistory
        path = os.path.join(csv_dir, "view_history.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = []
            for r in read_csv(path):
                data.append({
                    "id": to_int(r.get("id")),
                    "user_id": to_int(r.get("user_id")),
                    "movie_id": to_int(r.get("movie_id")),
                    "view_duration": to_int(r.get("view_duration")) or 0,
                    "view_type": r.get("view_type", "detail")
                })
            chunked_insert(db, ViewHistory, data)

        # 英文註解: Import UserProfiles
        path = os.path.join(csv_dir, "user_profiles.csv")
        if os.path.exists(path):
            print(f"Importing {path}...")
            data = []
            for r in read_csv(path):
                data.append({
                    "id": to_int(r.get("id")),
                    "user_id": to_int(r.get("user_id")),
                    "preferred_genres": r.get("preferred_genres", "[]"),
                    "preferred_directors": r.get("preferred_directors", "[]"),
                    "preferred_actors": r.get("preferred_actors", "[]"),
                    "preferred_languages": r.get("preferred_languages", "[]"),
                    "preferred_countries": r.get("preferred_countries", "[]"),
                    "genre_distribution_json": r.get("genre_distribution_json", "{}"),
                    "director_distribution_json": r.get("director_distribution_json", "{}"),
                    "actor_distribution_json": r.get("actor_distribution_json", "{}"),
                    "recent_activity_score": to_float(r.get("recent_activity_score")) or 0.0,
                    "preference_drift_score": to_float(r.get("preference_drift_score")) or 0.0,
                    "min_rating_threshold": to_float(r.get("min_rating_threshold")) or 3.0,
                    "total_ratings": to_int(r.get("total_ratings")) or 0,
                    "total_likes": to_int(r.get("total_likes")) or 0,
                    "total_favorites": to_int(r.get("total_favorites")) or 0,
                    "total_views": to_int(r.get("total_views")) or 0,
                    "average_rating_given": to_float(r.get("average_rating_given")) or 0.0,
                    "profile_setup_completed": to_bool(r.get("profile_setup_completed")),
                    "setup_skipped": to_bool(r.get("setup_skipped"))
                })
            chunked_insert(db, UserProfile, data)

        # 英文註解: Update PostgreSQL auto-increment sequences so new inserts don't fail
        print("Updating PostgreSQL sequences...")
        tables_with_id = [
            "users", "genres", "movies", "ratings", "favorites", "likes", "comments", "view_history", "user_profiles"
        ]
        for table in tables_with_id:
            try:
                db.execute(text(f"SELECT setval('{table}_id_seq', (SELECT MAX(id) FROM {table}));"))
            except Exception as e:
                db.rollback()
                print(f"Sequence update skipped for {table}: {e}")
        db.commit()

        print("Import completed successfully!")
    except Exception as e:
        db.rollback()
        print("Error during import!")
        print(repr(e).encode('utf-8', 'replace').decode('utf-8'))
    finally:
        db.close()

if __name__ == "__main__":
    main()
