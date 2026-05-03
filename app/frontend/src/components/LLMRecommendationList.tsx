import React, { useState, useEffect } from 'react';
import LLMRecommendationCard from './LLMRecommendationCard';
import LoadingSpinner from './LoadingSpinner';
import { api } from '../services/api';

interface LLMRecommendation {
  movie_id: number;
  movie_title: string;
  movie_year: number;
  explanation: string;
  model_used: string;
  success: boolean;
  error?: string;
}

interface LLMRecommendationListProps {
  userId: number;
  limit?: number;
  modelName?: string;
  onMovieSelect?: (movieId: number) => void;
  onMovieRate?: (movieId: number, rating: number) => void;
  showModelSelector?: boolean;
  showStats?: boolean;
}

const LLMRecommendationList: React.FC<LLMRecommendationListProps> = ({
  userId,
  limit = 10,
  modelName,
  onMovieSelect,
  onMovieRate,
  showModelSelector = true,
  showStats = true
}) => {
  const [recommendations, setRecommendations] = useState<LLMRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>(modelName || 'default');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

  // 獲取可用模型
  useEffect(() => {
    const fetchAvailableModels = async () => {
      try {
        const response = await api.get('/recommend/available-models');
        setAvailableModels(response.data.available_models || []);
        if (!modelName && response.data.available_models?.length > 0) {
          setSelectedModel(response.data.available_models[0]);
        }
      } catch (err) {
        console.error('獲取可用模型失敗:', err);
      }
    };

    fetchAvailableModels();
  }, [modelName]);

  // 獲取推薦
  const fetchRecommendations = async (model: string = selectedModel) => {
    try {
      setLoading(true);
      setError(null);

      const response = await api.get(`/recommend/llm-recommendations/${userId}`, {
        params: {
          limit,
          model_name: model
        }
      });

      setRecommendations(response.data.recommendations || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch recommendations');
      console.error('獲取推薦失敗:', err);
    } finally {
      setLoading(false);
    }
  };

  // 獲取系統統計
  const fetchStats = async () => {
    try {
      const response = await api.get('/recommend/llm-system-stats');
      setStats(response.data);
    } catch (err) {
      console.error('獲取統計失敗:', err);
    }
  };

  // 初始加載
  useEffect(() => {
    if (selectedModel) {
      fetchRecommendations(selectedModel);
    }
  }, [userId, limit, selectedModel]);

  // 定期獲取統計
  useEffect(() => {
    if (showStats) {
      fetchStats();
      const interval = setInterval(fetchStats, 30000); // 每30秒更新一次
      return () => clearInterval(interval);
    }
  }, [showStats]);

  // 刷新推薦
  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchRecommendations(selectedModel);
    setRefreshing(false);
  };

  // 模型切換
  const handleModelChange = async (model: string) => {
    setSelectedModel(model);
    await fetchRecommendations(model);
  };

  // 電影選擇
  const handleMovieSelect = (movieId: number) => {
    if (onMovieSelect) {
      onMovieSelect(movieId);
    }
  };

  // 電影評分
  const handleMovieRate = (movieId: number, rating: number) => {
    if (onMovieRate) {
      onMovieRate(movieId, rating);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <LoadingSpinner size="lg" />
        <p className="mt-4 text-gray-600">Generating AI recommendations...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <div className="text-red-600 mb-4">
          <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">Failed to get recommendations</h3>
        <p className="text-gray-600 mb-4">{error}</p>
        <button
          onClick={handleRefresh}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 標題和控制欄 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">AI Recommended Movies</h2>
          <p className="text-gray-600 mt-1">
            Personalized recommendations based on your preferences and knowledge graph
          </p>
        </div>

        <div className="mt-4 sm:mt-0 flex items-center space-x-4">
          {/* 模型選擇器 */}
          {showModelSelector && availableModels.length > 0 && (
            <select
              value={selectedModel}
              onChange={(e) => handleModelChange(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {availableModels.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          )}

          {/* 刷新按鈕 */}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="bg-gray-600 hover:bg-gray-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* 系統統計 */}
      {showStats && stats && (
        <div className="bg-gray-50 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">System status</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-600">Available models:</span>
              <span className="ml-1 font-medium">{stats.available_models?.length || 0}</span>
            </div>
            <div>
              <span className="text-gray-600">Queue size:</span>
              <span className="ml-1 font-medium">{stats.queue_size || 0}</span>
            </div>
            <div>
              <span className="text-gray-600">Cache size:</span>
              <span className="ml-1 font-medium">{stats.cache_size || 0}</span>
            </div>
            <div>
              <span className="text-gray-600">Worker threads:</span>
              <span className="ml-1 font-medium">{stats.workers_running || 0}</span>
            </div>
          </div>
        </div>
      )}

      {/* 推薦列表 */}
      {recommendations.length > 0 ? (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {recommendations.map((recommendation) => (
            <LLMRecommendationCard
              key={recommendation.movie_id}
              movie={recommendation}
              onRate={handleMovieRate}
              onView={handleMovieSelect}
              showLLMDetails={true}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <div className="text-gray-400 mb-4">
            <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6-4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.29-1.009-5.824-2.709M15 6.291A7.962 7.962 0 0112 4c-2.34 0-4.29 1.009-5.824 2.709" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No recommendations</h3>
          <p className="text-gray-600 mb-4">
            We couldn't find suitable movie recommendations for you. Please try again later.
          </p>
          <button
            onClick={handleRefresh}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
          >
            Regenerate recommendations
          </button>
        </div>
      )}

      {/* 推薦統計 */}
      {recommendations.length > 0 && (
        <div className="text-center text-sm text-gray-600">
          Showing {recommendations.length} recommendations using model: {selectedModel}
        </div>
      )}
    </div>
  );
};

export default LLMRecommendationList;
