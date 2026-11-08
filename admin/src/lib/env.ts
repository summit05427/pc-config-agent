import { z } from 'zod'

/**
 * 管理端运行时配置。
 *
 * 统一从这里读取 `import.meta.env`，业务代码不直接访问，避免配置项散落。
 * 校验失败直接抛错（fail-fast），防止用错误地址打包出不可用的产物。
 */
const envSchema = z.object({
  VITE_APP_TITLE: z.string().min(1).default('Agent 管理后台'),
  VITE_API_BASE_URL: z.string().min(1).default('/api/v1'),
  VITE_BASE_PATH: z
    .string()
    .min(1)
    .default('/')
    .refine((value) => value.startsWith('/'), {
      message: 'VITE_BASE_PATH 必须以 / 开头',
    }),
})

const parsed = envSchema.safeParse(import.meta.env)

if (!parsed.success) {
  throw new Error(`环境变量校验失败：${parsed.error.message}`)
}

// 去掉结尾斜杠后交给 Router；根路径用 undefined 表示「不启用 basepath」
const normalizedBasePath = parsed.data.VITE_BASE_PATH.replace(/\/+$/, '')

export const env = {
  appTitle: parsed.data.VITE_APP_TITLE,
  // 去掉结尾斜杠，避免拼接出 /api/v1//auth/login
  apiBaseUrl: parsed.data.VITE_API_BASE_URL.replace(/\/+$/, ''),
  // Vite 的 base 需要以 / 结尾，Router 的 basepath 不能带结尾斜杠
  viteBasePath: parsed.data.VITE_BASE_PATH.endsWith('/')
    ? parsed.data.VITE_BASE_PATH
    : `${parsed.data.VITE_BASE_PATH}/`,
  routerBasePath:
    normalizedBasePath === '' || normalizedBasePath === '/'
      ? undefined
      : normalizedBasePath,
} as const
