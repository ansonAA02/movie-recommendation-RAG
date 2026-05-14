"""
Comment Management Endpoints
評論管理端點 - 完整的評論CRUD功能
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from pydantic import BaseModel
from datetime import datetime, timedelta

import sys
import os

# 確保可以匯入 models 模組
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import get_db
from models import Comment, User, Movie, Rating
from auth import get_current_user
from schemas import CommentCreate, CommentUpdate, CommentResponse, CommentPageResponse

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 創建路由器
router = APIRouter(prefix="/api/comments", tags=["Comment Management"])


def _build_comment_responses(
    db: Session,
    comment_rows: List[Comment],
    default_username: Optional[str] = None,
) -> List[CommentResponse]:
    if not comment_rows:
        return []

    movie_ids = list({c.movie_id for c in comment_rows})
    user_ids = list({c.user_id for c in comment_rows})

    movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all() if movie_ids else []
    movie_map = {m.id: m for m in movies}

    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {u.id: u for u in users}

    rating_rows = db.query(Rating.user_id, Rating.movie_id, Rating.rating).filter(
        and_(Rating.user_id.in_(user_ids), Rating.movie_id.in_(movie_ids))
    ).all() if user_ids and movie_ids else []
    rating_map = {(uid, mid): score for uid, mid, score in rating_rows}

    out: List[CommentResponse] = []
    for comment in comment_rows:
        movie = movie_map.get(comment.movie_id)
        username = default_username or (user_map.get(comment.user_id).username if user_map.get(comment.user_id) else "Unknown User")
        out.append(
            CommentResponse(
                id=comment.id,
                user_id=comment.user_id,
                movie_id=comment.movie_id,
                content=comment.content,
                rating=comment.rating,
                created_at=comment.created_at,
                updated_at=comment.updated_at,
                user_username=username,
                movie_title=movie.title if movie else "Unknown Movie",
                movie_year=movie.year if movie else None,
                user_rating=rating_map.get((comment.user_id, comment.movie_id)),
            )
        )
    return out

# 統計模型
class CommentStats(BaseModel):
    """評論統計模型"""
    total_comments: int
    user_comments: int
    movie_comments: int
    recent_comments: int
    average_length: float

@router.post("/", response_model=CommentResponse)
async def create_comment(
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    創建評論
    
    Args:
        comment_data: 評論數據
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        創建的評論
    """
    try:
        # 檢查電影是否存在
        movie = db.query(Movie).filter(Movie.id == comment_data.movie_id).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        
        # 允許用戶對同一部電影多次評論（移除重複檢查）
        
        # 創建評論
        comment = Comment(
            user_id=current_user.id,
            movie_id=comment_data.movie_id,
            content=comment_data.content.strip(),
            rating=comment_data.rating
        )
        
        db.add(comment)
        db.commit()
        db.refresh(comment)
        
        # 更新電影的評論計數
        movie.comment_count = (movie.comment_count or 0) + 1
        db.commit()
        
        # 更新統計數據
        from services.statistics_updater import statistics_updater
        statistics_updater.update_related_statistics(db, current_user.id, comment_data.movie_id)
        
        # 獲取用戶評分
        user_rating = db.query(Rating).filter(
            and_(
                Rating.user_id == current_user.id,
                Rating.movie_id == comment_data.movie_id
            )
        ).first()
        
        return CommentResponse(
            id=comment.id,
            user_id=comment.user_id,
            movie_id=comment.movie_id,
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            user_username=current_user.username,
            user_avatar=None,  # 可以後續添加頭像功能
            movie_title=movie.title,
            movie_year=movie.year,
            user_rating=user_rating.rating if user_rating else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"創建評論失敗: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create comment")

