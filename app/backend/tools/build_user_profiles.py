#!/usr/bin/env python3
"""
Build enriched user profile CSV from DataCSV folder.

Inputs (best-effort, optional):
  - data/DataCSV/user_profiles.csv               (base, optional)
  - data/DataCSV/ratings.csv                     (user_id, movie_id, rating, created_at)
  - data/DataCSV/favorites.csv                   (user_id, movie_id, created_at)
  - data/DataCSV/likes.csv                       (user_id, movie_id, created_at)
  - data/DataCSV/view_history.csv                (user_id, movie_id, viewed_at, view_duration, view_type)
  - data/DataCSV/comments.csv                    (user_id, movie_id, content, rating, created_at)
  - data/DataCSV/movies.csv                      (id, title, year, director, cast, language, country, genres)

Output:
  - data/DataCSV/user_profiles_enriched.csv

The script is resilient to missing files and will compute
only what is possible from available inputs.
"""

from __future__ import annotations

import os
import sys
import json
import pandas as pd
from pathlib import Path
from typing import List, Dict

def _detect_data_dir() -> Path:
    """Prefer a data/DataCSV that actually contains core CSVs (ratings/movies)."""
    here = Path(__file__).resolve()
    probe_names = ["ratings.csv", "movies.csv", "user_profiles.csv", "movie_genre.csv"]

    # Build a candidate list walking up
    candidates = []
    for parent in [here] + list(here.parents):
        candidates.append(parent / "data" / "DataCSV")
    # 1) Prefer a candidate that has at least one key file
    for c in candidates:
        if c.exists() and any((c / n).exists() for n in probe_names):
            return c
    # 2) Otherwise, first existing data/DataCSV
    for c in candidates:
        if c.exists():
            return c
    # 3) Fallback: project-root style guess
    return here.parents[3] / "data" / "DataCSV"

DATADIR = _detect_data_dir()
OUT_CSV = DATADIR / "user_profiles_enriched.csv"


def read_csv_safe(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        print(f"[WARN] Missing file: {path}")
        return pd.DataFrame()
    try:
        return pd.read_csv(path, **kwargs)
    except Exception as e:
        print(f"[WARN] Failed to read {path}: {e}")
        return pd.DataFrame()


def parse_genres_col(series: pd.Series) -> pd.Series:
    """Parse genres from either JSON-like or pipe/comma strings."""
    def parse_one(x):
        if pd.isna(x):
            return []
        if isinstance(x, list):
            return x
        sx = str(x)
        # Try JSON first
        try:
            j = json.loads(sx)
            if isinstance(j, list):
                return [str(g).strip() for g in j if str(g).strip()]
        except Exception:
            pass
        # Fallback split
        for sep in ["|", ",", ";"]:
            if sep in sx:
                return [s.strip() for s in sx.split(sep) if s.strip()]
        return [sx.strip()] if sx.strip() else []

    return series.apply(parse_one)


def split_people(series: pd.Series) -> pd.Series:
    def parse_one(x):
        if pd.isna(x):
            return []
        sx = str(x)
        return [s.strip() for s in sx.split(",") if s.strip()]
    return series.apply(parse_one)


def topk_from_lists(series: pd.Series, k: int = 5) -> List[str]:
    counts: Dict[str, int] = {}
    for lst in series.dropna():
        for item in lst:
            counts[item] = counts.get(item, 0) + 1
    return [x for x, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:k]]


