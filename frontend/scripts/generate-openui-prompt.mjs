#!/usr/bin/env node
/**
 * 从 OPENUI_LIBRARY 生成 Agent 侧的组件提示词。
 *
 * 组件签名只能有一份事实来源，因此这里直接加载 library/index.ts，
 * 不做任何手写清单；--check 用于 CI 比对，发现漂移立即失败。
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import { createServer } from 'vite'

const FRONTEND_ROOT = fileURLToPath(new URL('..', import.meta.url))
const LIBRARY_ENTRY = '/src/features/generative-ui/library/index.ts'
const PROMPTS_DIR = fileURLToPath(new URL('../../agent-service/app/agent/prompts/', import.meta.url))
const OUTPUT_PATH = fileURLToPath(new URL('../../agent-service/app/agent/prompts/openui.md', import.meta.url))
const IS_CHECK_MODE = process.argv.includes('--check')
const HEADER =
  '<!-- 由 frontend/scripts/generate-openui-prompt.mjs 生成，请勿手改；执行 corepack pnpm --dir frontend openui:prompt 重新生成。 -->'

// 官方 prompt 要求「整条回复只能是 openui-lang」，与项目约定的 ```openui 围栏块冲突。
// 这里替换官方首段并追加输出约定，让模型只在围栏内输出 DSL，围栏外允许简短 Markdown。
const PROJECT_PREAMBLE =
  'You are an AI assistant that can present rich, interactive UI using openui-lang, a declarative UI language. When a UI is the best answer, put the complete openui-lang program in a Markdown fenced code block whose info string is exactly "openui"; you may write brief Markdown outside the block. If a UI is not appropriate, answer with normal Markdown only.'

const PROJECT_OUTPUT_CONVENTION = `## Project Output Convention (highest priority)

- Present UI only inside a Markdown fenced code block: the opening fence is three backticks followed by \`openui\`, and the closing fence is three backticks.
- The first line inside the fence must be \`root = Stack(...)\`. Never emit openui-lang statements outside a fence.
- A short Markdown explanation may appear outside the fence. If the answer cannot be expressed with the available components, answer in normal Markdown; do not invent component names.
- The number of UI blocks is capped by the "输出规模限制" section appended by the server.
- Do not use \`Form\` (or other input components) to collect fields the system still needs for clarification. Missing budget/scenario is handled by the built-in clarification flow; asking the same values in a Form creates two competing inputs and the Form answers bypass the clarification resume. Use a Form only for optional refinements the user may skip.

Example shape:

\`\`\`openui
root = Stack([...])
\`\`\``

/**
 * 用项目输出约定替换官方首段。
 *
 * 依赖官方 prompt 的固定结构：首段之后紧跟 `## Syntax Rules`。结构变化时直接失败，
 * 避免静默生成一份没有围栏约定的契约。
 */
function applyProjectOutputConvention(prompt) {
  const syntaxMarker = '## Syntax Rules'
  const markerIndex = prompt.indexOf(syntaxMarker)
  if (markerIndex === -1) {
    throw new TypeError('OpenUI prompt 缺少 Syntax Rules 段，需重新确认生成逻辑')
  }
  if (!prompt.slice(0, markerIndex).includes('ENTIRE response must be valid openui-lang')) {
    throw new TypeError('OpenUI prompt 首段已变化，需重新确认替换位置')
  }

  const body = prompt.slice(markerIndex).trim()
  return `${PROJECT_PREAMBLE}\n\n${body}\n\n${PROJECT_OUTPUT_CONVENTION}`
}

/** Vite SSR 只负责解析 TSX 与 `@/` 别名，不加载应用插件，避免 Tailwind 干扰脚本 */
async function buildPrompt() {
  const server = await createServer({
    configFile: false,
    root: FRONTEND_ROOT,
    logLevel: 'error',
    appType: 'custom',
    server: { middlewareMode: true },
    resolve: {
      alias: { '@': fileURLToPath(new URL('../src', import.meta.url)) },
    },
    // 官方 dist 内部使用无扩展名相对导入，默认外置会被 Node ESM 拒绝，
    // 必须交给 Vite 转换；与 vitest.config.ts 的 inline 设置保持一致
    ssr: {
      noExternal: ['@openuidev/react-ui'],
    },
  })

  try {
    const libraryModule = await server.ssrLoadModule(LIBRARY_ENTRY)
    const prompt = libraryModule.OPENUI_LIBRARY.prompt()
    if (typeof prompt !== 'string' || prompt.trim() === '') {
      throw new TypeError('OPENUI_LIBRARY.prompt() 未返回非空字符串')
    }

    return `${HEADER}\n\n${applyProjectOutputConvention(prompt.trim())}\n`
  } finally {
    await server.close()
  }
}

async function main() {
  const content = await buildPrompt()

  if (IS_CHECK_MODE) {
    const current = await readFile(OUTPUT_PATH, 'utf8').catch(() => '')
    if (current !== content) {
      console.error(
        `OpenUI Prompt 已与组件库不一致：${OUTPUT_PATH}\n请执行 corepack pnpm --dir frontend openui:prompt 后重新提交。`,
      )
      process.exitCode = 1
      return
    }

    console.log('OpenUI Prompt 与组件库一致。')
    return
  }

  await mkdir(PROMPTS_DIR, { recursive: true })
  await writeFile(OUTPUT_PATH, content, 'utf8')
  console.log(`已生成 ${OUTPUT_PATH}`)
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
