import csv
import os
import sys
from typing import Dict, Iterable, Optional

from dotenv import load_dotenv


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

load_dotenv()

try:
    from database import Base, engine, SessionLocal  # type: ignore
    from models import Genre, Movie, movie_genre_association  # type: ignore
except ImportError:
    from app.backend.database import Base, engine, SessionLocal  # type: ignore
    from app.backend.models import Genre, Movie, movie_genre_association  # type: ignore


def detect_new_movies_csv() -> str:
    env_path = os.getenv("NEW_MOVIES_CSV")
    if env_path and os.path.isfile(env_path):
        return env_path
    default_path = os.path.join(PROJECT_ROOT, "data", "DataCSV", "new_movies.csv")
    if os.path.isfile(default_path):
        return default_path
    raise FileNotFoundError("new_movies.csv not found. Set NEW_MOVIES_CSV or ensure data/DataCSV/new_movies.csv exists.")


def read_csv(path: str) -> Iterable[Dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
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


def split_genres(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    normalized = str(raw).replace(",", "|")
    return [x.strip() for x in normalized.split("|") if x.strip()]


def normalize_title(title: Optional[str]) -> str:
    return " ".join(str(title or "").strip().lower().split())


def get_existing_movie(db, movie_id: Optional[int], imdb_id: Optional[str], title: str, year: Optional[int]):
    if movie_id is not None:
        row = db.query(Movie).filter(Movie.id == movie_id).first()
        if row:
            return row
    imdb_norm = (imdb_id or "").strip()
    if imdb_norm:
        row = db.query(Movie).filter(Movie.imdb_id == imdb_norm).first()
        if row:
            return row
    title_norm = normalize_title(title)
    rows = db.query(Movie).filter(Movie.year == year).all() if year is not None else db.query(Movie).all()
    for row in rows:
        if normalize_title(getattr(row, "title", "")) == title_norm:
            return row
    return None


def get_or_create_genre(db, name: str) -> Genre:
    row = db.query(Genre).filter(Genre.name == name).first()
    if row:
        return row
    row = Genre(name=name)
    db.add(row)
    db.flush()
    return row


def ensure_movie_genre_link(db, movie_id: int, genre_id: int) -> bool:
    exists = db.execute(
        movie_genre_association.select().where(
            (movie_genre_association.c.movie_id == movie_id) &
            (movie_genre_association.c.genre_id == genre_id)
        )
    ).first()
    if exists:
        return False
    db.execute(movie_genre_association.insert().values(movie_id=movie_id, genre_id=genre_id))
    return True


def main() -> None:
    new_movies_csv = detect_new_movies_csv()
    print(f"Using new movies CSV: {new_movies_csv}")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    inserted_movies = 0
    skipped_movies = 0
    inserted_genres = 0
    inserted_links = 0

    try:
        for row in read_csv(new_movies_csv):
            movie_id = to_int(row.get("id"))
            title = (row.get("title") or "").strip()
            year = to_int(row.get("year"))
            imdb_id = (row.get("imdb_id") or "").strip() or None

            if not title:
                skipped_movies += 1
                continue

            existing = get_existing_movie(db, movie_id, imdb_id, title, year)
            if existing:
                skipped_movies += 1
                continue

            movie = Movie(
                id=movie_id,
                title=title,
                year=year,
                imdb_id=imdb_id,
                poster_url=(row.get("poster_url") or "").strip() or None,
                description=(row.get("description") or "").strip() or None,
                director=(row.get("director") or "").strip() or None,
                cast=(row.get("cast") or "").strip() or None,
                runtime=to_int(row.get("runtime")),
                language=(row.get("language") or "").strip() or None,
                country=(row.get("country") or "").strip() or None,
                average_rating=to_float(row.get("average_rating")) or 0.0,
                rating_count=to_int(row.get("rating_count")) or 0,
                view_count=to_int(row.get("view_count")) or 0,
                like_count=to_int(row.get("like_count")) or 0,
                favorite_count=to_int(row.get("favorite_count")) or 0,
            )
            db.add(movie)
            db.flush()
            inserted_movies += 1

            for genre_name in split_genres(row.get("genres")):
                before_id = None
                genre = db.query(Genre).filter(Genre.name == genre_name).first()
                if genre is None:
                    genre = get_or_create_genre(db, genre_name)
                    inserted_genres += 1
                else:
                    before_id = genre.id
                if ensure_movie_genre_link(db, movie.id, genre.id):
                    inserted_links += 1

        db.commit()
        print(f"Inserted movies: {inserted_movies}")
        print(f"Skipped movies: {skipped_movies}")
        print(f"Inserted genres: {inserted_genres}")
        print(f"Inserted movie-genre links: {inserted_links}")
    except Exception as e:
        db.rollback()
        print(f"Incremental import failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
