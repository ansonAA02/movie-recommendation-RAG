from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey, Table, BigInteger, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# 电影和类型的多对多关系表
movie_genre_association = Table(
    'movie_genre',
    Base.metadata,
    Column('movie_id', Integer, ForeignKey('movies.id'), primary_key=True),
    Column('genre_id', Integer, ForeignKey('genres.id'), primary_key=True)
)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    age = Column(Integer)
    gender = Column(String(10))
    occupation = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    ratings = relationship("Rating", back_populates="user")
    favorites = relationship("Favorite", back_populates="user")
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    view_history = relationship("ViewHistory")
    comments = relationship("Comment")

class Genre(Base):
    __tablename__ = "genres"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    
    # 关系
    movies = relationship("Movie", secondary=movie_genre_association, back_populates="genres")

class Movie(Base):
    __tablename__ = "movies"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)  # 電影標題
    year = Column(Integer)  # 年份
    imdb_id = Column(String(20), unique=True)  # IMDB ID
    poster_url = Column(String(500))  # 海報圖片URL
    description = Column(Text)  # 電影描述
    director = Column(String(255))  # 導演
    cast = Column(Text)  # 演員陣容
    runtime = Column(Integer)  # 時長(分鐘)
    language = Column(String(100))  # 語言
    country = Column(String(100))  # 製作國家
    
    # 統計信息
    average_rating = Column(Float, default=0.0)  # 平均評分
    rating_count = Column(Integer, default=0)  # 評分數量
    view_count = Column(Integer, default=0)  # 觀看次數
    like_count = Column(Integer, default=0)  # 點贊數量
    favorite_count = Column(Integer, default=0)  # 收藏數量
    comment_count = Column(Integer, default=0)  # 評論數量
    
    # 時間戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    genres = relationship("Genre", secondary=movie_genre_association, back_populates="movies")
    ratings = relationship("Rating", back_populates="movie")
    # reviews = relationship("Review", back_populates="movie")  # 已合併到 Comment
    favorites = relationship("Favorite", back_populates="movie")
    likes = relationship("Like")

class Rating(Base):
    __tablename__ = "ratings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    rating = Column(Float, nullable=False)  # 1-5星评分
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="ratings")
    movie = relationship("Movie", back_populates="ratings")

# Review 表已合併到 Comment 表中

class Favorite(Base):
    __tablename__ = "favorites"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    user = relationship("User", back_populates="favorites")
    movie = relationship("Movie", back_populates="favorites")

class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # 偏好设置
    preferred_genres = Column(Text)  # JSON字符串存储偏好的类型
    preferred_directors = Column(Text)  # JSON字符串存储偏好的导演
    preferred_actors = Column(Text)  # JSON字符串存储偏好的演员
    preferred_languages = Column(Text)  # JSON字符串存储偏好的语言
    preferred_countries = Column(Text)  # JSON字符串存储偏好的国家
    genre_distribution_json = Column(Text)  # JSON字符串存储類型分佈
    director_distribution_json = Column(Text)  # JSON字符串存储導演分佈
    actor_distribution_json = Column(Text)  # JSON字符串存储演員分佈
    recent_activity_score = Column(Float, default=0.0)  # 近期活躍度
    preference_drift_score = Column(Float, default=0.0)  # 與歷史偏好的漂移程度
    
    # 评分偏好
    min_rating_threshold = Column(Float, default=3.0)  # 最低评分阈值
    max_runtime = Column(Integer)  # 最大时长偏好(分钟)
    min_runtime = Column(Integer)  # 最小时长偏好(分钟)
    
    # 统计信息
    total_ratings = Column(Integer, default=0)  # 总评分数量
    total_likes = Column(Integer, default=0)  # 总点赞数量
    total_favorites = Column(Integer, default=0)  # 总收藏数量
    total_views = Column(Integer, default=0)  # 总观看数量
    total_comments = Column(Integer, default=0)  # 总评论数量
    average_rating_given = Column(Float, default=0.0)  # 用户给出的平均评分
    most_rated_year = Column(Integer)  # 评分最多的年份
    
    # 引導流程狀態
    profile_setup_completed = Column(Boolean, default=False)  # 是否完成檔案設置
    setup_skipped = Column(Boolean, default=False)  # 是否跳過設置
    setup_completed_at = Column(DateTime(timezone=True))  # 完成設置的時間
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="profile")

class Like(Base):
    """點贊表"""
    __tablename__ = "likes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    user = relationship("User")
    movie = relationship("Movie", overlaps="likes")
    
    # 唯一約束：每個用戶只能對每部電影點贊一次
    __table_args__ = (
        UniqueConstraint('user_id', 'movie_id', name='unique_user_movie_like'),
    )

class ViewHistory(Base):
    """用戶瀏覽歷史表"""
    __tablename__ = "view_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    viewed_at = Column(DateTime(timezone=True), server_default=func.now())
    view_duration = Column(Integer, default=0)  # 瀏覽時長（秒）
    view_type = Column(String(20), default="detail")  # 瀏覽類型：detail, list, search
    
    # 关系
    user = relationship("User", overlaps="view_history")
    movie = relationship("Movie")
    
    # 索引優化
    __table_args__ = (
        Index('idx_user_viewed_at', 'user_id', 'viewed_at'),
        Index('idx_movie_viewed_at', 'movie_id', 'viewed_at'),
    )


class Comment(Base):
    """統一評論表 - 包含評論和評價"""
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    content = Column(Text, nullable=False)
    rating = Column(Float, nullable=True)  # 可選的評分
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", overlaps="comments")
    movie = relationship("Movie")
    
    # 索引優化
    __table_args__ = (
        Index('idx_comment_user', 'user_id'),
        Index('idx_comment_movie', 'movie_id'),
        Index('idx_comment_created', 'created_at'),
    )


class ExplanationRating(Base):
    """Explanation quality rating for user study (Likert scale 1-5)."""
    __tablename__ = "explanation_ratings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    explanation = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 Likert scale
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    user = relationship("User")
    movie = relationship("Movie")
    
    # 索引優化
    __table_args__ = (
        Index('idx_explanation_rating_user', 'user_id'),
        Index('idx_explanation_rating_movie', 'movie_id'),
        Index('idx_explanation_rating_created', 'created_at'),
    )

