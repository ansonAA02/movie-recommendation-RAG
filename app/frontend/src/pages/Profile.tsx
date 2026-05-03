import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { User, Mail, Calendar, Briefcase, Edit3, Save, X, Star, Heart, Settings, Film } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { authApi } from '../services/api'
import toast from 'react-hot-toast'

const Profile = () => {
  const { user, userProfile, updateUser, fetchUserProfile, updateUserProfile } = useAuthStore()
  const normalizeGenderValue = (value?: string) => {
    if (value === 'M') return 'male'
    if (value === 'F') return 'female'
    return value || ''
  }

  const getGenderLabel = (value?: string) => {
    const normalized = normalizeGenderValue(value)
    if (normalized === 'male') return 'Male'
    if (normalized === 'female') return 'Female'
    if (normalized === 'other') return 'Other'
    return 'Not set'
  }

  const [isEditing, setIsEditing] = useState(false)
  const [isEditingPreferences, setIsEditingPreferences] = useState(false)
  const [formData, setFormData] = useState({
    username: user?.username || '',
    email: user?.email || '',
    age: user?.age || 0,
    gender: normalizeGenderValue(user?.gender),
    occupation: user?.occupation || ''
  })
  const [preferencesData, setPreferencesData] = useState({
    preferred_genres: userProfile?.preferred_genres || [],
    min_rating_threshold: userProfile?.min_rating_threshold || 3.0,
    max_runtime: userProfile?.max_runtime || null,
    min_runtime: userProfile?.min_runtime || null,
  })

  // 获取用户档案
  useEffect(() => {
    if (user && !userProfile) {
      fetchUserProfile()
    }
  }, [user, userProfile, fetchUserProfile])

  // 定期刷新用戶資料以獲取最新統計數據
  useEffect(() => {
    if (user && userProfile) {
      const interval = setInterval(() => {
        fetchUserProfile()
      }, 30000) // 每30秒刷新一次
      
      return () => clearInterval(interval)
    }
  }, [user, userProfile, fetchUserProfile])

  // 更新偏好数据
  useEffect(() => {
    if (userProfile) {
      setPreferencesData({
        preferred_genres: userProfile.preferred_genres || [],
        min_rating_threshold: userProfile.min_rating_threshold || 3.0,
        max_runtime: userProfile.max_runtime || null,
        min_runtime: userProfile.min_runtime || null,
      })
    }
  }, [userProfile])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: name === 'age' ? parseInt(value) || 0 : value
    }))
  }

  const handlePreferencesChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target
    setPreferencesData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : 
              type === 'number' ? (value ? parseFloat(value) : null) : value
    }))
  }

  const handleSave = async () => {
    try {
      const payload = {
        email: formData.email,
        age: formData.age || undefined,
        gender: formData.gender || undefined,
        occupation: formData.occupation || undefined,
      }

      const updatedUser = await authApi.updateCurrentUser(payload)
      updateUser(updatedUser)
      setIsEditing(false)
      toast.success('Personal information updated successfully!')
    } catch (error) {
      toast.error('Update failed, please try again')
    }
  }

  const handleSavePreferences = async () => {
    try {
      // Convert null values to undefined for API compatibility
      const apiData = {
        ...preferencesData,
        max_runtime: preferencesData.max_runtime || undefined,
        min_runtime: preferencesData.min_runtime || undefined
      }
      await updateUserProfile(apiData)
      setIsEditingPreferences(false)
      toast.success('Preferences updated successfully！')
    } catch (error: any) {
      toast.error(error.message || 'Update failed, please try again')
    }
  }

  const handleCancel = () => {
    setFormData({
      username: user?.username || '',
      email: user?.email || '',
      age: user?.age || 0,
      gender: normalizeGenderValue(user?.gender),
      occupation: user?.occupation || ''
    })
    setIsEditing(false)
  }

  useEffect(() => {
    if (user) {
      setFormData({
        username: user.username || '',
        email: user.email || '',
        age: user.age || 0,
        gender: normalizeGenderValue(user.gender),
        occupation: user.occupation || '',
      })
    }
  }, [user])

  const handleCancelPreferences = () => {
    if (userProfile) {
      setPreferencesData({
        preferred_genres: userProfile.preferred_genres || [],
        min_rating_threshold: userProfile.min_rating_threshold || 3.0,
        max_runtime: userProfile.max_runtime || null,
        min_runtime: userProfile.min_runtime || null,
      })
    }
    setIsEditingPreferences(false)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-purple-900">
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
        {/* Hero Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-3xl mb-6 shadow-glow">
            <User className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-5xl font-bold text-white mb-4">
            <span className="text-gradient">Profile</span>
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto">
            Manage your personal information, preferences, and viewing statistics
          </p>
        </motion.div>

        {/* Personal Information Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="card-elevated"
        >
        {/* 头像区域 */}
        <div className="text-center mb-8">
          <div className="w-24 h-24 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full mx-auto mb-4 flex items-center justify-center">
            <User className="h-12 w-12 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-white">{user?.username}</h2>
          <p className="text-white/60">Movie lover</p>
        </div>

        {/* 编辑按钮 */}
        <div className="flex justify-end mb-6">
          {!isEditing ? (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setIsEditing(true)}
              className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors duration-200"
            >
              <Edit3 className="h-4 w-4" />
              <span>Edit information</span>
            </motion.button>
          ) : (
            <div className="flex space-x-2">
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleSave}
                className="flex items-center space-x-2 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors duration-200"
              >
                <Save className="h-4 w-4" />
                <span>Save</span>
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleCancel}
                className="flex items-center space-x-2 bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg transition-colors duration-200"
              >
                <X className="h-4 w-4" />
                <span>Cancel</span>
              </motion.button>
            </div>
          )}
        </div>

        {/* 个人信息表单 */}
        <div className="space-y-6">
          {/* 用户名 */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              <User className="h-4 w-4 inline mr-2" />
              Username
            </label>
            {isEditing ? (
              <input
                type="text"
                name="username"
                value={formData.username}
                onChange={handleInputChange}
                className="input-field"
                disabled
              />
            ) : (
              <p className="text-white/80 py-2">{user?.username}</p>
            )}
          </div>

          {/* 邮箱 */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              <Mail className="h-4 w-4 inline mr-2" />
              Email
            </label>
            {isEditing ? (
              <input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleInputChange}
                className="input-field"
              />
            ) : (
              <p className="text-white/80 py-2">{user?.email}</p>
            )}
          </div>

          {/* 年龄 */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              <Calendar className="h-4 w-4 inline mr-2" />
              Age
            </label>
            {isEditing ? (
              <input
                type="number"
                name="age"
                value={formData.age}
                onChange={handleInputChange}
                className="input-field"
                min="1"
                max="120"
              />
            ) : (
              <p className="text-white/80 py-2">{user?.age || 'Not set'}</p>
            )}
          </div>

          {/* 性别 */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Gender
            </label>
            {isEditing ? (
              <select
                name="gender"
                value={formData.gender}
                onChange={handleInputChange}
                className="input-field"
              >
                <option value="">Please select gender</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            ) : (
              <p className="text-white/80 py-2">
                {getGenderLabel(user?.gender)}
              </p>
            )}
          </div>

          {/* 职业 */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              <Briefcase className="h-4 w-4 inline mr-2" />
              Occupation
            </label>
            {isEditing ? (
              <input
                type="text"
                name="occupation"
                value={formData.occupation}
                onChange={handleInputChange}
                className="input-field"
                placeholder="Please enter your occupation"
              />
            ) : (
              <p className="text-white/80 py-2">{user?.occupation || 'Not set'}</p>
            )}
          </div>
        </div>
      </motion.div>

      {/* 统计信息 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="grid grid-cols-1 md:grid-cols-4 gap-6"
      >
        <div className="bg-white/10 backdrop-blur-md rounded-lg p-6 border border-white/20 text-center">
          <Star className="h-8 w-8 text-yellow-400 mx-auto mb-2" />
          <div className="text-2xl font-bold text-white mb-2">{userProfile?.total_ratings || 0}</div>
          <div className="text-white/60 text-sm">Rated movies</div>
        </div>
        
        <div className="bg-white/10 backdrop-blur-md rounded-lg p-6 border border-white/20 text-center">
          <Heart className="h-8 w-8 text-red-400 mx-auto mb-2" />
          <div className="text-2xl font-bold text-white mb-2">{userProfile?.total_favorites || 0}</div>
          <div className="text-white/60 text-sm">Favorited movies</div>
        </div>
        
        <div className="bg-white/10 backdrop-blur-md rounded-lg p-6 border border-white/20 text-center">
          <Heart className="h-8 w-8 text-pink-400 mx-auto mb-2" />
          <div className="text-2xl font-bold text-white mb-2">{userProfile?.total_likes || 0}</div>
          <div className="text-white/60 text-sm">Liked movies</div>
        </div>

        <div className="bg-white/10 backdrop-blur-md rounded-lg p-6 border border-white/20 text-center">
          <Film className="h-8 w-8 text-purple-400 mx-auto mb-2" />
          <div className="text-2xl font-bold text-white mb-2">{userProfile?.total_views || 0}</div>
          <div className="text-white/60 text-sm">Watched movies</div>
        </div>
      </motion.div>

      {/* 第二行統計數據 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6"
      >
        <div className="bg-white/10 backdrop-blur-md rounded-lg p-6 border border-white/20 text-center">
          <Star className="h-8 w-8 text-yellow-400 mx-auto mb-2" />
          <div className="text-2xl font-bold text-white mb-2">{userProfile?.average_rating_given?.toFixed(1) || '0.0'}</div>
          <div className="text-white/60 text-sm">Average rating</div>
        </div>
        
      </motion.div>

      {/* 用户偏好信息 */}
      {userProfile && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="bg-white/10 backdrop-blur-md rounded-lg p-8 border border-white/20"
        >
          <h3 className="text-xl font-bold text-white mb-6 flex items-center">
            <Film className="h-5 w-5 mr-2" />
            Viewing preferences
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            <div>
                  <h4 className="text-white font-medium mb-3">Most rated year</h4>
              <p className="text-white/80">
                {userProfile.most_rated_year || 'No data'}
              </p>
            </div>
            
            {userProfile.preferred_genres && userProfile.preferred_genres.length > 0 && (
              <div className="md:col-span-2">
                <h4 className="text-white font-medium mb-3">Preferred genres</h4>
                <div className="flex flex-wrap gap-2">
                  {userProfile.preferred_genres.map((genre, index) => (
                    <span
                      key={index}
                      className="px-3 py-1 bg-blue-600/20 text-blue-300 rounded-full text-sm"
                    >
                      {genre}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </motion.div>
      )}

      {/* 偏好设置 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
        className="bg-white/10 backdrop-blur-md rounded-lg p-8 border border-white/20"
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-white flex items-center">
            <Settings className="h-5 w-5 mr-2" />
            Preferences settings
          </h3>
          {!isEditingPreferences ? (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setIsEditingPreferences(true)}
              className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors duration-200"
            >
              <Edit3 className="h-4 w-4" />
              <span>Edit settings</span>
            </motion.button>
          ) : (
            <div className="flex space-x-2">
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleSavePreferences}
                className="flex items-center space-x-2 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors duration-200"
              >
                <Save className="h-4 w-4" />
                <span>Save</span>
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleCancelPreferences}
                className="flex items-center space-x-2 bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg transition-colors duration-200"
              >
                <X className="h-4 w-4" />
                <span>Cancel</span>
              </motion.button>
            </div>
          )}
        </div>
        
        <div className="space-y-6">
          {/* 推荐算法设置 */}
          <div>
            {/* 推薦算法設置已移除 */}
          </div>

          {/* 最低评分阈值 */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Minimum Rating Threshold
            </label>
            {isEditingPreferences ? (
              <input
                type="number"
                name="min_rating_threshold"
                value={preferencesData.min_rating_threshold}
                onChange={handlePreferencesChange}
                className="input-field"
                min="1"
                max="5"
                step="0.1"
              />
            ) : (
              <p className="text-white/80 py-2">{preferencesData.min_rating_threshold} stars</p>
            )}
          </div>

          {/* 时长偏好 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Minimum runtime (minutes)
              </label>
              {isEditingPreferences ? (
                <input
                  type="number"
                  name="min_runtime"
                  value={preferencesData.min_runtime || ''}
                  onChange={handlePreferencesChange}
                  className="input-field"
                  placeholder="No limit"
                />
              ) : (
                <p className="text-white/80 py-2">{preferencesData.min_runtime || 'No limit'}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Maximum runtime (minutes)
              </label>
              {isEditingPreferences ? (
                <input
                  type="number"
                  name="max_runtime"
                  value={preferencesData.max_runtime || ''}
                  onChange={handlePreferencesChange}
                  className="input-field"
                  placeholder="No limit"
                />
              ) : (
                <p className="text-white/80 py-2">{preferencesData.max_runtime || 'No limit'}</p>
              )}
            </div>
          </div>

          {/* AI 推薦設置已移除 */}
        </div>
        </motion.div>
      </div>
    </div>
  )
}

export default Profile
