from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Literal, Tuple
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # mount static
from dotenv import load_dotenv  # Load .env for environment configuration
from contextlib import asynccontextmanager
import threading
import time  # Measure stage latencies
import csv   # Persist feedback events to CSV
import json  # Serialize feedback meta to JSON string for CSV
from collections import Counter, defaultdict  # Aggregations for metrics

from .services.recommender import PopularityRecommender
from .services.dataset import DatasetManager, DatasetConfig
from .services.evaluation import evaluate_popularity, evaluate_bpr, evaluate_cf_user, evaluate_cf_item, evaluate_lightgcn  # Add CF & LightGCN evaluations
from .services.bpr import BPRMF  # Import BPR model
from .services.llm_service import create_llm_service  # LLM service factory
from .services.collaborative_filtering import UserBasedCF, ItemBasedCF, LightGCNPlaceholder  # CF models
from datetime import datetime, timedelta  # JWT expiry handling
from jose import jwt  # JWT encode/decode
from passlib.context import CryptContext  # Password hashing
import numpy as np  # Vector operations for embeddings
from typing import Set  # Set type for seen items
from sentence_transformers import SentenceTransformer  # Text embedding model
# Try to import Annoy; fallback to NumPy-only search if not available (e.g., Windows without Build Tools)
try:
    from annoy import AnnoyIndex  # Approximate nearest neighbors index
    HAS_ANNOY = True  # Annoy is available
except Exception:
    AnnoyIndex = None  # type: ignore
    HAS_ANNOY = False  # Annoy is not available; we will fallback to NumPy search

# Global singletons (simple for demo)
DATASET_MANAGER: Optional[DatasetManager] = None
POPULARITY_MODEL: Optional[PopularityRecommender] = None
BPR_MODEL: Optional[BPRMF] = None  # Hold a trained BPR model when available
LLM_SERVICE = None  # Lazy-initialized LLM service
# Content-based retrieval globals
CONTENT_MODEL = None  # SentenceTransformer model instance (lazy)
CONTENT_INDEX: Optional[object] = None  # Annoy index instance when available; None otherwise
CONTENT_EMBED_DIM: int = 0  # Embedding dimensionality
CONTENT_ID2IDX: Dict[int, int] = {}  # Map item_id -> index in embedding matrix
CONTENT_IDX2ID: List[int] = []  # Reverse mapping from index to item_id
CONTENT_EMBEDDINGS: Optional[np.ndarray] = None  # Cached item embeddings
CONTENT_EMBEDDINGS_READY: bool = False
ANNOY_READY: bool = False
MAX_META_BYTES: int = 4096

# CF/GCN models (globals)
CF_USER_MODEL: Optional[UserBasedCF] = None
CF_ITEM_MODEL: Optional[ItemBasedCF] = None
LIGHTGCN_MODEL: Optional[LightGCNPlaceholder] = None

# Global lock to protect concurrent access to global models/resources
MODEL_LOCK = threading.RLock()

