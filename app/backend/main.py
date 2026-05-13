from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import or_, text
from sqlalchemy.exc import OperationalError as SAOperationalError
import uvicorn
import json
import sqlite3
import time
from contextlib import asynccontextmanager

from database import get_db, engine, Base
from models import User, Movie, Rating, Favorite, Genre, UserProfile, Like, ViewHistory, Comment
from schemas import (
    UserCreate, UserLogin, UserResponse, 
    UserUpdate,
    UserProfileResponse, UserProfileUpdate, PreferencesUpdate,
    MovieResponse, RatingCreate,
    # ReviewCreate 已合併到 Comment 中
    # 推薦相關Schema已移除
)
from auth import create_access_token, verify_token, get_password_hash, verify_password
# Movie enhancement service removed - using direct database operations
from api.comment_endpoints import router as comment_router
from api.view_history_endpoints import router as view_history_router
from api.recommend_endpoints import router as recommend_router
from api.llm_endpoints import router as llm_router
from services.statistics_updater import statistics_updater

# 创建数据库表
Base.metadata.create_all(bind=engine)


def _ensure_user_profile_columns() -> None:
    required_columns = {
        "genre_distribution_json": "TEXT",
        "director_distribution_json": "TEXT",
        "actor_distribution_json": "TEXT",
        "recent_activity_score": "FLOAT DEFAULT 0.0",
        "preference_drift_score": "FLOAT DEFAULT 0.0",
    }
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(user_profiles)")).fetchall()
            existing = {str(r[1]) for r in rows}
            for col_name, col_type in required_columns.items():
                if col_name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_type}"))
    except Exception:
        # Best effort only; the app should still boot even if schema upgrade fails.
        pass


_ensure_user_profile_columns()
import os
print(">>> EMB PATH =", os.getenv("MOVIE_EMB_PATH"))
# 安全JSON解析函數
def safe_json_loads(json_str):
    if not json_str or json_str.strip() == '':
        return []
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []


def commit_with_sqlite_retry(db: Session, retries: int = 5, base_sleep_seconds: float = 0.2) -> None:
    """Commit with retry for transient SQLite 'database is locked' errors."""
    for attempt in range(retries):
        try:
            db.commit()
            return
        except (sqlite3.OperationalError, SAOperationalError) as exc:
            error_text = str(exc).lower()
            if "database is locked" not in error_text:
                raise
            db.rollback()
            if attempt == retries - 1:
                raise HTTPException(
                    status_code=503,
                    detail="Database is busy. Please retry in a moment."
                )
            time.sleep(base_sleep_seconds * (attempt + 1))
        except Exception:
            db.rollback()
            raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    print("Movie recommendation system starting...")
    print("Recommendation system initialized")
    print("Database connection established")
    print("Cache service started")
    yield
    # 关闭时清理资源
    print("System shutting down...")

app = FastAPI(
    title="Movie Recommendation System",
    description="A comprehensive movie recommendation system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:8080",
        
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# 依赖项：获取当前用户
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

# 用户认证相关API
@app.post("/api/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # 检查邮箱是否已存在
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # 创建新用户
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        age=user_data.age,
        gender=user_data.gender,
        occupation=user_data.occupation
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # 不自動創建用戶檔案，讓用戶通過引導流程創建
    # 這樣可以區分"從未設置"和"主動跳過"的用戶
    
    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        age=db_user.age,
        gender=db_user.gender,
        occupation=db_user.occupation
    )

@app.post("/api/auth/login")
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            age=user.age,
            gender=user.gender,
            occupation=user.occupation
        )
    }

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        age=current_user.age,
        gender=current_user.gender,
        occupation=current_user.occupation
    )


