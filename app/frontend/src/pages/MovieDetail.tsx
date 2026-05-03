import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useParams, useNavigate } from 'react-router-dom'
import { 
  Star, 
  Heart, 
  ThumbsUp, 
  Play, 
  Calendar, 
  Clock, 
  Award, 
  Users,
  Share2,
  ArrowLeft,
  ChevronRight,
  Sparkles,
  TrendingUp
} from 'lucide-react'
import { movieApi, ratingApi, viewHistoryApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import StarRating from '../components/StarRating'
import { CommentForm } from '../components/CommentForm'
import { CommentList } from '../components/CommentList'
import type { CommentListRef } from '../components/CommentList'
import type { Movie } from '../services/api'
import toast from 'react-hot-toast'

const MovieDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user, refreshUserProfile } = useAuthStore()
  const [movie, setMovie] = useState<Movie | null>(null)
  const [userRating, setUserRating] = useState(0)
  const [isFavorite, setIsFavorite] = useState(false)
  const [isLiked, setIsLiked] = useState(false)
  const [loading, setLoading] = useState(true)
  const [ratingLoading, setRatingLoading] = useState(false)
  const [favoriteLoading, setFavoriteLoading] = useState(false)
  const [likeLoading, setLikeLoading] = useState(false)
  const commentListRef = useRef<CommentListRef>(null)
  const [commentSortBy, setCommentSortBy] = useState<'newest' | 'oldest'>('newest')

  console.log('MovieDetail component rendered, id:', id, 'loading:', loading, 'movie:', movie)

  useEffect(() => {
    console.log('MovieDetail useEffect triggered, id:', id)
    if (id) {
      loadMovieDetail()
    } else {
      console.log('No id provided')
    }
  }, [id])

  // 記錄瀏覽歷史
  useEffect(() => {
    if (movie && user) {
      recordViewHistory()
    }
  }, [movie, user])

  const loadMovieDetail = async () => {
    try {
      console.log('Loading movie detail for ID:', id)
      setLoading(true)
      
      // 首先加載電影基本信息
      const movieData = await movieApi.getMovie(parseInt(id!))
      console.log('Movie data loaded:', movieData)
      setMovie(movieData)
      setLoading(false) // 立即設置加載完成，讓用戶看到電影信息
      
      // 然後並行加載其他信息
      const loadAdditionalData = async () => {
        try {
          // 並行加載用戶評分和狀態
          const [ratingResponse, statusResponse] = await Promise.allSettled([
            ratingApi.getUserRating(movieData.id),
            movieApi.getMovieStatus(movieData.id)
          ])
          
          // 處理評分結果
          if (ratingResponse.status === 'fulfilled' && ratingResponse.value.has_rated) {
            setUserRating(ratingResponse.value.rating)
          }
          
          // 處理狀態結果
          if (statusResponse.status === 'fulfilled') {
            setIsFavorite(statusResponse.value.is_favorite)
            setIsLiked(statusResponse.value.is_liked)
          } else {
            setIsFavorite(false)
            setIsLiked(false)
          }
        } catch (error) {
          console.log('Failed to load additional data:', error)
          setIsFavorite(false)
          setIsLiked(false)
        }
      }
      
      // 異步加載其他數據，不阻塞主要內容顯示
      loadAdditionalData()
      
    } catch (error) {
      console.error('Failed to load movie:', error)
      console.error('Error details:', error)
      toast.error('Failed to load movie details')
      setLoading(false)
    }
  }

  const handleRating = async (rating: number) => {
    if (!movie || !user) return
    
    try {
      setRatingLoading(true)
      await ratingApi.createOrUpdateRating(movie.id, rating)
      toast.success('Rating successful!')
      setUserRating(rating)
      
      // 延遲重新載入電影數據以更新平均評分
      setTimeout(() => {
        loadMovieDetail()
      }, 500)
      
      // 延遲刷新用戶資料以更新統計數據
      setTimeout(async () => {
        await refreshUserProfile()
      }, 1000)
    } catch (error) {
      console.error('Rating failed:', error)
      toast.error('Rating failed')
      setUserRating(0)
    } finally {
      setRatingLoading(false)
    }
  }

  const handleToggleFavorite = async () => {
    if (!movie || !user || favoriteLoading) return
    
    try {
      setFavoriteLoading(true)
      await movieApi.toggleFavorite(movie.id)
      setIsFavorite(!isFavorite)
      toast.success(isFavorite ? 'Removed from favorites' : 'Added to favorites')
      
      // 只刷新用戶資料，電影統計會在下次載入時更新
      await refreshUserProfile()
    } catch (error) {
      console.error('Favorite operation failed:', error)
      toast.error('Operation failed, please try again')
    } finally {
      setFavoriteLoading(false)
    }
  }

  const handleToggleLike = async () => {
    if (!movie || !user || likeLoading) return
    
    try {
      setLikeLoading(true)
      await movieApi.toggleLike(movie.id)
      setIsLiked(!isLiked)
      toast.success(isLiked ? 'Like removed' : 'Liked')
      
      // 只刷新用戶資料，電影統計會在下次載入時更新
      await refreshUserProfile()
    } catch (error) {
      console.error('Like operation failed:', error)
      toast.error('Operation failed, please try again')
    } finally {
      setLikeLoading(false)
    }
  }

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: movie?.title,
          text: movie?.description,
          url: window.location.href
        })
      } catch (error) {
        console.log('Share cancelled')
      }
    } else {
      // 複製到剪貼板
      navigator.clipboard.writeText(window.location.href)
      toast.success('Link copied to clipboard')
    }
  }

  const recordViewHistory = async () => {
    if (!movie || !user) return

    try {
      await viewHistoryApi.createViewHistory({
        movie_id: movie.id,
        view_duration: 0, // 可以根據實際觀看時間調整
        view_type: 'preview' // 預設為預覽類型
      })
    } catch (error) {
      console.error('Error recording view history:', error)
    }
  }

  const handleCommentAdded = () => {
    // 刷新評論列表
    if (commentListRef.current) {
      commentListRef.current.refreshComments()
    }
  }

  if (loading) {
    console.log('MovieDetail loading state:', loading)
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="loading-spinner mx-auto mb-4"></div>
          <p className="text-gray-400">Loading movie details...</p>
        </div>
      </div>
    )
  }

  if (!movie) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-white mb-4">Movie Not Found</h2>
          <button
            onClick={() => navigate('/movies')}
            className="btn-primary"
          >
            Back to Movie List
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* 返回按鈕 */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5 }}
        className="fixed top-24 left-4 z-40"
      >
        <button
          onClick={() => navigate('/movies')}
          className="p-3 bg-gray-800/80 backdrop-blur-xl rounded-xl text-white hover:bg-gray-700 transition-all duration-300 shadow-lg"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
      </motion.div>

      {/* 電影海報和基本信息 */}
      <section className="relative">
        {/* 背景圖片 */}
        <div className="absolute inset-0">
          <img
            src={movie.poster_url || '/api/placeholder/1920/1080'}
            alt={movie.title}
            className="w-full h-[70vh] object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-gray-900 via-gray-900/80 to-transparent"></div>
        </div>

        <div className="relative z-10 pt-32 pb-16 px-4 sm:px-6 lg:px-8">
          <div className="max-w-7xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
              {/* 電影海報 */}
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.6 }}
                className="lg:col-span-1"
              >
                <div className="relative group">
                  <img
                    src={movie.poster_url || '/api/placeholder/400/600'}
                    alt={movie.title}
                    className="w-full max-w-sm mx-auto rounded-2xl shadow-2xl transition-transform duration-500 group-hover:scale-105"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                  <div className="absolute bottom-4 left-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                    <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-xl transition-colors duration-300 flex items-center justify-center space-x-2">
                      <Play className="w-5 h-5" />
                      <span>Play Trailer</span>
                    </button>
                  </div>
                </div>
              </motion.div>

              {/* 電影信息 */}
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.2 }}
                className="lg:col-span-2"
              >
                <div className="text-white">
                  <h1 className="text-5xl font-bold mb-4 text-gradient">{movie.title}</h1>
                  
                  <div className="flex flex-wrap items-center gap-4 mb-6">
                    <div className="flex items-center space-x-2 bg-yellow-500/20 rounded-full px-3 py-1">
                      <Star className="w-5 h-5 text-yellow-400 fill-current" />
                      <span className="text-yellow-400 font-semibold">{movie.average_rating?.toFixed(1) || 'N/A'}</span>
                    </div>
                    
                    <div className="flex items-center space-x-2 text-gray-300">
                      <Calendar className="w-4 h-4" />
                      <span>{movie.year}</span>
                    </div>
                    
                    <div className="flex items-center space-x-2 text-gray-300">
                      <Clock className="w-4 h-4" />
                      <span>{movie.runtime} minutes</span>
                    </div>
                    
                    <div className="flex items-center space-x-2 text-gray-300">
                      <Award className="w-4 h-4" />
                      <span>{movie.director}</span>
                    </div>
                  </div>

                  <p className="text-xl text-gray-300 mb-8 leading-relaxed">
                    {movie.description}
                  </p>

                  {/* 操作按鈕 */}
                  <div className="flex flex-wrap gap-4 mb-8">
                    <motion.button
                      whileHover={{ scale: favoriteLoading ? 1 : 1.05 }}
                      whileTap={{ scale: favoriteLoading ? 1 : 0.95 }}
                      onClick={handleToggleFavorite}
                      disabled={favoriteLoading}
                      className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-semibold transition-all duration-300 ${
                        isFavorite
                          ? 'bg-red-600 text-white shadow-glow'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white'
                      } ${favoriteLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <Heart className={`w-5 h-5 ${isFavorite ? 'fill-current' : ''}`} />
                      <span>{favoriteLoading ? 'Loading...' : (isFavorite ? 'Favorited' : 'Favorite')}</span>
                    </motion.button>

                    <motion.button
                      whileHover={{ scale: likeLoading ? 1 : 1.05 }}
                      whileTap={{ scale: likeLoading ? 1 : 0.95 }}
                      onClick={handleToggleLike}
                      disabled={likeLoading}
                      className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-semibold transition-all duration-300 ${
                        isLiked
                          ? 'bg-green-600 text-white shadow-glow'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white'
                      } ${likeLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <ThumbsUp className={`w-5 h-5 ${isLiked ? 'fill-current' : ''}`} />
                      <span>{likeLoading ? 'Loading...' : (isLiked ? 'Liked' : 'Like')}</span>
                    </motion.button>

                    <motion.button
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={handleShare}
                      className="flex items-center space-x-2 px-6 py-3 bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white rounded-xl font-semibold transition-all duration-300"
                    >
                      <Share2 className="w-5 h-5" />
                      <span>Share</span>
                    </motion.button>
                  </div>

                  {/* 評分區域 */}
                  {user && (
                    <div className="card p-6">
                      <h3 className="text-xl font-bold text-white mb-4">Rate This Movie</h3>
                      <div className="flex items-center space-x-4">
                        <StarRating
                          rating={userRating}
                          movieId={movie.id}
                          size="lg"
                          showNumber={true}
                          theme="dark"
                          onRatingChange={async (rating) => {
                            setUserRating(rating)
                            handleRating(rating)
                          }}
                        />
                        {ratingLoading && (
                          <div className="loading-dots">
                            <div></div>
                            <div></div>
                            <div></div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </section>

      {/* 電影統計 */}
      <section className="py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="grid grid-cols-2 md:grid-cols-4 gap-6"
          >
            {[
              { icon: Star, label: 'Average Rating', value: movie.average_rating?.toFixed(1) || 'N/A', color: 'text-yellow-400' },
              { icon: Users, label: 'Ratings', value: movie.rating_count || 0, color: 'text-blue-400' },
              { icon: Heart, label: 'Favorites', value: movie.favorite_count || 0, color: 'text-red-400' },
              { icon: ThumbsUp, label: 'Likes', value: movie.like_count || 0, color: 'text-green-400' }
            ].map((stat, index) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5, delay: index * 0.1 }}
                className="card text-center"
              >
                <stat.icon className={`w-8 h-8 mx-auto mb-3 ${stat.color}`} />
                <div className="text-2xl font-bold text-white mb-1">{stat.value}</div>
                <div className="text-sm text-gray-400">{stat.label}</div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* 評論區域 */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-slate-900/50 to-purple-900/30 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            className="mb-16"
          >
            {/* 標題區域 */}
            <div className="text-center mb-16">
              <h2 className="text-4xl font-bold text-white mb-4">Comments & Discussion</h2>
              <p className="text-gray-300 text-lg mb-8">Share your thoughts about this movie</p>
              <div className="w-24 h-1 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full mx-auto"></div>
            </div>

            {/* 評論區域布局 - 上下布局 */}
            <div className="space-y-12">
              {/* 評論列表 - 上方 */}
              <div className="bg-gradient-to-br from-slate-800/60 to-slate-900/60 rounded-3xl shadow-2xl border border-white/15 p-10 backdrop-blur-xl">
                <div className="flex items-center justify-between mb-10">
                  <div>
                    <h3 className="text-3xl font-bold text-white mb-3 bg-gradient-to-r from-green-400 to-cyan-400 bg-clip-text text-transparent">
                      All Comments
                    </h3>
                    <p className="text-gray-300 text-lg">See what other users think</p>
                  </div>
                  <div className="flex space-x-3">
                    <button 
                      onClick={() => setCommentSortBy('newest')}
                      className={`px-6 py-3 rounded-2xl transition-all duration-300 text-sm font-medium transform hover:scale-105 ${
                        commentSortBy === 'newest' 
                          ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-xl' 
                          : 'bg-white/10 text-white hover:bg-white/20 border border-white/20'
                      }`}
                    >
                      ✨ Newest
                    </button>
                    <button 
                      onClick={() => setCommentSortBy('oldest')}
                      className={`px-6 py-3 rounded-2xl transition-all duration-300 text-sm font-medium transform hover:scale-105 ${
                        commentSortBy === 'oldest' 
                          ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-xl' 
                          : 'bg-white/10 text-white hover:bg-white/20 border border-white/20'
                      }`}
                    >
                      📅 Oldest
                    </button>
                  </div>
                </div>
                
                <CommentList
                  ref={commentListRef}
                  movieId={movie.id}
                  currentUserId={user?.id}
                  commentType="all"
                  sortBy={commentSortBy}
                  pageSize={10}
                />
              </div>

              {/* 評論表單 - 下方 */}
              <div className="bg-gradient-to-br from-slate-800/90 to-slate-900/90 rounded-3xl shadow-2xl border border-white/20 p-10 backdrop-blur-xl">
                <div className="text-center mb-10">
                  <h3 className="text-3xl font-bold text-white mb-3 bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                    Comments & Discussion
                  </h3>
                  <p className="text-gray-300 text-lg">Share your thoughts about this movie</p>
                  <div className="w-20 h-1 bg-gradient-to-r from-purple-500 to-blue-500 mx-auto mt-4 rounded-full"></div>
                </div>
                
                {user ? (
                  <CommentForm
                    movieId={movie.id}
                    onCommentAdded={handleCommentAdded}
                    commentType="review"
                  />
                ) : (
                  <div className="text-center py-16">
                    <div className="w-20 h-20 bg-gradient-to-br from-blue-500/20 to-purple-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
                      <svg className="w-10 h-10 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    </div>
                    <h3 className="text-2xl font-bold text-white mb-4">Please log in</h3>
                    <p className="text-gray-300 mb-8 text-lg">Log in to post a comment</p>
                    <button
                      onClick={() => navigate('/login')}
                      className="px-10 py-4 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-2xl hover:from-blue-600 hover:to-purple-700 transition-all duration-200 transform hover:scale-105 shadow-xl font-medium text-lg"
                    >
                      Log in now
                    </button>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* 相關電影推薦 */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 bg-gray-800/30">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="flex items-center justify-between mb-12"
          >
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-purple-600/20 rounded-xl">
                <Sparkles className="w-6 h-6 text-purple-400" />
              </div>
              <div>
                <h2 className="text-3xl font-bold text-white">Related Recommendations</h2>
                <p className="text-gray-400">Recommendations based on this movie</p>
              </div>
            </div>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => navigate('/movies')}
              className="btn-ghost flex items-center space-x-2"
            >
              <span>View more</span>
              <ChevronRight className="w-4 h-4" />
            </motion.button>
          </motion.div>

          <div className="text-center py-16">
            <div className="w-24 h-24 bg-gray-700 rounded-full flex items-center justify-center mx-auto mb-6">
              <TrendingUp className="w-12 h-12 text-gray-400" />
            </div>
            <h3 className="text-2xl font-bold text-white mb-2">Recommendation Feature Under Development</h3>
            <p className="text-gray-400 mb-6">We are preparing personalized recommendations for you</p>
            <button
              onClick={() => navigate('/movies')}
              className="btn-primary"
            >
              Browse More Movies
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}

export default MovieDetail
