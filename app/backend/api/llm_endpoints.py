#!/usr/bin/env python3
"""
LLM 相關的 API 端點
使用 Ollama 本地模型
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from database import get_db
from models import Movie, Rating
from auth import verify_token
from services.pure_ollama_client import (
    get_pure_ollama_client,
    resolve_llm_model,
    build_explain_inputs,
    postprocess_explanation,
)

router = APIRouter(prefix="/api/llm", tags=["LLM Services"])
security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    """獲取當前用戶ID"""
    token = credentials.credentials
    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    return user_id

@router.get("/status")
async def get_llm_status():
    """獲取 LLM 服務狀態"""
    try:
        client = get_pure_ollama_client()
        result = {
            "available": client.is_available()
        }
        return {
            "status": "success",
            "llm_status": result,
            "message": "LLM service status retrieved successfully"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to get LLM status: {str(e)}"
        }

@router.get("/models")
async def get_available_models():
    """獲取可用的模型列表"""
    try:
        client = get_pure_ollama_client()
        models = client.list_models()
        
        return {
            "status": "success",
            "models": models,
            "total_count": len(models),
            "message": "Model list retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model list: {str(e)}"
        )

@router.post("/explain-recommendation")
async def explain_recommendation(
    request: Dict[str, Any],
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """生成推薦解釋"""
    try:
        movie_id = request.get("movie_id")
        requested_model = request.get("model_name")
        model_name = resolve_llm_model(task_type="explain", requested_model=requested_model)

        if not movie_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="movie_id is required"
            )

        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movie not found"
            )

        user_ratings = db.query(Rating).filter(Rating.user_id == user_id).all()

        inputs = build_explain_inputs(movie=movie, user_ratings=user_ratings, request_payload=request)
        question = inputs["question"]
        answer_language = inputs["answer_language"]
        movie_context = inputs["movie_context"]
        user_preferences = inputs["user_preferences"]
        evidence_payload = inputs["evidence_payload"]
        combined_scores = inputs["combined_scores"]

        # 生成推薦解釋 - 使用純 Ollama
        ollama_client = get_pure_ollama_client()

        llm_result = await ollama_client.agenerate_recommendation_explanation_with_meta(
            movie_context,
            user_preferences,
            question,
            answer_language,
            evidence_payload,
            combined_scores,
            model_name,
        )
        explanation = (llm_result.get("text") or "").strip()
        if not explanation:
            explanation = (
                f"Finished generating a recommendation explanation for '{movie.title}', but the model did not return any readable content this time."
                f" Please try again later, or ask a more specific question (e.g., 'What do this movie and what I've watched recently have in common?')."
            )

        post = postprocess_explanation(explanation=explanation, evidence_payload=evidence_payload)
        explanation = post["explanation"]
        cited_ids = post["citations_used"]
        uncited_ids = post["citations_unused"]
        citation_alignment_score = post["citation_alignment_score"]
        
        return {
            "status": "success",
            "success": True,  # 與前端 LLMRecommendation 型別對齊
            "movie_id": movie_id,
            "movie_title": movie.title,
            "movie_year": movie.year,
            "explanation": explanation,
            "model_used": model_name,
            "llm_success": bool(llm_result.get("success")),
            "llm_error": llm_result.get("error"),
            "response_time": llm_result.get("response_time", 0),
            "user_preferences": user_preferences,
            "evidence_catalog": [{"id": f"E{i+1}", "text": e} for i, e in enumerate(evidence_payload)],
            "citations_used": cited_ids,
            "citations_unused": uncited_ids,
            "citation_alignment_score": citation_alignment_score,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate recommendation explanation: {str(e)}"
        )

@router.post("/compare-movies")
async def compare_movies(
    request: Dict[str, Any],
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """比較兩部電影"""
    try:
        movie1_id = request.get("movie1_id")
        movie2_id = request.get("movie2_id")
        requested_model = request.get("model_name")
        model_name = resolve_llm_model(task_type="compare", requested_model=requested_model)
        
        if not movie1_id or not movie2_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="movie1_id and movie2_id are required"
            )
        
        # 獲取電影信息
        movie1 = db.query(Movie).filter(Movie.id == movie1_id).first()
        movie2 = db.query(Movie).filter(Movie.id == movie2_id).first()
        
        if not movie1 or not movie2:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or both movies not found"
            )
        
        # 生成比較 - 使用純 Ollama
        ollama_client = get_pure_ollama_client()
        
        comparison = await ollama_client.agenerate_movie_comparison(
            f"{movie1.title} ({movie1.year})",
            f"{movie2.title} ({movie2.year})",
            model_name,
        )
        
        return {
            "status": "success",
            "movie1": {
                "id": movie1.id,
                "title": movie1.title,
                "year": movie1.year
            },
            "movie2": {
                "id": movie2.id,
                "title": movie2.title,
                "year": movie2.year
            },
            "comparison": comparison,
            "model_used": model_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare movies: {str(e)}"
        )

@router.get("/user-insights")
async def get_user_insights(
    user_id: int = Depends(get_current_user_id),
    model_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """獲取用戶洞察"""
    try:
        # 獲取用戶評分記錄
        user_ratings = db.query(Rating).filter(Rating.user_id == user_id).all()
        
        if not user_ratings:
            return {
                "status": "success",
                "message": "User has no rating records yet",
                "insights": "Start rating movies to get personalized insights!"
            }
        
        # 構建評分數據
        rating_data = []
        for rating in user_ratings:
            movie = rating.movie
            rating_data.append({
                "movie": {
                    "title": movie.title,
                    "year": movie.year,
                    "genres": [g.name for g in movie.genres],
                    "director": movie.director,
                    "cast": movie.cast
                },
                "rating": rating.rating
            })
        
        resolved_model = resolve_llm_model(task_type="insight", requested_model=model_name)

        # 生成洞察 - 使用純 Ollama
        ollama_client = get_pure_ollama_client()
        insights = await ollama_client.agenerate_user_insights(
            rating_data,
            resolved_model,
        )
        
        return {
            "status": "success",
            "user_id": user_id,
            "total_ratings": len(user_ratings),
            "insights": insights,
            "model_used": resolved_model
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user insights: {str(e)}"
        )

@router.post("/chat")
async def chat_with_llm(
    request: Dict[str, Any],
    _user_id: int = Depends(get_current_user_id)
):
    """與 LLM 對話"""
    try:
        message = request.get("message")
        requested_model = request.get("model_name")
        model_name = resolve_llm_model(task_type="chat", requested_model=requested_model)
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="message is required"
            )
        
        # 生成回應 - 使用純 Ollama
        ollama_client = get_pure_ollama_client()
        response = await ollama_client.achat(
            message,
            model_name
        )
        
        return {
            "status": "success",
            "message": message,
            "response": response,
            "model_used": model_name,
            "tokens_used": 0,
            "response_time": 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}"
        )
