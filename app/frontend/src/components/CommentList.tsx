import { useState, useEffect, useImperativeHandle, forwardRef } from 'react'
import { commentApi } from '../services/api'
import type { Comment } from '../services/api'
import { CommentItem } from './CommentItem'
import LoadingSpinner from './LoadingSpinner'

interface CommentListProps {
  movieId: number
  currentUserId?: number
  commentType?: 'all' | 'comment' | 'review'
  sortBy?: 'newest' | 'oldest'
  pageSize?: number
  onCommentAdded?: () => void
}

export interface CommentListRef {
  refreshComments: () => void
}

export const CommentList = forwardRef<CommentListRef, CommentListProps>(({
  movieId,
  currentUserId,
  commentType: _commentType = 'all', // 保留參數以保持接口兼容性，但暫時不使用
  sortBy = 'newest',
  pageSize = 10,
  onCommentAdded
}, ref) => {
  const [comments, setComments] = useState<Comment[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [totalComments, setTotalComments] = useState(0)

  const loadComments = async (pageNum: number = 1, reset: boolean = false) => {
    try {
      setLoading(true)
      const response = await commentApi.getMovieComments(movieId, pageNum, pageSize, sortBy)
      
      if (reset) {
        setComments(response.comments || [])
      } else {
        setComments(prev => [...prev, ...(response.comments || [])])
      }
      
      setTotalComments(response.total || 0)
      setHasMore(response.has_more || false)
    } catch (error) {
      console.error('Error loading comments:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadComments(1, true)
  }, [movieId, sortBy, pageSize])

  // 監聽評論添加事件
  useEffect(() => {
    if (onCommentAdded) {
      // 這裡可以通過 props 傳遞的 onCommentAdded 來觸發刷新
      // 但更好的方式是使用 useEffect 監聽外部狀態變化
    }
  }, [onCommentAdded])

  // 暴露刷新方法給父組件
  const refreshComments = () => {
    loadComments(1, true)
  }

  useImperativeHandle(ref, () => ({
    refreshComments
  }))

  const handleCommentUpdated = () => {
    loadComments(1, true)
  }

  const handleCommentDeleted = () => {
    loadComments(1, true)
  }

  const loadMore = () => {
    if (!loading && hasMore) {
      const nextPage = page + 1
      setPage(nextPage)
      loadComments(nextPage, false)
    }
  }

  const filteredComments = comments

  if (loading && comments.length === 0) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {totalComments > 0 && (
        <div className="relative bg-gradient-to-br from-slate-900/80 to-slate-800/80 rounded-2xl p-5 mb-6 border border-white/10 shadow-lg backdrop-blur-sm">
          {/* 背景裝飾 */}
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500/3 to-purple-500/3 rounded-2xl"></div>
          
          <div className="relative z-10 flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="relative">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 rounded-xl flex items-center justify-center shadow-lg">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full border border-slate-900 flex items-center justify-center">
                  <span className="text-white text-xs font-bold">{totalComments}</span>
                </div>
              </div>
              <div>
                <h3 className="text-xl font-bold text-white mb-1 bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  Comments & Discussion
                </h3>
                <p className="text-gray-300 text-sm">Share your thoughts and feelings</p>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-white">{totalComments}</div>
              <div className="text-gray-400 text-xs">comments</div>
            </div>
          </div>
        </div>
      )}

      {filteredComments.length === 0 ? (
        <div className="relative text-center py-12">
          {/* 背景裝飾 */}
          <div className="absolute inset-0 bg-gradient-to-br from-slate-900/30 to-slate-800/30 rounded-2xl"></div>
          
          <div className="relative z-10">
            <div className="w-20 h-20 bg-gradient-to-br from-blue-500/20 via-purple-500/20 to-pink-500/20 rounded-full flex items-center justify-center mx-auto mb-4 border border-white/10 shadow-lg backdrop-blur-sm">
              <svg className="w-10 h-10 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h3 className="text-2xl font-bold text-white mb-3 bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
              No comments yet
            </h3>
            <p className="text-gray-300 text-sm mb-4 max-w-sm mx-auto leading-relaxed">
              Be the first to share your thoughts
            </p>
            <div className="flex justify-center space-x-1">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
              <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse" style={{animationDelay: '0.2s'}}></div>
              <div className="w-2 h-2 bg-pink-500 rounded-full animate-pulse" style={{animationDelay: '0.4s'}}></div>
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="space-y-4">
            {filteredComments.map((comment) => (
              <CommentItem
                key={comment.id}
                comment={comment}
                currentUserId={currentUserId}
                onCommentUpdated={handleCommentUpdated}
                onCommentDeleted={handleCommentDeleted}
              />
            ))}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-6">
              <button
                onClick={loadMore}
                disabled={loading}
                className="group relative px-6 py-3 bg-gradient-to-r from-slate-800/80 to-slate-700/80 text-white rounded-xl hover:from-slate-700/80 hover:to-slate-600/80 transition-all duration-300 shadow-lg disabled:opacity-50 disabled:cursor-not-allowed border border-white/10 backdrop-blur-sm"
              >
                <div className="flex items-center space-x-2">
                  {loading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                      <span className="text-sm">Loading...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4 group-hover:translate-y-0.5 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                      <span className="text-sm">Load more comments</span>
                    </>
                  )}
                </div>
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
})

CommentList.displayName = 'CommentList'