@app.put("/api/auth/me", response_model=UserResponse)
async def update_current_user_info(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's basic information."""
    update_data = user_data.model_dump(exclude_unset=True)

    if "email" in update_data and update_data["email"]:
        existing_email = db.query(User).filter(
            User.email == update_data["email"],
            User.id != current_user.id
        ).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

    for field, value in update_data.items():
        setattr(current_user, field, value)

    commit_with_sqlite_retry(db)
    db.refresh(current_user)

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        age=current_user.age,
        gender=current_user.gender,
        occupation=current_user.occupation
    )

# 电影相关API
@app.get("/api/movies", response_model=list[MovieResponse])
async def get_movies(
    skip: int = 0, 
    limit: int = 20, 
    search: str = None,
    genre: str = None,
    year: int = None,
    min_rating: float = None,
    runtime_min: int = None,
    runtime_max: int = None,
    sort_by: str = "rating",
    db: Session = Depends(get_db)
):
    query = db.query(Movie)
    
    if search:
        q = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Movie.title.ilike(q),
                Movie.director.ilike(q),
                Movie.cast.ilike(q),
            )
        )
    
    if genre:
        query = query.join(Movie.genres).filter(Genre.name == genre)

    if year:
        query = query.filter(Movie.year == year)

    if min_rating is not None:
        query = query.filter(Movie.average_rating >= min_rating)

    if runtime_min is not None:
        query = query.filter(Movie.runtime >= runtime_min)

    if runtime_max is not None:
        query = query.filter(Movie.runtime <= runtime_max)

    if sort_by == "popularity":
        query = query.order_by(Movie.view_count.desc().nullslast(), Movie.rating_count.desc().nullslast())
    elif sort_by == "year":
        query = query.order_by(Movie.year.desc().nullslast(), Movie.average_rating.desc().nullslast())
    elif sort_by == "title":
        query = query.order_by(Movie.title.asc())
    else:
        query = query.order_by(Movie.average_rating.desc().nullslast(), Movie.rating_count.desc().nullslast())
    
    movies = query.offset(skip).limit(limit).all()
    return movies


@app.get("/api/movies/count")
async def get_movies_count(
    search: str = None,
    genre: str = None,
    year: int = None,
    min_rating: float = None,
    runtime_min: int = None,
    runtime_max: int = None,
    db: Session = Depends(get_db),
):
    query = db.query(Movie)

    if search:
        q = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Movie.title.ilike(q),
                Movie.director.ilike(q),
                Movie.cast.ilike(q),
            )
        )

    if genre:
        query = query.join(Movie.genres).filter(Genre.name == genre)
    if year:
        query = query.filter(Movie.year == year)
    if min_rating is not None:
        query = query.filter(Movie.average_rating >= min_rating)
    if runtime_min is not None:
        query = query.filter(Movie.runtime >= runtime_min)
    if runtime_max is not None:
        query = query.filter(Movie.runtime <= runtime_max)

    return {"total": query.count()}


@app.get("/api/movies/suggestions")
async def suggest_movies(query: str, limit: int = 8, db: Session = Depends(get_db)):
    q = (query or "").strip()
    if len(q) < 2:
        return []
    like_q = f"%{q}%"
    rows = (
        db.query(Movie.id, Movie.title, Movie.year)
        .filter(
            or_(
                Movie.title.ilike(like_q),
                Movie.director.ilike(like_q),
                Movie.cast.ilike(like_q),
            )
        )
        .order_by(Movie.rating_count.desc().nullslast(), Movie.average_rating.desc().nullslast())
        .limit(max(1, min(limit, 20)))
        .all()
    )
    return [{"id": r.id, "title": r.title, "year": r.year} for r in rows]

@app.get("/api/movies/popular", response_model=list[MovieResponse])
async def get_popular_movies(limit: int = 10, db: Session = Depends(get_db)):
    # 获取评分最高的电影，处理NULL值
    movies = db.query(Movie).order_by(
        Movie.average_rating.desc().nullslast(),
        Movie.rating_count.desc()
    ).limit(limit).all()
    return movies

