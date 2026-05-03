import axios from 'axios'
import toast from 'react-hot-toast'

// 创建axios实例
export const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 从localStorage获取token
    const token = localStorage.getItem('auth-storage')
    if (token) {
      try {
        const authData = JSON.parse(token)
        if (authData.state?.token) {
          config.headers.Authorization = `Bearer ${authData.state.token}`
        }
      } catch (error) {
        console.error('Error parsing auth token:', error)
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response?.status === 401) {
      // 未授权，清除本地存储并重定向到登录页
      localStorage.removeItem('auth-storage')
      window.location.href = '/login'
    } else if (error.response?.status >= 500) {
      toast.error('Server error, please try again later')
    } else if (error.response?.data?.detail) {
      toast.error(error.response.data.detail)
    } else {
      toast.error('Request failed, please check your network connection')
    }
    return Promise.reject(error)
  }
)

// API接口类型定义
export interface Movie {
  id: number
  title: string  // 電影標題
  year?: number  // 年份
  imdb_id?: string  // IMDB ID
  poster_url?: string  // 海報圖片URL
  description?: string  // 電影描述
  director?: string  // 導演
  cast?: string  // 演員陣容
  runtime?: number  // 時長(分鐘)
  language?: string  // 語言
  country?: string  // 製作國家
  average_rating: number  // 平均評分
  rating_count: number  // 評分數量
  view_count: number  // 觀看次數
  like_count: number  // 點贊數量
  favorite_count: number  // 收藏數量
  genres: Genre[]
}

export interface Genre {
  id: number
  name: string
}

export interface User {
  id: number
  username: string
  email: string
  age?: number
  gender?: string
  occupation?: string
}

export interface UserProfile {
  id: number
  user_id: number
  preferred_genres?: string[]
  preferred_directors?: string[]
  preferred_actors?: string[]
  preferred_languages?: string[]
  preferred_countries?: string[]
  min_rating_threshold: number
  max_runtime?: number
  min_runtime?: number
  total_ratings: number
  average_rating_given: number
  most_rated_year?: number
  total_likes: number
  total_favorites: number
  total_views: number
  profile_setup_completed: boolean
  setup_skipped: boolean
  setup_completed_at?: string
  created_at: string
  updated_at: string
}

export interface Rating {
  id: number
  user_id: number
  movie_id: number
  rating: number
  created_at: string
}

export interface Comment {
  id: number
  user_id: number
  movie_id: number
  content: string
  rating?: number
  created_at: string
  updated_at?: string
  user_username: string
  movie_title: string
  movie_year?: number
  user_rating?: number
}

export interface RecommendationRequest {
  type: 'collaborative' | 'content' | 'hybrid'
  limit?: number
}

export interface ChatRequest {
  message: string
}

export interface ChatResponse {
  response: string
  user_id: number
}

// API方法
export const movieApi = {
  // 获取电影列表
  getMovies: async (params?: {
    skip?: number
    limit?: number
    search?: string
    genre?: string
    year?: number
    min_rating?: number
    runtime_min?: number
    runtime_max?: number
    sort_by?: 'rating' | 'popularity' | 'year' | 'title'
  }) => {
    const response = await api.get('/movies', { params })
    return response.data
  },

  getMovieCount: async (params?: {
    search?: string
    genre?: string
    year?: number
    min_rating?: number
    runtime_min?: number
    runtime_max?: number
  }) => {
    const response = await api.get('/movies/count', { params })
    return response.data
  },

  getMovieSuggestions: async (query: string, limit: number = 8) => {
    const response = await api.get('/movies/suggestions', { params: { query, limit } })
    return response.data as Array<{ id: number; title: string; year?: number }>
  },

  // 获取电影详情
  getMovie: async (id: number) => {
    const response = await api.get(`/movies/${id}`)
    return response.data
  },

  // 获取热门电影
  getPopularMovies: async (limit: number = 10) => {
    const response = await api.get('/movies/popular', { params: { limit } })
    return response.data
  },

  // 评分电影
  rateMovie: async (movieId: number, rating: number) => {
    const response = await api.post('/ratings', { movie_id: movieId, rating })
    return response.data
  },

  // 添加评论
  addReview: async (movieId: number, content: string, rating?: number) => {
    // 對齊後端 /api/comments/ 路由
    const response = await api.post('/comments/', { movie_id: movieId, content, rating })
    return response.data
  },

  // 切换收藏状态
  toggleFavorite: async (movieId: number) => {
    const response = await api.post(`/favorites/${movieId}`)
    return response.data
  },

  // 获取收藏列表
  getFavorites: async () => {
    const response = await api.get('/favorites')
    return response.data
  },

  // 获取点赞列表
  getLikes: async () => {
    const response = await api.get('/likes')
    return response.data
  },

  // 切换点赞状态
  toggleLike: async (movieId: number) => {
    const response = await api.post(`/likes/${movieId}`)
    return response.data
  },

  // 获取点赞状态
  getLikeStatus: async (movieId: number) => {
    const response = await api.get(`/likes/${movieId}`)
    return response.data
  },

  // 获取用户对电影的评分
  getUserRating: async (movieId: number) => {
    const response = await api.get(`/ratings/${movieId}`)
    return response.data
  },

  // Get movie status (favorite and like status)
  getMovieStatus: async (movieId: number) => {
    const response = await api.get(`/movies/${movieId}/status`)
    return response.data
  }
}

