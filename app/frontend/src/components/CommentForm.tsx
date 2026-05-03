import React, { useState } from 'react'
import { commentApi } from '../services/api'
import toast from 'react-hot-toast'

interface CommentFormProps {
  movieId: number
  onCommentAdded: () => void
  commentType?: 'comment' | 'review'
}

export const CommentForm: React.FC<CommentFormProps> = ({
  movieId,
  onCommentAdded,
  commentType = 'comment'
}) => {
  const [content, setContent] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!content.trim()) {
      toast.error('Please enter your comment')
      return
    }

    setIsSubmitting(true)
    try {
      await commentApi.createComment({
        movie_id: movieId,
        content: content.trim()
      })
      setContent('')
      toast.success(commentType === 'review' ? 'Review posted successfully!' : 'Comment added successfully!')
      onCommentAdded()
    } catch (error) {
      console.error('Error creating comment:', error)
      toast.error('Failed to publish comment. Please try again later.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="relative">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={commentType === 'review' ? 'Share your thoughts about this movie...' : 'Write your comment...'}
            className="w-full p-4 border-2 border-white/20 rounded-2xl focus:ring-4 focus:ring-blue-500/20 focus:border-blue-400 resize-none transition-all duration-200 bg-white/10 backdrop-blur-sm text-white placeholder-gray-400"
            rows={4}
            maxLength={1000}
          />
          <div className="absolute bottom-3 right-3 text-xs text-gray-400 bg-black/20 px-2 py-1 rounded-full backdrop-blur-sm">
            {content.length}/1000
          </div>
        </div>
        
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSubmitting || !content.trim()}
            className="px-8 py-3 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-2xl hover:from-blue-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 transform hover:scale-105 shadow-lg font-medium"
          >
            {isSubmitting ? (
              <span className="flex items-center space-x-2">
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Publishing...</span>
              </span>
            ) : (
              <span>{commentType === 'review' ? 'Post Review' : 'Add Comment'}</span>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}