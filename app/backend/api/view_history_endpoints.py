"""
View History Management Endpoints
瀏覽歷史管理端點 - 完整的用戶瀏覽歷史功能
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
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
from models import ViewHistory, User, Movie, Rating, Comment, Favorite, Like
from auth import get_current_user
from schemas import ViewHistoryCreate, ViewHistoryResponse

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 創建路由器
router = APIRouter(prefix="/api/view-history", tags=["View History Management"])


def _build_user_movie_flags(
    db: Session,
    user_id: int,
    movie_ids: List[int],
):
    if not movie_ids:
        return {}, set(), set(), set()
    rating_rows = db.query(Rating.movie_id, Rating.rating).filter(
        and_(Rating.user_id == user_id, Rating.movie_id.in_(movie_ids))
    ).all()
    favorite_rows = db.query(Favorite.movie_id).filter(
        and_(Favorite.user_id == user_id, Favorite.movie_id.in_(movie_ids))
    ).all()
    like_rows = db.query(Like.movie_id).filter(
        and_(Like.user_id == user_id, Like.movie_id.in_(movie_ids))
    ).all()
    review_rows = db.query(Comment.movie_id).filter(
        and_(Comment.user_id == user_id, Comment.movie_id.in_(movie_ids))
    ).distinct().all()

    rating_map = {mid: score for mid, score in rating_rows}
    favorite_set = {mid for (mid,) in favorite_rows}
    like_set = {mid for (mid,) in like_rows}
    review_set = {mid for (mid,) in review_rows}
    return rating_map, favorite_set, like_set, review_set


def _build_view_history_response_items(
    db: Session,
    current_user_id: int,
    views: List[ViewHistory],
) -> List[ViewHistoryResponse]:
    if not views:
        return []

    movie_ids = list({v.movie_id for v in views})
    movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
    movie_map = {m.id: m for m in movies}

    rating_map, favorite_set, like_set, review_set = _build_user_movie_flags(
        db=db,
        user_id=current_user_id,
        movie_ids=movie_ids,
    )

    history_list: List[ViewHistoryResponse] = []
    for view in views:
        movie = movie_map.get(view.movie_id)
        if not movie:
            continue
        genres_str = ", ".join([genre.name for genre in movie.genres]) if movie.genres else ""
        history_list.append(
            ViewHistoryResponse(
                id=view.id,
                user_id=view.user_id,
                movie_id=view.movie_id,
                viewed_at=view.viewed_at,
                view_duration=view.view_duration,
                view_type=view.view_type,
                movie_title=movie.title,
                movie_year=movie.year,
                movie_poster_url=movie.poster_url,
                movie_average_rating=movie.average_rating,
                movie_genres=genres_str,
                user_rating=rating_map.get(view.movie_id),
                is_favorite=view.movie_id in favorite_set,
                is_liked=view.movie_id in like_set,
                has_review=view.movie_id in review_set,
            )
        )
    return history_list

# 統計和分析模型

class ViewHistoryStats(BaseModel):
    """瀏覽歷史統計模型"""
    total_views: int
    unique_movies: int
    total_duration: int
    average_duration: float
    most_viewed_genre: Optional[str] = None
    most_viewed_year: Optional[int] = None
    recent_activity: int  # 最近7天瀏覽次數

class ViewHistoryAnalytics(BaseModel):
    """瀏覽歷史分析模型"""
    user_id: int
    viewing_patterns: dict
    genre_preferences: dict
    year_preferences: dict
    rating_patterns: dict
    engagement_level: str

@router.post("/batch")
async def create_batch_view_history(
    view_data_list: List[ViewHistoryCreate],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    批量創建瀏覽記錄（用於測試）
    
    Args:
        view_data_list: 瀏覽記錄列表
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        創建的瀏覽記錄列表
    """
    try:
        created_views = []
        for view_data in view_data_list:
            # 設置用戶ID
            view_data.user_id = current_user.id
            
            # 創建瀏覽記錄
            view_history = ViewHistory(**view_data.dict())
            db.add(view_history)
            db.flush()  # 獲取ID
            
            # 獲取電影信息
            movie = db.query(Movie).filter(Movie.id == view_data.movie_id).first()
            if movie:
                genres_str = ", ".join([genre.name for genre in movie.genres]) if movie.genres else ""
                
                created_views.append(ViewHistoryResponse(
                    id=view_history.id,
                    user_id=view_history.user_id,
                    movie_id=view_history.movie_id,
                    viewed_at=view_history.viewed_at,
                    view_duration=view_history.view_duration,
                    view_type=view_history.view_type,
                    movie_title=movie.title,
                    movie_year=movie.year,
                    movie_poster_url=movie.poster_url,
                    movie_average_rating=movie.average_rating,
                    movie_genres=genres_str,
                    user_rating=None,
                    is_favorite=False,
                    is_liked=False,
                    has_review=False
                ))
        
        db.commit()
        return {
            "message": f"Successfully created {len(created_views)} viewing history records",
            "views": created_views
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"批量創建瀏覽記錄失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to create batch view history")

