import React, { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { History, Grid, List, Search, Clock, Calendar } from 'lucide-react'
import { viewHistoryApi } from '../services/api'
import MovieCard from '../components/MovieCard'
import LoadingSpinner from '../components/LoadingSpinner'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

const ViewHistory: React.FC = () => {
  const { user, isAuthenticated } = useAuthStore()
  const [viewHistory, setViewHistory] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [days, setDays] = useState(30)
  const [viewType, setViewType] = useState<string>('')
  const [stats, setStats] = useState<any>(null)
  const [showSearchSuggestions, setShowSearchSuggestions] = useState(false)

  useEffect(() => {
    if (isAuthenticated && user) {
      loadViewHistory()
      loadStats()
    }
  }, [isAuthenticated, user, days, viewType])

  const loadViewHistory = async () => {
    console.log('loadViewHistory called:', { isAuthenticated, user, days, viewType })
    
    if (!isAuthenticated || !user) {
      console.log('User not authenticated, skipping view history load')
      return
    }
    
    try {
      setIsLoading(true)
      console.log('Loading UNIQUE movies with params:', { days, viewType })
      
      // 檢查認證令牌
      const token = localStorage.getItem('auth-storage')
      console.log('Auth token exists:', !!token)
      
      const response = await viewHistoryApi.getUserUniqueMovies(days, viewType)
      console.log('Unique movies response:', response)
      const movies = response.movies || []
      console.log('Movies length (raw):', movies.length)

      // 客戶端再做一次去重保險（依 movie_id）
      const seen = new Set<number>()
      const deduped = [] as any[]
      for (const m of movies) {
        const mid = (m.movie_id ?? m.id) as number
        if (mid == null) continue
        if (seen.has(mid)) continue
        seen.add(mid)
        deduped.push(m)
      }
      console.log('Movies length (deduped):', deduped.length)

      // unique-movies 已按最新瀏覽排序
      setViewHistory(deduped)
    } catch (error: any) {
      console.error('Error loading view history:', error)
      console.error('Error details:', error.response?.data)
      console.error('Error status:', error.response?.status)
      toast.error('Failed to load watch history')
    } finally {
      setIsLoading(false)
    }
  }

  const loadStats = async () => {
    if (!isAuthenticated || !user) return
    
    try {
      const response = await viewHistoryApi.getViewHistoryStats(days)
      setStats(response)
    } catch (error) {
      console.error('Error loading stats:', error)
    }
  }

  // const handleClearHistory = async () => {
  //   if (!window.confirm('確定要清除瀏覽歷史嗎？此操作無法復原。')) {
  //     return
  //   }

  //   try {
  //     await viewHistoryApi.clearViewHistory(days)
  //     setViewHistory([])
  //     loadStats()
  //     toast.success('瀏覽歷史已清除')
  //   } catch (error) {
  //     console.error('Error clearing history:', error)
  //     toast.error('清除瀏覽歷史失敗')
  //   }
  // }

  // 根據用戶ID和電影ID獲取瀏覽記錄，按時間排序（最近到最久）
  const getBrowsingHistory = () => {
    // 按時間排序（最近到最久）
    const sortedHistory = [...viewHistory].sort((a, b) => 
      new Date(b.viewed_at).getTime() - new Date(a.viewed_at).getTime()
    )
    
    // 轉換為電影格式，保留所有瀏覽記錄信息
    return sortedHistory.map(view => ({
      id: view.movie_id,
      title: view.movie_title,
      year: view.movie_year,
      poster_url: view.movie_poster_url,
      average_rating: view.movie_average_rating,
      rating_count: 0,
      genres: view.movie_genres ? view.movie_genres.split(', ') : [],
      runtime: undefined,
      language: '',
      country: '',
      director: '',
      cast: '',
      description: '',
      imdb_id: '',
      view_count: 0,
      like_count: 0,
      favorite_count: 0,
      comment_count: 0,
      // 瀏覽記錄信息
      view_id: view.id,
      user_id: view.user_id,
      viewed_at: view.viewed_at,
      view_duration: view.view_duration,
      view_type: view.view_type,
      user_rating: view.user_rating,
      is_favorite: view.is_favorite,
      is_liked: view.is_liked,
      has_review: view.has_review
    }))
  }

  const browsingHistory = getBrowsingHistory()
  
  // 完善搜索功能 - 支持標題、年份、類型搜索
  const filteredHistory = browsingHistory.filter(movie => {
    const searchLower = searchTerm.toLowerCase()
    return (
      movie.title.toLowerCase().includes(searchLower) ||
      movie.year?.toString().includes(searchLower) ||
      movie.genres.some((genre: string) => genre.toLowerCase().includes(searchLower))
    )
  })

  // 搜索建議
  const searchSuggestions = browsingHistory
    .filter(movie => 
      movie.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      movie.year?.toString().includes(searchTerm) ||
      movie.genres.some((genre: string) => genre.toLowerCase().includes(searchTerm.toLowerCase()))
    )
    .slice(0, 5)
    .map(movie => ({
      title: movie.title,
      year: movie.year,
      genres: movie.genres.join(', ')
    }))

  if (!isAuthenticated || !user) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="w-32 h-32 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-3xl flex items-center justify-center mx-auto mb-8">
            <span className="text-6xl">🔒</span>
          </div>
          <h3 className="text-2xl font-bold text-white mb-4">Please log in</h3>
          <p className="text-gray-300 text-lg mb-8">Log in to view your watch history</p>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return <LoadingSpinner message="Loading watch history..." />
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        {/* Hero Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-purple-500 to-pink-600 rounded-3xl mb-6 shadow-glow">
            <History className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-5xl font-bold text-white mb-4">
            <span className="text-gradient">Watch History</span>
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto">
            View your movie watch history and stats
          </p>
        </motion.div>

        {/* 統計卡片 */}
        {stats && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
          >
            <div className="bg-gradient-to-br from-blue-500/20 to-blue-600/20 rounded-2xl p-6 border border-blue-500/30">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-blue-200 text-sm font-medium">Total views</p>
                  <p className="text-3xl font-bold text-white">{stats.total_views || 0}</p>
                </div>
                <Clock className="w-8 h-8 text-blue-400" />
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-green-500/20 to-green-600/20 rounded-2xl p-6 border border-green-500/30">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-green-200 text-sm font-medium">Unique movies</p>
                  <p className="text-3xl font-bold text-white">{stats.unique_movies || 0}</p>
                </div>
                <Calendar className="w-8 h-8 text-green-400" />
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-purple-500/20 to-purple-600/20 rounded-2xl p-6 border border-purple-500/30">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-purple-200 text-sm font-medium">Total watch time (hrs)</p>
                  <p className="text-3xl font-bold text-white">{Math.round((stats.total_duration || 0) / 3600)}</p>
                </div>
                <Clock className="w-8 h-8 text-purple-400" />
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-pink-500/20 to-pink-600/20 rounded-2xl p-6 border border-pink-500/30">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-pink-200 text-sm font-medium">Avg watch time (min)</p>
                  <p className="text-3xl font-bold text-white">{Math.round((stats.average_duration || 0) / 60)}</p>
                </div>
                <Clock className="w-8 h-8 text-pink-400" />
              </div>
            </div>
          </motion.div>
        )}

        {/* 篩選和搜索控制 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gradient-to-r from-slate-800/50 to-slate-900/50 rounded-3xl shadow-2xl border border-white/10 p-8 backdrop-blur-xl"
        >
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between space-y-4 lg:space-y-0">
            {/* 篩選選項 */}
            <div className="flex flex-wrap items-center gap-6">
              <div className="flex items-center space-x-3">
                <label className="text-sm font-semibold text-white">Time range</label>
                <select
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value))}
                  className="px-4 py-2 bg-slate-700/50 text-white rounded-xl border border-white/20 focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
                >
                  <option value={7}>Last 7 days</option>
                  <option value={30}>Last 30 days</option>
                  <option value={90}>Last 90 days</option>
                  <option value={365}>Last year</option>
                </select>
              </div>

              <div className="flex items-center space-x-3">
                <label className="text-sm font-semibold text-white">Watch type</label>
                <select
                  value={viewType}
                  onChange={(e) => setViewType(e.target.value)}
                  className="px-4 py-2 bg-slate-700/50 text-white rounded-xl border border-white/20 focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
                >
                  <option value="">All types</option>
                  <option value="full">Full</option>
                  <option value="partial">Partial</option>
                  <option value="trailer">Trailer</option>
                  <option value="preview">Preview</option>
                </select>
              </div>
            </div>

            {/* 搜索和視圖控制 */}
            <div className="flex flex-col sm:flex-row sm:items-center space-y-4 sm:space-y-0 sm:space-x-4">
              {/* 搜索欄 */}
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-white/60" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value)
                    setShowSearchSuggestions(e.target.value.length > 0)
                  }}
                  onFocus={() => setShowSearchSuggestions(searchTerm.length > 0)}
                  onBlur={() => setTimeout(() => setShowSearchSuggestions(false), 200)}
                  placeholder="Search title, year, or genre..."
                  className="w-full pl-10 pr-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white placeholder-white/60 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
                {searchTerm && (
                  <button
                    onClick={() => {
                      setSearchTerm('')
                      setShowSearchSuggestions(false)
                    }}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-white/60 hover:text-white transition-colors"
                  >
                    ✕
                  </button>
                )}
                
                {/* 搜索建議 */}
                {showSearchSuggestions && searchSuggestions.length > 0 && (
                  <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800/95 backdrop-blur-xl border border-white/20 rounded-lg shadow-2xl z-50 max-h-60 overflow-y-auto">
                    {searchSuggestions.map((suggestion, index) => (
                      <div
                        key={index}
                        onClick={() => {
                          setSearchTerm(suggestion.title)
                          setShowSearchSuggestions(false)
                        }}
                        className="px-4 py-3 hover:bg-white/10 cursor-pointer border-b border-white/10 last:border-b-0"
                      >
                        <div className="text-white font-medium">{suggestion.title}</div>
                        <div className="text-gray-400 text-sm">
                          {suggestion.year} {suggestion.genres && `• ${suggestion.genres}`}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 視圖模式切換 */}
              <div className="flex items-center space-x-2">
                <span className="text-white/80 text-sm">
                  {searchTerm ? `Found ${filteredHistory.length} records` : `${filteredHistory.length} records`}
                </span>
                {searchTerm && (
                  <button
                    onClick={() => setSearchTerm('')}
                    className="text-blue-400 hover:text-blue-300 text-sm underline"
                  >
                    Clear search
                  </button>
                )}
                
                <div className="flex items-center space-x-2">
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => setViewMode('grid')}
                    className={`p-2 rounded-lg transition-colors duration-200 ${
                      viewMode === 'grid'
                        ? 'bg-blue-500 text-white'
                        : 'bg-white/20 text-white/60 hover:bg-white/30'
                    }`}
                  >
                    <Grid className="h-5 w-5" />
                  </motion.button>
                  
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => setViewMode('list')}
                    className={`p-2 rounded-lg transition-colors duration-200 ${
                      viewMode === 'list'
                        ? 'bg-blue-500 text-white'
                        : 'bg-white/20 text-white/60 hover:bg-white/30'
                    }`}
                  >
                    <List className="h-5 w-5" />
                  </motion.button>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* 瀏覽歷史列表 */}
        {filteredHistory.length > 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className={
              viewMode === 'grid'
                ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6'
                : 'space-y-4'
            }
          >
            {filteredHistory.map((movie, index) => (
              <motion.div
                key={movie.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className="relative"
              >
                {/* 瀏覽時間標籤 */}
                <div className="absolute top-2 right-2 z-10">
                  <div className="bg-gradient-to-r from-purple-500/90 to-pink-500/90 text-white text-xs px-2 py-1 rounded-full backdrop-blur-sm shadow">
                    {new Date(movie.viewed_at).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </div>
                </div>
                
                {/* 瀏覽類型標籤 */}
                {movie.view_type && (
                  <div className="absolute top-2 left-2 z-10">
                    <div className="bg-gradient-to-r from-blue-500/90 to-cyan-500/90 text-white text-xs px-2 py-1 rounded-full backdrop-blur-sm shadow">
                      {movie.view_type === 'preview' ? 'Preview' : 
                       movie.view_type === 'full' ? 'Full' :
                       movie.view_type === 'partial' ? 'Partial' :
                       movie.view_type === 'trailer' ? 'Trailer' : 'View'}
                    </div>
                  </div>
                )}
                
                {/* 瀏覽時長標籤 */}
                {movie.view_duration > 0 && (
                  <div className="absolute bottom-2 right-2 z-10">
                    <div className="bg-gradient-to-r from-green-500/90 to-emerald-500/90 text-white text-xs px-2 py-1 rounded-full backdrop-blur-sm shadow">
                      {Math.floor(movie.view_duration / 60)} min
                    </div>
                  </div>
                )}
                
                {/* 用戶評分標籤 */}
                {movie.user_rating > 0 && (
                  <div className="absolute bottom-2 left-2 z-10">
                    <div className="bg-gradient-to-r from-yellow-500/90 to-orange-500/90 text-white text-xs px-2 py-1 rounded-full backdrop-blur-sm shadow">
                      ⭐ {movie.user_rating}
                    </div>
                  </div>
                )}
                
                <MovieCard
                  movie={movie}
                  showRating={false}
                />
              </motion.div>
            ))}
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="text-center py-20"
          >
            <div className="w-32 h-32 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-3xl flex items-center justify-center mx-auto mb-8">
              <span className="text-6xl">📺</span>
            </div>
            <h3 className="text-2xl font-bold text-white mb-4">No watch history yet</h3>
            <p className="text-gray-300 text-lg mb-8">Start watching movies to build your history.</p>
            <div className="w-24 h-1 bg-gradient-to-r from-purple-500 to-pink-600 rounded-full mx-auto"></div>
          </motion.div>
        )}
      </div>
    </div>
  )
}

export default ViewHistory