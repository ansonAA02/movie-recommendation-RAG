import React from 'react'

interface ViewHistoryItemProps {
  view: {
    id: number
    user_id: number
    movie_id: number
    viewed_at: string
    view_duration?: number
    view_type?: string
    movie_title: string
    movie_year?: number
    movie_poster_url?: string
    movie_average_rating?: number
    movie_genres?: string
    user_rating?: number
    is_favorite: boolean
    is_liked: boolean
    has_review: boolean
  }
  onMovieClick: (movieId: number) => void
}

export const ViewHistoryItem: React.FC<ViewHistoryItemProps> = ({
  view,
  onMovieClick
}) => {
  const formatDuration = (seconds?: number) => {
    if (!seconds) return 'Unknown'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = seconds % 60
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`
    } else {
      return `${secs}s`
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60))
    
    if (diffInHours < 1) return 'Just now'
    if (diffInHours < 24) return `${diffInHours}h ago`
    if (diffInHours < 168) return `${Math.floor(diffInHours / 24)}d ago`
    
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getViewTypeLabel = (viewType?: string) => {
    switch (viewType) {
      case 'full': return 'Full'
      case 'partial': return 'Partial'
      case 'trailer': return 'Trailer'
      case 'preview': return 'Preview'
      default: return 'View'
    }
  }

  return (
    <div 
      className="bg-gradient-to-br from-slate-800/50 to-slate-900/50 rounded-2xl shadow-lg border border-white/10 p-6 hover:shadow-2xl hover:scale-105 transition-all duration-300 cursor-pointer backdrop-blur-sm"
      onClick={() => onMovieClick(view.movie_id)}
    >
      <div className="flex space-x-4">
        {/* 電影海報 */}
        <div className="flex-shrink-0">
          {view.movie_poster_url ? (
            <img
              src={view.movie_poster_url}
              alt={view.movie_title}
              className="w-20 h-28 object-cover rounded-2xl shadow-lg"
            />
          ) : (
            <div className="w-20 h-28 bg-gradient-to-br from-slate-700 to-slate-800 rounded-2xl flex items-center justify-center border border-white/10">
              <span className="text-gray-400 text-sm">🎬</span>
            </div>
          )}
        </div>

        {/* 電影資訊 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between mb-2">
            <div>
              <h3 className="font-bold text-white text-lg truncate">
                {view.movie_title}
              </h3>
              {view.movie_year && (
                <p className="text-sm text-gray-400">{view.movie_year}</p>
              )}
            </div>
            <div className="flex items-center space-x-2">
              <span className="px-3 py-1 bg-gradient-to-r from-blue-500 to-purple-600 text-white text-xs rounded-full font-medium shadow-sm">
                {getViewTypeLabel(view.view_type)}
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-6 text-sm text-gray-300 mb-3">
            <span className="flex items-center space-x-1">
              <span>⏱️</span>
              <span>{formatDuration(view.view_duration)}</span>
            </span>
            <span className="flex items-center space-x-1">
              <span>🕒</span>
              <span>{formatDate(view.viewed_at)}</span>
            </span>
          </div>

          {/* 互動狀態 */}
          <div className="flex items-center space-x-3 mb-3">
            <div className="flex items-center space-x-2">
              {view.user_rating && (
                <span className="px-3 py-1 bg-gradient-to-r from-yellow-500/20 to-orange-500/20 text-yellow-400 text-xs rounded-full border border-yellow-500/30">
                  ⭐ Rated
                </span>
              )}
              {view.is_liked && (
                <span className="px-3 py-1 bg-gradient-to-r from-red-500/20 to-pink-500/20 text-red-400 text-xs rounded-full border border-red-500/30">
                  ❤️ Liked
                </span>
              )}
              {view.is_favorite && (
                <span className="px-3 py-1 bg-gradient-to-r from-pink-500/20 to-rose-500/20 text-pink-400 text-xs rounded-full border border-pink-500/30">
                  💖 Favorited
                </span>
              )}
              {view.has_review && (
                <span className="px-3 py-1 bg-gradient-to-r from-green-500/20 to-emerald-500/20 text-green-400 text-xs rounded-full border border-green-500/30">
                  💬 Commented
                </span>
              )}
            </div>
          </div>

          {/* 電影評分 */}
          {view.movie_average_rating && view.movie_average_rating > 0 && (
            <div className="flex items-center space-x-3 bg-white/10 rounded-xl p-3">
              <div className="flex items-center space-x-1">
                <span className="text-yellow-400 text-lg">⭐</span>
                <span className="text-lg font-bold text-white">
                  {view.movie_average_rating.toFixed(1)}
                </span>
              </div>
              <span className="text-sm text-gray-300">
                Average rating
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