@app.get("/api/movies/{movie_id}", response_model=MovieResponse)
async def get_movie(
    movie_id: int,
    db: Session = Depends(get_db)
):
    """獲取單部電影詳情（匿名可訪問）。
    注意：如需記錄瀏覽歷史與統計，請使用 /api/movies/{movie_id}/authenticated。
    """
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found"
        )
    return movie

@app.get("/api/movies/{movie_id}/authenticated", response_model=MovieResponse)
async def get_movie_authenticated(
    movie_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """獲取電影詳情並記錄用戶瀏覽歷史（需要認證）"""
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found"
        )
    
    # 增加電影瀏覽次數
    try:
        movie.view_count = (movie.view_count or 0) + 1
        db.commit()
        
        # 記錄用戶瀏覽歷史
        view_history = ViewHistory(
            user_id=current_user.id,
            movie_id=movie_id,
            view_duration=0,
            view_type="detail"
        )
        db.add(view_history)
        db.commit()
        
        # 更新統計數據
        from services.statistics_updater import statistics_updater
        statistics_updater.update_related_statistics(db, current_user.id, movie_id)
        
    except Exception as e:
        print(f"Failed to update view count and history: {e}")
        db.rollback()
    
    return movie

# OpenAI增強API

# 用户行为API
@app.post("/api/ratings")
async def create_rating(
    rating_data: RatingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # 验证评分范围
        if not (0.5 <= rating_data.rating <= 5.0):
            raise HTTPException(status_code=400, detail="Rating must be between 0.5 and 5.0")
        
        # 检查电影是否存在
        movie = db.query(Movie).filter(Movie.id == rating_data.movie_id).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        
        # 检查是否已评分
        existing_rating = db.query(Rating).filter(
            Rating.user_id == current_user.id,
            Rating.movie_id == rating_data.movie_id
        ).first()
        
        if existing_rating:
            existing_rating.rating = rating_data.rating
        else:
            db_rating = Rating(
                user_id=current_user.id,
                movie_id=rating_data.movie_id,
                rating=rating_data.rating
            )
            db.add(db_rating)
        
        db.commit()
        
        # 使用統一的統計更新器
        from services.statistics_updater import statistics_updater
        
        # 更新電影統計
        statistics_updater.update_movie_statistics(db, movie.id)
        
        # 更新用戶統計
        statistics_updater.update_user_statistics(db, current_user.id)
        
        # 清除相關緩存
                
        return {"message": "Rating created successfully", "rating": rating_data.rating}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating rating: {str(e)}")

@app.get("/api/ratings/{movie_id}")
async def get_user_rating(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's rating for a specific movie"""
        
    rating = db.query(Rating).filter(
        Rating.user_id == current_user.id,
        Rating.movie_id == movie_id
    ).first()
    
    result = {"rating": rating.rating, "has_rated": True} if rating else {"rating": 0, "has_rated": False}

    return result

# Review 端點已合併到 Comment 端點中
# 請使用 POST /api/comments/ 創建評論或評價

@app.post("/api/favorites/{movie_id}")
async def toggle_favorite(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 檢查電影是否存在
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    
    existing_favorite = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.movie_id == movie_id
    ).first()
    
    if existing_favorite:
        db.delete(existing_favorite)
        message = "Removed from favorites"
    else:
        db_favorite = Favorite(
            user_id=current_user.id,
            movie_id=movie_id
        )
        db.add(db_favorite)
        message = "Added to favorites"
        
        # 收藏時增加觀看次數
        movie.view_count = (movie.view_count or 0) + 1
    
    # 先提交收藏操作（加重試處理避免 sqlite locked）
    import time, sqlite3
    for _ in range(5):
        try:
            db.commit()
            break
        except Exception as e:
            # 僅對 sqlite locked 做簡單退避重試
            if isinstance(e, sqlite3.OperationalError) and "database is locked" in str(e):
                time.sleep(0.2)
                continue
            raise
    
    # 使用統一的統計更新器更新電影和用戶統計
    from services.statistics_updater import statistics_updater
    statistics_updater.update_related_statistics(db, current_user.id, movie_id)
    
    # 使相關緩存失效
        
    # statistics_updater已經處理了commit，不需要再次commit
    return {"message": message}

@app.get("/api/favorites", response_model=list[MovieResponse])
async def get_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    favorites = db.query(Movie).join(Favorite).filter(
        Favorite.user_id == current_user.id
    ).all()
    return favorites

@app.get("/api/likes", response_model=list[MovieResponse])
async def get_likes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    likes = db.query(Movie).join(Like).filter(
        Like.user_id == current_user.id
    ).all()
    return likes

# 點贊API
@app.post("/api/likes/{movie_id}")
async def toggle_like(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """切換電影點贊狀態"""
    # 檢查電影是否存在
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    
    # 檢查是否已點贊
    existing_like = db.query(Like).filter(
        Like.user_id == current_user.id,
        Like.movie_id == movie_id
    ).first()
    
    if existing_like:
        # 取消點贊
        db.delete(existing_like)
        message = "Unliked"
        is_liked = False
    else:
        # 添加點贊
        db_like = Like(
            user_id=current_user.id,
            movie_id=movie_id
        )
        db.add(db_like)
        message = "Liked"
        is_liked = True
    
    # 先提交點贊操作（加重試處理避免 sqlite locked）
    import time, sqlite3
    for _ in range(5):
        try:
            db.commit()
            break
        except Exception as e:
            if isinstance(e, sqlite3.OperationalError) and "database is locked" in str(e):
                time.sleep(0.2)
                continue
            raise
    
    # 使用統一的統計更新器更新電影和用戶統計
    statistics_updater.update_related_statistics(db, current_user.id, movie_id)
    
    # 使相關緩存失效
        
    # statistics_updater已經處理了commit，不需要再次commit
    
    # 獲取最新的電影數據
    updated_movie = db.query(Movie).filter(Movie.id == movie_id).first()
    
    return {
        "message": message,
        "is_liked": is_liked,
        "like_count": updated_movie.like_count or 0
    }

@app.get("/api/likes/{movie_id}")
async def get_like_status(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's like status for a movie"""
    like = db.query(Like).filter(
        Like.user_id == current_user.id,
        Like.movie_id == movie_id
    ).first()
    
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    
    return {
        "is_liked": like is not None,
        "like_count": movie.like_count or 0
    }

@app.get("/api/movies/{movie_id}/status")
async def get_movie_status(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's favorite and like status for a movie"""
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    
    # Check if user has favorited this movie
    favorite = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.movie_id == movie_id
    ).first()
    
    # Check if user has liked this movie
    like = db.query(Like).filter(
        Like.user_id == current_user.id,
        Like.movie_id == movie_id
    ).first()
    
    return {
        "is_favorite": favorite is not None,
        "is_liked": like is not None,
        "favorite_count": movie.favorite_count or 0,
        "like_count": movie.like_count or 0
    }

# 用户档案相关API
@app.get("/api/profile", response_model=UserProfileResponse | None)
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's profile"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        # 如果沒有用戶資料，返回None，讓前端處理引導流程
        return None
    
    # Convert JSON strings to lists with safe parsing
    
    from datetime import datetime
    profile_data = {
        "id": profile.id,
        "user_id": profile.user_id,
        "preferred_genres": safe_json_loads(profile.preferred_genres),
        "preferred_directors": safe_json_loads(profile.preferred_directors),
        "preferred_actors": safe_json_loads(profile.preferred_actors),
        "preferred_languages": safe_json_loads(profile.preferred_languages),
        "preferred_countries": safe_json_loads(profile.preferred_countries),
        "genre_distribution_json": safe_json_loads(profile.genre_distribution_json),
        "director_distribution_json": safe_json_loads(profile.director_distribution_json),
        "actor_distribution_json": safe_json_loads(profile.actor_distribution_json),
        "recent_activity_score": profile.recent_activity_score or 0.0,
        "preference_drift_score": profile.preference_drift_score or 0.0,
        "min_rating_threshold": profile.min_rating_threshold or 3.0,
        "max_runtime": profile.max_runtime,
        "min_runtime": profile.min_runtime,
        "total_ratings": profile.total_ratings or 0,
        "total_likes": profile.total_likes or 0,
        "total_favorites": profile.total_favorites or 0,
        "total_views": profile.total_views or 0,
        "average_rating_given": profile.average_rating_given or 0.0,
        "most_rated_year": profile.most_rated_year,
        "profile_setup_completed": profile.profile_setup_completed or False,
        "setup_skipped": profile.setup_skipped or False,
        "setup_completed_at": profile.setup_completed_at.isoformat() if isinstance(profile.setup_completed_at, datetime) else profile.setup_completed_at,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at
    }
    
    return UserProfileResponse(**profile_data)

@app.put("/api/profile", response_model=UserProfileResponse)
async def update_user_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile (create if not exists)"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    
    # 如果用戶資料不存在，創建一個新的
    if not profile:
        profile = UserProfile(
            user_id=current_user.id,
            preferred_genres=json.dumps([]),
            preferred_directors=json.dumps([]),
            preferred_actors=json.dumps([]),
            preferred_languages=json.dumps([]),
            preferred_countries=json.dumps([]),
            genre_distribution_json=json.dumps({}, ensure_ascii=False),
            director_distribution_json=json.dumps({}, ensure_ascii=False),
            actor_distribution_json=json.dumps({}, ensure_ascii=False),
            recent_activity_score=0.0,
            preference_drift_score=0.0,
            min_rating_threshold=3.0,
            total_ratings=0,
            average_rating_given=0.0,
            total_likes=0,
            total_favorites=0,
            total_views=0,
            profile_setup_completed=False,
            setup_skipped=False
        )
        db.add(profile)
        commit_with_sqlite_retry(db)
        db.refresh(profile)
    
    # Update profile fields
    from datetime import datetime
    for field, value in profile_data.model_dump(exclude_unset=True).items():
        if field in ["preferred_genres", "preferred_directors", "preferred_actors", 
                     "preferred_languages", "preferred_countries"] and value is not None:
            setattr(profile, field, json.dumps(value))
        elif field == "setup_completed_at" and value is not None:
            # Accept ISO string from client; convert to python datetime for SQLite
            try:
                # support '...Z' by normalizing to +00:00
                if isinstance(value, str) and value.endswith("Z"):
                    value = value.replace("Z", "+00:00")
                if isinstance(value, str):
                    value_dt = datetime.fromisoformat(value)
                else:
                    value_dt = value
                setattr(profile, field, value_dt)
            except Exception:
                # If parsing fails, skip setting to avoid 500
                pass
        else:
            setattr(profile, field, value)
    
    commit_with_sqlite_retry(db)
    db.refresh(profile)
    
    # Convert back to response format
    from datetime import datetime
    profile_data = {
        "id": profile.id,
        "user_id": profile.user_id,
        "preferred_genres": safe_json_loads(profile.preferred_genres),
        "preferred_directors": safe_json_loads(profile.preferred_directors),
        "preferred_actors": safe_json_loads(profile.preferred_actors),
        "preferred_languages": safe_json_loads(profile.preferred_languages),
        "preferred_countries": safe_json_loads(profile.preferred_countries),
        "genre_distribution_json": safe_json_loads(profile.genre_distribution_json),
        "director_distribution_json": safe_json_loads(profile.director_distribution_json),
        "actor_distribution_json": safe_json_loads(profile.actor_distribution_json),
        "recent_activity_score": profile.recent_activity_score or 0.0,
        "preference_drift_score": profile.preference_drift_score or 0.0,
        "min_rating_threshold": profile.min_rating_threshold or 3.0,
        "max_runtime": profile.max_runtime,
        "min_runtime": profile.min_runtime,
        "total_ratings": profile.total_ratings or 0,
        "total_likes": profile.total_likes or 0,
        "total_favorites": profile.total_favorites or 0,
        "total_views": profile.total_views or 0,
        "average_rating_given": profile.average_rating_given or 0.0,
        "most_rated_year": profile.most_rated_year,
        "profile_setup_completed": profile.profile_setup_completed or False,
        "setup_skipped": profile.setup_skipped or False,
        "setup_completed_at": profile.setup_completed_at.isoformat() if isinstance(profile.setup_completed_at, datetime) else profile.setup_completed_at,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at
    }
    
    return UserProfileResponse(**profile_data)

@app.put("/api/profile/preferences", response_model=UserProfileResponse)
async def update_preferences(
    preferences: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user preferences"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found"
        )
    
    # Update preference fields
    for field, value in preferences.dict(exclude_unset=True).items():
        if field in ["preferred_genres", "preferred_directors", "preferred_actors", 
                     "preferred_languages", "preferred_countries"] and value is not None:
            setattr(profile, field, json.dumps(value))
        else:
            setattr(profile, field, value)
    
    commit_with_sqlite_retry(db)
    db.refresh(profile)
    
    # Convert back to response format
    profile_data = {
        "id": profile.id,
        "user_id": profile.user_id,
        "preferred_genres": safe_json_loads(profile.preferred_genres),
        "preferred_directors": safe_json_loads(profile.preferred_directors),
        "preferred_actors": safe_json_loads(profile.preferred_actors),
        "preferred_languages": safe_json_loads(profile.preferred_languages),
        "preferred_countries": safe_json_loads(profile.preferred_countries),
        "genre_distribution_json": safe_json_loads(profile.genre_distribution_json),
        "director_distribution_json": safe_json_loads(profile.director_distribution_json),
        "actor_distribution_json": safe_json_loads(profile.actor_distribution_json),
        "recent_activity_score": profile.recent_activity_score or 0.0,
        "preference_drift_score": profile.preference_drift_score or 0.0,
        "min_rating_threshold": profile.min_rating_threshold or 3.0,
        "max_runtime": profile.max_runtime,
        "min_runtime": profile.min_runtime,
        "total_ratings": profile.total_ratings or 0,
        "total_likes": profile.total_likes or 0,
        "total_favorites": profile.total_favorites or 0,
        "total_views": profile.total_views or 0,
        "average_rating_given": profile.average_rating_given or 0.0,
        "most_rated_year": profile.most_rated_year,
        "profile_setup_completed": profile.profile_setup_completed or False,
        "setup_skipped": profile.setup_skipped or False,
        "setup_completed_at": profile.setup_completed_at.isoformat() if profile.setup_completed_at else None,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at
    }
    
    return UserProfileResponse(**profile_data)

# Onboarding status - simple boolean for frontend guards
@app.get("/api/onboarding/status")
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if profile is None:
        return {"needs_onboarding": True}
    needs = (not (profile.profile_setup_completed or False)) and (not (profile.setup_skipped or False))
    return {"needs_onboarding": needs}

# 健康检查
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "Movie Recommendation System is running"}

# 評論和瀏覽歷史路由
app.include_router(comment_router)
app.include_router(view_history_router)
app.include_router(recommend_router)
app.include_router(llm_router)

# 問卷路由
try:
    from api.questionnaire_endpoints import router as questionnaire_router
    app.include_router(questionnaire_router)
except ImportError as e:
    print(f"[Warning] Questionnaire router not available: {e}")

# K-RagRec 路由
try:
    from api.k_ragrec_endpoints import router as k_ragrec_router
    app.include_router(k_ragrec_router)
except ImportError as e:
    print(f"[Warning] K-RagRec router not available: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
