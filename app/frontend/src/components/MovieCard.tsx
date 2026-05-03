import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Calendar, Clock, Globe, Star, Users, X, Eye } from 'lucide-react'
import StarRating from './StarRating'
// import { useAuthStore } from '../stores/authStore' // 暫時不需要
import type { Movie } from '../services/api'

interface MovieCardProps {
  movie: Movie
  showRating?: boolean
  onRatingChange?: (movieId: number, rating: number) => void
  onRemoveFavorite?: () => void
}

const MovieCard: React.FC<MovieCardProps> = ({
  movie,
  showRating = true,
  onRatingChange,
  onRemoveFavorite
}) => {
  const navigate = useNavigate()
  // const { refreshUserProfile } = useAuthStore() // 暫時不需要

  // 處理電影卡片點擊
  const handleMovieClick = () => {
    navigate(`/movies/${movie.id}`)
  }
  // 格式化運行時長
  const formatRuntime = (minutes: number | null) => {
    if (!minutes) return 'Unknown'
    const hours = Math.floor(minutes / 60)
    const mins = minutes % 60
    return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
  }

  // 格式化評分顯示
  const formatRating = (rating: number) => {
    return rating > 0 ? rating.toFixed(1) : 'Unrated'
  }

  return (
    <div
      className="group relative rounded-2xl overflow-hidden cursor-pointer bg-gradient-to-br from-slate-900/60 to-slate-800/60 border border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.12)] hover:shadow-[0_12px_40px_rgb(0,0,0,0.25)] transition-all duration-300 backdrop-blur-xl"
      onClick={handleMovieClick}
    >
      {/* 電影海報 */}
      <div className="relative aspect-[2/3] bg-slate-800">
        {movie.poster_url ? (
          <img
            src={movie.poster_url}
            alt={movie.title}
            className="w-full h-full object-cover transform transition-transform duration-500 group-hover:scale-105"
            onError={(e) => {
              e.currentTarget.src = '/placeholder-movie.jpg'
            }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-slate-800 to-slate-700">
            <div className="text-center text-slate-300">
              <Star className="w-12 h-12 mx-auto mb-2 opacity-70" />
              <p className="text-sm">No poster</p>
            </div>
          </div>
        )}

        {/* 上方漸變遮罩 */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-slate-950/70 via-transparent to-transparent" />

        {/* 評分標籤 */}
        {movie.average_rating > 0 && (
          <div className="absolute top-3 right-3 px-2.5 py-1 rounded-full text-[11px] font-semibold flex items-center gap-1.5 bg-white/15 text-yellow-300 backdrop-blur-md border border-white/10 shadow">
            <Star className="w-3.5 h-3.5" />
            {formatRating(movie.average_rating)}
          </div>
        )}

        {/* 移除收藏按鈕 */}
        {onRemoveFavorite && (
          <button
            onClick={onRemoveFavorite}
            className="absolute top-3 left-3 bg-red-500/90 text-white p-1.5 rounded-full hover:bg-red-500 transition-colors shadow-md"
            title="Remove from favorites"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* 電影信息 */}
      <div className="p-4">
        {/* 標題和年份 */}
        <div className="mb-2.5">
          <h3 className="text-base font-semibold text-white line-clamp-2 mb-1 tracking-tight">
            {movie.title}
          </h3>
          {movie.year && (
            <div className="flex items-center text-xs text-white/70">
              <Calendar className="w-3.5 h-3.5 mr-1" />
              {movie.year}
            </div>
          )}
        </div>

        {/* 電影描述 */}
        {movie.description && (
          <p className="text-sm text-white/70 mb-3 line-clamp-3">
            {movie.description}
          </p>
        )}

        {/* 電影詳情（精簡為晶片樣式） */}
        <div className="flex flex-wrap gap-1.5 mb-4">
          {movie.runtime && (
            <span className="inline-flex items-center px-2 py-1 rounded-full text-[11px] bg-white/10 text-white/80 border border-white/10">
              <Clock className="w-3.5 h-3.5 mr-1" /> {formatRuntime(movie.runtime)}
            </span>
          )}
          {(movie.language || movie.country) && (
            <span className="inline-flex items-center px-2 py-1 rounded-full text-[11px] bg-white/10 text-white/80 border border-white/10">
              <Globe className="w-3.5 h-3.5 mr-1" />
              {[movie.language, movie.country].filter(Boolean).join(' • ')}
            </span>
          )}
          {movie.rating_count > 0 && (
            <span className="inline-flex items-center px-2 py-1 rounded-full text-[11px] bg-white/10 text-white/80 border border-white/10">
              <Users className="w-3.5 h-3.5 mr-1" /> {movie.rating_count} ratings
            </span>
          )}
          {movie.view_count > 0 && (
            <span className="inline-flex items-center px-2 py-1 rounded-full text-[11px] bg-white/10 text-white/80 border border-white/10">
              <Eye className="w-3.5 h-3.5 mr-1" /> {movie.view_count} views
            </span>
          )}
        </div>

        {/* 評分組件 */}
        {showRating && (
          <div
            className="border-t border-white/10 pt-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-white/90">Your rating</span>
              {movie.average_rating > 0 && (
                <span className="text-xs text-white/60">
                  Avg {formatRating(movie.average_rating)}
                </span>
              )}
            </div>
            <StarRating
              rating={0}
              movieId={movie.id}
              size="sm"
              showNumber={false}
              onRatingChange={async (rating) => {
                onRatingChange?.(movie.id, rating)
              }}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default MovieCard