import React, { useState } from 'react'
import { commentApi } from '../services/api'
import toast from 'react-hot-toast'

interface CommentItemProps {
  comment: {
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
  currentUserId?: number
  onCommentUpdated: () => void
  onCommentDeleted: () => void
}

export const CommentItem: React.FC<CommentItemProps> = ({
  comment,
  currentUserId,
  onCommentUpdated,
  onCommentDeleted
}) => {
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(comment.content)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const isOwner = currentUserId === comment.user_id
  const isReview = false // 簡化：所有評論都是普通評論

  const handleEdit = async () => {
    if (!editContent.trim()) {
      toast.error('Comment cannot be empty')
      return
    }

    setIsSubmitting(true)
    try {
      await commentApi.updateComment(comment.id, editContent)
      toast.success('Comment updated')
      setIsEditing(false)
      onCommentUpdated()
    } catch (error) {
      console.error('Error updating comment:', error)
      toast.error('Failed to update comment')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete this comment?')) return

    try {
      await commentApi.deleteComment(comment.id)
      toast.success('Comment deleted')
      onCommentDeleted()
    } catch (error) {
      console.error('Error deleting comment:', error)
      toast.error('Failed to delete comment')
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60))
    
    if (diffInHours < 1) return 'Just now'
    if (diffInHours < 24) return `${diffInHours}h ago`
    if (diffInHours < 48) return 'Yesterday'
    
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <div className="group relative bg-gradient-to-br from-slate-900/70 to-slate-800/70 rounded-xl shadow-md border border-white/5 p-4 hover:shadow-lg hover:border-white/10 transition-all duration-200 backdrop-blur-sm">
      {/* 背景光效 */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-500/2 to-purple-500/2 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-200"></div>
      
      <div className="relative z-10">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center space-x-2">
            {/* 超緊湊頭像設計 */}
            <div className="relative">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 rounded-lg flex items-center justify-center text-white text-xs font-bold shadow-md ring-1 ring-white/5">
                {comment.user_username.charAt(0).toUpperCase()}
              </div>
              {/* 在線狀態指示器 */}
              <div className="absolute -bottom-0.5 -right-0.5 w-2 h-2 bg-green-500 rounded-full border border-slate-900"></div>
            </div>
            
            <div className="flex-1">
              <div className="flex items-center space-x-2 mb-0.5">
                <h4 className="font-medium text-white text-xs bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  {comment.user_username}
                </h4>
                {isReview && (
                  <span className="px-1.5 py-0.5 bg-gradient-to-r from-amber-500/20 to-orange-500/20 text-amber-300 text-xs rounded-md font-medium border border-amber-500/30">
                    ⭐
                  </span>
                )}
              </div>
              <div className="flex items-center space-x-1">
                <span className="text-gray-400 text-xs flex items-center space-x-1">
                  <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                  </svg>
                  <span>{formatDate(comment.created_at)}</span>
                </span>
              </div>
            </div>
          </div>
          
          {isOwner && (
            <div className="flex space-x-1">
              <button
                onClick={() => setIsEditing(!isEditing)}
                className="p-1.5 bg-gradient-to-r from-blue-500/20 to-purple-500/20 text-blue-300 rounded-md hover:from-blue-500/30 hover:to-purple-500/30 transition-all duration-200 border border-blue-500/30 hover:border-blue-400/50"
              >
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button
                onClick={handleDelete}
                className="p-1.5 bg-gradient-to-r from-red-500/20 to-pink-500/20 text-red-300 rounded-md hover:from-red-500/30 hover:to-pink-500/30 transition-all duration-200 border border-red-500/30 hover:border-red-400/50"
              >
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          )}
        </div>

        {/* 評論內容 */}
        <div className="mb-3">
          {isEditing ? (
            <div className="space-y-2">
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full p-2 bg-slate-800/50 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 backdrop-blur-sm resize-none text-xs"
                rows={2}
                placeholder="Share your thoughts..."
              />
              <div className="flex space-x-1">
                <button
                  onClick={handleEdit}
                  disabled={isSubmitting}
                  className="px-3 py-1.5 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-md hover:from-blue-600 hover:to-purple-700 transition-all duration-200 shadow-md disabled:opacity-50 disabled:cursor-not-allowed text-xs"
                >
                  {isSubmitting ? 'Saving...' : 'Save'}
                </button>
                <button
                  onClick={() => {
                    setIsEditing(false)
                    setEditContent(comment.content)
                  }}
                  className="px-3 py-1.5 bg-slate-700/50 text-gray-300 rounded-md hover:bg-slate-600/50 transition-all duration-200 border border-white/10 text-xs"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="prose prose-invert max-w-none">
              <p className="text-gray-200 text-xs leading-relaxed whitespace-pre-wrap">
                {comment.content}
              </p>
            </div>
          )}
        </div>

        {/* 互動區域 */}
        <div className="flex items-center justify-between pt-2 border-t border-white/5">
          <div className="flex items-center space-x-3">
            <button className="flex items-center space-x-1 text-gray-400 hover:text-blue-400 transition-colors duration-200">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
              <span className="text-xs">Like</span>
            </button>
            <button className="flex items-center space-x-1 text-gray-400 hover:text-purple-400 transition-colors duration-200">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <span className="text-xs">Reply</span>
            </button>
          </div>
          
          {comment.rating && (
            <div className="flex items-center space-x-1">
              <div className="flex">
                {[...Array(5)].map((_, i) => (
                  <svg
                    key={i}
                    className={`w-2.5 h-2.5 ${i < comment.rating! ? 'text-yellow-400' : 'text-gray-600'}`}
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                  </svg>
                ))}
              </div>
              <span className="text-yellow-400 text-xs font-medium">{comment.rating}/5</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}