import React, { useState } from 'react';
import StarRating from './StarRating';

interface LLMRecommendationCardProps {
  movie: {
    movie_id: number;
    movie_title: string;
    movie_year: number;
    explanation: string;
    model_used: string;
    success: boolean;
    error?: string;
  };
  onRate?: (movieId: number, rating: number) => void;
  onView?: (movieId: number) => void;
  showLLMDetails?: boolean;
}

const LLMRecommendationCard: React.FC<LLMRecommendationCardProps> = ({
  movie,
  onRate,
  onView,
  showLLMDetails = true
}) => {
  const [showFullExplanation, setShowFullExplanation] = useState(false);

  const handleView = () => {
    if (onView) {
      onView(movie.movie_id);
    }
  };

  const handleRate = (rating: number) => {
    if (onRate) {
      onRate(movie.movie_id, rating);
    }
  };

  const toggleExplanation = () => {
    setShowFullExplanation(!showFullExplanation);
  };

  const truncateExplanation = (text: string, maxLength: number = 150) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow duration-200">
      {/* 電影基本信息 */}
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1">
          <h3 className="text-xl font-bold text-gray-900 mb-1">
            {movie.movie_title}
          </h3>
          <p className="text-gray-600 mb-2">
            {movie.movie_year}
          </p>
        </div>
        
        {showLLMDetails && (
          <div className="flex items-center space-x-2">
            <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded-full">
              {movie.model_used}
            </span>
            {movie.success ? (
              <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">
                AI-generated
              </span>
            ) : (
              <span className="text-xs bg-red-100 text-red-800 px-2 py-1 rounded-full">
                Generation failed
              </span>
            )}
          </div>
        )}
      </div>

      {/* LLM 推薦解釋 */}
      <div className="mb-4">
        <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg p-4 border-l-4 border-blue-400">
          <div className="flex items-center mb-2">
            <div className="w-2 h-2 bg-blue-400 rounded-full mr-2"></div>
            <h4 className="text-sm font-semibold text-gray-700">
              AI Recommendation Reason
            </h4>
          </div>
          
          {movie.success ? (
            <div>
              <p className="text-gray-700 leading-relaxed">
                {showFullExplanation 
                  ? movie.explanation 
                  : truncateExplanation(movie.explanation)
                }
              </p>
              
              {movie.explanation.length > 150 && (
                <button
                  onClick={toggleExplanation}
                  className="text-blue-600 hover:text-blue-800 text-sm mt-2 font-medium"
                >
                  {showFullExplanation ? 'Collapse' : 'Expand'}
                </button>
              )}
            </div>
          ) : (
            <div className="text-red-600 text-sm">
              <p>Sorry, we can't generate the recommendation explanation.</p>
              {movie.error && (
                <p className="text-xs mt-1 opacity-75">
                  Error: {movie.error}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 操作按鈕 */}
      <div className="flex justify-between items-center">
        <div className="flex space-x-2">
          <button
            onClick={handleView}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
          >
            View details
          </button>
          
          <button
            onClick={() => window.open(`https://www.imdb.com/title/tt${movie.movie_id}`, '_blank')}
            className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
          >
            IMDb
          </button>
        </div>

        {onRate && (
          <div className="flex items-center space-x-2">
            <span className="text-sm text-gray-600">Rating:</span>
            <StarRating
              rating={0}
              onRatingChange={handleRate}
              size="sm"
            />
          </div>
        )}
      </div>

    </div>
  );
};

export default LLMRecommendationCard;
