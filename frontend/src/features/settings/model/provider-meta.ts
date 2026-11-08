/**
 * Provider 展示名与本地 logo 映射。
 *
 * 模型目录只返回 provider code（如 `openai`），未接入的供应商也没有连接记录可读，
 * 因此展示名与图标在本地补齐；未知 code 回退为首字母大写，避免出现空占位。
 * logo 文件位于 `public/logo/`，通过站点根路径直接引用。
 */
export interface ProviderMeta {
  code: string
  name: string
  logoSrc: string | null
}

type ProviderBrand = Omit<ProviderMeta, 'code'>

const PROVIDER_BRANDS: Readonly<Record<string, ProviderBrand>> = {
  openai: { name: 'OpenAI', logoSrc: '/logo/openai.svg' },
  deepseek: { name: 'DeepSeek', logoSrc: '/logo/deepseek-color.svg' },
  qwen: { name: 'Qwen', logoSrc: '/logo/qwen-color.svg' },
  dashscope: { name: 'Alibaba Cloud', logoSrc: '/logo/alibabacloud-color.svg' },
  alibaba: { name: 'Alibaba Cloud', logoSrc: '/logo/alibabacloud-color.svg' },
  'alibaba-cloud': { name: 'Alibaba Cloud', logoSrc: '/logo/alibabacloud-color.svg' },
  volcengine: { name: 'Volcengine', logoSrc: '/logo/bytedance-color.svg' },
  bytedance: { name: 'ByteDance', logoSrc: '/logo/bytedance-color.svg' },
  gemini: { name: 'Gemini', logoSrc: '/logo/gemini-color.svg' },
  google: { name: 'Google', logoSrc: '/logo/gemini-color.svg' },
  anthropic: { name: 'Anthropic', logoSrc: '/logo/claude-color.svg' },
  claude: { name: 'Claude', logoSrc: '/logo/claude-color.svg' },
}

const DEFAULT_PROVIDER_NAME = 'Provider'

const toFallbackName = (code: string): string => {
  const trimmed = code.trim()
  if (trimmed === '') {
    return DEFAULT_PROVIDER_NAME
  }
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

/**
 * 解析 Provider 展示信息。
 *
 * `displayName` 来自服务端连接记录时优先，保证与后端命名一致；
 * 未命中本地品牌表时保留 code 原值，便于排查新增 Provider。
 */
export const getProviderMeta = (code: string, displayName?: string | null): ProviderMeta => {
  const brand = PROVIDER_BRANDS[code.trim().toLowerCase()]

  return {
    code,
    name: displayName?.trim() || brand?.name || toFallbackName(code),
    logoSrc: brand?.logoSrc ?? null,
  }
}
