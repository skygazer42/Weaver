import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { getModelProviders } from '../lib/models'
import { translations } from '../lib/i18n/translations'

test('backend model allowlists are grouped by vendor with concise names and stable provider IDs', () => {
  const options = [
    'gpt-4.1', 'Pro/deepseek-ai/DeepSeek-V3', 'Pro/Qwen/Qwen3-235B',
    'zai-org/GLM-4.6', 'THUDM/GLM-4.1', 'Pro/moonshotai/Kimi-K2',
    'tencent/Hunyuan-A13B', 'meituan-longcat/LongCat-Flash', 'PaddlePaddle/PaddleOCR-VL',
    'Pro/MiniMaxAI/MiniMax-M2', 'ByteDance-Seed/Seed-OSS', 'Pro/acme/Research', 'local-model',
    'Pro/Qwen/Qwen3-235B',
  ]
  const providers = getModelProviders(options)
  assert.deepEqual(providers.map(({ id, name }) => [id, name]), [
    ['openai', 'OpenAI'], ['deepseek', 'DeepSeek'], ['qwen', 'Qwen'], ['zhipu', 'Zhipu GLM'],
    ['moonshot', 'Moonshot'], ['tencent', 'Tencent'], ['meituan', 'Meituan'],
    ['paddlepaddle', 'PaddlePaddle'], ['minimax', 'MiniMax'], ['bytedance', 'ByteDance'],
    ['acme', 'acme'], ['other', 'Other'],
  ])
  const models = providers.flatMap(provider => provider.models)
  assert.deepEqual(new Set(models.map(model => model.id)), new Set(options))
  assert.equal(models.length, new Set(options).size)
  assert.equal(models.find(model => model.id === 'Pro/deepseek-ai/DeepSeek-V3')?.name, 'DeepSeek-V3')
  assert.equal(models.find(model => model.id === 'gpt-4.1')?.name, 'GPT-4.1')
})

test('static fallback and backend vision models retain their vision badges', () => {
  const fallback = getModelProviders()
  assert.deepEqual(getModelProviders([]), fallback)
  const staticModels = fallback.flatMap(provider => provider.models)
  assert.equal(staticModels.find(model => model.id === 'qwen3-vl-flash')?.isVision, true)
  assert.equal(staticModels.find(model => model.id === 'glm-4.6v')?.isVision, true)
  const models = getModelProviders(['Qwen/Qwen3-VL', 'org/model-vl', 'zai-org/glm-4.6v', 'org/OCR', 'org/text'])
    .flatMap(provider => provider.models)
  assert.deepEqual(Object.fromEntries(models.map(model => [model.id, model.isVision])), {
    'Qwen/Qwen3-VL': true, 'org/model-vl': true, 'zai-org/glm-4.6v': true, 'org/OCR': true, 'org/text': false,
  })
})

test('gateway organization prefixes and unprefixed model IDs share vendor groups', () => {
  const groups = [
    ['openai', 'OpenAI', ['openai/gpt-4.1', 'gpt-5-mini', 'o1-preview', 'o3', 'o4-mini']],
    ['anthropic', 'Anthropic', ['Anthropic/claude-sonnet-4', 'claude-opus-4']],
    ['google', 'Google', ['google/gemini-2.5-pro', 'gemini-2.5-flash']],
    ['meta', 'Meta', ['meta-llama/Llama-3.3-70B-Instruct', 'llama3.2:latest']],
    ['mistral', 'Mistral', ['mistralai/Mistral-Small', 'mistral:latest', 'mixtral-8x7b']],
    ['xai', 'xAI', ['x-ai/grok-4', 'grok-3']],
    ['deepseek', 'DeepSeek', ['deepseek/deepseek-chat', 'deepseek-ai/DeepSeek-R1', 'deepseek-r1:32b']],
    ['qwen', 'Qwen', ['Qwen/Qwen3-32B', 'qwen3:8b', 'qwq:32b']],
    ['zhipu', 'Zhipu GLM', ['zai-org/GLM-4.6', 'THUDM/GLM-4.5', 'glm-4.7']],
    ['moonshot', 'Moonshot', ['moonshotai/Kimi-K2', 'kimi-k2-thinking']],
    ['tencent', 'Tencent', ['tencent/Hunyuan-A13B', 'hunyuan-turbos']],
    ['minimax', 'MiniMax', ['MiniMaxAI/MiniMax-M2', 'minimax-m2']],
    ['bytedance', 'ByteDance', ['ByteDance-Seed/Seed-OSS', 'seed-oss-36b']],
  ] as const
  const providers = getModelProviders(groups.flatMap(([, , ids]) => ids))
  for (const [id, name, ids] of groups) {
    const provider = providers.find(provider => provider.id === id)
    assert.equal(provider?.name, name)
    assert.deepEqual(provider?.models.map(model => model.id), ids)
  }
  assert.deepEqual(getModelProviders(['ollama/llama3.2:latest'])[0].id, 'meta')
  assert.equal(getModelProviders(['acme/custom-model'])[0].name, 'acme')
})

test('reasoning badges recognize model families without matching unrelated substrings', () => {
  const reasoning = [
    'Pro/deepseek-ai/DeepSeek-R1-0528', 'deepseek-reasoner', 'Qwen/QwQ-32B', 'qwq:latest',
    'google/gemini-2.0-flash-thinking-exp', 'openai/o1', 'o3-mini', 'o4-mini-high',
    'moonshotai/Kimi-K2-Thinking', 'microsoft/Phi-4-reasoning-plus',
  ]
  const other = ['gpt-4.1', 'deepseek-chat', 'qwen3:8b', 'o10', 'org/color1', 'thinking-org/standard']
  const models = getModelProviders([...reasoning, ...other]).flatMap(provider => provider.models)
  assert.deepEqual(models.filter(model => model.isReasoning).map(model => model.id).sort(), reasoning.sort())
  assert.equal(getModelProviders().flatMap(provider => provider.models).find(model => model.id === 'deepseek-reasoner')?.isReasoning, true)
})

test('all four locales translate model roles, routing, badges, and catalog sources', () => {
  const keys = [
    'primaryModel', 'reasoningModel', 'primaryRole', 'reasoningRole', 'followPrimaryModel',
    'modelRouting', 'primaryModelDescription', 'reasoningModelDescription', 'followPrimaryDescription',
    'reasoningBadge', 'visionBadge', 'proBadge', 'catalogSourceGateway', 'catalogSourceSiliconFlow',
    'catalogSourceStatic', 'modelCatalogCount',
  ] as const
  for (const locale of ['en', 'zh', 'ja', 'ko'] as const) {
    for (const key of keys) assert.ok(translations[locale][key], `${locale}: ${key}`)
    assert.ok(translations[locale].modelCatalogCount.includes('{count}'))
  }
})
