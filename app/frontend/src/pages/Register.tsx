import { useState } from 'react'
import { motion } from 'framer-motion'
import { Link, useNavigate } from 'react-router-dom'
import { 
  Eye, 
  EyeOff, 
  Mail, 
  Lock, 
  User, 
  Sparkles,
  ArrowRight,
  CheckCircle,
  AlertCircle,
  Loader,
  Calendar,
  Users
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

const Register = () => {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    age: '',
    gender: '',
    occupation: ''
  })
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [currentStep, setCurrentStep] = useState(1)
  
  const { register } = useAuthStore()
  const navigate = useNavigate()

  const steps = [
    { number: 1, title: 'Basics', description: 'Username & password' },
    { number: 2, title: 'Profile', description: 'Age & gender' },
    { number: 3, title: 'Finish', description: 'Confirm details' }
  ]

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    // 清除對應的錯誤信息
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: '' }))
    }
  }

  const validateStep1 = () => {
    const newErrors: Record<string, string> = {}
    
    if (!formData.username.trim()) {
      newErrors.username = 'Please enter a username'
    } else if (formData.username.length < 3) {
      newErrors.username = 'Username must be at least 3 characters'
    }
    
    if (!formData.email.trim()) {
      newErrors.email = 'Please enter an email'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email address'
    }
    
    if (!formData.password) {
      newErrors.password = 'Please enter a password'
    } else if (formData.password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters'
    }
    
    if (!formData.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password'
    } else if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match'
    }
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const validateStep2 = () => {
    const newErrors: Record<string, string> = {}
    
    if (!formData.age) {
      newErrors.age = 'Please enter your age'
    } else if (isNaN(Number(formData.age)) || Number(formData.age) < 13 || Number(formData.age) > 120) {
      newErrors.age = 'Please enter a valid age (13–120)'
    }
    
    if (!formData.gender) {
      newErrors.gender = 'Please select a gender'
    }
    
    if (!formData.occupation.trim()) {
      newErrors.occupation = 'Please enter an occupation'
    }
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleNext = () => {
    if (currentStep === 1 && validateStep1()) {
      setCurrentStep(2)
    } else if (currentStep === 2 && validateStep2()) {
      setCurrentStep(3)
    }
  }

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateStep1() || !validateStep2()) return
    
    try {
      setLoading(true)
      await register({
        username: formData.username,
        email: formData.email,
        password: formData.password,
        age: parseInt(formData.age),
        gender: formData.gender,
        occupation: formData.occupation
      })
      toast.success('Account created! Welcome to MovieHub!', {
        style: {
          background: '#1f2937',
          color: '#f9fafb',
          border: '1px solid #374151'
        }
      })
      navigate('/')
    } catch (error: any) {
      console.error('Registration failed:', error)
      toast.error(error.response?.data?.detail || 'Registration failed. Please try again.')
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

      <div className="relative z-10 w-full max-w-2xl">
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
              Join MovieHub
            </motion.h1>
            
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="text-white/60"
            >
              Start your movie exploration journey
            </motion.p>
          </div>

          {/* 步驟指示器 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.5 }}
            className="flex items-center justify-center mb-8"
          >
            {steps.map((step, index) => (
              <div key={step.number} className="flex items-center">
                <div className="flex flex-col items-center">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold transition-all duration-300 ${
                    currentStep >= step.number
                      ? 'bg-gradient-to-br from-blue-600 to-purple-600 text-white shadow-md border border-white/10'
                      : 'bg-slate-700/70 text-white/60 border border-white/10'
                  }`}>
                    {currentStep > step.number ? (
                      <CheckCircle className="w-5 h-5" />
                    ) : (
                      step.number
                    )}
                  </div>
                  <div className="mt-2 text-center">
                    <div className={`text-sm font-medium ${
                      currentStep >= step.number ? 'text-white' : 'text-white/60'
                    }`}>
                      {step.title}
                    </div>
                    <div className="text-xs text-white/50">{step.description}</div>
                  </div>
                </div>
                {index < steps.length - 1 && (
                  <div className={`w-16 h-1 mx-4 rounded-full transition-all duration-300 ${
                    currentStep > step.number ? 'bg-blue-600' : 'bg-slate-700/70'
                  }`} />
                )}
              </div>
            ))}
          </motion.div>

          {/* 註冊表單 */}
          <motion.form
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.6 }}
            onSubmit={handleSubmit}
            className="space-y-6"
          >
            {/* 步驟1: 基本信息 */}
            {currentStep === 1 && (
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5 }}
                className="space-y-6"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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

                  <div className="form-group">
                    <label className="form-label text-white/80">Email</label>
                    <div className="relative">
                      <Mail className="pointer-events-none absolute left-3 top-1/2 transform -translate-y-1/2 text-blue-300 w-12 h-12 p-2.5 rounded-lg bg-transparent" />
                      <input
                        type="email"
                        name="email"
                        value={formData.email}
                        onChange={handleChange}
                        placeholder="Enter your email"
                        className={`w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition ${errors.email ? 'border-red-500 focus:ring-red-500' : ''} pl-24`}
                      />
                      {errors.email && (
                        <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
                          <AlertCircle className="w-5 h-5 text-red-500" />
                        </div>
                      )}
                    </div>
                    {errors.email && (
                      <p className="form-error">{errors.email}</p>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
                        className="absolute right-4 top-1/2 transform -translate-y-1/2 text-white/60 hover:text-white transition-colors"
                      >
                        {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
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

                  <div className="form-group">
                    <label className="form-label text-white/80">Confirm password</label>
                    <div className="relative">
                      <Lock className="pointer-events-none absolute left-3 top-1/2 transform -translate-y-1/2 text-blue-300 w-12 h-12 p-2.5 rounded-lg bg-transparent" />
                      <input
                        type={showConfirmPassword ? 'text' : 'password'}
                        name="confirmPassword"
                        value={formData.confirmPassword}
                        onChange={handleChange}
                        placeholder="Re-enter your password"
                        className={`w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition ${errors.confirmPassword ? 'border-red-500 focus:ring-red-500' : ''} pl-24 pr-16`}
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        className="absolute right-4 top-1/2 transform -translate-y-1/2 text-white/60 hover:text-white transition-colors"
                      >
                        {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                      </button>
                      {errors.confirmPassword && (
                        <div className="absolute right-12 top-1/2 transform -translate-y-1/2">
                          <AlertCircle className="w-5 h-5 text-red-500" />
                        </div>
                      )}
                    </div>
                    {errors.confirmPassword && (
                      <p className="form-error">{errors.confirmPassword}</p>
                    )}
                  </div>
                </div>
              </motion.div>
            )}

            {/* 步驟2: 個人資料 */}
            {currentStep === 2 && (
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5 }}
                className="space-y-6"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="form-group">
                    <label className="form-label">Age</label>
                    <div className="relative">
                      <Calendar className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-12 h-12 p-2.5 rounded-lg bg-transparent" />
                      <input
                        type="number"
                        name="age"
                        value={formData.age}
                        onChange={handleChange}
                        placeholder="Enter your age"
                        min="13"
                        max="120"
                        className={`input-field pl-12 ${errors.age ? 'border-red-500 focus:ring-red-500' : ''}`}
                      />
                      {errors.age && (
                        <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
                          <AlertCircle className="w-5 h-5 text-red-500" />
                        </div>
                      )}
                    </div>
                    {errors.age && (
                      <p className="form-error">{errors.age}</p>
                    )}
                  </div>

                  <div className="form-group">
                    <label className="form-label">Gender</label>
                    <div className="relative">
                      <Users className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-12 h-12 p-2.5 rounded-lg bg-transparent" />
                      <select
                        name="gender"
                        value={formData.gender}
                        onChange={handleChange}
                        className={`input-field pl-12 ${errors.gender ? 'border-red-500 focus:ring-red-500' : ''}`}
                      >
                        <option value="">Select gender</option>
                        <option value="male">Male</option>
                        <option value="female">Female</option>
                        <option value="other">Other</option>
                      </select>
                      {errors.gender && (
                        <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
                          <AlertCircle className="w-5 h-5 text-red-500" />
                        </div>
                      )}
                    </div>
                    {errors.gender && (
                      <p className="form-error">{errors.gender}</p>
                    )}
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Occupation</label>
                  <div className="relative">
                    <User className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-12 h-12 p-2.5 rounded-lg bg-transparent" />
                    <input
                      type="text"
                      name="occupation"
                      value={formData.occupation}
                      onChange={handleChange}
                      placeholder="Enter your occupation"
                      className={`input-field pl-12 ${errors.occupation ? 'border-red-500 focus:ring-red-500' : ''}`}
                    />
                    {errors.occupation && (
                      <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
                        <AlertCircle className="w-5 h-5 text-red-500" />
                      </div>
                    )}
                  </div>
                  {errors.occupation && (
                    <p className="form-error">{errors.occupation}</p>
                  )}
                </div>
              </motion.div>
            )}

            {/* 步驟3: 確認信息 */}
            {currentStep === 3 && (
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5 }}
                className="space-y-6"
              >
                <div className="card p-6">
                  <h3 className="text-xl font-bold text-white mb-4">Confirm your details</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Username:</span>
                      <span className="text-white">{formData.username}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Email:</span>
                      <span className="text-white">{formData.email}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Age:</span>
                      <span className="text-white">{formData.age} years</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Gender:</span>
                      <span className="text-white">
                        {formData.gender === 'male' ? 'Male' : 
                         formData.gender === 'female' ? 'Female' : 'Other'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Occupation:</span>
                      <span className="text-white">{formData.occupation}</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* 按鈕區域 */}
            <div className="flex justify-between pt-6">
              {currentStep > 1 && (
                <motion.button
                  type="button"
                  onClick={handleBack}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="rounded-xl px-4 py-2 text-white/80 hover:text-white bg-white/10 border border-white/10"
                >
                  Back
                </motion.button>
              )}
              
              <div className="flex-1" />
              
              {currentStep < 3 ? (
                <motion.button
                  type="button"
                  onClick={handleNext}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="rounded-xl bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-2 shadow-lg hover:shadow-xl transition-shadow flex items-center space-x-2"
                >
                  <span>Next</span>
                  <ArrowRight className="w-4 h-4" />
                </motion.button>
              ) : (
                <motion.button
                  type="submit"
                  disabled={loading}
                  whileHover={{ scale: loading ? 1 : 1.02 }}
                  whileTap={{ scale: loading ? 1 : 0.98 }}
                  className="rounded-xl bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-2 shadow-lg hover:shadow-xl transition-shadow flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <>
                      <Loader className="w-5 h-5 animate-spin" />
                      <span>Creating account...</span>
                    </>
                  ) : (
                    <>
                      <span>Create account</span>
                      <CheckCircle className="w-4 h-4" />
                    </>
                  )}
                </motion.button>
              )}
            </div>
          </motion.form>

          {/* 分割線 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.7 }}
            className="my-8 h-px w-full bg-gradient-to-r from-transparent via-white/20 to-transparent"
          />

          {/* 登錄鏈接 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.8 }}
            className="text-center"
          >
            <p className="text-white/70 mb-4">
              Already have an account?
            </p>
            <Link
              to="/login"
              className="w-full flex items-center justify-center space-x-2 text-blue-400 hover:text-blue-300"
            >
              <span>Sign in</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </motion.div>
        </motion.div>

        {/* 底部信息 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.9 }}
          className="text-center mt-8"
        >
          <p className="text-white/60 text-sm">
            By signing up, you agree to our{' '}
            <a href="#" className="text-blue-400 hover:text-blue-300 transition-colors">Terms of Service</a>
            {' '}and{' '}
            <a href="#" className="text-blue-400 hover:text-blue-300 transition-colors">Privacy Policy</a>
          </p>
        </motion.div>
      </div>
    </div>
  )
}

export default Register