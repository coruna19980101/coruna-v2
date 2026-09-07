<template>
  <div class="agents-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">代理商管理</div>
        <div class="page-subtitle">代理商账号、渠道分配、分成比例与配额管理</div>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        <span>新建代理商</span>
      </el-button>
    </div>

    <div class="search-bar">
      <el-input v-model="filters.q" placeholder="搜索账号/姓名/手机" clearable style="width:280px;" @clear="loadList" @keyup.enter="loadList">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.enabled" placeholder="状态" clearable style="width:140px;" @change="loadList">
        <el-option label="启用" :value="true" />
        <el-option label="禁用" :value="false" />
      </el-select>
      <el-button type="primary" @click="loadList">搜索</el-button>
    </div>

    <el-table :data="list" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="登录账号" width="140">
        <template #default="{ row }">
          <el-avatar :size="28" style="background:#9b59b6;margin-right:8px;">{{ row.username[0] }}</el-avatar>
          <span class="mono" style="font-weight:500;">{{ row.username }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="姓名" width="120" />
      <el-table-column prop="phone" label="联系方式" width="160">
        <template #default="{ row }">
          <span class="mono">{{ row.phone }}</span>
          <div v-if="row.email" class="text-muted" style="font-size:12px;">{{ row.email }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="plain">{{ row.enabled ? '启用' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="device_quota" label="设备配额" width="110">
        <template #default="{ row }">
          <el-progress :percentage="safePct(row.device_count, row.device_quota)" :stroke-width="8" />
          <div style="font-size:12px;color:#909399;margin-top:2px;">{{ safeNum(row.device_count, 0) }} / {{ safeNum(row.device_quota, 0) }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="commission" label="分成" width="100">
        <template #default="{ row }">{{ safeCommission(row.commission) }}</template>
      </el-table-column>
      <el-table-column label="关联渠道" width="100">
        <template #default="{ row }">{{ safeNum(row.channels_count, 0) }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建日期" width="120">
        <template #default="{ row }"><span class="text-muted">{{ formatDate(row.created_at, true) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
          <el-button type="primary" link size="small" @click="openChangePwd(row)">改密</el-button>
          <el-button type="success" link size="small" @click="openAssignChannels(row)">分配渠道</el-button>
          <el-button :type="row.enabled ? 'warning' : 'success'" link size="small" @click="toggleEnabled(row)">
            {{ row.enabled ? '禁用' : '启用' }}
          </el-button>
          <el-button type="danger" link size="small" @click="deleteRow(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :page-sizes="[20, 50, 100]"
      :total="total"
      layout="total, sizes, prev, pager, next"
      background
      style="justify-content:flex-end;margin-top:16px;"
      @current-change="loadList"
      @size-change="loadList"
    />
  </div>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑代理商' : '新建代理商'" width="560px">
    <el-form :model="form" :rules="agentRules" ref="formRef" label-width="100px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="登录账号" prop="username">
            <el-input v-model="form.username" :disabled="!!form.id" placeholder="英文账号" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" show-password :placeholder="form.id ? '留空不修改' : '至少8位'" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="姓名" prop="name">
            <el-input v-model="form.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="手机" prop="phone">
            <el-input v-model="form.phone" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="邮箱">
        <el-input v-model="form.email" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="设备配额" prop="device_quota">
            <el-input-number v-model="form.device_quota" :min="0" :max="100000" style="width:100%;" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="分成比例" prop="commission">
            <el-slider v-model="form.commission" :min="0" :max="0.9" :step="0.05" :format-tooltip="v => Math.round(v*100) + '%'" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="启用状态">
        <el-switch v-model="form.enabled" active-text="启用" inactive-text="禁用" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="pwdDialogVisible" title="修改代理商密码" width="420px">
    <el-form :model="pwdForm" :rules="pwdRules" ref="pwdFormRef" label-width="100px">
      <el-form-item label="账号"><el-input v-model="pwdForm.username" disabled /></el-form-item>
      <el-form-item label="新密码" prop="password">
        <el-input v-model="pwdForm.password" type="password" show-password placeholder="至少8位" />
      </el-form-item>
      <el-form-item label="确认密码" prop="password2">
        <el-input v-model="pwdForm.password2" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="pwdSubmitting" @click="submitPwd">确定</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="channelDialogVisible" title="分配渠道" width="520px">
    <el-form label-width="100px">
      <el-form-item label="代理商"><el-input :model-value="channelForm.username" disabled /></el-form-item>
      <el-form-item label="可管理渠道">
        <el-select v-model="channelForm.channel_ids" multiple filterable placeholder="选择可管理的渠道" style="width:100%;">
          <el-option v-for="c in allChannels" :key="c.id" :label="`${c.name} (${c.slug})`" :value="c.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="channelDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="chSubmitting" @click="submitChannels">保存</el-button>
    </template>
  </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, require2FA } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = reactive({ q: '', enabled: null })
const allChannels = ref([])

function safeNum(v, def = 0) { const n = Number(v); return Number.isFinite(n) ? n : def }
function safePct(device_count, device_quota) {
  const c = safeNum(device_count, 0); const q = safeNum(device_quota, 0)
  if (q <= 0) return 0
  return Math.min(100, Math.max(0, Math.round(c / Math.max(1, q) * 100)))
}
function safeCommission(v) { return `${(safeNum(v, 0) * 100).toFixed(0)}%` }
function normalizeRow(r) {
  r.device_count = safeNum(r.device_count, 0)
  r.device_quota = safeNum(r.device_quota, 0)
  r.commission = safeNum(r.commission, 0)
  r.channels_count = safeNum(r.channels_count, 0)
  return r
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const form = reactive(defaultAgent())
const agentRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }, { min: 3, message: '至少3位', trigger: 'blur' }],
  password: [{ validator: (_, v, cb) => (form.id || (v && v.length >= 8) ? cb() : cb(new Error('至少8位'))), trigger: 'blur' }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  phone: [{ required: true, message: '请输入联系电话', trigger: 'blur' }],
  device_quota: [{ required: true, message: '请输入配额', trigger: 'blur' }]
}

const pwdDialogVisible = ref(false)
const pwdSubmitting = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ id: null, username: '', password: '', password2: '' })
const pwdRules = {
  password: [{ required: true, message: '请输入新密码', trigger: 'blur' }, { min: 8, message: '至少8位', trigger: 'blur' }],
  password2: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: (_, v, cb) => (v === pwdForm.password ? cb() : cb(new Error('两次不一致'))), trigger: 'blur' }
  ]
}

