/// <reference types="vitest/config" />
import path from 'path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import { playwright } from '@vitest/browser-playwright'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 第三个参数传空字符串：允许读取未加 VITE_ 前缀的变量用于本地代理配置
  const env = loadEnv(mode, process.cwd(), '')

  // 生产由 frontend Nginx 以 /admin/ 暴露，构建产物需带同样前缀；
  // 本地开发默认 /，避免访问地址变成 http://localhost:5274/admin/。
  const basePath = env.VITE_BASE_PATH?.trim() || '/'
  const viteBase = basePath.endsWith('/') ? basePath : `${basePath}/`

  return {
    base: viteBase,
    plugins: [
      tanstackRouter({
        target: 'react',
        autoCodeSplitting: true,
      }),
      react(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      // 与前台开发服务器（5273）及同机其它项目（5173/5174）都错开
      port: 5274,
      strictPort: true,
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://localhost:18080',
          // 保留浏览器原始 Host：Java 对 refresh/logout 做同源 Origin 校验，
          // 改写 Host 会让 localhost:5274 被判为跨域来源。
          changeOrigin: false,
        },
      },
    },
    test: {
      silent: 'passed-only',
      unstubEnvs: true,
      browser: {
        enabled: true,
        provider: playwright(),
        instances: [{ browser: 'chromium' }],
      },
      coverage: {
        exclude: [
          'src/components/ui/**',
          'src/assets/**',
          'src/routeTree.gen.ts',
          'src/test-utils/**',
          'src/routes/**',
        ],
      },
    },
  }
})
