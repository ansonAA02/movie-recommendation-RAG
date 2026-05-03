import React, { useEffect, useState, useCallback } from 'react'
import { useAuthStore } from '../stores/authStore'
import ProfileSetupWizard from './ProfileSetupWizard'
import LoadingSpinner from './LoadingSpinner'
import { api } from '../services/api'

interface OnboardingGuardProps {
  children: React.ReactNode
}

const OnboardingGuard: React.FC<OnboardingGuardProps> = ({ children }) => {
  const { user, fetchUserProfile, isAuthenticated } = useAuthStore()
  const [isChecking, setIsChecking] = useState(true)
  const [showProfileSetup, setShowProfileSetup] = useState(false)

  // 使用 useCallback 穩定 fetchUserProfile 函數
  const stableFetchUserProfile = useCallback(fetchUserProfile, [])

  useEffect(() => {
    const checkOnboardingStatus = async () => {
      console.log('OnboardingGuard: Checking status', { isAuthenticated, user: !!user })

      if (!isAuthenticated || !user) {
        setIsChecking(false)
        return
      }

      try {
        // 以後端狀態為準
        const resp = await api.get('/onboarding/status')
        const needs = Boolean(resp.data?.needs_onboarding)
        setShowProfileSetup(needs)

        // 順帶同步一次用戶資料，供後續頁面使用
        await stableFetchUserProfile()
      } catch (error) {
        console.error('Error checking onboarding status:', error)
        setShowProfileSetup(true)
      } finally {
        setIsChecking(false)
      }
    }

    checkOnboardingStatus()
  }, [isAuthenticated, user, stableFetchUserProfile])

  const handleProfileSetupComplete = () => {
    setShowProfileSetup(false)
    // 刷新用戶資料
    stableFetchUserProfile()
  }

  const handleProfileSetupSkip = () => {
    setShowProfileSetup(false)
    // 刷新用戶資料
    stableFetchUserProfile()
  }

  // 如果正在檢查，顯示加載狀態
  if (isChecking) {
    return <LoadingSpinner message="Checking user setup..." />
  }

  // 如果需要檔案設置，顯示檔案設置組件
  if (showProfileSetup) {
    return <ProfileSetupWizard onComplete={handleProfileSetupComplete} onSkip={handleProfileSetupSkip} />
  }

  // 否則顯示正常內容
  return <>{children}</>
}

export default OnboardingGuard
