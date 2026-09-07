<template>
  <div class="login-wrapper">
    <div class="login-container">
      <div class="login-left">
        <div class="brand">
          <h1 class="brand-title">Coruna</h1>
          <p class="brand-subtitle">设备管理与控制平台</p>
        </div>
        <div class="brand-features">
          <div class="feature-item">
            <el-icon :size="20"><Lock /></el-icon>
            <span>安全加密通信</span>
          </div>
          <div class="feature-item">
            <el-icon :size="20"><DataLine /></el-icon>
            <span>实时数据监控</span>
          </div>
          <div class="feature-item">
            <el-icon :size="20"><Cpu /></el-icon>
            <span>高效命令执行</span>
          </div>
        </div>
      </div>
      <div class="login-right">
        <div class="login-form-wrap">
          <h2 class="login-title">管理员登录</h2>
          <p class="login-desc">请输入您的账号与密码登录系统</p>

          <el-form
            v-if="!show2FA"
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            label-position="top"
            @submit.prevent="handleLogin"
          >
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="loginForm.username"
                placeholder="请输入用户名"
                size="large"
                :prefix-icon="User"
                autocomplete="username"
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="请输入密码"
                size="large"
                :prefix-icon="Lock"
                show-password
                autocomplete="current-password"
                @keyup.enter="handleLogin"
              />
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="loginForm.remember">记住我</el-checkbox>
            </el-form-item>
            <el-button
              type="primary"
              size="large"
              class="login-btn"
              :loading="loading"
              @click="handleLogin"
            >
              登 录
            </el-button>
          </el-form>

          <el-form v-else label-position="top" @submit.prevent="handleVerify2FA">
            <el-alert
              type="warning"
              :closable="false"
              show-icon
              title="双因素认证"
              description="请打开 Google 验证器或其他 TOTP 应用，输入 6 位验证码"
              style="margin-bottom: 16px;"
            />
            <el-form-item label="6 位验证码">
              <el-input
                v-model="otpCode"
                placeholder="请输入 6 位数字"
                size="large"
                :prefix-icon="Key"
                maxlength="6"
                @keyup.enter="handleVerify2FA"
              />
            </el-form-item>
            <div style="display:flex;gap:12px;">
              <el-button size="large" class="flex-1" @click="handleCancel2FA">返回</el-button>
              <el-button type="primary" size="large" class="flex-1" :loading="loading" @click="handleVerify2FA">
                验证并登录
              </el-button>
            </div>
          </el-form>

          <div class="login-footer">
            <span>© 2025 Coruna Admin Panel</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Key, DataLine, Cpu } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const loginFormRef = ref(null)
const loginForm = reactive({
  username: '',
  password: '',
  remember: authStore.remember
})
const loginRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}
const loading = ref(false)
const show2FA = ref(false)
const otpCode = ref('')

onMounted(() => {
  if (authStore.remember && localStorage.getItem('remember_username')) {
    loginForm.username = localStorage.getItem('remember_username') || ''
  }
})

async function handleLogin() {
  if (!loginFormRef.value) return
  const valid = await loginFormRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    authStore.setRemember(loginForm.remember)
    if (loginForm.remember) {
      localStorage.setItem('remember_username', loginForm.username)
    } else {
      localStorage.removeItem('remember_username')
    }

    const result = await authStore.login(loginForm.username, loginForm.password)
    if (result.requires2FA) {
      show2FA.value = true
    } else if (result.success) {
      ElMessage.success('登录成功')
      router.push('/dashboard')
    } else {
      ElMessage.error(result.error)
    }
  } finally {
    loading.value = false
  }
}

async function handleVerify2FA() {
  if (!/^\d{6}$/.test(otpCode.value)) {
    ElMessage.warning('请输入 6 位数字验证码')
    return
  }
  loading.value = true
  try {
    const result = await authStore.verify2FA(otpCode.value)
    if (result.success) {
      ElMessage.success('登录成功')
      router.push('/dashboard')
    } else {
      ElMessage.error(result.error)
    }
  } finally {
    loading.value = false
  }
}

function handleCancel2FA() {
  authStore.reset2FAState()
  show2FA.value = false
  otpCode.value = ''
}
</script>

<style scoped>
.login-wrapper {
  min-height: 100vh;
  width: 100%;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.login-container {
  width: 100%;
  max-width: 960px;
  background: #ffffff;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  min-height: 560px;
}

.login-left {
  width: 45%;
  background: linear-gradient(160deg, #1a1a2e 0%, #25325c 100%);
  padding: 48px 40px;
  color: #ffffff;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.brand-title {
  font-size: 36px;
  font-weight: 700;
  letter-spacing: 3px;
  margin: 0;
  color: #ffffff;
}

.brand-subtitle {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
  margin-top: 8px;
}

.brand-features {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 14px;
}

.login-right {
  width: 55%;
  padding: 48px 56px;
  display: flex;
  align-items: center;
}

.login-form-wrap {
  width: 100%;
}

.login-title {
  font-size: 26px;
  font-weight: 700;
  color: #303133;
  margin: 0 0 8px;
}

.login-desc {
  font-size: 14px;
  color: #909399;
  margin: 0 0 32px;
}

.login-btn {
  width: 100%;
  margin-top: 8px;
  letter-spacing: 4px;
  font-weight: 600;
}

.flex-1 {
  flex: 1;
}

.login-footer {
  margin-top: 32px;
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
}

@media (max-width: 768px) {
  .login-container {
    flex-direction: column;
    min-height: auto;
  }
  .login-left,
  .login-right {
    width: 100%;
  }
  .login-left {
    padding: 32px 24px;
  }
  .login-right {
    padding: 32px 24px;
  }
}
</style>
