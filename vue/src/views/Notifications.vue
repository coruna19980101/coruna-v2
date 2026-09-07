<template>
  <div class="notifications-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">通知中心</div>
        <div class="page-subtitle">系统实时通知，支持 SSE 推送与浏览器系统通知</div>
      </div>
      <div style="display:flex;gap:8px;">
        <el-badge v-if="unread > 0" :value="unread" class="item">
          <el-button type="primary" plain @click="markAllRead">全部标记已读</el-button>
        </el-badge>
        <el-button v-else type="primary" plain disabled>全部已读</el-button>
        <el-button type="danger" plain @click="clearAll">清空通知</el-button>
      </div>
    </div>

    <div class="notify-settings">
      <div class="notify-setting-row">
        <el-switch
          v-model="notifyEnabled"
          @change="handleNotifySwitchChange"
          @click.capture="onSwitchCaptureClick"
          :loading="permissionRequesting"
        />
        <span class="notify-switch-label">浏览器主动通知</span>
        <el-tag size="small" :type="permissionTagType" effect="plain">
          {{ permissionText }}
        </el-tag>
        <el-button
          v-if="permission === 'default'"
          type="primary"
          size="small"
          plain
          @click="requestNotifyPermission"
          :loading="permissionRequesting"
        >立即授权</el-button>
        <el-button
          v-else-if="permission === 'denied'"
          type="warning"
          size="small"
          plain
          @click="openSiteSettingsHelp"
        >如何开启</el-button>
        <el-button
          v-if="notifyEnabled && permission === 'granted'"
          size="small"
          @click="fireTestNotification"
          plain
        >发送测试通知</el-button>
      </div>
      <div class="notify-setting-row">
        <el-switch
          v-model="pageToastEnabled"
          @change="handlePageToastSwitchChange"
        />
        <span class="notify-switch-label">页面悬浮通知</span>
        <el-tag size="small" type="success" effect="plain" v-if="pageToastEnabled">已启用</el-tag>
        <el-tag size="small" type="info" effect="plain" v-else>已关闭</el-tag>
      </div>
      <div class="notify-hint" v-if="notifyEnabled && permission === 'default'">
        点击右侧「立即授权」按钮，在浏览器弹窗中点击 <b>允许</b>，之后新设备上线等事件会弹出桌面提醒
      </div>
      <div class="notify-hint notify-hint--warn" v-else-if="notifyEnabled && permission === 'denied'">
        权限被浏览器拒绝，请点击「如何开启」，或在地址栏左侧的「站点设置」里把通知权限设为「允许」后刷新页面
      </div>
      <div class="notify-hint" v-if="!pageToastEnabled && notifyEnabled">
        已关闭页面内悬浮通知，仅浏览器系统通知会弹出
      </div>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.category" placeholder="分类" clearable style="width:160px;" @change="loadList">
        <el-option label="设备" value="device" />
        <el-option label="窃取数据" value="exfil" />
        <el-option label="命令执行" value="command" />
        <el-option label="系统" value="system" />
        <el-option label="告警" value="alert" />
      </el-select>
      <el-select v-model="filters.read" placeholder="已读状态" clearable style="width:140px;" @change="loadList">
        <el-option label="未读" :value="false" />
        <el-option label="已读" :value="true" />
      </el-select>
      <el-button type="primary" @click="loadList">查询</el-button>
    </div>

    <div class="notification-list">
      <div
        v-for="n in list"
        :key="n.id"
        class="notify-item"
        :class="{ unread: !n.read }"
        @click="openNotify(n)"
      >
        <div class="notify-icon" :class="iconClass(n)">
          <el-icon><component :is="iconName(n)" /></el-icon>
        </div>
        <div class="notify-body" style="flex:1;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong style="color:#303133;">{{ n.title }}</strong>
            <span class="text-muted" style="font-size:12px;">{{ formatRelative(n.created_at || n.time) }}</span>
          </div>
          <div class="notify-content text-muted">{{ n.description || n.message || n.content }}</div>
          <div style="margin-top:4px;display:flex;gap:6px;flex-wrap:wrap;">
            <el-tag v-if="n.category" size="small" effect="plain" :type="catTag(n.category)">{{ n.category }}</el-tag>
            <span v-if="n.related_device_uuid" class="mono text-muted" style="font-size:12px;">设备: {{ shortUuid(n.related_device_uuid) }}</span>
          </div>
        </div>
        <div class="notify-actions">
          <el-checkbox v-if="!n.read" :model-value="true" @click.stop="markRead(n)" title="标记已读">已读</el-checkbox>
          <el-button type="danger" link size="small" @click.stop="deleteOne(n)">删除</el-button>
        </div>
      </div>
      <el-empty v-if="!list.length" description="暂无通知" />
    </div>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :page-sizes="[20, 50, 100]"
      :total="total"
      layout="total, sizes, prev, pager, next"
      background
      style="justify-content:flex-end;margin-top:16px;"
      @current-change="loadList"
      @size-change="loadList"
    />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Iphone, DataLine, Promotion, Setting, Warning, Bell } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatRelative, shortUuid } from '../utils/twofa'

