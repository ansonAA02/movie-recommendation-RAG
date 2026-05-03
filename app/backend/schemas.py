from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

# 用户相关Schema
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None

# 用户档案相关Schema
class UserProfileResponse(BaseModel):
    id: int
    user_id: int
    preferred_genres: Optional[List[str]] = None
    preferred_directors: Optional[List[str]] = None
    preferred_actors: Optional[List[str]] = None
    preferred_languages: Optional[List[str]] = None
    preferred_countries: Optional[List[str]] = None
    genre_distribution_json: Optional[dict] = None
    director_distribution_json: Optional[dict] = None
    actor_distribution_json: Optional[dict] = None
    recent_activity_score: float = 0.0
    preference_drift_score: float = 0.0
    min_rating_threshold: float = 3.0
    max_runtime: Optional[int] = None
    min_runtime: Optional[int] = None
    total_ratings: int = 0
    total_likes: int = 0
    total_favorites: int = 0
    total_views: int = 0
    average_rating_given: float = 0.0
    most_rated_year: Optional[int] = None
    profile_setup_completed: bool = False
    setup_skipped: bool = False
    setup_completed_at: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class UserProfileUpdate(BaseModel):
    preferred_genres: Optional[List[str]] = None
    preferred_directors: Optional[List[str]] = None
    preferred_actors: Optional[List[str]] = None
    preferred_languages: Optional[List[str]] = None
    preferred_countries: Optional[List[str]] = None
    min_rating_threshold: Optional[float] = None
    max_runtime: Optional[int] = None
    min_runtime: Optional[int] = None
    # onboarding flags
    profile_setup_completed: Optional[bool] = None
    setup_skipped: Optional[bool] = None
    setup_completed_at: Optional[str] = None

class PreferencesUpdate(BaseModel):
    preferred_genres: Optional[List[str]] = None
    preferred_directors: Optional[List[str]] = None
    preferred_actors: Optional[List[str]] = None
    preferred_languages: Optional[List[str]] = None
    preferred_countries: Optional[List[str]] = None
    min_rating_threshold: Optional[float] = None
    max_runtime: Optional[int] = None
    min_runtime: Optional[int] = None

# 推薦設置已移除

# 电影相关Schema
class GenreResponse(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

class MovieResponse(BaseModel):
    id: int
    title: str  # 電影標題
    year: Optional[int] = None  # 年份
    imdb_id: Optional[str] = None  # IMDB ID
    poster_url: Optional[str] = None  # 海報圖片URL
    description: Optional[str] = None  # 電影描述
    director: Optional[str] = None  # 導演
    cast: Optional[str] = None  # 演員陣容
    runtime: Optional[int] = None  # 時長(分鐘)
    language: Optional[str] = None  # 語言
    country: Optional[str] = None  # 製作國家
    
    # 統計信息
    average_rating: float = 0.0  # 平均評分
    rating_count: int = 0  # 評分數量
    view_count: int = 0
    like_count: int = 0  # 點贊數量
    favorite_count: int = 0  # 收藏數量
    comment_count: int = 0  # 評論數量
    
    genres: List[GenreResponse] = []
    
    class Config:
        from_attributes = True

# 评分和评论Schema
class RatingCreate(BaseModel):
    movie_id: int
    rating: float

# Review 相關 Schema 已合併到 Comment 中

# 評論管理Schema
class CommentCreate(BaseModel):
    """創建評論請求"""
    movie_id: int
    content: str
    rating: Optional[float] = None  # 可選的評分

class CommentUpdate(BaseModel):
    """更新評論請求"""
    content: str

class CommentResponse(BaseModel):
    """評論響應模型"""
    id: int
    user_id: int
    movie_id: int
    content: str
    rating: Optional[float] = None  # 評分
    created_at: datetime
    updated_at: Optional[datetime] = None
    user_username: str
    movie_title: str
    movie_year: Optional[int] = None
    user_rating: Optional[float] = None
    
    class Config:
        from_attributes = True

# 瀏覽歷史Schema
class ViewHistoryCreate(BaseModel):
    """創建瀏覽記錄請求"""
    movie_id: int
    view_duration: Optional[int] = 0
    view_type: Optional[str] = "detail"

class ViewHistoryResponse(BaseModel):
    """瀏覽歷史響應模型"""
    id: int
    user_id: int
    movie_id: int
    viewed_at: datetime
    view_duration: int
    view_type: str
    movie_title: str
    movie_year: Optional[int] = None
    movie_poster_url: Optional[str] = None
    movie_average_rating: Optional[float] = None
    movie_genres: Optional[str] = None
    user_rating: Optional[float] = None
    is_favorite: bool = False
    is_liked: bool = False
    has_review: bool = False
    
    class Config:
        from_attributes = True

# 評論分頁響應模型
class CommentPageResponse(BaseModel):
    comments: List[CommentResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
    
    class Config:
        from_attributes = True

class RecommendationItem(BaseModel):
    movie_id: int
    title: Optional[str] = None
    year: Optional[int] = None
    poster_url: Optional[str] = None
    average_rating: Optional[float] = 0.0
    rating_count: Optional[int] = 0
    genres: Optional[List[str]] = []
    runtime: Optional[int] = None
    language: Optional[str] = None
    director: Optional[str] = None
    cast: Optional[str] = None
    description: Optional[str] = None
    kg_score: float = 0.0
    combined_score: float = 0.0
    ann_score: float = 0.0
    gnn_score: float = 0.0
    reason: str = ""
    reason_details: List[str] = []
    # Traceable evidence for FYP write-up / debugging (optional so it won't break older clients)
    evidence: Optional[dict] = None

    class Config:
        from_attributes = True

class RecommendationResponse(BaseModel):
    user_id: int
    recommendations: List[RecommendationItem]

    class Config:
        from_attributes = True


