#!/usr/bin/env python3
"""
完整的 K-RagRec 實現
基於論文 "Knowledge Graph Retrieval-Augmented Generation for LLM-based Recommendation"
"""

import logging
import json
import numpy as np
from typing import List, Dict, Tuple, Optional, Set, Any
from dataclasses import dataclass
from neo4j import GraphDatabase
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
from datetime import datetime, timedelta
import math
import asyncio
from concurrent.futures import ThreadPoolExecutor

import sys
import os

# 確保可以匯入 models 模組
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import get_db
from models import User, Movie, ViewHistory, Rating, Genre, Like, Favorite, Comment
from services.pure_ollama_client import get_pure_ollama_client

logger = logging.getLogger(__name__)


def _entropy_from_counts(values: List[str]) -> float:
    if not values:
        return 0.0
    counts: Dict[str, int] = {}
    for v in values:
        k = str(v).strip()
        if not k:
            continue
        counts[k] = counts.get(k, 0) + 1
    total = float(sum(counts.values()))
    if total <= 0:
        return 0.0
    entropy = 0.0
    for c in counts.values():
        p = c / total
        entropy -= p * math.log(p + 1e-12, 2)
    # Normalize by a practical upper bound.
    max_h = math.log(max(len(counts), 2), 2)
    return max(0.0, min(1.0, entropy / max_h)) if max_h > 0 else 0.0

@dataclass
class KGSubgraph:
    """知識圖譜子圖 - 論文核心數據結構"""
    movie_id: int
    title: str
    year: int
    genres: List[str]
    directors: List[str]
    actors: List[str]
    
    # 結構關係
    similar_movies: List[int]  # 相似電影
    co_director_movies: List[int]  # 同導演電影
    co_actor_movies: List[int]     # 同演員電影
    same_genre_movies: List[int]   # 同類型電影
    sequel_movies: List[int]       # 續集電影
    franchise_movies: List[int]    # 系列電影
    
    # 評分和流行度
    rating: float
    rating_count: int
    view_count: int
    like_count: int
    favorite_count: int
    
    # 計算得分
    popularity_score: float
    quality_score: float
    diversity_score: float
    
    # 嵌入向量
    embedding: Optional[np.ndarray] = None

@dataclass
class UserContext:
    """用戶上下文 - 論文中的用戶建模"""
    user_id: int
    recent_movies: List[int]
    preferred_genres: List[str]
    preferred_directors: List[str]
    preferred_actors: List[str]
    rating_pattern: Dict[str, float]  # 評分模式
    activity_level: str  # 'high', 'medium', 'low'
    cold_start: bool
    diversity_preference: float
    novelty_seeking: float

