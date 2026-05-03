import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Sparkles, TrendingUp, Zap, Search, Star, MessageSquare, X, Send, Copy, Pin, PinOff, Heart } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { kgRecommendApi, llmApi, movieApi } from '../services/api'
import type { Movie } from '../services/api'
import toast from 'react-hot-toast'
// import MovieCard from '../components/MovieCard'

type RecommendationMethod = 'kg-rag' | 'enhanced-hybrid'

type RecommendationMovie = Movie & {
  reason?: string
  reason_details?: string[]
  kg_score?: number
  combined_score?: number
  ann_score?: number
  gnn_score?: number
}

type ChatMessage = {
  role: 'user' | 'assistant'
  movieId: number
  content: string
  createdAt: number
}

const EnhancedRecommendations = () => {
  const [recommendations, setRecommendations] = useState<RecommendationMovie[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [method, setMethod] = useState<RecommendationMethod>('enhanced-hybrid')
  const [queryText, setQueryText] = useState('')
  const [qaQuestion, setQaQuestion] = useState('Why should I watch this movie? Please give me 3 key points.')
  const [qaLoadingMovieId, setQaLoadingMovieId] = useState<number | null>(null)
  const [qaAnswers, setQaAnswers] = useState<Record<number, string>>({})
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatSidebarOpen, setChatSidebarOpen] = useState(false)
  const [chatSidebarWide, setChatSidebarWide] = useState(false)
  const [selectedQaMovieId, setSelectedQaMovieId] = useState<number | null>(null)
  const [pinnedQaMovieId, setPinnedQaMovieId] = useState<number | null>(null)
  const [answerLanguage, setAnswerLanguage] = useState<'zh' | 'en'>('zh')
  const [answerStyle, setAnswerStyle] = useState<'brief' | 'detailed'>('brief')
  const [genreFilter, setGenreFilter] = useState('all')
  const [minYearFilter, setMinYearFilter] = useState('')
  const [minRatingFilter, setMinRatingFilter] = useState('')
  const navigate = useNavigate()

  const fetchRecommendations = async () => {
    setLoading(true)
    setError(null)
    
    try {
      let raw: any
      
      if (method === 'enhanced-hybrid') {
        raw = await kgRecommendApi.getEnhancedHybrid(10, queryText || undefined)
      } else {
        raw = await kgRecommendApi.getKgRag(10)
      }

      const data: RecommendationMovie[] = Array.isArray(raw)
        ? raw
        : Array.isArray(raw?.recommendations)
          ? raw.recommendations
          : []

      const normalized = (data as any[]).map((item) => {
        const reason = item.reason ?? item.explanation ?? ''
        const reasonDetails = Array.isArray(item.reason_details)
          ? item.reason_details
          : reason
            ? [reason]
            : []

        return {
          ...item,
          id: item.id ?? item.movie_id,
          ann_score: item.ann_score ?? 0,
          kg_score: item.kg_score ?? 0,
          gnn_score: item.gnn_score ?? 0,
          combined_score: item.combined_score ?? 0,
          reason,
          reason_details: reasonDetails,
        }
      })
      
      setRecommendations(normalized as RecommendationMovie[])
      
      if (normalized.length === 0) {
        toast('No recommendations yet. Please rate some movies first', { icon: 'ℹ️' })
      } else {
        toast.success(`Successfully fetched ${normalized.length} recommendations`)
      }
    } catch (e: any) {
      const errorMsg = e?.response?.data?.detail || e?.message || 'Failed to fetch recommendations'
      setError(errorMsg)
      toast.error(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  const handleMovieClick = (movieId: number) => {
    navigate(`/movies/${movieId}`)
  }

  const handleAskRecommendationQA = async (movie: RecommendationMovie) => {
    try {
      setSelectedQaMovieId(movie.id)
      setChatSidebarOpen(true)
      setQaLoadingMovieId(movie.id)
      const langHint = answerLanguage === 'zh' ? '請用繁體中文回答。' : 'Please answer in English.'
      const styleHint = answerStyle === 'brief' ? 'Keep it concise in 3 bullet points.' : 'Provide a detailed explanation with evidence.'
      const userQuestion = `${(qaQuestion || '').trim() || 'Why should I watch this movie? Please give me 3 key points.'} ${langHint} ${styleHint}`

      setChatMessages((prev) => ([
        ...prev,
        { role: 'user', movieId: movie.id, content: qaQuestion || 'Why should I watch this movie?', createdAt: Date.now() },
      ]))

      const explainOptions: any = {
        question: userQuestion,
        answer_language: answerLanguage,
        evidence: movie.reason_details || (movie.reason ? [movie.reason] : []),
        scores: {
          ann: movie.ann_score,
          kg: movie.kg_score,
          gnn: movie.gnn_score,
          combined: movie.combined_score,
        },
        movie_metadata: {
          title: movie.title,
          year: movie.year,
          genres: movie.genres,
          director: movie.director,
          cast: movie.cast,
          description: movie.description,
        },
      }
      const response = await llmApi.explainRecommendation(movie.id, explainOptions)

      const answer = response?.explanation || 'No readable explanation was returned. Please try again later.'
      setQaAnswers((prev) => ({ ...prev, [movie.id]: answer }))
      setChatMessages((prev) => ([
        ...prev,
        { role: 'assistant', movieId: movie.id, content: answer, createdAt: Date.now() },
      ]))
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Failed to generate Q&A'
      toast.error(msg)
    } finally {
      setQaLoadingMovieId(null)
    }
  }

  const handleShuffleRecommendations = () => {
    setRecommendations((prev) => {
      const next = [...prev]
      for (let i = next.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[next[i], next[j]] = [next[j], next[i]]
      }
      return next
    })
  }

  const handleToggleFavorite = async (movieId: number) => {
    try {
      const res = await movieApi.toggleFavorite(movieId)
      toast.success(res?.message || 'Favorites updated')
    } catch {
      toast.error('Failed to update favorites')
    }
  }

  const handleCopySelectedAnswer = async () => {
    if (!activeQaMovieId || !qaAnswers[activeQaMovieId]) {
      toast('No answer to copy yet', { icon: 'ℹ️' })
      return
    }
    await navigator.clipboard.writeText(qaAnswers[activeQaMovieId])
    toast.success('Answer copied')
  }

  const handleClearChat = () => {
    if (!activeQaMovieId) {
      setChatMessages([])
      return
    }
    setChatMessages((prev) => prev.filter((m) => m.movieId !== activeQaMovieId))
    setQaAnswers((prev) => {
      const next = { ...prev }
      delete next[activeQaMovieId]
      return next
    })
  }

  const handleSendFromSidebar = async () => {
    if (!selectedQaMovie) {
      toast('Please select a movie first', { icon: 'ℹ️' })
      return
    }
    await handleAskRecommendationQA(selectedQaMovie)
  }

  const clampScore = (value?: number) => {
    if (value == null || Number.isNaN(value)) {
      return 0
    }
    return Math.max(0, Math.min(value, 1))
  }

  const formatScore = (value?: number) => {
    if (value == null || Number.isNaN(value)) {
      return '0.00'
    }
    return value.toFixed(2)
  }

  const activeQaMovieId = pinnedQaMovieId ?? selectedQaMovieId
  const selectedQaMovie = recommendations.find((m) => m.id === activeQaMovieId) || null
  const chatForSelectedMovie = activeQaMovieId
    ? chatMessages.filter((m) => m.movieId === activeQaMovieId)
    : []

  const genreOptions = Array.from(
    new Set(recommendations.flatMap((m) => (m.genres || []).map((g: any) => typeof g === 'string' ? g : g?.name).filter(Boolean)))
  )

  const filteredRecommendations = recommendations.filter((m) => {
    const genres = (m.genres || []).map((g: any) => typeof g === 'string' ? g : g?.name)
    const hitGenre = genreFilter === 'all' || genres.includes(genreFilter)
    const hitYear = !minYearFilter || ((m.year || 0) >= Number(minYearFilter))
    const hitRating = !minRatingFilter || ((m.average_rating || 0) >= Number(minRatingFilter))
    return hitGenre && hitYear && hitRating
  })

  useEffect(() => {
    fetchRecommendations()
  }, [method])

  return (
    <>
    <div className="max-w-7xl mx-auto px-4 py-8 text-white">
      {/* 標題和說明 */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Sparkles className="w-8 h-8 text-yellow-400" />
          <h1 className="text-3xl font-bold">Enhanced Hybrid Recommendations</h1>
        </div>
        <p className="text-gray-300 text-sm">
          An intelligent recommendation system that combines knowledge graph retrieval and vector search using dynamically updated user embeddings
        </p>
      </div>

      {/* 推薦方法選擇和查詢 */}
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          {/* 方法選擇 */}
          <div>
            <label className="block text-sm font-medium mb-2">Recommendation method</label>
            <div className="flex gap-2">
              <button
                onClick={() => setMethod('enhanced-hybrid')}
                className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  method === 'enhanced-hybrid'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                <Zap className="w-4 h-4 inline mr-2" />
                Enhanced Hybrid
              </button>
              <button
                onClick={() => setMethod('kg-rag')}
                className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  method === 'kg-rag'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                <TrendingUp className="w-4 h-4 inline mr-2" />
                KG-RAG Recommendations
              </button>
            </div>
          </div>

          {/* 查詢輸入 */}
          <div>
            <label className="block text-sm font-medium mb-2">Query text (optional)</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                placeholder="e.g., action movie, sci-fi..."
                className="flex-1 px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <button
                onClick={fetchRecommendations}
                disabled={loading}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 flex items-center gap-2"
              >
                <Search className="w-4 h-4" />
                Search
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-indigo-400/30 bg-indigo-500/10 p-4 mb-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium">Recommendation Q&A (LLM)</div>
            <div className="text-xs text-gray-300 mt-1">Open the Q&A sidebar: ask questions and view answers on the right</div>
          </div>
          <button
            onClick={() => setChatSidebarOpen(true)}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm inline-flex items-center gap-2"
          >
            <MessageSquare className="w-4 h-4" />
            Open Q&A sidebar
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          <select
            value={genreFilter}
            onChange={(e) => setGenreFilter(e.target.value)}
            className="px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white"
            style={{ colorScheme: 'dark' }}
          >
            <option value="all" className="bg-slate-900 text-white">All genres</option>
            {genreOptions.map((g) => (
              <option key={g} value={g} className="bg-slate-900 text-white">{g}</option>
            ))}
          </select>
          <input
            type="number"
            value={minYearFilter}
            onChange={(e) => setMinYearFilter(e.target.value)}
            placeholder="Minimum year, e.g. 2018"
            className="px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400"
          />
          <input
            type="number"
            step="0.1"
            min="0"
            max="5"
            value={minRatingFilter}
            onChange={(e) => setMinRatingFilter(e.target.value)}
            placeholder="Minimum rating, e.g. 4.0"
            className="px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400"
          />
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <button onClick={handleShuffleRecommendations} className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-sm">Shuffle (local reorder)</button>
          <button onClick={() => { setGenreFilter('all'); setMinYearFilter(''); setMinRatingFilter('') }} className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-sm">Clear filters</button>
        </div>

        {/* 方法說明 */}
        <div className="text-xs text-gray-400 space-y-1">
          {method === 'enhanced-hybrid' ? (
            <>
              <p>✨ <strong>Enhanced Hybrid Recommendations</strong>: combines Neo4j graph retrieval and FAISS ANN retrieval using dynamically updated user embeddings</p>
              <p>• Graph retrieval: relation search based on the knowledge graph</p>
              <p>• ANN retrieval: vector similarity search based on user embeddings</p>
              <p>• Fusion strategy: weighted fusion of both retrieval results</p>
            </>
          ) : (
            <>
              <p>📊 <strong>KG-RAG Recommendations</strong>: recommendations based on the knowledge graph, including subgraph indexing and adaptive retrieval</p>
              <p>• Subgraph indexing: pre-extract movie-related knowledge graph subgraphs</p>
              <p>• Adaptive retrieval: choose a retrieval strategy based on user context</p>
              <p>• LLM explanation: use a large language model to generate recommendation explanations</p>
            </>
          )}
        </div>
      </div>

      {/* 錯誤提示 */}
      {error && (
        <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-4 mb-6 text-red-200">
          <p className="font-medium">Error</p>
          <p className="text-sm mt-1">{error}</p>
        </div>
      )}

      {/* 推薦結果 */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="loading-spinner mx-auto mb-4"></div>
            <p className="text-gray-400">Generating recommendations...</p>
          </div>
        </div>
      ) : filteredRecommendations.length > 0 ? (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold">Recommendation results ({filteredRecommendations.length})</h2>
            <button
              onClick={fetchRecommendations}
              className="px-4 py-2 text-sm rounded-lg bg-white/10 hover:bg-white/20"
            >
              Refresh recommendations
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredRecommendations.map((movie, index) => (
              <motion.div
                key={`movie-${movie.id}-${index}`}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                className="rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/60 via-indigo-900/40 to-slate-900/20 overflow-hidden shadow-[0_20px_60px_-30px_rgba(0,0,0,0.8)] hover:border-white/20 transition-all"
              >
                <div className="relative aspect-[16/9] w-full overflow-hidden">
                  {movie.poster_url ? (
                    <img
                      src={movie.poster_url}
                      alt={movie.title}
                      className="h-full w-full object-cover transition duration-500 hover:scale-105"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-slate-800 to-slate-900 text-white/30">
                      <Sparkles className="h-10 w-10" />
                    </div>
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
                  <div className="absolute bottom-3 left-4 right-4 flex flex-wrap items-center gap-3 text-xs text-white/80">
                    {movie.genres?.slice(0, 3).map((genre, i) => (
                      <span key={i} className="rounded-full border border-white/20 bg-white/10 px-3 py-1">
                        {typeof genre === 'string' ? genre : (genre as any).name || String(genre)}
                      </span>
                    ))}
                  </div>
                </div>

                {/* 可點擊的電影主體區域 */}
                <div
                  onClick={() => handleMovieClick(movie.id)}
                  className="p-5 cursor-pointer hover:bg-white/5 transition-all space-y-2"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-xl font-semibold tracking-tight">{movie.title}</h3>
                      {movie.year && <p className="text-sm text-gray-400">{movie.year}</p>}
                    </div>
                    {movie.average_rating && (
                      <div className="inline-flex items-center gap-1 rounded-full border border-yellow-400/40 bg-yellow-400/10 px-3 py-1 text-xs text-yellow-200">
                        <Star className="h-3.5 w-3.5" />
                        <span>{movie.average_rating.toFixed(1)}</span>
                      </div>
                    )}
                  </div>
                    {(movie.reason_details?.length || movie.reason) && (
                      <div className="mt-3 rounded-xl border border-indigo-500/30 bg-gradient-to-r from-indigo-900/30 to-purple-900/20 p-3 text-xs text-gray-200">
                        <div className="text-[10px] uppercase tracking-[0.4em] text-indigo-200">Recommendation basis</div>
                        <div className="mt-2 space-y-1">
                          {movie.reason_details?.length
                            ? movie.reason_details.map((detail, idx) => (
                                <div key={idx} className="flex items-start gap-2">
                                  <span className="text-indigo-300">•</span>
                                  <span>{detail}</span>
                                </div>
                              ))
                            : (
                              <p>{movie.reason || 'Hybrid retrieval result'}</p>
                            )
                          }
                        </div>
                      </div>
                    )}

                    <div className="mt-3 rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-3 text-xs text-gray-100 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-[10px] uppercase tracking-[0.4em] text-cyan-200">Recommendation Q&A</div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setSelectedQaMovieId(movie.id)
                            setChatSidebarOpen(true)
                          }}
                          className="px-3 py-1 rounded-md bg-cyan-700 hover:bg-cyan-600 text-white text-xs"
                        >
                          View in sidebar
                        </button>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleAskRecommendationQA(movie)
                          }}
                          disabled={qaLoadingMovieId === movie.id}
                          className="flex-1 px-3 py-2 rounded-md bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60 text-white text-xs"
                        >
                          {qaLoadingMovieId === movie.id ? 'Generating...' : 'Ask AI for reasons'}
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleToggleFavorite(movie.id)
                          }}
                          className="px-3 py-2 rounded-md bg-pink-600/80 hover:bg-pink-500 text-white text-xs inline-flex items-center gap-1"
                        >
                          <Heart className="w-3.5 h-3.5" /> Favorite
                        </button>
                      </div>
                      {qaAnswers[movie.id] && (
                        <p className="text-cyan-100/80 line-clamp-2">{qaAnswers[movie.id]}</p>
                      )}
                    </div>

                    <div className="mt-3 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-gray-200 space-y-2">
                      <div className="text-[10px] uppercase tracking-[0.4em] text-white/50">Retrieval components</div>
                      {[
                        { label: 'ANN similarity', value: movie.ann_score, color: 'from-sky-400 to-sky-500' },
                        { label: 'KG relevance', value: movie.kg_score, color: 'from-emerald-400 to-emerald-500' },
                        { label: 'GNN structural score', value: movie.gnn_score, color: 'from-purple-400 to-purple-500' },
                      ].map((signal) => (
                        <div key={signal.label} className="space-y-1">
                          <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.3em] text-white/60">
                            <span>{signal.label}</span>
                            <span>{formatScore(signal.value)}</span>
                          </div>
                          <div className="h-1.5 w-full rounded-full bg-white/10">
                            <div
                              className={`h-full rounded-full bg-gradient-to-r ${signal.color}`}
                              style={{ width: `${clampScore(signal.value) * 100}%` }}
                            />
                          </div>
                        </div>
                      ))}
                      {movie.combined_score != null && (
                        <div className="text-right text-[11px] uppercase tracking-[0.4em] text-white/60">
                          Combined score {movie.combined_score.toFixed(3)}
                        </div>
                      )}
                    </div>
                  </div>

                </motion.div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-center py-12 bg-white/5 rounded-xl border border-white/10">
          <p className="text-gray-400 mb-4">No recommendations yet</p>
          <p className="text-sm text-gray-500 mb-4">
            Please rate, like, or favorite some movies. We'll generate personalized recommendations based on your preferences
          </p>
          <button
            onClick={() => navigate('/movies')}
            className="px-6 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500"
          >
            Browse movies
          </button>
        </div>
      )}
      {/* 問答側翻欄 */}
      {chatSidebarOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={() => setChatSidebarOpen(false)}>
          <div
            className={`h-full w-full ${chatSidebarWide ? 'max-w-2xl' : 'max-w-md'} bg-slate-950 border-l border-white/10 p-5 overflow-y-auto transition-all`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-cyan-300" />
                <h3 className="text-lg font-semibold">Recommendation Q&A Sidebar</h3>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setChatSidebarWide((v) => !v)}
                  className="px-2 py-1 rounded-md bg-white/10 hover:bg-white/20 text-xs"
                >
                  {chatSidebarWide ? 'Compact' : 'Expanded'}
                </button>
                <button
                  onClick={() => setChatSidebarOpen(false)}
                  className="p-2 rounded-md bg-white/10 hover:bg-white/20"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 mb-3">
              <select
                value={answerLanguage}
                onChange={(e) => setAnswerLanguage(e.target.value as 'zh' | 'en')}
                className="px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white text-sm"
                style={{ colorScheme: 'dark' }}
              >
                <option value="zh" className="bg-slate-900 text-white">Chinese answer</option>
                <option value="en" className="bg-slate-900 text-white">English answer</option>
              </select>
              <select
                value={answerStyle}
                onChange={(e) => setAnswerStyle(e.target.value as 'brief' | 'detailed')}
                className="px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white text-sm"
                style={{ colorScheme: 'dark' }}
              >
                <option value="brief" className="bg-slate-900 text-white">Brief</option>
                <option value="detailed" className="bg-slate-900 text-white">Detailed</option>
              </select>
            </div>

            <div className="space-y-3">
              <label className="text-sm text-gray-300">Your question (Enter to send, Shift+Enter for a new line)</label>
              <textarea
                value={qaQuestion}
                onChange={(e) => setQaQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSendFromSidebar()
                  }
                }}
                rows={3}
                placeholder="e.g., How is this movie related to what I've watched recently?"
                className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none"
              />
            </div>

            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-xs uppercase tracking-[0.35em] text-white/50">Selected movie</div>
                <button
                  onClick={() => setPinnedQaMovieId((prev) => (prev ? null : selectedQaMovie?.id || null))}
                  className="px-2 py-1 rounded-md bg-white/10 hover:bg-white/20 text-xs inline-flex items-center gap-1"
                >
                  {pinnedQaMovieId ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
                  {pinnedQaMovieId ? 'Unpin' : 'Pin movie'}
                </button>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/5 p-3">
                <div className="font-medium">{selectedQaMovie?.title || 'Select a movie card, then click "View in sidebar".'}</div>
                {selectedQaMovie?.year && <div className="text-sm text-gray-400 mt-1">{selectedQaMovie.year}</div>}
              </div>
            </div>

            <div className="mt-4 flex items-center gap-2">
              <button
                onClick={handleSendFromSidebar}
                disabled={!selectedQaMovie || qaLoadingMovieId === selectedQaMovie.id}
                className="flex-1 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60 inline-flex items-center justify-center gap-2"
              >
                <Send className="w-4 h-4" />
                {selectedQaMovie && qaLoadingMovieId === selectedQaMovie.id ? 'Generating...' : 'Send Q&A'}
              </button>
              <button onClick={handleCopySelectedAnswer} className="px-3 py-2 rounded-lg bg-white/10 hover:bg-white/20">
                <Copy className="w-4 h-4" />
              </button>
              <button onClick={handleClearChat} className="px-3 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-xs">Clear</button>
            </div>

            <div className="mt-5">
              <div className="text-xs uppercase tracking-[0.35em] text-white/50 mb-2">Conversation</div>
              <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-3 min-h-56 text-sm text-cyan-50 space-y-2">
                {chatForSelectedMovie.length > 0 ? (
                  chatForSelectedMovie.map((msg) => (
                    <div key={`${msg.createdAt}-${msg.role}`} className={`rounded-lg px-3 py-2 ${msg.role === 'user' ? 'bg-white/15 ml-10' : 'bg-cyan-900/40 mr-10'}`}>
                      <div className="text-[10px] uppercase tracking-[0.2em] text-white/60 mb-1">{msg.role === 'user' ? 'You' : 'AI'}</div>
                      <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                    </div>
                  ))
                ) : (
                  <p>Q&A recommendation explanations will appear here.</p>
                )}
              </div>
            </div>

            {selectedQaMovie?.reason_details?.length ? (
              <div className="mt-4">
                <div className="text-xs uppercase tracking-[0.35em] text-white/50 mb-2">Evidence / Citations</div>
                <div className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-1 text-xs text-gray-200">
                  {selectedQaMovie.reason_details.slice(0, 4).map((d, idx) => (
                    <div key={idx}>E{idx + 1}. {d}</div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>

    </>
  )
}

export default EnhancedRecommendations

