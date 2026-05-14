import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ThumbsUp, Grid, List, Search, Play, X } from 'lucide-react'
import { movieApi } from '../services/api'
import type { Movie } from '../services/api'
import LoadingSpinner from '../components/LoadingSpinner'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

const Likes = () => {
  const refreshUserProfile = useAuthStore((state) => state.refreshUserProfile)
  const navigate = useNavigate()
  const [likes, setLikes] = useState<Movie[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')

  useEffect(() => {
    loadLikes()
  }, [])

  const loadLikes = async () => {
    try {
      setIsLoading(true)
      const data = await movieApi.getLikes()
      setLikes(data)
    } catch {
      toast.error('Failed to load liked movies')
    } finally {
      setIsLoading(false)
    }
  }

  // English comment: Remove the like immediately and let profile totals catch up in the background.
  const handleRemoveLike = async (movieId: number) => {
    try {
      await movieApi.toggleLike(movieId)
      setLikes(prev => prev.filter(movie => movie.id !== movieId))
      toast.success('Removed from likes')
      void refreshUserProfile()
    } catch {
      toast.error('Failed to remove like')
    }
  }

  const filteredLikes = likes.filter(movie =>
    movie.title.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const totalLikes = likes.length
  const averageLikeRating = totalLikes
    ? (likes.reduce((sum, m) => sum + (m.average_rating || 0), 0) / totalLikes).toFixed(1)
    : '0.0'

  if (isLoading) {
    return <LoadingSpinner message="Loading likes..." />
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-cyan-950 to-black text-white">
      <div className="max-w-7xl mx-auto px-4 py-10 space-y-10">
        <motion.section
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-cyan-600/40 via-blue-700/30 to-slate-900/40 p-10 shadow-[0_25px_60px_-20px_rgba(0,0,0,0.9)]"
        >
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="inline-flex items-center gap-3 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm uppercase tracking-[0.3em] text-white/80">
                <ThumbsUp className="h-4 w-4 text-cyan-200" /> Quick Approval
              </div>
              <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-5xl">
                Movies I Like<span className="text-cyan-200">.</span>
              </h1>
              <p className="mt-4 max-w-2xl text-lg text-white/80">
                Your lightweight signal list — fast likes that help the recommender understand your taste.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4 rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-white/60">Liked movies</p>
                <p className="mt-2 text-3xl font-semibold">{totalLikes}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-white/60">Avg rating</p>
                <p className="mt-2 text-3xl font-semibold">{averageLikeRating}</p>
              </div>
            </div>
          </div>
        </motion.section>

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
                placeholder="Search liked movies"
                className="w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-12 pr-4 text-white placeholder:text-white/40 focus:border-cyan-400/60 focus:outline-none focus:ring-0"
              />
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-white/60">{filteredLikes.length} movies</span>
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
        </motion.section>

        <section>
          {filteredLikes.length > 0 ? (
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
              {filteredLikes.map((movie, index) => (
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
                        <ThumbsUp className="h-10 w-10" />
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
                      <p className="text-sm text-white/70">{movie.year || 'Unknown year'}</p>
                      <div className="flex flex-wrap gap-3 pt-2">
                        <button
                          onClick={() => navigate(`/movies/${movie.id}`)}
                          className="inline-flex items-center gap-2 rounded-full bg-white/90 px-4 py-2 text-xs font-semibold text-black shadow-lg transition hover:bg-white"
                        >
                          <Play className="h-4 w-4" />
                          View details
                        </button>
                        <button
                          onClick={() => handleRemoveLike(movie.id)}
                          className="inline-flex items-center gap-2 rounded-full border border-white/40 bg-black/30 px-4 py-2 text-xs font-semibold text-white/80 transition hover:border-cyan-400 hover:text-cyan-200"
                        >
                          <X className="h-4 w-4" />
                          Remove
                        </button>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="rounded-3xl border border-dashed border-white/20 bg-white/5 p-12 text-center"
            >
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-2xl border border-white/10 bg-white/10">
                <ThumbsUp className="h-10 w-10 text-white/50" />
              </div>
              <h3 className="mt-6 text-2xl font-semibold">No liked movies yet</h3>
              <p className="mt-2 text-white/60">
                {searchTerm ? 'Try adjusting your search.' : 'Tap like on a movie and it will appear here.'}
              </p>
              {!searchTerm && (
                <a
                  href="/movies"
                  className="mt-6 inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold text-black transition hover:bg-cyan-100"
                >
                  <span>Browse movies</span>
                </a>
              )}
            </motion.div>
          )}
        </section>
      </div>
    </div>
  )
}

export default Likes