const channelDialogVisible = ref(false)
const chSubmitting = ref(false)
const channelForm = reactive({ id: null, username: '', channel_ids: [] })

function defaultAgent() {
  return { id: null, username: '', password: '', name: '', phone: '', email: '', device_quota: 500, commission: 0.3, enabled: true, remark: '' }
}

function openCreate() { Object.assign(form, defaultAgent()); dialogVisible.value = true }
function openEdit(row) { Object.assign(form, { ...defaultAgent(), ...row, password: '' }); dialogVisible.value = true }

async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const otp = await require2FA(form.id ? 'update agent' : 'create agent')
    if (otp === false) { submitting.value = false; return }
    const params = {}
    if (otp) params.otp_code = otp
    if (form.id) {
      await axios.patch(`/api/agents/${form.id}`, form, { params })
      ElMessage.success('已更新')
    } else {
      await axios.post('/api/agents', form, { params })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadList()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '保存失败'
    ElMessage.error(msg)
  } finally { submitting.value = false }
}

function openChangePwd(row) {
  pwdForm.id = row.id
  pwdForm.username = row.username
  pwdForm.password = ''
  pwdForm.password2 = ''
  pwdDialogVisible.value = true
}
async function submitPwd() {
  if (!pwdFormRef.value) return
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  pwdSubmitting.value = true
  try {
    const otp = await require2FA('change agent password')
    if (otp === false) { pwdSubmitting.value = false; return }
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post(`/api/agents/${pwdForm.id}/change-password`, { password: pwdForm.password }, { params })
    ElMessage.success('修改成功')
    pwdDialogVisible.value = false
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '修改失败'
    ElMessage.error(msg)
  } finally { pwdSubmitting.value = false }
}

async function openAssignChannels(row) {
  channelForm.id = row.id
  channelForm.username = row.username
  channelForm.channel_ids = row.channel_ids || []
  await loadChannels()
  channelDialogVisible.value = true
}

async function submitChannels() {
  chSubmitting.value = true
  try {
    const otp = await require2FA('assign agent channels')
    if (otp === false) { chSubmitting.value = false; return }
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post(`/api/agents/${channelForm.id}/assign-channels`, { channel_ids: channelForm.channel_ids }, { params })
    ElMessage.success('渠道分配已更新')
    channelDialogVisible.value = false
    loadList()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '渠道分配失败'
    ElMessage.error(msg)
  } finally { chSubmitting.value = false }
}

async function toggleEnabled(row) {
  const origEnabled = row.enabled
  try {
    const otp = await require2FA(origEnabled ? 'disable agent' : 'enable agent')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.patch(`/api/agents/${row.id}`, { enabled: !origEnabled }, { params })
    ElMessage.success(origEnabled ? '已禁用' : '已启用')
    loadList()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '状态更新失败'
    ElMessage.error(msg)
    row.enabled = origEnabled
  }
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(`确认删除代理商「${row.name}（${row.username}）」？`, '删除', { type: 'warning' })
    const otp = await require2FA('delete agent')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/agents/${row.id}`, { params })
    ElMessage.success('已删除')
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}

async function loadChannels() {
  try {
    const res = await axios.get('/api/channels', { params: { page_size: 200 } })
    allChannels.value = res.data?.items || res.data || []
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '渠道列表加载失败'
    ElMessage.error(msg)
    allChannels.value = []
  }
}

async function loadList() {
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filters.q && filters.q.trim()) params.q = filters.q.trim()
    if (filters.enabled === true || filters.enabled === false) params.enabled = filters.enabled
    const res = await axios.get('/api/agents', { params })
    const data = res.data?.items || res.data || []
    list.value = Array.isArray(data) ? data.map(normalizeRow) : []
    total.value = safeNum(res.data?.total, list.value.length)
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '代理商列表加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(async () => { await loadChannels(); loadList() })
</script>
