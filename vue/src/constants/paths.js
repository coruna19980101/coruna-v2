// Frontend path constants.  后端 settings -> fe.route_* 对应默认值；
// 若以后需要改成可由后端下发（比如多租户），改为在 App.vue onMounted 里从 /api/settings 读取并覆盖即可。
const PATHS = {
  LOGIN: '/login',
  ROOT: '/',
  DASHBOARD: '/dashboard',

  DEVICES: '/devices',
  DEVICE_DETAIL: '/devices/:uuid',
  deviceDetail: (uuid) => `/devices/${encodeURIComponent(uuid)}`,

  CHANNELS: '/channels',
  TEMPLATES: '/templates',

  EXFIL: '/exfil',
  EXFIL_KEYCHAIN: '/exfil/keychain',
  EXFIL_WIFI: '/exfil/wifi',
  EXFIL_CONTACTS: '/exfil/contacts',
  EXFIL_SMS: '/exfil/sms',
  EXFIL_CALLS: '/exfil/calls',
  EXFIL_PHOTOS: '/exfil/photos',
  EXFIL_FILES: '/exfil/files',

  WALLETS: '/wallets',
  COMMANDS: '/commands',
  SCRIPTS: '/scripts',

  LOGS: '/logs',
  AUDIT: '/audit',
  NOTIFICATIONS: '/notifications',

  USERS: '/users',
  AGENTS: '/agents',

  SETTINGS: '/settings',
  PROFILE: '/profile',

  CATCH_ALL: '/:pathMatch(.*)*',
}

// Same values, re-exported as the same set used by auth flow + guards
// (Keep in sync with backend `fe.route_login` / `fe.route_dashboard` defaults.)
export const DEFAULT_AFTER_LOGIN = PATHS.DASHBOARD
export const LOGIN_PAGE = PATHS.LOGIN

export default PATHS