@router.post("/", response_model=ViewHistoryResponse)
async def create_view_history(
    view_data: ViewHistoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    創建瀏覽記錄
    
    Args:
        view_data: 瀏覽數據
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        創建的瀏覽記錄
    """
    try:
        # 檢查電影是否存在
        movie = db.query(Movie).filter(Movie.id == view_data.movie_id).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        
        # 創建瀏覽記錄
        view_history = ViewHistory(
            user_id=current_user.id,
            movie_id=view_data.movie_id,
            view_duration=view_data.view_duration,
            view_type=view_data.view_type
        )
        
        db.add(view_history)
        db.commit()
        db.refresh(view_history)
        
        # 更新統計數據
        from services.statistics_updater import statistics_updater
        statistics_updater.update_related_statistics(db, current_user.id, view_data.movie_id)
        
        # 獲取電影相關信息
        genres_str = ", ".join([genre.name for genre in movie.genres]) if movie.genres else ""
        
        # 檢查用戶互動
        user_rating = db.query(Rating).filter(
            and_(
                Rating.user_id == current_user.id,
                Rating.movie_id == view_data.movie_id
            )
        ).first()
        
        is_favorite = db.query(Favorite).filter(
            and_(
                Favorite.user_id == current_user.id,
                Favorite.movie_id == view_data.movie_id
            )
        ).first() is not None
        
        is_liked = db.query(Like).filter(
            and_(
                Like.user_id == current_user.id,
                Like.movie_id == view_data.movie_id
            )
        ).first() is not None
        
        has_review = db.query(Comment).filter(
            and_(
                Comment.user_id == current_user.id,
                Comment.movie_id == view_data.movie_id
            )
        ).first() is not None
        
        return ViewHistoryResponse(
            id=view_history.id,
            user_id=view_history.user_id,
            movie_id=view_history.movie_id,
            viewed_at=view_history.viewed_at,
            view_duration=view_history.view_duration,
            view_type=view_history.view_type,
            movie_title=movie.title,
            movie_year=movie.year,
            movie_poster_url=movie.poster_url,
            movie_average_rating=movie.average_rating,
            movie_genres=genres_str,
            user_rating=user_rating.rating if user_rating else None,
            is_favorite=is_favorite,
            is_liked=is_liked,
            has_review=has_review
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"創建瀏覽記錄失敗: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create view history")

@router.get("/user")
async def get_user_view_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    view_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    獲取用戶瀏覽歷史
    
    Args:
        page: 頁碼
        page_size: 每頁大小
        days: 查詢天數
        view_type: 瀏覽類型過濾
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        用戶瀏覽歷史列表
    """
    try:
        # 計算日期範圍
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # 構建查詢
        query = db.query(ViewHistory).filter(
            and_(
                ViewHistory.user_id == current_user.id,
                ViewHistory.viewed_at >= start_date
            )
        )
        
        # 類型過濾
        if view_type:
            query = query.filter(ViewHistory.view_type == view_type)
        
        # 排序和分頁
        offset = (page - 1) * page_size
        view_histories = query.order_by(desc(ViewHistory.viewed_at)).offset(offset).limit(page_size).all()
        
        # 構建響應（批次查詢避免 N+1）
        history_list = _build_view_history_response_items(
            db=db,
            current_user_id=current_user.id,
            views=view_histories,
        )
        
        # 獲取總數（用於分頁）
        total_count = query.count()
        
        return {
            "views": history_list,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "has_more": (page * page_size) < total_count
        }
        
    except Exception as e:
        logger.error(f"獲取用戶瀏覽歷史失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user view history")

@router.get("/unique-movies")
async def get_user_unique_movies(
    days: int = Query(30, ge=1, le=365),
    view_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    獲取用戶瀏覽過的唯一電影列表（去重，按最新瀏覽時間排序）
    
    Args:
        days: 查詢天數
        view_type: 瀏覽類型過濾
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        用戶瀏覽過的唯一電影列表
    """
    try:
        # 計算日期範圍
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # 構建查詢 - 獲取每個電影的最新瀏覽記錄
        subquery = db.query(
            ViewHistory.movie_id,
            func.max(ViewHistory.viewed_at).label('latest_view')
        ).filter(
            and_(
                ViewHistory.user_id == current_user.id,
                ViewHistory.viewed_at >= start_date
            )
        )
        
        if view_type:
            subquery = subquery.filter(ViewHistory.view_type == view_type)
            
        subquery = subquery.group_by(ViewHistory.movie_id).subquery()
        
        # 獲取最新瀏覽記錄的完整信息
        query = db.query(ViewHistory).join(
            subquery,
            and_(
                ViewHistory.movie_id == subquery.c.movie_id,
                ViewHistory.viewed_at == subquery.c.latest_view
            )
        ).order_by(desc(ViewHistory.viewed_at))
        
        view_histories = query.all()
        
        # 構建響應（批次查詢避免 N+1）
        history_list = _build_view_history_response_items(
            db=db,
            current_user_id=current_user.id,
            views=view_histories,
        )
        
        return {
            "movies": history_list,
            "total": len(history_list)
        }
        
    except Exception as e:
        logger.error(f"獲取用戶唯一電影列表失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user unique movies")

@router.get("/stats", response_model=ViewHistoryStats)
async def get_view_history_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    獲取瀏覽歷史統計
    
    Args:
        days: 查詢天數
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        瀏覽歷史統計
    """
    try:
        # 計算日期範圍
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # 基本統計
        total_views = db.query(ViewHistory).filter(
            and_(
                ViewHistory.user_id == current_user.id,
                ViewHistory.viewed_at >= start_date
            )
        ).count()
        
        # 唯一電影數量
        unique_movies = db.query(ViewHistory.movie_id).filter(
            and_(
                ViewHistory.user_id == current_user.id,
                ViewHistory.viewed_at >= start_date
            )
        ).distinct().count()
        
        # 總瀏覽時長
        total_duration = db.query(func.sum(ViewHistory.view_duration)).filter(
            and_(
                ViewHistory.user_id == current_user.id,
                ViewHistory.viewed_at >= start_date
            )
        ).scalar() or 0
        
        # 平均瀏覽時長
        average_duration = total_duration / total_views if total_views > 0 else 0
        
        # 最近7天活動
        recent_start = datetime.utcnow() - timedelta(days=7)
        recent_activity = db.query(ViewHistory).filter(
            and_(
                ViewHistory.user_id == current_user.id,
                ViewHistory.viewed_at >= recent_start
            )
        ).count()
        
        # 最常瀏覽的類型（需要聯表查詢）
        most_viewed_genre = None
        most_viewed_year = None
        
        # 這裡可以添加更複雜的分析邏輯
        
        return ViewHistoryStats(
            total_views=total_views,
            unique_movies=unique_movies,
            total_duration=total_duration,
            average_duration=round(average_duration, 2),
            most_viewed_genre=most_viewed_genre,
            most_viewed_year=most_viewed_year,
            recent_activity=recent_activity
        )
        
    except Exception as e:
        logger.error(f"獲取瀏覽歷史統計失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get view history stats")

@router.get("/analytics", response_model=ViewHistoryAnalytics)
async def get_view_history_analytics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    獲取瀏覽歷史分析
    
    Args:
        days: 查詢天數
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        瀏覽歷史分析
    """
    try:
        # 計算日期範圍
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # 獲取瀏覽記錄
        view_histories = db.query(ViewHistory).filter(
            and_(
                ViewHistory.user_id == current_user.id,
                ViewHistory.viewed_at >= start_date
            )
        ).all()
        
        if not view_histories:
            return ViewHistoryAnalytics(
                user_id=current_user.id,
                viewing_patterns={},
                genre_preferences={},
                year_preferences={},
                rating_patterns={},
                engagement_level="low"
            )
        
        # 分析瀏覽模式
        viewing_patterns = {
            "total_views": len(view_histories),
            "average_duration": sum(v.view_duration for v in view_histories) / len(view_histories),
            "view_types": {}
        }
        
        # 瀏覽類型分析
        view_types = {}
        for view in view_histories:
            view_types[view.view_type] = view_types.get(view.view_type, 0) + 1
        viewing_patterns["view_types"] = view_types
        
        # 類型偏好分析（批次查詢電影）
        genre_preferences = {}
        year_preferences = {}

        movie_ids = list({v.movie_id for v in view_histories})
        movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all() if movie_ids else []
        movie_map = {m.id: m for m in movies}
        for view in view_histories:
            movie = movie_map.get(view.movie_id)
            if not movie:
                continue
            if movie.year:
                year_preferences[movie.year] = year_preferences.get(movie.year, 0) + 1
            if movie.genres:
                for genre in movie.genres:
                    genre_preferences[genre.name] = genre_preferences.get(genre.name, 0) + 1
        
        # 評分模式分析
        rating_patterns = {
            "rated_movies": 0,
            "average_rating": 0.0,
            "rating_distribution": {}
        }
        
        rated_movies = 0
        total_rating = 0.0
        rating_dist = {}
        
        rating_rows = db.query(Rating.movie_id, Rating.rating).filter(
            and_(Rating.user_id == current_user.id, Rating.movie_id.in_(movie_ids))
        ).all() if movie_ids else []
        rating_map = {mid: score for mid, score in rating_rows}
        for view in view_histories:
            score = rating_map.get(view.movie_id)
            if score is not None:
                rated_movies += 1
                total_rating += score
                rating_dist[int(score)] = rating_dist.get(int(score), 0) + 1
        
        if rated_movies > 0:
            rating_patterns["rated_movies"] = rated_movies
            rating_patterns["average_rating"] = round(total_rating / rated_movies, 2)
            rating_patterns["rating_distribution"] = rating_dist
        
        # 參與度分析
        total_views = len(view_histories)
        if total_views >= 50:
            engagement_level = "high"
        elif total_views >= 20:
            engagement_level = "medium"
        else:
            engagement_level = "low"
        
        return ViewHistoryAnalytics(
            user_id=current_user.id,
            viewing_patterns=viewing_patterns,
            genre_preferences=genre_preferences,
            year_preferences=year_preferences,
            rating_patterns=rating_patterns,
            engagement_level=engagement_level
        )
        
    except Exception as e:
        logger.error(f"獲取瀏覽歷史分析失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get view history analytics")

@router.delete("/clear")
async def clear_view_history(
    days: Optional[int] = Query(None, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    清除瀏覽歷史
    
    Args:
        days: 清除天數（None表示清除全部）
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        清除結果
    """
    try:
        if days:
            # 清除指定天數的歷史
            start_date = datetime.utcnow() - timedelta(days=days)
            deleted_count = db.query(ViewHistory).filter(
                and_(
                    ViewHistory.user_id == current_user.id,
                    ViewHistory.viewed_at >= start_date
                )
            ).delete()
        else:
            # 清除全部歷史
            deleted_count = db.query(ViewHistory).filter(
                ViewHistory.user_id == current_user.id
            ).delete()
        
        db.commit()
        
        return {
            "message": f"Successfully cleared {deleted_count} view history records",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        logger.error(f"清除瀏覽歷史失敗: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to clear view history")

@router.get("/recent", response_model=List[ViewHistoryResponse])
async def get_recent_views(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    獲取最近瀏覽記錄
    
    Args:
        limit: 限制數量
        current_user: 當前用戶
        db: 數據庫會話
        
    Returns:
        最近瀏覽記錄列表
    """
    try:
        # 獲取最近瀏覽記錄
        recent_views = db.query(ViewHistory).filter(
            ViewHistory.user_id == current_user.id
        ).order_by(desc(ViewHistory.viewed_at)).limit(limit).all()
        
        return _build_view_history_response_items(
            db=db,
            current_user_id=current_user.id,
            views=recent_views,
        )
        
    except Exception as e:
        logger.error(f"獲取最近瀏覽記錄失敗: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recent views")
