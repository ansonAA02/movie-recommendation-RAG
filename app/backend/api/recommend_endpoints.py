"""Recommendation endpoints augmented with KG subgraph retrieval.

All code and comments are in English per user rules.
"""

from __future__ import annotations

from typing import List, Dict, Any, Tuple
import os
import re
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
from models import Movie, Rating, ViewHistory, Genre
from auth import verify_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from services.neo4j_manager import Neo4jManager
from services.k_ragrec_complete import get_k_ragrec_recommender
from schemas import RecommendationResponse, RecommendationItem
from services.retrieval import HybridRetriever
import logging
logger = logging.getLogger(__name__)

load_dotenv()

router = APIRouter(prefix="/api/recommend", tags=["Recommendation (KG)"])

security = HTTPBearer()

# Create a global neo4j manager (soft failure if driver missing)
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")
neo4j_manager = Neo4jManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
try:
    neo4j_manager.connect()
except Exception:
    pass

# Create KG-RAG recommender instance
kg_rag_recommender = None


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """Extract and verify user id from bearer token."""
    token = credentials.credentials
    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


def _infer_user_preferences(db: Session, user_id: int, top_k: int = 5) -> Dict[str, Any]:
    from datetime import datetime, timedelta

    movies = []
    recent_views = (
        db.query(ViewHistory)
        .filter(ViewHistory.user_id == user_id)
        .order_by(ViewHistory.viewed_at.desc())
        .limit(200)
        .all()
    )
    if not recent_views:
        logger.debug(f"No recent views for user {user_id}")
    user_ratings = (
        db.query(Rating)
        .filter(Rating.user_id == user_id)
        .order_by(Rating.created_at.desc())
        .limit(100)
        .all()
    )
    rating_map = {r.movie_id: r.rating for r in user_ratings}

    genre_count = {}
    director_count = {}
    actor_count = {}
    year_preferences = {}
    genre_examples: Dict[str, str] = {}
    director_examples: Dict[str, str] = {}
    actor_examples: Dict[str, str] = {}
    year_examples: Dict[int, str] = {}

    movie_ids = [v.movie_id for v in recent_views]
    if movie_ids:
        movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        # ensure same order as recent_views if you care about time-decay ordering
        id_to_movie = {m.id: m for m in movies}
        ordered_movies = [id_to_movie.get(mid) for mid in movie_ids if id_to_movie.get(mid) is not None]
        for i, m in enumerate(ordered_movies):
            time_weight = 1.0 - (i * 0.01)
            time_weight = max(time_weight, 0.1)
            quality_weight = 1.0
            if m.id in rating_map:
                user_rating = rating_map[m.id]
                quality_weight = 1.0 + (user_rating - 3.0) * 0.2
                quality_weight = max(quality_weight, 0.1)
            combined_weight = time_weight * quality_weight
            for g in (m.genres or []):
                genre_count[g.name] = genre_count.get(g.name, 0) + combined_weight
                genre_examples.setdefault(g.name, m.title)
            if m.director:
                director_count[m.director] = director_count.get(m.director, 0) + combined_weight
                director_examples.setdefault(m.director, m.title)
            if m.cast:
                actors = [actor.strip() for actor in m.cast.split(',')[:5]]
                for actor in actors:
                    actor_count[actor] = actor_count.get(actor, 0) + combined_weight
                    actor_examples.setdefault(actor, m.title)
            if m.year:
                year_preferences[m.year] = year_preferences.get(m.year, 0) + combined_weight
                year_examples.setdefault(m.year, m.title)

    top_genres = [k for k, _ in sorted(genre_count.items(), key=lambda x: x[1], reverse=True)[:top_k]]
    top_directors = [k for k, _ in sorted(director_count.items(), key=lambda x: x[1], reverse=True)[:top_k]]
    top_actors = [k for k, _ in sorted(actor_count.items(), key=lambda x: x[1], reverse=True)[:top_k]]

    if year_preferences:
        sorted_years = sorted(year_preferences.items(), key=lambda x: x[1], reverse=True)
        preferred_years = [year for year, _ in sorted_years[:3]]
        avg_year = sum(year * weight for year, weight in sorted_years[:5]) / sum(weight for _, weight in sorted_years[:5])
    else:
        preferred_years = []
        avg_year = 2010

    recent_movies = {m.id: m.title for m in movies} if movies else {}
    total_preferences = len(genre_count) + len(director_count) + len(actor_count)
    unique_preferences = len(set(genre_count.keys()) | set(director_count.keys()) | set(actor_count.keys()))
    diversity_score = unique_preferences / max(total_preferences, 1)

    return {
        "genres": top_genres,
        "directors": top_directors,
        "actors": top_actors,
        "preferred_years": preferred_years,
        "avg_year": avg_year,
        "diversity_score": diversity_score,
        "recent_map": recent_movies,
        "rating_map": rating_map,
        "genre_examples": genre_examples,
        "director_examples": director_examples,
        "actor_examples": actor_examples,
        "year_examples": year_examples,
    }


