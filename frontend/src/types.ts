export interface Kpi {
  key: string
  label: string
  weight: number
  value: number
  contribution: number
  detail: string
  source_record_ids?: string[]
}

export interface RiskTrigger {
  code: string
  label: string
  detail: string
  source_record_ids: string[]
}

export interface NextAction {
  recommended_action: string
  system_control: string
}

export interface TrendPoint { period: string; value: number }

export interface Scorecard {
  vendor_code: string
  name: string
  type: 'supplier' | 'service_provider'
  category: string
  country: string
  status: string
  blocked_flag: number
  kpis: Kpi[]
  final_score: number
  classification: string
  risk: string
  risk_triggers: RiskTrigger[]
  next_action: NextAction
  trend: TrendPoint[]
}

export interface VendorsResponse {
  vendors: Scorecard[]
  summary: {
    total: number
    classification: Record<string, number>
    risk: Record<string, number>
  }
  as_of: string
}

export interface Alerts {
  expiring_documents: any[]
  expired_mandatory_documents: any[]
  hse_incidents: any[]
  overdue_capa: any[]
  boundary_cases: any[]
  as_of: string
}

export type AskEvent =
  | { type: 'token'; content: string }
  | { type: 'tool_use'; name: string; input: any }
  | { type: 'citation'; vendor_code?: string; record_id: string; trigger?: string }
  | { type: 'notice'; content: string }
  | { type: 'done' }