// 傳統推薦端點已移除，改用下方 KG 推薦 API

// KG-augmented recommendations (backend: /api/recommend/with-kg)
export const kgRecommendApi = {
  // Fetch top-K movie ids with score and reason (requires auth token)
  getWithKg: async (k: number = 6): Promise<Array<{ movie_id: number; score: number; reason: string }>> => {
    const response = await api.get('/recommend/with-kg', { params: { k } })
    return response.data
  },
  
  // Advanced KG-RAG recommendations with subgraph indexing and adaptive retrieval
  getKgRag: async (k: number = 10): Promise<Movie[]> => {
    const response = await api.get('/recommend/kg-rag', { params: { k } })
    return response.data
  },
  
  // Enhanced hybrid recommendations with ANN + KG integration and user embeddings
  getEnhancedHybrid: async (k: number = 10, queryText?: string): Promise<Movie[]> => {
    const params: any = { k }
    if (queryText) {
      params.query_text = queryText
    }
    const response = await api.get('/recommend/enhanced-hybrid', { params })
    return response.data
  },
  
  // Get user context analysis for debugging
  getUserContext: async (): Promise<any> => {
    const response = await api.get('/recommend/kg-rag/context')
    return response.data
  }
}

// Full K-RagRec (backend: /api/k-ragrec/*)
export const kRagRecApi = {
  // 系統狀態（需後端 Neo4j 可用）
  systemStatus: async () => {
    const response = await api.get('/k-ragrec/system-status')
    return response.data
  },

  // 取得推薦（需登入）
  getRecommendations: async (num: number = 10) => {
    const response = await api.get('/k-ragrec/recommendations', { params: { num_recommendations: num } })
    return response.data
  },

  // 取得用戶上下文（需登入）
  getUserContext: async () => {
    const response = await api.get('/k-ragrec/user-context')
    return response.data
  },

  // 取得電影子圖（需登入）
  getMovieSubgraph: async (movieId: number) => {
    const response = await api.get(`/k-ragrec/movie-subgraph/${movieId}`)
    return response.data
  },

  // 生成推薦解釋（需登入）
  explainRecommendation: async (movieId: number) => {
    const response = await api.post('/k-ragrec/explain-recommendation', { movie_id: movieId })
    return response.data
  }
}

// LLM 端點 - 基於 KG 的推薦解釋
export const llmApi = {
  // 生成推薦解釋（支持問答問題）
  explainRecommendation: async (
    movieId: number,
    options?: {
      question?: string
      answer_language?: 'zh' | 'en'
      model_name?: string
      evidence?: string[]
      evidence_structured?: any
      scores?: any
      movie_metadata?: any
    }
  ) => {
    const response = await api.post('/llm/explain-recommendation', {
      movie_id: movieId,
      ...(options || {}),
    })
    return response.data
  }
}
export const authApi = {
  // 登录
  login: async (username: string, password: string) => {
    const response = await api.post('/auth/login', { username, password })
    return response.data
  },

  // 注册
  register: async (userData: {
    username: string
    email: string
    password: string
    age?: number
    gender?: string
    occupation?: string
  }) => {
    const response = await api.post('/auth/register', userData)
    return response.data
  },

  // 获取当前用户信息
  getCurrentUser: async () => {
    const response = await api.get('/auth/me')
    return response.data
  },

  // 更新当前用户基本信息
  updateCurrentUser: async (userData: {
    email?: string
    age?: number
    gender?: string
    occupation?: string
  }) => {
    const response = await api.put('/auth/me', userData)
    return response.data
  }
}

