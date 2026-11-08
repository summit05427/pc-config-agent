import { defineConfig, devices } from '@playwright/test'

const PORT = 5273
// Windows 下 Vite 默认仅监听 localhost（可能解析到 IPv6 回环），
// 这里与 dev server 保持同一地址，避免 127.0.0.1 探测被拒绝。
const BASE_URL = `http://localhost:${PORT}`

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  // Vite dev server 按需编译，并行 6 个 worker 时首个访问对话页的用例首帧可能
  // 超过默认 5s 的轮询预算，会把冷启动抖动误判成断言失败
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // 复用本地已启动的 dev server，避免每次跑 e2e 都新起一个端口。
  // 通过 corepack 启动，确保使用 package.json 固定的 pnpm 版本，而不是机器上的全局 pnpm。
  webServer: {
    command: 'corepack pnpm dev',
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
