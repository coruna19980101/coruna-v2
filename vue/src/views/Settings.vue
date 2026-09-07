<template>
  <div class="settings-page">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="基础设置" name="basic">
        <div class="page-card">
          <div class="page-header">
            <div>
              <div class="page-title">基础系统设置</div>
              <div class="page-subtitle">CORS、限流、重定向等全局基础参数</div>
            </div>
          </div>
          <el-form :model="basic" label-width="200px" style="max-width:760px;">
            <el-form-item label="CORS 允许来源">
              <el-select v-model="basic.cors_origins" multiple filterable allow-create default-first-option placeholder="输入完整域名，回车添加（* 表示全部）" style="width:100%;" />
              <div class="text-muted" style="font-size:12px;margin-top:4px;">默认包含 http://localhost:5173，生产环境建议配置具体域名</div>
            </el-form-item>
            <el-form-item label="API 限流 (每分钟)">
              <el-row :gutter="12">
                <el-col :span="8">
                  <label>未登录用户：</label>
                  <el-input-number v-model="basic.rate_anon" :min="10" :max="10000" style="width:100%;margin-top:4px;" />
                </el-col>
                <el-col :span="8">
                  <label>登录用户：</label>
                  <el-input-number v-model="basic.rate_auth" :min="10" :max="50000" style="width:100%;margin-top:4px;" />
                </el-col>
                <el-col :span="8">
                  <label>登录失败：</label>
                  <el-input-number v-model="basic.rate_login" :min="1" :max="1000" style="width:100%;margin-top:4px;" />
                </el-col>
              </el-row>
            </el-form-item>
            <el-form-item label="默认重定向 URL">
              <el-input v-model="basic.default_redirect" placeholder="https://example.com/landing" />
              <div class="text-muted" style="font-size:12px;margin-top:4px;">未指定 redirect_url 时使用的默认落地页</div>
            </el-form-item>
            <el-form-item label="会话 Token 有效期 (分钟)">
              <el-input-number v-model="basic.token_expire" :min="5" :max="10080" style="width:240px;" />
            </el-form-item>
            <el-form-item label="水印设置">
              <el-switch v-model="basic.watermark_enabled" active-text="启用" inactive-text="禁用" style="margin-right:24px;" />
              <el-color-picker v-model="basic.watermark_color" />
              <el-input-number v-model="basic.watermark_opacity" :min="0" :max="1" :step="0.05" style="width:140px;margin-left:12px;" />
              <span class="text-muted" style="margin-left:8px;">透明度</span>
            </el-form-item>
            <el-divider />
            <el-form-item>
              <el-button type="primary" :loading="saving.basic" @click="saveBasic">保存设置</el-button>
              <el-button @click="loadBasic">重置</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <el-tab-pane label="安全与 2FA" name="security">
        <div class="page-card">
          <div class="page-header">
            <div>
              <div class="page-title">双因素认证 (2FA)</div>
              <div class="page-subtitle">启用后，敏感操作需额外输入 6 位 Google Authenticator 验证码</div>
            </div>
          </div>

          <el-alert title="全局安全开关" type="info" :closable="false" show-icon style="margin-bottom:16px;" />
          <el-form :model="security" label-width="200px" style="max-width:760px;">
            <el-form-item label="强制 2FA 全局开关">
              <el-switch v-model="security.require_2fa" active-text="启用 2FA 强制保护" inactive-text="关闭" />
            </el-form-item>
            <el-divider content-position="left">需要 2FA 的模块（仅在全局启用时生效）</el-divider>
            <el-form-item label="用户管理模块">
              <el-switch v-model="security.twofa_users" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="模板管理模块">
              <el-switch v-model="security.twofa_templates" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="渠道管理模块">
              <el-switch v-model="security.twofa_channels" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="设备批量操作">
              <el-switch v-model="security.twofa_devices" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="命令发送/脚本执行">
              <el-switch v-model="security.twofa_commands" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="个人敏感操作">
              <el-switch v-model="security.twofa_profile" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-divider content-position="left">数据与高级管理模块</el-divider>
            <el-form-item label="代理商管理">
              <el-switch v-model="security.twofa_agents" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="数据窃取 (Exfil)">
              <el-switch v-model="security.twofa_exfil" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="审计日志">
              <el-switch v-model="security.twofa_audit" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="系统日志">
              <el-switch v-model="security.twofa_logs" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="通知中心">
              <el-switch v-model="security.twofa_notifications" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-form-item label="钱包数据">
              <el-switch v-model="security.twofa_wallets" active-text="需要 2FA" inactive-text="不需要" />
            </el-form-item>
            <el-divider />
            <el-form-item>
              <el-button type="primary" :loading="saving.security" @click="saveSecurity">保存安全设置</el-button>
            </el-form-item>
          </el-form>

          <el-divider />

          <h3 style="margin-bottom:12px;">我的 2FA 设置</h3>
          <el-descriptions :column="2" border size="small" style="margin-bottom:16px;">
            <el-descriptions-item label="当前状态">
              <el-tag v-if="me2fa" type="success" effect="plain">已启用 2FA</el-tag>
              <el-tag v-else type="warning" effect="plain">未启用 2FA</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="验证器">Google Authenticator / 兼容 TOTP 应用</el-descriptions-item>
          </el-descriptions>

          <div v-if="!me2fa && !twofaStep" style="margin-bottom:12px;">
            <el-button type="primary" @click="startEnable2FA">
              <el-icon><Key /></el-icon>
              <span>启用 2FA</span>
            </el-button>
          </div>
          <div v-if="me2fa" style="margin-bottom:12px;">
            <el-button type="danger" @click="disable2FA">
              <el-icon><Remove /></el-icon>
              <span>禁用我的 2FA</span>
            </el-button>
          </div>

          <el-alert v-if="twofaStep === 1" title="第 1 步：使用验证器 App 扫描二维码" type="success" :closable="false" show-icon style="margin-bottom:12px;">
            推荐使用 Google Authenticator、Microsoft Authenticator、1Password、Authy 等支持 TOTP 的 App。
          </el-alert>
          <el-card v-if="twofaStep === 1" class="twofa-card">
            <div style="display:flex;gap:20px;align-items:center;">
              <div style="flex-shrink:0;">
                <img v-if="qrDataUrl" :src="qrDataUrl" alt="TOTP QR" style="width:200px;height:200px;border:1px solid #eee;padding:8px;background:#fff;" />
                <el-skeleton v-else :rows="8" animated />
              </div>
              <div>
                <h4 style="margin:0 0 8px;">扫码有问题？手动输入密钥：</h4>
                <div style="margin-bottom:8px;">
                  <el-input v-model="twofaSecret" readonly style="max-width:380px;">
                    <template #append>
                      <el-button @click="copySecret">复制</el-button>
                    </template>
                  </el-input>
                </div>
                <div class="text-muted" style="font-size:13px;">
                  账户：{{ accountName }}<br />
                  发行方：Coruna Admin<br />
                  类型：基于时间 (TOTP)
                </div>
                <el-button type="primary" style="margin-top:14px;" @click="twofaStep = 2">已添加，下一步</el-button>
              </div>
            </div>
          </el-card>

          <el-alert v-if="twofaStep === 2" title="第 2 步：输入验证码以确认启用" type="warning" :closable="false" show-icon style="margin-top:16px;margin-bottom:12px;" />
          <el-card v-if="twofaStep === 2" class="twofa-card">
            <el-form label-width="120px">
              <el-form-item label="6 位验证码">
                <el-input v-model="otpCode" placeholder="请输入 App 上显示的 6 位数字" maxlength="6" style="width:240px;" />
              </el-form-item>
              <el-form-item>
                <el-button @click="twofaStep = 1">上一步</el-button>
                <el-button type="primary" :loading="enabling2FA" @click="confirmEnable2FA">确认启用</el-button>
              </el-form-item>
            </el-form>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Key, Remove } from '@element-plus/icons-vue'
