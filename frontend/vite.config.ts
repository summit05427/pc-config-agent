import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Tailwind v4 通过 Vite 插件接入，无需 tailwind.config.js
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 与同机其它项目错开：宿主机 5173 可能已被另一套项目占用
    port: 5273,
    strictPort: true,
    // 本地开发保持与生产一致的相对路径：同源请求才会带上 /auth/refresh 需要的
    // HttpOnly Cookie；直连 8080 属于跨源，浏览器不会转发该 Cookie，刷新即掉登录。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        // 必须保留浏览器原始 Host：Java 用 Origin 与 Host 判同源（/auth/refresh 的 CSRF 兜底），
        // 改成后端主机名会被判为跨域，而白名单为空时所有 /api 请求都会 403。
        changeOrigin: false,
      },
      '/agent': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // 生产由 Nginx 剥离 /agent 前缀，这里保持一致
        rewrite: (path) => path.replace(/^\/agent/, ''),
      },
    },
  },
})
