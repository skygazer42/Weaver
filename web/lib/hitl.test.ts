import { describe, expect, it } from 'vitest'

import { buildHitlDecisions, type HitlToolApprovalRequest } from './hitl'

describe('HITL helpers', () => {
  const request: HitlToolApprovalRequest = {
    action_requests: [
      {
        name: 'browser_search',
        args: { query: 'cats' },
        description: 'Tool execution pending approval\n\nTool: browser_search\nArgs: {"query":"cats"}',
      },
      {
        name: 'execute_python_code',
        args: { code: 'print(1)' },
        description: 'Tool execution pending approval\n\nTool: execute_python_code\nArgs: {"code":"print(1)"}',
      },
    ],
    review_configs: [
      { action_name: 'browser_search', allowed_decisions: ['approve', 'edit', 'reject'] },
      { action_name: 'execute_python_code', allowed_decisions: ['approve', 'edit', 'reject'] },
    ],
  }

  it('builds approve decisions for every action request', () => {
    expect(buildHitlDecisions(request, { type: 'approve' })).toEqual([
      { type: 'approve' },
      { type: 'approve' },
    ])
  })

  it('builds reject decisions for every action request (with message)', () => {
    expect(buildHitlDecisions(request, { type: 'reject', message: 'No tools.' })).toEqual([
      { type: 'reject', message: 'No tools.' },
      { type: 'reject', message: 'No tools.' },
    ])
  })

  it('builds edit decisions, defaulting missing edits to original args', () => {
    expect(
      buildHitlDecisions(request, { type: 'edit', editedArgs: [{ query: 'dogs' }, undefined] }),
    ).toEqual([
      {
        type: 'edit',
        edited_action: { name: 'browser_search', args: { query: 'dogs' } },
      },
      {
        type: 'edit',
        edited_action: { name: 'execute_python_code', args: { code: 'print(1)' } },
      },
    ])
  })
})