# Ensure static assets directory exists before mounting (avoid startup failure)
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# Create FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan to initialize and expose shared state via app.state.
    This keeps existing global singletons for backward compatibility while enabling
    a safer access pattern for future route modules."""
    # Eagerly initialize core resources to avoid None state when using lifespan
    try:
        _init_resources()  # Ensure DATASET_MANAGER and baseline models are ready
    except Exception:
        # Do not crash on startup; endpoints will return precise errors if needed
        pass

    # Sync current globals into app.state for unified access across routers
    try:
        app.state.DATASET_MANAGER = DATASET_MANAGER  # Dataset manager singleton
    except NameError:
        app.state.DATASET_MANAGER = None
    try:
        app.state.POPULARITY_MODEL = POPULARITY_MODEL  # Popularity recommender
    except NameError:
        app.state.POPULARITY_MODEL = None
    try:
        app.state.BPR_MODEL = BPR_MODEL  # BPR model (may be lazy/optional)
    except NameError:
        app.state.BPR_MODEL = None
    try:
        app.state.CF_USER_MODEL = CF_USER_MODEL  # User-based CF model
    except NameError:
        app.state.CF_USER_MODEL = None
    try:
        app.state.CF_ITEM_MODEL = CF_ITEM_MODEL  # Item-based CF model
    except NameError:
        app.state.CF_ITEM_MODEL = None
    try:
        app.state.CONTENT_MODEL = CONTENT_MODEL  # SentenceTransformer or None
    except NameError:
        app.state.CONTENT_MODEL = None
    try:
        app.state.CONTENT_INDEX = CONTENT_INDEX  # Annoy index or None
        app.state.CONTENT_EMBEDDINGS = CONTENT_EMBEDDINGS  # np.ndarray or None
        app.state.CONTENT_ID2IDX = CONTENT_ID2IDX
        app.state.CONTENT_IDX2ID = CONTENT_IDX2ID
        app.state.CONTENT_EMBED_DIM = CONTENT_EMBED_DIM
        app.state.CONTENT_EMBEDDINGS_READY = CONTENT_EMBEDDINGS_READY
        app.state.ANNOY_READY = ANNOY_READY
    except NameError:
        app.state.CONTENT_INDEX = None
        app.state.CONTENT_EMBEDDINGS = None
        app.state.CONTENT_ID2IDX = {}
        app.state.CONTENT_IDX2ID = {}
        app.state.CONTENT_EMBED_DIM = 0
        app.state.CONTENT_EMBEDDINGS_READY = False
        app.state.ANNOY_READY = False
    try:
        app.state.LLM_SERVICE = LLM_SERVICE  # LLM service helper
    except NameError:
        app.state.LLM_SERVICE = None

    # Yield control to application runtime
    yield

    # Optional cleanup on shutdown (currently no-op)
    # You can close files, flush metrics, or persist caches here if needed.

# Create FastAPI app instance with lifespan
app = FastAPI(title="FYP RecSys API", version="0.1.0", lifespan=lifespan)

# Configure CORS (allow UI dev server and configured origins)
cors_origins_env = os.getenv("FYP_CORS_ORIGINS", "")
if cors_origins_env.strip():
    # Parse comma-separated list from environment
    allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
else:
    # Sensible defaults for local development UIs
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets (demo UI)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize dataset and baseline models at startup
# @app.on_event("startup")  # removed to avoid double initialization; lifespan now invokes _init_resources()
def _init_resources() -> None:
    global DATASET_MANAGER, POPULARITY_MODEL, CF_USER_MODEL, CF_ITEM_MODEL, LIGHTGCN_MODEL

    # Load environment variables from app/.env if present
    try:
        app_dir = os.path.dirname(os.path.dirname(__file__))  # path to app/
        env_path = os.path.join(app_dir, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
    except Exception:
        # Silently continue if .env cannot be loaded to avoid startup failure
        pass

    # Dataset configuration with environment-configurable base_dir
    data_dir = os.getenv("FYP_DATA_DIR")
    if not data_dir:
        # Default fallback: navigate from app/backend/ to project root/data
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        data_dir = os.path.join(project_root, "data")
    else:
        # Convert relative path to absolute if needed
        if not os.path.isabs(data_dir):
            app_dir = os.path.dirname(os.path.dirname(__file__))  # Navigate to app/ directory
            data_dir = os.path.join(app_dir, data_dir)

    cfg = DatasetConfig(
        dataset_name=os.getenv("FYP_DATASET", "ml-100k"),
        base_dir=data_dir
    )

    # Initialize dataset and baseline model under lock
    with MODEL_LOCK:
        DATASET_MANAGER = DatasetManager(cfg)
        DATASET_MANAGER.ensure_ready()

        POPULARITY_MODEL = PopularityRecommender()
        POPULARITY_MODEL.fit(
            interactions=DATASET_MANAGER.interactions,
            item_meta=DATASET_MANAGER.item_meta,
        )
        # Initialize CF models
        CF_USER_MODEL = UserBasedCF(k_neighbors=50, min_overlap=2)
        CF_USER_MODEL.fit(DATASET_MANAGER.interactions)
        CF_ITEM_MODEL = ItemBasedCF(k_neighbors=50, min_overlap=2)
        CF_ITEM_MODEL.fit(DATASET_MANAGER.interactions)
        # LightGCN placeholder
        LIGHTGCN_MODEL = LightGCNPlaceholder()
        LIGHTGCN_MODEL.fit(DATASET_MANAGER.interactions)


def _get_content_model(model_name: str = "all-MiniLM-L6-v2"):
    """Lazily load SentenceTransformer and set embedding dimension."""
    global CONTENT_MODEL, CONTENT_EMBED_DIM
    if CONTENT_MODEL is None or getattr(CONTENT_MODEL, "_model_name", None) != model_name:
        CONTENT_MODEL = SentenceTransformer(model_name)
        setattr(CONTENT_MODEL, "_model_name", model_name)
        try:
            CONTENT_EMBED_DIM = int(CONTENT_MODEL.get_sentence_embedding_dimension())
        except Exception:
            CONTENT_EMBED_DIM = int(CONTENT_MODEL.encode(["test"], convert_to_numpy=True).shape[1])
    return CONTENT_MODEL


def _item_text(meta: Dict[str, Any]) -> str:
    """Compose text from item metadata (title, genres, overview) for embedding."""
    title = meta.get("title") or ""
    genres = meta.get("genres") or meta.get("genre") or []
    if isinstance(genres, (list, tuple)):
        genres = ", ".join(map(str, genres))
    genres = str(genres)
    desc = meta.get("overview") or meta.get("plot") or meta.get("description") or ""
    parts = [s for s in [title, genres, desc] if s]
    return " | ".join(parts) if parts else title


def _build_content_index(model_name: str = "all-MiniLM-L6-v2", n_trees: int = 50) -> None:
    """Compute embeddings for all items and build/update an Annoy index in memory.
    Falls back to only caching embeddings when Annoy is not available (Windows without Build Tools).
    """
    if DATASET_MANAGER is None:
        raise RuntimeError("Dataset not initialized")
    model = _get_content_model(model_name)

    # Prepare texts in stable order by item_id
    items = sorted(DATASET_MANAGER.item_meta.items(), key=lambda kv: kv[0])
    texts = [_item_text(meta) for _, meta in items]

    # Encode to normalized embeddings
    emb = model.encode(texts, batch_size=64, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
    dim = int(emb.shape[1])

    # Build Annoy index when available; otherwise, skip and use brute-force later
    index = None
    if 'HAS_ANNOY' in globals() and HAS_ANNOY and AnnoyIndex is not None:
        index = AnnoyIndex(dim, metric="angular")
        for idx, (iid, _) in enumerate(items):
            index.add_item(idx, emb[idx].tolist())
        index.build(int(n_trees))

    # Build id maps
    id2idx: Dict[int, int] = {}
    idx2id: List[int] = []
    for idx, (iid, _) in enumerate(items):
        id2idx[iid] = idx
        idx2id.append(iid)

    # Publish globals atomically
    global CONTENT_INDEX, CONTENT_EMBEDDINGS, CONTENT_ID2IDX, CONTENT_IDX2ID, CONTENT_EMBED_DIM, CONTENT_EMBEDDINGS_READY, ANNOY_READY
    with MODEL_LOCK:
        CONTENT_INDEX = index
        CONTENT_EMBEDDINGS = emb.astype(np.float32)
        CONTENT_ID2IDX = id2idx
        CONTENT_IDX2ID = idx2id
        CONTENT_EMBED_DIM = dim
        CONTENT_EMBEDDINGS_READY = True
        ANNOY_READY = index is not None


def _ensure_content_index(model_name: str = "all-MiniLM-L6-v2") -> None:
    """Ensure content index exists; build it if missing."""
    if not CONTENT_EMBEDDINGS_READY:
        _build_content_index(model_name)


# Build or rebuild the content index
@app.post("/content/index")
def content_index_build(
    model_name: str = Query("all-MiniLM-L6-v2", description="SentenceTransformer model name"),
    trees: int = Query(50, ge=10, le=200, description="Number of Annoy trees to build"),
) -> Dict[str, Any]:
    """Build or rebuild the content-based Annoy index using Sentence-Transformers embeddings.
    Returns metadata about the index for observability.
    """
    if DATASET_MANAGER is None:
        raise HTTPException(status_code=500, detail="Dataset not initialized")
    try:
        start = time.perf_counter()
        _build_content_index(model_name=model_name, n_trees=int(trees))
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return {
            "status": "ok",
            "model_name": model_name,
            "dim": int(CONTENT_EMBED_DIM),
            "n_items": len(CONTENT_IDX2ID),
            "trees": int(trees) if ('HAS_ANNOY' in globals() and HAS_ANNOY and CONTENT_INDEX is not None) else 0,
            "annoy_available": bool('HAS_ANNOY' in globals() and HAS_ANNOY),
            "elapsed_ms": round(elapsed_ms, 2),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"content_index_failed: {e}")


class RecommendRequest(BaseModel):
    user_id: Optional[int] = None
    k: int = 10


class RecommendItem(BaseModel):
    item_id: int
    score: float
    title: Optional[str] = None
    reason: Optional[str] = None


class RecommendResponse(BaseModel):
    items: List[RecommendItem]
    meta: Dict[str, Any]


# New: Feedback event model for POST /feedback
class FeedbackEvent(BaseModel):
    """Schema for a single feedback event posted from the UI.
    Extends with optional attribution fields to support metrics aggregation.
    """
    user_id: int
    item_id: int
    action: Literal[
        "impress", "click", "like", "dislike", "purchase", "rate", "comment", "favorite", "share", "view"
    ]
    ts: Optional[float] = None
    source: Optional[Literal["feed", "search", "detail", "chat", "push", "other"]] = None
    rec_model: Optional[str] = None
    position: Optional[int] = None
    page: Optional[str] = None
    session_id: Optional[str] = None
    ab: Optional[str] = None
    dwell_ms: Optional[int] = None
    score: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None


@app.on_event("startup")
def on_startup() -> None:
    """Deprecated startup hook kept as no-op for backward compatibility."""
    return None




@app.get("/dataset")
def dataset_info() -> Dict[str, Any]:
    """Get basic dataset statistics to verify data loading.
    Provides number of users, items, and interactions.
    """
    if DATASET_MANAGER is None:
        raise HTTPException(status_code=500, detail="Dataset not initialized")
    stats = DATASET_MANAGER.stats()
    return stats


@app.get("/recommend", response_model=RecommendResponse)
def recommend(
    user_id: Optional[int] = Query(None),
    k: int = Query(10, ge=1, le=100),
    model: str = Query("popularity", description="Which model to use: popularity, bpr, cf_user, cf_item, lightgcn, content"),
    rerank: Literal["none", "llm"] = Query("none", description="Rerank strategy: none or llm"),
    explain: bool = Query(False, description="Whether to generate explanations for top items"),
    dedupe: bool = Query(True, description="Whether to remove duplicates in the final list"),
    filter_seen: bool = Query(True, description="Whether to filter items already seen by the user"),
    llm_top_m: int = Query(10, ge=1, le=100, description="How many top items to let LLM reorder (Top-M)")
):
    """Return top-k recommendations with optional controls.
    Keeps a minimal implementation focusing on baseline models for stability.
    """
    if DATASET_MANAGER is None:
        raise HTTPException(status_code=500, detail="Dataset not initialized")

    if model not in {"popularity", "bpr", "cf_user", "cf_item", "lightgcn", "content"}:
        raise HTTPException(status_code=400, detail="Invalid model. Use 'popularity', 'bpr', 'cf_user', 'cf_item', 'lightgcn', or 'content'.")

    seen_map = DATASET_MANAGER.user2items if (filter_seen and user_id is not None) else None

    items: List[Tuple[int, float]] = []
    reason_text = None
    with MODEL_LOCK:
        if model == "popularity":
            if POPULARITY_MODEL is None:
                raise HTTPException(status_code=500, detail="Popularity model not initialized")
            user_seen_map = DATASET_MANAGER.user2items if (filter_seen and user_id is not None) else {}
            items = POPULARITY_MODEL.recommend(user_id=user_id, k=k, user_seen=user_seen_map)
            reason_text = "Popular overall" if user_id is None else "Popular among similar users"
        elif model == "bpr":
            if BPR_MODEL is None:
                raise HTTPException(status_code=400, detail="BPR model not trained. Call /train/bpr first.")
            items = BPR_MODEL.recommend(user_id=user_id or 0, k=k, seen=seen_map)
            reason_text = "Personalized by BPR"
        elif model == "cf_user":
            if CF_USER_MODEL is None:
                raise HTTPException(status_code=500, detail="CF user-based model not initialized")
            items = CF_USER_MODEL.recommend(user_id=user_id or 0, k=k, seen=seen_map)
            reason_text = "User-based CF personalization"
        elif model == "cf_item":
            if CF_ITEM_MODEL is None:
                raise HTTPException(status_code=500, detail="CF item-based model not initialized")
            items = CF_ITEM_MODEL.recommend(user_id=user_id or 0, k=k, seen=seen_map)
            reason_text = "Item-based CF personalization"
        elif model == "content":
            _ensure_content_index()
            if CONTENT_EMBEDDINGS is None or not CONTENT_IDX2ID:
                raise HTTPException(status_code=500, detail="Content embeddings not available")
            user_seen: Set[int] = DATASET_MANAGER.user2items.get(user_id, set()) if (user_id is not None) else set()
            profile_vec: Optional[np.ndarray] = None
            if user_seen:
                vecs = []
                for iid in user_seen:
                    idx = CONTENT_ID2IDX.get(iid)
                    if idx is not None:
                        vecs.append(CONTENT_EMBEDDINGS[idx])
                if vecs:
                    profile_vec = np.mean(np.stack(vecs, axis=0), axis=0)
                    norm = np.linalg.norm(profile_vec)
                    if norm > 0:
                        profile_vec = profile_vec / norm
            if profile_vec is None:
                profile_vec = CONTENT_EMBEDDINGS.mean(axis=0)
                norm = np.linalg.norm(profile_vec)
                if norm > 0:
                    profile_vec = profile_vec / norm

            sims = (CONTENT_EMBEDDINGS @ profile_vec.astype(np.float32))
            if filter_seen and user_id is not None:
                for iid in user_seen:
                    idx = CONTENT_ID2IDX.get(iid)
                    if idx is not None:
                        sims[idx] = -1e9
            top_idx = np.argpartition(sims, -k)[-k:]
            top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]
            items = [(CONTENT_IDX2ID[int(i)], float(sims[int(i)])) for i in top_idx]
            reason_text = "Content similarity"
        else:
            if LIGHTGCN_MODEL is None:
                raise HTTPException(status_code=500, detail="LightGCN model not initialized")
            items = LIGHTGCN_MODEL.recommend(user_id=user_id or 0, k=k, seen=seen_map)
            reason_text = "Graph-based personalization"

    enriched: List[RecommendItem] = []
    for item_id, score in items:
        title = DATASET_MANAGER.item_meta.get(item_id, {}).get("title", f"Item {item_id}")
        enriched.append(RecommendItem(item_id=item_id, score=float(score), title=title, reason=reason_text))

    if dedupe:
        seen_ids = set()
        deduped: List[RecommendItem] = []
        for it in enriched:
            if it.item_id not in seen_ids:
                deduped.append(it)
                seen_ids.add(it.item_id)
        enriched = deduped

    return RecommendResponse(
        items=enriched[:k],
        meta={
            "model": model,
            "dataset": DATASET_MANAGER.cfg.dataset_name,
            "user_id": user_id,
            "k": k,
            "policies": {"dedupe": bool(dedupe), "filter_seen": bool(filter_seen)},
        },
    )


@app.post("/feedback")
def submit_feedback(event: FeedbackEvent) -> Dict[str, Any]:
    """Accept a single user feedback event and append it to a CSV file with basic sanitization."""
    if DATASET_MANAGER is None:
        raise HTTPException(status_code=500, detail="Dataset not initialized")

    base_root = getattr(DATASET_MANAGER, "base_root", None) or os.path.dirname(DATASET_MANAGER.root)
    feedback_dir = os.path.join(base_root, "feedback")
    os.makedirs(feedback_dir, exist_ok=True)
    csv_path = os.path.join(feedback_dir, "events.csv")

    def _sanitize_str(v: Optional[str], max_len: int = 128) -> Optional[str]:
        if v is None:
            return None
        v = str(v).replace("\r", " ").replace("\n", " ").replace("\t", " ")
        return v[:max_len]

    meta_obj = event.meta or {}
    try:
        meta_str = json.dumps(meta_obj, ensure_ascii=False)
    except Exception:
        meta_str = "{}"
    if len(meta_str.encode("utf-8")) > MAX_META_BYTES:
        raise HTTPException(status_code=400, detail="meta too large")

    ts = event.ts if event.ts is not None else time.time()
    row = {
        "ts": ts,
        "user_id": int(event.user_id),
        "item_id": int(event.item_id),
        "action": event.action,
        "source": event.source,
        "rec_model": _sanitize_str(event.rec_model, 64),
        "position": int(event.position) if event.position is not None else None,
        "page": _sanitize_str(event.page, 128),
        "session_id": _sanitize_str(event.session_id, 128),
        "ab": _sanitize_str(event.ab, 32),
        "dwell_ms": int(event.dwell_ms) if event.dwell_ms is not None else None,
        "score": float(event.score) if event.score is not None else None,
        "meta": meta_str,
    }

    file_exists = os.path.exists(csv_path)
    try:
        with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "ts", "user_id", "item_id", "action", "source", "rec_model", "position", "page",
                    "session_id", "ab", "dwell_ms", "score", "meta"
                ],
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist feedback: {e}")

    return {"status": "ok", "written": os.path.relpath(csv_path, start=base_root), "ts": ts}




# -----------------------------
# Content index persistence APIs
# -----------------------------
class ContentIndexSaveResponse(BaseModel):
    """Response model for saving content index artifacts to disk."""
    embeddings_path: Optional[str] = None
    id2idx_path: Optional[str] = None
    idx2id_path: Optional[str] = None
    annoy_path: Optional[str] = None


class ContentIndexLoadResponse(BaseModel):
    """Response model describing the loaded content index state."""
    embeddings_loaded: bool
    mappings_loaded: bool
    annoy_loaded: bool
    embed_dim: int
    items: int


def _content_index_dir() -> str:
    """Resolve the directory to store content index artifacts under data/."""
    # Prefer dataset base_root if available, else fallback to project_root/data
    base_dir = None
    if DATASET_MANAGER is not None and hasattr(DATASET_MANAGER, "base_root"):
        base_dir = getattr(DATASET_MANAGER, "base_root")
    if not base_dir:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        base_dir = os.path.join(project_root, "data")
    target = os.path.join(base_dir, "content_index")
    os.makedirs(target, exist_ok=True)
    return target


@app.post("/content/index/save", response_model=ContentIndexSaveResponse)
def save_content_index() -> ContentIndexSaveResponse:
    """Persist embeddings, mappings, and Annoy index (if any) to data/content_index/."""
    global CONTENT_EMBEDDINGS, CONTENT_ID2IDX, CONTENT_IDX2ID, CONTENT_EMBED_DIM, CONTENT_INDEX
    if CONTENT_EMBEDDINGS is None or not CONTENT_ID2IDX or not CONTENT_IDX2ID:
        raise HTTPException(status_code=400, detail="Content index not ready. Build it first.")

    out_dir = _content_index_dir()
    embeddings_path = os.path.join(out_dir, "CONTENT_EMBEDDINGS.npy")
    id2idx_path = os.path.join(out_dir, "id2idx.json")
    idx2id_path = os.path.join(out_dir, "idx2id.json")
    annoy_path = os.path.join(out_dir, "content_index.ann") if (HAS_ANNOY and CONTENT_INDEX is not None) else None

    # Save numpy embeddings
    try:
        np.save(embeddings_path, CONTENT_EMBEDDINGS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save embeddings: {e}")

    # Save mappings
    try:
        with open(id2idx_path, "w", encoding="utf-8") as f:
            json.dump({str(k): int(v) for k, v in CONTENT_ID2IDX.items()}, f)
        with open(idx2id_path, "w", encoding="utf-8") as f:
            json.dump([int(i) for i in CONTENT_IDX2ID], f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save mappings: {e}")

    # Save Annoy index if available
    if annoy_path and CONTENT_INDEX is not None:
        try:
            CONTENT_INDEX.save(annoy_path)
        except Exception as e:
            # Non-fatal; still return paths for other artifacts
            annoy_path = None

    return ContentIndexSaveResponse(
        embeddings_path=embeddings_path,
        id2idx_path=id2idx_path,
        idx2id_path=idx2id_path,
        annoy_path=annoy_path,
    )


@app.post("/content/index/load", response_model=ContentIndexLoadResponse)
def load_content_index() -> ContentIndexLoadResponse:
    """Load persisted content index artifacts from data/content_index/ if present."""
    global CONTENT_INDEX, CONTENT_EMBEDDINGS, CONTENT_ID2IDX, CONTENT_IDX2ID, CONTENT_EMBED_DIM, CONTENT_EMBEDDINGS_READY, ANNOY_READY
    in_dir = _content_index_dir()
    embeddings_path = os.path.join(in_dir, "CONTENT_EMBEDDINGS.npy")
    id2idx_path = os.path.join(in_dir, "id2idx.json")
    idx2id_path = os.path.join(in_dir, "idx2id.json")
    annoy_path = os.path.join(in_dir, "content_index.ann")

    embeddings_loaded = False
    mappings_loaded = False
    annoy_loaded = False

    # Load embeddings
    if os.path.exists(embeddings_path):
        try:
            emb = np.load(embeddings_path)
            CONTENT_EMBEDDINGS = emb.astype(np.float32)
            CONTENT_EMBED_DIM = int(CONTENT_EMBEDDINGS.shape[1]) if CONTENT_EMBEDDINGS.ndim == 2 else 0
            embeddings_loaded = True
            CONTENT_EMBEDDINGS_READY = True
        except Exception:
            CONTENT_EMBEDDINGS = None
            CONTENT_EMBEDDINGS_READY = False
            CONTENT_EMBED_DIM = 0

    # Load mappings
    if os.path.exists(id2idx_path) and os.path.exists(idx2id_path):
        try:
            with open(id2idx_path, "r", encoding="utf-8") as f:
                id2idx_raw = json.load(f)
                CONTENT_ID2IDX = {int(k): int(v) for k, v in id2idx_raw.items()}
            with open(idx2id_path, "r", encoding="utf-8") as f:
                idx2id_raw = json.load(f)
                CONTENT_IDX2ID = [int(i) for i in idx2id_raw]
            mappings_loaded = True
        except Exception:
            CONTENT_ID2IDX = {}
            CONTENT_IDX2ID = []
            mappings_loaded = False

    # Load Annoy index if available
    if HAS_ANNOY and os.path.exists(annoy_path) and CONTENT_EMBED_DIM > 0:
        try:
            index = AnnoyIndex(CONTENT_EMBED_DIM, metric="angular")
            index.load(annoy_path)  # type: ignore
            CONTENT_INDEX = index
            annoy_loaded = True
            ANNOY_READY = True
        except Exception:
            CONTENT_INDEX = None
            annoy_loaded = False
            ANNOY_READY = False
    else:
        CONTENT_INDEX = None
        ANNOY_READY = False

    items = int(CONTENT_EMBEDDINGS.shape[0]) if (CONTENT_EMBEDDINGS is not None and CONTENT_EMBEDDINGS.ndim == 2) else 0
    return ContentIndexLoadResponse(
        embeddings_loaded=embeddings_loaded,
        mappings_loaded=mappings_loaded,
        annoy_loaded=annoy_loaded,
        embed_dim=CONTENT_EMBED_DIM,
        items=items,
    )


@app.get("/metrics/summary")
def metrics_summary(
    start_ts: Optional[float] = Query(None, description="ts >= start_ts (epoch secs)"),
    end_ts: Optional[float] = Query(None, description="ts <= end_ts (epoch secs)"),
) -> Dict[str, Any]:
    """Aggregate feedback metrics and system state over an optional time window.
    - Filters CSV events by [start_ts, end_ts] if provided.
    - Returns counts by action/source/rec_model/ab, overall CTR and per-group CTR,
      unique users/items, daily totals and daily-by-action breakdown,
      plus dataset and content index summaries for monitoring.
    """
    if DATASET_MANAGER is None:
        raise HTTPException(status_code=500, detail="Dataset not initialized")

    # Validate time window
    if start_ts is not None and end_ts is not None and float(end_ts) < float(start_ts):
        raise HTTPException(status_code=400, detail="end_ts must be >= start_ts")

    base_root = getattr(DATASET_MANAGER, "base_root", None) or os.path.dirname(DATASET_MANAGER.root)
    feedback_dir = os.path.join(base_root, "feedback")
    csv_path = os.path.join(feedback_dir, "events.csv")

    # Prepare aggregators
    by_action: Counter = Counter()
    by_source: Counter = Counter()
    by_rec_model: Counter = Counter()
    by_ab: Counter = Counter()
    users: set = set()
    items: set = set()
    daily: Dict[str, int] = defaultdict(int)
    daily_by_action: Dict[str, Counter] = defaultdict(Counter)

    # For group CTRs (source/model)
    source_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"impress": 0, "click": 0})
    model_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"impress": 0, "click": 0})

    total_events = 0
    impressions = 0
    clicks = 0

    if os.path.exists(csv_path):
        try:
            with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse timestamp and apply window filter
                    try:
                        ts = float(row.get("ts") or 0)
                    except Exception:
                        ts = 0.0
                    if start_ts is not None and ts < float(start_ts):
                        continue
                    if end_ts is not None and ts > float(end_ts):
                        continue

                    total_events += 1
                    action = (row.get("action") or "").strip()
                    source = (row.get("source") or "").strip() or None
                    model = (row.get("rec_model") or "").strip() or None
                    ab = (row.get("ab") or "").strip() or None

                    # Increment basic aggregations
                    if action:
                        by_action[action] += 1
                    if source:
                        by_source[source] += 1
                    if model:
                        by_rec_model[model] += 1
                    if ab:
                        by_ab[ab] += 1

                    # Track unique users/items from events
                    try:
                        users.add(int(row.get("user_id") or 0))
                        items.add(int(row.get("item_id") or 0))
                    except Exception:
                        pass

                    # Build daily keys and breakdowns
                    try:
                        day_key = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                    except Exception:
                        day_key = "unknown"
                    daily[day_key] += 1
                    if action:
                        daily_by_action[day_key][action] += 1

                    # Overall CTR counters
                    if action == "impress":
                        impressions += 1
                    elif action == "click":
                        clicks += 1

                    # Group CTR counters
                    if source and action in ("impress", "click"):
                        source_counts[source][action] += 1
                    if model and action in ("impress", "click"):
                        model_counts[model][action] += 1
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read metrics: {e}")

    # Compute CTRs
    ctr = (clicks / impressions) if impressions > 0 else 0.0

    def _ctr_pair(counts: Dict[str, int]) -> float:
        """Compute CTR given a dict containing 'click' and 'impress' counts."""
        i = counts.get("impress", 0)
        c = counts.get("click", 0)
        return (c / i) if i > 0 else 0.0

    ctr_by_source = {k: round(_ctr_pair(v), 4) for k, v in source_counts.items()}
    ctr_by_rec_model = {k: round(_ctr_pair(v), 4) for k, v in model_counts.items()}

    # Dataset summary
    try:
        ds_users = len(getattr(DATASET_MANAGER, "user2items", {}) or {})
        ds_items = len(getattr(DATASET_MANAGER, "item_meta", {}) or {})
        ds_interactions = sum(len(v) for v in getattr(DATASET_MANAGER, "user2items", {}).values())
    except Exception:
        ds_users = ds_items = ds_interactions = 0

    dataset_summary = {
        "user_count": ds_users,
        "item_count": ds_items,
        "interaction_count": ds_interactions,
    }

    # Content index summary
    try:
        emb_items = int(CONTENT_EMBEDDINGS.shape[0]) if (CONTENT_EMBEDDINGS is not None and CONTENT_EMBEDDINGS.ndim == 2) else 0
    except Exception:
        emb_items = 0

    content_index_summary = {
        "embed_dim": int(CONTENT_EMBED_DIM or 0),
        "embeddings_ready": bool(CONTENT_EMBEDDINGS_READY),
        "annoy_ready": bool(ANNOY_READY),
        "items": emb_items,
    }

    # Timeseries formatting
    timeseries_daily = sorted(daily.items(), key=lambda x: x[0])
    timeseries_daily_by_action = [
        (day, dict(counter)) for day, counter in sorted(daily_by_action.items(), key=lambda x: x[0])
    ]

    return {
        "window": {"start_ts": start_ts, "end_ts": end_ts},
        "total_events": total_events,
        "by_action": dict(by_action),
        "by_source": dict(by_source),
        "by_rec_model": dict(by_rec_model),
        "by_ab": dict(by_ab),
        "ctr": round(ctr, 4),
        "ctr_by_source": ctr_by_source,
        "ctr_by_rec_model": ctr_by_rec_model,
        "unique_users": len(users),
        "unique_items": len(items),
        "timeseries_daily": timeseries_daily,
        "timeseries_daily_by_action": timeseries_daily_by_action,
        "dataset": dataset_summary,
        "content_index": content_index_summary,
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "ts": time.time()}


# ---------------------
# Search and Item APIs
# ---------------------
class ItemDetail(BaseModel):
    item_id: int
    title: str
    popularity: Optional[float] = None

class SearchResponse(BaseModel):
    items: List[ItemDetail]
    total: int

@app.get("/search", response_model=SearchResponse)
def search_items(
    q: str = Query(..., min_length=1, description="Query string to match item titles (case-insensitive)"),
    limit: int = Query(20, ge=1, le=100),
) -> SearchResponse:
    """Search items by title (case-insensitive) and return a paginated subset with simple popularity."""
    if DATASET_MANAGER is None:
        raise HTTPException(status_code=500, detail="Dataset not initialized")
    q_lower = q.strip().lower()
    if not q_lower:
        raise HTTPException(status_code=400, detail="Empty query")
    matched: List[ItemDetail] = []
    for item_id, meta in DATASET_MANAGER.item_meta.items():
        title = meta.get("title", f"Item {item_id}")
        if q_lower in title.lower():
            pop = 0
            try:
                for _, items in DATASET_MANAGER.user2items.items():
                    if item_id in items:
                        pop += 1
            except Exception:
                pop = 0
            matched.append(ItemDetail(item_id=item_id, title=title, popularity=float(pop)))
            if len(matched) >= limit:
                break
    return SearchResponse(items=matched, total=len(matched))

@app.get("/item/{item_id}", response_model=ItemDetail)
def get_item(item_id: int) -> ItemDetail:
    """Get an item's metadata by id and compute a naive popularity count across users."""
    if DATASET_MANAGER is None:
        raise HTTPException(status_code=500, detail="Dataset not initialized")
    meta = DATASET_MANAGER.item_meta.get(item_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Item not found")
    pop = 0
    try:
        for _, items in DATASET_MANAGER.user2items.items():
            if item_id in items:
                pop += 1
    except Exception:
        pop = 0
    return ItemDetail(item_id=item_id, title=meta.get("title", f"Item {item_id}"), popularity=float(pop))

# ---------------------
# JWT/Auth settings
# ---------------------
# JWT settings: enforce presence of secret from environment for all environments
JWT_SECRET_KEY = os.getenv("FYP_JWT_SECRET")  # No default; must be set via environment
JWT_ALGORITHM = os.getenv("FYP_JWT_ALG", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("FYP_JWT_EXPIRE_MIN", "1440"))  # default 24h
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
if not JWT_SECRET_KEY or JWT_SECRET_KEY.strip().lower() in ("", "dev-secret-change-me", "changeme", "default"):
    # Fail fast to prevent insecure tokens in any environment
    raise RuntimeError("FYP_JWT_SECRET is required and must be a strong, non-default value.")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _user_store_path() -> str:
    if DATASET_MANAGER is not None and getattr(DATASET_MANAGER, "base_root", None):
        base_root = DATASET_MANAGER.base_root
    else:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        base_root = os.path.join(project_root, "data")
    os.makedirs(base_root, exist_ok=True)
    return os.path.join(base_root, "users.json")

def _load_users() -> Dict[str, Any]:
    path = _user_store_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _save_users(users: Dict[str, Any]) -> None:
    path = _user_store_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False

def _hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def _create_access_token(subject: str, expires_minutes: int = JWT_EXPIRE_MINUTES) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

@app.post("/auth/register")
def auth_register(payload: RegisterRequest) -> Dict[str, Any]:
    """Register a new user with username/password; hash and persist the password securely."""
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="username and password required")
    if len(payload.username) < 3 or len(payload.username) > 64:
        raise HTTPException(status_code=400, detail="username length must be 3-64")
    if len(payload.password) < 6 or len(payload.password) > 128:
        raise HTTPException(status_code=400, detail="password length must be 6-128")
    with MODEL_LOCK:
        users = _load_users()
        if payload.username in users:
            raise HTTPException(status_code=409, detail="username already exists")
        users[payload.username] = {"password_hash": _hash_password(payload.password)}
        try:
            _save_users(users)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"failed to save user: {e}")
    return {"status": "ok"}

