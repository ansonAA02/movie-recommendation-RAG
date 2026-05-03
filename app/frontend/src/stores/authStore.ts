import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, type UserProfile } from '../services/api'

interface User {
  id: number
  username: string
  email: string
  age?: number
  gender?: string
  occupation?: string
}

interface AuthState {
  user: User | null
  userProfile: UserProfile | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  initializeAuth: () => void
  login: (username: string, password: string) => Promise<void>
  register: (userData: RegisterData) => Promise<void>
  logout: () => void
  updateUser: (userData: Partial<User>) => void
  fetchUserProfile: () => Promise<void>
  updateUserProfile: (profileData: Partial<UserProfile>) => Promise<void>
  refreshUserProfile: () => Promise<void>
}

interface RegisterData {
  username: string
  email: string
  password: string
  age?: number
  gender?: string
  occupation?: string
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      userProfile: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,

      // 初始化認證狀態
      initializeAuth: () => {
        const state = get()
        if (state.token) {
          // 設置認證頭
          api.defaults.headers.common['Authorization'] = `Bearer ${state.token}`
          set({ isAuthenticated: true })
        }
      },

      login: async (username: string, password: string) => {
        set({ isLoading: true })
        try {
          const response = await api.post('/auth/login', { username, password })
          const { access_token, user } = response.data
          
          // 设置认证头
          api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
          
          set({
            user,
            token: access_token,
            isAuthenticated: true,
            isLoading: false
          })
          
          // 登录后获取用户档案
          await get().fetchUserProfile()
        } catch (error: any) {
          set({ isLoading: false })
          throw new Error(error.response?.data?.detail || 'Login failed')
        }
      },

      register: async (userData: RegisterData) => {
        set({ isLoading: true })
        try {
          const response = await api.post('/auth/register', userData)
          const user = response.data
          
          set({
            user,
            isAuthenticated: false,
            isLoading: false
          })
        } catch (error: any) {
          set({ isLoading: false })
          throw new Error(error.response?.data?.detail || 'Registration failed')
        }
      },

      logout: () => {
        // 清除认证头
        delete api.defaults.headers.common['Authorization']
        
        set({
          user: null,
          userProfile: null,
          token: null,
          isAuthenticated: false,
          isLoading: false
        })
      },

      updateUser: (userData: Partial<User>) => {
        const { user } = get()
        if (user) {
          set({
            user: { ...user, ...userData }
          })
        }
      },

      fetchUserProfile: async () => {
        try {
          const response = await api.get('/profile')
          // 如果API返回null，表示用戶沒有檔案
          set({ userProfile: response.data || null })
        } catch (error: any) {
          console.error('Failed to fetch user profile:', error)
          // 如果获取档案失败，設置為null
          set({ userProfile: null })
        }
      },

      updateUserProfile: async (profileData: Partial<UserProfile>) => {
        try {
          const response = await api.put('/profile', profileData)
          set({ userProfile: response.data })
        } catch (error: any) {
          throw new Error(error.response?.data?.detail || 'Failed to update profile')
        }
      },

      // 刷新用戶資料（用於交互後更新統計數據）
      refreshUserProfile: async () => {
        try {
          const response = await api.get('/profile')
          set({ userProfile: response.data })
        } catch (error: any) {
          console.error('Failed to refresh user profile:', error)
          // 靜默失敗，不影響用戶體驗
        }
      }
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated
      })
    }
  )
)