@router.get("/movie/{movie_id}", response_model=CommentPageResponse)
async def get_movie_comments(
    movie_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    sort_by: str = Query("newest", pattern="^(newest|oldest|rating)$"),
    db: Session = Depends(get_db)
):
    """
    獲取電影評論
    
    Args:
        movie_id: 電影ID
        page: 頁碼
        page_size: 每頁大小
        sort_by: 排序方式
        db: 數據庫會話
        
    Returns:
        評論列表
    """
    try:
        # 檢查電影是否存在
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        
        # 構建查詢
        query = db.query(Comment).filter(Comment.movie_id == movie_id)
        
        # 排序
        if sort_by == "newest":
            query = query.order_by(desc(Comment.created_at))
        elif sort_by == "oldest":
            query = query.order_by(Comment.created_at)
        elif sort_by == "rating":
            # 按用戶評分排序（需要聯表查詢）
            query = query.join(Rating, and_(
                Rating.user_id == Comment.user_id,
                Rating.movie_id == Comment.movie_id
            )).order_by(desc(Rating.rating))
        
        # 分頁
        offset = (page - 1) * page_size
        comments_data = query.offset(offset).limit(page_size).all()
        total_count = query.count()
        
        # 構建響應（批次查詢避免 N+1）
        comments = _build_comment_responses(db=db, comment_rows=comments_data)
        
        return {
            "comments": comments,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "has_more": (offset + len(comments)) < total_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取電影評論失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get movie comments")

@router.get("/user/{user_id}", response_model=List[CommentResponse])
async def get_user_comments(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    獲取用戶評論
    
    Args:
        user_id: 用戶ID
        page: 頁碼
        page_size: 每頁大小
        db: 數據庫會話
        
    Returns:
        用戶評論列表
    """
    try:
        # 檢查用戶是否存在
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 獲取評論
        offset = (page - 1) * page_size
        comment_rows = db.query(Comment).filter(
            Comment.user_id == user_id
        ).order_by(desc(Comment.created_at)).offset(offset).limit(page_size).all()
        
        # 構建響應（批次查詢避免 N+1）
        return _build_comment_responses(
            db=db,
            comment_rows=comment_rows,
            default_username=user.username,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取用戶評論失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user comments")

@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: int,
    comment_data: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新評論
    
    Args:
        comment_id: 評論ID
        comment_data: 更新數據
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        更新的評論
    """
    try:
        # 獲取評論
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")
        
        # 檢查權限
        if comment.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only update your own comments")
        
        # 更新評論
        comment.content = comment_data.content.strip()
        comment.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(comment)
        
        # 獲取電影信息
        movie = db.query(Movie).filter(Movie.id == comment.movie_id).first()
        
        # 獲取用戶評分
        user_rating = db.query(Rating).filter(
            and_(
                Rating.user_id == comment.user_id,
                Rating.movie_id == comment.movie_id
            )
        ).first()
        
        return CommentResponse(
            id=comment.id,
            user_id=comment.user_id,
            movie_id=comment.movie_id,
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            user_username=current_user.username,
            user_avatar=None,
            movie_title=movie.title if movie else "Unknown Movie",
            movie_year=movie.year if movie else None,
            user_rating=user_rating.rating if user_rating else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新評論失敗: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update comment")

@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    刪除評論
    
    Args:
        comment_id: 評論ID
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        刪除結果
    """
    try:
        # 獲取評論
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")
        
        # 檢查權限
        if comment.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only delete your own comments")
        
        # 刪除評論
        movie_id = comment.movie_id
        
        # 更新電影的評論計數
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if movie and movie.comment_count > 0:
            movie.comment_count -= 1
            db.commit()
        
        db.delete(comment)
        db.commit()
        
        # 更新統計數據
        from services.statistics_updater import statistics_updater
        statistics_updater.update_related_statistics(db, current_user.id, movie_id)
        
        return {"message": "Comment deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除評論失敗: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete comment")

@router.get("/stats/{movie_id}", response_model=CommentStats)
async def get_comment_stats(
    movie_id: int,
    db: Session = Depends(get_db)
):
    """
    獲取電影評論統計
    
    Args:
        movie_id: 電影ID
        db: 數據庫會話
        
    Returns:
        評論統計
    """
    try:
        # 檢查電影是否存在
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        
        # 統計數據
        total_comments = db.query(Comment).filter(Comment.movie_id == movie_id).count()
        
        # 最近7天的評論
        recent_date = datetime.utcnow() - timedelta(days=7)
        recent_comments = db.query(Comment).filter(
            and_(
                Comment.movie_id == movie_id,
                Comment.created_at >= recent_date
            )
        ).count()
        
        # 平均評論長度
        comments = db.query(Comment).filter(Comment.movie_id == movie_id).all()
        if comments:
            average_length = sum(len(comment.content) for comment in comments) / len(comments)
        else:
            average_length = 0.0
        
        return CommentStats(
            total_comments=total_comments,
            user_comments=0,  # 可以後續添加
            movie_comments=total_comments,
            recent_comments=recent_comments,
            average_length=round(average_length, 2)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取評論統計失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get comment stats")

@router.get("/recent", response_model=List[CommentResponse])
async def get_recent_comments(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    獲取最近評論
    
    Args:
        limit: 限制數量
        db: 數據庫會話
        
    Returns:
        最近評論列表
    """
    try:
        # 獲取最近評論
        comment_rows = db.query(Comment).order_by(desc(Comment.created_at)).limit(limit).all()
        return _build_comment_responses(db=db, comment_rows=comment_rows)
        
    except Exception as e:
        logger.error(f"獲取最近評論失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recent comments")