class SubgraphIndexer:
    """子圖索引器 - 論文核心組件1"""
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        self.subgraph_cache = {}
        self.cache_ttl = 3600  # 1小時緩存
        
    def build_movie_subgraph(self, movie_id: int, db: Session) -> KGSubgraph:
        """構建電影子圖"""
        with self.driver.session() as session:
            # 獲取電影基本信息
            movie = db.query(Movie).filter(Movie.id == movie_id).first()
            if not movie:
                return None
                
            # 獲取類型
            genres = [g.name for g in movie.genres]
            
            # 獲取導演和演員
            directors = [movie.director] if movie.director else []
            actors = [a.strip() for a in movie.cast.split(',') if a.strip()] if movie.cast else []
            
            # 查詢相似電影（基於類型）
            similar_query = """
            MATCH (m:Movie {movie_id: $movie_id})
            MATCH (m)-[:HAS_GENRE]->(g:Genre)<-[:HAS_GENRE]-(similar:Movie)
            WHERE similar.movie_id <> $movie_id
            RETURN DISTINCT similar.movie_id as id, similar.title as title, similar.year as year, similar.average_rating as rating
            ORDER BY rating DESC
            LIMIT 20
            """
            try:
                similar_result = session.run(similar_query, movie_id=movie_id)
                similar_movies = [record["id"] for record in similar_result]
            except Exception as neo_exc:
                logger.warning(f"Neo4j similar_movies query failed for movie_id={movie_id}: {neo_exc}")
                similar_movies = []
            
            # 查詢同導演電影
            co_director_query = """
            MATCH (m:Movie {movie_id: $movie_id})
            MATCH (m)-[:DIRECTED_BY]->(d:Person {type: 'Director'})<-[:DIRECTED_BY]-(co_dir:Movie)
            WHERE co_dir.movie_id <> $movie_id
            RETURN DISTINCT co_dir.movie_id as id, co_dir.average_rating as rating
            ORDER BY rating DESC
            LIMIT 10
            """
            try:
                co_director_result = session.run(co_director_query, movie_id=movie_id)
                co_director_movies = [record["id"] for record in co_director_result]
            except Exception as neo_exc:
                logger.warning(f"Neo4j co_director query failed for movie_id={movie_id}: {neo_exc}")
                co_director_movies = []
            
            # 查詢同演員電影
            co_actor_query = """
            MATCH (m:Movie {movie_id: $movie_id})
            MATCH (m)-[:STARRED_BY]->(a:Person {type: 'Actor'})<-[:STARRED_BY]-(co_actor:Movie)
            WHERE co_actor.movie_id <> $movie_id
            RETURN DISTINCT co_actor.movie_id as id, co_actor.average_rating as rating
            ORDER BY rating DESC
            LIMIT 15
            """
            try:
                co_actor_result = session.run(co_actor_query, movie_id=movie_id)
                co_actor_movies = [record["id"] for record in co_actor_result]
            except Exception as neo_exc:
                logger.warning(f"Neo4j co_actor query failed for movie_id={movie_id}: {neo_exc}")
                co_actor_movies = []
            
            # 查詢同類型電影
            same_genre_query = """
            MATCH (m:Movie {movie_id: $movie_id})
            MATCH (m)-[:HAS_GENRE]->(g:Genre)<-[:HAS_GENRE]-(same_genre:Movie)
            WHERE same_genre.movie_id <> $movie_id
            RETURN DISTINCT same_genre.movie_id as id, same_genre.average_rating as rating
            ORDER BY rating DESC
            LIMIT 15
            """
            try:
                same_genre_result = session.run(same_genre_query, movie_id=movie_id)
                same_genre_movies = [record["id"] for record in same_genre_result]
            except Exception as neo_exc:
                logger.warning(f"Neo4j same_genre query failed for movie_id={movie_id}: {neo_exc}")
                same_genre_movies = []
            
            # 計算得分
            popularity_score = self._calculate_popularity_score(movie)
            quality_score = self._calculate_quality_score(movie)
            diversity_score = self._calculate_diversity_score(genres, directors, actors)
            
            return KGSubgraph(
                movie_id=movie_id,
                title=movie.title,
                year=movie.year,
                genres=genres,
                directors=directors,
                actors=actors,
                similar_movies=similar_movies,
                co_director_movies=co_director_movies,
                co_actor_movies=co_actor_movies,
                same_genre_movies=same_genre_movies,
                sequel_movies=[],  # 需要額外實現
                franchise_movies=[],  # 需要額外實現
                rating=movie.average_rating or 0.0,
                rating_count=movie.rating_count or 0,
                view_count=movie.view_count or 0,
                like_count=movie.like_count or 0,
                favorite_count=movie.favorite_count or 0,
                popularity_score=popularity_score,
                quality_score=quality_score,
                diversity_score=diversity_score
            )
    
    def _calculate_popularity_score(self, movie: Movie) -> float:
        """計算流行度得分"""
        view_weight = 0.4
        rating_weight = 0.3
        like_weight = 0.2
        favorite_weight = 0.1
        
        view_score = min(movie.view_count or 0, 10000) / 10000
        rating_score = (movie.average_rating or 0) / 5.0
        like_score = min(movie.like_count or 0, 1000) / 1000
        favorite_score = min(movie.favorite_count or 0, 500) / 500
        
        return (view_score * view_weight + 
                rating_score * rating_weight + 
                like_score * like_weight + 
                favorite_score * favorite_weight)
    
    def _calculate_quality_score(self, movie: Movie) -> float:
        """計算質量得分"""
        rating_score = (movie.average_rating or 0) / 5.0
        rating_count_score = min(movie.rating_count or 0, 1000) / 1000
        
        return rating_score * 0.7 + rating_count_score * 0.3
    
    def _calculate_diversity_score(self, genres: List[str], directors: List[str], actors: List[str]) -> float:
        """計算多樣性得分"""
        genre_diversity = len(set(genres)) / 5.0  # 假設最多5個類型
        cast_diversity = len(set(actors)) / 10.0  # 假設最多10個演員
        
        return min(genre_diversity + cast_diversity, 1.0)

