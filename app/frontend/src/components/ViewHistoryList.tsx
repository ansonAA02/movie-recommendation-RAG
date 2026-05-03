import React, { useState, useEffect } from 'react'
import { viewHistoryApi } from '../services/api'
import { ViewHistoryItem } from './ViewHistoryItem'
import LoadingSpinner from './LoadingSpinner'
import { useAuthStore } from '../stores/authStore'

interface ViewHistoryListProps {
  onMovieClick: (movieId: number) => void
  days?: number
  viewType?: string
  pageSize?: number
}

export const ViewHistoryList: React.FC<ViewHistoryListProps> = ({
  onMovieClick,
  days = 30,
  viewType,
  pageSize = 20
}) => {
  const { user, isAuthenticated } = useAuthStore()
  const [views, setViews] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [totalViews, setTotalViews] = useState(0)
  const [stats, setStats] = useState<any>(null)

  const loadViewHistory = async (pageNum: number = 1, reset: boolean = false) => {
    console.log('loadViewHistory called:', { isAuthenticated, user, pageNum, reset })
    
    if (!isAuthenticated || !user) {
      console.log('User not authenticated, skipping view history load')
      setLoading(false)
      return
    }
    
    try {
      setLoading(true)
      console.log('Loading view history:', { pageNum, pageSize, days, viewType, userId: user.id })
      
      // 檢查認證令牌
      const token = localStorage.getItem('auth-storage')
      console.log('Auth token from localStorage:', token ? 'exists' : 'missing')
      
      const response = await viewHistoryApi.getUserViewHistory(pageNum, pageSize, days, viewType)
      console.log('View history response:', response)
      
      if (reset) {
        setViews(response.views || [])
      } else {
        setViews(prev => [...prev, ...(response.views || [])])
      }
      
      setTotalViews(response.total || 0)
      setHasMore(response.has_more || false)
    } catch (error: any) {
      console.error('Error loading view history:', error)
      console.error('Error details:', error.response?.data)
      console.error('Error status:', error.response?.status)
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const response = await viewHistoryApi.getViewHistoryStats(days)
      setStats(response)
    } catch (error) {
      console.error('Error loading stats:', error)
    }
  }

  useEffect(() => {
    loadViewHistory(1, true)
    loadStats()
  }, [days, viewType, pageSize])

  const handleLoadMore = () => {
    if (!loading && hasMore) {
      const nextPage = page + 1
      setPage(nextPage)
      loadViewHistory(nextPage, false)
    }
  }

  const handleClearHistory = async () => {
    if (!window.confirm('Are you sure you want to clear your viewing history? This action cannot be undone.')) {
      return
    }

    try {
      await viewHistoryApi.clearViewHistory(days)
      setViews([])
      setTotalViews(0)
      setHasMore(false)
      loadStats()
    } catch (error) {
      console.error('Error clearing history:', error)
    }
  }

  if (!isAuthenticated || !user) {
    return (
      <div className="text-center py-20">
        <div className="w-32 h-32 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-3xl flex items-center justify-center mx-auto mb-8">
          <span className="text-6xl">🔒</span>
        </div>
        <h3 className="text-2xl font-bold text-white mb-4">Please log in</h3>
        <p className="text-gray-300 text-lg mb-8">Log in to view your watch history</p>
        <div className="w-24 h-1 bg-gradient-to-r from-purple-500 to-pink-600 rounded-full mx-auto"></div>
      </div>
    )
  }

  if (loading && views.length === 0) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 統計資訊 */}
      {stats && (
        <div className="bg-gradient-to-br from-slate-800/50 to-slate-900/50 rounded-3xl shadow-2xl border border-white/10 p-8 backdrop-blur-xl">
          <div className="flex items-center space-x-3 mb-6">
            <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center">
              <span className="text-white text-xl">📊</span>
            </div>
            <div>
              <h3 className="text-2xl font-bold text-white">Watch stats</h3>
              <p className="text-gray-400">Your viewing analytics</p>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div className="text-center bg-gradient-to-br from-blue-500/20 to-cyan-500/20 rounded-2xl p-6 border border-blue-500/30">
              <div className="text-3xl font-bold text-blue-400 mb-2">{stats.total_views}</div>
              <div className="text-sm text-gray-300">Total views</div>
            </div>
            <div className="text-center bg-gradient-to-br from-green-500/20 to-emerald-500/20 rounded-2xl p-6 border border-green-500/30">
              <div className="text-3xl font-bold text-green-400 mb-2">{stats.unique_movies}</div>
              <div className="text-sm text-gray-300">Unique movies</div>
            </div>
            <div className="text-center bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-2xl p-6 border border-purple-500/30">
              <div className="text-3xl font-bold text-purple-400 mb-2">{stats.total_duration}</div>
              <div className="text-sm text-gray-300">Total watch time (hrs)</div>
            </div>
            <div className="text-center bg-gradient-to-br from-orange-500/20 to-red-500/20 rounded-2xl p-6 border border-orange-500/30">
              <div className="text-3xl font-bold text-orange-400 mb-2">{stats.avg_duration}</div>
              <div className="text-sm text-gray-300">Avg watch time (min)</div>
            </div>
          </div>
        </div>
      )}

      {/* 操作按鈕 */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center space-x-4">
          <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-pink-600 rounded-2xl flex items-center justify-center">
            <span className="text-white text-xl">📊</span>
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">
              Watch History ({totalViews})
            </h2>
            <p className="text-gray-400">Your viewing records</p>
          </div>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={handleClearHistory}
            className="px-6 py-3 bg-gradient-to-r from-red-500/20 to-pink-500/20 text-red-400 border border-red-500/30 rounded-xl hover:from-red-500/30 hover:to-pink-500/30 transition-all duration-200 font-medium"
          >
            🗑️ Clear history
          </button>
        </div>
      </div>

      {/* 瀏覽歷史列表 */}
      {views.length === 0 ? (
        <div className="text-center py-20">
          <div className="w-32 h-32 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-3xl flex items-center justify-center mx-auto mb-8">
            <span className="text-6xl">📺</span>
          </div>
          <h3 className="text-2xl font-bold text-white mb-4">No watch history yet</h3>
          <p className="text-gray-300 text-lg mb-8">Start watching movies to build your history.</p>
          <div className="w-24 h-1 bg-gradient-to-r from-purple-500 to-pink-600 rounded-full mx-auto"></div>
        </div>
      ) : (
        <>
          <div className="space-y-4">
            {views.map((view) => (
              <ViewHistoryItem
                key={view.id}
                view={view}
                onMovieClick={onMovieClick}
              />
            ))}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-8">
              <button
                onClick={handleLoadMore}
                disabled={loading}
                className="px-8 py-4 bg-gradient-to-r from-purple-500 to-pink-600 text-white rounded-2xl hover:from-purple-600 hover:to-pink-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 transform hover:scale-105 shadow-lg font-medium"
              >
                {loading ? (
                  <span className="flex items-center space-x-2">
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>Loading...</span>
                  </span>
                ) : (
                  <span className="flex items-center space-x-2">
                    <span>Load more</span>
                    <span>⬇️</span>
                  </span>
                )}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
