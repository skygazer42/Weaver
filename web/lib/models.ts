export interface ModelOption {
  id: string
  name: string
  isVision: boolean
  isPro: boolean
  isReasoning: boolean
}

export interface ModelProvider {
  id: string
  name: string
  models: ModelOption[]
}

const vendors: Record<string, { id: string; name: string }> = {
  openai: { id: 'openai', name: 'OpenAI' },
  anthropic: { id: 'anthropic', name: 'Anthropic' },
  google: { id: 'google', name: 'Google' },
  'meta-llama': { id: 'meta', name: 'Meta' },
  meta: { id: 'meta', name: 'Meta' },
  mistralai: { id: 'mistral', name: 'Mistral' },
  mistral: { id: 'mistral', name: 'Mistral' },
  'x-ai': { id: 'xai', name: 'xAI' },
  xai: { id: 'xai', name: 'xAI' },
  deepseek: { id: 'deepseek', name: 'DeepSeek' },
  'deepseek-ai': { id: 'deepseek', name: 'DeepSeek' },
  qwen: { id: 'qwen', name: 'Qwen' },
  'zai-org': { id: 'zhipu', name: 'Zhipu GLM' },
  thudm: { id: 'zhipu', name: 'Zhipu GLM' },
  moonshotai: { id: 'moonshot', name: 'Moonshot' },
  tencent: { id: 'tencent', name: 'Tencent' },
  'meituan-longcat': { id: 'meituan', name: 'Meituan' },
  paddlepaddle: { id: 'paddlepaddle', name: 'PaddlePaddle' },
  minimaxai: { id: 'minimax', name: 'MiniMax' },
  minimax: { id: 'minimax', name: 'MiniMax' },
  'bytedance-seed': { id: 'bytedance', name: 'ByteDance' },
  cohere: { id: 'cohere', name: 'Cohere' },
  microsoft: { id: 'microsoft', name: 'Microsoft' },
  nvidia: { id: 'nvidia', name: 'NVIDIA' },
  perplexity: { id: 'perplexity', name: 'Perplexity' },
}

function inferVendor(name: string) {
  if (/^(?:gpt-|chatgpt-|o[134](?:[.-]|$))/i.test(name)) return vendors.openai
  if (/^claude-/i.test(name)) return vendors.anthropic
  if (/^gemini-/i.test(name)) return vendors.google
  if (/^deepseek/i.test(name)) return vendors.deepseek
  if (/^(?:qwen|qwq)/i.test(name)) return vendors.qwen
  if (/^glm/i.test(name)) return vendors['zai-org']
  if (/^llama/i.test(name)) return vendors.meta
  if (/^(?:mistral|mixtral)/i.test(name)) return vendors.mistral
  if (/^grok/i.test(name)) return vendors.xai
  if (/^kimi/i.test(name)) return vendors.moonshotai
  if (/^minimax/i.test(name)) return vendors.minimax
  if (/^hunyuan/i.test(name)) return vendors.tencent
  if (/^seed-/i.test(name)) return vendors['bytedance-seed']
  return null
}

const staticModels = [
  { id: 'gpt-5', name: 'GPT-5', providerId: 'openai', provider: 'OpenAI' },
  { id: 'gpt-4.1', name: 'GPT-4.1', providerId: 'openai', provider: 'OpenAI' },
  { id: 'gpt-4o', name: 'GPT-4o', providerId: 'openai', provider: 'OpenAI' },
  { id: 'claude-sonnet-4-5-20250514', name: 'Claude Sonnet 4.5', providerId: 'anthropic', provider: 'Anthropic' },
  { id: 'claude-opus-4-20250514', name: 'Claude Opus 4', providerId: 'anthropic', provider: 'Anthropic' },
  { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4', providerId: 'anthropic', provider: 'Anthropic' },
  { id: 'deepseek-chat', name: 'deepseek-chat', providerId: 'deepseek', provider: 'DeepSeek' },
  { id: 'deepseek-reasoner', name: 'deepseek-reasoner', providerId: 'deepseek', provider: 'DeepSeek' },
  { id: 'qwen-plus', name: 'qwen-plus', providerId: 'qwen', provider: 'Qwen' },
  { id: 'qwen3-vl-flash', name: 'qwen3-vl-flash', providerId: 'qwen', provider: 'Qwen' },
  { id: 'glm-4.6', name: 'GLM-4.6', providerId: 'zhipu', provider: 'Zhipu GLM' },
  { id: 'glm-4.6v', name: 'glm-4.6v', providerId: 'zhipu', provider: 'Zhipu GLM' },
]

export function getModelProviders(options?: readonly string[]): ModelProvider[] {
  const known = new Map(staticModels.map(model => [model.id, model]))
  const ids = options?.length ? new Set(options) : known.keys()
  const providers = new Map<string, ModelProvider>()

  for (const id of ids) {
    const model = known.get(id)
    const normalized = id.replace(/^Pro\//i, '')
    const name = normalized.slice(normalized.lastIndexOf('/') + 1)
    const org = normalized.includes('/') ? normalized.split('/')[0] : null
    const provider = model
      ? { id: model.providerId, name: model.provider }
      : (org && vendors[org.toLowerCase()]) || inferVendor(name) || (org ? { id: org.toLowerCase(), name: org } : { id: 'other', name: 'Other' })
    if (!providers.has(provider.id)) providers.set(provider.id, { ...provider, models: [] })
    providers.get(provider.id)!.models.push({
      id,
      name: model?.name ?? name,
      isVision: /vl|4\.6v|ocr/i.test(id),
      isPro: /^Pro\//i.test(id),
      isReasoning: /(?:^|[-_.:])(?:r1|reasoner|reasoning|thinking|qwq\d*|o[134])(?:[-_.:]|$)/i.test(name),
    })
  }

  return Array.from(providers.values())
}
