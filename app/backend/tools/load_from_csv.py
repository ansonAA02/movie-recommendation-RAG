import os
import sys
import csv
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Set

from dotenv import load_dotenv

# 允許在工具腳本中匯入後端模組
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
# 允許以多種位置執行（專案根目錄或 app/backend/tools 內）
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

load_dotenv()

# 嘗試相對與絕對導入，兼容不同執行位置
try:
    from database import Base, engine, SessionLocal  # type: ignore
    from models import (  # type: ignore
        User,
        Genre,
        Movie,
        Rating,
        Favorite,
        Like,
        ViewHistory,
        Comment,
        UserProfile,
        movie_genre_association,
    )
    from services.statistics_updater import statistics_updater  # type: ignore
except ImportError:
    from app.backend.database import Base, engine, SessionLocal  # type: ignore
    from app.backend.models import (  # type: ignore
        User,
        Genre,
        Movie,
        Rating,
        Favorite,
        Like,
        ViewHistory,
        Comment,
        UserProfile,
        movie_genre_association,
    )
    from app.backend.statistics_updater import statistics_updater  # type: ignore


def detect_csv_dir() -> str:
    # 優先讀取環境變數 CSV_DIR；否則使用專案根目錄 data/DataCSV
    env_dir = os.getenv("CSV_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    default_dir = os.path.join(PROJECT_ROOT, "data", "DataCSV")
    if os.path.isdir(default_dir):
        return default_dir
    raise FileNotFoundError("CSV directory not found. Set CSV_DIR or ensure data/DataCSV exists.")


def read_csv(path: str) -> Iterable[Dict[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: (v if v is not None else "") for k, v in row.items()}


def to_int(value: Optional[str]) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def to_float(value: Optional[str]) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def to_bool(value: Optional[str]) -> Optional[bool]:
    if value is None or value == "":
        return None
    v = value.strip().lower()
    if v in {"1", "true", "t", "yes", "y"}:
        return True
    if v in {"0", "false", "f", "no", "n"}:
        return False
    return None


def main() -> None:
    csv_dir = detect_csv_dir()
    print(f"Using CSV directory: {csv_dir}")

    # 確保資料表存在
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 先清空資料（注意外鍵順序）
        print("Clearing existing data...")
        db.query(Like).delete(synchronize_session=False)
        db.query(Favorite).delete(synchronize_session=False)
        db.query(Rating).delete(synchronize_session=False)
        db.query(Comment).delete(synchronize_session=False)
        db.query(ViewHistory).delete(synchronize_session=False)
        # 多對多關聯表
        db.execute(movie_genre_association.delete())
        # 主表
        db.query(Movie).delete(synchronize_session=False)
        db.query(Genre).delete(synchronize_session=False)
        db.query(UserProfile).delete(synchronize_session=False)
        db.query(User).delete(synchronize_session=False)
        db.commit()

        # 載入順序：users -> genres -> movies -> movie_genre -> ratings -> favorites -> likes -> comments -> user_profiles
        print("Importing users.csv (if present)...")
        users_csv = os.path.join(csv_dir, "users.csv")
        if os.path.isfile(users_csv):
            for row in read_csv(users_csv):
                user = User(
                    id=to_int(row.get("id")) or None,
                    username=row.get("username") or row.get("name") or f"user_{row.get('id')}",
                    email=row.get("email") or f"user_{row.get('id')}@example.com",
                    hashed_password=row.get("hashed_password") or row.get("password") or "",
                    age=to_int(row.get("age")),
                    gender=row.get("gender"),
                    occupation=row.get("occupation"),
                )
                db.add(user)
            db.commit()

        print("Importing genres.csv (if present)...")
        genres_csv = os.path.join(csv_dir, "genres.csv")
        if os.path.isfile(genres_csv):
            for row in read_csv(genres_csv):
                genre = Genre(
                    id=to_int(row.get("id")) or None,
                    name=row.get("name") or "Unknown",
                )
                db.add(genre)
            db.commit()

        print("Importing movies.csv (if present)...")
        movies_csv = os.path.join(csv_dir, "movies.csv")
        if os.path.isfile(movies_csv):
            for row in read_csv(movies_csv):
                # Normalize imdb_id: empty string should be treated as NULL to satisfy UNIQUE constraint
                raw_imdb = row.get("imdb_id")
                imdb_norm = (raw_imdb or None)
                if isinstance(imdb_norm, str) and imdb_norm.strip() == "":
                    imdb_norm = None
                movie = Movie(
                    id=to_int(row.get("id")) or None,
                    title=row.get("title") or row.get("name") or "Untitled",
                    year=to_int(row.get("year")),
                    imdb_id=imdb_norm,
                    poster_url=row.get("poster_url"),
                    description=row.get("description") or row.get("overview"),
                    director=row.get("director"),
                    cast=row.get("cast"),
                    runtime=to_int(row.get("runtime")),
                    language=row.get("language"),
                    country=row.get("country"),
                )
                db.add(movie)
            db.commit()

        print("Importing movie_genre.csv (if present)...")
        mg_csv = os.path.join(csv_dir, "movie_genre.csv")
        if os.path.isfile(mg_csv):
            for row in read_csv(mg_csv):
                mid = to_int(row.get("movie_id"))
                gid = to_int(row.get("genre_id"))
                if mid and gid:
                    db.execute(movie_genre_association.insert().values(movie_id=mid, genre_id=gid))
            db.commit()

        print("Importing ratings.csv (if present)...")
        ratings_csv = os.path.join(csv_dir, "ratings.csv")
        if os.path.isfile(ratings_csv):
            for row in read_csv(ratings_csv):
                rating = Rating(
                    id=to_int(row.get("id")) or None,
                    user_id=to_int(row.get("user_id")) or 0,
                    movie_id=to_int(row.get("movie_id")) or 0,
                    rating=to_float(row.get("rating")) or 0.0,
                )
                db.add(rating)
            db.commit()

        print("Importing favorites.csv (if present)...")
        favorites_csv = os.path.join(csv_dir, "favorites.csv")
        if os.path.isfile(favorites_csv):
            for row in read_csv(favorites_csv):
                fav = Favorite(
                    id=to_int(row.get("id")) or None,
                    user_id=to_int(row.get("user_id")) or 0,
                    movie_id=to_int(row.get("movie_id")) or 0,
                )
                db.add(fav)
            db.commit()

        print("Importing likes.csv (if present)...")
        likes_csv = os.path.join(csv_dir, "likes.csv")
        if os.path.isfile(likes_csv):
            for row in read_csv(likes_csv):
                like = Like(
                    id=to_int(row.get("id")) or None,
                    user_id=to_int(row.get("user_id")) or 0,
                    movie_id=to_int(row.get("movie_id")) or 0,
                )
                db.add(like)
            db.commit()

        print("Importing comments.csv (if present)...")
        comments_csv = os.path.join(csv_dir, "comments.csv")
        if os.path.isfile(comments_csv):
            for row in read_csv(comments_csv):
                c = Comment(
                    id=to_int(row.get("id")) or None,
                    user_id=to_int(row.get("user_id")) or 0,
                    movie_id=to_int(row.get("movie_id")) or 0,
                    content=row.get("content") or row.get("comment") or "",
                    rating=to_float(row.get("rating")),
                )
                db.add(c)
            db.commit()

        print("Importing user_profiles.csv (if present)...")
        up_csv = os.path.join(csv_dir, "user_profiles.csv")
        if os.path.isfile(up_csv):
            for row in read_csv(up_csv):
                up = UserProfile(
                    id=to_int(row.get("id")) or None,
                    user_id=to_int(row.get("user_id")) or 0,
                    preferred_genres=row.get("preferred_genres") or "[]",
                    preferred_directors=row.get("preferred_directors") or "[]",
                    preferred_actors=row.get("preferred_actors") or "[]",
                    preferred_languages=row.get("preferred_languages") or "[]",
                    preferred_countries=row.get("preferred_countries") or "[]",
                    min_rating_threshold=to_float(row.get("min_rating_threshold")) or 3.0,
                    max_runtime=to_int(row.get("max_runtime")),
                    min_runtime=to_int(row.get("min_runtime")),
                    total_ratings=to_int(row.get("total_ratings")) or 0,
                    total_likes=to_int(row.get("total_likes")) or 0,
                    total_favorites=to_int(row.get("total_favorites")) or 0,
                    total_views=to_int(row.get("total_views")) or 0,
                    total_comments=to_int(row.get("total_comments")) or 0,
                    average_rating_given=to_float(row.get("average_rating_given")) or 0.0,
                    most_rated_year=to_int(row.get("most_rated_year")),
                    profile_setup_completed=to_bool(row.get("profile_setup_completed")) or False,
                    setup_skipped=to_bool(row.get("setup_skipped")) or False,
                )
                db.add(up)
            db.commit()

        # 重算聚合統計
        print("Recomputing aggregates...")
        movie_ids: Set[int] = set(mid for (mid,) in db.query(Movie.id).all())
        user_ids: Set[int] = set(uid for (uid,) in db.query(User.id).all())
        for mid in movie_ids:
            statistics_updater.update_movie_statistics(db, mid)
        for uid in user_ids:
            statistics_updater.update_user_statistics(db, uid)

        print("CSV import completed.")

    except Exception as e:
        db.rollback()
        print(f"Import failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()


