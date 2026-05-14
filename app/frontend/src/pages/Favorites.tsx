import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Heart, Grid, List, Search, Play, X } from 'lucide-react'
import { movieApi } from '../services/api'
import type { Movie } from '../services/api'
import LoadingSpinner from '../components/LoadingSpinner'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

const Favorites = () => {
  const refreshUserProfile = useAuthStore((state) => state.refreshUserProfile)
  const navigate = useNavigate()
  const [favorites, setFavorites] = useState<Movie[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')

  useEffect(() => {
    loadFavorites()
  }, [])

  const loadFavorites = async () => {
    try {
      setIsLoading(true)
      const data = await movieApi.getFavorites()
      setFavorites(data)
    } catch (error) {
      toast.error('Failed to load favorites list')
    } finally {
      setIsLoading(false)
    }
  }

  // English comment: Remove the favorite immediately and let profile totals catch up in the background.
  const handleRemoveFavorite = async (movieId: number) => {
    try {
      await movieApi.toggleFavorite(movieId)
      setFavorites(prev => prev.filter(movie => movie.id !== movieId))
      toast.success('Removed from favorites')
      // English comment: Keep the interaction snappy by not blocking on profile recomputation.
      void refreshUserProfile()
    } catch (error) {
      toast.error('Failed to remove from favorites')
    }
  }

  const filteredFavorites = favorites.filter(movie =>
    movie.title.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const totalFavorites = favorites.length
  const ratedFavorites = favorites.filter(m => m.average_rating > 0).length
  const averageFavoriteRating = totalFavorites
    ? (favorites.reduce((sum, m) => sum + (m.average_rating || 0), 0) / totalFavorites).toFixed(1)
    : '0.0'

  const genreCountMap = new Map<string, number>()
  favorites.forEach(movie => {
    movie.genres?.forEach((genre: any) => {
      const name = typeof genre === 'string' ? genre : genre?.name
      if (!name) return
      genreCountMap.set(name, (genreCountMap.get(name) || 0) + 1)
    })
  })
  const topGenres = Array.from(genreCountMap.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
  const genreDiversity = genreCountMap.size

  if (isLoading) {
    return <LoadingSpinner message="Loading favorites..." />
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-black text-white">
      <div className="max-w-7xl mx-auto px-4 py-10 space-y-10">
        {/* Hero */}
        <motion.section
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-rose-600/40 via-fuchsia-700/30 to-indigo-900/40 p-10 shadow-[0_25px_60px_-20px_rgba(0,0,0,0.9)]"
        >
          <div className="absolute -right-16 -top-16 w-64 h-64 bg-rose-500/30 blur-3xl" />
          <div className="absolute -left-20 -bottom-12 w-72 h-72 bg-indigo-500/20 blur-[120px]" />
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="inline-flex items-center gap-3 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm uppercase tracking-[0.3em] text-white/80">
                <Heart className="h-4 w-4 text-rose-200" /> Premium Collection
              </div>
              <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-5xl">
                My Private Cinema<span className="text-rose-200">.</span>
              </h1>
              <p className="mt-4 max-w-2xl text-lg text-white/80">
                Your personal vault of favorites. Come back anytime to reconnect with what you truly enjoy.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4 rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-white/60">Favorites</p>
                <p className="mt-2 text-3xl font-semibold">{totalFavorites}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-white/60">Avg rating</p>
                <p className="mt-2 text-3xl font-semibold">{averageFavoriteRating}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-white/60">Rated</p>
                <p className="mt-2 text-3xl font-semibold">{ratedFavorites}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-white/60">Genre diversity</p>
                <p className="mt-2 text-3xl font-semibold">{genreDiversity}</p>
              </div>
            </div>
          </div>
        </motion.section>

        {/* 控制面板 */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-2xl border border-white/10 bg-white/5 p-6 backdrop-blur"
        >
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-white/50" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search saved movies, directors, or keywords"
                className="w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-12 pr-4 text-white placeholder:text-white/40 focus:border-rose-400/60 focus:outline-none focus:ring-0"
              />
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-white/60">{filteredFavorites.length} movies</span>
              <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 p-1">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    viewMode === 'grid' ? 'bg-white text-black shadow-lg' : 'text-white/70'
                  }`}
                >
                  <Grid className="inline h-4 w-4" />
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    viewMode === 'list' ? 'bg-white text-black shadow-lg' : 'text-white/70'
                  }`}
                >
                  <List className="inline h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          {topGenres.length > 0 && (
            <div className="mt-6 flex flex-wrap items-center gap-3 text-sm text-white/70">
              <span className="text-xs uppercase tracking-[0.4em] text-white/40">Top genres</span>
              {topGenres.map(([genre, count]) => (
                <span
                  key={genre}
                  className="rounded-full border border-white/20 bg-white/10 px-4 py-1 text-white/80"
                >
                  {genre} · {count}
                </span>
              ))}
            </div>
          )}
        </motion.section>

        {/* 收藏列表 */}
        <section>
          {filteredFavorites.length > 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.15 }}
              className={
                viewMode === 'grid'
                  ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6'
                  : 'space-y-4'
              }
            >
              {filteredFavorites.map((movie, index) => {
                const displayGenres =
                  movie.genres
                    ?.slice(0, 2)
                    .map((genre: any) => (typeof genre === 'string' ? genre : genre?.name))
                    .filter(Boolean) ?? []

                return (
                  <motion.div
                    key={movie.id}
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.04 }}
                    className="group relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 shadow-[0_15px_45px_-25px_rgba(0,0,0,0.8)]"
                  >
                    <div className="relative aspect-[2/3] w-full overflow-hidden">
                      {movie.poster_url ? (
                        <img
                          src={movie.poster_url}
                          alt={movie.title}
                          className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
                          loading="lazy"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-slate-800 to-slate-900 text-white/30">
                          <Heart className="h-10 w-10" />
                        </div>
                      )}

                      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />

                      {movie.average_rating ? (
                        <div className="absolute top-4 right-4 rounded-full border border-white/20 bg-black/40 px-3 py-1 text-xs font-semibold text-white backdrop-blur">
                          ⭐ {movie.average_rating.toFixed(1)}
                        </div>
                      ) : null}

                      <div className="absolute bottom-4 left-4 right-4 space-y-2">
                        <p className="text-lg font-semibold leading-tight">{movie.title}</p>
                        <p className="text-sm text-white/70">
                          {movie.year && <span>{movie.year}</span>}
                          {movie.year && displayGenres.length > 0 && (
                            <span className="mx-2 text-white/40">•</span>
                          )}
                          {displayGenres.join(', ')}
                        </p>
                        <div className="flex flex-wrap gap-3 pt-2">
                          <button
                            onClick={() => navigate(`/movies/${movie.id}`)}
                            className="inline-flex items-center gap-2 rounded-full bg-white/90 px-4 py-2 text-xs font-semibold text-black shadow-lg transition hover:bg-white"
                          >
                            <Play className="h-4 w-4" />
                            View details
                          </button>
                          <button
                            onClick={() => handleRemoveFavorite(movie.id)}
                            className="inline-flex items-center gap-2 rounded-full border border-white/40 bg-black/30 px-4 py-2 text-xs font-semibold text-white/80 transition hover:border-rose-400 hover:text-rose-200"
                          >
                            <X className="h-4 w-4" />
                            Remove
                          </button>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )
              })}
            </motion.div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="rounded-3xl border border-dashed border-white/20 bg-white/5 p-12 text-center"
            >
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-2xl border border-white/10 bg-white/10">
                <Heart className="h-10 w-10 text-white/50" />
              </div>
              <h3 className="mt-6 text-2xl font-semibold">No favorites yet</h3>
              <p className="mt-2 text-white/60">
                {searchTerm ? 'Try adjusting your search.' : 'Tap the heart on a movie to start your private list.'}
              </p>
              {!searchTerm && (
                <a
                  href="/movies"
                  className="mt-6 inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold text-black transition hover:bg-rose-100"
                >
                  <span>Browse movies</span>
                </a>
              )}
            </motion.div>
          )}
        </section>

        {/* 統計 */}
        {favorites.length > 0 && (
          <motion.section
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="rounded-3xl border border-white/10 bg-gradient-to-br from-indigo-900/60 via-slate-900/50 to-black/60 p-8 backdrop-blur"
          >
            <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.4em] text-white/40">Overview</p>
                <h2 className="mt-3 text-2xl font-semibold">Favorites Intelligence</h2>
                <p className="mt-2 text-white/70">
                  We track your favorite patterns so GNN + KG can understand you better over time.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-center">
                  <p className="text-sm uppercase tracking-[0.2em] text-white/50">Total</p>
                  <p className="mt-2 text-2xl font-semibold">{totalFavorites}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-center">
                  <p className="text-sm uppercase tracking-[0.2em] text-white/50">Rated</p>
                  <p className="mt-2 text-2xl font-semibold">{ratedFavorites}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-center">
                  <p className="text-sm uppercase tracking-[0.2em] text-white/50">Avg rating</p>
                  <p className="mt-2 text-2xl font-semibold">{averageFavoriteRating}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-center">
                  <p className="text-sm uppercase tracking-[0.2em] text-white/50">Genre coverage</p>
                  <p className="mt-2 text-2xl font-semibold">{genreDiversity}</p>
                </div>
              </div>
            </div>
          </motion.section>
        )}
      </div>
    </div>
  )
}

export default Favorites
