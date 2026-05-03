import { Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuthStore } from './stores/authStore'
import Layout from './components/Layout'
import OnboardingGuard from './components/OnboardingGuard'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import MovieList from './pages/MovieList'
import MovieDetail from './pages/MovieDetail'
import Profile from './pages/Profile'
import Favorites from './pages/Favorites'
import Likes from './pages/Likes'
import ViewHistory from './pages/ViewHistory'
import EnhancedRecommendations from './pages/EnhancedRecommendations'

function App() {
  const { isAuthenticated, initializeAuth } = useAuthStore()

  // 初始化認證狀態
  useEffect(() => {
    initializeAuth()
  }, [initializeAuth])

  console.log('App rendered, isAuthenticated:', isAuthenticated)

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/" element={isAuthenticated ? <Layout /> : <Navigate to="/login" replace />}>
          <Route index element={<OnboardingGuard><Home /></OnboardingGuard>} />
          <Route path="movies" element={<OnboardingGuard><MovieList /></OnboardingGuard>} />
          <Route path="movies/:id" element={<OnboardingGuard><MovieDetail /></OnboardingGuard>} />
          <Route path="view-history" element={<OnboardingGuard><ViewHistory /></OnboardingGuard>} />
          <Route path="profile" element={<OnboardingGuard><Profile /></OnboardingGuard>} />
          <Route path="favorites" element={<OnboardingGuard><Favorites /></OnboardingGuard>} />
          <Route path="likes" element={<OnboardingGuard><Likes /></OnboardingGuard>} />
          <Route path="enhanced-recommendations" element={<OnboardingGuard><EnhancedRecommendations /></OnboardingGuard>} />
        </Route>
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </div>
  )
}

export default App
