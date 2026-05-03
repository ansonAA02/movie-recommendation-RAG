"""
Unified statistics updater.
On any interaction (rating/favorite/like/view/comment), call the relevant
method or the generic update_related_statistics(db, user_id, movie_id).

It recomputes Movie aggregates (like_count, favorite_count, comment_count,
rating_count, average_rating, view_count) and basic UserProfile totals. Best-effort,
never throws to callers.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from models import Movie, Rating, Favorite, Like, Comment, ViewHistory, UserProfile


class _StatisticsUpdater:
    def _top_weighted_keys(self, scores: dict[str, float], limit: int) -> list[str]:
        ranked = [
            (key, score)
            for key, score in scores.items()
            if str(key).strip() and float(score) > 0.0
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return [key for key, _ in ranked[:limit]]

    def _normalized_distribution(
        self,
        scores: dict[str, float],
        limit: int | None = None,
        min_score: float = 0.0,
    ) -> dict[str, float]:
        ranked = [
            (str(key).strip(), float(score))
            for key, score in scores.items()
            if str(key).strip() and float(score) > min_score
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        if limit is not None:
            ranked = ranked[:limit]
        total = sum(score for _, score in ranked)
        if total <= 0.0:
            return {}
        return {key: round(score / total, 4) for key, score in ranked}

    def _recent_activity_score(
        self,
        ratings: list[Rating],
        favorites: list[Favorite],
        likes: list[Like],
        comments: list[Comment],
        views: list[ViewHistory],
    ) -> float:
        now = datetime.now(timezone.utc)
        horizon = now - timedelta(days=30)
        weighted = 0.0
        for collection, base_weight, attr in [
            (ratings, 2.0, "created_at"),
            (favorites, 2.5, "created_at"),
            (likes, 1.5, "created_at"),
            (comments, 1.7, "created_at"),
            (views, 1.0, "viewed_at"),
        ]:
            for item in collection:
                ts = getattr(item, attr, None)
                if ts is None:
                    continue
                if getattr(ts, "tzinfo", None) is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < horizon:
                    continue
                age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
                weighted += base_weight * math.exp(-age_days / 14.0)
        # Saturate to 0-1 so the score remains stable for UI usage.
        return round(weighted / (weighted + 8.0), 4) if weighted > 0 else 0.0

    def _preference_drift_score(
        self,
        long_term_scores: dict[str, float],
        recent_scores: dict[str, float],
    ) -> float:
        long_dist = self._normalized_distribution(long_term_scores, limit=12)
        recent_dist = self._normalized_distribution(recent_scores, limit=12)
        if not long_dist or not recent_dist:
            return 0.0
        keys = set(long_dist) | set(recent_dist)
        l1 = sum(abs(long_dist.get(k, 0.0) - recent_dist.get(k, 0.0)) for k in keys)
        return round(min(1.0, l1 / 2.0), 4)

    def _recompute_movie_aggregates(self, db: Session, movie_id: int) -> None:
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            return
        like_count = db.query(func.count(Like.id)).filter(Like.movie_id == movie_id).scalar() or 0
        favorite_count = db.query(func.count(Favorite.id)).filter(Favorite.movie_id == movie_id).scalar() or 0
        comment_count = db.query(func.count(Comment.id)).filter(Comment.movie_id == movie_id).scalar() or 0
        view_count = db.query(func.count(ViewHistory.id)).filter(ViewHistory.movie_id == movie_id).scalar() or 0
        rating_stats = (
            db.query(func.count(Rating.id), func.avg(Rating.rating))
            .filter(Rating.movie_id == movie_id)
            .first()
        )
        rating_count = int(rating_stats[0] or 0)
        average_rating = float(rating_stats[1] or 0.0)

        movie.like_count = like_count
        movie.favorite_count = favorite_count
        movie.comment_count = comment_count
        movie.view_count = view_count
        movie.rating_count = rating_count
        movie.average_rating = average_rating

    def _recompute_user_profile(self, db: Session, user_id: Optional[int]) -> None:
        if not user_id:
            return
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            profile = UserProfile(
                user_id=user_id,
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
                total_likes=0,
                total_favorites=0,
                total_views=0,
                total_comments=0,
                average_rating_given=0.0,
            )
            db.add(profile)
            db.flush()
        total_likes = db.query(func.count(Like.id)).filter(Like.user_id == user_id).scalar() or 0
        total_favorites = db.query(func.count(Favorite.id)).filter(Favorite.user_id == user_id).scalar() or 0
        total_comments = db.query(func.count(Comment.id)).filter(Comment.user_id == user_id).scalar() or 0
        total_ratings = db.query(func.count(Rating.id)).filter(Rating.user_id == user_id).scalar() or 0
        total_views = db.query(func.count(ViewHistory.id)).filter(ViewHistory.user_id == user_id).scalar() or 0
        avg_given = db.query(func.avg(Rating.rating)).filter(Rating.user_id == user_id).scalar() or 0.0

        profile.total_likes = int(total_likes)
        profile.total_favorites = int(total_favorites)
        profile.total_comments = int(total_comments)
        profile.total_ratings = int(total_ratings)
        profile.total_views = int(total_views)
        profile.average_rating_given = float(avg_given or 0.0)

        ratings = db.query(Rating).filter(Rating.user_id == user_id).all()
        favorites = db.query(Favorite).filter(Favorite.user_id == user_id).all()
        likes = db.query(Like).filter(Like.user_id == user_id).all()
        comments = db.query(Comment).filter(Comment.user_id == user_id).all()
        views = (
            db.query(ViewHistory)
            .filter(ViewHistory.user_id == user_id)
            .order_by(ViewHistory.viewed_at.desc())
            .limit(400)
            .all()
        )

        movie_weights: dict[int, float] = defaultdict(float)
        for r in ratings:
            movie_weights[int(r.movie_id)] += 1.5 + max(0.0, float(r.rating) - 3.0) * 1.25
        for f in favorites:
            movie_weights[int(f.movie_id)] += 3.0
        for l in likes:
            movie_weights[int(l.movie_id)] += 2.0
        for c in comments:
            movie_weights[int(c.movie_id)] += 1.5 + (0.5 if getattr(c, "rating", None) else 0.0)
        for rank, v in enumerate(views):
            decay = 1.0 / (1.0 + 0.08 * rank)
            type_weight = 1.0 if (getattr(v, "view_type", "detail") or "detail").lower() == "detail" else 0.35
            movie_weights[int(v.movie_id)] += 0.7 * decay * type_weight

        if not movie_weights:
            profile.preferred_genres = json.dumps([], ensure_ascii=False)
            profile.preferred_directors = json.dumps([], ensure_ascii=False)
            profile.preferred_actors = json.dumps([], ensure_ascii=False)
            profile.preferred_languages = json.dumps([], ensure_ascii=False)
            profile.preferred_countries = json.dumps([], ensure_ascii=False)
            profile.genre_distribution_json = json.dumps({}, ensure_ascii=False)
            profile.director_distribution_json = json.dumps({}, ensure_ascii=False)
            profile.actor_distribution_json = json.dumps({}, ensure_ascii=False)
            profile.recent_activity_score = self._recent_activity_score(ratings, favorites, likes, comments, views)
            profile.preference_drift_score = 0.0
            profile.most_rated_year = None
            return

        movies = (
            db.query(Movie)
            .options(joinedload(Movie.genres))
            .filter(Movie.id.in_(list(movie_weights.keys())))
            .all()
        )
        by_id = {m.id: m for m in movies}

        genre_scores: dict[str, float] = defaultdict(float)
        director_scores: dict[str, float] = defaultdict(float)
        actor_scores: dict[str, float] = defaultdict(float)
        language_scores: dict[str, float] = defaultdict(float)
        country_scores: dict[str, float] = defaultdict(float)
        year_scores: dict[int, float] = defaultdict(float)
        recent_genre_scores: dict[str, float] = defaultdict(float)
        positive_runtimes: list[int] = []

        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=45)
        recent_movie_weights: dict[int, float] = defaultdict(float)
        for rank, view in enumerate(views[:120]):
            viewed_at = getattr(view, "viewed_at", None)
            if viewed_at is None:
                continue
            if getattr(viewed_at, "tzinfo", None) is None:
                viewed_at = viewed_at.replace(tzinfo=timezone.utc)
            if viewed_at < recent_cutoff:
                continue
            recent_movie_weights[int(view.movie_id)] += 1.0 / (1.0 + 0.04 * rank)
        for rating in ratings:
            created_at = getattr(rating, "created_at", None)
            if created_at is None:
                continue
            if getattr(created_at, "tzinfo", None) is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at < recent_cutoff:
                continue
            recent_movie_weights[int(rating.movie_id)] += 1.2 + max(0.0, float(rating.rating) - 3.0)

        for mid, weight in movie_weights.items():
            movie = by_id.get(mid)
            if not movie:
                continue
            for genre in (movie.genres or []):
                if getattr(genre, "name", None):
                    genre_scores[str(genre.name)] += weight
                    if recent_movie_weights.get(mid):
                        recent_genre_scores[str(genre.name)] += recent_movie_weights[mid]
            if getattr(movie, "director", None):
                director_scores[str(movie.director)] += weight
            if getattr(movie, "cast", None):
                for actor in [a.strip() for a in str(movie.cast).split(",") if a.strip()][:8]:
                    actor_scores[actor] += weight
            if getattr(movie, "language", None):
                language_scores[str(movie.language)] += weight
            if getattr(movie, "country", None):
                country_scores[str(movie.country)] += weight
            if getattr(movie, "year", None):
                year_scores[int(movie.year)] += weight
            if getattr(movie, "runtime", None) and weight >= 1.5:
                positive_runtimes.append(int(movie.runtime))

        profile.preferred_genres = json.dumps(self._top_weighted_keys(genre_scores, 6), ensure_ascii=False)
        profile.preferred_directors = json.dumps(self._top_weighted_keys(director_scores, 5), ensure_ascii=False)
        profile.preferred_actors = json.dumps(self._top_weighted_keys(actor_scores, 8), ensure_ascii=False)
        profile.preferred_languages = json.dumps(self._top_weighted_keys(language_scores, 4), ensure_ascii=False)
        profile.preferred_countries = json.dumps(self._top_weighted_keys(country_scores, 4), ensure_ascii=False)
        profile.genre_distribution_json = json.dumps(
            self._normalized_distribution(genre_scores, limit=10),
            ensure_ascii=False,
        )
        profile.director_distribution_json = json.dumps(
            self._normalized_distribution(director_scores, limit=8),
            ensure_ascii=False,
        )
        profile.actor_distribution_json = json.dumps(
            self._normalized_distribution(actor_scores, limit=12),
            ensure_ascii=False,
        )
        profile.recent_activity_score = self._recent_activity_score(ratings, favorites, likes, comments, views)
        profile.preference_drift_score = self._preference_drift_score(genre_scores, recent_genre_scores)

        if year_scores:
            profile.most_rated_year = max(year_scores.items(), key=lambda x: x[1])[0]

        positive_ratings = [float(r.rating) for r in ratings if float(r.rating) >= 4.0]
        if positive_ratings:
            profile.min_rating_threshold = max(3.0, min(5.0, sum(positive_ratings) / len(positive_ratings) - 0.25))
        else:
            profile.min_rating_threshold = max(3.0, float(avg_given or 0.0) - 0.1) if avg_given else 3.0

        if positive_runtimes:
            positive_runtimes.sort()
            idx = min(len(positive_runtimes) - 1, max(0, math.ceil(len(positive_runtimes) * 0.8) - 1))
            profile.max_runtime = int(positive_runtimes[idx])
            profile.min_runtime = int(min(positive_runtimes))

    # Generic one-shot updater
    def update_related_statistics(self, db: Session, user_id: int, movie_id: int) -> None:
        try:
            self._recompute_movie_aggregates(db, movie_id)
            self._recompute_user_profile(db, user_id)
            db.commit()
            
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # Backward-compatible wrappers used by existing endpoints
    def update_movie_statistics(self, db: Session, movie_id: int) -> None:
        try:
            self._recompute_movie_aggregates(db, movie_id)
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    def update_user_statistics(self, db: Session, user_id: int) -> None:
        try:
            self._recompute_user_profile(db, user_id)
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # Convenience hooks (optional to use)
    def on_rating(self, db: Session, user_id: int, movie_id: int) -> None:
        self.update_related_statistics(db, user_id, movie_id)

    def on_favorite(self, db: Session, user_id: int, movie_id: int) -> None:
        self.update_related_statistics(db, user_id, movie_id)

    def on_unfavorite(self, db: Session, user_id: int, movie_id: int) -> None:
        self.update_related_statistics(db, user_id, movie_id)

    def on_like(self, db: Session, user_id: int, movie_id: int) -> None:
        self.update_related_statistics(db, user_id, movie_id)

    def on_unlike(self, db: Session, user_id: int, movie_id: int) -> None:
        self.update_related_statistics(db, user_id, movie_id)

    def on_view(self, db: Session, user_id: int, movie_id: int) -> None:
        self.update_related_statistics(db, user_id, movie_id)

    def on_comment_create(self, db: Session, user_id: int, movie_id: int) -> None:
        self.update_related_statistics(db, user_id, movie_id)

    def on_comment_delete(self, db: Session, user_id: int, movie_id: int) -> None:
        self.update_related_statistics(db, user_id, movie_id)

statistics_updater = _StatisticsUpdater()