const LS_KEY = 'notify_enabled'
const LS_PAGE_TOAST_KEY = 'page_toast_enabled'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const unread = ref(0)
const filters = reactive({ category: '', read: null })

const notifyEnabled = ref(localStorage.getItem(LS_KEY) === 'true')
const pageToastEnabled = ref(localStorage.getItem(LS_PAGE_TOAST_KEY) !== 'false')
const permissionRequesting = ref(false)

const permission = ref(
  (typeof window !== 'undefined' && 'Notification' in window) ? Notification.permission : 'unsupported'
)

let permissionInterval = null

function catTag(c) { return { device: 'success', exfil: 'warning', command: 'primary', system: 'info', alert: 'danger' }[c] || 'info' }
function iconName(n) {
  return { device: Iphone, exfil: DataLine, command: Promotion, system: Setting, alert: Warning }[n.category] || Bell
}
function iconClass(n) {
  return { device: 'ic-device', exfil: 'ic-exfil', command: 'ic-cmd', system: 'ic-sys', alert: 'ic-alert' }[n.category] || 'ic-default'
}

const permissionText = computed(() => {
  if (permission.value === 'granted') return '权限已允许'
  if (permission.value === 'denied') return '权限被拒绝'
  if (permission.value === 'default') return '尚未授权'
  return '浏览器不支持'
})
const permissionTagType = computed(() => {
  if (permission.value === 'granted') return 'success'
  if (permission.value === 'denied') return 'danger'
  if (permission.value === 'default') return 'warning'
  return 'info'
})

function openNotify(n) {
  if (!n.read) markRead(n)
}

async function markRead(n) {
  try {
    await axios.put(`/api/notifications/${n.id}/read`)
    n.read = true
    unread.value = Math.max(0, unread.value - 1)
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '标记失败'
    ElMessage.error(msg)
  }
}

async function markAllRead() {
  try {
    await axios.put('/api/notifications/read')
    list.value.forEach(n => (n.read = true))
    unread.value = 0
    ElMessage.success('已全部标记为已读')
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '操作失败'
    ElMessage.error(msg)
  }
}

async function deleteOne(n) {
  try {
    await ElMessageBox.confirm('删除该通知？', '删除', { type: 'warning' })
    await axios.delete(`/api/notifications/${n.id}`)
    list.value = list.value.filter(x => x.id !== n.id)
    total.value = Math.max(0, total.value - 1)
    if (!n.read) unread.value = Math.max(0, unread.value - 1)
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}

async function clearAll() {
  try {
    await ElMessageBox.confirm('清空所有通知？此操作不可恢复。', '清空通知', { type: 'warning' })
    await axios.delete('/api/notifications')
    list.value = []
    total.value = 0
    unread.value = 0
    ElMessage.success('已清空')
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '清空失败'
      ElMessage.error(msg)
    }
  }
}

async function loadList() {
  try {
    const skip = (page.value - 1) * pageSize.value
    const params = { skip, limit: pageSize.value }
    if (filters.category) params.category = filters.category
    if (filters.read === false) params.unread_only = true
    const res = await axios.get('/api/notifications', { params })
    const items = (res.data?.items || res.data || []).map(n => ({
      ...n,
      read: !(n.is_read === 0 || n.is_read === false)
    }))
    list.value = (filters.read === true) ? items.filter(n => n.read) : items
    total.value = res.data?.total ?? list.value.length
    unread.value = typeof res.data?.unread_count === 'number' ? res.data.unread_count : list.value.filter(n => !n.read).length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '通知加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
    unread.value = 0
  }
}

function handlePushNotification(event) {
  const item = event && event.detail
  if (!item) return
  const existingId = typeof item.id === 'number' ? item.id : null
  if (existingId && list.value.some(n => n.id === existingId)) return
  list.value.unshift({
    id: item.id ?? Date.now(),
    title: item.title || '',
    description: item.description || item.message || '',
    category: item.type || item.category || 'info',
    type: item.type || item.category || 'info',
    read: false,
    created_at: item.created_at || new Date().toISOString(),
    related_device_uuid: item.related_device_uuid || null,
    related_resource_type: item.related_resource_type || null,
    related_resource_id: item.related_resource_id || null,
  })
  total.value = (total.value ?? list.value.length - 1) + 1
  unread.value = (unread.value ?? 0) + 1
}

function fireTestNotification() {
  try {
    const n = new Notification('Coruna 通知已开启 ✅', {
      body: '当有新设备上线、访问或重要事件时，您会收到浏览器桌面通知（点击此通知跳转到通知中心）',
      tag: 'coruna-notify-test-' + Date.now(),
    })
    if (n && typeof n.addEventListener === 'function') {
      n.addEventListener('click', () => {
        window.focus()
        n.close()
      })
    }
    setTimeout(() => n && n.close && n.close(), 7000)
  } catch (_) {}
}

