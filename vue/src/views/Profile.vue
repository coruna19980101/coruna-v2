<template>
  <div class="profile-page">
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="page-title">个人资料</div>
        <div class="page-subtitle">管理您的账号信息、密码与 2FA</div>
      </div>
    </div>

    <el-row :gutter="24">
      <el-col :span="8">
        <el-card shadow="never" class="profile-card">
          <div style="text-align:center;">
            <el-avatar :size="88" style="background:#409eff;font-size:32px;">
              {{ (user?.username || 'U')[0] }}
            </el-avatar>
            <h3 style="margin:14px 0 4px;">{{ user?.username }}</h3>
            <div style="margin-bottom:14px;">
              <el-tag v-if="user?.role === 'admin'" type="danger" effect="dark">管理员</el-tag>
              <el-tag v-else type="primary" effect="plain">操作员</el-tag>
              <el-tag v-if="me2fa" type="success" effect="plain" style="margin-left:6px;">2FA 已启用</el-tag>
            </div>
          </div>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="ID">{{ user?.id || '-' }}</el-descriptions-item>
            <el-descriptions-item label="邮箱">{{ user?.email || '<未设置>' }}</el-descriptions-item>
            <el-descriptions-item label="手机">{{ user?.phone || '<未设置>' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDate(user?.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="最后登录">
              {{ user?.last_login ? formatRelative(user.last_login) : '首次登录' }}
            </el-descriptions-item>
            <el-descriptions-item label="最后 IP">
              <span v-if="user?.last_ip" class="mono">{{ user.last_ip }}</span>
              <span v-else>-</span>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <strong>基本资料</strong>
            </div>
          </template>
          <el-form :model="profileForm" label-width="100px" style="max-width:560px;">
            <el-form-item label="昵称 / 显示名">
              <el-input v-model="profileForm.display_name" placeholder="显示名" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="profileForm.email" placeholder="邮箱（仅用于接收告警）" />
            </el-form-item>
            <el-form-item label="手机">
              <el-input v-model="profileForm.phone" placeholder="手机号" />
            </el-form-item>
            <el-form-item label="时区">
              <el-select v-model="profileForm.timezone" style="width:100%;">
                <el-option label="UTC+08:00 北京" value="Asia/Shanghai" />
                <el-option label="UTC+00:00 UTC" value="UTC" />
                <el-option label="UTC-05:00 纽约" value="America/New_York" />
                <el-option label="UTC+09:00 东京" value="Asia/Tokyo" />
              </el-select>
            </el-form-item>
            <el-form-item label="语言">
              <el-select v-model="profileForm.lang" style="width:240px;">
                <el-option label="简体中文" value="zh-CN" />
                <el-option label="English" value="en-US" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存资料</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" style="margin-top:16px;">
          <template #header><strong>修改密码</strong></template>
          <el-form :model="pwdForm" :rules="pwdRules" ref="pwdFormRef" label-width="120px" style="max-width:560px;">
            <el-form-item label="当前密码" prop="old">
              <el-input v-model="pwdForm.old" type="password" show-password placeholder="请输入当前密码" />
            </el-form-item>
            <el-form-item label="新密码" prop="new1">
              <el-input v-model="pwdForm.new1" type="password" show-password placeholder="至少8位，字母+数字+符号混合更佳" />
            </el-form-item>
            <el-form-item label="确认新密码" prop="new2">
              <el-input v-model="pwdForm.new2" type="password" show-password placeholder="请再次输入新密码" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingPwd" @click="changePwd">确认修改密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" style="margin-top:16px;">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <strong>双因素认证 (2FA)</strong>
              <el-tag v-if="me2fa" type="success" effect="plain">已启用</el-tag>
              <el-tag v-else type="warning" effect="plain">未启用</el-tag>
            </div>
          </template>
          <div style="margin-bottom:16px;" class="text-muted">
            2FA 会在登录与敏感操作时要求额外的 6 位一次性验证码，强烈建议所有账号启用以增强安全性。
          </div>
          <div v-if="!me2fa && !twofaStep" style="margin-bottom:12px;">
            <el-button type="primary" @click="startEnable"><el-icon><Key /></el-icon><span>启用 2FA</span></el-button>
          </div>
          <div v-if="me2fa" style="margin-bottom:12px;">
            <el-button type="danger" @click="disableMe"><el-icon><Remove /></el-icon><span>禁用 2FA</span></el-button>
          </div>

          <el-alert v-if="twofaStep === 1" title="第 1 步：扫描二维码或复制密钥" type="success" :closable="false" show-icon style="margin-bottom:12px;" />
          <div v-if="twofaStep === 1" style="display:flex;gap:20px;align-items:center;">
            <img v-if="qrDataUrl" :src="qrDataUrl" style="width:200px;height:200px;border:1px solid #eee;padding:6px;" />
            <div>
              <p style="margin:0 0 6px;">如无法扫码，手动输入密钥：</p>
              <el-input v-model="twofaSecret" readonly style="max-width:360px;">
                <template #append><el-button @click="copySecret">复制</el-button></template>
              </el-input>
              <div style="margin-top:10px;"><el-button type="primary" @click="twofaStep = 2">下一步</el-button></div>
            </div>
          </div>

          <el-alert v-if="twofaStep === 2" title="第 2 步：输入验证码确认启用" type="warning" :closable="false" show-icon style="margin:12px 0;" />
          <el-form v-if="twofaStep === 2" label-width="120px">
            <el-form-item label="6 位验证码">
              <el-input v-model="otpCode" maxlength="6" style="width:240px;" />
            </el-form-item>
            <el-form-item>
              <el-button @click="twofaStep = 1">上一步</el-button>
              <el-button type="primary" :loading="enabling" @click="confirmEnable">确认启用</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Key, Remove } from '@element-plus/icons-vue'
import QRCode from 'qrcode'
import * as OTPAuth from 'otpauth'
import axios from '../utils/axios'
import { useAuthStore } from '../stores/auth'
import { formatDate, formatRelative, copyToClipboard, prompt2FA } from '../utils/twofa'

const authStore = useAuthStore()
const user = computed(() => authStore.user)
const me2fa = computed(() => user.value?.twofa_enabled === true)

const profileForm = reactive({ display_name: '', email: '', phone: '', timezone: 'Asia/Shanghai', lang: 'zh-CN' })
const savingProfile = ref(false)

const pwdFormRef = ref(null)
const pwdForm = reactive({ old: '', new1: '', new2: '' })
const pwdRules = {
  old: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new1: [{ required: true, message: '请输入新密码', trigger: 'blur' }, { min: 8, message: '至少8位', trigger: 'blur' }],
  new2: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: (_, v, cb) => (v === pwdForm.new1 ? cb() : cb(new Error('两次密码不一致'))), trigger: 'blur' }
  ]
}
const savingPwd = ref(false)