import QRCode from 'qrcode'
import * as OTPAuth from 'otpauth'
import axios from '../utils/axios'
import { copyToClipboard, require2FA } from '../utils/twofa'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const activeTab = ref('basic')

const basic = reactive({
  cors_origins: ['*'],
  rate_anon: 60,
  rate_auth: 600,
  rate_login: 10,
  default_redirect: '',
  token_expire: 1440,
  watermark_enabled: true,
  watermark_color: '#409eff',
  watermark_opacity: 0.15
})

const security = reactive({
  require_2fa: false,
  twofa_users: true,
  twofa_templates: false,
  twofa_channels: false,
  twofa_devices: true,
  twofa_commands: true,
  twofa_profile: true,
  twofa_agents: false,
  twofa_exfil: false,
  twofa_audit: false,
  twofa_logs: false,
  twofa_notifications: false,
  twofa_wallets: false
})

const saving = reactive({ basic: false, security: false })
const me2fa = ref(false)
const twofaStep = ref(0)
const twofaSecret = ref('')
const qrDataUrl = ref('')
const otpCode = ref('')
const enabling2FA = ref(false)
const accountName = computed(() => {
  const u = authStore.user?.username || 'user'
  return `Coruna (${u})`
})

async function loadBasic() {
  try {
    const res = await axios.get('/api/settings')
    if (res.data?.basic) {
      Object.assign(basic, res.data.basic)
      if (res.data.watermark) {
        basic.watermark_enabled = !!res.data.watermark.enabled
        if (res.data.watermark.color) basic.watermark_color = res.data.watermark.color
        if (res.data.watermark.opacity != null) basic.watermark_opacity = Number(res.data.watermark.opacity)
      }
    } else {
      if (res.data?.watermark) Object.assign(basic, { watermark_enabled: true, watermark_color: '#409eff', watermark_opacity: 0.15, ...res.data.watermark })
    }
    if (res.data?.security) Object.assign(security, res.data.security)
    me2fa.value = !!res.data?.me?.twofa_enabled || (authStore.user?.twofa_enabled === true)
  } catch (err) {
    const msg = err?.response?.data?.detail || '加载设置失败'
    ElMessage.error(msg)
    me2fa.value = authStore.user?.twofa_enabled === true
  }
}

