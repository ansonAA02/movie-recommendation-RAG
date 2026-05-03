import { useState } from 'react'
import { motion } from 'framer-motion'
import { Link, useNavigate } from 'react-router-dom'
import { 
  Eye, 
  EyeOff, 
  Lock, 
  User, 
  Sparkles,
  ArrowRight,
  AlertCircle,
  Loader
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

const Login = () => {
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  })
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  
  const { login } = useAuthStore()
  const navigate = useNavigate()

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    // 清除對應的錯誤信息
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: '' }))
    }
  }

  const validateForm = () => {
    const newErrors: Record<string, string> = {}
    
    if (!formData.username.trim()) {
      newErrors.username = 'Please enter a username'
    }
    
    if (!formData.password) {
      newErrors.password = 'Please enter a password'
    } else if (formData.password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters'
    }
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateForm()) return
    
    try {
      setLoading(true)
      await login(formData.username, formData.password)
      toast.success('Signed in successfully!', {
        style: {
          background: '#1f2937',
          color: '#f9fafb',
          border: '1px solid #374151'
        }
      })
      navigate('/')
    } catch (error: any) {
      console.error('Login failed:', error)
      toast.error(error.response?.data?.detail || 'Sign-in failed. Please check your username and password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center p-4">
      {/* 背景裝飾 */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute inset-0 opacity-50" style={{ backgroundImage: 'radial-gradient(circle at 20% 20%, rgba(59,130,246,0.12), transparent 25%), radial-gradient(circle at 80% 30%, rgba(168,85,247,0.12), transparent 25%), radial-gradient(circle at 40% 80%, rgba(236,72,153,0.12), transparent 25%)' }} />
      </div>

      <div className="relative z-10 w-full max-w-md">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900/60 to-slate-800/60 backdrop-blur-xl shadow-[0_8px_30px_rgb(0,0,0,0.25)] p-8"
        >
          {/* Logo和標題 */}
          <div className="text-center mb-8">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="relative inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-blue-600 to-purple-600 rounded-2xl mb-4 shadow-[0_8px_30px_rgb(0,0,0,0.25)] border border-white/10 overflow-hidden"
            >
              <div className="pointer-events-none absolute inset-0 opacity-60" style={{ backgroundImage: 'conic-gradient(from 180deg at 50% 50%, rgba(255,255,255,0.25), transparent 30%, rgba(255,255,255,0.15), transparent 70%, rgba(255,255,255,0.25))' }} />
              <Sparkles className="w-8 h-8 text-blue-100" />
            </motion.div>
            
            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="text-3xl font-bold text-white mb-2 tracking-tight"
            >
              Welcome Back
            </motion.h1>
            
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="text-white/60"
            >
              Sign in to your MovieHub account
            </motion.p>
          </div>

          {/* 登錄表單 */}
          <motion.form
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.5 }}
            onSubmit={handleSubmit}
            className="space-y-6"
          >
            {/* 用戶名輸入 */}
            <div className="form-group">
              <label className="form-label text-white/80">Username</label>
              <div className="relative">
                <User className="pointer-events-none absolute left-3 top-1/2 transform -translate-y-1/2 text-blue-300 w-12 h-12 p-2.5 rounded-lg bg-transparent" />
                <input
                  type="text"
                  name="username"
                  value={formData.username}
                  onChange={handleChange}
                  placeholder="Enter your username"
                  className={`w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition ${errors.username ? 'border-red-500 focus:ring-red-500' : ''} pl-24`}
                />
                {errors.username && (
                  <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
                    <AlertCircle className="w-5 h-5 text-red-500" />
                  </div>
                )}
              </div>
              {errors.username && (
                <p className="form-error">{errors.username}</p>
              )}
            </div>

            {/* 密碼輸入 */}
            <div className="form-group">
              <label className="form-label text-white/80">Password</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 transform -translate-y-1/2 text-blue-300 w-12 h-12 p-2.5 rounded-lg bg-transparent" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  placeholder="Enter your password"
                  className={`w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition ${errors.password ? 'border-red-500 focus:ring-red-500' : ''} pl-24 pr-16`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-blue-300 hover:text-blue-200 transition-colors bg-white/10 border border-white/10 rounded-lg p-1.5 backdrop-blur-sm"
                >
                  {showPassword ? <EyeOff className="w-8 h-8" /> : <Eye className="w-8 h-8" />}
                </button>
                {errors.password && (
                  <div className="absolute right-12 top-1/2 transform -translate-y-1/2">
                    <AlertCircle className="w-5 h-5 text-red-500" />
                  </div>
                )}
              </div>
              {errors.password && (
                <p className="form-error">{errors.password}</p>
              )}
            </div>

            {/* 記住我和忘記密碼 */}
            <div className="flex items-center justify-between">
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="w-4 h-4 text-blue-600 bg-slate-800 border-slate-600 rounded focus:ring-blue-500 focus:ring-2"
                />
                <span className="text-sm text-white/70">Remember me</span>
              </label>
              <button
                type="button"
                className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
              >
                Forgot password?
              </button>
            </div>

            {/* 登錄按鈕 */}
            <motion.button
              type="submit"
              disabled={loading}
              whileHover={{ scale: loading ? 1 : 1.02 }}
              whileTap={{ scale: loading ? 1 : 0.98 }}
              className="w-full flex items-center justify-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-3 shadow-lg hover:shadow-xl transition-shadow"
            >
              {loading ? (
                <>
                  <Loader className="w-5 h-5 animate-spin" />
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </motion.button>
          </motion.form>

          {/* 分割線 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.6 }}
            className="my-8 h-px w-full bg-gradient-to-r from-transparent via-white/20 to-transparent"
          />

          {/* 註冊鏈接 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.7 }}
            className="text-center"
          >
            <p className="text-white/70 mb-4">
              Don't have an account?
            </p>
            <Link
              to="/register"
              className="w-full flex items-center justify-center space-x-2 text-blue-400 hover:text-blue-300"
            >
              <span>Sign Up Now</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </motion.div>
        </motion.div>

        {/* 底部信息 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.8 }}
          className="text-center mt-8"
        >
          <p className="text-white/60 text-sm">
            By signing in, you agree to our{' '}
            <a href="#" className="text-blue-400 hover:text-blue-300 transition-colors">Terms of Service</a>
            {' '}and{' '}
            <a href="#" className="text-blue-400 hover:text-blue-300 transition-colors">Privacy Policy</a>
          </p>
        </motion.div>
      </div>
    </div>
  )
}

export default Login