import { Outlet, Link, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Home,
  Film,
  User,
  Heart,
  Menu,
  X,
  LogOut,
  Settings,
  Sparkles,
  History,
  ThumbsUp,
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'

const Layout = () => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isHovering, setIsHovering] = useState(false)
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    logout()
    toast.success('Logged out successfully', {
      style: {
        background: '#1f2937',
        color: '#f9fafb',
        border: '1px solid #374151'
      }
    })
    navigate('/login')
  }

  const navigation = [
    { name: 'Home', href: '/', icon: Home, description: 'Explore amazing content', color: 'from-blue-500 to-cyan-500' },
    { name: 'Movies', href: '/movies', icon: Film, description: 'Browse all movies', color: 'from-purple-500 to-pink-500' },
    { name: 'Enhanced Rec', href: '/enhanced-recommendations', icon: Sparkles, description: 'Enhanced hybrid recommendations (ANN + KG)', color: 'from-yellow-500 to-orange-500' },
    { name: 'History', href: '/view-history', icon: History, description: 'Viewing history and analytics', color: 'from-pink-500 to-rose-500' },
    { name: 'Favorites', href: '/favorites', icon: Heart, description: 'Personal favorites', color: 'from-red-500 to-pink-500' },
    { name: 'Likes', href: '/likes', icon: ThumbsUp, description: 'Movies you liked', color: 'from-cyan-500 to-blue-500' },
    { name: 'Profile', href: '/profile', icon: User, description: 'Account settings', color: 'from-gray-500 to-slate-500' },
  ]

  const isActive = (href: string) => {
    if (href === '/') {
      return location.pathname === '/'
    }
    return location.pathname.startsWith(href)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 relative">
      <motion.div
        className="fixed left-0 top-0 h-full z-50"
        onMouseEnter={() => setIsHovering(true)}
        onMouseLeave={() => setIsHovering(false)}
        initial={{ x: -320 }}
        animate={{ x: isHovering ? 0 : -320 }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
      >
        <div className="h-full w-80 bg-gradient-to-b from-slate-900/95 to-slate-800/95 backdrop-blur-xl border-r border-white/10 shadow-2xl">
          <div className="p-6 border-b border-white/10">
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center space-x-4"
            >
              <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center shadow-lg">
                <Sparkles className="w-7 h-7 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">MovieHub</h1>
                <p className="text-sm text-gray-400">AI Movie Platform</p>
              </div>
            </motion.div>
          </div>

          <div className="p-4 space-y-2">
            {navigation.map((item, index) => (
              <motion.div
                key={item.name}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
              >
                <Link
                  to={item.href}
                  className={`group flex items-center space-x-4 p-4 rounded-2xl transition-all duration-300 ${
                    isActive(item.href)
                      ? `bg-gradient-to-r ${item.color} text-white shadow-lg transform scale-105`
                      : 'text-gray-300 hover:bg-white/10 hover:text-white hover:transform hover:scale-105'
                  }`}
                >
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-300 ${
                    isActive(item.href)
                      ? 'bg-white/20 shadow-lg'
                      : `bg-gradient-to-br ${item.color} group-hover:shadow-lg`
                  }`}>
                    <item.icon className="w-5 h-5" />
                  </div>
                  <div className="flex-1">
                    <div className="font-semibold">{item.name}</div>
                    <div className="text-xs opacity-80">{item.description}</div>
                  </div>
                  {isActive(item.href) && (
                    <motion.div
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      className="w-2 h-2 bg-white rounded-full"
                    />
                  )}
                </Link>
              </motion.div>
            ))}
          </div>

          <div className="absolute bottom-0 left-0 right-0 p-6 border-t border-white/10">
            <div className="flex items-center space-x-4 mb-4">
              <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center shadow-lg">
                <span className="text-white text-lg font-bold">
                  {user?.username?.charAt(0).toUpperCase()}
                </span>
              </div>
              <div className="flex-1">
                <div className="font-semibold text-white">{user?.username}</div>
                <div className="text-sm text-gray-400">Premium User</div>
              </div>
            </div>

            <div className="flex space-x-2">
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="flex-1 p-3 bg-white/10 text-white rounded-xl hover:bg-white/20 transition-all duration-200 flex items-center justify-center space-x-2"
              >
                <Settings className="w-4 h-4" />
                <span className="text-sm">Settings</span>
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleLogout}
                className="flex-1 p-3 bg-red-500/20 text-red-400 rounded-xl hover:bg-red-500/30 transition-all duration-200 flex items-center justify-center space-x-2"
              >
                <LogOut className="w-4 h-4" />
                <span className="text-sm">Logout</span>
              </motion.button>
            </div>
          </div>
        </div>
      </motion.div>

      <div
        className="fixed left-0 top-0 w-8 h-full z-40 cursor-pointer"
        onMouseEnter={() => setIsHovering(true)}
        onMouseLeave={() => setIsHovering(false)}
      />

      <motion.div
        className="fixed left-2 top-1/2 transform -translate-y-1/2 z-30"
        animate={{
          opacity: isHovering ? 0 : 0.6,
          x: isHovering ? -20 : 0
        }}
        transition={{ duration: 0.3 }}
      >
        <div className="w-1 h-16 bg-gradient-to-b from-blue-500 to-purple-600 rounded-full shadow-lg"></div>
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-white text-xs font-bold">
          →
        </div>
      </motion.div>

      <motion.main
        className="transition-all duration-300"
        animate={{
          marginLeft: isHovering ? '320px' : '0px',
          paddingLeft: isHovering ? '0px' : '0px'
        }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
      >
        <Outlet />
      </motion.main>

      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        className="md:hidden fixed top-4 left-4 z-50 p-3 bg-slate-800/90 backdrop-blur-xl text-white rounded-2xl shadow-lg border border-white/10"
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
      >
        {isMobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
      </motion.button>

      <AnimatePresence>
        {isMobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, x: -300 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -300 }}
            className="md:hidden fixed left-0 top-0 h-full w-80 bg-gradient-to-b from-slate-900/95 to-slate-800/95 backdrop-blur-xl border-r border-white/10 shadow-2xl z-40"
          >
            <div className="p-6 border-b border-white/10">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center shadow-lg">
                    <Sparkles className="w-7 h-7 text-white" />
                  </div>
                  <div>
                    <h1 className="text-xl font-bold text-white">MovieHub</h1>
                    <p className="text-sm text-gray-400">AI Movie Platform</p>
                  </div>
                </div>
                <button
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="p-2 text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>
            </div>

            <div className="p-4 space-y-2">
              {navigation.map((item) => (
                <Link
                  key={item.name}
                  to={item.href}
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`group flex items-center space-x-4 p-4 rounded-2xl transition-all duration-300 ${
                    isActive(item.href)
                      ? `bg-gradient-to-r ${item.color} text-white shadow-lg`
                      : 'text-gray-300 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                    isActive(item.href) ? 'bg-white/20' : `bg-gradient-to-br ${item.color}`
                  }`}>
                    <item.icon className="w-5 h-5" />
                  </div>
                  <div className="flex-1">
                    <div className="font-semibold">{item.name}</div>
                    <div className="text-xs opacity-80">{item.description}</div>
                  </div>
                </Link>
              ))}
            </div>

            <div className="absolute bottom-0 left-0 right-0 p-6 border-t border-white/10">
              <div className="flex items-center space-x-4 mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center shadow-lg">
                  <span className="text-white text-lg font-bold">
                    {user?.username?.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="flex-1">
                  <div className="font-semibold text-white">{user?.username}</div>
                  <div className="text-sm text-gray-400">Premium User</div>
                </div>
              </div>

              <div className="flex space-x-2">
                <button className="flex-1 p-3 bg-white/10 text-white rounded-xl hover:bg-white/20 transition-all duration-200 flex items-center justify-center space-x-2">
                  <Settings className="w-4 h-4" />
                  <span className="text-sm">Settings</span>
                </button>
                <button
                  onClick={handleLogout}
                  className="flex-1 p-3 bg-red-500/20 text-red-400 rounded-xl hover:bg-red-500/30 transition-all duration-200 flex items-center justify-center space-x-2"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="text-sm">Logout</span>
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default Layout
