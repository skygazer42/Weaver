import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { getModelProviders } from '../lib/models'

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