export const ratingApi = {
  // 创建或更新评分
  createOrUpdateRating: async (movieId: number, rating: number) => {
    const response = await api.post('/ratings', { movie_id: movieId, rating })
    return response.data
  },

  // 获取用户对特定电影的评分
  getUserRating: async (movieId: number) => {
    const response = await api.get(`/ratings/${movieId}`)
    return response.data
  }
}

export const profileApi = {
  // 获取用户档案
  getUserProfile: async () => {
    const response = await api.get('/profile')
    return response.data
  },

  // 更新用户档案
  updateUserProfile: async (profileData: Partial<UserProfile>) => {
    const response = await api.put('/profile', profileData)
    return response.data
  },

  // 更新用户偏好设置
  updatePreferences: async (preferences: {
    preferred_genres?: string[]
    preferred_directors?: string[]
    preferred_actors?: string[]
    preferred_languages?: string[]
    preferred_countries?: string[]
    min_rating_threshold?: number
    max_runtime?: number
    min_runtime?: number
  }) => {
    const response = await api.put('/profile/preferences', preferences)
    return response.data
  },

}

// 推薦相關API已移除

// 終極AI API
export const ultimateAIApi = {
  getSystemStatus: async () => {
    const response = await api.get('/ultimate-ai/status')
    return response.data
  },

  getUltimateRecommendations: async (query: string, userProfile: any, options: any = {}) => {
    const response = await api.post('/ultimate-ai/recommendations', {
      query,
      user_profile: userProfile,
      embedding_model: options.embedding_model || 'mini_lm',
      language_model: options.language_model || 'distilgpt2',
      n_recommendations: options.n_recommendations || 5
    })
    return response.data
  },

  getConversationalRecommendations: async (message: string, chatHistory: any[] = [], languageModel: string = 'distilgpt2') => {
    const response = await api.post('/ultimate-ai/conversational', {
      message,
      chat_history: chatHistory,
      language_model: languageModel
    })
    return response.data
  },

  analyzeSentiment: async (text: string) => {
    const response = await api.post('/ultimate-ai/analyze-sentiment', text)
    return response.data
  },

  generateSummary: async (movieData: any) => {
    const response = await api.post('/ultimate-ai/generate-summary', movieData)
    return response.data
  },

  addMoviesToKnowledgeBase: async (movies: any[], embeddingModel: string = 'mini_lm') => {
    const response = await api.post('/ultimate-ai/add-movies', {
      movies,
      embedding_model: embeddingModel
    })
    return response.data
  },

  getAvailableModels: async () => {
    const response = await api.get('/ultimate-ai/models')
    return response.data
  },

  testRecommendationSystem: async () => {
    const response = await api.post('/ultimate-ai/test-recommendation')
    return response.data
  },

  healthCheck: async () => {
    const response = await api.get('/ultimate-ai/health')
    return response.data
  }
}

// 評估 API
export const evaluationApi = {
  // 獲取評估指標
  getMetrics: async (kValues: string = "5,10,20") => {
    const response = await api.get('/evaluation/metrics', { params: { k_values: kValues } })
    return response.data
  },
  
  // 批量評估
  batchEvaluate: async (userIds: number[], kValues: string = "5,10,20") => {
    const response = await api.post('/evaluation/batch-evaluate', { user_ids: userIds, k_values: kValues })
    return response.data
  },
  
  // 獲取系統性能
  getSystemPerformance: async () => {
    const response = await api.get('/evaluation/system-performance')
    return response.data
  },
  
  // 對比推薦方法
  compareMethods: async (k: number = 10) => {
    const response = await api.get('/evaluation/compare-methods', { params: { k } })
    return response.data
  },
  
  // 生成評估報告
  generateReport: async (userId?: number, format: string = "json") => {
    const params: any = { format }
    if (userId) {
      params.user_id = userId
    }
    const response = await api.get('/evaluation/report', { params })
    return response.data
  }
}

