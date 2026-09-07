<template>
  <div class="audit-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">审计日志</div>
        <div class="page-subtitle">管理员与操作员的敏感操作审计记录</div>
      </div>
      <el-button type="primary" plain @click="exportCSV">导出 CSV</el-button>
    </div>

    <div class="filter-bar">
      <el-input v-model="filters.username" placeholder="用户名" clearable style="width:160px;" @clear="loadList" @keyup.enter="loadList" />
      <el-select v-model="filters.action" placeholder="操作" clearable style="width:180px;" @change="loadList">
        <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
      </el-select>
      <el-input v-model="filters.ip" placeholder="IP" clearable style="width:160px;" @clear="loadList" @keyup.enter="loadList" />
      <el-input v-model="filters.resource" placeholder="资源类型" clearable style="width:160px;" @clear="loadList" @keyup.enter="loadList" />
      <el-date-picker v-model="filters.dateRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD HH:mm:ss" style="width:360px;" />
      <el-button type="primary" @click="loadList">
        <el-icon><Search /></el-icon>
        <span>查询</span>
      </el-button>
      <el-button @click="resetFilter">重置</el-button>
    </div>

    <el-table :data="list" stripe>
      <el-table-column prop="time" label="时间" width="170">
        <template #default="{ row }"><span class="text-muted mono">{{ formatDate(row.time || row.created_at) }}</span></template>
      </el-table-column>
      <el-table-column prop="username" label="用户名" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="row.role === 'admin' ? 'danger' : 'primary'" effect="plain">{{ row.username }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="action" label="操作" width="150">
        <template #default="{ row }">
          <el-tag :type="actionTag(row.action)" size="small" effect="plain">{{ row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="resource" label="资源类型" width="120" />
      <el-table-column label="详情" show-overflow-tooltip>
        <template #default="{ row }">
          <code class="mono" style="background:#f5f5f5;padding:2px 6px;border-radius:4px;">{{ row.detail || JSON.stringify(row.details || {}) }}</code>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP" width="140">
        <template #default="{ row }"><span class="mono">{{ row.ip }}</span></template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :page-sizes="[50, 100, 200]"
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
import { formatDate } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = reactive({ username: '', action: '', ip: '', resource: '', dateRange: [] })
const actions = ['登录', '登出', '修改密码', '用户管理-创建', '用户管理-删除', '用户管理-重置2FA', '创建渠道', '删除渠道', '重置渠道Key', '删除设备', '发送命令', '删除模板', '修改系统设置', '重置用户密码']

function actionTag(a) {
  if (a?.includes('删除')) return 'danger'
  if (a?.includes('创建')) return 'success'
  if (a?.includes('修改') || a?.includes('重置')) return 'warning'
  if (a === '登录' || a === '登出') return 'info'
  if (a?.includes('发送')) return 'primary'
  return 'info'
}

function resetFilter() {
  Object.assign(filters, { username: '', action: '', ip: '', resource: '', dateRange: [] })
  page.value = 1
  loadList()
}

function exportCSV() { ElMessage.success('已生成 CSV 下载任务') }

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      username: filters.username || undefined,
      action: filters.action || undefined,
      resource: filters.resource || undefined,
      ip: filters.ip || undefined,
      start_time: Array.isArray(filters.dateRange) && filters.dateRange[0] ? filters.dateRange[0] : undefined,
      end_time: Array.isArray(filters.dateRange) && filters.dateRange[1] ? filters.dateRange[1] : undefined,
    }
    const res = await axios.get('/api/audit', { params })
    const raw = res.data?.items || res.data || []
    list.value = raw.map(r => ({
      ...r,
      time: r.time || r.timestamp || r.created_at,
      created_at: r.created_at || r.timestamp || r.time,
      resource: r.resource || r.resource_type,
      detail: r.detail || r.details || '',
    }))
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '审计日志加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
