<template>
  <div class="users-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">用户管理</div>
        <div class="page-subtitle">管理员账号与操作员账号管理</div>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        <span>新建用户</span>
      </el-button>
    </div>

    <div class="search-bar">
      <el-input v-model="filters.q" placeholder="搜索用户名" clearable style="width:240px;" @clear="loadList" @keyup.enter="loadList">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.role" placeholder="角色" clearable style="width:140px;" @change="loadList">
        <el-option label="管理员" value="admin" />
        <el-option label="操作员" value="operator" />
      </el-select>
      <el-button type="primary" @click="loadList">搜索</el-button>
    </div>

    <el-table :data="list" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" width="160">
        <template #default="{ row }">
          <el-avatar :size="28" style="background:#409eff;margin-right:8px;">{{ row.username[0] }}</el-avatar>
          <span style="font-weight:500;">{{ row.username }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="role" label="角色" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.role === 'admin'" type="danger" size="small" effect="dark">管理员</el-tag>
          <el-tag v-else type="primary" size="small" effect="plain">操作员</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="2FA" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.twofa_enabled" type="success" size="small" effect="plain">已启用</el-tag>
          <el-tag v-else type="info" size="small" effect="plain">未启用</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }"><span class="text-muted">{{ formatDate(row.created_at) }}</span></template>
      </el-table-column>
      <el-table-column prop="last_login" label="上次登录" width="170">
        <template #default="{ row }">
          <span v-if="row.last_login" class="text-muted">{{ formatRelative(row.last_login) }}</span>
          <span v-else class="text-muted">从未登录</span>
        </template>
      </el-table-column>
      <el-table-column prop="last_ip" label="上次 IP" width="140">
        <template #default="{ row }"><span v-if="row.last_ip" class="mono text-muted">{{ row.last_ip }}</span><span v-else class="text-muted">-</span></template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openChangePwd(row)">改密</el-button>
          <el-button type="warning" link size="small" @click="reset2FA(row)" v-if="row.twofa_enabled">重置2FA</el-button>
          <el-button v-if="row.id !== meId" type="danger" link size="small" @click="deleteRow(row)">删除</el-button>
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

  <el-dialog v-model="userDialogVisible" :title="form.id ? '编辑用户' : '新建用户'" width="480px">
    <el-form :model="form" :rules="userRules" ref="userFormRef" label-width="100px">
      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" placeholder="英文+数字" :disabled="!!form.id" />
      </el-form-item>
      <el-form-item v-if="!form.id" label="密码" prop="password">
        <el-input v-model="form.password" type="password" show-password placeholder="至少8位，建议复杂密码" />
      </el-form-item>
      <el-form-item label="角色" prop="role">
        <el-select v-model="form.role" style="width:100%;">
          <el-option label="管理员 (全部权限)" value="admin" />
          <el-option label="操作员 (只读+执行)" value="operator" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="userDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitUser">确定</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="pwdDialogVisible" title="修改密码" width="420px">
    <el-form :model="pwdForm" :rules="pwdRules" ref="pwdFormRef" label-width="100px">
      <el-form-item label="账号">
        <el-input v-model="pwdForm.username" disabled />
      </el-form-item>
      <el-form-item label="新密码" prop="password">
        <el-input v-model="pwdForm.password" type="password" show-password placeholder="至少8位" />
      </el-form-item>
      <el-form-item label="确认密码" prop="password2">
        <el-input v-model="pwdForm.password2" type="password" show-password placeholder="再输入一次" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="pwdSubmitting" @click="submitPwd">确定修改</el-button>
    </template>
  </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, formatRelative, require2FA } from '../utils/twofa'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const meId = computed(() => authStore.user?.id)

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = reactive({ q: '', role: '' })

const userDialogVisible = ref(false)
const submitting = ref(false)
const userFormRef = ref(null)
const form = reactive(defaultUser())
const userRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }, { min: 3, message: '至少3位', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 8, message: '至少8位', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}

const pwdDialogVisible = ref(false)
const pwdSubmitting = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ id: null, username: '', password: '', password2: '' })
const pwdRules = {
  password: [{ required: true, message: '请输入新密码', trigger: 'blur' }, { min: 8, message: '至少8位', trigger: 'blur' }],
  password2: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_, v, cb) => (v === pwdForm.password ? cb() : cb(new Error('两次密码不一致'))),
      trigger: 'blur'
    }
  ]
}

function defaultUser() { return { id: null, username: '', password: '', role: 'operator', remark: '' } }

function openCreate() { Object.assign(form, defaultUser()); userDialogVisible.value = true }

async function submitUser() {
  if (!userFormRef.value) return
  const valid = await userFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const otp = await require2FA(form.id ? 'update user' : 'create user')
    if (otp === false) { submitting.value = false; return }
    const params = {}
    if (otp) params.otp_code = otp
    if (form.id) {
      await axios.patch(`/api/users/${form.id}`, form, { params })
      ElMessage.success('已更新')
    } else {
      await axios.post('/api/users', form, { params })
      ElMessage.success('创建成功')
    }
    userDialogVisible.value = false
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
    const otp = await require2FA('change user password')
    if (otp === false) { pwdSubmitting.value = false; return }
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post(`/api/users/${pwdForm.id}/change-password`, { password: pwdForm.password }, { params })
    ElMessage.success('密码修改成功')
    pwdDialogVisible.value = false
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '修改失败'
    ElMessage.error(msg)
  } finally { pwdSubmitting.value = false }
}

async function reset2FA(row) {
  try {
    await ElMessageBox.confirm(`确认重置用户「${row.username}」的 2FA？用户下次登录需重新绑定验证器。`, '重置 2FA', { type: 'warning' })
    const otp = await require2FA('reset user 2FA')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post(`/api/users/${row.id}/reset-2fa`, null, { params })
    ElMessage.success('已重置 2FA')
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '重置失败'
      ElMessage.error(msg)
    }
  }
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(`确认删除用户「${row.username}」？该操作不可恢复。`, '删除用户', { type: 'warning' })
    const otp = await require2FA('delete user')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/users/${row.id}`, { params })
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
    const res = await axios.get('/api/users', { params: { page: page.value, page_size: pageSize.value, ...filters } })
    list.value = res.data?.items || res.data || []
    total.value = res.data?.total || list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(loadList)
</script>
