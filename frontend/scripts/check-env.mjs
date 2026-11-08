#!/usr/bin/env node
// 生产构建前的环境变量硬校验。
// 使用 Vite 自身的 loadEnv 读取 .env* 与 process.env（VITE_ 前缀），
// 保证校验结果与 `vite build` 实际打包进去的值完全一致。
import process from 'node:process'
import { loadEnv } from 'vite'

const MODE_FLAG = '--mode'
const DEFAULT_MODE = 'production'
const REQUIRED_KEYS = ['VITE_APP_ENV', 'VITE_APP_TITLE', 'VITE_API_BASE_URL']
// VITE_ 变量会被原样打进前端产物，这些名字一旦出现基本可以判定是在放密钥
const FORBIDDEN_NAME_PATTERNS = ['SECRET', 'PASSWORD', 'TOKEN', 'PRIVATE_KEY', 'API_KEY']
const FORBIDDEN_BASE_URL_PATTERNS = ['http://', 'localhost', '127.0.0.1', '0.0.0.0', 'file://']

/** 解析 `--mode production` / `--mode=production` 两种写法 */
const parseMode = (args) => {
  const inlineArg = args.find((arg) => arg.startsWith(`${MODE_FLAG}=`))
  if (inlineArg) {
    return inlineArg.slice(MODE_FLAG.length + 1)
  }

  const flagIndex = args.indexOf(MODE_FLAG)
  if (flagIndex !== -1 && args[flagIndex + 1]) {
    return args[flagIndex + 1]
  }

  return DEFAULT_MODE
}

const isPositiveInteger = (value) => /^[1-9]\d*$/.test(value)

const isAllowedBaseUrl = (value) => {
  if (FORBIDDEN_BASE_URL_PATTERNS.some((pattern) => value.toLowerCase().includes(pattern))) {
    return false
  }

  // 同源相对路径（/api/v1），或显式 https 绝对地址
  return (value.startsWith('/') && !value.startsWith('//')) || value.startsWith('https://')
}

const collectErrors = (env) => {
  const errors = []

  for (const key of REQUIRED_KEYS) {
    if (!env[key]) {
      errors.push(`缺少必填变量 ${key}（请检查 .env 文件或构建参数注入）`)
    }
  }

  if (env.VITE_APP_ENV && env.VITE_APP_ENV !== 'production') {
    errors.push(`VITE_APP_ENV 必须为 production，当前值不符合要求`)
  }

  if (String(env.VITE_USE_MOCK).toLowerCase() === 'true') {
    errors.push('VITE_USE_MOCK 必须为 false，生产包禁止启用 Mock 数据')
  }

  if (env.VITE_API_BASE_URL && !isAllowedBaseUrl(env.VITE_API_BASE_URL)) {
    errors.push(
      'VITE_API_BASE_URL 只允许以 / 开头的同源相对路径（如 /api/v1）或 https:// 绝对地址，' +
        '禁止 http://、localhost、127.0.0.1、0.0.0.0、file://',
    )
  }

  if (env.VITE_AGENT_BASE_URL && !isAllowedBaseUrl(env.VITE_AGENT_BASE_URL)) {
    errors.push(
      'VITE_AGENT_BASE_URL 只允许以 / 开头的同源相对路径（如 /agent/api/v1）或 https:// 绝对地址，' +
        '禁止 http://、localhost、127.0.0.1、0.0.0.0、file://',
    )
  }

  if (env.VITE_API_TIMEOUT && !isPositiveInteger(env.VITE_API_TIMEOUT)) {
    errors.push('VITE_API_TIMEOUT 必须为正整数（毫秒）')
  }

  for (const key of Object.keys(env)) {
    if (!key.startsWith('VITE_')) {
      continue
    }

    const upperKey = key.toUpperCase()
    if (FORBIDDEN_NAME_PATTERNS.some((pattern) => upperKey.includes(pattern))) {
      // 只报变量名，不打印变量值，避免把疑似密钥写进 CI 日志
      errors.push(`变量 ${key} 的命名疑似敏感信息（VITE_ 变量会打包进前端产物，禁止存放密钥/Token）`)
    }
  }

  return errors
}

const mode = parseMode(process.argv.slice(2))
const env = loadEnv(mode, process.cwd(), 'VITE_')
const errors = collectErrors(env)

if (errors.length > 0) {
  console.error(`[check-env] 生产构建环境校验失败（mode=${mode}），共 ${errors.length} 项：`)
  errors.forEach((message, index) => {
    console.error(`  ${index + 1}. ${message}`)
  })
  console.error('[check-env] 请修正后重新执行构建。')
  process.exit(1)
}

console.log(`[check-env] 环境校验通过（mode=${mode}），可以执行生产构建。`)
