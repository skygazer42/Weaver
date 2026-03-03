export type HitlDecisionType = 'approve' | 'edit' | 'reject'

export type HitlDecision =
  | { type: 'approve' }
  | { type: 'reject'; message?: string }
  | {
      type: 'edit'
      edited_action: { name: string; args: Record<string, unknown> }
    }

export type HitlActionRequest = {
  name: string
  args: Record<string, unknown>
  description?: string
}

export type HitlReviewConfig = {
  action_name: string
  allowed_decisions: HitlDecisionType[]
  args_schema?: Record<string, unknown>
}

export type HitlToolApprovalRequest = {
  action_requests: HitlActionRequest[]
  review_configs: HitlReviewConfig[]
}

export function isHitlToolApprovalRequest(value: unknown): value is HitlToolApprovalRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  if (!Array.isArray(record.action_requests) || !Array.isArray(record.review_configs)) return false
  return true
}

type BuildDecision =
  | { type: 'approve' }
  | { type: 'reject'; message?: string }
  | { type: 'edit'; editedArgs: Array<Record<string, unknown> | undefined> }

export function buildHitlDecisions(request: HitlToolApprovalRequest, decision: BuildDecision): HitlDecision[] {
  const actionRequests = Array.isArray(request.action_requests) ? request.action_requests : []

  if (decision.type === 'approve') {
    return actionRequests.map(() => ({ type: 'approve' }))
  }

  if (decision.type === 'reject') {
    return actionRequests.map(() =>
      decision.message ? ({ type: 'reject', message: decision.message } as const) : ({ type: 'reject' } as const),
    )
  }

  const editedArgs = Array.isArray(decision.editedArgs) ? decision.editedArgs : []
  return actionRequests.map((req, idx) => {
    const args = editedArgs[idx] ?? req.args ?? {}
    return {
      type: 'edit',
      edited_action: {
        name: req.name,
        args: args && typeof args === 'object' && !Array.isArray(args) ? args : {},
      },
    }
  })
}

