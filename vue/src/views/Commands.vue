<template>
  <div class="commands-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">命令历史</div>
        <div class="page-subtitle">查看所有已发送命令的执行状态与输出</div>
      </div>
    </div>

    <div class="search-bar">
      <el-input v-model="filters.device_uuid" placeholder="设备 UUID" clearable style="width:240px;" @clear="loadList" @keyup.enter="loadList" />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width:140px;" @change="loadList">
        <el-option label="待执行" value="pending" />
        <el-option label="执行中" value="running" />
        <el-option label="已完成" value="completed" />
        <el-option label="失败" value="failed" />
        <el-option label="已过期" value="expired" />
      </el-select>
      <el-input v-model="filters.q" placeholder="搜索命令内容" clearable style="width:260px;" @clear="loadList" @keyup.enter="loadList">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="loadList">搜索</el-button>
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
      <el-table-column type="expand">
        <template #default="{ row }">
          <div style="padding:8px 16px;background:#fafafa;border-radius:6px;">
            <div style="font-size:12px;color:#909399;margin-bottom:6px;">命令输出 ({{ row.output ? row.output.length : 0 }} chars)：</div>
            <pre class="mono" style="background:#0d1117;color:#e6edf3;padding:12px;border-radius:6px;max-height:320px;overflow:auto;margin:0;">{{ row.output || row.error || '<无输出>' }}</pre>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="device_uuid" label="设备" width="160">
        <template #default="{ row }">
          <span class="mono text-muted" :title="row.device_uuid">{{ shortUuid(row.device_uuid) }}</span>
          <el-button link type="primary" size="small" @click="goDevice(row)">详情</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="command" label="命令内容" min-width="240">
        <template #default="{ row }">
          <code class="mono">{{ row.command }}</code>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small" effect="plain">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }"><span class="text-muted">{{ formatDate(row.created_at) }}</span></template>
      </el-table-column>
      <el-table-column prop="executed_at" label="执行时间" width="170">
        <template #default="{ row }"><span class="text-muted">{{ row.executed_at ? formatDate(row.executed_at) : '-' }}</span></template>
      </el-table-column>
      <el-table-column label="耗时" width="100">
        <template #default="{ row }">{{ row.duration_ms ? row.duration_ms + ' ms' : '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.status === 'pending'" type="primary" link size="small" @click="cancel(row)">取消</el-button>
          <el-button type="primary" link size="small" @click="retry(row)">重发</el-button>
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
import { Search, Delete } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, shortUuid, require2FA } from '../utils/twofa'

const router = useRouter()
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = reactive({ device_uuid: '', status: '', q: '' })
const selectedIds = ref([])
const tableRef = ref(null)

function statusTag(s) {
  return { pending: 'warning', running: 'primary', completed: 'success', failed: 'danger', expired: 'info' }[s] || 'info'
}
function statusLabel(s) {
  return { pending: '待执行', running: '执行中', completed: '已完成', failed: '失败', expired: '已过期' }[s] || s
}

function goDevice(row) { if (row.device_uuid) router.push(`/devices/${row.device_uuid}`) }

async function cancel(row) {
  try {
    await ElMessageBox.confirm('确认取消该命令？', '取消命令', { type: 'warning' })
    const otp = await require2FA('cancel command')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post(`/api/commands/${row.id}/cancel`, null, { params })
    ElMessage.success('已取消')
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '取消失败'
      ElMessage.error(msg)
    }
  }
}

async function retry(row) {
  try {
    const otp = await require2FA('resend command')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post(`/api/commands/${row.id}/retry`, null, { params })
    ElMessage.success('已重新发送')
    loadList()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '重发失败'
    ElMessage.error(msg)
  }
}

function onSelectionChange(rows) {
  selectedIds.value = (rows || []).map(r => r.id).filter(id => id != null)
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm('确认删除该命令？此操作不可恢复。', '删除', { type: 'warning' })
    const otp = await require2FA('delete command')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/commands/${row.id}`, { params })
    ElMessage.success('已删除')
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}

async function batchDeleteSelected() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先勾选要删除的命令')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除已勾选的 ${selectedIds.value.length} 条命令？此操作不可恢复。`,
      '批量删除',
      { type: 'warning' }
    )
    const otp = await require2FA('batch delete commands')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    const res = await axios.post('/api/commands/batch_delete', {
      ids: [...selectedIds.value],
      all_filtered: false
    }, { params })
    const msg = res.data?.message || `已删除 ${res.data?.deleted || 0} 条`
    ElMessage.success(msg)
    selectedIds.value = []
    if (tableRef.value && tableRef.value.clearSelection) tableRef.value.clearSelection()
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '批量删除失败'
      ElMessage.error(msg)
    }
  }
}

async function deleteAllFiltered() {
  try {
    const hasFilter = filters.device_uuid || filters.status || filters.q
    let hint = hasFilter ? '将删除当前筛选条件下的全部命令记录。' : '当前未设置筛选条件，将删除所有命令记录！'
    await ElMessageBox.confirm(
      `${hint}\n确认继续？此操作不可恢复。`,
      '清理全部筛选结果',
      { type: 'warning', dangerouslyUseHTMLString: false }
    )
    const otp = await require2FA('delete all filtered commands')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    const body = { all_filtered: true }
    if (filters.device_uuid) body.device_uuid = filters.device_uuid
    if (filters.status) body.status = filters.status
    if (filters.q) body.q = filters.q
    const res = await axios.post('/api/commands/batch_delete', body, { params })
    const msg = res.data?.message || `已删除 ${res.data?.deleted || 0} 条`
    ElMessage.success(msg)
    selectedIds.value = []
    if (tableRef.value && tableRef.value.clearSelection) tableRef.value.clearSelection()
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '清理失败'
      ElMessage.error(msg)
    }
  }
}

async function loadList() {
  try {
    const res = await axios.get('/api/commands', { params: { page: page.value, page_size: pageSize.value, ...filters } })
    list.value = res.data?.items || res.data || []
    total.value = res.data?.total || list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '命令列表加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
