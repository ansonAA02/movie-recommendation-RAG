import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Search, 
  // Filter, - 暫時未使用 
  Grid, 
  List, 
  Star, 
  Heart, 
  Clock,
  Calendar,
  TrendingUp,
  Award,
  Sparkles,
  ChevronDown,
  X,
  SlidersHorizontal,
  Film
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { movieApi } from '../services/api'
import type { Movie } from '../services/api'
import toast from 'react-hot-toast'

const MovieList = () => {
  const [movies, setMovies] = useState<Movie[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [sortBy, setSortBy] = useState('rating')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [showFilters, setShowFilters] = useState(false)
  const [filters, setFilters] = useState({
    genre: '',
    year: '',
    rating: '',
    runtime: ''
  })
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [suggestions, setSuggestions] = useState<Array<{ id: number; title: string; year?: number }>>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    loadMovies()
  }, [currentPage, sortBy, filters])

  const loadMovies = async () => {
    try {
      setLoading(true)
      const runtimeFilter = (() => {
        if (!filters.runtime) return { runtime_min: undefined as number | undefined, runtime_max: undefined as number | undefined }
        if (filters.runtime === '90') return { runtime_min: undefined, runtime_max: 90 }
        if (filters.runtime === '120') return { runtime_min: 90, runtime_max: 120 }
        if (filters.runtime === '150') return { runtime_min: 120, runtime_max: 150 }
        return { runtime_min: 150, runtime_max: undefined }
      })()

      const queryParams = {
        search: searchTerm || undefined,
        genre: filters.genre || undefined,
        year: filters.year ? Number(filters.year) : undefined,
        min_rating: filters.rating ? Number(filters.rating) : undefined,
        runtime_min: runtimeFilter.runtime_min,
        runtime_max: runtimeFilter.runtime_max,
      }

      const [response, countResp] = await Promise.all([
        movieApi.getMovies({
        skip: (currentPage - 1) * 20,
        limit: 20,
          sort_by: sortBy as 'rating' | 'popularity' | 'year' | 'title',
          ...queryParams,
        }),
        movieApi.getMovieCount(queryParams),
      ])
      setMovies(response)
      const total = Number(countResp?.total || 0)
      setTotalPages(Math.max(1, Math.ceil(total / 20)))
    } catch (error) {
      console.error('Failed to load movies:', error)
      toast.error('Failed to load movies')
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setCurrentPage(1)
    setShowSuggestions(false)
    loadMovies()
  }

  useEffect(() => {
    const q = searchTerm.trim()
    if (q.length < 2) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }
    const t = setTimeout(async () => {
      try {
        const rows = await movieApi.getMovieSuggestions(q, 8)
        setSuggestions(rows)
        setShowSuggestions(rows.length > 0)
      } catch {
        setSuggestions([])
        setShowSuggestions(false)
      }
    }, 250)
    return () => clearTimeout(t)
  }, [searchTerm])

  const handleMovieClick = (movieId: number) => {
    navigate(`/movies/${movieId}`)
  }

  const handleSortChange = (newSort: string) => {
    setSortBy(newSort)
    setCurrentPage(1)
  }

  const handleFilterChange = (key: string, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }))
    setCurrentPage(1)
  }

  const clearFilters = () => {
    setFilters({
      genre: '',
      year: '',
      rating: '',
      runtime: ''
    })
    setSearchTerm('')
    setSuggestions([])
    setShowSuggestions(false)
    setCurrentPage(1)
  }

  const sortOptions = [
    { value: 'rating', label: 'Rating', icon: Star },
    { value: 'popularity', label: 'Popularity', icon: TrendingUp },
    { value: 'year', label: 'Year', icon: Calendar },
    { value: 'title', label: 'Title', icon: Award }
  ]

  const genreOptions = [
    'Action', 'Adventure', 'Animation', 'Comedy', 'Crime', 'Documentary', 'Drama', 'Family',
    'Fantasy', 'History', 'Horror', 'Music', 'Mystery', 'Romance', 'Sci-Fi', 'Sport', 'Thriller', 'War', 'Western'
  ]

  const yearOptions = Array.from({ length: 30 }, (_, i) => 2024 - i)

  const buildPagination = (current: number, total: number): Array<number | string> => {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
    const pages: Array<number | string> = [1]
    const left = Math.max(2, current - 1)
    const right = Math.min(total - 1, current + 1)

    if (left > 2) pages.push('...')
    for (let p = left; p <= right; p += 1) pages.push(p)
    if (right < total - 1) pages.push('...')
    pages.push(total)
    return pages
  }

  if (loading && movies.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="loading-spinner mx-auto mb-4"></div>
          <p className="text-gray-400">Loading movies...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        {/* Page Title */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-8"
        >
          <div className="flex items-center space-x-3 mb-4">
            <div className="p-2 bg-blue-600/20 rounded-xl">
              <Sparkles className="w-6 h-6 text-blue-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-white">Movie Library</h1>
              <p className="text-gray-400">Explore the rich world of movies</p>
            </div>
          </div>
        </motion.div>

        {/* Search and Filter Area */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="card mb-8"
        >
          <div className="flex flex-col lg:flex-row gap-4">
            {/* Search Box */}
            <form onSubmit={handleSearch} className="flex-1">
              <div className="relative">
                <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                <input
                  type="text"
                  placeholder="Search movie titles, directors, actors..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  onFocus={() => {
                    if (suggestions.length > 0) setShowSuggestions(true)
                  }}
                  className="input-field pl-12 pr-4"
                />
                {showSuggestions && (
                  <div className="absolute z-20 mt-2 w-full rounded-xl border border-gray-700 bg-gray-900 shadow-xl max-h-72 overflow-y-auto">
                    {suggestions.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => {
                          setSearchTerm(s.title)
                          setShowSuggestions(false)
                          setCurrentPage(1)
                          setTimeout(() => {
                            void loadMovies()
                          }, 0)
                        }}
                        className="w-full text-left px-4 py-3 hover:bg-gray-800 border-b border-gray-800 last:border-b-0"
                      >
                        <div className="text-white font-medium">{s.title}</div>
                        <div className="text-xs text-gray-400">{s.year || 'Unknown year'}</div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </form>

            {/* Sort Options */}
            <div className="flex items-center space-x-2">
              <span className="text-gray-400 text-sm">Sort:</span>
              <div className="flex space-x-1 bg-gray-700 rounded-lg p-1">
                {sortOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => handleSortChange(option.value)}
                    className={`flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium transition-all duration-300 ${
                      sortBy === option.value
                        ? 'bg-blue-600 text-white shadow-lg'
                        : 'text-gray-300 hover:text-white hover:bg-gray-600'
                    }`}
                  >
                    <option.icon className="w-4 h-4" />
                    <span>{option.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center space-x-2">
              <span className="text-gray-400 text-sm">View:</span>
              <div className="flex bg-gray-700 rounded-lg p-1">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-2 rounded-md transition-all duration-300 ${
                    viewMode === 'grid'
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  <Grid className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  className={`p-2 rounded-md transition-all duration-300 ${
                    viewMode === 'list'
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  <List className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Filter Button */}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowFilters(!showFilters)}
              className="btn-ghost flex items-center space-x-2"
            >
              <SlidersHorizontal className="w-4 h-4" />
              <span>Filter</span>
              <ChevronDown className={`w-4 h-4 transition-transform duration-300 ${showFilters ? 'rotate-180' : ''}`} />
            </motion.button>
          </div>

          {/* Filter Panel */}
          <AnimatePresence>
            {showFilters && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.3 }}
                className="mt-6 pt-6 border-t border-gray-700"
              >
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  {/* Genre Filter */}
                  <div>
                    <label className="form-label">Genre</label>
                    <select
                      value={filters.genre}
                      onChange={(e) => handleFilterChange('genre', e.target.value)}
                      className="input-field"
                    >
                      <option value="">All Genres</option>
                      {genreOptions.map(genre => (
                        <option key={genre} value={genre}>{genre}</option>
                      ))}
                    </select>
                  </div>

                  {/* Year Filter */}
                  <div>
                    <label className="form-label">Year</label>
                    <select
                      value={filters.year}
                      onChange={(e) => handleFilterChange('year', e.target.value)}
                      className="input-field"
                    >
                      <option value="">All Years</option>
                      {yearOptions.map(year => (
                        <option key={year} value={year}>{year}</option>
                      ))}
                    </select>
                  </div>

                  {/* Rating Filter */}
                  <div>
                    <label className="form-label">Min Rating</label>
                    <select
                      value={filters.rating}
                      onChange={(e) => handleFilterChange('rating', e.target.value)}
                      className="input-field"
                    >
                      <option value="">All Ratings</option>
                      <option value="4">4.0+</option>
                      <option value="3">3.0+</option>
                      <option value="2">2.0+</option>
                    </select>
                  </div>

                  {/* Runtime Filter */}
                  <div>
                    <label className="form-label">Runtime</label>
                    <select
                      value={filters.runtime}
                      onChange={(e) => handleFilterChange('runtime', e.target.value)}
                      className="input-field"
                    >
                      <option value="">All Runtimes</option>
                      <option value="90">Under 90 min</option>
                      <option value="120">90-120 min</option>
                      <option value="150">120-150 min</option>
                      <option value="999">Over 150 min</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end mt-4 space-x-2">
                  <button
                    onClick={clearFilters}
                    className="btn-ghost flex items-center space-x-2"
                  >
                    <X className="w-4 h-4" />
                    <span>Clear Filters</span>
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        {/* Movie List */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          {viewMode === 'grid' ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
              {movies.map((movie, index) => (
                <motion.div
                  key={movie.id}
                  initial={{ opacity: 0, y: 30 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: index * 0.05 }}
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
                        <button className="p-2 bg-white/20 backdrop-blur-sm rounded-full text-white hover:bg-white/30 transition-colors">
                          <Heart className="w-4 h-4" />
                        </button>
                      </div>
                      <div className="absolute bottom-4 left-4 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                        <div className="flex items-center space-x-1 bg-black/50 backdrop-blur-sm rounded-full px-3 py-1">
                          <Star className="w-3 h-3 text-yellow-400 fill-current" />
                          <span className="text-white text-sm font-medium">{movie.average_rating?.toFixed(1) || 'N/A'}</span>
                        </div>
                      </div>
                    </div>
                    
                    <div className="p-6">
                      <h3 className="text-lg font-bold text-white mb-2 group-hover:text-blue-400 transition-colors line-clamp-2">
                        {movie.title}
                      </h3>
                      <p className="text-gray-400 text-sm mb-4 line-clamp-2">
                        {movie.description}
                      </p>
                      
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center space-x-2 text-gray-400">
                          <Calendar className="w-4 h-4" />
                          <span>{movie.year}</span>
                        </div>
                        <div className="flex items-center space-x-2 text-gray-400">
                          <Clock className="w-4 h-4" />
                          <span>{movie.runtime} min</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              {movies.map((movie, index) => (
                <motion.div
                  key={movie.id}
                  initial={{ opacity: 0, x: -30 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.5, delay: index * 0.05 }}
                  whileHover={{ scale: 1.02 }}
                  className="card group cursor-pointer"
                  onClick={() => handleMovieClick(movie.id)}
                >
                  <div className="flex space-x-6">
                    <div className="relative overflow-hidden rounded-xl flex-shrink-0">
                      <img
                        src={movie.poster_url || '/api/placeholder/150/200'}
                        alt={movie.title}
                        className="w-32 h-48 object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between mb-2">
                        <h3 className="text-xl font-bold text-white group-hover:text-blue-400 transition-colors">
                          {movie.title}
                        </h3>
                        <div className="flex items-center space-x-1 bg-yellow-500/20 rounded-full px-2 py-1">
                          <Star className="w-4 h-4 text-yellow-400 fill-current" />
                          <span className="text-yellow-400 font-semibold text-sm">{movie.average_rating?.toFixed(1) || 'N/A'}</span>
                        </div>
                      </div>
                      
                      <p className="text-gray-400 mb-4 line-clamp-3">
                        {movie.description}
                      </p>
                      
                      <div className="flex items-center space-x-6 text-sm text-gray-400">
                        <div className="flex items-center space-x-1">
                          <Calendar className="w-4 h-4" />
                          <span>{movie.year}</span>
                        </div>
                        <div className="flex items-center space-x-1">
                          <Clock className="w-4 h-4" />
                          <span>{movie.runtime} min</span>
                        </div>
                        <div className="flex items-center space-x-1">
                          <Award className="w-4 h-4" />
                          <span>{movie.director}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>

        {/* Pagination */}
        {totalPages > 1 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="flex justify-center mt-12"
          >
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-3 py-2 rounded-lg font-medium bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Prev
              </button>

              {buildPagination(currentPage, totalPages).map((item, idx) => (
                typeof item === 'string' ? (
                  <span key={`ellipsis-${idx}`} className="px-2 text-gray-400">...</span>
                ) : (
                  <button
                    key={item}
                    onClick={() => setCurrentPage(item)}
                    className={`px-4 py-2 rounded-lg font-medium transition-all duration-300 ${
                      currentPage === item
                        ? 'bg-blue-600 text-white shadow-lg'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white'
                    }`}
                  >
                    {item}
                  </button>
                )
              ))}

              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-3 py-2 rounded-lg font-medium bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </motion.div>
        )}

        {/* Empty State */}
        {movies.length === 0 && !loading && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-center py-16"
          >
            <div className="w-24 h-24 bg-gray-700 rounded-full flex items-center justify-center mx-auto mb-6">
              <Film className="w-12 h-12 text-gray-400" />
            </div>
            <h3 className="text-2xl font-bold text-white mb-2">No Movies Found</h3>
            <p className="text-gray-400 mb-6">Try adjusting your search criteria or filters</p>
            <button
              onClick={clearFilters}
              className="btn-primary"
            >
              Clear Filters
            </button>
          </motion.div>
        )}
      </div>
    </div>
  )
}

export default MovieList