// 問卷 API（用戶研究）
export const questionnaireApi = {
  // 提交解釋質量評分
  submitExplanationRating: async (movieId: number, explanation: string, rating: number, feedback?: string) => {
    const response = await api.post('/questionnaire/explanation-rating', {
      movie_id: movieId,
      explanation,
      rating, // 1-5 Likert scale
      feedback
    })
    return response.data
  },
  
  // 獲取用戶的問卷記錄
  getUserRatings: async () => {
    const response = await api.get('/questionnaire/my-ratings')
    return response.data
  },
  
  // 獲取統計分析（管理員）
  getStatistics: async () => {
    const response = await api.get('/questionnaire/statistics')
    return response.data
  }
}

// 評論管理API
export const commentApi = {
  // 創建評論
  createComment: async (commentData: { movie_id: number; content: string }) => {
    const response = await api.post('/comments/', commentData)
    return response.data
  },
  
  // 獲取電影評論
  getMovieComments: async (movieId: number, page: number = 1, pageSize: number = 10, sortBy: string = 'newest') => {
    const response = await api.get(`/comments/movie/${movieId}`, {
      params: { page, page_size: pageSize, sort_by: sortBy }
    })
    return response.data
  },
  
  // 獲取用戶評論
  getUserComments: async (userId: number, page: number = 1, pageSize: number = 10) => {
    const response = await api.get(`/comments/user/${userId}`, {
      params: { page, page_size: pageSize }
    })
    return response.data
  },
  
  // 更新評論
  updateComment: async (commentId: number, content: string) => {
    const response = await api.put(`/comments/${commentId}`, { content })
    return response.data
  },
  
  // 刪除評論
  deleteComment: async (commentId: number) => {
    const response = await api.delete(`/comments/${commentId}`)
    return response.data
  },
  
  // 獲取評論統計
  getCommentStats: async (movieId: number) => {
    const response = await api.get(`/comments/stats/${movieId}`)
    return response.data
  },
  
  // 獲取最近評論
  getRecentComments: async (limit: number = 10) => {
    const response = await api.get('/comments/recent', {
      params: { limit }
    })
    return response.data
  }
}

// 瀏覽歷史API
export const viewHistoryApi = {
  // 創建瀏覽記錄
  createViewHistory: async (viewData: { movie_id: number; view_duration?: number; view_type?: string }) => {
    const response = await api.post('/view-history/', viewData)
    return response.data
  },
  
  // 獲取用戶瀏覽歷史
  getUserViewHistory: async (page: number = 1, pageSize: number = 20, days: number = 30, viewType?: string) => {
    const response = await api.get('/view-history/user', {
      params: { page, page_size: pageSize, days, view_type: viewType }
    })
    return response.data
  },

  // 獲取用戶「去重」瀏覽電影（每部電影只顯示最新一次）
  getUserUniqueMovies: async (days: number = 30, viewType?: string) => {
    const response = await api.get('/view-history/unique-movies', {
      params: { days, view_type: viewType }
    })
    return response.data
  },
  
  // 獲取瀏覽歷史統計
  getViewHistoryStats: async (days: number = 30) => {
    const response = await api.get('/view-history/stats', {
      params: { days }
    })
    return response.data
  },
  
  // 獲取瀏覽歷史分析
  getViewHistoryAnalytics: async (days: number = 30) => {
    const response = await api.get('/view-history/analytics', {
      params: { days }
    })
    return response.data
  },
  
  // 清除瀏覽歷史
  clearViewHistory: async (days?: number) => {
    const response = await api.delete('/view-history/clear', {
      params: { days }
    })
    return response.data
  },
  
  // 獲取最近瀏覽記錄
  getRecentViews: async (limit: number = 10) => {
    const response = await api.get('/view-history/recent', {
      params: { limit }
    })
    return response.data
  }
}
