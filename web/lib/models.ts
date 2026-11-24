export interface ModelOption {
  id: string
  name: string
  isVision: boolean
  isPro: boolean
}

export interface ModelProvider {
  id: string
  name: string
  models: ModelOption[]
}

const vendors: Record<string, { id: string; name: string }> = {
  'deepseek-ai': { id: 'deepseek', name: 'DeepSeek' },
  Qwen: { id: 'qwen', name: 'Qwen' },
  'zai-org': { id: 'zhipu', name: 'Zhipu GLM' },
  THUDM: { id: 'zhipu', name: 'Zhipu GLM' },
  moonshotai: { id: 'moonshot', name: 'Moonshot' },
  tencent: { id: 'tencent', name: 'Tencent' },
  'meituan-longcat': { id: 'meituan', name: 'Meituan' },
  PaddlePaddle: { id: 'paddlepaddle', name: 'PaddlePaddle' },
  MiniMaxAI: { id: 'minimax', name: 'MiniMax' },
  'ByteDance-Seed': { id: 'bytedance', name: 'ByteDance' },
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
    const normalized = id.replace(/^Pro\//, '')
    const org = normalized.includes('/') ? normalized.split('/')[0] : null
    const provider = model
      ? { id: model.providerId, name: model.provider }
      : org ? vendors[org] ?? { id: org.toLowerCase(), name: org } : { id: 'other', name: 'Other' }
    if (!providers.has(provider.id)) providers.set(provider.id, { ...provider, models: [] })
    providers.get(provider.id)!.models.push({
      id,
      name: model?.name ?? normalized.slice(normalized.lastIndexOf('/') + 1),
      isVision: /vl|4\.6v|ocr/i.test(id),
      isPro: id.startsWith('Pro/'),
    })
  }

  return Array.from(providers.values())
}
