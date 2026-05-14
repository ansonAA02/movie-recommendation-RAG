# app/backend/services/retrieval.py
# ------------------------------------------------------------
# Hybrid Retriever with explicit baselines:
#   - popular
#   - content_only (ANN)
#   - hybrid_no_gnn (ANN + KG)
#   - full (ANN + KG + GNN)  <-- proposed model
# ------------------------------------------------------------

import os, sys, json, math, logging
import numpy as np
import faiss
from typing import List, Dict, Any, Optional, Iterable
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from neo4j import GraphDatabase
from datetime import datetime, timezone
logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Path setup (project-local imports)
# ------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))   # app/backend/services
BACKEND_DIR = os.path.dirname(CURRENT_DIR)                 # app/backend
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models import Rating, Movie, ViewHistory, Favorite, Like, Comment, Genre

# ------------------------------------------------------------
# ENV / Config
# ------------------------------------------------------------
def _resolve_backend_path(raw_path: Optional[str], *default_parts: str) -> str:
    candidate = str(raw_path or os.path.join(BACKEND_DIR, *default_parts)).strip()
    if os.path.isabs(candidate):
        return candidate
    return os.path.abspath(os.path.join(BACKEND_DIR, candidate))


EMB_PATH = _resolve_backend_path(os.getenv("MOVIE_EMB_PATH"), "embeddings", "movie_embeddings.npy")
ID_MAP_PATH = _resolve_backend_path(os.getenv("MOVIE_ID_MAP"), "embeddings", "id_map.json")
FAISS_INDEX_PATH = _resolve_backend_path(os.getenv("FAISS_INDEX_PATH"), "embeddings", "faiss.index")

GNN_EMB_PATH = _resolve_backend_path(os.getenv("GNN_EMB_PATH"), "embeddings", "embeddings1", "movie_subgraph_embeddings.npy")
GNN_ID_LIST_PATH = _resolve_backend_path(os.getenv("GNN_ID_LIST_PATH"), "embeddings", "embeddings1", "movie_subgraph_id_map.json")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


DEFAULT_ALPHA = _env_float("HYBRID_ALPHA", 0.6)
DEFAULT_GNN_WEIGHT = _env_float("HYBRID_GNN_WEIGHT", 0.3)
DEFAULT_KG_SIM_WEIGHT = _env_float("HYBRID_KG_SIM_WEIGHT", 0.3)  # weight for Neo4j SIMILAR_TO signal
VIEW_DECAY_TAU_DAYS = _env_float("VIEW_DECAY_TAU_DAYS", 30.0)  # larger => slower decay
FUSION_MODE = (os.getenv("HYBRID_FUSION_MODE", "manual") or "manual").strip().lower()
FUSION_WEIGHTS_PATH = os.getenv(
    "HYBRID_FUSION_WEIGHTS_PATH",
    os.path.join(BACKEND_DIR, "embeddings", "hybrid_ltr_weights.json"),
)
FUSION_WEIGHTS_PATH = _resolve_backend_path(FUSION_WEIGHTS_PATH)


def _get_weights(
    alpha: Optional[float] = None,
    gnn_weight: Optional[float] = None,
    kg_sim_weight: Optional[float] = None,
) -> tuple[float, float, float]:
    """Resolve weights from explicit overrides or environment defaults."""
    if alpha is not None:
        a = float(alpha)
    else:
        a = _env_float("HYBRID_ALPHA", DEFAULT_ALPHA)

    if gnn_weight is not None:
        gw = float(gnn_weight)
    else:
        gw = _env_float("HYBRID_GNN_WEIGHT", DEFAULT_GNN_WEIGHT)

    if kg_sim_weight is not None:
        ksw = float(kg_sim_weight)
    else:
        ksw = _env_float("HYBRID_KG_SIM_WEIGHT", DEFAULT_KG_SIM_WEIGHT)
    # keep weights in [0, 1] for stability
    a = max(0.0, min(1.0, a))
    gw = max(0.0, min(1.0, gw))
    ksw = max(0.0, min(1.0, ksw))
    return a, gw, ksw


def _resolve_manual_fusion_weights(
    alpha: float,
    gnn_weight: float,
) -> Dict[str, float]:
    ann_w = (1.0 - gnn_weight) * alpha
    kg_w = (1.0 - gnn_weight) * (1.0 - alpha)
    gnn_w = gnn_weight
    total = max(ann_w + kg_w + gnn_w, 1e-12)
    return {
        "ann": ann_w / total,
        "kg": kg_w / total,
        "gnn": gnn_w / total,
    }