class AdaptiveRetriever:
    """自適應檢索器 - 論文核心組件2"""
    
    def __init__(self, subgraph_indexer: SubgraphIndexer):
        self.indexer = subgraph_indexer
        self.retrieval_strategies = {
            'cold_start': self._cold_start_retrieval,
            'preference_based': self._preference_based_retrieval,
            'diversity_focused': self._diversity_focused_retrieval,
            'quality_focused': self._quality_focused_retrieval
        }
    
    def retrieve_subgraphs(self, user_context: UserContext, candidate_movies: List[int], 
                          db: Session, max_subgraphs: int = 10) -> List[KGSubgraph]:
        """自適應檢索子圖"""
        
        # 選擇檢索策略
        strategy = self._select_retrieval_strategy(user_context)
        
        # 執行檢索
        subgraphs = self.retrieval_strategies[strategy](
            user_context, candidate_movies, db, max_subgraphs
        )
        
        return subgraphs

    def analyze_user_context(self, user_id: int, db: Session) -> UserContext:
        """輕量級用戶上下文分析，供調試端點使用。
        與 K_RagRecRecommender._build_user_context 一致性足夠即可，無需完全相同。"""
        # 最近觀看
        recent_movies = db.query(ViewHistory.movie_id).filter(
            ViewHistory.user_id == user_id
        ).order_by(desc(ViewHistory.viewed_at)).limit(20).all()
        recent_movie_ids = [m[0] for m in recent_movies]

        # 評分記錄
        ratings = db.query(Rating).filter(Rating.user_id == user_id).all()

        # 偏好統計
        preferred_genres: List[str] = []
        preferred_directors: List[str] = []
        preferred_actors: List[str] = []
        rating_pattern: Dict[str, float] = {}

        genre_scores: Dict[str, List[float]] = {}
        director_scores: Dict[str, List[float]] = {}
        actor_scores: Dict[str, List[float]] = {}
        for r in ratings:
            movie = db.query(Movie).filter(Movie.id == r.movie_id).first()
            if not movie:
                continue
            for g in movie.genres:
                genre_scores.setdefault(g.name, []).append(r.rating)
            if movie.director:
                director_scores.setdefault(movie.director, []).append(r.rating)
            if movie.cast:
                for a in [x.strip() for x in movie.cast.split(',') if x.strip()]:
                    actor_scores.setdefault(a, []).append(r.rating)

        for group in (genre_scores, director_scores, actor_scores):
            for key, scores in group.items():
                rating_pattern[key] = sum(scores) / len(scores)

        preferred_genres = [k for k, v in sorted(((k, sum(v)/len(v)) for k, v in genre_scores.items()), key=lambda x: x[1], reverse=True) if v >= 3.0][:5]
        preferred_directors = [k for k, v in sorted(((k, sum(v)/len(v)) for k, v in director_scores.items()), key=lambda x: x[1], reverse=True) if v >= 3.0][:3]
        preferred_actors = [k for k, v in sorted(((k, sum(v)/len(v)) for k, v in actor_scores.items()), key=lambda x: x[1], reverse=True) if v >= 3.0][:5]

        diversity_preference = _entropy_from_counts(preferred_genres)
        novelty_seeking = 1.0 - min(len(recent_movie_ids), 20) / 20.0 if recent_movie_ids else 0.5

        return UserContext(
            user_id=user_id,
            recent_movies=recent_movie_ids,
            preferred_genres=preferred_genres,
            preferred_directors=preferred_directors,
            preferred_actors=preferred_actors,
            rating_pattern=rating_pattern,
            activity_level='high' if len(ratings) > 50 else 'medium' if len(ratings) > 20 else 'low',
            cold_start=len(ratings) < 5,
            diversity_preference=diversity_preference,
            novelty_seeking=novelty_seeking
        )

    def should_retrieve_kg(self, context: UserContext) -> bool:
        """根據上下文判斷是否需要檢索 KG。"""
        if context.cold_start:
            # 冷啟動時仍可用 KG 幫助擴展，但若活動極低可暫緩
            return context.activity_level != 'low'
        # 非冷啟動，偏好多樣或活動中高時檢索 KG
        return context.diversity_preference >= 0.3 or context.activity_level in ('medium', 'high')
    
    def _select_retrieval_strategy(self, user_context: UserContext) -> str:
        """選擇檢索策略"""
        if user_context.cold_start:
            return 'cold_start'
        elif user_context.diversity_preference > 0.7:
            return 'diversity_focused'
        elif user_context.novelty_seeking > 0.6:
            return 'quality_focused'
        else:
            return 'preference_based'
    
    def _cold_start_retrieval(self, user_context: UserContext, candidate_movies: List[int], 
                             db: Session, max_subgraphs: int) -> List[KGSubgraph]:
        """冷啟動檢索 - 基於流行度和質量"""
        subgraphs = []
        
        for movie_id in candidate_movies[:max_subgraphs]:
            subgraph = self.indexer.build_movie_subgraph(movie_id, db)
            if subgraph:
                # 冷啟動時優先考慮流行度和質量
                score = (subgraph.popularity_score * 0.6 + 
                        subgraph.quality_score * 0.4)
                subgraph.embedding = np.array([score])  # 簡化嵌入
                subgraphs.append(subgraph)
        
        return sorted(subgraphs, key=lambda x: x.popularity_score + x.quality_score, reverse=True)
    
    def _preference_based_retrieval(self, user_context: UserContext, candidate_movies: List[int], 
                                   db: Session, max_subgraphs: int) -> List[KGSubgraph]:
        """基於偏好的檢索"""
        subgraphs = []
        
        for movie_id in candidate_movies:
            subgraph = self.indexer.build_movie_subgraph(movie_id, db)
            if subgraph:
                # 計算偏好匹配得分
                preference_score = self._calculate_preference_match(subgraph, user_context)
                subgraph.embedding = np.array([preference_score])
                subgraphs.append(subgraph)
        
        return sorted(subgraphs, key=lambda x: x.embedding[0] if x.embedding is not None else 0, reverse=True)[:max_subgraphs]
    
    def _diversity_focused_retrieval(self, user_context: UserContext, candidate_movies: List[int], 
                                    db: Session, max_subgraphs: int) -> List[KGSubgraph]:
        """多樣性導向檢索"""
        subgraphs = []
        
        for movie_id in candidate_movies:
            subgraph = self.indexer.build_movie_subgraph(movie_id, db)
            if subgraph:
                # 多樣性得分
                diversity_score = subgraph.diversity_score
                subgraph.embedding = np.array([diversity_score])
                subgraphs.append(subgraph)
        
        return sorted(subgraphs, key=lambda x: x.diversity_score, reverse=True)[:max_subgraphs]
    
    def _quality_focused_retrieval(self, user_context: UserContext, candidate_movies: List[int], 
                                  db: Session, max_subgraphs: int) -> List[KGSubgraph]:
        """質量導向檢索"""
        subgraphs = []
        
        for movie_id in candidate_movies:
            subgraph = self.indexer.build_movie_subgraph(movie_id, db)
            if subgraph:
                # 質量得分
                quality_score = subgraph.quality_score
                subgraph.embedding = np.array([quality_score])
                subgraphs.append(subgraph)
        
        return sorted(subgraphs, key=lambda x: x.quality_score, reverse=True)[:max_subgraphs]
    
    def _calculate_preference_match(self, subgraph: KGSubgraph, user_context: UserContext) -> float:
        """計算偏好匹配得分"""
        genre_match = len(set(subgraph.genres) & set(user_context.preferred_genres)) / max(len(user_context.preferred_genres), 1)
        director_match = len(set(subgraph.directors) & set(user_context.preferred_directors)) / max(len(user_context.preferred_directors), 1)
        actor_match = len(set(subgraph.actors) & set(user_context.preferred_actors)) / max(len(user_context.preferred_actors), 1)
        
        return (genre_match * 0.5 + director_match * 0.3 + actor_match * 0.2)

