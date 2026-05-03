import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Star } from 'lucide-react'
import toast from 'react-hot-toast'

interface StarRatingProps {
  rating: number
  movieId?: number
  size?: 'sm' | 'md' | 'lg'
  showNumber?: boolean
  theme?: 'light' | 'dark'
  readonly?: boolean
  onRatingChange?: (rating: number) => void
}

const StarRating: React.FC<StarRatingProps> = ({
  rating,
  movieId,
  size = 'md',
  showNumber = false,
  theme = 'dark',
  readonly = false,
  onRatingChange
}) => {
  const [currentRating, setCurrentRating] = useState(rating)
  const [hoverRating, setHoverRating] = useState(0)

  useEffect(() => {
    setCurrentRating(rating)
  }, [rating])

  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6'
  }

  const handleStarClick = async (starRating: number, event: React.MouseEvent) => {
    if (readonly) return

    event.preventDefault()
    event.stopPropagation()

    setCurrentRating(starRating) // 立即更新 UI

    if (movieId) {
      try {
        const { ratingApi } = await import('../services/api')
        await ratingApi.createOrUpdateRating(movieId, starRating)
        toast.success(`Rated ${starRating} star${starRating === 1 ? '' : 's'}`, {
          style: {
            background: '#1f2937',
            color: '#f9fafb',
            border: '1px solid #374151'
          }
        })
        onRatingChange?.(starRating) // 評分成功後才調用回調
      } catch (error) {
        console.error('Failed to save rating:', error)
        toast.error('Failed to save rating. Please try again.', {
          style: {
            background: '#1f2937',
            color: '#f9fafb',
            border: '1px solid #374151'
          }
        })
        setCurrentRating(rating) // 恢復之前的評分
      }
    } else {
      onRatingChange?.(starRating) // 沒有電影ID時直接調用回調
    }
  }

  const handleStarHover = (starRating: number) => {
    if (!readonly) {
      setHoverRating(starRating)
    }
  }

  const handleStarLeave = () => {
    if (!readonly) {
      setHoverRating(0)
    }
  }

  const displayRating = hoverRating || currentRating

  return (
    <div className="flex items-center space-x-2">
      <div className="flex space-x-1">
        {[1, 2, 3, 4, 5].map((star) => {
          const isFilled = star <= displayRating
          const isHovered = hoverRating > 0 && star <= hoverRating
          
          return (
            <motion.button
              key={star}
              type="button"
              onClick={(e) => handleStarClick(star, e)}
              onMouseEnter={() => handleStarHover(star)}
              onMouseLeave={handleStarLeave}
              disabled={readonly}
              whileHover={!readonly ? { scale: 1.2 } : {}}
              whileTap={!readonly ? { scale: 0.9 } : {}}
              className={`${sizeClasses[size]} transition-all duration-300 ${
                readonly ? 'cursor-default' : 'cursor-pointer'
              }`}
            >
              <Star
                className={`${sizeClasses[size]} transition-all duration-300 ${
                  isFilled
                    ? 'text-yellow-400 fill-current drop-shadow-md'
                    : isHovered
                    ? 'text-yellow-300 fill-current drop-shadow-sm'
                    : theme === 'dark'
                    ? 'text-gray-600 hover:text-yellow-300'
                    : 'text-gray-300 hover:text-yellow-400'
                } ${
                  !readonly && (isFilled || isHovered)
                    ? 'animate-pulse'
                    : ''
                }`}
              />
            </motion.button>
          )
        })}
      </div>
      
      {showNumber && (
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
          className="flex items-center space-x-1"
        >
          <span className={`font-semibold ${
            theme === 'dark' ? 'text-white' : 'text-gray-800'
          }`}>
            {displayRating.toFixed(1)}
          </span>
          <span className={`text-sm ${
            theme === 'dark' ? 'text-gray-400' : 'text-gray-500'
          }`}>
            / 5
          </span>
        </motion.div>
      )}
    </div>
  )
}

export default StarRating