def _manual_fusion_score(
    ann_s: float,
    kg_s: float,
    gnn_s: float,
    weights: Dict[str, float],
) -> float:
    return (
        float(weights.get("ann", 0.0)) * float(ann_s)
        + float(weights.get("kg", 0.0)) * float(kg_s)
        + float(weights.get("gnn", 0.0)) * float(gnn_s)
    )

# ------------------------------------------------------------
# Globals (loaded once)
# ------------------------------------------------------------
_embs = None
_id_map = None
_index = None
_driver = None

_gnn_embs = None
_gnn_movie_ids = None
_gnn_id_to_idx = None
_fusion_weights = None


# ------------------------------------------------------------
# Loaders
# ------------------------------------------------------------
def _ensure_loaded():
    global _embs, _id_map, _index, _driver
    global _gnn_embs, _gnn_movie_ids, _gnn_id_to_idx, _fusion_weights

    if _embs is None:
        if os.path.exists(EMB_PATH):
            _embs = np.load(EMB_PATH).astype("float32")
        else:
            logger.warning(f"Embedding file not found: {EMB_PATH}. Fallback to dummy embeddings.")
            _embs = np.zeros((1, 1536), dtype="float32")

    if _id_map is None:
        if os.path.exists(ID_MAP_PATH):
            with open(ID_MAP_PATH, "r", encoding="utf-8") as f:
                _id_map = _normalize_id_map(json.load(f))
        else:
            logger.warning(f"ID map file not found: {ID_MAP_PATH}. Fallback to empty map.")
            _id_map = {"id_to_idx": {}, "idx_to_id": {}}

    if _index is None:
        if os.path.exists(FAISS_INDEX_PATH):
            _index = faiss.read_index(FAISS_INDEX_PATH)
        else:
            faiss.normalize_L2(_embs)
            _index = faiss.IndexFlatIP(_embs.shape[1])
            _index.add(_embs)

    # GNN embeddings (optional)
    if _gnn_embs is None and os.path.exists(GNN_EMB_PATH):
        try:
            _gnn_embs = np.load(GNN_EMB_PATH).astype("float32")
            faiss.normalize_L2(_gnn_embs)
        except Exception:
            _gnn_embs = None

    if _gnn_movie_ids is None and os.path.exists(GNN_ID_LIST_PATH):
        try:
            with open(GNN_ID_LIST_PATH, "r", encoding="utf-8") as f:
                _gnn_movie_ids = [int(x) for x in json.load(f)]
            _gnn_id_to_idx = {mid: i for i, mid in enumerate(_gnn_movie_ids)}
        except Exception:
            _gnn_movie_ids = None
            _gnn_id_to_idx = None

    # Neo4j (optional)
    if _driver is None and NEO4J_URI and NEO4J_USER:
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as s:
                s.run("RETURN 1").consume()
            _driver = driver
        except Exception:
            _driver = None

    # Auto-fusion weights (optional)
    if _fusion_weights is None:
        _fusion_weights = _load_fusion_weights()


# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------
def _movie_idx_to_id(idx: int) -> int:
    return int(_id_map["idx_to_id"][str(int(idx))])


def _movie_id_to_idx(mid: int) -> Optional[int]:
    return int(_id_map["id_to_idx"][str(mid)]) if str(mid) in _id_map["id_to_idx"] else None


def _ann_search(user_emb: np.ndarray, top_k: int):
    vec = user_emb.astype("float32").reshape(1, -1)
    faiss.normalize_L2(vec)
    scores, idxs = _index.search(vec, top_k)
    return scores[0], idxs[0]


def _normalize(scores: Dict[int, float]) -> Dict[int, float]:
    vals = np.array(list(scores.values()), dtype=float)
    if vals.size == 0 or np.ptp(vals) == 0:
        return {k: 0.0 for k in scores}
    vmin, vmax = vals.min(), vals.max()
    return {k: float((v - vmin) / (vmax - vmin)) for k, v in scores.items()}


def _sigmoid(x: float) -> float:
    x = max(-50.0, min(50.0, float(x)))
    return 1.0 / (1.0 + math.exp(-x))