@app.post("/auth/login", response_model=TokenResponse)
def auth_login(payload: LoginRequest) -> TokenResponse:
    """Authenticate user and return a JWT access token with configured expiry."""
    users = _load_users()
    user = users.get(payload.username)
    if not user or not _verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = _create_access_token(subject=payload.username, expires_minutes=JWT_EXPIRE_MINUTES)
    return TokenResponse(access_token=token, token_type="bearer", expires_in=JWT_EXPIRE_MINUTES * 60)

# Content index: build endpoint and response model
class ContentIndexBuildResponse(BaseModel):
    """Response model for building content index in memory."""
    built: bool
    embed_dim: int
    items: int
    annoy_ready: bool

@app.post("/content/index/build", response_model=ContentIndexBuildResponse)
def content_index_build(
    model_name: str = Query("all-MiniLM-L6-v2", description="SentenceTransformer model name for embeddings"),
    n_trees: int = Query(50, ge=1, le=200, description="Number of trees for Annoy index (if available)"),
) -> ContentIndexBuildResponse:
    """Build item content embeddings and (optionally) an Annoy index, updating global state."""
    with MODEL_LOCK:
        _build_content_index(model_name=model_name, n_trees=n_trees)
        return ContentIndexBuildResponse(
            built=bool(CONTENT_EMBEDDINGS_READY),
            embed_dim=int(CONTENT_EMBED_DIM),
            items=int(len(CONTENT_IDX2ID)),
            annoy_ready=bool(ANNOY_READY),
        )