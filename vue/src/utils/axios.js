import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const instance = axios.create({
  baseURL: '',
  timeout: 60000
})

// 跨域调试日志：开发模式输出请求/响应详情，便于排查 CORS / CSP 问题
const _DEBUG = import.meta.env.DEV

function _logCors(tag, msg) {
  if (!_DEBUG) return
  try {
    // eslint-disable-next-line no-console
    console.log(`[AXIOS-${tag}] ${msg}`)
  } catch (e) {}
}

instance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    if (_DEBUG) {
      const fullUrl = (config.baseURL || '') + (config.url || '')
      _logCors('REQ', `${(config.method || 'get').toUpperCase()} ${fullUrl}`)
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

instance.interceptors.response.use(
  (response) => {
    if (_DEBUG) {
      const acao = response.headers?.['access-control-allow-origin'] || '-'
      _logCors('RESP', `${response.config?.method?.toUpperCase() || 'GET'} ${response.config?.url || ''} → ${response.status} acao=${acao}`)
    }
    return response
  },
  (error) => {
    const status = error.response?.status
    const message = error.response?.data?.detail || error.message || '请求失败'

    // 关键：无 error.response 通常是 CORS 被浏览器拦截 / 网络断开 / 超时
    // CORS 错误特征：error.message 包含 "Network Error" 且浏览器 console 有 CORS 警告
    if (!error.response) {
      const isCorsLikely = /network error/i.test(error.message || '')
      _logCors('BLOCKED', `${error.config?.method?.toUpperCase() || 'GET'} ${error.config?.url || ''} → no response (${error.message})${isCorsLikely ? ' [CORS likely]' : ''}`)
    } else if (_DEBUG) {
      const acao = error.response.headers?.['access-control-allow-origin'] || '-'
      _logCors('ERR', `${error.config?.method?.toUpperCase() || 'GET'} ${error.config?.url || ''} → ${status} acao=${acao}`)
    }

    if (status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      ElMessage.warning('登录已过期，请重新登录')
      window.location.href = '/login'
    } else if (status === 403) {
      ElMessage.error('没有权限执行此操作')
    } else if (status === 404) {
      ElMessage.error('请求的资源不存在')
    } else if (status === 422) {
      ElMessage.error('请求参数错误')
    } else if (status && status >= 500) {
      ElMessage.error('服务器错误，请稍后重试')
    } else if (!error.response) {
      // 区分 CORS 错误与普通网络错误，给用户更明确的提示
      const isCorsLikely = /network error/i.test(error.message || '')
      ElMessage.error(isCorsLikely ? '跨域/网络请求被阻止，请检查 CORS 配置' : '网络连接失败，请检查网络')
    }

    return Promise.reject(error)
  }
)

export default instance
