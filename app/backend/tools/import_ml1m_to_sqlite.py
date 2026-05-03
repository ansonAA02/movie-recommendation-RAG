#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError
from passlib.context import CryptContext

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import Base, SessionLocal, engine  # type: ignore
from models import (  # type: ignore
    Comment,
    ExplanationRating,
    Favorite,
    Genre,
    Like,
    Movie,
    Rating,
    User,
    UserProfile,
    ViewHistory,
    movie_genre_association,
)
from services.statistics_updater import statistics_updater  # type: ignore

YEAR_RE = re.compile(r"\((\d{4})\)\s*$")
PAREN_RE = re.compile(r"\(([^()]+)\)")
RUNTIME_RE = re.compile(r"(\d+)")


def load_env_files() -> None:
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(PROJECT_ROOT / "app" / ".env")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--ml1m-dir", default=str(PROJECT_ROOT / "data" / "ml-1m"))
    p.add_argument("--enrich-metadata", action="store_true")
    p.add_argument("--metadata-cache", default=str(PROJECT_ROOT / "data" / "ml-1m" / "metadata_cache.json"))
    p.add_argument("--omdb-api-key", default="")
    p.add_argument("--tmdb-api-key", default="")
    p.add_argument("--metadata-sleep", type=float, default=0.03)
    p.add_argument("--unmatched-report", default=str(PROJECT_ROOT / "data" / "ml-1m" / "unmatched_movies_report.json"))
    p.add_argument("--only-ratings-profiles", action="store_true", help="Only refresh ratings + user_profiles")
    return p.parse_args()


def parse_year_from_title(title: str) -> Optional[int]:
    m = YEAR_RE.search(title or "")
    return int(m.group(1)) if m else None


def strip_year_suffix(title: str) -> str:
    return YEAR_RE.sub("", title or "").strip()


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def reorder_trailing_article(text: str) -> str:
    s = text or ""
    low = s.casefold()
    for suffix, prefix in [(", the", "The "), (", a", "A "), (", an", "An "), (", le", "Le "), (", la", "La "), (", il", "Il ")]:
        if low.endswith(suffix):
            return prefix + s[: -len(suffix)]
    return s


def strip_parentheticals(text: str) -> str:
    return normalize_spaces(PAREN_RE.sub("", text or ""))


def build_query_candidates(title: str) -> List[str]:
    raw = strip_year_suffix(title)
    out = [normalize_spaces(raw)]
    r = normalize_spaces(reorder_trailing_article(raw))
    if r and r not in out:
        out.append(r)
    if ":" in raw:
        p = normalize_spaces(raw.split(":", 1)[0])
        if p and p not in out:
            out.append(p)
    if " - " in raw:
        p = normalize_spaces(raw.split(" - ", 1)[0])
        if p and p not in out:
            out.append(p)
    sp = strip_parentheticals(raw)
    if sp and sp not in out:
        out.append(sp)
    for alias in [x.strip() for x in PAREN_RE.findall(raw) if x.strip()]:
        a = normalize_spaces(alias)
        if a and a not in out:
            out.append(a)
    return out[:8]


