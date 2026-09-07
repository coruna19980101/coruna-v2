<template>
  <div class="logs-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">访问日志</div>
        <div class="page-subtitle">全部 HTTP 请求访问记录</div>
      </div>
    </div>

    <div class="filter-bar">
      <el-input v-model="filters.ip" placeholder="IP 地址" clearable style="width:180px;" @clear="loadList" @keyup.enter="loadList" />
      <el-input v-model="filters.path" placeholder="路径" clearable style="width:240px;" @clear="loadList" @keyup.enter="loadList" />
      <el-select v-model="filters.method" placeholder="方法" clearable style="width:110px;" @change="loadList">
        <el-option v-for="m in ['GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD']" :key="m" :label="m" :value="m" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态码" clearable style="width:120px;" @change="loadList">
        <el-option label="2xx" value="2" />
        <el-option label="3xx" value="3" />
        <el-option label="4xx" value="4" />
        <el-option label="5xx" value="5" />
      </el-select>
      <el-date-picker v-model="filters.dateRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD HH:mm:ss" style="width:360px;" />
      <el-button type="primary" @click="loadList">
        <el-icon><Search /></el-icon>
        <span>查询</span>
      </el-button>
      <el-button @click="resetFilter">重置</el-button>
    </div>

    <el-table :data="list" stripe size="small">
      <el-table-column prop="time" label="时间" width="170">
        <template #default="{ row }"><span class="text-muted mono">{{ formatDate(row.time || row.created_at) }}</span></template>
      </el-table-column>
      <el-table-column prop="ip" label="IP" width="140">
        <template #default="{ row }">
          <span class="mono">{{ row.ip }}</span>
          <el-button link type="primary" size="small" @click="copy(row.ip)">复制</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="method" label="方法" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="methodTag(row.method)" effect="plain">{{ row.method }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="path" label="路径" show-overflow-tooltip>
        <template #default="{ row }"><code class="mono" style="color:#303133;">{{ row.path }}</code></template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTag(row.status)" effect="plain">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="size" label="字节" width="90">
        <template #default="{ row }">{{ formatSize(row.size || row.bytes) }}</template>
      </el-table-column>
      <el-table-column prop="ua" label="User-Agent" min-width="220" show-overflow-tooltip>
        <template #default="{ row }"><span class="text-muted">{{ row.ua || row.user_agent || '-' }}</span></template>
      </el-table-column>
      <el-table-column prop="device_uuid" label="设备" width="140">
        <template #default="{ row }">
          <span v-if="row.device_uuid" class="mono text-muted">{{ shortUuid(row.device_uuid) }}</span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="channel" label="渠道" width="100" />
      <el-table-column prop="template" label="模板" width="120" />
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :page-sizes="[50, 100, 200, 500]"
      :total="total"
      layout="total, sizes, prev, pager, next, jumper"
      background
      style="justify-content:flex-end;margin-top:16px;"
      @current-change="loadList"
      @size-change="loadList"
    />
  </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, shortUuid, copyToClipboard } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(100)
const filters = reactive({ ip: '', path: '', method: '', status: '', dateRange: [] })

function methodTag(m) {
  return { GET: 'success', POST: 'primary', PUT: 'warning', PATCH: 'warning', DELETE: 'danger', OPTIONS: 'info', HEAD: 'info' }[m] || 'info'
}
function statusTag(s) {
  if (!s) return 'info'
  if (String(s).startsWith('2')) return 'success'
  if (String(s).startsWith('3')) return 'info'
  if (String(s).startsWith('4')) return 'warning'
  if (String(s).startsWith('5')) return 'danger'
  return 'info'
}
function formatSize(b) {
  if (!b) return '-'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(2) + ' MB'
}

async function copy(t) {
  await copyToClipboard(t || '')
  ElMessage.success('已复制')
}

function resetFilter() {
  Object.assign(filters, { ip: '', path: '', method: '', status: '', dateRange: [] })
  page.value = 1
  loadList()
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      ip: filters.ip || undefined,
      path: filters.path || undefined,
      method: filters.method || undefined,
      status: filters.status || undefined,
      start_time: Array.isArray(filters.dateRange) && filters.dateRange[0] ? filters.dateRange[0] : undefined,
      end_time: Array.isArray(filters.dateRange) && filters.dateRange[1] ? filters.dateRange[1] : undefined,
    }
    const res = await axios.get('/api/logs', { params })
    const raw = res.data?.items || res.data || []
    list.value = raw.map(r => ({
      ...r,
      time: r.time || r.timestamp || r.created_at,
      created_at: r.created_at || r.timestamp || r.time,
      status: r.status ?? r.status_code,
      size: r.size ?? r.bytes ?? r.content_length,
      bytes: r.bytes ?? r.size ?? r.content_length,
      ua: r.ua || r.user_agent,
    }))
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '访问日志加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
