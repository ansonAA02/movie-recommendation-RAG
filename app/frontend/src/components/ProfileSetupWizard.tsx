import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { 
  Heart, 
  Settings, 
  CheckCircle, 
  ArrowRight, 
  ArrowLeft,
  SkipForward,
  Sparkles
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

interface ProfileSetupWizardProps {
  onComplete: () => void
  onSkip: () => void
}

const ProfileSetupWizard = ({ onComplete, onSkip }: ProfileSetupWizardProps) => {
  const { updateUserProfile } = useAuthStore()
  const [currentStep, setCurrentStep] = useState(0)
  const [formData, setFormData] = useState({
    // Preferences
    preferred_genres: [] as string[],
    preferred_directors_text: '',
    preferred_actors_text: '',
    preferred_languages_text: '',
    preferred_countries_text: '',
    min_rating_threshold: 3.0,
    max_runtime: null as number | null,
    min_runtime: null as number | null,
    // Settings (簡化)
  })

  const steps = [
    {
      id: 'preferences',
      title: 'Movie Preferences',
      description: 'What do you like to watch?',
      icon: Heart,
      color: 'from-pink-500 to-pink-600'
    },
    {
      id: 'settings',
      title: 'Recommendation Settings',
      description: 'Customize your experience',
      icon: Settings,
      color: 'from-purple-500 to-purple-600'
    }
  ]

  const genres = [
    'Action', 'Adventure', 'Animation', 'Comedy', 'Crime', 'Documentary',
    'Drama', 'Family', 'Fantasy', 'History', 'Horror', 'Music', 'Mystery',
    'Romance', 'Sci-Fi', 'Sport', 'Thriller', 'War', 'Western'
  ]

  const handleInputChange = (field: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }))
  }

  const handleGenreToggle = (genre: string) => {
    setFormData(prev => ({
      ...prev,
      preferred_genres: prev.preferred_genres.includes(genre)
        ? prev.preferred_genres.filter(g => g !== genre)
        : [...prev.preferred_genres, genre]
    }))
  }

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1)
    }
  }

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handleComplete = async () => {
    try {
      // 驗證：至少選1個類型
      if (!formData.preferred_genres || formData.preferred_genres.length === 0) {
        toast.error('Please select at least 1 preferred genre')
        return
      }

      // 轉換逗號分隔為陣列
      const directors = formData.preferred_directors_text.split(',').map(s => s.trim()).filter(Boolean)
      const actors = formData.preferred_actors_text.split(',').map(s => s.trim()).filter(Boolean)
      const languages = formData.preferred_languages_text.split(',').map(s => s.trim()).filter(Boolean)
      const countries = formData.preferred_countries_text.split(',').map(s => s.trim()).filter(Boolean)

      await updateUserProfile({
        ...formData,
        preferred_genres: formData.preferred_genres,
        preferred_directors: directors,
        preferred_actors: actors,
        preferred_languages: languages,
        preferred_countries: countries,
        max_runtime: formData.max_runtime || undefined,
        min_runtime: formData.min_runtime || undefined,
        profile_setup_completed: true,
        setup_skipped: false,
        setup_completed_at: new Date().toISOString()
      })
      
      toast.success('Profile setup completed!')
      onComplete()
    } catch (error) {
      toast.error('Failed to save profile')
    }
  }

  const handleSkip = async () => {
    try {
      // 創建一個基本的用戶檔案，標記為跳過
      await updateUserProfile({
        preferred_genres: [],
        preferred_directors: [],
        preferred_actors: [],
        preferred_languages: [],
        preferred_countries: [],
        min_rating_threshold: 3.0,
        profile_setup_completed: false,
        setup_skipped: true,
        setup_completed_at: new Date().toISOString()
      })
      
      toast.success('Profile setup skipped')
      onSkip()
    } catch (error) {
      toast.error('Failed to skip profile setup')
    }
  }

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-white mb-4">
                Preferred Genres (Select multiple)
              </label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {genres.map((genre) => (
                  <motion.button
                    key={genre}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handleGenreToggle(genre)}
                    className={`p-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                      formData.preferred_genres.includes(genre)
                        ? 'bg-pink-500 text-white'
                        : 'bg-white/20 text-white hover:bg-white/30'
                    }`}
                  >
                    {genre}
                  </motion.button>
                ))}
              </div>
            </div>
            
            {/* Free-text preferences */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-white mb-2">Preferred Directors (comma-separated)</label>
                <input
                  type="text"
                  value={formData.preferred_directors_text}
                  onChange={(e) => handleInputChange('preferred_directors_text', e.target.value)}
                  className="input-field"
                  placeholder="e.g. Christopher Nolan, Ridley Scott"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white mb-2">Preferred Actors (comma-separated)</label>
                <input
                  type="text"
                  value={formData.preferred_actors_text}
                  onChange={(e) => handleInputChange('preferred_actors_text', e.target.value)}
                  className="input-field"
                  placeholder="e.g. Tom Hanks, Scarlett Johansson"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white mb-2">Preferred Languages (comma-separated)</label>
                <input
                  type="text"
                  value={formData.preferred_languages_text}
                  onChange={(e) => handleInputChange('preferred_languages_text', e.target.value)}
                  className="input-field"
                  placeholder="e.g. English, Japanese"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white mb-2">Preferred Countries/Regions (comma-separated)</label>
                <input
                  type="text"
                  value={formData.preferred_countries_text}
                  onChange={(e) => handleInputChange('preferred_countries_text', e.target.value)}
                  className="input-field"
                  placeholder="e.g. US, HK, JP"
                />
              </div>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Minimum Rating Threshold
              </label>
              <input
                type="number"
                value={formData.min_rating_threshold}
                onChange={(e) => handleInputChange('min_rating_threshold', parseFloat(e.target.value))}
                className="input-field"
                min="1"
                max="5"
                step="0.1"
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-white mb-2">
                  Min Runtime (minutes)
                </label>
                <input
                  type="number"
                  value={formData.min_runtime || ''}
                  onChange={(e) => handleInputChange('min_runtime', e.target.value ? parseInt(e.target.value) : null)}
                  className="input-field"
                  placeholder="No limit"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white mb-2">
                  Max Runtime (minutes)
                </label>
                <input
                  type="number"
                  value={formData.max_runtime || ''}
                  onChange={(e) => handleInputChange('max_runtime', e.target.value ? parseInt(e.target.value) : null)}
                  className="input-field"
                  placeholder="No limit"
                />
              </div>
            </div>
          </div>
        )
      
      case 1:
        return (
          <div className="space-y-6">
            <div className="text-center text-white/60">
              <p>Recommendation setup has been simplified, focused on core functionality</p>
            </div>
          </div>
        )
      
      default:
        return null
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-purple-900 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-2xl"
      >
        {/* Progress Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-3xl mb-6 shadow-glow">
            <Sparkles className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-4xl font-bold text-white mb-2">
            <span className="text-gradient">Profile Setup</span>
          </h1>
          <p className="text-xl text-gray-300">
            Let's personalize your movie experience
          </p>
        </div>

        {/* Progress Steps */}
        <div className="flex items-center justify-center mb-8">
          {steps.map((step, index) => (
            <div key={step.id} className="flex items-center">
              <div className={`flex items-center justify-center w-12 h-12 rounded-full ${
                index <= currentStep 
                  ? 'bg-gradient-to-r ' + step.color 
                  : 'bg-white/20'
              }`}>
                {index < currentStep ? (
                  <CheckCircle className="w-6 h-6 text-white" />
                ) : (
                  <step.icon className="w-6 h-6 text-white" />
                )}
              </div>
              {index < steps.length - 1 && (
                <div className={`w-16 h-1 mx-2 ${
                  index < currentStep ? 'bg-gradient-to-r ' + step.color : 'bg-white/20'
                }`} />
              )}
            </div>
          ))}
        </div>

        {/* Step Content */}
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          className="card-elevated mb-8"
        >
          <div className="text-center mb-6">
            <div className={`inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br ${steps[currentStep].color} rounded-2xl mb-4`}>
              {React.createElement(steps[currentStep].icon, { className: "w-8 h-8 text-white" })}
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">
              {steps[currentStep].title}
            </h2>
            <p className="text-gray-300">
              {steps[currentStep].description}
            </p>
          </div>

          {renderStepContent()}
        </motion.div>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleSkip}
            className="flex items-center space-x-2 text-white/60 hover:text-white transition-colors"
          >
            <SkipForward className="w-4 h-4" />
            <span>Skip Setup</span>
          </motion.button>

          <div className="flex items-center space-x-4">
            {currentStep > 0 && (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handlePrevious}
                className="btn-ghost flex items-center space-x-2"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Previous</span>
              </motion.button>
            )}

            {currentStep < steps.length - 1 ? (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleNext}
                className="btn-primary flex items-center space-x-2"
              >
                <span>Next</span>
                <ArrowRight className="w-4 h-4" />
              </motion.button>
            ) : (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleComplete}
                className="btn-primary flex items-center space-x-2"
              >
                <CheckCircle className="w-4 h-4" />
                <span>Complete Setup</span>
              </motion.button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}

export default ProfileSetupWizard