def parse_runtime(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    m = RUNTIME_RE.search(str(raw))
    return int(m.group(1)) if m else None


def parse_users(path: Path) -> List[Tuple[int, str, int, str]]:
    out = []
    with path.open("r", encoding="latin-1") as f:
        for line in f:
            p = line.rstrip("\n").split("::")
            if len(p) == 5:
                out.append((int(p[0]), p[1].strip(), int(p[2]), p[3].strip()))
    return out


def parse_movies(path: Path) -> List[Tuple[int, str, Optional[int], List[str]]]:
    out = []
    with path.open("r", encoding="latin-1") as f:
        for line in f:
            p = line.rstrip("\n").split("::")
            if len(p) == 3:
                out.append((int(p[0]), p[1].strip(), parse_year_from_title(p[1]), [g.strip() for g in p[2].split("|") if g.strip()]))
    return out


def parse_ratings(path: Path) -> List[Tuple[int, int, float, datetime]]:
    out = []
    with path.open("r", encoding="latin-1") as f:
        for line in f:
            p = line.rstrip("\n").split("::")
            if len(p) == 4:
                out.append((int(p[0]), int(p[1]), float(p[2]), datetime.fromtimestamp(int(p[3]), tz=timezone.utc)))
    return out


def movie_stats(ratings: List[Tuple[int, int, float, datetime]]) -> Dict[int, Dict[str, float]]:
    sums, cnts = defaultdict(float), defaultdict(int)
    for _, mid, r, _ in ratings:
        sums[mid] += r
        cnts[mid] += 1
    return {mid: {"average_rating": sums[mid] / cnts[mid], "rating_count": float(cnts[mid])} for mid in cnts}


def load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(path: Path, cache: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


TMDB_BASE = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"


def normalize_title_loose(title: str) -> str:
    t = strip_parentheticals(reorder_trailing_article(strip_year_suffix(title))).casefold()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    return normalize_spaces(t)


def tmdb_search(api_key: str, query: str, year: Optional[int]) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"api_key": api_key, "query": query, "include_adult": "false"}
    if year is not None:
        params["year"] = year
    r = requests.get(f"{TMDB_BASE}/search/movie", params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("results") or []


def tmdb_details(api_key: str, tmdb_id: int) -> Dict[str, Any]:
    params = {"api_key": api_key, "append_to_response": "credits,external_ids"}
    r = requests.get(f"{TMDB_BASE}/movie/{tmdb_id}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def tmdb_fetch(api_key: str, title: str, year: Optional[int], sleep_s: float) -> Dict[str, Any]:
    candidates = build_query_candidates(title)
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for q in candidates:
        results = tmdb_search(api_key, q, year)
        for res in results[:8]:
            r_title = str(res.get("title") or "")
            sim = difflib.SequenceMatcher(None, normalize_title_loose(title), normalize_title_loose(r_title)).ratio()
            r_year = None
            rd = str(res.get("release_date") or "")
            if len(rd) >= 4 and rd[:4].isdigit():
                r_year = int(rd[:4])
            score = sim
            if year is not None and r_year is not None:
                if abs(year - r_year) == 0:
                    score += 0.08
                elif abs(year - r_year) == 1:
                    score += 0.03
            scored.append((score, res))

    if not scored:
        return {}

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    details = tmdb_details(api_key, int(best["id"]))

    crew = details.get("credits", {}).get("crew", []) or []
    cast = details.get("credits", {}).get("cast", []) or []
    directors = [c.get("name") for c in crew if str(c.get("job", "")).lower() == "director" and c.get("name")]
    actors = [c.get("name") for c in cast[:8] if c.get("name")]

    external_ids = details.get("external_ids", {}) or {}
    poster_path = details.get("poster_path")

    out = {
        "imdb_id": external_ids.get("imdb_id") or None,
        "poster_url": f"{POSTER_BASE}{poster_path}" if poster_path else None,
        "description": details.get("overview") or None,
        "director": ", ".join(directors) if directors else None,
        "cast": ", ".join(actors) if actors else None,
        "runtime": details.get("runtime") or None,
        "language": details.get("original_language") or None,
        "country": None,
    }

    countries = details.get("production_countries") or []
    c_names = [c.get("name") for c in countries if c.get("name")]
    if c_names:
        out["country"] = ", ".join(c_names[:3])

    if sleep_s > 0:
        time.sleep(sleep_s)
    return out


def omdb_fetch(api_key: str, title: str, year: Optional[int], sleep_s: float) -> Dict[str, Any]:
    candidates = build_query_candidates(title)
    if not candidates:
        candidates = [strip_year_suffix(title)]

    for qtitle in candidates:
        q: Dict[str, Any] = {"apikey": api_key, "t": qtitle, "plot": "short"}
        if year is not None:
            q["y"] = year
        resp = requests.get("http://www.omdbapi.com/", params=q, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("Response", "")).lower() == "true":
            if sleep_s > 0:
                time.sleep(sleep_s)
            return data
        err = str(data.get("Error", ""))
        if err and any(x in err.lower() for x in ["invalid api key", "request limit reached", "too many results"]):
            raise RuntimeError(f"OMDb API error: {err}")

    # second pass without year constraint
    for qtitle in candidates:
        q = {"apikey": api_key, "t": qtitle, "plot": "short"}
        resp = requests.get("http://www.omdbapi.com/", params=q, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("Response", "")).lower() == "true":
            if sleep_s > 0:
                time.sleep(sleep_s)
            return data
        err = str(data.get("Error", ""))
        if err and any(x in err.lower() for x in ["invalid api key", "request limit reached", "too many results"]):
            raise RuntimeError(f"OMDb API error: {err}")

    return {}


def _pick_stronger_meta(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(primary)
    for k in ["imdb_id", "poster_url", "description", "director", "cast", "runtime", "language", "country"]:
        if not out.get(k) and secondary.get(k):
            out[k] = secondary.get(k)
    return out


def build_meta(
    movies: List[Tuple[int, str, Optional[int], List[str]]],
    enrich: bool,
    omdb_api_key: str,
    tmdb_api_key: str,
    cache_path: Path,
    sleep_s: float,
    unmatched_report_path: Path,
) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    if not enrich:
        return out

    if not omdb_api_key and not tmdb_api_key:
        raise ValueError("At least one key is required for enrichment: OMDb or TMDb")

    cache = load_cache(cache_path)
    hit = 0
    miss = 0
    ok = 0
    unmatched: List[Dict[str, Any]] = []

    if omdb_api_key:
        try:
            sanity = omdb_fetch(omdb_api_key, "Toy Story", 1995, 0.0)
            print(f"[Meta Check] OMDb sanity title found={bool(sanity)}")
        except Exception as e:
            print(f"[Meta Check] OMDb unavailable: {e}")
            omdb_api_key = ""

    if tmdb_api_key:
        try:
            sanity_tmdb = tmdb_fetch(tmdb_api_key, "Toy Story (1995)", 1995, 0.0)
            print(f"[Meta Check] TMDb sanity title found={bool(sanity_tmdb)}")
        except Exception as e:
            print(f"[Meta Check] TMDb unavailable: {e}")
            tmdb_api_key = ""

    for idx, (mid, title, year, _) in enumerate(movies, 1):
        key = f"{strip_year_suffix(title)}::{year or ''}"
        if key in cache:
            d = cache[key] or {}
            hit += 1
        else:
            d_omdb: Dict[str, Any] = {}
            d_tmdb: Dict[str, Any] = {}

            if omdb_api_key:
                try:
                    raw = omdb_fetch(omdb_api_key, title, year, sleep_s)
                    d_omdb = {
                        "imdb_id": raw.get("imdbID") or None,
                        "poster_url": None if raw.get("Poster") in (None, "", "N/A") else raw.get("Poster"),
                        "description": None if raw.get("Plot") in (None, "", "N/A") else raw.get("Plot"),
                        "director": None if raw.get("Director") in (None, "", "N/A") else raw.get("Director"),
                        "cast": None if raw.get("Actors") in (None, "", "N/A") else raw.get("Actors"),
                        "runtime": parse_runtime(raw.get("Runtime")),
                        "language": None if raw.get("Language") in (None, "", "N/A") else raw.get("Language"),
                        "country": None if raw.get("Country") in (None, "", "N/A") else raw.get("Country"),
                    }
                except Exception:
                    d_omdb = {}

            if tmdb_api_key:
                try:
                    d_tmdb = tmdb_fetch(tmdb_api_key, title, year, sleep_s)
                except Exception:
                    d_tmdb = {}

            d = _pick_stronger_meta(d_omdb, d_tmdb)
            cache[key] = d
            miss += 1

        if any(d.get(k) for k in ["imdb_id", "poster_url", "description", "director", "cast", "runtime", "language", "country"]):
            ok += 1
        else:
            unmatched.append({
                "movie_id": mid,
                "title": title,
                "year": year,
                "query_candidates": build_query_candidates(title),
            })

        out[mid] = {
            "imdb_id": d.get("imdb_id") or None,
            "poster_url": d.get("poster_url") or None,
            "description": d.get("description") or None,
            "director": d.get("director") or None,
            "cast": d.get("cast") or None,
            "runtime": d.get("runtime") or None,
            "language": d.get("language") or None,
            "country": d.get("country") or None,
        }

        if idx % 200 == 0 or idx == len(movies):
            print(f"[Meta Progress] {idx}/{len(movies)} | matched={ok} | cache_hit={hit} | fetched={miss}")

    save_cache(cache_path, cache)
    unmatched_report_path.parent.mkdir(parents=True, exist_ok=True)
    unmatched_report_path.write_text(json.dumps(unmatched, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[Meta Summary] matched={ok}/{len(movies)} ({(ok / max(1, len(movies))):.2%}), cache_hit={hit}, fetched={miss}")
    print(f"[Meta Summary] unmatched report: {unmatched_report_path}")
    return out


def insert_ratings_with_retry(db, chunk: List[Tuple[int, int, float, datetime]], retries: int = 8) -> None:
    for attempt in range(1, retries + 1):
        try:
            db.bulk_save_objects([Rating(user_id=u, movie_id=m, rating=r, created_at=ts) for u, m, r, ts in chunk])
            db.commit()
            return
        except OperationalError as e:
            db.rollback()
            msg = str(e).lower()
            if "database is locked" not in msg or attempt == retries:
                raise
            wait_s = min(2.0, 0.25 * attempt)
            print(f"[Ratings Retry] database locked, retry {attempt}/{retries} after {wait_s:.2f}s")
            time.sleep(wait_s)
def clear_all(db) -> None:
    db.query(ExplanationRating).delete(synchronize_session=False)
    db.query(Like).delete(synchronize_session=False)
    db.query(Favorite).delete(synchronize_session=False)
    db.query(Rating).delete(synchronize_session=False)
    db.query(Comment).delete(synchronize_session=False)
    db.query(ViewHistory).delete(synchronize_session=False)
    db.query(UserProfile).delete(synchronize_session=False)
    db.execute(movie_genre_association.delete())
    db.query(Movie).delete(synchronize_session=False)
    db.query(Genre).delete(synchronize_session=False)
    db.query(User).delete(synchronize_session=False)


def clear_ratings_profiles_only(db) -> None:
    db.query(ExplanationRating).delete(synchronize_session=False)
    db.query(Rating).delete(synchronize_session=False)
    db.query(UserProfile).delete(synchronize_session=False)


def main() -> None:
    load_env_files()
    args = parse_args()
    ml1m = Path(args.ml1m_dir)
    users_dat, movies_dat, ratings_dat = ml1m / "users.dat", ml1m / "movies.dat", ml1m / "ratings.dat"
    for p in (users_dat, movies_dat, ratings_dat):
        if not p.exists():
            raise FileNotFoundError(p)

    users = parse_users(users_dat)
    ratings = parse_ratings(ratings_dat)

    movies: List[Tuple[int, str, Optional[int], List[str]]] = []
    stats: Dict[int, Dict[str, float]] = {}
    meta: Dict[int, Dict[str, Any]] = {}

    if not args.only_ratings_profiles:
        movies = parse_movies(movies_dat)
        stats = movie_stats(ratings)
        omdb_key = (args.omdb_api_key or os.getenv("OMDB_API_KEY") or "").strip()
        tmdb_key = (args.tmdb_api_key or os.getenv("TMDB_API_KEY") or "").strip()
        if args.enrich_metadata:
            print(f"[Meta Config] OMDB_API_KEY loaded={bool(omdb_key)} | TMDB_API_KEY loaded={bool(tmdb_key)}")

        meta = build_meta(
            movies,
            bool(args.enrich_metadata),
            omdb_key,
            tmdb_key,
            Path(args.metadata_cache),
            float(args.metadata_sleep),
            Path(args.unmatched_report),
        )

    print(f"Parsed users={len(users)} movies={len(movies) if movies else 'skip'} ratings={len(ratings)}")
    print(f"[Source Check] unique users in ratings={len({u for u, _, _, _ in ratings})}, unique movies in ratings={len({m for _, m, _, _ in ratings})}")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.only_ratings_profiles:
            print("Clearing ratings + user_profiles only...")
            clear_ratings_profiles_only(db)
            db.commit()

            print("Import ratings...")
            batch = 50000
            total_batches = (len(ratings) + batch - 1) // batch
            for i in range(0, len(ratings), batch):
                ch = ratings[i:i + batch]
                insert_ratings_with_retry(db, ch)
                bidx = (i // batch) + 1
                if bidx % 2 == 0 or bidx == total_batches:
                    print(f"[Ratings Progress] batch={bidx}/{total_batches}, inserted={min((bidx * batch), len(ratings))}/{len(ratings)}")

            print("Recompute user_profiles from real interactions...")
            ids = [u for u, _, _, _ in users]
            for i, uid in enumerate(ids, 1):
                statistics_updater.update_user_statistics(db, uid)
                if i % 500 == 0:
                    print(f"  profile progress: {i}/{len(ids)}")
        else:
            print("Clearing existing SQLite data (tables kept)...")
            clear_all(db)
            db.commit()

            print("Import users...")
            user_objs = [
                User(id=u, username=f"ml1m_user_{u}", email=f"ml1m_user_{u}@example.com", hashed_password="ml1m_placeholder", age=age, gender=g, occupation=occ)
                for u, g, age, occ in users
            ]
            db.bulk_save_objects(user_objs)
            db.commit()
            print(f"[Import] users inserted={len(user_objs)}")

            print("Import genres...")
            all_g = sorted({g for _, _, _, gs in movies for g in gs})
            db.bulk_save_objects([Genre(name=g) for g in all_g])
            db.commit()
            gmap = {g.name: g.id for g in db.query(Genre).all()}
            print(f"[Import] genres inserted={len(all_g)}")

            print("Import movies...")
            mobjs, links = [], []
            used_imdb_ids: set[str] = set()
            duplicate_imdb_ids = 0
            for mid, title, year, gs in movies:
                st = stats.get(mid, {"average_rating": 0.0, "rating_count": 0.0})
                m = meta.get(mid, {})

                imdb_id = m.get("imdb_id")
                if imdb_id:
                    imdb_id = str(imdb_id).strip()
                    if imdb_id in used_imdb_ids:
                        duplicate_imdb_ids += 1
                        imdb_id = None
                    else:
                        used_imdb_ids.add(imdb_id)

                mobjs.append(Movie(
                    id=mid, title=title, year=year,
                    imdb_id=imdb_id, poster_url=m.get("poster_url"), description=m.get("description"),
                    director=m.get("director"), cast=m.get("cast"), runtime=m.get("runtime"),
                    language=m.get("language"), country=m.get("country"),
                    average_rating=float(st["average_rating"]), rating_count=int(st["rating_count"]),
                    view_count=0, like_count=0, favorite_count=0, comment_count=0,
                ))
                for g in gs:
                    gid = gmap.get(g)
                    if gid is not None:
                        links.append({"movie_id": mid, "genre_id": gid})
            db.bulk_save_objects(mobjs)
            db.commit()
            print(f"[Import] movies inserted={len(mobjs)}")
            if duplicate_imdb_ids > 0:
                print(f"[Import] duplicate imdb_id handled={duplicate_imdb_ids} (set to NULL to satisfy UNIQUE constraint)")
            if links:
                db.execute(movie_genre_association.insert(), links)
                db.commit()
            print(f"[Import] movie_genre links inserted={len(links)}")

            print("Import ratings...")
            batch = 50000
            total_batches = (len(ratings) + batch - 1) // batch
            for i in range(0, len(ratings), batch):
                ch = ratings[i:i + batch]
                insert_ratings_with_retry(db, ch)
                bidx = (i // batch) + 1
                if bidx % 2 == 0 or bidx == total_batches:
                    print(f"[Ratings Progress] batch={bidx}/{total_batches}, inserted={min((bidx * batch), len(ratings))}/{len(ratings)}")

            print("Recompute user_profiles from real interactions...")
            ids = [u for u, _, _, _ in users]
            for i, uid in enumerate(ids, 1):
                statistics_updater.update_user_statistics(db, uid)
                if i % 500 == 0:
                    print(f"  profile progress: {i}/{len(ids)}")

        db_users = db.query(User).count()
        db_movies = db.query(Movie).count()
        db_genres = db.query(Genre).count()
        db_ratings = db.query(Rating).count()
        db_profiles = db.query(UserProfile).count()

        print("[Final Counts]")
        print(f"  users: {db_users} (expected {len(users)})")
        print(f"  movies: {db_movies} (expected {len(movies) if movies else db_movies})")
        print(f"  genres: {db_genres} (expected {len(all_g) if not args.only_ratings_profiles else db_genres})")
        print(f"  ratings: {db_ratings} (expected {len(ratings)})")
        print(f"  user_profiles: {db_profiles} (expected {len(users)})")

        if db_ratings != len(ratings):
            raise RuntimeError("Import count mismatch detected for ratings. Please check logs above.")
        if not args.only_ratings_profiles and (db_users != len(users) or db_movies != len(movies)):
            raise RuntimeError("Import count mismatch detected. Please check logs above.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
