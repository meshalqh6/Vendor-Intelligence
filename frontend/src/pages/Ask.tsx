import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { askStream } from '../api'
import type { AskEvent } from '../types'

const SUGGESTIONS = [
  'Which of our suppliers are high risk right now, and what\'s driving it?',
  'Al Wajba Packaging scores 96% but you\'ve flagged them high risk — why?',
  'Show me exactly which inspection lots produced Gulf Dairy Feeds\' quality score.',
  'What changes if Doha Calibration Services closes its overdue CAPA this week?',
  'Which vendors have mandatory documents expiring in the next 30 days?',
  'Generate the Q2 evaluation report for all transport and logistics providers.',
]

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string))
}

const CELL_CLASS: Record<string, string> = {
  Preferred: 'b-good', Approved: 'b-info', Conditional: 'b-warn',
  'Reassessment Required': 'b-bad', Reassessment: 'b-bad',
  Low: 'b-good', Medium: 'b-info', Moderate: 'b-warn', High: 'b-bad',
}
function nodeText(node: any): string {
  if (node == null) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(nodeText).join('')
  if (node.props) return nodeText(node.props.children)
  return ''
}
const mdComponents = {
  td({ children, ...props }: any) {
    const raw = nodeText(children).trim()
    const key = raw.replace(/\s*Risk$/i, '')
    if (CELL_CLASS[key]) return <td {...props}><span className={`badge ${CELL_CLASS[key]}`}>{raw}</span></td>
    return <td {...props}>{children}</td>
  },
}

const PRINT_CSS = `
  @page { size: A4; margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color: #0f172a; font-size: 12px; line-height: 1.55; margin: 0; }
  .rpt-head { display: flex; align-items: center; justify-content: space-between;
    border-bottom: 2px solid #4f46e5; padding-bottom: 10px; margin-bottom: 16px; }
  .rpt-brand { display: flex; align-items: center; gap: 8px; font-weight: 800; font-size: 18px; }
  .rpt-logo { width: 26px; height: 26px; border-radius: 6px; background: linear-gradient(135deg,#6366f1,#22d3ee);
    color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 14px; }
  .rpt-meta { color: #64748b; font-size: 11px; }
  .rpt-title { font-size: 16px; margin: 0 0 18px; color: #1e293b; }
  .rpt-foot { margin-top: 26px; padding-top: 10px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 10px; }
  .md h1 { font-size: 16px; margin: 16px 0 8px; padding-bottom: 6px; border-bottom: 1px solid #e2e8f0; }
  .md h2 { font-size: 14px; margin: 16px 0 6px; }
  .md h3 { font-size: 12.5px; margin: 12px 0 4px; color: #334155; }
  .md p { margin: 8px 0; }
  .md ul, .md ol { margin: 6px 0; padding-left: 20px; }
  .md code { font-family: ui-monospace, Menlo, monospace; font-size: 11px; background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
  .md table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 11px; }
  .md th { background: #eef2ff; text-align: left; font-weight: 700; text-transform: uppercase;
    letter-spacing: .4px; font-size: 9.5px; color: #4338ca; padding: 7px 9px; border: 1px solid #c7d2fe; }
  .md td { padding: 7px 9px; border: 1px solid #e2e8f0; vertical-align: middle; }
  .md td:first-child { font-weight: 700; }
  .md tbody tr:nth-child(even) td { background: #fafbff; }
  .md tr { break-inside: avoid; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 10px; font-weight: 700; }
  .b-good { background: #ecfdf5; color: #059669; }
  .b-info { background: #eff6ff; color: #2563eb; }
  .b-warn { background: #fffbeb; color: #b45309; }
  .b-bad { background: #fef2f2; color: #dc2626; }
`