class Reranker:
    """重新排序器 - 論文核心組件3"""
    
    def __init__(self):
        self.reranking_weights = {
            'preference_match': 0.4,
            'quality_score': 0.3,
            'popularity_score': 0.2,
            'diversity_score': 0.1
        }
    
    def rerank_subgraphs(self, subgraphs: List[KGSubgraph], user_context: UserContext) -> List[KGSubgraph]:
        """重新排序子圖"""
        for subgraph in subgraphs:
            # 計算綜合得分
            final_score = self._calculate_final_score(subgraph, user_context)
            subgraph.embedding = np.array([final_score])
        
        return sorted(subgraphs, key=lambda x: x.embedding[0] if x.embedding is not None else 0, reverse=True)
    
    def _calculate_final_score(self, subgraph: KGSubgraph, user_context: UserContext) -> float:
        """計算最終得分"""
        preference_match = self._calculate_preference_match(subgraph, user_context)
        
        final_score = (
            preference_match * self.reranking_weights['preference_match'] +
            subgraph.quality_score * self.reranking_weights['quality_score'] +
            subgraph.popularity_score * self.reranking_weights['popularity_score'] +
            subgraph.diversity_score * self.reranking_weights['diversity_score']
        )
        
        return final_score
    
    def _calculate_preference_match(self, subgraph: KGSubgraph, user_context: UserContext) -> float:
        """計算偏好匹配"""
        genre_match = len(set(subgraph.genres) & set(user_context.preferred_genres)) / max(len(user_context.preferred_genres), 1)
        director_match = len(set(subgraph.directors) & set(user_context.preferred_directors)) / max(len(user_context.preferred_directors), 1)
        actor_match = len(set(subgraph.actors) & set(user_context.preferred_actors)) / max(len(user_context.preferred_actors), 1)
        
        return (genre_match * 0.5 + director_match * 0.3 + actor_match * 0.2)