const twofaStep = ref(0)
const twofaSecret = ref('')
const qrDataUrl = ref('')
const otpCode = ref('')
const enabling = ref(false)
const account = computed(() => `Coruna (${user.value?.username || 'user'})`)

async function loadMe() {
  const u = await authStore.getMe()
  if (u) {
    profileForm.display_name = u.display_name || u.username
    profileForm.email = u.email || ''
    profileForm.phone = u.phone || ''
    profileForm.timezone = u.timezone || 'Asia/Shanghai'
    profileForm.lang = u.lang || 'zh-CN'
  }
}

async function saveProfile() {
  savingProfile.value = true
  try {
    await axios.patch('/api/auth/me', profileForm)
    ElMessage.success('资料已保存')
    authStore.getMe()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '资料保存失败'
    ElMessage.error(msg)
  }
  finally { savingProfile.value = false }
}

async function changePwd() {
  if (!pwdFormRef.value) return
  const ok = await pwdFormRef.value.validate().catch(() => false)
  if (!ok) return
  savingPwd.value = true
  try {
    await axios.post('/api/auth/change-password', { old_password: pwdForm.old, new_password: pwdForm.new1 })
    ElMessage.success('密码已修改，下次登录请使用新密码')
    pwdForm.old = pwdForm.new1 = pwdForm.new2 = ''
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '密码修改失败')
  } finally { savingPwd.value = false }
}

function genSecret() { return new OTPAuth.Secret({ size: 20 }).base32 }

async function startEnable() {
  twofaSecret.value = genSecret()
  const totp = new OTPAuth.TOTP({
    issuer: 'Coruna', label: account.value,
    algorithm: 'SHA1', digits: 6, period: 30,
    secret: OTPAuth.Secret.fromBase32(twofaSecret.value)
  })
  try { qrDataUrl.value = await QRCode.toDataURL(totp.toString(), { width: 200 }) } catch (_) {}
  twofaStep.value = 1
  try { await axios.post('/api/auth/2fa/setup', { secret: twofaSecret.value }) } catch (_) {}
}

async function copySecret() { await copyToClipboard(twofaSecret.value); ElMessage.success('密钥已复制') }

async function confirmEnable() {
  if (!/^\d{6}$/.test(otpCode.value)) { ElMessage.warning('请输入 6 位数字验证码'); return }
  enabling.value = true
  try {
    await axios.post('/api/auth/2fa/enable', { secret: twofaSecret.value, otp_code: otpCode.value })
    twofaStep.value = 0
    twofaSecret.value = ''
    otpCode.value = ''
    ElMessage.success('2FA 已启用')
    authStore.getMe()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '验证失败')
  } finally { enabling.value = false }
}

async function disableMe() {
  try {
    const otp = await prompt2FA()
    if (otp === null) return
    await axios.post('/api/auth/2fa/disable', otp ? { otp_code: otp } : {})
    ElMessage.success('2FA 已禁用')
    authStore.getMe()
  } catch (_) {}
}

onMounted(loadMe)
</script>

<style scoped>
.profile-card { border-radius: 8px; }
</style>
