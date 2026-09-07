import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from '../utils/axios'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))
  const tempToken = ref('')
  const requires2FA = ref(false)
  const remember = ref(localStorage.getItem('remember') === 'true')

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username, password) {
    try {
      const response = await axios.post('/api/auth/login', new URLSearchParams({
        username,
        password
      }), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })

      if (response.data.requires_2fa) {
        requires2FA.value = true
        tempToken.value = response.data.temp_token
        return { requires2FA: true }
      }

      token.value = response.data.access_token
      localStorage.setItem('token', token.value)
      requires2FA.value = false
      tempToken.value = ''
      await getMe()
      return { success: true }
    } catch (error) {
      return { success: false, error: error.response?.data?.detail || '登录失败' }
    }
  }

  async function verify2FA(otpCode) {
    try {
      const response = await axios.post('/api/auth/verify-2fa', {
        temp_token: tempToken.value,
        otp_code: otpCode
      })
      token.value = response.data.access_token
      localStorage.setItem('token', token.value)
      requires2FA.value = false
      tempToken.value = ''
      await getMe()
      return { success: true }
    } catch (error) {
      return { success: false, error: error.response?.data?.detail || '2FA 验证失败' }
    }
  }

  function reset2FAState() {
    requires2FA.value = false
    tempToken.value = ''
  }

  async function getMe() {
    try {
      const response = await axios.get('/api/auth/me')
      user.value = response.data
      localStorage.setItem('user', JSON.stringify(user.value))
      return user.value
    } catch (_) {
      return null
    }
  }

  async function logout() {
    try {
      if (token.value) {
        await axios.post('/api/auth/logout')
      }
    } catch (_) {
    }
    token.value = ''
    user.value = null
    tempToken.value = ''
    requires2FA.value = false
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  function setRemember(val) {
    remember.value = val
    localStorage.setItem('remember', val ? 'true' : 'false')
  }

  return {
    token,
    user,
    tempToken,
    requires2FA,
    remember,
    isLoggedIn,
    isAdmin,
    login,
    verify2FA,
    reset2FAState,
    getMe,
    logout,
    setRemember
  }
})