def _simple_candidate_recall(db: Session, preferences: Dict[str, Any], limit: int = 50) -> List[int]:
    """Return a multi-source candidate pool instead of a thin genre/director fallback."""
    preferred_ids: List[int] = []

    top_genres: List[str] = preferences.get("genres", []) or []
    top_directors: List[str] = preferences.get("directors", []) or []
    top_actors: List[str] = preferences.get("actors", []) or []
    preferred_years: List[int] = preferences.get("preferred_years", []) or []

    if top_genres:
        genre_matched = (
            db.query(Movie)
            .join(Movie.genres)
            .filter(Genre.name.in_(top_genres))
            .order_by(Movie.rating_count.desc())
            .limit(limit)
            .all()
        )
        preferred_ids.extend([m.id for m in genre_matched])

    if top_directors:
        director_matched = (
            db.query(Movie)
            .filter(Movie.director.in_(top_directors))
            .order_by(Movie.rating_count.desc())
            .limit(limit)
            .all()
        )
        preferred_ids.extend([m.id for m in director_matched])

    if top_actors:
        for actor in top_actors[:3]:
            actor_matched = (
                db.query(Movie)
                .filter(Movie.cast.ilike(f"%{actor}%"))
                .order_by(Movie.rating_count.desc())
                .limit(max(10, limit // 2))
                .all()
            )
            preferred_ids.extend([m.id for m in actor_matched])

    if preferred_years:
        year_matched = (
            db.query(Movie)
            .filter(Movie.year >= min(preferred_years) - 3, Movie.year <= max(preferred_years) + 3)
            .order_by(Movie.average_rating.desc().nullslast(), Movie.rating_count.desc())
            .limit(limit // 2)
            .all()
        )
        preferred_ids.extend([m.id for m in year_matched])

    # Popular fallback
    popular = (
        db.query(Movie)
        .order_by(Movie.average_rating.desc().nullslast(), Movie.rating_count.desc())
        .limit(limit)
        .all()
    )
    preferred_ids.extend([m.id for m in popular])

    # Deduplicate while preserving order
    seen = set()
    ordered_unique = []
    for mid in preferred_ids:
        if mid not in seen:
            seen.add(mid)
            ordered_unique.append(mid)

    return ordered_unique[:limit]


def _parse_query_constraints(query_text: str | None) -> Dict[str, Any]:
    text = (query_text or "").strip().lower()
    constraints: Dict[str, Any] = {
        "include_genres": [],
        "exclude_genres": [],
        "min_year": None,
        "max_year": None,
        "min_rating": None,
        "max_runtime": None,
        "languages": [],
        "countries": [],
    }
    if not text:
        return constraints
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
    if len(years) >= 2:
        constraints["min_year"] = min(years[:2])
        constraints["max_year"] = max(years[:2])
    elif len(years) == 1:
        if any(k in text for k in ["after", "之後", "之后", "recent", "近年"]):
            constraints["min_year"] = years[0]
        elif any(k in text for k in ["before", "之前", "以前"]):
            constraints["max_year"] = years[0]
    runtime_match = re.search(r"(\d{2,3})\s*(?:分鐘|分钟|min|mins)", text)
    if runtime_match and any(k in text for k in ["內", "以内", "以內", "under", "within", "<="]):
        constraints["max_runtime"] = int(runtime_match.group(1))
    rating_match = re.search(r"(?:評分|评分|rating)\s*(?:>=|>|至少|at least)?\s*([0-5](?:\.\d)?)", text)
    if rating_match:
        constraints["min_rating"] = float(rating_match.group(1))
    elif any(k in text for k in ["高分", "high rating", "highly rated"]):
        constraints["min_rating"] = 4.0
    if "english" in text or "英文" in text:
        constraints["languages"] = ["english"]
    return constraints


def _fallback_recommendations(db: Session, user_id: int, k: int) -> List[Dict[str, Any]]:
    """Fallback recommendations when Neo4j is not available"""
    # Get user's viewed movies
    viewed_movies = db.query(ViewHistory.movie_id).filter(
        ViewHistory.user_id == user_id
    ).all()
    viewed_movie_ids = [m[0] for m in viewed_movies]
    
    # Get popular movies not viewed by user
    candidates = db.query(Movie).filter(
        ~Movie.id.in_(viewed_movie_ids)
    ).order_by(
        desc(Movie.average_rating),
        desc(Movie.rating_count)
    ).limit(k).all()
    
    results = []
    for movie in candidates:
        results.append({
            "movie_id": movie.id,
            "title": movie.title,
            "year": movie.year,
            "poster_url": movie.poster_url,
            "average_rating": movie.average_rating,
            "rating_count": movie.rating_count,
            "genres": [g.name for g in movie.genres],
            "runtime": movie.runtime,
            "language": movie.language,
            "country": movie.country,
            "director": movie.director,
            "cast": movie.cast,
            "description": movie.description,
            "imdb_id": movie.imdb_id,
            "view_count": movie.view_count,
            "like_count": movie.like_count,
            "favorite_count": movie.favorite_count,
            "comment_count": movie.comment_count,
            "kg_score": 0.0,
            "combined_score": movie.average_rating or 0.0,
            "reason": "Popular choice (Neo4j unavailable)"
        })
    
    return results


def _score_with_subgraph(preferences: Dict[str, Any], subgraph: Dict[str, Any]) -> Dict[str, Any]:
    """Compute an enhanced score and detailed textual reason from preferences and a subgraph."""
    genres = set(subgraph.get("genres", []) or [])
    directors = subgraph.get("directors", []) or []
    actors = subgraph.get("actors", []) or []
    similar_movies = subgraph.get("similar_movies", []) or []
    co_director_movies = subgraph.get("co_director_movies", []) or []
    co_actor_movies = subgraph.get("co_actor_movies", []) or []
    same_genre_movies = subgraph.get("same_genre_movies", []) or []
    rating = subgraph.get("rating", 0) or 0
    popularity_score = subgraph.get("popularity_score", 0) or 0
    year = subgraph.get("year", 0) or 0
    
    prefer_genres = set(preferences.get("genres", []))
    prefer_directors = set(preferences.get("directors", []))
    prefer_actors = set(preferences.get("actors", []))
    recent_map: Dict[int, str] = preferences.get("recent_map", {}) or {}
    
    # Calculate various match scores
    genre_overlap = len(genres & prefer_genres)
    director_hit = 1 if (prefer_directors & set(directors)) else 0
    actor_hit = 1 if (prefer_actors & set(actors)) else 0
    
    # Multi-hop relationship hits
    similar_hit_ids = list(set(similar_movies) & set(recent_map.keys()))
    similar_hit = 1 if similar_hit_ids else 0
    
    co_director_hit = 1 if any(mid in recent_map for mid in co_director_movies) else 0
    co_actor_hit = 1 if any(mid in recent_map for mid in co_actor_movies) else 0
    same_genre_hit = 1 if any(mid in recent_map for mid in same_genre_movies) else 0
    
    # Quality and recency bonuses
    quality_bonus = 0.5 if rating > 4.0 else 0.2 if rating > 3.0 else 0
    recency_bonus = 0.3 if year > 2010 else 0.1 if year > 2000 else 0
    popularity_bonus = popularity_score * 0.2
    
    # Calculate weighted score
    score = (3 * director_hit + 
             2.5 * actor_hit + 
             2 * genre_overlap + 
             1.5 * similar_hit + 
             1 * co_director_hit + 
             1 * co_actor_hit + 
             0.5 * same_genre_hit + 
             quality_bonus + 
             recency_bonus + 
             popularity_bonus)
    
    # Generate detailed explanation
    reason_parts: List[str] = []
    
    if director_hit and directors:
        matched_directors = list(set(directors) & prefer_directors)
        reason_parts.append(f"Directed by your favorite: {', '.join(matched_directors)}")
    
    if actor_hit and actors:
        matched_actors = list(set(actors) & prefer_actors)
        reason_parts.append(f"Stars your favorite actor: {', '.join(matched_actors[:2])}")
    
    if genre_overlap and genres:
        matched_genres = list(genres & prefer_genres)
        reason_parts.append(f"Matches your preferred genres: {', '.join(matched_genres[:3])}")
    
    if similar_hit and similar_hit_ids:
        matched_id = similar_hit_ids[0]
        similar_title = recent_map.get(matched_id, f"Movie {matched_id}")
        reason_parts.append(f"Similar to: {similar_title}")
    
    if co_director_hit:
        reason_parts.append("From a director whose other films you've enjoyed")
    
    if co_actor_hit:
        reason_parts.append("Features actors from movies you've liked")
    
    if rating > 4.5:
        reason_parts.append("Critically acclaimed")
    elif rating > 4.0:
        reason_parts.append("Highly rated")
    elif rating > 3.5:
        reason_parts.append("Well-received")
    
    if year > 2020:
        reason_parts.append("Recent release")
    elif year > 2015:
        reason_parts.append("Modern film")
    
    if popularity_score > 0.8:
        reason_parts.append("Popular choice")
    
    if not reason_parts:
        reason_parts.append("Recommended based on your viewing patterns")
    
    # Limit to 3 most relevant reasons
    reason = " | ".join(reason_parts[:3])
    
    return {"score": score, "reason": reason}


@router.get("/enhanced-hybrid", response_model=List[RecommendationItem])
def recommend_enhanced_hybrid(
    k: int = 10,
    query_text: str | None = None,  # 預留參數，目前主要依賴用戶歷史而非查詢詞
    constraints: Dict[str, Any] | None = None,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> List[RecommendationItem]:
    """
    Personalized recommendations using:
    - Text ANN user embedding (from interaction history)
    - KG similarity (Neo4j 或 SQL fallback)
    - GNN movie subgraph embeddings

    This是 NeoRAGRec 中「GNN + 用戶行為」的主力推薦端點，
    適合作為用戶登入後的 For You/Recommendations 頁面數據來源。
    """
    retriever = HybridRetriever(db=db)
    query_constraints = dict(constraints or _parse_query_constraints(query_text))
    hybrid = retriever.recommend(
        user_id=current_user_id,
        top_k=k,
        ann_k=max(150, k * 15),
        constraints=query_constraints,
    )

    movie_ids = [h["movie_id"] for h in hybrid]
    movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
    meta = {m.id: m for m in movies}

    # Batch fetch SIMILAR_TO reference movies (for traceable KG evidence)
    sim_ref_ids = sorted(
        {
            int(h.get("kg_sim_ref_movie_id"))
            for h in hybrid
            if h.get("kg_sim_ref_movie_id") is not None
        }
    )
    sim_ref_title: Dict[int, str] = {}
    if sim_ref_ids:
        ref_movies = db.query(Movie).filter(Movie.id.in_(sim_ref_ids)).all()
        sim_ref_title = {m.id: getattr(m, "title", str(m.id)) for m in ref_movies}

    # 獲取用戶偏好以生成推薦理由
    user_prefs = _infer_user_preferences(db, current_user_id)
    pref_genres = set(user_prefs.get("genres") or [])
    pref_directors = set(user_prefs.get("directors") or [])
    pref_actors = set(user_prefs.get("actors") or [])
    pref_years = set(user_prefs.get("preferred_years") or [])
    rating_map = user_prefs.get("rating_map") or {}
    genre_examples = user_prefs.get("genre_examples") or {}
    director_examples = user_prefs.get("director_examples") or {}
    actor_examples = user_prefs.get("actor_examples") or {}
    year_examples = user_prefs.get("year_examples") or {}

    items: List[RecommendationItem] = []
    for h in hybrid:
        mid = h["movie_id"]
        movie = meta.get(mid)
        if not movie:
            continue
        reason_parts: List[str] = []
        detail_parts: List[str] = []
        kg_score = float(h.get("kg_score", 0.0))
        gnn_score = float(h.get("gnn_score", 0.0))
        ann_score = float(h.get("ann_score", 0.0))
        fusion_mode = h.get("fusion_mode")
        fusion_weights = h.get("fusion_weights") if isinstance(h.get("fusion_weights"), dict) else {}
        fusion_components = h.get("fusion_components") if isinstance(h.get("fusion_components"), dict) else {}
        kg_jaccard = float(h.get("kg_jaccard", 0.0)) if h.get("kg_jaccard") is not None else 0.0
        kg_similar_to = float(h.get("kg_similar_to", 0.0)) if h.get("kg_similar_to") is not None else 0.0
        kg_sim_ref_movie_id = h.get("kg_sim_ref_movie_id")
        kg_source = h.get("kg_source")

        movie_genres = {g.name for g in getattr(movie, "genres", [])} if getattr(movie, "genres", None) else set()
        overlap_genres = sorted(movie_genres & pref_genres)
        if overlap_genres:
            for genre_name in overlap_genres[:2]:
                ref_title = genre_examples.get(genre_name)
                if ref_title:
                    detail_parts.append(f"Graph match: shares genre '{genre_name}' with your liked '{ref_title}'")
                else:
                    detail_parts.append(f"Graph match: aligns with your frequent genre '{genre_name}'")

        if movie.director and movie.director in pref_directors:
            ref_title = director_examples.get(movie.director)
            if ref_title:
                detail_parts.append(f"Graph match: shares director '{movie.director}' with '{ref_title}'")
            else:
                detail_parts.append(f"Graph match: director '{movie.director}' matches your preferences")

        if getattr(movie, "cast", None):
            cast_set = {a.strip() for a in movie.cast.split(",") if a.strip()}
            overlap_actors = sorted(cast_set & pref_actors)
            if overlap_actors:
                for actor in overlap_actors[:2]:
                    ref_title = actor_examples.get(actor)
                    if ref_title:
                        detail_parts.append(f"Graph match: shares actor '{actor}' with '{ref_title}'")
                    else:
                        detail_parts.append(f"Graph match: includes an actor you like ('{actor}')")

        if movie.year and movie.year in pref_years:
            ref_title = year_examples.get(movie.year)
            if ref_title:
                detail_parts.append(f"Graph match: same era as '{ref_title}' ({movie.year})")
            else:
                detail_parts.append(f"Year match: {movie.year} aligns with your frequently watched years")

        user_rating = rating_map.get(mid)
        if user_rating:
            detail_parts.append(f"You previously rated similar content {user_rating:.1f}/5")

        if ann_score > 0.3:
            reason_parts.append(f"High ANN similarity ({ann_score:.2f})")
        if kg_score > 0.2:
            reason_parts.append(f"Strong KG relevance ({kg_score:.2f})")
        if gnn_score > 0.25:
            reason_parts.append(f"GNN structural similarity ({gnn_score:.2f})")
            detail_parts.append("GNN: multi-hop graph structure resembles your recent liked items")

        score_line = f"Scores: ANN {ann_score:.2f} · KG {kg_score:.2f} · GNN {gnn_score:.2f}"
        detail_parts.append(score_line)
        if fusion_mode:
            detail_parts.append(
                "Fusion: "
                f"{fusion_mode} "
                f"(ann={float(fusion_weights.get('ann', 0.0)):.2f}, "
                f"kg={float(fusion_weights.get('kg', 0.0)):.2f}, "
                f"gnn={float(fusion_weights.get('gnn', 0.0)):.2f})"
            )
        if kg_source:
            detail_parts.append(f"KG source: {kg_source}")
        if kg_similar_to > 0:
            ref_id = int(kg_sim_ref_movie_id) if kg_sim_ref_movie_id is not None else None
            ref_title = sim_ref_title.get(ref_id) if ref_id is not None else None
            if ref_id is not None:
                detail_parts.append(f"Neo4j SIMILAR_TO: similarity {kg_similar_to:.3f} to your history movie {ref_id} ({ref_title or 'unknown'})")
            else:
                detail_parts.append(f"Neo4j SIMILAR_TO: similarity {kg_similar_to:.3f}")
        if kg_jaccard > 0:
            detail_parts.append(f"KG neighbor overlap (Jaccard) = {kg_jaccard:.3f}")

        if not detail_parts:
            detail_parts.append("Top result by hybrid retrieval score")
        if reason_parts:
            detail_parts.insert(0, "; ".join(reason_parts))

        reason = " · ".join(detail_parts)

        # Structured, traceable evidence for report/debug
        evidence = {
            "shared_genres": overlap_genres[:3],
            "shared_actors": overlap_actors[:3] if getattr(movie, "cast", None) else [],
            "shared_director": movie.director if movie.director and movie.director in pref_directors else None,
            "kg": {
                "source": kg_source,
                "jaccard": kg_jaccard,
                "similar_to": kg_similar_to,
                "sim_ref_movie_id": int(kg_sim_ref_movie_id) if kg_sim_ref_movie_id is not None else None,
                "sim_ref_title": sim_ref_title.get(int(kg_sim_ref_movie_id)) if kg_sim_ref_movie_id is not None else None,
            },
            "fusion": {
                "mode": fusion_mode,
                "weights": fusion_weights,
                "components": fusion_components,
            },
        }
        
        items.append(
            RecommendationItem(
                movie_id=mid,
                title=getattr(movie, "title", None),
                year=getattr(movie, "year", None),
                poster_url=getattr(movie, "poster_url", None),
                average_rating=getattr(movie, "average_rating", None),
                rating_count=getattr(movie, "rating_count", None),
                genres=[g.name for g in movie.genres] if getattr(movie, "genres", None) else [],
                runtime=getattr(movie, "runtime", None),
                language=getattr(movie, "language", None),
                director=getattr(movie, "director", None),
                cast=getattr(movie, "cast", None),
                description=getattr(movie, "description", None),
                kg_score=kg_score,
                ann_score=ann_score,
                gnn_score=gnn_score,
                combined_score=float(h.get("score", 0.0)),
                reason=reason,
                reason_details=detail_parts,
                evidence=evidence,
            )
        )

    # 已在 HybridRetriever.recommend 裡排序，這裡再截斷一次以防萬一
    items = sorted(items, key=lambda x: x.combined_score or 0.0, reverse=True)[:k]
    return items


@router.get("/with-kg", response_model=RecommendationResponse)
def recommend_with_kg(
    k: int = 10,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    # 1) infer preferences
    preferences = _infer_user_preferences(db, current_user_id)

    # 2) Use HybridRetriever to get ANN-based candidates (with simple KG fallback)
    retriever = HybridRetriever(db=db)
    hybrid_candidates = retriever.recommend(user_id=current_user_id, top_k=max(k, 50), ann_k=100)
    candidate_ids = [c["movie_id"] for c in hybrid_candidates]

    # 3) batch fetch movies metadata to avoid N+1
    movies = db.query(Movie).filter(Movie.id.in_(candidate_ids)).all()
    meta = {m.id: m for m in movies}

    items = []
    # Build a map from mid -> ann_score for fusion
    ann_map = {c["movie_id"]: c.get("ann_score", 0.0) for c in hybrid_candidates}
    for c in hybrid_candidates:
        mid = c["movie_id"]
        movie = meta.get(mid)
        # fetch subgraph if neo4j available
        sg = {}
        if getattr(neo4j_manager, "driver", None):
            try:
                sg = neo4j_manager.get_movie_subgraph(mid)
            except Exception:
                sg = {}
        scored = _score_with_subgraph(preferences, sg)
        # simple fusion: give ANN a certain weight, and subgraph heuristic a certain weight
        ann_score = float(ann_map.get(mid, 0.0))
        kg_score = float(scored.get("score", 0.0))
        # normalize fusion scheme as example (you can tune HYBRID_ALPHA / weights)
        from os import getenv
        alpha = float(getenv("HYBRID_ALPHA", 0.6))
        combined = alpha * ann_score + (1.0 - alpha) * kg_score

        item = RecommendationItem(
            movie_id=mid,
            title=getattr(movie, "title", None),
            year=getattr(movie, "year", None),
            poster_url=getattr(movie, "poster_url", None),
            average_rating=getattr(movie, "average_rating", None),
            rating_count=getattr(movie, "rating_count", None),
            genres=[g.name for g in movie.genres] if getattr(movie, "genres", None) else [],
            runtime=getattr(movie, "runtime", None),
            language=getattr(movie, "language", None),
            director=getattr(movie, "director", None),
            cast=getattr(movie, "cast", None),
            description=getattr(movie, "description", None),
            kg_score=kg_score,
            combined_score=combined,
            reason=scored.get("reason", "")
        )
        items.append(item)

    # sort and return top-k
    items = sorted(items, key=lambda x: x.combined_score, reverse=True)[:k]
    return RecommendationResponse(user_id=current_user_id, recommendations=items)


@router.get("/kg-rag", response_model=RecommendationResponse)
def recommend_with_kg_rag(
    k: int = 10,
    constraints: Dict[str, Any] | None = None,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    global kg_rag_recommender

    # initialize kg_rag_recommender if needed
    if kg_rag_recommender is None:
        neo4j_driver = getattr(neo4j_manager, "driver", None)
        if not neo4j_driver:
            try:
                neo4j_manager.connect()
                neo4j_driver = neo4j_manager.driver
            except Exception:
                neo4j_driver = None
        if neo4j_driver is None:
            # fallback to simple popular recommendations
            fallback = _fallback_recommendations(db, current_user_id, k)
            items = [RecommendationItem(movie_id=f["movie_id"], title=f["title"],
                        combined_score=f["combined_score"], reason=f["reason"]) for f in fallback]
            return RecommendationResponse(user_id=current_user_id, recommendations=items)

        kg_rag_recommender = get_k_ragrec_recommender(neo4j_driver)

    try:
        recommendations = kg_rag_recommender.generate_recommendations(current_user_id, db, k, constraints=constraints)
        # recommendations expected as list of dicts with movie_id, score, explanation
        movie_ids = [r["movie_id"] for r in recommendations]
        movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        meta = {m.id: m for m in movies}

        items = []
        for rec in recommendations:
            mid = rec.get("movie_id")
            movie = meta.get(mid)
            items.append(RecommendationItem(
                movie_id=mid,
                title=getattr(movie, "title", None),
                year=getattr(movie, "year", None),
                poster_url=getattr(movie, "poster_url", None),
                average_rating=getattr(movie, "average_rating", None),
                rating_count=getattr(movie, "rating_count", None),
                genres=[g.name for g in movie.genres] if getattr(movie, "genres", None) else [],
                runtime=getattr(movie, "runtime", None),
                language=getattr(movie, "language", None),
                director=getattr(movie, "director", None),
                cast=getattr(movie, "cast", None),
                description=getattr(movie, "description", None),
                kg_score=rec.get("score", 0.0),
                combined_score=rec.get("score", 0.0),
                reason=rec.get("explanation", "Recommended for you")
            ))
        return RecommendationResponse(user_id=current_user_id, recommendations=items)
    except Exception as e:
        # if kg-rag failed, fallback to hybrid retriever
        print(f"[KG-RAG Error] uid={current_user_id} error={str(e)}; falling back to hybrid")
        retriever = HybridRetriever(db=db)
        hybrid = retriever.recommend(user_id=current_user_id, top_k=k)
        movie_ids = [h["movie_id"] for h in hybrid]
        movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        meta = {m.id: m for m in movies}
        items = []
        for h in hybrid:
            mid = h["movie_id"]
            movie = meta.get(mid)
            items.append(RecommendationItem(
                movie_id=mid,
                title=getattr(movie, "title", None),
                combined_score=h.get("score", 0.0),
                reason="Fallback Hybrid retrieval"
            ))
        return RecommendationResponse(user_id=current_user_id, recommendations=items)


@router.get("/kg-rag/context")
def get_user_context(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get user context analysis for debugging and understanding recommendations."""
    global kg_rag_recommender
    
    if kg_rag_recommender is None:
        neo4j_driver = getattr(neo4j_manager, "driver", None)
        if not neo4j_driver:
            try:
                if neo4j_manager.connect():
                    neo4j_driver = neo4j_manager.driver
            except Exception:
                neo4j_driver = None
        if neo4j_driver is None:
            # Return basic context when Neo4j is not available
            return {
                "user_id": current_user_id,
                "cold_start": True,
                "activity_level": "unknown",
                "preference_diversity": 0.0,
                "recent_genres": [],
                "recent_directors": [],
                "recent_actors": [],
                "should_retrieve_kg": False,
                "note": "Neo4j not available - using basic context"
            }
        kg_rag_recommender = get_k_ragrec_recommender(neo4j_driver)
    
    try:
        # 需要傳入數據庫會話來分析用戶上下文
        context = kg_rag_recommender.adaptive_retriever.analyze_user_context(current_user_id, db)
        
        return {
            "user_id": context.user_id,
            "cold_start": context.cold_start,
            "activity_level": context.activity_level,
            "preference_diversity": context.preference_diversity,
            "recent_genres": context.recent_genres,
            "recent_directors": context.recent_directors,
            "recent_actors": context.recent_actors,
            "should_retrieve_kg": kg_rag_recommender.adaptive_retriever.should_retrieve_kg(context)
        }
        
    except AttributeError as e:
        # 如果 adaptive_retriever 不存在或方法簽名不同，返回基本上下文
        return {
            "user_id": current_user_id,
            "cold_start": True,
            "activity_level": "unknown",
            "preference_diversity": 0.0,
            "recent_genres": [],
            "recent_directors": [],
            "recent_actors": [],
            "should_retrieve_kg": False,
            "note": f"Context analysis not available: {str(e)}"
        }
    except Exception as e:
        # 返回基本上下文而不是拋出錯誤
        return {
            "user_id": current_user_id,
            "cold_start": True,
            "activity_level": "unknown",
            "preference_diversity": 0.0,
            "recent_genres": [],
            "recent_directors": [],
            "recent_actors": [],
            "should_retrieve_kg": False,
            "note": f"Error analyzing context: {str(e)}"
        }

