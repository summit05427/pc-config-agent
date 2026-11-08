// 本地存储键统一登记，避免散落在各处的字符串
// 注意：index.html 首屏脚本需要同步读取 app-state 中的 theme，修改时需一并更新
// Access Token 只存内存、刷新令牌只在 HttpOnly Cookie 里，这里不登记任何凭证键
export const STORAGE_KEYS = {
  appState: 'app-state',
  agentThread: 'agent-thread',
  // 本地生成、服务端首轮结束前尚未落库的会话 ID
  agentDraftThread: 'agent-draft-thread',
} as const
