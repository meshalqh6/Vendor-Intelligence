import axios from 'axios'
import type { AskEvent, Alerts, OpportunityMatchRequest, OpportunityMatchResponse, Scorecard, VendorsResponse } from './types'

const BASE = import.meta.env.VITE_API_URL || '/api'
const client = axios.create({ baseURL: BASE })

export async function getVendors(params?: Record<string, string>): Promise<VendorsResponse> {
  return (await client.get('/vendors', { params })).data
}

export async function getVendor(code: string): Promise<Scorecard> {
  return (await client.get(`/vendors/${code}`)).data
}

export async function getRecords(code: string, table: string): Promise<{ rows: any[] }> {
  return (await client.get(`/vendors/${code}/records`, { params: { table } })).data
}

export async function getAlerts(): Promise<Alerts> {
  return (await client.get('/alerts')).data
}

export async function getHealth(): Promise<any> {
  return (await client.get('/health', { baseURL: BASE.replace(/\/api$/, '') })).data
}

export async function getConfig(): Promise<any> {
  return (await client.get('/config')).data
}

export async function sendFollowup(payload: any): Promise<{ status: string; reference: string; queued_at: string }> {
  return (await client.post('/followup', payload)).data
}

/** Stream the /ask SSE endpoint, invoking onEvent for each parsed event. */
export async function askStream(
  question: string,
  history: { role: string; content: string }[],
  onEvent: (e: AskEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history }),
  })
  if (!res.body) return
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() || ''
    for (const chunk of chunks) {
      const line = chunk.trim()
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6)) as AskEvent) } catch { /* ignore */ }
      }
    }
  }
}

export async function matchVendors(payload: OpportunityMatchRequest): Promise<OpportunityMatchResponse> {
  return (await client.post('/opportunities/match', payload)).data
}