function refreshPermission() {
  if ('Notification' in window) {
    permission.value = Notification.permission
  }
}

async function requestNotifyPermission(thenEnableSwitch = true) {
  if (!('Notification' in window)) {
    ElMessage.warning('当前浏览器不支持桌面通知')
    return false
  }
  refreshPermission()
  if (permission.value === 'granted') {
    if (thenEnableSwitch) {
      notifyEnabled.value = true
      localStorage.setItem(LS_KEY, 'true')
    }
    fireTestNotification()
    ElMessage.success('通知权限已就绪')
    return true
  }
  if (permission.value === 'denied') {
    ElMessage.warning('通知权限已被浏览器拒绝，请在地址栏左侧站点设置中手动开启后刷新')
    return false
  }
  if (permissionRequesting.value) return false
  permissionRequesting.value = true
  try {
    const result = await Notification.requestPermission()
    permission.value = result
    if (result === 'granted') {
      if (thenEnableSwitch) {
        notifyEnabled.value = true
        localStorage.setItem(LS_KEY, 'true')
      }
      ElMessage.success('通知权限已授权，新设备上线等事件会主动提醒')
      fireTestNotification()
      return true
    } else if (result === 'denied') {
      ElMessage.warning('您点击了「拒绝」，浏览器不会主动弹出通知')
      return false
    } else {
      ElMessage.info('未授权通知权限，仅在页面通知列表中可见')
      return false
    }
  } catch (err) {
    console.error('申请通知权限失败:', err)
    ElMessage.error('申请通知权限失败')
    return false
  } finally {
    permissionRequesting.value = false
  }
}

function onSwitchCaptureClick() {
  if (!('Notification' in window)) return
  if (notifyEnabled.value === false) return
  if (permission.value === 'default') {
    requestNotifyPermission(false)
  }
}

function openSiteSettingsHelp() {
  const msg = '请在地址栏左侧「站点设置」(🔒 / ⚠️ 图标) 中，将「通知」改为「允许」，然后刷新页面即可'
  ElMessageBox && typeof ElMessageBox.alert === 'function'
    ? ElMessageBox.alert(msg, '如何开启浏览器通知权限', { confirmButtonText: '知道了' }).catch(() => {})
    : ElMessage.info(msg)
}

function handlePageToastSwitchChange(on) {
  localStorage.setItem(LS_PAGE_TOAST_KEY, on ? 'true' : 'false')
  if (on) {
    ElMessage.success('已开启页面悬浮通知，新事件会在右下角弹出卡片')
  } else {
    ElMessage.info('已关闭页面悬浮通知')
  }
}

async function handleNotifySwitchChange(on) {
  localStorage.setItem(LS_KEY, on ? 'true' : 'false')
  if (!on) {
    ElMessage.info('已关闭浏览器主动通知')
    return
  }
  await requestNotifyPermission(true)
}

let sseHandler = null
onMounted(() => {
  loadList()
  if ('Notification' in window) {
    permissionInterval = setInterval(() => {
      permission.value = Notification.permission
    }, 2000)
  }
  sseHandler = handlePushNotification
  window.addEventListener('coruna-notification', sseHandler)
})
onBeforeUnmount(() => {
  if (permissionInterval) clearInterval(permissionInterval)
  window.removeEventListener('coruna-notification', sseHandler)
})
</script>

<style scoped>
.notification-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.notify-item {
  display: flex;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  transition: all 0.15s;
  cursor: pointer;
  align-items: flex-start;
  background: #fff;
}
.notify-item:hover {
  background: #fafbfc;
  border-color: #dcdfe6;
}
.notify-item.unread {
  background: #ecf5ff;
  border-color: #b3d8ff;
}
.notify-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20px;
  flex-shrink: 0;
}
.ic-device { background: #67c23a; }
.ic-exfil { background: #e6a23c; }
.ic-cmd { background: #409eff; }
.ic-sys { background: #909399; }
.ic-alert { background: #f56c6c; }
.ic-default { background: #409eff; }
.notify-content {
  font-size: 13px;
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notify-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.notify-settings {
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px 18px;
  margin: 14px 0 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.notify-setting-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.notify-switch-label {
  min-width: 130px;
  font-size: 14px;
  color: #303133;
  font-weight: 500;
}
.notify-hint {
  padding: 8px 12px;
  border-radius: 6px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  color: #409eff;
  font-size: 13px;
  line-height: 1.5;
}
.notify-hint--warn {
  background: #fdf6ec;
  border-color: #faecd8;
  color: #e6a23c;
}
.mono { font-family: Consolas, Menlo, monospace; }
.text-muted { color: #909399; }
</style>
