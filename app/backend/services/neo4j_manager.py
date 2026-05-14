#!/usr/bin/env python3
"""
Neo4j 數據庫管理系統
提供完整的 Neo4j 數據庫管理、同步和監控功能

功能包括：
1. 數據庫結構檢查
2. 自動增量同步
3. 手動全量同步
4. 數據庫健康監控
5. 性能優化建議
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy.orm import Session
from neo4j import GraphDatabase
from dotenv import load_dotenv
from tqdm import tqdm

# 調整匯入路徑，讓可以從 backend 根目錄匯入 database/models
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))   # app/backend/services
BACKEND_DIR = os.path.dirname(CURRENT_DIR)                 # app/backend
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import get_db  # type: ignore
from models import User, Movie, Genre, Rating, Favorite, Like, ViewHistory, UserProfile, Comment  # type: ignore

load_dotenv()

# 配置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _json_safe(value):
    """Recursively convert Neo4j driver values to JSON-serializable primitives.

    - neo4j.time.DateTime/Date/Time -> ISO string via .isoformat()
    - dict/list/tuple/set -> recurse
    - bytes -> utf-8 string fallback
    - others -> unchanged
    """
    # neo4j temporal types support isoformat()
    try:
        # Guard against objects that implement isoformat (datetime-like)
        if hasattr(value, "isoformat"):
            return value.isoformat()
    except Exception:
        pass

    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [ _json_safe(v) for v in value ]
    if isinstance(value, set):
        return [ _json_safe(v) for v in value ]
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return str(value)
    return value


def _resolve_neo4j_username(explicit_user: Optional[str] = None) -> str:
    """Resolve the Neo4j username across local and Aura-style env names."""
    return explicit_user or os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j")



    """Neo4j 數據庫管理器 - 整合了所有 Neo4j 操作功能"""
    
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.neo4j_uri = uri or os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
        self.neo4j_user = _resolve_neo4j_username(user)
        self.neo4j_password = password or os.getenv("NEO4J_PASSWORD", "12345678")
        self.driver = None
        self.last_sync_time = None
        
    def connect(self) -> bool:
        """連接到 Neo4j 數據庫"""
        try:
            self.driver = GraphDatabase.driver(
                self.neo4j_uri, 
                auth=(self.neo4j_user, self.neo4j_password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=60
            )
            # 測試連接
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("✅ 成功連接到 Neo4j 數據庫")
            return True
        except Exception as e:
            logger.error(f"❌ 連接 Neo4j 失敗: {e}")
            return False
    
    def get_movie_subgraph(self, movie_id: int, depth: int = 2) -> Dict[str, Any]:
        """獲取電影子圖信息 - 整合自 neo4j_client.py"""
        if not self.driver:
            return {}
        
        cypher = f"""
            MATCH (m:Movie {{movie_id:$movieId}})
            OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d:Person)
            OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
            OPTIONAL MATCH (m)-[:STARRED_BY]->(a:Person)
            OPTIONAL MATCH (m)-[:SIMILAR_TO]->(s:Movie)
            
            // Multi-hop relationships
            OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d)-[:DIRECTED_BY]->(co_dir_movies:Movie)
            WHERE co_dir_movies.movie_id <> $movieId
            OPTIONAL MATCH (m)-[:STARRED_BY]->(a)-[:STARRED_BY]->(co_actor_movies:Movie)
            WHERE co_actor_movies.movie_id <> $movieId
            OPTIONAL MATCH (m)-[:HAS_GENRE]->(g)<-[:HAS_GENRE]-(same_genre_movies:Movie)
            WHERE same_genre_movies.movie_id <> $movieId
            
            RETURN m.movie_id AS movie_id, 
                   m.title AS title,
                   m.year AS year,
                   m.average_rating AS rating,
                   m.rating_count AS rating_count,
                   m.view_count AS view_count,
                   collect(DISTINCT d.name)[..3] AS directors,
                   collect(DISTINCT g.name)[..5] AS genres,
                   collect(DISTINCT a.name)[..5] AS actors,
                   collect(DISTINCT s.movie_id)[..10] AS similar_movies,
                   collect(DISTINCT co_dir_movies.movie_id)[..5] AS co_director_movies,
                   collect(DISTINCT co_actor_movies.movie_id)[..5] AS co_actor_movies,
                   collect(DISTINCT same_genre_movies.movie_id)[..5] AS same_genre_movies
        """
        
        try:
            with self.driver.session() as session:
                rec = session.run(cypher, movieId=movie_id).single()
                if not rec:
                    return {}
                
                data = rec.data()
                
                # Calculate popularity score
                rating_count = data.get('rating_count', 0) or 0
                view_count = data.get('view_count', 0) or 0
                popularity_score = min((rating_count / 1000) * 0.7 + (view_count / 10000) * 0.3, 1.0)
                data['popularity_score'] = popularity_score
                
                return data
        except Exception as exc:
            logger.error(f"獲取電影子圖失敗 movie_id={movie_id}: {exc}")
            return {}
    
    def close(self):
        """關閉 Neo4j 連接"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j 連接已關閉")
    
    def get_database_stats(self) -> Dict[str, Any]:
        """獲取數據庫統計信息"""
        if not self.driver:
            return {}
        
        try:
            with self.driver.session() as session:
                node_stats = None
                try:
                    # English comment: Prefer APOC stats when the plugin is available.
                    node_stats = session.run("""
                        CALL apoc.meta.stats() YIELD labels, relTypes
                        RETURN labels, relTypes
                    """).single()
                except Exception as apoc_error:
                    logger.warning(f"APOC stats unavailable, falling back to manual counts: {apoc_error}")
                
                if not node_stats:
                    # English comment: Fall back to plain Cypher counts when APOC is not installed.
                    movie_count = session.run("MATCH (m:Movie) RETURN count(m) as count").single()['count']
                    user_count = session.run("MATCH (u:User) RETURN count(u) as count").single()['count']
                    genre_count = session.run("MATCH (g:Genre) RETURN count(g) as count").single()['count']
                    person_count = session.run("MATCH (p:Person) RETURN count(p) as count").single()['count']
                    
                    # 關係統計
                    rating_count = session.run("MATCH ()-[r:RATED]->() RETURN count(r) as count").single()['count']
                    view_count = session.run("MATCH ()-[r:VIEWED]->() RETURN count(r) as count").single()['count']
                    similar_count = session.run("MATCH ()-[r:SIMILAR_TO]->() RETURN count(r) as count").single()['count']
                    
                    return {
                        "nodes": {
                            "Movie": movie_count,
                            "User": user_count,
                            "Genre": genre_count,
                            "Person": person_count
                        },
                        "relationships": {
                            "RATED": rating_count,
                            "VIEWED": view_count,
                            "SIMILAR_TO": similar_count
                        }
                    }
                else:
                    return {
                        "nodes": dict(node_stats['labels']),
                        "relationships": dict(node_stats['relTypes'])
                    }
                    
        except Exception as e:
            logger.error(f"獲取數據庫統計失敗: {e}")
            return {}
    
    def check_database_health(self) -> Dict[str, Any]:
        """檢查數據庫健康狀態"""
        if not self.driver:
            return {"status": "disconnected", "message": "Neo4j not connected"}
        
        try:
            with self.driver.session() as session:
                # 基本連接測試
                session.run("RETURN 1")
                
                # 獲取數據庫統計
                stats = self.get_database_stats()
                
                # 檢查關鍵節點是否存在
                movie_count = stats.get("nodes", {}).get("Movie", 0)
                user_count = stats.get("nodes", {}).get("User", 0)
                
                health_status = {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "statistics": stats,
                    "checks": {
                        "connection": "✅ Healthy",
                        "movies_loaded": f"✅ {movie_count} movies" if movie_count > 0 else "❌ No movie data",
                        "users_loaded": f"✅ {user_count} users" if user_count > 0 else "❌ No user data"
                    }
                }
                
                # 健康評分
                health_score = 0
                if movie_count > 0:
                    health_score += 40
                if user_count > 0:
                    health_score += 30
                if stats.get("relationships", {}).get("RATED", 0) > 0:
                    health_score += 20
                if stats.get("relationships", {}).get("SIMILAR_TO", 0) > 0:
                    health_score += 10
                
                health_status["health_score"] = health_score
                
                if health_score < 50:
                    health_status["status"] = "warning"
                elif health_score < 30:
                    health_status["status"] = "critical"
                
                return health_status
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Health check failed: {e}",
                "timestamp": datetime.now().isoformat()
            }
    
    def get_database_structure(self) -> Dict[str, Any]:
        """獲取數據庫結構信息"""
        if not self.driver:
            return {}
        
        try:
            with self.driver.session() as session:
                # 獲取所有節點標籤
                labels = session.run("CALL db.labels()").data()
                
                # 獲取所有關係類型
                rel_types = session.run("CALL db.relationshipTypes()").data()
                
                # 獲取約束
                constraints = session.run("SHOW CONSTRAINTS").data()
                
                # 獲取索引
                indexes = session.run("SHOW INDEXES").data()
                
                result = {
                    "labels": [label.get("label") for label in labels],
                    "relationship_types": [rel.get("relationshipType") for rel in rel_types],
                    "constraints": constraints,
                    "indexes": indexes
                }
                # Ensure JSON-serializable
                return _json_safe(result)
                
        except Exception as e:
            logger.error(f"獲取數據庫結構失敗: {e}")
            return {}
    
    def sync_incremental(self, since: datetime = None) -> Dict[str, Any]:
        """執行增量同步"""
        if not self.driver:
            return {"success": False, "message": "Neo4j not connected"}
        
        if since is None:
            since = datetime.utcnow() - timedelta(hours=1)
        
        db = next(get_db())
        sync_results = {}
        
        try:
            # 同步新評分
            new_ratings = db.query(Rating).filter(Rating.created_at >= since).all()
            if new_ratings:
                with self.driver.session() as session:
                    for rating in new_ratings:
                        session.run("""
                            MERGE (u:User {user_id: $user_id})
                            MERGE (m:Movie {movie_id: $movie_id})
                            MERGE (u)-[r:RATED]->(m)
                            SET r.rating = $rating, r.timestamp = $timestamp
                        """, 
                        user_id=rating.user_id,
                        movie_id=rating.movie_id,
                        rating=rating.rating,
                        timestamp=rating.created_at.isoformat() if rating.created_at else None
                        )
            sync_results["ratings"] = len(new_ratings)
            
            # 同步新觀看記錄
            new_views = db.query(ViewHistory).filter(ViewHistory.viewed_at >= since).all()
            if new_views:
                with self.driver.session() as session:
                    for view in new_views:
                        session.run("""
                            MERGE (u:User {user_id: $user_id})
                            MERGE (m:Movie {movie_id: $movie_id})
                            MERGE (u)-[r:VIEWED]->(m)
                            SET r.timestamp = $timestamp, r.duration = $duration
                        """, 
                        user_id=view.user_id,
                        movie_id=view.movie_id,
                        timestamp=view.viewed_at.isoformat() if view.viewed_at else None,
                        duration=view.view_duration
                        )
            sync_results["views"] = len(new_views)
            
            # 同步新收藏
            new_favorites = db.query(Favorite).filter(Favorite.created_at >= since).all()
            if new_favorites:
                with self.driver.session() as session:
                    for favorite in new_favorites:
                        session.run("""
                            MERGE (u:User {user_id: $user_id})
                            MERGE (m:Movie {movie_id: $movie_id})
                            MERGE (u)-[r:FAVORITED]->(m)
                            SET r.timestamp = $timestamp
                        """, 
                        user_id=favorite.user_id,
                        movie_id=favorite.movie_id,
                        timestamp=favorite.created_at.isoformat() if favorite.created_at else None
                        )
            sync_results["favorites"] = len(new_favorites)
            
            # 更新電影統計
            updated_movies = db.query(Movie).filter(Movie.updated_at >= since).all()
            if updated_movies:
                with self.driver.session() as session:
                    for movie in updated_movies:
                        session.run("""
                            MATCH (m:Movie {movie_id: $movie_id})
                            SET m.average_rating = $average_rating,
                                m.rating_count = $rating_count,
                                m.view_count = $view_count,
                                m.like_count = $like_count,
                                m.favorite_count = $favorite_count,
                                m.comment_count = $comment_count
                        """, 
                        movie_id=movie.id,
                        average_rating=movie.average_rating,
                        rating_count=movie.rating_count,
                        view_count=movie.view_count,
                        like_count=movie.like_count,
                        favorite_count=movie.favorite_count,
                        comment_count=movie.comment_count
                        )
            sync_results["updated_movies"] = len(updated_movies)
            
            self.last_sync_time = datetime.now()
            
            return {
                "success": True,
                "message": "Incremental sync completed",
                "timestamp": self.last_sync_time.isoformat(),
                "results": sync_results
            }
            
        except Exception as e:
            logger.error(f"增量同步失敗: {e}")
            return {"success": False, "message": f"Incremental sync failed: {e}"}
        finally:
            db.close()
    
    def sync_full(self, clear_first: bool = False) -> Dict[str, Any]:
        """執行全量同步"""
        if not self.driver:
            return {"success": False, "message": "Neo4j not connected"}
        
        try:
            # 清空數據庫（如果需要）
            if clear_first:
                with self.driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
                logger.info("已清空 Neo4j 數據庫")
            
            # 創建約束和索引
            self._create_constraints_and_indexes()
            
            db = next(get_db())
            sync_results = {}
            
            # 同步類型
            genres = db.query(Genre).all()
            with self.driver.session() as session:
                for genre in genres:
                    session.run("MERGE (g:Genre {name: $name}) SET g.genre_id = $genre_id", 
                              genre_id=genre.id, name=genre.name)
            sync_results["genres"] = len(genres)
            
            # 同步電影
            movies = db.query(Movie).all()
            with self.driver.session() as session:
                for movie in movies:
                    # 創建電影節點
                    session.run("""
                        MERGE (m:Movie {movie_id: $movie_id})
                        SET m.title = $title, m.year = $year, m.director = $director,
                            m.cast = $cast, m.average_rating = $average_rating,
                            m.rating_count = $rating_count, m.view_count = $view_count
                    """, 
                    movie_id=movie.id, title=movie.title, year=movie.year,
                    director=movie.director, cast=movie.cast,
                    average_rating=movie.average_rating, rating_count=movie.rating_count,
                    view_count=movie.view_count
                    )
                    
                    # 創建導演關係
                    if movie.director:
                        session.run("""
                            MERGE (d:Person {name: $director_name})
                            SET d.type = 'Director'
                            WITH d
                            MATCH (m:Movie {movie_id: $movie_id})
                            MERGE (m)-[:DIRECTED_BY]->(d)
                        """, director_name=movie.director, movie_id=movie.id)
                    
                    # 創建類型關係
                    for genre in movie.genres:
                        session.run("""
                            MERGE (g:Genre {name: $genre_name})
                            MERGE (m:Movie {movie_id: $movie_id})
                            MERGE (m)-[:HAS_GENRE]->(g)
                        """, genre_name=genre.name, movie_id=movie.id)
                    
                    # 創建演員關係
                    if movie.cast:
                        actors = [actor.strip() for actor in movie.cast.split(',')[:5]]
                        for actor in actors:
                            if actor:
                                session.run("""
                                    MERGE (a:Person {name: $actor_name})
                                    SET a.type = 'Actor'
                                    WITH a
                                    MATCH (m:Movie {movie_id: $movie_id})
                                    MERGE (m)-[:STARRED_BY]->(a)
                                """, actor_name=actor, movie_id=movie.id)
            
            sync_results["movies"] = len(movies)
            
            # 同步用戶
            users = db.query(User).all()
            with self.driver.session() as session:
                for user in users:
                    session.run("""
                        MERGE (u:User {user_id: $user_id})
                        SET u.username = $username, u.email = $email
                    """, 
                    user_id=user.id, username=user.username, email=user.email
                    )
            sync_results["users"] = len(users)
            
            # 同步評分
            ratings = db.query(Rating).all()
            with self.driver.session() as session:
                for rating in ratings:
                    session.run("""
                        MATCH (u:User {user_id: $user_id})
                        MATCH (m:Movie {movie_id: $movie_id})
                        MERGE (u)-[r:RATED]->(m)
                        SET r.rating = $rating, r.timestamp = $timestamp
                    """, 
                    user_id=rating.user_id, movie_id=rating.movie_id,
                    rating=rating.rating, timestamp=rating.created_at.isoformat() if rating.created_at else None
                    )
            sync_results["ratings"] = len(ratings)
            
            # 創建相似電影關係
            self._create_similarity_relationships(db)
            
            self.last_sync_time = datetime.now()
            
            return {
                "success": True,
                "message": "Full sync completed",
                "timestamp": self.last_sync_time.isoformat(),
                "results": sync_results
            }
            
        except Exception as e:
            logger.error(f"全量同步失敗: {e}")
            return {"success": False, "message": f"Full sync failed: {e}"}
        finally:
            db.close()
    
    def _create_constraints_and_indexes(self):
        """創建約束和索引"""
        constraints_and_indexes = [
            "CREATE CONSTRAINT movie_id_unique IF NOT EXISTS FOR (m:Movie) REQUIRE m.movie_id IS UNIQUE",
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
            "CREATE CONSTRAINT genre_name_unique IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE",
            "CREATE INDEX movie_title_index IF NOT EXISTS FOR (m:Movie) ON (m.title)",
            "CREATE INDEX movie_year_index IF NOT EXISTS FOR (m:Movie) ON (m.year)",
            "CREATE INDEX person_name_index IF NOT EXISTS FOR (p:Person) ON (p.name)"
        ]
        
        with self.driver.session() as session:
            for query in constraints_and_indexes:
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning(f"約束/索引創建警告: {e}")
    
    def _create_similarity_relationships(self, db: Session):
        """創建電影相似性關係"""
        try:
            movies = db.query(Movie).all()
            
            with self.driver.session() as session:
                for i, movie1 in enumerate(movies):
                    if i % 100 == 0:
                        logger.info(f"處理相似性關係 {i}/{len(movies)}")
                    
                    # 獲取評分此電影的用戶
                    users_rated_movie1 = db.query(Rating.user_id).filter(
                        Rating.movie_id == movie1.id
                    ).distinct().all()
                    user_ids_1 = [u[0] for u in users_rated_movie1]
                    
                    if len(user_ids_1) < 5:
                        continue
                    
                    # 找到有共同評分用戶的電影
                    from sqlalchemy import func
                    similar_movies = db.query(Rating.movie_id).filter(
                        Rating.user_id.in_(user_ids_1),
                        Rating.movie_id != movie1.id
                    ).group_by(Rating.movie_id).having(
                        func.count(Rating.user_id) >= 3
                    ).all()
                    
                    # 計算相似性並創建關係
                    for movie2_id in similar_movies[:10]:
                        movie2_id = movie2_id[0]
                        
                        users_rated_movie2 = db.query(Rating.user_id).filter(
                            Rating.movie_id == movie2_id
                        ).distinct().all()
                        user_ids_2 = [u[0] for u in users_rated_movie2]
                        
                        intersection = len(set(user_ids_1) & set(user_ids_2))
                        union = len(set(user_ids_1) | set(user_ids_2))
                        similarity = intersection / union if union > 0 else 0
                        
                        if similarity > 0.1:
                            session.run("""
                                MATCH (m1:Movie {movie_id: $movie1_id})
                                MATCH (m2:Movie {movie_id: $movie2_id})
                                MERGE (m1)-[r:SIMILAR_TO]->(m2)
                                SET r.similarity = $similarity
                            """, movie1_id=movie1.id, movie2_id=movie2_id, similarity=similarity)
            
            logger.info("相似性關係創建完成")
            
        except Exception as e:
            logger.error(f"創建相似性關係失敗: {e}")
    
    def get_sync_status(self) -> Dict[str, Any]:
        """獲取同步狀態"""
        return {
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "neo4j_connected": self.driver is not None,
            "neo4j_uri": self.neo4j_uri
        }
    
    def optimize_database(self) -> Dict[str, Any]:
        """優化數據庫性能"""
        if not self.driver:
            return {"success": False, "message": "Neo4j not connected"}
        
        try:
            with self.driver.session() as session:
                # 創建額外的性能索引
                optimization_queries = [
                    "CREATE INDEX movie_rating_index IF NOT EXISTS FOR (m:Movie) ON (m.average_rating)",
                    "CREATE INDEX movie_view_count_index IF NOT EXISTS FOR (m:Movie) ON (m.view_count)",
                    "CREATE INDEX rating_timestamp_index IF NOT EXISTS FOR ()-[r:RATED]-() ON (r.timestamp)",
                    "CREATE INDEX view_timestamp_index IF NOT EXISTS FOR ()-[r:VIEWED]-() ON (r.timestamp)"
                ]
                
                for query in optimization_queries:
                    try:
                        session.run(query)
                    except Exception as e:
                        logger.warning(f"優化查詢警告: {e}")
                
                return {
                    "success": True,
                    "message": "Database optimization completed",
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"數據庫優化失敗: {e}")
            return {"success": False, "message": f"Database optimization failed: {e}"}
    
    # ==================== 整合的同步方法 ====================
    
    def batch_execute(self, query: str, data: List[Dict], batch_size: int = 2000, param_name: str = "data") -> Dict[str, Any]:
        """批量執行 Cypher 查詢"""
        if not self.driver:
            return {"success": False, "message": "Neo4j not connected"}
        
        start_time = time.time()
        processed = 0
        failed = 0
        errors = []
        
        try:
            with self.driver.session() as session:
                for i in range(0, len(data), batch_size):
                    batch = data[i:i + batch_size]
                    
                    try:
                        session.run(query, **{param_name: batch})
                        processed += len(batch)
                    except Exception as e:
                        failed += len(batch)
                        error_msg = f"Batch {i//batch_size + 1} failed: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        
        except Exception as e:
            failed = len(data) - processed
            errors.append(f"Batch execution failed: {e}")
            logger.error(f"批量執行失敗: {e}")
        
        duration = time.time() - start_time
        throughput = processed / duration if duration > 0 else 0
        
        return {
            "success": failed == 0,
            "processed": processed,
            "failed": failed,
            "duration": duration,
            "throughput": throughput,
            "errors": errors
        }
    
    def sync_genres(self, db: Session) -> Dict[str, Any]:
        """同步類型數據"""
        start_time = time.time()
        
        try:
            genres = db.query(Genre).all()
            genre_data = [{'genre_id': g.id, 'name': g.name} for g in genres]
            
            query = """
                UNWIND $genres AS genre
                MERGE (g:Genre {name: genre.name})
                SET g.genre_id = genre.genre_id
            """
            
            result = self.batch_execute(query, genre_data, param_name="genres")
            result["data_type"] = "genres"
            result["duration"] = time.time() - start_time
            
            logger.info(f"✅ 類型同步完成: {len(genres)} 個")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ 類型同步失敗: {e}")
            return {"success": False, "processed": 0, "failed": 0, "duration": duration, "errors": [str(e)]}
    
    def sync_users(self, db: Session) -> Dict[str, Any]:
        """同步用戶數據"""
        start_time = time.time()
        
        try:
            users = db.query(User).all()
            user_data = []
            
            for user in users:
                user_data.append({
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'age': user.age,
                    'gender': user.gender,
                    'occupation': user.occupation,
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'updated_at': user.updated_at.isoformat() if user.updated_at else None
                })
            
            query = """
                UNWIND $users AS user
                MERGE (u:User {user_id: user.user_id})
                SET u.username = user.username,
                    u.email = user.email,
                    u.age = user.age,
                    u.gender = user.gender,
                    u.occupation = user.occupation,
                    u.created_at = user.created_at,
                    u.updated_at = user.updated_at
            """
            
            result = self.batch_execute(query, user_data, param_name="users")
            result["data_type"] = "users"
            result["duration"] = time.time() - start_time
            
            logger.info(f"✅ 用戶同步完成: {len(users)} 個")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ 用戶同步失敗: {e}")
            return {"success": False, "processed": 0, "failed": 0, "duration": duration, "errors": [str(e)]}
    
    def sync_movies_enhanced(self, db: Session) -> Dict[str, Any]:
        """增強版電影同步 - 整合所有電影相關數據"""
        start_time = time.time()
        processed = 0
        failed = 0
        errors = []
        
        try:
            # 獲取總數
            total_movies = db.query(Movie).count()
            
            with tqdm(total=total_movies, desc="同步電影", unit="部") as pbar:
                for offset in range(0, total_movies, 2000):  # 使用較大的批次
                    movies = db.query(Movie).offset(offset).limit(2000).all()
                    if not movies:
                        break
                    
                    # 準備電影數據
                    movie_data = []
                    for movie in movies:
                        movie_data.append({
                            'movie_id': movie.id,
                            'title': movie.title,
                            'year': movie.year,
                            'imdb_id': movie.imdb_id,
                            'poster_url': movie.poster_url,
                            'description': movie.description,
                            'director': movie.director,
                            'cast': movie.cast,
                            'runtime': movie.runtime,
                            'language': movie.language,
                            'country': movie.country,
                            'average_rating': movie.average_rating,
                            'rating_count': movie.rating_count,
                            'view_count': movie.view_count,
                            'like_count': movie.like_count,
                            'favorite_count': movie.favorite_count,
                            'comment_count': movie.comment_count,
                            'created_at': movie.created_at.isoformat() if movie.created_at else None,
                            'updated_at': movie.updated_at.isoformat() if movie.updated_at else None
                        })
                    
                    # 批量插入電影
                    movie_query = """
                        UNWIND $movies AS movie
                        MERGE (m:Movie {movie_id: movie.movie_id})
                        SET m.title = movie.title,
                            m.year = movie.year,
                            m.imdb_id = movie.imdb_id,
                            m.poster_url = movie.poster_url,
                            m.description = movie.description,
                            m.director = movie.director,
                            m.cast = movie.cast,
                            m.runtime = movie.runtime,
                            m.language = movie.language,
                            m.country = movie.country,
                            m.average_rating = movie.average_rating,
                            m.rating_count = movie.rating_count,
                            m.view_count = movie.view_count,
                            m.like_count = movie.like_count,
                            m.favorite_count = movie.favorite_count,
                            m.comment_count = movie.comment_count,
                            m.created_at = movie.created_at,
                            m.updated_at = movie.updated_at
                    """
                    
                    try:
                        with self.driver.session() as session:
                            session.run(movie_query, movies=movie_data)
                        
                        # 創建導演關係
                        self._create_director_relationships(movies)
                        
                        # 創建演員關係
                        self._create_actor_relationships(movies)
                        
                        processed += len(movie_data)
                        pbar.update(len(movies))
                        pbar.set_postfix({
                            '已處理': processed,
                            '失敗': failed
                        })
                        
                    except Exception as e:
                        failed += len(movies)
                        error_msg = f"電影批次同步失敗: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        pbar.update(len(movies))
            
            # 創建類型關係
            self._create_genre_relationships(db)
            
            duration = time.time() - start_time
            throughput = processed / duration if duration > 0 else 0
            
            logger.info(f"✅ 電影同步完成: {processed} 部, 失敗 {failed} 部")
            return {
                "success": failed == 0,
                "processed": processed,
                "failed": failed,
                "duration": duration,
                "throughput": throughput,
                "errors": errors
            }
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ 電影同步失敗: {e}")
            return {"success": False, "processed": processed, "failed": failed, "duration": duration, "errors": [str(e)]}
    
    def _create_director_relationships(self, movies: List[Movie]):
        """創建導演關係"""
        try:
            director_data = []
            for movie in movies:
                if movie.director:
                    director_data.append({
                        'movie_id': movie.id,
                        'director_name': movie.director
                    })
            
            if director_data:
                query = """
                    UNWIND $directors AS dir
                    MERGE (d:Person {name: dir.director_name})
                    SET d.type = 'Director'
                    WITH d, dir
                    MATCH (m:Movie {movie_id: dir.movie_id})
                    MERGE (m)-[:DIRECTED_BY]->(d)
                """
                
                with self.driver.session() as session:
                    session.run(query, directors=director_data)
                    
        except Exception as e:
            logger.error(f"創建導演關係失敗: {e}")
    
    def _create_actor_relationships(self, movies: List[Movie]):
        """創建演員關係"""
        try:
            actor_data = []
            for movie in movies:
                if movie.cast:
                    actors = [actor.strip() for actor in movie.cast.split(',')[:10]]  # 限制演員數量
                    for actor in actors:
                        if actor:
                            actor_data.append({
                                'movie_id': movie.id,
                                'actor_name': actor
                            })
            
            if actor_data:
                query = """
                    UNWIND $actors AS actor
                    MERGE (a:Person {name: actor.actor_name})
                    SET a.type = 'Actor'
                    WITH a, actor
                    MATCH (m:Movie {movie_id: actor.movie_id})
                    MERGE (m)-[:STARRED_BY]->(a)
                """
                
                with self.driver.session() as session:
                    session.run(query, actors=actor_data)
                    
        except Exception as e:
            logger.error(f"創建演員關係失敗: {e}")
    
    def _create_genre_relationships(self, db: Session):
        """創建類型關係"""
        try:
            movie_genres = db.query(Movie.id, Genre.name).join(Movie.genres).all()
            
            if movie_genres:
                genre_data = [{'movie_id': movie_id, 'genre_name': genre_name} 
                             for movie_id, genre_name in movie_genres]
                
                query = """
                    UNWIND $genres AS genre
                    MATCH (g:Genre {name: genre.genre_name})
                    WITH g, genre
                    MATCH (m:Movie {movie_id: genre.movie_id})
                    MERGE (m)-[:HAS_GENRE]->(g)
                """
                
                with self.driver.session() as session:
                    session.run(query, genres=genre_data)
                
                logger.info(f"✅ 已創建 {len(genre_data)} 個類型關係")
                
        except Exception as e:
            logger.error(f"創建類型關係失敗: {e}")

def main():
    """主函數 - 提供命令行接口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Neo4j 數據庫管理工具')
    parser.add_argument('--action', choices=['health', 'stats', 'structure', 'sync-incremental', 'sync-full', 'optimize'], 
                       required=True, help='執行的操作')
    parser.add_argument('--clear', action='store_true', help='全量同步前清空數據庫')
    parser.add_argument('--since', type=str, help='增量同步的起始時間 (ISO格式)')
    
    args = parser.parse_args()
    
    manager = Neo4jManager()
    
    if not manager.connect():
        print("❌ 無法連接到 Neo4j")
        return
    
    try:
        if args.action == 'health':
            result = manager.check_database_health()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        elif args.action == 'stats':
            result = manager.get_database_stats()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        elif args.action == 'structure':
            result = manager.get_database_structure()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        elif args.action == 'sync-incremental':
            since = None
            if args.since:
                since = datetime.fromisoformat(args.since)
            result = manager.sync_incremental(since)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        elif args.action == 'sync-full':
            result = manager.sync_full(clear_first=args.clear)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        elif args.action == 'optimize':
            result = manager.optimize_database()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
    finally:
        manager.close()

if __name__ == "__main__":
    main()
