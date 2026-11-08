import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// 单测与构建共用同一套别名与 React 转换，业务代码里的 @/ 导入无需改动
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.spec.ts', 'src/**/*.spec.tsx'],
    setupFiles: ['./src/test/setup.ts'],
    clearMocks: true,
    restoreMocks: true,
    // 官方原语 dist 内部使用无扩展名相对导入，Node 解析器不支持；
    // 内联后交给 Vite 解析器处理，才能与运行时、构建保持一致
    server: {
      deps: {
        inline: ['@openuidev/react-ui'],
      },
    },
    // S1 阶段骨架里还没有单测文件，先允许空集合通过；后续阶段新增测试后自然生效
    passWithNoTests: true,
    coverage: {
      provider: 'v8',
      include: [
        'src/core/http/**',
        'src/features/*/api/**',
        'src/features/chat/runtime/**',
        'src/features/chat/hooks/**',
        'src/routes/**',
      ],
      // 纯类型文件、barrel 导出与测试自身不产生可执行分支，统计时排除
      exclude: ['src/**/*.spec.ts', 'src/**/*.spec.tsx', 'src/**/index.ts', 'src/**/types.ts'],
      thresholds: {
        lines: 80,
      },
    },
  },
})
