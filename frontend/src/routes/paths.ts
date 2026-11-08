/** 路由路径唯一登记处：守卫、导航与重定向都引用常量，避免字符串散落 */
export const ROUTE_PATHS = {
  welcome: '/',
  welcomeAlias: '/welcome',
  login: '/login',
  chatNew: '/chat/new',
  chatSession: '/chat/$sessionId',
  settings: '/settings',
  settingsSection: '/settings/$section',
  designSystem: '/design-system',
  openUiDemo: '/dev/openui',
  forbidden: '/403',
} as const
