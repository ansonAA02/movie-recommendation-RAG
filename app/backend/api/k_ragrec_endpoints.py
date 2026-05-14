from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any, Optional
import os
from dotenv import load_dotenv
from pydantic import BaseModel

from services.neo4j_manager import Neo4jManager
from services.k_ragrec_complete import get_k_ragrec_recommender
from database import get_db
from sqlalchemy.orm import Session

load_dotenv()

# 提供 K-RAGRec 路由器骨架，避免匯入錯誤
router = APIRouter(prefix="/api/k-ragrec", tags=["K-RAGRec"])

# Create a global neo4j manager
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")
neo4j_manager = Neo4jManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

# Create KG-RAG recommender instance
kg_rag_recommender = None


class RecommendRequest(BaseModel):
    user_id: int
    top_k: int = 10
    constraints: Optional[Dict[str, Any]] = None


@router.get("/health")
async def k_ragrec_health_check():
    return {"status": "ok", "service": "k-ragrec"}


@router.get("/system-status")
async def get_system_status() -> Dict[str, Any]:
    """Get K-RagRec system status including Neo4j and recommender availability."""
    global kg_rag_recommender
    
    # Check Neo4j connection
    neo4j_available = False
    try:
        if not hasattr(neo4j_manager, 'driver') or neo4j_manager.driver is None:
            neo4j_manager.connect()
        neo4j_available = neo4j_manager.driver is not None
    except Exception:
        neo4j_available = False
    
    # Check recommender availability
    recommender_available = False
    if kg_rag_recommender is None and neo4j_available:
        try:
            kg_rag_recommender = get_k_ragrec_recommender(neo4j_manager.driver)
            recommender_available = True
        except Exception:
            recommender_available = False
    elif kg_rag_recommender is not None:
        recommender_available = True
    
    return {
        "neo4j_available": neo4j_available,
        "recommender_available": recommender_available,
        "system_ready": neo4j_available and recommender_available
    }


@router.post("/recommend")
async def k_ragrec_recommend(req: RecommendRequest, db: Session = Depends(get_db)):
    global kg_rag_recommender

    try:
        if neo4j_manager.driver is None:
            connected = neo4j_manager.connect()
            if not connected or neo4j_manager.driver is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Neo4j is unavailable"
                )

        if kg_rag_recommender is None:
            kg_rag_recommender = get_k_ragrec_recommender(neo4j_manager.driver)
        if kg_rag_recommender is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="K-RAGRec recommender is unavailable"
            )

        recs = kg_rag_recommender.recommend(
            user_id=req.user_id,
            db=db,
            top_k=max(1, min(int(req.top_k or 10), 50)),
            constraints=req.constraints or {},
        )
        return {
            "ok": True,
            "method": "k_ragrec",
            "recommendations": recs,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"K-RAGRec recommendation failed: {exc}"
        )