def _load_fusion_weights() -> Dict[str, float]:
    # Default weights mimic a moderate ANN-first hybrid when no trained model exists.
    defaults = {
        "bias": -1.2,
        "ann": 2.4,
        "kg": 1.6,
        "gnn": 1.8,
        "ann_kg": 0.8,
        "ann_gnn": 1.0,
        "kg_gnn": 0.6,
    }
    if not os.path.exists(FUSION_WEIGHTS_PATH):
        return defaults
    try:
        with open(FUSION_WEIGHTS_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return defaults
        weights = dict(defaults)
        for k in defaults.keys():
            if k in obj:
                try:
                    weights[k] = float(obj[k])
                except Exception:
                    pass
        # Safety: ANN/KG/GNN and interaction terms should be non-negative for stable ranking behavior.
        # If a trained file has obviously invalid signs, fall back to defaults.
        core_keys = ["ann", "kg", "gnn", "ann_kg", "ann_gnn", "kg_gnn"]
        if any(weights[k] < 0.0 for k in core_keys):
            return defaults
        return weights
    except Exception:
        return defaults


def _normalize_id_map(raw_map: Any) -> Dict[str, Dict[str, Any]]:
    """
    Normalize supported id-map formats into:
      {"id_to_idx": {movie_id(str): idx(int)}, "idx_to_id": {idx(str): movie_id(str)}}
    """
    if isinstance(raw_map, dict) and "id_to_idx" in raw_map and "idx_to_id" in raw_map:
        id_to_idx = {str(k): int(v) for k, v in (raw_map.get("id_to_idx") or {}).items()}
        idx_to_id = {str(k): str(v) for k, v in (raw_map.get("idx_to_id") or {}).items()}
        return {"id_to_idx": id_to_idx, "idx_to_id": idx_to_id}

    if isinstance(raw_map, dict):
        id_to_idx: Dict[str, int] = {}
        for k, v in raw_map.items():
            try:
                id_to_idx[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
        if id_to_idx:
            idx_to_id = {str(idx): mid for mid, idx in id_to_idx.items()}
            return {"id_to_idx": id_to_idx, "idx_to_id": idx_to_id}

    if isinstance(raw_map, list):
        idx_to_id = {str(i): str(mid) for i, mid in enumerate(raw_map)}
        id_to_idx = {str(mid): i for i, mid in enumerate(raw_map)}
        return {"id_to_idx": id_to_idx, "idx_to_id": idx_to_id}

    raise ValueError("Unsupported MOVIE_ID_MAP format")


def _auto_fusion_score(ann_s: float, kg_s: float, gnn_s: float) -> float:
    w = _fusion_weights or _load_fusion_weights()
    z = (
        w["bias"]
        + w["ann"] * ann_s
        + w["kg"] * kg_s
        + w["gnn"] * gnn_s
        + w["ann_kg"] * (ann_s * kg_s)
        + w["ann_gnn"] * (ann_s * gnn_s)
        + w["kg_gnn"] * (kg_s * gnn_s)
    )
    return _sigmoid(z)


# ------------------------------------------------------------
# KG helpers
# ------------------------------------------------------------
def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter / union) if union else 0.0


def _split_cast(cast: Optional[str], limit: int = 8) -> List[str]:
    if not cast:
        return []
    parts = [p.strip() for p in cast.split(",") if p.strip()]
    return parts[:limit]


def _as_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ------------------------------------------------------------
# Hybrid Retriever
# ------------------------------------------------------------
class HybridRetriever:
    """
    Modes:
      - popular
      - content_only
      - hybrid_no_gnn
      - full   (ANN + KG + GNN)
    """

    def __init__(self, db: Optional[Session] = None):
        _ensure_loaded()
        self.db = db

    # -------------------------------
    # User history
    # -------------------------------
    def user_history_movie_ids(self, user_id: int) -> List[int]:
        if self.db is None:
            return []

        weights: Dict[int, float] = {}

        # Use recency-weighted browsing signals (time decay) to reflect evolving preferences.
        # We cap the number of events for latency stability.
        views = (
            self.db.query(ViewHistory)
            .filter(ViewHistory.user_id == user_id)
            .order_by(ViewHistory.viewed_at.desc())
            .limit(500)
            .all()
        )
        ratings = self.db.query(Rating).filter(Rating.user_id == user_id).all()
        favs = self.db.query(Favorite).filter(Favorite.user_id == user_id).all()
        likes = self.db.query(Like).filter(Like.user_id == user_id).all()
        comments = self.db.query(Comment).filter(Comment.user_id == user_id).all()

        now = datetime.now(timezone.utc)
        tau = max(1e-6, float(VIEW_DECAY_TAU_DAYS))
        for v in views:
            # Exponential decay by recency (in days)
            t = _as_aware_utc(getattr(v, "viewed_at", None))
            if t is None:
                delta_days = 0.0
            else:
                delta = now - t
                delta_days = max(0.0, delta.total_seconds() / 86400.0)
            decay = math.exp(-delta_days / tau)

            # Optional: lighter weight for non-detail browsing
            vt = (getattr(v, "view_type", None) or "detail").lower()
            type_weight = 1.0 if vt == "detail" else 0.3

            w = 1.0 * type_weight * decay
            # keep a small floor so recent browsing still contributes even with noisy timestamps
            w = max(w, 0.05)
            weights[v.movie_id] = weights.get(v.movie_id, 0.0) + w
        for r in ratings:
            weights[r.movie_id] = weights.get(r.movie_id, 0.0) + (1.0 + max(0, r.rating - 3))
        for f in favs:
            weights[f.movie_id] = weights.get(f.movie_id, 0.0) + 3.0
        for l in likes:
            weights[l.movie_id] = weights.get(l.movie_id, 0.0) + 2.0
        for c in comments:
            weights[c.movie_id] = weights.get(c.movie_id, 0.0) + 2.0

        history: List[int] = []
        for mid, w in weights.items():
            history.extend([mid] * min(int(round(w)), 8))

        return history

    # -------------------------------
    # Embeddings
    # -------------------------------
    def _user_emb_text(self, mids: List[int]) -> np.ndarray:
        vecs = []
        weights = []
        for rank, mid in enumerate(mids):
            idx = _movie_id_to_idx(mid)
            if idx is not None:
                # Earlier items in weighted history should contribute more strongly.
                w = 1.0 / (1.0 + 0.03 * rank)
                vecs.append(_embs[idx] * w)
                weights.append(w)
        if not vecs:
            return np.mean(_embs, axis=0)
        total = max(float(sum(weights)), 1e-12)
        return np.sum(vecs, axis=0) / total

    def _user_emb_gnn(self, mids: List[int]) -> Optional[np.ndarray]:
        if _gnn_embs is None or _gnn_id_to_idx is None:
            return None
        vecs = []
        weights = []
        for rank, mid in enumerate(mids):
            if mid in _gnn_id_to_idx:
                w = 1.0 / (1.0 + 0.03 * rank)
                vecs.append(_gnn_embs[_gnn_id_to_idx[mid]] * w)
                weights.append(w)
        if not vecs:
            return None
        total = max(float(sum(weights)), 1e-12)
        return np.sum(vecs, axis=0) / total

    def _apply_hard_filters(self, query, constraints: Optional[Dict[str, Any]]):
        if self.db is None or not constraints:
            return query
        include_genres = [str(x).strip() for x in (constraints.get("include_genres") or []) if str(x).strip()]
        exclude_genres = [str(x).strip() for x in (constraints.get("exclude_genres") or []) if str(x).strip()]
        min_year = constraints.get("min_year")
        max_year = constraints.get("max_year")
        min_rating = constraints.get("min_rating")
        max_runtime = constraints.get("max_runtime")
        raw_languages = constraints.get("languages")
        if raw_languages in (None, []):
            raw_languages = constraints.get("language")
        if isinstance(raw_languages, str):
            languages = [raw_languages.strip()] if raw_languages.strip() else []
        else:
            languages = [str(x).strip() for x in (raw_languages or []) if str(x).strip()]
        countries = [str(x).strip() for x in (constraints.get("countries") or []) if str(x).strip()]

        if include_genres:
            query = query.filter(Movie.genres.any(func.lower(Genre.name).in_([g.lower() for g in include_genres])))
        if exclude_genres:
            query = query.filter(~Movie.genres.any(func.lower(Genre.name).in_([g.lower() for g in exclude_genres])))
        if isinstance(min_year, int):
            query = query.filter(Movie.year >= int(min_year))
        if isinstance(max_year, int):
            query = query.filter(Movie.year <= int(max_year))
        if isinstance(min_rating, (int, float)):
            query = query.filter(Movie.average_rating >= float(min_rating))
        if isinstance(max_runtime, int):
            query = query.filter(Movie.runtime <= int(max_runtime))
        if languages:
            if len(languages) == 1:
                query = query.filter(func.lower(Movie.language).like(f"%{languages[0].lower()}%"))
            else:
                query = query.filter(func.lower(Movie.language).in_([x.lower() for x in languages]))
        if countries:
            query = query.filter(func.lower(Movie.country).in_([x.lower() for x in countries]))
        return query

    def _multi_recall_candidates(
        self,
        history: List[int],
        ann_pairs: List[tuple[int, float]],
        constraints: Optional[Dict[str, Any]],
        limit: int,
    ) -> List[tuple[int, float]]:
        if self.db is None:
            return ann_pairs[:limit]

        seen_history = set(history or [])
        candidate_scores: Dict[int, float] = {}
        ann_seed_pairs = ann_pairs[: max(limit, 120)]
        if constraints:
            ann_seed_ids = [int(mid) for mid, _ in ann_seed_pairs]
            if ann_seed_ids:
                allowed_ann_ids = {
                    int(row.id)
                    for row in self._apply_hard_filters(self.db.query(Movie.id), constraints)
                    .filter(Movie.id.in_(ann_seed_ids))
                    .all()
                }
                ann_seed_pairs = [(mid, score) for mid, score in ann_seed_pairs if int(mid) in allowed_ann_ids]
        for mid, score in ann_seed_pairs:
            candidate_scores[mid] = max(candidate_scores.get(mid, 0.0), float(score) + 4.0)

        hist_movies = (
            self.db.query(Movie)
            .options(joinedload(Movie.genres))
            .filter(Movie.id.in_(list(set(history[:60]))))
            .all()
        )
        pref_genres: list[str] = []
        pref_directors: list[str] = []
        pref_actors: list[str] = []
        pref_years: list[int] = []
        pref_languages: list[str] = []
        pref_countries: list[str] = []
        for movie in hist_movies:
            pref_genres.extend([g.name for g in (movie.genres or []) if getattr(g, "name", None)])
            if getattr(movie, "director", None):
                pref_directors.append(str(movie.director))
            pref_actors.extend(_split_cast(getattr(movie, "cast", None), limit=4))
            if getattr(movie, "year", None):
                pref_years.append(int(movie.year))
            if getattr(movie, "language", None):
                pref_languages.append(str(movie.language))
            if getattr(movie, "country", None):
                pref_countries.append(str(movie.country))

        def _top(items: Iterable[Any], n: int) -> list[Any]:
            counts: Dict[Any, int] = {}
            for x in items:
                counts[x] = counts.get(x, 0) + 1
            return [k for k, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n]]

        genre_top = _top(pref_genres, 4)
        director_top = _top(pref_directors, 3)
        actor_top = _top(pref_actors, 5)
        year_lo = min(pref_years[-10:] or [0]) if pref_years else None
        year_hi = max(pref_years[-10:] or [0]) if pref_years else None
        language_top = _top(pref_languages, 2)
        country_top = _top(pref_countries, 2)

        def _add_rows(rows, bonus: float):
            for row in rows:
                candidate_scores[int(row.id)] = max(candidate_scores.get(int(row.id), 0.0), bonus)

        base_query = self.db.query(Movie).options(joinedload(Movie.genres))
        base_query = self._apply_hard_filters(base_query, constraints)

        if genre_top:
            rows = (
                base_query.join(Movie.genres)
                .filter(Genre.name.in_(genre_top))
                .order_by(Movie.rating_count.desc())
                .limit(limit)
                .all()
            )
            _add_rows(rows, 2.8)
        if director_top:
            rows = (
                self._apply_hard_filters(self.db.query(Movie), constraints)
                .filter(Movie.director.in_(director_top))
                .order_by(Movie.rating_count.desc())
                .limit(limit)
                .all()
            )
            _add_rows(rows, 2.4)
        if actor_top:
            actor_query = self._apply_hard_filters(self.db.query(Movie), constraints)
            actor_rows = []
            for actor in actor_top[:3]:
                actor_rows.extend(actor_query.filter(Movie.cast.ilike(f"%{actor}%")).limit(max(10, limit // 2)).all())
            _add_rows(actor_rows, 2.1)
        if year_lo is not None and year_hi is not None and year_lo > 0:
            rows = (
                self._apply_hard_filters(self.db.query(Movie), constraints)
                .filter(Movie.year >= max(1900, year_lo - 3), Movie.year <= year_hi + 3)
                .order_by(Movie.average_rating.desc().nullslast(), Movie.rating_count.desc())
                .limit(limit)
                .all()
            )
            _add_rows(rows, 1.6)
        if language_top:
            rows = (
                self._apply_hard_filters(self.db.query(Movie), constraints)
                .filter(func.lower(Movie.language).in_([x.lower() for x in language_top]))
                .order_by(Movie.rating_count.desc())
                .limit(limit)
                .all()
            )
            _add_rows(rows, 1.2)
        if country_top:
            rows = (
                self._apply_hard_filters(self.db.query(Movie), constraints)
                .filter(func.lower(Movie.country).in_([x.lower() for x in country_top]))
                .order_by(Movie.rating_count.desc())
                .limit(limit)
                .all()
            )
            _add_rows(rows, 1.1)

        popular_rows = (
            self._apply_hard_filters(self.db.query(Movie), constraints)
            .order_by(Movie.average_rating.desc().nullslast(), Movie.rating_count.desc())
            .limit(max(20, limit // 3))
            .all()
        )
        _add_rows(popular_rows, 0.8)

        merged = [(mid, score) for mid, score in candidate_scores.items() if mid not in seen_history]
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged[:limit]

    # -------------------------------
    # KG scoring
    # -------------------------------
    def _kg_scores_with_evidence(
        self,
        cand_ids: List[int],
        history_ids: List[int],
        kg_sim_weight: float,
    ) -> tuple[Dict[int, float], Dict[int, Dict[str, Any]]]:
        """
        Compute a knowledge-graph similarity score between candidate movies and user's history.

        Priority:
        1) Neo4j (if connected): Jaccard overlap over entity neighbors (Genre/Person) + optional SIMILAR_TO boost.
        2) SQL fallback: Jaccard overlap over (genres + director + actors) between candidate and history set.
        """
        if not cand_ids:
            return {}, {}

        # Default zeros
        scores: Dict[int, float] = {mid: 0.0 for mid in cand_ids}
        evidence: Dict[int, Dict[str, Any]] = {mid: {} for mid in cand_ids}

        # If no history, we can't personalize KG; keep zeros.
        hist_unique = [int(x) for x in dict.fromkeys(history_ids or [])]
        if not hist_unique:
            return scores, evidence

        # ---------------------------
        # Neo4j path (real KG)
        # ---------------------------
        if _driver is not None:
            try:
                # Cap history size for query cost (still stable for scoring)
                # Reduced from 50 -> 20 to avoid Neo4j MemoryPoolOutOfMemoryError
                hist_cap = hist_unique[:20]
                cypher = """
                MATCH (h:Movie)
                WHERE h.movie_id IN $hist_ids
                OPTIONAL MATCH (h)-[:HAS_GENRE|DIRECTED_BY|STARRED_BY]->(he)
                WITH collect(DISTINCT id(he)) AS histEntIds, $cand_ids AS candIds
                UNWIND candIds AS cid
                MATCH (c:Movie {movie_id: cid})
                OPTIONAL MATCH (c)-[:HAS_GENRE|DIRECTED_BY|STARRED_BY]->(ce)
                WITH cid, histEntIds, collect(DISTINCT id(ce)) AS candEntIds
                WITH
                    cid,
                    histEntIds,
                    candEntIds,
                    size([x IN candEntIds WHERE x IN histEntIds]) AS inter,
                    size(histEntIds) AS hSize,
                    size(candEntIds) AS cSize
                OPTIONAL MATCH (c)-[r:SIMILAR_TO]->(hm:Movie)
                WHERE hm.movie_id IN $hist_ids
                WITH cid, inter, hSize, cSize, hm.movie_id AS hm_id, coalesce(r.similarity, 0.0) AS sim
                ORDER BY sim DESC
                WITH cid, inter, hSize, cSize, collect({hm_id: hm_id, sim: sim})[0] AS best
                RETURN
                    cid AS movie_id,
                    CASE
                        WHEN (hSize + cSize - inter) = 0 THEN 0.0
                        ELSE toFloat(inter) / toFloat(hSize + cSize - inter)
                    END AS jaccard,
                    coalesce(best.sim, 0.0) AS sim,
                    best.hm_id AS sim_ref_movie_id
                """
                with _driver.session() as s:
                    rows = s.run(cypher, hist_ids=hist_cap, cand_ids=cand_ids).data()
                for r in rows:
                    mid = int(r["movie_id"])
                    j = float(r.get("jaccard") or 0.0)
                    sim = float(r.get("sim") or 0.0)
                    sim_ref = r.get("sim_ref_movie_id")
                    # Blend: entity overlap + SIMILAR_TO boost (both in [0,1] typically)
                    blended = (1.0 - kg_sim_weight) * j + kg_sim_weight * sim
                    if mid in scores:
                        scores[mid] = blended
                        evidence[mid] = {
                            "kg_jaccard": j,
                            "kg_similar_to": sim,
                            "kg_sim_ref_movie_id": int(sim_ref) if sim_ref is not None else None,
                            "kg_source": "neo4j",
                        }
                # Keep scores as-is (already normalized-ish), but normalize within candidate set for fusion stability.
                return _normalize(scores), evidence
            except Exception as e:
                # In offline eval, SQL fallback can be too slow and may trigger heavy ORM issues.
                # Return zero KG signal to keep pipeline stable and deterministic.
                logger.warning(f"Neo4j KG scoring failed, using zero-KG fallback: {e}")
                for mid in cand_ids:
                    evidence[mid] = {
                        "kg_jaccard": 0.0,
                        "kg_similar_to": 0.0,
                        "kg_sim_ref_movie_id": None,
                        "kg_source": "neo4j_error_zero_fallback",
                    }
                return _normalize(scores), evidence

        # ---------------------------
        # SQL fallback (KG-like via relational edges)
        # ---------------------------
        if self.db is None:
            for mid in cand_ids:
                evidence[mid] = {"kg_source": "none"}
            return scores, evidence

        try:
            all_ids = list(set(hist_unique) | set(cand_ids))
            movies = (
                self.db.query(Movie)
                .options(joinedload(Movie.genres))
                .filter(Movie.id.in_(all_ids))
                .all()
            )
            by_id = {m.id: m for m in movies}

            user_entities: set = set()
            for hid in hist_unique:
                m = by_id.get(hid)
                if not m:
                    continue
                for g in getattr(m, "genres", []) or []:
                    user_entities.add(f"genre:{getattr(g, 'name', '')}")
                if getattr(m, "director", None):
                    user_entities.add(f"director:{m.director}")
                for a in _split_cast(getattr(m, "cast", None)):
                    user_entities.add(f"actor:{a}")

            for cid in cand_ids:
                m = by_id.get(cid)
                if not m:
                    scores[cid] = 0.0
                    evidence[cid] = {"kg_source": "sql_fallback"}
                    continue
                cand_entities: set = set()
                for g in getattr(m, "genres", []) or []:
                    cand_entities.add(f"genre:{getattr(g, 'name', '')}")
                if getattr(m, "director", None):
                    cand_entities.add(f"director:{m.director}")
                for a in _split_cast(getattr(m, "cast", None)):
                    cand_entities.add(f"actor:{a}")
                j = _jaccard(user_entities, cand_entities)
                scores[cid] = j
                evidence[cid] = {
                    "kg_jaccard": j,
                    "kg_similar_to": 0.0,
                    "kg_sim_ref_movie_id": None,
                    "kg_source": "sql_fallback",
                }

            return _normalize(scores), evidence
        except Exception:
            for mid in cand_ids:
                evidence[mid] = {"kg_source": "sql_fallback_error"}
            return scores, evidence

    # -------------------------------
    # Baseline: Popularity
    # -------------------------------
    def _recommend_popular(self, top_k: int) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(Rating.movie_id, func.count(Rating.movie_id).label("cnt"))
            .group_by(Rating.movie_id)
            .order_by(func.count(Rating.movie_id).desc())
            .limit(top_k)
            .all()
        )
        return [{"movie_id": r.movie_id, "score": float(r.cnt)} for r in rows]

    # -------------------------------
    # Main API
    # -------------------------------
    def recommend(
        self,
        user_id: int,
        top_k: int = 10,
        ann_k: int = 150,
        mode: str = "full",
        alpha: Optional[float] = None,
        gnn_weight: Optional[float] = None,
        kg_sim_weight: Optional[float] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:

        if mode == "popular":
            return self._recommend_popular(top_k)

        history = self.user_history_movie_ids(user_id)
        user_emb = self._user_emb_text(history)
        user_emb_gnn = self._user_emb_gnn(history)

        ann_scores, ann_idxs = _ann_search(user_emb, ann_k)
        raw_ann_pairs = [(_movie_idx_to_id(i), float(s)) for i, s in zip(ann_idxs, ann_scores)]
        cand_pairs = self._multi_recall_candidates(
            history=history,
            ann_pairs=raw_ann_pairs,
            constraints=constraints,
            limit=max(ann_k, top_k * 12),
        )

        # Don't recommend already-interacted items (better UX + cleaner offline eval)
        seen = set(history or [])
        cand_pairs = [(mid, float(s)) for mid, s in cand_pairs if mid not in seen]
        cand_ids = [mid for mid, _ in cand_pairs]
        if not cand_ids:
            # Fallback to popular if ANN candidates are all seen or missing
            if constraints:
                return []
            return self._recommend_popular(top_k) if self.db is not None else []

        # ANN normalize
        a_norm = _normalize({mid: s for mid, s in cand_pairs})

        # Cap KG candidate size to avoid Neo4j OOM; we only need a reasonable pool for re-ranking
        KG_CAND_CAP = 150
        kg_cand_ids = cand_ids[:KG_CAND_CAP]

        if mode == "content_only":
            return sorted(
                [{"movie_id": mid, "score": a_norm[mid]} for mid in cand_ids],
                key=lambda x: x["score"],
                reverse=True
            )[:top_k]

        alpha_v, gnn_w_v, kg_sim_w_v = _get_weights(alpha=alpha, gnn_weight=gnn_weight, kg_sim_weight=kg_sim_weight)
        manual_fusion_weights = _resolve_manual_fusion_weights(alpha=alpha_v, gnn_weight=gnn_w_v)

        # KG score (Neo4j when available; SQL fallback otherwise) + evidence
        # Use capped candidate list to prevent Neo4j MemoryPoolOutOfMemoryError
        kg_scores, kg_evidence = self._kg_scores_with_evidence(
            cand_ids=kg_cand_ids,
            history_ids=history,
            kg_sim_weight=kg_sim_w_v,
        )
        # Pad missing candidates (beyond KG_CAND_CAP) with zero KG score
        for mid in cand_ids[KG_CAND_CAP:]:
            kg_scores[mid] = 0.0
            kg_evidence[mid] = {"kg_source": "beyond_kg_cap"}

        if mode == "hybrid_no_gnn":
            results = []
            for mid in cand_ids:
                score = (
                    alpha_v * a_norm[mid]
                    + (1 - alpha_v) * kg_scores.get(mid, 0.0)
                )
                row = {
                    "movie_id": mid,
                    "score": score,
                    "ann_score": a_norm[mid],
                    "kg_score": kg_scores.get(mid, 0.0),
                    "fusion_mode": "manual_weighted",
                    "fusion_weights": {"ann": alpha_v, "kg": 1.0 - alpha_v, "gnn": 0.0},
                }
                row.update(kg_evidence.get(mid, {}))
                results.append(row)
            return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]

        # GNN scores
        gnn_scores = {mid: 0.0 for mid in cand_ids}
        gnn_available = (
            user_emb_gnn is not None
            and _gnn_embs is not None
            and _gnn_id_to_idx is not None
        )
        if gnn_available:
            user_emb_gnn = user_emb_gnn / (np.linalg.norm(user_emb_gnn) + 1e-12)
            for mid in cand_ids:
                if mid in _gnn_id_to_idx:
                    mv = _gnn_embs[_gnn_id_to_idx[mid]]
                    gnn_scores[mid] = float(np.dot(mv, user_emb_gnn))
        gnn_scores = _normalize(gnn_scores)

        # FULL model
        use_auto_fusion = (mode == "full_auto") or (FUSION_MODE == "auto")
        results = []
        for mid in cand_ids:
            if use_auto_fusion:
                final = _auto_fusion_score(
                    ann_s=float(a_norm[mid]),
                    kg_s=float(kg_scores.get(mid, 0.0)),
                    gnn_s=float(gnn_scores.get(mid, 0.0)),
                )
                fusion_weights = {
                    "ann": float((_fusion_weights or {}).get("ann", 0.0)),
                    "kg": float((_fusion_weights or {}).get("kg", 0.0)),
                    "gnn": float((_fusion_weights or {}).get("gnn", 0.0)),
                }
            else:
                final = _manual_fusion_score(
                    ann_s=float(a_norm[mid]),
                    kg_s=float(kg_scores.get(mid, 0.0)),
                    gnn_s=float(gnn_scores.get(mid, 0.0)),
                    weights=manual_fusion_weights,
                )
                fusion_weights = dict(manual_fusion_weights)

            row = {
                "movie_id": mid,
                "score": final,
                "ann_score": a_norm[mid],
                "kg_score": kg_scores.get(mid, 0.0),
                "gnn_score": gnn_scores.get(mid, 0.0),
                "gnn_source": "embedding" if gnn_available else "unavailable",
                "fusion_mode": "auto_ltr" if use_auto_fusion else "manual_weighted",
                "fusion_weights": fusion_weights,
                "fusion_components": {
                    "ann": float(a_norm[mid]),
                    "kg": float(kg_scores.get(mid, 0.0)),
                    "gnn": float(gnn_scores.get(mid, 0.0)),
                },
            }
            row.update(kg_evidence.get(mid, {}))
            results.append(row)

        return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]