def build_profiles():
    DATADIR.mkdir(parents=True, exist_ok=True)

    base = read_csv_safe(DATADIR / "user_profiles.csv")
    ratings = read_csv_safe(DATADIR / "ratings.csv")
    favorites = read_csv_safe(DATADIR / "favorites.csv")
    likes = read_csv_safe(DATADIR / "likes.csv")
    views = read_csv_safe(DATADIR / "view_history.csv")
    comments = read_csv_safe(DATADIR / "comments.csv")
    movies = read_csv_safe(DATADIR / "movies.csv")
    movie_genre = read_csv_safe(DATADIR / "movie_genre.csv")
    genres_lut = read_csv_safe(DATADIR / "genres.csv")

    # Normalize movie metadata lists
    if not movies.empty:
        if "genres" in movies.columns:
            movies["genres_list"] = parse_genres_col(movies["genres"])  # list[str]
        else:
            movies["genres_list"] = [[] for _ in range(len(movies))]
        movies["director_str"] = movies.get("director", pd.Series(["" for _ in range(len(movies))]))
        movies["cast_list"] = split_people(movies.get("cast", pd.Series(["" for _ in range(len(movies))])))
        movies["language_str"] = movies.get("language", pd.Series(["" for _ in range(len(movies))]))
        movies["country_str"] = movies.get("country", pd.Series(["" for _ in range(len(movies))]))
        movies.rename(columns={"id": "movie_id"}, inplace=True)

    # If we have movie_genre + genres, build a reliable genres_list per movie
    if not movie_genre.empty and not genres_lut.empty:
        # Expect columns: movie_id, genre_id ; and genres: id, name
        if "id" in genres_lut.columns:
            genres_lut = genres_lut.rename(columns={"id": "genre_id"})
        if {"movie_id", "genre_id"} <= set(movie_genre.columns) and {"genre_id", "name"} <= set(genres_lut.columns):
            mg = movie_genre.merge(genres_lut[["genre_id", "name"]], on="genre_id", how="left")
            mg = mg.dropna(subset=["name"]).copy()
            # aggregate to list by movie_id
            mg_agg = mg.groupby("movie_id")["name"].apply(lambda s: sorted(set(s.tolist()))).reset_index()
            if not movies.empty and "movie_id" in movies.columns:
                movies = movies.merge(mg_agg, on="movie_id", how="left")
                # prefer the joined list when available
                movies["genres_list"] = movies["name"].combine_first(movies["genres_list"]).apply(lambda x: x if isinstance(x, list) else ([] if pd.isna(x) else [x]))
                movies = movies.drop(columns=["name"], errors="ignore")
            else:
                # Build a minimal movies df if movies.csv is missing
                movies = mg_agg.rename(columns={"name": "genres_list"})

    # Collect all user ids that appear anywhere
    user_ids = set()
    for df, col in [(base, "user_id"), (ratings, "user_id"), (favorites, "user_id"), (likes, "user_id"), (views, "user_id"), (comments, "user_id")]:
        if not df.empty and col in df.columns:
            user_ids.update(df[col].dropna().astype(int).tolist())

    rows = []
    for uid in sorted(user_ids):
        row = {"user_id": uid}

        # Totals
        def count(df: pd.DataFrame) -> int:
            if df.empty:
                return 0
            return int((df[df["user_id"] == uid].shape[0]) if "user_id" in df.columns else 0)

        total_ratings = count(ratings)
        total_likes = count(likes)
        total_favorites = count(favorites)
        total_views = count(views)
        total_comments = count(comments)

        row.update({
            "total_ratings": total_ratings,
            "total_likes": total_likes,
            "total_favorites": total_favorites,
            "total_views": total_views,
            "total_comments": total_comments,
        })

        # Average rating given
        if not ratings.empty and "rating" in ratings.columns:
            rsub = ratings[ratings["user_id"] == uid]
            row["average_rating_given"] = float(rsub["rating"].mean()) if not rsub.empty else 0.0
        else:
            row["average_rating_given"] = 0.0

        # Most rated year
        if not movies.empty and not ratings.empty and {"movie_id", "year"} <= set(movies.columns):
            merged = ratings.merge(movies[["movie_id", "year"]], on="movie_id", how="left")
            yr = merged[merged["user_id"] == uid]["year"].dropna().astype(int)
            row["most_rated_year"] = int(yr.mode().iloc[0]) if not yr.empty else None
        else:
            row["most_rated_year"] = None

        # Preferences (top-k from consumed movies)
        def topk_from_user(list_col: str, transform=None, k=5) -> List[str]:
            if movies.empty:
                return []
            # user movie set from ratings/favorites/views/comments (union)
            mids = set()
            for df in [ratings, favorites, views, comments]:
                if not df.empty and {"user_id", "movie_id"} <= set(df.columns):
                    mids.update(df[df["user_id"] == uid]["movie_id"].dropna().astype(int).tolist())
            if not mids:
                return []
            sub = movies[movies["movie_id"].isin(mids)].copy()
            col = sub[list_col]
            if transform:
                col = transform(col)
            return topk_from_lists(col, k=k)

        preferred_genres = topk_from_user("genres_list")
        preferred_directors = topk_from_user("director_str", transform=lambda s: s.apply(lambda x: [str(x)] if str(x).strip() else []))
        preferred_actors = topk_from_user("cast_list")
        preferred_languages = topk_from_user("language_str", transform=lambda s: s.apply(lambda x: [str(x)] if str(x).strip() else []))
        preferred_countries = topk_from_user("country_str", transform=lambda s: s.apply(lambda x: [str(x)] if str(x).strip() else []))

        row.update({
            "preferred_genres": json.dumps(preferred_genres, ensure_ascii=False),
            "preferred_directors": json.dumps(preferred_directors, ensure_ascii=False),
            "preferred_actors": json.dumps(preferred_actors, ensure_ascii=False),
            "preferred_languages": json.dumps(preferred_languages, ensure_ascii=False),
            "preferred_countries": json.dumps(preferred_countries, ensure_ascii=False),
        })

        # Thresholds/runtimes defaults
        row.update({
            "min_rating_threshold": 3.0,
            "max_runtime": None,
            "min_runtime": None,
        })

        # Onboarding flags default to completed if base has it
        from datetime import datetime, timezone
        # 強制設置為完成（不受 base 影響）
        profile_flags = {
            "profile_setup_completed": True,
            "setup_skipped": False,
            "setup_completed_at": datetime.now(timezone.utc).isoformat(),
        }
        row.update(profile_flags)

        rows.append(row)

    out = pd.DataFrame(rows)
    # Order columns (best-effort)
    preferred_cols = [
        "user_id",
        "preferred_genres", "preferred_directors", "preferred_actors", "preferred_languages", "preferred_countries",
        "min_rating_threshold", "max_runtime", "min_runtime",
        "total_ratings", "total_likes", "total_favorites", "total_views", "total_comments",
        "average_rating_given", "most_rated_year",
        "profile_setup_completed", "setup_skipped", "setup_completed_at",
    ]
    out = out[[c for c in preferred_cols if c in out.columns] + [c for c in out.columns if c not in preferred_cols]]
    out.to_csv(OUT_CSV, index=False)
    print(f"[OK] Wrote {OUT_CSV}")


if __name__ == "__main__":
    build_profiles()