function exportPdf(el: HTMLElement | null, question: string) {
  const html = el?.innerHTML || ''
  const w = window.open('', '_blank', 'width=900,height=1000')
  if (!w) return
  const date = new Date().toLocaleString()
  w.document.write(
    `<!doctype html><html><head><meta charset="utf-8"><title>VendorLens Report</title>` +
    `<style>${PRINT_CSS}</style></head><body>` +
    `<div class="rpt-head"><div class="rpt-brand"><span class="rpt-logo">V</span> VendorLens</div>` +
    `<div class="rpt-meta">Generated ${escapeHtml(date)}</div></div>` +
    `<div class="rpt-title">${escapeHtml(question)}</div>` +
    `<div class="md">${html}</div>` +
    `<div class="rpt-foot">Scores computed by the VendorLens deterministic rules engine. ` +
    `Every figure traces to a source record; the language model retrieves and explains only.</div>` +
    `</body></html>`)
  w.document.close(); w.focus()
  setTimeout(() => w.print(), 500)
}

interface Msg { role: 'user' | 'assistant'; content: string; question?: string; streaming?: boolean }

function AssistantMessage({ msg }: { msg: Msg }) {
  const ref = useRef<HTMLDivElement>(null)
  return (
    <div className="msg assistant">
      <div className="avatar">✦</div>
      <div className="bubble">
        {msg.content ? (
          <>
            <div className="answer md" ref={ref}>
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{msg.content}</ReactMarkdown>
              {msg.streaming && <span className="cursor" />}
            </div>
            {!msg.streaming && (
              <div className="answer-actions">
                <button className="btn-export" onClick={() => exportPdf(ref.current, msg.question || 'VendorLens')}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 3v12" /><path d="m7 11 5 5 5-5" /><path d="M4 20h16" />
                  </svg>
                  Export PDF
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="typing"><span /><span /><span /></div>
        )}
      </div>
    </div>
  )
}

const upd = (arr: Msg[], fn: (m: Msg) => Msg) => arr.map((m, i) => (i === arr.length - 1 ? fn(m) : m))

export default function Ask() {
  const [q, setQ] = useState('')
  const [messages, setMessages] = useState<Msg[]>([])
  const [busy, setBusy] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function run(question: string) {
    if (!question.trim() || busy) return
    setQ('')
    // Prior completed turns become the conversation context for this question.
    const history = messages
      .filter((m) => m.content && !m.streaming)
      .map((m) => ({ role: m.role, content: m.content }))
    setMessages((m) => [...m, { role: 'user', content: question },
                              { role: 'assistant', content: '', question, streaming: true }])
    setBusy(true)
    await askStream(question, history, (e: AskEvent) => {
      if (e.type === 'token') setMessages((m) => upd(m, (x) => ({ ...x, content: x.content + e.content })))
      else if (e.type === 'notice') setMessages((m) => upd(m, (x) => ({ ...x, content: x.content + e.content + '\n\n' })))
    })
    setMessages((m) => upd(m, (x) => ({ ...x, streaming: false })))
    setBusy(false)
  }

  const empty = messages.length === 0

  return (
    <div className="chat">
      <div className="page-head">
        <div>
          <h1>Ask VendorLens</h1>
          <div className="sub">Natural-language questions, answered from the rules engine.</div>
        </div>
      </div>

      {empty ? (
        <div className="chat-hero">
          <div className="hero-mark">✦</div>
          <div className="hero-title">What would you like to know?</div>
          <div className="hero-sub">Ask about any vendor or the whole portfolio. Try one of these:</div>
          <div className="hero-suggest">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => run(s)}>{s}</button>
            ))}
          </div>
        </div>
      ) : (
        <div className="chat-thread">
          {messages.map((m, i) => (
            m.role === 'user'
              ? <div className="msg user" key={i}><div className="bubble">{m.content}</div></div>
              : <AssistantMessage msg={m} key={i} />
          ))}
          <div ref={bottom} />
        </div>
      )}

      <div className="chat-foot">
        {!empty && (
          <div className="chat-chips">
            {SUGGESTIONS.map((s) => (
              <button key={s} title={s} disabled={busy} onClick={() => run(s)}>{s}</button>
            ))}
          </div>
        )}
        <div className="chat-input">
          <input
            placeholder="Ask a follow-up…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run(q)}
          />
          <button className="btn" disabled={busy || !q.trim()} onClick={() => run(q)}>
            {busy ? 'Thinking…' : 'Ask'}
          </button>
        </div>
      </div>
    </div>
  )
}
