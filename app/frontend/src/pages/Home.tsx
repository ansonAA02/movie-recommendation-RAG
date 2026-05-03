import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { 
  Play, 
  Star, 
  Heart, 
  TrendingUp, 
  Award, 
  Users, 
  Clock,
  Sparkles,
  ArrowRight,
  ChevronRight,
  Film,
  MessageCircle,
  Bookmark
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { movieApi, kgRecommendApi } from '../services/api'
import type { Movie } from '../services/api'
import toast from 'react-hot-toast'

const Home = () => {
  const [featuredMovies, setFeaturedMovies] = useState<Movie[]>([])
  const [trendingMovies, setTrendingMovies] = useState<Movie[]>([])
  const [kgRecMovies, setKgRecMovies] = useState<Movie[]>([])
  const [kgReasons, setKgReasons] = useState<Record<number, string>>({})
  const [userContext, setUserContext] = useState<any>(null)
  const [kgLoading, setKgLoading] = useState(true)
  // const [topRatedMovies, setTopRatedMovies] = useState<Movie[]>([]) // 暫時未使用
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    loadHomeData()
  }, [])

  const loadHomeData = async () => {
    try {
      setLoading(true)
      setKgLoading(true)

      // 首屏資料先回來，避免整頁被 KG-RAG 慢請求卡住
      const [featured, trending] = await Promise.all([
        movieApi.getMovies({ limit: 6 }),
        movieApi.getMovies({ limit: 8 }),
      ])
      
      setFeaturedMovies(featured.slice(0, 6))
      setTrendingMovies(trending.slice(0, 8))
      setLoading(false)

      // KG-RAG 與 context 後載入，不阻塞首頁首屏
      Promise.all([
        kgRecommendApi.getKgRag(6).catch(() => []),
        kgRecommendApi.getUserContext().catch(() => null),
      ])
        .then(([kgRec, context]) => {
          if (Array.isArray(kgRec) && kgRec.length > 0) {
            const reasonMap: Record<number, string> = {}
            kgRec.forEach((movie: any) => {
              reasonMap[movie.movie_id] = movie.reason || 'Recommended for you'
            })
            setKgRecMovies(kgRec)
            setKgReasons(reasonMap)
          } else {
            setKgRecMovies([])
            setKgReasons({})
          }
          setUserContext(context)
        })
        .finally(() => {
          setKgLoading(false)
        })
    } catch (error) {
      console.error('Failed to load home data:', error)
      toast.error('Failed to load data')
      setLoading(false)
      setKgLoading(false)
    } finally {
      // 首屏 loading 由 featured/trending 控制，避免被慢查詢覆蓋
    }
  }

  const handleMovieClick = (movieId: number) => {
    navigate(`/movies/${movieId}`)
  }

  const handleQuickAction = (action: string) => {
    switch (action) {
      case 'browse':
        navigate('/movies')
        break
      case 'chat':
        // 對齊現有路由：目前 AI 互動入口在 Enhanced Recommendations
        navigate('/enhanced-recommendations')
        break
      case 'favorites':
        navigate('/favorites')
        break
      default:
        break
    }
  }

  const handleAddToFavorites = async (movieId: number) => {
    try {
      const res = await movieApi.toggleFavorite(movieId)
      toast.success(res?.message || 'Updated favorites')
    } catch (error) {
      console.error('Failed to update favorite:', error)
      toast.error('Failed to update favorites. Please try again later.')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="loading-spinner mx-auto mb-4"></div>
          <p className="text-gray-400">Loading great content...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* 英雄區域 */}
      <section className="relative py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            className="text-center mb-16"
          >
            <div className="inline-flex items-center space-x-2 bg-blue-600/20 text-blue-400 px-4 py-2 rounded-full text-sm font-medium mb-6">
              <Sparkles className="w-4 h-4" />
              <span>Intelligent Movie Recommendation Platform</span>
            </div>
            
            <h1 className="text-5xl md:text-7xl font-bold text-white mb-6">
              <span className="text-gradient">Discover</span>
              <br />
              Amazing Movie World
            </h1>
            
            <p className="text-xl text-gray-300 mb-8 max-w-2xl mx-auto">
              AI-powered intelligent recommendation system that precisely recommends the most suitable movie content for you
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => handleQuickAction('browse')}
                className="btn-primary flex items-center space-x-2"
              >
                <Play className="w-5 h-5" />
                <span>Start Exploring</span>
                <ArrowRight className="w-4 h-4" />
              </motion.button>
              
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => handleQuickAction('chat')}
                className="btn-ghost flex items-center space-x-2"
              >
                <MessageCircle className="w-5 h-5" />
                <span>AI Assistant</span>
              </motion.button>
            </div>
          </motion.div>

          {/* 統計數據 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-16"
          >
            {[
              { icon: Film, label: 'Total Movies', value: '10,000+', color: 'text-blue-400' },
              { icon: Users, label: 'Active Users', value: '50,000+', color: 'text-green-400' },
              { icon: Star, label: 'Average Rating', value: '4.8/5', color: 'text-yellow-400' },
              { icon: Award, label: 'Recommendation Accuracy', value: '95%', color: 'text-purple-400' }
            ].map((stat, index) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5, delay: 0.3 + index * 0.1 }}
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

      {/* KG Recommendations (Personalized) */}
      <section className="py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="flex items-center justify-between mb-12"
          >
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-blue-600/20 rounded-xl">
                <Sparkles className="w-6 h-6 text-blue-400" />
              </div>
              <div>
                <h2 className="text-3xl font-bold text-white">For You</h2>
                <p className="text-gray-400">
                  {userContext ? (
                    <>
                      {userContext.cold_start ? 'New user recommendations' : 
                       `Personalized for ${userContext.activity_level} activity user`}
                      {userContext.should_retrieve_kg && ' • KG-enhanced'}
                    </>
                  ) : (
                    'KG-augmented recommendations with reasons'
                  )}
                </p>
              </div>
            </div>
          </motion.div>

          {kgLoading ? (
            <div className="text-sm text-gray-400">Loading personalized recommendations...</div>
          ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {kgRecMovies.map((movie, index) => (
              <motion.div
                key={`kg-${movie.id}`}
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                whileHover={{ scale: 1.05 }}
                className="movie-card group cursor-pointer"
                onClick={() => handleMovieClick(movie.id)}
              >
                <div className="movie-card-content">
                  <div className="relative overflow-hidden rounded-xl mb-4">
                    <img
                      src={movie.poster_url || '/api/placeholder/300/450'}
                      alt={movie.title}
                      className="w-full h-64 object-cover transition-transform duration-500 group-hover:scale-110"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    <div className="absolute top-4 left-4">
                      <span className="px-2.5 py-1 text-xs rounded-full bg-white/15 text-blue-200 backdrop-blur-sm border border-white/10">
                        {kgReasons[movie.id] || 'Recommended'}
                      </span>
                    </div>
                  </div>

                  <div className="p-6">
                    <h3 className="text-xl font-bold text-white mb-2 group-hover:text-blue-400 transition-colors">
                      {movie.title}
                    </h3>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <div className="flex items-center space-x-1">
                          <Star className="w-4 h-4 text-yellow-400 fill-current" />
                          <span className="text-white font-semibold">{movie.average_rating?.toFixed(1) || 'N/A'}</span>
                        </div>
                        <span className="text-gray-400">•</span>
                        <span className="text-gray-400 text-sm">{movie.year}</span>
                      </div>

                      <div className="flex items-center space-x-1 text-gray-400 text-sm">
                        <Clock className="w-4 h-4" />
                        <span>{movie.runtime} minutes</span>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
          )}
        </div>
      </section>

      {/* 精選電影 */}
      <section className="py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="flex items-center justify-between mb-12"
          >
            <div>
              <h2 className="text-3xl font-bold text-white mb-2">Featured Recommendations</h2>
              <p className="text-gray-400">Carefully selected based on your preferences</p>
            </div>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => navigate('/movies')}
              className="btn-ghost flex items-center space-x-2"
            >
              <span>View All</span>
              <ChevronRight className="w-4 h-4" />
            </motion.button>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {featuredMovies.map((movie, index) => (
              <motion.div
                key={movie.id}
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                whileHover={{ scale: 1.05 }}
                className="movie-card group cursor-pointer"
                onClick={() => handleMovieClick(movie.id)}
              >
                <div className="movie-card-content">
                  <div className="relative overflow-hidden rounded-xl mb-4">
                    <img
                      src={movie.poster_url || '/api/placeholder/300/450'}
                      alt={movie.title}
                      className="w-full h-64 object-cover transition-transform duration-500 group-hover:scale-110"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleAddToFavorites(movie.id)
                        }}
                        className="p-2 bg-white/20 backdrop-blur-sm rounded-full text-white hover:bg-white/30 transition-colors"
                        title="Add to favorites"
                        aria-label="Add to favorites"
                      >
                        <Heart className="w-4 h-4" />
                      </button>
                    </div>
                    <div className="absolute bottom-4 left-4 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleMovieClick(movie.id)
                        }}
                        className="p-2 bg-blue-600 rounded-full text-white hover:bg-blue-700 transition-colors"
                        title="View movie details"
                        aria-label="View movie details"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  
                  <div className="p-6">
                    <h3 className="text-xl font-bold text-white mb-2 group-hover:text-blue-400 transition-colors">
                      {movie.title}
                    </h3>
                    <p className="text-gray-400 text-sm mb-4 line-clamp-2">
                      {movie.description}
                    </p>
                    
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <div className="flex items-center space-x-1">
                          <Star className="w-4 h-4 text-yellow-400 fill-current" />
                          <span className="text-white font-semibold">{movie.average_rating?.toFixed(1) || 'N/A'}</span>
                        </div>
                        <span className="text-gray-400">•</span>
                        <span className="text-gray-400 text-sm">{movie.year}</span>
                      </div>
                      
                      <div className="flex items-center space-x-1 text-gray-400 text-sm">
                        <Clock className="w-4 h-4" />
                        <span>{movie.runtime} minutes</span>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Trending Movies */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 bg-gray-800/30">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="flex items-center justify-between mb-12"
          >
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-orange-600/20 rounded-xl">
                <TrendingUp className="w-6 h-6 text-orange-400" />
              </div>
              <div>
                <h2 className="text-3xl font-bold text-white">Trending Movies</h2>
                <p className="text-gray-400">Currently most popular movies</p>
              </div>
            </div>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => navigate('/movies')}
              className="btn-ghost flex items-center space-x-2"
            >
              <span>View All</span>
              <ChevronRight className="w-4 h-4" />
            </motion.button>
          </motion.div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-6">
            {trendingMovies.map((movie, index) => (
              <motion.div
                key={movie.id}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5, delay: index * 0.05 }}
                whileHover={{ scale: 1.05 }}
                className="group cursor-pointer"
                onClick={() => handleMovieClick(movie.id)}
              >
                <div className="relative overflow-hidden rounded-xl mb-3">
                  <img
                    src={movie.poster_url || '/api/placeholder/200/300'}
                    alt={movie.title}
                    className="w-full h-48 object-cover transition-transform duration-300 group-hover:scale-110"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                  <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                    <div className="p-1 bg-yellow-500 rounded-full">
                      <Star className="w-3 h-3 text-white fill-current" />
                    </div>
                  </div>
                </div>
                <h3 className="text-sm font-semibold text-white group-hover:text-blue-400 transition-colors line-clamp-2">
                  {movie.title}
                </h3>
                <div className="flex items-center space-x-1 mt-1">
                  <Star className="w-3 h-3 text-yellow-400 fill-current" />
                  <span className="text-xs text-gray-400">{movie.average_rating?.toFixed(1) || 'N/A'}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* 快速操作 */}
      <section className="py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-center mb-12"
          >
            <h2 className="text-3xl font-bold text-white mb-4">Quick Start</h2>
            <p className="text-gray-400">Choose the action you want</p>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                icon: Film,
                title: 'Browse Movies',
                description: 'Explore rich movie collection',
                action: 'browse',
                color: 'from-blue-500 to-blue-600',
                hoverColor: 'hover:from-blue-600 hover:to-blue-700'
              },
              {
                icon: MessageCircle,
                title: 'AI Assistant',
                description: 'Chat with intelligent assistant',
                action: 'chat',
                color: 'from-purple-500 to-purple-600',
                hoverColor: 'hover:from-purple-600 hover:to-purple-700'
              },
              {
                icon: Bookmark,
                title: 'My Favorites',
                description: 'View personal favorites',
                action: 'favorites',
                color: 'from-pink-500 to-pink-600',
                hoverColor: 'hover:from-pink-600 hover:to-pink-700'
              }
            ].map((item, index) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => handleQuickAction(item.action)}
                className="card-elevated cursor-pointer group"
              >
                <div className={`w-16 h-16 bg-gradient-to-br ${item.color} rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300`}>
                  <item.icon className="w-8 h-8 text-white" />
                </div>
                <h3 className="text-xl font-bold text-white mb-3">{item.title}</h3>
                <p className="text-gray-400 mb-6">{item.description}</p>
                <div className="flex items-center text-blue-400 group-hover:text-blue-300 transition-colors">
                  <span className="font-medium">Get Started</span>
                  <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

export default Home