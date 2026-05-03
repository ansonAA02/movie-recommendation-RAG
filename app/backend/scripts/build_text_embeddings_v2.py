"""
build_text_embeddings_v2.py

Enhanced Movie Embedding v2:
- Read movies from SQLite DB (movie_recommendation.db in backend/)
- Build rich prompt from title/description/genres/director/cast/year/etc.
- Use sentence-transformers to produce embeddings (batch, device option)
- Normalize embeddings, save .npy, id_map.json, faiss.index, meta.json
- Choose FAISS IndexFlatIP (small) or IndexIVFFlat (large) automatically

Usage (from app/backend):
    python scripts/build_text_embeddings_v2.py --model all-mpnet-base-v2 --batch 64 --device cpu

Dependencies:
    pip install sentence-transformers faiss-cpu sqlalchemy tqdm
    (or faiss-gpu if you want GPU)

Note: This will download the model the first time (internet required).
"""

import os
import sys
import json
import argparse
from typing import List, Dict, Any
from tqdm import tqdm

# make backend importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))   # app/backend/scripts
BACKEND_DIR = os.path.dirname(CURRENT_DIR)                 # app/backend
sys.path.insert(0, BACKEND_DIR)

# imports that rely on project layout
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Movie  # your ORM model, expected to be in app/backend/models.py

import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

# -----------------------
# Utility: build prompt
# -----------------------
def build_prompt(movie: Movie) -> str:
    """
    Compose a rich natural-language prompt for a movie.
    Use all available metadata safely (skip None).
    """
    parts: List[str] = []
    if movie.title:
        parts.append(f"Title: {movie.title}.")
    meta = []
    if getattr(movie, "year", None):
        meta.append(str(movie.year))
    if getattr(movie, "country", None):
        meta.append(movie.country)
    if getattr(movie, "language", None):
        meta.append(movie.language)
    if meta:
        parts.append(" | ".join(meta) + ".")
    if getattr(movie, "genres", None):
        try:
            genres = [g.name for g in movie.genres]
            if genres:
                parts.append(f"Genres: {', '.join(genres)}.")
        except Exception:
            # some schemas use plain string in genre field
            pass
    if getattr(movie, "director", None):
        parts.append(f"Director: {movie.director}.")
    if getattr(movie, "cast", None):
        cast = movie.cast
        if isinstance(cast, str):
            # assume comma-separated
            cast_list = [c.strip() for c in cast.split(",") if c.strip()]
            if cast_list:
                parts.append(f"Top cast: {', '.join(cast_list[:5])}.")
    if getattr(movie, "description", None):
        desc = movie.description.strip()
        if desc:
            # keep a reasonable length
            parts.append(f"Plot: {desc[:800]}")
    # optional numeric quality signal
    if getattr(movie, "average_rating", None):
        try:
            parts.append(f"Average rating: {float(movie.average_rating):.1f}.")
        except Exception:
            pass

    prompt = " ".join(parts)
    # final clean
    prompt = " ".join(prompt.split())
    return prompt if prompt else (movie.title or "Untitled movie")

# -----------------------
# Main pipeline
# -----------------------
def main(
    db_path: str,
    out_dir: str,
    model_name: str = "all-mpnet-base-v2",
    batch_size: int = 64,
    device: str = "cpu",
    use_ivf_threshold: int = 50000,
    nlist: int = 4096
):
    os.makedirs(out_dir, exist_ok=True)
    emb_path = os.path.join(out_dir, "movie_embeddings.npy")
    idmap_path = os.path.join(out_dir, "id_map.json")
    faiss_path = os.path.join(out_dir, "faiss.index")
    meta_path = os.path.join(out_dir, "meta.json")

    # --- DB session
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # fetch movies
    movies = session.query(Movie).all()
    if not movies:
        print("No movies found in database. Exiting.")
        return

    meta_list: List[Dict[str, Any]] = []
    texts: List[str] = []
    id_list: List[str] = []

    print(f"Found {len(movies)} movies. Building prompts...")
    for m in movies:
        prompt = build_prompt(m)
        texts.append(prompt)
        id_list.append(str(m.id))
        meta_list.append({
            "movie_id": str(m.id),
            "title": m.title,
            "year": getattr(m, "year", None),
            "genres": [g.name for g in (m.genres or [])] if getattr(m, "genres", None) else [],
            "director": getattr(m, "director", None),
            "cast": getattr(m, "cast", None),
            "language": getattr(m, "language", None),
            "country": getattr(m, "country", None),
            "average_rating": getattr(m, "average_rating", None),
        })

    # --- load model
    print(f"Loading model {model_name} on device={device} ...")
    model = SentenceTransformer(model_name, device=device)

    # --- encode in batches
    print("Encoding embeddings (batches)...")
    embeddings = []
    for i in tqdm(range(0, len(texts), batch_size), desc="batches"):
        batch_texts = texts[i : i + batch_size]
        emb_batch = model.encode(batch_texts, show_progress_bar=False, convert_to_numpy=True, device=device)
        embeddings.append(emb_batch.astype("float32"))
    embs = np.vstack(embeddings)
    print("Embeddings shape:", embs.shape)

    # normalize for cosine similarity
    faiss.normalize_L2(embs)

    # save embeddings matrix
    np.save(emb_path, embs)
    print("Saved embeddings:", emb_path)

    # id_map
    idx_to_id = {str(i): id_list[i] for i in range(len(id_list))}
    id_to_idx = {v: k for k, v in idx_to_id.items()}
    with open(idmap_path, "w", encoding="utf-8") as f:
        json.dump({"idx_to_id": idx_to_id, "id_to_idx": id_to_idx}, f, ensure_ascii=False, indent=2)
    print("Saved id_map:", idmap_path)

    # save meta (for UI / debugging / reasons)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_list, f, ensure_ascii=False, indent=2)
    print("Saved meta:", meta_path)

    # build FAISS index
    d = embs.shape[1]
    if len(embs) >= use_ivf_threshold:
        # build IVF index for large datasets
        print(f"Building IVF index (nlist={nlist}) for {len(embs)} vectors...")
        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
        # train
        index.train(embs)
        index.add(embs)
    else:
        print("Building IndexFlatIP (exact search) ...")
        index = faiss.IndexFlatIP(d)
        index.add(embs)

    # write index
    faiss.write_index(index, faiss_path)
    print("Saved faiss index:", faiss_path)

    print("All done.")

# -----------------------
# CLI
# -----------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="all-mpnet-base-v2", help="sentence-transformers model name")
    parser.add_argument("--batch", type=int, default=64, help="batch size for encoding")
    parser.add_argument("--device", type=str, default="cpu", help="device: cpu or cuda")
    parser.add_argument("--db", type=str, default=os.path.join(BACKEND_DIR, "movie_recommendation.db"), help="sqlite db path")
    parser.add_argument("--out", type=str, default=os.path.join(BACKEND_DIR, "embeddings"), help="output folder")
    parser.add_argument("--ivf-threshold", type=int, default=50000, help="use IVF if num vectors >= threshold")
    parser.add_argument("--nlist", type=int, default=4096, help="nlist for IVF (if used)")
    args = parser.parse_args()

    main(
        db_path=args.db,
        out_dir=args.out,
        model_name=args.model,
        batch_size=args.batch,
        device=args.device,
        use_ivf_threshold=args.ivf_threshold,
        nlist=args.nlist
    )
