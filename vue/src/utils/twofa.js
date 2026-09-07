import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'

export async function prompt2FA(title = '身份验证', message = '请输入 6 位 Google 验证器验证码') {
  try {
    const { value } = await ElMessageBox.prompt(message, title, {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '请输入 6 位验证码',
      inputPattern: /^\d{6}$/,
      inputErrorMessage: '请输入 6 位数字验证码',
      closeOnClickModal: false
    })
    return value
  } catch (_) {
    return null
  }
}

function _userHas2FA() {
  try {
    const auth = useAuthStore()
    const u = auth && auth.user
    if (!u) return false
    return (
      u.google_2fa_enabled === 1 ||
      u.google_2fa_enabled === true ||
      u.twofa_enabled === true ||
      Number(u.google_2fa_enabled) === 1
    )
  } catch (_) {
    return false
  }
}

export async function require2FA(action) {
  if (!_userHas2FA()) {
    if (typeof action === 'function') {
      try {
        await action('')
        return true
      } catch (err) {
        return false
      }
    }
    return ''
  }
  const otp = await prompt2FA()
  if (otp === null) return false
  if (action) {
    try {
      await action(otp)
      return true
    } catch (err) {
      return false
    }
  }
  return otp
}

export function maskSecret(secret, visible = 4) {
  if (!secret) return ''
  if (secret.length <= visible * 2) return '*'.repeat(secret.length)
  return secret.slice(0, visible) + '*'.repeat(secret.length - visible * 2) + secret.slice(-visible)
}

export function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function formatRelative(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  const now = Date.now()
  const diff = Math.floor((now - d.getTime()) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`
  return formatDate(dateStr)
}

export function truncate(text, len = 50) {
  if (!text) return ''
  if (text.length <= len) return text
  return text.slice(0, len) + '...'
}

export function shortUuid(uuid) {
  if (!uuid) return ''
  if (uuid.length <= 8) return uuid
  return uuid.slice(0, 8) + '...'
}

export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (_) {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      return true
    } finally {
      document.body.removeChild(ta)
    }
  }
}