async function saveBasic() {
  saving.basic = true
  try {
    const otp = await require2FA('save basic settings')
    const params = {}
    if (otp) params.otp_code = otp
    await axios.put('/api/settings', { basic }, { params })
    ElMessage.success('基础设置已保存')
  } catch (err) {
    const msg = err?.response?.data?.detail || '保存失败'
    ElMessage.error(msg)
  } finally { saving.basic = false }
}

async function saveSecurity() {
  saving.security = true
  try {
    const otp = await require2FA('save security settings')
    const params = {}
    if (otp) params.otp_code = otp
    await axios.put('/api/settings/security', security, { params })
    ElMessage.success('安全设置已保存')
  } catch (err) {
    const msg = err?.response?.data?.detail || '保存失败'
    ElMessage.error(msg)
  } finally { saving.security = false }
}

function generateSecret() {
  return new OTPAuth.Secret({ size: 20 }).base32
}

async function startEnable2FA() {
  twofaSecret.value = generateSecret()
  const totp = new OTPAuth.TOTP({
    issuer: 'Coruna',
    label: accountName.value,
    algorithm: 'SHA1',
    digits: 6,
    period: 30,
    secret: OTPAuth.Secret.fromBase32(twofaSecret.value)
  })
  try {
    qrDataUrl.value = await QRCode.toDataURL(totp.toString(), { width: 200, margin: 1 })
  } catch (_) { qrDataUrl.value = '' }
  twofaStep.value = 1
  try { await axios.post('/api/auth/2fa/setup', { secret: twofaSecret.value }) } catch (_) {}
}

async function copySecret() {
  await copyToClipboard(twofaSecret.value)
  ElMessage.success('密钥已复制')
}

async function confirmEnable2FA() {
  if (!/^\d{6}$/.test(otpCode.value)) {
    ElMessage.warning('请输入 6 位数字验证码')
    return
  }
  enabling2FA.value = true
  try {
    await axios.post('/api/auth/2fa/enable', { secret: twofaSecret.value, otp_code: otpCode.value })
    me2fa.value = true
    twofaStep.value = 0
    twofaSecret.value = ''
    otpCode.value = ''
    ElMessage.success('2FA 已启用')
    authStore.getMe()
  } catch (err) {
    const msg = err.response?.data?.detail || '验证失败，请检查验证码或系统时间'
    ElMessage.error(msg)
  } finally { enabling2FA.value = false }
}

async function disable2FA() {
  try {
    const otp = await require2FA()
    if (!otp && otp !== '') return
    await axios.post('/api/auth/2fa/disable', otp ? { otp_code: otp } : {})
    me2fa.value = false
    ElMessage.success('已禁用 2FA')
    authStore.getMe()
  } catch (_) {}
}

onMounted(loadBasic)
</script>

<style scoped>
.twofa-card { margin-top: 0; border-radius: 8px; }
</style>