class K_RagRecRecommender:
    """K-RagRec 推薦器 - 論文核心組件4"""
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        self.subgraph_indexer = SubgraphIndexer(neo4j_driver)
        self.adaptive_retriever = AdaptiveRetriever(self.subgraph_indexer)
        self.reranker = Reranker()
        self.ollama_client = get_pure_ollama_client()

    def _apply_candidate_constraints(self, query, constraints: Optional[Dict[str, Any]]):
        if not constraints:
            return query
        include_genres = [str(x).strip().lower() for x in (constraints.get("include_genres") or []) if str(x).strip()]
        exclude_genres = [str(x).strip().lower() for x in (constraints.get("exclude_genres") or []) if str(x).strip()]
        min_year = constraints.get("min_year")
        max_year = constraints.get("max_year")
        min_rating = constraints.get("min_rating")
        languages = [str(x).strip().lower() for x in (constraints.get("languages") or []) if str(x).strip()]
        countries = [str(x).strip().lower() for x in (constraints.get("countries") or []) if str(x).strip()]
        max_runtime = constraints.get("max_runtime")
        if include_genres:
            query = query.filter(Movie.genres.any(func.lower(Genre.name).in_(include_genres)))
        if exclude_genres:
            query = query.filter(~Movie.genres.any(func.lower(Genre.name).in_(exclude_genres)))
        if isinstance(min_year, int):
            query = query.filter(Movie.year >= int(min_year))
        if isinstance(max_year, int):
            query = query.filter(Movie.year <= int(max_year))
        if isinstance(min_rating, (int, float)):
            query = query.filter(Movie.average_rating >= float(min_rating))
        if languages:
            if len(languages) == 1:
                query = query.filter(func.lower(Movie.language).like(f"%{languages[0]}%"))
            else:
                query = query.filter(func.lower(Movie.language).in_(languages))
        if countries:
            query = query.filter(func.lower(Movie.country).in_(countries))
        if isinstance(max_runtime, int):
            query = query.filter(Movie.runtime <= int(max_runtime))
        return query
    
    def generate_recommendations(self, user_id: int, db: Session, 
                                num_recommendations: int = 10, constraints: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """生成推薦"""
        
        # 1. 構建用戶上下文
        user_context = self._build_user_context(user_id, db)
        
        # 2. 獲取候選電影
        candidate_movies = self._get_candidate_movies(user_id, db, num_recommendations * 3, constraints=constraints)
        
        # 3. 檢索子圖
        subgraphs = self.adaptive_retriever.retrieve_subgraphs(
            user_context, candidate_movies, db, num_recommendations * 2
        )
        
        # 4. 重新排序
        reranked_subgraphs = self.reranker.rerank_subgraphs(subgraphs, user_context)
        
        # 5. 生成推薦解釋
        recommendations = []
        for i, subgraph in enumerate(reranked_subgraphs[:num_recommendations]):
            explanation = self._generate_explanation(subgraph, user_context)
            
            recommendations.append({
                "movie_id": subgraph.movie_id,
                "title": subgraph.title,
                "year": subgraph.year,
                "genres": subgraph.genres,
                "rating": subgraph.rating,
                "explanation": explanation,
                "score": subgraph.embedding[0] if subgraph.embedding is not None else 0,
                "rank": i + 1
            })
        
        return recommendations
    
    def _build_user_context(self, user_id: int, db: Session) -> UserContext:
        """構建用戶上下文"""
        # 獲取用戶最近觀看的電影
        recent_movies = db.query(ViewHistory.movie_id).filter(
            ViewHistory.user_id == user_id
        ).order_by(desc(ViewHistory.viewed_at)).limit(20).all()
        recent_movie_ids = [m[0] for m in recent_movies]
        
        # 獲取用戶評分記錄
        ratings = db.query(Rating).filter(Rating.user_id == user_id).all()
        
        # 分析偏好
        preferred_genres = []
        preferred_directors = []
        preferred_actors = []
        rating_pattern = {}
        genre_scores: Dict[str, List[float]] = {}
        director_scores: Dict[str, List[float]] = {}
        actor_scores: Dict[str, List[float]] = {}
        
        for rating in ratings:
            movie = db.query(Movie).filter(Movie.id == rating.movie_id).first()
            if movie:
                # 類型偏好
                for genre in movie.genres:
                    genre_scores.setdefault(genre.name, []).append(rating.rating)
                
                # 導演偏好
                if movie.director:
                    director_scores.setdefault(movie.director, []).append(rating.rating)
                
                # 演員偏好
                if movie.cast:
                    for actor in movie.cast.split(','):
                        actor = actor.strip()
                        if actor:
                            actor_scores.setdefault(actor, []).append(rating.rating)
        
        for bucket in (genre_scores, director_scores, actor_scores):
            for key, scores in bucket.items():
                rating_pattern[key] = sum(scores) / len(scores)

        preferred_genres = [k for k, v in sorted(((k, sum(v)/len(v)) for k, v in genre_scores.items()), key=lambda x: x[1], reverse=True) if v >= 3.0][:5]
        preferred_directors = [k for k, v in sorted(((k, sum(v)/len(v)) for k, v in director_scores.items()), key=lambda x: x[1], reverse=True) if v >= 3.0][:3]
        preferred_actors = [k for k, v in sorted(((k, sum(v)/len(v)) for k, v in actor_scores.items()), key=lambda x: x[1], reverse=True) if v >= 3.0][:5]
        
        # 判斷冷啟動
        cold_start = len(ratings) < 5
        
        # 活動水平
        activity_level = 'high' if len(ratings) > 50 else 'medium' if len(ratings) > 20 else 'low'
        
        # 多樣性偏好
        recent_genre_tokens: List[str] = []
        for mid in recent_movie_ids:
            movie = db.query(Movie).filter(Movie.id == mid).first()
            if movie:
                recent_genre_tokens.extend([g.name for g in movie.genres])
        diversity_preference = _entropy_from_counts(recent_genre_tokens)
        
        # 新奇尋求
        novelty_seeking = 1.0 - (len(recent_movie_ids) / 20.0) if recent_movie_ids else 0.5
        
        return UserContext(
            user_id=user_id,
            recent_movies=recent_movie_ids,
            preferred_genres=preferred_genres,
            preferred_directors=preferred_directors,
            preferred_actors=preferred_actors,
            rating_pattern=rating_pattern,
            activity_level=activity_level,
            cold_start=cold_start,
            diversity_preference=diversity_preference,
            novelty_seeking=novelty_seeking
        )
    
    def _get_candidate_movies(self, user_id: int, db: Session, limit: int, constraints: Optional[Dict[str, Any]] = None) -> List[int]:
        """獲取候選電影"""
        seen_ids = {
            int(x[0]) for x in db.query(Rating.movie_id).filter(Rating.user_id == user_id).all()
        }
        seen_ids |= {int(x[0]) for x in db.query(ViewHistory.movie_id).filter(ViewHistory.user_id == user_id).all()}
        seen_ids |= {int(x[0]) for x in db.query(Like.movie_id).filter(Like.user_id == user_id).all()}
        seen_ids |= {int(x[0]) for x in db.query(Favorite.movie_id).filter(Favorite.user_id == user_id).all()}
        seen_ids |= {int(x[0]) for x in db.query(Comment.movie_id).filter(Comment.user_id == user_id).all()}

        candidates: List[int] = []
        recent_history = (
            db.query(ViewHistory.movie_id)
            .filter(ViewHistory.user_id == user_id)
            .order_by(desc(ViewHistory.viewed_at))
            .limit(15)
            .all()
        )
        recent_ids = [int(x[0]) for x in recent_history]

        if recent_ids and self.driver:
            with self.driver.session() as session:
                kg_query = """
                MATCH (h:Movie)
                WHERE h.movie_id IN $hist_ids
                MATCH (h)-[:HAS_GENRE|DIRECTED_BY|STARRED_BY]->(e)<-[:HAS_GENRE|DIRECTED_BY|STARRED_BY]-(cand:Movie)
                WHERE NOT cand.movie_id IN $hist_ids
                RETURN DISTINCT cand.movie_id AS mid
                LIMIT $limit
                """
                try:
                    rows = session.run(kg_query, hist_ids=recent_ids, limit=max(limit, 40)).data()
                    candidates.extend([int(r["mid"]) for r in rows if r.get("mid") is not None])
                except Exception:
                    pass

        for mid in recent_ids[:8]:
            movie = db.query(Movie).filter(Movie.id == mid).first()
            if not movie:
                continue
            if movie.director:
                rows = db.query(Movie.id).filter(Movie.director == movie.director).limit(8).all()
                candidates.extend([int(x[0]) for x in rows])
            if movie.cast:
                first_actor = [a.strip() for a in movie.cast.split(',') if a.strip()]
                if first_actor:
                    rows = db.query(Movie.id).filter(Movie.cast.ilike(f"%{first_actor[0]}%")).limit(8).all()
                    candidates.extend([int(x[0]) for x in rows])

        popular = (
            self._apply_candidate_constraints(db.query(Movie.id), constraints)
            .filter(~Movie.id.in_(list(seen_ids) or [-1]))
            .order_by(desc(Movie.average_rating), desc(Movie.rating_count))
            .limit(max(limit, 30))
            .all()
        )
        candidates.extend([int(c[0]) for c in popular])

        dedup: List[int] = []
        seen = set(seen_ids)
        for mid in candidates:
            if mid in seen:
                continue
            if constraints:
                allowed = (
                    self._apply_candidate_constraints(db.query(Movie.id), constraints)
                    .filter(Movie.id == mid)
                    .first()
                )
                if allowed is None:
                    continue
            seen.add(mid)
            dedup.append(mid)
        return dedup[:limit]

    def recommend(self, user_id: int, db: Session, top_k: int = 10, constraints: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self.generate_recommendations(
            user_id=user_id,
            db=db,
            num_recommendations=top_k,
            constraints=constraints,
        )
    
    def _generate_explanation(self, subgraph: KGSubgraph, user_context: UserContext) -> str:
        """Generate short list-ready reasons without calling the LLM for every item."""
        reasons: List[str] = []
        shared_genres = sorted(set(subgraph.genres) & set(user_context.preferred_genres))
        shared_directors = sorted(set(subgraph.directors) & set(user_context.preferred_directors))
        shared_actors = sorted(set(subgraph.actors) & set(user_context.preferred_actors))
        if shared_genres:
            reasons.append(f"Matches your genres: {', '.join(shared_genres[:2])}")
        if shared_directors:
            reasons.append(f"Director match: {', '.join(shared_directors[:1])}")
        if shared_actors:
            reasons.append(f"Actor match: {', '.join(shared_actors[:2])}")
        if subgraph.rating >= 4.0:
            reasons.append(f"Strong community rating ({subgraph.rating:.1f}/5)")
        if subgraph.year >= 2018:
            reasons.append("Recent release")
        if not reasons:
            reasons.append("Recommended from your graph neighbors and viewing history")
        return " | ".join(reasons[:3])

# 全局實例
_k_ragrec_recommender = None

def get_k_ragrec_recommender(neo4j_driver=None):
    """獲取 K-RagRec 推薦器實例"""
    global _k_ragrec_recommender
    if _k_ragrec_recommender is None and neo4j_driver:
        _k_ragrec_recommender = K_RagRecRecommender(neo4j_driver)
    return _k_ragrec_recommender

if __name__ == "__main__":
    # 測試代碼
    print("🎬 K-RagRec 系統測試")
    print("=" * 50)
    
    # 這裡需要 Neo4j 驅動程序
    # driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
    # recommender = get_k_ragrec_recommender(driver)
    # print("✅ K-RagRec 推薦器初始化成功")
